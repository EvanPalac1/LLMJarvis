"""Lo unico que sabe en que sistema operativo corre Eve.

El resto del proyecto llama a estas funciones en vez de importar `ctypes.windll`
o `os.startfile` directo. Asi agregar un sistema es tocar un archivo, y los
modulos que si son especificos de Windows (Outlook, WhatsApp, Discord) pueden
degradarse solos con `@solo_windows` en vez de reventar al importarse.
"""

import os
import shutil
import subprocess
import sys

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")

NOMBRE = "Windows" if WINDOWS else "macOS" if MACOS else "Linux" if LINUX else sys.platform


APP = "LLMJarvis"


def congelado() -> bool:
    """True si corre desde un binario empaquetado y no desde el codigo."""
    return getattr(sys, "frozen", False)


# CREATE_NO_WINDOW. Sin esto, cada subprocess de una app sin consola (la bandeja,
# el panel) abre y cierra una ventana negra en pantalla. Con algo periodico —la
# barra de estado consulta cada 5 segundos— es un parpadeo constante.
_SIN_VENTANA = 0x08000000 if WINDOWS else 0


def correr(argv, **kwargs):
    """subprocess.run que no abre una consola en Windows."""
    if WINDOWS:
        kwargs.setdefault("creationflags", _SIN_VENTANA)
    return subprocess.run(argv, **kwargs)


def lanzar(argv, **kwargs):
    """subprocess.Popen que no abre una consola en Windows."""
    if WINDOWS:
        kwargs.setdefault("creationflags", kwargs.pop("creationflags", 0) | _SIN_VENTANA)
    return subprocess.Popen(argv, **kwargs)


def datos_usuario() -> str:
    """Carpeta escribible para config, agenda, historial y voces.

    Instalado en Program Files (o /opt) el directorio del programa es de solo
    lectura: si los datos vivieran ahi, la app no arrancaria. Cada sistema tiene
    su lugar para esto y hay que usarlo.
    """
    if WINDOWS:
        raiz = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif MACOS:
        raiz = os.path.expanduser("~/Library/Application Support")
    else:
        raiz = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    ruta = os.path.join(raiz, APP)
    os.makedirs(ruta, exist_ok=True)
    return ruta


def fps_sugerido() -> int:
    """Cuadros por segundo razonables para esta maquina.

    30 en x86, 20 en ARM. No es una medicion de esta maquina --hacerla en cada
    arranque costaria mas que lo que ahorra-- sino el punto de partida: quien
    quiera otro numero lo pone en `ui_fps`, que para eso existe.
    """
    import platform

    return 20 if platform.machine().lower() in ("arm64", "aarch64") else 30


def fps(cfg: dict | None = None) -> int:
    """Los fps efectivos: lo que diga la config, o lo que sugiera la maquina."""
    pedidos = int((cfg or {}).get("ui_fps", 0) or 0)
    if pedidos <= 0:
        return fps_sugerido()
    # Un tope por arriba y por abajo: 120 fps de un cartel no los ve nadie, y
    # menos de 5 deja la onda a tirones sin que se entienda por que.
    return max(5, min(120, pedidos))


def recursos() -> str:
    """Carpeta de solo lectura con lo que viaja junto al programa (EVE.md, iconos).

    Congelado es el temporal que arma PyInstaller; desde el codigo, la raiz del
    repositorio. Asi correr `python main.py` sigue funcionando igual.
    """
    if congelado():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ejecutable_app() -> str:
    """Ruta del binario principal, para relanzarse a si mismo."""
    return sys.executable


def comando_propio(flag: str) -> list[str]:
    """argv para invocar una sub-herramienta de Eve.

    Congelado no hay `python` ni archivos `.py` sueltos: el propio binario
    despacha por flag (ver main.py). Desde el codigo se llama al modulo.
    """
    if congelado():
        return [sys.executable, flag]
    modulo = {"--cli": "eve.integrations", "--hook": "eve.hook_gate",
              "--panel": "eve.gui", "--overlay": "eve.overlay",
            "--consola": "eve.consola"}[flag]
    exe = sys.executable.replace("pythonw.exe", "python.exe")
    return [exe, "-m", modulo]


