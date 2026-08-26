"""Paleta de colores, una sola para el panel y para el overlay.

Los colores se nombran por su papel y no por su tono ("acento", no "cian"): asi
cambiar de paleta no obliga a tocar ni un dibujo, y una paleta clara y una oscura
se describen con las mismas ocho claves.
"""

ROLES = (
    "fondo",        # el fondo de todo
    "panel",        # cajas y campos, un escalon por encima del fondo
    "texto",        # texto principal
    "texto_tenue",  # ayudas, subtitulos, lo secundario
    "acento",       # lo que tiene que saltar: la onda, el titulo, el foco
    "acento2",      # el acento apagado, para lo inactivo
    "borde",        # contornos
    "alerta",       # errores y avisos
)

PALETAS = {
    # El de la referencia: cian sobre negro azulado, tipo HUD militar.
    "tactico": {
        "fondo": "#04101a", "panel": "#0a2130", "texto": "#dbeef7",
        "texto_tenue": "#7d9aa8", "acento": "#4fc3f7", "acento2": "#1b6d8a",
        "borde": "#1f5f78", "alerta": "#ff6b5a",
    },
    "ambar": {
        "fondo": "#140d02", "panel": "#2a1c06", "texto": "#f6e6c8",
        "texto_tenue": "#a68b5e", "acento": "#ffb300", "acento2": "#8a5f00",
        "borde": "#77571a", "alerta": "#ff5252",
    },
    "fosforo": {
        "fondo": "#03120a", "panel": "#082718", "texto": "#d6f5e3",
        "texto_tenue": "#6f9c83", "acento": "#3ddc84", "acento2": "#1a7a4a",
        "borde": "#1f6b45", "alerta": "#ff7043",
    },
    "magenta": {
        "fondo": "#12040f", "panel": "#2a0a24", "texto": "#f7dff2",
        "texto_tenue": "#a97ba0", "acento": "#ff4fd8", "acento2": "#8a1b74",
        "borde": "#6f1f60", "alerta": "#ffca28",
    },
    # Las dos neutras son las de fabrica --clara en el panel, oscura en el
    # cartel-- y por eso son las unicas que se disenaron contra `PISOS` en vez
    # de a ojo. Las cuatro con color de arriba son la personalidad de alguien y
    # viajan en los perfiles exportados; estas dos son el default, que es otra
    # responsabilidad.
    "oscuro": {
        "fondo": "#16181d", "panel": "#1e2127", "texto": "#e7e9ee",
        "texto_tenue": "#a2a9b4", "acento": "#7aa2f7", "acento2": "#41598a",
        "borde": "#2e333d", "alerta": "#f7768e",
    },
    "claro": {
        "fondo": "#f6f7f9", "panel": "#ffffff", "texto": "#1a1d23",
        "texto_tenue": "#59616c", "acento": "#2563eb", "acento2": "#9dbaf7",
        # El borde se oscurecio de #dde1e6 a este: aquel daba 1.23 contra el
        # fondo y no se veia. Un borde invisible no es un borde sutil.
        "borde": "#c9d0d9", "alerta": "#c0342f",
    },
}

NOMBRES = [*PALETAS, "personalizado"]
BASE_PERSONALIZADO = "tactico"

# La escala tipografica, en PUNTOS y como desplazamiento sobre el cuerpo.
#
# Antes habia cuatro tamanos sueltos y ninguno se llamaba de ninguna manera:
# `base`, `base + 4`, un `10` puesto a mano en el cartel, y uno que se calcula
# encogiendo de 19 a 11 hasta que el titulo entre. Cinco pasos con nombre
# significa que "esto es un subtitulo" se decide una vez y no en cada linea.
#
# El cuerpo sube de 9 a 10: 9pt de Segoe UI son ~12px, que es chico para leer
# ayudas de tres renglones, y las HIG piden que el cuerpo sea comodo antes que
# denso. Los otros cuatro se cuentan DESDE el cuerpo, asi que subir el cuerpo
# --o que el usuario ponga su propio tamano-- mueve la escala entera junta.
CUERPO = 10
ESCALA = {
    "ayuda": -1,      # ayudas y notas al pie
    "cuerpo": 0,      # rotulos, campos, lo que se lee
    "subtitulo": +3,  # cabeceras de seccion
    "titulo": +7,     # el nombre de la pestana
    "display": +12,   # el nombre del asistente en el cartel
}

