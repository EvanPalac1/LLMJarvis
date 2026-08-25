"""Dibujo por GPU con Skia, y la decision de si conviene usarlo.

Por que existe: `lienzo.py` compone con Pillow sobre la CPU y sube con
`PhotoImage`. Eso alcanza para lo que Eve dibuja hoy --su propia cabecera
documenta 7.1 ms de p95 con un modulo animando-- pero tiene un techo que no se
mueve con optimizaciones: no hay shaders, ni bloom, ni miles de particulas.

Medido en esta maquina sobre 1100x700, seis capas con alpha y 500 particulas:

    Pillow por CPU, seis modulos animando p50 20.34 ms  <- ya optimizado
    Skia por GPU adentro de tkinter      p50   2.04 ms   <- el dibujo
    Skia por CPU (sin GPU utilizable)    p50 214.17 ms   <- por eso el respaldo

Ese ultimo numero es la razon de que este modulo sea una CAPACIDAD y no un
interruptor. Sin GPU, Skia es diez veces PEOR que lo que ya hay. Si
`GrDirectContext.MakeGL()` no devuelve contexto, se cae a Pillow y no a Skia por
CPU, que seria la peor de las tres opciones.

Se comprobo ademas lo que de verdad decidia si esto servia para el cartel: que la
transparencia y el click-through sobrevivan al contexto de OpenGL. Con una
ventana verde detras y una foto de la pantalla, la esquina del cartel mostro
(0, 200, 60) --el verde de atras-- y el centro el dibujo de Skia. O sea que el
recorte por chroma-key SI se aplica al contenido de GL, y `WS_EX_TRANSPARENT`
sigue puesto. Sin eso, esto habria servido solo para la ventana de actividad.

Los imports son diferidos a proposito: quien no active el motor por GPU no paga
ni el arranque, y si las librerias faltan el modulo entero se declara no
disponible en vez de impedir que Eve arranque.

El widget con contexto lo pone `eve/marco_gl.py`, que es nuestro. Dependia de
`pyopengltk` hasta que CI lo probo en los cinco objetivos: en los dos de macOS ni
importa --su `darwin.py` dice "Currently not implemented"-- y lo que quedaba era
depender de un paquete 0.0.4 sin mantenimiento para doscientas lineas.
"""

import os

from . import plataforma

# Lo que puede valer `motor_dibujo`. `auto` es el de fabrica: usa la GPU si la
# hay. Un valor elegido a mano NO lo pisa la deteccion, que es la misma regla
# que ya rige `sensibilidad` y `ui_fps`.
MOTORES = ("auto", "skia", "pillow")

_CACHE = None       # None = todavia no se pregunto; se pregunta una sola vez
_FALLO = ""         # si el contexto se intento y no salio, el motivo


def _probar() -> tuple[bool, str]:
    """Si estan las tres librerias. Devuelve (puede que sirva, por que no).

    ES UNA COMPROBACION BARATA Y NO ALCANZA, y conviene que quede escrito
    porque este mismo docstring afirmaba lo contrario. Decia "se prueba CREANDO
    el contexto" cuando solo miraba los imports -- describia justo el modo de
    falla que no cubria.

    Lo destapo CI: en el runner de Windows las tres librerias importan bien y el
    contexto de OpenGL igual no se arma, porque no hay GPU ni driver detras.
    Crear un contexto de verdad aca costaria abrir una ventana en cada arranque
    de Eve, que es caro y ademas imposible antes de que exista la ventana.

    La salida es `marcar_fallo()`: quien intente usar la GPU y no pueda lo
    anota, y desde ahi toda la sesion cae a Pillow. Barato al preguntar,
    honesto al fallar.
    """
    try:
        import skia  # noqa: F401
    except ImportError:
        return False, "falta skia-python"
    try:
        import OpenGL.GL  # noqa: F401
    except ImportError:
        return False, "falta PyOpenGL"
    # El widget con contexto lo pone `marco_gl`, que es nuestro. Antes esto
    # dependia de `pyopengltk`, que en macOS ni importa: su `darwin.py` dice
    # "Currently not implemented" y su `__init__` tiene el import comentado.
    from . import marco_gl

    puede, motivo = marco_gl.se_puede()
    if not puede:
        return False, motivo
    if os.environ.get("EVE_SIN_GPU"):
        # Para los tests y para poder reproducir el camino sin GPU en una
        # maquina que si la tiene, que es donde se escribe el codigo.
        return False, "desactivada por EVE_SIN_GPU"
    return True, ""


