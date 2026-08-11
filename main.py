"""LLMJarvis - punto de entrada unico.

Empaquetado no hay `python` ni archivos `.py` sueltos que invocar, asi que el
mismo binario despacha sus sub-herramientas por flag antes de arrancar la
bandeja. Desde el codigo cada una sigue siendo un modulo normal.

    Eve.exe            asistente (bandeja + atajo global)
    Eve.exe --panel    panel de configuracion
    Eve.exe --cli ...  conexiones con apps (lo llama el modelo)
    Eve.exe --hook     freno del motor claude-code
    Eve.exe --check    diagnostico
"""

import sys


def _flag_por_nombre() -> str:
    """Los tres binarios salen de este mismo archivo; se distinguen por su nombre.

    Empaquetar un solo entry point y renombrar el ejecutable evita triplicar la
    copia de Python y las librerias, que son casi todo el peso.
    """
    import os

    nombre = os.path.basename(sys.executable).lower()
    return "--panel" if "config" in nombre else ""


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        implicito = _flag_por_nombre()
        if implicito:
            argv = [implicito]

    if argv and argv[0].startswith("--"):
        flag, resto = argv[0], argv[1:]

        if flag == "--cli":
            from eve import integrations

            return integrations.main(resto)
        if flag == "--hook":
            from eve import hook_gate

            return hook_gate.main()
        if flag == "--panel":
            from eve.gui import Panel

            Panel().mainloop()
            return 0
        if flag == "--check":
            import diagnostico

            sys.argv = [sys.argv[0], *resto]
            return diagnostico.main()
        if flag == "--descargar-modelo":
            # Lo llama el instalador si el usuario marco bajarlo durante la
            # instalacion, en vez de esperar al primer uso.
            from faster_whisper import WhisperModel

            from eve import store

            WhisperModel(store.load_config()["stt_model"], device="cpu", compute_type="int8")
            print("Modelo de voz descargado.")
            return 0
        if flag == "--descargar-voz":
            from eve import store, voices

            clave = resto[0] if resto else "es_ES-davefx-medium"
            print(voices.descargar(clave))
            cfg = store.load_config()
            cfg.update({"tts_provider": "piper", "piper_voice": clave})
            store.save_config(cfg)
            return 0
        if flag in ("--version", "-v"):
            from eve import __version__

            print(f"LLMJarvis {__version__}")
            return 0
        if flag in ("--help", "-h"):
            print(__doc__)
            return 0

    from eve import listener as listener_mod
    from eve import store, tray

    cfg = store.load_config()
    try:
        lis = listener_mod.Listener(cfg)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Abriendo el panel de configuracion...")
        tray.open_panel()
        return 1

    lis.start()
    icono = tray.build(lis)
    # El panel corre aparte; al guardar cambia config.json y el listener se rearma
    # solo. El icono actualiza su tooltip para que se note que paso.
    lis.watch_config(on_reload=lambda l: setattr(icono, "title", tray._title(l)))
    icono.run()  # bloquea hasta 'Salir'
    return 0


if __name__ == "__main__":
    sys.exit(main())
