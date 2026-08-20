"""Que es un modulo, y como se guarda.

Un modulo NO es una ventana ni un widget: es una fila de datos mas una funcion
que dibuja. Esa distincion es la que hace que lo mismo sirva en el cartel
flotante, en la ventana de actividad y en el panel, sin tres implementaciones.

Se guarda como claves PLANAS con prefijo `mod_<id>_<prop>` en la misma config
que todo lo demas. No es capricho: `store.perfilable()` deja entrar sola
cualquier clave con prefijo conocido, y `store.solo_cosmetico()` evita que
tocarla rearme el motor y corte la conversacion. Nombrar bien la clave da
perfilado exportable y recarga en vivo sin escribir una linea.

El precio de las claves planas es que `Panel.save()` decide el tipo con
`type(DEFAULTS[clave])`, y estas no estan en DEFAULTS porque se inventan en
runtime. Por eso cada tipo declara sus props con su valor por defecto:
`tipo_de_clave()` es lo que el panel consulta para no guardar todo como texto.
"""

PREFIJO = "mod_"

# Props que tiene todo modulo, sea del tipo que sea.
#   prop -> (valor por defecto, ayuda)
COMUNES = {
    "tipo": ("texto", "que dibuja"),
    "superficie": ("overlay", "overlay | tablero"),
    "x": (40, "posicion en pixeles"),
    "y": (40, "posicion en pixeles"),
    "ancho": (300, "pixeles"),
    "alto": (120, "pixeles"),
    "z": (0, "orden de dibujo; mas alto va arriba"),
    "pantalla": (0, "en que monitor, 0 = el principal"),
    "opacidad": (100, "0 a 100"),
    # Decidido con el usuario: cada modulo elige cuando se ve. Un reloj o el
    # medidor quedan fijos; la onda aparece solo al hablar.
    "cuando": ("siempre", "siempre | trabajando | hover"),
    "interactivo": (False, "si recibe clics"),
    # --- animacion, comun a las cuatro clases ---
    "velocidad": (1.0, "multiplicador de tiempo"),
    "easing": ("lineal", "lineal | suave | rebote"),
    "escala": (100, "porcentaje"),
    "rotacion": (0, "grados"),
    "tinte": ("", "color que se mezcla, vacio = ninguno"),
    # Que rol de la paleta usa. El cartel viejo pinta el titulo con el acento y
    # la linea de estado con el color tenue, y sin esto todo salia igual.
    "color": ("texto", "texto | texto_tenue | acento | acento2 | borde | alerta"),
    # La prop que separa una animacion importada de una que reacciona.
    "fuente": ("reloj", "reloj | microfono"),
}

# Props propias de cada tipo, ademas de las comunes.
TIPOS = {
    "texto": {"contenido": ("", "que dice, cuando el origen es fijo"),
              "origen": ("nombre", "fijo | nombre | detalle | usuario | eve"),
              "tam": (16, "puntos")},
    "icono": {"imagen": ("", "ruta a png, gif, apng o webp animado"),
              "lados": (6, "menos de 3 = circulo"),
              "redondeo": (0, "0 = vertices en punta")},
    "onda": {"estilo": ("barras", "barras | espejo | linea | puntos"),
             "muestras": (56, "cuantas barras")},
    "particulas": {"cantidad": (200, "tope por modulo"),
                   "vida": (1.5, "segundos"),
                   "gravedad": (0.0, "pixeles por segundo al cuadrado")},
    "reloj": {"formato": ("%H:%M", "como en strftime")},
    # El medidor de contexto. Es el unico modulo que muestra un numero medido y
    # no un adorno: sale de `prompt.partes()` y del gasto real de cada turno.
    "contexto": {"detalle": ("barra", "barra | numeros")},
    # Lo que Eve hizo de verdad, sacado del log de auditoria. Los nodos son las
    # herramientas que se ejecutaron y las aristas las que salieron seguidas.
    "grafo": {"cuantas": (150, "cuantas acciones se miran hacia atras"),
              "etiquetas": (True, "escribir el nombre de cada nodo")},
    # El texto de una pagina que se pidio leer. Se llena con `E leer URL`.
    "lector": {"tam": (12, "puntos"), "lineas": (14, "cuantas entran")},
}

