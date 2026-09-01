"""Microfono -> texto (STT) y texto -> parlante (TTS).

Local por defecto: faster-whisper para STT (el reconocimiento nativo de Windows
es mediocre en espanol) y SAPI para TTS. Los proveedores en la nube quedan
disponibles si el usuario carga sus propias claves en el panel.
"""

import io
import datetime
import os
import queue
import tempfile
import wave

import numpy as np
import sounddevice as sd

from . import plataforma, store

SAMPLE_RATE = 16000
_whisper = None
_whisper_para = None  # (modelo, device) con el que se construyo el de arriba

# Los modelos ya cargados, por (modelo, device, computo). DOS ranuras y no una.
#
# Con una sola, la palabra clave y la transcripcion se pisaban todo el tiempo:
# la puerta pide `tiny` y transcribir pide `small`, asi que cada despertar
# descargaba uno y cargaba el otro, y al contestar hacia el viaje de vuelta.
# En CPU son unos segundos por vuelta; en CUDA, ademas, mueve el modelo a la
# placa cada vez. Dos es exactamente lo que hace falta: no hay un tercer modelo
# en juego, y guardar todos los que se hayan pedido seria dejar memoria de video
# tomada por uno que no se va a volver a usar.
_CACHE_WHISPER: dict = {}
CACHE_WHISPER_TOPE = 2


def _traer_whisper(clave: tuple):
    """El modelo pedido, cargandolo solo si todavia no esta."""
    modelo = _CACHE_WHISPER.get(clave)
    if modelo is None:
        modelo = _abrir_whisper(*clave)
        _CACHE_WHISPER[clave] = modelo
        # Se va el mas viejo. Los dict de Python conservan el orden de
        # insercion, asi que el primero es el que hace mas que no se pide.
        while len(_CACHE_WHISPER) > CACHE_WHISPER_TOPE:
            del _CACHE_WHISPER[next(iter(_CACHE_WHISPER))]
    return modelo


class MicBusyError(RuntimeError):
    """Otro programa tiene el microfono en modo exclusivo (Discord, OBS, Zoom)."""


