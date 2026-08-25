"""El grafo de lo que Eve hace, sacado del log de auditoria.

No es una decoracion animada: los nodos son las herramientas que se ejecutaron
de verdad y las aristas son las que salieron una detras de otra en la misma
tanda. Sirve para ver lo que ninguna lista contesta bien -- que hace seguido,
que combina con que, y que quedo sin usarse nunca.

El modelo es el de Graphify y no el de un grafo de memoria con LLM: extraccion
DETERMINISTA, sin llamadas a ningun modelo, sobre datos que ya estaban. Un
asistente de voz tiene ~5 segundos de presupuesto por turno; gastar una llamada
a un modelo por cada cosa que se anota no entra.

El acomodado es dirigido por fuerzas: resortes entre lo conectado y repulsion
entre todo. Es el mismo motor que las particulas --posiciones en una matriz de
numpy que avanza por cuadro--, asi que el grafo "trabajando" sale del sistema
que ya existe en vez de uno nuevo.
"""

import ast
import json
import os
import re

import numpy as np

from . import store

TOPE_NODOS = 24
# Lo que se ejecuta a traves de la CLI aparece como un `run_command` con el
# subcomando adentro. Sin sacarlo, el grafo entero seria un solo nodo gigante
# que dice "run_command" y no cuenta nada.
_SUBCOMANDO = re.compile(r"--cli\s+([a-z][a-z0-9-]+)")


def _comando(detalle: str) -> str:
    """El texto del comando que hay adentro del detalle, si lo hay.

    El detalle se guarda como el repr de un dict, y viene en dos sabores segun
    el motor: comillas simples de Python o JSON con comillas dobles.
    """
    llave = detalle.find("{")
    if llave >= 0:
        crudo = detalle[llave:]
        for parsear in (json.loads, ast.literal_eval):
            try:
                datos = parsear(crudo)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(datos, dict) and datos.get("command"):
                return str(datos["command"])
    # Si no se pudo parsear --detalles cortados a 2000 caracteres, por ejemplo--
    # se busca a mano, saltando las comillas escapadas: buscar la primera comilla
    # a secas cortaba el comando en `& \"` y devolvia el nombre de la tool.
    for marca in ("'command': '", '"command": "'):
        i = detalle.find(marca)
        if i < 0:
            continue
        resto = detalle[i + len(marca):]
        cierre = marca[-1]
        j = 0
        while j < len(resto):
            if resto[j] == "\\":
                j += 2
                continue
            if resto[j] == cierre:
                return resto[:j]
            j += 1
        return resto
    return detalle


def _nombre(fila) -> str:
    """Como se llama el nodo de esta accion.

    La primera version partia el detalle entero en palabras y se quedaba con la
    primera larga. Sobre comandos de Windows eso devolvia pedazos de ruta --el
    nodo mas pesado del grafo era "C", y despues "Users"-- que no dicen nada de
    lo que Eve hizo. Ahora se saca el comando y, si arranca con una ruta, se usa
    el nombre del ejecutable, que es lo que uno reconoceria.
    """
    tool = str(fila[1] or "?")
    detalle = str(fila[2] or "")
    hallado = _SUBCOMANDO.search(detalle)
    if hallado:
        return hallado.group(1)
    if tool.lower() in ("powershell", "bash", "run_command"):
        crudo = _comando(detalle).strip()
        crudo = crudo.lstrip("& ").lstrip()
        # Primer token, respetando que una ruta con espacios va entre comillas.
        if crudo[:1] in ("'", '"', "\\"):
            cierre = crudo.find(crudo[0], 1) if crudo[0] in "'\"" else -1
            token = crudo[1:cierre] if cierre > 0 else crudo[1:].split()[0] if crudo[1:].split() else ""
        else:
            token = crudo.split()[0] if crudo.split() else ""
        token = token.strip("\\\"' ")
        if not token:
            return tool[:22]
        # Si es una ruta, el ejecutable; si no, el cmdlet tal cual.
        base = token.replace("\\", "/").rstrip("/").split("/")[-1]
        return (base or token)[:22]
    return tool[:22]


# Rutas que aparecen en los detalles. Sirve tanto para `path` como para las que
# vienen sueltas adentro de un comando.
_RUTA = re.compile(
    # Entre comillas primero: las rutas con espacios --"Trabajos GOD"-- vienen
    # asi, y cortarlas en el espacio dejaba el proyecto con medio nombre.
    r'"([A-Za-z]:[\\/][^"]*)"'
    r"|'([A-Za-z]:[\\/][^']*)'"
    r"|([A-Za-z]:[\\/][^\"'\s,}]+)"
    r"|(/(?:home|Users|mnt|opt)/[^\"'\s,}]+)"
)


