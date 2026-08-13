"""Push-to-talk: manten la tecla del keypad, habla, solta.

Independiente del panel: el boton del keypad NUNCA abre la GUI.
"""

import os
import queue
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
        self._hook = None
        self._vista = {}  # ultimo estado mandado al overlay
        # Se puede hablarle mientras piensa: lo que se grabe queda esperando.
        self.cola: queue.Queue = queue.Queue()
        self._trabajando = False
        self._obrero = None
        self.eve = self._build_engine()

    @property
    def ocupada(self) -> bool:
        return self._trabajando or not self.cola.empty()

    # --- lo que ve el usuario en pantalla ----------------------------------

    def mostrar(self, **cambios) -> None:
        """Actualiza el overlay. Acumula, asi que se manda solo lo que cambia."""
        self._vista.update(cambios)
        store.emitir_overlay(self._vista)

    def _sostener_overlay(self) -> None:
        """Repite la señal mientras Eve trabaja, aunque no haya novedades.

        Los motores avisan 'Pensando...' una vez y despues se bloquean esperando
        al modelo. Como el overlay descarta las señales viejas para no quedarse
        pegado si Eve muere, una peticion larga lo hacia desaparecer justo
        mientras trabajaba. Esto es el pulso que dice 'sigo aca'.
        """
        while True:
            time.sleep(1.0)
            if self._vista.get("estado", "reposo") != "reposo":
                store.emitir_overlay(self._vista)

    def _con_cola(self, texto: str) -> str:
        """El texto de estado, avisando cuantas peticiones esperan turno."""
        esperando = self.cola.qsize()
        return f"{texto}  ·  {esperando} EN COLA" if esperando else texto

    def _estado(self, texto: str) -> None:
        """Lo que los motores reportan por `on_status`: sale por consola y a la
        pantalla, que es donde el usuario lo va a ver."""
        print(texto)
        self.mostrar(estado="pensando",
                     detalle=self._con_cola(texto.upper().rstrip(". ")), nivel=0.12)

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
        # A proposito NO se rechaza mientras trabaja: podes apretar y hablarle de
        # nuevo mientras piensa, y lo que grabes espera turno.
        if self.paused or self._down:
            return
        self._down = True
        try:
            self.recorder.start()
            print("[grabando]")
            self.mostrar(estado="escuchando",
                         detalle=self._con_cola("ESCUCHANDO"),
                         usuario="" if not self.ocupada else self._vista.get("usuario", ""),
                         eve="" if not self.ocupada else self._vista.get("eve", ""))
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
        self.cola.put(audio)
        if self._trabajando:
            # Ya hay una en curso: esta espera. No se pisa el estado que se este
            # mostrando, solo se avisa cuantas hay detras.
            self.mostrar(detalle=self._con_cola(self._vista.get("detalle", "PENSANDO")))
        else:
            self.mostrar(estado="pensando", detalle=self._con_cola("TRANSCRIBIENDO"),
                         nivel=0.1)

    def _atender_cola(self) -> None:
        """Un solo obrero saca de a una y la procesa entera antes de la siguiente.

        Serial y no en paralelo a proposito: dos pedidos a la vez se pisarian el
        microfono, los parlantes y el contexto de la conversacion.
        """
        while True:
            audio = self.cola.get()
            self._trabajando = True
            try:
                self._process(audio)
            except Exception as exc:  # noqa: BLE001 - el obrero no puede morir
                traceback.print_exc()
                store.log_action("listener", "cola", f"ERROR: {exc}")
            finally:
                self._trabajando = False
                self.cola.task_done()
                if self.cola.empty() and not self._down:
                    self.mostrar(estado="reposo", detalle="", nivel=0.0)

    def _process(self, audio) -> None:
        try:
            text = voice.transcribe(audio, self.cfg)
            if not text:
                return
            print(f"[usuario] {text}")
            self.mostrar(estado="pensando", detalle=self._con_cola("PENSANDO"),
                         usuario=text, eve="")
            reply = self.eve.ask(text)
            print(f"[{self.cfg['assistant_name']}] {reply}")
            self.mostrar(estado="hablando", detalle=self._con_cola("RESPONDIENDO"), eve="")
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
        # El obrero y el pulso arrancan una sola vez y sobreviven a los restart:
        # la cola no tiene por que vaciarse porque cambiaste un color.
        if self._obrero is None:
            self._obrero = threading.Thread(target=self._atender_cola, daemon=True)
            self._obrero.start()
            threading.Thread(target=self._sostener_overlay, daemon=True).start()
            self._precalentar()

    def _precalentar(self) -> None:
        """Deja los modelos cargados antes de la primera orden.

        Cargar Piper cuesta ~2.3s y Whisper otro tanto. Pagarlo mientras el
        usuario todavia no hablo es gratis; pagarlo en la primera orden es la
        diferencia entre parecer lento y no parecerlo.
        """
        if self.cfg.get("tts_provider") == "piper":
            from . import voices

            clave = self.cfg.get("piper_voice") or (voices.instaladas() or [""])[0]
            if clave:
                voices.precargar(clave)

        def whisper():
            try:
                voice.precargar_stt(self.cfg)
            except Exception:  # noqa: BLE001 - si falla, se vera al hablar
                pass

        threading.Thread(target=whisper, daemon=True).start()
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
                # proximo tick, cuando termine. Lo cosmetico si se aplica ya,
                # porque no toca nada de lo que este corriendo.
                nueva = store.load_config()
                if self.ocupada and not store.solo_cosmetico(self.cfg, nueva):
                    continue
                ultimo = actual
                try:
                    self.restart(nueva)
                    print("[config recargada]")
                    if on_reload:
                        on_reload(self)
                except Exception as exc:  # noqa: BLE001 - el watcher no puede morir
                    traceback.print_exc()
                    store.log_action("listener", "recarga automatica", f"ERROR: {exc}")

        threading.Thread(target=bucle, daemon=True).start()

    def restart(self, nueva: dict | None = None) -> None:
        """Relee config.json y rearma lo que haga falta.

        Sin esto, guardar en el panel no cambia nada hasta cerrar y volver a
        abrir el programa: el listener tiene la config vieja en memoria.

        Si lo unico que cambio es el aspecto, no se toca el motor. Rearmarlo
        borra la conversacion, y cambiar un color no tiene por que costarte el
        contexto de lo que venias hablando.
        """
        nueva = nueva if nueva is not None else store.load_config()
        cosmetico = store.solo_cosmetico(self.cfg, nueva)
        self.cfg = nueva
        if cosmetico:
            return
        self.stop()
        self.eve = self._build_engine()
        self.start()
