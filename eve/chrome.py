"""Lo que ttk no sabe dibujar: esquinas redondeadas, tarjetas, anillos de foco.

ttk no tiene esquinas redondeadas, ni sombras, ni desenfoque. No es una opcion
que falte activar: los widgets los dibuja el motor de temas de Tk y su
vocabulario no las incluye. Asi que lo que en el diseno es una tarjeta con
radio 10 hay que pintarlo sobre un Canvas.

**Y aca esta la decision que sostiene todo este modulo:** se dibuja el CROMO y
no los controles. El marco de la tarjeta, el separador, la pastilla de la
seccion activa, el anillo de foco -- eso se pinta. El campo de texto, el
desplegable y la casilla siguen siendo widgets de ttk de verdad, puestos
encima con `create_window()`.

La razon no es pereza. Un control dibujado sobre un Canvas es **invisible para
un lector de pantalla**: no tiene rol, ni nombre, ni estado que anunciar. Las
HIG ponen la accesibilidad por encima de lo visual, y ademas habria que volver
a resolver a mano el orden del tabulador, el cursor de texto, la seleccion, el
portapapeles y el IME -- cosas que ttk da gratis y que se hacen mal muy facil.
Dibujar el marco y dejar el control es como lo hacen las aplicaciones que
envuelven controles nativos, y se gana todo lo que se ve sin perder nada de lo
que se usa.

Todo lo de aca pinta con los roles de `tema`, nunca con un color propio: ver
`tema.PISOS`, que es lo que mide que cada par se lea.
"""

import tkinter as tk

from . import tema

# El radio de una tarjeta. Uno solo en todo el panel: el diseno se sostiene
# porque hay pocas medidas distintas, no porque cada una sea la correcta.
RADIO = 10
# Cuanto respira el contenido adentro de su tarjeta. Sale de `tema.ESPACIO`.
MARGEN = 12


def rect_redondeado(lienzo, x0, y0, x1, y1, radio=RADIO, **kw):
    """Un rectangulo con las esquinas redondeadas, como un solo poligono.

    Tk no tiene esto. La forma habitual de fingirlo es `create_polygon` con
    `smooth=True`, pero eso redondea TODO el contorno --los lados dejan de ser
    rectos-- y a radio chico se nota como un borde blando. Aca se calculan los
    puntos del arco de cada esquina, asi que los lados quedan rectos y el radio
    es el que se pidio.

    Ocho puntos por esquina alcanzan: a radio 10 el paso es de poco mas de un
    pixel, y por debajo de eso el suavizado de Tk no distingue.
    """
    radio = max(0, min(radio, abs(x1 - x0) / 2, abs(y1 - y0) / 2))
    if radio <= 0:
        return lienzo.create_rectangle(x0, y0, x1, y1, **kw)

    import math

    pasos = 8
    puntos = []
    # (centro del arco, angulo inicial) por esquina, en sentido horario desde
    # la de arriba a la izquierda.
    esquinas = (
        (x0 + radio, y0 + radio, 180),
        (x1 - radio, y0 + radio, 270),
        (x1 - radio, y1 - radio, 0),
        (x0 + radio, y1 - radio, 90),
    )
    for cx, cy, desde in esquinas:
        for i in range(pasos + 1):
            a = math.radians(desde + 90 * i / pasos)
            puntos.extend((cx + radio * math.cos(a), cy + radio * math.sin(a)))
    return lienzo.create_polygon(puntos, smooth=False, **kw)


class Tarjeta(tk.Canvas):
    """Un Canvas que dibuja una tarjeta y hospeda widgets de ttk adentro.

    Se usa como contenedor: `t = Tarjeta(padre, paleta)` y despues todo lo que
    vaya adentro se empaqueta en `t.cuerpo`, que es un `ttk.Frame` de siempre.
    El Canvas solo pinta el fondo redondeado y el contorno.

    El alto se ajusta SOLO al del contenido. Es lo unico delicado del modulo:
    un Canvas no crece con lo que tiene adentro --no es un gestor de
    geometria-- asi que hay que mirar el `<Configure>` del cuerpo y seguirlo.
    Sin eso, plegar una seccion deja el hueco y desplegarla la recorta.
    """

    def __init__(self, padre, paleta: dict, margen: int = MARGEN, **kw):
        from tkinter import ttk

        super().__init__(padre, highlightthickness=0, borderwidth=0,
                         background=paleta["fondo"], **kw)
        self.paleta = paleta
        self.margen = margen
        self._forma = None
        self.cuerpo = ttk.Frame(self)
        self._ventana = self.create_window(
            (margen, margen), window=self.cuerpo, anchor="nw")
        self.cuerpo.bind("<Configure>", self._seguir)
        self.bind("<Configure>", self._seguir)

    def _seguir(self, _e=None) -> None:
        """Que el Canvas mida lo que mide su contenido, y repintar la tarjeta."""
        ancho = max(1, self.winfo_width())
        alto = self.cuerpo.winfo_reqheight() + self.margen * 2
        if self.winfo_height() != alto:
            self.configure(height=alto)
        self.itemconfigure(self._ventana, width=max(1, ancho - self.margen * 2))
        self.pintar()

    def _medida(self, opcion: str, medido: int) -> int:
        """Lo que mide de verdad, o lo que se pidio si todavia no se mapeo.

        Un Canvas sin mapear devuelve 1 en `winfo_width`, y con ancho 1 el
        radio se acota a cero y la tarjeta sale CUADRADA. En la practica se
        corrige sola en el primer `<Configure>`, asi que no se ve -- pero
        dibujar una forma degenerada y confiar en que despues alguien la
        arregle es la clase de cosa que un dia deja de arreglarse.
        """
        return medido if medido > 1 else max(1, int(self.cget(opcion)))

    def pintar(self) -> None:
        ancho = self._medida("width", self.winfo_width())
        alto = self._medida("height", self.winfo_height())
        if self._forma is not None:
            self.delete(self._forma)
        self._forma = rect_redondeado(
            self, 0.5, 0.5, ancho - 0.5, alto - 0.5,
            fill=self.paleta["panel"], outline=self.paleta["borde"], width=1)
        # Debajo de la ventana con los controles, o los taparia.
        self.tag_lower(self._forma)

    def aplicar(self, paleta: dict) -> None:
        """Otro tema, sin reconstruir nada. El panel cambia de tema en vivo."""
        self.paleta = paleta
        self.configure(background=paleta["fondo"])
        self.pintar()


