"""Indice de programas instalados: menu inicio + juegos de Steam.

Resuelve dos problemas de una sola pasada:

1. faster-whisper decodificando en espanol destroza los nombres propios en
   ingles ("abre rainbow six siege" -> "Haberé en Vox XC"). Pasarle los nombres
   reales como `initial_prompt` lo arregla.
2. Eve no sabe con que comando se abre cada cosa. El catalogo va al system
   prompt.
"""

import json
import os
import re
import time

from . import plataforma, store

CACHE_PATH = os.path.join(store.BASE, "apps.json")
MAX_AGE_DAYS = 7

START_MENUS = [
    os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
]

# Accesos que solo son ruido para un asistente de voz.
SKIP = re.compile(
    r"uninstall|desinstalar|readme|leame|licen|help|ayuda|manual|documentation|"
    r"website|sitio web|report a bug|changelog|release notes|command prompt|"
    r"powershell|administrative tools|herramientas administrativas|odbc|"
    r"configuration editor|debug|\.url$|"
    # Accesibilidad y utilidades del sistema: se comen lugares del vocabulario
    # sin que nadie las pida por voz.
    r"^(magnify|narrator|voiceaccess|livecaptions|on-screen keyboard|"
    r"character map|steps recorder|quick assist|windows media player legacy)$",
    re.IGNORECASE,
)

# Limite duro de whisper para initial_prompt: 224 tokens. Nombres, no frases.
VOCAB_LIMIT = 45
# El catalogo viaja en cada system prompt: los juegos entran siempre, los
# programas se recortan. 80 lineas son ~2k tokens.
CATALOG_LIMIT = 80


def _apps_macos() -> dict[str, str]:
    """Bundles .app en las carpetas de Aplicaciones."""
    found: dict[str, str] = {}
    for root in ("/Applications", "/System/Applications", os.path.expanduser("~/Applications")):
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, _files in os.walk(root):
            for d in list(dirs):
                if d.endswith(".app"):
                    found.setdefault(d[:-4], os.path.join(dirpath, d))
                    dirs.remove(d)  # no bajar dentro del bundle
    return found


def _apps_linux() -> dict[str, str]:
    """Entradas .desktop del estandar freedesktop."""
    found: dict[str, str] = {}
    roots = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/flatpak/exports/share/applications",
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            if not name.endswith(".desktop"):
                continue
            ruta = os.path.join(root, name)
            etiqueta = name[:-8]
            try:
                with open(ruta, encoding="utf-8", errors="replace") as f:
                    for linea in f:
                        if linea.startswith("Name="):
                            etiqueta = linea[5:].strip()
                            break
                        if linea.startswith("NoDisplay=true"):
                            etiqueta = ""
                            break
            except OSError:
                continue
            if etiqueta and not SKIP.search(etiqueta):
                found.setdefault(etiqueta, ruta)
    return found


def _start_menu() -> dict[str, str]:
    if plataforma.MACOS:
        return _apps_macos()
    if plataforma.LINUX:
        return _apps_linux()

    found: dict[str, str] = {}
    for root in START_MENUS:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if not name.lower().endswith(".lnk"):
                    continue
                label = name[:-4]
                if SKIP.search(label) or SKIP.search(dirpath):
                    continue
                found.setdefault(label, os.path.join(dirpath, name))
    return found


def _bases_steam() -> list[str]:
    if plataforma.MACOS:
        return [os.path.expanduser("~/Library/Application Support/Steam")]
    if plataforma.LINUX:
        return [
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.var/app/com.valvesoftware.Steam/data/Steam"),
        ]
    return [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Steam"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Steam"),
    ]


def _steam_libraries() -> list[str]:
    """Lee libraryfolders.vdf en vez de adivinar rutas."""
    roots = []
    for base in _bases_steam():
        vdf = os.path.join(base, "steamapps", "libraryfolders.vdf")
        if not os.path.exists(vdf):
            continue
        roots.append(os.path.join(base, "steamapps"))
        with open(vdf, encoding="utf-8", errors="replace") as f:
            for path in re.findall(r'"path"\s+"([^"]+)"', f.read()):
                lib = os.path.join(path.replace("\\\\", "\\"), "steamapps")
                if os.path.isdir(lib):
                    roots.append(lib)
    return list(dict.fromkeys(roots))


