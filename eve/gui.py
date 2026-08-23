"""Panel de configuracion. Se abre solo cuando el usuario hace click en la bandeja.

Corre como proceso aparte (`python -m eve.gui`) para no mezclar el mainloop de
tkinter con el de pystray.
"""

import json
import math
import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import modulos, plataforma, registro, store, textos, voice
from .textos import t as tr

CREATE_NEW_CONSOLE = 0x00000010

PAD = 12
GRIS, ROJO, VERDE = "#666666", "#c0392b", "#1e8449"

# Cuanto se muestra de una. `esencial` deja abiertas las secciones que usa
# cualquiera y cierra las de ajuste fino; `completo` abre todo.
#
# Cerrada NO es escondida: el titulo se sigue viendo y dice cuantas opciones hay
# adentro, y un clic la abre. Esconder de verdad una opcion detras de un modo que
# no sabes que existe es lo mismo que no tenerla --y este panel ya se comio una
# vez el precio de eso, con una ventana entera cuyo unico boton vivia adentro de
# otra pestaña.
BASICO, AVANZADO = "basico", "avanzado"

def _parece_app_password(valor: str) -> bool:
    """Google las emite como 16 letras minusculas en 4 grupos de 4."""
    limpio = valor.replace(" ", "")
    return len(limpio) == 16 and limpio.isalpha() and limpio.islower()


PERM_ASK = "Preguntar antes de acciones riesgosas (recomendado)"
PERM_ALL = "Permitir todo sin preguntar"


def overlay_formas() -> list:
    """Los atajos de forma del marco. Import perezoso: overlay trae tkinter."""
    from . import overlay

    return list(overlay.FORMAS)


