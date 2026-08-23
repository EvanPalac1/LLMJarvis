"""Addons: comandos que se le agregan al agente sin tocar el nucleo.

Un addon expone acciones y el texto que el modelo necesita para usarlas, y Eve
las llama con `E addon NOMBRE ACCION ...`. Un solo subcomando generico en vez de
uno por addon: asi agregar uno no obliga a tocar el parser ni el despachador.

Contrato de un addon (todo opcional salvo NOMBRE y ejecutar):

    NOMBRE = "spotify"
    DESCRIPCION = "una linea para el panel"
    CLAVES = [("spotify_client_id", "Client ID", False), ...]  # (clave, etiqueta, secreta)
    def disponible(cfg) -> tuple[bool, str]   # (se expone?, por que no)
    def prompt(cfg) -> str                    # lo que ve el modelo
    def ejecutar(accion: str, args: list[str], cfg: dict) -> str

Vienen de dos lados: los integrados, que viajan con el programa, y los del
usuario, que son archivos `.py` sueltos en `<datos>/addons/`. Los del usuario se
importan y corren dentro de Eve: son codigo con los mismos permisos que el
programa, asi que solo hay que poner ahi cosas en las que se confie.
"""

import os
import traceback

from .. import store

INTEGRADOS = ("spotify", "obs")
CARPETA_USUARIO = os.path.join(store.BASE, "addons")

_cache: dict = {}


def _integrados() -> dict:
    """Los que vienen con el programa.

    Importados por nombre y no descubriendo la carpeta: PyInstaller no ve los
    imports dinamicos, y un addon que solo falta en la version instalada seria
    de esas fallas que aparecen tarde.
    """
    modulos = {}
    for nombre in INTEGRADOS:
        try:
            modulos[nombre] = __import__(f"eve.addons.{nombre}", fromlist=[nombre])
        except Exception:  # noqa: BLE001 - un addon roto no puede tumbar a Eve
            traceback.print_exc()
    return modulos


def huella(ruta: str) -> str:
    """Los primeros 12 hex del sha1 del archivo. "" si no se pudo leer."""
    import hashlib

    try:
        with open(ruta, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:12]
    except OSError:
        return ""


def _aprobados(cfg=None) -> dict:
    cfg = cfg if cfg is not None else store.load_config()
    salida = {}
    for parte in str(cfg.get("addons_aprobados", "")).split(","):
        nombre, _, marca = parte.strip().partition(":")
        if nombre and marca:
            salida[nombre] = marca
    return salida


def pendientes() -> list:
    """Los addons del usuario que estan sin revisar o cambiaron desde entonces.

    Devuelve [(nombre_archivo, ruta, huella)].
    """
    if not os.path.isdir(CARPETA_USUARIO):
        return []
    aprobados = _aprobados()
    salida = []
    for archivo in sorted(os.listdir(CARPETA_USUARIO)):
        if not archivo.endswith(".py") or archivo.startswith("_"):
            continue
        ruta = os.path.join(CARPETA_USUARIO, archivo)
        marca = huella(ruta)
        if aprobados.get(archivo[:-3]) != marca:
            salida.append((archivo[:-3], ruta, marca))
    return salida


def aprobar(nombre: str, marca: str = "") -> str:
    """Deja pasar este addon tal como esta ahora."""
    ruta = os.path.join(CARPETA_USUARIO, nombre + ".py")
    marca = marca or huella(ruta)
    if not marca:
        return f"No encuentro {nombre}.py"
    cfg = store.load_config()
    aprobados = _aprobados(cfg)
    aprobados[nombre] = marca
    cfg["addons_aprobados"] = ",".join(f"{n}:{m}" for n, m in sorted(aprobados.items()))
    store.save_config(cfg)
    _cache.clear()
    return f"{nombre} aprobado."


def revocar(nombre: str) -> str:
    """Saca la aprobacion de un addon: vuelve a la lista de sin revisar.

    Aprobar era un camino de ida. Una vez que dabas el si, la unica forma de
    volver atras era editar `config.json` a mano --y desde que
    `addons_aprobados` es una de las claves que Eve no puede escribir, ella
    tampoco podia deshacerlo. Una decision de seguridad que no se puede desandar
    es una que la gente evita tomar.

    El archivo no se toca: se saca de la lista y nada mas. Borrarle el `.py` a
    alguien porque dijo "ya no confio" seria decidir por el.
    """
    cfg = store.load_config()
    aprobados = _aprobados(cfg)
    if nombre not in aprobados:
        return f"{nombre} no estaba aprobado."
    del aprobados[nombre]
    cfg["addons_aprobados"] = ",".join(f"{n}:{m}" for n, m in sorted(aprobados.items()))
    store.save_config(cfg)
    _cache.clear()
    return f"{nombre} vuelve a la lista de sin revisar. El archivo sigue ahi."


def aprobados_ahora() -> list[str]:
    """Los nombres aprobados hoy, para que el panel los pueda mostrar."""
    return sorted(_aprobados(store.load_config()))


