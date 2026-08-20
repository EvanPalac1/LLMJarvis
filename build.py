"""Arma la aplicacion para el sistema donde se corre.

    python build.py            solo los binarios
    python build.py --paquete  ademas el instalador del sistema

PyInstaller no cross-compila: cada sistema y arquitectura se arma en su propia
maquina. Para los 5 objetivos esta .github/workflows/release.yml.

One-dir y no one-file: arranca al instante en vez de descomprimir todo en un
temporal cada vez, y `keyboard` en un solo .exe dispara alertas de antivirus
mucho mas seguido.

El modelo de voz NO se empaqueta: son ~460 MB que se bajan al cache del usuario
la primera vez. El instalador ofrece bajarlos durante la instalacion.
"""

import os
import platform
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
from eve import __version__ as VERSION

# amd64/x86_64 -> x64, aarch64/arm64 -> arm64
_M = platform.machine().lower()
ARCH = "arm64" if _M in ("arm64", "aarch64") else "x64"

OCULTOS = [
    "pystray._win32" if WINDOWS else "pystray._darwin" if MACOS else "pystray._appindicator",
    "comtypes", "piper", "onnxruntime",
    # El puente PIL->tkinter. Nada lo importa a nivel de modulo, asi que
    # PyInstaller no lo ve solo, y sin el no hay compositor de modulos. Que
    # viaje se comprueba corriendo el binario (`_verificar_imports`), no
    # mirando si existe un archivo.
    "PIL.ImageTk",
    "eve.brain", "eve.cc_engine", "eve.ollama_engine", "eve.voices",
    "eve.integrations", "eve.hook_gate", "eve.gui",
    "eve.modulos", "eve.lienzo", "eve.prompt", "eve.consola",
    "eve.lector", "eve.grafo", "eve.memoria", "eve.despertar",
]
if WINDOWS:
    OCULTOS += [
        "win32com.client", "win32clipboard", "keyboard",
        "winrt.windows.ui.notifications",
        "winrt.windows.ui.notifications.management",
        "winrt.windows.foundation",
    ]
else:
    OCULTOS += ["pynput"]

# Paquetes que cargan archivos de datos en runtime. PyInstaller NO los copia si
# no se le pide, y el fallo no aparece hasta que alguien usa la funcion: la v1.0.0
# salio con el reconocimiento de voz roto porque faltaba silero_vad_v6.onnx.
CON_DATOS = ["faster_whisper", "piper", "onnxruntime"]

# Archivos sin los cuales el paquete esta roto aunque el build "haya salido bien".
IMPRESCINDIBLES = [os.path.join("faster_whisper", "assets", "silero_vad_v6.onnx")]


def _icono() -> list[str]:
    """Los iconos se generan en la carpeta de datos; se copian al build."""
    subprocess.run([sys.executable, "-m", "eve.icon"], cwd=RAIZ, check=False,
                   capture_output=True)
    from eve import icon as icon_mod

    if WINDOWS and os.path.exists(icon_mod.ICO_PATH):
        return ["--icon", icon_mod.ICO_PATH]
    if MACOS and os.path.exists(icon_mod.PNG_PATH):
        return ["--icon", icon_mod.PNG_PATH]
    return []


