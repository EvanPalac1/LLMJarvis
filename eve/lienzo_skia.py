"""Los tipos de modulo dibujados con Skia por GPU.

No es un motor paralelo completo y no pretende serlo. `lienzo.py` sigue siendo
el que manda: acomoda, decide que se repinta, maneja el modo Edit y el hit-test.
Aca vive solo el DIBUJO de los tipos que ya estan portados, que hoy es uno.

Por que uno y no trece: portar los trece de una serian 285 lineas escritas dos
veces antes de saber si el camino sirve en las cinco plataformas. Se porta el
mas caro --`onda`, que redibuja entero en cada cuadro porque depende del
microfono-- y se mide. Los que no estan portados los sigue haciendo Pillow, y
`PORTADOS` es lo que dice cuales son: un tipo que no este ahi no se rompe, se
dibuja como siempre.

El impuesto de tener dos caminos es real y esta medido: ~22 lineas por tipo. Lo
que lo justifica no son cuadros por segundo --con un modulo animando Pillow ya
da 7.1 ms de p95, que sobra-- sino el techo. Con Skia el dibujo cuesta 2 ms de
un cuadro de 10, o sea que queda el 80% libre para shaders, bloom y miles de
particulas. Por el camino de CPU eso no entra a ningun precio.
"""

import math

# Los tipos que este modulo sabe dibujar. Lo consulta `lienzo.py` antes de
# mandarle nada: lo que no este aca lo dibuja Pillow, sin ruido.
PORTADOS = ("onda", "particulas")


def _barras(lienzo, sup, modulo, muestras, ancho, alto, pincel):
    """El estilo `barras`: una columna por muestra, creciendo desde abajo."""
    n = max(1, len(muestras))
    paso = ancho / n
    grosor = max(1.0, paso * 0.6)
    for i, v in enumerate(muestras):
        h = max(1.0, float(v) * alto)
        x = i * paso + (paso - grosor) / 2
        lienzo.drawRect(sup.skia.Rect(x, alto - h, x + grosor, alto), pincel)


def _espejo(lienzo, sup, modulo, muestras, ancho, alto, pincel):
    """El estilo `espejo`: crece desde el centro hacia arriba y abajo."""
    n = max(1, len(muestras))
    paso = ancho / n
    grosor = max(1.0, paso * 0.6)
    medio = alto / 2
    for i, v in enumerate(muestras):
        h = max(1.0, float(v) * medio)
        x = i * paso + (paso - grosor) / 2
        lienzo.drawRect(sup.skia.Rect(x, medio - h, x + grosor, medio + h), pincel)


def _linea(lienzo, sup, modulo, muestras, ancho, alto, pincel):
    """El estilo `linea`: una polilinea suave. Es donde Skia se nota."""
    n = max(2, len(muestras))
    paso = ancho / (n - 1)
    camino = sup.skia.Path()
    medio = alto / 2
    for i, v in enumerate(muestras):
        y = medio - (float(v) - 0.5) * alto
        if i == 0:
            camino.moveTo(0, y)
        else:
            camino.lineTo(i * paso, y)
    trazo = sup.skia.Paint(pincel)
    trazo.setStyle(sup.skia.Paint.kStroke_Style)
    trazo.setStrokeWidth(max(1.5, alto / 40))
    trazo.setStrokeCap(sup.skia.Paint.kRound_Cap)
    trazo.setStrokeJoin(sup.skia.Paint.kRound_Join)
    lienzo.drawPath(camino, trazo)


def _puntos(lienzo, sup, modulo, muestras, ancho, alto, pincel):
    """El estilo `puntos`: un circulo por muestra."""
    n = max(1, len(muestras))
    paso = ancho / n
    radio = max(1.0, paso * 0.3)
    medio = alto / 2
    for i, v in enumerate(muestras):
        y = medio - (float(v) - 0.5) * alto
        lienzo.drawCircle(i * paso + paso / 2, y, radio, pincel)


ESTILOS = {"barras": _barras, "espejo": _espejo, "linea": _linea,
           "puntos": _puntos}


