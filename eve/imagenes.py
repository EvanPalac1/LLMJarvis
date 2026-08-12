"""Fondos de imagen para el overlay: PNG y GIF animado.

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
import os
import tempfile
import tkinter as tk

MAX_CUADROS = 60      # un GIF largo no justifica ocupar memoria de a 60 PNG
MS_POR_DEFECTO = 100  # si el GIF no declara duracion

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
        salida = Image.new("RGB", (ancho, alto))
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


def procesar(ruta: str, ancho: int, alto: int, ajuste: str = "recortar",
             opacidad: int = 100, tinte: int = 0, color_base: str = "#000000",
             color_tinte: str = "#000000") -> tuple[list[str], list[int]]:
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

        firma = hashlib.sha1(
            f"{ruta}|{os.path.getmtime(ruta)}|{ancho}x{alto}|{ajuste}|"
            f"{opacidad}|{tinte}|{color_base}|{color_tinte}".encode()
        ).hexdigest()[:12]

        rutas, tiempos = [], []
        with Image.open(ruta) as animada:
            total = min(getattr(animada, "n_frames", 1), MAX_CUADROS)
            for i in range(total):
                destino = os.path.join(_carpeta(), f"{firma}-{i}.png")
                animada.seek(i)
                if not os.path.exists(destino):
                    cuadro = _encajar(animada.convert("RGB"), ancho, alto, ajuste)
                    if tinte > 0:
                        capa = Image.new("RGB", cuadro.size, _rgb(color_tinte))
                        cuadro = Image.blend(cuadro, capa, min(100, tinte) / 100)
                    if opacidad < 100:
                        # Mezclar contra el color del panel imita la
                        # transparencia sin tocar el alpha de la ventana, que se
                        # llevaria puesto tambien al texto.
                        fondo = Image.new("RGB", cuadro.size, _rgb(color_base))
                        cuadro = Image.blend(fondo, cuadro, max(0, opacidad) / 100)
                    cuadro.save(destino)
                rutas.append(destino)
                tiempos.append(int(animada.info.get("duration") or MS_POR_DEFECTO))
        return rutas, tiempos
    except Exception:  # noqa: BLE001 - un fondo roto no puede tumbar el overlay
        return [], []


def cargar(ruta: str, ancho: int, alto: int, ajuste: str = "recortar",
           opacidad: int = 100, tinte: int = 0, color_base: str = "#000000",
           color_tinte: str = "#000000") -> tuple[list, list[int]]:
    """Lo mismo que `procesar` pero ya convertido a imagenes de tk."""
    rutas, tiempos = procesar(ruta, ancho, alto, ajuste, opacidad, tinte,
                              color_base, color_tinte)
    try:
        return [tk.PhotoImage(file=r) for r in rutas], tiempos
    except tk.TclError:
        return [], []


class Fondo:
    """Guarda los cuadros y sabe cual toca segun el reloj."""

    def __init__(self):
        self.cuadros: list = []
        self.tiempos: list[int] = []
        self._clave = None
        self._desde = 0.0

    def aplicar(self, ruta: str, ancho: int, alto: int, ajuste: str, opacidad: int,
                tinte: int, color_base: str, color_tinte: str) -> None:
        clave = (ruta, ancho, alto, ajuste, opacidad, tinte, color_base, color_tinte)
        if clave == self._clave:
            return  # ya esta cargado: recargar en cada cuadro seria absurdo
        self._clave = clave
        self.cuadros, self.tiempos = cargar(
            ruta, ancho, alto, ajuste, opacidad, tinte, color_base, color_tinte
        )
        import time

        self._desde = time.monotonic()

    @property
    def hay(self) -> bool:
        return bool(self.cuadros)

    def actual(self):
        """El cuadro que corresponde ahora. None si no hay fondo."""
        if not self.cuadros:
            return None
        if len(self.cuadros) == 1:
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
