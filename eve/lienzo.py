"""Dibuja modulos sobre un tk.Canvas. Un item de canvas por modulo.

La arquitectura sale de una medicion, no de un gusto. Sobre un lienzo de
1200x800 con seis modulos con alpha y 500 particulas:

    capas del tamaño completo, PhotoImage nueva  ->  p95  53.1 ms   27 fps
    cada modulo compuesto en su rectangulo       ->  p95  26.9 ms   57 fps
    recomponiendo solo lo que cambio             ->  p95  21.7 ms   70 fps
    una PhotoImage POR MODULO, uno animado       ->  p95   7.1 ms  217 fps

De ahi salen tres reglas: cada modulo se compone en su propio rectangulo y nunca
en capas del tamaño del cuadro; solo se repinta el que cambio; y la PhotoImage
se crea una vez y despues se le hace `paste`, porque reasignarla cada cuadro
cuesta el doble.

DONDE ESTA EL TECHO, perfilado despues sobre seis modulos animando a la vez:

    ImageTk.paste (el puente PIL -> Tcl)    89% del cuadro
    dibujar los modulos de verdad            9%

O sea que el cuello no es lo que se dibuja sino subirlo al toolkit, y cuesta
~15 ms por modulo animado por cuadro. Un modulo animando entra comodo; seis
cuestan ~90 ms hagan lo que hagan adentro. Optimizar el dibujo no mueve ese
numero: la unica forma de bajarlo es no pasar por el puente, que es lo que hace
`lienzo_skia.py` escribiendo directo en el framebuffer de la GPU.

Y UNA SEGUNDA COSA, PEOR Y SIN EXPLICAR TODAVIA: el cuadro no cuesta lo mismo al
principio que despues. Con seis modulos animando arranca en ~78 ms y a los
cincuenta cuadros --menos de dos segundos de uso-- se planta en ~505, y ahi se
queda. Seis veces y media, sin volver.

Lo que YA se descarto, midiendo:

    el bucle apretado del banco   pasa igual a 30 fps con pausas
    la ventana tapada             pasa igual al frente y con foco
    que algo se acumule           los items quedan en 6, las imagenes de Tcl en 10,
                                  y los caches internos no crecen

El 91% del cuadro se va en `_tkinter.tkapp.call`, o sea del lado de Tcl, pero no
se encontro QUE crece ahi. Queda anotado como reproducible y sin causa, que es
mejor que una explicacion inventada:

    python main.py --bench-dibujo pillow

El camino de Skia no lo tiene: 1.96 ms de punta a punta, sin rampa.

De yapa, un item de canvas por modulo es lo que el modo Edit necesita igual para
saber en cual se hizo clic y para el orden de dibujo.

El alpha por modulo es composicion de PIL de verdad, no el `-alpha` de la
ventana: ese afecta a todo por igual y se llevaria puesto el texto.
"""

import math
import os
import time
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import grafo as grafo_mod
from .textos import t as tr
from . import imagenes, modulos, plataforma, tema

# Tope por modulo. Medido: con seis modulos animando 500 particulas cada uno el
# p95 sube a 32 ms, que en una maquina ARM es la mitad de los cuadros.
TOPE_PARTICULAS = 500


def _fuente(tam, familia="", negrita=False):
    """La tipografia elegida en el panel, en el tamaño pedido.

    tkinter pide la familia ("Constantia") y PIL pide el archivo
    ("constan.ttf"), y de uno no se deriva el otro: hay que preguntarle al
    sistema, que es lo que hace `plataforma.archivo_de_fuente`. Sin esto los
    modulos salian con la tipografia por defecto de PIL mientras el resto del
    cartel usaba la del tema, y la diferencia se veia de lejos.

    Si la familia no existe, `load_default` alcanza para que se lea algo: un
    cartel con otra tipografia es mejor que un cartel vacio.
    """
    tam = max(6, int(tam))
    ruta = plataforma.archivo_de_fuente(familia, negrita)
    if ruta:
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _rgba(color, opacidad=100):
    r, g, b = tema._rgb(color)
    return (r, g, b, max(0, min(255, int(255 * opacidad / 100))))


def _curva(x: float, easing: str) -> float:
    """Aplica la curva elegida a un valor de 0 a 1.

    `easing` estaba declarada en COMUNES, salia en el panel de todos los modulos
    y no la leia nadie. Ahora es la forma en que el nivel del microfono se
    convierte en movimiento: `lineal` sigue el volumen tal cual, `suave` ignora
    los ruiditos y exagera los picos, y `rebote` se pasa un poco de largo, que
    es lo que hace que algo parezca vivo y no una barra de progreso.
    """
    x = max(0.0, min(float(x), 1.0))
    if easing == "suave":
        return x * x * (3 - 2 * x)          # smoothstep
    if easing == "rebote":
        return x * (1.7 - 0.7 * x) if x < 1 else 1.0
    return x


