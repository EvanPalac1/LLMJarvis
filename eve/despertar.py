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
CIERRE_S = 0.7               # silencio que da por terminada la frase.
                             # Con un juez de fin de turno pasa a ser el
                             # TOPE: se puede cortar antes, nunca despues.
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
    # Sin puntuacion, a los DOS lados. Al texto oido porque el modelo escribe
    # "Eve," o "¿Eve?"; a la palabra configurada porque el usuario la escribe
    # como se le ocurre, y una coma de mas cerraba la puerta para siempre y en
    # silencio. Medido antes del arreglo:
    #
    #     separar("Eve, abre Spotify", "eve, computadora") -> None
    #     separar("Eve, abre Spotify", "Eve!")             -> None
    #
    # Se limpiaba un lado y el otro no, que es la unica forma de que una
    # comparacion de dos cosas normalizadas siga fallando.
    limpio = _sin_puntuacion(hay)
    crudo = _sin_puntuacion(texto)
    for variante in _variantes(palabra):
        partes = _sin_puntuacion(normalizar(variante))
        if not partes or limpio[: len(partes)] != partes:
            continue
        return " ".join(crudo[len(partes):]).strip()
    return None


def _sin_puntuacion(texto: str) -> list:
    """Las palabras sueltas, sin nada que no sea letra o numero."""
    return "".join(c if c.isalnum() or c.isspace() else " " for c in texto).split()


def _variantes(palabra) -> list:
    """Las formas de llamarla. Separadas por `|` o por coma, las dos.

    La documentada es `|`, pero escribir "computadora, eve" es lo que hace
    cualquiera que vea una lista, y hasta ahora eso no daba una lista: daba UNA
    variante de dos palabras, que solo coincidiria si dijeras las dos seguidas.
    La puerta quedaba cerrada para siempre y nada lo decia --ni un aviso, ni un
    renglon en Acciones-- porque desde adentro no hay diferencia entre "la
    palabra no coincide" y "la palabra es imposible".

    Aceptar las dos no rompe nada: una palabra clave con una coma adentro no
    existe, y quien use `|` sigue igual.
    """
    crudo = str(palabra).replace(",", "|")
    return [v for v in (x.strip() for x in crudo.split("|")) if v]


def palabra_de(cfg: dict) -> str:
    """La palabra que la despierta. Vacia = como se llama el asistente.

    La seccion del panel se llama "Despertarla diciendo su nombre" y leia OTRO
    campo, en otra pestana: renombrar la IA a "Viernes" dejaba la puerta
    abierta en "computadora" y ninguna pantalla lo decia. Eran dos ajustes que
    de afuera se ven como uno.

    Ahora el vacio significa "usa el nombre", que es lo que la seccion promete,
    y escribir algo sigue mandando --hay una razon medida para preferir una
    palabra larga, y es del usuario decidirlo--:

        palabra                modelo   desperto   falsos
        Computadora            tiny        4 / 4    0 / 6
        Eve (+ ebe, eva)       tiny        2 / 4    0 / 6

    Tres letras no le dan al reconocedor con que agarrarse. Por eso el valor de
    fabrica sigue siendo "computadora" y no el vacio: quien quiera el nombre lo
    borra, y ahi la puerta pasa a llamarse como ella.
    """
    palabra = str(cfg.get("wake_palabra", "") or "").strip()
    if palabra:
        return palabra
    return str(cfg.get("assistant_name", "") or "").strip() or "eve"


