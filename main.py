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
    "rlottie_python",  # las animaciones vectoriales; import diferido en lienzo
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
    # Los textos de la interfaz. Lo importan gui, tray y consola a nivel de
    # modulo, asi que PyInstaller deberia verlo solo --pero sin el no arranca
    # NINGUNA de las tres ventanas, y ese es exactamente el tipo de cosa que se
    # da por sentada hasta que un dia no viaja.
    "eve.textos",
    # Los dos entran por un `from . import` adentro de una funcion, asi que
    # PyInstaller los levanta solo --comprobado sobre el binario de la 1.17.0--
    # pero nada lo garantizaba. Un modulo que se importa tarde y no viajo se
    # rompe recien al usarse, que es el modo de falla que esta lista existe
    # para atrapar: `comandos` lo llama el listener al oirte y `skills` el
    # prompt en cada llamada.
    "eve.comandos",
    "eve.skills",
    # Igual que los dos de arriba: `gui` lo importa a nivel de modulo pero
    # `integrations` lo trae adentro de una funcion, y es el que arma el prompt
    # en cada llamada. Un cliente MCP que no viajo se rompe recien cuando
    # alguien enciende un servidor, o sea despues de la release.
    "eve.mcp",
    # El motor por GPU. Los dos importan SIN `skia` ni `PyOpenGL` --las traen
    # adentro de funciones, para que su ausencia no impida arrancar-- asi que
    # comprobarlos aca vale en los cinco objetivos, incluido macOS, donde las
    # librerias no se instalan. Lo que se comprueba es que los MODULOS viajen;
    # que la capacidad sirva lo dice `--probar-gpu`, que abre un contexto de
    # verdad y cuenta pixeles.
    "eve.lienzo_skia", "eve.marco_gl",
]
if sys.platform == "win32":
    # Lo usa `plataforma.archivo_de_fuente` para traducir "Constantia" a
    # "constan.ttf". Va importado adentro de una funcion, que es justo el caso
    # que PyInstaller puede no ver.
    IMPORTS_CRITICOS.append("winreg")


# Estos abren una conexion con el servidor de ventanas al importarse. En un
# runner sin pantalla eso revienta, y no dice nada sobre si el modulo viajo.
NECESITAN_PANTALLA = ("pystray", "pynput")

SIN_PANTALLA = ("display", "DisplayName", "X connection", "_xorg", "$DISPLAY")


def _es_falta_de_pantalla(exc: BaseException) -> bool:
    """Si el import fallo por no haber servidor de ventanas, no por faltar.

    Se mira el texto del error y no el tipo porque cada libreria elige el suyo:
    pystray tira `Xlib.error.DisplayNameError` y pynput un `ImportError` con el
    motivo adentro del mensaje.
    """
    texto = f"{type(exc).__name__}: {exc}"
    return any(marca in texto for marca in SIN_PANTALLA)


def _probar_imports() -> int:
    """Verifica que lo critico VIAJE en el binario. Corre DENTRO del paquete.

    "No viajo" y "no hay pantalla" no son lo mismo, y confundirlos freno un
    release entero: `pystray` y `pynput` abrian una conexion con X al importarse
    y en el runner de Linux no hay ninguna, asi que el paquete --que estaba
    perfecto-- se reportaba como incompleto.

    Cuando el import falla por falta de pantalla se cae a buscar el spec del
    modulo, que es lo que de verdad contesta la pregunta y no necesita display.
    """
    import importlib
    import importlib.util

    faltan = []
    for nombre in IMPORTS_CRITICOS + PROPIOS_DIFERIDOS:
        try:
            importlib.import_module(nombre)
        except Exception as exc:  # noqa: BLE001 - vale cualquier motivo
            sin_pantalla = nombre in NECESITAN_PANTALLA and _es_falta_de_pantalla(exc)
            if not sin_pantalla:
                faltan.append(f"{nombre}: {type(exc).__name__}: {exc}")
                continue
            try:
                viaja = importlib.util.find_spec(nombre) is not None
            except Exception:  # noqa: BLE001 - un spec roto tambien es no viajar
                viaja = False
            if viaja:
                print(f"  ok  {nombre}  (viaja; sin pantalla para importarlo)")
            else:
                faltan.append(f"{nombre}: no viaja en el paquete")
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


# Lo que entra en el globo de la bandeja de Windows: `NOTIFYICONDATAW.szInfo`
# es un WCHAR[256] y `szInfoTitle` un WCHAR[64]. Se deja margen a proposito para
# que una traduccion mas larga no quede al borde.
TOPE_GLOBO, TOPE_TITULO_GLOBO = 250, 60


