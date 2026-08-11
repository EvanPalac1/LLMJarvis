"""Hook PreToolUse para el motor Claude Code.

Claude Code headless no puede preguntarle nada al usuario: lo que no esta
permitido se deniega en silencio. Este hook reintroduce el freno — traduce cada
tool de Claude Code a nuestro chequeo de safety.py y, si es riesgoso, saca un
dialogo modal de Windows antes de dejarlo pasar.

Se invoca solo, via cc_settings.json. No se importa desde el resto del programa.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eve import plataforma, safety, store  # noqa: E402

# Tools de Claude Code que no tocan el sistema: pasan sin preguntar.
READ_ONLY = {"Glob", "Grep", "TodoWrite", "WebSearch", "WebFetch", "Task", "SlashCommand"}


def ask_user(msg: str) -> bool:
    """Dialogo modal del SO. Aislado para poder sustituirlo en los tests."""
    return plataforma.preguntar(msg, "LLMJarvis - confirmar accion")


def translate(tool_name: str, tool_input: dict) -> tuple[str, dict] | None:
    """Tool de Claude Code -> (nuestra tool, args). None = no evaluable."""
    if tool_name == "Bash":
        return "run_command", {"command": tool_input.get("command", "")}
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        return "write_file", {"path": tool_input.get("file_path", "")}
    if tool_name == "Read":
        return "read_file", {"path": tool_input.get("file_path", "")}
    return None


def decide(payload: dict, cfg: dict) -> tuple[str, str]:
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name in READ_ONLY:
        return "allow", ""

    pair = translate(tool_name, tool_input)
    if pair is None:
        # Tool que no sabemos evaluar (MCP, plugins): preguntar.
        reason = f"tool no reconocida por el freno: {tool_name}"
    else:
        our_tool, args = pair
        reason = safety.needs_confirmation(our_tool, args, cfg["workdirs"])
        if reason is None:
            return "allow", ""

    detail = json.dumps(tool_input, ensure_ascii=False)[:600]

    if not cfg.get("confirm_destructive", True):
        # Allow all: no se pregunta, pero queda asentado. El log es el unico
        # registro que queda de una accion riesgosa en este modo.
        store.log_action(tool_name, detail, f"AUTO-PERMITIDO (allow all) - {reason}")
        return "allow", ""

    ok = ask_user(f"{tool_name}\n\n{reason}\n\n{detail}\n\nPermitir?")
    store.log_action(tool_name, detail, "PERMITIDO por el usuario" if ok else "DENEGADO por el usuario")
    if ok:
        return "allow", ""
    return "deny", f"El usuario denego esta accion ({reason}). No la reintentes; pregunta que hacer."


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # sin decision -> flujo normal de permisos

    decision, why = decide(payload, store.load_config())
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    if why:
        out["hookSpecificOutput"]["permissionDecisionReason"] = why
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
