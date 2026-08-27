"""Frases tuyas que hacen algo fijo, escritas en `Comandos.md`.

Hoy toda frase transcrita va derecho al modelo (`listener.py`, `motor.ask`).
Para "prende el server" eso es pagar una llamada, esperar uno o dos segundos y
confiar en que interprete bien algo que no tiene ninguna ambiguedad. Este
modulo se mete JUSTO ANTES: si lo que dijiste coincide con un comando tuyo, se
resuelve aca y el modelo no se entera.

**El archivo es markdown y nada mas.** El titulo es lo que decis --varias
formas separadas por `|`-- y debajo va una linea `tipo: valor`. No hay
frontmatter ni un formato propio que aprender:

    ## prende el server | arranca el server
    sistema: D:\\Server\\Start.bat

    ## armame el parte | resumen del dia
    prompt: Resumi lo que hice hoy en tres bloques: hecho, trabado, proximo.

    ## modo concentracion
    accion: abrir Spotify

Los tres tipos y por que son tres y no uno:

  `accion`   una de una lista CERRADA. Ninguna es destructiva, asi que no pide
             aprobacion. No llama al modelo.
  `prompt`   la frase corta se reemplaza por un texto largo y ESO va al modelo.
             Es el unico de los tres que paga una llamada, y se dice.
  `sistema`  corre lo que le pongas. Pasa por el mismo freno que los addons:
             aprobacion por hash del texto exacto, y si lo editas hay que
             volver a aprobarlo. Sin aprobar, la frase no hace nada.

La coincidencia es EXACTA sobre el texto normalizado --sin mayusculas, sin
acentos, sin puntuacion de mas-- y no difusa a proposito. Un comando que a
veces agarra es peor que uno que no existe: la gracia de esto es que sepas de
antemano que va a pasar.
"""

import hashlib
import os
import re
import subprocess
import unicodedata

from . import store

RUTA = os.path.join(store.BASE, "Comandos.md")

TIPOS = ("accion", "prompt", "sistema")

# Las acciones que un comando `accion` puede pedir. Cerrada a proposito: una
# que corriera cualquier cosa seria un `sistema` sin su freno.
ACCIONES = ("abrir", "panel", "cartel", "mostrar")

PLANTILLA = """# Comandos por voz

Cada `##` es lo que decis. Varias formas de decir lo mismo van separadas
por `|`. Debajo, una linea `tipo: valor`.

Tipos: `accion` (lista cerrada, no llama al modelo), `prompt` (reemplaza tu
frase por un texto largo y lo manda al modelo), `sistema` (corre un comando;
hay que aprobarlo en el panel antes de que ande).

## modo concentracion | modo foco
accion: abrir Spotify

## armame el parte | resumen del dia
prompt: Resumi lo que hice hoy en tres bloques: hecho, trabado, y que sigue.
"""


def normalizar(texto: str) -> str:
    """Para comparar: sin mayusculas, sin acentos, sin puntuacion, un espacio.

    Se normaliza de los dos lados --lo escrito y lo dicho-- porque el
    transcriptor pone puntos y comas donde quiere y escribe "concentracion" o
    "concentración" segun el dia. Comparar crudo dejaria el comando andando a
    veces, que es la peor version de esto.
    """
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", " ", texto, flags=re.UNICODE)
    return re.sub(r"\s+", " ", texto).strip()