def disponible() -> tuple[bool, str]:
    """Cacheada. Si el contexto ya fallo una vez, dice que no para siempre."""
    global _CACHE
    if _FALLO:
        return False, _FALLO
    if _CACHE is None:
        _CACHE = _probar()
    return _CACHE


def marcar_fallo(motivo: str) -> None:
    """El contexto se intento y no salio: no volver a intentarlo esta sesion.

    Lo llama quien arma la superficie. Sin esto, una maquina donde las
    librerias estan pero la GPU no responde reintentaria en cada cuadro, y cada
    reintento cuesta abrir un contexto que ya sabemos que no se arma.
    """
    global _FALLO
    _FALLO = motivo or "el contexto de OpenGL no se pudo armar"


def olvidar() -> None:
    """Vuelve a preguntar, y olvida el fallo. La usan los tests."""
    global _CACHE, _FALLO
    _CACHE = None
    _FALLO = ""


def elegido(cfg: dict) -> str:
    """Que motor de dibujo usar de verdad: "skia" o "pillow".

    Nunca devuelve "auto": la decision se toma aca y una sola vez, para que el
    resto del codigo no tenga que volver a preguntarsela. Y nunca devuelve
    "skia" si no se puede: pedirlo a mano en una maquina sin GPU degradaria a
    214 ms por cuadro, y el proyecto no degrada en silencio.
    """
    quiere = str(cfg.get("motor_dibujo", "auto"))
    if quiere not in MOTORES:
        quiere = "auto"
    if quiere == "pillow":
        return "pillow"
    sirve, _ = disponible()
    return "skia" if sirve else "pillow"


def por_que(cfg: dict) -> str:
    """Una linea para el panel y para el log. Que se esta usando, y por que.

    Un ajuste que puede no hacer lo que dice tiene que decir lo que hizo. Es la
    misma regla que `plataforma.modo_transparencia()`: bandera de capacidad,
    nunca degradar callado.
    """
    quiere = str(cfg.get("motor_dibujo", "auto"))
    sirve, motivo = disponible()
    if quiere == "pillow":
        return "Pillow por CPU (elegido a mano)."
    if sirve:
        return "Skia por GPU."
    if quiere == "skia":
        return f"Pediste Skia pero no se puede ({motivo}); va Pillow por CPU."
    return f"Pillow por CPU: no hay GPU utilizable ({motivo})."


class Superficie:
    """Un lienzo de Skia atado al framebuffer de un widget de tkinter.

    `pyopengltk.OpenGLFrame` crea y mantiene el contexto; Skia se engancha al que
    este activo. Es la misma division que usa Chrome: el toolkit pone la ventana,
    Skia pinta adentro. Y sale mas barato que traer un toolkit nuevo: medido,
    tkinter+Skia da 9.99 ms de cuadro real contra 13.33 de Qt+Skia, con 16 MB de
    dependencias nuevas en vez de 134.
    """

    def __init__(self, ancho: int, alto: int):
        import skia
        from OpenGL import GL

        self.skia = skia
        self.ancho = ancho
        self.alto = alto
        self.ctx = skia.GrDirectContext.MakeGL()
        if not self.ctx:
            raise RuntimeError("no hay contexto de OpenGL")
        info = skia.GrGLFramebufferInfo(0, GL.GL_RGBA8)
        objetivo = skia.GrBackendRenderTarget(ancho, alto, 0, 8, info)
        self.superficie = skia.Surface.MakeFromBackendRenderTarget(
            self.ctx, objetivo, skia.kBottomLeft_GrSurfaceOrigin,
            skia.kRGBA_8888_ColorType, skia.ColorSpace.MakeSRGB())
        if not self.superficie:
            raise RuntimeError("no pude armar la superficie sobre el framebuffer")

    @property
    def lienzo(self):
        return self.superficie.getCanvas()

    def limpiar(self, rgba) -> None:
        self.lienzo.clear(self.skia.Color(*rgba))

    def presentar(self) -> None:
        self.ctx.flush()

    def color(self, rgba):
        return self.skia.Color(*rgba)

    def pincel(self, rgba, suavizado=True):
        return self.skia.Paint(Color=self.color(rgba), AntiAlias=suavizado)


