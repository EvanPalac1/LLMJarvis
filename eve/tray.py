"""Icono en la bandeja del sistema. Clic izquierdo abre el panel."""

import os
import subprocess
import sys
import threading

import pystray

from . import icon as icon_mod


def open_panel() -> None:
    # Proceso aparte: tkinter y pystray no comparten mainloop sin dolor.
    from . import plataforma

    if plataforma.congelado():
        # Binario propio al lado del principal, no un modulo de Python.
        exe = os.path.join(
            os.path.dirname(sys.executable),
            "Eve-config.exe" if plataforma.WINDOWS else "Eve-config",
        )
        if os.path.exists(exe):
            subprocess.Popen([exe])
            return
    subprocess.Popen(plataforma.comando_propio("--panel"), cwd=_project_root())


def _project_root() -> str:
    from . import plataforma

    return plataforma.recursos()


def _title(listener) -> str:
    estado = "pausado" if listener.paused else "activo"
    return f"LLMJarvis - {listener.cfg['assistant_name']} ({estado}, {listener.cfg['hotkey']})"


def build(listener) -> pystray.Icon:
    def toggle_pause(icon, item):  # noqa: ANN001
        listener.paused = not listener.paused
        icon.title = _title(listener)

    def _en_hilo(icon, trabajo):
        """Los callbacks del menu corren en el hilo que bombea los mensajes de la
        bandeja. Cualquier cosa lenta ahi congela el icono, asi que se delega."""
        threading.Thread(target=trabajo, args=(icon,), daemon=True).start()

    def restart(icon, item):  # noqa: ANN001
        def trabajo(icon):
            try:
                listener.restart()
                icon.title = _title(listener)
                _avisar(icon, f"Listo. Tecla: {listener.cfg['hotkey']}", "Listener reiniciado")
            except Exception as exc:  # noqa: BLE001 - el icono no puede morir por esto
                _avisar(icon, str(exc)[:200], "No pude reiniciar el listener")

        _en_hilo(icon, trabajo)

    def limpiar(icon, item):  # noqa: ANN001
        def trabajo(icon):
            from . import store

            n = store.clear_history()
            listener.eve.reset_context()
            _avisar(icon, f"{n} mensajes borrados y contexto en cero.", "Historial limpiado")

        _en_hilo(icon, trabajo)

    def actualizar(icon, item):  # noqa: ANN001
        def trabajo(icon):
            from . import plataforma, updater

            if not plataforma.congelado():
                _avisar(icon, "Corriendo desde el codigo: actualiza con git pull.", "Actualizar")
                return
            try:
                nueva = updater.buscar()
            except RuntimeError as exc:
                _avisar(icon, str(exc), "Actualizar")
                return
            if not nueva:
                _avisar(icon, f"Ya tenes la ultima ({updater.version_actual()}).", "Actualizar")
                return
            if not nueva["asset"]:
                _avisar(icon, f"Hay {nueva['version']}, pero aun sin paquete para tu sistema.",
                        "Actualizar")
                plataforma.abrir(nueva["url"])
                return
            # Descargar y ejecutar un instalador no se hace a espaldas del usuario.
            if not plataforma.preguntar(
                f"Hay una version nueva: {nueva['version']}\n"
                f"Tenes la {updater.version_actual()}.\n\n"
                "Se descarga, se verifica su firma sha256 y se instala encima.\n"
                "Tus datos y tu configuracion no se tocan.\n\n"
                "Actualizar ahora?",
                "Actualizar Eve",
            ):
                return
            _avisar(icon, "Descargando...", "Actualizar")
            try:
                ruta = updater.descargar(nueva["asset"])
            except (ValueError, OSError) as exc:
                _avisar(icon, str(exc), "No pude actualizar")
                return
            _avisar(icon, updater.instalar(ruta), "Actualizar")
            icon.stop()  # liberar el .exe para que el instalador lo reemplace

        _en_hilo(icon, trabajo)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir panel", lambda: open_panel(), default=True),
        pystray.MenuItem("Limpiar historial y contexto", limpiar),
        pystray.MenuItem("Reiniciar listener (aplicar config)", restart),
        pystray.MenuItem(
            "Pausar listener", toggle_pause, checked=lambda _: listener.paused
        ),
        pystray.MenuItem("Buscar actualizaciones", actualizar),
        pystray.MenuItem("Salir", lambda icon: icon.stop()),
    )
    return pystray.Icon("LLMJarvis", icon_mod.tray_image(), _title(listener), menu)


def _avisar(icon, msg: str, titulo: str = "LLMJarvis") -> None:
    """Notificacion nativa de la bandeja, no un modal.

    Antes esto abria un MessageBox con MB_SYSTEMMODAL desde el hilo que bombea
    los mensajes del icono: ese hilo quedaba bloqueado dentro del dialogo, que es
    justo el que tiene que procesar el clic en Aceptar. El resultado era una
    ventana que no se podia cerrar.
    """
    try:
        icon.notify(msg, titulo)
    except Exception:  # noqa: BLE001 - no todos los entornos soportan globos
        print(f"[{titulo}] {msg}")