def pintar_onda(sup, modulo, estado, ahora, ancho, alto, rgba):
    """La onda del microfono, por GPU.

    Recibe la superficie ya activa --el contexto lo maneja el widget-- y las
    coordenadas ya resueltas por `lienzo.py`. Esta funcion no sabe donde esta el
    modulo ni cuando toca repintarlo: eso sigue siendo de quien manda.
    """
    lienzo = sup.lienzo
    cuantas = max(4, int(modulo.get("muestras", 48) or 48))
    crudas = list(estado.get("onda") or [])
    if crudas:
        # Remuestreo lineal a la cantidad pedida, igual que hace el camino de
        # Pillow: la cantidad de muestras es una preferencia del usuario y no
        # tiene por que coincidir con lo que entrego el microfono.
        paso = len(crudas) / cuantas
        muestras = [crudas[min(len(crudas) - 1, int(i * paso))]
                    for i in range(cuantas)]
    else:
        # Sin audio, una onda de reposo. Que quede QUIETA seria indistinguible
        # de un modulo roto, asi que respira despacio.
        nivel = float(estado.get("nivel", 0.0) or 0.0)
        muestras = [0.5 + 0.12 * math.sin(ahora * 2 + i / 3) * (0.3 + nivel)
                    for i in range(cuantas)]

    pincel = sup.pincel(rgba)
    dibujar = ESTILOS.get(str(modulo.get("estilo", "barras")), _barras)
    dibujar(lienzo, sup, modulo, muestras, ancho, alto, pincel)


# Cuantos grupos de transparencia para las particulas. Skia dibuja en lote con
# UN pincel, y el pincel tiene un solo alpha, asi que para que se apaguen con la
# edad hay que agrupar. Ocho es donde deja de notarse el escalon: con cuatro se
# ve el salto, con dieciseis se pagan el doble de llamadas sin ganar nada.
GRUPOS_ALFA = 8


def pintar_particulas(sup, modulo, sistema, ancho, alto, rgba):
    """Las particulas, en lote y como circulos de verdad.

    El camino de Pillow pinta UN PIXEL por particula --es lo unico que sale
    barato sobre la CPU-- y por eso se ven como polvo. Aca son circulos con
    tamaño, que es la diferencia que se nota a simple vista y la razon principal
    para tener este camino.

    Se dibujan en LOTE: `drawPoints` con el cap redondo manda las N posiciones
    de una. Quinientas llamadas sueltas a `drawCircle` costarian quinientas
    idas al driver, que es justo lo que se venia a evitar.

    La fisica no se toca: es `lienzo.Particulas`, la misma de numpy que ya
    estaba. Tener dos simuladores seria tener dos comportamientos.
    """
    import numpy as np

    lienzo = sup.lienzo
    pos = sistema.pos
    edad = sistema.edad
    if not len(pos):
        return

    tam = max(1.5, min(ancho, alto) / 60.0)
    # Un pincel por grupo de transparencia, y `drawPoints` por grupo. Ocho
    # llamadas en vez de quinientas.
    grupo = np.clip(((1.0 - edad) * GRUPOS_ALFA).astype(int), 0, GRUPOS_ALFA - 1)
    for g in range(GRUPOS_ALFA):
        cuales = pos[grupo == g]
        if not len(cuales):
            continue
        alfa = int(rgba[3] * (g + 1) / GRUPOS_ALFA)
        if alfa <= 2:
            continue
        pincel = sup.pincel((rgba[0], rgba[1], rgba[2], alfa))
        pincel.setStrokeWidth(tam)
        pincel.setStrokeCap(sup.skia.Paint.kRound_Cap)
        lienzo.drawPoints(
            sup.skia.Canvas.kPoints_PointMode,
            [sup.skia.Point(float(x), float(y)) for x, y in cuales],
            pincel)


