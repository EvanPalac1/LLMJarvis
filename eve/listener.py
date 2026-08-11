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
        self.eve = self._build_engine()

    def _build_engine(self):
        motor = self.cfg.get("engine")
        if motor == "claude-code":
            return cc_engine.ClaudeCodeEve(self.cfg, on_status=print)
        if motor == "ollama":
            from . import ollama_engine

            return ollama_engine.OllamaEve(self.cfg, confirm=self._confirm, on_status=print)
        from . import brain  # import perezoso: el motor CLI no necesita `anthropic`

        return brain.Eve(self.cfg, confirm=self._confirm, on_status=print)

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
        except voice.MicBusyError:
            self._down = False
            voice.speak("No puedo usar el microfono, otro programa lo tiene tomado.", self.cfg)

    def _on_up(self, _tecla) -> None:
        if not self._down:
            return
        self._down = False
        audio = self.recorder.stop()
        self._busy = True
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio) -> None:
        try:
            text = voice.transcribe(audio, self.cfg)
            if not text:
                return
            print(f"[usuario] {text}")
            reply = self.eve.ask(text)
            print(f"[{self.cfg['assistant_name']}] {reply}")
            voice.speak(reply, self.cfg)
        except Exception as exc:  # noqa: BLE001 - el listener no puede morir en silencio
            traceback.print_exc()
            store.log_action("listener", "procesar audio", f"ERROR: {exc}")
            voice.speak("Tuve un error procesando eso.", self.cfg)
        finally:
            self._busy = False

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
