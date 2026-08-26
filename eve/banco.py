"""Grabador guiado del banco de voz, con el silencio que el banco no tiene.

Existe por una sola razon, y esta medida: el banco actual se corto por silencio
--umbral relativo al pico de cada archivo-- y eso elimino justo los silencios,
que es donde vive el ruido de fondo. Medido sobre los 24 clips de hoy: mediana
de **90 ms** antes de la primera palabra y **1 solo clip** llega a los 300 ms.

Sin ese silencio no se puede medir la relacion senal-ruido de cada clip, y sin
eso el modo de sensibilidad `auto` --el que mira el ruido del ambiente y elige
solo, en vez de adivinarlo por el reloj-- no se puede validar. Es el unico
punto del plan que quedo sin hacer, y no por falta de codigo.

Lo que hace este modulo es lo minimo para arreglarlo: guiar la grabacion y
**comprobar el silencio antes de aceptar el clip**. Un grabador que no lo
comprueba deja pasar exactamente el problema que vino a resolver, porque
adelantarse a hablar es lo normal cuando uno esta leyendo una frase.

Las frases salen del `transcripciones.json` que ya existe, y eso es a
proposito: grabar las MISMAS frases deja el banco nuevo comparable contra los
numeros publicados --WER por grupo, la tabla de modelos-- en vez de empezar una
serie nueva que no se puede contrastar con nada.

El banco viejo NO se toca. Es la linea base de todo lo medido hasta hoy.
"""

import json
import os
import wave

import numpy as np

from . import store, voice

CARPETA_VIEJA = "banco_voz"
CARPETA = "banco_voz_crudo"
TRANSCRIPCIONES = "transcripciones.json"

# Cuanto silencio hace falta antes de la primera palabra. 300 ms es lo que
# necesita una estimacion de ruido de fondo que no sea ruido ella misma: con
# 100 ms la varianza de la medicion se come la diferencia entre un cuarto
# callado y uno con un ventilador.
SILENCIO_MINIMO_MS = 300
# Lo que se le pide al usuario, con margen: apuntar justo al minimo garantiza
# que la mitad de las tomas queden abajo.
SILENCIO_PEDIDO_MS = 1200


def carpeta(cual: str = CARPETA) -> str:
    return os.path.join(store.BASE, cual)


def frases() -> dict:
    """{nombre.wav: texto} del banco viejo, que es el que da las frases.

    Si no esta, se devuelve vacio y quien llame lo dira: inventar una lista de
    frases aca haria que el banco nuevo no se pueda comparar con el viejo, que
    es la mitad de para que sirve grabarlo.
    """
    ruta = os.path.join(carpeta(CARPETA_VIEJA), TRANSCRIPCIONES)
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if v}
    except (OSError, ValueError):
        return {}


def hechas() -> set:
    """Los clips que ya se grabaron en el banco nuevo."""
    d = carpeta()
    if not os.path.isdir(d):
        return set()
    return {n for n in os.listdir(d) if n.lower().endswith(".wav")}


def silencio_inicial_ms(audio, sr: int = voice.SAMPLE_RATE) -> float:
    """Cuantos ms pasan hasta la primera palabra.

    El umbral es relativo al pico del propio clip y no absoluto, por lo mismo
    que lo era en el cortador: un susurro y un grito tienen picos que se llevan
    veinte dB, y un umbral fijo daria "no hablo nunca" en uno y "hablo desde el
    primer cuadro" en el otro.
    """
    audio = np.asarray(audio, dtype="float32").flatten()
    if not len(audio):
        return 0.0
    pico = float(np.abs(audio).max())
    if pico <= 0:
        return len(audio) / sr * 1000.0
    fuertes = np.flatnonzero(np.abs(audio) > pico * 0.1)
    return (float(fuertes[0]) if len(fuertes) else len(audio)) / sr * 1000.0


def ruido_de_fondo_db(audio, sr: int = voice.SAMPLE_RATE) -> float:
    """dBFS del silencio inicial. Es el dato que el banco viejo no puede dar.

    Devuelve -120 si no hay silencio suficiente que medir, que es lo mismo que
    decir "este clip no sirve para esto".
    """
    audio = np.asarray(audio, dtype="float32").flatten()
    ms = silencio_inicial_ms(audio, sr)
    if ms < SILENCIO_MINIMO_MS:
        return -120.0
    # Se descartan los ultimos 50 ms del silencio: ahi ya suele estar la
    # inspiracion previa a hablar, que no es ruido de ambiente.
    fin = max(1, int((ms - 50) / 1000.0 * sr))
    rms = float(np.sqrt(np.mean(np.square(audio[:fin]))) + 1e-12)
    return 20.0 * np.log10(rms)


def revisar(audio, sr: int = voice.SAMPLE_RATE) -> tuple:
    """(sirve, motivo). El motivo esta escrito para leerse en pantalla."""
    audio = np.asarray(audio, dtype="float32").flatten()
    if len(audio) < sr * 0.5:
        return False, "Salio muy corto. Empeza de nuevo."
    ms = silencio_inicial_ms(audio, sr)
    if ms < SILENCIO_MINIMO_MS:
        return False, (f"Te adelantaste: {ms:.0f} ms de silencio y hacen falta "
                       f"{SILENCIO_MINIMO_MS}. Espera a que diga HABLA.")
    if float(np.abs(audio).max()) < 0.02:
        return False, "Casi no se te escucha. Fijate el microfono."
    return True, (f"Bien: {ms:.0f} ms de silencio, ruido de fondo "
                  f"{ruido_de_fondo_db(audio, sr):.0f} dBFS.")


def guardar(nombre: str, audio, sr: int = voice.SAMPLE_RATE) -> str:
    """Escribe el WAV **sin recortar nada**. Devuelve la ruta.

    Sin recortar es toda la funcion de este modulo: el cortador por silencio es
    lo que dejo al banco viejo sin poder medir el ruido de fondo.
    """
    d = carpeta()
    os.makedirs(d, exist_ok=True)
    ruta = os.path.join(d, os.path.basename(nombre))
    datos = np.clip(np.asarray(audio, dtype="float32").flatten(), -1, 1)
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((datos * 32767).astype("<i2").tobytes())
    return ruta


def escribir_transcripciones() -> str:
    """Copia las frases al banco nuevo, solo para los clips que existen.

    Se escriben las que YA se grabaron y no las 24: `banco_voz.py` recorre este
    archivo, asi que una entrada sin su wav lo hace fallar a mitad de la
    medicion en vez de medir lo que hay.
    """
    d = carpeta()
    os.makedirs(d, exist_ok=True)
    tengo = hechas()
    datos = {k: v for k, v in frases().items() if k in tengo}
    ruta = os.path.join(d, TRANSCRIPCIONES)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    return ruta


def resumen() -> str:
    """Una linea con como viene el banco nuevo, para mostrar en el panel."""
    total = len(frases())
    tengo = len(hechas())
    if not total:
        return "Falta el banco viejo: de ahi salen las frases."
    return f"{tengo} de {total} grabadas."