def _proyecto(ruta: str, workdirs) -> str:
    """A que proyecto pertenece una ruta, o "" si no es un proyecto.

    Un proyecto es la primera carpeta que cuelga de un directorio permitido:
    es donde el usuario trabaja y es lo unico donde Eve puede tocar sin pedir
    confirmacion. Todo lo demas --temporales, Archivos de Programa, el propio
    Python-- es plomeria, y meterla en el grafo lo llenaba de nodos como "s:",
    "0" y carpetas temporales que no le dicen nada a nadie.

    Un archivo suelto tampoco dice nada; la carpeta que lo contiene si.
    """
    # Las barras dobles del escapado JSON se colapsan: sin esto la ruta queda
    # como `C://Users//...` y deja de coincidir con el directorio permitido.
    normal = re.sub(r"/{2,}", "/", ruta.replace("\\", "/")).rstrip("/")
    for base in workdirs or []:
        raiz = re.sub(r"/{2,}", "/", str(base).replace("\\", "/")).rstrip("/")
        if not raiz or not normal.lower().startswith(raiz.lower() + "/"):
            continue
        resto = [x for x in normal[len(raiz) + 1:].split("/") if x]
        if not resto:
            continue
        # Si lo unico que cuelga es un archivo, el proyecto es el directorio.
        nombre = resto[0] if len(resto) > 1 or "." not in resto[0] else os.path.basename(raiz)
        return nombre[:26]
    return ""


def _proyectos_de(fila, workdirs) -> list:
    """Los proyectos que toco esta accion, sin repetir."""
    detalle = str(fila[2] or "")
    vistos = []
    for grupos in _RUTA.findall(detalle):
        ruta = next((g for g in grupos if g), "")
        nombre = _proyecto(ruta, workdirs) if ruta else ""
        if nombre and nombre not in vistos:
            vistos.append(nombre)
    return vistos[:2]



def leer(limite: int = 150, workdirs=None) -> tuple[list, list]:
    """(nodos, aristas) de las ultimas acciones.

    Hay dos clases de nodo y eso es lo que hace util al grafo: las HERRAMIENTAS
    que se ejecutaron y los PROYECTOS sobre los que se ejecutaron. Solo con
    herramientas se ve que hace Eve; con las dos se ve donde lo hace, que es la
    pregunta que ninguna lista contesta bien.

    nodos: [{"nombre", "peso", "clase"}]   aristas: [(i, j, veces)]
    """
    filas = store.recent_actions(limite)
    if not filas:
        return [], []
    if workdirs is None:
        try:
            workdirs = store.load_config().get("workdirs") or []
        except Exception:  # noqa: BLE001 - el grafo no puede tumbar la ventana
            workdirs = []

    secuencia = []
    pesos: dict = {}
    juntos: dict = {}

    def sumar(nombre, clase):
        clave = (clase, nombre)
        pesos[clave] = pesos.get(clave, 0) + 1
        return clave

    for fila in reversed(filas):
        herramienta = sumar(_nombre(fila), "herramienta")
        secuencia.append(herramienta)
        for proyecto in _proyectos_de(fila, workdirs):
            clave = sumar(proyecto, "proyecto")
            # La arista que importa: esta herramienta toco este proyecto.
            par = tuple(sorted((herramienta, clave)))
            juntos[par] = juntos.get(par, 0) + 1

    elegidos = [c for c, _ in sorted(pesos.items(), key=lambda p: -p[1])[:TOPE_NODOS]]
    indice = {c: i for i, c in enumerate(elegidos)}

    # Y las herramientas que salieron una detras de otra.
    for antes, despues in zip(secuencia, secuencia[1:]):
        if antes == despues or antes not in indice or despues not in indice:
            continue
        par = tuple(sorted((antes, despues)))
        juntos[par] = juntos.get(par, 0) + 1

    nodos = [{"nombre": nombre, "peso": pesos[(clase, nombre)], "clase": clase}
             for clase, nombre in elegidos]
    aristas = [(indice[a], indice[b], v) for (a, b), v in juntos.items()
               if a in indice and b in indice]
    return nodos, aristas


