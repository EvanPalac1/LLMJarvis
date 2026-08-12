"""Config (JSON), claves (keyring del SO) e historial (SQLite).

Nada de esto vive en la API: el programa es dueño del historial, la API solo
recibe una ventana corta. El panel lee de aca, no de Anthropic.
"""

import json
import os
import shutil
import sqlite3
import time

from . import plataforma

# Datos del usuario: escribibles, sobreviven a desinstalar y reinstalar.
BASE = plataforma.datos_usuario()
# Archivos que viajan con el programa y no se tocan.
RECURSOS = plataforma.recursos()

CONFIG_PATH = os.path.join(BASE, "config.json")
DB_PATH = os.path.join(BASE, "eve.db")


def _migrar_desde_codigo() -> None:
    """Mueve los datos de una instalacion vieja, cuando vivian junto al codigo.

    Se corre una sola vez: si el archivo ya existe en la carpeta nueva, no se
    pisa. Sin esto, actualizar a la version instalable perderia la agenda, la
    memoria y el historial.
    """
    viejo = plataforma.recursos()
    if os.path.abspath(viejo) == os.path.abspath(BASE):
        return
    for nombre in ("config.json", "contactos.json", "eve.db", "apps.json", "MEMORIA.md"):
        origen, destino = os.path.join(viejo, nombre), os.path.join(BASE, nombre)
        if os.path.exists(origen) and not os.path.exists(destino):
            try:
                shutil.copy2(origen, destino)
            except OSError:
                pass
    # Las voces son descargas de decenas de MB: no hacerlas bajar de nuevo.
    # Archivo por archivo, no copytree: la carpeta destino puede existir ya con
    # el catalogo adentro y copytree se saltearia todo.
    origen, destino = os.path.join(viejo, "voices"), os.path.join(BASE, "voices")
    if os.path.isdir(origen):
        os.makedirs(destino, exist_ok=True)
        for nombre in os.listdir(origen):
            src, dst = os.path.join(origen, nombre), os.path.join(destino, nombre)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass


_migrar_desde_codigo()

SERVICE = "LLMJarvis"
KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "openai": "OPENAI_API_KEY",
    # Conexiones con apps. Todas opcionales: sin ellas, Eve compone el mensaje y
    # lo abre en la app para que lo mandes vos.
    "gmail": "GMAIL_APP_PASSWORD",
    "discord_webhook": "DISCORD_WEBHOOK_URL",
    "steam": "STEAM_API_KEY",
}

DEFAULTS = {
    "assistant_name": "Eve",
    "language": "es",
    # "api"         -> Messages API directa. Necesita ANTHROPIC_API_KEY.
    # "claude-code" -> CLI de Claude Code headless. Usa tu suscripcion, sin key.
    # "ollama"      -> modelo local. Sin key, sin nube, pero peor con tools.
    "engine": "api",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "qwen3:8b",
    # Opus 5 por defecto. Cambialo a claude-sonnet-5 o claude-haiku-4-5 desde
    # el panel si preferis latencia sobre capacidad.
    "model": "claude-opus-5",
    "cc_model": "sonnet",
    "cc_permission_mode": "acceptEdits",
    "effort": "medium",
    "max_tokens": 8000,
    "hotkey": "f13",
    "workdirs": [os.path.join(os.path.expanduser("~"), "Documents")],
    "stt_provider": "faster-whisper",  # faster-whisper | openai
    # 'base' destroza los nombres propios en ingles ("rainbow six siege" ->
    # "Haberé en Vox XC"). 'small' con vocabulario los acierta.
    "stt_model": "small",
    "stt_device": "cpu",
    "stt_vocabulary": "",  # palabras extra que el STT suele errar
    # piper es el unico que funciona igual en los tres sistemas; sapi es solo
    # Windows, y dejarlo de default afuera hacia que Eve no pudiera hablar en una
    # instalacion limpia de Linux o macOS.
    "tts_provider": "sapi" if plataforma.WINDOWS else "piper",  # sapi|piper|elevenlabs
    "tts_voice": "",
    "piper_voice": "",  # clave del catalogo, ej. es_ES-davefx-medium
    "elevenlabs_voice_id": "",
    "context_turns": 6,
    "context_minutes": 10,
    # False = "allow all": ni el freno propio ni el de Claude Code preguntan nada.
    # Todo lo ejecutado sigue quedando en el log de auditoria (tabla `actions`),
    # que pasa a ser el unico registro de lo que hizo Eve.
    "confirm_destructive": True,
    "speak_replies": True,
    "gmail_address": "",
    "steam_id": "",
    # Simula el Enter final en WhatsApp. El destino lo garantiza la URI con el
    # numero, no una busqueda por nombre.
    "whatsapp_autosend": True,
    # Escribe en Discord manejando tu cliente. Es la via fragil: depende del foco
    # de la ventana. El webhook con `discord_username` es mas confiable.
    "discord_autosend": True,
    # Nombre y foto con los que aparecen los mensajes del webhook.
    "discord_username": "",
    "discord_avatar": "",
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


CONTACTS_PATH = os.path.join(BASE, "contactos.json")
# El manual viaja con el programa; la memoria es del usuario.
BRIEF_PATH = os.path.join(RECURSOS, "EVE.md")


def load_contacts() -> list[dict]:
    """Agenda propia: nombre, alias, mail, telefono y canal de Discord.

    Aparte de config.json porque crece, se edita en su propia tabla, y no tiene
    que perderse si alguien toca la config a mano.
    """
    if not os.path.exists(CONTACTS_PATH):
        return []
    try:
        with open(CONTACTS_PATH, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(datos, list):
        return []
    for c in datos:
        # Antes habia un solo campo `discord`; ahora estan separados. Se migra al
        # vuelo para no perder lo ya cargado.
        if c.get("discord") and not c.get("discord_dm"):
            c["discord_dm"] = c.pop("discord")
    return datos


def save_contacts(contactos: list[dict]) -> None:
    with open(CONTACTS_PATH, "w", encoding="utf-8") as f:
        json.dump(contactos, f, indent=2, ensure_ascii=False)


def _plano(texto: str) -> str:
    """Minusculas sin tildes: la voz transcribe 'Nicolas' tanto como 'Nicolás'."""
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower()) if not unicodedata.combining(c)
    ).strip()