def _construir(nombre: str, ventana: bool, extra: list[str]) -> None:
    sep = ";" if WINDOWS else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir",
        "--name", nombre,
        "--distpath", os.path.join(RAIZ, "dist"),
        "--workpath", os.path.join(RAIZ, "build"),
        "--specpath", os.path.join(RAIZ, "build"),
        "--noconsole" if ventana else "--console",
        # EVE.md se lee en cada llamada al modelo: tiene que viajar con el binario.
        "--add-data", f"{os.path.join(RAIZ, 'EVE.md')}{sep}.",
        # Los perfiles de ejemplo. Sin esto existen en el repositorio y no en la
        # version instalada, que es justo la que los necesita: quien instala no
        # clona el repo para conseguir un tema.
        "--add-data", f"{os.path.join(RAIZ, 'perfiles')}{sep}perfiles",
    ]
    for m in OCULTOS:
        cmd += ["--hidden-import", m]
    for paquete in CON_DATOS:
        cmd += ["--collect-data", paquete]
    # Los addons se importan por nombre en tiempo de ejecucion, asi que el
    # analisis estatico de PyInstaller no los ve y quedarian afuera: el addon
    # existiria corriendo desde el codigo y faltaria en la version instalada.
    cmd += ["--collect-submodules", "eve.addons"]
    cmd += _icono() + extra + [os.path.join(RAIZ, "main.py")]

    print(f"\n=== {nombre} ===")
    if subprocess.run(cmd, cwd=RAIZ).returncode != 0:
        sys.exit(f"PyInstaller fallo armando {nombre}")


def _fusionar(principal: str, extras: list[str]) -> None:
    """Deja los binarios secundarios dentro de la carpeta del principal.

    Sin esto cada uno arrastra su copia completa de Python y las librerias, que
    son casi todo el peso.
    """
    dist = os.path.join(RAIZ, "dist")
    for extra in extras:
        origen = os.path.join(dist, extra)
        binario = os.path.join(origen, extra + (".exe" if WINDOWS else ""))
        if os.path.exists(binario):
            shutil.copy2(binario, os.path.join(dist, principal, os.path.basename(binario)))
        shutil.rmtree(origen, ignore_errors=True)


