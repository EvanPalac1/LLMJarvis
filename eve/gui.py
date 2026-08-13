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

from . import plataforma, store, voice

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
        ttk.Button(fila, text="Guardar", command=self.save).pack(side="right")
        ttk.Button(fila, text="Buscar actualizaciones", command=self.buscar_update).pack(
            side="right", padx=(0, 6)
        )
        self.after(300, self._refrescar_estado)

        nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 6))
        self.vars: dict[str, tk.Variable] = {}
        self.key_vars: dict[str, tk.Variable] = {}
        # Cinco pestañas agrupadas por lo que uno viene a hacer, no por modulo.
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
        lienzo.bind_all("<MouseWheel>", lambda e: lienzo.yview_scroll(-e.delta // 120, "units"))
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

        try:
            self.after(3000, self._refrescar_estado)
        except tk.TclError:
            pass

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
        ttk.Button(caja, text="Abrir la carpeta de addons",
                   command=self._addons_carpeta).pack(anchor="w", padx=12, pady=(0, 10))
        return t

    def _addons_carpeta(self):
        from . import addons

        os.makedirs(addons.CARPETA_USUARIO, exist_ok=True)
        plataforma.abrir(addons.CARPETA_USUARIO)

    def _tab_apariencia(self, nb):
        return self._componer(
            nb, "Apariencia",
            "Los colores de todo, y el cartel que Eve muestra encima de lo que estes haciendo.",
            [self._bloque_tema, self._bloque_hud, self._bloque_subtitulos],
        )

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
            "Un perfil guarda TODA la configuracion de golpe: motor, tecla, permisos,\n"
            "voz y aspecto. Sirve para tener uno para jugar y otro para trabajar.\n"
            "La posicion del cartel no entra: esa es de tu pantalla, no de tu modo.",
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

        ruta = filedialog.askopenfilename(
            title="Importar perfil", parent=self,
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
        self._row(t, "Ollama: host", "ollama_host")
        self._row(t, "Ollama: modelo", "ollama_model")
        self._row(t, "Effort", "effort", EFFORTS)
        self._row(t, "Max tokens", "max_tokens")
        self._row(t, "Tecla del keypad", "hotkey")
        self._row(t, "Turnos de contexto", "context_turns")
        self._row(t, "Minutos de contexto", "context_minutes")

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
        self.contactos = [
            c for c in self.contactos if store._plano(c.get("nombre", "")) != store._plano(nombre)
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
        self._row(t, "STT (reconocimiento)", "stt_provider", ["faster-whisper", "openai"])
        self._row(t, "Modelo Whisper local", "stt_model", ["tiny", "base", "small", "medium"])
        self._row(t, "Dispositivo", "stt_device", ["cpu", "cuda"])
        self._row(t, "TTS (voz)", "tts_provider", ["sapi", "piper", "elevenlabs"])
        self._row(t, "Voz de Piper", "piper_voice")
        self._row(t, "Voz de Windows", "tts_voice", voice.list_sapi_voices() or None)
        self._row(t, "ElevenLabs voice_id", "elevenlabs_voice_id")
        self._check(t, "Leer las respuestas en voz alta", "speak_replies")

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

        self._pintor = None
        self._filas_color = []
        t = ttk.Frame(nb)

        caja = self._seccion(t, "Vista previa")
        self.previa = tk.Canvas(caja, width=460, height=128, highlightthickness=0)
        self.previa.pack(padx=12, pady=(8, 4))
        self._ayuda(caja, "Asi se ve el cartel. La escala real se aplica en pantalla.")

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

        caja = self._seccion(t, "Colores del cartel")
        self._ayuda(
            caja,
            "El cartel puede tener su propio tema. Dejalo vacio y usa el del panel.",
        )
        self._row(caja, "Tema del cartel", "hud_tema", ["", *tema.NOMBRES])
        for rol, etiqueta in ROLES_ETIQUETA:
            self._fila_color(caja, "hud", rol, etiqueta)
        self.vars["hud_tema"].trace_add("write", self._previa_redibujar)

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
                filetypes=[("Imagenes", "*.png *.gif"), ("Todos", "*.*")],
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

    def _bloque_hud(self, nb):
        t = ttk.Frame(nb)
        caja = self._seccion(t, "Cartel en pantalla")
        self._row(caja, "Cuando se ve", "overlay_modo", ["auto", "siempre", "nunca"])
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
                filetypes=[("Imagenes", "*.png *.gif"), ("Todos", "*.*")],
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
            filetypes=[("Imagenes", "*.png *.gif"), ("Todos", "*.*")],
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
        cfg = dict(self.cfg)
        for key, var in self.vars.items():
            value = var.get()
            default = store.DEFAULTS.get(key)
            if isinstance(default, bool):
                cfg[key] = bool(value)
            elif isinstance(default, int):
                try:
                    cfg[key] = int(value)
                except ValueError:
                    messagebox.showerror("Valor invalido", f"'{key}' debe ser un numero entero.")
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