class Recorder:
    """Push-to-talk: start() al presionar, stop() al soltar."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._stream = None
        # Volumen del ultimo bloque, 0..1. Lo lee el overlay para dibujar la
        # onda: es el mismo audio que se va a transcribir, no una animacion.
        self.nivel = 0.0

    def start(self) -> None:
        if self._stream is not None:
            return
        self._q = queue.Queue()

        def cb(indata, _frames, _t, status):  # noqa: ANN001
            if status:
                pass  # xruns: preferimos audio con glitches a perder la frase
            # RMS por raiz cuadrada para que la voz normal ocupe buena parte de
            # la barra: el RMS crudo de la voz vive en valores muy chicos.
            self.nivel = min(1.0, float(np.sqrt(np.abs(indata).mean())) * 2.2)
            self._q.put(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=cb
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._stream = None
            raise MicBusyError(str(exc)) from exc

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype="float32")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self.nivel = 0.0
        chunks = []
        while not self._q.empty():
            chunks.append(self._q.get())
        if not chunks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(chunks).flatten()


def _to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _computo(cfg: dict) -> str:
    """Tipo de computo a usar. 'auto' elige el mejor para el dispositivo.

    Estaba fijo en "int8" sin mirar el device, asi que poner la GPU en el panel
    la usaba con el tipo pensado para CPU. En Turing el que corresponde es
    int8_float16; en CPU no existe y hay que quedarse en int8.
    """
    elegido = str(cfg.get("stt_computo", "auto") or "auto").strip()
    if elegido != "auto":
        return elegido
    return "int8_float16" if str(cfg.get("stt_device", "cpu")) == "cuda" else "int8"


_dlls_cuda = False


def _sitios_python() -> list[str]:
    """Los site-packages del Python del SISTEMA, no del que viaja en el .exe.

    Congelado, `site.getsitepackages()` devuelve el interprete empaquetado, donde
    los wheels de NVIDIA no estan ni van a estar. Por eso activar la GPU en la
    version instalada no hacia nada aunque las librerias estuvieran bajadas en la
    maquina. Y estan: son ~2 GB, asi que encontrarlas es mucho mejor negocio que
    volver a bajarlas.
    """
    import json
    import shutil
    import subprocess

    for nombre in ("python", "python3", "py"):
        ruta = shutil.which(nombre)
        # El stub de la Microsoft Store no es un Python: al ejecutarlo abre la
        # tienda. Con esto no le damos la oportunidad.
        if not ruta or "WindowsApps" in ruta:
            continue
        try:
            salida = subprocess.run(
                [ruta, "-c", "import json,site;print(json.dumps(site.getsitepackages()))"],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            rutas = json.loads(salida.stdout.strip())
            if rutas:
                return [str(r) for r in rutas]
        except Exception:  # noqa: BLE001 - cualquier python roto se saltea
            continue
    return []


def _carpetas_cuda() -> list[str]:
    """Todas las carpetas donde pueden estar las DLL de NVIDIA, sin repetir."""
    import glob
    import site

    bases = list(site.getsitepackages())
    try:
        bases.append(site.getusersitepackages())
    except AttributeError:
        pass

    def nvidia(donde: list[str]) -> list[str]:
        return [d for b in donde for d in glob.glob(os.path.join(b, "nvidia", "*", "bin"))]

    carpetas = nvidia(bases)
    # Solo si las propias no dieron nada: correr desde el codigo fuente ya las
    # encuentra y no vale la pena pagar un subproceso en cada arranque.
    if not carpetas:
        carpetas = nvidia(_sitios_python())

    propias = os.path.join(store.BASE, "cuda")
    sueltas = glob.glob(os.path.join(propias, "**", "*.dll"), recursive=True)
    carpetas += sorted({os.path.dirname(x) for x in sueltas})
    return list(dict.fromkeys(carpetas))


def _preparar_cuda() -> None:
    """Deja las DLL de NVIDIA donde ctranslate2 las pueda encontrar.

    Los wheels `nvidia-*-cu12` las instalan dentro de site-packages, que no esta
    en el PATH. `os.add_dll_directory` NO alcanza: ctranslate2 es una extension
    compilada y resuelve sus dependencias con LoadLibrary, que mira el PATH del
    proceso. Medido: con las libs instaladas y sin esto, seguia tirando
    "Library cublas64_12.dll is not found" igual que si no estuvieran.

    Tiene que correr ANTES de importar faster_whisper.
    """
    global _dlls_cuda
    if _dlls_cuda:
        return
    _dlls_cuda = True
    carpetas = _carpetas_cuda()
    if not carpetas:
        return
    os.environ["PATH"] = os.pathsep.join(carpetas) + os.pathsep + os.environ.get("PATH", "")
    for carpeta in carpetas:
        try:
            os.add_dll_directory(carpeta)
        except (OSError, AttributeError):
            pass


def _abrir_whisper(modelo: str, device: str, computo: str):
    """El modelo, cayendo a CPU si la GPU no esta lista.

    Las librerias de CUDA no vienen con el programa: son casi un giga y la
    mayoria de las maquinas no tiene NVIDIA. Si el usuario pidio GPU y falta
    alguna DLL, faster-whisper tira RuntimeError recien al transcribir la
    primera frase; sin esta red, la primera cosa que le decis a Eve se pierde
    con una excepcion en vez de contestarte mas lento.
    """
    if device != "cpu":
        _preparar_cuda()
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(modelo, device=device, compute_type=computo)
    except Exception as exc:  # noqa: BLE001 - vale cualquier falla del backend
        if device == "cpu":
            raise
        print(f"[stt] la GPU no esta disponible ({str(exc)[:80]}); sigo en CPU")
        return WhisperModel(modelo, device="cpu", compute_type="int8")


def probar_gpu(cfg: dict) -> str:
    """Dice si la GPU va a servir, para no enterarse recien en la primera orden.

    Transcribe de verdad un segundo de silencio. El error de CUDA no salta al
    construir el modelo sino al correr el encoder por primera vez: una prueba
    que solo cargue el modelo diria que esta todo bien y despues fallaria con la
    primera cosa que le digas.
    """
    import time as reloj

    carpetas = _carpetas_cuda()
    if not carpetas:
        return (
            "No encontre las librerias de NVIDIA.\n\n"
            "Instalalas con:\n"
            "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n\n"
            "o copia sus DLL adentro de:\n"
            f"    {os.path.join(store.BASE, 'cuda')}"
        )
    _preparar_cuda()
    computo = _computo({**cfg, "stt_device": "cuda"})
    from faster_whisper import WhisperModel

    try:
        desde = reloj.perf_counter()
        modelo = WhisperModel(cfg["stt_model"], device="cuda", compute_type=computo)
        segmentos, _ = modelo.transcribe(
            np.zeros(SAMPLE_RATE, dtype="float32"), language=cfg["language"], beam_size=1
        )
        list(segmentos)
    except Exception as exc:  # noqa: BLE001 - vale cualquier falla del backend
        return (
            f"La GPU todavia no sirve:\n{str(exc)[:240]}\n\n"
            "Busque las librerias en:\n    " + "\n    ".join(carpetas[:4]) + "\n\n"
            "Eve sigue andando en CPU mientras tanto."
        )
    return (
        f"La GPU anda. Modelo {cfg['stt_model']} en {computo}, "
        f"cargado y probado en {reloj.perf_counter() - desde:.1f}s.\n\n"
        f"Librerias tomadas de:\n    {carpetas[0]}"
    )


_parakeet = None
_parakeet_para = None


def _abrir_parakeet(cuantizacion: str):
    """Carga el modelo de NVIDIA, bajandolo la primera vez.

    Entro porque gano medido sobre el mismo banco de 24 clips que whisper, y con
    la misma metrica --no porque sea mas nuevo:

        sistema                    TOTAL   RTF   disco
        whisper small en gpu       10.9%  0.27   464 MB
        whisper small en cpu       10.9%  1.38   464 MB
        whisper medium en gpu       5.4%  0.61   1.5 GB
        parakeet v3 int8 en CPU     7.1%  0.19   639 MB

    Lo importante no es el punto y medio de WER: es que ese 0.19 es **en CPU**.
    Whisper small tarda siete veces mas en la misma maquina sin GPU, y la mayoria
    de las instalaciones no tienen CUDA configurado. Aca un reconocedor mejor deja
    de costar una placa de video.

    Donde pierde: nombres propios (30.4% contra 21.7% de whisper small con int8),
    que es justo el grupo que decide si Eve abre el programa correcto, y no acepta
    un sesgo de vocabulario como el `initial_prompt` de whisper. Por eso es una
    opcion y no el default.
    """
    import onnx_asr

    return onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3",
                               quantization=cuantizacion or None)


def transcribe(audio: np.ndarray, cfg: dict) -> str:
    if audio.size < SAMPLE_RATE // 4:  # menos de 250 ms: fue un toque, no una frase
        return ""

    if cfg.get("stt_provider") == "parakeet":
        global _parakeet, _parakeet_para
        quiere = str(cfg.get("parakeet_cuantizacion", "int8"))
        if _parakeet is None or _parakeet_para != quiere:
            _parakeet = _abrir_parakeet(quiere)
            _parakeet_para = quiere
        # Sin VAD y sin sesgo de vocabulario: el modelo no los acepta, y no le
        # hacen falta --sobre el grupo susurrado, donde whisper con el detector
        # puesto devolvia vacio, este da 0.0% con el audio crudo.
        return str(_parakeet.recognize(audio, sample_rate=SAMPLE_RATE,
                                       language=cfg.get("language", "es"))).strip()

    if cfg["stt_provider"] == "openai":
        import requests

        key = store.get_key("openai")
        if not key:
            raise RuntimeError("STT en OpenAI seleccionado pero falta la OPENAI_API_KEY.")
        r = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": ("audio.wav", _to_wav_bytes(audio), "audio/wav")},
            data={"model": "whisper-1", "language": cfg["language"]},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("text", "").strip()

    global _whisper, _whisper_para
    # Cargar el modelo cuesta segundos, asi que se cachea; pero atado a con que
    # se cargo. Sin esto, cambiar el modelo o el device en el panel no hacia
    # nada: el listener se rearmaba y seguia usando el que ya estaba en memoria.
    quiere = (cfg["stt_model"], cfg["stt_device"], _computo(cfg))
    _whisper = _traer_whisper(quiere)
    _whisper_para = quiere
    # Sin initial_prompt, decodificar en espanol destroza los nombres propios en
    # ingles. Pasarle los programas instalados es lo que hace que "abre rainbow
    # six siege" no salga como "Haberé en Vox XC".
    from . import apps

    try:
        return _decodificar(_whisper, audio, cfg)
    except RuntimeError as exc:
        # La GPU no falla al construir el modelo sino al correr el primer
        # encoder: ahi recien se cargan cuBLAS y cuDNN. Capturarlo solo en el
        # constructor dejaba pasar el error hasta aca y se perdia la primera
        # frase que le decias, que es exactamente lo que la caida a CPU tenia
        # que evitar. Se reintenta una vez, ya en CPU.
        if cfg.get("stt_device") == "cpu":
            raise
        print(f"[stt] la GPU fallo transcribiendo ({str(exc)[:80]}); paso a CPU")
        # Por la cache y no directo: el que fallo en GPU se queda ahi ocupando
        # una ranura y volveria a elegirse en la proxima frase.
        _CACHE_WHISPER.pop((cfg["stt_model"], cfg["stt_device"], _computo(cfg)), None)
        _whisper_para = (cfg["stt_model"], "cpu", "int8")
        _whisper = _traer_whisper(_whisper_para)
        return _decodificar(_whisper, audio, cfg)


# Sensibilidad: los tres modos, y de donde salen los numeros.
#
# Barrido sobre el banco de 24 clips, modelo `small`, umbral del detector x aire
# en milisegundos. El WER total del ajuste que venia de fabrica (0.5/400) era
# 12.0%:
#
#   umbral/aire    lejos  limpio  propios  rapido   ruido  susurro   TOTAL
#   0.5/400        15.2%    3.2%    26.1%   16.7%   18.8%     0.0%   12.0%
#   0.5/100        15.2%    3.2%    21.7%   22.2%   12.5%     0.0%   10.9%
#   0.85/250       15.2%    3.2%    26.1%   16.7%    0.0%     0.0%    8.7%
#   sin VAD        15.2%    3.2%    26.1%   22.2%   18.8%     0.0%   12.5%
#
# Dos cosas que salieron al reves de lo que dice la intuicion:
#
# 1. Para hablar bajo NO sirve un detector permisivo. Con umbral 0.35 el susurro
#    empeora a 26.7%, porque un detector flojo encuentra "voz" adentro del ruido,
#    devuelve algo en vez de vacio, y asi le tapa la puerta al reintento sin VAD
#    de mas abajo --que es lo que de verdad rescata un susurro, y lo deja en 0%.
# 2. El aire de 400 ms que trae la libreria es demasiado: recortarlo a 100 baja
#    el WER un punto entero y de paso acelera.
MODOS = {
    # nombre    umbral  aire_ms
    "normal":   (0.50, 100),   # 10.9% total, y el mejor en nombres propios
    "ruido":    (0.85, 250),   # el grupo con ruido de fondo pasa de 18.8% a 0.0%
    "bajo":     (0.50, 250),   # mas aire para no comerse ataques suaves
}


# Vive en `store` para que los perfiles contextuales puedan usar el MISMO
# parser sin importar este modulo, que arrastra sounddevice. Dos parsers de
# horario serian dos comportamientos con la misma sintaxis.
_rango = store.rango_horario


def modo_horario(cfg: dict, ahora=None) -> str:
    """El modo que corresponde a esta hora, o "" si ninguna regla aplica.

    Formato: `00:00-06:00=bajo, 20:00-23:59=ruido`. Gana la primera que entra.
    """
    reglas = str(cfg.get("stt_horario", "")).strip()
    if not reglas:
        return ""
    ahora = ahora or datetime.datetime.now()
    for regla in reglas.split(","):
        if "=" not in regla:
            continue
        rango, modo = (x.strip() for x in regla.split("=", 1))
        try:
            if modo in MODOS and _rango(rango, ahora):
                return modo
        except (ValueError, IndexError):
            continue  # una regla mal escrita no puede dejar a Eve sorda
    return ""


def sensibilidad(cfg: dict, ahora=None) -> tuple[float, int, str]:
    """(umbral, aire_ms, de donde salio). El horario solo pisa al modo `auto`.

    Que `auto` sea el unico que el reloj puede pisar es a proposito: si elegiste
    "modo ruido" a mano, que a las 12 de la noche te lo cambie una regla que
    escribiste hace un mes es exactamente la sensacion de app poseida que el
    ajuste de autoridad existe para evitar.
    """
    elegido = str(cfg.get("stt_sensibilidad", "auto"))
    if elegido == "manual":
        return (_frac(cfg, "stt_vad_umbral", 0.5, 0.05, 0.95),
                _num(cfg, "stt_vad_aire_ms", 0, 2000), "manual")
    if elegido in MODOS:
        return (*MODOS[elegido], elegido)
    por_hora = modo_horario(cfg, ahora)
    if por_hora:
        return (*MODOS[por_hora], f"{por_hora} (por horario)")
    return (*MODOS["normal"], "normal")


# Debajo de esto no hay voz que rescatar: el reintento sin VAD solo agregaria
# una pasada del modelo sobre aire. Medido sobre el banco de voz, un susurro de
# verdad pica en -27 dBFS y un clip inservible en -39.
PISO_REINTENTO = 0.008  # ~ -42 dBFS de pico


def _decodificar(modelo, audio: np.ndarray, cfg: dict) -> str:
    from . import apps

    umbral, aire, _ = sensibilidad(cfg)

    def correr(con_vad: bool) -> str:
        segments, _ = modelo.transcribe(
            audio,
            language=cfg["language"],
            # Quien llama puede pisar el sesgo. La puerta de la palabra clave
            # lo usa: servirle el catalogo de 80 juegos a un modelo que solo
            # tiene que reconocer un nombre lo empuja a escribir cualquier cosa
            # menos ese nombre --medido, "Eve, abri Spotify" salia "Mb.Avris.phi.".
            initial_prompt=(cfg["stt_prompt"] if "stt_prompt" in cfg
                            else apps.vocabulary(cfg.get("stt_vocabulary", ""))),
            # Recortar los silencios acelera (medido: 1.19x -> 1.09x de tiempo
            # real) y no cambia el texto.
            vad_filter=con_vad,
            # El umbral del detector es LA perilla de sensibilidad: el 0.5 fijo
            # de la libreria es lo que se comia los susurros enteros.
            vad_parameters={"threshold": umbral, "speech_pad_ms": aire}
            if con_vad else None,
            # Medido sobre una orden tipica: beam 5 tarda 4.4s y beam 1 tarda
            # 3.5s, con el MISMO texto. La busqueda por haz sirve para dictado
            # largo; una orden de ocho palabras no cambia de resultado por
            # explorar cinco ramas.
            beam_size=int(_num(cfg, "stt_beam", 1, 5)),
            # Cada orden es independiente: arrastrar la anterior como contexto
            # solo agrega trabajo y le da al modelo una excusa para inventar
            # continuidad.
            condition_on_previous_text=False,
            # Por defecto la libreria prueba temperaturas 0, 0.2 ... 1.0 hasta
            # que el resultado le convence, y eso hace que la MISMA onda de un
            # texto distinto entre corridas. Para dictar esta bien. Para la
            # puerta de la palabra clave es fatal: despertaria al azar. Por eso
            # `despertar.escuchado` fija esta clave en 0 y nadie mas la usa.
            **({"temperature": cfg["stt_temperatura"]}
               if "stt_temperatura" in cfg else {}),
        )
        return " ".join(s.text for s in segments).strip()

    con_vad = bool(cfg.get("stt_vad", True))
    texto = correr(con_vad)
    # El VAD no "se come alguna palabra" dicha bajo: se come la frase entera. En
    # el banco se tragó 3 de 29 clips --los tres susurrados-- y el modelo los
    # transcribia perfecto con el detector apagado. Reintentar solo cuando no
    # salio nada no cuesta nada en el caso normal, y el turno ya estaba perdido.
    # No inventa texto sobre ruido: probado con silencio puro y con ruido blanco
    # a -30 y -20 dB, las tres veces devuelve vacio.
    if not texto and con_vad and float(np.abs(audio).max(initial=0.0)) > PISO_REINTENTO:
        texto = correr(False)
    return texto


def precargar_stt(cfg: dict) -> None:
    """Deja el modelo de voz cargado y listo, sin transcribir nada.

    Construirlo cuesta ~2.5s. Pagarlo mientras el usuario todavia no hablo es
    gratis; pagarlo en la primera orden es la diferencia entre parecer lento y
    no parecerlo. No se transcribe de prueba: cargar alcanza, y correr el modelo
    de verdad seria trabajo y CPU al pedo justo en el arranque.
    """
    global _whisper, _whisper_para, _parakeet, _parakeet_para
    if cfg.get("stt_provider") == "parakeet":
        quiere = str(cfg.get("parakeet_cuantizacion", "int8"))
        if _parakeet is None or _parakeet_para != quiere:
            _parakeet = _abrir_parakeet(quiere)
            _parakeet_para = quiere
        return
    if cfg.get("stt_provider") != "faster-whisper":
        return
    # La misma clave de tres partes que usa transcribe(): con dos, precargar
    # dejaba listo un modelo que transcribe descartaba por no coincidir, y se
    # pagaba la carga dos veces justo en la primera orden.
    quiere = (cfg["stt_model"], cfg["stt_device"], _computo(cfg))
    # Por la MISMA cache que usa transcribe(): precargar por afuera dejaba un
    # modelo cargado que la cache no conocia, y la primera orden lo cargaba de
    # nuevo --justo lo que precargar existe para evitar--.
    _whisper = _traer_whisper(quiere)
    _whisper_para = quiere


def _num(cfg: dict, clave: str, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(maximo, int(cfg.get(clave, minimo))))
    except (TypeError, ValueError):
        return minimo


def _frac(cfg: dict, clave: str, defecto: float, minimo: float, maximo: float) -> float:
    """Como `_num` pero sin redondear, y cayendo al defecto y no al minimo.

    El umbral del VAD vive entre 0 y 1: con int() todo valor util se aplasta a
    0. Y cayendo al minimo, un cfg incompleto --un test, una config vieja-- daria
    el detector mas permisivo que existe en vez del que eligio el usuario."""
    try:
        return max(minimo, min(maximo, float(cfg.get(clave, defecto))))
    except (TypeError, ValueError):
        return defecto


def hasta(texto: str, fraccion: float) -> str:
    """El texto revelado hasta esa fraccion de la reproduccion.

    Corta en palabra entera y reparte el tiempo segun el largo de cada una, que
    es una aproximacion decente a como se tarda en pronunciarlas. No hace falta
    nada mas fino: la duracion total la da el wav, asi que el final siempre cae
    donde tiene que caer.
    """
    palabras = texto.split()
    if not palabras:
        return ""
    fraccion = max(0.0, min(1.0, fraccion))
    largos = [len(p) + 1 for p in palabras]
    total = sum(largos)
    objetivo, acumulado, cuantas = total * fraccion, 0, 0
    for i, largo in enumerate(largos):
        acumulado += largo
        cuantas = i + 1
        if acumulado >= objetivo:
            break
    return " ".join(palabras[:cuantas])


# Hasta cuando NO hay que creerle al microfono, en reloj monotono. Lo mueve
# `speak` mientras habla, y lo lee la escucha continua.
#
# Sin esto Eve se oye a si misma: con la palabra clave prendida el microfono
# queda abierto mientras ella contesta, silero recorta su propia voz como una
# frase, y si la respuesta empieza con el nombre --"Eve esta lista"-- la puerta
# se abre sola. Se realimenta: cada respuesta puede disparar la siguiente.
_callar_hasta = 0.0

# Cuanto seguir desconfiando despues de que se apago el parlante. La frase que
# la escucha esta armando se cierra recien tras CIERRE_S de silencio (0.7s), y
# llega DESPUES de que speak volvio: sin esta cola, la ultima frase que dijo
# ella entra igual.
COLA_SORDA_S = 1.2


def hablando() -> bool:
    """Si el parlante esta sonando ahora, o acaba de apagarse."""
    import time as _t

    return _t.monotonic() < _callar_hasta


def _marcar_hablando(segundos: float = 0.0) -> None:
    global _callar_hasta
    import time as _t

    _callar_hasta = max(_callar_hasta, _t.monotonic() + segundos + COLA_SORDA_S)


def speak(text: str, cfg: dict, progreso=None) -> None:
    """Dice `text`. `progreso(nivel, revelado)` sigue el avance para el overlay."""
    if not text or not cfg.get("speak_replies", True):
        return
    # Antes de abrir la boca: mientras dure esto, lo que entre por el microfono
    # es ella misma. La marca se renueva al terminar, con la cola.
    _marcar_hablando(2.0)
    try:
        _hablar(text, cfg, progreso)
    finally:
        _marcar_hablando()


def _hablar(text: str, cfg: dict, progreso=None) -> None:
    """Lo que speak hacia antes de tener que avisar que esta hablando."""

    if cfg["tts_provider"] == "elevenlabs":
        _speak_elevenlabs(text, cfg)
        return

    if cfg["tts_provider"] == "piper":
        from . import voices

        clave = cfg.get("piper_voice") or (voices.instaladas() or [""])[0]
        if not clave:
            raise RuntimeError(
                "TTS en Piper pero no hay ninguna voz descargada. Panel > Voz."
            )
        avance = None
        if progreso:
            avance = lambda f, nivel: progreso(nivel, hasta(text, f))  # noqa: E731
        hablante = int(cfg.get("piper_hablante", 0) or 0)
        velocidad = float(cfg.get("piper_velocidad", 1.0) or 1.0)
        # Lo que Eve repite siempre ya esta generado en disco: se lee y suena.
        ruta = voices.frase_cacheada(text, clave, hablante, velocidad)
        if not ruta:
            ruta = voices.hablar(text, clave, hablante=hablante, velocidad=velocidad)
            voices.guardar_frase(text, clave, ruta, hablante, velocidad)
        voices.reproducir(ruta, avance, float(cfg.get("volumen", 1.0) or 1.0))
        return

    if not plataforma.WINDOWS:
        # pyttsx3 ni se instala fuera de Windows: sin esto el usuario que elija
        # sapi en Linux se come un ImportError pelado en vez de saber que hacer.
        raise RuntimeError(
            f"El TTS 'sapi' solo existe en Windows y aca corre {plataforma.NOMBRE}. "
            "Panel > Voz: elige Piper."
        )
    import pyttsx3

    # Motor nuevo por utterance: pyttsx3 se cuelga si se reusa entre hilos.
    engine = pyttsx3.init()
    if cfg.get("tts_voice"):
        for v in engine.getProperty("voices"):
            if cfg["tts_voice"].lower() in v.name.lower():
                engine.setProperty("voice", v.id)
                break
    if progreso:
        # SAPI avisa en que palabra va: aca el subtitulo queda sincronizado de
        # verdad, no repartido por largo como con Piper. El nivel lo inventamos
        # a partir del largo de la palabra, porque SAPI no da amplitud.
        def al_empezar_palabra(_nombre, ubicacion, largo):  # noqa: ANN001
            progreso(min(1.0, 0.35 + largo / 12), text[:ubicacion + largo])

        engine.connect("started-word", al_empezar_palabra)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def _speak_elevenlabs(text: str, cfg: dict) -> None:
    import requests

    key = store.get_key("elevenlabs")
    voice = cfg.get("elevenlabs_voice_id")
    if not key or not voice:
        raise RuntimeError("TTS en ElevenLabs seleccionado pero falta la key o el voice_id.")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": key},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=60,
    )
    r.raise_for_status()
    path = os.path.join(tempfile.gettempdir(), "eve_tts.mp3")
    with open(path, "wb") as f:
        f.write(r.content)
    plataforma.abrir(path)  # reproductor por defecto del sistema


def list_sapi_voices() -> list[str]:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        names = [v.name for v in engine.getProperty("voices")]
        engine.stop()
        return names
    except Exception:  # noqa: BLE001
        return []
