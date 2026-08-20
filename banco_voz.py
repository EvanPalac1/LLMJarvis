"""Banco de voz: mide WER sobre grabaciones reales.

No hay forma de saber si un motor de voz nuevo es mejor sin medirlo, y un motor
de voz no se mide con audio sintetizado: la voz de Piper no tiene ruido de fondo,
no se aleja del microfono y no dice nombres propios en ingles con acento
argentino, que es exactamente donde se rompe.

El banco NO va al repo. Son grabaciones de la voz de una persona, asi que viven
en la carpeta de datos junto a los contactos y los perfiles:

    %APPDATA%/LLMJarvis/banco_voz/       (Windows)
    ~/.local/share/LLMJarvis/banco_voz/  (Linux)

Adentro, un `.wav` por clip y un `transcripciones.json` con lo que se dijo de
verdad. Correr:

    python banco_voz.py                 mide todo con la config actual
    python banco_voz.py --modelo medium  pisa el modelo sin tocar la config
    python banco_voz.py --grupo propios  solo un grupo
    python banco_voz.py --comparar small,medium,large-v3   tabla de modelos
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

from eve import store, voice

CARPETA = Path(store.BASE) / "banco_voz"
TRANSCRIPCIONES = "transcripciones.json"


def normalizar(texto: str) -> list[str]:
    """Baja a la forma en la que Eve realmente compara.

    Se sacan los acentos a proposito: el matcher de comandos y de contactos ya es
    insensible a ellos, asi que contar "abri" vs "abrí" como un error inflaria el
    WER con fallas que a la aplicacion no le cambian nada.
    """
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", t).split()


def distancia(ref: list[str], hip: list[str]) -> tuple[int, int, int]:
    """Levenshtein por palabras. Devuelve (sustituciones, inserciones, borrados)."""
    # Matriz con el rastro de que operacion gano, para poder desglosar el error:
    # un motor que inventa palabras y otro que se las come dan el mismo WER y se
    # arreglan de formas distintas.
    n, m = len(ref), len(hip)
    d = [[(0, 0, 0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = (i, 0, 0, i)  # costo, sub, ins, del
    for j in range(1, m + 1):
        d[0][j] = (j, 0, j, 0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hip[j - 1]:
                d[i][j] = d[i - 1][j - 1]
                continue
            c_sub, c_ins, c_del = d[i - 1][j - 1][0], d[i][j - 1][0], d[i - 1][j][0]
            mejor = min(c_sub, c_ins, c_del)
            s, ins, dl = (
                d[i - 1][j - 1][1:] if mejor == c_sub
                else d[i][j - 1][1:] if mejor == c_ins
                else d[i - 1][j][1:]
            )
            if mejor == c_sub:
                d[i][j] = (mejor + 1, s + 1, ins, dl)
            elif mejor == c_ins:
                d[i][j] = (mejor + 1, s, ins + 1, dl)
            else:
                d[i][j] = (mejor + 1, s, ins, dl + 1)
    return d[n][m][1:]


def leer_wav(ruta: Path) -> tuple[np.ndarray, float]:
    with wave.open(str(ruta), "rb") as w:
        cuadros = w.getnframes()
        audio = np.frombuffer(w.readframes(cuadros), dtype="<i2")
        rate, canales = w.getframerate(), w.getnchannels()
    if canales > 1:
        audio = audio.reshape(-1, canales).mean(axis=1)
    audio = audio.astype("float32") / 32768.0
    if rate != 16000:
        idx = (np.arange(int(len(audio) * 16000 / rate)) * rate / 16000).astype(int)
        audio = audio[idx]
    return audio, cuadros / rate


def grupo_de(nombre: str) -> str:
    """`limpio_03.wav` -> `limpio`. El grupo es lo que se mide por separado."""
    return re.sub(r"_\d+$", "", Path(nombre).stem)


def _referencias(carpeta: Path) -> dict | None:
    ficha = carpeta / TRANSCRIPCIONES
    if not ficha.exists():
        print(f"Falta {ficha}.")
        print("Corre `python banco_voz.py --borrador` para generarlo y despues corregilo.")
        return None
    return json.loads(ficha.read_text(encoding="utf-8"))


def _correr(carpeta: Path, cfg: dict, refs: dict, solo: str = "") -> dict[str, list]:
    por_grupo: dict[str, list] = {}
    for nombre, esperado in sorted(refs.items()):
        if not esperado or (solo and grupo_de(nombre) != solo):
            continue
        audio, segundos = leer_wav(carpeta / nombre)
        t0 = time.perf_counter()
        salida = voice.transcribe(audio, cfg)
        tardo = time.perf_counter() - t0

        ref, hip = normalizar(esperado), normalizar(salida)
        sub, ins, dl = distancia(ref, hip)
        por_grupo.setdefault(grupo_de(nombre), []).append(
            (nombre, len(ref), sub, ins, dl, tardo, segundos, esperado, salida)
        )
    return por_grupo


def _totales(filas: list) -> tuple[int, int, float, float]:
    """(palabras, errores, segundos de proceso, segundos de audio)."""
    return (sum(f[1] for f in filas), sum(f[2] + f[3] + f[4] for f in filas),
            sum(f[5] for f in filas), sum(f[6] for f in filas))


def comparar(carpeta: Path, cfg: dict, modelos: list[str], solo: str = "") -> int:
    """Una fila por modelo, una columna por grupo. Es la tabla que decide si un
    motor nuevo entra: sin esto la comparacion es una opinion."""
    refs = _referencias(carpeta)
    if refs is None:
        return 1
    grupos = sorted({grupo_de(n) for n, t in refs.items() if t and (not solo or grupo_de(n) == solo)})
    print(f"{'modelo':<12} " + " ".join(f"{g:>9}" for g in grupos) + f"{'TOTAL':>10}{'RTF':>7}")
    print("-" * (12 + 10 * len(grupos) + 17))
    for m in modelos:
        por_grupo = _correr(carpeta, cfg | {"stt_model": m}, refs, solo)
        fila, tp, te, tt, ts = f"{m:<12} ", 0, 0, 0.0, 0.0
        for g in grupos:
            p, e, t, sg = _totales(por_grupo.get(g, []))
            tp, te, tt, ts = tp + p, te + e, tt + t, ts + sg
            fila += f"{e / p:>8.1%} " if p else f"{'-':>9} "
        print(fila + f"{te / tp:>9.1%}" + f"{tt / ts:>7.2f}")
    return 0


def medir(carpeta: Path, cfg: dict, solo: str = "") -> int:
    refs = _referencias(carpeta)
    if refs is None:
        return 1
    por_grupo = _correr(carpeta, cfg, refs, solo)
    if not por_grupo:
        print("No hay clips con transcripcion para medir.")
        return 1

    print(f"modelo {cfg['stt_model']} en {cfg['stt_device']}\n")
    tot_p = tot_e = 0
    tot_t = tot_s = 0.0
    for gr, filas in por_grupo.items():
        p, e, t, s = _totales(filas)
        tot_p, tot_e, tot_t, tot_s = tot_p + p, tot_e + e, tot_t + t, tot_s + s
        print(f"{gr:<10} WER {e / p:6.1%}   {e}/{p} palabras   RTF {t / s:.2f}")
        for nombre, np_, sub, ins, dl, _, _, esperado, salida in filas:
            if sub + ins + dl:
                print(f"    {nombre}  s{sub} i{ins} b{dl}")
                print(f"      dijo: {esperado}")
                print(f"      oyo : {salida}")
    print(f"\nTOTAL      WER {tot_e / tot_p:6.1%}   {tot_e}/{tot_p} palabras   "
          f"RTF {tot_t / tot_s:.2f}  ({tot_t:.1f}s para {tot_s:.1f}s de audio)")
    return 0


def borrador(carpeta: Path, cfg: dict) -> int:
    """Transcribe todo y deja el json para corregir a mano.

    Es mas rapido corregir 29 lineas que escribirlas, pero el borrador NO es la
    referencia: sale del mismo motor que se va a medir, asi que aceptarlo sin
    leerlo daria un WER de 0% que no significa nada.
    """
    ficha = carpeta / TRANSCRIPCIONES
    previo = json.loads(ficha.read_text(encoding="utf-8")) if ficha.exists() else {}
    salida = {}
    for w in sorted(carpeta.glob("*.wav")):
        if previo.get(w.name):
            salida[w.name] = previo[w.name]
            continue
        audio, _ = leer_wav(w)
        salida[w.name] = voice.transcribe(audio, cfg).strip()
        print(f"{w.name}: {salida[w.name]}")
    ficha.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBorrador en {ficha}. Corregilo antes de medir: lo que dice ahi es la verdad.")
    return 0


def main(argv: list[str]) -> int:
    carpeta = CARPETA
    cfg = store.load_config()
    solo, hacer_borrador, modelos = "", False, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--modelo":
            i += 1
            cfg["stt_model"] = argv[i]
        elif a == "--device":
            i += 1
            cfg["stt_device"] = argv[i]
        elif a == "--grupo":
            i += 1
            solo = argv[i]
        elif a == "--carpeta":
            i += 1
            carpeta = Path(argv[i])
        elif a == "--borrador":
            hacer_borrador = True
        elif a == "--comparar":
            i += 1
            modelos = argv[i].split(",")
        else:
            print(__doc__)
            return 1
        i += 1

    if not carpeta.exists():
        print(f"No existe {carpeta}. Dejá ahi los .wav del banco.")
        return 1
    if hacer_borrador:
        return borrador(carpeta, cfg)
    if modelos:
        return comparar(carpeta, cfg, modelos, solo)
    return medir(carpeta, cfg, solo)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
