"""Leer una pagina web y quedarse con el texto.

No es un navegador y no pretende serlo. Renderizar un sitio arbitrario ES un
motor web, y meter uno adentro de un asistente de voz es cambiar el tamaño del
programa por algo que Eve no puede aprovechar: un navegador devuelve pixeles, y
lo que hace falta es texto que entre al contexto.

Asi que fetch, sacar el contenido y devolver texto plano. Sale mas barato en
tokens que cualquier otra forma, y de paso reduce la superficie de inyeccion:
lo que vuelve son datos que se envuelven con `integrations.envolver_ajeno`
antes de que los vea el modelo.

Sin dependencias nuevas: `HTMLParser` es de la biblioteca estandar.
"""

import json
import os
import re
from html.parser import HTMLParser

import requests

from . import store

# Etiquetas cuyo contenido NO es texto de la pagina.
MUDAS = {"script", "style", "noscript", "template", "svg", "head"}
# Las que separan parrafos: sin esto todo el sitio vuelve como un solo renglon.
CORTAN = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "article", "header", "footer", "blockquote", "pre"}

TOPE = 12000     # caracteres. Mas que esto no entra en el contexto de nadie.
ESPERA = 20      # segundos


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list = []
        self.titulo = ""
        self._mudo = 0
        self._en_titulo = False

    def handle_starttag(self, tag, attrs):
        if tag in MUDAS:
            self._mudo += 1
        elif tag == "title":
            self._en_titulo = True
        elif tag in CORTAN:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in MUDAS and self._mudo:
            self._mudo -= 1
        elif tag == "title":
            self._en_titulo = False
        elif tag in CORTAN:
            self.partes.append("\n")

    def handle_data(self, data):
        if self._en_titulo:
            self.titulo += data
        elif not self._mudo and data.strip():
            self.partes.append(data)


def extraer(html: str) -> tuple[str, str]:
    """(titulo, texto) de un HTML. No lanza: una pagina rota da texto vacio."""
    parser = _Extractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - el HTML de la web real esta roto seguido
        pass
    texto = "".join(parser.partes)
    # Espacios repetidos a uno, y no mas de una linea en blanco seguida.
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto)
    texto = re.sub(r" *\n[ \n]*", "\n", texto)
    return parser.titulo.strip(), texto.strip()


def leer(url: str, tope: int = TOPE) -> dict:
    """Baja una pagina y devuelve {url, titulo, texto, error}."""
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    salida = {"url": url, "titulo": "", "texto": "", "error": ""}
    try:
        r = requests.get(url, timeout=ESPERA, headers={
            # Sin User-Agent, unos cuantos sitios contestan 403.
            "User-Agent": "Mozilla/5.0 (compatible; LLMJarvis)",
            "Accept-Language": "es,en;q=0.8",
        })
    except requests.RequestException as exc:
        salida["error"] = f"no pude abrir la pagina: {exc}"
        return salida
    if r.status_code >= 400:
        salida["error"] = f"la pagina contesto {r.status_code}"
        return salida
    tipo = r.headers.get("Content-Type", "")
    if "html" not in tipo and "text" not in tipo:
        salida["error"] = f"eso no es una pagina de texto ({tipo or 'sin tipo'})"
        return salida

    titulo, texto = extraer(r.text)
    salida["titulo"] = titulo
    salida["texto"] = texto[:tope]
    if len(texto) > tope:
        salida["texto"] += "\n[...cortado]"
    if not texto:
        salida["error"] = "la pagina no tiene texto legible (puede ser toda javascript)"
    return salida


def buscar(consulta: str, cuantos: int = 5) -> dict:
    """Busca en DuckDuckGo y devuelve los resultados como texto.

    La version HTML no pide clave ni javascript, que es lo unico que este
    lector puede leer.
    """
    pagina = leer("https://html.duckduckgo.com/html/?q=" + requests.utils.quote(consulta))
    if pagina["error"]:
        return pagina
    lineas = [l.strip() for l in pagina["texto"].splitlines() if l.strip()]
    # Se descarta el andamiaje del buscador, que son las primeras lineas.
    utiles = [l for l in lineas if len(l) > 25][:cuantos * 3]
    pagina["titulo"] = f"Resultados para {consulta!r}"
    pagina["texto"] = "\n".join(utiles)
    return pagina


ULTIMA = "ultima_pagina.json"


def _ruta_ultima() -> str:
    return os.path.join(store.BASE, ULTIMA)


def guardar_ultima(datos: dict) -> None:
    """Deja lo ultimo que se leyo para que lo muestre el modulo `lector`.

    Archivo propio y no el canal del cartel: ese lo escribe el listener entero
    en cada cuadro, asi que meterse ahi desde otro proceso seria pisarlo.
    """
    try:
        with open(_ruta_ultima(), "w", encoding="utf-8") as f:
            json.dump({"url": datos.get("url", ""), "titulo": datos.get("titulo", ""),
                       "texto": datos.get("texto", "")[:6000]}, f, ensure_ascii=False)
    except OSError:
        pass


def ultima() -> dict:
    try:
        with open(_ruta_ultima(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