def _avisar_donde_esta(icono) -> None:
    """La primera vez que Eve corre, decir DONDE quedo su icono.

    Windows 11 manda los iconos nuevos al desplegable de la flechita y no a la
    barra de tareas. Medido en la PC donde se encontro esto: de 88 iconos
    registrados hay UNO promovido a la barra, y es de Microsoft --Steam,
    Discord, Spotify, OBS y NVIDIA estan todos guardados donde esta Eve.

    Sin esto Eve arranca, anda, registra el icono, y no da ninguna señal de
    donde esta. Desde afuera eso es indistinguible de que no arranco: se
    reporto dos veces como "no aparece el proceso".

    La marca va en un archivo y no en una clave de config: no es una
    preferencia del usuario, es algo que pasa una vez. Y todo el cuerpo va
    envuelto porque un globo que no se puede mostrar no puede impedir que Eve
    arranque.
    """
    from eve import store, textos  # adentro: main.py no los importa arriba
    from eve.textos import t as tr

    marca = os.path.join(store.BASE, ".aviso_bandeja")
    try:
        if os.path.exists(marca):
            return
        textos.desde_config(store.load_config())
        # Recortado a lo que entra en el globo de Windows: `szInfo` es un
        # WCHAR[256] y `szInfoTitle` un WCHAR[64], y pasarse hace que ctypes
        # rechace la llamada entera. Ya paso: el mensaje en espanol tenia 273
        # caracteres, el `except` de abajo se comio el error, y el aviso no
        # salio nunca sin dejar rastro. Que el que traduce tenga que acordarse
        # del tamano de un struct de Win32 es pedirle que falle.
        icono.notify(
            tr("Estoy en el desplegable de la flechita de la barra de tareas, con "
               "Steam y Discord. Arrastrame fuera para fijarme en la "
               "barra.")[:TOPE_GLOBO],
            tr("Eve esta corriendo")[:TOPE_TITULO_GLOBO],
        )
        with open(marca, "w", encoding="utf-8") as f:
            f.write("mostrado una vez\n")
    except Exception:  # noqa: BLE001 - arrancar no puede fallar por un globo
        pass


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

        if flag == "--probar-gpu":
            # La puerta que le falta al motor por GPU: que ande en los CINCO
            # objetivos. Vive aca y no en un script suelto para que CI lo corra
            # igual que `--probar-imports`, sobre el binario si hace falta.
            from eve import gpu

            return gpu.probar_a_fondo()

        if flag == "--bench-dibujo":
            # Mide los dos motores de dibujo sobre la misma escena, adentro de
            # Eve. Vive aca y no en un script suelto porque los bancos sueltos
            # ya dieron tres numeros falsos: medir el motor de verdad es lo
            # unico que no se puede falsear sin querer.
            from eve import bench_dibujo

            return bench_dibujo.correr(resto[0] if resto else "")

    from eve import listener as listener_mod
    from eve import store, tray

    cfg = store.load_config()

    # Una sola Eve por maquina. El cartel ya tenia su guarda; el asistente no, y
    # es el que importa: dos listeners son dos hooks globales sobre la misma
    # tecla. Va antes de lanzar el cartel para no dejar procesos sueltos.
    otro = store.otro_asistente()
    if otro:
        # Volver a abrir Eve estando ya abierta ABRE EL PANEL, no se va en
        # silencio. Es lo que hace cualquier programa de bandeja: doble clic
        # sobre Steam abierto te trae su ventana.
        #
        # Por que importa tanto: el instalador deja `Eve.lnk` en la carpeta de
        # Inicio, asi que despues de prender la PC ya hay una Eve corriendo
        # SIEMPRE. Cada doble clic caia aca. Y como `Eve.exe` se arma sin
        # consola, el `print` de abajo no lo lee nadie: no pasaba nada visible.
        # Con `Eve-debug.exe` --el mismo codigo pero con consola-- si aparecia
        # una ventana con el mensaje, asi que el sintoma se reporto como "el de
        # debug abre y el normal no". Los dos hacian exactamente lo mismo.
        #
        # No es un MessageBox: `MessageBoxW` medido en esta maquina devuelve
        # IDOK al instante sin dibujarse cuando el proceso no tiene escritorio
        # interactivo, o sea que el aviso puede no existir y nadie se entera.
        # Una ventana de verdad no se puede confundir con nada.
        print(f"Eve ya esta corriendo (pid {otro}). Abro el panel.")
        try:
            tray.open_panel()
        except Exception as exc:  # noqa: BLE001 - salir no puede fallar por esto
            print(f"no pude abrir el panel: {exc}")
        return 0

    # El motor se arma ANTES de lanzar las ventanas hijas. Estaba al reves --el
    # cartel primero, porque armarlo tarda y asi aparecia antes-- y eso convertia
    # una config mala en el sintoma mas confuso del proyecto: el cartel y la
    # ventana de actividad ya estaban en pantalla cuando el motor fallaba, Eve se
    # iba, y quedaban los dos hijos HUERFANOS hablando con nadie, mas el panel
    # abierto. Desde afuera se ve como "me abre el panel y actividad pero no me
    # sale el segundo plano", que es textual como se reporto tres veces.
    #
    # Se paga que el cartel tarde un poco mas en aparecer. Es barato al lado de
    # dejar dos ventanas sueltas cada vez que el motor no esta configurado.
    lis = listener_mod.Listener(cfg)
    if getattr(lis, "motor_error", ""):
        # Un motor que no se puede armar YA NO impide arrancar. Antes esto se
        # iba con codigo 1 y no abria nada: ni bandeja, ni tecla, ni panel. O
        # sea que un Ollama apagado --o un modelo sin bajar, o una key vencida,
        # o el motor que ni siquiera estabas usando-- dejaba a Eve sin poder
        # abrirse, y la unica forma de arreglarlo era la ventana que tampoco
        # abria. Se avisa, se deja escrito, y se sigue: todo lo que no necesita
        # el motor --que es casi todo-- funciona igual, y el panel esta ahi
        # para arreglarlo. Al guardar, el listener rearma el motor solo.
        #
        # `print` no alcanza: `Eve.exe` se arma windowed y no tiene stdout por
        # ningun camino. Este error tiene que VERSE y quedar ESCRITO. Que la
        # unica rama que falla fuera la unica sin rastro es lo que hizo que
        # esto se reportara tres veces sin poder diagnosticarse.
        print(f"MOTOR NO DISPONIBLE: {lis.motor_error}")
        from eve import plataforma

        try:
            store.log_action("eve", "arranque-sin-motor", lis.motor_error[:300])
        except Exception:  # noqa: BLE001 - el log no puede tapar el error real
            pass
        # En un hilo, porque `avisar` BLOQUEA hasta que alguien apriete OK
        # --en Windows es un MessageBoxW-- y eso dejaba la bandeja y la tecla
        # esperando a que el usuario mirara la pantalla. Medido sobre el
        # binario: el aviso quedo escrito a las 17:47:37 y la bandeja se armo
        # a las 17:48:25, o sea 48 segundos en los que Eve, para el usuario,
        # no existia. Arrancando desde la carpeta de Inicio es peor: el
        # dialogo sale detras de lo que estes haciendo y la tecla no responde
        # hasta que lo encuentres.
        import threading

        threading.Thread(
            target=plataforma.avisar, daemon=True,
            args=(lis.motor_error + chr(10) * 2 + "Eve abre igual: la tecla, "
                  "la bandeja y el panel andan. Lo que no va a poder es "
                  "contestarte hasta que elijas un motor que funcione."
                  + chr(10) * 2 + "Te abri el panel.",
                  "Eve arranco sin motor"),
            kwargs={"error": False}).start()
        tray.open_panel()

    # Con el motor armado o sin el, se lanzan las ventanas hijas.
    from eve import overlay

    overlay.asegurar(cfg)  # corre aparte y se cierra solo cuando Eve sale

    if str(cfg.get("consola_modo", "nunca")) == "con_eve":
        # Igual que el cartel: proceso aparte, para que colgarse no se lleve
        # puesto al asistente.
        from eve import consola

        consola.abrir()

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
    def _bandeja_lista(icono):
        """Corre una vez, cuando pystray ya armo el menu nativo.

        Es el unico punto del programa donde se sabe que el menu se construyo
        sin reventar. En Windows el menu se arma DENTRO del procedimiento de
        ventana: si algo ahi tira, ctypes se come la excepcion, el traceback va
        a un stdout que en el binario no imprime nada, y lo que ve el usuario es
        un icono que al hacerle clic derecho no muestra nada.

        Si esta linea esta en el log y el clic derecho igual no abre nada, el
        problema esta afuera de este codigo; si NO esta, esta aca. Sin ella las
        dos posibilidades se ven exactamente igual.
        """
        try:
            cuantos = len(list(icono.menu))
        except Exception as exc:  # noqa: BLE001
            cuantos = f"error: {exc}"
        try:
            store.log_action("eve", "bandeja", f"menu armado, {cuantos} items")
        except Exception:  # noqa: BLE001
            pass
        icono.visible = True
        _avisar_donde_esta(icono)

    motivo = "sin llegar a arrancar la bandeja"
    try:
        icono.run(setup=_bandeja_lista)  # bloquea hasta 'Salir'
        motivo = "salida normal"
    except BaseException as exc:  # noqa: BLE001 - se re-lanza abajo
        motivo = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # Por que se fue Eve queda ESCRITO, y esto no es paranoia.
        #
        # En la version empaquetada el camino del listener no imprime nada: cero
        # bytes, aunque `--version` y `--check` impriman bien. Asi que si Eve se
        # cierra sola, hoy no queda ni un rastro en ningun lado --ni siquiera en
        # el registro de eventos de Windows, porque salir limpio no es un crash.
        # Se perdio una noche entera creyendo que la app no arrancaba cuando en
        # realidad estaba entera, y sin este renglon la proxima vez pasaria lo
        # mismo.
        try:
            store.log_action("eve", "salida", motivo)
        except Exception:  # noqa: BLE001 - salir nunca puede fallar por el log
            pass
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
