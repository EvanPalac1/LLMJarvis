"""Frenos. Sin dependencias externas — es la capa que el council marcó como
la que hunde el proyecto si falta, asi que se testea sola (ver test_eve.py)."""

import os
import re

# Patrones que NUNCA se ejecutan sin confirmacion explicita del usuario.
DESTRUCTIVE = [
    (r"\brm\s+-[a-z]*[rf]", "borrado recursivo (rm)"),
    (r"\bRemove-Item\b.*-Recurse", "borrado recursivo (Remove-Item)"),
    (r"\bdel\b.*\/[sq]", "borrado masivo (del)"),
    (r"\brmdir\b.*\/s", "borrado de directorio (rmdir)"),
    (r"\bformat\s+[a-z]:", "formateo de disco"),
    (r"\bdiskpart\b", "diskpart"),
    (r"\breg\s+delete\b", "borrado de registro"),
    (r"\bShutdown|\bRestart-Computer\b|\bshutdown\s+/", "apagado/reinicio"),
    (r"\bStop-Computer\b", "apagado"),
    (r"\bStop-Process\b.*-Force", "matar proceso forzado"),
    (r"\bSet-ExecutionPolicy\b", "cambio de politica de ejecucion"),
    (r"\bnetsh\b|\bbcdedit\b", "config de red/arranque"),
    (r">\s*[A-Za-z]:\\", "redireccion que sobrescribe archivo"),
    (r"\bcurl\b.*\|\s*(iex|sh|bash)", "descarga y ejecucion remota"),
    (r"\bInvoke-Expression\b|\biex\b", "Invoke-Expression"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in DESTRUCTIVE]


def destructive_reason(command: str) -> str | None:
    """Devuelve el motivo si el comando es destructivo, None si es seguro."""
    for rx, why in _COMPILED:
        if rx.search(command):
            return why
    return None


def path_allowed(path: str, workdirs: list[str]) -> bool:
    """True si `path` cae dentro de alguno de los workdirs permitidos.

    Resuelve symlinks y `..` antes de comparar: un allowlist que compara strings
    crudos se saltea con `C:\\ok\\..\\Windows`.
    """
    if not workdirs:
        return False
    try:
        target = os.path.realpath(os.path.abspath(path))
    except (OSError, ValueError):
        return False
    for root in workdirs:
        try:
            base = os.path.realpath(os.path.abspath(root))
        except (OSError, ValueError):
            continue
        try:
            dentro = os.path.commonpath([target, base]) == base
        except ValueError:
            # En Windows `commonpath` TIRA si las rutas estan en unidades
            # distintas, en vez de decir que no tienen nada en comun. Sin este
            # except, un workdir en C: y otro en D: --que es una config
            # normal-- hacia reventar la comprobacion ENTERA en el primer
            # workdir de otra unidad: no solo se rechazaba lo de afuera, se
            # rechazaba con un traceback lo que SI estaba permitido, porque la
            # excepcion salia antes de mirar el segundo workdir.
            #
            # Rutas en otra unidad no estan adentro de esta: se sigue con la
            # que viene. La guarda queda fail-closed igual.
            continue
        if dentro:
            return True
    return False


def needs_confirmation(tool_name: str, tool_input: dict, workdirs: list[str]) -> str | None:
    """Motivo por el que esta llamada a tool necesita un si/no del usuario.

    None = ejecutar directo.
    """
    if tool_name == "run_command":
        cmd = tool_input.get("command", "")
        why = destructive_reason(cmd)
        if why:
            return f"comando destructivo: {why}"
        cwd = tool_input.get("cwd")
        if cwd and not path_allowed(cwd, workdirs):
            return f"directorio fuera de las rutas permitidas: {cwd}"
        return None

    if tool_name in ("write_file", "read_file", "list_dir"):
        path = tool_input.get("path", "")
        if not path_allowed(path, workdirs):
            return f"ruta fuera de las rutas permitidas: {path}"
        return None

    return f"tool desconocida: {tool_name}"