def marco(padre, ancho: int, alto: int, fondo: str = "",
          al_iniciar=None, al_dibujar=None):
    """El widget que hospeda el contexto. Devuelve None si no se puede.

    Se separa de `Superficie` porque el widget lo crea tkinter y la superficie
    solo existe una vez que el contexto esta activo, o sea adentro de `initgl`.
    """
    sirve, _ = disponible()
    if not sirve:
        return None
    from . import marco_gl

    extra = {"bg": fondo} if fondo else {}
    try:
        return marco_gl.MarcoGL(padre, al_iniciar=al_iniciar,
                                al_dibujar=al_dibujar,
                                width=ancho, height=alto, **extra)
    except Exception as exc:  # noqa: BLE001 - sin GL no hay widget
        marcar_fallo(f"no se pudo crear el widget de OpenGL ({exc})")
        return None


def fps_tope(cfg: dict) -> int:
    """Cuadros por segundo sugeridos segun el motor que va a dibujar.

    Con Skia el dibujo cuesta ~2 ms, asi que el limite lo pone la pantalla y no
    el motor: no tiene sentido dejar el tope de 20 que se eligio para ARM cuando
    el trabajo entra treinta veces en el cuadro.
    """
    if elegido(cfg) != "skia":
        return plataforma.fps_sugerido()
    # `fps_sugerido` devuelve 20 en ARM y 30 en el resto. Con Skia el dibujo
    # entra treinta veces en el cuadro, asi que se duplica: el limite pasa a ser
    # la pantalla y no el motor.
    return plataforma.fps_sugerido() * 2