def _steam_games() -> dict[str, str]:
    games: dict[str, str] = {}
    for lib in _steam_libraries():
        for name in os.listdir(lib):
            if not name.startswith("appmanifest_") or not name.endswith(".acf"):
                continue
            try:
                with open(os.path.join(lib, name), encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            appid = re.search(r'"appid"\s+"(\d+)"', text)
            title = re.search(r'"name"\s+"([^"]+)"', text)
            if appid and title and "Steamworks" not in title.group(1):
                games[title.group(1)] = f"steam://rungameid/{appid.group(1)}"
    return games


def _ubisoft_games() -> dict[str, str]:
    """Ubisoft Connect no deja acceso directo por juego; esta en el registro."""
    if not plataforma.WINDOWS:
        return {}
    import winreg

    games: dict[str, str] = {}
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"
        )
    except OSError:
        return games
    with key:
        for i in range(winreg.QueryInfoKey(key)[0]):
            appid = winreg.EnumKey(key, i)
            try:
                with winreg.OpenKey(key, appid) as sub:
                    install_dir = winreg.QueryValueEx(sub, "InstallDir")[0]
            except OSError:
                continue
            name = os.path.basename(install_dir.replace("/", "\\").rstrip("\\"))
            if name:
                games[name] = f"uplay://launch/{appid}/0"
    return games


def _epic_games() -> dict[str, str]:
    if not plataforma.WINDOWS:
        return {}
    root = os.path.join(os.environ.get("ProgramData", ""), r"Epic\EpicGamesLauncher\Data\Manifests")
    games: dict[str, str] = {}
    if not os.path.isdir(root):
        return games
    for name in os.listdir(root):
        if not name.endswith(".item"):
            continue
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                m = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        ident = f"{m.get('CatalogNamespace')}:{m.get('CatalogItemId')}:{m.get('AppName')}"
        if m.get("DisplayName") and "None" not in ident:
            games[m["DisplayName"]] = (
                f"com.epicgames.launcher://apps/{ident}?action=launch&silent=true"
            )
    return games


def scan() -> dict:
    """Escanea de cero. Los juegos van primero: son los que mas rompe el STT."""
    games = {}
    for source in (_steam_games, _ubisoft_games, _epic_games):
        try:
            games.update(source())
        except Exception:  # noqa: BLE001 - una tienda rota no debe tumbar el indice
            pass
    apps = {k: v for k, v in _start_menu().items() if k not in games}
    return {"scanned_at": time.time(), "games": games, "apps": apps}


def load(refresh: bool = False) -> dict:
    if not refresh and os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - data.get("scanned_at", 0) < MAX_AGE_DAYS * 86400:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    data = scan()
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data


def vocabulary(extra: str = "") -> str:
    """initial_prompt para whisper. Corto a proposito: el limite son 224 tokens."""
    data = load()
    # Los contactos van primero: un nombre propio mal transcrito manda el mensaje
    # a la persona equivocada, un juego mal transcrito solo abre otra cosa.
    personas = []
    for c in store.load_contacts():
        personas += [p.strip() for p in (c.get("nombre", ""), *c.get("alias", "").split(",")) if p.strip()]
    names = personas + list(data["games"]) + list(data["apps"])
    names = list(dict.fromkeys(names))[:VOCAB_LIMIT]
    base = "Comandos de voz en Windows para abrir programas y mandar mensajes."
    if extra.strip():
        base += " " + extra.strip()
    return f"{base} Nombres: {', '.join(names)}."


# El menu inicio vive siempre bajo estas dos raices. Escribirlas enteras en cada
# linea del catalogo cuesta ~60 caracteres por app, y el catalogo viaja en cada
# llamada: PowerShell expande las variables de entorno solo.
_SM = r"Microsoft\Windows\Start Menu\Programs"
_ABREVIA = [
    (os.path.join(os.environ.get("APPDATA", ""), _SM), "SMU"),
    (os.path.join(os.environ.get("ProgramData", ""), _SM), "SMP"),
]


