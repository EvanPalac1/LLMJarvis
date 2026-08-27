"""Instrucciones tuyas, en `.md`, que Eve puede consultar.

**Esto NO es un cliente MCP**, y conviene decirlo porque el nombre se parece.
Aquel es un protocolo con un proceso aparte y descubrimiento en vivo, y desde
la 1.19.0 existe de verdad en `eve/mcp.py`. Esto otro es texto que vos escribis
y Eve lee, que es lo mismo que ya hacen `EVE.md` y los addons: sin proceso, sin
protocolo y sin nada ajeno corriendo en tu maquina.

**El freno esta en cuanto viaja, y es la razon de ser del modulo.** Meter los
`.md` enteros en el prompt seria pagarlos en CADA frase que le digas, incluso
en "que hora es". Ya se midio con `ayuda_vocabulario`: el diccionario de
modulos costaba 1 352 caracteres por llamada, y recortarlo a "sabe que existe y
como preguntar" bajo 1 042. Diez skills enteras serian mucho peor que eso.

Por eso lo que viaja es el INDICE --nombre y un renglon-- y el cuerpo se pide
con `E skill ver NOMBRE` cuando hace falta.

Una skill es un `.md` y nada mas. Sin formato propio, sin frontmatter
obligatorio: el titulo sale del primer `#` y el renglon del indice, del primer
parrafo. Inventarle un formato seria pedirte que aprendas uno para poder
escribir un archivo de texto.
"""

import os
import re
import shutil

from . import store

SKILLS_DIR = os.path.join(store.BASE, "skills")

# Un `.md` puede ser cualquier cosa, incluido el manual entero de algo. Lo que
# se lee de una sola vez tiene tope: sin esto, `E skill ver` podria meter un
# archivo de dos megas en el contexto de un saque.
TOPE_CUERPO = 20000

# El indice viaja en todas las llamadas, asi que su renglon tiene tope tambien.
TOPE_RESUMEN = 90


def _carpeta() -> str:
    os.makedirs(SKILLS_DIR, exist_ok=True)
    return SKILLS_DIR


def instaladas() -> list[str]:
    """Los nombres de las skills que hay, ordenados."""
    try:
        archivos = os.listdir(_carpeta())
    except OSError:
        return []
    return sorted(a[:-3] for a in archivos if a.lower().endswith(".md"))


def ruta_de(nombre: str) -> str:
    return os.path.join(_carpeta(), nombre + ".md")


def _primer_parrafo(texto: str) -> str:
    """El renglon que describe la skill, para el indice.

    Se salta el titulo y las lineas vacias. Si el archivo no dice nada util, se
    devuelve cadena vacia y el indice muestra solo el nombre: es preferible a
    inventar una descripcion a partir de la primera linea que haya.
    """
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        # Nada de markdown en el indice: va adentro de un prompt, no se dibuja.
        linea = re.sub(r"[*_`\[\]]", "", linea)
        return linea[:TOPE_RESUMEN]
    return ""


def resumen() -> list[tuple]:
    """[(nombre, renglon)] de todo lo instalado. Es lo que viaja al prompt."""
    salida = []
    for nombre in instaladas():
        try:
            with open(ruta_de(nombre), encoding="utf-8-sig") as f:
                # No se lee entero para armar el indice: alcanza el principio.
                cabeza = f.read(2000)
        except OSError:
            continue
        salida.append((nombre, _primer_parrafo(cabeza)))
    return salida


def leer(nombre: str) -> str:
    """El cuerpo de una skill, para cuando Eve la pide de verdad."""
    nombre = (nombre or "").strip()
    if nombre not in instaladas():
        tengo = ", ".join(instaladas()) or "ninguna"
        raise ValueError(f"No hay una skill que se llame {nombre!r}. Hay: {tengo}.")
    # `utf-8-sig` y no `utf-8`: el Bloc de notas y PowerShell guardan con BOM, y
    # leido como utf-8 esos tres bytes entran como texto. Ya paso con `mostrar`.
    with open(ruta_de(nombre), encoding="utf-8-sig") as f:
        cuerpo = f.read(TOPE_CUERPO + 1)
    if len(cuerpo) > TOPE_CUERPO:
        cuerpo = cuerpo[:TOPE_CUERPO] + "\n\n[...cortado, la skill sigue]"
    return cuerpo


def revisar(ruta: str) -> tuple:
    """(sirve, motivo) para un archivo que alguien quiere importar."""
    if not ruta.lower().endswith((".md", ".markdown", ".txt")):
        return False, "Una skill es un archivo de texto: .md, .markdown o .txt"
    if not os.path.exists(ruta):
        return False, "No existe ese archivo."
    try:
        tam = os.path.getsize(ruta)
    except OSError as exc:
        return False, f"No se puede leer: {exc}"
    if tam == 0:
        return False, "El archivo esta vacio."
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            f.read(4096)
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"No parece texto: {exc}"
    return True, ""


def importar(ruta: str, nombre: str = "") -> str:
    """Copia un `.md` a la carpeta de skills. Devuelve su nombre."""
    sirve, motivo = revisar(ruta)
    if not sirve:
        raise ValueError(motivo)
    base = os.path.basename(ruta)
    clave = (nombre or os.path.splitext(base)[0]).strip()
    if not clave or any(c in clave for c in '\\/:*?"<>|'):
        raise ValueError("Ese nombre no sirve para un archivo.")
    if clave in instaladas():
        raise ValueError(f"Ya hay una skill que se llama {clave!r}.")
    shutil.copyfile(ruta, ruta_de(clave))
    return clave


def borrar(nombre: str) -> None:
    if nombre not in instaladas():
        raise ValueError(f"No hay una skill que se llame {nombre!r}.")
    os.remove(ruta_de(nombre))
