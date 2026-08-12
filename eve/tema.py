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
    "oscuro": {
        "fondo": "#101114", "panel": "#1c1e24", "texto": "#e8eaed",
        "texto_tenue": "#9aa0a6", "acento": "#8ab4f8", "acento2": "#3c5a86",
        "borde": "#3c4043", "alerta": "#f28b82",
    },
    "claro": {
        "fondo": "#f5f6f8", "panel": "#ffffff", "texto": "#1f2328",
        "texto_tenue": "#616a75", "acento": "#0b6bcb", "acento2": "#9fc4ec",
        "borde": "#d0d7de", "alerta": "#c0392b",
    },
}

NOMBRES = [*PALETAS, "personalizado"]
BASE_PERSONALIZADO = "tactico"


def resolver(cfg: dict) -> dict:
    """Paleta final: el preset elegido, con los colores propios encima.

    Devuelve siempre los ocho roles. Si el usuario dejo un campo vacio o puso
    cualquier cosa, se queda el del preset: un color invalido en un canvas de tk
    es una excepcion, y no vale la pena tirar el overlay por una letra de mas.
    """
    nombre = cfg.get("ui_tema", "tactico")
    paleta = dict(PALETAS.get(nombre, PALETAS[BASE_PERSONALIZADO]))
    if nombre == "personalizado":
        for rol in ROLES:
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


def aplicar_ttk(style, paleta: dict) -> None:
    """Pinta los widgets ttk con la paleta. Requiere el tema `clam`."""
    fondo, panel = paleta["fondo"], paleta["panel"]
    texto, tenue = paleta["texto"], paleta["texto_tenue"]
    acento, borde = paleta["acento"], paleta["borde"]

    style.configure(".", background=fondo, foreground=texto,
                    fieldbackground=panel, bordercolor=borde,
                    lightcolor=panel, darkcolor=panel, focuscolor=acento)
    style.configure("TFrame", background=fondo)
    style.configure("TLabel", background=fondo, foreground=texto)
    style.configure("Ayuda.TLabel", background=fondo, foreground=tenue)
    style.configure("Error.TLabel", background=fondo, foreground=paleta["alerta"])
    style.configure("Ok.TLabel", background=fondo, foreground=acento)
    style.configure("Titulo.TLabel", background=fondo, foreground=acento)
    style.configure("TLabelframe", background=fondo, bordercolor=borde)
    style.configure("TLabelframe.Label", background=fondo, foreground=tenue)
    style.configure("TButton", background=panel, foreground=texto, bordercolor=borde)
    style.map("TButton",
              background=[("active", borde), ("pressed", acento)],
              foreground=[("pressed", fondo)])
    style.configure("TEntry", fieldbackground=panel, foreground=texto,
                    insertcolor=texto, bordercolor=borde)
    style.configure("TCombobox", fieldbackground=panel, background=panel,
                    foreground=texto, arrowcolor=acento)
    style.map("TCombobox", fieldbackground=[("readonly", panel)],
              foreground=[("readonly", texto)])
    style.configure("TCheckbutton", background=fondo, foreground=texto)
    style.map("TCheckbutton", background=[("active", fondo)],
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
    style.configure("TScale", background=fondo, troughcolor=panel)
