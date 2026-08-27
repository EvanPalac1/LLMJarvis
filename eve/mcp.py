"""Servidores MCP: los que ya tenes configurados, dentro de Eve.

**Los dos modos son del usuario, no una decision del programa**, porque no son
la misma cosa con distinto grado sino dos tratos distintos:

  `prompt`    Eve NO se conecta a nada. Lo que viaja al modelo es la lista de
              herramientas que declaraste, como texto, para que sepa que
              existen y te pida que las uses vos. Cero superficie nueva: no se
              lanza ningun proceso.
  `cliente`   Eve levanta el servidor, le pregunta que herramientas tiene y se
              las ofrece al modelo. Es lo que la gente espera de "soporte MCP",
              y es tambien correr codigo de terceros en tu maquina.

El default es `apagado`. Encender esto es una decision, no un descubrimiento.

**Toda herramienta ajena pasa por el mismo freno que los addons**: se pregunta
antes de correr y queda anotada en Acciones. Un servidor MCP puede exponer
`delete_file` o `run_shell` y llamarse `utils`; el nombre no dice nada, asi que
la confirmacion es por defecto y sacarla es por herramienta y a mano. Ese es el
agujero que `addons` tardo tres versiones en cerrar y no se vuelve a abrir aca.

El transporte es stdio con JSON-RPC 2.0, un mensaje por linea, que es lo que
define el protocolo. Sin dependencias: son treinta lineas de `subprocess` y
`json`, y una libreria mas seria un objetivo mas donde fallar en los cinco
sistemas.
"""

import json
import os
import shutil
import subprocess
import threading
import time

from . import plataforma, store

ARCHIVO = os.path.join(store.BASE, "mcp.json")

MODOS = ("apagado", "prompt", "cliente")

# La version del protocolo que se anuncia en `initialize`. Fija y no la ultima
# que exista: un servidor que no la conozca contesta con la suya y se sigue
# igual, pero pedir una que todavia no salio es pedir que fallen todos.
PROTOCOLO = "2024-11-05"

# Cuanto se espera a que el servidor conteste. Un MCP que arranca bajando un
# paquete con `uvx` tarda; uno que se colgo, no contesta nunca.
ESPERA = 25.0

# De donde se pueden traer servidores ya configurados. (etiqueta, ruta).
def fuentes() -> list:
    """Los archivos de otros programas donde puede haber servidores MCP.

    Se leen, no se tocan. Traer lo que ya configuraste es la diferencia entre
    "soporta MCP" y "sirve": nadie quiere volver a escribir a mano el comando y
    los argumentos de cada servidor que ya anda en otro lado.
    """
    casa = os.path.expanduser("~")
    salida = [
        ("Claude Code", os.path.join(casa, ".claude.json")),
        ("Claude Desktop", os.path.join(
            os.environ.get("APPDATA", casa), "Claude", "claude_desktop_config.json")),
        ("Cursor", os.path.join(casa, ".cursor", "mcp.json")),
        ("LM Studio", os.path.join(casa, ".lmstudio", "mcp.json")),
        ("VS Code", os.path.join(
            os.environ.get("APPDATA", casa), "Code", "User", "mcp.json")),
    ]
    if plataforma.MACOS:
        salida[1] = ("Claude Desktop", os.path.join(
            casa, "Library", "Application Support", "Claude",
            "claude_desktop_config.json"))
    return [(nombre, ruta) for nombre, ruta in salida if os.path.isfile(ruta)]


def _servidores_de(datos) -> dict:
    """Los `mcpServers` de un archivo, mire donde mire.

    Claude Desktop y Cursor los ponen en la raiz; Claude Code los guarda POR
    PROYECTO, dentro de `projects.<ruta>.mcpServers`. Buscar solo en la raiz
    daba cero servidores en la maquina donde este modulo se escribio, que es
    justo el caso que tenia que funcionar.
    """
    salida = {}
    if not isinstance(datos, dict):
        return salida
    for nombre, cfg in (datos.get("mcpServers") or {}).items():
        if isinstance(cfg, dict):
            salida[str(nombre)] = cfg
    for proyecto in (datos.get("projects") or {}).values():
        if isinstance(proyecto, dict):
            for nombre, cfg in (proyecto.get("mcpServers") or {}).items():
                if isinstance(cfg, dict):
                    salida.setdefault(str(nombre), cfg)
    return salida


