"""Icono en la bandeja del sistema. Clic izquierdo abre el panel."""

import os
import subprocess
import sys
import threading

import pystray

from . import icon as icon_mod
from .textos import t as tr


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
            plataforma.lanzar([exe])
            return
    plataforma.lanzar(plataforma.comando_propio("--panel"), cwd=_project_root())


def _abrir_consola() -> None:
    """La ventana de actividad, como proceso aparte igual que el panel."""
    from . import consola

    consola.abrir()


def _project_root() -> str:
    from . import plataforma

    return plataforma.recursos()


def _title(listener) -> str:
    # Con `.get` y no con corchetes: el titulo se recalcula cada vez que cambia
    # la config, y una clave que falte tira KeyError adentro del hilo que bombea
    # los mensajes del icono. O sea, se lleva puesta la bandeja entera por un
    # campo de texto.
    cfg = listener.cfg
    estado = tr("pausado") if listener.paused else tr("activo")
    return (f"LLMJarvis - {cfg.get('assistant_name', 'Eve')} "
            f"({estado}, {cfg.get('hotkey', '?')})")


def build(listener) -> pystray.Icon:
    # El menu se arma una sola vez, asi que el idioma se fija ahora. Cambiarlo
    # despues pide reiniciar el asistente; el panel ya lo dice.
    from . import textos

    textos.desde_config(listener.cfg)

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
                _avisar(icon, f"Listo. Tecla: {listener.cfg['hotkey']}", tr("Listener reiniciado"))
            except Exception as exc:  # noqa: BLE001 - el icono no puede morir por esto
                _avisar(icon, str(exc)[:200], tr("No pude reiniciar el listener"))

        _en_hilo(icon, trabajo)

    def limpiar(icon, item):  # noqa: ANN001
        def trabajo(icon):
            from . import store

            n = store.clear_history()
            listener.eve.reset_context()
            _avisar(icon, f"{n} mensajes borrados y contexto en cero.", tr("Historial limpiado"))

        _en_hilo(icon, trabajo)

    def actualizar(icon, item):  # noqa: ANN001
        def trabajo(icon):
            from . import plataforma, updater

            if not plataforma.congelado():
                _avisar(icon, tr("Corriendo desde el codigo: actualiza con git pull."), tr("Actualizar"))
                return
            try:
                nueva = updater.buscar()
            except RuntimeError as exc:
                _avisar(icon, str(exc), tr("Actualizar"))
                return
            if not nueva:
                _avisar(icon, f"Ya tienes la ultima ({updater.version_actual()}).", tr("Actualizar"))
                return
            if not nueva["asset"]:
                _avisar(icon, f"Hay {nueva['version']}, pero aun sin paquete para tu sistema.",
                        tr("Actualizar"))
                plataforma.abrir(nueva["url"])
                return
            # Descargar y ejecutar un instalador no se hace a espaldas del usuario.
            if not plataforma.preguntar(
                f"Hay una version nueva: {nueva['version']}\n"
                f"Tienes la {updater.version_actual()}.\n\n"
                "Se descarga, se verifica su firma sha256 y se instala encima.\n"
                "Tus datos y tu configuracion no se tocan.\n\n"
                "Actualizar ahora?",
                tr("Actualizar Eve"),
            ):
                return
            _avisar(icon, tr("Descargando..."), tr("Actualizar"))
            try:
                ruta = updater.descargar(nueva["asset"])
            except (ValueError, OSError) as exc:
                _avisar(icon, str(exc), tr("No pude actualizar"))
                return
            _avisar(icon, updater.instalar(ruta), tr("Actualizar"))
            icon.stop()  # liberar el .exe para que el instalador lo reemplace

        _en_hilo(icon, trabajo)

    def _item_perfil(nombre: str):
        """Arma el item de un perfil.

        El nombre se captura con una fabrica y NO con un parametro por defecto:
        pystray cuenta los argumentos del callback y rechaza cualquiera con mas
        de dos, asi que un `def cambiar(icon, item, nombre=nombre)` levanta
        ValueError y se lleva puesto el arranque entero de la bandeja.
        """
        from . import store

        def cambiar(icon, item):
            def trabajo(icon):
                try:
                    store.aplicar_perfil(nombre)
                    # No se llama a listener.restart(): el watcher de
                    # config.json lo hace solo, y asi hay un unico camino.
                    _avisar(icon, f"Perfil {nombre} aplicado.", tr("Perfiles"))
                except (ValueError, OSError) as exc:
                    _avisar(icon, str(exc)[:200], tr("No pude cambiar de perfil"))

            _en_hilo(icon, trabajo)

        def marcado(_item):
            return listener.cfg.get("perfil_activo") == nombre

        return pystray.MenuItem(nombre, cambiar, checked=marcado, radio=True)

    def perfiles():
        """Submenu para cambiar de perfil sin abrir el panel.

        Se arma cada vez que se despliega el menu, asi aparecen los perfiles
        nuevos sin reiniciar la bandeja. Devuelve una tupla y no un generador:
        pystray recorre los items mas de una vez y un generador ya agotado
        dejaria el submenu vacio la segunda.
        """
        from . import store

        # Envuelto porque este callable corre DENTRO del procedimiento de
        # ventana, cada vez que se despliega el menu. Si tira --un perfiles.json
        # a medio escribir alcanza-- no se pierde el submenu: se pierde el MENU
        # ENTERO, y el sintoma que ve el usuario es un clic derecho que no
        # muestra absolutamente nada, sin ninguna pista de por que.
        try:
            guardados = sorted(store.listar_perfiles())
        except Exception as exc:  # noqa: BLE001 - el menu no puede morir por esto
            return (pystray.MenuItem(f"({exc})", lambda: None, enabled=False),)
        if not guardados:
            return (pystray.MenuItem(tr("(no hay perfiles guardados)"),
                                     lambda: None, enabled=False),)
        return tuple(_item_perfil(n) for n in guardados)

    menu = pystray.Menu(
        pystray.MenuItem(tr("Abrir panel"), lambda: open_panel(), default=True),
        pystray.MenuItem(tr("Ventana de actividad"), lambda: _abrir_consola()),
        pystray.MenuItem(tr("Perfiles"), pystray.Menu(perfiles)),
        pystray.MenuItem(tr("Limpiar historial y contexto"), limpiar),
        pystray.MenuItem(tr("Reiniciar listener (aplicar config)"), restart),
        pystray.MenuItem(
            tr("Pausar listener"), toggle_pause, checked=lambda _: listener.paused
        ),
        pystray.MenuItem(tr("Buscar actualizaciones"), actualizar),
        pystray.MenuItem(tr("Salir"), lambda icon: icon.stop()),
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
