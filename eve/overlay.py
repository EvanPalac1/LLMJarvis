"""Overlay HUD + subtitulos: lo que Eve muestra encima de todo lo demas.

Corre como proceso propio (`Eve --overlay`), igual que el panel, porque el
listener ya le dio su hilo principal al icono de la bandeja.

Lo que hace que sirva es que la ventana no roba el foco ni se come los clics:
podes estar jugando y el HUD aparece encima sin sacarte del juego. Eso vive en
`plataforma.ventana_fantasma`.
"""

import math
import os
import sys
import time
import tkinter as tk
from collections import deque

from . import imagenes, plataforma, store, tema

# Color que la ventana vuelve invisible en modo "recortado". Uno raro a
# proposito: cualquier pixel exactamente de este color desaparece, asi que no
# puede ser uno que alguien elija para su tema.
MAGICO = "#010203"

CUADRO = 33          # ms entre cuadros, ~30 por segundo
CADA_LECTURA = 3     # leer el estado 1 de cada N cuadros: 10 Hz alcanza
MUESTRAS = 56        # barras de la onda
DESVANECER = 2.5     # segundos sin actividad antes de esconderse en modo auto

ANCHO, ALTO = 460, 128   # a escala 100


def _num(cfg: dict, clave: str, minimo: float, maximo: float) -> float:
    """Un numero de la config, acotado. El panel deja escribir cualquier cosa."""
    try:
        return max(minimo, min(maximo, float(cfg.get(clave, minimo))))
    except (TypeError, ValueError):
        return minimo


def acotar(x: int, y: int, ancho: int, alto: int, limites: tuple) -> tuple[int, int]:
    """Mete la posicion dentro del escritorio, sea cual sea.

    Funcion aparte y sin tkinter para poder probarla sin pantalla. Con dos
    monitores las coordenadas pueden ser negativas, y desenchufar el segundo
    dejaria el cartel fuera de la vista sin forma de traerlo de vuelta.
    """
    x0, y0, ancho_total, alto_total = limites
    x1 = max(x0, x0 + ancho_total - ancho)
    y1 = max(y0, y0 + alto_total - alto)
    return max(x0, min(x, x1)), max(y0, min(y, y1))


def _alto_item(lienzo, item) -> float:
    x0, y0, x1, y1 = lienzo.bbox(item)
    return y1 - y0


class Ventana(tk.Toplevel):
    """Toplevel sin borde, encima de todo y transparente a los clics."""

    def __init__(self, raiz, alpha: float):
        super().__init__(raiz)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", alpha)
        self.lienzo = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.lienzo.pack(fill="both", expand=True)
        self._fantasma = None
        self._transparente = None

    def fantasma(self, atraviesan: bool) -> None:
        """Aplica los estilos solo cuando cambia: SetWindowPos cada cuadro
        provoca parpadeo y trabajo inutil."""
        if self._fantasma == atraviesan:
            return
        self._fantasma = atraviesan
        plataforma.ventana_fantasma(self, atraviesan_los_clics=atraviesan)

    def colocar(self, x: int, y: int, ancho: int, alto: int) -> None:
        self.geometry(f"{ancho}x{alto}+{x}+{y}")

    def transparente(self, color: str) -> None:
        """Hace invisible todo lo que sea exactamente de ese color. '' lo apaga.

        Solo existe en Windows; en el resto se ignora y el cartel queda como una
        caja, que es lo que hay.
        """
        if self._transparente == color:
            return
        self._transparente = color
        try:
            self.attributes("-transparentcolor", color)
        except tk.TclError:
            pass