class Recortador:
    """La parte de la escucha que se puede probar sin microfono.

    Recibe bloques y decide donde empieza y donde termina una frase. Vive aparte
    del stream a proposito: lo unico complicado aca son los buffers, y atarlos a
    un dispositivo de audio los volveria imposibles de testear.
    """

    def __init__(self, modelo, juez=None) -> None:
        self.modelo = modelo
        # Quien decide que terminaste de hablar, si hay alguien.
        #
        # Sin juez manda el cronometro: `CIERRE_S` de silencio y la frase se
        # cierra. Es un numero fijo para dos situaciones que no se parecen
        # --pensar en medio de una orden larga, y terminar de decirla-- asi que
        # se equivoca en las dos direcciones. Con juez, el cronometro pasa a ser
        # el TOPE: se pregunta antes, y si dice que termino se corta antes.
        #
        # Se recibe como parametro y no se importa aca: asi el Recortador se
        # sigue probando sin modelo, con una funcion de tres lineas, que es lo
        # que lo hace testeable --y es la misma razon por la que `modelo` ya
        # entraba por parametro--.
        self.juez = juez
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
            if not self._termino_antes():
                return None
        audio, con_voz = np.concatenate(self._frase), self._con_voz
        self._frase, self._callado, self._previo, self._con_voz = [], 0.0, [], 0.0
        # Se mide la VOZ, no el largo del recorte. Con el aire de antes y el
        # silencio de cierre, un chasquido de 0.26s salia como una frase de
        # 1.5s y el minimo no filtraba nada: lo encontro el test, no el uso.
        return audio if con_voz >= MIN_S else None

    def _termino_antes(self) -> bool:
        """Le pregunta al juez si la frase ya esta completa.

        Solo despues de `SILENCIO_MIN_S` de silencio: preguntarle en medio de
        una palabra es pedirle una opinion sobre algo que todavia no paso, y la
        respuesta seria ruido.

        Y falla hacia el cronometro, siempre. Un juez que se cae, que tarda o
        que devuelve algo raro NO puede cortar la escucha ni cortar al usuario
        a mitad de frase: se ignora y manda `CIERRE_S`, que es lo que habia
        antes de que existiera esto.
        """
        if self.juez is None or not self._frase:
            return False
        from . import turno

        if self._callado < turno.SILENCIO_MIN_S:
            return False
        try:
            return bool(self.juez(np.concatenate(self._frase)))
        except Exception:  # noqa: BLE001 - el cronometro sigue estando
            self.juez = None
            return False


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
        # Cuantas frases fallaron sin tumbar la escucha. Se cuenta para que se
        # pueda comprobar que sigue viva DESPUES de un error, que es lo unico
        # que distingue "aguanto" de "no paso nada".
        self.fallos = 0

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

        # El juez sale de la config del momento y no de una que se leyo al
        # importar: prender el modelo en el panel y que no pase nada hasta
        # reiniciar es el bug que ya tuvo la cache de whisper.
        #
        # Armar el recortador tambien va adentro de un try. Estaba afuera, y
        # eso era el mismo agujero que el del lazo: cargar silero o el juez
        # puede fallar, y sin esto el hilo se moria antes de empezar, con
        # `error` vacio y `activa` en False --o sea, indistinguible de "el
        # microfono lo tiene otro programa"--.
        try:
            from . import store, turno

            recorta = Recortador(get_vad_model(), turno.juez(store.load_config()))
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            return
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
                try:
                    frase = recorta.empujar(bloque)
                    if frase is not None:
                        self.al_terminar(frase)
                except Exception as exc:  # noqa: BLE001
                    # Una frase que falla NO puede llevarse la escucha entera.
                    #
                    # Este `try` faltaba y el de afuera es un `try/finally` sin
                    # `except`: cualquier excepcion de `al_terminar` --y ahi
                    # adentro corre un whisper y un `voice.speak`-- mataba el
                    # hilo, cerraba el stream y dejaba a Eve sorda hasta el
                    # proximo cambio de config. En silencio: nada lo anunciaba,
                    # y desde afuera se ve como "dejo de despertar sola".
                    self.fallos += 1
                    self.error = f"{type(exc).__name__}: {exc}"
                    try:
                        from . import store

                        store.log_action("listener", "wake", f"ERROR en la escucha: {exc}")
                    except Exception:  # noqa: BLE001 - anotar no puede fallar feo
                        pass
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
    palabra = palabra_de(cfg)
    chico["stt_prompt"] = ", ".join(_variantes(palabra))
    texto = voice.transcribe(audio, chico)
    if not texto:
        return None
    return separar(texto, palabra)