def buscar_contacto(texto: str) -> list[dict]:
    """Coincidencias por nombre o alias. Devuelve varias si son ambiguas."""
    objetivo = _plano(texto)
    if not objetivo:
        return []
    exactos, parciales = [], []
    for c in load_contacts():
        campos = [c.get("nombre", "")] + str(c.get("alias", "")).split(",")
        campos = [_plano(x) for x in campos if x and x.strip()]
        if objetivo in campos:
            exactos.append(c)
        elif any(objetivo in campo or campo in objetivo for campo in campos):
            parciales.append(c)
    return exactos or parciales


FORMATO_CONTACTO = "evecontact"
CAMPOS_CONTACTO = (
    "nombre", "alias", "email", "telefono",
    "discord_user", "discord_dm", "discord_canal",
)


def exportar_contactos(nombres: list[str], destino: str) -> str:
    """Guarda contactos en un .evecontact para mandarselos a alguien.

    Siempre una lista, aunque sea uno solo: el mismo archivo sirve para compartir
    un contacto o la agenda entera, y quien lo recibe usa el mismo boton.
    """
    elegidos = []
    for nombre in nombres:
        hits = buscar_contacto(nombre)
        if not hits:
            return f"No encontre a {nombre!r} en la agenda."
        elegidos.append({k: hits[0].get(k, "") for k in CAMPOS_CONTACTO if hits[0].get(k)})
    if not elegidos:
        return "No hay nada para exportar."

    with open(destino, "w", encoding="utf-8") as f:
        json.dump(
            {"formato": FORMATO_CONTACTO, "version": 1, "contactos": elegidos},
            f, indent=2, ensure_ascii=False,
        )
    cuantos = len(elegidos)
    return f"{cuantos} contacto{'s' if cuantos > 1 else ''} exportado{'s' if cuantos > 1 else ''} a {destino}"


def leer_contactos_archivo(ruta: str) -> list[dict]:
    """Contactos de un .evecontact, validados. Lanza ValueError si no sirve."""
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No pude leer el archivo: {exc}") from exc

    if not isinstance(datos, dict) or datos.get("formato") != FORMATO_CONTACTO:
        raise ValueError("Eso no es un archivo de contactos de Eve.")

    salida = []
    for c in datos.get("contactos", []):
        if not isinstance(c, dict) or not c.get("nombre"):
            continue
        # Solo campos conocidos: un archivo de una version futura no rompe nada
        # ni mete claves raras en la agenda.
        salida.append({k: str(c[k]) for k in CAMPOS_CONTACTO if c.get(k)})
    if not salida:
        raise ValueError("El archivo no tiene ningun contacto valido.")
    return salida


def importar_contactos(nuevos: list[dict], reemplazar: set[str] | None = None) -> tuple[int, int, list[str]]:
    """Fusiona contactos en la agenda.

    Devuelve (agregados, reemplazados, nombres_en_conflicto). Los que ya existen
    y no estan en `reemplazar` se dejan como estan: pisar la agenda de alguien en
    silencio no es aceptable.
    """
    reemplazar = reemplazar or set()
    agenda = load_contacts()
    por_nombre = {_plano(c.get("nombre", "")): i for i, c in enumerate(agenda)}

    agregados = cambiados = 0
    conflictos = []
    for c in nuevos:
        clave = _plano(c["nombre"])
        if clave in por_nombre:
            if c["nombre"] in reemplazar or clave in {_plano(x) for x in reemplazar}:
                agenda[por_nombre[clave]] = c
                cambiados += 1
            else:
                conflictos.append(c["nombre"])
            continue
        agenda.append(c)
        por_nombre[clave] = len(agenda) - 1
        agregados += 1

    if agregados or cambiados:
        save_contacts(agenda)
    return agregados, cambiados, conflictos


