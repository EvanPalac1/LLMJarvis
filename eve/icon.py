"""Genera el icono del proyecto: un orbe azul con una onda de voz.

Se dibuja a 256px y se reescala, asi la version de 16px de la bandeja queda
nitida. Se genera solo si falta, para no necesitar un paso de build ni meter
binarios en el repo.
"""

import os

from PIL import Image, ImageDraw

from . import store

ASSETS = os.path.join(store.BASE, "assets")
ICO_PATH = os.path.join(ASSETS, "eve.ico")
PNG_PATH = os.path.join(ASSETS, "eve.png")

SIZE = 1024  # se dibuja grande y se baja: los bordes quedan suaves sin antialias manual
ICO_SIZES = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]

TOP = (86, 140, 255)      # azul claro, arriba del orbe
BOTTOM = (58, 44, 168)    # violeta, abajo
BAR = (255, 255, 255, 255)

# Alturas relativas de las 5 barras de la onda. Solo 3 sobreviven a 16px, pero
# a tamano grande la silueta se lee como voz y no como "tres palitos".
BARS = [0.34, 0.62, 1.0, 0.62, 0.34]


def _orb(size: int) -> Image.Image:
    """Circulo con degradado vertical."""
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        px[0, y] = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
    grad = grad.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def _wave(img: Image.Image, size: int) -> None:
    d = ImageDraw.Draw(img)
    bar_w = round(size * 0.088)
    gap = round(size * 0.052)
    total = len(BARS) * bar_w + (len(BARS) - 1) * gap
    x = (size - total) / 2
    cy = size / 2
    max_h = size * 0.46
    radius = bar_w / 2

    for rel in BARS:
        h = max_h * rel
        d.rounded_rectangle(
            (round(x), round(cy - h / 2), round(x + bar_w), round(cy + h / 2)),
            radius=radius,
            fill=BAR,
        )
        x += bar_w + gap


def render(size: int = SIZE) -> Image.Image:
    img = _orb(size)
    _wave(img, size)
    return img


def ensure_icon() -> str:
    """Devuelve la ruta del .ico, generandolo si no existe."""
    if os.path.exists(ICO_PATH) and os.path.exists(PNG_PATH):
        return ICO_PATH
    os.makedirs(ASSETS, exist_ok=True)
    big = render()
    big.resize((256, 256), Image.LANCZOS).save(PNG_PATH)
    big.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)
    return ICO_PATH


def tray_image() -> Image.Image:
    """Imagen para pystray (trabaja con objetos PIL, no con rutas)."""
    ensure_icon()
    return Image.open(PNG_PATH)


if __name__ == "__main__":
    print(ensure_icon())