# La escala de espaciado, en pixeles. Antes cada padding se decidia en su
# linea: (8,6), (14,7), (10,4), (18,5), padx=12, pady=(4,10). Seis valores, y
# nada fuera de ellos: lo que hace que un panel se vea prolijo no es que cada
# hueco sea el correcto, es que haya pocos huecos distintos.
ESPACIO = (4, 8, 12, 16, 24, 32)


def pt(nombre: str, cuerpo: int = 0) -> int:
    """El tamano de un paso de la escala, en puntos.

    `cuerpo` permite partir del tamano que el usuario haya elegido en vez del
    de fabrica, que es lo que hace que su preferencia mueva toda la escala en
    vez de un solo texto.
    """
    return max(7, (cuerpo or CUERPO) + ESCALA.get(nombre, 0))


def resolver(cfg: dict, prefijo: str = "ui") -> dict:
    """Paleta final: el preset elegido, con los colores propios encima.

    `prefijo` elige de que juego de claves leer: "ui" es el del panel y "hud" el
    del cartel, que pueden tener temas distintos. Si el del cartel no esta
    definido, hereda el del panel para no obligar a configurar dos veces.

    Devuelve siempre los ocho roles. Si el usuario dejo un campo vacio o puso
    cualquier cosa, se queda el del preset: un color invalido en un canvas de tk
    es una excepcion, y no vale la pena tirar el overlay por una letra de mas.
    """
    nombre = str(cfg.get(f"{prefijo}_tema", "") or cfg.get("ui_tema", "tactico"))
    paleta = dict(PALETAS.get(nombre, PALETAS[BASE_PERSONALIZADO]))
    if nombre == "personalizado":
        for rol in ROLES:
            valor = str(cfg.get(f"{prefijo}_color_{rol}", "")).strip()
            if not _color_valido(valor) and prefijo != "ui":
                valor = str(cfg.get(f"ui_color_{rol}", "")).strip()
            if _color_valido(valor):
                paleta[rol] = valor
    return paleta


def _color_valido(valor: str) -> bool:
    """#rgb o #rrggbb. No se aceptan nombres de color a proposito: lo que el
    panel escribe siempre es hexadecimal, y asi no hay que preguntarle a tk."""
    if not valor.startswith("#") or len(valor) not in (4, 7):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in valor[1:])


