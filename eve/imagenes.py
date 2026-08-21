"""Fondos de imagen: PNG, GIF, APNG, WebP animado y sprite sheets.

Dos decisiones que valen el comentario:

`ImageTk` no se usa. Es el puente natural entre PIL y tkinter, pero es un
submodulo aparte que puede no viajar en el binario empaquetado, y un fondo que
solo falla en la version instalada es el peor tipo de falla. En vez de eso PIL
escala y mezcla, guarda un PNG temporal, y lo carga `tk.PhotoImage`, que lee PNG
de forma nativa desde Tk 8.6.

La opacidad del fondo se hornea en la imagen en vez de pedirsela a la ventana.
El `-alpha` de la ventana afecta a todo por igual, asi que bajarlo para atenuar
el fondo se llevaria puesto al texto. Mezclando la imagen contra el color del
panel antes de mostrarla, el fondo queda tenue y las letras siguen enteras.
"""

import hashlib
import json
import os
import tempfile
import tkinter as tk

MAX_CUADROS = 60      # una animacion larga no justifica ocupar memoria de a 60 PNG
MS_POR_DEFECTO = 100  # si el archivo no declara duracion

# El recorrido de cuadros de abajo no sabe de formatos: pide `n_frames`, hace
# `seek` y lee `info["duration"]`, y eso en PIL vale igual para GIF, APNG y
# WebP animado. O sea que los dos ultimos ya andaban desde siempre y lo unico
# que los tapaba era el filtro del dialogo de archivos. Sale barato y se nota:
# el mismo dibujo de tres cuadros guardado como GIF queda en 2 colores unicos
# --paleta de 256 y alpha de un bit-- y como APNG en 92, con alpha de 8 bits.

_DIR = None


def _carpeta() -> str:
    global _DIR
    if _DIR is None:
        _DIR = tempfile.mkdtemp(prefix="eve-fondos-")
    return _DIR


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _encajar(img, ancho: int, alto: int, ajuste: str):
    """Lleva la imagen al tamaño del cartel segun el modo elegido."""
    from PIL import Image

    if ancho < 1 or alto < 1:
        return img
    if ajuste == "estirar":
        return img.resize((ancho, alto), Image.LANCZOS)
    if ajuste == "mosaico":
        # El modo de la fuente, no RGB fijo: si viene con alpha hay que mantenerlo.
        salida = Image.new(img.mode, (ancho, alto))
        for x in range(0, ancho, img.width):
            for y in range(0, alto, img.height):
                salida.paste(img, (x, y))
        return salida
    # recortar: llena el cartel sin deformar y se queda con el centro.
    escala = max(ancho / img.width, alto / img.height)
    grande = img.resize((max(1, round(img.width * escala)),
                         max(1, round(img.height * escala))), Image.LANCZOS)
    izq, arriba = (grande.width - ancho) // 2, (grande.height - alto) // 2
    return grande.crop((izq, arriba, izq + ancho, arriba + alto))