class Particulas:
    """Un sistema de particulas por modulo, en numpy.

    Son aritmetica sobre un array y no objetos de canvas: 500 items de Tcl
    moviendose cuestan mucho mas que 500 filas de una matriz.
    """

    def __init__(self, cantidad, ancho, alto):
        self.n = max(1, min(int(cantidad), TOPE_PARTICULAS))
        self.ancho, self.alto = max(1, int(ancho)), max(1, int(alto))
        rng = np.random.default_rng(1234)
        self.pos = rng.random((self.n, 2)) * [self.ancho, self.alto]
        self.vel = (rng.random((self.n, 2)) - 0.5) * 40
        self.edad = rng.random(self.n)

    def avanzar(self, dt, vida, gravedad, empuje):
        self.vel[:, 1] += gravedad * dt
        self.pos += self.vel * dt * (0.5 + empuje * 2.0)
        self.edad += dt / max(0.05, vida)
        # Las que se pasaron de vida o se fueron del rectangulo vuelven a nacer.
        muertas = (
            (self.edad >= 1.0)
            | (self.pos[:, 0] < 0) | (self.pos[:, 0] >= self.ancho)
            | (self.pos[:, 1] < 0) | (self.pos[:, 1] >= self.alto)
        )
        cuantas = int(muertas.sum())
        if cuantas:
            rng = np.random.default_rng()
            self.pos[muertas] = rng.random((cuantas, 2)) * [self.ancho, self.alto]
            self.vel[muertas] = (rng.random((cuantas, 2)) - 0.5) * 40
            self.edad[muertas] = 0.0

    def pintar(self, img, color):
        px = np.array(img)
        xs = self.pos[:, 0].astype(np.int32)
        ys = self.pos[:, 1].astype(np.int32)
        dentro = (xs >= 0) & (xs < img.width) & (ys >= 0) & (ys < img.height)
        cuantas = int(dentro.sum())
        if not cuantas:
            return
        # Se apagan con la edad: sin eso aparecen y desaparecen de golpe.
        alfa = ((1.0 - self.edad) * color[3]).clip(0, 255).astype(np.uint8)
        px[ys[dentro], xs[dentro]] = np.column_stack([
            np.full(cuantas, color[0], np.uint8),
            np.full(cuantas, color[1], np.uint8),
            np.full(cuantas, color[2], np.uint8),
            alfa[dentro],
        ])
        img.paste(Image.fromarray(px, "RGBA"))


