"""Revisa que falta para que Eve funcione en esta PC.

    python diagnostico.py           -> reporte
    python diagnostico.py --tecla   -> ademas detecta que manda tu keypad
"""

import shutil
import subprocess
import sys

from eve import store

OK, FAIL, WARN = "[ok]  ", "[FALTA]", "[!]   "

DEPS = [
    ("anthropic", "motor 'api' (no hace falta con motor 'claude-code')"),
    ("keyboard", "detectar el boton del keypad"),
    ("sounddevice", "grabar del microfono"),
    ("numpy", "manejar el audio"),
    ("faster_whisper", "transcribir voz a texto"),
    ("pyttsx3", "leer las respuestas en voz alta"),
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


def main() -> int:
    cfg = store.load_config()
    print(f"Eve = '{cfg['assistant_name']}' | hotkey '{cfg['hotkey']}'")
    missing = check_deps()
    check_engine(cfg)
    check_mic()
    check_workdirs(cfg)

    print("\n== Resumen ==")
    if missing:
        print(f"{FAIL} Instala lo que falta:  pip install -r requirements.txt")
    else:
        print(f"{OK}Todo lo necesario esta instalado.")

    if "--tecla" in sys.argv:
        detect_key()
    else:
        print("\nCorre  python diagnostico.py --tecla  para saber que manda tu keypad.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