# Cuantas lineas viajan cuando el catalogo se recorta a lo que se usa.
USADOS_LIMIT = 22


def _linea(name: str, cmd: str) -> str:
    for largo, corto in _ABREVIA:
        if largo and cmd.startswith(largo):
            return f"{name} => {corto}{cmd[len(largo):]}"
    return f"{name} => {cmd}"


def buscar(consulta: str, cuantos: int = 8) -> str:
    """Busca un programa en el catalogo COMPLETO, por si no viajo en el prompt.

    Es la contraparte del catalogo recortado: lo que no entra en el prompt no
    desaparece, se pide. Un round-trip cuando hace falta sale mucho mas barato
    que ciento setenta lineas en cada llamada.
    """
    data = load()
    todos = {**data["games"], **data["apps"]}
    consulta = consulta.strip().lower()
    if not consulta:
        return "Deci que programa buscar."
    exactos = [n for n in todos if n.lower() == consulta]
    parciales = [n for n in todos if consulta in n.lower() and n not in exactos]
    hallados = (exactos + parciales)[:cuantos]
    if not hallados:
        return (f"No tengo ningun programa que se parezca a {consulta!r}. "
                "Proba con Get-StartApps.")
    return "\n".join(_linea(n, todos[n]) for n in hallados)


def catalog(usados=None) -> str:
    """Lineas 'Nombre => ruta' para el system prompt.

    Sin `Start-Process` repetido en cada linea (la regla se dice una vez) y con
    las raices abreviadas.

    Si se pasa `usados` --los programas que aparecen en el log, ordenados por
    frecuencia-- viajan esos y no el catalogo entero. El catalogo completo son
    unas 80 lineas en cada llamada al modelo, casi un tercio del system prompt,
    y en la practica se abren unos pocos. Lo que no viaja no se pierde: se pide
    con `E programa NOMBRE`.

    Sin historial se manda el catalogo completo. Recortar por falta de datos
    dejaria a una instalacion nueva sin saber abrir nada.
    """
    data = load()
    todos = {**data["games"], **data["apps"]}
    if usados:
        elegidos = [n for n in usados if n in todos][:USADOS_LIMIT]
        if elegidos:
            return "\n".join(_linea(n, todos[n]) for n in elegidos)

    lines = list(data["games"].items())
    apps_ = list(data["apps"].items())[: CATALOG_LIMIT - len(lines)]
    return "\n".join(_linea(n, c) for n, c in lines + apps_)


def catalog_header(parcial: bool = False) -> str:
    """Una sola sustitucion literal, sin que el modelo tenga que reconstruir nada.

    Con `parcial`, avisa que la lista NO es todo lo instalado. Sin ese aviso el
    modelo cree que la lista es completa y contesta "no tengo ese programa" en
    vez de buscarlo, que es la unica forma de que recortar el catalogo salga mal.
    """
    aviso = ("\nEsta lista es SOLO lo que abris seguido, no todo lo instalado. Si "
             "te piden algo\nque no esta, NO digas que no lo tenes: buscalo con "
             "`E programa NOMBRE`.\n") if parcial else ""
    if not plataforma.WINDOWS:
        verbo = "open" if plataforma.MACOS else "xdg-open"
        return f'Abrilos con: {verbo} "RUTA".{aviso}'
    return (
        'Abrilos con Start-Process "RUTA". En las rutas de abajo reemplaza el prefijo:\n'
        f'  SMU = $env:APPDATA\\{_SM}\n'
        f'  SMP = $env:ProgramData\\{_SM}' + aviso
    )


if __name__ == "__main__":
    d = load(refresh=True)
    print(f"{len(d['games'])} juegos de Steam, {len(d['apps'])} programas")
    print("\nvocabulario STT:\n ", vocabulary()[:600])
