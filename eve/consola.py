"""La ventana de actividad: modo Work para mirar, modo Edit para acomodar.

Tercera ventana del programa, proceso aparte como el cartel. Muestra los modulos
de la superficie `tablero` y, a diferencia del cartel, se puede tocar.

Los dos modos no son dos pantallas: son quien puede escribir. En Work la ventana
lee el estado y lo dibuja; en Edit el mismo dibujo se vuelve editable --clic para
elegir, Ctrl para sumar, Shift para un rango, arrastrar para mover-- y el panel
de la derecha muestra los ajustes de lo elegido.

Con varios modulos elegidos se muestran las props que TIENEN EN COMUN, no
ninguna: agrupar un modulo redondo con uno cuadrado tiene que dejar cambiar la
opacidad de los dos, que es lo unico que comparten. Y si el valor difiere entre
ellos, el campo arranca vacio y solo pisa a los dos si se escribe algo.

Lo que queda afuera a proposito: guias de alineacion, z-order anidado, copiar
estilo y snapping. Aceptar uno solo de esos es empezar a mantener un editor de
diseño, y esto tiene que seguir siendo una ventana de un asistente de voz.
"""

import json
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import ttk

from . import lienzo, modulos, plataforma, store, tema, textos
from .textos import t as tr

CUADRO = 33          # ms entre cuadros, ~30 fps
CADA_LECTURA = 3     # el estado se relee a 10 Hz, como en el cartel
PASOS_DESHACER = 20
ANCHO, ALTO = 1100, 700