class Acomodo:
    """Posiciones que se van acomodando solas, cuadro a cuadro.

    Guarda la IDENTIDAD de cada nodo --su (clase, nombre)-- y no solo cuantos
    son. Esa es toda la diferencia entre una animacion continua y una que se
    reinicia sola: el log se relee cada tantos cuadros, y al releerlo el orden
    de los nodos cambia --salen ordenados por peso-- asi que sin la identidad
    lo unico que se podia hacer era tirar el acomodo y empezar de nuevo desde
    una nube aleatoria. Cada tres segundos, a la vista.

    Con la identidad, releer no mueve nada: los que ya estaban se quedan donde
    estan, los que aparecen entran cerca del centro, y los que se fueron dejan
    su lugar. Solo se ve moverse lo que de verdad cambio.
    """

    def __init__(self, claves, ancho: int, alto: int):
        self.ancho, self.alto = max(1, ancho), max(1, alto)
        self.rng = np.random.default_rng(7)
        self.claves = []
        self.pos = np.zeros((0, 2))
        self.vel = np.zeros((0, 2))
        self.fase = np.zeros(0)
        self.sincronizar(claves)

    # --- identidad --------------------------------------------------------

    def _sembrar(self, cuantos: int) -> np.ndarray:
        """Posiciones de arranque para nodos nuevos: cerca del centro.

        Cerca y no en el centro exacto porque la repulsion divide por la
        distancia: dos nodos en el mismo punto se disparan a los bordes.
        """
        centro = np.array([self.ancho / 2, self.alto / 2])
        radio = min(self.ancho, self.alto) * 0.18
        return centro + (self.rng.random((max(0, cuantos), 2)) - 0.5) * radio

    def sincronizar(self, claves) -> None:
        """Deja el acomodo con estos nodos, conservando lo que ya estaba.

        `claves` es la lista de (clase, nombre) en el orden en que se van a
        dibujar, o sea el mismo orden que `leer()` devolvio.
        """
        claves = [tuple(c) for c in claves]
        if claves == self.claves:
            return
        donde = {c: i for i, c in enumerate(self.claves)}
        pos = self._sembrar(len(claves))
        vel = np.zeros((len(claves), 2))
        fase = self.rng.random(len(claves)) * 6.283185
        for i, clave in enumerate(claves):
            j = donde.get(clave)
            if j is not None:
                pos[i] = self.pos[j]
                vel[i] = self.vel[j]
                fase[i] = self.fase[j]
        self.claves, self.pos, self.vel, self.fase = claves, pos, vel, fase

    def redimensionar(self, ancho: int, alto: int) -> None:
        """Otro tamaño de modulo NO es otro grafo: se escala, no se rehace.

        Redimensionar reseteando era el mismo reinicio por otra puerta, y
        saltaba con solo agrandar la ventana de actividad.
        """
        ancho, alto = max(1, ancho), max(1, alto)
        if (ancho, alto) == (self.ancho, self.alto):
            return
        if len(self.pos):
            self.pos *= np.array([ancho / self.ancho, alto / self.alto])
        self.ancho, self.alto = ancho, alto

    # --- fisica -----------------------------------------------------------

    def avanzar(self, aristas, pasos: int = 1) -> None:
        if not len(self.pos):
            return
        for _ in range(pasos):
            # Repulsion de todos contra todos: sin esto se apilan en el centro.
            resta = self.pos[:, None, :] - self.pos[None, :, :]
            dist = np.linalg.norm(resta, axis=2) + 1e-6
            empuje = (resta / dist[:, :, None]) * (2200.0 / dist[:, :, None] ** 2)
            np.fill_diagonal(empuje[:, :, 0], 0.0)
            np.fill_diagonal(empuje[:, :, 1], 0.0)
            fuerza = empuje.sum(axis=1)
            # Resortes en lo conectado.
            for a, b, veces in aristas:
                if a >= len(self.pos) or b >= len(self.pos):
                    continue
                delta = self.pos[b] - self.pos[a]
                largo = np.linalg.norm(delta) + 1e-6
                tira = delta / largo * (largo - 70.0) * 0.015 * min(veces, 4)
                fuerza[a] += tira
                fuerza[b] -= tira
            # Y un tiron suave al centro para que no se vaya del rectangulo.
            fuerza += (np.array([self.ancho / 2, self.alto / 2]) - self.pos) * 0.010
            self.vel = (self.vel + fuerza) * 0.82
            self.pos += self.vel
            np.clip(self.pos, [14, 14], [self.ancho - 14, self.alto - 14], out=self.pos)

    def dibujables(self, t: float) -> np.ndarray:
        """Donde se dibuja cada nodo: lo acomodado mas una deriva minima.

        Un acomodado por fuerzas CONVERGE --el amortiguado es 0.82, en unos dos
        segundos la velocidad es cero-- y a partir de ahi la imagen queda
        completamente quieta. Eso esta bien para un diagrama y mal para algo
        que se mira: quieto del todo no se distingue de colgado, y era parte de
        por que el reinicio cada tres segundos pasaba por "la animacion".

        La deriva son 1.6 pixeles, cada nodo con su propia fase, y va ACA y no
        en las fuerzas a proposito: metida en la fisica pelearia con los
        resortes y nunca dejaria converger. Aplicada al dibujar no puede
        desestabilizar nada.
        """
        if not len(self.pos):
            return self.pos
        deriva = np.stack((np.sin(t * 0.7 + self.fase),
                           np.cos(t * 0.5 + self.fase * 1.3)), axis=1) * 1.6
        return self.pos + deriva


