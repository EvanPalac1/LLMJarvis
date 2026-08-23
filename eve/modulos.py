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

import plistlib

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
    # Lo que Eve pone en pantalla con `E mostrar`: texto, un .txt, un .md o un
    # HTML del que se saca el texto. Es la salida que hace posible la regla
    # cero --lo que no entra en dos frases habladas va a la ventana-- y antes
    # abria el navegador, que es salirse del programa para leer tres renglones.
    "documento": {"tam": (13, "puntos"),
                  "lineas": (24, "cuantas entran"),
                  "titulo": (True, "escribir el titulo arriba"),
                  "desplazar": (0, "desde que linea se empieza a leer")},
    # La conversacion, lo mismo que muestra el panel en Actividad.
    "historial": {"tam": (11, "puntos"),
                  "lineas": (18, "cuantas entran"),
                  "cuantos": (20, "turnos hacia atras")},
    # El log de auditoria: que ejecuto Eve y como salio.
    "acciones": {"tam": (10, "puntos"),
                 "lineas": (18, "cuantas entran"),
                 "cuantas": (20, "acciones hacia atras"),
                 "resultado": (True, "mostrar tambien como salio")},
    # Un boton que dispara algo, con lista CERRADA de acciones. Ninguna es
    # destructiva: un modulo que corriera cualquier comando seria un addon sin
    # el freno de los addons, y "limpiar historial" a un clic en un tablero es
    # un accidente esperando.
    # Animacion vectorial de After Effects, via Bodymovin o LottieFiles. Escala
    # sin pixelarse y pasa el tope de 60 cuadros de un GIF, que es lo unico que
    # de verdad agrega sobre un APNG.
    "lottie": {"archivo": ("", "ruta a un .json de Lottie"),
               "cuadro": (-1, "-1 = animado; 0 o mas = ese cuadro fijo")},
    "boton": {"accion": ("panel", "que hace al tocarlo"),
              "etiqueta": ("", "que dice; vacio = el nombre de la accion"),
              "tam": (12, "puntos")},
}

# Lo unico que un modulo `boton` puede disparar. Cerrada a proposito.
ACCIONES_BOTON = {
    "panel": "Abrir el panel",
    "cartel": "Mostrar el cartel",
    "escuchar": "Probar que te escucha",
    "hablar": "Probar que te habla",
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
    "accion": list(ACCIONES_BOTON),
    "color": ["texto", "texto_tenue", "acento", "acento2", "borde", "alerta"],
}


# Tipos que pueden reaccionar al microfono en vez de al reloj. Una animacion
# importada se puede escalar y teñir, pero no reaccionar: para eso el dibujo lo
# tiene que calcular la maquina.
REACTIVOS = ("onda", "particulas")