def _app_macos() -> None:
    """Info.plist: sin esto macOS niega el microfono en silencio."""
    plist = os.path.join(RAIZ, "dist", "Eve.app", "Contents", "Info.plist")
    if not os.path.exists(plist):
        return
    plantilla = os.path.join(RAIZ, "packaging", "macos", "Info.plist")
    if os.path.exists(plantilla):
        with open(plantilla, encoding="utf-8") as f:
            contenido = f.read().replace("@VERSION@", VERSION)
        with open(plist, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("    Info.plist aplicado (LSUIElement, permiso de microfono)")


def _verificar(carpeta: str) -> None:
    """Aborta si falta algo que rompe el programa en runtime.

    Un build "exitoso" al que le faltan datos de paquetes no falla hasta que el
    usuario intenta hablar. Mejor romper aca que publicar una release rota.
    """
    faltan = []
    for relativo in IMPRESCINDIBLES:
        if not any(
            os.path.exists(os.path.join(carpeta, base, relativo))
            for base in ("_internal", ".", os.path.join("Contents", "Resources"),
                         os.path.join("Contents", "Frameworks"))
        ):
            faltan.append(relativo)
    if faltan:
        sys.exit(
            "Build incompleto, falta:\n  " + "\n  ".join(faltan) +
            "\n\nRevisa CON_DATOS en build.py: son datos de paquetes que PyInstaller\n"
            "no copia solo y sin los cuales el programa falla recien al usarse."
        )
    print("    verificado: los datos imprescindibles estan en el paquete")


def _paquete() -> None:
    """Instalador nativo del sistema."""
    pkg = os.path.join(RAIZ, "packaging")
    if WINDOWS:
        # winget lo instala por usuario en LOCALAPPDATA, no en Program Files.
        candidatos = [
            os.path.join(base, "Inno Setup 6", "ISCC.exe")
            for base in (
                os.environ.get("LOCALAPPDATA", "") and
                os.path.join(os.environ["LOCALAPPDATA"], "Programs"),
                os.environ.get("ProgramFiles(x86)", ""),
                os.environ.get("ProgramFiles", ""),
            )
            if base
        ]
        iscc = next((p for p in candidatos if os.path.exists(p)), shutil.which("iscc"))
        if not iscc:
            print("\nFalta Inno Setup. Instalalo con:  winget install JRSoftware.InnoSetup")
            return
        # El .iss espera el icono en dist/: se genera en la carpeta de datos.
        from eve import icon as icon_mod

        if os.path.exists(icon_mod.ICO_PATH):
            shutil.copy2(icon_mod.ICO_PATH, os.path.join(RAIZ, "dist", "eve.ico"))
        subprocess.run(
            [iscc, f"/DMiVersion={VERSION}", f"/DMiArch={ARCH}",
             os.path.join(pkg, "windows", "eve.iss")],
            cwd=RAIZ, check=True,
        )
    elif MACOS:
        subprocess.run(["bash", os.path.join(pkg, "macos", "dmg.sh"), VERSION, ARCH],
                       cwd=RAIZ, check=True)
    else:
        # check=True a proposito: con check=False un script roto dejaba el job en
        # verde sin ningun paquete, que es como se publico una release vacia.
        # Lo unico que se saltea en silencio es la herramienta ausente.
        for guion, herramienta in (("build_deb.sh", "dpkg-deb"), ("build_rpm.sh", "rpmbuild")):
            if not shutil.which(herramienta):
                print(f"    salteado {guion}: falta {herramienta}")
                continue
            subprocess.run([
                "bash", os.path.join(pkg, "linux", guion), VERSION, ARCH
            ], cwd=RAIZ, check=True)


def _verificar_imports(carpeta: str) -> None:
    """Corre el binario recien armado y le pide que importe lo critico.

    `_verificar` de arriba mira si un ARCHIVO viaja. Esto es lo otro: un
    submodulo que PyInstaller no vio no deja ningun archivo faltante a la vista,
    y el programa recien falla cuando el usuario usa la funcion. Es la falla que
    `eve/imagenes.py` describe y por la que se evito `ImageTk` a mano.
    """
    if MACOS:
        candidatos = [os.path.join(carpeta, "Contents", "MacOS", "Eve")]
    else:
        sufijo = ".exe" if WINDOWS else ""
        # El de consola primero: es el que tiene stdout de verdad en Windows.
        candidatos = [os.path.join(carpeta, "Eve-debug" + sufijo),
                      os.path.join(carpeta, "Eve" + sufijo)]
    binario = next((c for c in candidatos if os.path.exists(c)), "")
    if not binario:
        sys.exit("No encontre el ejecutable para probar los imports: " + str(candidatos))

    print("    probando los imports criticos adentro del paquete...")
    r = subprocess.run([binario, "--probar-imports"], capture_output=True, text=True, timeout=300)
    for linea in (r.stdout or "").splitlines():
        print("    " + linea)
    if r.returncode != 0:
        print((r.stderr or "")[:2000])
        sys.exit(
            "Build incompleto: el paquete no puede importar algo critico.\n"
            "Revisa OCULTOS en build.py: son modulos que PyInstaller no descubre\n"
            "solo porque nadie los importa a nivel de modulo."
        )


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Falta PyInstaller. Corre:  pip install pyinstaller")
        return 1

    shutil.rmtree(os.path.join(RAIZ, "dist"), ignore_errors=True)

    if MACOS:
        _construir("Eve", ventana=True, extra=["--windowed"])
        _app_macos()
    else:
        _construir("Eve", ventana=True, extra=[])
        # El panel es un binario propio: la bandeja lo lanza como proceso aparte
        # para no mezclar el mainloop de tkinter con el de pystray.
        _construir("Eve-config", ventana=True, extra=[])
        _construir("Eve-debug", ventana=False, extra=[])
        _fusionar("Eve", ["Eve-config", "Eve-debug"])

    destino = os.path.join(RAIZ, "dist", "Eve.app" if MACOS else "Eve")
    _verificar(destino)
    _verificar_imports(destino)

    salida = os.path.join(RAIZ, "dist")
    print(f"\nListo: {salida}  ({sys.platform} {ARCH})")

    if "--paquete" in sys.argv:
        _paquete()

    print("El modelo de voz se baja la primera vez que hables (~460 MB).")
    if WINDOWS:
        print(
            "Si el antivirus marca el binario: es por `keyboard`, que engancha el teclado\n"
            "globalmente. Es inherente a lo que hace el programa."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