def _leer_archivo() -> str:
    # `utf-8-sig`: el Bloc de notas y PowerShell guardan con BOM, y leido como
    # utf-8 esos tres bytes entran como texto. Ya paso con `mostrar`.
    try:
        with open(RUTA, encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return ""


def leer() -> list:
    """Los comandos del archivo. Uno roto se saltea, no tumba a los demas."""
    comandos = []
    actual = None
    for numero, linea in enumerate(_leer_archivo().splitlines(), 1):
        cabeza = linea.strip()
        if cabeza.startswith("## "):
            actual = {"frases": [f.strip() for f in cabeza[3:].split("|") if f.strip()],
                      "tipo": "", "valor": "", "linea": numero}
            if actual["frases"]:
                comandos.append(actual)
            else:
                actual = None
            continue
        if actual is None or actual["tipo"]:
            continue
        m = re.match(r"([a-z]+)\s*:\s*(.+)$", cabeza)
        if m and m.group(1) in TIPOS:
            actual["tipo"] = m.group(1)
            actual["valor"] = m.group(2).strip()
    # Un `##` sin su linea de tipo no es un comando: es un titulo suelto.
    return [c for c in comandos if c["tipo"] and c["valor"]]


def buscar(texto: str) -> dict:
    """El comando cuya frase coincide con lo dicho, o {}."""
    dicho = normalizar(texto)
    if not dicho:
        return {}
    for cmd in leer():
        for frase in cmd["frases"]:
            if normalizar(frase) == dicho:
                return cmd
    return {}


def firma(cmd: dict) -> str:
    """Los 12 hex del sha1 de lo que el comando HACE.

    Del tipo y el valor, no de la frase: cambiarle el texto al comando tiene
    que invalidar la aprobacion --es lo que se aprobo-- y renombrar la frase
    con la que lo llamas, no.
    """
    crudo = f"{cmd.get('tipo', '')}:{cmd.get('valor', '')}".encode("utf-8")
    return hashlib.sha1(crudo).hexdigest()[:12]


def _aprobados(cfg: dict) -> dict:
    salida = {}
    for parte in str(cfg.get("comandos_aprobados", "")).split(","):
        nombre, _, marca = parte.partition(":")
        if nombre.strip():
            salida[nombre.strip()] = marca.strip()
    return salida


def aprobado(cmd: dict, cfg: dict) -> bool:
    """Solo `sistema` necesita aprobacion; los otros dos no pueden romper nada."""
    if cmd.get("tipo") != "sistema":
        return True
    return _aprobados(cfg).get(cmd["frases"][0]) == firma(cmd)


def aprobar(cmd: dict) -> None:
    """Deja aprobado ESTE texto. Editarlo despues lo vuelve a frenar."""
    cfg = store.load_config()
    aprobados = _aprobados(cfg)
    aprobados[cmd["frases"][0]] = firma(cmd)
    cfg["comandos_aprobados"] = ",".join(
        f"{n}:{m}" for n, m in sorted(aprobados.items()))
    store.save_config(cfg)
    store.log_action("comandos", "aprobar", f"{cmd['frases'][0]} -> {cmd['valor'][:80]}")


def pendientes(cfg: dict) -> list:
    """Los `sistema` que todavia no aprobaste. Es lo que el panel destaca."""
    return [c for c in leer() if c["tipo"] == "sistema" and not aprobado(c, cfg)]


def _hacer_accion(valor: str, cfg: dict) -> str:
    verbo, _, resto = valor.partition(" ")
    verbo, resto = verbo.strip().lower(), resto.strip()
    if verbo not in ACCIONES:
        return f"No conozco la accion {verbo!r}. Hay: {', '.join(ACCIONES)}."
    if verbo == "abrir":
        from . import apps

        catalogo = apps.load()
        # Por nombre normalizado: el .md lo escribiste vos y el catalogo sale
        # del menu inicio, asi que "spotify" y "Spotify" tienen que ser lo
        # mismo sin que tengas que averiguar como figura.
        for nombre, cmd in catalogo.items():
            if normalizar(nombre) == normalizar(resto):
                subprocess.Popen(cmd, shell=True)
                return f"Abriendo {nombre}."
        return f"No encontre {resto!r} entre los programas que conozco."
    if verbo == "mostrar":
        from . import integrations

        return integrations.mostrar("", resto, "")
    if verbo == "panel":
        from . import plataforma

        # Igual que el item de la bandeja (`tray.py:27`): un proceso aparte.
        # El panel no puede vivir adentro del listener --son dos mainloops.
        plataforma.lanzar(plataforma.comando_propio("--panel"))
        return "Panel abierto."
    from . import overlay

    overlay.asegurar(cfg)
    return "Cartel a la vista."


def ejecutar(cmd: dict, cfg: dict) -> tuple:
    """(que_hacer, dato). `que_hacer` es 'hecho' o 'prompt'.

    'prompt' devuelve el texto que hay que mandarle al modelo en lugar de lo
    que dijiste; los otros dos ya hicieron lo suyo y `dato` es lo que se dice
    en voz alta.
    """
    tipo, valor = cmd["tipo"], cmd["valor"]
    if tipo == "prompt":
        return "prompt", valor
    if tipo == "accion":
        return "hecho", _hacer_accion(valor, cfg)
    if not aprobado(cmd, cfg):
        return "hecho", ("Ese comando todavia no esta aprobado. Miralo en el "
                         "panel, en Comandos, y aprobalo si es lo que querias.")
    store.log_action("comandos", "sistema", f"{cmd['frases'][0]}: {valor[:120]}")
    try:
        r = subprocess.run(valor, shell=True, capture_output=True, text=True,
                           timeout=120)
    except subprocess.TimeoutExpired:
        return "hecho", "El comando tardo mas de dos minutos y lo corte."
    salida = (r.stdout or r.stderr or "").strip()
    if r.returncode != 0:
        return "hecho", f"Fallo: {salida[:200] or 'codigo ' + str(r.returncode)}"
    return "hecho", (salida[:200] if salida else "Listo.")


def resolver(texto: str, cfg: dict) -> tuple:
    """Lo que el listener pregunta: ('nada'|'hecho'|'prompt', dato).

    'nada' quiere decir que lo dicho no era un comando y sigue el camino de
    siempre. Es el caso normal y tiene que costar poco: leer el archivo y
    comparar diez frases es microsegundos contra el segundo largo que tarda una
    llamada al modelo.
    """
    if not str(cfg.get("comandos_voz", "si")).startswith("s"):
        return "nada", ""
    cmd = buscar(texto)
    if not cmd:
        return "nada", ""
    return ejecutar(cmd, cfg)


def asegurar_archivo() -> str:
    """Crea `Comandos.md` con la plantilla si no existe. Devuelve la ruta."""
    if not os.path.exists(RUTA):
        os.makedirs(os.path.dirname(RUTA), exist_ok=True)
        with open(RUTA, "w", encoding="utf-8") as f:
            f.write(PLANTILLA)
    return RUTA
