"""Quien decide que terminaste de hablar.

Hoy lo decide un cronometro: `despertar.CIERRE_S`, 0.7 segundos de silencio y
la frase se cierra. Es un numero fijo para dos situaciones que no se parecen en
nada --pensar en medio de una orden larga, y terminar de decirla-- asi que se
equivoca en las dos direcciones: te corta cuando estas pensando, y te hace
esperar cuando ya terminaste.

Lo que arregla eso es un modelo de fin de turno: escucha el pedazo y contesta
si la frase esta completa. El que se eligio es `smart-turn-v3`, de pipecat, y
paso todas las puertas del proyecto:

    licencia      BSD-2, se puede redistribuir
    tamano        8 MB en int8
    dependencia   onnxruntime, que YA viaja en los cinco paquetes porque es
                  lo que corre el detector de voz de la palabra clave
    costo         ~12 ms en CPU por consulta
    entrada       16 kHz, ventana de hasta 8 s -- que es exactamente lo que
                  `despertar.MAX_S` ya recorta
    idiomas       espanol entre los 23 que declara

**Este modulo esta listo y el modelo no esta bajado.** Son dos decisiones
distintas y la segunda es del usuario: bajar 8 MB de un tercero es algo que
elige quien usa el programa, con el boton del panel, no algo que aparece solo.
Mientras no este, `juez()` devuelve None y el cronometro sigue mandando: el
comportamiento de hoy, sin cambios.

Y hay una medicion que TODAVIA NO SE HIZO, escrita para que nadie la de por
hecha: **que el modelo reconozca el final de turno en espanol rioplatense**. La
lista de 23 idiomas es lo que declara el modelo, no lo que se comprobo aca. Eso
se mide con voz real --el banco de voz-- y hasta que se mida, `cierre_modo`
viene en `fijo` de fabrica.
"""

import os

from . import store

# De donde sale, y a donde va. El archivo se guarda en la carpeta de datos y no
# adentro del paquete: el paquete es de solo lectura una vez instalado, y
# ademas asi sobrevive a una actualizacion del programa.
REPO = "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main"
ARCHIVO = "smart-turn-v3.0-int8-dynamic.onnx"
FUENTE = f"{REPO}/{ARCHIVO}"

# Cuanto silencio hace falta antes de preguntarle al modelo. No es el cierre:
# es el piso para no consultarlo en medio de una palabra, donde cualquier
# respuesta seria ruido. El cierre sigue siendo `despertar.CIERRE_S`, que ahora
# funciona como TOPE: si el modelo no dice que termino, se espera lo de siempre.
SILENCIO_MIN_S = 0.2

# La ventana que se le manda, en segundos. El modelo se entreno con 8 y
# mandarle mas no lo mejora: lo que decide el final de una frase esta al final.
VENTANA_S = 8.0

_sesion = None
_entrada = ""


def ruta() -> str:
    """Donde tiene que estar el archivo."""
    return os.path.join(store.BASE, "modelos", ARCHIVO)


def disponible() -> bool:
    """Si el modelo esta bajado. No lo carga."""
    return os.path.exists(ruta())


def estado() -> str:
    """Una linea para el panel: si esta, y si no, que hacer."""
    if not disponible():
        return (f"No esta bajado. Son 8 MB, licencia BSD-2, y corre sobre el "
                f"onnxruntime que ya viaja con el programa.\n{FUENTE}")
    tam = os.path.getsize(ruta()) / (1 << 20)
    return f"Listo: {tam:.1f} MB en {ruta()}"