class Consola:
    def __init__(self):
        self.cfg = store.load_config()
        textos.desde_config(self.cfg)
        self.raiz = tk.Tk()
        self.raiz.title(f"{self.cfg.get('assistant_name', 'Eve')} — {tr('actividad')}")
        self.raiz.geometry(f"{ANCHO}x{ALTO}")
        self.raiz.minsize(640, 420)

        self.modo = tk.StringVar(value="work")
        self.seleccion: list = []
        self.deshacer: deque = deque(maxlen=PASOS_DESHACER)
        self.estado: dict = {}
        self.cuadro = 0
        self.mtime = self._mtime()
        self._arrastre = None
        self._partes = None
        self._lista = None
        self._pagina_cache = None
        self._documento_cache = None
        self._historial_cache = None
        self._acciones_cache = None
        # Lo que un hilo de boton dejo para que lo muestre el lazo de dibujo.
        self._resultado = None

        store.consola_presente()
        self._armar()
        self._aplicar_tema()
        self._refrescar_props()

    # --- armado -----------------------------------------------------------

    def _armar(self) -> None:
        barra = ttk.Frame(self.raiz)
        barra.pack(fill="x", side="top")
        for valor, texto in (("work", "  Work  "), ("edit", "  Edit  ")):
            ttk.Radiobutton(barra, text=texto, value=valor, variable=self.modo,
                            command=self._cambio_modo,
                            style="Toolbutton").pack(side="left", padx=(6, 0), pady=6)
        self.aviso = ttk.Label(barra, text="", style="Ayuda.TLabel")
        self.aviso.pack(side="left", padx=16)
        # Solo aparece con el tablero vacio: un boton que no hace falta es ruido,
        # pero no tenerlo obliga a volver al panel a buscar donde estaba.
        self.boton_semilla = ttk.Button(barra, text=tr("Armar el tablero"),
                                        command=self._armar_tablero)
        self.botones_edit = ttk.Frame(barra)
        self.botones_edit.pack(side="right", padx=6)
        for texto, accion in ((tr("Deshacer"), self._deshacer),
                              (tr("Duplicar"), self._duplicar),
                              (tr("Borrar"), self._borrar)):
            ttk.Button(self.botones_edit, text=texto, command=accion).pack(side="left", padx=3)

        cuerpo = ttk.Frame(self.raiz)
        cuerpo.pack(fill="both", expand=True)

        self.lienzo = tk.Canvas(cuerpo, highlightthickness=0, borderwidth=0)
        self.lienzo.pack(side="left", fill="both", expand=True)
        self.pintor = lienzo.Lienzo(self.lienzo, self.cfg, "hud")

        self.panel = ttk.Frame(cuerpo, width=260)
        self.panel.pack(side="right", fill="y")
        self.panel.pack_propagate(False)
        self.props = ttk.Frame(self.panel)
        self.props.pack(fill="both", expand=True)
        self.vars: dict = {}

        self.lienzo.bind("<Button-1>", self._clic)
        self.lienzo.bind("<B1-Motion>", self._mover)
        self.lienzo.bind("<ButtonRelease-1>", self._soltar)
        self.raiz.bind("<Control-z>", lambda _e: self._deshacer())
        self.raiz.bind("<Delete>", lambda _e: self._borrar())
        self._cambio_modo()

    def _armar_tablero(self) -> None:
        """Pone los modulos de arranque y los dibuja, sin cerrar la ventana."""
        cfg = store.load_config()
        for ident, m in modulos.por_defecto_tablero().items():
            cfg = modulos.guardar(cfg, dict(m, id=ident))
        store.save_config(cfg)
        self.cfg = cfg
        self._lista = None
        self.mtime = self._mtime()
        self.aviso.config(text=tr("listo, ahi estan"))

    def _dibujar_vacio(self) -> None:
        """Que la ventana diga por que esta vacia en vez de estarlo y ya.

        Un rectangulo negro no se distingue de un programa que no arranco, y ese
        fue el reporte textual: no saber si la ventana existia. Ahora dice que
        existe, por que no muestra nada, y donde esta el boton que lo arregla.
        """
        self.lienzo.delete("vacio")
        paleta = tema.resolver(self.cfg, "ui")
        ancho = max(1, self.lienzo.winfo_width())
        alto = max(1, self.lienzo.winfo_height())
        self.lienzo.create_text(
            ancho // 2, alto // 2 - 24, tags="vacio", fill=paleta["texto"],
            font=(None, 13), justify="center",
            text=tr("Esta ventana esta vacia porque el tablero no tiene modulos."))
        self.lienzo.create_text(
            ancho // 2, alto // 2 + 12, tags="vacio", fill=paleta["texto_tenue"],
            font=(None, 10), justify="center",
            text=tr("Toca 'Armar el tablero' aca arriba para poner los de arranque,\n"
                    "o agregalos uno por uno desde el panel, en Apariencia > Modulos."))

    def _aplicar_tema(self) -> None:
        paleta = tema.resolver(self.cfg, "ui")
        if tema.pinta_panel(self.cfg):
            estilo = ttk.Style(self.raiz)
            try:
                estilo.theme_use("clam")
            except tk.TclError:
                pass
            tema.aplicar_ttk(estilo, paleta)
            self.raiz.configure(background=paleta["fondo"])
        self.lienzo.configure(bg=paleta["fondo"])

    # --- modos ------------------------------------------------------------

    def _cambio_modo(self) -> None:
        editando = self.modo.get() == "edit"
        if editando:
            self.botones_edit.pack(side="right", padx=6)
            self.panel.pack(side="right", fill="y")
            self.aviso.config(text=tr("clic para elegir · Ctrl suma · Shift agrega un rango · arrastra para mover"))
        else:
            self.botones_edit.pack_forget()
            self.panel.pack_forget()
            self.aviso.config(text="")
            self.seleccion = []
        self._dibujar_seleccion()

    # --- seleccion --------------------------------------------------------

    def _modulos(self) -> list:
        if self._lista is None:
            self._lista = modulos.listar(self.cfg, "tablero")
        return self._lista

    def _en(self, x: int, y: int, solo_interactivos: bool = False) -> str:
        """Cual esta debajo del punto. De arriba hacia abajo por orden de dibujo.

        Con `solo_interactivos`, lo que no recibe clics no los tapa tampoco. Es
        la misma regla del cartel --ahi un modulo no interactivo deja pasar el
        clic al programa de atras-- aplicada adentro de la ventana: sin esto un
        `documento` de 640x560 se come todos los clics del tablero y un boton
        debajo no se puede tocar nunca, sin nada que explique por que.

        En Edit se usa SIN el filtro: ahi se esta acomodando, y hay que poder
        agarrar justamente lo que no es interactivo.
        """
        for m in reversed(self._modulos()):
            if solo_interactivos and not m.get("interactivo"):
                continue
            if m["x"] <= x < m["x"] + m["ancho"] and m["y"] <= y < m["y"] + m["alto"]:
                return m["id"]
        return ""

    def _tocar_boton(self, ident: str) -> None:
        """Corre la accion de un modulo `boton`. Lista cerrada, nada destructivo.

        Cada accion se hace en un hilo salvo las instantaneas: escuchar graba
        tres segundos y hablar sintetiza, y hacer eso en el hilo de tkinter deja
        la ventana dura justo mientras el usuario espera a ver si anduvo.
        """
        if not ident:
            return
        modulo = next((m for m in self._modulos() if m["id"] == ident), None)
        if not modulo or modulo["tipo"] != "boton":
            return
        accion = str(modulo.get("accion", "panel"))
        self.aviso.config(text=tr("ejecutando") + f": {accion}")

        def trabajo():
            try:
                texto = self._correr_accion(accion)
            except Exception as exc:  # noqa: BLE001 - la ventana no puede morir
                texto = f"{type(exc).__name__}: {str(exc)[:120]}"
            # Se DEJA el resultado; lo levanta el lazo de dibujo. Aca no se
            # toca tkinter: `after()` desde otro hilo crea un comando Tcl desde
            # el hilo equivocado, y si la ventana se cierra mientras esto corre
            # el interprete se libera desde aca y el proceso ENTERO aborta con
            # `Tcl_AsyncDelete`. Eso no se puede atrapar.
            self._resultado = texto

        threading.Thread(target=trabajo, daemon=True).start()

    def _correr_accion(self, accion: str) -> str:
        """Lo que hace cada accion. Ninguna borra ni escribe nada del usuario."""
        cfg = store.load_config()
        if accion == "panel":
            from . import tray

            tray.open_panel()
            return tr("panel abierto")
        if accion == "cartel":
            from . import overlay

            overlay.asegurar(cfg)
            store.emitir_overlay({
                "estado": "hablando", "detalle": "PRUEBA DEL CARTEL", "nivel": 0.5,
                "titulo": str(cfg.get("assistant_name", "Eve")).upper(),
                "usuario": "probando el cartel",
                "eve": "Si ves esto, el cartel anda.",
            })
            return tr("cartel mostrado unos segundos")
        if accion == "hablar":
            from . import voice

            voice.speak("Hola, soy " + str(cfg.get("assistant_name", "Eve"))
                        + ". Si escuchas esto, la voz anda.", cfg)
            return tr("listo, hablo")
        if accion == "escuchar":
            import time as _t

            import numpy as np

            from . import voice

            rec = voice.Recorder()
            rec.start()
            _t.sleep(3.0)
            audio = rec.stop()
            if audio.size < 1000:
                return tr("no entro audio; el microfono puede estar tomado")
            pico = 20 * np.log10(max(1e-9, float(np.abs(audio).max())))
            dicho = voice.transcribe(audio, cfg)
            if not dicho:
                return tr("no entendi nada") + f" (pico {pico:.0f} dBFS)"
            return f"{tr('te escuche')}: {dicho!r}"
        return tr("accion desconocida") + f": {accion}"

    def _clic(self, evento) -> None:
        if self.modo.get() != "edit":
            # En Work el clic no elige nada, pero SI acciona los botones: un
            # modulo `boton` que solo se pudiera tocar en modo edicion no seria
            # un boton, seria un dibujo de un boton.
            self._tocar_boton(self._en(evento.x, evento.y, solo_interactivos=True))
            return
        ident = self._en(evento.x, evento.y)
        ctrl = bool(evento.state & 0x0004)
        shift = bool(evento.state & 0x0001)
        if not ident:
            if not (ctrl or shift):
                self.seleccion = []
        elif ctrl:
            if ident in self.seleccion:
                self.seleccion.remove(ident)
            else:
                self.seleccion.append(ident)
        elif shift and self.seleccion:
            # Rango en el orden en que se dibujan, que es el unico orden que
            # existe en un lienzo: de lo que estaba elegido a lo que se toco.
            orden = [m["id"] for m in self._modulos()]
            try:
                desde, hasta = orden.index(self.seleccion[-1]), orden.index(ident)
            except ValueError:
                desde = hasta = orden.index(ident)
            if desde > hasta:
                desde, hasta = hasta, desde
            for i in orden[desde:hasta + 1]:
                if i not in self.seleccion:
                    self.seleccion.append(i)
        else:
            self.seleccion = [ident]
        self._arrastre = (evento.x, evento.y) if self.seleccion else None
        self._dibujar_seleccion()
        self._refrescar_props()

    def _mover(self, evento) -> None:
        if self.modo.get() != "edit" or not self._arrastre or not self.seleccion:
            return
        dx, dy = evento.x - self._arrastre[0], evento.y - self._arrastre[1]
        if not dx and not dy:
            return
        self._arrastre = (evento.x, evento.y)
        for m in self._modulos():
            if m["id"] in self.seleccion:
                m["x"] = max(0, m["x"] + dx)
                m["y"] = max(0, m["y"] + dy)
        self._dibujar_seleccion()

    def _soltar(self, _evento=None) -> None:
        """Al soltar se guarda, no en cada pixel: serian 30 escrituras por segundo."""
        if self.modo.get() != "edit" or not self._arrastre:
            return
        self._arrastre = None
        if self.seleccion:
            self._anotar()
            cfg = store.load_config()
            for m in self._modulos():
                if m["id"] in self.seleccion:
                    cfg = modulos.guardar(cfg, m)
            self._guardar(cfg)

    def _dibujar_seleccion(self) -> None:
        self.lienzo.delete("marca")
        if self.modo.get() != "edit":
            return
        paleta = self.pintor.paleta
        for m in self._modulos():
            if m["id"] in self.seleccion:
                self.lienzo.create_rectangle(
                    m["x"] - 1, m["y"] - 1, m["x"] + m["ancho"], m["y"] + m["alto"],
                    outline=paleta["acento"], width=2, dash=(4, 3), tags="marca")

    # --- ajustes de lo elegido --------------------------------------------

    def _comunes(self) -> dict:
        """Props que comparten TODOS los elegidos, con su valor si coinciden.

        Devuelve {prop: (defecto, ayuda, valor_o_None)}. El None es "cada uno
        tiene lo suyo": el campo arranca vacio y solo pisa si se escribe algo.
        """
        elegidos = [m for m in self._modulos() if m["id"] in self.seleccion]
        if not elegidos:
            return {}
        nombres = set(modulos.props_de(elegidos[0]["tipo"]))
        for m in elegidos[1:]:
            nombres &= set(modulos.props_de(m["tipo"]))
        nombres.discard("tipo")
        salida = {}
        for prop in nombres:
            defecto, ayuda = modulos.COMUNES.get(prop) or modulos.props_de(
                elegidos[0]["tipo"])[prop]
            valores = {m.get(prop) for m in elegidos}
            salida[prop] = (defecto, ayuda, valores.pop() if len(valores) == 1 else None)
        return salida

    def _refrescar_props(self) -> None:
        for hijo in self.props.winfo_children():
            hijo.destroy()
        self.vars = {}
        if not self.seleccion:
            ttk.Label(self.props, text=tr("Nada elegido."), style="Ayuda.TLabel").pack(
                anchor="w", padx=10, pady=10)
            return
        ttk.Label(self.props, text=f"{len(self.seleccion)} elegido(s)").pack(
            anchor="w", padx=10, pady=(10, 4))
        comunes = self._comunes()
        for prop in sorted(comunes):
            defecto, _ayuda, valor = comunes[prop]
            fila = ttk.Frame(self.props)
            fila.pack(fill="x", padx=10, pady=1)
            ttk.Label(fila, text=prop, width=12).pack(side="left")
            if isinstance(defecto, bool):
                var = tk.BooleanVar(value=bool(valor))
            else:
                var = tk.StringVar(value="" if valor is None else str(valor))
            if isinstance(defecto, bool):
                ttk.Checkbutton(fila, variable=var).pack(side="left")
            elif prop in modulos.OPCIONES:
                ttk.Combobox(fila, textvariable=var, values=modulos.OPCIONES[prop],
                             state="readonly", width=13).pack(side="left")
            else:
                ttk.Entry(fila, textvariable=var, width=15).pack(side="left")
            self.vars[prop] = (var, defecto, valor)
        ttk.Button(self.props, text=tr("Aplicar a los elegidos"),
                   command=self._aplicar_props).pack(anchor="w", padx=10, pady=10)

    def _aplicar_props(self) -> None:
        if not self.seleccion:
            return
        self._anotar()
        cfg = store.load_config()
        for m in self._modulos():
            if m["id"] not in self.seleccion:
                continue
            for prop, (var, defecto, previo) in self.vars.items():
                valor = var.get()
                if not isinstance(defecto, bool) and str(valor) == "":
                    continue   # cada uno tenia lo suyo y no se escribio nada
                if previo is not None and str(valor) == str(previo):
                    continue
                m[prop] = _convertir(valor, defecto)
            cfg = modulos.guardar(cfg, m)
        self._guardar(cfg)
        self._refrescar_props()

    # --- acciones ---------------------------------------------------------

    def _anotar(self) -> None:
        """Guarda como estaba antes de tocar. Deshacer es volver a esta foto."""
        solo_mods = {k: v for k, v in store.load_config().items()
                     if k.startswith(modulos.PREFIJO)}
        self.deshacer.append(json.dumps(solo_mods))

    def _deshacer(self) -> None:
        if not self.deshacer:
            self.aviso.config(text=tr("no hay nada para deshacer"))
            return
        previos = json.loads(self.deshacer.pop())
        cfg = {k: v for k, v in store.load_config().items()
               if not k.startswith(modulos.PREFIJO)}
        cfg.update(previos)
        self._guardar(cfg)
        self.seleccion = [i for i in self.seleccion
                          if i in modulos.identificadores(cfg)]
        self._refrescar_props()

    def _duplicar(self) -> None:
        if not self.seleccion:
            return
        self._anotar()
        cfg = store.load_config()
        nuevos = []
        for ident in list(self.seleccion):
            modulo = modulos.leer(cfg, ident)
            usados = set(modulos.identificadores(cfg))
            n = 2
            while f"{ident}{n}" in usados:
                n += 1
            modulo["id"] = f"{ident}{n}"
            modulo["x"] = int(modulo["x"]) + 20
            modulo["y"] = int(modulo["y"]) + 20
            cfg = modulos.guardar(cfg, modulo)
            nuevos.append(modulo["id"])
        self._guardar(cfg)
        self.seleccion = nuevos
        self._dibujar_seleccion()
        self._refrescar_props()

    def _borrar(self) -> None:
        if self.modo.get() != "edit" or not self.seleccion:
            return
        self._anotar()
        cfg = store.load_config()
        for ident in self.seleccion:
            cfg = modulos.borrar(cfg, ident)
        self._guardar(cfg)
        self.seleccion = []
        self._refrescar_props()

    def _guardar(self, cfg: dict) -> None:
        store.save_config(cfg)
        self.cfg = cfg
        self._lista = None
        self._partes = None
        self.mtime = self._mtime()
        self.pintor.aplicar(cfg)
        self._dibujar_seleccion()

    # --- ciclo ------------------------------------------------------------

    def _mtime(self) -> float:
        try:
            import os

            return os.path.getmtime(store.CONFIG_PATH)
        except OSError:
            return 0.0

    def _releer(self) -> None:
        if self._mtime() == self.mtime:
            return
        self.mtime = self._mtime()
        self.cfg = store.load_config()
        self._lista = None
        self._partes = None
        self.pintor.aplicar(self.cfg)
        self._aplicar_tema()
        self._dibujar_seleccion()

    def _partes_del_prompt(self, lista) -> dict:
        if not any(m["tipo"] == "contexto" for m in lista):
            return {}
        if self._partes is None:
            from . import prompt

            try:
                self._partes = prompt.partes(self.cfg)
            except Exception:  # noqa: BLE001 - un medidor no tumba la ventana
                self._partes = {}
        return self._partes

    def _pagina(self, lista) -> str:
        """Lo ultimo que se leyo de la web, si hay algun modulo que lo muestre."""
        if not any(m["tipo"] == "lector" for m in lista):
            return ""
        if self.cuadro % 30 != 0 and self._pagina_cache is not None:
            return self._pagina_cache
        from . import lector

        datos = lector.ultima()
        titulo = datos.get("titulo") or ""
        self._pagina_cache = ((titulo + "\n\n") if titulo else "") + datos.get("texto", "")
        return self._pagina_cache

    def _documento(self, lista) -> dict:
        """Lo que Eve mostro con `E mostrar`, si hay un modulo que lo muestre.

        Se relee cada 30 cuadros y no en cada uno: el archivo puede tener veinte
        mil caracteres y nadie muestra un documento nuevo treinta veces por
        segundo. Igual que la pagina del lector.
        """
        if not any(m["tipo"] == "documento" for m in lista):
            return {}
        if self.cuadro % 30 != 0 and self._documento_cache is not None:
            return self._documento_cache
        self._documento_cache = store.ultimo_documento()
        return self._documento_cache

    def _historial(self, lista) -> str:
        """La conversacion, si hay un modulo que la muestre.

        Cada 30 cuadros: pegarle a SQLite treinta veces por segundo para mostrar
        veinte renglones que casi nunca cambian es gastar por gastar.
        """
        if not any(m["tipo"] == "historial" for m in lista):
            return ""
        if self.cuadro % 30 != 0 and self._historial_cache is not None:
            return self._historial_cache
        cuantos = max(1, max((int(m.get("cuantos", 20)) for m in lista
                              if m["tipo"] == "historial"), default=20))
        try:
            filas = store.recent_turns(cuantos)
        except Exception:  # noqa: BLE001 - sin base, el modulo queda vacio
            filas = []
        quien = {"user": "tu", "assistant": str(self.cfg.get("assistant_name", "Eve"))}
        lineas = [f"{quien.get(rol, rol)}: {texto}"
                  for _ts, rol, texto in reversed(filas)]
        self._historial_cache = "\n".join(lineas)
        return self._historial_cache

    def _acciones(self, lista) -> str:
        """El log de auditoria: que ejecuto Eve y como salio."""
        if not any(m["tipo"] == "acciones" for m in lista):
            return ""
        if self.cuadro % 30 != 0 and self._acciones_cache is not None:
            return self._acciones_cache
        propios = [m for m in lista if m["tipo"] == "acciones"]
        cuantas = max(1, max((int(m.get("cuantas", 20)) for m in propios), default=20))
        con_resultado = any(m.get("resultado", True) for m in propios)
        try:
            filas = store.recent_actions(cuantas)
        except Exception:  # noqa: BLE001
            filas = []
        # Con la fecha cuando NO es de hoy. Solo la hora hacia que una accion
        # de hace diez dias se leyera como de esta noche: me paso mirando este
        # mismo modulo y di por vivo un error que estaba muerto hacia una semana.
        hoy = time.strftime("%Y-%m-%d")
        lineas = []
        for ts, tool, detalle, salida in reversed(filas):
            local = time.localtime(ts)
            hora = (time.strftime("%H:%M", local)
                    if time.strftime("%Y-%m-%d", local) == hoy
                    else time.strftime("%d/%m %H:%M", local))
            linea = f"{hora}  {tool}  {detalle}"
            if con_resultado and salida:
                linea += f"  -> {salida}"
            lineas.append(linea)
        self._acciones_cache = "\n".join(lineas)
        return self._acciones_cache

    def tick(self) -> None:
        self.cuadro += 1
        # Lo que dejo el hilo de un boton, aplicado desde el hilo principal.
        if self._resultado is not None:
            self.aviso.config(text=self._resultado)
            self._resultado = None
        # Que la ventana avise que existe. Sin esto `E mostrar` abriria una
        # ventana nueva cada vez en lugar de escribir en la que ya esta.
        if self.cuadro % 60 == 0:
            store.consola_presente()
        if self.cuadro % CADA_LECTURA == 0:
            self.estado = store.estado_overlay(max_edad=8.0) or {}
            self._releer()
        lista = self._modulos()
        # En Edit se ven todos, incluso los que en Work estarian escondidos:
        # no se puede acomodar lo que no se ve.
        editando = self.modo.get() == "edit"
        vista = {
            "estado": "pensando" if editando else self.estado.get("estado", "reposo"),
            "nivel": float(self.estado.get("nivel", 0.0) or 0.0),
            "detalle": self.estado.get("detalle", ""),
            "titulo": self.cfg.get("assistant_name", "Eve"),
            "usuario": self.estado.get("usuario", ""),
            "eve": self.estado.get("eve", ""),
            "partes": self._partes_del_prompt(lista),
            "pagina": self._pagina(lista),
            "documento": self._documento(lista),
            "historial": self._historial(lista),
            "acciones": self._acciones(lista),
        }
        if editando:
            lista = [dict(m, cuando="siempre") for m in lista]
        self.pintor.dibujar(lista, vista)
        # Sin modulos no hay nada que dibujar y la ventana queda negra, que es
        # indistinguible de "no arranco". Se dice por que, y aparece el boton.
        if lista:
            self.lienzo.delete("vacio")
            self.boton_semilla.pack_forget()
        else:
            self._dibujar_vacio()
            # `winfo_manager` y no `winfo_ismapped`: el segundo es False mientras
            # la ventana este oculta, asi que esto volveria a empaquetar el boton
            # treinta veces por segundo sin que se vea nada raro.
            if not self.boton_semilla.winfo_manager():
                self.boton_semilla.pack(side="left", padx=6)
        if editando:
            self.lienzo.tag_raise("marca")
        self.raiz.after(CUADRO, self.tick)

    def correr(self) -> None:
        self.raiz.after(CUADRO, self.tick)
        self.raiz.mainloop()


def _convertir(valor, defecto):
    if isinstance(defecto, bool):
        return bool(valor)
    if isinstance(defecto, int):
        try:
            return int(float(str(valor).replace(",", ".")))
        except ValueError:
            return defecto
    if isinstance(defecto, float):
        try:
            return float(str(valor).replace(",", "."))
        except ValueError:
            return defecto
    return valor


def abrir() -> None:
    """La lanza como proceso aparte, igual que el cartel y el panel."""
    plataforma.lanzar(plataforma.comando_propio("--consola"))


def asegurar() -> bool:
    """La abre solo si no hay una. True si la lanzo.

    Sin esto, cada `E mostrar` abriria una ventana nueva encima de la anterior:
    seis ventanas y ninguna pista de cual mira el asistente.
    """
    if store.consola_ya_corre():
        return False
    abrir()
    return True


def main(argv=None) -> int:
    Consola().correr()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
