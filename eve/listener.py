"""Push-to-talk: manten la tecla del keypad, habla, solta.

Independiente del panel: el boton del keypad NUNCA abre la GUI.
"""

import os
import threading
import time
import traceback

from . import cc_engine, plataforma, store, voice


def _mtime(ruta: str) -> float:
    try:
        return os.path.getmtime(ruta)
    except OSError:
        return 0.0


def ask_yes_no(reason: str, detail: str) -> bool:
    """Dialogo modal del SO. Se llama desde hilos de fondo, no desde tkinter."""
    return plataforma.preguntar(
        f"{reason}\n\n{detail}\n\nEjecutar de todas formas?",
        "LLMJarvis - confirmar accion",
    )


class Listener:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.paused = False
        self.recorder = voice.Recorder()
        self._down = False  # filtra el autorepeat de keydown de Windows
        self._busy = False  # ignora un segundo disparo mientras procesa el anterior
        self._hook = None
        self._vista = {}  # ultimo estado mandado al overlay
        self.eve = self._build_engine()

    # --- lo que ve el usuario en pantalla ----------------------------------

    def mostrar(self, **cambios) -> None:
        """Actualiza el overlay. Acumula, asi que se manda solo lo que cambia."""
        self._vista.update(cambios)
        store.emitir_overlay(self._vista)

    def _estado(self, texto: str) -> None:
        """Lo que los motores reportan por `on_status`: sale por consola y a la
        pantalla, que es donde el usuario lo va a ver."""
        print(texto)
        self.mostrar(estado="pensando", detalle=texto.upper().rstrip(". "), nivel=0.12)

    def _build_engine(self):
        motor = self.cfg.get("engine")
        if motor == "claude-code":
            return cc_engine.ClaudeCodeEve(self.cfg, on_status=self._estado)
        if motor == "ollama":
            from . import ollama_engine

            return ollama_engine.OllamaEve(
                self.cfg, confirm=self._confirm, on_status=self._estado
            )
        from . import brain  # import perezoso: el motor CLI no necesita `anthropic`

        return brain.Eve(self.cfg, confirm=self._confirm, on_status=self._estado)

    def _confirm(self, reason: str, detail: str) -> bool:
        voice.speak(f"Necesito tu confirmacion. {reason}.", self.cfg)
        return ask_yes_no(reason, detail)

    def _on_down(self, _tecla) -> None:
        if self.paused or self._down or self._busy:
            return
        self._down = True
        try:
            self.recorder.start()
            print("[grabando]")
            self.mostrar(estado="escuchando", detalle="ESCUCHANDO", usuario="", eve="")
            threading.Thread(target=self._seguir_microfono, daemon=True).start()
        except voice.MicBusyError:
            self._down = False
            voice.speak("No puedo usar el microfono, otro programa lo tiene tomado.", self.cfg)

    def _seguir_microfono(self) -> None:
        """Manda el volumen del microfono mientras dura la grabacion.

        En un hilo aparte para no meter trabajo en el callback de audio, que
        tiene que devolver rapido o se pierden bloques.
        """
        while self._down:
            self.mostrar(nivel=self.recorder.nivel)
            time.sleep(0.1)

    def _on_up(self, _tecla) -> None:
        if not self._down:
            return
        self._down = False
        audio = self.recorder.stop()
        self._busy = True
        self.mostrar(estado="pensando", detalle="TRANSCRIBIENDO", nivel=0.1)
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio) -> None:
        try:
            text = voice.transcribe(audio, self.cfg)
            if not text:
                self.mostrar(estado="reposo", detalle="", nivel=0.0)
                return
            print(f"[usuario] {text}")
            self.mostrar(estado="pensando", detalle="PENSANDO", usuario=text, eve="")
            reply = self.eve.ask(text)
            print(f"[{self.cfg['assistant_name']}] {reply}")
            self.mostrar(estado="hablando", detalle="RESPONDIENDO", eve="")
            voice.speak(
                reply, self.cfg,
                progreso=lambda nivel, dicho: self.mostrar(nivel=nivel, eve=dicho),
            )
            # El texto completo queda a la vista aunque no se hable la respuesta.
            self.mostrar(eve=reply, nivel=0.0)
        except Exception as exc:  # noqa: BLE001 - el listener no puede morir en silencio
            traceback.print_exc()
            store.log_action("listener", "procesar audio", f"ERROR: {exc}")
            self.mostrar(estado="error", detalle="ERROR", eve=str(exc)[:200], nivel=0.0)
            voice.speak("Tuve un error procesando eso.", self.cfg)
        finally:
            self._busy = False
            self.mostrar(estado="reposo", detalle="", nivel=0.0)

    def _on_event(self, nombre: str, tipo: str) -> None:
        if nombre != self.cfg["hotkey"]:
            return
        if tipo == "down":
            self._on_down(nombre)
        else:
            self._on_up(nombre)

    def start(self) -> None:
        # Un unico hook global filtrado por nosotros, en vez de uno por tecla:
        # ver plataforma.hook_teclado para por que eso filtraba hooks.
        self._hook = plataforma.hook_teclado(self._on_event)
        print(
            f"Listener activo en la tecla '{self.cfg['hotkey']}' "
            f"({plataforma.backend_teclado()}). Manten presionado para hablar."
        )

    def stop(self) -> None:
        if self._hook is not None:
            plataforma.unhook_teclado(self._hook)
            self._hook = None
        self._down = False
        try:
            self.recorder.stop()
        except Exception:  # noqa: BLE001 - si no estaba grabando, da igual
            pass

    def watch_config(self, on_reload=None) -> None:
        """Recarga sola cuando el panel guarda.

        El panel corre en otro proceso, asi que no puede tocar este objeto. En vez
        de inventar un canal de IPC, se vigila el mtime de config.json: el archivo
        que el panel ya escribe ES la señal. Sirve igual si lo editan a mano.
        """

        def bucle():
            ultimo = _mtime(store.CONFIG_PATH)
            while True:
                # El panel corre en otro proceso y lee esto para saber si el
                # asistente esta vivo, sin tener que preguntarle al SO.
                store.latir({"motor": self.cfg.get("engine"), "tecla": self.cfg.get("hotkey"),
                             "pausado": self.paused})
                time.sleep(2)
                actual = _mtime(store.CONFIG_PATH)
                if actual == ultimo:
                    continue
                # Esperar a que deje de cambiar: guardar no es atomico y una
                # escritura a medias daria un JSON invalido.
                time.sleep(1)
                if _mtime(store.CONFIG_PATH) != actual:
                    continue
                # No cambiar el motor en medio de un pedido: se reintenta al
                # proximo tick, cuando termine.
                if self._busy:
                    continue
                ultimo = actual
                try:
                    self.restart()
                    print("[config recargada]")
                    if on_reload:
                        on_reload(self)
                except Exception as exc:  # noqa: BLE001 - el watcher no puede morir
                    traceback.print_exc()
                    store.log_action("listener", "recarga automatica", f"ERROR: {exc}")

        threading.Thread(target=bucle, daemon=True).start()

    def restart(self) -> None:
        """Relee config.json y rearma todo.

        Sin esto, guardar en el panel no cambia nada hasta cerrar y volver a
        abrir el programa: el listener tiene la config vieja en memoria.
        """
        self.stop()
        self.cfg = store.load_config()
        self._busy = False
        self.eve = self._build_engine()
        self.start()
