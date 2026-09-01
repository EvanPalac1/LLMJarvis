"""Push-to-talk: manten la tecla del keypad, habla, solta.

Independiente del panel: el boton del keypad NUNCA abre la GUI.
"""

import os
import queue
import threading
import time
import traceback

from . import cc_engine, plataforma, store, voice
from .textos import t as tr


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


def armar_motor(cfg: dict, confirm=None, on_status=None):
    """El motor que dice la config, ya armado.

    Vive suelta y no adentro del Listener porque el panel necesita exactamente
    este mismo motor para su boton de probar: si fueran dos caminos, el boton
    podria decir que anda mientras el asistente usa otro que no.
    """
    motor = cfg.get("engine")
    if motor == "claude-code":
        return cc_engine.ClaudeCodeEve(cfg, on_status=on_status)
    if motor == "compat":
        from . import compat_engine

        return compat_engine.CompatEve(cfg, confirm=confirm, on_status=on_status)
    if motor == "ollama":
        from . import ollama_engine

        return ollama_engine.OllamaEve(cfg, confirm=confirm, on_status=on_status)
    from . import brain  # import perezoso: el motor CLI no necesita `anthropic`

    return brain.Eve(cfg, confirm=confirm, on_status=on_status)


class Listener:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.paused = False
        # El ultimo perfil que aplicaron las reglas de contexto. Arranca con el
        # que ya estaba puesto: si al abrir Eve ya estabas en Discord y la regla
        # dice `discord=gaming`, no tiene sentido re-aplicar lo que ya rige.
        self._perfil_contextual = str(cfg.get("perfil_activo", "") or "")
        # La escucha continua, si el usuario la prendio. None = apagada.
        self.escucha = None
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
        """El motor de la config, o None con el motivo guardado.

        NO propaga el error, y esa es toda la diferencia entre "Eve no abre" y
        "Eve abre y te dice que le falta". Antes esto reventaba hacia arriba,
        `main` lo atrapaba y se iba con codigo 1: un Ollama apagado, un modelo
        sin bajar o una key vencida y no arrancaba NADA --ni la bandeja, ni la
        tecla, ni el panel-- aunque el resto del programa no necesita el motor
        para nada. Y peor: el motor que fallaba podia ser uno que ni siquiera
        estabas usando, porque basta con que `engine` haya quedado apuntando
        ahi.

        El error se guarda y se dice cuando de verdad hace falta, que es al
        hablarle. Un asistente que no puede pensar todavia puede abrir su
        panel para que lo arregles, y esa es justamente la ventana que hace
        falta cuando el motor esta mal configurado.
        """
        self.motor_error = ""
        try:
            return armar_motor(self.cfg, confirm=self._confirm,
                               on_status=self._estado)
        except Exception as exc:  # noqa: BLE001 - ningun motor puede impedir abrir
            self.motor_error = str(exc)
            print(f"MOTOR NO DISPONIBLE: {exc}")
            store.log_action("listener", f"motor {self.cfg.get('engine')}",
                             f"NO DISPONIBLE: {str(exc)[:300]}")
            return None

    def _motor(self):
        """El motor, reintentando armarlo si la vez pasada no se pudo.

        Se reintenta aca y no solo al cambiar la config porque lo que falla
        suele ser algo de AFUERA --Ollama que todavia no arranco, la red, el
        CLI recien instalado-- y eso se arregla sin tocar ningun ajuste. Sin
        el reintento habria que reiniciar Eve para algo que ya anda.
        """
        if self.eve is None:
            self.eve = self._build_engine()
        return self.eve

    def _confirm(self, reason: str, detail: str) -> bool:
        voice.speak(f"Necesito tu confirmacion. {reason}.", self.cfg)
        return ask_yes_no(reason, detail)

    def _desperto(self, audio) -> None:
        """Le llega una frase que silero recorto. Decide si era para Eve.

        Corre en el hilo de la escucha, asi que lo unico que hace es la puerta
        --el modelo chico-- y despues delega en la misma cola de siempre. Un
        despertar no es distinto de apretar la tecla: entra por el mismo lado.
        """
        if self.paused or self._down:
            return
        # Lo que entro mientras ella hablaba es ELLA. Con la palabra clave
        # prendida el microfono queda abierto mientras contesta, silero recorta
        # su propia voz como una frase, y una respuesta que empiece con el
        # nombre --"Eve esta lista"-- abre la puerta sola. Peor: se realimenta,
        # porque la respuesta a eso vuelve a pasar por aca.
        if voice.hablando():
            return
        try:
            from . import despertar

            pedido = despertar.escuchado(audio, self.cfg)
        except Exception as exc:  # noqa: BLE001 - la escucha no puede morir
            store.log_action("listener", "wake", f"ERROR: {exc}")
            return
        if pedido is None:
            return
        store.log_action("listener", "wake", pedido or "(solo la palabra)")
        if not pedido:
            # Dijo la palabra y nada mas. Se avisa y se corta: encadenar una
            # segunda ventana de captura seria una maquina de estados entera
            # para ahorrarle al usuario decir la orden en la misma respiracion.
            #
            # Y va adentro de un try: esto corre en el HILO DE LA ESCUCHA, cuyo
            # lazo era un `try/finally` sin `except`. Un TTS que falla --una voz
            # borrada, el parlante tomado-- mataba el hilo, cerraba el stream y
            # dejaba a Eve sorda hasta el proximo cambio de config, en silencio.
            try:
                voice.speak("Decime la orden junto con mi nombre.", self.cfg)
            except Exception as exc:  # noqa: BLE001
                store.log_action("listener", "wake", f"no pude contestar: {exc}")
            return
        self.cola.put((audio, True))
        if not self._trabajando:
            self.mostrar(estado="pensando", detalle=self._con_cola("TRANSCRIBIENDO"),
                         nivel=0.1)

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
            item = self.cola.get()
            # La cola lleva audio suelto (la tecla) o (audio, quitar_palabra)
            # cuando entro por la palabra clave. Un solo obrero para los dos
            # caminos: la alternativa era una segunda cola que se pisaria con
            # esta por el microfono, los parlantes y el contexto.
            audio, quitar = item if isinstance(item, tuple) else (item, False)
            self._trabajando = True
            try:
                self._process(audio, quitar)
            except Exception as exc:  # noqa: BLE001 - el obrero no puede morir
                traceback.print_exc()
                store.log_action("listener", "cola", f"ERROR: {exc}")
            finally:
                self._trabajando = False
                self.cola.task_done()
                if self.cola.empty() and not self._down:
                    self.mostrar(estado="reposo", detalle="", nivel=0.0)

    def _process(self, audio, quitar_palabra: bool = False) -> None:
        try:
            text = voice.transcribe(audio, self.cfg)
            if not text:
                return
            if quitar_palabra:
                # La puerta ya decidio que era para Eve con el modelo chico;
                # esto es la misma frase transcrita bien. Si el modelo bueno
                # escribio la palabra clave se le saca, y si no la escribio se
                # usa igual: quien decide es la puerta, no la ortografia.
                from . import despertar

                sin = despertar.separar(text, despertar.palabra_de(self.cfg))
                text = sin if sin else text
            print(f"[usuario] {text}")

            # Un comando tuyo se resuelve ACA, sin llamar al modelo. Va antes
            # de `mostrar(estado="pensando")` porque no hay nada que pensar:
            # decir "pensando" para algo que ya esta resuelto es mentirle al
            # cartel. Si lo dicho no es un comando, `resolver` devuelve 'nada'
            # y sigue el camino de siempre.
            from . import comandos

            que, dato = comandos.resolver(text, self.cfg)
            if que == "hecho":
                print(f"[comando] {dato}")
                self.mostrar(estado="hablando", detalle=self._con_cola("COMANDO"),
                             usuario=text, eve=dato)
                voice.speak(dato, self.cfg)
                self.mostrar(eve=dato, nivel=0.0)
                return
            if que == "prompt":
                # La frase corta se reemplaza por el texto largo y ESE va al
                # modelo. Es el unico de los tres tipos que paga una llamada.
                text = dato

            self.mostrar(estado="pensando", detalle=self._con_cola("PENSANDO"),
                         usuario=text, eve="")
            motor = self._motor()
            if motor is None:
                self._sin_motor()
                return
            reply = motor.ask(text)
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

    def _sin_motor(self) -> None:
        """Que se entienda que falta configurar algo, y donde.

        Por voz una frase corta --el detalle tecnico hablado no lo entiende
        nadie-- y el detalle entero a la pantalla, que es donde se puede leer.
        """
        detalle = self.motor_error or tr("No hay ningun motor configurado.")
        print(f"SIN MOTOR: {detalle}")
        self.mostrar(estado="error", detalle=tr("SIN MOTOR"),
                     eve=detalle[:300], nivel=0.0)
        voice.speak(tr("No tengo motor configurado. Miralo en el panel."), self.cfg)

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
        self._escucha_wake()

    def _escucha_wake(self) -> None:
        """Prende o apaga la escucha continua segun la config del momento."""
        quiere = bool(self.cfg.get("wake_activo"))
        if quiere and self.escucha is None:
            from . import despertar

            self.escucha = despertar.Escucha(self._desperto)
            # El microfono lo puede tener otro programa en modo exclusivo. Si no
            # abrio, decirlo: anunciar "escuchando" y no escuchar es peor que no
            # tener la funcion, porque el usuario deja de apretar la tecla.
            if self.escucha.arrancar(esperar=8.0):
                # La palabra de verdad, que con `wake_palabra` vacia es el
                # nombre del asistente. Imprimir el campo crudo anunciaba
                # "escuchando por ''" cuando estaba vacio.
                print(f"Escuchando por la palabra "
                      f"'{despertar.palabra_de(self.cfg)}'. "
                      "El microfono queda abierto.")
            else:
                motivo = self.escucha.error or "no se pudo abrir"
                print(f"NO pude abrir el microfono para la palabra clave: {motivo}")
                print("Sigue usando la tecla. Se reintenta al proximo cambio de config.")
                store.log_action("listener", "wake", f"microfono no disponible: {motivo}")
                self.escucha.parar()
                self.escucha = None
        elif not quiere and self.escucha is not None:
            self.escucha.parar()
            self.escucha = None

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
        if self.escucha is not None:
            self.escucha.parar()
            self.escucha = None
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
                self._perfil_del_contexto()
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

    def _perfil_del_contexto(self) -> None:
        """Aplica el perfil que pide la hora o el programa en foco, si cambio.

        Se engancha al bucle que ya vigila la config y ya late: agregar un hilo
        propio para esto seria un hilo mas para hacer lo que este ya hace cada
        dos segundos.

        No hace falta ningun canal nuevo: `aplicar_perfil` escribe config.json,
        y el vigilante de mtime que esta cinco lineas mas abajo lo recarga solo,
        con el cartel y la ventana de actividad incluidos.

        **Solo actua cuando el RESULTADO de las reglas cambia**, y eso es lo que
        lo separa de una app poseida. Si mientras estas en Discord movés un
        color a mano, la regla `discord=gaming` no te lo va a volver a pisar en
        el proximo tick: ya aplico `gaming` y sigue aplicando `gaming`. Recien
        cuando cambies de programa o de hora vuelve a tocar algo. Es la misma
        regla que el modo `auto` de sensibilidad, donde una eleccion a mano no
        la pisa el reloj.
        """
        try:
            quiere = store.perfil_por_contexto(self.cfg)
        except Exception:  # noqa: BLE001 - el vigilante no puede morir por esto
            return
        if not quiere or quiere == self._perfil_contextual:
            return
        try:
            store.aplicar_perfil(quiere)
            self._perfil_contextual = quiere
            print(f"[perfil por contexto: {quiere}]")
            store.log_action("listener", f"perfil {quiere}", "por contexto")
        except Exception as exc:  # noqa: BLE001 - un perfil borrado no puede
            self._perfil_contextual = quiere   # no reintentar en cada tick
            store.log_action("listener", f"perfil {quiere}", f"ERROR: {exc}")

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