# Props que son de eleccion cerrada. Es lo que hace que el panel se GENERE en
# vez de cablearse: sin esta tabla habria que escribir a mano un combo por prop
# y por tipo, que es exactamente el problema que el sistema de modulos viene a
# sacar de encima.
OPCIONES = {
    "tipo": list(TIPOS),
    "superficie": ["overlay", "tablero"],
    "cuando": ["siempre", "trabajando", "hover"],
    "fuente": ["reloj", "microfono"],
    "easing": ["lineal", "suave", "rebote"],
    "estilo": ["barras", "espejo", "linea", "puntos"],
    "detalle": ["barra", "numeros"],
    "origen": ["fijo", "nombre", "detalle", "usuario", "eve"],
    "color": ["texto", "texto_tenue", "acento", "acento2", "borde", "alerta"],
}


# Tipos que pueden reaccionar al microfono en vez de al reloj. Una animacion
# importada se puede escalar y teñir, pero no reaccionar: para eso el dibujo lo
# tiene que calcular la maquina.
REACTIVOS = ("onda", "particulas")


def props_de(tipo):
    """Todas las props de un tipo: las comunes mas las suyas."""
    return {**COMUNES, **TIPOS.get(tipo, {})}


def clave(ident, prop):
    return PREFIJO + ident + "_" + prop


def _partir(k):
    """`mod_onda1_estilo` -> ('onda1', 'estilo'). El id no lleva guion bajo."""
    resto = k[len(PREFIJO):]
    ident, _, prop = resto.partition("_")
    return ident, prop


def tipo_de_clave(cfg, k):
    """El tipo Python que le corresponde a una clave de modulo, o None.

    Lo consulta el panel al guardar: sin esto una posicion quedaria guardada
    como el texto "40" y la cuenta siguiente sumaria cadenas.
    """
    if not k.startswith(PREFIJO):
        return None
    ident, prop = _partir(k)
    if not prop:
        return None
    tipo = str(cfg.get(clave(ident, "tipo"), COMUNES["tipo"][0]))
    defecto = props_de(tipo).get(prop)
    return type(defecto[0]) if defecto else None


def identificadores(cfg):
    """Los ids que aparecen en la config."""
    vistos = []
    for k in cfg:
        if k.startswith(PREFIJO):
            ident, prop = _partir(k)
            if prop and ident not in vistos:
                vistos.append(ident)
    return sorted(vistos)


def leer(cfg, ident):
    """Un modulo completo, con los defaults de su tipo ya puestos."""
    tipo = str(cfg.get(clave(ident, "tipo"), COMUNES["tipo"][0]))
    modulo = {"id": ident, "tipo": tipo}
    for prop, par in props_de(tipo).items():
        if prop == "tipo":
            continue
        defecto = par[0]
        valor = cfg.get(clave(ident, prop), defecto)
        # La config puede traer texto donde se espera numero: viene de un panel.
        if isinstance(defecto, bool):
            valor = str(valor).lower() in ("1", "true", "si", "yes")
        elif isinstance(defecto, int) and not isinstance(valor, bool):
            valor = _entero(valor, defecto)
        elif isinstance(defecto, float):
            valor = _flotante(valor, defecto)
        modulo[prop] = valor
    return modulo


def listar(cfg, superficie=""):
    """Los modulos de una superficie, ordenados para dibujar."""
    todos = [leer(cfg, i) for i in identificadores(cfg)]
    if superficie:
        todos = [m for m in todos if m["superficie"] == superficie]
    return sorted(todos, key=lambda m: (m["z"], m["id"]))


def guardar(cfg, modulo):
    """Escribe un modulo en la config, sin tocar el resto."""
    ident = modulo["id"]
    nueva = dict(cfg)
    nueva[clave(ident, "tipo")] = modulo["tipo"]
    for prop, valor in modulo.items():
        if prop not in ("id", "tipo"):
            nueva[clave(ident, prop)] = valor
    return nueva


def borrar(cfg, ident):
    """Saca un modulo entero de la config."""
    return {k: v for k, v in cfg.items()
            if not (k.startswith(PREFIJO) and _partir(k)[0] == ident)}


def visible(modulo, estado, bajo_el_mouse=False):
    """Si este modulo se dibuja ahora mismo."""
    cuando = modulo.get("cuando", "siempre")
    if cuando == "siempre":
        return True
    if cuando == "hover":
        return bajo_el_mouse
    return estado not in ("", "reposo")


def _entero(valor, defecto):
    try:
        return int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        return defecto


def _flotante(valor, defecto):
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return defecto


