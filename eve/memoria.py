"""Los hechos que Eve recuerda, acotados a lo que vale la pena mandar.

`MEMORIA.md` lo escribe `recordar` agregando lineas al final y nunca sacando
ninguna, y viaja ENTERO en cada llamada al modelo. Con veinte hechos no se nota;
con doscientos es la mitad del presupuesto de contexto gastado en cosas que no
tienen nada que ver con lo que se acaba de preguntar.

Dos podas, las dos deterministas y sin una sola llamada a un modelo:

1. La cabecera del archivo esta escrita para la PERSONA que lo edita --"este
   archivo no va al repositorio", "no se guarda lo de un solo uso"-- y viajaba
   igual. El modelo no necesita saber como se administra su propia memoria.

2. Si los hechos pasan del presupuesto, se mandan los mas relevantes: los que
   nombran cosas que aparecieron en lo que Eve viene haciendo, y los mas nuevos.

La relevancia se calcula contra el LOG, no contra la pregunta del momento. Es a
proposito: un prompt que cambia en cada turno tira por la ventana el cache de
prompt del motor de Anthropic, y ese cache vale mas que los pocos tokens que se
ahorrarian afinando por pregunta.
"""

import re

from . import store

# Cuanto puede ocupar la memoria en el prompt. Por debajo de esto va entera.
TOPE_CHARS = 1800
# Cosas con nombre: mayusculas, rutas, y lo que este entre comillas o backticks.
_ENTIDADES = re.compile(
    r"`([^`]+)`"
    r'|"([^"]+)"'
    r"|([A-Z][\w.-]{2,})"
    r"|([A-Za-z]:[\\\\/][\\w\\\\/.-]+)"
)


def hechos(texto: str) -> list:
    """Las lineas de `- ...` del archivo. La cabecera no es un hecho."""
    return [linea.strip()[2:].strip()
            for linea in texto.splitlines()
            if linea.strip().startswith("- ") and len(linea.strip()) > 3]


def entidades(frase: str) -> set:
    """Las cosas con nombre que aparecen en una frase, en minusculas."""
    salida = set()
    for grupos in _ENTIDADES.findall(frase):
        for g in grupos:
            if g and len(g) > 2:
                salida.add(g.strip().lower())
    return salida


def _vistas(limite: int = 200) -> set:
    """Lo que aparecio en lo que Eve viene haciendo: turnos y acciones."""
    visto = set()
    try:
        for fila in store.recent_turns(limite):
            visto |= entidades(str(fila[2] or ""))
        for fila in store.recent_actions(limite):
            visto |= entidades(str(fila[2] or ""))
    except Exception:  # noqa: BLE001 - sin base, no hay relevancia y listo
        return set()
    return visto


def podar(texto: str, tope: int = TOPE_CHARS) -> str:
    """La memoria lista para el prompt: sin cabecera y dentro del presupuesto.

    Devuelve "" si no hay ningun hecho, para no mandar un titulo solo.
    """
    lista = hechos(texto)
    if not lista:
        return ""
    entero = "\n".join("- " + h for h in lista)
    if len(entero) <= tope:
        return entero

    vistas = _vistas()
    # Puntaje: cuantas cosas nombradas del hecho aparecieron ultimamente, y un
    # empujon por ser reciente para que lo recien aprendido no quede afuera.
    puntos = []
    for i, hecho in enumerate(lista):
        coincide = len(entidades(hecho) & vistas)
        puntos.append((coincide * 10 + i / max(1, len(lista)), i, hecho))
    puntos.sort(reverse=True)

    elegidos, largo = [], 0
    for _, i, hecho in puntos:
        linea = "- " + hecho
        if largo + len(linea) + 1 > tope:
            continue
        elegidos.append((i, linea))
        largo += len(linea) + 1
    # Se devuelven en el orden del archivo: leerlos salteados confunde.
    elegidos.sort()
    sobran = len(lista) - len(elegidos)
    salida = "\n".join(linea for _, linea in elegidos)
    if sobran:
        salida += f"\n- (hay {sobran} datos mas guardados; pedilos con `E recordado TEMA`)"
    return salida


def buscar(consulta: str, texto: str, cuantos: int = 8) -> str:
    """Los hechos que hablan de algo. Es la contraparte de la poda."""
    lista = hechos(texto)
    if not lista:
        return "No tengo nada guardado todavia."
    consulta = consulta.strip().lower()
    if not consulta:
        return "\n".join("- " + h for h in lista[:cuantos])
    hallados = [h for h in lista if consulta in h.lower()]
    if not hallados:
        pedidas = entidades(consulta)
        hallados = [h for h in lista if entidades(h) & pedidas]
    if not hallados:
        return f"No tengo nada guardado sobre {consulta!r}."
    return "\n".join("- " + h for h in hallados[:cuantos])
