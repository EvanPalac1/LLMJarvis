"""Activacion por palabra clave, sin dependencias nuevas.

Se evaluaron las opciones de siempre y ninguna entra en este proyecto:

    Porcupine        cinco objetivos OK, pero exige una AccessKey de cuenta.
                     No podes embeber la tuya en un instalador que distribuis.
    openWakeWord     los modelos preentrenados son CC-BY-NC, y `tflite-runtime`
                     no publica ruedas aarch64 recientes.
    Vosk             sin rueda para mac-arm64 ni para linux-aarch64: 3 de 5.
    whisper continuo el propio repo mide RTF 1.09 con `small` en CPU. Un core
                     entero, todo el dia, mientras el usuario juega.

Lo que sirve ya estaba adentro de la casa: faster-whisper trae
`assets/silero_vad_v6.onnx` (1.2 MB) y depende de onnxruntime, asi que los dos
viajan en los cinco paquetes desde siempre. Medido en esta maquina: **0.20% de
un core** para seguir el microfono en tiempo real. Eso es lo que puede estar
prendido todo el dia.

Entonces el esquema es de dos etapas. Silero decide *cuando* hay voz --barato,
todo el tiempo-- y recien sobre ese pedazo corre un whisper chico que decide
*que* dijo. En reposo no corre ningun modelo de lenguaje.

Y la frase va entera: "Eve, abri Spotify" se resuelve en una sola respiracion,
sin pitido en el medio ni ventana de captura aparte. El segmento que silero
recorto ya tiene la palabra clave Y la orden, asi que no hace falta ninguna
maquina de estados: se mira si arranca con la palabra y lo que sobra es el
pedido.
"""

from __future__ import annotations

import queue
import threading
import time
import unicodedata

import numpy as np

from . import voice

MUESTREO = 16000
TRAMA = 512                  # lo que espera silero v6 a 16 kHz: 32 ms
BLOQUE = TRAMA * 8           # ~0.26 s por vuelta del lazo
HABLA = 0.5                  # probabilidad a partir de la cual es voz
CIERRE_S = 0.7               # silencio que da por terminada la frase
MIN_S = 0.4                  # menos VOZ que esto fue un ruido, no una frase
MAX_S = 8.0                  # tope duro: nadie dicta un parrafo a un asistente
COLA_S = 0.3                 # audio previo que se guarda, para no comerse la "E"


