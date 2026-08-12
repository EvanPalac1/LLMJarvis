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
    modulo = {"--cli": "eve.integrations", "--hook": "eve.hook_gate", "--panel": "eve.gui"}[flag]
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