def desde_plist(ruta: str) -> dict:
    """Los parametros de un `.plist` de particulas, traducidos a props.

    Particle Designer, Particle2dx y el resto de los editores de particulas que
    hay dando vueltas exportan el `.plist` de cocos2d, que es el formato con mas
    archivos publicados. Y es XML de numeros: vida, gravedad, color inicial,
    angulo, dispersion. **`plistlib` esta en la stdlib.**

    Asi que aca no se importa un runtime, se importa la CONFIGURACION y la corre
    el simulador de numpy que ya existe. Es el mismo criterio que con Graphify:
    se toma la arquitectura, no la dependencia. Un runtime de terceros habria
    sido una libreria nueva en los cinco objetivos para dibujar puntos que ya
    sabemos dibujar.

    Lo que no viaja: modo radial, texturas por particula, mezclas aditivas y la
    varianza de cada parametro. El simulador tiene una sola forma de nacer y un
    solo color, asi que importar mas seria guardar numeros que nadie lee.

    Devuelve {} si el archivo no se entiende. Un `.plist` roto no puede tumbar
    el panel.
    """
    try:
        with open(ruta, "rb") as f:
            d = plistlib.load(f)
    except Exception:  # noqa: BLE001 - cualquier motivo da lo mismo aca
        return {}
    if not isinstance(d, dict):
        return {}

    def num(clave, x=0.0):
        try:
            return float(d.get(clave, x))
        except (TypeError, ValueError):
            return x

    props = {}
    cant = int(num("maxParticles", 0))
    if cant > 0:
        props["cantidad"] = max(1, min(cant, 2000))
    vida = num("particleLifespan", 0)
    if vida > 0:
        props["vida"] = round(min(vida, 30.0), 3)
    # En cocos2d la y crece hacia ARRIBA y en pantalla crece hacia ABAJO. Sin el
    # signo cambiado, una fuente importada dispara sus particulas al piso.
    grav = num("gravityy", 0)
    if grav:
        props["gravedad"] = round(-grav, 3)
    vel = num("speed", 0)
    if vel > 0:
        # `speed` viene en pixeles por segundo y `velocidad` es un multiplicador
        # del tiempo. 100 px/s es mas o menos lo que hace el simulador a 1.0.
        props["velocidad"] = round(max(0.05, min(vel / 100.0, 20.0)), 2)
    if "startColorRed" in d:
        props["tinte"] = "#%02x%02x%02x" % tuple(
            max(0, min(255, int(num(f"startColor{c}", 1.0) * 255)))
            for c in ("Red", "Green", "Blue"))
    alpha = num("startColorAlpha", -1)
    if 0 <= alpha <= 1:
        props["opacidad"] = int(round(alpha * 100))
    return props


def esquema_corto() -> str:
    """El vocabulario de modulos, en el formato mas barato que se entiende.

    Va en el system prompt, o sea que viaja en CADA llamada, asi que se genera
    desde las tablas de arriba en vez de escribirse a mano: una prop nueva
    aparece sola y no hay forma de que quede vieja. Y se manda cortito --solo
    lo que distingue a un tipo de otro-- porque las props comunes ya estan
    explicadas en una linea sola.
    """
    lineas = ["Comunes a todos: " + ", ".join(
        k for k in COMUNES if k not in ("tipo", "superficie"))]
    for tipo, propias in TIPOS.items():
        detalle = ", ".join(f"{k}={v[0]!r}" for k, v in propias.items())
        lineas.append(f"  {tipo}: {detalle}" if detalle else f"  {tipo}")
    cerradas = [f"{k}={'|'.join(str(x) for x in v)}" for k, v in OPCIONES.items()]
    lineas.append("Valores cerrados: " + "; ".join(cerradas))
    return "\n".join(lineas)


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
        # El default puede depender del TIPO y no solo de la prop: un `boton`
        # nace interactivo. Sin esto `defecto_de` existia y no la llamaba nadie,
        # asi que un boton recien creado no respondia al clic --justo la trampa
        # que esa funcion venia a evitar.
        defecto = defecto_de(tipo, prop)
        if defecto is None:
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
        # Donde cae lo que Eve muestra con `E mostrar`. Viene en el tablero de
        # arranque y no solo cuando hace falta: que la primera vez que pidas
        # "mostrame X" el texto tenga donde aparecer, ya colocado y del tamaño
        # que le corresponde, en vez de caer en un modulo puesto al vuelo.
        "tdoc": {"tipo": "documento", "superficie": "tablero", "x": 40, "y": 470,
                 "ancho": 620, "alto": 200, "tam": 12, "lineas": 12,
                 "cuando": "siempre", "z": 1},
    }


# Palabras que `hud_icono` acepta ademas de una ruta a una imagen.
FORMAS_ICONO = {"ninguno": None, "circulo": 0, "hexagono": 6, "cuadrado": 4}


def defecto_de(tipo: str, prop: str):
    """El valor de fabrica de una prop PARA ESE TIPO.

    Existe por el boton: es interactivo por definicion, y pedirle al usuario que
    tilde una casilla para que un boton responda al clic es una trampa.
    """
    if tipo == "boton" and prop == "interactivo":
        return True
    par = props_de(tipo).get(prop)
    return par[0] if par else None


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