def normalizar(texto: str) -> str:
    """Minusculas y sin acentos. La palabra clave se compara asi para que
    escribirla con o sin tilde en el panel de igual."""
    t = unicodedata.normalize("NFD", texto.lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def separar(texto: str, palabra: str) -> str | None:
    """El pedido que sigue a la palabra clave, o None si no esta al principio.

    Se exige al PRINCIPIO a proposito. Aceptarla en cualquier lado convierte
    cualquier charla que la mencione en una orden. Devuelve "" cuando la frase
    es solo la palabra: eso es una llamada valida, distinta de no coincidir.

    `palabra` acepta variantes separadas por `|`, y no es un lujo. Medido con la
    voz de Piper, cuatro ordenes positivas y seis frases que NO tienen que
    despertarla:

        palabra                modelo   desperto   falsos
        Computadora            tiny        4 / 4    0 / 6
        Computadora            small       4 / 4    0 / 6
        Eve (+ ebe, eva)       small       3 / 4    0 / 6
        Eve (+ ebe, eva)       tiny        2 / 4    0 / 6
        Eve (+ ebe, eva)       base        0 / 4    0 / 6

    Dos conclusiones. La palabra pesa mas que el modelo: "Computadora" con el
    modelo mas chico gana a "Eve" con uno cuatro veces mas grande, y ademas
    tarda menos de la mitad. Y tres letras no alcanzan para ser una puerta, sin
    que haya heuristica difusa que lo arregle: aceptar distancia 1 sobre "eve"
    abre la puerta a "ese", "ave" y "eco".

    Los falsos positivos dieron cero en las seis frases de control, incluida
    "le dije a Eve que abriera Steam", que es justo la que rompe una puerta que
    acepte la palabra en cualquier posicion.

    Si preferis el nombre, anota como te escribe a vos y agregalo como variante:
    `Eve --probar-voz "Eve, abri Spotify"`.
    """
    hay = normalizar(texto)
    # Sin puntuacion: el modelo escribe "Eve," o "¿Eve?" y eso no puede fallar.
    limpio = "".join(c if c.isalnum() or c.isspace() else " " for c in hay).split()
    crudo = "".join(c if c.isalnum() or c.isspace() else " " for c in texto).split()
    for variante in str(palabra).split("|"):
        partes = normalizar(variante).split()
        if not partes or limpio[: len(partes)] != partes:
            continue
        return " ".join(crudo[len(partes):]).strip()
    return None


class Recortador:
    """La parte de la escucha que se puede probar sin microfono.

    Recibe bloques y decide donde empieza y donde termina una frase. Vive aparte
    del stream a proposito: lo unico complicado aca son los buffers, y atarlos a
    un dispositivo de audio los volveria imposibles de testear.
    """

    def __init__(self, modelo) -> None:
        self.modelo = modelo
        self._previo: list[np.ndarray] = []
        self._frase: list[np.ndarray] = []
        self._callado = 0.0
        self._con_voz = 0.0
        self._max_previo = int(COLA_S * MUESTREO / BLOQUE) + 1

    def empujar(self, bloque: np.ndarray) -> np.ndarray | None:
        """Devuelve la frase completa cuando termino, y None mientras tanto."""
        plano = np.asarray(bloque, dtype="float32").flatten()
        if len(plano) % TRAMA:
            plano = plano[: len(plano) // TRAMA * TRAMA]
        if not len(plano):
            return None
        hay_voz = float(self.modelo(plano).max()) >= HABLA

        if hay_voz:
            if not self._frase:
                # El arranque de la frase quedo en el buffer rodante: sin esto
                # se pierde la primera silaba, que es justo la palabra clave.
                self._frase = list(self._previo)
            self._frase.append(plano)
            self._callado = 0.0
            self._con_voz += len(plano) / MUESTREO
        elif self._frase:
            self._frase.append(plano)   # el silencio del final es parte
            self._callado += len(plano) / MUESTREO
        else:
            self._previo.append(plano)
            del self._previo[:-self._max_previo]
            return None

        largo = sum(len(t) for t in self._frase) / MUESTREO
        if self._callado < CIERRE_S and largo < MAX_S:
            return None
        audio, con_voz = np.concatenate(self._frase), self._con_voz
        self._frase, self._callado, self._previo, self._con_voz = [], 0.0, [], 0.0
        # Se mide la VOZ, no el largo del recorte. Con el aire de antes y el
        # silencio de cierre, un chasquido de 0.26s salia como una frase de
        # 1.5s y el minimo no filtraba nada: lo encontro el test, no el uso.
        return audio if con_voz >= MIN_S else None


class Escucha:
    """Sigue el microfono y avisa cada vez que termina una frase.

    No transcribe: eso lo decide quien la usa. Aca solo se recorta.
    """

    def __init__(self, al_terminar) -> None:
        self.al_terminar = al_terminar
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self.activa = False
        self.error = ""

    def arrancar(self, esperar: float = 0.0) -> bool:
        """Prende la escucha. Con `esperar`, devuelve si el microfono abrio.

        Hace falta esperar porque el hilo primero carga silero --un par de
        segundos-- y recien despues toca el stream: preguntar antes de eso es
        preguntarle a un hilo que todavia no llego. Sin esto lo unico que se
        podia hacer era anunciar "escuchando" y cruzar los dedos.
        """
        if self._hilo is None:
            self._parar.clear()
            self._hilo = threading.Thread(target=self._lazo, daemon=True)
            self._hilo.start()
        limite = time.monotonic() + esperar
        while esperar and time.monotonic() < limite:
            if self.activa or self.error:
                break
            time.sleep(0.2)
        return self.activa

    def parar(self) -> None:
        """Cierra el stream de verdad, no lo ignora.

        Es la diferencia entre pausar y aparentar que se pauso: si el microfono
        sigue abierto, el LED sigue prendido y el chip de audio no duerme.
        """
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2)
            self._hilo = None
        self.activa = False

    def _lazo(self) -> None:
        try:
            import sounddevice as sd
            from faster_whisper.vad import get_vad_model
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return

        recorta = Recortador(get_vad_model())
        cola: queue.Queue = queue.Queue()

        def cb(indata, _frames, _t, _status):  # noqa: ANN001
            cola.put(indata.copy())

        try:
            stream = sd.InputStream(samplerate=MUESTREO, channels=1, dtype="float32",
                                    blocksize=BLOQUE, callback=cb)
            stream.start()
        except Exception as exc:  # noqa: BLE001 - el mic lo puede tener otro
            self.error = str(exc)
            return

        self.activa = True
        self.error = ""
        try:
            while not self._parar.is_set():
                try:
                    bloque = cola.get(timeout=0.5)
                except queue.Empty:
                    continue
                frase = recorta.empujar(bloque)
                if frase is not None:
                    self.al_terminar(frase)
        finally:
            stream.stop()
            stream.close()
            self.activa = False


def escuchado(audio: np.ndarray, cfg: dict) -> str | None:
    """Transcribe con el modelo chico y devuelve el pedido si desperto.

    El modelo de la puerta es aparte y chico a proposito: acierta o no acierta
    una palabra que ya conoce, y correr el modelo grande en cada frase que se
    dice cerca del microfono seria pagar la transcripcion buena por nada.
    """
    chico = dict(cfg)
    chico["stt_model"] = cfg.get("wake_modelo") or "tiny"
    # Determinista: sin esto la misma frase despierta o no segun la corrida.
    chico["stt_temperatura"] = 0.0
    # Y sesgado hacia su propia palabra, no hacia el catalogo de programas.
    palabra = str(cfg.get("wake_palabra", "eve"))
    chico["stt_prompt"] = ", ".join(v.strip() for v in palabra.split("|") if v.strip())
    texto = voice.transcribe(audio, chico)
    if not texto:
        return None
    return separar(texto, str(cfg.get("wake_palabra", "eve")))