class Lienzo:
    """Mantiene una PhotoImage por modulo sobre un canvas de tkinter."""

    def __init__(self, canvas, cfg, prefijo_tema="hud"):
        self.canvas = canvas
        self.cfg = cfg
        self.prefijo = prefijo_tema
        self.paleta = tema.resolver(cfg, prefijo_tema)
        self.familia = self._familia(cfg)
        # tkinter mide las fuentes en PUNTOS y PIL en PIXELES. A 96 dpi, 19
        # puntos son 25 pixeles: sin convertir, todo el texto de los modulos
        # salia al 75% del tamaño que tiene en el cartel viejo.
        try:
            self.por_punto = float(canvas.winfo_fpixels("1i")) / 72.0
        except Exception:  # noqa: BLE001 - sin ventana todavia, 96 dpi
            self.por_punto = 96.0 / 72.0
        self._items = {}       # id -> [item, PhotoImage, firma, ancho, alto]
        self._particulas = {}
        self._fondos = {}
        # Las animaciones de Lottie, cacheadas por ruta: `from_file`
        # parsea el JSON entero y hacerlo treinta veces por segundo
        # seria pagar el parseo para dibujar un cuadro.
        self._lotties: dict = {}
        self._ondas = {}
        self._grafos = {}
        self._t0 = time.monotonic()

    def aplicar(self, cfg):
        """Config nueva: se re-lee la paleta y se olvidan las firmas."""
        self.cfg = cfg
        self.paleta = tema.resolver(cfg, self.prefijo)
        self.familia = self._familia(cfg)
        for datos in self._items.values():
            datos[2] = None

    def _fuente_pt(self, puntos, negrita=False):
        """Una fuente pedida en puntos, como la pide el resto del programa."""
        return _fuente(round(float(puntos) * self.por_punto), self.familia, negrita)

    def _familia(self, cfg):
        """La del prefijo, con la del panel de respaldo, como hace el tema."""
        return str(cfg.get(self.prefijo + "_fuente")
                   or cfg.get("ui_fuente") or "").strip()

    def olvidar(self, ident):
        datos = self._items.pop(ident, None)
        if datos:
            self.canvas.delete(datos[0])
        self._particulas.pop(ident, None)
        self._fondos.pop(ident, None)
        self._ondas.pop(ident, None)
        self._grafos.pop(ident, None)

    def dibujar(self, lista, estado):
        """Pinta los modulos visibles. Devuelve cuantos hubo que repintar."""
        from PIL import ImageTk

        ahora = time.monotonic() - self._t0
        vivos = set()
        repintados = 0
        for modulo in lista:
            ident = modulo["id"]
            if not modulos.visible(modulo, estado.get("estado", ""),
                                   estado.get("hover") == ident):
                self.olvidar(ident)
                continue
            vivos.add(ident)
            firma = self._firma(modulo, estado, ahora)
            datos = self._items.get(ident)
            if datos is not None and datos[2] == firma:
                continue   # no cambio nada: no se toca

            img = self.pintar(modulo, estado, ahora)
            if datos is None or [datos[3], datos[4]] != [img.width, img.height]:
                if datos is not None:
                    self.canvas.delete(datos[0])
                foto = ImageTk.PhotoImage(img)
                item = self.canvas.create_image(modulo["x"], modulo["y"],
                                                anchor="nw", image=foto)
                self._items[ident] = [item, foto, firma, img.width, img.height]
            else:
                # La PhotoImage se reusa: crear una nueva por cuadro cuesta el
                # doble, medido.
                datos[1].paste(img)
                datos[2] = firma
                self.canvas.coords(datos[0], modulo["x"], modulo["y"])
            repintados += 1

        for ident in [i for i in self._items if i not in vivos]:
            self.olvidar(ident)
        return repintados

    def _firma(self, modulo, estado, ahora):
        """Que tiene que cambiar para justificar repintar este modulo."""
        base = (modulo["x"], modulo["y"], modulo["ancho"], modulo["alto"],
                modulo["opacidad"], modulo["escala"], modulo["rotacion"],
                modulo["tinte"], modulo.get("color"))
        tipo = modulo["tipo"]
        if tipo in modulos.REACTIVOS:
            if modulo.get("fuente") == "microfono":
                # El nivel del microfono ya viaja al overlay a 10 Hz.
                return base + (round(estado.get("nivel", 0.0), 3), round(ahora, 2))
            return base + (round(ahora, 2),)
        if tipo == "reloj":
            return base + (time.strftime(str(modulo.get("formato", "%H:%M"))),)
        if tipo == "texto":
            return base + (self._texto_de(modulo, estado), modulo.get("tam"))
        if tipo == "contexto":
            return base + (str(estado.get("partes")), modulo.get("detalle"))
        if tipo == "grafo":
            return base + (round(ahora, 2),)
        if tipo == "lector":
            return base + (str(estado.get("pagina", ""))[:80], modulo.get("tam"))
        if tipo == "historial":
            return base + (round(ahora, 1), modulo.get("tam"),
                           modulo.get("lineas"), modulo.get("cuantos"))
        if tipo == "acciones":
            return base + (round(ahora, 1), modulo.get("tam"),
                           modulo.get("lineas"), modulo.get("cuantas"),
                           modulo.get("resultado"))
        if tipo == "boton":
            return base + (modulo.get("accion"), modulo.get("etiqueta"),
                           modulo.get("tam"))
        if tipo == "lottie":
            # El cuadro depende del reloj salvo que se haya fijado uno.
            fijo = int(modulo.get("cuadro", -1) or -1)
            return base + (modulo.get("archivo"),
                           fijo if fijo >= 0 else round(ahora * 2, 1))
        if tipo == "documento":
            doc = estado.get("documento") or {}
            # El `ts` va en la firma para que reemplazar un documento por otro
            # del mismo largo tambien repinte: sin eso, mostrar dos textos
            # parecidos seguidos dejaba el primero en pantalla.
            return base + (doc.get("ts"), str(doc.get("texto", ""))[:80],
                           modulo.get("tam"), modulo.get("lineas"),
                           modulo.get("desplazar"), modulo.get("titulo"))
        if tipo == "icono":
            # Un GIF, APNG, WebP o sprite sheet cambia solo; una imagen fija no.
            #
            # Aca habia dos errores en una linea. `_fondos` guarda la tupla
            # (clave, rutas, tiempos) que arma `_cuadro_de`, no un
            # `imagenes.Fondo`, asi que `fondo.hay()` tiraba AttributeError; y
            # aunque hubiera sido un Fondo, `hay` es una property y llamarla
            # habria fallado igual. Reventaba en el SEGUNDO cuadro de cualquier
            # icono con imagen --el primero pasa porque todavia no hay nada
            # cacheado-- y como ni `overlay.tick` ni `consola.tick` lo atajan,
            # se cortaba el `after` y el dibujo se congelaba entero.
            #
            # De paso, la condicion correcta es "tiene mas de un cuadro" y no
            # "tiene cuadros": con la vieja, un PNG quieto se declaraba animado
            # y se repintaba sesenta veces por segundo para mostrar lo mismo.
            guardado = self._fondos.get(modulo["id"])
            animado = bool(guardado and len(guardado[1]) > 1 and modulo.get("imagen"))
            return base + (modulo.get("imagen"), modulo.get("lados"),
                           round(ahora, 2) if animado else 0)
        return base

    def _color(self, modulo, opac, rol_por_defecto="texto"):
        """El color del modulo, por rol de la paleta."""
        rol = str(modulo.get("color") or rol_por_defecto)
        return _rgba(self.paleta.get(rol, self.paleta[rol_por_defecto]), opac)

    def _texto_de(self, modulo, estado=None):
        """Que dice este modulo de texto: algo fijo, o algo que pasa ahora.

        Es lo que reemplaza a la linea de subtitulo del cartel viejo, y de paso
        habilita mostrar lo que se escucho y lo que Eve esta contestando sin
        inventar un tipo de modulo por cada cosa.
        """
        estado = estado or {}
        origen = str(modulo.get("origen", "nombre"))
        if origen == "fijo":
            return str(modulo.get("contenido") or "")
        if origen == "detalle":
            return str(estado.get("detalle") or "")
        if origen in ("usuario", "eve"):
            return str(estado.get(origen) or "")
        return str(estado.get("titulo") or self.cfg.get("assistant_name", "Eve")).upper()

    # --- dibujo -----------------------------------------------------------

    def pintar(self, modulo, estado, ahora):
        """El modulo, como una imagen RGBA de su propio tamaño."""
        # `fuente = microfono` dejo de ser cosa de dos tipos. Antes solo la onda
        # y las particulas leian el nivel, asi que la perilla estaba en el panel
        # de todos los modulos y no hacia nada en ninguno de los otros seis. Con
        # esto late lo que sea: un GIF, un sprite sheet, un reloj, un PNG quieto.
        # Es lo que separa "tiene animaciones" de "reacciona a tu voz", y vale
        # para todo lo importado, que por definicion no puede calcular nada.
        crece = 1.0
        if str(modulo.get("fuente")) == "microfono" and modulo["tipo"] not in modulos.REACTIVOS:
            crece = 1.0 + _curva(float(estado.get("nivel") or 0.0),
                                 str(modulo.get("easing", "lineal"))) * 0.35
        ancho = max(1, int(modulo["ancho"] * modulo["escala"] / 100 * crece))
        alto = max(1, int(modulo["alto"] * modulo["escala"] / 100 * crece))
        img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
        dibujo = ImageDraw.Draw(img)
        opac = int(modulo["opacidad"])
        acento = _rgba(self.paleta["acento"], opac)
        tipo = modulo["tipo"]

        if tipo == "texto":
            dibujo.text((0, 0), self._texto_de(modulo, estado),
                        font=self._fuente_pt(modulo.get("tam", 16), negrita=True),
                        fill=self._color(modulo, opac))
        elif tipo == "reloj":
            dibujo.text((0, 0), time.strftime(str(modulo.get("formato", "%H:%M"))),
                        font=self._fuente_pt(18),
                        fill=self._color(modulo, opac))
        elif tipo == "icono":
            self._pintar_icono(img, dibujo, modulo, acento, opac)
        elif tipo == "onda":
            self._pintar_onda(dibujo, modulo, estado, ahora, ancho, alto, opac)
        elif tipo == "particulas":
            self._pintar_particulas(img, modulo, estado, ancho, alto, acento)
        elif tipo == "contexto":
            self._pintar_contexto(dibujo, modulo, estado, ancho, alto, opac)
        elif tipo == "grafo":
            self._pintar_grafo(dibujo, modulo, ancho, alto, opac)
        elif tipo == "lector":
            self._pintar_lector(dibujo, modulo, estado, ancho, alto, opac)
        elif tipo == "documento":
            self._pintar_documento(dibujo, modulo, estado, ancho, alto, opac)
        elif tipo == "lottie":
            self._pintar_lottie(img, modulo, ahora, ancho, alto, opac)
        elif tipo == "historial":
            self._pintar_parrafos(
                dibujo, modulo, ancho, alto, opac,
                texto=str(estado.get("historial") or ""),
                vacio=tr("todavia no hablaron"))
        elif tipo == "acciones":
            self._pintar_parrafos(
                dibujo, modulo, ancho, alto, opac,
                texto=str(estado.get("acciones") or ""),
                vacio=tr("Eve no ejecuto nada todavia"))
        elif tipo == "boton":
            self._pintar_boton(dibujo, modulo, ancho, alto, opac)

        if modulo.get("rotacion"):
            img = img.rotate(-float(modulo["rotacion"]), expand=False,
                             resample=Image.BICUBIC)
        if modulo.get("tinte"):
            capa = Image.new("RGBA", img.size, _rgba(str(modulo["tinte"]), 100))
            capa.putalpha(img.getchannel("A"))
            img = Image.blend(img, capa, 0.35)
        return img

    def _cuadro_de(self, modulo, ancho, alto, opac):
        """El cuadro que toca de la imagen del modulo, ya como imagen de PIL.

        `imagenes.Fondo` devuelve una PhotoImage de tkinter, que no sirve para
        componer: aca hace falta PIL. `procesar()` es el escalon de abajo y
        devuelve los PNG ya escalados y cacheados por firma, animados incluidos.
        """
        ruta = str(modulo.get("imagen") or "").strip()
        if not ruta:
            return None
        clave = (ruta, ancho, alto, opac)
        guardado = self._fondos.get(modulo["id"])
        if guardado is None or guardado[0] != clave:
            rutas, tiempos = imagenes.procesar(
                ruta, ancho, alto, "recortar", opac, 0,
                self.paleta["panel"], self.paleta["acento"], conservar_alpha=True)
            guardado = (clave, rutas, tiempos)
            self._fondos[modulo["id"]] = guardado
        _, rutas, tiempos = guardado
        if not rutas:
            return None
        indice = 0
        if len(rutas) > 1:
            total = sum(tiempos) or 100
            # `velocidad` es un multiplicador de tiempo, y hasta ahora lo leian
            # solo la onda y las particulas: acelerar una animacion importada
            # era algo que el README prometia y el codigo no hacia. Se aplica
            # corriendo el reloj mas rapido, no re-escribiendo las duraciones,
            # asi el cache de cuadros sigue sirviendo igual.
            veloc = max(0.05, min(float(modulo.get("velocidad", 1.0) or 1.0), 20.0))
            transcurrido = int(time.monotonic() * 1000 * veloc) % total
            acumulado = 0
            for i, ms in enumerate(tiempos):
                acumulado += ms
                if transcurrido < acumulado:
                    indice = i
                    break
        try:
            return Image.open(rutas[indice]).convert("RGBA")
        except OSError:
            return None

    def _pintar_icono(self, img, dibujo, modulo, acento, opac):
        lados = int(modulo.get("lados", 6))
        cx, cy = img.width / 2, img.height / 2
        radio = max(2, min(cx, cy) - 2)
        # Relleno ademas del contorno: el icono del cartel viejo es una figura
        # solida con borde, y dejarlo hueco era la diferencia mas visible al
        # pasar a modulos.
        # Solo si NO hay imagen: cuando la hay, la imagen es el contenido y el
        # relleno le queda como un disco de color atras que el cartel viejo no
        # tiene.
        foto = self._cuadro_de(modulo, img.width, img.height, opac)
        relleno = None if foto is not None else _rgba(
            tema.mezclar(self.paleta["panel"], self.paleta["acento"], 0.18), opac)
        if lados < 3:
            dibujo.ellipse([cx - radio, cy - radio, cx + radio, cy + radio],
                           fill=relleno, outline=acento, width=2)
        else:
            puntos = [(cx + radio * math.cos(2 * math.pi * i / lados - math.pi / 2),
                       cy + radio * math.sin(2 * math.pi * i / lados - math.pi / 2))
                      for i in range(lados)]
            dibujo.polygon(puntos, fill=relleno, outline=acento)
        # La imagen va ENCIMA de la figura, como en el cartel de siempre.
        if foto is not None:
            img.alpha_composite(foto)

    def _pintar_onda(self, dibujo, modulo, estado, ahora, ancho, alto, opac):
        """La onda es el historial del microfono, no una animacion inventada.

        El cartel viejo guarda los ultimos N niveles suavizados y los dibuja
        corridos: por eso se ve como una senal y no como un patron repetido.
        Copiar ese modelo era la unica forma de que las dos versiones se
        parecieran de verdad.
        """
        n = max(4, int(modulo.get("muestras", 56)))
        historial = self._ondas.get(modulo["id"])
        if historial is None or historial.maxlen != n:
            historial = deque([0.0] * n, maxlen=n)
            self._ondas[modulo["id"]] = historial
        if modulo.get("fuente") == "microfono":
            objetivo = float(estado.get("nivel", 0.0) or 0.0)
        else:
            # Sin microfono, algo que se mueva para que se pueda ver.
            objetivo = abs(math.sin(ahora * 2 * float(modulo.get("velocidad", 1.0)))) * 0.6
        suave = historial[-1] + (objetivo - historial[-1]) * 0.35
        historial.append(suave)

        estilo = str(modulo.get("estilo", "barras"))
        if estilo == "ninguna":
            return
        paso = ancho / n
        grosor = max(1, int(paso * 0.45))
        medio = alto / 2
        puntos = []
        for i, v in enumerate(historial):
            px = i * paso + paso / 2
            h = max(1.0, min(v, 1.0) * alto)
            color = _rgba(tema.mezclar(self.paleta["acento2"], self.paleta["acento"],
                                       min(v, 1.0)), opac)
            if estilo == "barras":
                dibujo.line([px, medio - h / 2, px, medio + h / 2], fill=color, width=grosor)
            elif estilo == "espejo":
                hueco = alto * 0.09
                dibujo.line([px, medio - hueco - h / 2, px, medio - hueco],
                            fill=color, width=grosor)
                dibujo.line([px, medio + hueco, px, medio + hueco + h / 2],
                            fill=color, width=grosor)
            elif estilo == "puntos":
                rr = max(1.0, grosor * (0.35 + v))
                dibujo.ellipse([px - rr, medio - rr, px + rr, medio + rr], fill=color)
            else:
                puntos.append((px, medio - h / 2))
        if puntos and len(puntos) >= 2:
            dibujo.line(puntos, fill=_rgba(self.paleta["acento"], opac), width=2,
                        joint="curve")

    def _pintar_particulas(self, img, modulo, estado, ancho, alto, acento):
        sistema = self._particulas.get(modulo["id"])
        if sistema is None or (sistema.ancho, sistema.alto) != (ancho, alto):
            sistema = Particulas(modulo.get("cantidad", 200), ancho, alto)
            self._particulas[modulo["id"]] = sistema
        if modulo.get("fuente") == "microfono":
            empuje = float(estado.get("nivel", 0.0) or 0.0)
        else:
            empuje = 0.2
        sistema.avanzar(1 / 30 * float(modulo.get("velocidad", 1.0)),
                        float(modulo.get("vida", 1.5)),
                        float(modulo.get("gravedad", 0.0)), empuje)
        sistema.pintar(img, acento)

    def _pintar_grafo(self, dibujo, modulo, ancho, alto, opac):
        """Lo que Eve hizo: herramientas y las que salen una detras de otra.

        Se relee cada tantos cuadros y no en todos: leer el log en cada cuadro
        serian treinta consultas por segundo a una base que casi nunca cambia.
        El acomodado si avanza siempre, que es lo que se ve moverse.
        """
        guardado = self._grafos.get(modulo["id"])
        cuantas = int(modulo.get("cuantas", 150))
        if guardado is None or guardado["cuadros"] > 90 or guardado["tam"] != (ancho, alto):
            nodos, aristas = grafo_mod.leer(cuantas, self.cfg.get("workdirs"))
            guardado = {"nodos": nodos, "aristas": aristas, "cuadros": 0,
                        "tam": (ancho, alto),
                        "acomodo": grafo_mod.Acomodo(len(nodos), ancho, alto)}
            self._grafos[modulo["id"]] = guardado
        guardado["cuadros"] += 1
        nodos, aristas = guardado["nodos"], guardado["aristas"]
        if not nodos:
            dibujo.text((0, 0), "todavia no hice nada que graficar",
                        font=self._fuente_pt(10),
                        fill=_rgba(self.paleta["texto_tenue"], opac))
            return
        guardado["acomodo"].avanzar(aristas)
        pos = guardado["acomodo"].pos

        for a, b, veces in aristas:
            if a >= len(pos) or b >= len(pos):
                continue
            dibujo.line([tuple(pos[a]), tuple(pos[b])],
                        fill=_rgba(self.paleta["borde"], opac),
                        width=max(1, min(int(veces), 3)))
        mayor = max(n["peso"] for n in nodos)
        fuente = self._fuente_pt(8)
        for i, nodo in enumerate(nodos):
            if i >= len(pos):
                break
            r = 4 + 8 * (nodo["peso"] / mayor)
            x, y = pos[i]
            # Los proyectos se dibujan cuadrados y con el otro acento: de un
            # vistazo se separa DONDE trabajo de QUE uso para trabajar.
            if nodo.get("clase") == "proyecto":
                color = _rgba(self.paleta["acento2"], opac)
                dibujo.rectangle([x - r, y - r, x + r, y + r], fill=color)
            else:
                color = _rgba(tema.mezclar(self.paleta["acento2"], self.paleta["acento"],
                                           nodo["peso"] / mayor), opac)
                dibujo.ellipse([x - r, y - r, x + r, y + r], fill=color)
            if modulo.get("etiquetas", True):
                dibujo.text((x + r + 3, y - 5), nodo["nombre"], font=fuente,
                            fill=_rgba(self.paleta["texto"], opac))

    def _pintar_lector(self, dibujo, modulo, estado, ancho, alto, opac):
        """El texto de la ultima pagina leida, cortado al ancho del modulo."""
        self._pintar_parrafos(
            dibujo, modulo, ancho, alto, opac,
            texto=str(estado.get("pagina") or ""),
            vacio=tr("pidele que lea una pagina"))

    def _pintar_lottie(self, img, modulo, ahora, ancho, alto, opac):
        """Un cuadro de una animacion de Lottie, pegado sobre la capa.

        Rasteriza a `PIL.Image` y entra por el mismo camino que todo lo demas.
        La animacion se cachea por ruta: `LottieAnimation.from_file` parsea el
        JSON entero, y hacerlo treinta veces por segundo seria pagar el parseo
        para dibujar un cuadro.

        El import va adentro y envuelto: `rlottie-python` solo la necesita quien
        ponga un modulo de este tipo, y una libreria que falta no puede impedir
        que Eve arranque --a lo sumo deja un modulo en blanco.
        """
        ruta = str(modulo.get("archivo") or "")
        if not ruta or not os.path.exists(ruta):
            return
        anim = self._lotties.get(ruta)
        if anim is None:
            try:
                from rlottie_python import LottieAnimation
            except ImportError:
                return
            try:
                anim = LottieAnimation.from_file(ruta)
            except Exception:  # noqa: BLE001 - un .json roto no tumba el cuadro
                self._lotties[ruta] = False
                return
            self._lotties[ruta] = anim
        if anim is False:
            return

        try:
            total = max(1, int(anim.lottie_animation_get_totalframe()))
            fijo = int(modulo.get("cuadro", -1) or -1)
            if fijo >= 0:
                cuadro = min(fijo, total - 1)
            else:
                fps = float(anim.lottie_animation_get_framerate() or 30.0)
                cuadro = int(ahora * fps * float(modulo.get("velocidad", 1.0))) % total
            marco = anim.render_pillow_frame(frame_num=cuadro, width=ancho, height=alto)
        except Exception:  # noqa: BLE001
            return
        marco = marco.convert("RGBA")
        if opac < 100:
            alfa = marco.getchannel("A").point(lambda v: int(v * opac / 100))
            marco.putalpha(alfa)
        img.alpha_composite(marco)

    def _pintar_documento(self, dibujo, modulo, estado, ancho, alto, opac):
        """Lo que Eve mostro con `E mostrar`: texto, un .txt, un .md o un HTML.

        Mismo cortado de lineas que el lector --son el mismo problema-- y ademas
        el titulo arriba, con el acento, porque un documento sin titulo obliga a
        leer tres renglones para saber que estas mirando.
        """
        doc = estado.get("documento") or {}
        texto = str(doc.get("texto") or "")
        titulo = str(doc.get("titulo") or "") if modulo.get("titulo", True) else ""
        self._pintar_parrafos(
            dibujo, modulo, ancho, alto, opac, texto=texto, titulo=titulo,
            desde=int(modulo.get("desplazar", 0) or 0),
            vacio=tr("pidele que te muestre algo"))

    def _pintar_boton(self, dibujo, modulo, ancho, alto, opac):
        """Un boton: marco redondeado y la etiqueta centrada.

        Se dibuja con borde y no relleno para que se lea encima de cualquier
        fondo --el tablero puede tener una imagen debajo-- y para que se note
        que es algo que se toca y no un cartel mas.
        """
        from . import modulos as mods

        accion = str(modulo.get("accion", "panel"))
        etiqueta = str(modulo.get("etiqueta") or "").strip()
        if not etiqueta:
            etiqueta = mods.ACCIONES_BOTON.get(accion, accion)
        borde = _rgba(self.paleta["acento"], opac)
        radio = max(2, min(12, alto // 4))
        try:
            dibujo.rounded_rectangle([0, 0, ancho - 1, alto - 1], radius=radio,
                                     outline=borde, width=2)
        except AttributeError:  # Pillow viejo, sin esquinas redondeadas
            dibujo.rectangle([0, 0, ancho - 1, alto - 1], outline=borde, width=2)
        fuente = self._fuente_pt(modulo.get("tam", 12))
        caja = dibujo.textbbox((0, 0), etiqueta, font=fuente)
        x = max(4, (ancho - (caja[2] - caja[0])) // 2)
        y = max(2, (alto - (caja[3] - caja[1])) // 2 - caja[1])
        dibujo.text((x, y), etiqueta, font=fuente,
                    fill=_rgba(self.paleta["texto"], opac))

    def _pintar_parrafos(self, dibujo, modulo, ancho, alto, opac, texto,
                         vacio, titulo="", desde=0):
        """Texto largo cortado al ancho del modulo. Lo comparten dos tipos.

        El lector y el documento son el mismo problema --parrafos que hay que
        partir y recortar-- y tenerlo dos veces significaba arreglar el corte de
        lineas dos veces.
        """
        if not texto:
            dibujo.text((0, 0), vacio, font=self._fuente_pt(10),
                        fill=_rgba(self.paleta["texto_tenue"], opac))
            return
        puntos = float(modulo.get("tam", 12))
        fuente = self._fuente_pt(puntos)
        alto_linea = max(10, int(puntos * self.por_punto * 1.4))
        y = 0
        if titulo:
            grande = self._fuente_pt(puntos + 2)
            for linea in _cortar(titulo, grande, ancho, dibujo):
                if y + alto_linea > alto:
                    return
                dibujo.text((0, y), linea, font=grande,
                            fill=_rgba(self.paleta["acento"], opac))
                y += alto_linea + 2
            y += 4

        maximo = int(modulo.get("lineas", 14))
        saltar = max(0, int(desde))
        for cruda in texto.splitlines():
            for linea in _cortar(cruda, fuente, ancho, dibujo):
                # Desplazar cuenta lineas YA CORTADAS y no renglones del
                # archivo: es lo que se ve, que es contra lo que uno ajusta.
                if saltar > 0:
                    saltar -= 1
                    continue
                if y + alto_linea > alto or maximo <= 0:
                    return
                dibujo.text((0, y), linea, font=fuente,
                            fill=_rgba(self.paleta["texto"], opac))
                y += alto_linea
                maximo -= 1

    def _pintar_contexto(self, dibujo, modulo, estado, ancho, alto, opac):
        """El medidor: lo unico que muestra un numero medido y no un adorno."""
        partes = estado.get("partes") or {}
        total = sum(partes.values()) or 1
        colores = [self.paleta["acento"], self.paleta["acento2"],
                   self.paleta["borde"], self.paleta["texto_tenue"]]
        ordenadas = sorted(partes.items(), key=lambda par: -par[1])
        if str(modulo.get("detalle")) == "numeros":
            fuente = self._fuente_pt(9)
            y = 0
            # El color va en un cuadradito y el texto siempre en el color de
            # texto. Pintar la linea entera del color de su tramo dejaba dos de
            # las cinco filas ilegibles: el ciclo llega a `borde` y a
            # `texto_tenue`, que existen para cosas que NO se leen.
            for i, (nombre, valor) in enumerate(ordenadas[:5]):
                dibujo.rectangle([0, y + 2, 8, y + 10],
                                 fill=_rgba(colores[i % len(colores)], opac))
                dibujo.text((13, y), nombre + ": " + str(valor), font=fuente,
                            fill=_rgba(self.paleta["texto"], opac))
                y += 15
            return
        x = 0.0
        for i, (_, valor) in enumerate(ordenadas):
            w = ancho * valor / total
            dibujo.rectangle([x, 0, x + w, alto], fill=_rgba(colores[i % len(colores)], opac))
            x += w


def _cortar(texto, fuente, ancho, dibujo):
    """Parte una linea larga en varias que entren en el ancho."""
    palabras = texto.split()
    if not palabras:
        return [""]
    lineas, actual = [], palabras[0]
    for palabra in palabras[1:]:
        prueba = actual + " " + palabra
        if dibujo.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    lineas.append(actual)
    return lineas