def descubrir() -> dict:
    """{nombre: {comando, args, env, de}} de todo lo que haya configurado.

    Si el mismo nombre esta en dos programas gana el primero y se dice de donde
    salio: son el mismo servidor casi siempre, y ofrecerlo dos veces obligaria
    a elegir entre dos cosas identicas.
    """
    salida = {}
    for etiqueta, ruta in fuentes():
        try:
            with open(ruta, encoding="utf-8-sig") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            continue   # un archivo de otro programa roto no es problema nuestro
        for nombre, cfg in _servidores_de(datos).items():
            if nombre in salida:
                continue
            comando = str(cfg.get("command") or "").strip()
            if not comando:
                continue   # los servidores remotos (url) no se soportan todavia
            salida[nombre] = {
                "comando": comando,
                "args": [str(a) for a in (cfg.get("args") or [])],
                "env": {str(k): str(v) for k, v in (cfg.get("env") or {}).items()},
                "de": etiqueta,
            }
    return salida


# --- lo nuestro ------------------------------------------------------------

def leer() -> dict:
    datos = store._leer_json(ARCHIVO, {})
    if not isinstance(datos, dict):
        return {"servidores": {}}
    datos.setdefault("servidores", {})
    return datos


def escribir(datos: dict) -> None:
    store._escribir_json(ARCHIVO, datos)


def servidores() -> dict:
    return leer().get("servidores", {})


def agregar(nombre: str, comando: str, args=None, env=None, de: str = "") -> None:
    """Suma un servidor, APAGADO.

    Apagado y no encendido: importar es traer la configuracion, no autorizar
    que se ejecute. Que importar de otro programa encendiera doce servidores de
    golpe seria exactamente la sorpresa que este modulo tiene que evitar.
    """
    nombre = str(nombre).strip()
    if not nombre or not str(comando).strip():
        raise ValueError("Un servidor MCP necesita nombre y comando.")
    datos = leer()
    viejo = datos["servidores"].get(nombre, {})
    datos["servidores"][nombre] = {
        "comando": str(comando).strip(),
        "args": [str(a) for a in (args or [])],
        "env": {str(k): str(v) for k, v in (env or {}).items()},
        "de": de or viejo.get("de", ""),
        # Lo que ya estaba elegido se respeta: reimportar no puede apagar algo
        # que el usuario habia encendido.
        "activo": bool(viejo.get("activo", False)),
        "herramientas": dict(viejo.get("herramientas", {})),
        "confiadas": list(viejo.get("confiadas", [])),
    }
    escribir(datos)


def quitar(nombre: str) -> None:
    datos = leer()
    if datos["servidores"].pop(nombre, None) is not None:
        escribir(datos)


def activar(nombre: str, si: bool) -> None:
    datos = leer()
    if nombre in datos["servidores"]:
        datos["servidores"][nombre]["activo"] = bool(si)
        escribir(datos)


def activar_herramienta(servidor: str, herramienta: str, si: bool) -> None:
    """Encender y apagar de a una. Una que no figure se considera ENCENDIDA.

    Encendida por defecto porque la lista se descubre en vivo: un servidor que
    agrega una herramienta la agrega despues de que vos elegiste, y guardar
    "apagadas las que no conozco" dejaria de funcionar cada actualizacion del
    servidor sin decir por que. Lo que NO es por defecto es correrla sin
    preguntar: eso es `confiadas`, y esa lista arranca vacia.
    """
    datos = leer()
    srv = datos["servidores"].get(servidor)
    if srv is None:
        return
    srv.setdefault("herramientas", {})[herramienta] = bool(si)
    escribir(datos)


def herramienta_activa(srv: dict, herramienta: str) -> bool:
    return bool(srv.get("herramientas", {}).get(herramienta, True))


def confiar(servidor: str, herramienta: str, si: bool) -> None:
    """Correr esa herramienta sin preguntar cada vez. Se elige a mano, una por una."""
    datos = leer()
    srv = datos["servidores"].get(servidor)
    if srv is None:
        return
    confiadas = [h for h in srv.get("confiadas", []) if h != herramienta]
    if si:
        confiadas.append(herramienta)
    srv["confiadas"] = sorted(confiadas)
    escribir(datos)


def modo(cfg: dict) -> str:
    valor = str(cfg.get("mcp_modo", "apagado")).strip().lower()
    return valor if valor in MODOS else "apagado"


def activos() -> dict:
    return {n: s for n, s in servidores().items() if s.get("activo")}


# --- el cliente ------------------------------------------------------------

