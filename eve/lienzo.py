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

De yapa, un item de canvas por modulo es lo que el modo Edit necesita igual para
saber en cual se hizo clic y para el orden de dibujo.

El alpha por modulo es composicion de PIL de verdad, no el `-alpha` de la
ventana: ese afecta a todo por igual y se llevaria puesto el texto.
"""

import math
import time
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont

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
        self._ondas = {}
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
        if tipo == "icono":
            # Un GIF, APNG o WebP animado cambia solo; una imagen fija no.
            fondo = self._fondos.get(modulo["id"])
            animado = bool(fondo is not None and fondo.hay() and modulo.get("imagen"))
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
        ancho = max(1, int(modulo["ancho"] * modulo["escala"] / 100))
        alto = max(1, int(modulo["alto"] * modulo["escala"] / 100))
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
            transcurrido = int(time.monotonic() * 1000) % total
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
