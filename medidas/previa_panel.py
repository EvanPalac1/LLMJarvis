"""Mira el panel nuevo sin arrancar Eve y sin tener pywebview instalado.

    python medidas/previa_panel.py        arma la previa y dice donde quedo
    python medidas/previa_panel.py -s     ademas la sirve en localhost

Arma una carpeta aparte con el MISMO `index.html`, `panel.css` y `panel.js` que
usa el panel de verdad, y un puente simulado que contesta con el esquema real
--el de tu config-- en vez de con datos inventados. Sirve para dos cosas:

* **mirar el diseno** pestana por pestana, que es contra lo que se mide el
  exito de esta migracion (`medidas/diseno/LEEME.md`);
* **verificar el dibujo** con un navegador de prueba, sin abrir el microfono ni
  salir a la red.

Las acciones que tocan hardware o red contestan un texto fijo, a proposito: el
punto de esto es la pantalla. Las que solo leen --los comandos, las skills, los
proveedores-- llegan de verdad, porque viajan dentro del esquema.

**Escribe en una carpeta temporal y no en `web/`**: cualquier archivo que quede
ahi se empaqueta con el programa (`build.py` mete `web/` entero), y un archivo
de prueba adentro del instalador es basura que se publica sola.
"""

import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from eve import panel_api, store  # noqa: E402

PUENTE = """
<script>
const ESQUEMA_FIJO = %s;
const ELEGIR = %s;
// Lo que no se puede probar sin hardware ni red, con una respuesta de ejemplo.
// Son las mismas frases que devuelve la accion de verdad, para que se vea
// cuanto ocupan: una respuesta corta de mentira esconde el desborde.
const SIMULADAS = {
  probar_motor: {ok: true, salida: "api contesto en 0.8s: 'listo'"},
  probar_stt: {ok: true, salida: "Te escuche: 'abri spotify'   (pico -18 dBFS, modo auto)"},
  probar_tts: {ok: true, salida: "Listo. Voz: piper / es_AR-daniela-high"},
  probar_wake: {ok: true, salida: "se abrio y quedo la orden: 'abre spotify'"},
  gpu_probar: {ok: true, salida: "cuda: 1.2s para 3s de audio."},
  probar_tecla: {ok: true, salida: "llego 'f13', que es la configurada. el asistente esta corriendo."},
  hotkey_capturar: {ok: true, salida: "tecla: f13. Recuerda Guardar.", valores: {hotkey: "f13"}},
  probar_overlay: {ok: true, salida: "Cartel mostrado unos segundos."},
  probar_subtitulo: {ok: true, salida: "Subtitulo de prueba mostrado."},
  _abrir_consola: {ok: true, salida: "ventana de actividad abierta"},
};
window.pywebview = {api: {
  esquema: async () => JSON.parse(JSON.stringify(ESQUEMA_FIJO)),
  guardar: async (c) => ({ok: true, error: "", valores: c}),
  elegir_archivo: async () => ({ok: true, rutas: ["C:\\\\ejemplo\\\\imagen.png"]}),
  accion: async (nombre, cfg, args) => {
    if (SIMULADAS[nombre]) return Object.assign({valores: {}}, SIMULADAS[nombre]);
    if (nombre === "elegir_proveedor") {
      return ELEGIR[args.id] || {ok: false, valores: {}, salida: "?"};
    }
    if (nombre === "guardar_clave") {
      return {ok: true, valores: {}, salida: "clave guardada: " + args.proveedor};
    }
    if (nombre === "comandos_probar") {
      return {ok: true, valores: {}, salida: "Probado: " + (args.frases || [""])[0],
              titulo: "Probar: " + (args.frases || [""])[0],
              cuerpo: "sistema: echo hola\\n\\ncodigo de retorno: 0\\ntardo: 0.02s\\n\\n"
                      + "--- salida ---\\nhola\\n\\n--- errores ---\\n(ninguno)"};
    }
    return {ok: true, valores: {}, salida: "(simulado) " + nombre};
  },
}};
</script>
"""