def estado(guardado, cuantas: int, workdirs, ancho: int, alto: int,
           cada: int = 90):
    """El estado del grafo listo para dibujar, releido sin reiniciarse.

    Vive aca y no en cada renderer porque los dos --Pillow y Skia-- tenian la
    MISMA copia de esta logica, con el mismo defecto: tiraban el `Acomodo`
    entero cada `cada` cuadros y lo reconstruian desde una nube aleatoria. Dos
    copias del mismo bug es exactamente lo que pasa cuando algo que no es
    dibujo vive en el que dibuja.

    Devuelve el dict de siempre; el llamador lo guarda por id de modulo.
    """
    if guardado is None:
        nodos, aristas = leer(cuantas, workdirs)
        acomodo = Acomodo([(n["clase"], n["nombre"]) for n in nodos], ancho, alto)
        # Se asienta ANTES del primer cuadro. Naciendo de una nube aleatoria, el
        # primer paso de fuerzas mueve los nodos 93 pixeles de golpe --medido--
        # asi que el modulo aparecia explotando y recien despues se ordenaba.
        # Treinta pasos sobre 24 nodos como mucho es una vez y no se nota.
        acomodo.avanzar(aristas, pasos=30)
        return {"nodos": nodos, "aristas": aristas, "cuadros": 0, "t": 0.0,
                "cuantas": cuantas, "acomodo": acomodo}

    guardado["cuadros"] += 1
    guardado["t"] = guardado.get("t", 0.0) + 1.0 / 30.0
    guardado["acomodo"].redimensionar(ancho, alto)
    # Releer cambia los DATOS y nunca el acomodo. Tambien cuando cambia
    # `cuantas`, que antes ni se miraba: tocarlo en el panel no hacia nada
    # hasta la siguiente relectura, y entonces se veia como un reinicio mas.
    if guardado["cuadros"] > cada or guardado.get("cuantas") != cuantas:
        guardado["cuadros"] = 0
        guardado["cuantas"] = cuantas
        nodos, aristas = leer(cuantas, workdirs)
        guardado["nodos"], guardado["aristas"] = nodos, aristas
        guardado["acomodo"].sincronizar([(n["clase"], n["nombre"]) for n in nodos])
    if guardado["nodos"]:
        guardado["acomodo"].avanzar(guardado["aristas"])
    return guardado


def programas_usados(nombres, limite: int = 400) -> list:
    """De los programas del catalogo, cuales aparecieron en el log y cuantas veces.

    Es la unica parte del grafo que ahorra contexto en vez de mostrarlo. El
    catalogo entero viaja en CADA llamada al modelo --80 lineas, un tercio del
    system prompt-- y en la practica se abren unos pocos. Con esto el prompt
    lleva los que se usan y el resto se pide cuando hace falta.

    Sin llamadas a ningun modelo: es contar apariciones en un log que ya existe.
    """
    filas = store.recent_actions(limite)
    if not filas:
        return []
    texto = " \n ".join(str(f[2] or "").lower() for f in filas)
    cuenta = {}
    for nombre in nombres:
        # Nombres de una o dos letras aparecen en cualquier lado por casualidad.
        if len(nombre) < 3:
            continue
        veces = texto.count(nombre.lower())
        if veces:
            cuenta[nombre] = veces
    return [n for n, _ in sorted(cuenta.items(), key=lambda par: -par[1])]
