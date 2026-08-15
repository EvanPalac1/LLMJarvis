"""Motor para cualquier servicio que hable el protocolo de OpenAI.

Es UN motor, no cinco. Gemini, Groq, DeepSeek, OpenRouter, xAI, LM Studio y el
propio OpenAI exponen todos el mismo `POST /chat/completions` con `messages`,
`tools` y `tool_calls`. Escribir una integracion por proveedor seria copiar el
mismo archivo cambiando la URL, y despues mantener cinco copias cuando alguno
cambie algo. Aca el proveedor es configuracion: URL base, clave y modelo.

Presets conocidos en PROVEEDORES, para no tener que buscar la URL. Varios tienen
capa gratuita de verdad: Gemini y Groq regalan cuota diaria, y OpenRouter publica
modelos con sufijo `:free`.

Hereda de OllamaEve porque ese motor ya arma los mensajes, el esquema de tools y
el bucle de ejecucion con el freno de `safety.py`. Lo unico distinto es a donde
se manda el pedido y como se lee la respuesta.
"""

import time

import requests

from . import store
from .ollama_engine import OllamaEve

# nombre -> (url base, nombre de la clave en el llavero, modelo sugerido)
PROVEEDORES = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "gemini", "gemini-2.5-flash"),
    "openai": ("https://api.openai.com/v1", "openai", "gpt-5-mini"),
    "groq": ("https://api.groq.com/openai/v1", "groq", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek", "deepseek-chat"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter",
                   "deepseek/deepseek-chat-v3.1:free"),
    "xai": ("https://api.x.ai/v1", "xai", "grok-4-fast"),
    # Servidor local: no necesita clave y no sale nada de la maquina.
    "lmstudio": ("http://localhost:1234/v1", "", "local"),
    # "propio" usa lo que el usuario haya escrito en compat_url / compat_modelo.
    "propio": ("", "compat", ""),
}

GRATIS = ("gemini", "groq", "openrouter", "lmstudio")


class CompatEve(OllamaEve):
    """Misma interfaz que los otros motores: .ask(texto) -> respuesta."""

    def __init__(self, cfg: dict, confirm=None, on_status=None):
        proveedor = str(cfg.get("compat_proveedor", "gemini") or "gemini").lower()
        url, nombre_clave, modelo = PROVEEDORES.get(proveedor, PROVEEDORES["propio"])
        self.proveedor = proveedor
        self.host = (str(cfg.get("compat_url", "")).strip() or url).rstrip("/")
        self.modelo = str(cfg.get("compat_modelo", "")).strip() or modelo
        self.clave = store.get_key(nombre_clave) if nombre_clave else ""
        super().__init__(cfg, confirm=confirm, on_status=on_status)

    def comprobar(self) -> tuple[bool, str]:
        """Se llama en el constructor: sin esto el error aparece recien al hablar."""
        if not self.host:
            return False, ("Falta la URL del servicio. Panel > Cuentas, o elegi un "
                           "proveedor conocido en vez de 'propio'.")
        if not self.modelo:
            return False, "Falta el nombre del modelo. Panel > Cuentas."
        # Los servicios locales no piden clave; los de la nube si.
        if not self.clave and not self.host.startswith("http://localhost"):
            return False, (f"Falta la clave de {self.proveedor}. Cargala en "
                           f"Panel > Cuentas.")
        return True, "ok"

    def _pedir(self, mensajes: list[dict]) -> dict:
        """Una vuelta del chat. Devuelve el mensaje del asistente."""
        cabeceras = {"Content-Type": "application/json"}
        if self.clave:
            cabeceras["Authorization"] = f"Bearer {self.clave}"
        r = requests.post(
            f"{self.host}/chat/completions",
            headers=cabeceras,
            json={
                "model": self.modelo,
                "messages": mensajes,
                "tools": self._tools(),
                "max_tokens": int(self.cfg.get("max_tokens", 8000)),
                "temperature": 0.4,
            },
            timeout=300,
        )
        if r.status_code >= 400:
            # El cuerpo dice el motivo real (cuota, modelo inexistente, clave
            # mala). Sin esto el usuario ve "400 Bad Request" y no sabe cual.
            raise requests.RequestException(f"{r.status_code}: {r.text[:200]}")
        opciones = r.json().get("choices") or [{}]
        return opciones[0].get("message", {}) or {}

    def ask(self, text: str) -> str:
        store.log_turn("user", text)
        ahora = time.time()
        self.historial = store.trim_history(
            self.historial, self.cfg["context_turns"], self.cfg["context_minutes"], ahora
        )
        self.historial.append({"ts": ahora, "role": "user", "content": text})

        for _ in range(8):
            mensajes = [{"role": "system", "content": self._system()}]
            mensajes += [{k: v for k, v in m.items() if k != "ts"} for m in self.historial]

            self.on_status(f"Pensando ({self.proveedor})...")
            try:
                msg = self._pedir(mensajes)
            except requests.RequestException as exc:
                return f"{self.proveedor} fallo: {exc}"

            llamadas = msg.get("tool_calls") or []
            self.historial.append({"ts": time.time(), **msg})

            if not llamadas:
                respuesta = (msg.get("content") or "").strip() or "Listo."
                store.log_turn("assistant", respuesta)
                return respuesta

            for llamada in llamadas:
                fn = llamada.get("function", {})
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                texto, _ = self._ejecutar(fn.get("name", ""), args)
                # El protocolo pide devolver el id de la llamada: sin eso varios
                # servicios rechazan el turno siguiente entero.
                self.historial.append({
                    "ts": time.time(), "role": "tool",
                    "tool_call_id": llamada.get("id", ""),
                    "content": texto[:6000],
                })

        return f"Me perdi con {self.proveedor}. Proba de nuevo o cambia de motor."
