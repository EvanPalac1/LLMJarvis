"""El system prompt, armado en un solo lugar.

Estaba en tres `.format()` iguales -- `brain._request()`, `cc_engine._build_cmd()`
y `ollama_engine._system()` -- con la misma lista de ocho piezas repetida. Tres
copias de la misma decision es tres lugares donde olvidarse de una, y sobre todo
tres lugares donde habria que medir el costo en tokens.

Dos plantillas, no una: el motor de Claude Code maneja los directorios permitidos
con `--add-dir`, asi que su version no lleva la linea de rutas. Todo lo demas lo
comparten.

`partes()` es la razon principal de que este modulo exista: devuelve cuanto pesa
cada seccion, que es lo que necesita el medidor de contexto. Sin esto habria que
escribirlo tres veces.
"""

from . import apps, integrations, store

# Motores que hablan por API o por Ollama: ven el shell y las rutas permitidas.
SYSTEM = """Sos {name}, el asistente de voz de este usuario en Windows 11. Idioma: {lang}.
Rutas permitidas: {workdirs} (fuera de ahi el sistema pide confirmacion; no lo evadas).

{brief}

## Catalogo de programas

{catalog_header} La voz deforma los nombres en ingles: elegi la entrada mas parecida a
lo que se escucho, no exijas coincidencia literal. Si no esta, usa Get-StartApps.

{catalog}

{integrations}

{tono}"""

# Claude Code: sin la linea de rutas, que las recibe por `--add-dir`.
PERSONA = """Sos {name}, un asistente de voz. El usuario te habla por microfono y tu
respuesta final se lee en voz alta con un sintetizador. Idioma: {lang}.

{brief}

## Catalogo de programas

{catalog_header} La voz deforma los nombres en ingles: elegi la entrada mas parecida a
lo que se escucho, no exijas coincidencia literal. Si no esta, usa Get-StartApps.

{catalog}

{integrations}

{tono}"""


def _usados(cfg: dict):
    """Los programas que aparecen en el log, si el catalogo va recortado.

    Se calcula una vez por proceso: recorre el log de acciones y es lo mismo
    para todas las llamadas de una sesion. Cualquier problema devuelve None, que
    significa "manda el catalogo entero": un grafo roto no puede dejar a Eve sin
    saber abrir nada.
    """
    global _CACHE_USADOS
    if str(cfg.get("catalogo_modo", "usados")) != "usados":
        return None
    if _CACHE_USADOS is None:
        try:
            from . import grafo

            datos = apps.load()
            _CACHE_USADOS = grafo.programas_usados(
                list({**datos["games"], **datos["apps"]}))
        except Exception:  # noqa: BLE001 - sin log, catalogo completo
            _CACHE_USADOS = []
    return _CACHE_USADOS or None


def olvidar_usados() -> None:
    """Vuelve a mirar el log. Lo llama el listener cuando se rearma."""
    global _CACHE_USADOS
    _CACHE_USADOS = None


_CACHE_USADOS = None


def piezas(cfg: dict) -> dict:
    """Lo que rellena cualquiera de las dos plantillas."""
    return {
        "name": cfg["assistant_name"],
        "lang": "espanol" if cfg["language"] == "es" else cfg["language"],
        "workdirs": ", ".join(cfg["workdirs"]),
        "brief": store.load_brief(),
        "catalog": apps.catalog(_usados(cfg)),
        "catalog_header": apps.catalog_header(bool(_usados(cfg))),
        "integrations": integrations.prompt_section(),
        "tono": store.bloque_tono(cfg),
    }


def construir(cfg: dict, plantilla: str = "") -> str:
    """El system prompt entero. `plantilla` vacia = la de API/Ollama."""
    # `format` ignora las claves que la plantilla no usa, asi que PERSONA puede
    # no tener {workdirs} sin que haya que armarle un diccionario aparte.
    return (plantilla or SYSTEM).format(**piezas(cfg))


def partes(cfg: dict, plantilla: str = "") -> dict[str, int]:
    """Cuantos caracteres aporta cada seccion. Es lo que dibuja el medidor.

    La suma da exactamente el largo de `construir()` con la misma config: el
    andamiaje es la plantilla con los huecos vaciados.
    """
    plantilla = plantilla or SYSTEM
    valores = piezas(cfg)
    andamiaje = plantilla
    cuenta = {}
    for clave, valor in valores.items():
        hueco = "{" + clave + "}"
        if hueco in plantilla:
            cuenta[clave] = len(str(valor))
            andamiaje = andamiaje.replace(hueco, "")
    cuenta["andamiaje"] = len(andamiaje)
    return cuenta
