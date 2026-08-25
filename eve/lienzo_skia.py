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
# Los que muestran texto largo: mismo dibujo, distinta fuente de datos.
PARRAFOS = ("lector", "documento", "historial", "acciones")

PORTADOS = ("onda", "particulas", "texto", "reloj", "boton",
            "icono", "contexto", "grafo", "lottie") + PARRAFOS


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




def imagen_desde_pil(sup, img):
    """Un `skia.Image` a partir de un `PIL.Image` RGBA.

    Es el puente que necesitan `icono` y `lottie`: los dos producen su contenido
    con Pillow --uno lee archivos y hojas de sprites, el otro rasteriza vectores
    con rlottie-- y eso no tiene por que reescribirse para la GPU. `imagenes.py`
    ya resuelve formatos, cuadros, atlas y cache por sha1; duplicarlo en Skia
    seria mantener dos lectores de PNG.

    La subida a la GPU cuesta, y por eso quien la use tiene que cachear el
    `skia.Image` mientras el contenido no cambie. Aca no se cachea a proposito:
    esta funcion no sabe cuando el de arriba cambio de cuadro.
    """
    if img is None:
        return None
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    datos = sup.skia.Data.MakeWithoutCopy(img.tobytes())
    info = sup.skia.ImageInfo.Make(img.width, img.height,
                                   sup.skia.kRGBA_8888_ColorType,
                                   sup.skia.kUnpremul_AlphaType)
    return sup.skia.Image.MakeRasterData(info, datos, img.width * 4)


def pintar_icono(sup, modulo, ancho, alto, acento, panel, foto=None):
    """La figura parametrica del cartel, y encima la imagen si hay.

    Mismos parametros que el otro camino --`lados` y el radio-- porque es la
    misma figura: menos de 3 lados es un circulo, y de ahi para arriba un
    poligono regular con la punta arriba. Que las dos den la MISMA forma es lo
    que hace que cambiar de motor no cambie el diseño.

    El relleno solo va cuando NO hay imagen: con imagen, queda como un disco de
    color atras que el cartel de siempre no tiene.
    """
    import math

    lienzo = sup.lienzo
    cx, cy = ancho / 2.0, alto / 2.0
    radio = max(2.0, min(cx, cy) - 2.0)
    lados = int(modulo.get("lados", 6) or 6)

    if foto is None:
        relleno = sup.pincel(panel)
        if lados < 3:
            lienzo.drawCircle(cx, cy, radio, relleno)
        else:
            lienzo.drawPath(_poligono(sup, cx, cy, radio, lados), relleno)

    borde = sup.pincel(acento)
    borde.setStyle(sup.skia.Paint.kStroke_Style)
    borde.setStrokeWidth(2.0)
    if lados < 3:
        lienzo.drawCircle(cx, cy, radio, borde)
    else:
        lienzo.drawPath(_poligono(sup, cx, cy, radio, lados), borde)

    # La imagen va ENCIMA de la figura, como en el cartel de siempre.
    if foto is not None:
        lienzo.drawImageRect(foto, sup.skia.Rect(0, 0, ancho, alto))


def _poligono(sup, cx, cy, radio, lados):
    import math

    camino = sup.skia.Path()
    for i in range(lados):
        angulo = 2 * math.pi * i / lados - math.pi / 2
        x, y = cx + radio * math.cos(angulo), cy + radio * math.sin(angulo)
        if i == 0:
            camino.moveTo(x, y)
        else:
            camino.lineTo(x, y)
    camino.close()
    return camino


def pintar_contexto(sup, modulo, partes, ancho, alto, colores, texto_rgba,
                    familia="", por_punto=96.0 / 72.0):
    """El medidor: lo unico que muestra un numero medido y no un adorno.

    Dos formas, igual que en el otro camino. En `numeros`, el color va en un
    cuadradito y el texto SIEMPRE en el color de texto: pintar la linea entera
    del color de su tramo dejaba dos de las cinco filas ilegibles, porque el
    ciclo llega a `borde` y a `texto_tenue`, que existen para cosas que no se
    leen.
    """
    lienzo = sup.lienzo
    total = sum(partes.values()) or 1
    ordenadas = sorted(partes.items(), key=lambda par: -par[1])

    if str(modulo.get("detalle")) == "numeros":
        f = fuente(sup, 9, familia, por_punto=por_punto)
        m = f.getMetrics()
        y = 0.0
        for i, (nombre, valor) in enumerate(ordenadas[:5]):
            lienzo.drawRect(sup.skia.Rect(0, y + 2, 8, y + 10),
                            sup.pincel(colores[i % len(colores)]))
            lienzo.drawString(f"{nombre}: {valor}", 13, y - m.fAscent, f,
                              sup.pincel(texto_rgba))
            y += 15
        return

    x = 0.0
    for i, (_, valor) in enumerate(ordenadas):
        w = ancho * valor / total
        lienzo.drawRect(sup.skia.Rect(x, 0, x + w, alto),
                        sup.pincel(colores[i % len(colores)]))
        x += w


