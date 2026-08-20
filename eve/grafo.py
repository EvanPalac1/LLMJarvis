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


def leer(limite: int = 150) -> tuple[list, list]:
    """(nodos, aristas) de las ultimas acciones.

    nodos: [{"nombre", "peso"}]  aristas: [(i, j, veces)]
    """
    filas = store.recent_actions(limite)
    if not filas:
        return [], []
    secuencia = [_nombre(f) for f in reversed(filas)]

    pesos: dict = {}
    for nombre in secuencia:
        pesos[nombre] = pesos.get(nombre, 0) + 1
    elegidos = [n for n, _ in sorted(pesos.items(), key=lambda p: -p[1])[:TOPE_NODOS]]
    indice = {n: i for i, n in enumerate(elegidos)}

    juntos: dict = {}
    for antes, despues in zip(secuencia, secuencia[1:]):
        if antes == despues or antes not in indice or despues not in indice:
            continue
        par = (min(indice[antes], indice[despues]), max(indice[antes], indice[despues]))
        juntos[par] = juntos.get(par, 0) + 1

    nodos = [{"nombre": n, "peso": pesos[n]} for n in elegidos]
    aristas = [(a, b, v) for (a, b), v in juntos.items()]
    return nodos, aristas


class Acomodo:
    """Posiciones que se van acomodando solas, cuadro a cuadro."""

    def __init__(self, cuantos: int, ancho: int, alto: int):
        self.ancho, self.alto = max(1, ancho), max(1, alto)
        rng = np.random.default_rng(7)
        centro = np.array([self.ancho / 2, self.alto / 2])
        self.pos = centro + (rng.random((max(1, cuantos), 2)) - 0.5) * min(ancho, alto) * 0.6
        self.vel = np.zeros_like(self.pos)

    def avanzar(self, aristas, pasos: int = 1) -> None:
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