class Riel(tk.Canvas):
    """La barra lateral de secciones: pastillas dibujadas, foco de verdad.

    Reemplaza a las siete pestañas de arriba, que ya rozaban el ancho de la
    ventana y no dejaban lugar al buscador. Ajustes de Windows 11 y de macOS
    usan barra lateral por lo mismo.

    Se dibuja --la pastilla de la activa tiene esquinas redondeadas-- pero NO
    deja de ser accesible: el Canvas entra en el tabulador, las flechas mueven
    la seleccion, Enter y espacio activan, y cada item se anuncia por su texto.
    Un riel dibujado que solo respondiera al raton seria justo lo que este
    modulo dice que no hay que hacer.
    """

    ALTO_ITEM = 34
    SANGRIA = 8

    def __init__(self, padre, paleta: dict, items, al_elegir, ancho=214, **kw):
        super().__init__(padre, highlightthickness=0, borderwidth=0, width=ancho,
                         background=paleta["fondo"], takefocus=True, **kw)
        self.paleta = paleta
        self.items = list(items)          # [(clave, rotulo)]
        self.al_elegir = al_elegir
        self.elegido = self.items[0][0] if self.items else ""
        self._foco = False
        self.bind("<Button-1>", self._clic)
        self.bind("<Up>", lambda e: self._mover(-1))
        self.bind("<Down>", lambda e: self._mover(1))
        self.bind("<Return>", lambda e: self._activar())
        self.bind("<space>", lambda e: self._activar())
        self.bind("<FocusIn>", self._entra_foco)
        self.bind("<FocusOut>", self._sale_foco)
        self.bind("<Configure>", lambda e: self.pintar())
        self.configure(height=len(self.items) * self.ALTO_ITEM + self.SANGRIA * 2)

    # --- interaccion ------------------------------------------------------

    def _indice(self) -> int:
        for i, (clave, _r) in enumerate(self.items):
            if clave == self.elegido:
                return i
        return 0

    def _clic(self, evento) -> None:
        self.focus_set()
        i = (evento.y - self.SANGRIA) // self.ALTO_ITEM
        if 0 <= i < len(self.items):
            self.elegido = self.items[i][0]
            self.pintar()
            self.al_elegir(self.elegido)

    def _mover(self, paso: int) -> str:
        """Las flechas MUEVEN y activan, como una lista de sistema."""
        i = max(0, min(len(self.items) - 1, self._indice() + paso))
        self.elegido = self.items[i][0]
        self.pintar()
        self.al_elegir(self.elegido)
        return "break"

    def _activar(self) -> str:
        self.al_elegir(self.elegido)
        return "break"

    def _entra_foco(self, _e=None) -> None:
        self._foco = True
        self.pintar()

    def _sale_foco(self, _e=None) -> None:
        self._foco = False
        self.pintar()

    # --- dibujo -----------------------------------------------------------

    def pintar(self) -> None:
        self.delete("all")
        p, ancho = self.paleta, max(1, self.winfo_width())
        fuente = (self._familia(), tema.pt("cuerpo", self._tam()))
        for i, (clave, rotulo) in enumerate(self.items):
            y = self.SANGRIA + i * self.ALTO_ITEM
            activo = clave == self.elegido
            if activo:
                rect_redondeado(self, 6, y + 2, ancho - 6, y + self.ALTO_ITEM - 2,
                                radio=7, fill=p["panel"], outline="")
            if activo and self._foco:
                # El anillo de foco va SOBRE la pastilla y con el acento: es la
                # unica manera de saber que el teclado esta aca sin mirar el
                # raton, y ttk no lo dibuja en un Canvas.
                rect_redondeado(self, 6, y + 2, ancho - 6, y + self.ALTO_ITEM - 2,
                                radio=7, fill="", outline=p["acento"], width=2)
            self.create_text(
                20, y + self.ALTO_ITEM / 2, text=rotulo, anchor="w", font=fuente,
                fill=p["texto"] if activo else p["texto_tenue"])

    def _familia(self) -> str:
        from . import plataforma

        return "Segoe UI" if plataforma.WINDOWS else "Helvetica"

    def _tam(self) -> int:
        return 0   # el de la escala; el panel lo pisa si el usuario eligio otro

    def aplicar(self, paleta: dict) -> None:
        self.paleta = paleta
        self.configure(background=paleta["fondo"])
        self.pintar()