def atlas_de(ruta: str) -> list[tuple[tuple[int, int, int, int], int]]:
    """Los recortes de un sprite sheet: [((x, y, x2, y2), ms), ...].

    Aseprite y TexturePacker --que son con lo que la gente arma esto-- exportan
    un PNG con todos los cuadros pegados y un JSON al lado diciendo donde esta
    cada uno. El JSON se llama igual que la imagen, asi que no hace falta ningun
    ajuste nuevo: se deja el par de archivos en la carpeta, se elige el PNG, y
    si el JSON esta se usa.

    Los dos exportan `frames` como lista o como diccionario segun el modo, y las
    dos formas traen el mismo `frame: {x, y, w, h}`. Se aceptan las dos porque
    elegir el modo equivocado en el exportador no es culpa del usuario.

    Devuelve [] si no hay atlas o si el JSON no se entiende: sin eso un sprite
    sheet roto dejaria de mostrar hasta la imagen entera, que es peor.
    """
    lado = os.path.splitext(ruta)[0] + ".json"
    if not os.path.exists(lado):
        return []
    try:
        with open(lado, encoding="utf-8") as f:
            datos = json.load(f)
        crudos = datos.get("frames")
        if isinstance(crudos, dict):
            # En modo hash el orden del dict es el de exportacion, que es el de
            # la animacion. Ordenar por nombre romperia "10" antes que "2".
            crudos = list(crudos.values())
        if not isinstance(crudos, list):
            return []
        salida = []
        for entrada in crudos[:MAX_CUADROS]:
            caja = entrada.get("frame") or {}
            x, y = int(caja.get("x", 0)), int(caja.get("y", 0))
            w, h = int(caja.get("w", 0)), int(caja.get("h", 0))
            if w < 1 or h < 1:
                continue
            ms = int(entrada.get("duration") or MS_POR_DEFECTO)
            salida.append(((x, y, x + w, y + h), ms))
        return salida
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def procesar(ruta: str, ancho: int, alto: int, ajuste: str = "recortar",
             opacidad: int = 100, tinte: int = 0, color_base: str = "#000000",
             color_tinte: str = "#000000",
             conservar_alpha: bool = False) -> tuple[list[str], list[int]]:
    """(rutas de los PNG ya listos, milisegundos de cada uno).

    Todo el trabajo de imagen vive aca, sin tocar tkinter, para poder probarlo
    sin pantalla: el CI de Linux corre sin servidor grafico.

    Nunca lanza: un fondo es decoracion, y si el archivo se borro o esta roto el
    overlay tiene que seguir andando con su color de siempre.
    """
    if not ruta or not os.path.exists(ruta) or ancho < 1 or alto < 1:
        return [], []
    try:
        from PIL import Image

        lado = os.path.splitext(ruta)[0] + ".json"
        # El mtime del JSON entra en la firma: si no, reacomodar los recortes sin
        # tocar el PNG seguia sirviendo los cuadros viejos desde el cache.
        marca = os.path.getmtime(ruta) + (os.path.getmtime(lado)
                                          if os.path.exists(lado) else 0)
        firma = hashlib.sha1(
            f"{ruta}|{marca}|{ancho}x{alto}|{ajuste}|"
            f"{opacidad}|{tinte}|{color_base}|{color_tinte}|{conservar_alpha}".encode()
        ).hexdigest()[:12]

        rutas, tiempos = [], []
        recortes = atlas_de(ruta)
        with Image.open(ruta) as animada:
            total = len(recortes) or min(getattr(animada, "n_frames", 1), MAX_CUADROS)
            for i in range(total):
                destino = os.path.join(_carpeta(), f"{firma}-{i}.png")
                if not recortes:
                    animada.seek(i)
                if not os.path.exists(destino):
                    # Un fondo se aplana contra el color del panel: ocupa la
                    # tarjeta entera y no hay nada detras que dejar ver. Un icono
                    # NO: convertirlo a RGB tira el alpha y lo que era
                    # transparente termina en negro, o sea un cuadrado oscuro
                    # alrededor del dibujo. Tk compone PNG con alpha solo.
                    modo = "RGBA" if conservar_alpha else "RGB"
                    fuente = animada.crop(recortes[i][0]) if recortes else animada
                    cuadro = _encajar(fuente.convert(modo), ancho, alto, ajuste)
                    if tinte > 0:
                        capa = Image.new(modo, cuadro.size, _rgb(color_tinte))
                        if conservar_alpha:
                            capa.putalpha(cuadro.getchannel("A"))
                        cuadro = Image.blend(cuadro, capa, min(100, tinte) / 100)
                    if opacidad < 100:
                        # Mezclar contra el color del panel imita la
                        # transparencia sin tocar el alpha de la ventana, que se
                        # llevaria puesto tambien al texto.
                        if conservar_alpha:
                            alfa = cuadro.getchannel("A").point(
                                lambda v: int(v * max(0, opacidad) / 100))
                            cuadro.putalpha(alfa)
                        else:
                            fondo = Image.new("RGB", cuadro.size, _rgb(color_base))
                            cuadro = Image.blend(fondo, cuadro, max(0, opacidad) / 100)
                    cuadro.save(destino)
                rutas.append(destino)
                tiempos.append(recortes[i][1] if recortes
                               else int(animada.info.get("duration") or MS_POR_DEFECTO))
        return rutas, tiempos
    except Exception:  # noqa: BLE001 - un fondo roto no puede tumbar el overlay
        return [], []


def cargar(ruta: str, ancho: int, alto: int, ajuste: str = "recortar",
           opacidad: int = 100, tinte: int = 0, color_base: str = "#000000",
           color_tinte: str = "#000000",
           conservar_alpha: bool = False) -> tuple[list, list[int]]:
    """Lo mismo que `procesar` pero ya convertido a imagenes de tk."""
    rutas, tiempos = procesar(ruta, ancho, alto, ajuste, opacidad, tinte,
                              color_base, color_tinte, conservar_alpha)
    try:
        return [tk.PhotoImage(file=r) for r in rutas], tiempos
    except tk.TclError:
        return [], []


