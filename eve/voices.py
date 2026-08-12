"""Voces de la comunidad para Piper TTS.

Piper publica cientos de voces entrenadas por la comunidad en HuggingFace, en
mas de 30 idiomas, gratis y offline. El indice `voices.json` trae para cada una
su idioma, calidad, tamaño y el md5 de cada archivo.

Ademas resuelve el problema multiplataforma: SAPI solo existe en Windows, y
`pyttsx3` en macOS y Linux es irregular. Piper tiene wheels para los tres.
"""

import hashlib
import json
import os

import requests

from . import store

REPO = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
INDICE_URL = f"{REPO}/voices.json"
VOICES_DIR = os.path.join(store.BASE, "voices")
INDICE_LOCAL = os.path.join(VOICES_DIR, "voices.json")

CALIDADES = ("x_low", "low", "medium", "high")


def _dir() -> str:
    os.makedirs(VOICES_DIR, exist_ok=True)
    return VOICES_DIR


def catalogo(refresh: bool = False) -> dict:
    """Indice completo de voces. Se cachea: son ~1 MB de JSON."""
    if not refresh and os.path.exists(INDICE_LOCAL):
        try:
            with open(INDICE_LOCAL, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    r = requests.get(INDICE_URL, timeout=60)
    r.raise_for_status()
    datos = r.json()
    _dir()
    with open(INDICE_LOCAL, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    return datos


def listar(idioma: str = "", calidad: str = "") -> list[dict]:
    """Voces disponibles, filtrables. `idioma` matchea 'es', 'es_ES' o 'Spanish'."""
    filtro = idioma.lower().strip()
    salida = []
    for key, v in catalogo().items():
        lang = v.get("language", {})
        etiquetas = " ".join(
            str(lang.get(k, "")) for k in ("code", "family", "region", "name_native", "name_english")
        ).lower()
        if filtro and filtro not in etiquetas:
            continue
        if calidad and v.get("quality") != calidad:
            continue
        salida.append(
            {
                "key": key,
                "nombre": v.get("name", "?"),
                "idioma": lang.get("name_english", lang.get("code", "?")),
                "codigo": lang.get("code", ""),
                "calidad": v.get("quality", "?"),
                "voces": v.get("num_speakers", 1),
                "mb": round(sum(f.get("size_bytes", 0) for f in v.get("files", {}).values()) / 1e6, 1),
            }
        )
    return sorted(salida, key=lambda x: (x["idioma"], x["nombre"], CALIDADES.index(x["calidad"]) if x["calidad"] in CALIDADES else 9))


def idiomas() -> list[str]:
    vistos = {}
    for v in catalogo().values():
        lang = v.get("language", {})
        nombre = lang.get("name_english")
        if nombre:
            vistos[nombre] = lang.get("code", "")
    return sorted(vistos)


def ruta_modelo(key: str) -> str:
    return os.path.join(_dir(), f"{key}.onnx")


def instaladas() -> list[str]:
    if not os.path.isdir(VOICES_DIR):
        return []
    return sorted(
        n[:-5] for n in os.listdir(VOICES_DIR)
        if n.endswith(".onnx") and os.path.exists(os.path.join(VOICES_DIR, n + ".json"))
    )


def descargar(key: str, progreso=None) -> str:
    """Baja el .onnx y su .onnx.json, verificando el md5 del indice.

    Sin la verificacion, un corte de red deja un modelo truncado que despues
    falla al sintetizar con un error que no dice nada.
    """
    entrada = catalogo().get(key)
    if not entrada:
        return f"No existe la voz {key!r}. Fijate en el catalogo."

    archivos = {
        ruta: meta
        for ruta, meta in entrada.get("files", {}).items()
        if ruta.endswith(".onnx") or ruta.endswith(".onnx.json")
    }
    if not archivos:
        return f"La voz {key!r} no tiene modelo descargable."

    _dir()
    for ruta, meta in archivos.items():
        destino = ruta_modelo(key) + (".json" if ruta.endswith(".json") else "")
        total = meta.get("size_bytes", 0)
        bajado = 0
        tmp = destino + ".parcial"
        with requests.get(f"{REPO}/{ruta}", stream=True, timeout=300) as r:
            r.raise_for_status()
            md5 = hashlib.md5()  # noqa: S324 - es el checksum que publica el indice
            with open(tmp, "wb") as f:
                for trozo in r.iter_content(chunk_size=1 << 16):
                    f.write(trozo)
                    md5.update(trozo)
                    bajado += len(trozo)
                    if progreso and total:
                        progreso(key, bajado, total)
        esperado = meta.get("md5_digest")
        if esperado and md5.hexdigest() != esperado:
            os.remove(tmp)
            return f"La descarga de {key} salio corrupta (md5 no coincide). No se instalo."
        os.replace(tmp, destino)

    return f"Voz {key} instalada ({round(sum(m.get('size_bytes', 0) for m in archivos.values()) / 1e6, 1)} MB)."


def borrar(key: str) -> str:
    borrados = 0
    for sufijo in (".onnx", ".onnx.json"):
        ruta = os.path.join(VOICES_DIR, key + sufijo)
        if os.path.exists(ruta):
            os.remove(ruta)
            borrados += 1
    return f"Voz {key} borrada." if borrados else f"{key} no estaba instalada."


def hablar(texto: str, key: str, salida: str = "") -> str:
    """Sintetiza con Piper y reproduce. Devuelve la ruta del wav."""
    import wave

    from piper import PiperVoice

    modelo = ruta_modelo(key)
    if not os.path.exists(modelo):
        raise FileNotFoundError(f"La voz {key} no esta descargada.")

    if not salida:
        import tempfile

        salida = os.path.join(tempfile.gettempdir(), "eve_piper.wav")

    voz = PiperVoice.load(modelo)
    with wave.open(salida, "wb") as wav:
        voz.synthesize_wav(texto, wav)
    return salida


def reproducir(ruta: str, progreso=None) -> None:
    """Reproduce un wav por la placa de sonido, sin abrir ningun reproductor.

    Se usa `sounddevice`, que ya esta instalado para grabar el microfono: evita
    depender del reproductor por defecto de cada sistema.

    `progreso(fraccion, nivel)` se llama ~20 veces por segundo mientras suena,
    con cuanto va reproducido (0..1) y el volumen de ese instante. De ahi salen
    la onda del overlay y el avance del subtitulo, sincronizados con el audio de
    verdad y no con un cronometro aparte.
    """
    import time
    import wave

    import numpy as np
    import sounddevice as sd

    with wave.open(ruta, "rb") as wav:
        datos = wav.readframes(wav.getnframes())
        rate = wav.getframerate()
        canales = wav.getnchannels()
    audio = np.frombuffer(datos, dtype="<i2").astype("float32") / 32768.0
    if canales > 1:
        audio = audio.reshape(-1, canales)
    sd.play(audio, rate)
    if progreso is None:
        sd.wait()
        return

    mono = audio if audio.ndim == 1 else audio.mean(axis=1)
    duracion = len(mono) / rate
    arranque = time.monotonic()
    while True:
        t = time.monotonic() - arranque
        if t >= duracion:
            break
        i = int(t * rate)
        bloque = mono[i:i + rate // 20]
        nivel = float(np.sqrt(np.abs(bloque).mean())) * 1.8 if bloque.size else 0.0
        progreso(t / duracion, min(1.0, nivel))
        time.sleep(0.05)
    sd.wait()
    progreso(1.0, 0.0)


if __name__ == "__main__":
    print(f"{len(catalogo())} voces en el catalogo, {len(idiomas())} idiomas")
    for v in listar("spanish")[:10]:
        print(f"  {v['key']:34} {v['calidad']:7} {v['mb']:6} MB")
    print("\ninstaladas:", instaladas() or "ninguna")