def pintar_grafo(sup, guardado, ancho, alto, borde, acento, texto_rgba, vacio,
                 familia="", por_punto=96.0 / 72.0):
    """Lo que Eve hizo: herramientas, y las que salen una detras de otra.

    El acomodo lo hace `grafo.Acomodo`, el MISMO de siempre: es un sistema de
    particulas con resortes, no tiene nada de grafico, y tener dos daria dos
    dibujos distintos del mismo log.
    """
    lienzo = sup.lienzo
    nodos, aristas = guardado["nodos"], guardado["aristas"]
    if not nodos:
        f = fuente(sup, 10, familia, por_punto=por_punto)
        m = f.getMetrics()
        lienzo.drawString(vacio, 0, -m.fAscent, f, sup.pincel(texto_rgba))
        return

    pos = guardado["acomodo"].dibujables(guardado["t"])
    for a, b, veces in aristas:
        if a >= len(pos) or b >= len(pos):
            continue
        linea = sup.pincel(borde)
        linea.setStyle(sup.skia.Paint.kStroke_Style)
        linea.setStrokeWidth(float(max(1, min(int(veces), 3))))
        lienzo.drawLine(float(pos[a][0]), float(pos[a][1]),
                        float(pos[b][0]), float(pos[b][1]), linea)

    mayor = max(n["peso"] for n in nodos) or 1
    f = fuente(sup, 8, familia, por_punto=por_punto)
    m = f.getMetrics()
    for i, nodo in enumerate(nodos):
        if i >= len(pos):
            break
        x, y = float(pos[i][0]), float(pos[i][1])
        radio = 3.0 + 5.0 * (nodo["peso"] / mayor)
        lienzo.drawCircle(x, y, radio, sup.pincel(acento))
        if guardado.get("etiquetas", True):
            lienzo.drawString(str(nodo.get("nombre", ""))[:18],
                              x + radio + 3, y - m.fAscent / 2, f,
                              sup.pincel(texto_rgba))


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
        # tkinter mide en PUNTOS y Skia en PIXELES, igual que PIL. Mismo factor
        # que usa `Lienzo`, o el texto sale al 75% en una pantalla de 96 dpi.
        self.por_punto = 96.0 / 72.0
        self._fotos: dict = {}
        self._grafos: dict = {}
        # Los usan los metodos de `Lienzo` que se reusan sin ligar: ver
        # `_pil_de_lienzo`.
        self._fondos: dict = {}
        self._lotties: dict = {}

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

    def _marcar(self, lista, seleccion) -> None:
        """El contorno punteado de los modulos elegidos, en modo Edit."""
        lienzo = self.sup.lienzo
        pincel = self.sup.pincel(self._rol("acento"))
        pincel.setStyle(self.sup.skia.Paint.kStroke_Style)
        pincel.setStrokeWidth(2.0)
        # Punteado: 4 pintados, 3 en blanco, igual que el `dash=(4, 3)` del otro
        # camino. Que se vean IGUAL importa mas de lo que parece: es la unica
        # señal de que un modulo esta agarrado.
        pincel.setPathEffect(self.sup.skia.DashPathEffect.Make([4.0, 3.0], 0.0))
        for m in lista:
            if m["id"] not in seleccion:
                continue
            x, y = float(m.get("x", 0) or 0), float(m.get("y", 0) or 0)
            w = float(m.get("ancho", 0) or 0)
            h = float(m.get("alto", 0) or 0)
            lienzo.drawRect(self.sup.skia.Rect(x - 1, y - 1, x + w, y + h),
                            pincel)

    def _guia(self, medida) -> None:
        """El borde de otra superficie, punteado y tenue.

        Tenue y no con el acento a proposito: no es una seleccion, es una
        referencia, y con el mismo color que el contorno de agarre las dos
        cosas se leen como lo mismo.
        """
        try:
            ancho, alto = (float(x) for x in medida)
        except (TypeError, ValueError):
            return
        lienzo = self.sup.lienzo
        pincel = self.sup.pincel(self._rol("texto_tenue"))
        pincel.setStyle(self.sup.skia.Paint.kStroke_Style)
        pincel.setStrokeWidth(1.0)
        pincel.setPathEffect(self.sup.skia.DashPathEffect.Make([2.0, 4.0], 0.0))
        lienzo.drawRect(self.sup.skia.Rect(0, 0, ancho, alto), pincel)

    def vacio(self, texto: str, sub: str, ancho, alto) -> None:
        """El cartel de "no hay modulos", centrado.

        Existe por lo mismo que en el otro camino: el tablero viene sin modulos
        de fabrica, y abrirlo mostraba un rectangulo negro indistinguible de un
        programa que no arranco.
        """
        lienzo = self.sup.lienzo
        fam = str(self.cfg.get("ui_fuente", "") or "")
        for i, (linea, puntos, rol) in enumerate(
                ((texto, 13, "texto"), (sub, 10, "texto_tenue"))):
            if not linea:
                continue
            f = fuente(self.sup, puntos, fam, por_punto=self.por_punto)
            m = f.getMetrics()
            x = max(0.0, (ancho - f.measureText(linea)) / 2.0)
            y = alto / 2.0 + i * 26 - m.fAscent
            lienzo.drawString(linea, x, y, f, self.sup.pincel(self._rol(rol)))

    def _pil_de_lienzo(self, metodo, *args):
        """Llama a un metodo de `Lienzo` que solo necesita paleta y caches.

        `_cuadro_de` y `_pintar_lottie` no tocan nada de tkinter: leen
        `self.paleta` y guardan en `self._fondos` / `self._lotties`, que esta
        clase tambien tiene. Llamarlos sin ligar evita duplicar el lector de
        imagenes --formatos, cuadros de un GIF, atlas, cache por sha1-- y sobre
        todo evita que los dos motores muestren distinto el mismo archivo.

        Es reuso deliberado y no un accidente: si alguno de esos metodos
        empezara a necesitar el canvas, esto se rompe fuerte y en el acto, que
        es preferible a que se rompa despacio.
        """
        from . import lienzo as lienzo_mod

        return getattr(lienzo_mod.Lienzo, metodo)(self, *args)

    def _foto(self, modulo, ancho, alto):
        """La imagen del icono, ya subida a la GPU y cacheada.

        Se cachea el `skia.Image` por (ruta, tamaño, id del PIL): subir a la GPU
        cuesta, y un GIF que no avanzo no tiene por que volver a subirse.
        """
        if not str(modulo.get("imagen") or "").strip():
            return None
        try:
            img = self._pil_de_lienzo("_cuadro_de", modulo, ancho, alto, 100)
        except Exception:  # noqa: BLE001 - una imagen rota deja la figura sola
            return None
        if img is None:
            return None
        clave = (modulo["id"], ancho, alto, id(img))
        foto = self._fotos.get(clave)
        if foto is None:
            foto = imagen_desde_pil(self.sup, img)
            self._fotos = {clave: foto}   # uno por modulo: no crece
        return foto

    def _lottie(self, modulo, ahora, ancho, alto):
        """Un cuadro de la animacion, rasterizado por rlottie y subido a GPU.

        Se reusa `_pintar_lottie`, que compone sobre un PIL: se le pasa uno
        transparente y de ahi sale el cuadro. Asi el cache de la animacion --que
        evita parsear el JSON treinta veces por segundo-- es el mismo y no dos.
        """
        from PIL import Image

        base = Image.new("RGBA", (max(1, ancho), max(1, alto)), (0, 0, 0, 0))
        try:
            self._pil_de_lienzo("_pintar_lottie", base, modulo, ahora, ancho,
                                alto, 100)
        except Exception:  # noqa: BLE001 - un .json roto no tumba el cuadro
            return None
        if base.getchannel("A").getextrema()[1] == 0:
            return None   # no dibujo nada: no vale la pena subirlo
        foto = imagen_desde_pil(self.sup, base)
        if foto is not None:
            self.sup.lienzo.drawImageRect(
                foto, self.sup.skia.Rect(0, 0, ancho, alto))
        return None

    def _grafo(self, modulo, ancho, alto):
        """El grafo del log, releido cada tantos cuadros y acomodado siempre.

        Todo eso --relectura, acomodo y avance-- lo hace `grafo.estado`, que es
        el mismo para los dos renderers: tener una copia por cada uno daba dos
        dibujos distintos del mismo log, y de hecho dio el mismo bug dos veces.
        """
        from . import grafo as grafo_mod

        ident = modulo["id"]
        guardado = grafo_mod.estado(
            self._grafos.get(ident), int(modulo.get("cuantas", 150) or 150),
            self.cfg.get("workdirs"), ancho, alto)
        self._grafos[ident] = guardado
        guardado["etiquetas"] = bool(modulo.get("etiquetas", True))
        return guardado

    def _rol(self, nombre):
        """Un color de la paleta por su rol, en (r, g, b, a)."""
        crudo = (self.paleta.get(nombre) or "#ffffff").lstrip("#")
        if len(crudo) == 3:
            crudo = "".join(c * 2 for c in crudo)
        try:
            return (*(int(crudo[i:i + 2], 16) for i in (0, 2, 4)), 255)
        except ValueError:
            return (255, 255, 255, 255)

    def _texto_de(self, modulo, estado):
        """Lo que muestra un modulo `texto`, segun su `origen`."""
        origen = str(modulo.get("origen", "fijo") or "fijo")
        if origen == "fijo":
            return str(modulo.get("contenido", "") or "")
        if origen == "nombre":
            return str(self.cfg.get("assistant_name", "Eve"))
        return str(estado.get(origen, "") or "")

    def _parrafos_de(self, modulo, estado):
        """(texto, que decir si esta vacio, titulo) para los cuatro de parrafos.

        Todo sale de `estado`, que es de donde lo saca el camino de Pillow: este
        lienzo no lee la base ni el disco. Asi los dos motores muestran lo mismo
        POR CONSTRUCCION, y no porque alguien se acuerde de sincronizarlos.
        """
        from .textos import t as tr

        tipo = modulo["tipo"]
        if tipo == "lector":
            return (str(estado.get("pagina") or ""),
                    tr("todavia no lei ninguna pagina"), "")
        if tipo == "documento":
            doc = estado.get("documento") or {}
            titulo = (str(doc.get("titulo") or "")
                      if modulo.get("titulo", True) else "")
            return (str(doc.get("texto") or ""),
                    tr("pidele que te muestre algo"), titulo)
        if tipo == "historial":
            return (str(estado.get("historial") or ""),
                    tr("todavia no hablaron"), "")
        return (str(estado.get("acciones") or ""),
                tr("Eve no ejecuto nada todavia"), "")

    def _uno(self, modulo, estado, ahora, ancho, alto):
        """Reparte por tipo. Es el espejo de `Lienzo.pintar` del otro camino.

        Los cuatro de parrafos van por lista EXPLICITA y no por descarte. La
        primera version terminaba con un `return pintar_parrafos(...)` suelto, y
        eso hacia que cualquier tipo desconocido se dibujara como si fuera
        `acciones`: un `icono` mostrando el log de acciones. Peor que no
        dibujar, porque no se ve como un error sino como otro modulo.

        Lo destapo el test, que agrega un tipo a `PORTADOS` sin portarlo y
        exige que NO dibuje. Con el descarte, pasaba.
        """
        tipo = modulo["tipo"]
        rgba = self._rgba(modulo)
        fam = str(self.cfg.get("ui_fuente", "") or "")
        pp = self.por_punto

        if tipo == "onda":
            return pintar_onda(self.sup, modulo, estado, ahora, ancho, alto,
                               rgba)
        if tipo == "particulas":
            return pintar_particulas(self.sup, modulo,
                                     self._sistema(modulo, ancho, alto),
                                     ancho, alto, rgba)
        if tipo == "reloj":
            import time as _t

            texto = _t.strftime(str(modulo.get("formato", "%H:%M") or "%H:%M"))
            return pintar_texto(self.sup, modulo, texto, ancho, alto, rgba,
                                fam, pp)
        if tipo == "texto":
            return pintar_texto(self.sup, modulo,
                                self._texto_de(modulo, estado),
                                ancho, alto, rgba, fam, pp)
        if tipo == "boton":
            return pintar_boton(self.sup, modulo, ancho, alto, rgba,
                                self._rol("acento"), fam, pp)
        if tipo == "icono":
            return pintar_icono(self.sup, modulo, ancho, alto,
                                self._rol("acento"), self._rol("panel"),
                                self._foto(modulo, ancho, alto))
        if tipo == "lottie":
            return self._lottie(modulo, ahora, ancho, alto)
        if tipo == "contexto":
            colores = [self._rol("acento"), self._rol("acento2"),
                       self._rol("borde"), self._rol("texto_tenue")]
            return pintar_contexto(self.sup, modulo,
                                   estado.get("partes") or {}, ancho, alto,
                                   colores, self._rol("texto"), fam, pp)
        if tipo == "grafo":
            from .textos import t as tr

            return pintar_grafo(self.sup, self._grafo(modulo, ancho, alto),
                                ancho, alto, self._rol("borde"),
                                self._rol("acento"), self._rol("texto_tenue"),
                                tr("todavia no hice nada que graficar"),
                                fam, pp)

        # Los cuatro de parrafos: mismo dibujo, distinta fuente de datos.
        if tipo in PARRAFOS:
            texto, vacio, titulo = self._parrafos_de(modulo, estado)
            return pintar_parrafos(self.sup, modulo, texto, vacio, ancho, alto,
                                   rgba, self._rol("texto_tenue"), titulo,
                                   fam, pp)
        # Un tipo que no conocemos NO se dibuja. Llegar aca significa que
        # `PORTADOS` lo declara y este despachador no lo sabe pintar, que es un
        # error de programacion y no del usuario.
        return None

    def dibujar(self, lista, estado, ahora=None, seleccion=(), guia=None):
        """Un cuadro entero. Devuelve cuantos modulos dibujo de verdad.

        `guia` es un (ancho, alto) opcional: el borde de OTRA superficie
        dibujado encima de esta. Sirve para acomodar los modulos del cartel
        desde la ventana de actividad, que es mucho mas grande: sin ese
        rectangulo se acomoda a ciegas y lo que quede pasado el borde no se ve
        cuando el cartel se dibuja de verdad. El camino de Pillow lo hace con
        un item de canvas; aca hace falta pintarlo, porque no hay items.

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
        seleccion = set(seleccion or ())
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
            self._uno(modulo, estado, ahora, ancho, alto)
            lienzo.restore()
            hechos += 1
        # El contorno de lo elegido, DESPUES de todos los modulos: si se pintara
        # con cada uno, el de abajo se lo comeria el de arriba. En el camino de
        # Pillow eso lo resuelve un item de canvas con su propia etiqueta; aca,
        # el orden.
        if guia:
            self._guia(guia)
        if seleccion:
            self._marcar(lista, seleccion)
        self.sup.presentar()
        return hechos


# --------------------------------------------------------------------------- #
# Texto. Es lo que destraba la mitad de los tipos: `texto`, `reloj`, `boton` y
# los cuatro que muestran parrafos --lector, documento, historial, acciones--
# son todos el mismo problema con distinta fuente de datos.
#
# La tipografia sale del MISMO archivo que usa el camino de Pillow
# (`plataforma.archivo_de_fuente`). Dejar que Skia eligiera la suya habria dado
# dos caras distintas para el mismo tema segun que motor esté activo, que es
# justo lo que un motor intercambiable no puede hacer.
# --------------------------------------------------------------------------- #

_TIPOGRAFIAS: dict = {}


def fuente(sup, puntos: float, familia: str = "", negrita: bool = False,
           por_punto: float = 96.0 / 72.0):
    """Una `skia.Font` del tamaño pedido, cacheada por (familia, negrita).

    Los puntos se pasan a pixeles con el mismo factor que el otro camino:
    tkinter mide en PUNTOS y tanto PIL como Skia en PIXELES, y sin convertir el
    texto sale al 75% en una pantalla de 96 dpi.

    El `Typeface` se cachea y la `Font` no: crear el typeface parsea el archivo
    de la fuente, y hacerlo treinta veces por segundo seria pagar el parseo para
    dibujar un cuadro. La `Font` es una vista barata sobre el.
    """
    from . import plataforma

    clave = (familia, negrita)
    tf = _TIPOGRAFIAS.get(clave)
    if tf is None:
        ruta = ""
        try:
            ruta = plataforma.archivo_de_fuente(familia, negrita) if familia else ""
        except Exception:  # noqa: BLE001 - sin fuente del tema, la de Skia
            ruta = ""
        tf = sup.skia.Typeface.MakeFromFile(ruta) if ruta else None
        if tf is None:
            # Que la familia no exista no puede dejar el modulo en blanco: un
            # texto con otra tipografia se lee, uno que no se dibuja no.
            tf = sup.skia.Typeface("")
        _TIPOGRAFIAS[clave] = tf
    return sup.skia.Font(tf, max(6.0, float(puntos) * por_punto))


def cortar(texto: str, font, ancho: float) -> list[str]:
    """Parte una linea larga en varias que entren en el ancho.

    Es el mismo algoritmo que `lienzo._cortar`, con `measureText` en lugar de
    `textlength`. Se repite y no se comparte porque lo unico comun seria el
    bucle: quien mide es distinto, y abstraer eso costaria mas de lo que ahorra.
    """
    palabras = texto.split()
    if not palabras:
        return [""]
    lineas, actual = [], palabras[0]
    for palabra in palabras[1:]:
        prueba = actual + " " + palabra
        if font.measureText(prueba) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    lineas.append(actual)
    return lineas


def pintar_texto(sup, modulo, texto: str, ancho, alto, rgba, familia="",
                 por_punto=96.0 / 72.0):
    """Una linea de texto arriba a la izquierda. Sirve a `texto` y a `reloj`."""
    if not texto:
        return
    f = fuente(sup, float(modulo.get("tam", 14) or 14), familia,
               por_punto=por_punto)
    # `drawString` toma la LINEA BASE, no la esquina. Sin sumar el ascenso, el
    # texto queda cortado por arriba del modulo.
    metricas = f.getMetrics()
    sup.lienzo.drawString(texto, 0, -metricas.fAscent, f, sup.pincel(rgba))


def pintar_parrafos(sup, modulo, texto: str, vacio: str, ancho, alto, rgba,
                    tenue, titulo="", familia="", por_punto=96.0 / 72.0):
    """Texto largo cortado al ancho. Lo comparten los cuatro tipos de parrafos.

    Igual que en el otro camino: lector, documento, historial y acciones son el
    mismo problema --partir y recortar-- y tenerlo cuatro veces significaria
    arreglar el corte de lineas cuatro veces.
    """
    lienzo = sup.lienzo
    if not texto:
        f = fuente(sup, 10, familia, por_punto=por_punto)
        m = f.getMetrics()
        lienzo.drawString(vacio, 0, -m.fAscent, f, sup.pincel(tenue))
        return

    puntos = float(modulo.get("tam", 12) or 12)
    f = fuente(sup, puntos, familia, por_punto=por_punto)
    metricas = f.getMetrics()
    alto_linea = max(10.0, puntos * por_punto * 1.4)
    y = -metricas.fAscent
    pincel = sup.pincel(rgba)

    if titulo:
        neg = fuente(sup, puntos * 1.1, familia, negrita=True,
                     por_punto=por_punto)
        lienzo.drawString(titulo[:80], 0, y, neg, pincel)
        y += alto_linea * 1.4

    tope = int(modulo.get("lineas", 0) or 0)
    puestas = 0
    for parrafo in str(texto).splitlines():
        for linea in cortar(parrafo, f, ancho):
            if y > alto:            # se salio del modulo: no dibujar de gusto
                return
            if tope and puestas >= tope:
                return
            lienzo.drawString(linea, 0, y, f, pincel)
            y += alto_linea
            puestas += 1


def pintar_boton(sup, modulo, ancho, alto, rgba, acento, familia="",
                 por_punto=96.0 / 72.0):
    """Una caja con su etiqueta. Se dibuja igual este o no en modo Work.

    Que se VEA siempre y solo RESPONDA en Work es a proposito: un boton que
    desaparece al pasar a Edit haria imposible acomodarlo, que es justo lo que
    uno va a hacer en Edit.
    """
    lienzo = sup.lienzo
    r = sup.skia.Rect(0.5, 0.5, ancho - 0.5, alto - 0.5)
    radio = min(12.0, alto / 4.0)

    relleno = sup.pincel((acento[0], acento[1], acento[2], acento[3] // 6))
    lienzo.drawRoundRect(r, radio, radio, relleno)

    borde = sup.pincel(acento)
    borde.setStyle(sup.skia.Paint.kStroke_Style)
    borde.setStrokeWidth(1.5)
    lienzo.drawRoundRect(r, radio, radio, borde)

    etiqueta = str(modulo.get("etiqueta", "") or modulo.get("accion", ""))
    if not etiqueta:
        return
    f = fuente(sup, float(modulo.get("tam", 12) or 12), familia,
               por_punto=por_punto)
    m = f.getMetrics()
    x = max(0.0, (ancho - f.measureText(etiqueta)) / 2.0)
    y = (alto - (m.fDescent - m.fAscent)) / 2.0 - m.fAscent
    lienzo.drawString(etiqueta, x, y, f, sup.pincel(rgba))