def degradado(ancho: int, alto: int, color_a: str, color_b: str,
              direccion: str = "vertical") -> str:
    """Genera el degradado como PNG y devuelve su ruta. '' si no se pudo.

    Se dibuja con PIL y se carga como imagen en vez de simularlo con lineas en
    el canvas: mil lineas de un pixel por cada cuadro serian mil items que tk
    tiene que redibujar, y aca es una sola imagen.
    """
    if ancho < 1 or alto < 1:
        return ""
    firma = hashlib.sha1(
        f"grad|{ancho}x{alto}|{color_a}|{color_b}|{direccion}".encode()
    ).hexdigest()[:12]
    destino = os.path.join(_carpeta(), f"{firma}.png")
    if os.path.exists(destino):
        return destino
    try:
        from PIL import Image

        a, b = _rgb(color_a), _rgb(color_b)
        if direccion == "radial":
            import math

            img = Image.new("RGB", (ancho, alto))
            px = img.load()
            cx, cy = ancho / 2, alto / 2
            maximo = math.hypot(cx, cy) or 1
            for y in range(alto):
                for x in range(ancho):
                    t = min(1.0, math.hypot(x - cx, y - cy) / maximo)
                    px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
        else:
            # Se dibuja chico y se agranda: un degradado lineal es exactamente lo
            # que hace un resize bilineal, y cuesta nada.
            if direccion == "horizontal":
                chico = Image.new("RGB", (2, 1))
                chico.putpixel((0, 0), a)
                chico.putpixel((1, 0), b)
            elif direccion == "diagonal":
                chico = Image.new("RGB", (2, 2))
                chico.putpixel((0, 0), a)
                chico.putpixel((1, 0), tuple((a[i] + b[i]) // 2 for i in range(3)))
                chico.putpixel((0, 1), tuple((a[i] + b[i]) // 2 for i in range(3)))
                chico.putpixel((1, 1), b)
            else:  # vertical
                chico = Image.new("RGB", (1, 2))
                chico.putpixel((0, 0), a)
                chico.putpixel((0, 1), b)
            img = chico.resize((ancho, alto), Image.BILINEAR)
        img.save(destino)
        return destino
    except Exception:  # noqa: BLE001 - sin degradado se usa el color liso
        return ""


class Fondo:
    """Guarda los cuadros y sabe cual toca segun el reloj."""

    def __init__(self):
        self.cuadros: list = []
        self.tiempos: list[int] = []
        self._clave = None
        self._desde = 0.0

    def aplicar(self, ruta: str, ancho: int, alto: int, ajuste: str, opacidad: int,
                tinte: int, color_base: str, color_tinte: str, grad: tuple = (),
                conservar_alpha: bool = False) -> None:
        """`grad` es (direccion, color_a, color_b) y se usa si no hay imagen."""
        clave = (ruta, ancho, alto, ajuste, opacidad, tinte, color_base,
                 color_tinte, grad, conservar_alpha)
        if clave == self._clave:
            return  # ya esta cargado: recargar en cada cuadro seria absurdo
        self._clave = clave
        if not ruta and grad and grad[0] and grad[0] != "ninguno":
            # La imagen gana si hay las dos: es lo que el usuario eligio ultimo.
            ruta = degradado(ancho, alto, grad[1] or color_base,
                             grad[2] or color_tinte, grad[0])
            ajuste, opacidad, tinte = "estirar", 100, 0
        self.cuadros, self.tiempos = cargar(
            ruta, ancho, alto, ajuste, opacidad, tinte, color_base, color_tinte,
            conservar_alpha
        ) if ruta else ([], [])
        import time

        self._desde = time.monotonic()

    @property
    def hay(self) -> bool:
        return bool(self.cuadros)

    def actual(self, animar: bool = True):
        """El cuadro que corresponde ahora. None si no hay fondo."""
        if not self.cuadros:
            return None
        if len(self.cuadros) == 1 or not animar:
            return self.cuadros[0]
        import time

        total = sum(self.tiempos) or MS_POR_DEFECTO
        transcurrido = ((time.monotonic() - self._desde) * 1000) % total
        acumulado = 0
        for cuadro, ms in zip(self.cuadros, self.tiempos):
            acumulado += ms
            if transcurrido < acumulado:
                return cuadro
        return self.cuadros[-1]
