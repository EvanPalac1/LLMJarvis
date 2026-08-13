"""Addon de OBS: grabar, transmitir, cambiar de escena y silenciar el micro.

**No hace falta instalar ningun plugin en OBS.** Desde la version 28 trae
obs-websocket adentro: se prende en Herramientas > Configuracion del servidor
WebSocket. Escribir un plugin en Lua para esto seria mantener codigo dentro de
OBS a cambio de nada.

El protocolo es WebSocket con JSON. Se habla con `websocket-client`, que es una
dependencia chica, y el saludo se hace a mano: son cuatro lineas de sha256 y
base64, mucho menos que arrastrar un cliente entero.

La decision que hace que esto ande de verdad es el emparejado de nombres. El
reconocimiento de voz destroza los nombres propios ("Abrés Potisi" por "abre
Spotify"), y las escenas de OBS se llaman "Gameplay", "BRB", "Cámara 2". Pedir
la lista real a OBS y buscar el mas parecido es lo que evita que la mitad de los
pedidos fallen con un "no existe esa escena" que no le sirve a nadie.
"""

import base64
import os
import hashlib
import json
import time

from .. import store

NOMBRE = "obs"
DESCRIPCION = "Grabar, transmitir, cambiar de escena y silenciar el micro."
CLAVES = [("obs_password", "OBS: contraseña del WebSocket", True)]

PUERTO = 4455
_conexion = {"ws": None, "hasta": 0.0}


def disponible(cfg: dict) -> tuple[bool, str]:
    import importlib.util

    if importlib.util.find_spec("websocket") is None:
        return False, "falta la libreria websocket-client"
    return True, ""


def prompt(cfg: dict) -> str:
    return (
        "OBS (grabacion y streaming):\n"
        '  E addon obs estado                que esta pasando (grabando? escena?)\n'
        "  E addon obs grabar | parar-grabar | pausar-grabar\n"
        "  E addon obs transmitir | parar-transmitir\n"
        '  E addon obs escena "NOMBRE"       no hace falta el nombre exacto\n'
        "  E addon obs escenas               lista las que hay\n"
        "  E addon obs mute | unmute | mute-toggle\n"
        "  E addon obs captura               saca una foto de la pantalla de OBS\n"
        "  Si dice que OBS no responde, contalo y para: no lo rodees."
    )


# --- conexion ---------------------------------------------------------------

def _saludo(ws, password: str) -> None:
    """El handshake de obs-websocket v5: sha256(password+salt) y despues +challenge."""
    hola = json.loads(ws.recv())
    datos = hola.get("d", {})
    identificar = {"op": 1, "d": {"rpcVersion": 1}}
    auth = datos.get("authentication")
    if auth:
        if not password:
            raise RuntimeError(
                "OBS pide contraseña. Ponela en el panel > Addons "
                "(la ves en OBS: Herramientas > Configuracion del servidor WebSocket)."
            )
        secreto = base64.b64encode(
            hashlib.sha256((password + auth["salt"]).encode()).digest()
        ).decode()
        identificar["d"]["authentication"] = base64.b64encode(
            hashlib.sha256((secreto + auth["challenge"]).encode()).digest()
        ).decode()
    ws.send(json.dumps(identificar))
    respuesta = json.loads(ws.recv())
    if respuesta.get("op") != 2:
        raise RuntimeError("OBS rechazo la conexion: revisa la contraseña.")


def _config_obs() -> dict:
    """Lee la config del propio OBS para no pedirte que copies la contraseña.

    OBS guarda si el WebSocket esta activo, en que puerto y con que clave en su
    global.ini. Es tu archivo, en tu usuario: leerlo evita un paso de copiar y
    pegar que es justo donde la gente abandona. Si no esta, se usa lo del panel.
    """
    import configparser

    ruta = os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "global.ini")
    datos = {}
    if not os.path.exists(ruta):
        return datos
    try:
        parser = configparser.ConfigParser()
        parser.read(ruta, encoding="utf-8")
        if parser.has_section("OBSWebSocket"):
            seccion = parser["OBSWebSocket"]
            datos["activo"] = seccion.get("ServerEnabled", "").lower() == "true"
            datos["puerto"] = int(seccion.get("ServerPort", PUERTO) or PUERTO)
            if seccion.get("AuthRequired", "").lower() == "true":
                datos["password"] = seccion.get("ServerPassword", "")
    except Exception:  # noqa: BLE001 - si el ini cambia de forma, se sigue a mano
        pass
    return datos


