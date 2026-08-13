"""Addon de Spotify: buscar, poner y controlar la reproduccion.

Dos decisiones que explican la forma de todo lo demas:

**Sin OAuth de usuario.** Controlar la reproduccion por la Web API exige que el
usuario autorice la app, guardar tokens y refrescarlos, y ademas Premium. En vez
de eso se maneja el Spotify de escritorio que ya tiene abierto: reproducir es
abrir una URI `spotify:` y pausar es mandarle un comando a su ventana. Lo unico
que usa la API es la busqueda, que anda con credenciales de aplicacion (client
id y secret, sin login del usuario) y es opcional.

**Los comandos van a la ventana de Spotify, no como teclas multimedia globales.**
Una tecla multimedia se la lleva el reproductor que el sistema tenga en foco, que
puede ser el navegador con un video. `WM_APPCOMMAND` a su ventana le pega solo a
Spotify.
"""

import ctypes
import json
import os
import time
import urllib.parse
import urllib.request

from .. import plataforma, store

NOMBRE = "spotify"
DESCRIPCION = "Poner musica, pausar, saltar y saber que suena."
CLAVES = [
    ("spotify_client_id", "Spotify: Client ID", False),
    ("spotify_client_secret", "Spotify: Client Secret", True),
]

# Como se ve la ventana cuando no esta sonando nada.
TITULOS_QUIETOS = {"spotify", "spotify premium", "spotify free", "advertisement"}

_WM_APPCOMMAND = 0x0319
_COMANDOS = {
    "pausa": 14,      # PLAY_PAUSE, alterna
    "play": 14,
    "siguiente": 11,
    "anterior": 12,
    "stop": 13,
}

_token = {"valor": "", "vence": 0.0}


def disponible(cfg: dict) -> tuple[bool, str]:
    if not plataforma.WINDOWS:
        return False, "por ahora solo funciona en Windows"
    return True, ""


def prompt(cfg: dict) -> str:
    con_busqueda = _hay_credenciales()
    lineas = [
        "  E addon spotify poner \"lo que sea\"    busca y lo reproduce",
        "  E addon spotify sonando                que esta sonando ahora",
        "  E addon spotify pausa | siguiente | anterior",
        "  E addon spotify volumen subir|bajar [n]",
    ]
    if con_busqueda:
        lineas.append('  E addon spotify buscar "algo" [--tipo track|album|playlist|artist]')
    else:
        lineas.append("  (buscar necesita las claves de Spotify en el panel; sin ellas")
        lineas.append("   'poner' abre la busqueda en la app y la elige el usuario)")
    return "Spotify:\n" + "\n".join(lineas)


# --- la ventana de Spotify -------------------------------------------------