def _del_usuario() -> dict:
    """Los `.py` sueltos de la carpeta de datos, SOLO los aprobados.

    Un archivo aca es codigo que corre con los permisos del usuario y no pasa
    por `safety.py`. Mientras los escribiera una persona, cargarlos derecho era
    razonable; desde que Eve puede escribirlos, cargar sin mirar es automatizar
    el unico agujero que le queda al freno. La huella cambia con el archivo, asi
    que editar uno aprobado lo vuelve a dejar afuera.
    """
    modulos = {}
    if not os.path.isdir(CARPETA_USUARIO):
        return modulos
    import importlib.util

    aprobados = _aprobados()
    for archivo in sorted(os.listdir(CARPETA_USUARIO)):
        if not archivo.endswith(".py") or archivo.startswith("_"):
            continue
        nombre = archivo[:-3]
        ruta = os.path.join(CARPETA_USUARIO, archivo)
        if aprobados.get(nombre) != huella(ruta):
            print(f"[addon] {archivo} esta sin aprobar: no se carga. "
                  f"Revisalo en el panel > Addons.")
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"eve_addon_{nombre}", ruta
            )
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            modulos[getattr(modulo, "NOMBRE", nombre)] = modulo
        except Exception:  # noqa: BLE001 - idem: se avisa y se sigue
            print(f"[addon] no pude cargar {archivo}:")
            traceback.print_exc()
    return modulos


def todos(recargar: bool = False) -> dict:
    """{nombre: modulo} de todo lo que se pudo cargar, activo o no."""
    if recargar or not _cache:
        _cache.clear()
        _cache.update({**_integrados(), **_del_usuario()})
    return dict(_cache)


def activos(cfg: dict) -> dict:
    """Los que el usuario dejo prendidos y ademas se pueden usar ahora."""
    elegidos = str(cfg.get("addons_activos", "")).strip()
    permitidos = {x.strip() for x in elegidos.split(",") if x.strip()}
    salida = {}
    for nombre, modulo in todos().items():
        if permitidos and nombre not in permitidos:
            continue
        puede, _ = estado(modulo, cfg)
        if puede:
            salida[nombre] = modulo
    return salida


def estado(modulo, cfg: dict) -> tuple[bool, str]:
    """(se puede usar?, por que no). Sin `disponible`, se asume que si."""
    fn = getattr(modulo, "disponible", None)
    if fn is None:
        return True, ""
    try:
        return fn(cfg)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def prompt(cfg: dict) -> str:
    """El bloque que se suma al system prompt. Vacio si no hay addons activos.

    Vacio de verdad cuando no hay nada: este texto viaja en cada llamada al
    modelo, y una seccion con un titulo y nada abajo es peaje puro.
    """
    partes = []
    for nombre, modulo in sorted(activos(cfg).items()):
        fn = getattr(modulo, "prompt", None)
        texto = (fn(cfg) if callable(fn) else getattr(modulo, "PROMPT", "")) or ""
        if texto.strip():
            partes.append(texto.strip())
    if not partes:
        return ""
    return "\n\n## Addons\n\n" + "\n".join(partes)


def ejecutar(nombre: str, accion: str, args: list[str], cfg: dict) -> str:
    modulos = todos()
    if nombre not in modulos:
        conocidos = ", ".join(sorted(modulos)) or "ninguno"
        return f"No existe el addon {nombre!r}. Hay: {conocidos}."
    modulo = modulos[nombre]
    puede, motivo = estado(modulo, cfg)
    if not puede:
        return f"El addon {nombre!r} no esta listo: {motivo}"
    fn = getattr(modulo, "ejecutar", None)
    if fn is None:
        return f"El addon {nombre!r} no sabe ejecutar nada."

    # Un addon puede declarar que acciones suyas son riesgosas, con el motivo.
    # Se pregunta con el mismo freno que el resto: hasta ahora esta ruta lo
    # evadia entera, y era la unica del programa que lo hacia.
    motivo = (getattr(modulo, "RIESGOS", {}) or {}).get(accion)
    if motivo and cfg.get("confirm_destructive", True):
        # `..` y no `.`: esto vive en `eve/addons/__init__.py`, asi que un
        # `from . import plataforma` busca `eve.addons.plataforma`, que no
        # existe. La confirmacion reventaba con ImportError en vez de preguntar
        # --falla cerrada, pero el usuario veia un crash-- y nadie lo noto
        # porque ningun addon del repo declara RIESGOS y no habia test.
        from .. import plataforma

        detalle = f"{nombre} {accion} {' '.join(map(str, args))}"[:400]
        if not plataforma.preguntar(f"{motivo}\n\n{detalle}",
                                    f"Confirmar: {nombre} {accion}"):
            store.log_action(f"addon/{nombre}", detalle, "DENEGADO por el usuario")
            return "El usuario no dejo hacer eso."
    try:
        return str(fn(accion, args, cfg))
    except Exception as exc:  # noqa: BLE001 - el error vuelve al modelo, no explota
        traceback.print_exc()
        return f"ERROR en el addon {nombre}: {type(exc).__name__}: {exc}"
