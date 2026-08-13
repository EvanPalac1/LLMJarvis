"""Revisa que falta para que Eve funcione en esta PC.

    python diagnostico.py           -> reporte
    python diagnostico.py --tecla   -> ademas detecta que manda tu keypad
"""

import glob
import os
import shutil
import subprocess
import sys

from eve import plataforma, store

OK, FAIL, WARN = "[ok]  ", "[FALTA]", "[!]   "

DEPS = [
    ("anthropic", "motor 'api' (no hace falta con motor 'claude-code')"),
    # Fuera de Windows el backend del atajo global es pynput, no keyboard.
    ("keyboard" if plataforma.WINDOWS else "pynput", "detectar el boton del keypad"),
    ("sounddevice", "grabar del microfono"),
    ("numpy", "manejar el audio"),
    ("faster_whisper", "transcribir voz a texto"),
    # SAPI es de Windows; en el resto la voz la pone Piper.
    ("pyttsx3" if plataforma.WINDOWS else "piper", "leer las respuestas en voz alta"),
    ("pystray", "icono de bandeja"),
    ("PIL", "icono de bandeja"),
    ("keyring", "guardar las claves"),
]


def check_deps() -> list[str]:
    missing = []
    print("\n== Dependencias ==")
    for mod, why in DEPS:
        try:
            __import__(mod)
            print(f"{OK}{mod}")
        except ImportError:
            print(f"{FAIL} {mod} - {why}")
            missing.append(mod)
        except Exception as exc:  # noqa: BLE001 - el diagnostico no puede morirse aca
            # El modulo esta pero no carga su libreria del sistema: sounddevice
            # sin libportaudio2 tira OSError, no ImportError, y hacia explotar
            # justo a la herramienta que existe para avisar de esto.
            print(f"{FAIL} {mod} - {why}")
            print(f"        {type(exc).__name__}: {exc}")
            missing.append(mod)
    return missing


