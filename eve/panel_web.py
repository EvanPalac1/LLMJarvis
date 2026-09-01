"""Abre el panel nuevo: una ventana de pywebview con `web/` adentro.

Todo lo que se ve sale de `panel_api`; aca solo esta la ventana y el puente.
Que sea tan corto es a proposito: si este archivo empezara a saber que
pestanas hay o como se dibuja un campo, seria la segunda copia del panel.

El panel de tkinter sigue siendo el que se abre de verdad. Este se abre con
`--panel-web` y convive: la decision escrita es migrar primero y arreglar la
interfaz en el panel nuevo, y para eso las dos versiones tienen que poder
correr al lado durante la mudanza --que es como se migro al registro--.
"""

import os

from . import panel_api


class Puente:
    """Lo que el HTML puede llamar. Nada mas que esto.

    Cada metodo es una funcion de `panel_api`, sin logica propia: asi lo que
    hace el panel se puede probar sin abrir una ventana, que es lo que hace que
    los dos tests guardianes corran sin pantalla.
    """

    def __init__(self, ventana=None):
        # La ventana hace falta para UNA cosa: los cuadros de elegir archivo,
        # que son del sistema y no del HTML. `panel_api` no la puede tener
        # --seria una dependencia de la interfaz-- asi que el dialogo vive aca
        # y lo elegido vuelve como una ruta cualquiera.
        self.ventana = ventana

    def esquema(self):
        return panel_api.esquema()

    def guardar(self, cambios):
        return panel_api.guardar(cambios)

    def accion(self, nombre, cfg=None, args=None):
        return panel_api.accion(nombre, cfg, args)

    def elegir_archivo(self, filtros=None, varios=False):
        """Abre el cuadro del sistema y devuelve las rutas elegidas.

        Un `<input type=file>` del HTML no sirve: entrega el CONTENIDO del
        archivo, y lo que Eve guarda es la RUTA --la imagen del cartel se lee
        cada vez que se dibuja--. Copiar el contenido a otro lado seria
        inventar una carpeta de imagenes que hoy no existe.
        """
        if self.ventana is None:
            return {"ok": False, "rutas": [], "error": "sin ventana"}
        import webview

        tipo = (webview.OPEN_DIALOG if not varios
                else webview.OPEN_DIALOG)
        rutas = self.ventana.create_file_dialog(
            tipo, allow_multiple=bool(varios),
            file_types=tuple(filtros) if filtros else ())
        return {"ok": bool(rutas), "rutas": list(rutas or [])}

    def guardar_archivo(self, nombre="", filtros=None):
        """El cuadro de "guardar como", para exportar un perfil o un contacto.

        Aparte de `elegir_archivo` porque es el cuadro contrario: aquel exige
        que el archivo exista y este pregunta donde crear uno. pywebview los
        distingue por el tipo de dialogo, no por una bandera.
        """
        if self.ventana is None:
            return {"ok": False, "ruta": "", "error": "sin ventana"}
        import webview

        ruta = self.ventana.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=nombre or "",
            file_types=tuple(filtros) if filtros else ())
        # Segun la plataforma vuelve una cadena o una lista de una.
        if isinstance(ruta, (list, tuple)):
            ruta = ruta[0] if ruta else ""
        return {"ok": bool(ruta), "ruta": str(ruta or "")}


def ruta_web() -> str:
    """La carpeta `web/`, tanto en el repo como congelada.

    PyInstaller descomprime los datos en `sys._MEIPASS`, asi que la ruta al
    lado del fuente no existe ahi. Se prueban las dos y se falla con el nombre
    de las dos: un "no encuentro index.html" a secas no dice donde busco.
    """
    import sys

    candidatas = [os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web")]
    base = getattr(sys, "_MEIPASS", "")
    if base:
        candidatas.insert(0, os.path.join(base, "web"))
    for ruta in candidatas:
        if os.path.exists(os.path.join(ruta, "index.html")):
            return ruta
    raise FileNotFoundError("no encuentro web/index.html en: " + ", ".join(candidatas))


def abrir() -> None:
    import webview

    from . import store, tema

    cfg = store.load_config()
    paleta = tema.resolver(cfg, "ui")
    # El puente necesita la ventana para los cuadros de elegir archivo, y la
    # ventana necesita el puente para crearse. Se corta atandolo despues: es un
    # ciclo de una linea, no un problema de diseno.
    puente = Puente()
    puente.ventana = webview.create_window(
        "Eve · Configuracion",
        os.path.join(ruta_web(), "index.html"),
        js_api=puente,
        width=1060, height=760, min_size=(880, 560),
        # El fondo de la ventana ANTES de que cargue el HTML. Sin esto se ve un
        # flash blanco al abrir, que con un tema oscuro es un fogonazo.
        background_color=paleta["fondo"],
    )
    webview.start()
