"""Microfono -> texto (STT) y texto -> parlante (TTS).

Local por defecto: faster-whisper para STT (el reconocimiento nativo de Windows
es mediocre en espanol) y SAPI para TTS. Los proveedores en la nube quedan
disponibles si el usuario carga sus propias claves en el panel.
"""

import io
import os
import queue
import tempfile
import wave

import numpy as np
import sounddevice as sd

from . import store

SAMPLE_RATE = 16000
_whisper = None


class MicBusyError(RuntimeError):
    """Otro programa tiene el microfono en modo exclusivo (Discord, OBS, Zoom)."""


class Recorder:
    """Push-to-talk: start() al presionar, stop() al soltar."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._stream = None

    def start(self) -> None:
        if self._stream is not None:
            return
        self._q = queue.Queue()

        def cb(indata, _frames, _t, status):  # noqa: ANN001
            if status:
                pass  # xruns: preferimos audio con glitches a perder la frase
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


def transcribe(audio: np.ndarray, cfg: dict) -> str:
    if audio.size < SAMPLE_RATE // 4:  # menos de 250 ms: fue un toque, no una frase
        return ""

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

    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        _whisper = WhisperModel(
            cfg["stt_model"], device=cfg["stt_device"], compute_type="int8"
        )
    # Sin initial_prompt, decodificar en espanol destroza los nombres propios en
    # ingles. Pasarle los programas instalados es lo que hace que "abre rainbow
    # six siege" no salga como "Haberé en Vox XC".
    from . import apps

    segments, _ = _whisper.transcribe(
        audio,
        language=cfg["language"],
        initial_prompt=apps.vocabulary(cfg.get("stt_vocabulary", "")),
        vad_filter=True,
    )
    return " ".join(s.text for s in segments).strip()


def speak(text: str, cfg: dict) -> None:
    if not text or not cfg.get("speak_replies", True):
        return

    if cfg["tts_provider"] == "elevenlabs":
        _speak_elevenlabs(text, cfg)
        return

    if cfg["tts_provider"] == "piper":
        from . import voices

        clave = cfg.get("piper_voice") or (voices.instaladas() or [""])[0]
        if not clave:
            raise RuntimeError(
                "TTS en Piper pero no hay ninguna voz descargada. Panel > Voces."
            )
        voices.reproducir(voices.hablar(text, clave))
        return

    import pyttsx3

    # Motor nuevo por utterance: pyttsx3 se cuelga si se reusa entre hilos.
    engine = pyttsx3.init()
    if cfg.get("tts_voice"):
        for v in engine.getProperty("voices"):
            if cfg["tts_voice"].lower() in v.name.lower():
                engine.setProperty("voice", v.id)
                break
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
    os.startfile(path)  # noqa: S606 - reproductor por defecto de Windows


def list_sapi_voices() -> list[str]:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        names = [v.name for v in engine.getProperty("voices")]
        engine.stop()
        return names
    except Exception:  # noqa: BLE001
        return []
