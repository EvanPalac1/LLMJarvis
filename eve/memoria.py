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
# Cuantos ENLACES se siguen para la relevancia. 0 = solo lo que aparecio recien,
# que era el comportamiento anterior. 2 es lo que pide el plan, y lo que midio
# mejor: sobre un caso con respuesta conocida --se habla de Minecraft, y el dato
# util es del router, ligado por un hecho que nombra los dos-- 0 saltos traia 1
# de 3 hechos relevantes y 5 de ruido; 2 saltos trae los 3 y 3 de ruido. Con 3
# no cambia nada: el grafo de una memoria real es chato.
SALTOS = 2
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


def podar(texto: str, tope: int = TOPE_CHARS, saltos: int = SALTOS) -> str:
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
    # El segundo salto: ademas de lo que aparecio recien, lo que comparte un
    # hecho con eso. Un dato sobre el router es relevante cuando se esta
    # hablando de Minecraft si algun hecho nombra los dos.
    #
    # Los dos saltos NO valen lo mismo: lo directo pesa 10 y lo de segundo
    # salto 4. Con el mismo peso, en una memoria con temas que se repiten el
    # segundo salto alcanza a casi todo y deja de distinguir --medido: en una
    # memoria densa de 200 hechos llega al 100% del grafo.
    cerca = set()
    if saltos > 0:
        vecinos, _donde = grafo(lista)
        cerca = cercanas(vistas, vecinos, saltos) - vistas

    puntos = []
    for i, hecho in enumerate(lista):
        suyas = entidades(hecho)
        directo = len(suyas & vistas)
        indirecto = len(suyas & cerca)
        puntos.append((directo * 10 + indirecto * 4 + i / max(1, len(lista)), i, hecho))
    puntos.sort(reverse=True)

    # El pie se descuenta ANTES de elegir. Se sumaba despues del corte, asi que
    # `podar(tope=400)` devolvia 402 y con 800 devolvia 810: el tope no era
    # duro, que es lo unico que un tope tiene que ser. Se reserva lo que ocupa;
    # si al final no hace falta, lo que sobra es margen y no un desborde.
    PIE = "\n- (hay {} datos mas guardados; pedilos con `E recordado TEMA`)"
    reserva = len(PIE.format(len(lista)))

    elegidos, largo = [], 0
    for _, i, hecho in puntos:
        linea = "- " + hecho
        if largo + len(linea) + 1 > tope - reserva:
            continue
        elegidos.append((i, linea))
        largo += len(linea) + 1
    # Se devuelven en el orden del archivo: leerlos salteados confunde.
    elegidos.sort()
    sobran = len(lista) - len(elegidos)
    salida = "\n".join(linea for _, linea in elegidos)
    if sobran:
        salida += PIE.format(sobran)
    return salida


# --- el grafo -------------------------------------------------------------
# Nodos: las cosas con nombre. Aristas: aparecer en el mismo hecho. No hay
# archivo: el grafo se arma recorriendo los hechos una vez, y persistir algo
# derivado que cuesta microsegundos es mantener un cache que puede quedar viejo
# a cambio de nada. El plan pedia JSON; el motivo de no hacerlo esta medido.


def grafo(lista: list) -> tuple[dict, dict]:
    """(vecinos, donde) de una lista de hechos.

    `vecinos[e]` son las entidades que aparecen junto a `e` en algun hecho.
    `donde[e]` son los indices de los hechos donde aparece `e`.
    """
    vecinos: dict = {}
    donde: dict = {}
    for i, hecho in enumerate(lista):
        suyas = entidades(hecho)
        for e in suyas:
            donde.setdefault(e, []).append(i)
            vecinos.setdefault(e, set()).update(suyas - {e})
    return vecinos, donde


def cercanas(semillas: set, vecinos: dict, saltos: int = 2) -> set:
    """Las entidades a `saltos` ENLACES de las semillas, ellas incluidas.

    `saltos` cuenta enlaces seguidos, no niveles: 0 son las semillas solas --lo
    que `podar()` hacia siempre-- y 2 es lo que pide el plan. La primera version
    contaba niveles y quedaba corrida en uno, asi que "2 saltos" seguia un solo
    enlace y no llegaba a lo que el plan describe.
    """
    alcanzadas = {e for e in semillas if e in vecinos}
    frontera = set(alcanzadas)
    for _ in range(max(0, saltos)):
        nueva = set()
        for e in frontera:
            nueva |= vecinos.get(e, set())
        nueva -= alcanzadas
        if not nueva:
            break
        alcanzadas |= nueva
        frontera = nueva
    return alcanzadas


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
