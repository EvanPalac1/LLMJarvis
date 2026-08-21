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

from . import modulos, plataforma, store, voice

CREATE_NEW_CONSOLE = 0x00000010

PAD = 12
GRIS, ROJO, VERDE = "#666666", "#c0392b", "#1e8449"

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

ROLES_ETIQUETA = (
    ("fondo", "Fondo"), ("panel", "Cajas y campos"), ("texto", "Texto"),
    ("texto_tenue", "Texto secundario"), ("acento", "Acento"),
    ("acento2", "Acento apagado"), ("borde", "Contorno"), ("alerta", "Alerta"),
)

MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
CC_MODELS = ["opus", "sonnet", "haiku"]
CC_MODES = ["acceptEdits", "auto", "manual"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self._vivo = True
        self.cfg = store.load_config()
        self._estilo()
        self.title("LLMJarvis - configuracion")
        self.geometry("800x790")
        self.minsize(640, 420)

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
        ttk.Button(fila, text="Guardar", command=self.save,
                   style="Principal.TButton").pack(side="right")
        ttk.Button(fila, text="Buscar actualizaciones", command=self.buscar_update).pack(
            side="right", padx=(0, 6)
        )
        # Al lado del boton de actualizar, que es donde uno se pregunta "cual
        # tengo?". Sin esto habia que abrir una terminal y correr --version.
        from eve import __version__

        ttk.Label(fila, text=f"v{__version__}", style="Ayuda.TLabel").pack(
            side="right", padx=(0, 10)
        )
        self.after(300, self._refrescar_estado)

        nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 6))
        self.vars: dict[str, tk.Variable] = {}
        self._nombres_pantalla = {}
        self.key_vars: dict[str, tk.Variable] = {}
        # Siete pestañas agrupadas por lo que uno viene a hacer, no por modulo.
        nb.add(self._tab_general(nb), text="  General  ")
        nb.add(self._tab_cuentas(nb), text="  Cuentas  ")
        nb.add(self._tab_voz(nb), text="  Voz  ")
        nb.add(self._tab_contactos(nb), text="  Contactos  ")
        nb.add(self._tab_addons(nb), text="  Addons  ")
        nb.add(self._tab_apariencia(nb), text="  Apariencia  ")
        nb.add(self._tab_actividad(nb), text="  Actividad  ")
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
                self._ui(lambda: messagebox.showerror("Actualizar", fallo))
                return
            if not nueva:
                self._ui(lambda: messagebox.showinfo(
                    "Actualizar", f"Ya tenes la ultima version ({updater.version_actual()})."))
                return
            self._ui(lambda: self._ofrecer_update(nueva))

        threading.Thread(target=work, daemon=True).start()

    def _ofrecer_update(self, nueva: dict) -> None:
        from . import plataforma, updater

        if not plataforma.congelado():
            messagebox.showinfo(
                "Actualizar",
                f"Hay una version nueva: {nueva['version']}.\n\n"
                "Estas corriendo desde el codigo, asi que se actualiza con git pull.",
            )
            return
        if not nueva["asset"]:
            messagebox.showinfo(
                "Actualizar",
                f"Hay {nueva['version']}, pero todavia no hay paquete para tu sistema.\n"
                "Te abro la pagina de descargas.",
            )
            plataforma.abrir(nueva["url"])
            return
        if not messagebox.askyesno(
            "Actualizar",
            f"Version nueva: {nueva['version']}   (tenes la {updater.version_actual()})\n\n"
            "Se descarga, se verifica su sha256 y se instala encima.\n"
            "Tu configuracion, agenda, memoria y voces no se tocan.\n\n"
            "Descargar e instalar ahora?",
        ):
            return

        self.estado.config(text="descargando actualizacion...")

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
                self._ui(lambda: messagebox.showerror("Actualizar", fallo))
                return
            self._ui(lambda: (messagebox.showinfo("Actualizar", updater.instalar(ruta)),
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
                f"[on] asistente corriendo   |   motor: {vivo.get('motor', cfg['engine'])}"
                f"   |   tecla: {vivo.get('tecla', cfg['hotkey'])}"
            )
            estilo = "Ok.TLabel"
        else:
            texto = (
                f"[off] asistente detenido   |   motor: {cfg['engine']}"
                f"   |   tecla: {cfg['hotkey']}"
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
                text="La configuracion cambio por fuera. Guarda o cerra para recargarla.",
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

    def _seccion(self, padre, titulo: str):
        caja = ttk.LabelFrame(padre, text=titulo, style="Seccion.TLabelframe")
        caja.pack(fill="x", padx=(0, PAD), pady=(0, PAD))
        return caja

    def _ayuda(self, padre, texto: str) -> None:
        ttk.Label(padre, text=texto, style="Ayuda.TLabel", justify="left").pack(
            anchor="w", padx=PAD, pady=(2, 6)
        )


    # --- las cinco pestañas ------------------------------------------------
    # Componen los bloques que ya existian; cada bloque sigue creando su frame,
    # asi que se lo cuelga del contenedor con scroll y listo.

    def _componer(self, nb, titulo, subtitulo, bloques):
        marco, dentro = self._hoja(nb, titulo, subtitulo)
        for bloque in bloques:
            bloque(dentro).pack(fill="both", expand=True)
        return marco

    def _tab_general(self, nb):
        return self._componer(
            nb, "General",
            "Quien es Eve, quien piensa por ella y hasta donde puede meterse.",
            [self._bloque_perfiles, self._bloque_general],
        )

    def _tab_cuentas(self, nb):
        return self._componer(
            nb, "Cuentas",
            "Con que se conecta. Todo opcional salvo el motor que elegiste.",
            [self._bloque_claves, self._bloque_correo],
        )

    def _tab_voz(self, nb):
        return self._componer(
            nb, "Voz",
            "Como te escucha y como te responde.",
            [self._bloque_voz, self._bloque_voces],
        )

    def _tab_contactos(self, nb):
        return self._componer(
            nb, "Contactos",
            "La agenda que Eve usa cuando nombras a alguien.",
            [self._bloque_contactos],
        )

    def _tab_addons(self, nb):
        return self._componer(
            nb, "Addons",
            "Lo que Eve puede manejar ademas de tu PC. Cada uno trae sus comandos.",
            [self._bloque_addons],
        )

    def _bloque_addons(self, nb):
        from . import addons

        t = ttk.Frame(nb)
        cfg = store.load_config()
        cargados = addons.todos(recargar=True)

        caja = self._seccion(t, "Instalados")
        if not cargados:
            self._ayuda(caja, "No hay ninguno cargado.")
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
            "Destildar uno lo saca del prompt: deja de gastar tokens y Eve deja de\n"
            "ofrecerlo. Si no hay ninguno tildado, se usan todos los disponibles.",
        )

        caja = self._seccion(t, "Agregar los tuyos")
        self._ayuda(
            caja,
            f"Poné archivos .py en:\n  {addons.CARPETA_USUARIO}\n\n"
            "Cada uno define NOMBRE, un texto para el modelo y una funcion\n"
            "ejecutar(accion, args, cfg). Ojo: corren dentro de Eve, con los mismos\n"
            "permisos que el programa. Poné solo cosas en las que confies.",
        )
        sin_revisar = addons.pendientes()
        if sin_revisar:
            alerta = self._seccion(t, "Sin revisar")
            self._ayuda(
                alerta,
                "Estos archivos no se estan cargando. Un addon es codigo que corre\n"
                "con tus permisos y no pasa por el freno, asi que hay que mirarlo\n"
                "antes. Si Eve escribio alguno, aca es donde lo revisas.")
            for nombre, ruta, marca in sin_revisar:
                fila = ttk.Frame(alerta)
                fila.pack(fill="x", padx=12, pady=3)
                ttk.Label(fila, text=f"{nombre}.py", width=22).pack(side="left")
                ttk.Button(fila, text="Ver el codigo",
                           command=lambda r=ruta: self._addon_ver(r)).pack(side="left")
                ttk.Button(fila, text="Aprobar",
                           command=lambda n=nombre, m=marca: self._addon_aprobar(n, m)
                           ).pack(side="left", padx=6)

        ttk.Button(caja, text="Abrir la carpeta de addons",
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
        ttk.Label(cab, text="Apariencia", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(cab, text="Los colores de todo, y el cartel que Eve muestra "
                            "encima de lo que estes haciendo.",
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

        sub = ttk.Notebook(marco)
        sub.pack(fill="both", expand=True, padx=PAD, pady=(8, PAD))
        for titulo, bloques in (
            ("Tema", [self._bloque_tema]),
            ("Cartel", [self._bloque_hud]),
            ("Modulos", [self._bloque_modulos]),
            ("Subtitulos", [self._bloque_subtitulos]),
        ):
            sub.add(self._hoja_simple(sub, bloques), text=f"  {titulo}  ")
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
        for bloque in bloques:
            bloque(dentro).pack(fill="both", expand=True)
        return marco

    def _tab_actividad(self, nb):
        return self._componer(
            nb, "Actividad",
            "Que se dijo y que se ejecuto en tu PC.",
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
        ttk.Checkbutton(parent, text=label, variable=var).pack(anchor="w", padx=12, pady=4)

    # --- tabs --------------------------------------------------------------

    def _bloque_perfiles(self, nb):
        t = ttk.Frame(nb)
        caja = self._seccion(t, "Perfiles")
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(8, 4))
        ttk.Label(fila, text="Perfil activo", width=24).pack(side="left")
        self.perfil_var = tk.StringVar(value=self.cfg.get("perfil_activo", ""))
        self.perfil_combo = ttk.Combobox(fila, textvariable=self.perfil_var,
                                         values=sorted(store.listar_perfiles()),
                                         state="readonly")
        self.perfil_combo.pack(side="left", fill="x", expand=True)

        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(fila, text="Cargar", command=self._perfil_cargar).pack(side="left")
        ttk.Button(fila, text="Guardar como...",
                   command=self._perfil_guardar).pack(side="left", padx=6)
        ttk.Button(fila, text="Borrar", command=self._perfil_borrar).pack(side="left")
        ttk.Button(fila, text="Exportar...",
                   command=self._perfil_exportar).pack(side="left", padx=(12, 0))
        ttk.Button(fila, text="Importar...",
                   command=self._perfil_importar).pack(side="left", padx=6)
        self._ayuda(
            caja,
            "Un perfil guarda como se ve y como suena Eve: colores, forma, fuente,\n"
            "voz, velocidad, tono y el nombre del asistente.\n"
            "NO toca el motor, el modelo, la tecla, los permisos ni tus datos: un\n"
            "perfil que te pasan no puede cambiarte como trabaja el asistente.",
        )
        return t

    def _perfil_cargar(self):
        nombre = self.perfil_var.get()
        if not nombre:
            messagebox.showinfo("Perfiles", "Elegi un perfil de la lista.")
            return
        if not messagebox.askyesno(
            "Cargar perfil",
            f"Se va a aplicar el perfil {nombre!r} y se pierden los cambios sin guardar.\n\n"
            "Seguir?",
        ):
            return
        store.aplicar_perfil(nombre)
        messagebox.showinfo(
            "Perfiles",
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
            "Ya existe", f"Ya hay un perfil {nombre!r}. Lo pisamos?"
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
        messagebox.showinfo("Perfiles", f"Guardado como {nombre!r}.")

    def _perfil_exportar(self):
        from tkinter import filedialog

        nombre = self.perfil_var.get()
        if not nombre:
            messagebox.showinfo("Perfiles", "Elegi un perfil de la lista primero.")
            return
        destino = filedialog.asksaveasfilename(
            title="Exportar perfil", parent=self, initialfile=f"{nombre}.eveperfil",
            defaultextension=".eveperfil",
            filetypes=[("Perfil de Eve", "*.eveperfil"), ("Todos", "*.*")],
        )
        if not destino:
            return
        try:
            mensaje = store.exportar_perfil(nombre, destino)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Exportar", str(exc))
            return
        messagebox.showinfo(
            "Exportar",
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
            title="Importar perfil", parent=self,
            initialdir=ejemplos if os.path.isdir(ejemplos) else None,
            filetypes=[("Perfil de Eve", "*.eveperfil"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        try:
            nombre, config = store.leer_perfil_archivo(ruta)
        except ValueError as exc:
            messagebox.showerror("Importar", str(exc))
            return
        nombre = simpledialog.askstring("Importar perfil", "Guardarlo con el nombre:",
                                        initialvalue=nombre, parent=self) or ""
        if not nombre.strip():
            return
        nombre = nombre.strip()
        if nombre in store.listar_perfiles() and not messagebox.askyesno(
            "Ya existe", f"Ya hay un perfil {nombre!r}. Lo pisamos?"
        ):
            return
        store.guardar_perfil(nombre, {**store.DEFAULTS, **config})
        self.perfil_var.set(nombre)
        self.perfil_combo["values"] = sorted(store.listar_perfiles())
        messagebox.showinfo(
            "Importar",
            f"Perfil {nombre!r} importado con {len(config)} opciones.\n\n"
            "Toca 'Cargar' para aplicarlo.",
        )

    def _perfil_borrar(self):
        nombre = self.perfil_var.get()
        if not nombre:
            return
        if messagebox.askyesno("Borrar perfil", f"Borrar el perfil {nombre!r}?"):
            store.borrar_perfil(nombre)
            self.perfil_var.set("")
            self.perfil_combo["values"] = sorted(store.listar_perfiles())

    def _bloque_general(self, nb):
        t = ttk.Frame(nb)
        self._row(t, "Nombre de la IA", "assistant_name")
        self._row(t, "Idioma (es / en / ...)", "language")
        self._row(t, "Motor", "engine", ["api", "claude-code", "ollama"])
        ttk.Label(
            t,
            text="  api = Messages API, necesita tu ANTHROPIC_API_KEY.\n"
            "  claude-code = CLI de Claude Code, usa tu suscripcion sin key (mas lento).\n"
            "  ollama = modelo local, sin key ni nube. Peor encadenando varias tools.",
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12)
        self._row(t, "Modelo (motor api)", "model", MODELS)
        self._row(t, "Modelo (motor claude-code)", "cc_model", CC_MODELS)
        self._row(t, "Permisos (motor claude-code)", "cc_permission_mode", CC_MODES)
        from .compat_engine import GRATIS, PROVEEDORES

        caja = ttk.LabelFrame(t, text="Motor 'compat' (protocolo de OpenAI)")
        caja.pack(fill="x", padx=12, pady=(10, 4))
        self._row(caja, "Proveedor", "compat_proveedor", list(PROVEEDORES))
        self._row(caja, "Modelo (vacio = el sugerido)", "compat_modelo")
        self._row(caja, "URL propia (vacio = la del proveedor)", "compat_url", width=40)
        ttk.Label(
            caja,
            text="Con capa gratuita: " + ", ".join(GRATIS) + ".\n"
            "La clave de cada uno va en la pestania Cuentas. 'propio' sirve para\n"
            "cualquier servidor que hable /chat/completions.",
            style="Ayuda.TLabel", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self._row(t, "Ollama: host", "ollama_host")
        self._row(t, "Ollama: modelo", "ollama_model")
        self._row(t, "Effort", "effort", EFFORTS)
        self._row(t, "Max tokens", "max_tokens")
        self._row(t, "Tecla del keypad", "hotkey")
        self._row(t, "Turnos de contexto", "context_turns")
        self._row(t, "Minutos de contexto", "context_minutes")
        self._row(t, "Quien manda sobre un ajuste", "autoridad",
                  ["usuario", "eve", "preguntar"])
        self._ayuda(
            t,
            "usuario: lo que cambies a mano queda trabado y Eve no lo pisa.\n"
            "eve: puede cambiar lo que quiera.  preguntar: pide permiso cada vez.\n"
            "Para soltar lo trabado, decile 'destraba <clave>' o borra la lista abajo.")
        self._row(t, "Claves que fijaste vos", "claves_del_usuario", width=44)

        ttk.Label(t, text="Rutas de trabajo permitidas (una por linea)").pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        self.workdirs = tk.Text(t, height=5)
        self.workdirs.insert("1.0", "\n".join(self.cfg.get("workdirs", [])))
        self.workdirs.pack(fill="x", padx=12)

        ttk.Label(t, text="Permisos").pack(anchor="w", padx=12, pady=(12, 2))
        self.perm_var = tk.StringVar(
            value=PERM_ASK if self.cfg.get("confirm_destructive", True) else PERM_ALL
        )
        ttk.Combobox(
            t, textvariable=self.perm_var, values=[PERM_ASK, PERM_ALL], state="readonly", width=60
        ).pack(anchor="w", padx=12)
        ttk.Label(
            t,
            text="'Permitir todo' desactiva la confirmacion y tambien los permisos internos\n"
            "de Claude Code. Todo queda igual registrado en la pestaña Acciones.",
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(2, 0))
        return t

    def _bloque_claves(self, nb):
        t = ttk.Frame(nb)

        # --- sesion de Claude Code (motor 'claude-code', sin API key) ---
        box = ttk.LabelFrame(t, text="Sesion de Claude Code (motor 'claude-code')")
        box.pack(fill="x", padx=12, pady=(12, 4))
        self.auth_label = ttk.Label(box, text="consultando...", justify="left")
        self.auth_label.pack(anchor="w", padx=10, pady=(8, 4))
        row = ttk.Frame(box)
        row.pack(anchor="w", padx=10, pady=(0, 10))
        ttk.Button(row, text="Iniciar sesion", command=self.auth_login).pack(side="left")
        ttk.Button(row, text="Cerrar sesion", command=self.auth_logout).pack(side="left", padx=6)
        ttk.Button(row, text="Actualizar", command=self.refresh_auth).pack(side="left")
        self.after(100, self.refresh_auth)

        ttk.Label(
            t,
            text="Se guardan en el gestor de credenciales de Windows, nunca en texto plano.\n"
            "Anthropic solo hace falta con el motor 'api'; con 'claude-code' se usa tu suscripcion.\n"
            "Las otras habilitan proveedores opcionales de voz.",
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

        box = ttk.LabelFrame(t, text="Conexiones con apps (todas opcionales)")
        box.pack(fill="x", padx=12, pady=(14, 4))
        ttk.Label(
            box,
            text="Sin esto Eve igual abre WhatsApp, Discord, Telegram y el mail con el\n"
            "mensaje escrito, para que lo mandes vos. Estas claves solo agregan leer\n"
            "y enviar sin pasar por la app.",
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(8, 6))
        self._campo_clave(box, "discord_webhook", "Discord: URL del webhook")
        if not self.cfg.get("steam_id"):
            from . import integrations

            self.cfg["steam_id"] = integrations.steam_id_local()  # detectado del disco
        self._row(box, "Tu SteamID64 (autodetectado)", "steam_id", width=40)
        self._campo_clave(box, "steam", "Steam: Web API key")
        self._check(
            box,
            "WhatsApp: enviar solo (simula el Enter; exige numero, no nombre)",
            "whatsapp_autosend",
        )
        self._check(
            box,
            "Discord: escribir como vos (maneja tu cliente; verifica el canal por titulo)",
            "discord_autosend",
        )
        ttk.Label(
            box,
            text="Gmail: si 'Contrasenas de aplicaciones' no te aparece, tu cuenta no tiene 2FA\n"
            "o la administra tu organizacion. Alternativa sin claves: agrega el Gmail a\n"
            "Outlook (Archivo > Agregar cuenta) y Eve lo lee y escribe por ahi.\n"
            "Webhook: Editar canal > Integraciones > Webhooks. Steam key: steamcommunity.com/dev/apikey",
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
            text="Eve usa esta lista cuando nombras a alguien. En 'alias' pone como le decis\n"
            "de verdad, separado por comas (lucho, el lucas) — la voz rara vez dice el\n"
            "nombre completo.\n\n"
            "discord_user  = su @ (para mencionarlo dentro del mensaje)\n"
            "discord_dm    = su chat privado. Activa Ajustes > Avanzado > Modo desarrollador,\n"
            "                boton derecho sobre la conversacion > Copiar ID\n"
            "discord_canal = un canal de servidor. Boton derecho > Copiar enlace",
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
        ttk.Button(botones, text="Agregar / actualizar", command=self._contacto_guardar).pack(side="left")
        ttk.Button(botones, text="Borrar", command=self._contacto_borrar).pack(side="left", padx=6)
        ttk.Button(botones, text="Limpiar campos", command=self._contacto_limpiar).pack(side="left")

        compartir = ttk.Frame(t)
        compartir.pack(anchor="w", padx=12, pady=(0, 8))
        ttk.Label(compartir, text="Compartir:").pack(side="left", padx=(0, 8))
        ttk.Button(compartir, text="Exportar", command=self._contacto_exportar).pack(side="left")
        ttk.Button(compartir, text="Importar", command=self._contacto_importar).pack(side="left", padx=6)
        ttk.Label(
            t,
            text="Exportar genera un archivo .evecontact que podes mandarle a un amigo por\n"
            "WhatsApp o Discord; el lo abre con Importar y le queda el contacto cargado.",
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
            messagebox.showerror("Falta el nombre", "El nombre no puede estar vacio.")
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
            messagebox.showinfo("Exportar", "Elegi un contacto de la lista primero.")
            return
        seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in nombre).strip()
        destino = filedialog.asksaveasfilename(
            title="Guardar contacto para compartir",
            initialfile=f"{seguro}.evecontact",
            defaultextension=".evecontact",
            filetypes=[("Contacto de Eve", "*.evecontact"), ("JSON", "*.json")],
        )
        if destino:
            messagebox.showinfo("Exportar", store.exportar_contactos([nombre], destino))

    def _contacto_importar(self):
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(
            title="Abrir contacto compartido",
            filetypes=[("Contacto de Eve", "*.evecontact"), ("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        try:
            nuevos = store.leer_contactos_archivo(ruta)
        except ValueError as exc:
            messagebox.showerror("Importar", str(exc))
            return

        agregados, cambiados, conflictos = store.importar_contactos(nuevos)
        if conflictos:
            # Pisar la agenda de alguien en silencio no es aceptable: se pregunta.
            if messagebox.askyesno(
                "Ya existen",
                "Estos contactos ya estan en tu agenda:\n\n  "
                + "\n  ".join(conflictos)
                + "\n\nReemplazarlos con los del archivo?",
            ):
                mas, cambiados, _ = store.importar_contactos(nuevos, reemplazar=set(conflictos))
                agregados += mas

        self.contactos = store.load_contacts()
        self._contactos_refrescar()
        messagebox.showinfo(
            "Importar",
            f"{agregados} agregado(s), {cambiados} actualizado(s)."
            + (f"\n{len(conflictos) - cambiados} sin tocar." if conflictos and not cambiados else ""),
        )

    def _contacto_borrar(self):
        nombre = self.contacto_vars["nombre"].get().strip()
        if not nombre:
            messagebox.showinfo("Borrar", "Elegi un contacto de la lista primero.")
            return
        if not messagebox.askyesno("Borrar", f"Borrar a {nombre} de la agenda?"):
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
            text="Voces entrenadas por la comunidad (Piper). Gratis, offline, y las unicas\n"
            "que suenan igual en Windows, macOS y Linux. Se verifica el md5 al descargar.",
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        barra = ttk.Frame(t)
        barra.pack(fill="x", padx=12)
        ttk.Label(barra, text="Idioma").pack(side="left")
        self.voz_idioma = tk.StringVar(value="Spanish")
        self.voz_combo = ttk.Combobox(barra, textvariable=self.voz_idioma, width=22, state="readonly")
        self.voz_combo.pack(side="left", padx=6)
        ttk.Button(barra, text="Buscar", command=self.voces_buscar).pack(side="left")
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
        ttk.Button(botones, text="Descargar", command=self.voz_descargar).pack(side="left")
        ttk.Button(botones, text="Usar esta", command=self.voz_usar).pack(side="left", padx=6)
        ttk.Button(botones, text="Probar", command=self.voz_probar).pack(side="left")
        ttk.Button(botones, text="Borrar", command=self.voz_borrar).pack(side="left", padx=6)
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
            messagebox.showinfo("Voz", "Elegi una variante primero.", parent=self)
            return
        if clave not in voices.instaladas():
            try:
                messagebox.showinfo("Voz", voices.descargar(clave), parent=self)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Voz", f"No pude bajarla: {exc}", parent=self)
                return
        self.vars["piper_voice"].set(clave)
        self.vars["tts_provider"].set("piper")
        messagebox.showinfo("Voz", f"Voz puesta en {clave}. Guarda para aplicarlo.",
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
        self.voz_estado.config(text="consultando catalogo...")

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
            messagebox.showinfo("Voces", "Elegi una voz de la lista.")
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
            self._ui(lambda: (messagebox.showinfo("Voces", msg), self.voces_buscar()))

        threading.Thread(target=work, daemon=True).start()

    def voz_usar(self):
        from . import voices

        key = self._voz_sel()
        if key not in voices.instaladas():
            messagebox.showinfo("Voces", "Descargala primero.")
            return
        self.vars["piper_voice"].set(key)
        self.vars["tts_provider"].set("piper")
        messagebox.showinfo("Voces", f"{key} seleccionada.\nToca Guardar para aplicarla.")

    def voz_probar(self):
        from . import voices

        key = self._voz_sel() or self.cfg.get("piper_voice", "")
        if key not in voices.instaladas():
            messagebox.showinfo("Voces", "Descargala primero.")
            return

        def work():
            try:
                voices.reproducir(
                    voices.hablar(f"Hola, soy {self.cfg['assistant_name']}. Asi sueno.", key)
                )
            except Exception as exc:  # noqa: BLE001
                fallo = str(exc)
                self._ui(lambda: messagebox.showerror("Voces", fallo))

        threading.Thread(target=work, daemon=True).start()

    def voz_borrar(self):
        from . import voices

        key = self._voz_sel()
        if key and messagebox.askyesno("Voces", f"Borrar {key}?"):
            messagebox.showinfo("Voces", voices.borrar(key))
            self.voces_buscar()

    def _bloque_correo(self, nb):
        """Tab propio: junto con Claves no entraba en la ventana."""
        t = ttk.Frame(nb)

        out = ttk.LabelFrame(t, text="Outlook")
        out.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(
            out,
            text="No necesita ninguna clave: Eve usa la sesion que ya tiene Outlook en esta PC.",
            foreground="#666",
        ).pack(anchor="w", padx=10, pady=(8, 4))
        self.outlook_label = ttk.Label(out, text="consultando...", justify="left")
        self.outlook_label.pack(anchor="w", padx=10)
        fila = ttk.Frame(out)
        fila.pack(anchor="w", padx=10, pady=(6, 10))
        ttk.Button(fila, text="Agregar / gestionar cuentas", command=self.outlook_login).pack(
            side="left"
        )
        ttk.Button(fila, text="Actualizar", command=self.refresh_outlook).pack(side="left", padx=6)

        gm = ttk.LabelFrame(t, text="Gmail")
        gm.pack(fill="x", padx=12, pady=6)
        ttk.Label(
            gm,
            text="Lo mas simple es agregarlo a Outlook con el boton de arriba: Google hace el\n"
            "login y no queda ninguna clave tuya guardada aca.\n\n"
            "La otra via es una contrasena de aplicacion (16 letras minusculas). Si Google\n"
            "dice que no esta disponible, es que tu cuenta no tiene verificacion en dos\n"
            "pasos, o la administra tu organizacion.",
            foreground="#666",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(8, 4))
        self._row(gm, "Tu direccion de Gmail", "gmail_address", width=38)
        self._campo_clave(gm, "gmail", "Contrasena de aplicacion")
        self.gmail_label = ttk.Label(gm, text="", justify="left")
        self.gmail_label.pack(anchor="w", padx=12, pady=(6, 0))
        fila2 = ttk.Frame(gm)
        fila2.pack(anchor="w", padx=12, pady=(6, 10))
        ttk.Button(fila2, text="Obtener app password", command=self.gmail_login).pack(side="left")
        ttk.Button(fila2, text="Probar conexion", command=self.gmail_probar).pack(side="left", padx=6)

        self.after(200, self.refresh_outlook)
        return t

    def _bloque_voz(self, nb):
        t = ttk.Frame(nb)
        self._row(t, "STT (reconocimiento)", "stt_provider",
                  ["faster-whisper", "parakeet", "openai"])
        self._row(t, "Parakeet: cuantizacion", "parakeet_cuantizacion", ["int8", ""])
        self._ayuda(
            t,
            "parakeet es el modelo de NVIDIA. Entro porque gano medido sobre las\n"
            "mismas 24 grabaciones, con la misma cuenta:\n"
            "  whisper small en gpu   WER 10.9%   RTF 0.27    464 MB\n"
            "  whisper small en cpu   WER 10.9%   RTF 1.38    464 MB\n"
            "  whisper medium en gpu  WER  5.4%   RTF 0.61    1.5 GB\n"
            "  parakeet int8 en CPU   WER  7.1%   RTF 0.19    639 MB\n"
            "Lo que importa no es el punto y medio de WER: es que ese 0.19 es EN\n"
            "CPU. Whisper small tarda siete veces mas sin GPU, y la mayoria de las\n"
            "instalaciones no tienen CUDA configurado.\n"
            "\nDonde pierde: nombres propios, 30.4% contra 21.7%, que es justo el\n"
            "grupo que decide si abre el programa correcto -- no acepta el sesgo\n"
            "de vocabulario que si acepta whisper. Por eso no es el default.\n"
            "Sin cuantizar mejora los nombres propios pero pesa 2.4 GB.")
        self._row(t, "Modelo Whisper local", "stt_model",
                  ["tiny", "base", "small", "medium", "large-v3"])
        self._row(t, "Dispositivo", "stt_device", ["cpu", "cuda"])
        self._row(t, "Tipo de computo", "stt_computo",
                  ["auto", "int8", "int8_float32", "int8_float16", "float16", "float32"])
        self._check(t, "Recortar silencios antes de transcribir (VAD)", "stt_vad")
        self._row(t, "Sensibilidad", "stt_sensibilidad",
                  ["auto", "normal", "ruido", "bajo", "manual"])
        self._row(t, "Reglas por horario", "stt_horario", width=40)
        self._ayuda(
            t,
            "Como escuchar. Los numeros salen de medir 24 grabaciones propias:\n"
            "  normal  cuarto tranquilo         WER 10.9%  (con ruido 12.5%)\n"
            "  ruido   musica o el juego atras  WER  8.7%  (con ruido  0.0%)\n"
            "  bajo    de madrugada, voz suave  WER 12.0%  (con ruido 18.8%)\n"
            "  manual  usa el umbral y el aire de mas abajo\n"
            "Las reglas de horario van separadas por coma y solo pisan a 'auto':\n"
            "  00:00-06:00=bajo, 20:00-23:59=ruido\n"
            "Si elegis un modo a mano, el reloj no te lo cambia.")
        self._row(t, "Umbral del detector", "stt_vad_umbral", width=10)
        self._row(t, "Aire del detector (ms)", "stt_vad_aire_ms", width=10)
        self._check(t, "Activar diciendo una palabra (deja el microfono abierto)",
                    "wake_activo")
        self._row(t, "Palabra para despertarla", "wake_palabra", width=20)
        self._row(t, "Modelo de la puerta", "wake_modelo", ["tiny", "base", "small"])
        self._ayuda(
            t,
            "Apagado de fabrica: prenderlo deja el microfono abierto todo el\n"
            "tiempo. Decile el nombre y la orden de un tirón, en la misma frase:\n"
            "  \"Eve, abri Spotify\"\n"
            "El nombre tiene que ir al principio. Aceptarlo en cualquier lado\n"
            "convertiria en orden cualquier charla que te lo mencione.\n"
            "\nNo corre ningun modelo de lenguaje en reposo: primero un detector\n"
            "de voz de 1.2 MB que ya viaja en el paquete decide si hay alguien\n"
            "hablando --medido, 0.20% de un core-- y recien sobre ese pedazo\n"
            "corre el modelo de la puerta. Ese es chico a proposito: solo tiene\n"
            "que reconocer una palabra que ya conoce.\n"
            "\nLa palabra pesa mas que el modelo. Medido, 4 ordenes y 6 frases\n"
            "de control que NO tienen que despertarla:\n"
            "  Computadora  tiny   desperto 4/4    falsos 0/6\n"
            "  Eve          small  desperto 3/4    falsos 0/6\n"
            "  Eve          tiny   desperto 2/4    falsos 0/6\n"
            "Tres letras no alcanzan para ser una puerta. Por eso se aceptan\n"
            "variantes separadas por |, y de fabrica vienen las dos. Para ver\n"
            "como te escribe a vos:  Eve --probar-voz \"Eve, abri Spotify\"")
        ttk.Label(
            t,
            text="cuda necesita las librerias de NVIDIA instaladas; si faltan, cae a cpu\n"
            "solo y avisa. Medido en una GTX 1660 SUPER: 3.42s por orden en cpu\n"
            "contra 0.71s en gpu. 'auto' elige int8 en cpu e int8_float16 en gpu.\n"
            "\nQue modelo conviene, medido sobre el banco de voz:\n"
            "  small     WER 10.9%   0.9s por orden en gpu,  3.3s en cpu\n"
            "  medium    WER  4.9%   1.8s en gpu, 10.2s en cpu  <- pedi gpu\n"
            "  large-v3  WER  4.9%   2.7s en gpu, y PEOR en nombres propios\n"
            "            (34.8% contra 17.4% de medium): mas grande no es\n"
            "            mejor aca.",
            style="Ayuda.TLabel", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))
        ttk.Button(t, text="Probar GPU", command=self.gpu_probar).pack(anchor="w", padx=12)
        self.gpu_label = ttk.Label(t, text="", style="Ayuda.TLabel", justify="left")
        self.gpu_label.pack(anchor="w", padx=12, pady=(4, 8))
        self._row(t, "TTS (voz)", "tts_provider", ["sapi", "piper", "elevenlabs"])
        self._row(t, "Voz de Piper", "piper_voice")
        self._row(t, "Velocidad (1.0 = normal, mas = mas lento)", "piper_velocidad")
        self._row(t, "Volumen (1.0 = como sale del sintetizador)", "volumen")
        self._row(t, "Hablante (solo voces multi-voz)", "piper_hablante")
        self._row(t, "Voz de Windows", "tts_voice", voice.list_sapi_voices() or None)
        self._row(t, "ElevenLabs voice_id", "elevenlabs_voice_id")
        self._check(t, "Leer las respuestas en voz alta", "speak_replies")

        hab = ttk.LabelFrame(t, text="Que espanol habla")
        hab.pack(fill="x", padx=12, pady=(12, 4))
        self._row(hab, "Variante", "dialecto",
                  ["", "rioplatense", "neutro", "mexicano", "castellano"])
        ttk.Button(hab, text="Usar la voz que le corresponde",
                   command=self.voz_del_dialecto).pack(anchor="w", padx=12, pady=(0, 4))
        self._ayuda(
            hab,
            "Cambia como ESCRIBE: vos contra tu, vale contra dale. Vacio = no se\n"
            "le dice nada. Cuesta unos 40 tokens por llamada.\n"
            "\nLa voz va aparte porque no es lo mismo. Medido sobre diez frases,\n"
            "sintetizando y volviendo a transcribir --si el mejor reconocedor que\n"
            "hay no la entiende, vos con el juego de fondo tampoco:\n"
            "  es_ES-sharvard-medium   6.4%     es_ES-carlfm-x_low  10.0%\n"
            "  es_MX-claude-high       6.8%     es_MX-ald-medium    10.4%\n"
            "  es_ES-davefx-medium     8.4%     es_MX-ald-x_low     11.2%\n"
            "                                   es_AR-daniela-high  20.5%\n"
            "Es la media de tres corridas, y hacen falta las tres: Piper no es\n"
            "determinista y una misma voz se mueve hasta 8 puntos. Con una sola\n"
            "medicion casi todo este orden seria ruido.\n"
            "Lo que sobrevive: es_AR-daniela-high es la peor por mucho y la mas\n"
            "lenta por cinco veces. Por eso hasta la variante rioplatense\n"
            "sugiere una voz mexicana: la voz es el canal, no el acento del que\n"
            "habla. Si igual la queres, elegila a mano en Voz de Piper.")

        pers = ttk.LabelFrame(t, text="Personalidad")
        pers.pack(fill="x", padx=12, pady=(12, 4))
        self._row(pers, "Tono", "persona_tono", width=44)
        ttk.Label(
            pers,
            text="Como habla, no que hace. Va al final del prompt y siempre pierde\n"
                 "contra el manual: no puede hacerla hablar de mas ni narrar en vez\n"
                 "de actuar. Vacio = sin personaje. Lo setea cada perfil.",
            style="Ayuda.TLabel", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        box = ttk.LabelFrame(t, text="Programas que Eve conoce")
        box.pack(fill="x", padx=12, pady=(12, 4))
        self.apps_label = ttk.Label(box, text="", justify="left")
        self.apps_label.pack(anchor="w", padx=10, pady=(8, 4))
        self._row(box, "Vocabulario extra", "stt_vocabulary", width=40)
        ttk.Label(
            box,
            text="Nombres que el reconocimiento suele errar, separados por comas.",
            foreground="#666",
        ).pack(anchor="w", padx=12)
        ttk.Button(box, text="Reescanear programas", command=self.rescan_apps).pack(
            anchor="w", padx=12, pady=(6, 10)
        )
        self.refresh_apps(scan=False)
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
        messagebox.showinfo("Programas", "Indice actualizado.")

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

        boton = ttk.Button(fila, text="Elegir...", command=elegir, width=10)
        boton.pack(side="left")
        var.trace_add("write", repintar)
        var.trace_add("write", self._previa_redibujar)
        repintar()
        self._filas_color.append((prefijo, (entrada, boton)))

    def _bloque_tema(self, nb):
        from . import tema

        t = ttk.Frame(nb)
        caja = self._seccion(t, "Colores del panel")
        self._row(caja, "Tema", "ui_tema", tema.NOMBRES)
        self._check(caja, "Pintar tambien este panel con el tema", "ui_pintar_panel")
        self._ayuda(
            caja,
            "Pintar el panel obliga a dibujar los controles por nuestra cuenta: Windows\n"
            "no deja cambiarle el color a los suyos. El cambio se ve al instante.",
        )
        for rol, etiqueta in ROLES_ETIQUETA:
            self._fila_color(caja, "ui", rol, etiqueta)
        self._ayuda(caja, "Los colores de arriba solo se usan con el tema 'personalizado'.")

        self._check(caja, "No animar los GIF (dejar el primer cuadro)", "ui_sin_animacion")
        self.vars["ui_sin_animacion"].trace_add("write", self._previa_redibujar)

        caja = self._seccion(t, "Tipografia")
        self._row(caja, "Fuente del panel", "ui_fuente", tema.fuentes_disponibles())
        self._row(caja, "Tamaño (0 = el de la fuente)", "ui_fuente_tam")
        self._row(caja, "Fuente del cartel", "hud_fuente", tema.fuentes_disponibles())
        self._row(caja, "Fuente de los subtitulos", "sub_fuente", tema.fuentes_disponibles())
        for clave in ("ui_fuente", "ui_fuente_tam", "hud_fuente", "sub_fuente"):
            self.vars[clave].trace_add("write", self._previa_redibujar)

        # Los ocho colores del cartel se sacaron de aca: eran una segunda tanda
        # identica a la de arriba, y para lo unico que servian era para que el
        # cartel se viera distinto del panel, que ya se resuelve eligiendole
        # otro tema. Las claves hud_color_* siguen andando si alguien las edita
        # a mano; lo que se fue es la pared de campos repetidos.

        caja = self._seccion(t, "Cabecera del panel")
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=5)
        ttk.Label(fila, text="Imagen (PNG o GIF)", width=24).pack(side="left")
        var = tk.StringVar(value=str(self.cfg.get("ui_banner", "")))
        self.vars["ui_banner"] = var
        ttk.Entry(fila, textvariable=var).pack(side="left", fill="x", expand=True)

        def elegir_banner():
            from tkinter import filedialog

            ruta = filedialog.askopenfilename(
                title="Imagen de cabecera", parent=self,
                filetypes=[("Imagenes y sprite sheets",
                            "*.png *.gif *.webp *.apng *.jpg *.jpeg *.bmp"),
                       ("Todos", "*.*")],
            )
            if ruta:
                var.set(ruta)

        ttk.Button(fila, text="...", width=4,
                   command=elegir_banner).pack(side="left", padx=(6, 0))
        ttk.Button(fila, text="Quitar", width=8,
                   command=lambda: var.set("")).pack(side="left", padx=(4, 0))
        self._row(caja, "Opacidad (%)", "ui_banner_opacidad")
        self._ayuda(
            caja,
            "Se ve arriba de cada pestaña y se aplica al reabrir el panel. No hay fondo\n"
            "para todo el panel: los controles de Windows pintan su propio fondo opaco\n"
            "y lo taparian.",
        )

        for clave in ("ui_tema",):
            self.vars[clave].trace_add("write", self._previa_redibujar)
        return t

    def _addon_ver(self, ruta: str) -> None:
        """Muestra el archivo entero antes de aprobarlo."""
        from . import integrations

        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                codigo = f.read()
        except OSError as exc:
            messagebox.showerror("No pude leerlo", str(exc))
            return
        integrations.mostrar(os.path.basename(ruta), codigo)

    def _addon_aprobar(self, nombre: str, marca: str) -> None:
        if not messagebox.askyesno(
            "Aprobar addon",
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
        messagebox.showinfo("Listo", "Cerra y abri el panel para verlo cargado.")

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

        lista = self._seccion(t, "Modulos")
        self._ayuda(
            lista,
            "Cada modulo es una pieza del cartel: un icono, una onda, particulas,\n"
            "el reloj o el medidor de contexto. Se puede elegir donde va, de que\n"
            "tamano, con cuanta transparencia y cuando se muestra.",
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
        ttk.Button(fila, text="Agregar", command=self._mods_agregar).pack(side="left", padx=6)
        ttk.Button(fila, text="Duplicar", command=self._mods_duplicar).pack(side="left")
        ttk.Button(fila, text="Borrar", command=self._mods_borrar).pack(side="left", padx=6)
        ttk.Button(fila, text="Traer los del cartel actual",
                   command=self._mods_semilla).pack(side="left", padx=(18, 0))

        fila2 = ttk.Frame(lista)
        fila2.pack(anchor="w", padx=12, pady=(0, 10))
        ttk.Button(fila2, text="Armar el tablero de arranque",
                   command=self._mods_semilla_tablero).pack(side="left")
        ttk.Button(fila2, text="Abrir la ventana de actividad",
                   command=self._abrir_consola).pack(side="left", padx=6)
        self._ayuda(fila2, "  ahi se acomodan los modulos del tablero con el mouse")

        self.mod_caja = self._seccion(t, "Ajustes del modulo")
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
        self.estado.config(text="tablero armado: abri la ventana de actividad")

    def _abrir_consola(self) -> None:
        from . import consola

        consola.abrir()
        self.estado.config(text="ventana de actividad abierta")

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
            self._ayuda(self.mod_props, "Elegi un modulo de la lista para ajustarlo.")
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
        ttk.Button(pie, text="Aplicar", command=self._mods_aplicar).pack(side="left")
        if modulo["tipo"] == "particulas":
            ttk.Button(pie, text="Importar .plist",
                       command=self._mods_plist).pack(side="left", padx=8)
            self._ayuda(
                self.mod_props,
                "Los editores de particulas --Particle Designer, Particle2dx--\n"
                "exportan el .plist de cocos2d, que es XML de numeros: vida,\n"
                "gravedad, color, velocidad. Se importa la CONFIGURACION y la\n"
                "corre el simulador que ya esta, asi que no entra ninguna\n"
                "libreria nueva. Llena los campos de arriba; despues Aplicar.\n"
                "No viaja lo que el simulador no sabe hacer: modo radial,\n"
                "texturas por particula y mezclas aditivas.")

    def _mods_plist(self) -> None:
        """Trae los parametros de un .plist al formulario, sin guardarlos.

        Llena los campos y no aplica: importar es proponer valores, y que un
        archivo ajeno pise el modulo sin que lo veas es la misma sorpresa que el
        ajuste de autoridad existe para evitar.
        """
        from tkinter import filedialog, messagebox

        from . import modulos as mods

        ruta = filedialog.askopenfilename(
            title="Particulas de Particle Designer", parent=self,
            filetypes=[("Particulas", "*.plist"), ("Todos", "*.*")])
        if not ruta:
            return
        props = mods.desde_plist(ruta)
        if not props:
            messagebox.showerror(
                "Particulas",
                "No pude leer ese archivo. Tiene que ser un .plist de cocos2d "
                "(el que exportan Particle Designer y Particle2dx).", parent=self)
            return
        traidas = [p for p in props if p in self.mod_vars]
        for prop in traidas:
            self.mod_vars[prop].set(str(props[prop]))
        messagebox.showinfo(
            "Particulas",
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
                    messagebox.showerror("Valor invalido", f"'{prop}' tiene que ser un numero.")
                    return
            elif isinstance(defecto, float):
                try:
                    modulo[prop] = float(str(valor).replace(",", "."))
                except ValueError:
                    messagebox.showerror("Valor invalido", f"'{prop}' tiene que ser un numero.")
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
        self.estado.config(text="listo: el cartel de siempre, ahora como modulos")

    def _bloque_hud(self, nb):
        from . import tema

        t = ttk.Frame(nb)
        caja = self._seccion(t, "Cartel en pantalla")
        self._row(caja, "Cuando se ve", "overlay_modo", ["auto", "siempre", "nunca"])
        # El tema del cartel vive aca, junto a lo demas del cartel, y no
        # mezclado con los colores del panel.
        self._row(caja, "Tema (vacio = el del panel)", "hud_tema", ["", *tema.NOMBRES])
        self.vars["hud_tema"].trace_add("write", self._previa_redibujar)
        self._ayuda(
            caja,
            "auto = aparece al hablarle y se va sola. Nunca se lleva el foco de lo que\n"
            "estes haciendo, y los clics la atraviesan.",
        )
        self._row(caja, "Titulo (vacio = nombre IA)", "hud_titulo")
        self._row(caja, "Segunda linea", "hud_subtitulo")
        self._row(caja, "Icono", "hud_icono", ["hexagono", "ninguno"])
        self._row(caja, "Contorno", "hud_contorno",
                  ["ninguno", "linea", "esquinas", "doble", "hexagonal", "biselado"])
        self._row(caja, "Onda", "hud_onda",
                  ["barras", "espejo", "linea", "puntos", "ninguna"])
        self._row(caja, "Escala (%)", "hud_escala")
        self._row(caja, "Opacidad (%)", "hud_opacidad")
        self._ayuda(
            caja,
            "Menos de 10 se trata como 10: por debajo de eso el cartel no se ve\n"
            "y no habria forma de encontrarlo para subirlo de nuevo. La opacidad\n"
            "de cada modulo se MULTIPLICA con esta, asi que 20% de ventana por\n"
            "20% de modulo da 4% de verdad.")

        self._row(caja, "Pantalla", "overlay_pantalla", self._pantallas())
        self._row(caja, "Area", "overlay_area", ["trabajo", "completa"])
        self._ayuda(
            caja,
            "0 = donde lo dejes, sin restriccion, y podes arrastrarlo de un\n"
            "monitor al otro. 1 en adelante lo fija a ese monitor y lo mantiene\n"
            "adentro aunque lo arrastres. Si desenchufas el que elegiste, vuelve\n"
            "al escritorio entero en vez de quedar en un lugar que no existe.\n"
            "'trabajo' descuenta la barra de tareas; solo cambia algo en Windows.")

        self._row(caja, "Toma clics", "overlay_clics", ["nunca", "hover", "fijo"])
        self._ayuda(
            caja,
            "El cartel normalmente deja pasar los clics al programa de atras.\n"
            "  nunca   nunca los toma\n"
            "  hover   solo mientras el puntero esta sobre un modulo marcado\n"
            "          como 'interactivo'; si no marcaste ninguno, es igual\n"
            "          que 'nunca'\n"
            "  fijo    siempre los toma, y siempre tapa lo que este debajo\n"
            "Se pregunta donde esta el puntero treinta veces por segundo en vez\n"
            "de escuchar eventos, porque una ventana que deja pasar los clics\n"
            "tampoco recibe los de movimiento: esperarlos seria esperar para\n"
            "siempre. Ese mismo poll es el que hace andar 'cuando = hover'.")

        self._row(caja, "Forma", "hud_forma", ["caja", "recortado"])
        self._ayuda(
            caja,
            "recortado = el cartel deja de ser un rectangulo y por las esquinas cortadas\n"
            "de los contornos hexagonal y biselado se ve lo que hay atras.",
        )

        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(6, 10))
        ttk.Button(fila, text="Elegir imagen del icono...",
                   command=self._icono_elegir).pack(side="left")
        ttk.Button(fila, text="Mover en pantalla",
                   command=self._overlay_mover).pack(side="left", padx=6)
        ttk.Button(fila, text="Volver a la esquina",
                   command=self._overlay_esquina).pack(side="left")

        caja = self._seccion(t, "Marco del icono")
        self._ayuda(
            caja,
            "El marco es parametrico: elegis cuantos lados, cuanto gira y cuanto se\n"
            "redondean las puntas. Las formas de abajo son atajos que llenan esos\n"
            "numeros; despues los podes tocar a mano.",
        )
        fila = ttk.Frame(caja)
        fila.pack(fill="x", padx=12, pady=(4, 8))
        ttk.Label(fila, text="Formas", width=24).pack(side="left")
        self.forma_var = tk.StringVar()
        combo = ttk.Combobox(fila, textvariable=self.forma_var,
                             values=sorted(overlay_formas()), state="readonly")
        combo.pack(side="left", fill="x", expand=True)
        combo.bind("<<ComboboxSelected>>", self._forma_elegida)
        self._row(caja, "Lados (menos de 3 = circulo)", "hud_marco_lados")
        self._row(caja, "Giro (grados)", "hud_marco_rot")
        self._row(caja, "Redondeo de las puntas", "hud_marco_redondeo")
        self._row(caja, "Grosor del trazo", "hud_marco_grosor")
        for clave in ("hud_marco_lados", "hud_marco_rot", "hud_marco_redondeo",
                      "hud_marco_grosor"):
            self.vars[clave].trace_add("write", self._previa_redibujar)

        self._bloque_fondo(t, "hud", "Fondo del cartel")
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
        ttk.Label(fila, text="Imagen (PNG o GIF)", width=24).pack(side="left")
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
        ttk.Button(fila, text="Quitar", width=8,
                   command=lambda: var.set("")).pack(side="left", padx=(4, 0))

        self._row(caja, "Ajuste", f"{prefijo}_fondo_ajuste",
                  ["recortar", "estirar", "mosaico"])
        self._row(caja, "Opacidad de la imagen (%)", f"{prefijo}_fondo_opacidad")
        self._row(caja, "Tinte con el acento (%)", f"{prefijo}_fondo_tinte")
        self._ayuda(
            caja,
            "El GIF se anima solo. La opacidad se mezcla en la imagen y no en la ventana,\n"
            "asi que bajarla atenua el fondo pero el texto sigue entero.",
        )
        self._row(caja, "Degradado (si no hay imagen)", f"{prefijo}_grad",
                  ["ninguno", "vertical", "horizontal", "diagonal", "radial"])
        self._fila_color_libre(caja, f"{prefijo}_grad_a", "Degradado: color 1")
        self._fila_color_libre(caja, f"{prefijo}_grad_b", "Degradado: color 2")
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

        ttk.Button(fila, text="Elegir...", command=elegir, width=10).pack(side="left")
        var.trace_add("write", repintar)
        repintar()

    def _icono_elegir(self):
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(
            title="Imagen para el icono", parent=self,
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
            "Mover el cartel",
            "El cartel esta suelto: arrastralo a donde quieras y soltalo.\n\n"
            "Al soltarlo se guarda la posicion y vuelve a dejar pasar los clics.",
        )

    def _overlay_esquina(self):
        self.vars["hud_x"].set("40") if "hud_x" in self.vars else None
        cfg = store.load_config()
        cfg.update({"hud_x": 40, "hud_y": 40})
        store.save_config(cfg)
        self.cfg.update({"hud_x": 40, "hud_y": 40})
        messagebox.showinfo("Posicion", "El cartel vuelve a la esquina de arriba a la izquierda.")

    def _bloque_subtitulos(self, nb):
        t = ttk.Frame(nb)
        caja = self._seccion(t, "Subtitulos")
        self._row(caja, "Que se muestra", "sub_muestra", ["ambos", "eve", "usuario"])
        self._ayuda(
            caja,
            "ambos = lo que dijiste vos (para ver si te entendio) y lo que responde Eve,\n"
            "revelandose mientras lo dice.",
        )
        self._row(caja, "Tamano de letra", "sub_tam")
        self._row(caja, "Lineas maximas", "sub_lineas")
        self._row(caja, "Opacidad (%)", "sub_opacidad")
        self._row(caja, "Separacion del cartel (px)", "sub_separacion")
        self._bloque_fondo(t, "sub", "Fondo de los subtitulos")
        return t

    def _bloque_historial(self, nb):
        t = ttk.Frame(nb)
        bar = ttk.Frame(t)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Button(bar, text="Limpiar historial", command=self.clear_history).pack(side="left")
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
            "Limpiar historial",
            "Borra la conversacion guardada y deja la ventana de contexto en cero.\n\n"
            "El registro de acciones (pestaña Acciones) NO se toca.\n\n"
            "Si el listener esta corriendo, usa tambien la bandeja > 'Limpiar historial y\n"
            "contexto' para vaciar lo que ya tiene en memoria.\n\nBorrar?",
        ):
            return
        n = store.clear_history()
        self.refresh_history()
        messagebox.showinfo("Limpiar historial", f"{n} mensajes borrados.")

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
        self.outlook_label.config(text="consultando...")

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

        messagebox.showinfo("Outlook", integrations.outlook_agregar_cuenta())

    def gmail_login(self):
        import webbrowser

        webbrowser.open("https://myaccount.google.com/apppasswords")
        messagebox.showinfo(
            "Gmail",
            "Te abri la pagina de contrasenas de aplicacion.\n\n"
            "Si dice que no esta disponible para tu cuenta, es porque no tenes\n"
            "verificacion en dos pasos activada, o la administra tu organizacion.\n\n"
            "En ese caso usa el boton de Outlook: agregas el Gmail ahi y listo.",
        )

    def gmail_probar(self):
        self.gmail_label.config(text="probando...")

        def work():
            from . import integrations

            texto = integrations.gmail_probar()
            self._ui(lambda: self.gmail_label.config(text=texto))

        threading.Thread(target=work, daemon=True).start()

    def gpu_probar(self):
        """Carga el modelo en la GPU y transcribe algo, en un hilo.

        Elegir 'cuda' en el desplegable no daba ninguna senal: si faltaba una
        DLL, Eve caia a CPU sola y en silencio, y la unica pista era que seguia
        tardando lo mismo. Esto contesta antes de hablarle.
        """
        self.gpu_label.config(text="probando, puede tardar unos segundos...")

        def work():
            texto = voice.probar_gpu(store.load_config())
            self._ui(lambda: self.gpu_label.config(text=texto))

        threading.Thread(target=work, daemon=True).start()

    # --- sesion de Claude Code ---------------------------------------------

    def refresh_auth(self):
        """Lee `claude auth status` en un hilo: el CLI tarda ~1s y congelaria la GUI."""
        self.auth_label.config(text="consultando...")

        def work():
            text = _auth_status()
            self._ui(lambda: self.auth_label.config(text=text))

        threading.Thread(target=work, daemon=True).start()

    def auth_login(self):
        if not shutil.which("claude"):
            messagebox.showerror("Falta el CLI", "No encontre 'claude' en el PATH.")
            return
        # Consola nueva: el login es interactivo (abre el navegador y espera).
        subprocess.Popen(["claude", "auth", "login"], creationflags=CREATE_NEW_CONSOLE)
        messagebox.showinfo(
            "Iniciar sesion",
            "Se abrio una consola con el login de Claude Code.\n"
            "Cuando termines, tocá 'Actualizar' para ver el estado.",
        )

    def auth_logout(self):
        if not messagebox.askyesno(
            "Cerrar sesion",
            "Esto cierra tu sesion de Claude Code en toda la PC, no solo en Eve.\n\n"
            "El motor 'claude-code' va a dejar de funcionar hasta que vuelvas a entrar.\n\nSeguro?",
        ):
            return
        r = plataforma.correr(["claude", "auth", "logout"], capture_output=True, text=True, timeout=60)
        messagebox.showinfo("Cerrar sesion", (r.stdout or r.stderr or "Sesion cerrada.").strip()[:500])
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
                    messagebox.showerror("Valor invalido", f"'{key}' debe ser un numero entero.")
                    return
            elif isinstance(default, float):
                # Sin esta rama la velocidad se guardaba como texto: funcionaba
                # igual porque quien la lee la convierte, pero el tipo se iba
                # cambiando solo en cada guardado.
                try:
                    cfg[key] = float(str(value).replace(",", "."))
                except ValueError:
                    messagebox.showerror("Valor invalido", f"'{key}' debe ser un numero.")
                    return
            else:
                cfg[key] = value
        cfg["workdirs"] = [
            line.strip() for line in self.workdirs.get("1.0", "end").splitlines() if line.strip()
        ]
        if not cfg["workdirs"]:
            messagebox.showerror(
                "Rutas vacias", "Necesitas al menos una ruta de trabajo permitida."
            )
            return

        allow_all = self.perm_var.get() == PERM_ALL
        if allow_all and self.cfg.get("confirm_destructive", True):  # recien lo activa
            if not messagebox.askyesno(
                "Permitir todo",
                "Eve va a ejecutar cualquier comando que decida, sin preguntarte:\n"
                "borrar carpetas, apagar la PC, modificar el registro.\n\n"
                "El reconocimiento de voz se equivoca, y en este modo un error de\n"
                "transcripcion se ejecuta directo.\n\n"
                "Queda registrado en la pestaña Acciones, pero nada lo va a frenar.\n\n"
                "Activar igual?",
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
                    "Eso no parece una app password",
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
                "Guardado",
                "Configuracion guardada.\n\nSi el listener esta corriendo, aplica los\n"
                "cambios solo en unos segundos. Los de aspecto no le cortan la\n"
                "conversacion; los de motor o tecla si lo rearman.",
            )


if __name__ == "__main__":
    Panel().mainloop()