def _ws(cfg: dict):
    """Conexion viva, reusada unos segundos entre comandos seguidos."""
    import websocket

    if _conexion["ws"] is not None and time.time() < _conexion["hasta"]:
        return _conexion["ws"]
    _cerrar()
    propia = _config_obs()
    if propia and propia.get("activo") is False:
        raise RuntimeError(
            "El servidor WebSocket de OBS esta apagado. Prendelo en OBS: "
            "Herramientas > Configuracion del servidor WebSocket > Activar."
        )
    puerto = propia.get("puerto", PUERTO)
    try:
        ws = websocket.create_connection(f"ws://localhost:{puerto}", timeout=4)
    except Exception as exc:  # noqa: BLE001 - cerrado y deshabilitado dan lo mismo
        raise RuntimeError(
            "OBS no responde. Fijate que este abierto y que el WebSocket este "
            "activado en Herramientas > Configuracion del servidor WebSocket."
        ) from exc
    # La del panel manda; la de OBS es el atajo para no copiarla.
    _saludo(ws, store.get_key("obs_password") or propia.get("password", ""))
    _conexion.update({"ws": ws, "hasta": time.time() + 20})
    return ws


def _cerrar() -> None:
    if _conexion["ws"] is not None:
        try:
            _conexion["ws"].close()
        except Exception:  # noqa: BLE001
            pass
    _conexion.update({"ws": None, "hasta": 0.0})


def pedir(cfg: dict, tipo: str, datos: dict | None = None) -> dict:
    """Una peticion a OBS. Devuelve responseData."""
    ws = _ws(cfg)
    ident = str(time.time())
    ws.send(json.dumps({"op": 6, "d": {
        "requestType": tipo, "requestId": ident, "requestData": datos or {},
    }}))
    # Pueden llegar eventos sueltos antes de la respuesta: se saltean.
    for _ in range(20):
        mensaje = json.loads(ws.recv())
        if mensaje.get("op") == 7 and mensaje["d"].get("requestId") == ident:
            estado = mensaje["d"].get("requestStatus", {})
            if not estado.get("result"):
                raise RuntimeError(estado.get("comment") or
                                   f"OBS rechazo {tipo}: {estado.get('code')}")
            return mensaje["d"].get("responseData") or {}
    raise RuntimeError(f"OBS no contesto a {tipo}.")


# --- nombres de escena ------------------------------------------------------

def _plano(texto: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if not unicodedata.combining(c) and (c.isalnum() or c == " ")
    ).strip()


def parecido(pedido: str, opciones: list[str]) -> str:
    """La opcion mas parecida a lo que se pidio, o '' si ninguna se acerca.

    El STT no escribe los nombres propios como estan en OBS: pide "camara dos" y
    la escena se llama "Cámara 2". Comparar exacto haria fallar la mitad de los
    pedidos, asi que se compara sin tildes y por similitud.
    """
    import difflib

    objetivo = _plano(pedido)
    if not objetivo:
        return ""
    planos = {_plano(o): o for o in opciones}
    if objetivo in planos:
        return planos[objetivo]
    # Contenida en el nombre: "camara" encuentra "Cámara 2".
    for plano, real in planos.items():
        if objetivo in plano or plano in objetivo:
            return real
    cerca = difflib.get_close_matches(objetivo, list(planos), n=1, cutoff=0.6)
    return planos[cerca[0]] if cerca else ""


# --- acciones ---------------------------------------------------------------

def _estado(cfg: dict) -> str:
    grab = pedir(cfg, "GetRecordStatus")
    trans = pedir(cfg, "GetStreamStatus")
    escena = pedir(cfg, "GetCurrentProgramScene")
    partes = [f"Escena: {escena.get('sceneName', '?')}"]
    if grab.get("outputActive"):
        partes.append("grabando" + (" (en pausa)" if grab.get("outputPaused") else
                                    f" hace {grab.get('outputTimecode', '')[:8]}"))
    else:
        partes.append("no esta grabando")
    if trans.get("outputActive"):
        partes.append(f"transmitiendo hace {trans.get('outputTimecode', '')[:8]}")
    return ". ".join(partes) + "."


