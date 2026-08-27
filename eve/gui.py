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
# Los colores NO se escriben aca. Vivian tres constantes --#666666,
# #c0392b, #1e8449-- y el problema no era cual: era que no seguian a la
# paleta, asi que con un tema oscuro la ayuda quedaba en 3.29:1. Ahora los
# estilos salen de `tema.resolver`, que es lo unico que pasa por el piso de
# contraste. Ver `tema.PISOS`.

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
        # Las tarjetas dibujadas, para poder repintarlas al cambiar de tema:
        # un Canvas no consulta el motor de estilos de ttk, hay que avisarle.
        self._tarjetas: list = []
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
        # 980 y no 900: el pie gano el boton de revisar el listener y a 900 el
        # ultimo quedaba cortado. Se conto sobre una captura del binario.
        self.geometry("980x820")
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
        # Al lado, porque son las dos cosas que uno quiere ABRIR desde aca. La
        # linea de estado de arriba ya decia si el asistente corre, pero decirlo
        # y no poder hacer nada al respecto es la mitad inutil: si estaba
        # detenido habia que ir a buscar el acceso directo.
        self.boton_listener = ttk.Button(
            fila, text=tr("Revisar listener"), command=self._revisar_listener)
        self.boton_listener.pack(side="left", padx=(6, 0))
        # Al lado del boton de actualizar, que es donde uno se pregunta "cual
        # tengo?". Sin esto habia que abrir una terminal y correr --version.
        from eve import __version__

        ttk.Label(fila, text=f"v{__version__}", style="Ayuda.TLabel").pack(
            side="right", padx=(0, 10)
        )
        self.after(300, self._refrescar_estado)

        self.vars: dict[str, tk.Variable] = {}
        self._barra_superior(self)

        # Nueve pestañas agrupadas por lo que uno viene a hacer, no por
        # modulo. El rotulo traducido va aca, con el texto LITERAL adentro de
        # `tr(...)`: con una variable el chequeo de traduccion no lo ve.
        pestanas = (
            ("General", tr("General"), self._tab_general),
            ("Modelos", tr("Modelos y claves"), self._tab_modelos),
            ("Cuentas", tr("Cuentas"), self._tab_cuentas),
            ("Comandos", tr("Comandos"), self._tab_comandos),
            ("Voz", tr("Voz"), self._tab_voz),
            ("Contactos", tr("Contactos"), self._tab_contactos),
            ("Addons", tr("Addons"), self._tab_addons),
            ("Apariencia", tr("Apariencia"), self._tab_apariencia),
            ("Actividad", tr("Actividad"), self._tab_actividad),
        )

        # Barra lateral o pestañas. Las dos arman los MISMOS marcos y los
        # guardan en `self._tabs`: lo unico que cambia es quien los muestra.
        # Asi el buscador --que salta a una pestaña, abre una seccion y corre
        # el scroll-- sigue funcionando igual por los dos caminos.
        self._riel = None
        nb = None
        if self._con_riel():
            from . import chrome, tema as tema_mod

            fila = ttk.Frame(self, style="Fondo.TFrame")
            fila.pack(side="top", fill="both", expand=True, padx=(10, 10), pady=(6, 6))
            self._riel = chrome.Riel(
                fila, tema_mod.resolver(self.cfg, "ui"),
                [(clave, rotulo) for clave, rotulo, _a in pestanas],
                self.mostrar_pestana, ancho=178)
            self._riel.pack(side="left", fill="y", padx=(0, 10))
            padre_tabs = self._area = ttk.Frame(fila, style="Fondo.TFrame")
            self._area.pack(side="left", fill="both", expand=True)
        else:
            nb = ttk.Notebook(self)
            nb.pack(side="top", fill="both", expand=True, padx=10, pady=(6, 6))
            padre_tabs = nb
        self._nb = nb
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
        # En un bucle y no en siete lineas para que el titulo quede asociado a
        # la pestaña: es lo que el buscador necesita para saltar hasta ella.
        for titulo, rotulo, armar in pestanas:
            self._ctx_pestana, self._ctx_sub = titulo, ""
            self._ctx_pestana_rot, self._ctx_sub_rot = rotulo, ""
            self._ctx_seccion, self._ctx_abrir = "", None
            marco = armar(padre_tabs)
            if nb is not None:
                nb.add(marco, text=f"  {rotulo}  ")
            self._tabs[titulo] = marco
        if self._riel is not None:
            self.mostrar_pestana("General")
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
        # El cuerpo sale de la escala y no de un numero puesto aca. Subio de
        # 9 a 10 puntos: 9pt de Segoe UI son ~12px, chico para una ayuda de
        # tres renglones, y las HIG piden que el cuerpo sea comodo antes que
        # denso. Los otros pasos se cuentan DESDE este, asi que sube todo junto.
        familia = "Segoe UI" if plataforma.WINDOWS else "Helvetica"
        base = (familia, tema_mod.CUERPO if plataforma.WINDOWS else tema_mod.CUERPO + 1)
        self.option_add("*Font", base)
        # Los colores de texto salen de la paleta incluso SIN pintar el panel:
        # el tema nativo de Windows ignora los fondos que uno le pone, pero el
        # color de la letra si lo respeta. Cuando no se pinta, la referencia es
        # la paleta clara, porque el tema `vista` dibuja claro sea cual sea el
        # tema del cartel --y un `texto_tenue` oscuro sobre el gris del sistema
        # es justo el caso que fallaba al reves.
        pal = tema_mod.resolver(self.cfg, "ui") if pintar else tema_mod.PALETAS["claro"]
        s.configure("Titulo.TLabel", font=(base[0], tema_mod.pt("titulo", base[1]), "bold"))
        s.configure("Ayuda.TLabel", foreground=pal["texto_tenue"])
        s.configure("Error.TLabel", foreground=pal["alerta"])
        s.configure("Ok.TLabel", foreground=pal["acento"])
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
        s.configure("Titulo.TLabel", font=(base[0], tema_mod.pt("titulo", base[1]), "bold"))
        s.configure("Seccion.TLabelframe.Label", font=(base[0], base[1], "bold"))
        s.configure("Seccion.TButton", anchor="w", padding=(8, 6), relief="flat",
                    font=(base[0], base[1], "bold"))
        self.configure(background=paleta["fondo"])
        # Y lo que no pasa por ttk.Style se recorre a mano.
        tema_mod.repintar_tk(self, paleta)
        # Las tarjetas son Canvas, y un Canvas no consulta el motor de estilos:
        # sin esto el tema cambia en vivo en todo menos en el marco dibujado,
        # que es justo lo que mas se nota.
        if getattr(self, "_riel", None) is not None:
            try:
                self._riel.aplicar(paleta)
            except tk.TclError:
                pass
        for tarjeta in list(self._tarjetas):
            try:
                tarjeta.aplicar(paleta)
            except tk.TclError:
                self._tarjetas.remove(tarjeta)

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
        # `Fondo.TFrame`: es el color de la PAGINA, lo que se ve entre una
        # tarjeta y la siguiente. El default de los widgets es `panel`, porque
        # casi todos viven adentro de una tarjeta; los pocos contenedores
        # estructurales como este lo piden explicito.
        dentro = ttk.Frame(lienzo, style="Fondo.TFrame")
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
                # La mayoria de las Salidas las llena un boton de prueba, pero
                # algunas tienen algo que decir apenas se abre el panel. Un
                # gancho generico por nombre y no un `if` por atributo: si no,
                # el pintor del registro empieza a conocer casos particulares.
                inicial = getattr(self, "_texto_" + item.atributo, None)
                if inicial:
                    try:
                        etiqueta.config(text=inicial())
                    except Exception:  # noqa: BLE001 - abrir el panel no puede
                        pass           # fallar porque una etiqueta no se llene
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

    def _atajos_de_forma(self, padre) -> None:
        """El desplegable de formas: no guarda una clave, LLENA otras cuatro.

        Excepcion declarada: elegir "hexagono" escribe lados, giro y redondeo de
        un saque. No tiene clave propia, asi que no es una fila.
        """
        fila = ttk.Frame(padre)
        fila.pack(fill="x", padx=12, pady=(4, 8))
        ttk.Label(fila, text=tr("Formas"), width=24).pack(side="left")
        self.forma_var = tk.StringVar()
        combo = ttk.Combobox(fila, textvariable=self.forma_var,
                             values=sorted(overlay_formas()), state="readonly")
        combo.pack(side="left", fill="x", expand=True)
        combo.bind("<<ComboboxSelected>>", self._forma_elegida)

    def _previa_primera_vez(self, _padre) -> None:
        """Dibuja la vista previa una vez, ya con todos los campos puestos."""
        self._previa_redibujar()

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

    def _skills_lista(self, padre) -> None:
        """La lista de skills con Importar y Quitar.

        No es un `Campo` porque no hay una clave que editar: lo que se maneja
        son archivos en una carpeta. Mismo caso que las voces propias.
        """
        from . import skills as mod_skills

        caja = ttk.Frame(padre)
        caja.pack(fill="x", padx=12, pady=(6, 2))
        self.skills_lista = tk.Listbox(caja, height=4, exportselection=False)
        self.skills_lista.pack(side="left", fill="x", expand=True)
        barra = ttk.Frame(caja)
        barra.pack(side="left", padx=(8, 0))
        ttk.Button(barra, text=tr("Importar skill..."),
                   command=self.skill_importar).pack(fill="x")
        ttk.Button(barra, text=tr("Quitar"),
                   command=self.skill_quitar).pack(fill="x", pady=(4, 0))

        def refrescar():
            self.skills_lista.delete(0, "end")
            for nombre, renglon in mod_skills.resumen():
                self.skills_lista.insert(
                    "end", f"{nombre}   {renglon}" if renglon else nombre)
            if not mod_skills.instaladas():
                self.skills_lista.insert("end", tr("(ninguna todavia)"))

        self._skills_refrescar = refrescar
        refrescar()

    def skill_importar(self) -> None:
        from tkinter import filedialog

        from . import skills as mod_skills

        ruta = filedialog.askopenfilename(
            title=tr("Elegi el .md de la skill"), parent=self,
            filetypes=[(tr("Texto"), "*.md *.markdown *.txt"), (tr("Todos"), "*.*")],
        )
        if not ruta:
            return
        try:
            mod_skills.importar(ruta)
        except ValueError as exc:
            messagebox.showerror(tr("Skills"), str(exc))
            return
        except OSError as exc:
            messagebox.showerror(tr("Skills"), f"{tr('no pude copiarla')}: {exc}")
            return
        self._skills_refrescar()

    def skill_quitar(self) -> None:
        from . import skills as mod_skills

        sel = self.skills_lista.curselection()
        instaladas = mod_skills.instaladas()
        if not sel or sel[0] >= len(instaladas):
            return
        nombre = instaladas[sel[0]]
        if not messagebox.askyesno(tr("Skills"), f"{tr('Borrar')} {nombre}?"):
            return
        mod_skills.borrar(nombre)
        self._skills_refrescar()

    # Los tres motores que no son `compat`. El resto sale de
    # `compat_engine.PROVEEDORES`, para que agregar uno alla lo muestre aca
    # sin tocar nada: la lista anterior habria que acordarse de actualizarla.
    MOTORES_PROPIOS = (
        ("api", "Anthropic", "api", "anthropic", "la nube - Messages API"),
        ("claude-code", "Claude Code", "claude-code", "", "tu suscripcion, sin clave"),
        ("ollama", "Ollama", "ollama", "", "tu maquina - localhost:11434"),
    )

    # Como se escribe cada uno. La clave del diccionario es un identificador
    # --`lmstudio`, `xai`-- y mostrarlo crudo al lado de "Claude Code" queda
    # como si faltara terminarlo. Lo que no este aca sale con su id, que es
    # mejor que no salir.
    NOMBRE_PROVEEDOR = {
        "gemini": "Gemini", "openai": "OpenAI", "groq": "Groq",
        "deepseek": "DeepSeek", "openrouter": "OpenRouter", "xai": "xAI",
        "lmstudio": "LM Studio", "omniroute": "OmniRoute",
        "propio": "Otro servidor",
    }

    def catalogo_proveedores(self) -> list:
        """(id, rotulo, engine, clave, donde) de todo lo que puede pensar.

        Publico porque el test lo recorre: lo que importa es que la lista salga
        de `PROVEEDORES` y no de una copia escrita a mano al lado.
        """
        from . import compat_engine as ce

        salida = list(self.MOTORES_PROPIOS)
        for nombre, (url, clave, _modelo) in ce.PROVEEDORES.items():
            donde = ("tu maquina" if url.startswith("http://localhost")
                     else "la nube")
            if nombre == "propio":
                # No es un proveedor: es "poneme vos la URL". Se queda, pero
                # dicho como lo que es.
                donde = "el servidor que le pongas abajo"
            salida.append((nombre, self.NOMBRE_PROVEEDOR.get(nombre, nombre),
                           "compat", clave, donde))
        return salida

    def _selector_proveedor(self, padre) -> None:
        """Quien piensa por ella: uno solo, elegido de una lista.

        Antes eran DOS controles --`engine`, y si decias `compat`, tambien
        `compat_proveedor`-- y estaban en secciones distintas. Peor: el panel
        mostraba nueve campos de clave uno abajo del otro sin ninguna señal de
        cual estaba en uso.

        Las claves SIEMPRE fueron mutuamente excluyentes --`brain` lee la de
        Anthropic y `compat_engine` lee la del proveedor elegido, nunca hay dos
        en juego-- asi que esto no cambia el comportamiento: hace visible el
        que ya habia. El listener tampoco cambia; sigue leyendo las mismas dos
        claves que este control escribe.
        """
        engine = tk.StringVar(value=str(self.cfg.get("engine", "api")))
        prov = tk.StringVar(value=str(self.cfg.get("compat_proveedor", "")))
        self.vars["engine"] = engine
        self.vars["compat_proveedor"] = prov

        cat = self.catalogo_proveedores()
        actual = engine.get()
        if actual == "compat":
            elegido = prov.get() or cat[3][0]
        else:
            elegido = actual
        self._prov_var = tk.StringVar(value=elegido)

        for ident, rotulo, _motor, clave, donde in cat:
            fila = ttk.Frame(padre)
            fila.pack(fill="x", padx=12, pady=1)
            ttk.Radiobutton(fila, text=rotulo, value=ident,
                            variable=self._prov_var,
                            command=self._selector_aplicar,
                            width=16).pack(side="left")
            ttk.Label(fila, text=donde, style="Ayuda.TLabel").pack(side="left")
            ttk.Label(fila, text=self._estado_clave(clave),
                      style="Ayuda.TLabel").pack(side="right")

        self.prov_label = ttk.Label(padre, text="", style="Ayuda.TLabel",
                                    justify="left")
        self.prov_label.pack(anchor="w", padx=12, pady=(8, 2))
        self._prov_estado()

    def _selector_aplicar(self) -> None:
        """Escribe las DOS claves de una. Es el punto del control.

        Metodo y no una funcion adentro de `_selector_proveedor` para que el
        test pueda elegir un proveedor y comprobar que quedaron escritas las
        dos: un `command=` que solo existe atado a un widget se prueba
        haciendo clics, y eso no se puede automatizar.
        """
        quien = self._prov_var.get()
        for ident, _rot, motor, _clave, _donde in self.catalogo_proveedores():
            if ident != quien:
                continue
            self.vars["engine"].set(motor)
            # Solo tiene sentido con `compat`; con los otros se deja lo que
            # habia, para no perderle la eleccion si despues vuelve.
            if motor == "compat":
                self.vars["compat_proveedor"].set(ident)
            break
        self._prov_estado()

    def _estado_clave(self, clave: str) -> str:
        if not clave:
            return tr("no necesita clave")
        try:
            return tr("clave cargada") if store.get_key(clave) else tr("sin clave")
        except Exception:  # noqa: BLE001 - keyring puede no estar
            return ""

    def _prov_estado(self) -> None:
        """Que quedaria escrito, dicho con las claves de verdad.

        Se muestra el par y no un "listo": lo que el usuario tiene que poder
        creer es que esto escribe la config, no que alguien adivino por el.
        """
        quien = self._prov_var.get()
        motor = self.vars["engine"].get()
        par = f"engine={motor}"
        if motor == "compat":
            par += f"   compat_proveedor={quien}"
        faltan = [c for i, _r, _m, c, _d in self.catalogo_proveedores()
                  if i == quien and c and not self._tiene_clave(c)]
        aviso = ""
        if faltan:
            aviso = "   " + tr("falta la clave, cargala abajo")
        self.prov_label.config(text=par + aviso)

    def _tiene_clave(self, clave: str) -> bool:
        try:
            return bool(store.get_key(clave))
        except Exception:  # noqa: BLE001 - keyring puede no estar
            return False

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
        if self._con_tarjetas():
            from . import chrome, tema as tema_mod

            tarjeta = chrome.Tarjeta(padre, tema_mod.resolver(self.cfg, "ui"))
            tarjeta.pack(fill="x", padx=(0, PAD), pady=(0, 10))
            self._tarjetas.append(tarjeta)
            caja = tarjeta.cuerpo
        else:
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

    def _con_riel(self) -> bool:
        """Si la navegacion va por barra lateral en vez de pestañas."""
        return str(self.cfg.get("ui_nav", "lateral")) == "lateral"

    def rotulos_navegacion(self) -> list:
        """Los rotulos de las siete secciones, como se ven en pantalla.

        Existe porque hay dos navegaciones --barra lateral y pestañas-- y quien
        quiere saber que dice la interfaz no tiene por que saber cual esta
        puesta. Sin esto, el chequeo de traduccion leia el Notebook a mano y se
        caia el dia que el Notebook dejo de existir.
        """
        if self._nb is not None:
            return [self._nb.tab(i, "text").strip()
                    for i in range(self._nb.index("end"))]
        if self._riel is not None:
            return [rotulo for _clave, rotulo in self._riel.items]
        return []

    def mostrar_pestana(self, clave: str) -> None:
        """Deja a la vista la pestaña pedida. Sirve por los dos caminos.

        Con pestañas delega en el Notebook; con barra lateral empaqueta el
        marco que toca y esconde los demas. Es UN metodo y no dos porque el
        buscador salta a una pestaña sin saber ni tener que saber como se
        dibuja la navegacion.
        """
        marco = self._tabs.get(clave)
        if marco is None:
            return
        if self._nb is not None:
            self._nb.select(marco)
            return
        for titulo, otro in self._tabs.items():
            if titulo == clave:
                otro.pack(fill="both", expand=True)
            else:
                otro.pack_forget()
        if self._riel is not None and self._riel.elegido != clave:
            self._riel.elegido = clave
            self._riel.pintar()

    def _con_tarjetas(self) -> bool:
        """Si las secciones van en tarjeta dibujada.

        Pide el panel pintado: sin eso los widgets los dibuja el sistema con su
        propio gris y una tarjeta de color debajo se ve como un error, no como
        un diseno.
        """
        from . import tema as tema_mod

        return (tema_mod.pinta_panel(self.cfg)
                and str(self.cfg.get("ui_cromo", "tarjeta")) == "tarjeta")

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

    def _borde(self) -> str:
        """El color de contorno de la paleta puesta. Ver `_tenue`."""
        from . import tema as tema_mod

        if not tema_mod.pinta_panel(self.cfg):
            return tema_mod.PALETAS["claro"]["borde"]
        return tema_mod.resolver(self.cfg, "ui")["borde"]

    def _tenue(self) -> str:
        """El color de lo secundario, siguiendo la paleta que este puesta.

        Hace falta como funcion --y no como constante-- porque el tema se
        cambia en vivo desde el propio panel: una constante quedaria del tema
        anterior hasta reabrir la ventana.
        """
        from . import tema as tema_mod

        if not tema_mod.pinta_panel(self.cfg):
            return tema_mod.PALETAS["claro"]["texto_tenue"]
        return tema_mod.resolver(self.cfg, "ui")["texto_tenue"]

    def _pista_buscador(self) -> None:
        self.buscar_var.set(self._pista())
        self.buscar_entry.config(foreground=self._tenue())

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
                self.mostrar_pestana(entrada["pestana"])
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

    def _tab_modelos(self, nb):
        return self._componer(
            nb, tr("Modelos y claves"),
            tr("Cual piensa, cual te escucha, cual te habla, y la clave de cada uno."),
            [self._bloque_modelos, self._bloque_claves_ia],
        )

    def _bloque_modelos(self, nb):
        """Generado desde `registro.MODELOS`."""
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.MODELOS)
        return t

    def _tab_comandos(self, nb):
        return self._componer(
            nb, tr("Comandos"),
            tr("Frases tuyas que hacen algo fijo, sin pasar por el modelo."),
            [self._bloque_comandos],
        )

    def _bloque_comandos(self, nb):
        """Generado desde `registro.COMANDOS`."""
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.COMANDOS)
        return t

    def _comandos_lista(self, padre) -> None:
        """Lo que dice Comandos.md, y el freno de los que corren algo.

        La lista se lee del archivo cada vez que se refresca en vez de
        guardarse en la config: el archivo es la fuente, y tener una copia al
        lado es garantizar que un dia digan cosas distintas.
        """
        from . import comandos as mod

        # Los rotulos con el texto LITERAL adentro de `tr(...)`: escribirlos
        # como `tr(c.capitalize())` los deja invisibles para el chequeo de
        # traduccion, que es como este panel ya mostro tres textos en español
        # estando en ingles.
        columnas = (("frase", tr("Frase"), 200), ("tipo", tr("Tipo"), 70),
                    ("hace", tr("Hace"), 300), ("estado", tr("Estado"), 110))
        cols = tuple(c for c, _r, _a in columnas)
        self.cmd_tree = ttk.Treeview(padre, columns=cols, show="headings",
                                     height=7)
        for c, rotulo, ancho in columnas:
            self.cmd_tree.heading(c, text=rotulo)
            self.cmd_tree.column(c, width=ancho, anchor="w")
        self.cmd_tree.pack(fill="x", padx=12, pady=(6, 4))

        barra = ttk.Frame(padre)
        barra.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(barra, text=tr("Abrir Comandos.md"),
                   command=self.comando_abrir_archivo).pack(side="left")
        ttk.Button(barra, text=tr("Recargar"),
                   command=lambda: self._comandos_refrescar()).pack(side="left", padx=6)
        ttk.Button(barra, text=tr("Revisar y aprobar"),
                   command=self.comando_aprobar).pack(side="left")
        ttk.Button(barra, text=tr("Probar"),
                   command=self.comando_probar).pack(side="left", padx=6)
        self.cmd_estado = ttk.Label(padre, text="", style="Ayuda.TLabel",
                                    justify="left")
        self.cmd_estado.pack(anchor="w", padx=12, pady=(2, 6))

        def refrescar():
            self.cmd_tree.delete(*self.cmd_tree.get_children())
            self._cmd_filas = mod.leer()
            for c in self._cmd_filas:
                if c["tipo"] == "sistema":
                    estado = (tr("aprobado") if mod.aprobado(c, self.cfg)
                              else tr("SIN APROBAR"))
                else:
                    estado = tr("sin riesgo")
                self.cmd_tree.insert("", "end", values=(
                    " | ".join(c["frases"]), c["tipo"], c["valor"][:80], estado))
            faltan = len([c for c in self._cmd_filas
                          if c["tipo"] == "sistema" and not mod.aprobado(c, self.cfg)])
            if not self._cmd_filas:
                self.cmd_estado.config(text=tr("Todavia no hay comandos. Abri el archivo y escribi uno."))
            elif faltan:
                self.cmd_estado.config(
                    text=f"{faltan} {tr('sin aprobar: esas frases no hacen nada todavia.')}")
            else:
                self.cmd_estado.config(text=tr("Todos listos."))

        self._comandos_refrescar = refrescar
        refrescar()

    def _comando_elegido(self):
        sel = self.cmd_tree.selection()
        if not sel:
            return None
        i = self.cmd_tree.index(sel[0])
        filas = getattr(self, "_cmd_filas", [])
        return filas[i] if i < len(filas) else None

    def comando_abrir_archivo(self) -> None:
        from . import comandos as mod, plataforma

        plataforma.abrir(mod.asegurar_archivo())

    def comando_aprobar(self) -> None:
        """Aprueba el comando elegido, mostrandolo entero primero.

        Se muestra ANTES de aprobar y no despues: aprobar a ciegas seria el
        mismo agujero que aprobar un addon sin leerlo. Y la aprobacion es del
        TEXTO --por hash-- asi que editarlo despues lo vuelve a frenar.
        """
        from . import comandos as mod

        cmd = self._comando_elegido()
        if cmd is None:
            messagebox.showinfo(tr("Comandos"), tr("Elegi uno de la lista."))
            return
        if cmd["tipo"] != "sistema":
            messagebox.showinfo(tr("Comandos"),
                                tr("Ese no corre nada: no hace falta aprobarlo."))
            return
        ok = messagebox.askyesno(
            tr("Comandos"),
            f"{tr('Al decir')} \"{cmd['frases'][0]}\" {tr('se va a correr')}:\n\n"
            f"{cmd['valor']}\n\n{tr('Lo apruebo?')}")
        if not ok:
            store.log_action("comandos", "aprobar", f"DENEGADO {cmd['frases'][0]}")
            return
        mod.aprobar(cmd)
        self.cfg = store.load_config()
        self._comandos_refrescar()

    def comando_probar(self) -> None:
        """Lo corre ahora, sin tener que decirlo en voz alta."""
        from . import comandos as mod

        cmd = self._comando_elegido()
        if cmd is None:
            messagebox.showinfo(tr("Comandos"), tr("Elegi uno de la lista."))
            return
        que, dato = mod.ejecutar(cmd, self.cfg)
        if que == "prompt":
            dato = f"{tr('le mandaria al modelo')}: {dato}"
        self.cmd_estado.config(text=str(dato)[:300])

    def _tab_cuentas(self, nb):
        return self._componer(
            nb, tr("Cuentas"),
            tr("Las apps a las que Eve le escribe. Todo opcional."),
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
        # `Fondo.TFrame`: es el color de la PAGINA, lo que se ve entre una
        # tarjeta y la siguiente. El default de los widgets es `panel`, porque
        # casi todos viven adentro de una tarjeta; los pocos contenedores
        # estructurales como este lo piden explicito.
        dentro = ttk.Frame(lienzo, style="Fondo.TFrame")
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
        self._galeria_perfiles(caja)
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

    # % del tamaño real del cartel. Sale de una cuenta y no de probar: la
    # ventana abre en 900, la barra lateral se lleva 178, los margenes de la
    # tarjeta y el scroll ~60, asi que quedan ~660 para tres columnas con 10 de
    # separacion -> 200 cada una. A 46% el cartel mide 211 y la tercera columna
    # se cortaba; a 40% mide 184 y entra con aire.
    ESCALA_MUESTRA = 40

    def _galeria_perfiles(self, padre) -> None:
        """Los ocho perfiles que vienen, dibujados como se van a ver.

        Hasta ahora se llegaba a ellos por Importar y un dialogo de archivos:
        habia que saber que existian, donde estaban, y abrirlos de a uno para
        ver cual era cual. Un tema que no se puede ver antes de aplicarlo no se
        elige, se sortea.

        Cada muestra la dibuja **el mismo `overlay.Pintor` que el cartel de
        verdad**, con la escala bajada. No es una imagen de promocion que
        alguien tiene que acordarse de regenerar: si el dibujo del cartel
        cambia, las muestras cambian con el. Es lo mismo que ya hace la vista
        previa de Apariencia.
        """
        from . import overlay as ov
        from . import tema as tema_mod

        ejemplos = store.perfiles_de_ejemplo()
        if not ejemplos:
            return
        self._muestras: dict = {}
        rejilla = ttk.Frame(padre)
        rejilla.pack(fill="x", padx=12, pady=(8, 2))
        # Tres y no cuatro: la barra lateral se lleva 178 px del ancho, y con
        # cuatro la ultima columna quedaba cortada por el borde de la tarjeta.
        # Se conto sobre la captura, no a ojo.
        por_fila = 3
        ancho = int(ov.ANCHO * self.ESCALA_MUESTRA / 100)
        alto = int(ov.ALTO * self.ESCALA_MUESTRA / 100)

        for i, (nombre, propio) in enumerate(sorted(ejemplos.items())):
            fila, col = divmod(i, por_fila)
            celda = ttk.Frame(rejilla)
            celda.grid(row=fila, column=col, padx=(0, 10), pady=(0, 10), sticky="w")

            cfg = {**store.DEFAULTS, **propio}
            cfg["hud_escala"] = self.ESCALA_MUESTRA
            lienzo = tk.Canvas(celda, width=ancho, height=alto,
                               highlightthickness=0, borderwidth=0)
            # `_eve_color_propio`: la muestra ES el color del perfil, y el
            # repintado del tema la dejaria del color del panel, o sea todas
            # iguales -- que es lo contrario de para lo que esta.
            lienzo._eve_color_propio = True
            lienzo.pack()
            try:
                paleta = tema_mod.resolver(cfg, "hud")
                lienzo.configure(background=paleta["fondo"])
                pintor = ov.Pintor(cfg, paleta)
                pintor.pintar(lienzo, "escuchando",
                              cfg.get("hud_titulo") or nombre,
                              cfg.get("hud_subtitulo") or "")
            except Exception as exc:  # noqa: BLE001 - un perfil roto no tumba el panel
                lienzo.create_text(ancho / 2, alto / 2, text=str(exc)[:40],
                                   fill=tema_mod.PALETAS["oscuro"]["alerta"])

            rotulo = ttk.Label(celda, text=nombre, style="Ayuda.TLabel")
            rotulo.pack(anchor="w", pady=(3, 0))
            self._muestras[nombre] = (lienzo, propio)
            for w in (lienzo, rotulo):
                w.bind("<Button-1>",
                       lambda _e, n=nombre: self._elegir_muestra(n))
                w.bind("<Double-Button-1>",
                       lambda _e, n=nombre: self._aplicar_muestra(n))

        self._ayuda(padre, tr(
            "Un clic para elegirlo, dos para aplicarlo. Vienen con el programa y no\n"
            "se borran: guardar uno propio con el mismo nombre no los pisa."))

    def _elegir_muestra(self, nombre: str) -> None:
        """Deja el nombre puesto en el combo, sin aplicar nada todavia."""
        if hasattr(self, "perfil_var"):
            self.perfil_var.set(nombre)
        self.estado.config(text=f"{tr('elegido')}: {nombre}", style="Ayuda.TLabel")

    def _aplicar_muestra(self, nombre: str) -> None:
        """Aplica un perfil de ejemplo sin tener que importarlo primero.

        Se guarda con su nombre antes de aplicarlo: asi queda en la lista de
        los tuyos y se puede volver a el, en vez de ser algo que se aplico una
        vez y no se sabe como recuperar.
        """
        propio = dict(self._muestras.get(nombre, (None, {}))[1])
        if not propio:
            return
        # Primero se guarda como uno tuyo y despues se delega en `_perfil_cargar`,
        # que es el camino que ya existe: pide confirmacion, aplica y cierra el
        # panel para que vuelva a armarse con el tema nuevo. Escribir aca un
        # segundo camino que aplique distinto es como se terminan teniendo dos
        # comportamientos para lo mismo.
        store.guardar_perfil(nombre, {**store.load_config(), **propio})
        if hasattr(self, "perfil_combo"):
            self.perfil_combo.config(values=sorted(store.listar_perfiles()))
        if hasattr(self, "perfil_var"):
            self.perfil_var.set(nombre)
        self._perfil_cargar()

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


    def _bloque_claves_ia(self, nb):
        """La sesion de Claude Code y las claves de los proveedores de modelo.

        Se separo de `_bloque_claves` --que se quedo con las de apps: Discord,
        el correo-- porque son dos cosas distintas con el mismo nombre. Estas
        habilitan al que PIENSA, escucha o habla, asi que viven al lado del
        selector de modelo; las otras habilitan a quien Eve le escribe.
        """
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
            ("omniroute", "OmniRoute: la clave que emite su propio panel"),
        ]:
            self._campo_clave(t, provider, label)

        return t

    def _bloque_claves(self, nb):
        """Las claves de las apps a las que Eve le escribe. Ver `_bloque_claves_ia`."""
        t = ttk.Frame(nb)
        box = self._seccion(t, tr("Conexiones con apps (todas opcionales)"))
        ttk.Label(
            box,
            text=tr("Sin esto Eve igual abre WhatsApp, Discord, Telegram y el mail con el\n"
            "mensaje escrito, para que lo mandes tu. Estas claves solo agregan leer\n"
            "y enviar sin pasar por la app."),
            style="Ayuda.TLabel",
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
            style="Ayuda.TLabel",
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
            style="Ayuda.TLabel",
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
            style="Ayuda.TLabel",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        barra = ttk.Frame(t)
        barra.pack(fill="x", padx=12)
        ttk.Label(barra, text=tr("Idioma")).pack(side="left")
        self.voz_idioma = tk.StringVar(value="Spanish")
        self.voz_combo = ttk.Combobox(barra, textvariable=self.voz_idioma, width=22, state="readonly")
        self.voz_combo.pack(side="left", padx=6)
        ttk.Button(barra, text=tr("Buscar"), command=self.voces_buscar).pack(side="left")
        ttk.Button(barra, text=tr("Importar voz..."),
                   command=self.voz_importar).pack(side="left", padx=6)
        self.voz_estado = ttk.Label(barra, text="", style="Ayuda.TLabel")
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

    def compat_buscar_modelos(self):
        """Le pregunta al servicio que modelos tiene y te deja elegir uno.

        En un hilo porque sale a la red: OpenRouter tarda lo que tarde, y el
        panel no puede quedarse congelado mientras tanto. Lo que vuelve se
        aplica con `_ui`, que es el unico camino seguro para tocar tkinter
        desde un worker.
        """
        import threading

        from . import compat_engine

        rotulo = getattr(self, "compat_estado", None)

        def decir(texto):
            if rotulo is not None:
                try:
                    rotulo.config(text=texto)
                except tk.TclError:
                    pass

        decir(tr("preguntando..."))

        def trabajo():
            try:
                motor = compat_engine.CompatEve.__new__(compat_engine.CompatEve)
                motor.cfg = self._cfg_de_pantalla()
                motor._destino(motor.cfg)
                lista = motor.modelos()
            except Exception as exc:  # noqa: BLE001 - la red falla de mil formas
                fallo = str(exc)[:120]
                self._ui(lambda: decir(f"{tr('no pude preguntarle')}: {fallo}"))
                return
            self._ui(lambda: self._elegir_modelo(lista, decir))

        threading.Thread(target=trabajo, daemon=True).start()

    def _cfg_de_pantalla(self) -> dict:
        """La config con lo que hay ESCRITO en el panel, sin guardar todavia.

        Hace falta porque uno cambia el proveedor y aprieta buscar sin guardar:
        leer del disco preguntaria al servicio anterior y devolveria una lista
        que no tiene nada que ver con lo que se esta mirando.
        """
        cfg = dict(self.cfg)
        for clave in ("compat_proveedor", "compat_url", "compat_modelo"):
            var = self.vars.get(clave)
            if var is not None:
                cfg[clave] = var.get().strip()
        return cfg

    def _elegir_modelo(self, lista, decir) -> None:
        """La lista que devolvio el servicio, para elegir de ahi."""
        if not lista:
            decir(tr("el servicio no publica ninguno"))
            return
        decir(f"{len(lista)} " + tr("disponibles"))
        v = tk.Toplevel(self)
        v.title(tr("Modelos disponibles"))
        v.geometry("520x420")
        v.transient(self)
        caja = tk.Listbox(v, activestyle="none")
        caja.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        for nombre in lista:
            caja.insert("end", nombre)
        actual = (self.vars.get("compat_modelo").get().strip()
                  if self.vars.get("compat_modelo") else "")
        if actual in lista:
            caja.selection_set(lista.index(actual))
            caja.see(lista.index(actual))

        def elegir(_e=None):
            sel = caja.curselection()
            if sel and self.vars.get("compat_modelo") is not None:
                self.vars["compat_modelo"].set(lista[sel[0]])
                decir(f"{tr('elegido')}: {lista[sel[0]]}")
            v.destroy()

        caja.bind("<Double-Button-1>", elegir)
        fila = ttk.Frame(v)
        fila.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(fila, text=tr("Usar este"), command=elegir,
                   style="Principal.TButton").pack(side="right")
        ttk.Button(fila, text=tr("Cerrar"), command=v.destroy).pack(side="right", padx=6)

    def voces_buscar(self):
        self.voz_estado.config(text=tr("consultando catalogo..."))

        def work():
            from . import voices

            try:
                idiomas = voices.idiomas()
                lista = voices.listar(self.voz_idioma.get())
                puestas = set(voices.instaladas())
                propias = voices.propias()
            except Exception as exc:  # noqa: BLE001
                fallo = str(exc)
                self._ui(lambda: self.voz_estado.config(text=f"error: {fallo}"))
                return

            def pintar():
                self.voz_combo["values"] = idiomas
                self.voz_tree.delete(*self.voz_tree.get_children())
                # Las tuyas primero y marcadas. Del catalogo salen nombre,
                # idioma, calidad y tamano; de una voz entrenada por vos no hay
                # nada de eso, asi que si la lista se armara solo del catalogo
                # se podria usar pero no ver -- y habria que acordarse del
                # nombre exacto y escribirlo a mano.
                for clave in propias:
                    self.voz_tree.insert(
                        "", "end",
                        values=(clave, tr("propia"), "", tr("instalada")))
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

    def voz_importar(self):
        """Trae una voz de Piper de cualquier carpeta a la de Eve.

        El cargador SIEMPRE acepto una voz que el catalogo no conoce --nunca lo
        consulto-- pero la unica forma de meterla era saber donde vive la
        carpeta de datos y copiar los dos archivos a mano. Esto es lo unico que
        faltaba para poder usar una voz entrenada por vos.
        """
        from tkinter import filedialog

        from . import voices

        ruta = filedialog.askopenfilename(
            title=tr("Elegi el .onnx de la voz"), parent=self,
            filetypes=[(tr("Voz de Piper"), "*.onnx"), (tr("Todos"), "*.*")],
        )
        if not ruta:
            return
        try:
            clave = voices.importar(ruta)
        except ValueError as exc:
            messagebox.showerror(tr("Voces"), str(exc))
            return
        except OSError as exc:
            messagebox.showerror(tr("Voces"), f"{tr('no pude copiarla')}: {exc}")
            return
        # Queda elegida: importar una voz y despues tener que ir a buscarla en
        # una lista seria dejar el trabajo por la mitad.
        if self.vars.get("piper_voice") is not None:
            self.vars["piper_voice"].set(clave)
        self.voz_estado.config(text=f"{tr('importada')}: {clave}")
        self.voces_buscar()

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
            style="Ayuda.TLabel",
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
            style="Ayuda.TLabel",
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


    def _texto_motor_dibujo_label(self) -> str:
        """Que motor de dibujo quedo activo, y por que.

        Se lee al abrir y no despues de un boton: `motor_dibujo` puede pedir
        Skia y quedarse en Pillow porque la maquina no da, y un ajuste que no
        hace lo que dice tiene que decirlo sin que se lo pregunten.
        """
        from . import gpu

        return gpu.por_que(self.cfg)

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
                pass  # a medio escribir, #4fc todavia no es un color

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
        # DONDE va, elegido al crearlo. Antes no se preguntaba y el modulo
        # nuevo caia en el cartel, que es el valor de fabrica de `superficie`.
        # Quien venia a armar la ventana de actividad agregaba un modulo, no
        # aparecia por ningun lado --el cartel en modo `auto` esta escondido
        # hasta que Eve trabaja-- y no habia nada que explicara por que. Se
        # reporto como "sigo sin saber como agregar modulos a actividad".
        ttk.Label(fila, text=tr("en")).pack(side="left", padx=(8, 4))
        self.mod_donde = tk.StringVar(value="tablero")
        ttk.Combobox(fila, textvariable=self.mod_donde,
                     values=[tr("tablero"), tr("cartel")],
                     state="readonly", width=9).pack(side="left")
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

    def _grabar_banco(self) -> None:
        """La ventana que guia la grabacion del banco de voz.

        El banco viejo se corto por silencio, y eso elimino justo los silencios
        --donde vive el ruido de fondo-- asi que el modo de sensibilidad `auto`
        no se puede validar con el. Medido sobre los 24 clips: mediana de 90 ms
        antes de la primera palabra y uno solo llega a 300.

        Lo que esta ventana hace, y es todo lo que hace falta, es imponer el
        silencio y COMPROBARLO antes de aceptar la toma. Un grabador que no lo
        comprueba deja pasar el mismo problema, porque adelantarse a hablar es
        lo normal cuando uno esta leyendo una frase de la pantalla.
        """
        from . import banco, voice

        frases = banco.frases()
        if not frases:
            self.estado.config(
                text=tr("falta el banco viejo: de ahi salen las frases"),
                style="Error.TLabel")
            return

        v = tk.Toplevel(self)
        v.title(tr("Grabar el banco de voz"))
        v.geometry("620x340")
        v.transient(self)

        pendientes = [n for n in sorted(frases) if n not in banco.hechas()]
        estado = {"grabador": None, "audio": None, "tarea": None}

        cabecera = ttk.Label(v, text="", style="Ayuda.TLabel")
        cabecera.pack(anchor="w", padx=16, pady=(14, 2))
        frase = ttk.Label(v, text="", font=(None, 15), wraplength=580,
                          justify="left")
        frase.pack(anchor="w", padx=16, pady=(4, 10))
        aviso = ttk.Label(v, text="", font=(None, 20, "bold"))
        aviso.pack(anchor="w", padx=16)
        barra = ttk.Progressbar(v, maximum=1.0, length=580)
        barra.pack(padx=16, pady=8)
        detalle = ttk.Label(v, text="", style="Ayuda.TLabel", wraplength=580,
                            justify="left")
        detalle.pack(anchor="w", padx=16)

        fila = ttk.Frame(v)
        fila.pack(side="bottom", fill="x", padx=16, pady=12)
        b_grabar = ttk.Button(fila, text=tr("Grabar"),
                              style="Principal.TButton")
        b_grabar.pack(side="left")
        b_saltar = ttk.Button(fila, text=tr("Saltar esta"))
        b_saltar.pack(side="left", padx=6)
        ttk.Button(fila, text=tr("Cerrar"),
                   command=v.destroy).pack(side="right")

        def mostrar():
            if not pendientes:
                cabecera.config(text=tr("Listo"))
                frase.config(text=tr("Ya estan las 24. Corre banco_voz.py para medir."))
                aviso.config(text="")
                detalle.config(text=banco.escribir_transcripciones())
                b_grabar.config(state="disabled")
                b_saltar.config(state="disabled")
                return
            nombre = pendientes[0]
            cabecera.config(text=f"{len(banco.hechas())} / {len(frases)}  ·  {nombre}")
            frase.config(text=frases[nombre])
            aviso.config(text="")

        def nivel():
            g = estado["grabador"]
            if g is None:
                return
            barra["value"] = g.nivel
            estado["tarea"] = v.after(50, nivel)

        def parar_tareas():
            if estado["tarea"] is not None:
                try:
                    v.after_cancel(estado["tarea"])
                except tk.TclError:
                    pass
                estado["tarea"] = None

        def arrancar():
            """Graba YA y recien despues avisa: el silencio tiene que quedar
            adentro del archivo, asi que la cuenta atras va con el microfono
            abierto. Empezar a grabar cuando aparece HABLA es exactamente lo
            que dejo al banco viejo sin silencio."""
            g = voice.Recorder()
            try:
                g.start()
            except Exception as exc:  # noqa: BLE001
                detalle.config(text=f"{tr('no pude abrir el microfono')}: {exc}")
                return
            estado["grabador"] = g
            b_grabar.config(state="disabled")
            b_saltar.config(state="disabled")
            detalle.config(text="")
            nivel()
            cuenta(banco.SILENCIO_PEDIDO_MS)

        def cuenta(restan):
            if restan > 0:
                aviso.config(text=tr("callate...") + f"  {restan // 100 / 10:.1f}")
                v.after(100, lambda: cuenta(restan - 100))
                return
            aviso.config(text=tr("HABLA"))
            b_grabar.config(text=tr("Listo"), state="normal",
                            command=terminar)

        def terminar():
            parar_tareas()
            g = estado["grabador"]
            estado["grabador"] = None
            barra["value"] = 0
            b_grabar.config(text=tr("Grabar"), command=arrancar)
            b_saltar.config(state="normal")
            aviso.config(text="")
            audio = g.stop() if g is not None else None
            if audio is None or not len(audio):
                detalle.config(text=tr("no entro audio"))
                return
            sirve, motivo = banco.revisar(audio)
            detalle.config(text=motivo)
            if not sirve:
                return   # se repite: no se guarda una toma que no sirve
            banco.guardar(pendientes[0], audio)
            banco.escribir_transcripciones()
            pendientes.pop(0)
            mostrar()

        def saltar():
            if pendientes:
                pendientes.pop(0)
            mostrar()

        b_grabar.config(command=arrancar)
        b_saltar.config(command=saltar)
        v.protocol("WM_DELETE_WINDOW",
                   lambda: (parar_tareas(), v.destroy()))
        mostrar()

    def _revisar_listener(self) -> None:
        """Abre el asistente si no esta, y si esta lo dice sin abrir otro.

        Es un solo boton y no un par prender/apagar a proposito: lo que el
        usuario quiere saber es "¿esta andando?" y lo que quiere que pase es
        "que ande". Dos botones obligan a saber la respuesta antes de apretar,
        que es justo lo que uno viene a averiguar.

        Y no abre uno segundo NUNCA. Dos listeners son dos hooks globales sobre
        la misma tecla: apretas una vez, se graban dos, se mandan dos pedidos y
        contestan dos voces encima. A simple vista hay un solo icono en la
        bandeja, asi que el sintoma parece de cualquier otra cosa. El arranque
        ya se defiende de eso con `otro_asistente`; esto lo comprueba ANTES de
        lanzar para poder decirlo, en vez de lanzar un proceso que se muere solo
        y dejar al usuario mirando un boton que no hizo nada visible.
        """
        pid = store.asistente_corriendo()
        if pid:
            self.estado.config(
                text=f"[on] {tr('el listener ya esta abierto')} (pid {pid})",
                style="Ok.TLabel")
            return
        try:
            plataforma.lanzar(plataforma.comando_asistente())
        except OSError as exc:
            self.estado.config(text=f"{tr('no pude abrir el listener')}: {exc}",
                               style="Error.TLabel")
            return
        self.estado.config(text=tr("abriendo el listener..."), style="Ayuda.TLabel")
        # El latido tarda en aparecer --arranca el modelo de voz-- asi que se
        # mira varias veces en vez de una. Sin esto el boton parece no haber
        # hecho nada y el usuario lo aprieta de nuevo, que es exactamente como
        # se termina con dos.
        self.boton_listener.config(state="disabled")
        self._esperar_listener(0)

    def _esperar_listener(self, intento: int) -> None:
        """Mira si ya latio. Hasta 20 segundos, y despues lo dice."""
        pid = store.asistente_corriendo()
        if pid:
            self.estado.config(text=f"[on] {tr('listener abierto')} (pid {pid})",
                               style="Ok.TLabel")
        elif intento >= 40:
            self.estado.config(
                text=tr("el listener no llego a dar señales; fijate en Acciones"),
                style="Ayuda.TLabel")
        else:
            try:
                self.after(500, lambda: self._esperar_listener(intento + 1))
            except tk.TclError:
                pass
            return
        try:
            self.boton_listener.config(state="normal")
        except tk.TclError:
            pass

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
        # `tablero` es la ventana de actividad y `overlay` el cartel. El rotulo
        # dice "cartel" porque es como se llama en todo el resto del panel;
        # `overlay` es el nombre interno y no tiene por que salir a la pantalla.
        donde = ("overlay" if self.mod_donde.get() in (tr("cartel"), "cartel")
                 else "tablero")
        nuevo = {"id": ident, "tipo": tipo, "superficie": donde}
        # En cascada y no siempre en el mismo punto: apilados en 40,40 el
        # segundo tapa al primero y parece que el boton no hizo nada. Es lo
        # mismo que ya hacia el boton de la ventana de actividad.
        cuantos = len([m for m in mods.listar(cfg) if m["superficie"] == donde])
        nuevo["x"] = 40 + (cuantos % 6) * 30
        nuevo["y"] = 40 + (cuantos % 6) * 30
        store.save_config(mods.guardar(cfg, nuevo))
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
        """Generado desde `registro.CARTEL`.

        Sexta y ultima pestaña bajo el freno del plan: 27% de excepciones.
        """
        t = ttk.Frame(nb)
        self._pintar_registro(t, registro.CARTEL)
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
                # Sin color elegido se muestra el `borde` de la paleta, que es
                # lo que ya significa "un contorno, nada mas". Antes era un
                # gris puesto a mano, que sobre un tema oscuro parecia un
                # color elegido en vez de un hueco.
                muestra.configure(bg=var.get().strip() or self._borde())
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
        self.hist_count = ttk.Label(bar, text="", style="Ayuda.TLabel")
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

    def hotkey_capturar(self) -> None:
        """Toma la proxima tecla que aprietes y la deja puesta.

        Escribir `f13` a mano exige saber COMO se llama la tecla, y el nombre no
        esta en ningun lado: el que vale no es el que dice el teclado ni el que
        usa tkinter, es el que reporta el hook global.

        Por eso la captura pasa por `plataforma.hook_teclado`, que es **el mismo
        backend con el que el listener registra**. `Listener._on_event` compara
        `nombre != cfg["hotkey"]` contra el nombre que le llega de ese hook, asi
        que capturar por ahi hace que lo guardado sea reconocible por
        construccion. Con el `<Key>` de tkinter --que es lo que usa el boton de
        al lado-- saldria `F13` donde el listener espera `f13`, y quedaria una
        tecla configurada que no responde nunca.

        Y por eso NO se aceptan combinaciones aunque el hook las podria armar:
        el listener compara UN nombre, asi que guardar `ctrl+k` seria dejar
        puesta una tecla que no puede coincidir con nada. Una perilla que miente
        es peor que una que falta.
        """
        if getattr(self, "_capturando", None):
            return

        from . import plataforma

        self._capturando = True
        self.tecla_label.config(text=tr("apreta la tecla que quieras...")
                                + "  " + tr("(Escape cancela)"))

        def soltar():
            """Desengancha una sola vez, venga de donde venga."""
            handle, self._capturando = self._capturando, None
            if handle is not True:
                plataforma.unhook_teclado(handle)

        def aplicar(nombre):
            if not self._capturando:
                return          # ya se resolvio por otro lado
            soltar()
            if nombre in ("esc", "escape"):
                self.tecla_label.config(text=tr("cancelado"))
                return
            self.vars["hotkey"].set(nombre)
            self.tecla_label.config(
                text=f"{tr('tecla')}: {nombre}. {tr('Acordate de Guardar.')}")

        def llego(nombre, tipo):
            # Del hilo del hook, que no es el de tkinter.
            if tipo == "down":
                self._ui(lambda: aplicar(nombre))

        self._capturando = plataforma.hook_teclado(llego)

        def rendirse():
            if self._capturando:
                soltar()
                self.tecla_label.config(text=tr("no llego ninguna tecla"))

        # Con tope: un panel esperando para siempre una tecla que nadie va a
        # apretar es peor que escribirla a mano.
        self.after(15000, rendirse)

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