def probar_a_fondo() -> int:
    """Comprueba el camino de GPU de punta a punta. Devuelve 0 si sirve.

    Lo corre CI en los cinco objetivos, que es la puerta que le falta a este
    modulo para poder entrar al instalador. No alcanza con que las tres
    librerias importen: `pyopengltk` crea el contexto de forma distinta en cada
    sistema, y en un runner sin pantalla puede importar perfecto y no dibujar.

    Por eso se llega hasta el final: se abre una ventana, se crea el contexto,
    se arma la superficie, se dibuja un modulo de verdad y SE MIRAN LOS PIXELES.
    Un "anduvo" que no comprobo que algo se dibujara no comprueba nada -- es
    exactamente el error que ya se cometio en este proyecto con la sonda del
    menu de la bandeja.
    """
    import platform

    print(f"Sistema: {platform.system()} {platform.machine()}")
    print(f"Python:  {platform.python_version()}")

    faltan = []
    for nombre in ("skia", "OpenGL.GL"):
        try:
            __import__(nombre)
            print(f"  ok    import {nombre}")
        except ImportError as exc:
            print(f"  FALTA import {nombre}: {exc}")
            faltan.append(nombre)
    if faltan:
        print(f"\nNo estan instaladas: {', '.join(faltan)}")
        print("Es un resultado valido: sin ellas Eve usa Pillow y anda igual.")
        return 1

    from . import marco_gl

    puede, motivo = marco_gl.se_puede()
    print(f"  {'ok   ' if puede else 'NO   '} contexto en este sistema"
          f"{'' if puede else ': ' + motivo}")
    if not puede:
        print()
        print(motivo)
        print("Es un resultado valido: Eve dibuja con Pillow, que anda en los "
              "cinco sistemas.")
        return 6

    import tkinter as tk

    try:
        raiz = tk.Tk()
    except tk.TclError as exc:
        print(f"\nSin pantalla: {exc}")
        print("No concluyente: hace falta un servidor grafico para decidir.")
        return 2

    ancho, alto = 320, 240
    resultado = {"codigo": 3, "dicho": "el widget no llego a dibujar"}
    try:
        raiz.geometry(f"{ancho}x{alto}")
        # Tk NO propaga las excepciones de sus callbacks: se las pasa a
        # `report_callback_exception`, que por defecto las imprime y sigue. O
        # sea que un fallo adentro de `initgl` --por ejemplo `MakeGL()`
        # devolviendo None en una maquina sin GPU-- no llega al `try` de afuera
        # y el resultado queda en el mensaje generico "no llego a dibujar".
        #
        # Eso es lo que paso en el runner de Windows: dos corridas de CI
        # diciendo "no llego a dibujar" sin una sola linea de por que. Aca se
        # captura para que el diagnostico exista.
        def _atrapar(tipo, valor, _traza):
            resultado.update(codigo=5, dicho=f"{tipo.__name__}: {valor}")
            raiz.quit()

        raiz.report_callback_exception = _atrapar
        estado = {}

        def initgl():
            if "sup" in estado:
                return
            estado["sup"] = Superficie(ancho, alto)

        def redraw():
            if "sup" not in estado or resultado["codigo"] != 3:
                return
            sup = estado["sup"]
            from . import lienzo_skia

            sup.limpiar((0, 0, 0, 255))
            modulo = {"id": "p", "tipo": "onda", "estilo": "barras",
                      "muestras": 16, "opacidad": 100, "color": "texto"}
            # Muestras al tope: las barras tienen que llenar el alto, asi que
            # un pixel claro abajo al medio es prueba de que dibujo.
            lienzo_skia.pintar_onda(sup, modulo, {"onda": [1.0] * 16}, 0.0,
                                    ancho, alto, (255, 255, 255, 255))
            sup.presentar()
            px = sup.superficie.toarray(
                colorType=sup.skia.kRGBA_8888_ColorType)
            claros = int((px[..., 0] > 200).sum())
            if claros > 100:
                resultado.update(codigo=0,
                                 dicho=f"dibujo {claros} pixeles claros")
            else:
                resultado.update(codigo=4,
                                 dicho=f"la superficie salio vacia ({claros})")
            raiz.quit()

        # Las dos funciones van AL CONSTRUCTOR y no como atributos despues:
        # asignarlas tarde es una carrera contra `<Map>` y `<Expose>`, y CI la
        # encontro. Ver `marco_gl.MarcoGL`.
        marco_gl = marco(raiz, ancho, alto, al_iniciar=initgl,
                         al_dibujar=redraw)
        if marco_gl is None:
            print()
            print("No se pudo crear el widget de OpenGL.")
            return 3
        marco_gl.pack(fill="both", expand=True)
        marco_gl.animate = 0
        marco_gl.after(80, marco_gl.tkExpose, None)
        # Un tope de tiempo: si el contexto no se arma, `mainloop` esperaria
        # para siempre y CI se quedaria colgado en vez de dar un resultado.
        raiz.after(15000, raiz.quit)
        raiz.mainloop()
    except Exception as exc:  # noqa: BLE001 - cualquier falla es un resultado
        print(f"\nFallo armando el camino: {type(exc).__name__}: {exc}")
        return 5
    finally:
        try:
            raiz.destroy()
        except Exception:  # noqa: BLE001
            pass

    print(f"\n{'SIRVE' if resultado['codigo'] == 0 else 'NO SIRVE'}: "
          f"{resultado['dicho']}")
    return resultado["codigo"]
