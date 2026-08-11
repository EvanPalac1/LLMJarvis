"""Motor alternativo: Claude Code headless en vez de la Messages API.

Sirve para correr Eve con una suscripcion de Claude (Pro/Max) sin API key: el
CLI usa el login que ya tenes. A cambio, cada llamada carga el system prompt y
las tools completas de Claude Code (~36k tokens de cache), asi que es mas lenta
y consume mas de tu limite de uso que la API cruda.

El freno vive en un hook PreToolUse (eve/hook_gate.py), no en brain.py: aca las
tools las ejecuta Claude Code, no nosotros.
"""

import json
import os
import subprocess
import sys
import time

from . import apps, integrations, store

SETTINGS_PATH = os.path.join(store.BASE, "cc_settings.json")

PERSONA = """Sos {name}, un asistente de voz. El usuario te habla por microfono y tu
respuesta final se lee en voz alta con un sintetizador. Idioma: {lang}.

{brief}

## Catalogo de programas

{catalog_header} La voz deforma los nombres en ingles: elegi la entrada mas parecida a
lo que se escucho, no exijas coincidencia literal. Si no esta, usa Get-StartApps.

{catalog}

{integrations}
"""


def write_settings() -> str:
    """Genera el settings JSON con el hook del freno. Idempotente."""
    from . import plataforma

    if plataforma.congelado():
        comando, args = sys.executable, ["--hook"]
    else:
        comando = sys.executable.replace("pythonw.exe", "python.exe")
        args = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook_gate.py")]
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": comando, "args": args, "timeout": 300}
                    ],
                }
            ]
        }
    }
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return SETTINGS_PATH


class ClaudeCodeEve:
    """Misma interfaz que brain.Eve: .ask(texto) -> respuesta."""

    def __init__(self, cfg: dict, confirm=None, on_status=None):
        self.cfg = cfg
        self.on_status = on_status or (lambda _: None)
        self.settings = write_settings()
        self._session: str | None = None
        self._last = 0.0
        if not _claude_available():
            raise RuntimeError(
                "El motor 'claude-code' necesita el CLI de Claude Code instalado y con sesion "
                "iniciada (corre `claude` una vez y logueate)."
            )

    def reset_context(self) -> None:
        """Suelta la sesion de Claude Code: el proximo pedido arranca una nueva."""
        self._session = None
        self._last = 0.0

    def _build_cmd(self, text: str) -> list[str]:
        cmd = [
            "claude",
            "-p",
            text,
            "--output-format",
            "json",
            "--model",
            self.cfg["cc_model"],
            "--append-system-prompt",
            PERSONA.format(
                name=self.cfg["assistant_name"],
                lang="espanol" if self.cfg["language"] == "es" else self.cfg["language"],
                brief=store.load_brief(),
                catalog=apps.catalog(),
                catalog_header=apps.catalog_header(),
                integrations=integrations.prompt_section(),
            ),
            "--settings",
            self.settings,
        ]
        if self.cfg.get("confirm_destructive", True):
            cmd += ["--permission-mode", self.cfg["cc_permission_mode"]]
        else:
            # Allow all. Sin esto, el hook dice "allow" pero la capa de permisos
            # propia de Claude Code sigue denegando en silencio (headless no puede
            # preguntar), y el usuario ve tareas que fallan sin motivo visible.
            cmd += ["--dangerously-skip-permissions"]

        for d in self.cfg["workdirs"]:
            cmd += ["--add-dir", d]

        # Continuidad dentro de la ventana; pasada esa, sesion nueva y limpia.
        if self._session and time.time() - self._last < self.cfg["context_minutes"] * 60:
            cmd += ["--resume", self._session]
        return cmd

    def ask(self, text: str) -> str:
        store.log_turn("user", text)
        cmd = self._build_cmd(text)
        self.on_status("Pensando...")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            cwd=self.cfg["workdirs"][0] if self.cfg["workdirs"] else None,
        )
        if proc.returncode != 0:
            store.log_action("claude-cli", " ".join(cmd[:4]), f"ERROR: {proc.stderr[:500]}")
            return "El motor de Claude Code fallo. Revisa el registro en el panel."

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return "No pude leer la respuesta de Claude Code."

        self._session = data.get("session_id") or self._session
        self._last = time.time()

        denials = data.get("permission_denials") or []
        if denials:
            store.log_action(
                "claude-cli", "permisos denegados", json.dumps(denials, ensure_ascii=False)[:500]
            )

        reply = (data.get("result") or "").strip() or "Listo."
        store.log_turn("assistant", reply)
        return reply


def _claude_available() -> bool:
    from shutil import which

    return which("claude") is not None
