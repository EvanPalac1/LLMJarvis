"""Dibuja una configuracion de modulos a un PNG, sin abrir ninguna ventana.

Sirve para tres cosas distintas y por eso vale su archivo:

1. **Ver un perfil antes de aplicarlo.** Un `.eveperfil` que te pasaron es un
   monton de claves; esto lo convierte en una imagen sin que tengas que pisarte
   la config para mirarlo.
2. **Testear lo visual.** Es la unica forma honesta de probar un sistema de
   dibujo: mismo perfil, misma imagen, mismo hash. Sin esto, "el overlay se ve
   bien" es una opinion y cualquier regresion de pixeles pasa sin que nadie se
   entere --como paso con el icono que se congelaba en el segundo cuadro.
3. **Armar la galeria del README** desde la CI, en vez de sacar capturas a mano
   que envejecen.

No necesita pantalla: `Lienzo.pintar()` devuelve una imagen de PIL y no toca
tkinter. El unico contacto con la ventana es `winfo_fpixels` para los dpi, y el
constructor ya cae a 96 solo si no hay ventana; aca se le pasa un canvas falso
que ademas deja elegir los dpi, para poder reproducir el mismo PNG en una
maquina con la pantalla escalada.
"""

from __future__ import annotations

import os

from PIL import Image

from . import lienzo as lienzo_mod
from . import modulos, store, tema

# Estados que el cartel puede tener. Se pueden pedir todos porque un modulo con
# `cuando = trabajando` no se dibuja en reposo, y mirar solo el reposo esconde
# justo lo que se quiso configurar.
ESTADOS = ("reposo", "escuchando", "pensando", "hablando")


class _CanvasFalso:
    """Lo unico que `Lienzo.__init__` le pide a un canvas son los dpi."""

    def __init__(self, dpi: float):
        self._dpi = dpi

    def winfo_fpixels(self, _cuanto):
        return self._dpi


def dibujar(cfg: dict, superficie: str = "overlay", estado: str = "reposo",
            nivel: float = 0.0, ancho: int = 0, alto: int = 0,
            fondo: str = "", dpi: float = 96.0, momento: float = 0.0):
    """La superficie entera como una imagen RGBA.

    `momento` es el tiempo simulado en segundos. Fijarlo es lo que hace que dos
    corridas den el mismo PNG: si se usara el reloj de verdad, un reloj o una
    onda cambiarian en cada llamada y no habria golden image posible.
    """
    lista = [m for m in modulos.listar(cfg, superficie)
             if modulos.visible(m, estado, bajo_el_mouse=True)]
    if not ancho or not alto:
        ancho = ancho or max([m["x"] + m["ancho"] for m in lista] or [0]) + 40
        alto = alto or max([m["y"] + m["alto"] for m in lista] or [0]) + 40
    ancho, alto = max(1, int(ancho)), max(1, int(alto))

    paleta = tema.resolver(cfg, "hud" if superficie == "overlay" else "ui")
    if fondo == "transparente":
        base = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    else:
        base = Image.new("RGBA", (ancho, alto),
                         lienzo_mod._rgba(fondo or paleta["panel"], 100))

    pintor = lienzo_mod.Lienzo(_CanvasFalso(dpi), cfg,
                               "hud" if superficie == "overlay" else "ui")
    vista = {"estado": estado, "nivel": float(nivel), "detalle": estado.upper(),
             "usuario": "abri spotify", "eve": "Listo."}
    for modulo in lista:
        img = pintor.pintar(modulo, vista, momento)
        # `escala` puede agrandar el modulo mas alla de su rectangulo; se pega
        # centrado en donde el usuario lo puso, que es como se ve en el overlay.
        x = int(modulo["x"]) - (img.width - int(modulo["ancho"])) // 2
        y = int(modulo["y"]) - (img.height - int(modulo["alto"])) // 2
        base.alpha_composite(img, (max(0, x), max(0, y)))
    return base


def a_archivo(destino: str, cfg: dict = None, **kw) -> str:
    """Guarda el PNG y devuelve la ruta."""
    img = dibujar(cfg if cfg is not None else store.load_config(), **kw)
    os.makedirs(os.path.dirname(os.path.abspath(destino)) or ".", exist_ok=True)
    img.save(destino)
    return destino


def firma(cfg: dict, **kw) -> str:
    """El sha1 de la imagen. Es la comparacion de un golden image."""
    import hashlib

    img = dibujar(cfg, **kw)
    return hashlib.sha1(img.tobytes()).hexdigest()[:16]


def main(argv: list[str]) -> int:
    """`Eve --retrato salida.png [opciones]`."""
    destino = ""
    kw = {"superficie": "overlay", "estado": "reposo", "nivel": 0.0,
          "ancho": 0, "alto": 0, "fondo": "", "dpi": 96.0, "momento": 0.0}
    perfil = ""
    todos = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--perfil":
            i += 1
            perfil = argv[i]
        elif a == "--todos":
            todos = True
        elif a.startswith("--") and a[2:] in kw:
            i += 1
            clave = a[2:]
            kw[clave] = type(kw[clave])(argv[i]) if not isinstance(kw[clave], str) \
                else argv[i]
        elif not a.startswith("--"):
            destino = a
        else:
            print(__doc__)
            print("\nOpciones: --perfil ARCHIVO  --todos  "
                  + "  ".join("--" + k for k in kw))
            return 1
        i += 1

    if not destino:
        print("Falta el archivo de salida.  Eve --retrato salida.png")
        return 1

    cfg = store.load_config()
    if perfil:
        # Se aplica sobre una COPIA: mirar un perfil ajeno no puede pisarte el
        # tuyo, que es justo para lo que sirve esto.
        cfg = dict(cfg)
        # devuelve (nombre, claves): interesa lo segundo
        cfg.update(store.leer_perfil_archivo(perfil)[1])

    if todos:
        raiz, ext = os.path.splitext(destino)
        for estado in ESTADOS:
            salida = a_archivo(f"{raiz}-{estado}{ext or '.png'}", cfg,
                               **{**kw, "estado": estado})
            print(salida)
        return 0
    print(a_archivo(destino, cfg, **kw))
    return 0
