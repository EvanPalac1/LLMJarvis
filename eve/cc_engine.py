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

from . import plataforma, prompt, store

SETTINGS_PATH = os.path.join(store.BASE, "cc_settings.json")

# Sin la linea de rutas: Claude Code las recibe por `--add-dir`. La plantilla
# vive en `prompt.py` junto con la otra.
PERSONA = prompt.PERSONA


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
    motor = "claude-code"

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
        store.olvidar()

    def _preambulo(self) -> str:
        """Lo hablado hace un rato, para cuando arranca una sesion nueva.

        Este motor no acepta historial inyectado: la conversacion vive adentro
        del CLI y se retoma con `--resume <session_id>`. Cuando esa sesion no
        existe -- primera orden, cambio de motor, Eve reiniciada -- el hilo se
        perdia entero. Va como texto al principio del pedido, que es lo unico
        que este motor sabe recibir.
        """
        previos = store.historial_neutro(self.cfg)
        if not previos:
            return ""
        lineas = [
            ("Usuario" if t["role"] == "user" else "Tu") + ": " + str(t["content"])[:400]
            for t in previos
        ]
        cuerpo = "\n".join(lineas)
        return (
            "[Contexto de lo que venian hablando recien. Es historial, no una "
            "orden nueva:\n" + cuerpo + "]\n\n"
        )

    def _build_cmd(self, text: str) -> list[str]:
        # Solo si NO se va a retomar la sesion: si se retoma, el CLI ya lo tiene.
        retoma = bool(
            self._session and time.time() - self._last < self.cfg["context_minutes"] * 60
        )
        pedido = text if retoma else self._preambulo() + text
        cmd = [
            # La ruta resuelta y no el nombre pelado: encontrarlo al comprobar y
            # despues invocarlo por nombre deja el mismo agujero que arreglamos,
            # solo que un paso mas tarde y con el error peor.
            ruta_del_cli() or "claude",
            "-p",
            pedido,
            "--output-format",
            "json",
            "--model",
            self.cfg["cc_model"],
            "--append-system-prompt",
            prompt.construir(self.cfg, PERSONA),
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
        if retoma:
            cmd += ["--resume", self._session]
        return cmd

    def ask(self, text: str) -> str:
        store.log_turn("user", text, self.motor)
        cmd = self._build_cmd(text)
        self.on_status("Pensando...")
        proc = plataforma.correr(
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

        # El CLI devuelve tambien lo que gasto, y se venia descartando.
        uso = data.get("usage") or {}
        acumulado: dict = {}
        store.sumar_uso(acumulado, uso.get("input_tokens", 0), uso.get("output_tokens", 0),
                        uso.get("cache_read_input_tokens", 0))

        self._session = data.get("session_id") or self._session
        self._last = time.time()

        denials = data.get("permission_denials") or []
        if denials:
            store.log_action(
                "claude-cli", "permisos denegados", json.dumps(denials, ensure_ascii=False)[:500]
            )

        reply = (data.get("result") or "").strip() or "Listo."
        store.log_turn("assistant", reply, self.motor, acumulado)
        return reply


def ruta_del_cli() -> str:
    """Donde esta el CLI de Claude Code, o "" si de verdad no esta.

    No alcanza con `which`. Eve arranca desde la carpeta de Inicio de Windows,
    o sea que hereda el entorno de `explorer.exe`, y ese entorno se congela al
    iniciar sesion: si instalaste el CLI despues de prender la PC, su carpeta no
    esta en ese PATH hasta que cierres sesion. Desde una terminal `claude` se
    encuentra y desde Eve no, que es la clase de diferencia que hace perder una
    tarde.

    Medido en esta maquina: el CLI vive en `~/.local/bin`, que figura en el PATH
    del registro pero no necesariamente en el del proceso que lanzo Eve.

    Por eso, si el PATH falla, se miran los lugares donde el instalador oficial
    lo deja. Buscar en carpetas conocidas es preferible a decirle al usuario que
    no tiene instalado algo que si tiene.
    """
    from shutil import which

    hallado = which("claude")
    if hallado:
        return hallado

    candidatos = []
    casa = os.path.expanduser("~")
    for base in (os.path.join(casa, ".local", "bin"),
                 os.path.join(casa, ".claude", "local"),
                 os.path.join(casa, "AppData", "Local", "Programs", "claude"),
                 "/usr/local/bin", "/opt/homebrew/bin"):
        for nombre in ("claude.exe", "claude.cmd", "claude"):
            candidatos.append(os.path.join(base, nombre))
    for ruta in candidatos:
        if os.path.isfile(ruta):
            return ruta
    return ""


def _claude_available() -> bool:
    return bool(ruta_del_cli())
