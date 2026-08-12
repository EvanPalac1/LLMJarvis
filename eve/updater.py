"""Actualizacion desde las releases de GitHub.

Descarga y ejecuta un instalador, asi que el camino esta cerrado a proposito:

  - Solo el repositorio oficial, solo HTTPS. El repo no se lee de la config.
  - **Se verifica el sha256** que publica la API de GitHub para cada asset. Si no
    coincide, el archivo se borra y no se ejecuta nada.
  - Nunca instala solo: busca y avisa, y el usuario decide.

Corriendo desde el codigo no actualiza nada — ahi la actualizacion es `git pull`.
"""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request

from . import plataforma

REPO = "EvanPalac1/LLMJarvis"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGINA = f"https://github.com/{REPO}/releases/latest"

_M = platform.machine().lower()
ARCH = "arm64" if _M in ("arm64", "aarch64") else "x64"


def version_actual() -> str:
    from . import __version__

    return __version__


def _numeros(v: str) -> tuple:
    """'v1.2.10' -> (1, 2, 10). Comparar como texto diria que 1.2.9 > 1.2.10."""
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


def hay_novedad(remota: str, local: str | None = None) -> bool:
    return _numeros(remota) > _numeros(local or version_actual())


def _asset_para_este_sistema(assets: list[dict]) -> dict | None:
    """Elige el paquete que corresponde a este sistema y arquitectura."""
    if plataforma.WINDOWS:
        quiere = [f"Eve-Setup-{ARCH}.exe"]
    elif plataforma.MACOS:
        quiere = ["Eve-AppleSilicon.dmg" if ARCH == "arm64" else "Eve-Intel.dmg"]
    else:
        # Se prefiere el formato del gestor de paquetes que tenga la maquina.
        import shutil

        deb = ARCH == "arm64" and "_arm64.deb" or "_amd64.deb"
        rpm = ".aarch64.rpm" if ARCH == "arm64" else ".x86_64.rpm"
        quiere = [deb, rpm] if shutil.which("dpkg") else [rpm, deb]

    for patron in quiere:
        for a in assets:
            if a.get("name", "").endswith(patron) or a.get("name") == patron:
                return a
    return None


def buscar(timeout: int = 20) -> dict | None:
    """Devuelve datos de la ultima release si es mas nueva, o None.

    Lanza RuntimeError si no se pudo consultar; el que llama decide si molestar
    al usuario con eso o callarselo (un chequeo automatico deberia callarselo).
    """
    pedido = urllib.request.Request(
        API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"LLMJarvis/{version_actual()}"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as r:  # noqa: S310 - URL fija y https
            datos = json.load(r)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"No pude consultar las actualizaciones: {exc}") from exc

    tag = datos.get("tag_name", "")
    if not tag or not hay_novedad(tag):
        return None

    return {
        "version": tag.lstrip("v"),
        "tag": tag,
        "notas": (datos.get("body") or "").strip(),
        "url": datos.get("html_url", PAGINA),
        "asset": _asset_para_este_sistema(datos.get("assets", [])),
    }


def descargar(asset: dict, progreso=None) -> str:
    """Baja el instalador y verifica su sha256. Devuelve la ruta local."""
    url = asset["browser_download_url"]
    if not url.startswith(f"https://github.com/{REPO}/"):
        raise ValueError("La descarga no viene del repositorio oficial.")

    destino = os.path.join(tempfile.gettempdir(), asset["name"])
    total = asset.get("size", 0)
    sha = hashlib.sha256()
    bajado = 0

    pedido = urllib.request.Request(url, headers={"User-Agent": f"LLMJarvis/{version_actual()}"})
    with urllib.request.urlopen(pedido, timeout=60) as r, open(destino, "wb") as f:  # noqa: S310
        while trozo := r.read(1 << 16):
            f.write(trozo)
            sha.update(trozo)
            bajado += len(trozo)
            if progreso and total:
                progreso(bajado, total)

    esperado = (asset.get("digest") or "").removeprefix("sha256:")
    if esperado and sha.hexdigest() != esperado:
        os.remove(destino)
        raise ValueError(
            "El archivo descargado no coincide con el publicado (sha256). "
            "No se instalo nada."
        )
    return destino


def instalar(ruta: str) -> str:
    """Lanza el instalador y deja que reemplace esta version.

    En Windows el instalador tiene el mismo AppId, asi que actualiza en el lugar
    y conserva los datos de %APPDATA%. Eve tiene que salir para liberar el .exe:
    de eso se encarga quien llama, cerrando la bandeja despues de esto.
    """
    if plataforma.WINDOWS:
        # /SILENT muestra la barra pero no vuelve a preguntar lo ya elegido.
        # Sin CREATE_NO_WINDOW a proposito: el instalador tiene que verse.
        subprocess.Popen([ruta, "/SILENT", "/NORESTART"], close_fds=True)
        return "Instalando la actualizacion. Eve se va a cerrar y volver a abrir."

    # macOS: monta el dmg. Linux: lo abre con el gestor de paquetes. En ninguno
    # de los dos se puede reemplazar la app en caliente sin pedir permisos.
    plataforma.abrir(ruta)
    return f"Descargado en {ruta}. Terminá la instalacion desde ahi."


def revisar_en_segundo_plano(al_encontrar) -> None:
    """Chequeo silencioso al arrancar. Nunca molesta si algo falla."""
    import threading

    def trabajo():
        if not plataforma.congelado():
            return  # desde el codigo se actualiza con git, no con el instalador
        try:
            nueva = buscar()
        except RuntimeError:
            return  # sin internet no es un error que valga la pena mostrar
        if nueva:
            al_encontrar(nueva)

    threading.Thread(target=trabajo, daemon=True).start()


def main(argv=None) -> int:
    """`Eve.exe --actualizar` desde consola."""
    argv = argv if argv is not None else sys.argv[1:]
    print(f"Version instalada: {version_actual()}")
    try:
        nueva = buscar()
    except RuntimeError as exc:
        print(exc)
        return 1

    if not nueva:
        print("Ya tenes la ultima version.")
        return 0

    print(f"Hay una nueva: {nueva['version']}  ->  {nueva['url']}")
    if not nueva["asset"]:
        print(f"Todavia no hay paquete para {plataforma.NOMBRE} {ARCH}. Bajalo a mano de la pagina.")
        return 1
    if "--instalar" not in argv:
        print("Corre con --instalar para bajarla e instalarla.")
        return 0

    ultimo = [0]

    def barra(hecho, total):
        pct = hecho * 100 // total
        if pct >= ultimo[0] + 10:
            ultimo[0] = pct
            print(f"  {pct}%")

    print(f"Descargando {nueva['asset']['name']}...")
    try:
        ruta = descargar(nueva["asset"], barra)
    except ValueError as exc:
        print(exc)
        return 1
    print(instalar(ruta))
    return 0
