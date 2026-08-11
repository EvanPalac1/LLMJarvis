"""Panel de configuracion. Se abre solo cuando el usuario hace click en la bandeja.

Corre como proceso aparte (`python -m eve.gui`) para no mezclar el mainloop de
tkinter con el de pystray.
"""

import json
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import store, voice

CREATE_NEW_CONSOLE = 0x00000010

def _parece_app_password(valor: str) -> bool:
    """Google las emite como 16 letras minusculas en 4 grupos de 4."""
    limpio = valor.replace(" ", "")
    return len(limpio) == 16 and limpio.isalpha() and limpio.islower()


PERM_ASK = "Preguntar antes de acciones riesgosas (recomendado)"
PERM_ALL = "Permitir todo sin preguntar"


def _auth_status() -> str:
    if not shutil.which("claude"):
        return "CLI 'claude' no encontrado en el PATH."
    try:
        r = subprocess.run(
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

MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
CC_MODELS = ["opus", "sonnet", "haiku"]
CC_MODES = ["acceptEdits", "auto", "manual"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = store.load_config()
        self.title("LLMJarvis - configuracion")
        self.geometry("800x790")
        self.minsize(640, 420)

        # El pie va PRIMERO y anclado abajo: pack reparte en orden de empaquetado,
        # asi que si el notebook va antes, empuja el boton Guardar fuera de la
        # ventana en cuanto una pestaña crece.
        footer = ttk.Frame(self)
        footer.pack(side="bottom", fill="x", pady=(0, 8))
        ttk.Label(
            footer,
            text="Guardar aplica los cambios solo: el listener detecta el guardado y se\n"
            "reinicia en unos segundos. No hace falta tocar nada mas.",
            foreground="#666",
        ).pack(side="bottom", pady=(4, 0))
        ttk.Button(footer, text="Guardar", command=self.save).pack(side="bottom")

        nb = ttk.Notebook(self)
        nb.pack(side="top", fill="both", expand=True, padx=8, pady=8)
        self.vars: dict[str, tk.Variable] = {}
        self.key_vars: dict[str, tk.Variable] = {}
        nb.add(self._tab_general(nb), text="General")
        nb.add(self._tab_keys(nb), text="Claves")
        nb.add(self._tab_correo(nb), text="Correo")
        nb.add(self._tab_contactos(nb), text="Contactos")
        nb.add(self._tab_voice(nb), text="Voz")
        nb.add(self._tab_voces(nb), text="Voces")
        nb.add(self._tab_history(nb), text="Historial")
        nb.add(self._tab_actions(nb), text="Acciones")

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

    def _tab_general(self, nb):
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

    def _tab_keys(self, nb):
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

    def _tab_contactos(self, nb):
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

    def _tab_voces(self, nb):
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
                self.after(0, lambda: self.voz_estado.config(text=f"error: {exc}"))
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

            self.after(0, pintar)

        threading.Thread(target=work, daemon=True).start()

    def voz_descargar(self):
        key = self._voz_sel()
        if not key:
            messagebox.showinfo("Voces", "Elegi una voz de la lista.")
            return

        def work():
            from . import voices

            self.after(0, lambda: self.voz_estado.config(text=f"descargando {key}..."))
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
            self.after(0, lambda: (messagebox.showinfo("Voces", msg), self.voces_buscar()))

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
                self.after(0, lambda: messagebox.showerror("Voces", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def voz_borrar(self):
        from . import voices

        key = self._voz_sel()
        if key and messagebox.askyesno("Voces", f"Borrar {key}?"):
            messagebox.showinfo("Voces", voices.borrar(key))
            self.voces_buscar()

    def _tab_correo(self, nb):
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

    def _tab_voice(self, nb):
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

    def _tab_history(self, nb):
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

    def _tab_actions(self, nb):
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
            self.after(0, lambda: self.outlook_label.config(text=texto))

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
            self.after(0, lambda: self.gmail_label.config(text=texto))

        threading.Thread(target=work, daemon=True).start()

    # --- sesion de Claude Code ---------------------------------------------

    def refresh_auth(self):
        """Lee `claude auth status` en un hilo: el CLI tarda ~1s y congelaria la GUI."""
        self.auth_label.config(text="consultando...")

        def work():
            text = _auth_status()
            self.after(0, lambda: self.auth_label.config(text=text))

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
        r = subprocess.run(["claude", "auth", "logout"], capture_output=True, text=True, timeout=60)
        messagebox.showinfo("Cerrar sesion", (r.stdout or r.stderr or "Sesion cerrada.").strip()[:500])
        self.refresh_auth()

    # --- guardar -----------------------------------------------------------

    def save(self):
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
        messagebox.showinfo(
            "Guardado",
            "Configuracion guardada.\n\nSi el listener esta corriendo, se reinicia solo\n"
            "en unos segundos con los cambios aplicados.",
        )


if __name__ == "__main__":
    Panel().mainloop()