class Cliente:
    """Un servidor MCP hablando por stdio. Se usa con `with`.

    Un proceso por conversacion y no uno vivo todo el tiempo: un servidor MCP
    es codigo ajeno, y tenerlo corriendo en tu maquina desde que abris Eve
    hasta que la cerras es una decision mucho mas grande que la de usarlo. Se
    levanta cuando hace falta y se baja al terminar.
    """

    def __init__(self, nombre: str, srv: dict):
        self.nombre = nombre
        self.srv = srv
        self.proc = None
        self._id = 0
        self._lock = threading.Lock()

    # -- ciclo de vida --
    def __enter__(self):
        self.abrir()
        return self

    def __exit__(self, *_e):
        self.cerrar()
        return False

    def abrir(self) -> None:
        comando = self.srv.get("comando", "")
        ruta = shutil.which(comando) or comando
        entorno = dict(os.environ)
        entorno.update(self.srv.get("env", {}))
        # `expandvars` porque los archivos de otros programas traen cosas como
        # `%LOCALAPPDATA%\Roblox\mcp.bat`, que la shell de ellos expande y
        # `subprocess` sin shell no. Sin esto el servidor no arranca y el error
        # es "el sistema no encuentra la ruta", que no dice nada.
        args = [os.path.expandvars(a) for a in self.srv.get("args", [])]
        self.proc = subprocess.Popen(
            [os.path.expandvars(ruta)] + args,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", bufsize=1, env=entorno,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._pedir("initialize", {
            "protocolVersion": PROTOCOLO,
            "capabilities": {},
            "clientInfo": {"name": "Eve", "version": _version()},
        })
        self._avisar("notifications/initialized")

    def cerrar(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None

    # -- protocolo --
    def _escribir(self, mensaje: dict) -> None:
        self.proc.stdin.write(json.dumps(mensaje) + "\n")
        self.proc.stdin.flush()

    def _avisar(self, metodo: str, params=None) -> None:
        """Una notificacion: sin `id`, y no se espera respuesta."""
        self._escribir({"jsonrpc": "2.0", "method": metodo,
                        "params": params or {}})

    def _pedir(self, metodo: str, params=None) -> dict:
        """Un pedido con respuesta. Tira RuntimeError si el servidor falla."""
        with self._lock:
            self._id += 1
            ident = self._id
            self._escribir({"jsonrpc": "2.0", "id": ident, "method": metodo,
                            "params": params or {}})
            limite = time.monotonic() + ESPERA
            while time.monotonic() < limite:
                linea = self.proc.stdout.readline()
                if not linea:
                    raise RuntimeError(
                        f"El servidor {self.nombre!r} se cerro sin contestar.")
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    msg = json.loads(linea)
                except ValueError:
                    # Hay servidores que escriben logs por stdout. No es
                    # nuestro mensaje: se saltea en vez de tirar todo abajo.
                    continue
                if msg.get("id") != ident:
                    continue   # una notificacion del servidor, o otra respuesta
                if "error" in msg:
                    detalle = (msg["error"] or {}).get("message", "")
                    raise RuntimeError(f"{self.nombre}: {detalle}")
                return msg.get("result") or {}
        raise RuntimeError(f"El servidor {self.nombre!r} no contesto en {ESPERA:.0f}s.")

    # -- lo que se le pide --
    def herramientas(self) -> list:
        """[{nombre, descripcion, esquema}] de lo que el servidor ofrece."""
        salida = []
        for h in (self._pedir("tools/list").get("tools") or []):
            if not isinstance(h, dict) or not h.get("name"):
                continue
            salida.append({
                "nombre": str(h["name"]),
                "descripcion": str(h.get("description") or "")[:300],
                "esquema": h.get("inputSchema") or {},
            })
        return sorted(salida, key=lambda x: x["nombre"])

    def llamar(self, herramienta: str, argumentos: dict) -> str:
        r = self._pedir("tools/call", {"name": herramienta,
                                       "arguments": argumentos or {}})
        return _texto_de(r)


def _version() -> str:
    from . import __version__

    return __version__


def _texto_de(resultado: dict) -> str:
    """El texto de una respuesta MCP, que viene como lista de bloques."""
    partes = []
    for bloque in (resultado.get("content") or []):
        if isinstance(bloque, dict) and bloque.get("type") == "text":
            partes.append(str(bloque.get("text") or ""))
    texto = "\n".join(p for p in partes if p).strip()
    if resultado.get("isError"):
        return f"ERROR: {texto or 'el servidor no dijo por que'}"
    return texto or "(sin salida)"


# --- lo que ve el modelo ---------------------------------------------------

def catalogo(cfg: dict, refrescar: bool = False) -> dict:
    """{servidor: [herramientas]} de los servidores encendidos.

    En modo `prompt` sale de lo guardado --lo que se vio la ultima vez-- y no
    se conecta a nada, que es el punto de ese modo. En modo `cliente` se puede
    pedir en vivo con `refrescar`.
    """
    salida = {}
    for nombre, srv in sorted(activos().items()):
        guardadas = srv.get("vistas") or []
        if refrescar and modo(cfg) == "cliente":
            try:
                with Cliente(nombre, srv) as c:
                    guardadas = c.herramientas()
                datos = leer()
                if nombre in datos["servidores"]:
                    datos["servidores"][nombre]["vistas"] = guardadas
                    escribir(datos)
            except (OSError, RuntimeError, ValueError):
                pass   # el que no arranca no puede dejar sin catalogo a los demas
        salida[nombre] = [h for h in guardadas
                          if herramienta_activa(srv, h.get("nombre", ""))]
    return salida


def prompt(cfg: dict) -> str:
    """El bloque que se suma al system prompt. Vacio si no hay nada encendido.

    Vacio de verdad: este texto viaja en CADA llamada al modelo, y un titulo
    con nada abajo es peaje puro. Es la misma regla que en `addons.prompt`.
    """
    if modo(cfg) == "apagado":
        return ""
    cat = {n: hs for n, hs in catalogo(cfg).items() if hs}
    if not cat:
        return ""
    lineas = []
    for servidor, herramientas in cat.items():
        lineas.append(f"### {servidor}")
        for h in herramientas:
            desc = h.get("descripcion", "").replace("\n", " ")[:120]
            lineas.append(f"  {h['nombre']}  {desc}".rstrip())
    if modo(cfg) == "cliente":
        cabecera = ("Herramientas de servidores MCP. Se llaman con\n"
                    "`E mcp SERVIDOR HERRAMIENTA {\"clave\": \"valor\"}`.\n"
                    "El usuario confirma cada una antes de que corra.")
    else:
        cabecera = ("Servidores MCP que el usuario tiene configurados. NO los\n"
                    "puedes llamar: estan en modo lectura. Si hace falta uno,\n"
                    "dilo y que lo use el.")
    return "\n\n## MCP\n\n" + cabecera + "\n" + "\n".join(lineas)


def llamar(servidor: str, herramienta: str, argumentos, cfg: dict) -> str:
    """Corre una herramienta ajena, con el freno puesto.

    El orden importa y es el mismo que usan los addons: primero se comprueba
    que este permitido, despues se PREGUNTA, y recien ahi se corre. Anotar
    despues de correr seria un registro de lo que ya paso, no un freno.
    """
    if modo(cfg) != "cliente":
        return ("Los servidores MCP estan en modo lectura: puedo decir que "
                "existen, no llamarlos. Se cambia en Panel > Addons.")
    srv = activos().get(servidor)
    if srv is None:
        conocidos = ", ".join(sorted(activos())) or "ninguno"
        return f"No hay un servidor MCP {servidor!r} encendido. Hay: {conocidos}."
    if not herramienta_activa(srv, herramienta):
        return f"La herramienta {herramienta!r} esta apagada en {servidor!r}."

    if isinstance(argumentos, str):
        try:
            argumentos = json.loads(argumentos or "{}")
        except ValueError:
            return "Los argumentos tienen que ser un JSON."
    if not isinstance(argumentos, dict):
        return "Los argumentos tienen que ser un JSON."

    detalle = f"{servidor} {herramienta} {json.dumps(argumentos)[:300]}"
    # Se pregunta SALVO que hayas marcado esa herramienta como de confianza. Al
    # reves --correr y preguntar solo por las riesgosas-- exigiria saber que
    # hace cada herramienta ajena, y no se sabe: el nombre lo elige quien
    # escribio el servidor.
    if herramienta not in srv.get("confiadas", []) and cfg.get("confirm_destructive", True):
        if not plataforma.preguntar(
                f"Un servidor MCP quiere correr esto:\n\n{detalle}",
                f"Confirmar: {servidor} {herramienta}"):
            store.log_action(f"mcp/{servidor}", detalle, "DENEGADO por el usuario")
            return "El usuario no dejo hacer eso."
    store.log_action(f"mcp/{servidor}", detalle, "permitido")
    try:
        with Cliente(servidor, srv) as c:
            return c.llamar(herramienta, argumentos)
    except (OSError, RuntimeError, ValueError) as exc:
        return f"ERROR de {servidor}: {exc}"
