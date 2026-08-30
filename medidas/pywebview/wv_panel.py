"""Puerta 1: pywebview abre, dibuja HTML, corre JS y habla con Python.

No alcanza con que la ventana abra. Lo que el panel necesita es el camino
completo: el HTML se dibuja, el JavaScript corre, y puede llamar a Python y
recibir la respuesta. Si eso no anda, no hay panel.
"""
import json
import os
import sys
import threading
import time

import webview

RESULTADO = {"js": None, "puente": None, "error": None}

HTML = """
<!doctype html>
<meta charset="utf-8">
<style>
  :root { --fondo:#0f1115; --panel:#171a21; --borde:#2a2f3a;
          --texto:#e6e9ef; --acento:#4c8dff; }
  body { background:var(--fondo); color:var(--texto);
         font:13px "Segoe UI",sans-serif; margin:0; padding:20px; }
  .tarjeta { background:var(--panel); border:1px solid var(--borde);
             border-radius:10px; padding:16px; margin-bottom:12px; }
  label { display:block; margin-bottom:6px; }
  input,select { background:var(--fondo); color:var(--texto);
                 border:1px solid var(--borde); border-radius:6px;
                 padding:7px 9px; width:100%; box-sizing:border-box; }
  input:focus,select:focus { outline:none; border-color:var(--acento); }
  button { background:var(--acento); color:#fff; border:0;
           border-radius:8px; padding:8px 16px; font-weight:600; }
</style>
<div class="tarjeta">
  <h3 style="margin-top:0">Quien piensa por ella</h3>
  <label for="prov">Proveedor</label>
  <select id="prov"><option>Anthropic</option><option>Groq</option></select>
</div>
<div class="tarjeta">
  <label for="modelo">Modelo</label>
  <input id="modelo" value="claude-opus-5">
</div>
<button id="b">Guardar</button>
<script>
  window.__marca = "el js corrio";
</script>
"""


class Puente:
    def desde_js(self, texto):
        RESULTADO["puente"] = texto
        return {"ok": True, "eco": texto}


def probar(ventana):
    time.sleep(2.5)
    try:
        RESULTADO["js"] = ventana.evaluate_js("window.__marca")
        # El camino que de verdad importa: JS llama a Python y recibe respuesta.
        vuelta = ventana.evaluate_js(
            "pywebview.api.desde_js('hola desde el panel')"
            ".then(r => JSON.stringify(r))")
        RESULTADO["vuelta"] = vuelta
        # Y que el DOM este de verdad, no solo la ventana.
        RESULTADO["dom"] = ventana.evaluate_js(
            "document.querySelectorAll('input,select,button').length")
    except Exception as exc:  # noqa: BLE001
        RESULTADO["error"] = f"{type(exc).__name__}: {exc}"
    time.sleep(1.5)
    ventana.destroy()


def _vigia_cuelgue(segundos):
    """Mata el proceso si start() nunca vuelve, en vez de esperar el timeout del job.

    Precedente en este repo: tk.Tk() se crea pero panel.update() no vuelve
    nunca en el runner de macOS, y eso solo colgo dos jobs 21 minutos porque
    nada lo cortaba antes (test_eve.py:6452-6474). webview.start() reentra el
    run loop de Cocoa igual que update() reentra el de Tcl/Tk: mismo riesgo.
    """
    time.sleep(segundos)
    RESULTADO["error"] = f"cuelgue: start() no volvio en {segundos}s"
    print("RESULTADO " + json.dumps(RESULTADO, default=str), flush=True)
    os._exit(3)


if __name__ == "__main__":
    v = webview.create_window("Eve · puerta pywebview", html=HTML,
                              js_api=Puente(), width=520, height=420)
    threading.Thread(target=probar, args=(v,), daemon=True).start()
    threading.Thread(target=_vigia_cuelgue, args=(90,), daemon=True).start()
    try:
        webview.start()
    except Exception as exc:  # noqa: BLE001
        RESULTADO["error"] = f"start: {type(exc).__name__}: {exc}"
    print("RESULTADO " + json.dumps(RESULTADO, default=str))
    sys.exit(0 if RESULTADO.get("js") and not RESULTADO.get("error") else 1)