def armar(destino: str = "") -> str:
    """Deja la previa lista y devuelve la ruta del html."""
    destino = destino or tempfile.mkdtemp(prefix="eve_previa_")
    os.makedirs(destino, exist_ok=True)
    web = os.path.join(RAIZ, "web")
    for nombre in ("tokens.css", "panel.css", "panel.js"):
        shutil.copy2(os.path.join(web, nombre), os.path.join(destino, nombre))

    esq = panel_api.esquema()
    # El historial es la conversacion del usuario y la agenda son personas
    # reales. La previa se mira y se comparte --de ahi salen las capturas del
    # diseno-- asi que esos dos se vacian antes de escribir el archivo. Lo que
    # importa para el dibujo es la FORMA, y con dos ejemplos inventados alcanza.
    esq["huecos"]["_historial"] = {
        "componente": "historial", "cuantos": "2 mensajes guardados",
        "lista": [{"hora": "31/08 16:04", "quien": "usuario",
                   "texto": "abri spotify y poneme algo tranquilo"},
                  {"hora": "31/08 16:04", "quien": "eve", "texto": "listo"}]}
    # Y el registro de acciones, por lo mismo: dice que comandos corrio Eve en
    # esta maquina, con su texto. Ademas son doscientos renglones, que en modo
    # flujo hacen una pagina de cinco mil pixeles y el navegador se atraganta
    # al volcarla. Dos ejemplos alcanzan, y uno tiene que ser DENEGADO: esa
    # tabla existe para mostrar lo que Eve ejecuto y lo que el usuario freno.
    esq["huecos"]["_acciones"]["lista"] = [
        ["31/08 15:55", "comandos", "aprobar", "marcar el disco -> echo listo"],
        ["31/08 15:52", "ajustar", "comandos_aprobados = ...", "RECHAZADO: clave de freno"],
    ]
    esq["huecos"]["_contactos"]["lista"] = [
        {"nombre": "Juan Perez", "alias": "juancho", "email": "juan@example.com",
         "telefono": "+54 11 5555 0001", "discord_user": "@juanp",
         "discord_dm": "123456789", "discord_canal": ""},
        {"nombre": "Ana Gomez", "alias": "anita, la ana", "email": "ana@example.com",
         "telefono": "", "discord_user": "@anag", "discord_dm": "", "discord_canal": ""},
    ]
    cfg = store.load_config()
    elegir = {p["id"]: panel_api.elegir_proveedor(cfg, p["id"])
              for p in esq["huecos"]["_selector_proveedor"]["lista"]}
    with open(os.path.join(web, "index.html"), encoding="utf-8") as f:
        base = f.read()
    puente = PUENTE % (json.dumps(esq), json.dumps(elegir))
    # Con una marca de tiempo pegada: sin esto el navegador se queda con el
    # panel.js de la vez anterior y uno mira una pantalla vieja convencido de
    # que el cambio no anduvo. Me paso, y no es rapido de darse cuenta.
    sello = int(os.path.getmtime(os.path.join(web, "panel.js")))
    html = base.replace('<script src="panel.js"></script>',
                        puente + f'<script src="panel.js?v={sello}"></script>')
    html = html.replace('href="panel.css"', f'href="panel.css?v={sello}"')
    salida = os.path.join(destino, "index.html")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(html)
    return salida


if __name__ == "__main__":
    ruta = armar()
    print("previa:", ruta)
    if "-s" in sys.argv:
        import http.server
        import socketserver

        os.chdir(os.path.dirname(ruta))
        with socketserver.TCPServer(("127.0.0.1", 8731),
                                    http.server.SimpleHTTPRequestHandler) as srv:
            print("http://127.0.0.1:8731/index.html   (Ctrl+C para cortar)")
            srv.serve_forever()
