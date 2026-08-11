"""Icono en la bandeja del sistema. Clic izquierdo abre el panel."""

import subprocess
import sys

import pystray

from . import icon as icon_mod


def open_panel() -> None:
    # Proceso aparte: tkinter y pystray no comparten mainloop sin dolor.
    subprocess.Popen([sys.executable, "-m", "eve.gui"], cwd=_project_root())


def _project_root() -> str:
    import os

    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _title(listener) -> str:
    estado = "pausado" if listener.paused else "activo"
    return f"LLMJarvis - {listener.cfg['assistant_name']} ({estado}, {listener.cfg['hotkey']})"


def build(listener) -> pystray.Icon:
    def toggle_pause(icon, item):  # noqa: ANN001
        listener.paused = not listener.paused
        icon.title = _title(listener)

    def restart(icon, item):  # noqa: ANN001
        try:
            listener.restart()
            icon.title = _title(listener)
            _notify(f"Listener reiniciado con la config guardada.\nTecla: {listener.cfg['hotkey']}")
        except Exception as exc:  # noqa: BLE001 - el icono no puede morir por esto
            _notify(f"No pude reiniciar el listener:\n\n{exc}", error=True)

    def limpiar(icon, item):  # noqa: ANN001
        from . import store

        n = store.clear_history()
        listener.eve.reset_context()
        _notify(f"Historial borrado ({n} mensajes) y contexto en cero.\nEl registro de acciones se conservo.")

    menu = pystray.Menu(
        pystray.MenuItem("Abrir panel", lambda: open_panel(), default=True),
        pystray.MenuItem("Limpiar historial y contexto", limpiar),
        pystray.MenuItem("Reiniciar listener (aplicar config)", restart),
        pystray.MenuItem(
            "Pausar listener", toggle_pause, checked=lambda _: listener.paused
        ),
        pystray.MenuItem("Salir", lambda icon: icon.stop()),
    )
    return pystray.Icon("LLMJarvis", icon_mod.tray_image(), _title(listener), menu)


def _notify(msg: str, error: bool = False) -> None:
    from . import plataforma

    plataforma.avisar(msg, "LLMJarvis", error=error)
