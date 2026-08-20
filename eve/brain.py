"""Loop de tools contra la Messages API de Anthropic.

Sin servidor MCP (el unico cliente sos vos: eso es una funcion, no un protocolo)
y sin router de modelos (un round-trip extra para ahorrar centimos en un
asistente donde la latencia percibida es todo). Llamada directa.
"""

import os
import subprocess
import time

import anthropic

from . import plataforma, prompt, safety, store

TOOLS = [
    {
        "name": "run_command",
        "description": (
            f"Ejecuta un comando de {plataforma.nombre_shell()} en la PC del usuario y devuelve stdout+stderr. "
            "Usalo para tareas del sistema, git, procesos, o cualquier cosa que no sea "
            "leer/escribir un archivo puntual."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": f"Comando de {plataforma.nombre_shell()} a ejecutar."},
                "cwd": {"type": "string", "description": "Directorio de trabajo (opcional)."},
            },
            "required": ["command"],
        },
    },
    {
        "name": "write_file",
        "description": "Crea o sobrescribe un archivo de texto con el contenido dado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta absoluta del archivo."},
                "content": {"type": "string", "description": "Contenido completo del archivo."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Lee un archivo de texto y devuelve su contenido.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Ruta absoluta."}},
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": "Lista el contenido de un directorio.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Ruta absoluta."}},
            "required": ["path"],
        },
    },
]

# Modelos que rechazan output_config.effort.
NO_EFFORT = ("claude-haiku-4-5", "claude-sonnet-4-5")

# La plantilla vive en `prompt.py`, que es donde se arma una sola vez para los
# cuatro motores. El alias queda porque `ollama_engine` la referencia por aca.
SYSTEM = prompt.SYSTEM


class Eve:
    # De clase: `ollama_engine` construye un Eve con __new__ para reusar _run()
    # sin pedir API key, y ese objeto nunca pasa por __init__.
    motor = "api"

    def __init__(self, cfg: dict, confirm=None, on_status=None):
        """confirm(reason, detail) -> bool. on_status(texto) para feedback en vivo."""
        self.cfg = cfg
        self.confirm = confirm or (lambda reason, detail: False)
        self.on_status = on_status or (lambda _: None)
        self.uso: dict = {}
        key = store.get_key("anthropic")
        if not key:
            raise RuntimeError("Falta la API key de Anthropic. Cargala en el panel de config.")
        self.client = anthropic.Anthropic(api_key=key)
        # Se arranca con lo que quedo en el log comun, no en blanco: cambiar de
        # motor o reiniciar Eve dejaba de existir la conversacion.
        self.history: list[dict] = store.historial_neutro(cfg)

    def reset_context(self) -> None:
        """Vuelve a arrancar en frio: el proximo pedido no ve nada anterior."""
        self.history = []
        store.olvidar()

    # --- ejecucion de tools ------------------------------------------------

    def _run(self, name: str, args: dict) -> tuple[str, bool]:
        """Devuelve (texto_resultado, es_error)."""
        try:
            if name == "run_command":
                proc = plataforma.correr(
                    plataforma.shell_cmd(args["command"]),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=args.get("cwd") or None,
                )
                out = (proc.stdout + proc.stderr).strip() or "(sin salida)"
                return out[:8000], proc.returncode != 0

            if name == "write_file":
                path = args["path"]
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(args["content"])
                return f"Escrito: {path} ({len(args['content'])} caracteres)", False

            if name == "read_file":
                with open(args["path"], encoding="utf-8", errors="replace") as f:
                    return f.read()[:8000], False

            if name == "list_dir":
                return "\n".join(sorted(os.listdir(args["path"])))[:8000], False

            return f"Tool desconocida: {name}", True
        except Exception as exc:  # noqa: BLE001 - el resultado vuelve al modelo
            return f"{type(exc).__name__}: {exc}", True

    def _handle_tool(self, block) -> dict:
        args = dict(block.input)
        detail = f"{block.name} {args}"
        reason = safety.needs_confirmation(block.name, args, self.cfg["workdirs"])

        if reason and self.cfg.get("confirm_destructive", True):
            self.on_status(f"Esperando confirmacion: {reason}")
            if not self.confirm(reason, detail):
                store.log_action(block.name, detail, "DENEGADO por el usuario")
                return {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "El usuario denego esta accion. No la reintentes; pregunta que hacer.",
                    "is_error": True,
                }

        self.on_status(f"Ejecutando {block.name}...")
        text, is_error = self._run(block.name, args)
        prefijo = "ERROR: " if is_error else ""
        if reason:  # llego hasta aca con un motivo => o lo aprobo el usuario, o es allow all
            prefijo = f"[riesgoso: {reason}] " + prefijo
        store.log_action(block.name, detail, prefijo + text[:500])
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": text,
            "is_error": is_error,
        }

    # --- loop --------------------------------------------------------------

    def _request(self, messages: list[dict]):
        kwargs = {
            "model": self.cfg["model"],
            "max_tokens": self.cfg["max_tokens"],
            "system": [
                {
                    "type": "text",
                    "text": prompt.construir(self.cfg),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "tools": TOOLS,
            "messages": messages,
        }
        if not self.cfg["model"].startswith(NO_EFFORT):
            kwargs["output_config"] = {"effort": self.cfg["effort"]}
        return self.client.messages.create(**kwargs)

    def ask(self, text: str) -> str:
        """Una instruccion hablada -> respuesta final en texto."""
        now = time.time()
        self.history = store.trim_history(
            self.history, self.cfg["context_turns"], self.cfg["context_minutes"], now
        )
        self.history.append({"ts": now, "role": "user", "content": text})
        # El gasto se acumula por turno, no por llamada: el loop de tools puede
        # dar varias vueltas y cada una cuesta.
        self.uso = {}
        store.log_turn("user", text, self.motor)

        for _ in range(12):  # tope duro: sin esto un loop de tools no termina nunca
            messages = [{"role": m["role"], "content": m["content"]} for m in self.history]
            resp = self._request(messages)
            u = getattr(resp, "usage", None)
            if u is not None:
                store.sumar_uso(self.uso, getattr(u, "input_tokens", 0),
                                getattr(u, "output_tokens", 0),
                                getattr(u, "cache_read_input_tokens", 0))

            # Opus 5 puede rechazar la peticion: chequear ANTES de leer content.
            if resp.stop_reason == "refusal":
                reply = "No puedo ayudarte con eso."
                self.history.append({"ts": time.time(), "role": "assistant", "content": reply})
                store.log_turn("assistant", reply, self.motor, self.uso)
                return reply

            self.history.append(
                {"ts": time.time(), "role": "assistant", "content": resp.content}
            )

            if resp.stop_reason != "tool_use":
                reply = "\n".join(b.text for b in resp.content if b.type == "text").strip()
                reply = reply or "Listo."
                store.log_turn("assistant", reply, self.motor, self.uso)
                return reply

            results = [self._handle_tool(b) for b in resp.content if b.type == "tool_use"]
            self.history.append({"ts": time.time(), "role": "user", "content": results})

        return "Me quede sin pasos antes de terminar la tarea."
