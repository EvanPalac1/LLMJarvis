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
    # El alias `-latest` y no un numero de version: Google va sacando modelos
    # concretos de circulacion y una cuenta nueva se come un 404 diciendo "this
    # model is no longer available to new users". El alias siempre apunta a uno
    # vigente.
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "gemini", "gemini-flash-latest"),
    "openai": ("https://api.openai.com/v1", "openai", "gpt-5-mini"),
    "groq": ("https://api.groq.com/openai/v1", "groq", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek", "deepseek-chat"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter",
                   "deepseek/deepseek-chat-v3.1:free"),
    "xai": ("https://api.x.ai/v1", "xai", "grok-4-fast"),
    # Servidor local: no necesita clave y no sale nada de la maquina.
    "lmstudio": ("http://localhost:1234/v1", "", "local"),
    # OmniRoute es una pasarela: corre en TU maquina y por detras habla con
    # decenas de proveedores. Emite su propia clave, pero NO la exige: su
    # `REQUIRE_API_KEY` viene en `false`. El modelo viene vacio porque enruta a
    # cientos y elegir uno por vos seria adivinar; el boton de buscar modelos
    # se los pregunta.
    "omniroute": ("http://localhost:20128/v1", "omniroute", ""),
    # "propio" usa lo que el usuario haya escrito en compat_url / compat_modelo.
    "propio": ("", "compat", ""),
}

GRATIS = ("gemini", "groq", "openrouter", "lmstudio")

# Codigos que se arreglan solos: el servicio esta saturado o nos frena un rato.
# Sin reintentar, un 503 pasajero de Gemini contesta "gemini fallo: 503" y ahi
# se termina la orden que el usuario acaba de decir en voz alta.
REINTENTABLES = (429, 500, 502, 503, 504)
# Mas que esto no se espera: el usuario ya hablo y esta parado ahi. Un 429 por
# tope de tokens por minuto pide 60s, y aguantar 60s callado es peor que decir
# que no se pudo.
ESPERA_MAX = 8.0
# Y un techo para la vuelta entera. Reintentar sirve cuando el servicio falla
# RAPIDO, que es el 503 tipico. Medido contra Gemini un dia saturado: cada
# pedido tardaba ~50s en fallar y los tres intentos dieron una respuesta
# correcta a los 159 segundos. Para un asistente de voz eso no es una respuesta,
# es un cuelgue: mejor avisar y que lo vuelvan a pedir.
LIMITE_TOTAL = 45.0

# Lo que devuelve el servicio cuando falla es JSON, y esto se lee en voz alta:
# "gemini fallo: 429: [{ "error": { "code": 429, "message": ..." sintetizado tal
# cual. Una frase por codigo, en el idioma en el que Eve habla.
MOTIVOS = {
    401: "la clave no sirve o esta vencida",
    403: "la clave no tiene permiso para este modelo",
    404: "ese modelo no existe para esta cuenta",
    413: "el pedido es mas grande de lo que acepta el plan",
    429: "te frenaron por cuota, proba mas tarde",
    500: "el servicio tuvo un error interno",
    503: "el servicio esta saturado",
}


def _motivo(r) -> str:  # noqa: ANN001
    """Por que fallo, en una frase que se pueda escuchar."""
    corto = MOTIVOS.get(r.status_code)
    if corto:
        return corto
    # Codigo que no esta en la tabla: al menos la frase del servicio y no el
    # JSON entero con llaves y corchetes.
    try:
        error = r.json().get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:200]
    except (ValueError, AttributeError):
        pass
    return f"error {r.status_code}"


