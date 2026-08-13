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


_cargadas: dict = {}


def _voz(key: str):
    """El modelo de Piper, cargado una sola vez por voz.

    Cargarlo cuesta ~2.3 segundos y sintetizar solo 0.24: hacerlo en cada frase
    era pagar diez veces el trabajo util y dejaba a Piper mas lento que la voz
    robotica de Windows. Cacheado, es cuatro veces mas rapido que SAPI ademas de
    sonar mejor.
    """
    if key not in _cargadas:
        from piper import PiperVoice

        modelo = ruta_modelo(key)
        if not os.path.exists(modelo):
            raise FileNotFoundError(f"La voz {key} no esta descargada.")
        _cargadas[key] = PiperVoice.load(modelo)
    return _cargadas[key]


def precargar(key: str) -> None:
    """Deja la voz lista antes de que haga falta, sin bloquear a nadie."""
    import threading

    def trabajo():
        try:
            _voz(key)
        except Exception:  # noqa: BLE001 - si no esta, ya se avisara al hablar
            pass

    threading.Thread(target=trabajo, daemon=True).start()


def hablar(texto: str, key: str, salida: str = "", hablante: int = 0,
           velocidad: float = 1.0) -> str:
    """Sintetiza con Piper y reproduce. Devuelve la ruta del wav.

    `hablante` elige la voz dentro de un modelo multi-voz; sin esto de
    es_ES-sharvard-medium (que trae una masculina y una femenina) solo salia la
    primera. `velocidad` es el length_scale del modelo: mas alto habla mas lento.
    Es lo que permite que dos personajes compartan modelo sin sonar iguales, y
    sale gratis: lo hace el sintetizador, no un efecto encima.
    """
    import wave

    if not salida:
        import tempfile

        salida = os.path.join(tempfile.gettempdir(), "eve_piper.wav")

    voz = _voz(key)
    ajustes = _ajustes(hablante, velocidad)
    with wave.open(salida, "wb") as wav:
        # Sin ajustes se llama igual que siempre, sin el parametro: la voz por
        # defecto recorre exactamente el mismo camino que antes de que esto
        # existiera.
        if ajustes is None:
            voz.synthesize_wav(texto, wav)
        else:
            voz.synthesize_wav(texto, wav, syn_config=ajustes)
    return salida


def _ajustes(hablante: int, velocidad: float):
    """SynthesisConfig, o None si no hay nada que cambiar.

    None cuando son los valores por defecto: asi las voces de una sola voz a
    velocidad normal siguen recorriendo exactamente el mismo camino que antes.
    """
    if not hablante and abs(velocidad - 1.0) < 1e-6:
        return None
    from piper import SynthesisConfig

    return SynthesisConfig(speaker_id=int(hablante) or None,
                           length_scale=float(velocidad))


CACHE_FRASES = os.path.join(store.BASE, "frases")


def _firma(texto: str, key: str, hablante: int = 0, velocidad: float = 1.0) -> str:
    """Identifica un wav cacheado por TODO lo que cambia como suena.

    El hablante y la velocidad van adentro, no solo la voz y el texto: dos
    personajes pueden compartir modelo y diferenciarse nada mas que por la
    velocidad, y con la firma vieja el segundo se comia el audio del primero
    -misma frase, misma voz- y sonaba a la velocidad equivocada.
    """
    import hashlib

    crudo = f"{key}|{hablante}|{velocidad:.3f}|{texto.strip().lower()}"
    return hashlib.sha1(crudo.encode()).hexdigest()[:16]


def frase_cacheada(texto: str, key: str, hablante: int = 0,
                   velocidad: float = 1.0) -> str:
    """Wav ya generado para esa frase con esa voz, o '' si no esta.

    Eve dice siempre lo mismo: "Abriendo Spotify", "Listo", "No te entendi". Son
    pocas y se repiten, asi que guardarlas en disco convierte el sintetizado en
    una lectura de archivo. Lo caro no era el motor sino generar de nuevo algo
    identico a lo de ayer.
    """
    ruta = os.path.join(CACHE_FRASES, f"{_firma(texto, key, hablante, velocidad)}.wav")
    return ruta if os.path.exists(ruta) else ""


def guardar_frase(texto: str, key: str, origen: str, hablante: int = 0,
                  velocidad: float = 1.0) -> None:
    """Guarda el wav de una frase corta para la proxima vez."""
    import shutil

    if len(texto) > 120:
        return  # las largas no se repiten; llenar el disco con ellas no paga
    try:
        os.makedirs(CACHE_FRASES, exist_ok=True)
        firma = _firma(texto, key, hablante, velocidad)
        shutil.copy2(origen, os.path.join(CACHE_FRASES, f"{firma}.wav"))
    except OSError:
        pass


def limpiar_cache_frases() -> int:
    """Borra los wav guardados. Devuelve cuantos. Al cambiar de voz hay que
    tirarlos: si no, seguirias escuchando la voz vieja en las frases repetidas."""
    if not os.path.isdir(CACHE_FRASES):
        return 0
    n = 0
    for archivo in os.listdir(CACHE_FRASES):
        try:
            os.remove(os.path.join(CACHE_FRASES, archivo))
            n += 1
        except OSError:
            pass
    return n


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