def _auth_status() -> str:
    if not shutil.which("claude"):
        return "CLI 'claude' no encontrado en el PATH."
    try:
        r = plataforma.correr(
            ["claude", "auth", "status"], capture_output=True, text=True, timeout=60
        )
        data = json.loads(r.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return "No pude leer el estado de la sesion."
    if not data.get("loggedIn"):
        return "Sin sesion iniciada."
    return (
        f"Conectado como {data.get('email', '?')}\n"
        f"Plan: {data.get('subscriptionType', '?')}   |   Metodo: {data.get('authMethod', '?')}"
    )

# Los roles viven en el registro: tenerlos en dos lados era una lista que se
# podia desfasar de la otra sin que nada lo dijera.
ROLES_ETIQUETA = registro.ROLES_ETIQUETA

MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
CC_MODELS = ["opus", "sonnet", "haiku"]
CC_MODES = ["acceptEdits", "auto", "manual"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self._vivo = True
        self.cfg = store.load_config()
        # Antes de crear un solo widget: si el idioma se fijara despues, la
        # primera mitad de la ventana quedaria en espanol y la segunda en ingles.
        textos.desde_config(self.cfg)
        # Donde vive cada control, para el buscador; y las secciones plegables,
        # para poder abrirlas desde el.
        self._indice: list[dict] = []
        self._secciones: list = []
        self._tabs: dict = {}
        self._subtabs: dict = {}
        self._subnb = None
        self._aciertos: list = []
        self._ctx_pestana = self._ctx_sub = self._ctx_seccion = ""
        # La clave navega y el rotulo se muestra. Son dos cosas: la clave es un
        # identificador estable en espanol --con ella se elige la pestaña-- y el
        # rotulo cambia con el idioma. Guardar una sola daba rutas a medio
        # traducir: "[Voz > How it speaks to you]".
        self._ctx_pestana_rot = self._ctx_sub_rot = ""
        self._ctx_abrir = None
        self._ctx_lienzo = None
        self._estilo()
        self.title(f"LLMJarvis - {tr('configuracion')}")
        # 900 y no 800: arriba del notebook ahora hay una barra con el modo, el
        # buscador y el idioma, y con 800 el ultimo boton del pie --el de la
        # ventana de actividad-- salia cortado como "Ventana de acti".
        self.geometry("900x820")
        self.minsize(760, 460)

        # El pie va PRIMERO y anclado abajo: pack reparte en orden de empaquetado,
        # asi que si el notebook va antes, empuja el boton Guardar fuera de la
        # ventana en cuanto una pestaña crece.
        footer = ttk.Frame(self)
        footer.pack(side="bottom", fill="x", pady=(0, 8))
        ttk.Separator(footer).pack(fill="x", pady=(0, 6))
        fila = ttk.Frame(footer)
        fila.pack(fill="x", padx=PAD)
        # Barra de estado: hasta ahora no habia forma de saber desde el panel si
        # el asistente estaba corriendo ni con que motor.
        self.estado = ttk.Label(fila, text="", style="Ayuda.TLabel")
        self.estado.pack(side="left")
        # Guardar es LA accion de esta ventana: tiene que verse distinta de las
        # secundarias, no igual. Es lo unico que se destaca en el pie.
        ttk.Button(fila, text=tr("Guardar"), command=self.save,
                   style="Principal.TButton").pack(side="right")
        ttk.Button(fila, text=tr("Buscar actualizaciones"), command=self.buscar_update).pack(
            side="right", padx=(0, 6)
        )
        # La ventana de actividad va en el PIE y no adentro de una pestaña.
        #
        # Es la tercera ventana del programa y hasta ahora la unica forma de
        # llegar era el menu de la bandeja --que en Windows 11 hay que sacar de
        # la flechita, apretar con el boton derecho y encontrar-- o un boton
        # enterrado tres niveles adentro de Apariencia. El pie se ve desde las
        # siete pestañas y desde el primer segundo.
        ttk.Button(fila, text=tr("Ventana de actividad"),
                   command=self._abrir_consola).pack(side="left", padx=(16, 0))
        # Al lado del boton de actualizar, que es donde uno se pregunta "cual
        # tengo?". Sin esto habia que abrir una terminal y correr --version.
        from eve import __version__

        ttk.Label(fila, text=f"v{__version__}", style="Ayuda.TLabel").pack(
            side="right", padx=(0, 10)
        )
        self.after(300, self._refrescar_estado)

        self.vars: dict[str, tk.Variable] = {}
        self._barra_superior(self)

        nb = self._nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=10, pady=(6, 6))
        # La rueda del mouse NO cambia el valor de una lista desplegable.
        #
        # Es el comportamiento de fabrica de ttk y es una trampa: las pestañas
        # scrollean, asi que rodas para leer mas abajo, el puntero pasa por
        # encima de un combo, y le cambiaste el motor de voz sin enterarte. El
        # valor queda mal hasta que alguien lo note, y no hay nada en pantalla
        # que diga que paso. Se aplica por CLASE, asi que vale para los combos
        # que ya existen y para los que se agreguen despues.
        self.bind_class("TCombobox", "<MouseWheel>", lambda e: "break")
        self.bind_class("TCombobox", "<Button-4>", lambda e: "break")
        self.bind_class("TCombobox", "<Button-5>", lambda e: "break")
        # Lo mismo con los spinbox, por el mismo motivo.
        self.bind_class("TSpinbox", "<MouseWheel>", lambda e: "break")
        self._nombres_pantalla = {}
        self.key_vars: dict[str, tk.Variable] = {}
        # Siete pestañas agrupadas por lo que uno viene a hacer, no por modulo.
        # En un bucle y no en siete lineas para que el titulo quede asociado a la
        # pestaña: es lo que el buscador necesita para poder saltar hasta ella.
        # El rotulo traducido va en la tupla y la clave queda aparte: `tr(titulo)`
        # con una variable no lo ve el chequeo de traduccion, y ese fue justo el
        # camino por el que tres textos salieron en espanol con el panel en ingles.
        for titulo, rotulo, armar in (
            ("General", tr("General"), self._tab_general),
            ("Cuentas", tr("Cuentas"), self._tab_cuentas),
            ("Voz", tr("Voz"), self._tab_voz),
            ("Contactos", tr("Contactos"), self._tab_contactos),
            ("Addons", tr("Addons"), self._tab_addons),
            ("Apariencia", tr("Apariencia"), self._tab_apariencia),
            ("Actividad", tr("Actividad"), self._tab_actividad),
        ):
            self._ctx_pestana, self._ctx_sub = titulo, ""
            self._ctx_pestana_rot, self._ctx_sub_rot = rotulo, ""
            self._ctx_seccion, self._ctx_abrir = "", None
            marco = armar(nb)
            nb.add(marco, text=f"  {rotulo}  ")
            self._tabs[titulo] = marco
        self._contar_secciones()
        # De nuevo, ahora que los widgets existen: el repintado de lo que no es
        # ttk necesita recorrer el arbol, y en _estilo() todavia estaba vacio.
        self.repintar()

    # --- estilo y helpers de layout ----------------------------------------

    def _estilo(self) -> None:
        """Un solo lugar donde se define como se ve todo.

        Antes cada widget traia su propio padx/pady y el resultado era desparejo.
        """
        from . import tema as tema_mod

        s = self.estilo = ttk.Style(self)
        pintar = tema_mod.pinta_panel(self.cfg)
        # `clam` es el unico tema de ttk que respeta los colores que uno le pone:
        # `vista` deja que los dibuje Windows. Por eso pintar obliga a cambiarlo.
        # Se elige UNA vez: volver a llamar theme_use resetea todos los estilos.
        preferidos = ("clam", "default") if pintar else ("vista", "clam", "default")
        for nombre in preferidos:
            if nombre in s.theme_names():
                s.theme_use(nombre)
                break
        base = ("Segoe UI", 9) if plataforma.WINDOWS else ("Helvetica", 11)
        self.option_add("*Font", base)
        s.configure("Titulo.TLabel", font=(base[0], base[1] + 4, "bold"))
        s.configure("Ayuda.TLabel", foreground=GRIS)
        s.configure("Error.TLabel", foreground=ROJO)
        s.configure("Ok.TLabel", foreground=VERDE)
        s.configure("Seccion.TLabelframe.Label", font=(base[0], base[1], "bold"))
        # La cabecera de una seccion plegable es un boton, pero no tiene que
        # parecer uno: el relieve de boton al lado de otros botones de verdad
        # hace que no se sepa cual ejecuta algo. Plano, alineado a la izquierda
        # y en negrita, que es como se lee un titulo.
        s.configure("Seccion.TButton", anchor="w", padding=(8, 6), relief="flat",
                    font=(base[0], base[1], "bold"))
        s.map("Seccion.TButton", relief=[("pressed", "flat"), ("active", "flat")])
        s.configure("TNotebook.Tab", padding=(14, 7))
        s.configure("TButton", padding=(10, 4))
        s.configure("Principal.TButton", padding=(18, 5),
                    font=(base[0], base[1], "bold"))

        self._base_fuente = base
        self.repintar()

    def repintar(self) -> None:
        """Aplica el tema y la fuente a la ventana YA construida.

        Se puede llamar cuantas veces haga falta: los widgets ttk consultan el
        motor de estilos en cada redibujado, asi que el color cambia en vivo sin
        reconstruir nada. Antes esto pedia cerrar y volver a abrir el panel.
        """
        from . import tema as tema_mod

        base = getattr(self, "_base_fuente", ("Segoe UI", 9))
        s, cfg = self.estilo, self.cfg
        tema_mod.aplicar_fuente(self, str(cfg.get("ui_fuente", "")),
                                int(cfg.get("ui_fuente_tam", 0) or 0))
        if not tema_mod.pinta_panel(cfg):
            return
        paleta = tema_mod.resolver(cfg, "ui")
        tema_mod.aplicar_ttk(s, paleta)
        # Reconfigurar el estilo base se lleva puestos los tipos de letra.
        s.configure("Titulo.TLabel", font=(base[0], base[1] + 4, "bold"))
        s.configure("Seccion.TLabelframe.Label", font=(base[0], base[1], "bold"))
        s.configure("Seccion.TButton", anchor="w", padding=(8, 6), relief="flat",
                    font=(base[0], base[1], "bold"))
        self.configure(background=paleta["fondo"])
        # Y lo que no pasa por ttk.Style se recorre a mano.
        tema_mod.repintar_tk(self, paleta)

    def _rueda(self, lienzo, dentro) -> None:
        """La rueda del mouse mueve el area que tenes debajo del puntero.

        Antes esto era un `bind_all`, que es global a la ventana: con pestañas
        adentro de pestañas, todos los canvas escuchaban el mismo evento y el
        ultimo en registrarse se quedaba con la rueda, asi que en el resto no
        pasaba nada. Ahora cada area toma la rueda solo mientras el puntero
        esta encima, y la suelta al salir.
        """
        def mover(evento):
            # delta es 120 por muesca en Windows; en Linux llegan Button-4/5.
            paso = -1 if getattr(evento, "num", 0) == 4 else 1
            if getattr(evento, "delta", 0):
                paso = -evento.delta // 120
            lienzo.yview_scroll(paso, "units")
            return "break"

        def tomar(_e=None):
            for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                lienzo.bind_all(evento, mover)

        def soltar(_e=None):
            for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                lienzo.unbind_all(evento)

        for widget in (lienzo, dentro):
            widget.bind("<Enter>", tomar)
            widget.bind("<Leave>", soltar)

    BANNER_ALTO = 76

    def _banner_en(self, marco) -> None:
        """Franja con imagen arriba de la pestaña, si el usuario cargo una.

        Es lo mas parecido a un fondo que admite este panel: los controles de ttk
        pintan su propio fondo opaco, asi que una imagen detras de todo se veria
        solo en los huecos. La cabecera si es un espacio libre.
        """
        ruta = str(self.cfg.get("ui_banner", ""))
        if not ruta:
            return
        from . import imagenes, tema as tema_mod

        if not hasattr(self, "_banner"):
            paleta = tema_mod.resolver(self.cfg)
            ancho = max(320, int(self.cfg.get("_ancho_panel", 0)) or 780)
            cuadros, _ = imagenes.cargar(
                ruta, ancho, self.BANNER_ALTO, "recortar",
                int(self.cfg.get("ui_banner_opacidad", 100) or 100), 0,
                paleta["fondo"], paleta["acento"],
            )
            # Solo el primer cuadro: un GIF animado en la cabecera de un panel de
            # configuracion distrae mas de lo que aporta.
            self._banner = cuadros[0] if cuadros else None
        if self._banner is None:
            return
        lienzo = tk.Canvas(marco, height=self.BANNER_ALTO, highlightthickness=0,
                           borderwidth=0)
        lienzo.pack(fill="x")
        lienzo.create_image(0, 0, image=self._banner, anchor="nw")

    def _hoja(self, nb, titulo: str, subtitulo: str):
        """Pestaña con encabezado y contenido con scroll.

        El scroll evita el problema recurrente de que agregar una fila empuje el
        boton Guardar fuera de la ventana.
        """
        marco = ttk.Frame(nb)
        self._banner_en(marco)
        cab = ttk.Frame(marco)
        cab.pack(fill="x", padx=PAD, pady=(PAD, 2))
        ttk.Label(cab, text=titulo, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(cab, text=subtitulo, style="Ayuda.TLabel").pack(anchor="w")
        ttk.Separator(marco).pack(fill="x", padx=PAD, pady=(6, 0))

        lienzo = tk.Canvas(marco, highlightthickness=0, borderwidth=0)
        barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
        dentro = ttk.Frame(lienzo)
        ventana = lienzo.create_window((0, 0), window=dentro, anchor="nw")

        def ajustar(_e=None):
            lienzo.configure(scrollregion=lienzo.bbox("all"))
            lienzo.itemconfigure(ventana, width=lienzo.winfo_width())

        dentro.bind("<Configure>", ajustar)
        lienzo.bind("<Configure>", ajustar)
        self._rueda(lienzo, dentro)
        lienzo.configure(yscrollcommand=barra.set)
        lienzo.pack(side="left", fill="both", expand=True, padx=(PAD, 0), pady=PAD)
        barra.pack(side="right", fill="y", pady=PAD)
        # El buscador necesita el par (canvas, marco interno) para poder correr
        # el scroll hasta el control: con el canvas solo no hay contra que medir.
        self._ctx_lienzo = (lienzo, dentro)
        return marco, dentro

    def _ui(self, accion) -> None:
        """Corre `accion` en el hilo de tkinter desde un worker.

        Se consulta una bandera propia y no `winfo_exists()`: ese ya es una
        llamada a tkinter, y hacerla desde otro hilo es justo lo que se quiere
        evitar. Si la ventana se cerro, no hacer nada; tocar tkinter despues
        tira "main thread is not in main loop".
        """
        if not getattr(self, "_vivo", False):
            return
        try:
            self.after(0, accion)
        except (tk.TclError, RuntimeError):
            self._vivo = False

    def destroy(self) -> None:
        self._vivo = False
        super().destroy()

    def buscar_update(self) -> None:
        from . import updater

        def work():
            try:
                nueva = updater.buscar()
            except RuntimeError as exc:
                # El mensaje se copia a una variable: Python borra `exc` al salir
                # del except, y estos lambdas corren despues, en el hilo de tk.
                fallo = str(exc)
                self._ui(lambda: messagebox.showerror(tr("Actualizar"), fallo))
                return
            if not nueva:
                self._ui(lambda: messagebox.showinfo(
                    tr("Actualizar"), f"Ya tienes la ultima version ({updater.version_actual()})."))
                return
            self._ui(lambda: self._ofrecer_update(nueva))

        threading.Thread(target=work, daemon=True).start()

    def _ofrecer_update(self, nueva: dict) -> None:
        from . import plataforma, updater

        if not plataforma.congelado():
            messagebox.showinfo(
                tr("Actualizar"),
                f"Hay una version nueva: {nueva['version']}.\n\n"
                "Estas corriendo desde el codigo, asi que se actualiza con git pull.",
            )
            return
        if not nueva["asset"]:
            messagebox.showinfo(
                tr("Actualizar"),
                f"Hay {nueva['version']}, pero todavia no hay paquete para tu sistema.\n"
                "Te abro la pagina de descargas.",
            )
            plataforma.abrir(nueva["url"])
            return
        if not messagebox.askyesno(
            tr("Actualizar"),
            f"Version nueva: {nueva['version']}   (tienes la {updater.version_actual()})\n\n"
            "Se descarga, se verifica su sha256 y se instala encima.\n"
            "Tu configuracion, agenda, memoria y voces no se tocan.\n\n"
            "Descargar e instalar ahora?",
        ):
            return

        self.estado.config(text=tr("descargando actualizacion..."))

        def bajar():
            try:
                ruta = updater.descargar(
                    nueva["asset"],
                    progreso=lambda hecho, total: self._ui(
                        lambda: self.estado.config(
                            text=f"descargando actualizacion... {hecho * 100 // total}%")
                    ),
                )
            except (ValueError, OSError) as exc:
                fallo = str(exc)
                self._ui(lambda: messagebox.showerror(tr("Actualizar"), fallo))
                return
            self._ui(lambda: (messagebox.showinfo(tr("Actualizar"), updater.instalar(ruta)),
                              self.destroy()))

        threading.Thread(target=bajar, daemon=True).start()

    def _refrescar_estado(self) -> None:
        """Dice si el asistente esta corriendo, con que motor y con que tecla."""

        # Leer un archivo es instantaneo, asi que no hace falta un hilo ni lanzar
        # un proceso. Lanzarlo era lo que hacia parpadear una consola cada 5s.
        vivo = store.latido()
        cfg = store.load_config()
        # Sin caracteres fuera de ASCII: la consola de Windows es cp1252 y este
        # proyecto ya rompio dos veces por eso.
        if vivo:
            texto = (
                f"[on] {tr('asistente corriendo')}   |   {tr('motor')}: "
                f"{vivo.get('motor', cfg['engine'])}"
                f"   |   {tr('tecla')}: {vivo.get('tecla', cfg['hotkey'])}"
            )
            estilo = "Ok.TLabel"
        else:
            texto = (
                f"[off] {tr('asistente detenido')}   |   {tr('motor')}: {cfg['engine']}"
                f"   |   {tr('tecla')}: {cfg['hotkey']}"
            )
            estilo = "Ayuda.TLabel"
        self.estado.config(text=f"{texto}   |   {plataforma.NOMBRE}", style=estilo)
        self._releer_si_cambio()

        try:
            self.after(3000, self._refrescar_estado)
        except tk.TclError:
            pass

    def _mtimes(self) -> tuple:
        def cuando(ruta):
            try:
                return os.path.getmtime(ruta)
            except OSError:
                return 0.0

        return (cuando(store.CONFIG_PATH), cuando(store.CONTACTS_PATH))

    def _releer_si_cambio(self) -> None:
        """Recarga si config.json o la agenda cambiaron por fuera del panel.

        El panel se sacaba una foto al abrirse y despues escribia esa foto
        entera de vuelta. Con el panel abierto, cambiar de perfil desde la
        bandeja te pintaba el cartel del personaje, y el primer Guardar lo
        revertia a lo que el panel tenia cargado de antes: por eso a veces
        salian los personajes y a veces los colores por defecto. Con la agenda
        pasaba lo mismo — un contacto que Eve agregaba por voz desaparecia al
        editar cualquier otro desde el panel.

        No se pisa lo que el usuario este editando ahora mismo: si toco algo y
        todavia no guardo, se avisa y se respeta lo suyo.
        """
        ahora = self._mtimes()
        if ahora == getattr(self, "_visto", ahora):
            self._visto = ahora
            return
        self._visto = ahora
        if self._hay_cambios_sin_guardar():
            self.estado.config(
                text=tr("La configuracion cambio por fuera. Guarda o cierra para recargarla."),
                style="Ayuda.TLabel")
            return
        self.recargar_de_disco()

    def _hay_cambios_sin_guardar(self) -> bool:
        for clave, var in self.vars.items():
            if clave not in self.cfg:
                continue
            if str(var.get()) != str(self.cfg[clave]):
                return True
        return False

    def recargar_de_disco(self) -> None:
        """Trae config y agenda del disco a los widgets. Idempotente."""
        self.cfg = store.load_config()
        for clave, var in self.vars.items():
            if clave in self.cfg:
                valor = self.cfg[clave]
                try:
                    var.set(valor if isinstance(var, tk.BooleanVar) else str(valor))
                except tk.TclError:
                    pass
        self.contactos = store.load_contacts()
        for refrescar in ("_contactos_refrescar", "_refrescar_contactos", "_listar_contactos"):
            fn = getattr(self, refrescar, None)
            if callable(fn):
                fn()
                break
        if hasattr(self, "perfil_var"):
            self.perfil_var.set(self.cfg.get("perfil_activo", ""))
        self.repintar()

    def _pintar_registro(self, padre, bloque, en_fila: bool = False) -> None:
        """Dibuja un bloque del registro repartiendo entre los helpers de siempre.

        Aca no hay dibujo nuevo: `Campo` va a `_row`, `Interruptor` a `_check`,
        `Fondo` a `_bloque_fondo`. Si esto tuviera que saber pintar algo por su
        cuenta, seria un framework nuevo en vez de una tabla --y el plan dice
        que en ese caso el control se escribe a mano y se anota como `Propio`.
        """
        for item in bloque:
            if isinstance(item, registro.Seccion):
                caja = self._seccion(padre, tr(item.titulo), item.nivel)
                self._pintar_registro(caja, item.hijos)
            elif isinstance(item, registro.Fila):
                fila = ttk.Frame(padre)
                fila.pack(fill="x", padx=12, pady=(4, 10))
                self._pintar_registro(fila, item.hijos, en_fila=True)
            elif isinstance(item, registro.Campo):
                # Las opciones pueden ser una lista, o el nombre de un metodo
                # que las arma al abrir: las voces de Windows salen de consultar
                # el sistema, y congelarlas al importar daria la lista de la
                # maquina que compilo el paquete.
                opciones = item.opciones
                if isinstance(opciones, str):
                    opciones = getattr(self, opciones)()
                self._row(padre, tr(item.etiqueta), item.clave, opciones, item.ancho)
            elif isinstance(item, registro.Salida):
                # Etiqueta vacia que el panel llena despues; queda accesible por
                # `self.<atributo>`, que es como la buscan los botones de prueba.
                etiqueta = ttk.Label(padre, text="", style="Ayuda.TLabel",
                                     justify="left")
                if en_fila:
                    etiqueta.pack(side="left", padx=8)
                else:
                    etiqueta.pack(anchor="w", padx=12, pady=(4, 8))
                setattr(self, item.atributo, etiqueta)
            elif isinstance(item, registro.Interruptor):
                self._check(padre, tr(item.etiqueta), item.clave)
            elif isinstance(item, registro.Ayuda):
                if en_fila:
                    ttk.Label(padre, text=tr(item.texto), style="Ayuda.TLabel",
                              justify="left").pack(side="left", padx=8)
                else:
                    self._ayuda(padre, tr(item.texto))
            elif isinstance(item, registro.Boton):
                # Adentro de una `Fila` el renglon ya esta puesto; suelto, se le
                # arma uno. Sin esto dos botones que van juntos se apilarian.
                caja = padre if en_fila else ttk.Frame(padre)
                if caja is not padre:
                    caja.pack(fill="x", padx=12, pady=(8, 2))
                ttk.Button(caja, text=tr(item.etiqueta),
                           command=getattr(self, item.metodo)).pack(
                               side="left", padx=(0, 6) if en_fila else 0)
            elif isinstance(item, registro.Colores):
                for rol, etiqueta in registro.ROLES_ETIQUETA:
                    self._fila_color(padre, item.prefijo, rol, tr(etiqueta))
            elif isinstance(item, registro.Vivo):
                # Al final del bloque y no al vuelo: las variables tienen que
                # existir para poder atarles el repintado.
                for clave in item.claves:
                    if clave in self.vars:
                        self.vars[clave].trace_add("write", self._previa_redibujar)
            elif isinstance(item, registro.Fondo):
                self._bloque_fondo(padre, item.prefijo, tr(item.titulo))
            elif isinstance(item, registro.Propio):
                getattr(self, item.metodo)(padre)
            else:  # pragma: no cover - una entrada de un tipo que no existe
                raise TypeError(f"el registro trae algo que no se dibujar: {item!r}")

    def _modelos_api(self) -> list:
        return MODELS

    def _modelos_cc(self) -> list:
        return CC_MODELS

    def _permisos_cc(self) -> list:
        return CC_MODES

    def _niveles_de_effort(self) -> list:
        return EFFORTS

    def _proveedores_compat(self) -> list:
        from .compat_engine import PROVEEDORES

        return list(PROVEEDORES)

    def _ayuda_compat(self, padre) -> None:
        """La ayuda del motor compatible, que arma su texto con una lista.

        Excepcion declarada: no toca ninguna clave, pero el texto se concatena
        con los proveedores que tienen capa gratuita, y eso no es un literal.
        """
        from .compat_engine import GRATIS

        self._ayuda(
            padre,
            tr("Los dos vacios = el modelo sugerido y la URL del proveedor.")
            + "\n" + tr("Con capa gratuita: ") + ", ".join(GRATIS) + ".\n"
            + tr("La clave de cada uno va en la pestaña Cuentas. 'propio' sirve para\n"
                 "cualquier servidor que hable /chat/completions."))

    def _rutas_permitidas(self, padre) -> None:
        """El cuadro de rutas de trabajo. Excepcion: es un Text de varias lineas.

        `Panel.save()` lo lee aparte, por eso no entra a `self.vars`.
        """
        ttk.Label(padre, text=tr("Rutas de trabajo permitidas (una por linea)")).pack(
            anchor="w", padx=12, pady=(8, 2))
        self.workdirs = tk.Text(padre, height=5)
        self.workdirs.insert("1.0", "\n".join(self.cfg.get("workdirs", [])))
        self.workdirs.pack(fill="x", padx=12)

    def _selector_de_permisos(self, padre) -> None:
        """El freno. Excepcion: guarda la NEGACION de su clave.

        El desplegable dice "permitir todo" y la clave se llama
        `confirm_destructive`, asi que no es una fila con una clave: es una
        eleccion que `save()` traduce.
        """
        ttk.Label(padre, text=tr("Permisos")).pack(anchor="w", padx=12, pady=(12, 2))
        self.perm_var = tk.StringVar(
            value=PERM_ASK if self.cfg.get("confirm_destructive", True) else PERM_ALL)
        ttk.Combobox(padre, textvariable=self.perm_var, values=[PERM_ASK, PERM_ALL],
                     state="readonly", width=60).pack(anchor="w", padx=12)

    def _temas_disponibles(self) -> list:
        from . import tema

        return tema.NOMBRES

    def _temas_del_cartel(self) -> list:
        """Igual que los del panel, mas el vacio: heredar el del panel."""
        from . import tema

        return ["", *tema.NOMBRES]

    def _fuentes_disponibles(self) -> list:
        from . import tema

        return tema.fuentes_disponibles()

    def _cabecera_del_panel(self, padre) -> None:
        """La imagen de cabecera: campo, selector de archivo y quitar.

        Excepcion declarada del registro: abre un dialogo de archivos, asi que
        no es una fila con una clave. Declara `ui_banner` para que la
        verificacion la siga viendo.
        """
        from tkinter import filedialog

        fila = ttk.Frame(padre)
        fila.pack(fill="x", padx=12, pady=5)
        ttk.Label(fila, text=tr("Imagen (PNG o GIF)"), width=24).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get("ui_banner", "")))
        self.vars["ui_banner"] = var
        ttk.Entry(fila, textvariable=var).pack(side="left", fill="x", expand=True)

        def elegir():
            ruta = filedialog.askopenfilename(
                title=tr("Imagen de cabecera"), parent=self,
                filetypes=[("Imagenes y sprite sheets",
                            "*.png *.gif *.webp *.apng *.jpg *.jpeg *.bmp"),
                           ("Todos", "*.*")],
            )
            if ruta:
                var.set(ruta)

        ttk.Button(fila, text="...", width=4, command=elegir).pack(side="left", padx=(6, 0))
        ttk.Button(fila, text=tr("Quitar"), width=8,
                   command=lambda: var.set("")).pack(side="left", padx=(4, 0))

    def _voces_de_windows(self) -> list | None:
        """Las voces de SAPI instaladas. Se consultan al abrir, no al importar."""
        return voice.list_sapi_voices() or None

    def _apps_al_abrir(self, _padre) -> None:
        """Llena el conteo de programas sin salir a escanear el disco."""
        self.refresh_apps(scan=False)

    def _seccion(self, padre, titulo: str, nivel: str = BASICO):
        """Una seccion plegable. Devuelve el cuerpo, donde va el contenido.

        Se pliegan TODAS, no solo las avanzadas: un mecanismo es mas facil de
        aprender que dos, y ver que la de al lado se pliega es lo que ensena que
        esta tambien puede. En modo `esencial` las avanzadas arrancan cerradas.

        La cabecera es un boton de verdad y no una etiqueta con un `<Button-1>`
        encima: asi entra en el recorrido del tabulador, se abre con Enter o
        con la barra espaciadora, y el lector de pantalla la anuncia como algo
        que se puede accionar.
        """
        abierta = nivel == BASICO or str(self.cfg.get("ui_modo_panel", "esencial")) != "esencial"
        caja = ttk.Frame(padre)
        caja.pack(fill="x", padx=(0, PAD), pady=(0, 8))
        cuerpo = ttk.Frame(caja)
        estado = {"abierta": abierta, "titulo": titulo, "cuenta": 0, "nivel": nivel}

        cab = ttk.Button(caja, style="Seccion.TButton")
        cab.pack(fill="x")

        def rotulo():
            flecha = "\u25be" if estado["abierta"] else "\u25b8"
            extra = ""
            if not estado["abierta"] and estado["cuenta"]:
                extra = f"   ({estado['cuenta']})"
            return f"{flecha}  {estado['titulo']}{extra}"

        def pintar():
            cab.config(text=rotulo())
            if estado["abierta"]:
                cuerpo.pack(fill="x", padx=(PAD, 0))
            else:
                cuerpo.pack_forget()

        def alternar():
            estado["abierta"] = not estado["abierta"]
            pintar()

        cab.config(command=alternar)
        estado["abrir"] = lambda: (alternar() if not estado["abierta"] else None)
        self._secciones.append((estado, cuerpo, pintar))
        self._ctx_seccion = titulo
        self._ctx_abrir = estado["abrir"]
        pintar()
        return cuerpo

    def _contar_secciones(self) -> None:
        """Cuantos controles quedaron adentro de cada seccion.

        Se hace al final y no al vuelo porque el cuerpo se llena DESPUES de
        crear la cabecera. Sin este numero, una seccion cerrada no dice si vale
        la pena abrirla.
        """
        def hojas(w):
            hijos = w.winfo_children()
            if not hijos:
                return 0
            propios = sum(isinstance(h, (ttk.Entry, ttk.Combobox, ttk.Checkbutton,
                                         ttk.Spinbox, tk.Text, ttk.Button))
                          for h in hijos)
            return propios + sum(hojas(h) for h in hijos)

        for estado, cuerpo, pintar in self._secciones:
            estado["cuenta"] = hojas(cuerpo)
            pintar()

    def _aplicar_modo_panel(self) -> None:
        """Abre o cierra segun el modo, respetando el nivel de cada seccion.

        No es "abrir todo / cerrar todo": en `esencial` las basicas siguen
        abiertas. Cerrar tambien lo basico dejaria el panel en blanco, que no es
        menos saturado sino menos util.
        """
        completo = str(self.modo_panel.get()) == "completo"
        for estado, _cuerpo, pintar in self._secciones:
            estado["abierta"] = completo or estado["nivel"] == BASICO
            pintar()
        self.cfg["ui_modo_panel"] = "completo" if completo else "esencial"

    # --- barra superior -----------------------------------------------------

    def _barra_superior(self, padre) -> None:
        """Modo, buscador e idioma: las tres cosas que valen para todo el panel.

        Van arriba de las pestañas y no adentro de una, porque una opcion que
        cambia como se ve el resto no puede vivir escondida en el resto. El
        idioma estaba en ningun lado y el modo no existia.
        """
        barra = ttk.Frame(padre)
        barra.pack(side="top", fill="x", padx=10, pady=(10, 0))

        izq = ttk.Frame(barra)
        izq.pack(side="left")
        ttk.Label(izq, text=tr("Ver"), style="Ayuda.TLabel").pack(side="left", padx=(0, 6))
        self.modo_panel = tk.StringVar(
            value=str(self.cfg.get("ui_modo_panel", "esencial")))
        # Las dos entran a `vars` para que Guardar las escriba como cualquier
        # otra clave. Si no, serian dos ajustes que existen en la config y que
        # el panel no puede tocar --justo lo que el test de cobertura busca.
        self.vars["ui_modo_panel"] = self.modo_panel
        for valor, etiqueta in (("esencial", tr("Lo esencial")), ("completo", tr("Todo"))):
            ttk.Radiobutton(izq, text=etiqueta, value=valor, variable=self.modo_panel,
                            command=self._aplicar_modo_panel,
                            style="Toolbutton").pack(side="left")

        der = ttk.Frame(barra)
        der.pack(side="right")
        ttk.Label(der, text=tr("Idioma del panel"), style="Ayuda.TLabel").pack(
            side="left", padx=(0, 6))
        self.idioma_var = tk.StringVar(value=textos.IDIOMAS.get(textos.actual(), "Espanol"))
        self.vars["ui_idioma"] = tk.StringVar(value=textos.actual())
        combo = ttk.Combobox(der, textvariable=self.idioma_var, width=10, state="readonly",
                             values=list(textos.IDIOMAS.values()))
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._cambiar_idioma)

        centro = ttk.Frame(barra)
        centro.pack(side="left", fill="x", expand=True, padx=16)
        self.buscar_var = tk.StringVar()
        self.buscar_entry = ttk.Entry(centro, textvariable=self.buscar_var)
        self.buscar_entry.pack(fill="x")
        self._pista_buscador()
        self.buscar_entry.bind("<KeyRelease>", self._buscar)
        self.buscar_entry.bind("<Return>", self._buscar_ir)
        self.buscar_entry.bind("<Down>", self._buscar_bajar)
        self.buscar_entry.bind("<Escape>", lambda _e: self._buscar_cerrar())
        self.buscar_entry.bind("<FocusIn>", self._pista_limpiar)
        # Ctrl+F es donde la mano va sola, en cualquier programa.
        self.bind("<Control-f>", lambda _e: (self.buscar_entry.focus_set(), "break")[1])

        self.resultados = tk.Listbox(self, height=8, activestyle="none",
                                     exportselection=False)
        self.resultados.bind("<Double-Button-1>", self._buscar_ir)
        self.resultados.bind("<Return>", self._buscar_ir)
        self.resultados.bind("<Escape>", lambda _e: self._buscar_cerrar())

    def _pista(self) -> str:
        """El texto en gris del buscador.

        Un metodo y no una constante de clase: como constante se leia con
        `tr(self.PISTA)`, y un `tr(variable)` es invisible para el chequeo de
        traduccion --el texto salia en espanol con el panel en ingles y ningun
        test lo decia.
        """
        return tr("Buscar un ajuste...   (Ctrl+F)")

    def _pista_buscador(self) -> None:
        self.buscar_var.set(self._pista())
        self.buscar_entry.config(foreground=GRIS)

    def _pista_limpiar(self, _e=None) -> None:
        if self.buscar_var.get() == self._pista():
            self.buscar_var.set("")
            self.buscar_entry.config(foreground="")

    def _buscar_cerrar(self) -> None:
        try:
            self.resultados.place_forget()
        except tk.TclError:
            pass

    def _buscar(self, evento=None) -> None:
        """Filtra el indice y muestra los aciertos debajo del campo."""
        if evento is not None and getattr(evento, "keysym", "") in ("Down", "Up", "Return", "Escape"):
            return
        texto = self.buscar_var.get().strip().lower()
        if texto == self._pista().lower() or len(texto) < 2:
            self._buscar_cerrar()
            return
        palabras = texto.split()
        self._aciertos = []
        for e in self._indice:
            heno = f"{e['etiqueta']} {e['clave']} {e['seccion']} {e['pestana']} {e['sub']}".lower()
            if all(p in heno for p in palabras):
                self._aciertos.append(e)
        self.resultados.delete(0, "end")
        if not self._aciertos:
            self.resultados.insert("end", "   " + tr("nada con esas palabras"))
        for e in self._aciertos[:40]:
            donde = " > ".join(x for x in (e["pestana_rot"], e["sub_rot"],
                                           e["seccion"]) if x)
            self.resultados.insert("end", f"  {e['etiqueta']}      [{donde}]")
        # Alto = lo que hay, hasta diez. Fijo en ocho dejaba cinco renglones
        # vacios abajo cuando habia tres resultados.
        self.resultados.config(height=max(1, min(10, self.resultados.size())))
        x = self.buscar_entry.winfo_rootx() - self.winfo_rootx()
        y = self.buscar_entry.winfo_rooty() - self.winfo_rooty() + self.buscar_entry.winfo_height()
        self.resultados.place(x=x, y=y, width=self.buscar_entry.winfo_width())
        self.resultados.lift()

    def _buscar_bajar(self, _e=None):
        if self.resultados.winfo_ismapped():
            self.resultados.focus_set()
            self.resultados.selection_clear(0, "end")
            self.resultados.selection_set(0)
        return "break"

    def _buscar_ir(self, _e=None):
        sel = self.resultados.curselection()
        i = sel[0] if sel else 0
        if i < len(getattr(self, "_aciertos", [])):
            self._ir_a(self._aciertos[i])
        self._buscar_cerrar()
        return "break"

    def _ir_a(self, entrada: dict) -> None:
        """Lleva hasta un ajuste: pestaña, sub-pestaña, seccion y scroll.

        Los cuatro pasos hacen falta. Con tres, el buscador te deja mirando la
        pestaña correcta con la opcion abajo del pliegue o fuera de la pantalla,
        que para el que busca es lo mismo que no haberla encontrado.
        """
        try:
            if entrada["pestana"] in self._tabs:
                self._nb.select(self._tabs[entrada["pestana"]])
            if entrada["sub"] and entrada["sub"] in self._subtabs:
                self._subnb.select(self._subtabs[entrada["sub"]])
            if entrada["abrir"]:
                entrada["abrir"]()
        except tk.TclError:
            return

        def desplazar():
            par = entrada.get("lienzo")
            w = entrada["widget"]
            if not par:
                pass
            else:
                lienzo, dentro = par
                try:
                    self.update_idletasks()
                    alto = max(1, dentro.winfo_height())
                    y = w.winfo_rooty() - dentro.winfo_rooty()
                    lienzo.yview_moveto(max(0.0, (y - 60) / alto))
                except tk.TclError:
                    pass
            try:
                w.focus_set()
            except tk.TclError:
                pass

        self.after(60, desplazar)

    def _cambiar_idioma(self, _e=None) -> None:
        """Guarda y vuelve a abrir el panel en el idioma elegido.

        Reconstruir los widgets en vivo seria mas elegante y mucho mas fragil:
        los textos estan repartidos en cincuenta lugares y basta olvidarse de
        uno para dejar la pantalla mitad en un idioma y mitad en otro. El panel
        ya corre como proceso aparte y ya sabe volver a abrirse; se usa eso.

        Se guarda primero: nadie pierde lo que estaba editando por cambiar el
        idioma. Si el guardado se frena por un valor invalido, no se reabre nada
        y el desplegable vuelve a donde estaba.
        """
        codigo = next((c for c, n in textos.IDIOMAS.items()
                       if n == self.idioma_var.get()), "es")
        if codigo == textos.actual():
            return
        self.vars["ui_idioma"].set(codigo)
        if not self.save(avisar=False):
            self.idioma_var.set(textos.IDIOMAS.get(textos.actual(), "Espanol"))
            return
        from . import tray

        tray.open_panel()
        self.destroy()

    def _ayuda(self, padre, texto: str) -> None:
        ttk.Label(padre, text=texto, style="Ayuda.TLabel", justify="left").pack(
            anchor="w", padx=PAD, pady=(2, 6)
        )


    # --- las siete pestañas ------------------------------------------------
    # Componen los bloques que ya existian; cada bloque sigue creando su frame,
    # asi que se lo cuelga del contenedor con scroll y listo.

    def _componer(self, nb, titulo, subtitulo, bloques):
        marco, dentro = self._hoja(nb, titulo, subtitulo)
        for bloque in bloques:
            bloque(dentro).pack(fill="both", expand=True)
        return marco

    def _tab_general(self, nb):
        return self._componer(
            nb, tr("General"),
            tr("Quien es Eve, quien piensa por ella y hasta donde puede meterse."),
            [self._bloque_perfiles, self._bloque_general],
        )

    def _tab_cuentas(self, nb):
        return self._componer(
            nb, tr("Cuentas"),
            tr("Con que se conecta. Todo opcional salvo el motor que elegiste."),
            [self._bloque_claves, self._bloque_correo],
        )

    def _tab_voz(self, nb):
        return self._componer(
            nb, tr("Voz"),
            tr("Como te escucha y como te responde."),
            [self._bloque_voz, self._bloque_voces],
        )

    def _tab_contactos(self, nb):
        return self._componer(
            nb, tr("Contactos"),
            tr("La agenda que Eve usa cuando nombras a alguien."),
            [self._bloque_contactos],
        )

    def _tab_addons(self, nb):
        return self._componer(
            nb, tr("Addons"),
            tr("Lo que Eve puede manejar ademas de tu PC. Cada uno trae sus comandos."),
            [self._bloque_addons],
        )

    def _bloque_addons(self, nb):
        from . import addons

        t = ttk.Frame(nb)
        cfg = store.load_config()
        cargados = addons.todos(recargar=True)

        caja = self._seccion(t, tr("Instalados"))
        if not cargados:
            self._ayuda(caja, tr("No hay ninguno cargado."))
        self.addon_vars = {}
        prendidos = {x.strip() for x in str(cfg.get("addons_activos", "")).split(",") if x.strip()}
        for nombre, modulo in sorted(cargados.items()):
            puede, motivo = addons.estado(modulo, cfg)
            fila = ttk.Frame(caja)
            fila.pack(fill="x", padx=12, pady=(6, 0))
            var = tk.BooleanVar(value=(not prendidos) or nombre in prendidos)
            self.addon_vars[nombre] = var
            ttk.Checkbutton(fila, text=nombre, variable=var).pack(side="left")
            estado = "" if puede else f"  —  no disponible: {motivo}"
            ttk.Label(fila, text=getattr(modulo, "DESCRIPCION", "") + estado,
                      style="Ayuda.TLabel").pack(side="left", padx=8)
            # Cada addon dice que claves necesita y el panel las dibuja: agregar
            # uno no obliga a tocar esta pantalla.
            for clave, etiqueta, secreta in getattr(modulo, "CLAVES", []):
                if secreta:
                    self._campo_clave(caja, clave, etiqueta)
                else:
                    self._campo_clave(caja, clave, etiqueta)

        self._ayuda(
            caja,
            tr("Destildar uno lo saca del prompt: deja de gastar tokens y Eve deja de\n"
            "ofrecerlo. Si no hay ninguno tildado, se usan todos los disponibles."),
        )

        caja = self._seccion(t, tr("Agregar los tuyos"))
        self._ayuda(
            caja,
            f"Poné archivos .py en:\n  {addons.CARPETA_USUARIO}\n\n"
            "Cada uno define NOMBRE, un texto para el modelo y una funcion\n"
            "ejecutar(accion, args, cfg). Ojo: corren dentro de Eve, con los mismos\n"
            "permisos que el programa. Poné solo cosas en las que confies.",
        )
        sin_revisar = addons.pendientes()
        if sin_revisar:
            alerta = self._seccion(t, tr("Sin revisar"))
            self._ayuda(
                alerta,
                tr("Estos archivos no se estan cargando. Un addon es codigo que corre\n"
                "con tus permisos y no pasa por el freno, asi que hay que mirarlo\n"
                "antes. Si Eve escribio alguno, aca es donde lo revisas."))
            for nombre, ruta, marca in sin_revisar:
                fila = ttk.Frame(alerta)
                fila.pack(fill="x", padx=12, pady=3)
                ttk.Label(fila, text=f"{nombre}.py", width=22).pack(side="left")
                ttk.Button(fila, text=tr("Ver el codigo"),
                           command=lambda r=ruta: self._addon_ver(r)).pack(side="left")
                ttk.Button(fila, text=tr("Aprobar"),
                           command=lambda n=nombre, m=marca: self._addon_aprobar(n, m)
                           ).pack(side="left", padx=6)

        aprobados = addons.aprobados_ahora()
        if aprobados:
            ok = self._seccion(t, tr("Aprobados"))
            self._ayuda(
                ok,
                tr("Estos se cargan. Revocar no borra el archivo: lo devuelve a la\n"
                "lista de sin revisar, para que puedas volver a mirarlo antes de\n"
                "decidir de nuevo. Editar un addon aprobado lo saca solo, porque\n"
                "la aprobacion es de la huella del contenido y no del nombre."))
            for nombre in aprobados:
                fila = ttk.Frame(ok)
                fila.pack(fill="x", padx=12, pady=3)
                ttk.Label(fila, text=f"{nombre}.py", width=22).pack(side="left")
                ttk.Button(fila, text=tr("Revocar"),
                           command=lambda n=nombre: self._addon_revocar(n)
                           ).pack(side="left")

        ttk.Button(caja, text=tr("Abrir la carpeta de addons"),
                   command=self._addons_carpeta).pack(anchor="w", padx=12, pady=(0, 10))
        return t

    def _addons_carpeta(self):
        from . import addons

        os.makedirs(addons.CARPETA_USUARIO, exist_ok=True)
        plataforma.abrir(addons.CARPETA_USUARIO)

    def _tab_apariencia(self, nb):
        """Apariencia se divide en sub-pestañas.

        Habia diez secciones apiladas en un solo scroll: para cambiar el tamaño
        de los subtitulos habia que pasar por delante de todo lo demas. Partirla
        en cuatro pantallas cortas hace que cada una entre sin scrollear y que
        se llegue en dos clics en vez de en un viaje.
        """
        marco = ttk.Frame(nb)
        cab = ttk.Frame(marco)
        cab.pack(fill="x", padx=PAD, pady=(PAD, 2))
        ttk.Label(cab, text=tr("Apariencia"), style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(cab, text=tr("Los colores de todo, y el cartel que Eve muestra "
                            "encima de lo que estes haciendo."),
                  style="Ayuda.TLabel").pack(anchor="w")

        # La vista previa vive arriba y no adentro de una sub-pestaña: es la
        # respuesta a lo que estas tocando, y tiene que verse toques lo que
        # toques. Metida en "Tema", ajustar el marco era a ciegas.
        self._pintor = None
        self._filas_color = []
        caja = ttk.Frame(marco)
        caja.pack(fill="x", padx=PAD, pady=(8, 0))
        self.previa = tk.Canvas(caja, width=460, height=128, highlightthickness=0)
        self.previa.pack()

        sub = self._subnb = ttk.Notebook(marco)
        sub.pack(fill="both", expand=True, padx=PAD, pady=(8, PAD))
        for titulo, rotulo, bloques in (
            ("Tema", tr("Tema"), [self._bloque_tema]),
            ("Cartel", tr("Cartel"), [self._bloque_hud]),
            ("Ventana", tr("Ventana"), [self._bloque_ventana]),
            ("Modulos", tr("Modulos"), [self._bloque_modulos]),
            ("Subtitulos", tr("Subtitulos"), [self._bloque_subtitulos]),
        ):
            self._ctx_sub, self._ctx_sub_rot = titulo, rotulo
            self._ctx_seccion, self._ctx_abrir = "", None
            hoja = self._hoja_simple(sub, bloques)
            sub.add(hoja, text=f"  {rotulo}  ")
            self._subtabs[titulo] = hoja
        self._ctx_sub = self._ctx_sub_rot = ""
        return marco

    def _hoja_simple(self, padre, bloques):
        """Contenido con scroll, sin encabezado propio: ya lo puso la pestaña."""
        marco = ttk.Frame(padre)
        lienzo = tk.Canvas(marco, highlightthickness=0, borderwidth=0)
        barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
        dentro = ttk.Frame(lienzo)
        ventana = lienzo.create_window((0, 0), window=dentro, anchor="nw")

        def ajustar(_e=None):
            lienzo.configure(scrollregion=lienzo.bbox("all"))
            lienzo.itemconfigure(ventana, width=lienzo.winfo_width())

        dentro.bind("<Configure>", ajustar)
        lienzo.bind("<Configure>", ajustar)
        lienzo.configure(yscrollcommand=barra.set)
        self._rueda(lienzo, dentro)
        lienzo.pack(side="left", fill="both", expand=True, pady=8)
        barra.pack(side="right", fill="y", pady=8)
        self._ctx_lienzo = (lienzo, dentro)
        for bloque in bloques:
            bloque(dentro).pack(fill="both", expand=True)
        return marco

    def _tab_actividad(self, nb):
        return self._componer(
            nb, tr("Actividad"),
            tr("Que se dijo y que se ejecuto en tu PC."),
            [self._bloque_historial, self._bloque_acciones],
        )

    # --- helpers -----------------------------------------------------------

    def _row(self, parent, label, key, values=None, width=44):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=12, pady=5)
        ttk.Label(frame, text=label, width=24).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(key, "")))
        self.vars[key] = var
        widget = (
            ttk.Combobox(frame, textvariable=var, values=values, width=width - 2, state="readonly")
            if values
            else ttk.Entry(frame, textvariable=var, width=width)
        )
        widget.pack(side="left", fill="x", expand=True)
        self._anotar(label, key, widget)
        return var

    def _campo_clave(self, parent, provider, label):
        """Campo enmascarado. Muestra asteriscos si ya hay algo guardado; si el
        usuario no lo reescribe, save() lo deja intacto."""
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=12, pady=4)
        ttk.Label(frame, text=label, width=34).pack(side="left")
        existing = ""
        try:
            existing = "*" * 12 if store.get_key(provider) else ""
        except Exception:  # noqa: BLE001 - keyring puede no estar disponible
            pass
        var = tk.StringVar(value=existing)
        self.key_vars[provider] = var
        ttk.Entry(frame, textvariable=var, show="*", width=44).pack(
            side="left", fill="x", expand=True
        )

    def _check(self, parent, label, key):
        var = tk.BooleanVar(value=bool(self.cfg.get(key, True)))
        self.vars[key] = var
        w = ttk.Checkbutton(parent, text=label, variable=var)
        w.pack(anchor="w", padx=12, pady=4)
        self._anotar(label, key, w)

    # --- buscador ----------------------------------------------------------

    def _anotar(self, etiqueta: str, clave: str, widget) -> None:
        """Guarda donde vive cada control, para poder llevar hasta el.

        Es la unica forma honesta de tener buscador en un panel de 120 opciones
        repartidas en siete pestañas y cinco sub-pestañas: sin indice, buscar
        seria recorrer widgets a mano y adivinar en cual estas.
        """
        self._indice.append({
            "etiqueta": etiqueta,
            "clave": clave,
            "widget": widget,
            "pestana": self._ctx_pestana,
            "sub": self._ctx_sub,
            "pestana_rot": self._ctx_pestana_rot or self._ctx_pestana,
            "sub_rot": self._ctx_sub_rot or self._ctx_sub,
            "seccion": self._ctx_seccion,
            "abrir": self._ctx_abrir,
            "lienzo": self._ctx_lienzo,
        })

    # --- tabs --------------------------------------------------------------

    def _bloque_perfiles(self, nb):
        t = ttk.Frame(nb)
        caja = self._seccion(t, tr("Perfiles"))
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(8, 4))
        ttk.Label(fila, text=tr("Perfil activo"), width=24).pack(side="left")
        self.perfil_var = tk.StringVar(value=self.cfg.get("perfil_activo", ""))
        self.perfil_combo = ttk.Combobox(fila, textvariable=self.perfil_var,
                                         values=sorted(store.listar_perfiles()),
                                         state="readonly")
        self.perfil_combo.pack(side="left", fill="x", expand=True)

        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(fila, text=tr("Cargar"), command=self._perfil_cargar).pack(side="left")
        ttk.Button(fila, text=tr("Guardar como..."),
                   command=self._perfil_guardar).pack(side="left", padx=6)
        ttk.Button(fila, text=tr("Borrar"), command=self._perfil_borrar).pack(side="left")
        ttk.Button(fila, text=tr("Exportar..."),
                   command=self._perfil_exportar).pack(side="left", padx=(12, 0))
        ttk.Button(fila, text=tr("Importar..."),
                   command=self._perfil_importar).pack(side="left", padx=6)
        self._ayuda(
            caja,
            tr("Un perfil guarda como se ve y como suena Eve: colores, forma, fuente,\n"
            "voz, velocidad, tono y el nombre del asistente.\n"
            "NO toca el motor, el modelo, la tecla, los permisos ni tus datos: un\n"
            "perfil que te pasan no puede cambiarte como trabaja el asistente."),
        )
        return t

    def _perfil_cargar(self):
        nombre = self.perfil_var.get()
        if not nombre:
            messagebox.showinfo(tr("Perfiles"), tr("Elige un perfil de la lista."))
            return
        if not messagebox.askyesno(
            tr("Cargar perfil"),
            f"Se va a aplicar el perfil {nombre!r} y se pierden los cambios sin guardar.\n\n"
            "Seguir?",
        ):
            return
        store.aplicar_perfil(nombre)
        messagebox.showinfo(
            tr("Perfiles"),
            f"Perfil {nombre!r} aplicado.\n\nCerra y volve a abrir el panel para verlo.",
        )
        self.destroy()

    def _perfil_guardar(self):
        from tkinter import simpledialog

        sugerido = self.perfil_var.get() or "nuevo"
        nombre = simpledialog.askstring("Guardar perfil", "Nombre del perfil:",
                                        initialvalue=sugerido, parent=self)
        if not nombre or not nombre.strip():
            return
        nombre = nombre.strip()
        if nombre in store.listar_perfiles() and not messagebox.askyesno(
            tr("Ya existe"), f"Ya hay un perfil {nombre!r}. Lo pisamos?"
        ):
            return
        # Se guarda lo que hay en pantalla, no lo ultimo guardado en disco.
        self.save(avisar=False)
        store.guardar_perfil(nombre, store.load_config())
        cfg = store.load_config()
        cfg["perfil_activo"] = nombre
        store.save_config(cfg)
        self.perfil_var.set(nombre)
        self.perfil_combo["values"] = sorted(store.listar_perfiles())
        messagebox.showinfo(tr("Perfiles"), f"Guardado como {nombre!r}.")

    def _perfil_exportar(self):
        from tkinter import filedialog

        nombre = self.perfil_var.get()
        if not nombre:
            messagebox.showinfo(tr("Perfiles"), tr("Elige un perfil de la lista primero."))
            return
        destino = filedialog.asksaveasfilename(
            title=tr("Exportar perfil"), parent=self, initialfile=f"{nombre}.eveperfil",
            defaultextension=".eveperfil",
            filetypes=[("Perfil de Eve", "*.eveperfil"), ("Todos", "*.*")],
        )
        if not destino:
            return
        try:
            mensaje = store.exportar_perfil(nombre, destino)
        except (ValueError, OSError) as exc:
            messagebox.showerror(tr("Exportar"), str(exc))
            return
        messagebox.showinfo(
            tr("Exportar"),
            f"{mensaje}\n\nNo incluye tus claves de API ni tus datos personales:\n"
            "las claves viven en el gestor de credenciales de Windows, no en el perfil.",
        )

    def _perfil_importar(self):
        from tkinter import filedialog, simpledialog

        # Arranca en los perfiles que vienen con el programa. Sin esto el dialogo
        # abre donde haya quedado la ultima vez y los ocho de ejemplo son
        # invisibles en la practica: nadie sale a buscarlos dentro de _internal.
        ejemplos = os.path.join(plataforma.recursos(), "perfiles")
        ruta = filedialog.askopenfilename(
            title=tr("Importar perfil"), parent=self,
            initialdir=ejemplos if os.path.isdir(ejemplos) else None,
            filetypes=[("Perfil de Eve", "*.eveperfil"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        try:
            nombre, config = store.leer_perfil_archivo(ruta)
        except ValueError as exc:
            messagebox.showerror(tr("Importar"), str(exc))
            return
        nombre = simpledialog.askstring("Importar perfil", "Guardarlo con el nombre:",
                                        initialvalue=nombre, parent=self) or ""
        if not nombre.strip():
            return
        nombre = nombre.strip()
        if nombre in store.listar_perfiles() and not messagebox.askyesno(
            tr("Ya existe"), f"Ya hay un perfil {nombre!r}. Lo pisamos?"
        ):
            return
        store.guardar_perfil(nombre, {**store.DEFAULTS, **config})
        self.perfil_var.set(nombre)
        self.perfil_combo["values"] = sorted(store.listar_perfiles())
        messagebox.showinfo(
            tr("Importar"),
            f"Perfil {nombre!r} importado con {len(config)} opciones.\n\n"
            "Toca 'Cargar' para aplicarlo.",
        )

    def _perfil_borrar(self):
        nombre = self.perfil_var.get()
        if not nombre:
            return
        if messagebox.askyesno(tr("Borrar perfil"), f"Borrar el perfil {nombre!r}?"):
            store.borrar_perfil(nombre)
            self.perfil_var.set("")
            self.perfil_combo["values"] = sorted(store.listar_perfiles())

    def _bloque_general(self, nb):
        """Lo de General, agrupado por lo que uno viene a hacer.

        Antes eran quince filas seguidas sin un titulo en el medio, en la primera
        pestaña que ve cualquiera: el nombre del asistente y la cuantizacion del
        motor compatible tenian exactamente el mismo peso visual. Ahora hay seis
        secciones y las tres que casi nadie toca arrancan plegadas.

        Lo que NO se pliega de fabrica, aunque sea largo: rutas permitidas y
        permisos. Son los frenos; esconderlos por prolijidad es lo mismo que
        apagarlos.
        """
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.GENERAL)
        return t


    def _bloque_claves(self, nb):
        t = ttk.Frame(nb)

        # --- sesion de Claude Code (motor 'claude-code', sin API key) ---
        box = self._seccion(t, tr("Sesion de Claude Code (motor 'claude-code')"))
        self.auth_label = ttk.Label(box, text=tr("consultando..."), justify="left")
        self.auth_label.pack(anchor="w", padx=10, pady=(8, 4))
        row = ttk.Frame(box)
        row.pack(anchor="w", padx=10, pady=(0, 10))
        ttk.Button(row, text=tr("Iniciar sesion"), command=self.auth_login).pack(side="left")
        ttk.Button(row, text=tr("Cerrar sesion"), command=self.auth_logout).pack(side="left", padx=6)
        ttk.Button(row, text=tr("Actualizar"), command=self.refresh_auth).pack(side="left")
        self.after(100, self.refresh_auth)

        ttk.Label(
            t,
            text=tr("Se guardan en el gestor de credenciales de Windows, nunca en texto plano.\n"
            "Anthropic solo hace falta con el motor 'api'; con 'claude-code' se usa tu suscripcion.\n"
            "Las otras habilitan proveedores opcionales de voz."),
            justify="left",
        ).pack(anchor="w", padx=12, pady=10)

        for provider, label in [
            ("anthropic", "Anthropic API key (motor 'api')"),
            ("openai", "OpenAI API key (STT en la nube)"),
            ("elevenlabs", "ElevenLabs API key (TTS en la nube)"),
            ("gemini", "Gemini API key (gratis en aistudio.google.com)"),
            ("groq", "Groq API key (gratis en console.groq.com)"),
            ("openrouter", "OpenRouter API key (tiene modelos :free)"),
            ("deepseek", "DeepSeek API key"),
            ("xai", "xAI API key"),
        ]:
            self._campo_clave(t, provider, label)

        box = self._seccion(t, tr("Conexiones con apps (todas opcionales)"))
        ttk.Label(
            box,
            text=tr("Sin esto Eve igual abre WhatsApp, Discord, Telegram y el mail con el\n"
            "mensaje escrito, para que lo mandes tu. Estas claves solo agregan leer\n"
            "y enviar sin pasar por la app."),
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(8, 6))
        self._campo_clave(box, "discord_webhook", tr("Discord: URL del webhook"))
        ttk.Button(box, text=tr("Probar el webhook"), command=self.probar_webhook).pack(
            anchor="w", padx=12, pady=(2, 4))
        self._row(box, tr("Discord: nombre a mostrar"), "discord_username", width=40)
        self._row(box, tr("Discord: URL del avatar"), "discord_avatar", width=40)
        self._ayuda(
            box,
            tr("Con que nombre y foto aparecen los mensajes que manda por webhook.\n"
            "Vacio = lo que tenga configurado el webhook en Discord. Andaba\n"
            "desde siempre; lo que faltaba era donde escribirlo sin editar el\n"
            "config a mano."))
        if not self.cfg.get("steam_id"):
            from . import integrations

            self.cfg["steam_id"] = integrations.steam_id_local()  # detectado del disco
        self._row(box, tr("Tu SteamID64 (autodetectado)"), "steam_id", width=40)
        self._campo_clave(box, "steam", tr("Steam: Web API key"))
        self._check(
            box,
            tr("WhatsApp: enviar solo (simula el Enter; exige numero, no nombre)"),
            "whatsapp_autosend",
        )
        self._check(
            box,
            tr("Discord: escribir como tu (maneja tu cliente; verifica el canal por titulo)"),
            "discord_autosend",
        )
        ttk.Label(
            box,
            text=tr("Gmail: si 'Contrasenas de aplicaciones' no te aparece, tu cuenta no tiene 2FA\n"
            "o la administra tu organizacion. Alternativa sin claves: agrega el Gmail a\n"
            "Outlook (Archivo > Agregar cuenta) y Eve lo lee y escribe por ahi.\n"
            "Webhook: Editar canal > Integraciones > Webhooks. Steam key: steamcommunity.com/dev/apikey"),
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(6, 10))
        return t

    CONTACT_COLS = (
        "nombre",
        "alias",
        "email",
        "telefono",
        "discord_user",
        "discord_dm",
        "discord_canal",
    )

    def _bloque_contactos(self, nb):
        """Agenda: 'mandale un correo a Lucas' necesita saber quien es Lucas."""
        t = ttk.Frame(nb)
        ttk.Label(
            t,
            text=tr("Eve usa esta lista cuando nombras a alguien. En 'alias' pon como le dices\n"
            "de verdad, separado por comas (lucho, el lucas) — la voz rara vez dice el\n"
            "nombre completo.\n\n"
            "discord_user  = su @ (para mencionarlo dentro del mensaje)\n"
            "discord_dm    = su chat privado. Activa Ajustes > Avanzado > Modo desarrollador,\n"
            "                boton derecho sobre la conversacion > Copiar ID\n"
            "discord_canal = un canal de servidor. Boton derecho > Copiar enlace"),
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.contactos = store.load_contacts()
        self.tree = ttk.Treeview(t, columns=self.CONTACT_COLS, show="headings", height=8)
        for c, w in zip(self.CONTACT_COLS, (110, 105, 150, 110, 95, 130, 130)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=12)
        self.tree.bind("<<TreeviewSelect>>", self._contacto_seleccionado)

        form = ttk.Frame(t)
        form.pack(fill="x", padx=12, pady=(8, 0))
        self.contacto_vars = {}
        for i, campo in enumerate(self.CONTACT_COLS):
            ttk.Label(form, text=campo, width=9).grid(row=i // 2, column=(i % 2) * 2, sticky="w", pady=2)
            var = tk.StringVar()
            self.contacto_vars[campo] = var
            ttk.Entry(form, textvariable=var, width=34).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="we", padx=(0, 14), pady=2
            )
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        botones = ttk.Frame(t)
        botones.pack(anchor="w", padx=12, pady=8)
        ttk.Button(botones, text=tr("Agregar / actualizar"), command=self._contacto_guardar).pack(side="left")
        ttk.Button(botones, text=tr("Borrar"), command=self._contacto_borrar).pack(side="left", padx=6)
        ttk.Button(botones, text=tr("Limpiar campos"), command=self._contacto_limpiar).pack(side="left")

        compartir = ttk.Frame(t)
        compartir.pack(anchor="w", padx=12, pady=(0, 8))
        ttk.Label(compartir, text=tr("Compartir:")).pack(side="left", padx=(0, 8))
        ttk.Button(compartir, text=tr("Exportar"), command=self._contacto_exportar).pack(side="left")
        ttk.Button(compartir, text=tr("Importar"), command=self._contacto_importar).pack(side="left", padx=6)
        ttk.Label(
            t,
            text=tr("Exportar genera un archivo .evecontact que puedes mandarle a un amigo por\n"
            "WhatsApp o Discord; el lo abre con Importar y le queda el contacto cargado."),
            style="Ayuda.TLabel",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self._contactos_refrescar()
        return t

    def _contactos_refrescar(self):
        self.tree.delete(*self.tree.get_children())
        for c in self.contactos:
            self.tree.insert("", "end", values=[c.get(k, "") for k in self.CONTACT_COLS])

    def _contacto_seleccionado(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        valores = self.tree.item(sel[0], "values")
        for campo, valor in zip(self.CONTACT_COLS, valores):
            self.contacto_vars[campo].set(valor)

    def _contacto_limpiar(self):
        for var in self.contacto_vars.values():
            var.set("")
        self.tree.selection_remove(*self.tree.selection())

    def _contacto_guardar(self):
        datos = {k: v.get().strip() for k, v in self.contacto_vars.items()}
        if not datos["nombre"]:
            messagebox.showerror(tr("Falta el nombre"), tr("El nombre no puede estar vacio."))
            return
        # Se relee del disco antes de tocar nada: si Eve agrego un contacto por
        # voz mientras el panel estaba abierto, escribir la lista que el panel
        # tenia cargada lo borraba sin decir nada.
        self.contactos = store.load_contacts()
        # Mismo nombre = actualizar, no duplicar.
        for i, c in enumerate(self.contactos):
            if store._plano(c.get("nombre", "")) == store._plano(datos["nombre"]):
                self.contactos[i] = datos
                break
        else:
            self.contactos.append(datos)
        store.save_contacts(self.contactos)
        self._contactos_refrescar()
        self._contacto_limpiar()

    def _contacto_exportar(self):
        from tkinter import filedialog

        nombre = self.contacto_vars["nombre"].get().strip()
        if not nombre:
            messagebox.showinfo(tr("Exportar"), tr("Elige un contacto de la lista primero."))
            return
        seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in nombre).strip()
        destino = filedialog.asksaveasfilename(
            title=tr("Guardar contacto para compartir"),
            initialfile=f"{seguro}.evecontact",
            defaultextension=".evecontact",
            filetypes=[("Contacto de Eve", "*.evecontact"), ("JSON", "*.json")],
        )
        if destino:
            messagebox.showinfo(tr("Exportar"), store.exportar_contactos([nombre], destino))

    def _contacto_importar(self):
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(
            title=tr("Abrir contacto compartido"),
            filetypes=[("Contacto de Eve", "*.evecontact"), ("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        try:
            nuevos = store.leer_contactos_archivo(ruta)
        except ValueError as exc:
            messagebox.showerror(tr("Importar"), str(exc))
            return

        agregados, cambiados, conflictos = store.importar_contactos(nuevos)
        if conflictos:
            # Pisar la agenda de alguien en silencio no es aceptable: se pregunta.
            if messagebox.askyesno(
                tr("Ya existen"),
                "Estos contactos ya estan en tu agenda:\n\n  "
                + "\n  ".join(conflictos)
                + "\n\nReemplazarlos con los del archivo?",
            ):
                mas, cambiados, _ = store.importar_contactos(nuevos, reemplazar=set(conflictos))
                agregados += mas

        self.contactos = store.load_contacts()
        self._contactos_refrescar()
        messagebox.showinfo(
            tr("Importar"),
            f"{agregados} agregado(s), {cambiados} actualizado(s)."
            + (f"\n{len(conflictos) - cambiados} sin tocar." if conflictos and not cambiados else ""),
        )

    def _contacto_borrar(self):
        nombre = self.contacto_vars["nombre"].get().strip()
        if not nombre:
            messagebox.showinfo(tr("Borrar"), tr("Elige un contacto de la lista primero."))
            return
        if not messagebox.askyesno(tr("Borrar"), f"Borrar a {nombre} de la agenda?"):
            return
        # Del disco, por lo mismo que al guardar: borrar uno no puede llevarse
        # puestos los que aparecieron mientras el panel estaba abierto.
        self.contactos = [
            c for c in store.load_contacts()
            if store._plano(c.get("nombre", "")) != store._plano(nombre)
        ]
        store.save_contacts(self.contactos)
        self._contactos_refrescar()
        self._contacto_limpiar()

    def _bloque_voces(self, nb):
        """Catalogo de Piper: 173 voces de la comunidad en 49 idiomas."""
        t = ttk.Frame(nb)
        ttk.Label(
            t,
            text=tr("Voces entrenadas por la comunidad (Piper). Gratis, offline, y las unicas\n"
            "que suenan igual en Windows, macOS y Linux. Se verifica el md5 al descargar."),
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        barra = ttk.Frame(t)
        barra.pack(fill="x", padx=12)
        ttk.Label(barra, text=tr("Idioma")).pack(side="left")
        self.voz_idioma = tk.StringVar(value="Spanish")
        self.voz_combo = ttk.Combobox(barra, textvariable=self.voz_idioma, width=22, state="readonly")
        self.voz_combo.pack(side="left", padx=6)
        ttk.Button(barra, text=tr("Buscar"), command=self.voces_buscar).pack(side="left")
        self.voz_estado = ttk.Label(barra, text="", foreground="#666")
        self.voz_estado.pack(side="left", padx=10)

        cols = ("key", "calidad", "mb", "estado")
        self.voz_tree = ttk.Treeview(t, columns=cols, show="headings", height=9)
        for c, w in zip(cols, (300, 90, 80, 110)):
            self.voz_tree.heading(c, text=c)
            self.voz_tree.column(c, width=w)
        self.voz_tree.pack(fill="both", expand=True, padx=12, pady=8)

        botones = ttk.Frame(t)
        botones.pack(anchor="w", padx=12, pady=(0, 10))
        ttk.Button(botones, text=tr("Descargar"), command=self.voz_descargar).pack(side="left")
        ttk.Button(botones, text=tr("Usar esta"), command=self.voz_usar).pack(side="left", padx=6)
        ttk.Button(botones, text=tr("Probar"), command=self.voz_probar).pack(side="left")
        ttk.Button(botones, text=tr("Borrar"), command=self.voz_borrar).pack(side="left", padx=6)
        self.after(300, self.voces_buscar)
        return t

    def voz_del_dialecto(self) -> None:
        """Pone la voz que le corresponde a la variante elegida.

        Con un boton y no solo: cambiar la voz de alguien porque toco otro
        control es exactamente la app poseida que el ajuste de autoridad existe
        para evitar. Se ofrece, no se impone.
        """
        from tkinter import messagebox

        from . import voices

        elegido = self.vars["dialecto"].get()
        clave = store.voz_del_dialecto(elegido)
        if not clave:
            messagebox.showinfo(tr("Voz"), tr("Elige una variante primero."), parent=self)
            return
        if clave not in voices.instaladas():
            try:
                messagebox.showinfo(tr("Voz"), voices.descargar(clave), parent=self)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror(tr("Voz"), f"No pude bajarla: {exc}", parent=self)
                return
        self.vars["piper_voice"].set(clave)
        self.vars["tts_provider"].set("piper")
        messagebox.showinfo(tr("Voz"), f"Voz puesta en {clave}. Guarda para aplicarlo.",
                            parent=self)

    def _pantallas(self) -> list:
        """Los numeros de monitor que se pueden elegir, con su tamaño al lado.

        Se le pregunta al sistema en vez de ofrecer un entero a ciegas: elegir
        "2" sin saber cual es el 2 es adivinar. Si no se pueden enumerar --pasa
        en Linux sin xrandr-- queda solo el 0, que es el comportamiento de
        siempre, y no se ofrece una opcion que no haria nada.
        """
        from . import plataforma

        valores = ["0"]
        for i, m in enumerate(plataforma.monitores(), 1):
            marca = " principal" if m["principal"] else ""
            valores.append(f"{i}")
            self._nombres_pantalla[f"{i}"] = f"{m['ancho']}x{m['alto']}{marca}"
        return valores

    def _voz_sel(self) -> str:
        sel = self.voz_tree.selection()
        return self.voz_tree.item(sel[0], "values")[0] if sel else ""

    def voces_buscar(self):
        self.voz_estado.config(text=tr("consultando catalogo..."))

        def work():
            from . import voices

            try:
                idiomas = voices.idiomas()
                lista = voices.listar(self.voz_idioma.get())
                puestas = set(voices.instaladas())
            except Exception as exc:  # noqa: BLE001
                fallo = str(exc)
                self._ui(lambda: self.voz_estado.config(text=f"error: {fallo}"))
                return

            def pintar():
                self.voz_combo["values"] = idiomas
                self.voz_tree.delete(*self.voz_tree.get_children())
                for v in lista:
                    self.voz_tree.insert(
                        "", "end",
                        values=(v["key"], v["calidad"], v["mb"],
                                "instalada" if v["key"] in puestas else ""),
                    )
                actual = self.cfg.get("piper_voice", "")
                self.voz_estado.config(
                    text=f"{len(lista)} voces · en uso: {actual or 'ninguna'}"
                )

            self._ui(pintar)

        threading.Thread(target=work, daemon=True).start()

    def voz_descargar(self):
        key = self._voz_sel()
        if not key:
            messagebox.showinfo(tr("Voces"), tr("Elige una voz de la lista."))
            return

        def work():
            from . import voices

            self._ui(lambda: self.voz_estado.config(text=f"descargando {key}..."))
            try:
                msg = voices.descargar(
                    key,
                    progreso=lambda k, hecho, total: self.after(
                        0, lambda: self.voz_estado.config(
                            text=f"{k}: {int(hecho * 100 / total)}%"
                        )
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"Fallo la descarga: {exc}"
            self._ui(lambda: (messagebox.showinfo(tr("Voces"), msg), self.voces_buscar()))

        threading.Thread(target=work, daemon=True).start()

    def voz_usar(self):
        from . import voices

        key = self._voz_sel()
        if key not in voices.instaladas():
            messagebox.showinfo(tr("Voces"), tr("Descargala primero."))
            return
        self.vars["piper_voice"].set(key)
        self.vars["tts_provider"].set("piper")
        messagebox.showinfo(tr("Voces"), f"{key} seleccionada.\nToca Guardar para aplicarla.")

    def voz_probar(self):
        from . import voices

        key = self._voz_sel() or self.cfg.get("piper_voice", "")
        if key not in voices.instaladas():
            messagebox.showinfo(tr("Voces"), tr("Descargala primero."))
            return

        def work():
            try:
                voices.reproducir(
                    voices.hablar(f"Hola, soy {self.cfg['assistant_name']}. Asi sueno.", key)
                )
            except Exception as exc:  # noqa: BLE001
                fallo = str(exc)
                self._ui(lambda: messagebox.showerror(tr("Voces"), fallo))

        threading.Thread(target=work, daemon=True).start()

    def voz_borrar(self):
        from . import voices

        key = self._voz_sel()
        if key and messagebox.askyesno(tr("Voces"), f"Borrar {key}?"):
            messagebox.showinfo(tr("Voces"), voices.borrar(key))
            self.voces_buscar()

    def _bloque_correo(self, nb):
        """Tab propio: junto con Claves no entraba en la ventana."""
        t = ttk.Frame(nb)

        out = self._seccion(t, tr("Outlook"))
        ttk.Label(
            out,
            text=tr("No necesita ninguna clave: Eve usa la sesion que ya tiene Outlook en esta PC."),
            foreground="#666",
        ).pack(anchor="w", padx=10, pady=(8, 4))
        self.outlook_label = ttk.Label(out, text=tr("consultando..."), justify="left")
        self.outlook_label.pack(anchor="w", padx=10)
        fila = ttk.Frame(out)
        fila.pack(anchor="w", padx=10, pady=(6, 10))
        ttk.Button(fila, text=tr("Agregar / gestionar cuentas"), command=self.outlook_login).pack(
            side="left"
        )
        ttk.Button(fila, text=tr("Actualizar"), command=self.refresh_outlook).pack(side="left", padx=6)

        gm = self._seccion(t, tr("Gmail"))
        ttk.Label(
            gm,
            text=tr("Lo mas simple es agregarlo a Outlook con el boton de arriba: Google hace el\n"
            "login y no queda ninguna clave tuya guardada aca.\n\n"
            "La otra via es una contrasena de aplicacion (16 letras minusculas). Si Google\n"
            "dice que no esta disponible, es que tu cuenta no tiene verificacion en dos\n"
            "pasos, o la administra tu organizacion."),
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(8, 4))
        self._row(gm, tr("Tu direccion de Gmail"), "gmail_address", width=38)
        self._campo_clave(gm, "gmail", tr("Contrasena de aplicacion"))
        self.gmail_label = ttk.Label(gm, text="", justify="left")
        self.gmail_label.pack(anchor="w", padx=12, pady=(6, 0))
        fila2 = ttk.Frame(gm)
        fila2.pack(anchor="w", padx=12, pady=(6, 10))
        ttk.Button(fila2, text=tr("Obtener app password"), command=self.gmail_login).pack(side="left")
        ttk.Button(fila2, text=tr("Probar conexion"), command=self.gmail_probar).pack(side="left", padx=6)

        self.after(200, self.refresh_outlook)
        return t

    def _bloque_voz(self, nb):
        """Generado desde `registro.VOZ`.

        La pestaña mas grande de las que se podian migrar: 48 llamadas
        declarativas contra 13 a mano, o sea 21% de excepciones. El freno del
        plan es un tercio, asi que entraba con margen.

        Convivio con la escrita a mano hasta comprobar que las 26 claves daban
        el mismo tipo y el mismo valor en las dos; recien ahi se borro la vieja.
        """
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.VOZ)
        return t


    def refresh_apps(self, scan: bool):
        from . import apps

        data = apps.load(refresh=scan)
        self.apps_label.config(
            text=f"{len(data['games'])} juegos (Steam, Ubisoft, Epic) y "
            f"{len(data['apps'])} programas del menu inicio."
        )

    def rescan_apps(self):
        self.refresh_apps(scan=True)
        messagebox.showinfo(tr("Programas"), tr("Indice actualizado."))

    # --- apariencia --------------------------------------------------------

    def _cfg_previa(self) -> dict:
        """La config como quedaria si guardaras ahora, para la vista previa."""
        cfg = dict(self.cfg)
        for clave, var in self.vars.items():
            if clave.startswith(("ui_", "hud_", "sub_")):
                valor = var.get()
                por_defecto = store.DEFAULTS.get(clave)
                if isinstance(por_defecto, int) and not isinstance(por_defecto, bool):
                    try:
                        valor = int(valor)
                    except (TypeError, ValueError):
                        valor = por_defecto
                cfg[clave] = valor
        # La escala es cuan grande sale en pantalla; en la previa sobraria.
        cfg["hud_escala"] = 100
        return cfg

    def _previa_redibujar(self, *_args) -> None:
        if not getattr(self, "previa", None):
            return
        from . import overlay, tema

        cfg = self._cfg_previa()
        paleta = tema.resolver(cfg, "hud")
        if self._pintor is None:
            self._pintor = overlay.Pintor(cfg, paleta)
            for i in range(overlay.MUESTRAS):  # una onda de muestra, quieta
                self._pintor.niveles.append(abs(math.sin(i * 0.37)) * 0.85)
        else:
            self._pintor.aplicar(cfg, paleta)
        self.previa.configure(bg=paleta["fondo"])
        titulo = cfg.get("hud_titulo") or self.vars["assistant_name"].get() or "Eve"
        self._pintor.pintar(self.previa, "hablando", titulo, "RESPONDIENDO")
        self._colores_habilitados()
        # Lo que se pidio: el panel cambia de color mientras elegis, sin reabrir.
        self.cfg = {**self.cfg, **{k: v for k, v in cfg.items() if k.startswith("ui_")}}
        self.repintar()

    def _colores_habilitados(self) -> None:
        for prefijo, fila in getattr(self, "_filas_color", []):
            tema_de = self.vars.get(f"{prefijo}_tema")
            elegido = tema_de.get() if tema_de else ""
            if prefijo != "ui" and not elegido:
                elegido = self.vars["ui_tema"].get()  # hereda el del panel
            propio = elegido == "personalizado"
            for w in fila:
                try:
                    w.configure(state="normal" if propio else "disabled")
                except tk.TclError:
                    pass

    def _fila_color(self, padre, prefijo: str, rol: str, etiqueta: str) -> None:
        from tkinter import colorchooser

        from . import tema

        clave = f"{prefijo}_color_{rol}"
        fila = ttk.Frame(padre)
        fila.pack(fill="x", padx=12, pady=3)
        ttk.Label(fila, text=etiqueta, width=24).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(clave, "")))
        self.vars[clave] = var
        entrada = ttk.Entry(fila, textvariable=var, width=12)
        entrada.pack(side="left")
        muestra = tk.Label(fila, width=4, relief="solid", borderwidth=1)
        muestra._eve_color_propio = True  # el repintado del tema no la toca
        muestra.pack(side="left", padx=6)

        def repintar(*_a):
            valor = var.get().strip() or tema.resolver(self._cfg_previa(), prefijo)[rol]
            try:
                muestra.configure(bg=valor)
            except tk.TclError:
                pass  # a medio escribir "#4fc" no es un color todavia

        def elegir():
            elegido = colorchooser.askcolor(color=muestra.cget("bg"), parent=self)[1]
            if elegido:
                var.set(elegido)

        boton = ttk.Button(fila, text=tr("Elegir..."), command=elegir, width=10)
        boton.pack(side="left")
        var.trace_add("write", repintar)
        var.trace_add("write", self._previa_redibujar)
        repintar()
        self._filas_color.append((prefijo, (entrada, boton)))

    def _bloque_tema(self, nb):
        """Generado desde `registro.TEMA`.

        Cuarta pestaña migrada, 23% de excepciones. La cabecera con el selector
        de archivo se queda como `Propio` --abre un dialogo, no es una fila-- y
        declara la clave que toca para que la verificacion no la pierda.
        """
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.TEMA)
        return t


    def _addon_revocar(self, nombre: str) -> None:
        """Saca la aprobacion y rearma la pestaña, para que se vea el cambio."""
        from . import addons

        self.estado.config(text=addons.revocar(nombre))
        self._recargar_addons()

    def _addon_ver(self, ruta: str) -> None:
        """Muestra el archivo entero antes de aprobarlo."""
        from . import integrations

        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                codigo = f.read()
        except OSError as exc:
            messagebox.showerror(tr("No pude leerlo"), str(exc))
            return
        integrations.mostrar(os.path.basename(ruta), codigo)

    def _addon_aprobar(self, nombre: str, marca: str) -> None:
        if not messagebox.askyesno(
            tr("Aprobar addon"),
            f"Vas a dejar que {nombre}.py corra con tus permisos.\n\n"
            "Lo miraste?",
        ):
            return
        from . import addons

        self.estado.config(text=addons.aprobar(nombre, marca))
        self._recargar_addons()

    def _recargar_addons(self) -> None:
        """Vuelve a armar la pestaña: la lista de pendientes cambio."""
        from . import addons

        addons.todos(recargar=True)
        messagebox.showinfo(tr("Listo"), tr("Cierra y abre el panel para verlo cargado."))

    def _bloque_ventana(self, nb):
        """Generado desde `registro.VENTANA`.

        Segunda pestaña migrada. La ventana de actividad estuvo sin pestaña
        propia desde que existe, y la unica forma de abrirla era un boton
        adentro de Modulos: si una ventana entera no tiene donde configurarse,
        para el usuario no existe.
        """
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.VENTANA)
        return t

    def _bloque_modulos(self, nb):
        """Los modulos del cartel y del tablero.

        El formulario de propiedades no esta escrito: se GENERA recorriendo el
        esquema de `modulos.props_de(tipo)`. Agregar una prop a un tipo de
        modulo no toca este archivo, que es todo el punto del sistema: si cada
        perilla nueva costara veinte lineas de tkinter, "hiperpersonalizable"
        no llegaria muy lejos.
        """
        from . import modulos as mods

        t = ttk.Frame(nb)
        self.mod_sel = ""
        self.mod_vars = {}

        lista = self._seccion(t, tr("Modulos"))
        self._ayuda(
            lista,
            tr("Cada modulo es una pieza del cartel: un icono, una onda, particulas,\n"
            "el reloj o el medidor de contexto. Se puede elegir donde va, de que\n"
            "tamano, con cuanta transparencia y cuando se muestra."),
        )
        self.mod_tree = ttk.Treeview(
            lista, columns=("tipo", "donde", "pos", "cuando"), show="headings", height=7
        )
        for col, titulo, ancho in (("tipo", "Tipo", 90), ("donde", "Superficie", 90),
                                   ("pos", "Posicion", 110), ("cuando", "Se ve", 90)):
            self.mod_tree.heading(col, text=titulo)
            self.mod_tree.column(col, width=ancho, anchor="w")
        self.mod_tree.pack(fill="x", padx=12, pady=(6, 0))
        self.mod_tree.bind("<<TreeviewSelect>>", self._mods_elegido)

        fila = ttk.Frame(lista)
        fila.pack(anchor="w", padx=12, pady=(6, 10))
        self.mod_tipo = tk.StringVar(value=mods.OPCIONES["tipo"][0])
        ttk.Combobox(fila, textvariable=self.mod_tipo, values=mods.OPCIONES["tipo"],
                     state="readonly", width=12).pack(side="left")
        ttk.Button(fila, text=tr("Agregar"), command=self._mods_agregar).pack(side="left", padx=6)
        ttk.Button(fila, text=tr("Duplicar"), command=self._mods_duplicar).pack(side="left")
        ttk.Button(fila, text=tr("Borrar"), command=self._mods_borrar).pack(side="left", padx=6)
        ttk.Button(fila, text=tr("Traer los del cartel actual"),
                   command=self._mods_semilla).pack(side="left", padx=(18, 0))

        fila2 = ttk.Frame(lista)
        fila2.pack(anchor="w", padx=12, pady=(0, 10))
        ttk.Button(fila2, text=tr("Armar el tablero de arranque"),
                   command=self._mods_semilla_tablero).pack(side="left")
        ttk.Button(fila2, text=tr("Abrir la ventana de actividad"),
                   command=self._abrir_consola).pack(side="left", padx=6)
        self._ayuda(fila2, tr("  ahi se acomodan los modulos del tablero con el mouse"))

        self.mod_caja = self._seccion(t, tr("Ajustes del modulo"))
        self.mod_props = ttk.Frame(self.mod_caja)
        self.mod_props.pack(fill="x")
        self._mods_refrescar()
        return t

    # --- modulos ------------------------------------------------------------

    def _mods_semilla_tablero(self) -> None:
        """Un tablero que ya muestre algo, en vez de una ventana en blanco."""
        from . import modulos as mods

        cfg = store.load_config()
        for ident, m in mods.por_defecto_tablero().items():
            cfg = mods.guardar(cfg, dict(m, id=ident))
        store.save_config(cfg)
        self._mods_refrescar()
        self.estado.config(text=tr("tablero armado: abre la ventana de actividad"))

    def _abrir_consola(self) -> None:
        from . import consola

        consola.abrir()
        self.estado.config(text=tr("ventana de actividad abierta"))

    def _mods_refrescar(self, elegir: str = "") -> None:
        from . import modulos as mods

        cfg = store.load_config()
        self.mod_tree.delete(*self.mod_tree.get_children())
        for m in mods.listar(cfg):
            self.mod_tree.insert(
                "", "end", iid=m["id"],
                values=(m["tipo"], m["superficie"],
                        f'{m["x"]},{m["y"]}  {m["ancho"]}x{m["alto"]}', m["cuando"]),
            )
        objetivo = elegir or self.mod_sel
        if objetivo and self.mod_tree.exists(objetivo):
            self.mod_tree.selection_set(objetivo)
            # Y se arma el formulario aca mismo. Dejarlo a que llegue el evento
            # `<<TreeviewSelect>>` significa que entre duplicar y editar hay un
            # momento en el que `mod_sel` apunta al modulo anterior: el boton
            # Borrar se llevaba el equivocado.
            self._mods_props(objetivo)
        else:
            self._mods_props("")

    def _mods_elegido(self, _evt=None) -> None:
        sel = self.mod_tree.selection()
        self._mods_props(sel[0] if sel else "")

    def _mods_props(self, ident: str) -> None:
        """Arma el formulario del modulo elegido, prop por prop del esquema."""
        from . import modulos as mods

        self.mod_sel = ident
        for hijo in self.mod_props.winfo_children():
            hijo.destroy()
        self.mod_vars = {}
        if not ident:
            self._ayuda(self.mod_props, tr("Elige un modulo de la lista para ajustarlo."))
            return

        modulo = mods.leer(store.load_config(), ident)
        for prop, par in mods.props_de(modulo["tipo"]).items():
            if prop == "tipo":
                continue
            valor = modulo.get(prop, par[0])
            fila = ttk.Frame(self.mod_props)
            fila.pack(fill="x", padx=12, pady=1)
            ttk.Label(fila, text=prop, width=13).pack(side="left")
            if isinstance(par[0], bool):
                var = tk.BooleanVar(value=bool(valor))
                ttk.Checkbutton(fila, variable=var).pack(side="left")
            elif prop in mods.OPCIONES:
                var = tk.StringVar(value=str(valor))
                ttk.Combobox(fila, textvariable=var, values=mods.OPCIONES[prop],
                             state="readonly", width=16).pack(side="left")
            else:
                var = tk.StringVar(value=str(valor))
                ttk.Entry(fila, textvariable=var, width=18).pack(side="left")
            self.mod_vars[prop] = var
            ttk.Label(fila, text="  " + par[1], style="Ayuda.TLabel").pack(side="left")

        pie = ttk.Frame(self.mod_props)
        pie.pack(fill="x", padx=12, pady=(8, 10))
        ttk.Button(pie, text=tr("Aplicar"), command=self._mods_aplicar).pack(side="left")
        if modulo["tipo"] == "particulas":
            ttk.Button(pie, text=tr("Importar .plist"),
                       command=self._mods_plist).pack(side="left", padx=8)
            self._ayuda(
                self.mod_props,
                tr("Los editores de particulas --Particle Designer, Particle2dx--\n"
                "exportan el .plist de cocos2d, que es XML de numeros: vida,\n"
                "gravedad, color, velocidad. Se importa la CONFIGURACION y la\n"
                "corre el simulador que ya esta, asi que no entra ninguna\n"
                "libreria nueva. Llena los campos de arriba; despues Aplicar.\n"
                "No viaja lo que el simulador no sabe hacer: modo radial,\n"
                "texturas por particula y mezclas aditivas."))

    def _mods_plist(self) -> None:
        """Trae los parametros de un .plist al formulario, sin guardarlos.

        Llena los campos y no aplica: importar es proponer valores, y que un
        archivo ajeno pise el modulo sin que lo veas es la misma sorpresa que el
        ajuste de autoridad existe para evitar.
        """
        from tkinter import filedialog, messagebox

        from . import modulos as mods

        ruta = filedialog.askopenfilename(
            title=tr("Particulas de Particle Designer"), parent=self,
            filetypes=[("Particulas", "*.plist"), ("Todos", "*.*")])
        if not ruta:
            return
        props = mods.desde_plist(ruta)
        if not props:
            messagebox.showerror(
                tr("Particulas"),
                tr("No pude leer ese archivo. Tiene que ser un .plist de cocos2d "
                "(el que exportan Particle Designer y Particle2dx)."), parent=self)
            return
        traidas = [p for p in props if p in self.mod_vars]
        for prop in traidas:
            self.mod_vars[prop].set(str(props[prop]))
        messagebox.showinfo(
            tr("Particulas"),
            "Traje: " + ", ".join(sorted(traidas)) + ".\n\nRevisalos y toca Aplicar.",
            parent=self)

    def _mods_aplicar(self) -> None:
        """Guarda el modulo. Los tipos salen del esquema, no de adivinar."""
        from . import modulos as mods

        if not self.mod_sel:
            return
        cfg = store.load_config()
        modulo = mods.leer(cfg, self.mod_sel)
        for prop, var in self.mod_vars.items():
            defecto = mods.props_de(modulo["tipo"]).get(prop, ("",))[0]
            valor = var.get()
            if isinstance(defecto, bool):
                modulo[prop] = bool(valor)
            elif isinstance(defecto, int):
                try:
                    modulo[prop] = int(float(str(valor).replace(",", ".")))
                except ValueError:
                    messagebox.showerror(tr("Valor invalido"), f"'{prop}' tiene que ser un numero.")
                    return
            elif isinstance(defecto, float):
                try:
                    modulo[prop] = float(str(valor).replace(",", "."))
                except ValueError:
                    messagebox.showerror(tr("Valor invalido"), f"'{prop}' tiene que ser un numero.")
                    return
            else:
                modulo[prop] = valor
        store.save_config(mods.guardar(cfg, modulo))
        store.marcar_tocadas([mods.clave(self.mod_sel, prop) for prop in self.mod_vars])
        self._mods_refrescar(self.mod_sel)
        self.estado.config(text=f"modulo '{self.mod_sel}' guardado")

    def _mods_agregar(self) -> None:
        from . import modulos as mods

        cfg = store.load_config()
        tipo = self.mod_tipo.get()
        usados = set(mods.identificadores(cfg))
        n = 1
        while f"{tipo}{n}" in usados:
            n += 1
        ident = f"{tipo}{n}"
        store.save_config(mods.guardar(cfg, {"id": ident, "tipo": tipo}))
        self._mods_refrescar(ident)

    def _mods_duplicar(self) -> None:
        from . import modulos as mods

        if not self.mod_sel:
            return
        cfg = store.load_config()
        modulo = mods.leer(cfg, self.mod_sel)
        usados = set(mods.identificadores(cfg))
        n = 2
        while f"{self.mod_sel}{n}" in usados:
            n += 1
        modulo["id"] = f"{self.mod_sel}{n}"
        modulo["x"] = int(modulo["x"]) + 20
        modulo["y"] = int(modulo["y"]) + 20
        store.save_config(mods.guardar(cfg, modulo))
        self._mods_refrescar(modulo["id"])

    def _mods_borrar(self) -> None:
        from . import modulos as mods

        if not self.mod_sel:
            return
        store.save_config(mods.borrar(store.load_config(), self.mod_sel))
        self.mod_sel = ""
        self._mods_refrescar()

    def _mods_semilla(self) -> None:
        """Escribe el cartel que ya existe como modulos, para tener de donde partir."""
        from . import modulos as mods

        cfg = store.load_config()
        for ident, m in mods.por_defecto(cfg).items():
            cfg = mods.guardar(cfg, dict(m, id=ident))
        store.save_config(cfg)
        self._mods_refrescar()
        self.estado.config(text=tr("listo: el cartel de siempre, ahora como modulos"))

    def _bloque_hud(self, nb):
        from . import tema

        t = ttk.Frame(nb)
        caja = self._seccion(t, tr("Cartel en pantalla"))
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(8, 2))
        ttk.Button(fila, text=tr("Mostrar el cartel"),
                   command=self.probar_overlay).pack(side="left")
        self._ayuda(
            caja,
            tr("Lo hace aparecer unos segundos aunque este en modo 'auto'. Es lo que\n"
            "separa 'el cartel esta mal configurado' de 'el cartel no arranca'."))
        self._row(caja, tr("Cuando se ve"), "overlay_modo", ["auto", "siempre", "nunca"])
        # El tema del cartel vive aca, junto a lo demas del cartel, y no
        # mezclado con los colores del panel.
        self._row(caja, tr("Tema (vacio = el del panel)"), "hud_tema", ["", *tema.NOMBRES])
        self.vars["hud_tema"].trace_add("write", self._previa_redibujar)
        self._ayuda(
            caja,
            tr("auto = aparece al hablarle y se va sola. Nunca se lleva el foco de lo que\n"
            "estes haciendo, y los clics la atraviesan."),
        )
        self._row(caja, tr("Titulo (vacio = nombre IA)"), "hud_titulo")
        self._row(caja, tr("Segunda linea"), "hud_subtitulo")
        self._row(caja, tr("Icono"), "hud_icono", ["hexagono", "ninguno"])
        self._row(caja, tr("Contorno"), "hud_contorno",
                  ["ninguno", "linea", "esquinas", "doble", "hexagonal", "biselado"])
        self._row(caja, tr("Onda"), "hud_onda",
                  ["barras", "espejo", "linea", "puntos", "ninguna"])
        self._row(caja, tr("Escala (%)"), "hud_escala")
        self._row(caja, tr("Opacidad (%)"), "hud_opacidad")
        self._ayuda(
            caja,
            tr("Menos de 10 se trata como 10: por debajo de eso el cartel no se ve\n"
            "y no habria forma de encontrarlo para subirlo de nuevo. La opacidad\n"
            "de cada modulo se MULTIPLICA con esta, asi que 20% de ventana por\n"
            "20% de modulo da 4% de verdad."))

        self._row(caja, tr("Pantalla"), "overlay_pantalla", self._pantallas())
        self._row(caja, tr("Area"), "overlay_area", ["trabajo", "completa"])
        self._ayuda(
            caja,
            tr("0 = donde lo dejes, sin restriccion, y puedes arrastrarlo de un\n"
            "monitor al otro. 1 en adelante lo fija a ese monitor y lo mantiene\n"
            "adentro aunque lo arrastres. Si desenchufas el que elegiste, vuelve\n"
            "al escritorio entero en vez de quedar en un lugar que no existe.\n"
            "'trabajo' descuenta la barra de tareas; solo cambia algo en Windows."))

        self._row(caja, tr("Toma clics"), "overlay_clics", ["nunca", "hover", "fijo"])
        self._ayuda(
            caja,
            tr("El cartel normalmente deja pasar los clics al programa de atras.\n"
            "  nunca   nunca los toma\n"
            "  hover   solo mientras el puntero esta sobre un modulo marcado\n"
            "          como 'interactivo'; si no marcaste ninguno, es igual\n"
            "          que 'nunca'\n"
            "  fijo    siempre los toma, y siempre tapa lo que este debajo\n"
            "Se pregunta donde esta el puntero treinta veces por segundo en vez\n"
            "de escuchar eventos, porque una ventana que deja pasar los clics\n"
            "tampoco recibe los de movimiento: esperarlos seria esperar para\n"
            "siempre. Ese mismo poll es el que hace andar 'cuando = hover'."))

        self._row(caja, tr("Forma"), "hud_forma", ["caja", "recortado"])
        self._ayuda(
            caja,
            tr("recortado = el cartel deja de ser un rectangulo y por las esquinas cortadas\n"
            "de los contornos hexagonal y biselado se ve lo que hay atras."),
        )

        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(6, 10))
        ttk.Button(fila, text=tr("Elegir imagen del icono..."),
                   command=self._icono_elegir).pack(side="left")
        ttk.Button(fila, text=tr("Mover en pantalla"),
                   command=self._overlay_mover).pack(side="left", padx=6)
        ttk.Button(fila, text=tr("Volver a la esquina"),
                   command=self._overlay_esquina).pack(side="left")

        caja = self._seccion(t, tr("Marco del icono"))
        self._ayuda(
            caja,
            tr("El marco es parametrico: eliges cuantos lados, cuanto gira y cuanto se\n"
            "redondean las puntas. Las formas de abajo son atajos que llenan esos\n"
            "numeros; despues los puedes tocar a mano."),
        )
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(4, 8))
        ttk.Label(fila, text=tr("Formas"), width=24).pack(side="left")
        self.forma_var = tk.StringVar()
        combo = ttk.Combobox(fila, textvariable=self.forma_var,
                             values=sorted(overlay_formas()), state="readonly")
        combo.pack(side="left", fill="x", expand=True)
        combo.bind("<<ComboboxSelected>>", self._forma_elegida)
        self._row(caja, tr("Lados (menos de 3 = circulo)"), "hud_marco_lados")
        self._row(caja, tr("Giro (grados)"), "hud_marco_rot")
        self._row(caja, tr("Redondeo de las puntas"), "hud_marco_redondeo")
        self._row(caja, tr("Grosor del trazo"), "hud_marco_grosor")
        for clave in ("hud_marco_lados", "hud_marco_rot", "hud_marco_redondeo",
                      "hud_marco_grosor"):
            self.vars[clave].trace_add("write", self._previa_redibujar)

        self._bloque_fondo(t, "hud", tr("Fondo del cartel"))
        for clave in ("hud_titulo", "hud_subtitulo", "hud_icono", "hud_contorno",
                      "hud_onda", "hud_forma"):
            self.vars[clave].trace_add("write", self._previa_redibujar)
        self._previa_redibujar()
        return t

    def _forma_elegida(self, _evento=None):
        """Una forma del catalogo es un atajo que llena los cuatro numeros."""
        from . import overlay

        valores = overlay.FORMAS.get(self.forma_var.get())
        if not valores:
            return
        lados, rot, redondeo = valores
        self.vars["hud_marco_lados"].set(str(lados))
        self.vars["hud_marco_rot"].set(str(rot))
        self.vars["hud_marco_redondeo"].set(str(redondeo))

    def _bloque_fondo(self, padre, prefijo: str, titulo: str) -> None:
        """Los controles de imagen de fondo, iguales para el cartel y los subtitulos."""
        from tkinter import filedialog

        caja = self._seccion(padre, titulo)
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=5)
        ttk.Label(fila, text=tr("Imagen (PNG o GIF)"), width=24).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(f"{prefijo}_fondo", "")))
        self.vars[f"{prefijo}_fondo"] = var
        ttk.Entry(fila, textvariable=var).pack(side="left", fill="x", expand=True)

        def elegir():
            ruta = filedialog.askopenfilename(
                title=titulo, parent=self,
                filetypes=[("Imagenes y sprite sheets",
                            "*.png *.gif *.webp *.apng *.jpg *.jpeg *.bmp"),
                       ("Todos", "*.*")],
            )
            if ruta:
                var.set(ruta)

        ttk.Button(fila, text="...", width=4, command=elegir).pack(side="left", padx=(6, 0))
        ttk.Button(fila, text=tr("Quitar"), width=8,
                   command=lambda: var.set("")).pack(side="left", padx=(4, 0))

        self._row(caja, tr("Ajuste"), f"{prefijo}_fondo_ajuste",
                  ["recortar", "estirar", "mosaico"])
        self._row(caja, tr("Opacidad de la imagen (%)"), f"{prefijo}_fondo_opacidad")
        self._row(caja, tr("Tinte con el acento (%)"), f"{prefijo}_fondo_tinte")
        self._ayuda(
            caja,
            tr("El GIF se anima solo. La opacidad se mezcla en la imagen y no en la ventana,\n"
            "asi que bajarla atenua el fondo pero el texto sigue entero."),
        )
        self._row(caja, tr("Degradado (si no hay imagen)"), f"{prefijo}_grad",
                  ["ninguno", "vertical", "horizontal", "diagonal", "radial"])
        self._fila_color_libre(caja, f"{prefijo}_grad_a", tr("Degradado: color 1"))
        self._fila_color_libre(caja, f"{prefijo}_grad_b", tr("Degradado: color 2"))
        for sufijo in ("fondo", "fondo_ajuste", "fondo_opacidad", "fondo_tinte",
                       "grad", "grad_a", "grad_b"):
            self.vars[f"{prefijo}_{sufijo}"].trace_add("write", self._previa_redibujar)

    def _fila_color_libre(self, padre, clave: str, etiqueta: str) -> None:
        """Un color suelto, sin depender del tema. Vacio = el del tema."""
        from tkinter import colorchooser

        fila = ttk.Frame(padre)
        fila.pack(fill="x", padx=12, pady=3)
        ttk.Label(fila, text=etiqueta, width=24).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get(clave, "")))
        self.vars[clave] = var
        ttk.Entry(fila, textvariable=var, width=12).pack(side="left")
        muestra = tk.Label(fila, width=4, relief="solid", borderwidth=1)
        muestra._eve_color_propio = True  # el repintado del tema no la toca
        muestra.pack(side="left", padx=6)

        def repintar(*_a):
            try:
                muestra.configure(bg=var.get().strip() or "#808080")
            except tk.TclError:
                pass

        def elegir():
            elegido = colorchooser.askcolor(color=muestra.cget("bg"), parent=self)[1]
            if elegido:
                var.set(elegido)

        ttk.Button(fila, text=tr("Elegir..."), command=elegir, width=10).pack(side="left")
        var.trace_add("write", repintar)
        repintar()

    def _icono_elegir(self):
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(
            title=tr("Imagen para el icono"), parent=self,
            filetypes=[("Imagenes y sprite sheets",
                            "*.png *.gif *.webp *.apng *.jpg *.jpeg *.bmp"),
                       ("Todos", "*.*")],
        )
        if ruta:
            self.vars["hud_icono"].set(ruta)

    def _overlay_mover(self):
        from . import overlay

        cfg = store.load_config()
        cfg["overlay_mover"] = True
        store.save_config(cfg)
        self.cfg["overlay_mover"] = True
        overlay.asegurar(cfg)
        messagebox.showinfo(
            tr("Mover el cartel"),
            tr("El cartel esta suelto: arrastralo a donde quieras y sueltalo.\n\n"
            "Al soltarlo se guarda la posicion y vuelve a dejar pasar los clics."),
        )

    def _overlay_esquina(self):
        self.vars["hud_x"].set("40") if "hud_x" in self.vars else None
        cfg = store.load_config()
        cfg.update({"hud_x": 40, "hud_y": 40})
        store.save_config(cfg)
        self.cfg.update({"hud_x": 40, "hud_y": 40})
        messagebox.showinfo(tr("Posicion"), tr("El cartel vuelve a la esquina de arriba a la izquierda."))

    def _bloque_subtitulos(self, nb):
        """Generado desde `registro.SUBTITULOS`.

        Primera pestaña migrada. Convivio con la escrita a mano hasta que el
        test comprobo que las dos daban las mismas claves, los mismos tipos y
        los mismos valores; recien ahi se borro la vieja. "Produce el mismo
        config" sin medirlo es una afirmacion, no una migracion.
        """
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.SUBTITULOS)
        return t


    def _bloque_historial(self, nb):
        t = ttk.Frame(nb)
        bar = ttk.Frame(t)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Button(bar, text=tr("Limpiar historial"), command=self.clear_history).pack(side="left")
        self.hist_count = ttk.Label(bar, text="", foreground="#666")
        self.hist_count.pack(side="left", padx=10)
        self.hist_box = tk.Text(t, wrap="word")
        self.hist_box.pack(fill="both", expand=True, padx=8, pady=8)
        self.refresh_history()
        return t

    def refresh_history(self):
        turns = store.recent_turns()
        self.hist_box.config(state="normal")
        self.hist_box.delete("1.0", "end")
        for ts, role, text in reversed(turns):
            stamp = time.strftime("%d/%m %H:%M", time.localtime(ts))
            self.hist_box.insert("end", f"[{stamp}] {role}: {text}\n\n")
        self.hist_box.config(state="disabled")
        self.hist_count.config(text=f"{len(turns)} mensajes guardados")

    def clear_history(self):
        if not messagebox.askyesno(
            tr("Limpiar historial"),
            tr("Borra la conversacion guardada y deja la ventana de contexto en cero.\n\n"
            "El registro de acciones (pestaña Acciones) NO se toca.\n\n"
            "Si el listener esta corriendo, usa tambien la bandeja > 'Limpiar historial y\n"
            "contexto' para vaciar lo que ya tiene en memoria.\n\nBorrar?"),
        ):
            return
        n = store.clear_history()
        self.refresh_history()
        messagebox.showinfo(tr("Limpiar historial"), f"{n} mensajes borrados.")

    def _bloque_acciones(self, nb):
        t = ttk.Frame(nb)
        cols = ("hora", "tool", "detalle", "resultado")
        tree = ttk.Treeview(t, columns=cols, show="headings")
        for c, w in zip(cols, (110, 100, 300, 300)):
            tree.heading(c, text=c)
            tree.column(c, width=w)
        for ts, tool, detail, outcome in store.recent_actions():
            tree.insert(
                "",
                "end",
                values=(time.strftime("%d/%m %H:%M", time.localtime(ts)), tool, detail, outcome),
            )
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        return t

    # --- correo -------------------------------------------------------------

    def refresh_outlook(self):
        """En un hilo: abrir Outlook por COM puede tardar segundos si esta cerrado."""
        self.outlook_label.config(text=tr("consultando..."))

        def work():
            from . import integrations

            cuentas = integrations.outlook_cuentas()
            texto = (
                "Cuentas: " + ", ".join(cuentas)
                if cuentas
                else "Sin cuentas, o Outlook no responde."
            )
            self._ui(lambda: self.outlook_label.config(text=texto))

        threading.Thread(target=work, daemon=True).start()

    def outlook_login(self):
        from . import integrations

        messagebox.showinfo(tr("Outlook"), integrations.outlook_agregar_cuenta())

    def gmail_login(self):
        import webbrowser

        webbrowser.open("https://myaccount.google.com/apppasswords")
        messagebox.showinfo(
            tr("Gmail"),
            tr("Te abri la pagina de contrasenas de aplicacion.\n\n"
            "Si dice que no esta disponible para tu cuenta, es porque no tienes\n"
            "verificacion en dos pasos activada, o la administra tu organizacion.\n\n"
            "En ese caso usa el boton de Outlook: agregas el Gmail ahi y listo."),
        )

    def gmail_probar(self):
        self.gmail_label.config(text=tr("probando..."))

        def work():
            from . import integrations

            texto = integrations.gmail_probar()
            self._ui(lambda: self.gmail_label.config(text=texto))

        threading.Thread(target=work, daemon=True).start()

    def probar_stt(self) -> None:
        """Graba tres segundos del microfono y los transcribe.

        El camino entero y no una pieza: microfono, sensibilidad, modelo y
        vocabulario, que es donde de verdad falla. Corre en un hilo porque
        grabar y transcribir bloquean, y el panel no puede quedarse duro.
        """
        import threading

        self.estado.config(text=tr("Habla ahora... (3 segundos)"))
        self.update_idletasks()

        def trabajo():
            try:
                import time as _t

                import numpy as np

                from . import voice

                cfg = store.load_config()
                rec = voice.Recorder()
                rec.start()
                _t.sleep(3.0)
                audio = rec.stop()
                if audio.size < 1000:
                    return "No entro audio. ¿Esta tomado el microfono por otro programa?"
                pico = 20 * np.log10(max(1e-9, float(np.abs(audio).max())))
                texto = voice.transcribe(audio, cfg)
                umbral, aire, modo = voice.sensibilidad(cfg)
                if not texto:
                    return (f"No entendi nada. Pico {pico:.0f} dBFS, modo {modo}. "
                            "Si el pico es menor a -40 el microfono esta muy bajo.")
                return f"Te escuche: {texto!r}   (pico {pico:.0f} dBFS, modo {modo})"
            except Exception as exc:  # noqa: BLE001 - el panel no puede morir
                return f"Fallo escuchando: {type(exc).__name__}: {exc}"

        def correr():
            r = trabajo()
            self.after(0, lambda: self.estado.config(text=r))

        threading.Thread(target=correr, daemon=True).start()

    def probar_tts(self) -> None:
        """Dice una frase con la voz configurada."""
        import threading

        self.estado.config(text=tr("Hablando..."))

        def correr():
            try:
                from . import voice

                cfg = store.load_config()
                voice.speak("Hola, soy " + str(cfg.get("assistant_name", "Eve"))
                            + ". Si escuchas esto, la voz anda.", cfg)
                r = f"Listo. Voz: {cfg.get('tts_provider')} / {cfg.get('piper_voice') or '-'}"
            except Exception as exc:  # noqa: BLE001
                r = f"Fallo hablando: {type(exc).__name__}: {exc}"
            self.after(0, lambda: self.estado.config(text=r))

        threading.Thread(target=correr, daemon=True).start()

    def probar_overlay(self) -> None:
        """Hace aparecer el cartel unos segundos, este en el modo que este.

        Sirve para separar "el cartel esta mal configurado" de "el cartel no
        arranca": si aparece, el problema es cuando se muestra y no si existe.
        """
        from . import overlay

        cfg = store.load_config()
        overlay.asegurar(cfg)
        store.emitir_overlay({
            "estado": "hablando", "detalle": "PRUEBA DEL CARTEL", "nivel": 0.5,
            "titulo": str(cfg.get("assistant_name", "Eve")).upper(),
            "usuario": "probando el cartel", "eve": "Si ves esto, el cartel anda.",
        })
        self.estado.config(
            text=tr("Cartel mostrado unos segundos. Si no aparecio, revisa 'Cuando se ve' "
                 "y 'Pantalla' mas abajo."))

    def probar_tecla(self) -> None:
        """Espera a que aprietes una tecla y dice cual llego.

        Y dice tambien lo que NO prueba, que es la mitad importante: la tecla la
        escucha el asistente con un hook global desde otro proceso. Que este
        panel la reciba no garantiza que el asistente la reciba con un juego en
        primer plano, y hacer creer eso seria peor que no tener el boton.
        """
        vivo = store.latido()
        esperada = str(self.cfg.get("hotkey", ""))
        self.tecla_label.config(text=f"apreta '{esperada}' ahora...")

        def llego(evento):
            self.unbind("<Key>", ident)
            recibida = evento.keysym
            coincide = recibida.lower().replace("kp_", "") == esperada.lower().replace("num ", "")
            estado_asistente = ("el asistente esta corriendo" if vivo
                                else "OJO: el asistente NO esta corriendo, asi que "
                                     "aunque la tecla ande nadie la va a escuchar")
            if coincide:
                txt = f"llego '{recibida}', que es la configurada. {estado_asistente}."
            else:
                txt = (f"llego '{recibida}' y la configurada es '{esperada}'. "
                       f"Si es la que querias, ponla arriba. {estado_asistente}.")
            self.tecla_label.config(text=txt)
            return "break"

        ident = self.bind("<Key>", llego)
        self.focus_force()

    def probar_motor(self) -> None:
        """Le hace una pregunta trivial al motor configurado y muestra que dijo.

        Arma el MISMO motor que usa el asistente --`listener.armar_motor`-- y no
        una version simplificada: un boton que prueba otro camino puede decir que
        todo anda mientras el camino real esta roto.
        """
        self.motor_label.config(text=tr("preguntando..."))

        def trabajo():
            import time as _t

            try:
                from . import listener as lis

                cfg = store.load_config()
                arranque = _t.perf_counter()
                motor = lis.armar_motor(cfg)
                # Sin herramientas ni contexto: lo que se prueba es que la
                # conexion, la clave y el modelo existan, no que sepa razonar.
                respuesta = motor.ask("Responde solo con la palabra: listo")
                tardo = _t.perf_counter() - arranque
                corto = " ".join(str(respuesta).split())[:70]
                return (f"{cfg.get('engine')} contesto en {tardo:.1f}s: {corto!r}")
            except Exception as exc:  # noqa: BLE001 - el panel no puede morir
                return f"{type(exc).__name__}: {str(exc)[:150]}"

        def correr():
            r = trabajo()
            self._ui(lambda: self.motor_label.config(text=r))

        threading.Thread(target=correr, daemon=True).start()

    def probar_wake(self) -> None:
        """Abre el microfono unos segundos y dice si la puerta se habria abierto.

        Es la unica forma de probar la palabra clave sin dejar el microfono
        abierto todo el dia: se graba a mano, se le pasa el mismo recorte al
        mismo modelo de la puerta, y se dice que separo.
        """
        segundos = 4.0
        self.wake_label.config(text=f"di su nombre y una orden... ({int(segundos)}s)")
        self.update_idletasks()

        def trabajo():
            try:
                import time as _t

                from . import despertar, voice

                cfg = store.load_config()
                rec = voice.Recorder()
                rec.start()
                _t.sleep(segundos)
                audio = rec.stop()
                if audio.size < 1000:
                    return "no entro audio; el microfono puede estar tomado"
                orden = despertar.escuchado(audio, cfg)
                if orden is None:
                    texto = voice.transcribe(audio, cfg)
                    return (f"la puerta NO se abrio. Se escucho {texto!r}; la palabra "
                            f"tiene que ir al principio y ser una de "
                            f"{cfg.get('wake_palabra')!r}")
                if not orden:
                    return "se abrio, pero no quedo ninguna orden detras del nombre"
                return f"se abrio y quedo la orden: {orden!r}"
            except Exception as exc:  # noqa: BLE001
                return f"{type(exc).__name__}: {str(exc)[:150]}"

        def correr():
            r = trabajo()
            self._ui(lambda: self.wake_label.config(text=r))

        threading.Thread(target=correr, daemon=True).start()

    def probar_subtitulo(self) -> None:
        """Muestra un subtitulo de prueba.

        Es un camino distinto al del cartel --otra ventana, otro tamaño, otra
        cantidad de lineas-- asi que el boton del cartel no lo cubre: se puede
        ver el cartel perfecto y no leer nunca un subtitulo.
        """
        from . import overlay

        cfg = store.load_config()
        overlay.asegurar(cfg)
        store.emitir_overlay({
            "estado": "hablando", "detalle": "PRUEBA DE SUBTITULOS", "nivel": 0.4,
            "titulo": str(cfg.get("assistant_name", "Eve")).upper(),
            "usuario": "esto es lo que dijiste tu",
            "eve": "Y esto es lo que responde Eve. Si lees estas dos lineas, "
                   "los subtitulos andan.",
        })
        self.estado.config(
            text=tr("Subtitulo de prueba mostrado. Si no aparecio, revisa 'Que se muestra' "
                 "y los segundos en pantalla."))

    def probar_webhook(self) -> None:
        """Manda un mensaje de prueba al webhook de Discord.

        Una URL de webhook mal copiada no da ninguna señal: Eve dice que mando y
        el mensaje no llega a ningun lado. Esto es lo unico que lo separa.
        """
        # El webhook vive en el gestor de credenciales, no en el config: el
        # campo del panel muestra asteriscos mientras no lo reescribas. Se usa lo
        # que haya tipeado ahora si tipeo algo, y lo guardado si no.
        tipeado = str(self.key_vars.get("discord_webhook").get()
                      if "discord_webhook" in self.key_vars else "").strip()
        url = tipeado if tipeado and set(tipeado) != {"*"} else ""
        if not url:
            try:
                url = store.get_key("discord_webhook")
            except Exception:  # noqa: BLE001 - keyring puede no estar
                url = ""
        if not url:
            self.estado.config(text=tr("No hay webhook cargado."))
            return
        if not messagebox.askyesno(
            tr("Probar el webhook"),
            tr("Se manda un mensaje de prueba al canal de Discord de ese webhook.\n\n"
            "Lo van a ver todos los que esten en el canal.\n\nMandarlo?"),
        ):
            return
        self.estado.config(text=tr("mandando..."))

        def trabajo():
            try:
                import json as _j
                import urllib.request

                cuerpo = {"content": "Mensaje de prueba de Eve. Si lo lees, el webhook anda."}
                nombre = str(self.cfg.get("discord_username", "") or "")
                if nombre:
                    cuerpo["username"] = nombre
                avatar = str(self.cfg.get("discord_avatar", "") or "")
                if avatar:
                    cuerpo["avatar_url"] = avatar
                pedido = urllib.request.Request(
                    url, data=_j.dumps(cuerpo).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(pedido, timeout=15) as r:
                    return f"Mandado (HTTP {r.status}). Fijate en el canal."
            except Exception as exc:  # noqa: BLE001
                return f"No pude mandarlo: {type(exc).__name__}: {str(exc)[:120]}"

        def correr():
            r = trabajo()
            self._ui(lambda: self.estado.config(text=r))

        threading.Thread(target=correr, daemon=True).start()

    def gpu_probar(self):
        """Carga el modelo en la GPU y transcribe algo, en un hilo.

        Elegir 'cuda' en el desplegable no daba ninguna senal: si faltaba una
        DLL, Eve caia a CPU sola y en silencio, y la unica pista era que seguia
        tardando lo mismo. Esto contesta antes de hablarle.
        """
        self.gpu_label.config(text=tr("probando, puede tardar unos segundos..."))

        def work():
            texto = voice.probar_gpu(store.load_config())
            self._ui(lambda: self.gpu_label.config(text=texto))

        threading.Thread(target=work, daemon=True).start()

    # --- sesion de Claude Code ---------------------------------------------

    def refresh_auth(self):
        """Lee `claude auth status` en un hilo: el CLI tarda ~1s y congelaria la GUI."""
        self.auth_label.config(text=tr("consultando..."))

        def work():
            text = _auth_status()
            self._ui(lambda: self.auth_label.config(text=text))

        threading.Thread(target=work, daemon=True).start()

    def auth_login(self):
        if not shutil.which("claude"):
            messagebox.showerror(tr("Falta el CLI"), tr("No encontre 'claude' en el PATH."))
            return
        # Consola nueva: el login es interactivo (abre el navegador y espera).
        subprocess.Popen(["claude", "auth", "login"], creationflags=CREATE_NEW_CONSOLE)
        messagebox.showinfo(
            tr("Iniciar sesion"),
            tr("Se abrio una consola con el login de Claude Code.\n"
            "Cuando termines, toca 'Actualizar' para ver el estado."),
        )

    def auth_logout(self):
        if not messagebox.askyesno(
            tr("Cerrar sesion"),
            tr("Esto cierra tu sesion de Claude Code en toda la PC, no solo en Eve.\n\n"
            "El motor 'claude-code' va a dejar de funcionar hasta que vuelvas a entrar.\n\nSeguro?"),
        ):
            return
        r = plataforma.correr(["claude", "auth", "logout"], capture_output=True, text=True, timeout=60)
        messagebox.showinfo(tr("Cerrar sesion"), (r.stdout or r.stderr or "Sesion cerrada.").strip()[:500])
        self.refresh_auth()

    # --- guardar -----------------------------------------------------------

    def save(self, avisar: bool = True):
        # La base sale del DISCO, no de la foto que el panel tomo al abrirse.
        # Con el panel abierto, cambiar de perfil desde la bandeja escribia el
        # personaje en config.json y el primer Guardar lo revertia entero,
        # porque partia de lo que el panel tenia cargado de antes. Lo que el
        # usuario esta editando gana igual: se aplica encima, clave por clave.
        cfg = {**store.load_config(), **{k: v for k, v in self.cfg.items()
                                         if k not in store.DEFAULTS}}
        tocadas = []
        for key, var in self.vars.items():
            value = var.get()
            # Si el widget sigue mostrando lo mismo que cuando el panel leyo la
            # config, el usuario NO toco ese campo: gana lo que haya en disco.
            # Sin esto, guardar cualquier cosa reescribia las noventa y pico de
            # claves con la foto vieja, y ahi se perdia el perfil que hubieras
            # cargado desde la bandeja mientras el panel estaba abierto.
            if key in self.cfg and str(value) == str(self.cfg[key]):
                continue
            tocadas.append(key)
            default = store.DEFAULTS.get(key)
            if default is None and key.startswith(modulos.PREFIJO):
                # Las claves de modulo se inventan en runtime, asi que no estan
                # en DEFAULTS y caerian todas a texto. El tipo lo declara el
                # tipo de modulo: sin esto una posicion se guardaria como "40" y
                # la cuenta siguiente sumaria cadenas.
                clase = modulos.tipo_de_clave(cfg, key)
                default = clase() if clase else None
            if isinstance(default, bool):
                cfg[key] = bool(value)
            elif isinstance(default, int):
                try:
                    cfg[key] = int(value)
                except ValueError:
                    messagebox.showerror(tr("Valor invalido"), f"'{key}' debe ser un numero entero.")
                    return
            elif isinstance(default, float):
                # Sin esta rama la velocidad se guardaba como texto: funcionaba
                # igual porque quien la lee la convierte, pero el tipo se iba
                # cambiando solo en cada guardado.
                try:
                    cfg[key] = float(str(value).replace(",", "."))
                except ValueError:
                    messagebox.showerror(tr("Valor invalido"), f"'{key}' debe ser un numero.")
                    return
            else:
                cfg[key] = value
        cfg["workdirs"] = [
            line.strip() for line in self.workdirs.get("1.0", "end").splitlines() if line.strip()
        ]
        if not cfg["workdirs"]:
            messagebox.showerror(
                tr("Rutas vacias"), tr("Necesitas al menos una ruta de trabajo permitida.")
            )
            return

        allow_all = self.perm_var.get() == PERM_ALL
        if allow_all and self.cfg.get("confirm_destructive", True):  # recien lo activa
            if not messagebox.askyesno(
                tr("Permitir todo"),
                tr("Eve va a ejecutar cualquier comando que decida, sin preguntarte:\n"
                "borrar carpetas, apagar la PC, modificar el registro.\n\n"
                "El reconocimiento de voz se equivoca, y en este modo un error de\n"
                "transcripcion se ejecuta directo.\n\n"
                "Queda registrado en la pestaña Acciones, pero nada lo va a frenar.\n\n"
                "Activar igual?"),
                icon="warning",
                default="no",
            ):
                self.perm_var.set(PERM_ASK)
                return
        cfg["confirm_destructive"] = not allow_all

        # Los addons se guardan como lista de nombres. Si estan todos tildados
        # se guarda vacio, que significa "todos": asi uno nuevo aparece solo en
        # vez de quedar apagado por no estar en una lista escrita antes.
        elegidos = [n for n, v in getattr(self, "addon_vars", {}).items() if v.get()]
        cfg["addons_activos"] = (
            "" if len(elegidos) == len(getattr(self, "addon_vars", {})) else ",".join(elegidos)
        )

        store.save_config(cfg)
        # Lo que cambiaste vos queda anotado: con `autoridad = usuario`, Eve no
        # lo pisa despues. Va tras guardar para no anotar algo que no se escribio.
        store.marcar_tocadas(tocadas)
        # Los widgets y self.cfg tienen que quedar iguales a lo que se acaba de
        # escribir. Si no, el guardado siguiente ve que un widget difiere de
        # self.cfg, lo toma como "el usuario lo edito" y lo escribe encima: bastaba
        # con guardar dos veces para revertir el perfil que se habia cargado.
        self.cfg = cfg
        self._visto = self._mtimes()
        for clave, var in self.vars.items():
            if clave in cfg:
                try:
                    var.set(cfg[clave] if isinstance(var, tk.BooleanVar) else str(cfg[clave]))
                except tk.TclError:
                    pass

        for provider, var in self.key_vars.items():
            value = var.get()
            if not value or set(value) == {"*"}:  # sin cambios: no tocar
                continue
            if provider == "gmail" and not _parece_app_password(value):
                if not messagebox.askyesno(
                    tr("Eso no parece una app password"),
                    "Las contrasenas de aplicacion de Google son 16 letras minusculas\n"
                    "(se muestran en 4 grupos de 4).\n\n"
                    f"Lo que pusiste tiene {len(value.replace(' ', ''))} caracteres.\n\n"
                    "Si es la contrasena normal de tu cuenta, Google la va a rechazar por\n"
                    "IMAP y ademas quedaria guardada en tu PC sin necesidad.\n\n"
                    "Guardar igual?",
                    icon="warning",
                    default="no",
                ):
                    continue
                value = value.replace(" ", "")
            store.set_key(provider, value.replace(" ", "") if provider == "gmail" else value)
        self.cfg = cfg
        if avisar:
            messagebox.showinfo(
                tr("Guardado"),
                tr("Configuracion guardada.\n\nSi el listener esta corriendo, aplica los\n"
                "cambios solo en unos segundos. Los de aspecto no le cortan la\n"
                "conversacion; los de motor o tecla si lo rearman."),
            )
        # Los `return` de arriba salen sin escribir nada. Quien necesita saber si
        # de verdad se guardo --cambiar el idioma reabre el panel-- mira esto.
        return True


if __name__ == "__main__":
    Panel().mainloop()
