"""Un widget de tkinter con contexto de OpenGL, sin `pyopengltk`.

Reemplaza a esa libreria, y no por gusto: CI la probo en los cinco objetivos y
en los dos de macOS ni siquiera importa. El error que da Python --"cannot import
name 'OpenGLFrame' from partially initialized module, most likely due to a
circular import"-- es una adivinanza equivocada. Mirando el paquete: su
`darwin.py` tiene UNA linea que dice "Currently not implemented", y el import de
darwin esta comentado en su `__init__.py`. **No hay soporte de macOS y no lo hubo
nunca**; el mensaje de circularidad despista.

Lo que quedaba era depender de un paquete 0.0.4 sin mantenimiento para 200 lineas
que se leen en un rato. Aca estan escritas, sin el codigo muerto que aquel
arrastra --su rama de Linux tiene un `return` con cincuenta lineas inalcanzables
detras-- y sin los `print` de depuracion que escupia en cada arranque.

Queda `PyOpenGL`, que es rueda pura, esta mantenida y publica para los cinco.

SOBRE macOS: sigue sin andar, y no por falta de ganas. Tk dibuja sobre su propio
NSView y atarle un NSOpenGLContext pide llamar al runtime de Objective-C por
ctypes; ademas Apple declaro obsoleto OpenGL en 10.14 y el camino moderno seria
Metal. No es una linea que falte: es una plataforma que eligio otro rumbo. Asi
que macOS declara que no puede y Eve dibuja con Pillow, igual que hoy.

Eso NO viola la regla de los cinco objetivos, y conviene ver por que: la regla
dice que una DEPENDENCIA no entra si no publica para los cinco. `skia-python` y
`PyOpenGL` publican para los cinco y se instalan bien en macOS. Lo que no anda es
la CAPACIDAD, y para eso el proyecto ya tiene su patron --`modo_transparencia()`
devuelve `perpixel`/`colorkey`/`global` y el panel muestra en gris lo que el
sistema no soporta. Una capacidad que degrada avisando es distinta de una
dependencia que rompe el paquete.
"""

import sys
import tkinter as tk

WINDOWS = sys.platform.startswith("win")
LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"


class SinContexto(RuntimeError):
    """No se puede armar un contexto de OpenGL aca. Trae el motivo."""


