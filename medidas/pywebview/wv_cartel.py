"""Puerta 2: el cartel. Ventana sin borde, encima, transparente y que deje pasar los clics.

Es lo que `overlay.py` hace hoy con tkinter: `overrideredirect(True)`,
`-topmost`, `-transparentcolor` y `WS_EX_TRANSPARENT`. Si pywebview no puede
las cuatro en Windows, el cartel no se muda y punto.

Se comprueba mirando la ventana DE VERDAD, con la API de Windows, no
preguntandole a pywebview si dice que si.
"""
import ctypes
import os
import json
import sys
import threading
import time

import webview

RES = {}

HTML = """
<!doctype html><meta charset="utf-8">
<style>
  html,body { margin:0; height:100%; overflow:hidden; background:#ff00ff; }
  .cartel { position:absolute; left:20px; top:20px;
            width:420px; height:80px; border-radius:14px;
            background:#12151c; border:1px solid #2a2f3a;
            color:#e6e9ef; font:14px "Segoe UI",sans-serif;
            display:flex; align-items:center; padding:0 18px; }
</style>
<div class="cartel"><b>Eve</b>&nbsp;&nbsp;escuchando...</div>
"""

DESTINO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "cartel_web2.png")

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
HWND_TOPMOST = -1


def mirar(titulo):
    """Le pregunta a WINDOWS, no a pywebview."""
    u32 = ctypes.windll.user32
    hwnd = u32.FindWindowW(None, titulo)
    if not hwnd:
        return {"encontrada": False}
    getl = u32.GetWindowLongPtrW if hasattr(u32, "GetWindowLongPtrW") else u32.GetWindowLongW
    ex = getl(hwnd, GWL_EXSTYLE)
    estilo = getl(hwnd, -16)   # GWL_STYLE
    WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
    return {
        "encontrada": True,
        "sin_borde": not bool(estilo & WS_CAPTION),
        "redimensionable": bool(estilo & WS_THICKFRAME),
        "layered": bool(ex & WS_EX_LAYERED),
        "deja_pasar_clics": bool(ex & WS_EX_TRANSPARENT),
    }


def probar(v, titulo):
    time.sleep(3.0)
    try:
        RES["antes"] = mirar(titulo)
        # Segundo intento: forzar el pasar-clics a mano, como hace
        # `plataforma.ventana_fantasma`. Si pywebview no lo ofrece pero la
        # ventana lo acepta, el cartel igual se podria hacer.
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW(None, titulo)
        if hwnd:
            getl = u32.GetWindowLongPtrW if hasattr(u32, "GetWindowLongPtrW") else u32.GetWindowLongW
            setl = u32.SetWindowLongPtrW if hasattr(u32, "SetWindowLongPtrW") else u32.SetWindowLongW
            ex = getl(hwnd, GWL_EXSTYLE)
            setl(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            u32.SetLayeredWindowAttributes(hwnd, 0x00FF00FF, 255, 0x1)  # LWA_COLORKEY, magenta
            time.sleep(0.6)
            RES["despues_de_forzarlo"] = mirar(titulo)
            # Y la prueba de verdad: MIRARLO. Que el flag este puesto no
            # prueba que el fondo se vea a traves.
            u32.SetWindowPos(hwnd, -1, 60, 60, 460, 120, 0x0040)
            time.sleep(1.2)
            from PIL import ImageGrab

            ImageGrab.grab((40, 40, 560, 220)).save(DESTINO)
            RES["captura"] = DESTINO
    except Exception as exc:  # noqa: BLE001
        RES["error"] = f"{type(exc).__name__}: {exc}"
    time.sleep(1.0)
    v.destroy()


if __name__ == "__main__":
    titulo = "Eve cartel prueba"
    intentos = {}
    # Se prueba lo que pywebview DICE que soporta, y se anota que paso.
    try:
        v = webview.create_window(
            titulo, html=HTML, frameless=True, on_top=True,
            transparent=True, easy_drag=False,
            width=460, height=120, background_color="#ff00ff")
        intentos["creada_con_transparent"] = True
    except Exception as exc:  # noqa: BLE001
        intentos["creada_con_transparent"] = f"{type(exc).__name__}: {exc}"
        v = webview.create_window(titulo, html=HTML, frameless=True,
                                  on_top=True, width=460, height=120)
    RES["intentos"] = intentos
    threading.Thread(target=probar, args=(v, titulo), daemon=True).start()
    try:
        webview.start()
    except Exception as exc:  # noqa: BLE001
        RES["error_start"] = f"{type(exc).__name__}: {exc}"
    print("RESULTADO " + json.dumps(RES, default=str, ensure_ascii=False))
    sys.exit(0)