class CompatEve(OllamaEve):
    """Misma interfaz que los otros motores: .ask(texto) -> respuesta."""

    def _destino(self, cfg: dict) -> None:
        proveedor = str(cfg.get("compat_proveedor", "gemini") or "gemini").lower()
        url, nombre_clave, modelo = PROVEEDORES.get(proveedor, PROVEEDORES["propio"])
        self.proveedor = proveedor
        # El nombre del proveedor y no "compat": el medidor tiene que poder
        # decir si el gasto fue de Gemini o de Groq.
        self.motor = proveedor
        self.host = (str(cfg.get("compat_url", "")).strip() or url).rstrip("/")
        self.modelo = str(cfg.get("compat_modelo", "")).strip() or modelo
        self.clave = store.get_key(nombre_clave) if nombre_clave else ""

    def _cabeceras(self) -> dict:
        """Las cabeceras de cada pedido, con lo que cada proveedor espera.

        OpenRouter usa `HTTP-Referer` y `X-Title` para saber que aplicacion
        habla: son opcionales, pero sin ellas los pedidos entran como anonimos
        y sus modelos gratuitos limitan mas fuerte a quien no se identifica.
        Cuestan dos lineas y no mandan nada del usuario --el nombre del
        programa y su repositorio, que ya son publicos.
        """
        cabeceras = {"Content-Type": "application/json"}
        if self.clave:
            cabeceras["Authorization"] = f"Bearer {self.clave}"
        if self.proveedor == "openrouter":
            cabeceras["HTTP-Referer"] = "https://github.com/EvanPalac1/LLMJarvis"
            cabeceras["X-Title"] = "LLMJarvis"
        return cabeceras

    def modelos(self, timeout: int = 15) -> list:
        """Los modelos que el servicio dice tener, preguntandoselos.

        Existe porque el modelo era un campo de texto libre, y eso es el mismo
        problema que ya se arreglo con las claves de config: OpenRouter publica
        cientos de modelos y LM Studio sirve el que hayas cargado, asi que
        habia que saber el identificador exacto, escribirlo bien, y descubrir
        el error recien al hablarle.

        `GET /v1/models` es parte del protocolo de OpenAI, asi que lo contestan
        los tres: OpenRouter, LM Studio y cualquier servidor propio.
        """
        if not self.host:
            return []
        r = requests.get(f"{self.host}/models", headers=self._cabeceras(),
                         timeout=timeout)
        r.raise_for_status()
        datos = r.json()
        filas = datos.get("data") if isinstance(datos, dict) else datos
        if not isinstance(filas, list):
            return []
        nombres = [str(f.get("id") or "") for f in filas if isinstance(f, dict)]
        return sorted(n for n in nombres if n)

    def comprobar(self) -> tuple[bool, str]:
        """Se llama en el constructor: sin esto el error aparece recien al hablar."""
        if not self.host:
            return False, ("Falta la URL del servicio. Panel > Cuentas, o elegi un "
                           "proveedor conocido en vez de 'propio'.")
        if not self.modelo:
            return False, "Falta el nombre del modelo. Panel > Cuentas."
        # Lo que corre en tu maquina no pide clave; lo de la nube si.
        #
        # Esto estuvo escrito al reves durante unas horas. Se cambio a "lo
        # decide el proveedor" para que OmniRoute exigiera clave, sobre la
        # creencia de que su panel emitia una obligatoria. Medido despues
        # contra el servicio corriendo: `REQUIRE_API_KEY` viene en `false`, y
        # `/v1/models` y `/v1/chat/completions` contestan sin ninguna clave
        # --119 modelos y una respuesta completa de qwen3-0.6b a traves de la
        # pasarela--. O sea que la version "arreglada" rechazaba la instalacion
        # por defecto, que es la que casi todos van a tener.
        #
        # La clave se sigue MANDANDO si esta cargada, para quien encienda ese
        # ajuste; lo que no se hace es exigirla. Un 401 conjeturado no vale una
        # negativa segura.
        if not self.clave and not self.host.startswith("http://localhost"):
            return False, (f"Falta la clave de {self.proveedor}. Cargala en "
                           f"Panel > Cuentas.")
        return True, "ok"

    def _pedir(self, mensajes: list[dict]) -> dict:
        """Una vuelta del chat. Devuelve el mensaje del asistente."""
        cabeceras = dict(self._cabeceras())
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "tools": self._tools(),
            "max_tokens": int(self.cfg.get("max_tokens", 8000)),
            "temperature": 0.4,
        }
        arranque = time.time()
        for intento in range(3):
            r = requests.post(
                f"{self.host}/chat/completions", headers=cabeceras, json=cuerpo, timeout=300
            )
            if r.status_code not in REINTENTABLES or intento == 2:
                break
            # El servicio suele decir cuanto esperar; si no, se sube de a poco.
            espera = float(r.headers.get("Retry-After", 0) or 0) or 1.5 * (intento + 1)
            if espera > ESPERA_MAX or time.time() - arranque + espera > LIMITE_TOTAL:
                break
            self.on_status(f"{self.proveedor} saturado, reintento en {espera:.0f}s...")
            time.sleep(espera)
        if r.status_code >= 400:
            # El detalle completo va a la consola, que es donde sirve para
            # arreglarlo; en voz alta va la frase corta.
            print(f"[{self.proveedor}] {r.status_code}: {r.text[:400]}")
            raise requests.RequestException(_motivo(r))
        cuerpo_resp = r.json()
        u = cuerpo_resp.get("usage") or {}
        entrada = int(u.get("prompt_tokens", 0) or 0)
        salida = int(u.get("completion_tokens", 0) or 0)
        # Medido contra Gemini: devuelve prompt_tokens 6, completion_tokens 0 y
        # total_tokens 13. Los tokens de razonamiento se cobran pero quedan
        # fuera de completion_tokens, asi que sin esto el medidor subestima el
        # turno a menos de la mitad.
        total = int(u.get("total_tokens", 0) or 0)
        if total > entrada + salida:
            salida = total - entrada
        store.sumar_uso(self.uso, entrada, salida,
                        (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        opciones = cuerpo_resp.get("choices") or [{}]
        return opciones[0].get("message", {}) or {}

    def ask(self, text: str) -> str:
        store.log_turn("user", text, self.motor)
        ahora = time.time()
        self.historial = store.trim_history(
            self.historial, self.cfg["context_turns"], self.cfg["context_minutes"], ahora
        )
        self.historial.append({"ts": ahora, "role": "user", "content": text})
        self.uso = {}

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
                store.log_turn("assistant", respuesta, self.motor, self.uso)
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