def descargar(progreso=None) -> str:
    """Baja el modelo. Solo se llama desde el boton del panel.

    Nunca se llama sola, ni al abrir, ni al primer uso. Bajar 8 MB de un
    tercero es una decision del usuario, y el momento en que aprieta el boton
    es el momento en que la toma. Un programa que se descarga cosas cuando le
    parece es exactamente lo que uno no quiere corriendo todo el dia.
    """
    import requests

    destino = ruta()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + ".parcial"
    try:
        with requests.get(FUENTE, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            bajado = 0
            with open(tmp, "wb") as f:
                for trozo in r.iter_content(chunk_size=1 << 16):
                    f.write(trozo)
                    bajado += len(trozo)
                    if progreso and total:
                        progreso(bajado / total)
    except Exception as exc:  # noqa: BLE001 - la red falla de mil formas
        # El parcial se borra: un archivo truncado carga y despues falla al
        # correr, con un error que no dice que el problema fue la descarga.
        if os.path.exists(tmp):
            os.remove(tmp)
        return f"No pude bajarlo: {type(exc).__name__}: {str(exc)[:150]}"
    os.replace(tmp, destino)
    _olvidar()
    return f"Bajado: {os.path.getsize(destino) / (1 << 20):.1f} MB."


def _olvidar() -> None:
    global _sesion, _entrada

    _sesion, _entrada = None, ""


def _cargar():
    """La sesion de onnx, o None si no se puede.

    El nombre del tensor de entrada se PREGUNTA, no se escribe: este modulo se
    escribio sin el archivo a mano --bajarlo es del usuario-- asi que hardcodear
    un nombre seria adivinarlo. Preguntarselo a la sesion es igual de corto y no
    puede estar mal.
    """
    global _sesion, _entrada

    if _sesion is not None:
        return _sesion
    if not disponible():
        return None
    try:
        import onnxruntime as ort

        opciones = ort.SessionOptions()
        # Un hilo: corre al lado de la escucha, que ya tiene el suyo, y esto es
        # una consulta de 12 ms. Dejarle todos los cores le saca tiempo a lo
        # que de verdad lo necesita.
        opciones.intra_op_num_threads = 1
        _sesion = ort.InferenceSession(ruta(), opciones,
                                       providers=["CPUExecutionProvider"])
        _entrada = _sesion.get_inputs()[0].name
    except Exception as exc:  # noqa: BLE001
        # Un detector de fin de turno que no carga NO puede dejar sorda a Eve:
        # se anota y se sigue con el cronometro, que es lo que habia antes.
        store.log_action("voz", "turno", f"no pude cargar el modelo: {exc}")
        _sesion, _entrada = None, ""
        return None
    return _sesion


def completo(audio) -> float | None:
    """Que tan probable es que la frase haya terminado, o None si no se sabe.

    None y no 0.0 a proposito: "no tengo opinion" y "seguro que sigue hablando"
    llevan a decisiones opuestas, y confundirlas haria que la falta del modelo
    se comporte como un modelo que siempre dice que no.
    """
    import numpy as np

    sesion = _cargar()
    if sesion is None:
        return None
    plano = np.asarray(audio, dtype="float32").flatten()
    if not plano.size:
        return None
    # Los ultimos 8 segundos: lo que decide el final de una frase esta al final.
    tope = int(VENTANA_S * 16000)
    if plano.size > tope:
        plano = plano[-tope:]
    try:
        salida = sesion.run(None, {_entrada: plano[None, :]})
    except Exception as exc:  # noqa: BLE001 - la forma del tensor puede no ser esta
        store.log_action("voz", "turno", f"el modelo rechazo la entrada: {exc}")
        _olvidar()
        return None
    return _probabilidad(salida)


def _probabilidad(salida) -> float | None:
    """El numero que sale del modelo, sea cual sea la forma en que lo entregue.

    Se acepta un escalar, un vector de uno, o un par [sigue, termino]. No se
    fija una forma porque este modulo se escribio sin el archivo delante, y
    equivocarse ahi daria un booleano invertido --el peor de los errores
    posibles aca: cortaria justo cuando estas hablando--.

    Si no se entiende lo que devolvio, devuelve None y manda el cronometro.
    """
    import numpy as np

    try:
        v = np.asarray(salida[0], dtype="float32").flatten()
    except Exception:  # noqa: BLE001
        return None
    if v.size == 1:
        return float(v[0])
    if v.size == 2:
        # Dos salidas es un softmax [sigue, termino]; la segunda es la que
        # importa. Si viniera al reves, el numero seria consistentemente el
        # complementario y se ve en la primera prueba con voz.
        return float(v[1])
    return None


def juez(cfg: dict):
    """La funcion que `despertar.Recortador` le pregunta, o None.

    None significa "no hay juez": el `Recortador` se queda con el cronometro de
    siempre, que es el comportamiento de fabrica.
    """
    if str(cfg.get("cierre_modo", "fijo")) != "modelo":
        return None
    if not disponible():
        return None
    umbral = _umbral(cfg)

    def decidir(audio) -> bool | None:
        p = completo(audio)
        return None if p is None else p >= umbral

    return decidir


def _umbral(cfg: dict) -> float:
    try:
        u = float(cfg.get("cierre_umbral", 0.6))
    except (TypeError, ValueError):
        return 0.6
    return min(0.99, max(0.01, u))