class LienzoSkia:
    """Dibuja una lista de modulos sobre UNA superficie de GPU.

    Es un lienzo paralelo y no un enganche adentro de `Lienzo`, y la razon es
    estructural: `Lienzo.pintar()` devuelve una imagen de PIL por modulo, y todo
    lo que Skia gana es por NO pasar por ahi. Traer el dibujo de vuelta de la GPU
    a un `PIL.Image` cuesta 31 ms medidos --mas que dibujar la escena entera con
    Pillow-- asi que un motor de GPU que produzca imagenes de CPU es mas lento
    que no tener motor de GPU.

    Lo que se paga por esa decision: este lienzo no comparte el `_items` de
    tkinter, o sea que el modo Edit --hit-test, seleccion, orden de dibujo-- no
    funciona aca todavia. Es sabido y esta anotado, no olvidado.
    """

    def __init__(self, superficie, cfg, paleta):
        self.sup = superficie
        self.cfg = cfg
        self.paleta = paleta
        # Un simulador por modulo, igual que en el camino de Pillow: las
        # particulas tienen estado y perderlo en cada cuadro las haria titilar.
        self._sistemas: dict = {}

    def aplicar(self, cfg, paleta):
        self.cfg = cfg
        self.paleta = paleta

    def _rgba(self, modulo):
        """El color del modulo como (r, g, b, a), desde la paleta del tema."""
        rol = str(modulo.get("color", "texto")) or "texto"
        crudo = self.paleta.get(rol) or self.paleta.get("texto") or "#ffffff"
        crudo = crudo.lstrip("#")
        if len(crudo) == 3:
            crudo = "".join(c * 2 for c in crudo)
        try:
            r, g, b = (int(crudo[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            r, g, b = 255, 255, 255
        opac = max(0, min(100, int(modulo.get("opacidad", 100) or 100)))
        return (r, g, b, int(255 * opac / 100))

    def _sistema(self, modulo, ancho, alto):
        """El simulador de este modulo, creado una vez y avanzado por cuadro."""
        from .lienzo import Particulas

        ident = modulo["id"]
        cuantas = int(modulo.get("cantidad", 120) or 120)
        firma = (ancho, alto, cuantas)
        guardado = self._sistemas.get(ident)
        if guardado is None or guardado[0] != firma:
            # Se rehace solo si cambio el tamaño o la cantidad. Rehacerlo por
            # cuadro haria titilar las particulas, y guardar uno por firma sin
            # borrar el anterior dejaria basura cada vez que se redimensiona.
            sistema = Particulas(cuantas, ancho, alto)
            self._sistemas[ident] = (firma, sistema)
        else:
            sistema = guardado[1]
        sistema.avanzar(1 / 60.0,
                        float(modulo.get("vida", 1.0) or 1.0),
                        float(modulo.get("gravedad", 40) or 40),
                        0.0)
        return sistema

    def dibujar(self, lista, estado, ahora=None):
        """Un cuadro entero. Devuelve cuantos modulos dibujo de verdad.

        Los tipos que no estan en `PORTADOS` se saltan en silencio: mezclar los
        dos motores en la misma superficie no se puede, asi que mientras la
        portacion este a medias este lienzo dibuja lo que sabe. Devolver la
        cuenta es lo que permite que quien lo use se entere de que se salteo
        algo, en vez de mostrar una ventana a medias sin decir nada.
        """
        import time as _t

        ahora = _t.monotonic() if ahora is None else ahora
        fondo = (self.paleta.get("fondo") or "#101010").lstrip("#")
        try:
            r, g, b = (int(fondo[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            r, g, b = 16, 16, 16
        self.sup.limpiar((r, g, b, 255))

        hechos = 0
        lienzo = self.sup.lienzo
        for modulo in sorted(lista, key=lambda m: int(m.get("z", 0) or 0)):
            if modulo.get("tipo") not in PORTADOS:
                continue
            ancho = int(modulo.get("ancho", 200) or 200)
            alto = int(modulo.get("alto", 100) or 100)
            # `save`/`restore` con `translate`: cada modulo dibuja en (0,0) sin
            # saber donde esta, igual que en el camino de Pillow, donde recibe
            # una imagen de su propio tamaño.
            lienzo.save()
            lienzo.translate(float(modulo.get("x", 0) or 0),
                             float(modulo.get("y", 0) or 0))
            lienzo.clipRect(self.sup.skia.Rect(0, 0, ancho, alto))
            if modulo["tipo"] == "particulas":
                pintar_particulas(self.sup, modulo,
                                  self._sistema(modulo, ancho, alto),
                                  ancho, alto, self._rgba(modulo))
            else:
                pintar_onda(self.sup, modulo, estado, ahora, ancho, alto,
                            self._rgba(modulo))
            lienzo.restore()
            hechos += 1
        self.sup.presentar()
        return hechos