class MarcoGL(tk.Frame):
    """Un `tk.Frame` que expone un contexto de OpenGL activo.

    Quien lo usa implementa dos metodos: `initgl` --una vez, con el contexto ya
    activo-- y `redraw` --cada cuadro. Es la misma forma que tenia `pyopengltk`,
    a proposito: el codigo que ya estaba escrito contra esa interfaz no cambia.
    """

    def __init__(self, padre=None, **kw):
        # Fondo vacio: sin esto Tk pinta encima del contenido de GL y parpadea.
        kw["bg"] = ""
        super().__init__(padre, **kw)
        self.animate = 0          # ms entre cuadros; 0 = solo cuando se pide
        self._pendiente = None
        self._hay_contexto = False
        self.bind("<Map>", self._al_mostrarse)
        self.bind("<Configure>", self._al_redimensionar)
        self.bind("<Expose>", self.tkExpose)

    # -- lo que implementa quien lo usa --------------------------------------

    def initgl(self) -> None:
        """Se llama una vez, con el contexto ya activo."""

    def redraw(self) -> None:
        """Se llama en cada cuadro, con el contexto ya activo."""

    # -- el ciclo ------------------------------------------------------------

    def _al_mostrarse(self, _evento=None) -> None:
        self._wid = self.winfo_id()
        if not self._hay_contexto:
            self.tkCreateContext()
            self._hay_contexto = True
            self.initgl()

    def _al_redimensionar(self, evento) -> None:
        self.width, self.height = evento.width, evento.height
        if self._hay_contexto and self.winfo_ismapped():
            from OpenGL import GL

            self.tkMakeCurrent()
            GL.glViewport(0, 0, self.width, self.height)
            self.initgl()

    def tkExpose(self, _evento=None) -> None:
        """Dibuja un cuadro. El nombre se conserva por compatibilidad."""
        if self._pendiente is not None:
            self.after_cancel(self._pendiente)
            self._pendiente = None
        if not self._hay_contexto:
            self._al_mostrarse()
        self.update_idletasks()
        self.tkMakeCurrent()
        self.redraw()
        self.tkSwapBuffers()
        if self.animate > 0:
            self._pendiente = self.after(self.animate, self.tkExpose)

    # -- lo que cambia por sistema -------------------------------------------

    def tkCreateContext(self) -> None:
        if WINDOWS:
            return self._contexto_windows()
        if LINUX:
            return self._contexto_linux()
        raise SinContexto(
            "OpenGL dentro de tkinter no esta soportado en macOS: Tk dibuja "
            "sobre su propio NSView y Apple declaro obsoleto OpenGL en 10.14. "
            "Eve dibuja con Pillow, que anda en los cinco sistemas.")

    def tkMakeCurrent(self) -> None:
        if not self.winfo_ismapped():
            return
        if WINDOWS:
            from OpenGL.WGL import wglMakeCurrent

            wglMakeCurrent(self._dc, self._ctx)
        elif LINUX:
            from OpenGL import GLX

            GLX.glXMakeCurrent(self._pantalla, self._wid, self._ctx)

    def tkSwapBuffers(self) -> None:
        if not self.winfo_ismapped():
            return
        if WINDOWS:
            from OpenGL.WGL import SwapBuffers

            SwapBuffers(self._dc)
        elif LINUX:
            from OpenGL import GLX

            GLX.glXSwapBuffers(self._pantalla, self._wid)

    # -- Windows -------------------------------------------------------------

    def _contexto_windows(self) -> None:
        import ctypes
        from ctypes import wintypes

        from OpenGL.WGL import (PIXELFORMATDESCRIPTOR, ChoosePixelFormat,
                                SetPixelFormat, wglCreateContext,
                                wglMakeCurrent)

        user32 = ctypes.WinDLL("user32")
        user32.GetDC.restype = wintypes.HDC
        user32.GetDC.argtypes = [ctypes.c_void_p]

        pfd = PIXELFORMATDESCRIPTOR()
        pfd.dwFlags = 0x00000004 | 0x00000020 | 0x00000001  # WINDOW|GL|DOUBLE
        pfd.iPixelType = 0                                   # RGBA
        pfd.cColorBits = 24
        pfd.cDepthBits = 16
        pfd.cStencilBits = 8   # Skia lo pide para recortar; sin esto la
        pfd.iLayerType = 0     # superficie se arma pero recorta mal
        self._dc = user32.GetDC(self.winfo_id())
        formato = ChoosePixelFormat(self._dc, pfd)
        if not formato:
            raise SinContexto("ningun formato de pixel sirve en esta maquina")
        SetPixelFormat(self._dc, formato, pfd)
        self._ctx = wglCreateContext(self._dc)
        if not self._ctx:
            raise SinContexto(
                "wglCreateContext fallo: no hay OpenGL utilizable "
                "(pasa en maquinas virtuales y escritorios remotos)")
        wglMakeCurrent(self._dc, self._ctx)

    # -- Linux ---------------------------------------------------------------

    def _contexto_linux(self) -> None:
        import ctypes
        from ctypes import POINTER, c_char_p, c_int, util

        from OpenGL import GL, GLX

        try:
            from OpenGL.raw._GLX import Display
        except ImportError:
            from OpenGL.raw.GLX._types import Display

        x11 = ctypes.cdll.LoadLibrary(util.find_library("X11"))
        x11.XOpenDisplay.argtypes = [c_char_p]
        x11.XOpenDisplay.restype = POINTER(Display)
        self._pantalla = x11.XOpenDisplay(self.winfo_screen().encode("utf-8"))
        if not self._pantalla:
            raise SinContexto("no pude abrir la pantalla de X11")

        mayor, menor = c_int(0), c_int(0)
        GLX.glXQueryVersion(self._pantalla, mayor, menor)

        if (mayor.value, menor.value) < (1, 3):
            # GLX viejo: el camino corto, que es el unico que hay.
            atributos = [GLX.GLX_RGBA, GLX.GLX_DOUBLEBUFFER,
                         GLX.GLX_RED_SIZE, 4, GLX.GLX_GREEN_SIZE, 4,
                         GLX.GLX_BLUE_SIZE, 4, GLX.GLX_DEPTH_SIZE, 16,
                         GLX.GLX_STENCIL_SIZE, 8, 0]
            visual = GLX.glXChooseVisual(
                self._pantalla, 0, (GL.GLint * len(atributos))(*atributos))
            if not visual:
                raise SinContexto("glXChooseVisual no encontro un visual")
            self._ctx = GLX.glXCreateContext(
                self._pantalla, visual, None, GL.GL_TRUE)
            GLX.glXMakeCurrent(self._pantalla, self._wid, self._ctx)
            return

        x11.XDefaultScreen.argtypes = [POINTER(Display)]
        x11.XDefaultScreen.restype = c_int
        pantalla_n = x11.XDefaultScreen(self._pantalla)

        atributos = [GLX.GLX_X_RENDERABLE, 1,
                     GLX.GLX_DRAWABLE_TYPE, GLX.GLX_WINDOW_BIT,
                     GLX.GLX_RENDER_TYPE, GLX.GLX_RGBA_BIT,
                     GLX.GLX_RED_SIZE, 1, GLX.GLX_GREEN_SIZE, 1,
                     GLX.GLX_BLUE_SIZE, 1,
                     # Skia recorta con el stencil buffer. Sin pedirlo aca la
                     # superficie se arma igual y los `clipRect` fallan callados,
                     # que es la peor forma de fallar.
                     GLX.GLX_STENCIL_SIZE, 8,
                     GLX.GLX_DOUBLEBUFFER, 1, 0]
        cuantos = GL.GLint(0)
        configs = GLX.glXChooseFBConfig(
            self._pantalla, pantalla_n,
            (GL.GLint * len(atributos))(*atributos), cuantos)
        if not configs or cuantos.value == 0:
            raise SinContexto("no hay ninguna FBConfig utilizable")

        # Se prefiere la que coincide con el visual que Tk ya le dio a la
        # ventana: si no coinciden, X puede tirar BadMatch al hacer current.
        ideal = int(self.winfo_visualid(), 16)
        mejor = 0
        for i in range(cuantos.value):
            vis = GLX.glXGetVisualFromFBConfig(self._pantalla, configs[i])
            if vis and vis.contents.visualid == ideal:
                mejor = i
                break

        self._ctx = GLX.glXCreateNewContext(
            self._pantalla, configs[mejor], GLX.GLX_RGBA_TYPE, None, GL.GL_TRUE)
        if not self._ctx:
            raise SinContexto("glXCreateNewContext fallo")
        GLX.glXMakeContextCurrent(
            self._pantalla, self._wid, self._wid, self._ctx)


def se_puede() -> tuple[bool, str]:
    """Si este sistema puede tener un contexto, sin abrir ninguna ventana."""
    if MACOS:
        return False, "macOS: Tk y OpenGL no se llevan, y Apple lo dio de baja"
    if not (WINDOWS or LINUX):
        return False, f"sistema no soportado: {sys.platform}"
    try:
        import OpenGL  # noqa: F401
    except ImportError:
        return False, "falta PyOpenGL"
    return True, ""
