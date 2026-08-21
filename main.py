"""LLMJarvis - punto de entrada unico.

Empaquetado no hay `python` ni archivos `.py` sueltos que invocar, asi que el
mismo binario despacha sus sub-herramientas por flag antes de arrancar la
bandeja. Desde el codigo cada una sigue siendo un modulo normal.

    Eve.exe            asistente (bandeja + atajo global)
    Eve.exe --panel    panel de configuracion
    Eve.exe --cli ...  conexiones con apps (lo llama el modelo)
    Eve.exe --hook     freno del motor claude-code
    Eve.exe --overlay  el cartel flotante
    Eve.exe --consola  la ventana de actividad (modo Work / modo Edit)
    Eve.exe --check       diagnostico
    Eve.exe --probar-voz  autotest: sintetiza una frase y la transcribe
    Eve.exe --actualizar  busca una version nueva (--instalar para aplicarla)
    Eve.exe --probar-imports  lo corre build.py: verifica el paquete armado
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


# Modulos que TIENEN que poder importarse en el binario empaquetado. Los corre
# `build.py` sobre el ejecutable recien armado: `IMPRESCINDIBLES` verifica que un
# archivo de datos viaje, pero un submodulo que NO viaja no se nota hasta que el
# usuario usa la funcion. Es exactamente la falla que describe `eve/imagenes.py`
# y por la que se evito `ImageTk` a mano durante todo el proyecto.
IMPORTS_CRITICOS = [
    "PIL.Image",
    "PIL.ImageTk",   # el puente PIL->tkinter: sin el no hay compositor de modulos
    "numpy",
    "sounddevice",
    "keyring",
    "faster_whisper",
    "piper",
    "onnxruntime",
    "onnx_asr",      # el reconocedor opcional de NVIDIA; rueda pura, sin deps nuevas
    # El icono de bandeja. Sin el no hay forma de llegar al panel ni de salir:
    # el proceso queda corriendo sin nada en pantalla, que es indistinguible de
    # que Eve no arranco.
    "pystray",
    "tkinter",
]
# El atajo global, que es EL feature: sin esto Eve corre y no responde a nada.
# Es Windows contra el resto y por eso no puede ir en la lista de arriba.
IMPORTS_CRITICOS += ["keyboard"] if sys.platform == "win32" else ["pynput"]

# Los modulos de Eve que NINGUN import a nivel de modulo alcanza: los carga el
# codigo cuando hacen falta, o los lanza otro proceso. PyInstaller no los ve
# solo, por eso estan en OCULTOS de build.py, y esta lista es lo que comprueba
# que esa entrada sigue estando. Sin esto, borrar un nombre de OCULTOS sale en
# verde y la funcion falla recien cuando el usuario la usa, en la version
# instalada y no en la de desarrollo, que es la peor clase de falla.
PROPIOS_DIFERIDOS = [
    "eve.brain", "eve.cc_engine", "eve.ollama_engine", "eve.compat_engine",
    "eve.gui", "eve.consola", "eve.overlay", "eve.integrations", "eve.hook_gate",
    "eve.voices", "eve.modulos", "eve.lienzo", "eve.prompt",
    "eve.lector", "eve.grafo", "eve.memoria", "eve.despertar", "eve.retrato",
]
if sys.platform == "win32":
    # Lo usa `plataforma.archivo_de_fuente` para traducir "Constantia" a
    # "constan.ttf". Va importado adentro de una funcion, que es justo el caso
    # que PyInstaller puede no ver.
    IMPORTS_CRITICOS.append("winreg")


def _probar_imports() -> int:
    """Importa lo critico y devuelve 1 si falta algo. Corre DENTRO del paquete."""
    import importlib

    faltan = []
    for nombre in IMPORTS_CRITICOS + PROPIOS_DIFERIDOS:
        try:
            importlib.import_module(nombre)
        except Exception as exc:  # noqa: BLE001 - vale cualquier motivo
            faltan.append(f"{nombre}: {type(exc).__name__}: {exc}")
        else:
            print(f"  ok  {nombre}")
    if faltan:
        print("")
        print("No se pudieron importar:")
        for linea in faltan:
            print("  " + linea)
        return 1
    print("")
    print(f"Los {len(IMPORTS_CRITICOS)} imports criticos y los "
          f"{len(PROPIOS_DIFERIDOS)} modulos diferidos andan.")
    return 0


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
        if flag == "--consola":
            from eve import consola

            return consola.main(resto)
        if flag == "--retrato":
            # Dibuja los modulos a un PNG sin abrir ninguna ventana. Sirve para
            # ver un perfil ajeno antes de aplicarlo y para testear lo visual.
            from eve import retrato

            return retrato.main(resto)
        if flag == "--overlay":
            from eve import overlay

            return overlay.main(resto)
        if flag == "--dialogo":
            # Lo llama plataforma cuando necesita un dialogo fuera de Windows y
            # macOS: congelado no hay un python al que pasarle `-c`.
            from eve import plataforma

            return plataforma.dialogo_cli(resto)
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
            except Exception as exc:  # noqa: BLE001 - sin Piper se usa la voz del sistema
                from eve import plataforma

                if not plataforma.WINDOWS:
                    # Fuera de Windows no hay voz del sistema a la que caer.
                    print(f"ERROR: no pude sintetizar con Piper: {exc}")
                    print("Bajate una voz con:  eve --descargar-voz es_ES-davefx-medium")
                    return 1
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
        if flag == "--probar-imports":
            return _probar_imports()

    from eve import listener as listener_mod
    from eve import store, tray

    cfg = store.load_config()

    # Una sola Eve por maquina. El cartel ya tenia su guarda; el asistente no, y
    # es el que importa: dos listeners son dos hooks globales sobre la misma
    # tecla. Va antes de lanzar el cartel para no dejar procesos sueltos.
    otro = store.otro_asistente()
    if otro:
        print(f"Eve ya esta corriendo (pid {otro}). Usa el icono de la bandeja.")
        return 0

    # El cartel se lanza ANTES de armar el motor: no depende de el, y armarlo
    # tarda varios segundos. Medido, asi tardaba nueve en aparecer, y en esa
    # ventana apretar la tecla no mostraba nada.
    from eve import overlay

    overlay.asegurar(cfg)  # corre aparte y se cierra solo cuando Eve sale

    if str(cfg.get("consola_modo", "nunca")) == "con_eve":
        # Igual que el cartel: proceso aparte, para que colgarse no se lleve
        # puesto al asistente.
        from eve import consola

        consola.abrir()

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
        # caduque, y el cartel se queda en pantalla otro rato.
        try:
            os.remove(store.LATIDO_PATH)
        except OSError:
            pass
        store.pedir_salida_overlay(esperar=2.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