def _mic(cfg: dict, accion: str) -> str:
    """Silencia la entrada de audio. Busca la de microfono entre las que haya."""
    entradas = pedir(cfg, "GetInputList").get("inputs", [])
    nombres = [e.get("inputName", "") for e in entradas]
    candidatos = [n for n in nombres
                  if any(p in _plano(n) for p in ("mic", "micro", "aux", "voz"))]
    objetivo = (candidatos or nombres or [""])[0]
    if not objetivo:
        return "OBS no tiene ninguna entrada de audio."
    if accion == "mute-toggle":
        estado = pedir(cfg, "ToggleInputMute", {"inputName": objetivo})
        silenciado = estado.get("inputMuted")
    else:
        silenciado = accion == "mute"
        pedir(cfg, "SetInputMute", {"inputName": objetivo, "inputMuted": silenciado})
    return f"{objetivo}: {'silenciado' if silenciado else 'con sonido'}."


def ejecutar(accion: str, args: list[str], cfg: dict) -> str:
    accion = (accion or "").lower()
    resto = " ".join(args).strip()
    try:
        if accion == "estado":
            return _estado(cfg)

        if accion == "escenas":
            escenas = pedir(cfg, "GetSceneList")
            nombres = [e["sceneName"] for e in escenas.get("scenes", [])]
            actual = escenas.get("currentProgramSceneName", "")
            return "Escenas: " + ", ".join(
                f"{n} (actual)" if n == actual else n for n in reversed(nombres)
            )

        if accion == "escena":
            if not resto:
                return "Decime a que escena cambiar."
            escenas = pedir(cfg, "GetSceneList")
            nombres = [e["sceneName"] for e in escenas.get("scenes", [])]
            elegida = parecido(resto, nombres)
            if not elegida:
                return (f"No hay ninguna escena parecida a {resto!r}. "
                        f"Estan: {', '.join(nombres)}")
            pedir(cfg, "SetCurrentProgramScene", {"sceneName": elegida})
            return f"Escena: {elegida}."

        if accion in ("grabar", "parar-grabar", "pausar-grabar"):
            estado = pedir(cfg, "GetRecordStatus")
            if accion == "grabar":
                if estado.get("outputActive"):
                    return "Ya estaba grabando."
                pedir(cfg, "StartRecord")
                store.log_action("obs", "grabar", "iniciada")
                return "Grabando."
            if accion == "pausar-grabar":
                if not estado.get("outputActive"):
                    return "No hay ninguna grabacion en curso."
                pedir(cfg, "ToggleRecordPause")
                return "Grabacion en pausa." if not estado.get("outputPaused") else "Sigo grabando."
            if not estado.get("outputActive"):
                return "No habia ninguna grabacion en curso."
            salida = pedir(cfg, "StopRecord")
            store.log_action("obs", "parar-grabar", salida.get("outputPath", ""))
            return f"Grabacion terminada. Quedo en {salida.get('outputPath', 'la carpeta de OBS')}."

        if accion in ("transmitir", "parar-transmitir"):
            estado = pedir(cfg, "GetStreamStatus")
            if accion == "transmitir":
                if estado.get("outputActive"):
                    return "Ya estabas transmitiendo."
                pedir(cfg, "StartStream")
                store.log_action("obs", "transmitir", "iniciada")
                return "Al aire."
            if not estado.get("outputActive"):
                return "No estabas transmitiendo."
            pedir(cfg, "StopStream")
            store.log_action("obs", "parar-transmitir", "detenida")
            return "Transmision cortada."

        if accion in ("mute", "unmute", "mute-toggle"):
            return _mic(cfg, accion)

        if accion == "captura":
            escena = pedir(cfg, "GetCurrentProgramScene").get("sceneName", "")
            import os
            import tempfile

            destino = os.path.join(tempfile.gettempdir(), "eve_obs.png")
            pedir(cfg, "SaveSourceScreenshot", {
                "sourceName": escena, "imageFormat": "png",
                "imageFilePath": destino, "imageWidth": 1280,
            })
            return f"Captura de {escena} en {destino}"

        return (f"No conozco la accion {accion!r}. Hay: estado, grabar, "
                "parar-grabar, pausar-grabar, transmitir, parar-transmitir, "
                "escena, escenas, mute, unmute, mute-toggle, captura.")
    except RuntimeError as exc:
        _cerrar()
        return str(exc)