class Pintor:
    """Dibuja el HUD en cualquier canvas.

    Aparte de la ventana porque la vista previa del panel usa exactamente este
    dibujo: si fueran dos implementaciones, la previa mentiria apenas se toque
    una de las dos.
    """

    def __init__(self, cfg: dict, paleta: dict):
        self.niveles = deque([0.0] * MUESTRAS, maxlen=MUESTRAS)
        self.nivel = 0.0
        self.imagen = None  # referencia viva: tk descarta las que no se guardan
        self.fondo = imagenes.Fondo()
        self.aplicar(cfg, paleta)

    def aplicar(self, cfg: dict, paleta: dict) -> None:
        self.cfg, self.paleta = cfg, paleta
        self.esc = _num(cfg, "hud_escala", 50, 300) / 100
        self.ancho, self.alto = int(ANCHO * self.esc), int(ALTO * self.esc)
        self.fondo.aplicar(
            str(cfg.get("hud_fondo", "")), self.ancho, self.alto,
            str(cfg.get("hud_fondo_ajuste", "recortar")),
            int(_num(cfg, "hud_fondo_opacidad", 0, 100)),
            int(_num(cfg, "hud_fondo_tinte", 0, 100)),
            paleta["panel"], paleta["acento"],
        )
        self.imagen = None
        ruta = str(cfg.get("hud_icono", ""))
        if ruta.lower().endswith((".png", ".gif")) and os.path.exists(ruta):
            try:
                # PhotoImage de tk lee PNG desde Tk 8.6: no hace falta PIL, que
                # ademas habria que empaquetar aparte para el binario.
                img = tk.PhotoImage(file=ruta)
                factor = max(1, round(img.width() / (72 * self.esc)))
                self.imagen = img.subsample(factor, factor)
            except tk.TclError:
                self.imagen = None  # archivo raro: se cae al dibujo de siempre

    def avanzar(self, objetivo: float) -> None:
        """Suaviza hacia el ultimo nivel leido y corre la onda un lugar.

        El nivel llega 10 veces por segundo pero se dibuja 30: sin interpolar,
        la onda se ve a saltos.
        """
        self.nivel += (objetivo - self.nivel) * 0.35
        self.niveles.append(self.nivel)

    def pintar(self, c, estado: str, titulo: str, linea2: str) -> None:
        p = self.paleta
        c.delete("all")
        e = self.esc
        self._contorno(c)

        alto_icono = self.alto - 24 * e
        if self.cfg.get("hud_icono") == "ninguno" and self.imagen is None:
            x = 26 * e  # sin icono no se deja el hueco donde iria
        else:
            cx, cy = 26 * e + alto_icono / 2, self.alto / 2
            self._icono(c, cx, cy, alto_icono / 2, activo=estado != "reposo")
            x = 26 * e + alto_icono + 22 * e
        c.create_text(x, self.alto * 0.30, text=titulo.upper(), anchor="w",
                      fill=p["acento"], font=("Segoe UI", int(19 * e), "bold"))
        c.create_text(x, self.alto * 0.50, text=linea2, anchor="w",
                      fill=p["texto_tenue"], font=("Segoe UI", int(10 * e)))
        self._onda(c, x, self.alto * 0.74, self.ancho - x - 22 * e, 30 * e)

    # --- piezas ------------------------------------------------------------

    def _contorno(self, c) -> None:
        p = self.paleta
        w, h, e = self.ancho - 1, self.alto - 1, self.esc
        color, grosor = p["borde"], max(1, int(1.6 * e))
        tipo = self.cfg.get("hud_contorno", "esquinas")
        m = 3 * e

        # El relleno: la imagen si hay, el color del panel si no.
        cuadro = self.fondo.actual()
        if cuadro is not None:
            c.create_image(0, 0, image=cuadro, anchor="nw")
        else:
            c.create_rectangle(m, m, w - m, h - m, fill=p["panel"], outline="")

        # Las formas con esquinas cortadas se tapan por fuera. Un canvas no sabe
        # recortar una imagen contra un poligono, asi que se pinta lo que sobra:
        # con el color de fondo, o con el magico si se pidio recortar de verdad,
        # y ahi las esquinas dejan ver el escritorio.
        corte = 14 * e if tipo == "hexagonal" else 16 * e
        if tipo in ("hexagonal", "biselado"):
            sobrante = MAGICO if self.cfg.get("hud_forma") == "recortado" else p["fondo"]
            esquinas = [((m, m), (m + corte, m), (m, m + corte)),
                        ((w - m, h - m), (w - m - corte, h - m), (w - m, h - m - corte))]
            if tipo == "hexagonal":
                esquinas += [((w - m, m), (w - m - corte, m), (w - m, m + corte)),
                             ((m, h - m), (m + corte, h - m), (m, h - m - corte))]
            for triangulo in esquinas:
                c.create_polygon([v for punto in triangulo for v in punto],
                                 fill=sobrante, outline=sobrante)

        if tipo == "ninguno":
            return
        if tipo == "linea":
            c.create_rectangle(m, m, w - m, h - m, outline=color, width=grosor)
        elif tipo == "doble":
            c.create_rectangle(m, m, w - m, h - m, outline=color, width=grosor)
            c.create_rectangle(m + 5 * e, m + 5 * e, w - m - 5 * e, h - m - 5 * e,
                               outline=p["acento2"], width=1)
        elif tipo == "esquinas":
            # Cuatro escuadras, como el HUD de la referencia.
            largo = 26 * e
            for ex, ey, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
                                   (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
                c.create_line(ex, ey, ex + largo * dx, ey, fill=p["acento"], width=grosor)
                c.create_line(ex, ey, ex, ey + largo * dy, fill=p["acento"], width=grosor)
        elif tipo == "hexagonal":
            corte = 14 * e
            c.create_polygon(
                m + corte, m, w - m - corte, m, w - m, m + corte,
                w - m, h - m - corte, w - m - corte, h - m,
                m + corte, h - m, m, h - m - corte, m, m + corte,
                outline=color, width=grosor, fill="",
            )
        elif tipo == "biselado":
            corte = 16 * e
            c.create_polygon(
                m + corte, m, w - m, m, w - m, h - m - corte,
                w - m - corte, h - m, m, h - m, m, m + corte,
                outline=color, width=grosor, fill="",
            )

    def _icono(self, c, cx: float, cy: float, r: float, activo: bool) -> None:
        p = self.paleta
        forma = str(self.cfg.get("hud_icono", "hexagono"))
        color = p["acento"] if activo else p["acento2"]
        grosor = max(1, int(1.6 * self.esc))

        if forma == "hexagono" or self.imagen is not None or forma not in (
            "circulo", "cuadrado", "ninguno"
        ):
            puntos = [
                (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                for a in range(-90, 270, 60)
            ]
            c.create_polygon([v for xy in puntos for v in xy],
                             outline=color, width=grosor, fill=p["fondo"])
        elif forma == "circulo":
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=color, width=grosor, fill=p["fondo"])
        elif forma == "cuadrado":
            c.create_rectangle(cx - r, cy - r, cx + r, cy + r,
                               outline=color, width=grosor, fill=p["fondo"])

        if self.imagen is not None:
            c.create_image(cx, cy, image=self.imagen)
            return
        if forma == "ninguno":
            return
        # Silueta: una cabeza y unos hombros. Dibujada y no una imagen, asi
        # escala sin pixelarse y no hay que empaquetar ningun archivo.
        cab = r * 0.34
        c.create_oval(cx - cab, cy - r * 0.62, cx + cab, cy - r * 0.62 + cab * 2,
                      fill=p["acento2"], outline="")
        c.create_arc(cx - r * 0.62, cy - r * 0.12, cx + r * 0.62, cy + r * 1.15,
                     start=0, extent=180, fill=p["acento2"], outline="")

    def _onda(self, c, x: float, y: float, ancho: float, alto: float) -> None:
        tipo = self.cfg.get("hud_onda", "barras")
        if tipo == "ninguna" or ancho <= 0:
            return
        p = self.paleta
        paso = ancho / MUESTRAS
        grosor = max(1, int(paso * 0.45))
        puntos = []
        for i, v in enumerate(self.niveles):
            px = x + i * paso + paso / 2
            h = max(1.0, v * alto)
            color = tema.mezclar(p["acento2"], p["acento"], v)
            if tipo == "barras":
                c.create_line(px, y - h / 2, px, y + h / 2, fill=color,
                              width=grosor, capstyle="round")
            elif tipo == "espejo":
                hueco = alto * 0.09
                c.create_line(px, y - hueco - h / 2, px, y - hueco, fill=color, width=grosor)
                c.create_line(px, y + hueco, px, y + hueco + h / 2, fill=color, width=grosor)
            elif tipo == "puntos":
                rr = max(1.0, grosor * (0.35 + v))
                c.create_oval(px - rr, y - rr, px + rr, y + rr, fill=color, outline="")
            else:  # linea
                puntos += [px, y - h / 2]
        if puntos and len(puntos) >= 4:
            c.create_line(*puntos, fill=p["acento"], width=max(1, int(1.6 * self.esc)),
                          smooth=True)

class Hud(Ventana):
    """La ventana del HUD. El dibujo lo pone el Pintor."""

    def __init__(self, raiz, cfg: dict, paleta: dict):
        super().__init__(raiz, _num(cfg, "hud_opacidad", 10, 100) / 100)
        self.pintor = Pintor(cfg, paleta)
        self.aplicar(cfg, paleta)

    def aplicar(self, cfg: dict, paleta: dict) -> None:
        self.pintor.aplicar(cfg, paleta)
        self.ancho, self.alto = self.pintor.ancho, self.pintor.alto
        self.esc = self.pintor.esc
        self.attributes("-alpha", _num(cfg, "hud_opacidad", 10, 100) / 100)
        # En modo recortado todo lo que quede del color magico desaparece, asi
        # que el cartel deja de ser un rectangulo y se ve solo su forma.
        recortado = cfg.get("hud_forma") == "recortado"
        self.transparente(MAGICO if recortado else "")
        self.lienzo.configure(bg=MAGICO if recortado else paleta["fondo"])

    def avanzar(self, objetivo: float) -> None:
        self.pintor.avanzar(objetivo)

    def pintar(self, estado: str, titulo: str, linea2: str) -> None:
        self.pintor.pintar(self.lienzo, estado, titulo, linea2)


class Subtitulos(Ventana):
    """Lo que se dijo, debajo del HUD."""

    def __init__(self, raiz, cfg: dict, paleta: dict):
        super().__init__(raiz, _num(cfg, "sub_opacidad", 10, 100) / 100)
        self._ultimo = None
        self.fondo = imagenes.Fondo()
        self.aplicar(cfg, paleta)

    def aplicar(self, cfg: dict, paleta: dict) -> None:
        self.cfg, self.paleta = cfg, paleta
        self.esc = _num(cfg, "hud_escala", 50, 300) / 100
        self.tam = int(_num(cfg, "sub_tam", 8, 48) * self.esc)
        self.lineas = int(_num(cfg, "sub_lineas", 1, 6))
        self.ancho = int(ANCHO * self.esc)
        self.alto = self._alto_de(self.lineas)
        self.attributes("-alpha", _num(cfg, "sub_opacidad", 10, 100) / 100)
        self.lienzo.configure(bg=paleta["fondo"])
        # Alto maximo: el texto puede crecer, y recargar la imagen cada vez que
        # cambia un renglon costaria mas que dibujarla un poco mas grande.
        self.fondo.aplicar(
            str(cfg.get("sub_fondo", "")), self.ancho, self._alto_de(6),
            str(cfg.get("sub_fondo_ajuste", "recortar")),
            int(_num(cfg, "sub_fondo_opacidad", 0, 100)),
            int(_num(cfg, "sub_fondo_tinte", 0, 100)),
            paleta["panel"], paleta["acento"],
        )
        self._ultimo = None  # forzar redibujo con los valores nuevos

    def _alto_de(self, lineas: float) -> int:
        return int(self.tam * 1.62 * lineas + 16 * self.esc)

    def pintar(self, usuario: str, eve: str) -> bool:
        """Dibuja y dice si hay algo que mostrar.

        Solo redibuja cuando el texto cambio: no se anima, y medir el alto real
        del texto envuelto cuesta lo suyo como para hacerlo 30 veces por segundo.
        """
        muestra = self.cfg.get("sub_muestra", "ambos")
        filas = []
        if usuario and muestra in ("ambos", "usuario"):
            filas.append((f"» {usuario}", self.paleta["texto_tenue"]))
        if eve and muestra in ("ambos", "eve"):
            filas.append((eve, self.paleta["texto"]))
        if not filas:
            self._ultimo = None
            return False
        # Con un GIF de fondo hay que redibujar aunque el texto no cambie, o la
        # animacion se congela apenas termina de aparecer la frase.
        if filas == self._ultimo and len(self.fondo.cuadros) <= 1:
            return True
        self._ultimo = list(filas)

        c, p = self.lienzo, self.paleta
        margen = 12 * self.esc
        # Tope por entrada, medido en alto propio y no en la y de la hoja: con
        # dos entradas, la segunda arranca ya pasada del tope y se recortaba sola.
        alto_max = self.tam * 1.62 * self.lineas
        tope = self._alto_de(self.lineas + 1)
        ancho_texto = self.ancho - margen * 2

        c.delete("all")
        # El fondo va primero para que quede debajo, y se le corrige el alto al
        # final, cuando ya se sabe cuanto ocupo el texto envuelto.
        cuadro = self.fondo.actual()
        fondo = c.create_rectangle(0, 0, self.ancho, tope, fill=p["panel"], outline="")
        if cuadro is not None:
            c.create_image(0, 0, image=cuadro, anchor="nw")
        c.create_line(0, 0, self.ancho, 0, fill=p["acento"],
                      width=max(1, int(2 * self.esc)))

        y = 8 * self.esc
        for texto, color in filas:
            item = c.create_text(margen, y, text=texto, anchor="nw", fill=color,
                                 width=ancho_texto, font=("Segoe UI", self.tam))
            # Cuantos renglones ocupa no se sabe hasta dibujarlo. Si no entra, se
            # sacan palabras del principio: en un subtitulo importa el final.
            palabras = texto.split()
            while len(palabras) > 3 and _alto_item(c, item) > alto_max:
                palabras.pop(0)
                c.itemconfigure(item, text="… " + " ".join(palabras))
            y = c.bbox(item)[3] + 4 * self.esc

        self.alto = int(y + 6 * self.esc)
        c.coords(fondo, 0, 0, self.ancho, self.alto)
        return True


class Overlay:
    """Junta las dos ventanas, lee el estado y atiende el modo mover."""

    def __init__(self):
        self.raiz = tk.Tk()
        self.raiz.withdraw()
        self.cfg = store.load_config()
        self.paleta = tema.resolver(self.cfg)
        self.hud = Hud(self.raiz, self.cfg, self.paleta)
        self.sub = Subtitulos(self.raiz, self.cfg, self.paleta)
        self.visible = False
        self.nacio = time.time()
        self.ultimo_activo = 0.0
        self.cuadro = 0
        self.estado = {}
        self.mtime_cfg = self._mtime()
        self.arrastre = None
        for v in (self.hud, self.sub):
            v.lienzo.bind("<Button-1>", self._agarrar)
            v.lienzo.bind("<B1-Motion>", self._mover)
            v.lienzo.bind("<ButtonRelease-1>", self._soltar)
        self._ubicar()

    # --- posicion ----------------------------------------------------------

    def _ubicar(self) -> None:
        x, y = self._posicion()
        self.hud.colocar(x, y, self.hud.ancho, self.hud.alto)
        hueco = int(_num(self.cfg, "sub_separacion", 0, 200) * self.hud.esc)
        self.sub.colocar(x, y + self.hud.alto + hueco, self.sub.ancho, self.sub.alto)

    def _posicion(self) -> tuple[int, int]:
        x = int(_num(self.cfg, "hud_x", -20000, 20000))
        y = int(_num(self.cfg, "hud_y", -20000, 20000))
        return acotar(x, y, self.hud.ancho, self.hud.alto + self.sub.alto,
                      self._escritorio())

    def _escritorio(self) -> tuple:
        """(x0, y0, ancho, alto) de todos los monitores juntos.

        En Windows tk no implementa el virtual root y devuelve el monitor
        principal, asi que se le pregunta al sistema: si no, arrastrar el cartel
        al segundo monitor lo devolvia de un salto al primero.
        """
        if plataforma.WINDOWS:
            import ctypes

            u = ctypes.windll.user32
            return tuple(u.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        r = self.raiz
        return (r.winfo_vrootx(), r.winfo_vrooty(),
                r.winfo_vrootwidth(), r.winfo_vrootheight())

    # --- arrastre ----------------------------------------------------------

    def _agarrar(self, evento) -> None:
        if not self.cfg.get("overlay_mover"):
            return
        self.arrastre = (evento.x_root - self.hud.winfo_x(),
                         evento.y_root - self.hud.winfo_y())

    def _mover(self, evento) -> None:
        if not self.arrastre:
            return
        dx, dy = self.arrastre
        self.cfg["hud_x"], self.cfg["hud_y"] = evento.x_root - dx, evento.y_root - dy
        self._ubicar()

    def _soltar(self, _evento) -> None:
        if not self.arrastre:
            return
        self.arrastre = None
        guardada = store.load_config()
        guardada.update({"hud_x": self.cfg["hud_x"], "hud_y": self.cfg["hud_y"],
                         "overlay_mover": False})
        store.save_config(guardada)
        self.cfg = guardada
        self.mtime_cfg = self._mtime()

    # --- ciclo -------------------------------------------------------------

    def _mtime(self) -> float:
        try:
            return os.path.getmtime(store.CONFIG_PATH)
        except OSError:
            return 0.0

    def _releer_config(self) -> None:
        actual = self._mtime()
        if actual == self.mtime_cfg:
            return
        self.mtime_cfg = actual
        self.cfg = store.load_config()
        self.paleta = tema.resolver(self.cfg)
        self.hud.aplicar(self.cfg, self.paleta)
        self.sub.aplicar(self.cfg, self.paleta)
        self._ubicar()

    def _sobra(self) -> bool:
        """El overlay es el HUD de Eve: si Eve se fue, no tiene sentido quedarse.

        Se le da margen desde que arranco porque el asistente puede estar todavia
        levantando el motor, y se respeta el modo mover: ahi lo abrio el panel
        para reubicarlo y puede que el asistente ni este corriendo.
        """
        if self.cfg.get("overlay_mover"):
            return False
        if time.time() - self.nacio < 25:
            return False
        return store.latido() is None

    def _mostrar(self, si: bool) -> None:
        if si == self.visible:
            return
        self.visible = si
        for v in (self.hud, self.sub):
            (v.deiconify if si else v.withdraw)()
        if si:
            self.hud.fantasma(not self.cfg.get("overlay_mover"))
            self.sub.fantasma(not self.cfg.get("overlay_mover"))

    def tick(self) -> None:
        self.cuadro += 1
        if self.cuadro % CADA_LECTURA == 0:
            self.estado = store.estado_overlay() or {}
            self._releer_config()
        if self.cuadro % 60 == 0:
            store.overlay_presente()
            if self._sobra():
                self.raiz.quit()
                return

        modo = self.cfg.get("overlay_modo", "auto")
        if modo == "nunca":
            self.raiz.quit()
            return

        estado = self.estado.get("estado", "reposo")
        moviendo = bool(self.cfg.get("overlay_mover"))
        if estado != "reposo":
            self.ultimo_activo = time.time()
        activo = time.time() - self.ultimo_activo < DESVANECER
        self._mostrar(modo == "siempre" or moviendo or activo)

        if self.visible:
            self.hud.fantasma(not moviendo)
            self.hud.avanzar(_num(self.estado, "nivel", 0, 1) if self.estado else 0.0)
            titulo = self.cfg.get("hud_titulo") or self.cfg.get("assistant_name", "Eve")
            linea2 = (
                "ARRASTRAME Y SOLTA PARA FIJARLO" if moviendo
                else self.estado.get("detalle") or self.cfg.get("hud_subtitulo", "")
            )
            self.hud.pintar(estado, titulo, linea2)
            alto_previo = self.sub.alto
            hay = self.sub.pintar(self.estado.get("usuario", ""), self.estado.get("eve", ""))
            if self.sub.alto != alto_previo:
                self._ubicar()  # el texto envuelto cambio de alto
            self.sub.fantasma(not moviendo)
            if hay or moviendo:
                self.sub.deiconify()
            else:
                self.sub.withdraw()

        self.raiz.after(CUADRO, self.tick)

    def correr(self) -> None:
        self.raiz.after(CUADRO, self.tick)
        self.raiz.mainloop()


def asegurar(cfg: dict | None = None) -> bool:
    """Lanza el overlay si corresponde y no hay uno ya. True si lo lanzo."""
    cfg = cfg if cfg is not None else store.load_config()
    if cfg.get("overlay_modo") == "nunca" or store.overlay_ya_corre():
        return False
    plataforma.lanzar(plataforma.comando_propio("--overlay"))
    return True


def main(argv=None) -> int:
    cfg = store.load_config()
    if cfg.get("overlay_modo") == "nunca":
        print("overlay_modo = nunca; no hay nada que mostrar.")
        return 0
    if store.overlay_ya_corre():
        print("Ya hay un overlay corriendo.")
        return 0
    store.overlay_presente()
    Overlay().correr()
    try:
        os.remove(store.OVERLAY_VIVO_PATH)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
