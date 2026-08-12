"""LLMJarvis - punto de entrada unico.

Empaquetado no hay `python` ni archivos `.py` sueltos que invocar, asi que el
mismo binario despacha sus sub-herramientas por flag antes de arrancar la
bandeja. Desde el codigo cada una sigue siendo un modulo normal.

    Eve.exe            asistente (bandeja + atajo global)
    Eve.exe --panel    panel de configuracion
    Eve.exe --cli ...  conexiones con apps (lo llama el modelo)
    Eve.exe --hook     freno del motor claude-code
    Eve.exe --check       diagnostico
    Eve.exe --probar-voz  autotest: sintetiza una frase y la transcribe
    Eve.exe --actualizar  busca una version nueva (--instalar para aplicarla)
"""

import os
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
        if flag == "--actualizar":
            from eve import updater

            return updater.main(resto)
        if flag == "--descargar-modelo":
            # Lo llama el instalador si el usuario marco bajarlo durante la
            # instalacion, en vez de esperar al primer uso.
            from faster_whisper import WhisperModel

            from eve import store

            WhisperModel(store.load_config()["stt_model"], device="cpu", compute_type="int8")
            print("Modelo de voz descargado.")
            return 0
        if flag == "--probar-voz":
            # Sintetiza una frase y la vuelve a transcribir. Recorre el mismo
            # camino que una orden hablada, que es donde fallo la v1.0.0: el
            # modelo VAD no viajaba en el paquete y no habia forma de notarlo
            # sin hablarle.
            import wave

            import numpy as np

            from eve import store, voice

            frase = " ".join(resto) or "probando la voz de Eve, uno dos tres"
            cfg = store.load_config()
            print(f"sintetizando: {frase!r}")
            try:
                from eve import voices

                clave = cfg.get("piper_voice") or (voices.instaladas() or [None])[0]
                if not clave:
                    raise RuntimeError("sin voz de Piper")
                ruta = voices.hablar(frase, clave)
            except Exception:  # noqa: BLE001 - sin Piper se usa la voz del sistema
                import pyttsx3
                import tempfile

                ruta = os.path.join(tempfile.gettempdir(), "eve_prueba.wav")
                motor = pyttsx3.init()
                motor.save_to_file(frase, ruta)
                motor.runAndWait()
                motor.stop()

            with wave.open(ruta, "rb") as w:
                audio = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
                rate = w.getframerate()
            audio = audio.astype("float32") / 32768.0
            if rate != 16000:
                idx = (np.arange(int(len(audio) * 16000 / rate)) * rate / 16000).astype(int)
                audio = audio[idx]

            print("transcribiendo...")
            print(f"resultado: {voice.transcribe(audio, cfg)!r}")
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

    from eve import updater

    # Chequeo silencioso: si no hay internet o no hay novedad, no molesta.
    updater.revisar_en_segundo_plano(
        lambda nueva: tray._avisar(
            icono, f"Version {nueva['version']} disponible. Bandeja > Buscar actualizaciones.",
            "Hay una actualizacion",
        )
    )
    # El panel corre aparte; al guardar cambia config.json y el listener se rearma
    # solo. El icono actualiza su tooltip para que se note que paso.
    lis.watch_config(on_reload=lambda l: setattr(icono, "title", tray._title(l)))
    try:
        icono.run()  # bloquea hasta 'Salir'
    finally:
        # Sin esto el panel cree que el asistente sigue vivo hasta que el latido
        # caduque.
        try:
            os.remove(store.LATIDO_PATH)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
