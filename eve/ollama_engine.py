"""Motor local: Ollama en vez de la nube.

Tercer motor con la misma interfaz que `brain.Eve` y `cc_engine.ClaudeCodeEve`.
Sin API key, sin suscripcion, sin que nada salga de la maquina.

Reutiliza el esquema de tools de `brain.TOOLS` tal cual — Ollama acepta el mismo
JSON Schema — y la ejecucion de `brain.Eve`, para que el freno de `safety.py` y
el log de auditoria sean exactamente los mismos que en el motor de Anthropic.

Limitacion honesta: los modelos chicos locales aciertan bastante menos que Claude
al elegir y encadenar tools. Para pedidos de un paso andan bien; para tareas de
varios pasos se pierden.
"""

import json
import time

import requests

from . import brain, prompt, store

SYSTEM = brain.SYSTEM


class OllamaEve:
    """Misma interfaz que los otros motores: .ask(texto) -> respuesta."""

    motor = "ollama"

    def __init__(self, cfg: dict, confirm=None, on_status=None):
        self.cfg = cfg
        self.on_status = on_status or (lambda _: None)
        self._destino(cfg)
        # La ejecucion de tools, el freno y el log se delegan en brain.Eve para
        # no tener dos implementaciones del mismo control de seguridad.
        self.runner = brain.Eve.__new__(brain.Eve)
        self.runner.cfg = cfg
        self.runner.confirm = confirm or (lambda reason, detail: False)
        self.runner.on_status = self.on_status
        # Igual que en los otros: el hilo lo guarda el log comun, no el motor.
        self.historial: list[dict] = store.historial_neutro(cfg)
        # Gasto del turno en curso. Lo llena _pedir/ask y lo lee log_turn.
        self.uso: dict = {}

        disponible, detalle = self.comprobar()
        if not disponible:
            raise RuntimeError(detalle)

    def _destino(self, cfg: dict) -> None:
        """A donde se manda el pedido. Lo reemplaza CompatEve con lo suyo.

        Va en un metodo y no suelto en __init__ porque una subclase que setee
        host y modelo antes de llamar a super() se los encuentra pisados por
        estos: asi le paso a compat_engine, que quedo apuntando a Ollama y
        contestando 404 aunque estuviera configurado para Gemini.
        """
        self.host = cfg.get("ollama_host", "http://localhost:11434").rstrip("/")
        self.modelo = cfg.get("ollama_model", "qwen3:8b")

    def comprobar(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=10)
            r.raise_for_status()
        except requests.RequestException:
            return False, (
                f"No hay un Ollama escuchando en {self.host}. Instalalo desde ollama.com "
                "y dejalo corriendo, o cambia el motor en el panel."
            )
        instalados = [m["name"] for m in r.json().get("models", [])]
        exacto = next((m for m in instalados if m == self.modelo), "")
        if exacto:
            return True, "ok"
        # Por prefijo se adopta el nombre COMPLETO del instalado. Antes esto
        # devolvia "ok" y dejaba puesto el nombre sin tag: con `qwen3:8b`
        # bajado y `qwen3` configurado, la comprobacion pasaba y despues cada
        # pedido moria en un 404 del propio Ollama, o sea el peor reparto
        # posible --el chequeo dice que si y el uso dice que no.
        con_tag = next((m for m in instalados
                        if m.startswith(self.modelo + ":")), "")
        if con_tag:
            self.modelo = con_tag
            return True, "ok"
        # El modelo pedido no esta, pero hay OTROS: se usa uno y se avisa, en
        # vez de negarse. `qwen3:8b` es el default de fabrica, o sea un nombre
        # que nadie eligio, y plantarse con "no tengo qwen3:8b" teniendo un
        # Ollama sano con modelos bajados es negarse por un detalle que al
        # usuario no le importa. El que quiera uno exacto lo pone en el panel,
        # y ahi si manda: entonces si es una eleccion y no un default.
        if instalados:
            self.modelo = instalados[0]
            return True, f"uso {self.modelo}, que el pedido no estaba"
        return False, (
            "Ollama anda pero no tiene ningun modelo bajado. Corre: "
            f"ollama pull {self.modelo}"
        )

    def reset_context(self) -> None:
        self.historial = []
        store.olvidar()

    def _system(self) -> str:
        return prompt.construir(self.cfg)

    def _tools(self) -> list[dict]:
        """`brain.TOOLS` al formato de Ollama: mismo schema, otro envoltorio."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in brain.TOOLS
        ]

    def ask(self, text: str) -> str:
        store.log_turn("user", text, self.motor)
        ahora = time.time()
        self.historial = store.trim_history(
            self.historial, self.cfg["context_turns"], self.cfg["context_minutes"], ahora
        )
        self.historial.append({"ts": ahora, "role": "user", "content": text})
        self.uso = {}

        # Tope mas bajo que en la nube: si un modelo local no resolvio en 6 pasos,
        # se perdio, y seguir solo gasta tiempo.
        for _ in range(6):
            mensajes = [{"role": "system", "content": self._system()}]
            mensajes += [{k: v for k, v in m.items() if k != "ts"} for m in self.historial]

            self.on_status("Pensando (local)...")
            try:
                r = requests.post(
                    f"{self.host}/api/chat",
                    json={
                        "model": self.modelo,
                        "messages": mensajes,
                        "tools": self._tools(),
                        "stream": False,
                        "options": {"temperature": 0.4},
                    },
                    timeout=600,
                )
                r.raise_for_status()
                datos = r.json()
                msg = datos.get("message", {})
                # Ollama los llama distinto que todos los demas.
                store.sumar_uso(self.uso, datos.get("prompt_eval_count", 0),
                                datos.get("eval_count", 0))
            except requests.RequestException as exc:
                return f"Ollama fallo: {exc}"

            llamadas = msg.get("tool_calls") or []
            self.historial.append({"ts": time.time(), **msg})

            if not llamadas:
                respuesta = (msg.get("content") or "").strip() or "Listo."
                store.log_turn("assistant", respuesta, self.motor, self.uso)
                return respuesta

            for llamada in llamadas:
                fn = llamada.get("function", {})
                nombre = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):  # algunos modelos mandan el JSON como texto
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                texto, _ = self._ejecutar(nombre, args)
                self.historial.append(
                    {"ts": time.time(), "role": "tool", "content": texto[:6000]}
                )

        return "Me perdi con el modelo local. Proba de nuevo o cambia a un motor en la nube."

    def _ejecutar(self, nombre: str, args: dict) -> tuple[str, bool]:
        """Pasa por el mismo freno que el motor de Anthropic."""
        from . import safety

        detalle = f"{nombre} {args}"
        motivo = safety.needs_confirmation(nombre, args, self.cfg["workdirs"])
        if motivo and self.cfg.get("confirm_destructive", True):
            self.on_status(f"Esperando confirmacion: {motivo}")
            if not self.runner.confirm(motivo, detalle):
                store.log_action(nombre, detalle, "DENEGADO por el usuario")
                return "El usuario denego esta accion. No la reintentes.", True

        self.on_status(f"Ejecutando {nombre}...")
        texto, error = self.runner._run(nombre, args)
        prefijo = "ERROR: " if error else ""
        if motivo:
            prefijo = f"[riesgoso: {motivo}] " + prefijo
        store.log_action(nombre, detalle, prefijo + texto[:500])
        return texto, error