def por_defecto_tablero():
    """Un tablero que sirva apenas se abre, en vez de una ventana vacia.

    Muestra lo que Eve ya sabe y hasta ahora no se veia junto: en que anda, que
    se escucho, que esta contestando, y en que se va el contexto.
    """
    return {
        "tnombre": {"tipo": "texto", "superficie": "tablero", "x": 40, "y": 30,
                    "ancho": 400, "alto": 44, "tam": 28, "origen": "nombre",
                    "cuando": "siempre", "z": 1},
        "testado": {"tipo": "texto", "superficie": "tablero", "x": 40, "y": 78,
                    "ancho": 400, "alto": 24, "tam": 13, "origen": "detalle",
                    "cuando": "siempre", "z": 1},
        "tonda": {"tipo": "onda", "superficie": "tablero", "x": 40, "y": 112,
                  "ancho": 620, "alto": 60, "fuente": "microfono",
                  "cuando": "siempre", "z": 1},
        "tvos": {"tipo": "texto", "superficie": "tablero", "x": 40, "y": 200,
                 "ancho": 620, "alto": 40, "tam": 15, "origen": "usuario",
                 "cuando": "siempre", "z": 1},
        "teve": {"tipo": "texto", "superficie": "tablero", "x": 40, "y": 250,
                 "ancho": 620, "alto": 40, "tam": 15, "origen": "eve",
                 "cuando": "siempre", "z": 1},
        "tcontexto": {"tipo": "contexto", "superficie": "tablero", "x": 40, "y": 330,
                      "ancho": 620, "alto": 18, "cuando": "siempre", "z": 1},
        "tcuentas": {"tipo": "contexto", "superficie": "tablero", "x": 40, "y": 360,
                     "ancho": 300, "alto": 90, "detalle": "numeros",
                     "cuando": "siempre", "z": 1},
        # Lo que Eve hizo, sacado del log de auditoria que ya se escribia.
        "tgrafo": {"tipo": "grafo", "superficie": "tablero", "x": 700, "y": 30,
                   "ancho": 360, "alto": 300, "cuando": "siempre", "z": 1},
        # Lo ultimo que se le pidio leer de la web.
        "tlector": {"tipo": "lector", "superficie": "tablero", "x": 700, "y": 350,
                    "ancho": 360, "alto": 220, "tam": 11, "cuando": "siempre", "z": 1},
    }


# Palabras que `hud_icono` acepta ademas de una ruta a una imagen.
FORMAS_ICONO = {"ninguno": None, "circulo": 0, "hexagono": 6, "cuadrado": 4}


def por_defecto(cfg=None):
    """El cartel de ESTE usuario, descrito como modulos.

    Antes inventaba un cartel generico --hexagono vacio, onda de barras, texto
    del color de texto-- y por eso pasar a modulos se veia como un downgrade:
    quien tenia su icono propio, su estilo de onda y su titulo con el color de
    acento perdia las tres cosas de golpe. Ahora se lee la config y se traduce.
    """
    cfg = cfg or {}
    icono_cfg = str(cfg.get("hud_icono", "hexagono") or "hexagono")
    lados = FORMAS_ICONO.get(icono_cfg, _entero(cfg.get("hud_marco_lados", 6), 6))
    imagen = "" if icono_cfg in FORMAS_ICONO else icono_cfg

    piezas = {}
    if icono_cfg != "ninguno":
        piezas["iconoeve"] = {
            "tipo": "icono", "superficie": "overlay", "x": 12, "y": 12,
            "ancho": 104, "alto": 104, "cuando": "trabajando", "z": 1,
            "imagen": imagen, "lados": lados if lados is not None else 6,
            "redondeo": _entero(cfg.get("hud_marco_redondeo", 0), 0),
            "rotacion": _entero(cfg.get("hud_marco_rot", 0), 0),
        }
    piezas["titulo"] = {
        "tipo": "texto", "superficie": "overlay", "x": 130, "y": 22,
        "ancho": 310, "alto": 32, "tam": 19, "origen": "nombre",
        "color": "acento", "cuando": "trabajando", "z": 2,
    }
    piezas["estado"] = {
        "tipo": "texto", "superficie": "overlay", "x": 130, "y": 54,
        "ancho": 310, "alto": 20, "tam": 10, "origen": "detalle",
        "color": "texto_tenue", "cuando": "trabajando", "z": 2,
    }
    piezas["ondaeve"] = {
        "tipo": "onda", "superficie": "overlay", "x": 130, "y": 82,
        "ancho": 310, "alto": 30, "cuando": "trabajando",
        "fuente": "microfono", "z": 2,
        "estilo": str(cfg.get("hud_onda", "barras") or "barras"),
    }
    return piezas
