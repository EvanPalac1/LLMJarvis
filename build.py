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
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = os.path.dirname(os.path.abspath(__file__))
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
from eve import __version__ as VERSION

# amd64/x86_64 -> x64, aarch64/arm64 -> arm64
_M = platform.machine().lower()
ARCH = "arm64" if _M in ("arm64", "aarch64") else "x64"

OCULTOS = [
    "pystray._win32" if WINDOWS else "pystray._darwin" if MACOS else "pystray._appindicator",
    "comtypes", "piper", "onnxruntime", "onnx_asr",
    # Solo lo importa `lienzo._pintar_lottie`, adentro de la funcion y envuelto
    # en try: PyInstaller no ve un import diferido, y sin esto el modulo lottie
    # quedaria en blanco en la version instalada y andando en desarrollo, que es
    # la peor clase de falla.
    "rlottie_python",
    # El puente PIL->tkinter. Nada lo importa a nivel de modulo, asi que
    # PyInstaller no lo ve solo, y sin el no hay compositor de modulos. Que
    # viaje se comprueba corriendo el binario (`_verificar_imports`), no
    # mirando si existe un archivo.
    "PIL.ImageTk",
    "eve.brain", "eve.cc_engine", "eve.ollama_engine", "eve.voices",
    "eve.integrations", "eve.hook_gate", "eve.gui",
    "eve.modulos", "eve.lienzo", "eve.prompt", "eve.consola",
    "eve.lector", "eve.grafo", "eve.memoria", "eve.despertar", "eve.retrato",
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
if not MACOS:
    # El motor de dibujo por GPU. Nada lo importa a nivel de modulo --`gpu.py`
    # lo hace adentro de una funcion y envuelto, para que su ausencia no pueda
    # impedir que Eve arranque-- asi que PyInstaller NO los ve solo. Sin esto,
    # descomentarlos en requirements.txt daria justo la peor falla posible: el
    # motor andando en desarrollo y ausente en la version instalada, sin que
    # nada lo diga, que es el mismo modo de falla que documenta `imagenes.py`.
    #
    # En macOS no van: ahi el contexto de OpenGL no se puede crear, asi que
    # tampoco se instala la dependencia.
    OCULTOS += ["skia", "OpenGL", "OpenGL.GL",
                "eve.lienzo_skia", "eve.marco_gl"]

# Paquetes que cargan archivos de datos en runtime. PyInstaller NO los copia si
# no se le pide, y el fallo no aparece hasta que alguien usa la funcion: la v1.0.0
# salio con el reconocimiento de voz roto porque faltaba silero_vad_v6.onnx.
CON_DATOS = ["faster_whisper", "piper", "onnxruntime", "onnx_asr"]

# Paquetes que leen su PROPIA version al importarse, con importlib.metadata.
# PyInstaller no copia los .dist-info salvo que se le pida, asi que el import
# revienta con PackageNotFoundError adentro del binario y anda perfecto en
# desarrollo. `--collect-data` no alcanza: eso trae los datos del paquete, no su
# metadata. Lo encontro `_verificar_imports`, que es para lo que esta.
CON_METADATA = ["onnx-asr"]

# Archivos sin los cuales el paquete esta roto aunque el build "haya salido bien".
IMPRESCINDIBLES = [
    os.path.join("faster_whisper", "assets", "silero_vad_v6.onnx"),
    # El panel nuevo es HTML: sin estos tres archivos `--panel-web` abre una
    # ventana en blanco. Un build sin ellos "sale bien" y falla al abrirlo.
    os.path.join("web", "index.html"),
    os.path.join("web", "panel.css"),
    os.path.join("web", "tokens.css"),
    os.path.join("web", "panel.js"),
]


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


def _version_windows(nombre: str) -> list[str]:
    """Nombre y version adentro del .exe, para que el proceso se pueda mirar.

    Sin esto los tres binarios salen con TODOS los campos de version vacios, y
    el Administrador de tareas no tiene mas remedio que listarlos con el nombre
    del archivo pelado, sin descripcion ni empresa. Eve corre sin ventana y con
    el icono en el desplegable de la flechita, asi que esa fila era la unica
    forma de confirmar que estaba andando -- y no decia nada.

    Se genera aca y no como archivo fijo en el repositorio porque lleva la
    version adentro: un `.txt` suelto se olvida de actualizar y termina
    afirmando una version que no es. Escrito en la carpeta de trabajo, no en el
    repositorio: es un intermedio de compilacion.
    """
    if not WINDOWS:
        return []
    partes = [int(x) for x in VERSION.split(".")[:3]] + [0]
    coma = ", ".join(str(x) for x in partes[:4])
    descripciones = {
        "Eve": "Eve - asistente de voz",
        "Eve-config": "Eve - panel de configuracion",
        "Eve-debug": "Eve - consola de diagnostico",
    }
    texto = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({coma}), prodvers=({coma}), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040a04b0', [
      StringStruct('CompanyName', 'LLMJarvis'),
      StringStruct('FileDescription', '{descripciones.get(nombre, nombre)}'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', '{nombre}'),
      StringStruct('OriginalFilename', '{nombre}.exe'),
      StringStruct('ProductName', 'LLMJarvis'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1034, 1200])])
  ]
)
"""
    os.makedirs(os.path.join(RAIZ, "build"), exist_ok=True)
    ruta = os.path.join(RAIZ, "build", f"version_{nombre}.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ["--version-file", ruta]


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
        # El panel nuevo. No son modulos de Python, asi que el analisis
        # estatico de PyInstaller no los ve: sin esto `--panel-web` abre una
        # ventana en blanco adentro del binario y perfecta en desarrollo.
        "--add-data", f"{os.path.join(RAIZ, 'web')}{sep}web",
    ]
    for m in OCULTOS:
        cmd += ["--hidden-import", m]
    for paquete in CON_DATOS:
        cmd += ["--collect-data", paquete]
    for paquete in CON_METADATA:
        cmd += ["--copy-metadata", paquete]
    # Los addons se importan por nombre en tiempo de ejecucion, asi que el
    # analisis estatico de PyInstaller no los ve y quedarian afuera: el addon
    # existiria corriendo desde el codigo y faltaria en la version instalada.
    cmd += ["--collect-submodules", "eve.addons"]
    cmd += _version_windows(nombre)
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


# Licencias que obligan a algo cuando distribuis un binario que las incluye. No
# es una lista de "malas": es la lista de las que piden aviso, texto de licencia
# y --las de copyleft fuerte-- ofrecer el fuente del conjunto. Estan aca para que
# el build las señale en vez de que aparezcan el dia que alguien mire.
COPYLEFT = ("GPL", "LGPL", "AGPL", "MPL", "EPL", "CDDL", "CC-BY-SA")
COPYLEFT_FUERTE = ("GPL",)   # sin la L ni delante ni detras: eso lo filtra _fuerte()


def _fuerte(licencia: str) -> bool:
    """GPL o AGPL a secas. LGPL no: con enlace dinamico solo pide aviso.

    Se miran las dos escrituras porque las dos aparecen de verdad en los
    metadatos: la sigla ("GPL-3.0-or-later", de `License-Expression`) y el
    nombre entero ("GNU General Public License", de los classifiers). Con solo
    la sigla, un paquete que se declara con el nombre largo pasaba de largo, y
    ese es justo el error que este archivo existe para no cometer.
    """
    l = licencia.upper().replace("-", "").replace(" ", "")
    sigla = "AGPL" in l or "GPL" in l
    escrito = "GENERALPUBLICLICENSE" in l
    if not (sigla or escrito):
        return False
    return "LGPL" not in l and "LESSERGENERALPUBLICLICENSE" not in l


def _licencia_de(dist) -> str:
    """La licencia de un paquete, mirando los tres lugares donde puede estar."""
    md = dist.metadata
    for clave in ("License-Expression", "License"):
        valor = (md.get(clave) or "").strip()
        # Algunos paquetes meten el TEXTO entero de la licencia en el campo.
        if valor and len(valor) < 120:
            return valor.splitlines()[0].strip()
        if valor:
            return valor.splitlines()[0].strip()[:80]
    for c in md.get_all("Classifier") or []:
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return "sin declarar"


def _cierre(nombres) -> dict:
    """Los paquetes pedidos mas todo lo que ellos arrastran.

    Se calcula desde requirements.txt y no desde lo que PyInstaller metio de
    verdad, y es a proposito: leer el .toc de PyInstaller seria mas exacto pero
    tambien mas fragil, y en un aviso de licencias sobrar es inofensivo mientras
    que faltar es el problema entero.
    """
    import importlib.metadata as meta

    vistos, pendientes = {}, list(nombres)
    while pendientes:
        nombre = pendientes.pop().split("[")[0].strip()
        clave = nombre.lower().replace("_", "-")
        if not clave or clave in vistos:
            continue
        try:
            dist = meta.distribution(nombre)
        except meta.PackageNotFoundError:
            continue
        vistos[clave] = dist
        for req in dist.requires or []:
            # Las dependencias de extras no viajan salvo que se pidan.
            if "extra ==" in req:
                continue
            pendientes.append(re.split(r"[<>=!;\[ ]", req, 1)[0])
    return vistos


def _terceros(carpeta: str) -> None:
    """Escribe `licencias/TERCEROS.md` adentro del paquete, con los textos.

    Va adentro de `dist/Eve` a proposito: los cuatro empaquetadores copian esa
    carpeta entera --el .iss con dist/Eve/*, y el deb, el rpm y el dmg desde
    `$RAIZ/dist/Eve`-- asi que el aviso viaja en los cuatro instaladores sin
    tocar ningun guion.

    Se genera en cada build y no se escribe a mano. Un aviso de licencias hecho
    a mano se pudre en la primera dependencia nueva, y una lista de licencias
    vieja es peor que no tenerla porque parece que alguien la reviso.
    """
    reqs = []
    with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as f:
        for linea in f:
            linea = linea.split("#")[0].strip()
            if linea:
                reqs.append(re.split(r"[<>=!;\[ ]", linea, 1)[0])

    paquetes = _cierre(reqs)
    destino = os.path.join(carpeta, "licencias")
    os.makedirs(destino, exist_ok=True)

    filas, avisados, fuertes = [], [], []
    for clave in sorted(paquetes):
        dist = paquetes[clave]
        lic = _licencia_de(dist)
        nombre = dist.metadata["Name"]
        url = (dist.metadata.get("Home-page")
               or next((u.split(",", 1)[-1].strip()
                        for u in (dist.metadata.get_all("Project-URL") or [])), ""))
        archivo = 0
        if any(m in lic.upper() for m in COPYLEFT):
            archivo = _copiar_licencia(dist, nombre, destino)
            if archivo:
                avisados.append(nombre)
            if _fuerte(lic):
                fuertes.append((nombre, lic, url))
        filas.append((nombre, dist.version, lic, url, archivo))

    with open(os.path.join(destino, "TERCEROS.md"), "w", encoding="utf-8") as f:
        f.write("# Librerias de terceros\n\n")
        f.write("Eve se distribuye bajo licencia MIT (ver `LICENSE`). Este archivo lo\n"
                "genera `build.py` en cada compilacion leyendo los metadatos de los\n"
                "paquetes instalados, asi que no puede quedar viejo.\n\n")
        if fuertes:
            f.write("## Copyleft fuerte\n\n"
                    "Estos paquetes viajan adentro del programa y su licencia alcanza al\n"
                    "conjunto distribuido, no solo a ellos:\n\n")
            for nombre, lic, url in fuertes:
                f.write(f"- **{nombre}** ({lic}) — fuente en {url or 'su repositorio'}\n")
            f.write("\nEl texto completo de cada una esta en esta misma carpeta.\n\n")
        f.write("## Todas\n\n| paquete | version | licencia | fuente |\n")
        f.write("|---|---|---|---|\n")
        for nombre, ver, lic, url, archivo in filas:
            marca = " *" if archivo else ""
            f.write(f"| {nombre}{marca} | {ver} | {lic} | {url or '—'} |\n")
        f.write("\n`*` = el texto de la licencia viaja en esta carpeta.\n")

    print(f"    licencias: {len(filas)} paquetes, {len(avisados)} con texto adjunto")
    if fuertes:
        print("    ATENCION, copyleft fuerte adentro del paquete: "
              + ", ".join(f"{n} ({l})" for n, l, _ in fuertes))


def _copiar_licencia(dist, nombre: str, destino: str) -> int:
    """Copia TODOS los textos de licencia del paquete. Devuelve cuantos.

    Todos y no el primero: la LGPLv3 se distribuye como dos archivos --el texto
    de la GPLv3 mas el suplemento que la ablanda-- y quedarse con uno solo deja
    el aviso a medias. pystray es exactamente ese caso.
    """
    copiados = 0
    vistos = set()
    for archivo in dist.files or []:
        base = os.path.basename(str(archivo))
        if not base.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
            continue
        if base in vistos:      # el mismo archivo puede estar en el dist-info y afuera
            continue
        try:
            origen = dist.locate_file(archivo)
            texto = Path(str(origen)).read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        if len(texto) < 200:      # un stub que solo dice "ver el repo" no sirve
            continue
        vistos.add(base)
        with open(os.path.join(destino, f"{nombre}-{base}"), "w", encoding="utf-8") as f:
            f.write(texto)
        copiados += 1
    return copiados


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
    _terceros(os.path.join(destino, "Contents", "Resources") if MACOS else destino)

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
