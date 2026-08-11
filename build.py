"""Arma el ejecutable de Eve para el sistema donde se corre.

    python build.py

PyInstaller no cross-compila: el binario de cada sistema se arma en ese sistema.

Modo one-dir a proposito, no one-file: arranca al instante en vez de descomprimir
todo en un temporal cada vez, y `keyboard` empaquetado en un solo .exe dispara
alertas de antivirus mucho mas seguido.

El modelo de voz NO se empaqueta: son ~460 MB que se bajan solos al cache la
primera vez que hablas. Meterlos adentro hace el build inmanejable.
"""

import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"

# Modulos que PyInstaller no descubre solo porque se importan de forma dinamica.
OCULTOS = [
    "pystray._win32" if WINDOWS else "pystray._darwin" if MACOS else "pystray._appindicator",
    "comtypes",
    "piper",
    "onnxruntime",
    "eve.ollama_engine",
    "eve.voices",
    "eve.brain",
    "eve.cc_engine",
]
if WINDOWS:
    OCULTOS += [
        "win32com.client",
        "winrt.windows.ui.notifications",
        "winrt.windows.ui.notifications.management",
        "winrt.windows.foundation",
    ]


def _icono() -> list[str]:
    ico = os.path.join(RAIZ, "assets", "eve.ico")
    png = os.path.join(RAIZ, "assets", "eve.png")
    if not os.path.exists(ico):
        subprocess.run([sys.executable, "-m", "eve.icon"], cwd=RAIZ, check=False)
    if WINDOWS and os.path.exists(ico):
        return ["--icon", ico]
    if MACOS and os.path.exists(png):
        return ["--icon", png]
    return []


def _construir(nombre: str, entrada: str, ventana: bool) -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", nombre,
        "--distpath", os.path.join(RAIZ, "dist"),
        "--workpath", os.path.join(RAIZ, "build"),
        "--specpath", os.path.join(RAIZ, "build"),
        "--noconsole" if ventana else "--console",
    ]
    for m in OCULTOS:
        cmd += ["--hidden-import", m]
    # EVE.md se lee en cada llamada: tiene que viajar con el binario.
    sep = ";" if WINDOWS else ":"
    cmd += ["--add-data", f"{os.path.join(RAIZ, 'EVE.md')}{sep}."]
    if MACOS:
        cmd += ["--windowed"]  # produce el .app
    cmd += _icono()
    cmd.append(os.path.join(RAIZ, entrada))

    print(f"\n=== {nombre} ===")
    r = subprocess.run(cmd, cwd=RAIZ)
    if r.returncode != 0:
        sys.exit(f"PyInstaller fallo armando {nombre}")


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Falta PyInstaller. Corre:  pip install pyinstaller")
        return 1

    _construir("Eve", "main.py", ventana=True)
    _construir("Eve-config", os.path.join("eve", "gui.py"), ventana=True)
    _construir("Eve-debug", "main.py", ventana=False)

    salida = os.path.join(RAIZ, "dist")
    # El panel y el modo debug viven dentro de la carpeta de Eve para no repetir
    # las dependencias, que son casi todo el peso.
    for extra in ("Eve-config", "Eve-debug"):
        origen = os.path.join(salida, extra)
        binario = os.path.join(origen, extra + (".exe" if WINDOWS else ""))
        destino = os.path.join(salida, "Eve", os.path.basename(binario))
        if os.path.exists(binario):
            shutil.copy2(binario, destino)
            shutil.rmtree(origen, ignore_errors=True)

    print(f"\nListo: {os.path.join(salida, 'Eve')}")
    print("El modelo de voz se baja solo la primera vez que hables (~460 MB).")
    if WINDOWS:
        print(
            "\nSi el antivirus marca el .exe: es por `keyboard`, que engancha el teclado\n"
            "globalmente. Es inherente a lo que hace el programa, no un empaquetado raro."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
