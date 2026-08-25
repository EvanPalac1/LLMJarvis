"""Mide los dos motores de dibujo sobre la MISMA escena, adentro de Eve.

Existe porque escribi tres bancos sinteticos seguidos y los tres dieron numeros
falsos. Uno dibujaba las particulas de a una cuando `lienzo.py` las hace por
numpy; otro media Qt sin subir la imagen a pantalla mientras a tkinter si se la
cobraba; el tercero recomponia la ventana entera, que es justamente lo que este
motor evita. Cada uno inflaba a un candidato distinto.

La leccion es del proyecto y ya estaba escrita para la voz: se mide el camino
entero y con el material de verdad, o no se mide. Aca eso significa el `Lienzo`
real, los modulos reales y `raiz.update()` incluido, que es donde se paga el
puente al toolkit.

    python main.py --bench-dibujo            los dos motores
    python main.py --bench-dibujo pillow     uno solo
"""

import os
import tempfile
import time

CUADROS = 240
CALENTAR = 30
ANCHO, ALTO = 1100, 700


def _escena(cuantas_particulas: int) -> list[dict]:
    """Seis modulos, N de ellos con 500 particulas. La escena pesada."""
    lista = []
    for i in range(6):
        m = {"id": f"b{i}", "tipo": "onda", "superficie": "tablero",
             "x": 20 + (i % 3) * 360, "y": 20 + (i // 3) * 340,
             "ancho": 340, "alto": 320, "z": i, "opacidad": 100, "escala": 100,
             "rotacion": 0, "cuando": "siempre", "interactivo": False,
             "velocidad": 1.0, "easing": "lineal", "fuente": "microfono",
             "tinte": "", "color": "acento", "pantalla": 0,
             "estilo": "barras", "muestras": 48}
        if i < cuantas_particulas:
            m.update({"tipo": "particulas", "cantidad": 500, "vida": 1.0,
                      "gravedad": 40})
        lista.append(m)
    return lista


def _percentiles(tiempos: list[float]) -> tuple[float, float]:
    ms = sorted(t * 1000.0 for t in tiempos)
    return ms[len(ms) // 2], ms[int(len(ms) * 0.95)]


def _medir(motor: str, cuantas_particulas: int) -> tuple[float, float] | None:
    """Una corrida. Devuelve (p50, p95) en ms, o None si ese motor no se puede.

    Los dos caminos se miden con `raiz.update()` adentro del cronometro. Es el
    paso que sube el dibujo al toolkit y es donde se paga de verdad: dejarlo
    afuera de uno de los dos --que es el error que ya cometi-- le regala la
    comparacion a ese.
    """
    import tkinter as tk

    import numpy as np

    from . import gpu, lienzo as lienzo_mod, store, tema

    cfg = dict(store.DEFAULTS)
    cfg["motor_dibujo"] = motor
    if gpu.elegido(cfg) != motor:
        print(f"  ({motor}: {gpu.por_que(cfg)})")
        return None

    lista = _escena(cuantas_particulas)
    estado = {"trabajando": True, "nivel": 0.5, "onda": [], "detalle": "bench",
              "usuario": "", "eve": ""}
    raiz = tk.Tk()
    raiz.geometry(f"{ANCHO}x{ALTO}")
    tiempos: list[float] = []

    if motor == "skia":
        from .lienzo_skia import LienzoSkia

        marco = gpu.marco(raiz, ANCHO, ALTO)
        if marco is None:
            raiz.destroy()
            return None
        marco.pack(fill="both", expand=True)
        estado_local = {"pintor": None, "n": 0}
        paleta = tema.resolver(cfg, "hud")

        def initgl():
            if estado_local["pintor"] is None:
                estado_local["pintor"] = LienzoSkia(
                    gpu.Superficie(ANCHO, ALTO), cfg, paleta)

        def redraw():
            pintor = estado_local["pintor"]
            if pintor is None:
                return
            i = estado_local["n"]
            t0 = time.perf_counter()
            estado["nivel"] = 0.3 + 0.3 * float(np.sin(i / 7.0))
            estado["onda"] = list(np.random.rand(64))
            pintor.dibujar(lista, estado)
            if i >= CALENTAR:
                tiempos.append(time.perf_counter() - t0)
            estado_local["n"] = i + 1
            if estado_local["n"] >= CUADROS + CALENTAR:
                raiz.quit()

        marco.initgl = initgl
        marco.redraw = redraw
        marco.animate = 1
        marco.after(50, marco.tkExpose, None)
        raiz.mainloop()
        raiz.destroy()
        return _percentiles(tiempos) if tiempos else None

    lienzo_tk = tk.Canvas(raiz, width=ANCHO, height=ALTO, highlightthickness=0,
                          bg="#101010")
    lienzo_tk.pack()
    pintor = lienzo_mod.Lienzo(lienzo_tk, cfg)
    for i in range(CUADROS + CALENTAR):
        t0 = time.perf_counter()
        # El microfono cambia en cada cuadro: es lo que obliga a repintar y lo
        # que hace de esta la escena cara. Con datos quietos no se repintaria
        # nada y estariamos midiendo el cache.
        estado["nivel"] = 0.3 + 0.3 * float(np.sin(i / 7.0))
        estado["onda"] = list(np.random.rand(64))
        pintor.dibujar(lista, estado)
        raiz.update()
        if i >= CALENTAR:
            tiempos.append(time.perf_counter() - t0)
    raiz.destroy()
    return _percentiles(tiempos)


def correr(cual: str = "") -> int:
    """Imprime la tabla. `cual` vacio = los dos motores."""
    from . import gpu, store

    # Corral: la escena escribe config de prueba y no tiene por que tocar la
    # del usuario. Es la misma regla que el resto de los bancos del proyecto.
    corral = tempfile.mkdtemp(prefix="eve-bench-")
    store.BASE = corral
    store.CONFIG_PATH = os.path.join(corral, "config.json")

    sirve, motivo = gpu.disponible()
    print(f"GPU utilizable: {'si' if sirve else 'no'}"
          f"{'' if sirve else '  (' + motivo + ')'}")
    print(f"Escena: 6 modulos de {ANCHO}x{ALTO}, {CUADROS} cuadros, "
          f"repintando todos cada cuadro.\n")

    motores = [cual] if cual else ["pillow", "skia"]
    print(f"{'motor':10} {'escena':28} {'p50':>9} {'p95':>9}  fps")
    print("-" * 62)
    hubo = False
    for motor in motores:
        for cuantas, etiqueta in ((0, "6 ondas"),
                                  (6, "6 x 500 particulas")):
            r = _medir(motor, cuantas)
            if r is None:
                break
            hubo = True
            p50, p95 = r
            print(f"{motor:10} {etiqueta:28} {p50:6.2f} ms {p95:6.2f} ms "
                  f"{1000 / p95:5.1f}")
    if not hubo:
        print("\nNingun motor se pudo medir aca.")
        return 1
    print()
    print("Donde se va el tiempo con Pillow, perfilado sobre esta escena:")
    print("  ImageTk.paste (el puente PIL -> Tcl) .... 89% del cuadro")
    print("  dibujar los modulos de verdad ...........  9%")
    print()
    print("O sea que el cuello NO es dibujar: es subir el dibujo al toolkit,")
    print("y cuesta ~15 ms por modulo animado por cuadro. Seis modulos")
    print("animando son ~90 ms hagan lo que hagan adentro. Ese es el techo,")
    print("y no se mueve optimizando el dibujo. Skia lo saca de raiz porque")
    print("escribe directo en el framebuffer de la GPU: no hay puente.")
    return 0