def _ventana() -> int:
    """HWND de la ventana principal de Spotify. 0 si no esta abierto."""
    if not plataforma.WINDOWS:
        return 0
    u = ctypes.windll.user32
    encontrada = ctypes.c_void_p(0)
    titulo = ctypes.create_unicode_buffer(512)
    clase = ctypes.create_unicode_buffer(256)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def revisar(hwnd, _param):
        if not u.IsWindowVisible(hwnd):
            return True
        u.GetClassNameW(hwnd, clase, 256)
        # Spotify es una app CEF: su ventana principal usa esta clase, y hay
        # varias ocultas de la misma clase, por eso se exige que tenga titulo.
        if clase.value != "Chrome_WidgetWin_1":
            return True
        if u.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = ctypes.c_ulong(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _proceso(pid.value).lower() == "spotify.exe":
            encontrada.value = hwnd
            return False
        return True

    u.EnumWindows(revisar, 0)
    if encontrada.value:
        u.GetWindowTextW(encontrada.value, titulo, 512)
    return encontrada.value or 0


def _proceso(pid: int) -> str:
    """Nombre del ejecutable de un pid. Vacio si no se pudo."""
    k = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        tam = ctypes.c_ulong(1024)
        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            return os.path.basename(buf.value)
        return ""
    finally:
        k.CloseHandle(h)


def _titulo(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value.strip()


def sonando() -> str:
    """Que suena, leido del titulo de la ventana.

    Spotify pone "Artista - Tema" en el titulo mientras reproduce y solo
    "Spotify" cuando esta pausado. Es informacion que ya esta en pantalla: no
    hace falta ni API ni permisos para leerla.
    """
    hwnd = _ventana()
    if not hwnd:
        return "Spotify no esta abierto."
    titulo = _titulo(hwnd)
    if not titulo or titulo.lower() in TITULOS_QUIETOS:
        return "Spotify esta abierto pero no esta sonando nada."
    if " - " in titulo:
        artista, tema = titulo.split(" - ", 1)
        return f"Suena {tema} de {artista}."
    return f"Suena {titulo}."


def _mandar(comando: int) -> bool:
    hwnd = _ventana()
    if not hwnd:
        return False
    ctypes.windll.user32.SendMessageW(hwnd, _WM_APPCOMMAND, hwnd, comando << 16)
    return True


# --- busqueda (opcional, con credenciales de aplicacion) --------------------

def _credenciales() -> tuple[str, str]:
    return store.get_key("spotify_client_id"), store.get_key("spotify_client_secret")


def _hay_credenciales() -> bool:
    """Ojo con preguntar por la tupla directamente: ('', '') es verdadero, y con
    eso el prompt le prometia al modelo una busqueda que no existia."""
    return all(_credenciales())


def _acceso() -> str:
    """Token de aplicacion, cacheado hasta que vence."""
    if _token["valor"] and time.time() < _token["vence"]:
        return _token["valor"]
    idc, secreto = _credenciales()
    if not (idc and secreto):
        return ""
    import base64

    datos = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    pedido = urllib.request.Request(
        "https://accounts.spotify.com/api/token", data=datos,
        headers={
            "Authorization": "Basic " + base64.b64encode(
                f"{idc}:{secreto}".encode()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(pedido, timeout=15) as r:  # noqa: S310 - URL fija
        respuesta = json.load(r)
    _token["valor"] = respuesta.get("access_token", "")
    _token["vence"] = time.time() + int(respuesta.get("expires_in", 3600)) - 60
    return _token["valor"]


def buscar(consulta: str, tipo: str = "track", limite: int = 5) -> list[dict]:
    """Resultados con su URI. Lista vacia si no hay credenciales."""
    token = _acceso()
    if not token:
        return []
    url = "https://api.spotify.com/v1/search?" + urllib.parse.urlencode(
        {"q": consulta, "type": tipo, "limit": limite}
    )
    pedido = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(pedido, timeout=15) as r:  # noqa: S310
        datos = json.load(r)
    salida = []
    for item in datos.get(f"{tipo}s", {}).get("items", []):
        if not item:
            continue
        artistas = ", ".join(a["name"] for a in item.get("artists", []))
        salida.append({
            "nombre": item.get("name", ""),
            "artista": artistas,
            "uri": item.get("uri", ""),
        })
    return salida


# --- acciones ---------------------------------------------------------------

def _poner(consulta: str) -> str:
    if not consulta:
        return "Decime que poner."
    resultados = buscar(consulta, "track", 1)
    if resultados and resultados[0]["uri"]:
        r = resultados[0]
        plataforma.abrir(r["uri"])
        store.log_action("spotify", f"poner {consulta}", r["uri"])
        return f"Poniendo {r['nombre']} de {r['artista']}."
    # Sin credenciales no se puede elegir el tema: se abre la busqueda y elige
    # el usuario. Se dice claro, no se simula que quedo sonando.
    plataforma.abrir("spotify:search:" + urllib.parse.quote(consulta))
    if not _hay_credenciales():
        return (f"Abri la busqueda de {consulta!r} en Spotify. Para que lo ponga "
                "solo, cargá las claves de Spotify en el panel > Addons.")
    return f"No encontre nada para {consulta!r}; te abri la busqueda."


def _volumen(args: list[str]) -> str:
    direccion = (args[0] if args else "subir").lower()
    try:
        pasos = max(1, min(20, int(args[1]))) if len(args) > 1 else 4
    except ValueError:
        pasos = 4
    if direccion.startswith("b"):
        codigo, texto = 9, "Bajando"     # VOLUME_DOWN
    elif direccion.startswith("s"):
        codigo, texto = 10, "Subiendo"   # VOLUME_UP
    else:
        return "Decime si subir o bajar."
    # El volumen es del sistema, asi que va como tecla y no a la ventana.
    if not plataforma.WINDOWS:
        return "El volumen solo lo puedo tocar en Windows."
    u = ctypes.windll.user32
    for _ in range(pasos):
        u.keybd_event(0xAF if codigo == 10 else 0xAE, 0, 0, 0)
        u.keybd_event(0xAF if codigo == 10 else 0xAE, 0, 2, 0)
    return f"{texto} el volumen."


def ejecutar(accion: str, args: list[str], cfg: dict) -> str:
    accion = (accion or "").lower()

    if accion == "sonando":
        return sonando()

    if accion == "poner":
        return _poner(" ".join(args).strip())

    if accion in _COMANDOS:
        if not _mandar(_COMANDOS[accion]):
            return "Spotify no esta abierto."
        time.sleep(0.4)  # darle tiempo a que cambie el titulo antes de leerlo
        if accion in ("siguiente", "anterior"):
            return sonando()
        return "Listo."

    if accion == "volumen":
        return _volumen(args)

    if accion == "buscar":
        tipo = "track"
        if "--tipo" in args:
            i = args.index("--tipo")
            tipo = args[i + 1] if i + 1 < len(args) else "track"
            args = args[:i] + args[i + 2:]
        consulta = " ".join(args).strip()
        if not consulta:
            return "Decime que buscar."
        resultados = buscar(consulta, tipo)
        if not resultados:
            if not _hay_credenciales():
                return ("Buscar necesita las claves de Spotify (panel > Addons). "
                        "Sin ellas puedo abrir la busqueda con 'poner'.")
            return f"No encontre nada para {consulta!r}."
        return "\n".join(
            f"{i}. {r['nombre']} - {r['artista']}  [{r['uri']}]"
            for i, r in enumerate(resultados, 1)
        )

    return (f"No conozco la accion {accion!r}. Hay: poner, sonando, pausa, play, "
            "siguiente, anterior, stop, volumen, buscar.")