def check_engine(cfg: dict) -> None:
    print(f"\n== Motor: {cfg['engine']} ==")
    if cfg["engine"] == "claude-code":
        path = shutil.which("claude")
        if not path:
            print(f"{FAIL} CLI 'claude' no encontrado en el PATH.")
            return
        print(f"{OK}CLI en {path}")
        try:
            r = subprocess.run(
                ["claude", "-p", "di solo: ok", "--model", "haiku"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                print(f"{OK}Responde con tu sesion actual (sin API key).")
            else:
                print(f"{FAIL} El CLI fallo. Corre `claude` una vez y logueate.")
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"{FAIL} No pude probar el CLI: {exc}")
    else:
        try:
            key = store.get_key("anthropic")
            print(f"{OK}API key cargada." if key else f"{FAIL} Falta la API key de Anthropic.")
        except Exception as exc:  # noqa: BLE001
            print(f"{FAIL} No pude leer el keyring: {exc}")


def check_mic() -> None:
    print("\n== Microfono ==")
    try:
        import sounddevice as sd
    except ImportError:
        print(f"{FAIL} sounddevice no instalado.")
        return
    inputs = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
    if not inputs:
        print(f"{FAIL} No hay dispositivos de entrada.")
        return
    default = sd.query_devices(kind="input")["name"]
    print(f"{OK}{len(inputs)} entradas. Default: {default}")
    try:
        sd.check_input_settings(samplerate=16000, channels=1)
        print(f"{OK}Disponible a 16 kHz mono.")
    except Exception as exc:  # noqa: BLE001
        print(f"{WARN}Ocupado o incompatible ({exc}). Cerra Discord/OBS/Zoom y reintenta.")


def check_workdirs(cfg: dict) -> None:
    import os

    print("\n== Rutas permitidas ==")
    if not cfg["workdirs"]:
        print(f"{FAIL} Ninguna. Eve no va a poder tocar nada.")
    for d in cfg["workdirs"]:
        print(f"{OK}{d}" if os.path.isdir(d) else f"{WARN}{d} (no existe)")


def detect_key() -> None:
    print("\n== Deteccion de tecla ==")
    try:
        import keyboard
    except ImportError:
        print(f"{FAIL} keyboard no instalado.")
        return
    print("Presiona el boton de tu keypad (Esc para salir)...")
    while True:
        ev = keyboard.read_event()
        if ev.event_type != "down":
            continue
        if ev.name == "esc":
            return
        mods = "+".join(m for m in ("ctrl", "alt", "shift") if keyboard.is_pressed(m))
        combo = f"{mods}+{ev.name}" if mods else ev.name
        print(f"  detectado: '{combo}'   (scan code {ev.scan_code})")
        print(f"  -> poné esto en el panel, campo 'Tecla del keypad': {combo}")


def check_sistema() -> None:
    from eve import plataforma

    print(f"\n== Sistema: {plataforma.NOMBRE} ==")
    print(f"{OK}{plataforma.resumen()}")
    if plataforma.WINDOWS:
        print(f"{OK}Todas las integraciones disponibles.")
    else:
        print(f"{WARN}Outlook, WhatsApp y Discord son solo Windows; avisan en vez de romper.")
        print(f"{WARN}Para TTS usa Piper (panel > Voces): SAPI no existe fuera de Windows.")
    notas = plataforma.notas_permisos()
    if notas:
        print(f"{WARN}{notas}")


def check_voces() -> None:
    from eve import voices

    print("\n== Voces (Piper) ==")
    puestas = voices.instaladas()
    if puestas:
        print(f"{OK}Instaladas: {', '.join(puestas)}")
    else:
        print(f"{WARN}Ninguna descargada. Panel > Voces (obligatorio fuera de Windows).")


def check_recursos() -> None:
    """Que lo que viaja junto al programa este de verdad en el paquete.

    Es la clase de falla que no se nota corriendo desde el codigo, porque ahi
    los archivos estan siempre: aparece solo en la version instalada y en el
    peor momento. Ya paso con el modelo del VAD y con los addons.
    """
    print("\n== Archivos que vienen con el programa ==")
    base = plataforma.recursos()
    manual = os.path.join(base, "EVE.md")
    print(f"{OK if os.path.exists(manual) else FAIL}EVE.md"
          + ("" if os.path.exists(manual) else " - el modelo se queda sin manual"))

    carpeta = os.path.join(base, "perfiles")
    cuantos = len(glob.glob(os.path.join(carpeta, "*.eveperfil")))
    if cuantos:
        print(f"{OK}Perfiles de ejemplo: {cuantos}")
    else:
        print(f"{WARN}Sin perfiles de ejemplo. El boton Importar abre en blanco.")


def main() -> int:
    cfg = store.load_config()
    print(f"Eve = '{cfg['assistant_name']}' | hotkey '{cfg['hotkey']}'")
    check_sistema()
    missing = check_deps()
    check_engine(cfg)
    check_mic()
    check_voces()
    check_workdirs(cfg)
    check_recursos()

    # Instalado desde un paquete no hay pip ni requirements.txt, y el ejecutable
    # no se llama python: mandar a correr eso es mandar a la nada.
    yo = "eve --check" if plataforma.congelado() else "python diagnostico.py"

    # Los addons se importan por nombre: si el empaquetado los dejo afuera, esto
    # es lo unico que lo delata antes de que el usuario los pida por voz.
    print("\n== Addons ==")
    try:
        from eve import addons

        cargados = addons.todos(recargar=True)
        if not cargados:
            print(f"{WARN}Ninguno cargado.")
        for nombre, modulo in sorted(cargados.items()):
            puede, motivo = addons.estado(modulo, cfg)
            print(f"{OK if puede else WARN}{nombre}" + ("" if puede else f" - {motivo}"))
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} no pude cargarlos: {exc}")

    print("\n== Resumen ==")
    if missing:
        if plataforma.congelado():
            print(f"{FAIL} Falta parte del programa. Reinstala el paquete.")
        else:
            print(f"{FAIL} Instala lo que falta:  pip install -r requirements.txt")
    else:
        print(f"{OK}Todo lo necesario esta instalado.")

    if "--tecla" in sys.argv:
        detect_key()
    else:
        print(f"\nCorre  {yo} --tecla  para saber que manda tu keypad.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