def solo_windows(func):
    """Devuelve un mensaje util en vez de fallar en macOS o Linux."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not WINDOWS:
            return (
                f"'{func.__name__}' solo funciona en Windows; aca corre {NOMBRE}. "
                "Deci esto en voz alta y no intentes rodearlo."
            )
        return func(*args, **kwargs)

    return wrapper


# --- abrir cosas -----------------------------------------------------------

def abrir(uri: str) -> None:
    """Abre una URI, archivo o app con el handler del sistema."""
    if WINDOWS:
        os.startfile(uri)  # noqa: S606 - handler registrado del SO
    elif MACOS:
        subprocess.Popen(["open", uri])
    else:
        subprocess.Popen(["xdg-open", uri])


def shell_cmd(comando: str) -> list[str]:
    """argv para correr una linea de shell en este sistema."""
    if WINDOWS:
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando]
    return ["/bin/sh", "-c", comando]


def nombre_shell() -> str:
    return "PowerShell" if WINDOWS else "sh"


# --- dialogos --------------------------------------------------------------
# Se usan desde hilos de fondo y desde procesos sueltos (el hook de Claude Code),
# asi que no pueden depender de que exista un mainloop de tkinter andando.

def preguntar(mensaje: str, titulo: str = "LLMJarvis") -> bool:
    """Si/no modal. False si el usuario dice que no o si no hay como preguntar."""
    if WINDOWS:
        import ctypes

        MB_YESNO, MB_ICONWARNING, MB_TOPMOST, IDYES = 0x04, 0x30, 0x40000, 6
        return (
            ctypes.windll.user32.MessageBoxW(
                0, mensaje, titulo, MB_YESNO | MB_ICONWARNING | MB_TOPMOST
            )
            == IDYES
        )
    if MACOS:
        guion = (
            f'display dialog {_as_applescript(mensaje)} with title {_as_applescript(titulo)} '
            'buttons {"No", "Si"} default button "No" with icon caution'
        )
        r = correr(["osascript", "-e", guion], capture_output=True, text=True)
        return "Si" in r.stdout
    return _tk_preguntar(mensaje, titulo)


def avisar(mensaje: str, titulo: str = "LLMJarvis", error: bool = False) -> None:
    if WINDOWS:
        import ctypes

        # Sin MB_SYSTEMMODAL: hacia que el dialogo quedara trabado cuando lo
        # abria un hilo que ya estaba bombeando mensajes. MB_TOPMOST alcanza.
        icono = 0x10 if error else 0x40  # ICONERROR / ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(0, mensaje, titulo, icono | 0x40000)
        return
    if MACOS:
        guion = (
            f'display dialog {_as_applescript(mensaje)} with title {_as_applescript(titulo)} '
            'buttons {"OK"} default button "OK"'
        )
        correr(["osascript", "-e", guion], capture_output=True)
        return
    _tk_avisar(mensaje, titulo)


def _as_applescript(texto: str) -> str:
    """AppleScript no tiene escapes: solo comillas dobles y backslash."""
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'


_GUION_DIALOGO = (
    "import tkinter,sys;from tkinter import messagebox;"
    "r=tkinter.Tk();r.withdraw();"
    "sys.exit(0 if (messagebox.askyesno(sys.argv[2], sys.argv[3])"
    " if sys.argv[1]=='pregunta' else"
    " messagebox.showinfo(sys.argv[2], sys.argv[3]) or True) else 1)"
)


def _argv_dialogo(tipo: str, titulo: str, mensaje: str) -> list[str]:
    """Como invocar el dialogo en otro proceso.

    Congelado, sys.executable es el propio Eve y no entiende `-c`: le pasaba el
    guion como argumento suelto y main.py, al no ver un flag, arrancaba un
    asistente entero de nuevo en vez de mostrar la pregunta. Por eso va por
    nuestro propio flag --dialogo.
    """
    if congelado():
        return [sys.executable, "--dialogo", tipo, titulo, mensaje]
    return [sys.executable.replace("pythonw.exe", "python.exe"),
            "-c", _GUION_DIALOGO, tipo, titulo, mensaje]


def dialogo_cli(argv: list[str]) -> int:
    """Implementa `Eve --dialogo pregunta|aviso TITULO MENSAJE`."""
    import tkinter
    from tkinter import messagebox

    tipo, titulo, mensaje = (argv + ["aviso", "LLMJarvis", ""])[:3]
    raiz = tkinter.Tk()
    raiz.withdraw()
    if tipo == "pregunta":
        return 0 if messagebox.askyesno(titulo, mensaje) else 1
    messagebox.showinfo(titulo, mensaje)
    return 0


def _tk_preguntar(mensaje: str, titulo: str) -> bool:
    """Linux: tkinter en una raiz propia y efimera.

    Va en un proceso aparte porque tkinter no tolera que lo llamen desde un hilo
    que no sea el suyo, y estos dialogos salen de hilos de fondo.
    """
    return correr(_argv_dialogo("pregunta", titulo, mensaje)).returncode == 0


def _tk_avisar(mensaje: str, titulo: str) -> None:
    correr(_argv_dialogo("aviso", titulo, mensaje))


# --- portapapeles ----------------------------------------------------------

def copiar(texto: str) -> str | None:
    """Pone texto en el portapapeles. Devuelve lo que habia, para restaurarlo."""
    if WINDOWS:
        import win32clipboard
        import win32con

        previo = None
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                previo = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, texto)
        finally:
            win32clipboard.CloseClipboard()
        return previo

    herramienta = ["pbcopy"] if MACOS else ["xclip", "-selection", "clipboard"]
    leer = ["pbpaste"] if MACOS else ["xclip", "-selection", "clipboard", "-o"]
    previo = None
    if shutil.which(leer[0]):
        previo = correr(leer, capture_output=True, text=True).stdout
    if shutil.which(herramienta[0]):
        correr(herramienta, input=texto, text=True)
    return previo


def restaurar_portapapeles(previo) -> None:
    if previo is None:
        return
    try:
        copiar(previo)
    except Exception:  # noqa: BLE001 - otro proceso puede tener el portapapeles
        pass


# --- teclado ---------------------------------------------------------------

def backend_teclado() -> str:
    """`keyboard` no anda en macOS y en Linux exige root; ahi va `pynput`."""
    return "keyboard" if WINDOWS else "pynput"


def hook_teclado(callback):
    """Engancha UN hook global. `callback(nombre_tecla, "down"|"up")`.

    Un solo hook filtrado por nosotros, no uno por tecla: `keyboard` comparte la
    entrada `_hooks[key]` entre press y release, y desenganchar el segundo tira
    KeyError antes de sacar el callback, dejando viva la tecla anterior.

    Devuelve un handle opaco para `unhook_teclado`.
    """
    if WINDOWS:
        import keyboard

        def puente(ev):
            tipo = "down" if ev.event_type == keyboard.KEY_DOWN else "up"
            callback(ev.name, tipo)

        return ("keyboard", keyboard.hook(puente, suppress=False))

    from pynput import keyboard as pk

    def nombre(tecla) -> str:
        if hasattr(tecla, "char") and tecla.char:
            return tecla.char.lower()
        return str(tecla).replace("Key.", "").lower()

    listener = pk.Listener(
        on_press=lambda t: callback(nombre(t), "down"),
        on_release=lambda t: callback(nombre(t), "up"),
    )
    listener.start()
    return ("pynput", listener)


def unhook_teclado(handle) -> None:
    if not handle:
        return
    backend, obj = handle
    try:
        if backend == "keyboard":
            import keyboard

            keyboard.unhook(obj)
        else:
            obj.stop()
    except Exception:  # noqa: BLE001 - desenganchar dos veces no debe romper nada
        pass


def notas_permisos() -> str:
    """Que tiene que habilitar el usuario para que el atajo global funcione."""
    if MACOS:
        return (
            "macOS pide permiso para leer el teclado: Ajustes del Sistema > Privacidad y "
            "seguridad > Accesibilidad, y agrega la app (o la terminal desde la que corras Eve)."
        )
    if LINUX:
        return (
            "En Linux el atajo global necesita acceso a /dev/input (grupo 'input' o root), y "
            "bajo Wayland solo llegan los eventos de apps sobre Xwayland."
        )
    return ""


def resumen() -> str:
    return f"{NOMBRE} | shell: {nombre_shell()} | teclado: {backend_teclado()}"


# --- ventanas que no molestan ----------------------------------------------
# Unico lugar que toca la API de ventanas del sistema.

_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020   # los clics la atraviesan
_WS_EX_TOOLWINDOW = 0x00000080    # no sale en Alt+Tab ni en la barra de tareas
_WS_EX_LAYERED = 0x00080000
_WS_EX_NOACTIVATE = 0x08000000    # no toma el foco al aparecer


def hwnd_de(ventana) -> int:
    """HWND real de un Toplevel de tk. 0 si no es Windows o no se pudo."""
    if not WINDOWS:
        return 0
    import ctypes

    ventana.update_idletasks()
    ident = ventana.winfo_id()
    # Con overrideredirect la jerarquia cambia segun la version de Tk: a veces
    # winfo_id() ya es la ventana de nivel superior y a veces es una hija.
    return ctypes.windll.user32.GetParent(ident) or ident


def ventana_fantasma(ventana, atraviesan_los_clics: bool = True) -> bool:
    """Deja la ventana encima sin robarle el foco a nada. True si se aplico.

    Es lo que hace que el overlay pueda aparecer mientras jugas sin sacarte del
    juego. Con `atraviesan_los_clics` los clics llegan al programa de abajo; se
    apaga solo mientras el usuario arrastra el overlay para reubicarlo.

    Fuera de Windows devuelve False: X11 necesita regiones de entrada por shape
    y macOS `ignoresMouseEvents`, que tk no expone. Ahi la ventana igual queda
    encima y sin borde, pero puede robar el foco y se come los clics.
    """
    if not WINDOWS:
        return False
    import ctypes

    hwnd = hwnd_de(ventana)
    if not hwnd:
        return False
    u = ctypes.windll.user32
    # Se AGREGAN bits a los que ya hay, no se reemplaza el estilo entero: tk pone
    # WS_EX_LAYERED por su cuenta para el '-alpha' y le asocia unos atributos.
    # Pisarlo dejaba una ventana layered sin atributos, o sea invisible: se
    # comportaba bien (no robaba foco, dejaba pasar los clics) pero no se veia.
    estilos = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    estilos |= _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE
    if atraviesan_los_clics:
        estilos |= _WS_EX_TRANSPARENT
    else:
        estilos &= ~_WS_EX_TRANSPARENT
    u.SetWindowLongW(hwnd, _GWL_EXSTYLE, estilos)
    # SWP_FRAMECHANGED, y HWND_TOPMOST para que el cambio surta efecto ya.
    u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020)
    return True


# --- tipografias -----------------------------------------------------------
# tkinter pide la familia ("Constantia") y PIL pide el archivo ("constan.ttf").
# No hay forma de derivar uno del otro: hay que preguntarle al sistema. Sin
# esto, los modulos dibujados con PIL salen con la tipografia por defecto de la
# libreria mientras el resto del cartel usa la elegida en el panel, y se nota.
_FUENTES: dict = {}

# Lo que se usa cuando el usuario no eligio ninguna.
_FUENTE_SISTEMA = {"win32": "segoeui.ttf", "darwin": "Helvetica.ttc"}


def archivo_de_fuente(familia: str = "", negrita: bool = False) -> str:
    """Ruta (o nombre que PIL sepa abrir) del TTF de una familia. "" si no hay."""
    clave = (familia or "", bool(negrita))
    if clave in _FUENTES:
        return _FUENTES[clave]
    ruta = _buscar_fuente(familia, negrita)
    _FUENTES[clave] = ruta
    return ruta


def _buscar_fuente(familia: str, negrita: bool) -> str:
    familia = (familia or "").strip()
    # "(la del sistema)" es la etiqueta del panel para "no elegi ninguna".
    if not familia or familia.startswith("("):
        return _FUENTE_SISTEMA.get(sys.platform, "DejaVuSans.ttf")
    if WINDOWS:
        hallado = _fuente_windows(familia, negrita)
        if hallado:
            return hallado
    elif LINUX:
        hallado = _fuente_fontconfig(familia, negrita)
        if hallado:
            return hallado
    # Ultimo intento: nombres derivados. Sirve para las familias cuyo archivo se
    # llama parecido, que son bastantes.
    sin_espacios = familia.replace(" ", "")
    for base in (sin_espacios, sin_espacios.lower(), familia, familia.lower()):
        for ext in (".ttf", ".ttc", ".otf"):
            if _pil_abre(base + ext):
                return base + ext
    return ""


def _pil_abre(nombre: str) -> bool:
    try:
        from PIL import ImageFont

        ImageFont.truetype(nombre, 12)
    except Exception:  # noqa: BLE001 - falta el archivo o PIL no lo entiende
        return False
    return True


def _fuente_windows(familia: str, negrita: bool) -> str:
    """El registro mapea "Constantia (TrueType)" -> "constan.ttf"."""
    try:
        import winreg
    except ImportError:
        return ""
    buscados = [familia.lower() + (" bold" if negrita else "")]
    if negrita:
        buscados.append(familia.lower())   # sin negrita antes que nada
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(
                raiz, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            ) as k:
                total = winreg.QueryInfoKey(k)[1]
                entradas = {}
                for i in range(total):
                    nombre, valor, _ = winreg.EnumValue(k, i)
                    # "Constantia Bold (TrueType)" -> "constantia bold"
                    limpio = nombre.split("(")[0].strip().lower()
                    entradas[limpio] = valor
        except OSError:
            continue
        for quiero in buscados:
            archivo = entradas.get(quiero)
            if archivo:
                completo = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                        "Fonts", archivo)
                return completo if os.path.exists(completo) else archivo
    return ""


def _fuente_fontconfig(familia: str, negrita: bool) -> str:
    """En Linux lo sabe `fc-match`, que viene con cualquier escritorio."""
    patron = familia + (":bold" if negrita else "")
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}", patron],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    ruta = (r.stdout or "").strip()
    return ruta if ruta and os.path.exists(ruta) else ""


def monitores() -> list[dict]:
    """Los monitores conectados: `[{x, y, ancho, alto, trabajo, principal}]`.

    `trabajo` es el rectangulo sin la barra de tareas; en los sistemas donde no
    se puede saber, es igual al completo. El principal va primero, y el resto
    ordenado por posicion, para que el numero que elige el usuario sea estable
    entre arranques.

    **tkinter no da esta lista en ningun sistema.** `winfo_screenwidth` es el
    monitor principal y `winfo_vroot*` es el rectangulo de todos juntos, que es
    lo que ya usa `overlay._escritorio()`. Asi que hay una via por sistema, y
    las tres usan algo que el proyecto ya tiene:

      Windows  EnumDisplayMonitors por ctypes, igual que los dialogos nativos
      macOS    Quartz, que viaja como dependencia dura de pynput en darwin
      Linux    `xrandr --listmonitors`, el mismo criterio que `fc-match`

    Si alguna falla, se devuelve UNA sola pantalla con el rectangulo virtual.
    Un cartel en el monitor equivocado es molesto; uno fuera de la vista, no se
    puede arreglar sin editar la config a mano.
    """
    try:
        crudos = _monitores_windows() if WINDOWS else (
            _monitores_macos() if MACOS else _monitores_linux())
    except Exception:  # noqa: BLE001 - cualquier motivo da lo mismo: se degrada
        crudos = []
    if not crudos:
        return []
    principal = [m for m in crudos if m["principal"]]
    resto = sorted((m for m in crudos if not m["principal"]),
                   key=lambda m: (m["x"], m["y"]))
    return principal + resto


def _monitores_windows() -> list[dict]:
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    salida = []
    PROTO = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(RECT), wintypes.LPARAM)

    def por_cada(hmon, _hdc, _rect, _datos):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r, t = info.rcMonitor, info.rcWork
            salida.append({
                "x": r.left, "y": r.top,
                "ancho": r.right - r.left, "alto": r.bottom - r.top,
                "trabajo": (t.left, t.top, t.right - t.left, t.bottom - t.top),
                "principal": bool(info.dwFlags & 1),   # MONITORINFOF_PRIMARY
            })
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(0, 0, PROTO(por_cada), 0)
    return salida


def _monitores_macos() -> list[dict]:
    # Quartz llega por pynput, que en darwin depende de pyobjc-framework-Quartz.
    from Quartz import CGDisplayBounds, CGGetActiveDisplayList, CGMainDisplayID

    ok, ids, cuantos = CGGetActiveDisplayList(16, None, None)
    if ok != 0:
        return []
    principal = CGMainDisplayID()
    salida = []
    for ident in list(ids)[:cuantos]:
        caja = CGDisplayBounds(ident)
        x, y = int(caja.origin.x), int(caja.origin.y)
        w, h = int(caja.size.width), int(caja.size.height)
        salida.append({"x": x, "y": y, "ancho": w, "alto": h,
                       "trabajo": (x, y, w, h),  # el Dock no se puede restar asi
                       "principal": ident == principal})
    return salida


def _monitores_linux() -> list[dict]:
    import re
    import shutil
    import subprocess

    if not shutil.which("xrandr"):
        return []
    salida = subprocess.run(["xrandr", "--listmonitors"], capture_output=True,
                            text=True, timeout=5).stdout
    monitores = []
    # ` 0: +*eDP-1 1920/344x1080/193+0+0  eDP-1`  --el * marca la primaria
    patron = re.compile(r"^\s*\d+:\s+\+(\*?)\S*\s+(\d+)/\d+x(\d+)/\d+\+(\d+)\+(\d+)")
    for linea in salida.splitlines():
        m = patron.match(linea)
        if not m:
            continue
        w, h, x, y = (int(g) for g in m.groups()[1:])
        monitores.append({"x": x, "y": y, "ancho": w, "alto": h,
                          "trabajo": (x, y, w, h),
                          "principal": m.group(1) == "*"})
    return monitores