def luminancia(color: str) -> float:
    """0 (negro) a 1 (blanco), con los pesos con que el ojo ve cada canal."""
    r, g, b = _rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _lineal(c: float) -> float:
    """Un canal de 0-255 a luz lineal, como lo define WCAG."""
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def ratio(uno: str, otro: str) -> float:
    """El contraste entre dos colores, 1 (iguales) a 21 (negro sobre blanco).

    Es la formula de WCAG y no la resta de `luminancia`: aquella pesa los
    canales pero no linealiza el gamma, asi que sirve para decidir "esto es
    claro u oscuro" y NO para decir si un texto se lee. La diferencia importa
    justo en los grises medios, que es donde estaban las dos fallas.
    """
    a, b = sorted((sum(k * _lineal(v) for k, v in zip((0.2126, 0.7152, 0.0722), _rgb(c)))
                   for c in (uno, otro)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def sobre(fondo: str) -> str:
    """Blanco o negro, el que se LEA sobre ese fondo. Para etiquetas.

    Existe aparte de `halo_de` porque durante mucho tiempo fueron la misma
    funcion, y eso costo una falla de contraste real: `halo_de` devuelve un
    color oscuro en las dos ramas --tiene que hacerlo, es un halo-- asi que la
    etiqueta del boton principal sobre la paleta clara quedaba en #101014
    sobre un azul oscuro: **3.60:1**, debajo del minimo de 4.5.

    Una funcion que nunca devuelve blanco no puede elegir el color de un texto.
    """
    return "#ffffff" if ratio("#ffffff", fondo) >= ratio("#111111", fondo) else "#111111"


def halo_de(color: str) -> str:
    """El halo que va DETRAS de un texto de ese color, en el cartel.

    Siempre oscuro, y a proposito: el halo existe para despegar el texto del
    escritorio, que puede ser cualquier cosa. Si alguien deja el rol `fondo` en
    el default oscuro y pinta el panel de violeta, un halo tomado de `fondo`
    dibuja manchas negras alrededor de cada letra; lo que tiene que contrastar
    es con el texto, no con la paleta.

    NO sirve para elegir el color de una etiqueta: para eso esta `sobre`.
    """
    return "#000000" if luminancia(color) > 0.5 else "#101014"


# Que par de roles tiene que contrastar con cual, y cuanto. Es la unica lista
# de esto en el proyecto: el test la recorre, asi que agregar un rol nuevo sin
# decir contra que se lee es lo que pone el test en rojo.
#
# 4.5 es el minimo de WCAG AA para texto normal. Los bordes no son texto y no
# tienen minimo formal, pero un borde que no se ve no es un borde sutil: 1.4
# es lo mas bajo que todavia dibuja una linea en una pantalla comun.
PISOS = (
    ("texto", "fondo", 4.5, "el cuerpo, sobre el fondo"),
    ("texto", "panel", 4.5, "el cuerpo, sobre una tarjeta"),
    ("texto_tenue", "fondo", 4.5, "las ayudas, sobre el fondo"),
    ("texto_tenue", "panel", 4.5, "las ayudas, sobre una tarjeta"),
    ("acento", "fondo", 3.0, "el acento como icono o anillo de foco"),
    ("acento", "panel", 3.0, "el acento sobre una tarjeta"),
    ("alerta", "fondo", 4.5, "un error se tiene que poder LEER"),
    ("alerta", "panel", 4.5, "un error sobre una tarjeta"),
    ("borde", "fondo", 1.4, "el contorno solo tiene que verse"),
    ("borde", "panel", 1.2, "un separador dentro de una tarjeta"),
)


def revisar(paleta: dict) -> list:
    """Los pares que NO llegan al piso. Lista vacia = la paleta sirve.

    Devuelve (frente, fondo, medido, piso, para_que) para que quien lo reporte
    pueda decir cual falla y por cuanto, en vez de "hay un problema de color".
    """
    malos = []
    for frente, fondo, piso, para in PISOS:
        if frente not in paleta or fondo not in paleta:
            continue
        r = ratio(paleta[frente], paleta[fondo])
        if r < piso:
            malos.append((frente, fondo, round(r, 2), piso, para))
    # La etiqueta del boton principal no es un par de roles --el color lo
    # calcula `sobre`-- pero es texto y se mide igual.
    etiqueta = sobre(paleta["acento"])
    r = ratio(etiqueta, paleta["acento"])
    if r < 4.5:
        malos.append(("etiqueta del boton", "acento", round(r, 2), 4.5,
                      "la accion principal"))
    return malos


def mezclar(uno: str, otro: str, cuanto: float) -> str:
    """Interpola dos colores. `cuanto` 0 devuelve `uno`, 1 devuelve `otro`.

    Sirve para las ondas y los degradados sin cargar ninguna libreria: tk no
    sabe mezclar colores, y son cuatro cuentas.
    """
    a, b = _rgb(uno), _rgb(otro)
    cuanto = max(0.0, min(1.0, cuanto))
    return "#%02x%02x%02x" % tuple(
        round(a[i] + (b[i] - a[i]) * cuanto) for i in range(3)
    )


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def pinta_panel(cfg: dict) -> bool:
    """Si el panel de configuracion se repinta o se deja con el aspecto nativo.

    Apagado por defecto: el tema `vista` de Windows dibuja los controles el
    sistema y no respeta los colores que uno le pone, asi que pintar obliga a
    pasar a `clam`, que cambia el aspecto de todo el panel. Que sea una decision
    explicita y no un efecto secundario de elegir una paleta para el overlay.
    """
    return bool(cfg.get("ui_pintar_panel", False))


FUENTE_POR_DEFECTO = "(la del sistema)"


def fuentes_disponibles() -> list[str]:
    """Las familias instaladas, sin las privadas que empiezan con @."""
    from tkinter import font as tkfont

    try:
        familias = sorted({f for f in tkfont.families() if not f.startswith("@")})
    except Exception:  # noqa: BLE001 - sin display no hay fuentes
        familias = []
    return [FUENTE_POR_DEFECTO, *familias]


def aplicar_fuente(raiz, familia: str, tamaño: int = 0) -> None:
    """Cambia la tipografia de TODA la ventana, en vivo.

    Las fuentes con nombre de tk son objetos compartidos: los widgets ya creados
    apuntan al mismo objeto, asi que reconfigurarlo los repinta a todos sin
    recorrer nada. `option_add`, en cambio, no es retroactivo y no serviria.
    """
    from tkinter import font as tkfont

    for nombre in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            fuente = tkfont.nametofont(nombre, root=raiz)
        except Exception:  # noqa: BLE001 - alguna puede no existir en este Tk
            continue
        cambios = {}
        if familia and familia != FUENTE_POR_DEFECTO:
            cambios["family"] = familia
        if tamaño:
            cambios["size"] = tamaño
        if cambios:
            fuente.configure(**cambios)


def repintar_tk(widget, paleta: dict) -> None:
    """Pinta los widgets que NO pasan por ttk.Style.

    Canvas, Text, Listbox, Frame de tk puro y los Toplevel tienen su color
    propio y el motor de estilos no los toca nunca. Se recorren a mano.

    **Los widgets de ttk se saltean**, y eso no es un detalle: un `ttk.Label`
    ACEPTA la opcion `background`, y ponersela PISA lo que diga el estilo. Este
    recorrido se la ponia a todo, asi que venia peleando con el motor de
    estilos y ganando -- y con el default de los widgets en `panel`, eso dejaba
    cada rotulo y cada ayuda con el color de la pagina encima de su tarjeta,
    como un recuadro mas claro que no queria decir nada. Los ttk los pinta
    `aplicar_ttk`; aca solo va lo que el motor de estilos no toca nunca.

    Igual se baja a los hijos: un `ttk.Frame` puede contener un `tk.Text`.

    Se saltea lo marcado con `_eve_color_propio`: las muestras del selector de
    color SON su color, y pintarlas con el del tema las dejaba todas iguales y
    vacias, que es justo lo contrario de para lo que estan.
    """
    from tkinter import ttk

    if getattr(widget, "_eve_color_propio", False):
        return
    if not isinstance(widget, ttk.Widget):
        opciones = {
            "background": paleta["fondo"],
            "bg": paleta["fondo"],
        }
        clase = widget.winfo_class()
        if clase in ("Text", "Listbox", "Entry"):
            opciones = {"background": paleta["panel"], "foreground": paleta["texto"],
                        "insertbackground": paleta["texto"]}
        elif clase in ("Label", "Checkbutton", "Radiobutton"):
            opciones = {"background": paleta["fondo"], "foreground": paleta["texto"]}
        for clave, valor in opciones.items():
            try:
                widget.configure(**{clave: valor})
            except Exception:  # noqa: BLE001 - no tiene esa opcion; se sigue
                pass
    for hijo in widget.winfo_children():
        repintar_tk(hijo, paleta)


def aplicar_ttk(style, paleta: dict) -> None:
    """Pinta los widgets ttk con la paleta. Requiere el tema `clam`.

    Se puede volver a llamar sobre widgets ya creados: los ttk consultan el motor
    de estilos en cada redibujado, asi que cambia el color en vivo. Lo que NO hay
    que hacer es volver a llamar `theme_use`, que resetea todos los estilos.
    """
    fondo, panel = paleta["fondo"], paleta["panel"]
    texto, tenue = paleta["texto"], paleta["texto_tenue"]
    acento, borde = paleta["acento"], paleta["borde"]

    # El fondo por defecto de los widgets es `panel` y NO `fondo`, y esto es
    # lo que hace posible la tarjeta dibujada.
    #
    # Una tarjeta se pinta sobre un Canvas --ttk no tiene esquinas
    # redondeadas-- y adentro lleva widgets de ttk de verdad. Si el `TFrame`
    # que va adentro trae `fondo`, pinta un rectangulo mas oscuro ENCIMA del
    # relleno de la tarjeta y el `panel` solo asoma como un anillo por los
    # bordes: la tarjeta queda al reves. Y no alcanza con darle un estilo al
    # marco de la tarjeta, porque cada fila crea sus propios `ttk.Frame` y
    # `ttk.Label` hijos, que volverian al default.
    #
    # Con `panel` como default, lo que necesita el color de la pagina --el
    # area de scroll, que es lo que se ve ENTRE las tarjetas-- lo pide con
    # `Fondo.TFrame`. Son unos pocos contenedores estructurales contra decenas
    # de widgets de contenido, asi que el default es el que conviene.
    style.configure(".", background=panel, foreground=texto,
                    fieldbackground=panel, bordercolor=borde,
                    lightcolor=panel, darkcolor=panel, focuscolor=acento)
    style.configure("TFrame", background=panel)
    style.configure("TLabel", background=panel, foreground=texto)
    style.configure("Ayuda.TLabel", background=panel, foreground=tenue)
    style.configure("Error.TLabel", background=panel, foreground=paleta["alerta"])
    style.configure("Ok.TLabel", background=panel, foreground=acento)
    # Lo estructural: el color de la pagina, entre tarjeta y tarjeta.
    style.configure("Fondo.TFrame", background=fondo)
    style.configure("Fondo.TLabel", background=fondo, foreground=texto)
    style.configure("FondoAyuda.TLabel", background=fondo, foreground=tenue)
    # El titulo va en `texto` y NO en `acento`: el acento significa "esto se
    # puede tocar" --la accion principal, el anillo de foco, la seccion activa--
    # y gastarlo en un titulo que no hace nada le quita ese significado a los
    # otros tres. La jerarquia sale del tamano y del peso, que es de donde
    # tiene que salir.
    style.configure("Titulo.TLabel", background=panel, foreground=texto)
    style.configure("TLabelframe", background=panel, bordercolor=borde)
    style.configure("TLabelframe.Label", background=panel, foreground=tenue)
    style.configure("TButton", background=panel, foreground=texto, bordercolor=borde)
    style.map("TButton",
              background=[("active", borde), ("pressed", acento)],
              foreground=[("pressed", fondo)])
    # La accion principal va con el acento de fondo: se distingue por color Y
    # por peso de letra, no solo por color, que es lo que pide accesibilidad.
    # `sobre(acento)` y NO `contraste(texto)`: la etiqueta va encima del
    # acento, asi que es contra el acento que tiene que contrastar. Tomarlo del
    # texto daba 3.60:1 en la paleta clara --texto oscuro, acento oscuro-- y
    # ademas `contraste` no sabia devolver blanco.
    style.configure("Principal.TButton", background=acento,
                    foreground=sobre(acento), bordercolor=acento)
    style.map("Principal.TButton",
              background=[("active", mezclar(acento, texto, 0.2)),
                          ("pressed", mezclar(acento, fondo, 0.3))])
    style.configure("TEntry", fieldbackground=panel, foreground=texto,
                    insertcolor=texto, bordercolor=borde)
    style.configure("TCombobox", fieldbackground=panel, background=panel,
                    foreground=texto, arrowcolor=acento)
    style.map("TCombobox", fieldbackground=[("readonly", panel)],
              foreground=[("readonly", texto)])
    style.configure("TCheckbutton", background=panel, foreground=texto)
    style.map("TCheckbutton", background=[("active", panel)],
              indicatorcolor=[("selected", acento)])
    style.configure("TNotebook", background=fondo, bordercolor=borde)
    style.configure("TNotebook.Tab", background=fondo, foreground=tenue)
    style.map("TNotebook.Tab",
              background=[("selected", panel)], foreground=[("selected", acento)])
    style.configure("Treeview", background=panel, fieldbackground=panel,
                    foreground=texto, bordercolor=borde)
    style.configure("Treeview.Heading", background=fondo, foreground=tenue)
    style.map("Treeview", background=[("selected", borde)],
              foreground=[("selected", texto)])
    style.configure("TScrollbar", background=panel, troughcolor=fondo,
                    bordercolor=borde, arrowcolor=tenue)
    style.configure("TSeparator", background=borde)
    # El deslizador vive DENTRO de una tarjeta, asi que su fondo es el de la
    # tarjeta; la canaleta va un escalon mas oscura para que se vea el riel.
    style.configure("TScale", background=panel, troughcolor=fondo)