MEMORIA_PATH = os.path.join(BASE, "MEMORIA.md")


def load_brief() -> str:
    """Manual de comportamiento + memoria. Va entero en cada system prompt, asi
    que los archivos estan escritos telegraficos a proposito.

    Son dos archivos separados a proposito: `EVE.md` es el manual, igual para
    todos y versionado; `MEMORIA.md` son los datos del usuario, que no van al
    repositorio.
    """
    partes = []
    if os.path.exists(BRIEF_PATH):
        with open(BRIEF_PATH, encoding="utf-8") as f:
            texto = f.read()
        # La primera linea es el titulo y la segunda una nota para quien lo
        # edita: el modelo no las necesita.
        cuerpo = texto.split("\n## ", 1)
        partes.append("## " + cuerpo[1] if len(cuerpo) > 1 else texto)
    if os.path.exists(MEMORIA_PATH):
        with open(MEMORIA_PATH, encoding="utf-8") as f:
            memoria = f.read().strip()
        if memoria:
            partes.append(memoria)
    return "\n\n".join(partes)


def get_key(provider: str) -> str:
    """Clave desde el gestor de credenciales del SO; env var como fallback."""
    env = os.environ.get(KEY_NAMES.get(provider, ""))
    if env:
        return env
    import keyring  # import perezoso: los tests de logica no lo necesitan

    return keyring.get_password(SERVICE, provider) or ""


def set_key(provider: str, value: str) -> None:
    import keyring

    if value:
        keyring.set_password(SERVICE, provider, value)
    else:
        try:
            keyring.delete_password(SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            pass


# --- historial -------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    tool TEXT NOT NULL,
    detail TEXT NOT NULL,
    outcome TEXT NOT NULL
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def log_turn(role: str, text: str) -> None:
    with db() as conn:
        conn.execute("INSERT INTO turns (ts, role, text) VALUES (?,?,?)", (time.time(), role, text))


def log_action(tool: str, detail: str, outcome: str) -> None:
    """Log de auditoria. Sin esto, 'se ejecuto algo mal' es indepurable."""
    with db() as conn:
        conn.execute(
            "INSERT INTO actions (ts, tool, detail, outcome) VALUES (?,?,?,?)",
            (time.time(), tool, detail[:2000], outcome[:2000]),
        )


def recent_turns(limit: int = 200) -> list[tuple]:
    with db() as conn:
        return conn.execute(
            "SELECT ts, role, text FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def recent_actions(limit: int = 200) -> list[tuple]:
    with db() as conn:
        return conn.execute(
            "SELECT ts, tool, detail, outcome FROM actions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


LATIDO_PATH = os.path.join(BASE, "latido.json")


def latir(datos: dict) -> None:
    """El asistente deja señales de vida para que el panel sepa si esta vivo."""
    datos = {**datos, "ts": time.time(), "pid": os.getpid()}
    try:
        with open(LATIDO_PATH, "w", encoding="utf-8") as f:
            json.dump(datos, f)
    except OSError:
        pass


def latido(max_edad: float = 20.0) -> dict | None:
    """Ultimo latido si es reciente, None si el asistente no esta corriendo.

    Un archivo en vez de preguntarle al SO por los procesos: consultar `tasklist`
    cada pocos segundos desde una app sin consola abria y cerraba una ventana
    negra todo el tiempo, y ademas es mucho mas caro que leer 80 bytes.
    """
    try:
        with open(LATIDO_PATH, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return datos if time.time() - datos.get("ts", 0) < max_edad else None


def clear_history(also_actions: bool = False) -> int:
    """Borra la conversacion guardada. El log de auditoria se conserva salvo que
    se pida lo contrario: es el registro de lo que Eve ejecuto en la PC."""
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        conn.execute("DELETE FROM turns")
        if also_actions:
            conn.execute("DELETE FROM actions")
    return n


def trim_history(history: list[dict], max_turns: int, max_minutes: float, now: float) -> list[dict]:
    """Ventana rodante: ni stateless puro ni chat infinito.

    Cada entrada es {"ts": float, "role": str, "content": ...}. Descarta lo
    viejo por tiempo y por cantidad, y garantiza que el primer mensaje que
    queda sea de rol `user` (la API rechaza historiales que arrancan en
    assistant, y un tool_result huerfano tambien).
    """
    cutoff = now - max_minutes * 60
    kept = [m for m in history if m["ts"] >= cutoff][-max_turns:]
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    # Un turno user que arranca con tool_result quedo huerfano de su tool_use.
    while kept and _starts_with_tool_result(kept[0]):
        kept.pop(0)
        while kept and kept[0]["role"] != "user":
            kept.pop(0)
    return kept


def _starts_with_tool_result(msg: dict) -> bool:
    content = msg.get("content")
    if not isinstance(content, list) or not content:
        return False
    first = content[0]
    if isinstance(first, dict):
        return first.get("type") == "tool_result"
    return getattr(first, "type", None) == "tool_result"
