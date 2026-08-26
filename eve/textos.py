"""Los textos de la interfaz, en espanol neutro y en ingles.

**La clave es el texto en espanol.** No es pereza, son tres cosas que se ganan y
que un diccionario de claves inventadas pierde:

1. El codigo se sigue leyendo. `t("Guardar")` dice lo que dice; `t("btn.save.1")`
   obliga a abrir otro archivo para saber que boton es.
2. Un texto sin traducir sale en espanol en vez de romperse o de mostrar la
   clave cruda. Traducir de a poco es posible sin dejar la app a medias.
3. Agregar un idioma es agregar un diccionario y nada mas.

Lo que se paga a cambio: cambiar una coma del espanol deja el texto sin
traduccion hasta que se cambie tambien la clave. Por eso existe
`usados_en_el_codigo()` y el test que lo usa --el desfasaje se ve solo, no se
descubre cuando un usuario cambia el idioma y encuentra media pantalla en
espanol.

No se usa `gettext`: pide extraer con xgettext, compilar .mo y llevar los
binarios adentro del paquete en los cinco objetivos. Para dos idiomas y
trescientos textos, un dict es todo lo que hace falta.
"""

import ast
import os

# Codigo -> como se llama ese idioma EN ESE idioma. Un desplegable que dice
# "Ingles" cuando ya estas en ingles no ayuda a nadie a volver.
IDIOMAS = {
    "es": "Espanol",
    "en": "English",
}

_idioma = "es"


def usar(codigo: str) -> str:
    """Fija el idioma de la interfaz. Devuelve el que quedo.

    Cualquier cosa que no conozcamos cae en espanol: un config a mano con
    `ui_idioma: "pt"` tiene que dejar el panel usable, no vacio.
    """
    global _idioma
    _idioma = codigo if codigo in IDIOMAS else "es"
    return _idioma


def desde_config(cfg: dict) -> str:
    """Atajo para las cuatro ventanas, que leen la misma clave."""
    return usar(str(cfg.get("ui_idioma", "es") or "es"))


def actual() -> str:
    return _idioma


def t(texto: str) -> str:
    """El texto en el idioma activo. Sin entrada, el original."""
    if _idioma == "es":
        return texto
    return TABLA.get(_idioma, {}).get(texto, texto)


# --- control de cobertura -------------------------------------------------
# Solo corre desde el repo: en el binario congelado no hay .py que leer, y no
# hace falta --esto es para el test, no para el usuario.

# `main.py` esta un nivel arriba del paquete: el aviso de donde quedo el icono
# de bandeja vive ahi, y es el primer texto que ve quien instala Eve.
ARCHIVOS = ("gui.py", "consola.py", "tray.py", "overlay.py", "textos.py",
            "lienzo.py", os.path.join("..", "main.py"))


def usados_en_el_codigo(carpeta: str = "") -> set:
    """Los textos literales que el codigo le pasa a `t()`.

    Que la extraccion sea buscar llamadas a `t()` y no adivinar cuales strings
    son de pantalla es justamente la ventaja de haberlas envuelto: no hay
    heuristica que se equivoque, esta o no esta envuelto.

    Quedan afuera los `t(variable)`, que son pocos y a proposito: ahi el texto
    se arma en otro lado y el que tiene que estar traducido es aquel.
    """
    carpeta = carpeta or os.path.dirname(os.path.abspath(__file__))
    encontrados = set()
    for nombre in ARCHIVOS:
        ruta = os.path.join(carpeta, nombre)
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as f:
            arbol = ast.parse(f.read())
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Call):
                continue
            nom = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            # `tr` y no `t` porque `t` ya era el nombre del frame en casi todos
            # los metodos del panel; se importa con alias. Se aceptan los dos por
            # si algun archivo nuevo lo importa sin renombrar.
            if nom not in ("t", "tr") or not n.args:
                continue
            a = n.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                encontrados.add(a.value)
    # Y lo que declara el registro. Ahi los rotulos son datos y no literales
    # adentro de `tr()`, asi que el recorrido de arriba no los ve.
    try:
        from . import registro

        encontrados.update(registro.textos())
    except Exception:  # noqa: BLE001 - sin registro, lo demas sigue valiendo
        pass
    return encontrados


def sin_traducir(idioma: str = "en", carpeta: str = "") -> list:
    """Lo que el codigo muestra y ese idioma todavia no cubre."""
    tabla = TABLA.get(idioma, {})
    return sorted(s for s in usados_en_el_codigo(carpeta) if s not in tabla)


# Funciones donde un `tr(variable)` es correcto: traducen texto que viene de
# una tabla declarada, y esa tabla ya la cubre `usados_en_el_codigo()`. Fuera de
# aca, un `tr(variable)` sigue siendo un texto que nadie verifica.
DESDE_TABLA = ("_pintar_registro",)


def textos_invisibles(carpeta: str = "") -> list:
    """Los `tr(variable)`: se muestran y el chequeo no los ve.

    Es el unico agujero que tiene este esquema, y no es teorico. Tres textos
    salieron en espanol con el panel en ingles --el titulo de la ventana, la
    pista del buscador y la barra de estado del pie-- y `sin_traducir()` decia
    que estaba todo cubierto, porque los tres se leian de una variable.

    El arreglo es siempre el mismo: mover el literal a donde se envuelve. Por
    eso esto devuelve el lugar y no intenta resolverlo solo.
    """
    import os

    carpeta = carpeta or os.path.dirname(os.path.abspath(__file__))
    sueltos = []
    for nombre in ARCHIVOS:  # noqa: PLR1702
        ruta = os.path.join(carpeta, nombre)
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as f:
            arbol = ast.parse(f.read())
        for fn in ast.walk(arbol):
            if isinstance(fn, ast.FunctionDef) and fn.name in DESDE_TABLA:
                continue
            if not isinstance(fn, ast.FunctionDef):
                continue
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                nom = (n.func.attr if isinstance(n.func, ast.Attribute)
                       else getattr(n.func, "id", ""))
                if nom not in ("t", "tr") or not n.args:
                    continue
                if not isinstance(n.args[0], ast.Constant):
                    sueltos.append(f"{nombre}:{n.lineno}  {ast.unparse(n)[:60]}")
    return sorted(sueltos)


EN = {
    "Navegacion":
        "Navigation",
    "Como se pasa de una seccion a otra:\n"
    "  lateral    una barra a la izquierda\n"
    "  pestanas   las de arriba, como era antes\n"
    "Siete pestañas arriba ya rozan el ancho de la ventana. La barra\n"
    "esta dibujada pero se maneja con el teclado igual: entra en el\n"
    "tabulador, las flechas mueven y Enter activa.\n"
    "\n"
    "El cambio se ve al reabrir el panel.":
        "How you move from one section to another:\n"
        "  lateral    a bar on the left\n"
        "  pestanas   the tabs on top, the way it used to be\n"
        "Seven tabs across the top already push the window's width. The bar\n"
        "is drawn but it still works from the keyboard: it joins the tab\n"
        "order, the arrows move and Enter activates.\n"
        "\n"
        "The change shows when you reopen the panel.",
    "Secciones":
        "Sections",
    "Como se ve cada seccion:\n"
    "  tarjeta  en una tarjeta con esquinas redondeadas\n"
    "  plano    filas sueltas, como era antes\n"
    "Las esquinas redondeadas ttk no las tiene, asi que el marco se\n"
    "dibuja aparte. Los CONTROLES siguen siendo los de siempre en los\n"
    "dos casos: uno dibujado seria invisible para un lector de\n"
    "pantalla, y eso no se cambia por una esquina.\n"
    "\n"
    "Necesita el tema aplicado al panel, aca arriba.":
        "How each section looks:\n"
        "  tarjeta  in a card with rounded corners\n"
        "  plano    plain rows, the way it used to be\n"
        "Rounded corners are not something ttk has, so the frame is drawn\n"
        "separately. The CONTROLS are the usual ones either way: a drawn\n"
        "one would be invisible to a screen reader, and that is not worth\n"
        "trading for a corner.\n"
        "\n"
        "Needs the theme applied to the panel, just above.",
    "Cerrar":
        "Close",
    "Grabar":
        "Record",
    "Grabar el banco de voz":
        "Record the voice bank",
    "HABLA":
        "SPEAK",
    "Listo":
        "Done",
    "Saltar esta":
        "Skip this one",
    "callate...":
        "stay quiet...",
    "no entro audio":
        "no audio came in",
    "no pude abrir el microfono":
        "could not open the microphone",
    "falta el banco viejo: de ahi salen las frases":
        "the old bank is missing: that is where the phrases come from",
    "Ya estan las 24. Corre banco_voz.py para medir.":
        "All 24 are in. Run banco_voz.py to measure.",
    "Probar recorre el camino entero y no una pieza suelta: graba de tu\n"
    "microfono de verdad y transcribe con el modelo que tengas elegido.\n"
    "\n"
    "Sensibilidad: 'normal' para un cuarto tranquilo, 'ruido' si hay\n"
    "musica o un juego atras, 'bajo' de madrugada. 'auto' la elige por\n"
    "hora; las reglas y los numeros medidos estan en el ajuste fino.\n"
    "\n"
    "'auto' NO se envia todavia, y por eso: el modo correcto mira el\n"
    "ruido del ambiente y elige solo, pero el banco con el que se mide\n"
    "todo esto se corto por silencio y quedo sin silencios: mediana de\n"
    "90 ms antes de la primera palabra, y uno solo de 24 llega a los\n"
    "300 que hacen falta. 'Grabar el banco de voz' arregla eso: guia\n"
    "la grabacion y no acepta una toma donde te adelantaste.":
        "Testing walks the whole path and not one piece of it: it records from\n"
        "your real microphone and transcribes with the model you picked.\n"
        "\n"
        "Sensitivity: 'normal' for a quiet room, 'ruido' if there is music or a\n"
        "game behind, 'bajo' late at night. 'auto' picks by the clock; the rules\n"
        "and the measured numbers are under fine tuning.\n"
        "\n"
        "'auto' does NOT ship yet, and here is why: the right mode looks at the\n"
        "room noise and picks on its own, but the bank everything is measured\n"
        "against was cut by silence and ended up with no silences: a median of\n"
        "90 ms before the first word, and only one clip out of 24 reaches the\n"
        "300 that are needed. 'Record the voice bank' fixes that: it guides the\n"
        "recording and refuses a take where you spoke too early.",
    "Revisar listener":
        "Check listener",
    "abriendo el listener...":
        "opening the listener...",
    "el listener no llego a dar señales; fijate en Acciones":
        "the listener never reported in; check the Actions tab",
    "el listener ya esta abierto":
        "the listener is already open",
    "listener abierto":
        "listener open",
    "no pude abrir el listener":
        "could not open the listener",
    "Agregalos con el boton de aca al lado. Sin ninguno, el\n"
    "cartel dibuja el diseno de siempre y no cambia nada.":
        "Add them with the button next to this one. With none, the\n"
        "card draws its usual design and nothing changes.",
    "Editando":
        "Editing",
    "Editando el cartel. El recuadro es su tamano real.":
        "Editing the card. The outline is its real size.",
    "Editando el tablero.":
        "Editing the board.",
    "El cartel no tiene modulos propios.":
        "The card has no modules of its own.",
    "borde del cartel":
        "edge of the card",
    "Cuadros por segundo":
        "Frames per second",
    "Fluidez":
        "Smoothness",
    "Vale para el cartel y para la ventana de actividad. 0 = el que\n"
    "sugiere tu maquina: 30 en un PC normal, 20 en ARM.\n"
    "\n"
    "Medido en un escritorio x64: componer la ventana entera con seis\n"
    "capas y quinientas particulas cuesta 21.6 ms de mediana y 23.1 de\n"
    "p95, asi que a 30 cuadros quedan 11 ms de margen. Si ves tirones,\n"
    "bajalo antes que apagar modulos: 20 cuadros con todo puesto se ve\n"
    "mejor que 30 a medias.":
        "Applies to the card and to the activity window. 0 = whatever your\n"
        "machine suggests: 30 on a normal PC, 20 on ARM.\n"
        "\n"
        "Measured on an x64 desktop: compositing the whole window with six\n"
        "layers and five hundred particles costs 21.6 ms median and 23.1 at\n"
        "p95, so at 30 frames there are 11 ms of headroom. If you see stutter,\n"
        "lower this before turning modules off: 20 frames with everything on\n"
        "looks better than 30 with half of it.",
    "Acento":
        "Accent",
    "Acento apagado":
        "Muted accent",
    "Alerta":
        "Alert",
    "Cajas y campos":
        "Boxes and fields",
    "Fondo":
        "Background",
    "Texto":
        "Text",
    "Texto secundario":
        "Secondary text",
    "Eve no ejecuto nada todavia":
        "Eve has not run anything yet",
    "accion desconocida":
        "unknown action",
    "cartel mostrado unos segundos":
        "card shown for a few seconds",
    "ejecutando":
        "running",
    "listo, hablo":
        "done, it spoke",
    "no entendi nada":
        "I did not understand anything",
    "no entro audio; el microfono puede estar tomado":
        "no audio came in; the microphone may be taken",
    "panel abierto":
        "panel opened",
    "pidele que lea una pagina":
        "ask it to read a page",
    "pidele que te muestre algo":
        "ask it to show you something",
    "te escuche":
        "I heard you",
    "todavia no hablaron":
        "you have not talked yet",
    "Eve esta corriendo":
        "Eve is running",
    # Los rotulos de "agregar un modulo EN tablero/cartel". Van cortos a
    # proposito: la fila del panel es `[tipo] en [donde] [Agregar]` y un rotulo
    # largo la parte en dos renglones.
    "en":
        "on",
    "tablero":
        "board",
    "cartel":
        "overlay",
    "Perfil segun el contexto":
        "Profile by context",
    "Cambia de perfil solo, segun la hora o el programa que\n"
    "tengas adelante. Misma sintaxis que la linea de arriba:\n"
    "  22:00-06:00=noche, discord=gaming\n"
    "\nLa condicion es un rango de horas si tiene forma de rango,\n"
    "y si no el nombre del programa. GANA LA PRIMERA QUE ENTRA,\n"
    "asi que el orden en que las escribis es el orden de\n"
    "prioridad -- es lo unico de esto que no se adivina.\n"
    "\nEl nombre del programa se compara por pedazo: `discord`\n"
    "agarra tambien `Discord.exe` y `discordptb`, para no tener\n"
    "que abrir el administrador de tareas para escribir una\n"
    "regla.\n"
    "\nVacio no cambia nada. Y un perfil solo toca como se VE y\n"
    "como suena Eve: no puede cambiarte el motor, la tecla, los\n"
    "permisos ni tus datos.":
        "Switches profile on its own, by the time of day or by the program\n"
        "you have in front. Same syntax as the line above:\n"
        "  22:00-06:00=night, discord=gaming\n"
        "\nThe condition is a time range if it looks like one, and otherwise\n"
        "the name of the program. THE FIRST MATCH WINS, so the order you\n"
        "write them in is their priority -- it is the only part of this you\n"
        "cannot guess.\n"
        "\nThe program name matches by substring: `discord` also catches\n"
        "`Discord.exe` and `discordptb`, so you do not have to open the task\n"
        "manager to write a rule.\n"
        "\nEmpty changes nothing. And a profile only touches how Eve LOOKS and\n"
        "sounds: it cannot change your engine, your key, your permissions or\n"
        "your data.",
    "Motor de dibujo":
        "Drawing engine",
    "Quien pinta los modulos. `auto` usa la GPU si tu maquina la\n"
    "tiene, y si no cae a Pillow por CPU, que es lo de siempre.\n"
    "\nMedido en un escritorio x64 sobre 1100x700 con seis capas y\n"
    "quinientas particulas: Pillow por CPU cuesta 20.3 ms de\n"
    "mediana y Skia por GPU 2.0. Pero Skia SIN GPU cuesta 214, o\n"
    "sea diez veces peor que no usarlo: por eso pedirlo a mano no\n"
    "lo fuerza si no se puede, y la linea de abajo dice que quedo.\n"
    "\nLo que gana no son cuadros por segundo --con un modulo\n"
    "animando ya sobra-- sino techo: shaders y miles de\n"
    "particulas no entran por el camino de CPU.":
        "Who paints the modules. `auto` uses the GPU if your machine has\n"
        "one, and falls back to Pillow on the CPU, which is the usual path.\n"
        "\nMeasured on an x64 desktop at 1100x700 with six layers and five\n"
        "hundred particles: Pillow on the CPU costs 20.3 ms median and Skia\n"
        "on the GPU 2.0. But Skia WITHOUT a GPU costs 214, ten times worse\n"
        "than not using it at all: that is why asking for it by hand does\n"
        "not force it, and the line below tells you what you got.\n"
        "\nWhat it buys is not frames per second --with one module animating\n"
        "there is already room to spare-- but headroom: shaders and\n"
        "thousands of particles do not fit through the CPU path.",
    "agregado":
        "added",
    "Estoy en el desplegable de la flechita de la barra de tareas, con Steam y Discord. Arrastrame fuera para fijarme en la barra.":
        "I am in the flyout behind the arrow on the taskbar, with Steam and Discord. Drag me out to pin me to the taskbar.",
    "Buscar un ajuste...   (Ctrl+F)":
        "Search a setting...   (Ctrl+F)",
    "Cartel":
        "Card",
    "Ventana":
        "Window",
    "asistente corriendo":
        "assistant running",
    "asistente detenido":
        "assistant stopped",
    "configuracion":
        "settings",
    "motor":
        "engine",
    "tecla":
        "key",
    "Armar el tablero":
        "Build the board",
    "Esta ventana esta vacia porque el tablero no tiene modulos.":
        "This window is empty because the board has no modules.",
    "Toca 'Armar el tablero' aca arriba para poner los de arranque,\n"
    "o agregalos uno por uno desde el panel, en Apariencia > Modulos.":
        "Press 'Build the board' above to add the starter ones,\n"
        "or add them one by one from the panel, under Appearance > Modules.",
    "listo, ahi estan":
        "done, there they are",
    "Colores a mano":
        "Colors by hand",
    "Solo se usan con el tema 'personalizado'.":
        "Only used with the 'personalizado' theme.",
    "  ahi se acomodan los modulos del tablero con el mouse":
        "  that is where you arrange the board modules with the mouse",
    "  api = Messages API, necesita tu ANTHROPIC_API_KEY.\n"
    "  claude-code = CLI de Claude Code, usa tu suscripcion sin key (mas lento).\n"
    "  ollama = modelo local, sin key ni nube. Peor encadenando varias tools.\n"
    "  compat = cualquier servidor que hable el protocolo de OpenAI.":
        "  api = Messages API, needs your ANTHROPIC_API_KEY.\n"
        "  claude-code = the Claude Code CLI, uses your subscription with no key (slower).\n"
        "  ollama = a local model, no key and no cloud. Worse at chaining several tools.\n"
        "  compat = any server that speaks the OpenAI protocol.",
    "  si la abres y esta vacia, es porque no hay modulos en el tablero":
        "  if you open it and it is empty, there are no modules on the board",
    "'Permitir todo' desactiva la confirmacion y tambien los permisos internos\n"
    "de Claude Code. Todo queda igual registrado en la pestaña Acciones.":
        "'Allow everything' turns off the confirmation and also Claude Code's own\n"
        "internal permissions. Everything is still recorded in the Actions tab.",
    "'nunca' = solo cuando la abres tu. 'con_eve' = se abre junto con\n"
    "Eve y queda ahi. Corre como proceso aparte, asi que si se cuelga no\n"
    "se lleva puesto al asistente.":
        "'nunca' = only when you open it. 'con_eve' = it opens together with\n"
        "Eve and stays there. It runs as its own process, so if it hangs it does\n"
        "not take the assistant down with it.",
    "(no hay perfiles guardados)":
        "(no saved profiles)",
    "0 = donde lo dejes, sin restriccion, y puedes arrastrarlo de un\n"
    "monitor al otro. 1 en adelante lo fija a ese monitor y lo mantiene\n"
    "adentro aunque lo arrastres. Si desenchufas el que elegiste, vuelve\n"
    "al escritorio entero en vez de quedar en un lugar que no existe.\n"
    "'trabajo' descuenta la barra de tareas; solo cambia algo en Windows.":
        "0 = wherever you leave it, no constraint, and you can drag it from one\n"
        "monitor to the other. 1 and up pins it to that monitor and keeps it\n"
        "inside even if you drag it. If you unplug the one you picked, it falls\n"
        "back to the whole desktop instead of sitting somewhere that no longer exists.\n"
        "'trabajo' subtracts the taskbar; it only changes anything on Windows.",
    "Abrir contacto compartido":
        "Open a shared contact",
    "Abrir la carpeta de addons":
        "Open the addons folder",
    "Abrir la ventana de actividad":
        "Open the activity window",
    "Abrir panel":
        "Open the panel",
    "Activar diciendo una palabra (deja el microfono abierto)":
        "Wake it by saying a word (keeps the microphone open)",
    "Actividad":
        "Activity",
    "Actualizar":
        "Refresh",
    "Actualizar Eve":
        "Update Eve",
    "Addons":
        "Addons",
    "Agregar":
        "Add",
    "Agregar / actualizar":
        "Add / update",
    "Agregar / gestionar cuentas":
        "Add / manage accounts",
    "Agregar los tuyos":
        "Add your own",
    "Aire del detector (ms)":
        "Detector padding (ms)",
    "Ajuste":
        "Fit",
    "Ajuste fino de la voz":
        "Voice fine tuning",
    "Ajuste fino del modelo":
        "Model fine tuning",
    "Ajuste fino del reconocimiento":
        "Recognition fine tuning",
    "Ajustes del modulo":
        "Module settings",
    "Apagado de fabrica: prenderlo deja el microfono abierto todo el\n"
    "tiempo. Dile el nombre y la orden de un tiron, en la misma frase:\n"
    "  \"Eve, abre Spotify\"\n"
    "El nombre tiene que ir al principio. Aceptarlo en cualquier lado\n"
    "convertiria en orden cualquier charla que te lo mencione.\n"
    "\n"
    "No corre ningun modelo de lenguaje en reposo: primero un detector\n"
    "de voz de 1.2 MB que ya viaja en el paquete decide si hay alguien\n"
    "hablando --medido, 0.20% de un core-- y recien sobre ese pedazo\n"
    "corre el modelo de la puerta. Ese es chico a proposito: solo tiene\n"
    "que reconocer una palabra que ya conoce.\n"
    "\n"
    "La palabra pesa mas que el modelo. Medido, 4 ordenes y 6 frases\n"
    "de control que NO tienen que despertarla:\n"
    "  Computadora  tiny   desperto 4/4    falsos 0/6\n"
    "  Eve          small  desperto 3/4    falsos 0/6\n"
    "  Eve          tiny   desperto 2/4    falsos 0/6\n"
    "Tres letras no alcanzan para ser una puerta. Por eso se aceptan\n"
    "variantes separadas por |, y de fabrica vienen las dos.":
        "Off by default: turning it on leaves the microphone open all the time.\n"
        "Say the name and the command in one go, in the same sentence:\n"
        "  \"Eve, open Spotify\"\n"
        "The name has to come first. Accepting it anywhere would turn any\n"
        "conversation that mentions it into a command.\n"
        "\n"
        "No language model runs while idle: first a 1.2 MB voice detector that\n"
        "already ships in the package decides whether somebody is talking\n"
        "--measured, 0.20% of one core-- and only then does the gate model run\n"
        "on that slice. That one is small on purpose: all it has to do is\n"
        "recognize a word it already knows.\n"
        "\n"
        "The word matters more than the model. Measured over 4 commands and 6\n"
        "control sentences that must NOT wake it:\n"
        "  Computadora  tiny   woke 4/4    false 0/6\n"
        "  Eve          small  woke 3/4    false 0/6\n"
        "  Eve          tiny   woke 2/4    false 0/6\n"
        "Three letters are not enough to be a gate. That is why variants\n"
        "separated by | are accepted, and both ship by default.",
    "Apariencia":
        "Appearance",
    "Aplicar":
        "Apply",
    "Aplicar a los elegidos":
        "Apply to selection",
    "Aprobados":
        "Approved",
    "Aprobar":
        "Approve",
    "Aprobar addon":
        "Approve addon",
    "Area":
        "Area",
    "Armar el tablero de arranque":
        "Build the starter board",
    "Autoridad":
        "Authority",
    "Borra la conversacion guardada y deja la ventana de contexto en cero.\n"
    "\n"
    "El registro de acciones (pestaña Acciones) NO se toca.\n"
    "\n"
    "Si el listener esta corriendo, usa tambien la bandeja > 'Limpiar historial y\n"
    "contexto' para vaciar lo que ya tiene en memoria.\n"
    "\n"
    "Borrar?":
        "Deletes the saved conversation and resets the context window to zero.\n"
        "\n"
        "The action log (Actions tab) is NOT touched.\n"
        "\n"
        "If the listener is running, also use the tray > 'Clear history and\n"
        "context' to flush what it already holds in memory.\n"
        "\n"
        "Delete?",
    "Borrar":
        "Delete",
    "Borrar perfil":
        "Delete profile",
    "Buscar":
        "Search",
    "Buscar actualizaciones":
        "Check for updates",
    "Busqueda por haz (beam)":
        "Beam search",
    "Cabecera del panel":
        "Panel header",
    "Cada modulo es una pieza del cartel: un icono, una onda, particulas,\n"
    "el reloj o el medidor de contexto. Se puede elegir donde va, de que\n"
    "tamano, con cuanta transparencia y cuando se muestra.":
        "Each module is a piece of the card: an icon, a waveform, particles,\n"
        "the clock or the context meter. You choose where it goes, how big,\n"
        "how transparent, and when it shows.",
    "Cambia como ESCRIBE: tu contra vos, vale contra dale. La voz va\n"
    "aparte, y el boton de arriba le pone la que le corresponde.\n"
    "No hay voz colombiana en el catalogo de Piper, asi que esa variante\n"
    "comparte la mexicana y cambia solo el vocabulario.":
        "Changes how it WRITES: tu against vos, vale against dale. The voice is\n"
        "a separate thing, and the button above sets the matching one.\n"
        "There is no Colombian voice in Piper's catalog, so that variant shares\n"
        "the Mexican one and only changes the vocabulary.",
    "Cargar":
        "Load",
    "Cargar perfil":
        "Load profile",
    "Cartel en pantalla":
        "On-screen card",
    "Cartel mostrado unos segundos. Si no aparecio, revisa 'Cuando se ve' y 'Pantalla' mas abajo.":
        "Card shown for a few seconds. If nothing appeared, check 'When it shows' and 'Display' below.",
    "Cerrar sesion":
        "Sign out",
    "Cierra y abre el panel para verlo cargado.":
        "Close and reopen the panel to see it loaded.",
    "Claves que fijaste tu":
        "Settings you pinned yourself",
    "Colores del cartel flotante":
        "Floating card colors",
    "Colores del panel":
        "Panel colors",
    "Como habla, no que hace. Va al final del prompt y siempre pierde\n"
    "contra el manual: no puede hacerla hablar de mas ni narrar en vez\n"
    "de actuar. Vacio = sin personaje. Lo setea cada perfil.":
        "How it talks, not what it does. It goes at the end of the prompt and\n"
        "always loses against the manual: it cannot make her talk more or narrate\n"
        "instead of acting. Empty = no character. Every profile sets it.",
    "Como te escucha":
        "How it hears you",
    "Como te escucha y como te responde.":
        "How it hears you and how it answers.",
    "Como te habla":
        "How it speaks to you",
    "Compartir:":
        "Share:",
    "Con capa gratuita: ":
        "With a free tier: ",
    "Con que nombre y foto aparecen los mensajes que manda por webhook.\n"
    "Vacio = lo que tenga configurado el webhook en Discord. Andaba\n"
    "desde siempre; lo que faltaba era donde escribirlo sin editar el\n"
    "config a mano.":
        "The name and picture the webhook messages show up with.\n"
        "Empty = whatever the webhook has configured in Discord. It always\n"
        "worked; what was missing was somewhere to type it without editing\n"
        "the config by hand.",
    "Con que se conecta. Todo opcional salvo el motor que elegiste.":
        "What it connects to. All optional except the engine you picked.",
    "Conexiones con apps (todas opcionales)":
        "App connections (all optional)",
    "Configuracion guardada.\n"
    "\n"
    "Si el listener esta corriendo, aplica los\n"
    "cambios solo en unos segundos. Los de aspecto no le cortan la\n"
    "conversacion; los de motor o tecla si lo rearman.":
        "Settings saved.\n"
        "\n"
        "If the listener is running, it applies the changes\n"
        "on its own within a few seconds. Appearance changes do not cut the\n"
        "conversation; engine or key changes do rebuild it.",
    "Contactos":
        "Contacts",
    "Contorno":
        "Outline",
    "Contrasena de aplicacion":
        "App password",
    "Corriendo desde el codigo: actualiza con git pull.":
        "Running from source: update with git pull.",
    "Cuando le pides algo hablando, hasta donde puede llegar:\n"
    "  nada    no toca nada; es la voz y nada mas\n"
    "  datos   modulos, ajustes y perfiles -- todo lo que ya es una\n"
    "          clave de config y pasa por el mismo freno que el panel\n"
    "  codigo  ademas puede DEJAR ESCRITO un addon .py, que igual no\n"
    "          corre hasta que lo apruebes a mano en Addons\n"
    "No hay un cuarto nivel donde apruebe sus propios addons, y no\n"
    "deberia haberlo: la huella del contenido es lo unico que separa un\n"
    "plugin de un agujero.\n"
    "\n"
    "Es OTRO eje que 'Quien manda'. Aquel decide quien gana cuando los\n"
    "dos quieren el mismo valor; este, que clase de cosa puede crear.\n"
    "Con 'nada' el prompt tampoco lleva el vocabulario de modulos.\n"
    "Cuanto de ese vocabulario viaja lo decide el ajuste de abajo.":
        "When you ask for something out loud, how far it can go:\n"
        "  nada    touches nothing; it is the voice and nothing else\n"
        "  datos   modules, settings and profiles -- everything that is already\n"
        "          a config key and goes through the same brake as the panel\n"
        "  codigo  it can also LEAVE WRITTEN a .py addon, which still does not\n"
        "          run until you approve it by hand under Addons\n"
        "There is no fourth level where it approves its own addons, and there\n"
        "should not be: the content hash is the only thing separating a plugin\n"
        "from a hole.\n"
        "\n"
        "This is a DIFFERENT axis from 'Who wins'. That one decides who wins\n"
        "when both want the same value; this one, what kind of thing it may\n"
        "create. With 'nada' the prompt also drops the module vocabulary.\n"
        "How much of that vocabulary travels is up to the setting below.",
    "Cuanto le contamos de antemano":
        "How much we tell it up front",
    "Cuanto vocabulario de interfaz viaja en CADA llamada:\n"
    "  consultar  dos renglones, y Eve pregunta con 'E ui buscar'\n"
    "             cuando le hace falta. 310 caracteres.\n"
    "  minimo     ademas los trece nombres de tipo. 485.\n"
    "  completo   el esquema entero, con sus props. 1352.\n"
    "Medido con el mismo contador que dibuja el modulo\n"
    "'contexto': de 11 972 caracteres de prompt, 'completo' se\n"
    "lleva el 11.3% y 'consultar' el 2.8%. O sea 8.7% menos en\n"
    "TODO lo que le digas, incluido 'que hora es', a cambio de\n"
    "una consulta extra las veces que si toca la interfaz.\n"
    "\n"
    "Es OTRO eje que los dos de arriba: aquellos dicen QUE puede\n"
    "hacer y quien gana cuando los dos quieren el mismo valor;\n"
    "este, solo cuanto le adelantamos. Con 'Hasta donde arma\n"
    "sola' en nada no viaja nada y este no hace diferencia.":
        "How much interface vocabulary travels on EVERY call:\n"
        "  consultar  two lines, and Eve asks with 'E ui buscar'\n"
        "             when it needs to. 310 characters.\n"
        "  minimo     plus the thirteen type names. 485.\n"
        "  completo   the whole schema, with each type's props. 1352.\n"
        "Measured with the same counter that draws the 'contexto'\n"
        "module: out of 11,972 characters of prompt, 'completo' takes\n"
        "11.3% and 'consultar' 2.8%. That is 8.7% less on EVERYTHING\n"
        "you say, 'what time is it' included, in exchange for one\n"
        "extra lookup the times it does touch the interface.\n"
        "\n"
        "This is a DIFFERENT axis from the two above: those say WHAT it\n"
        "may do and who wins when both want the same value; this one,\n"
        "only how much we tell it beforehand. With 'How far it goes on\n"
        "its own' set to nada, nothing travels and this makes no difference.",
    "Cuando se abre":
        "When it opens",
    "Cuando se ve":
        "When it shows",
    "Cuantas ramas explora el reconocedor. Medido sobre una orden\n"
    "tipica: beam 5 tarda 4.4s y beam 1 tarda 3.5s, con el MISMO texto.\n"
    "Sirve para dictado largo, no para ordenes de ocho palabras.":
        "How many branches the recognizer explores. Measured on a typical\n"
        "command: beam 5 takes 4.4s and beam 1 takes 3.5s, with the SAME text.\n"
        "Useful for long dictation, not for eight-word commands.",
    "Cuanto se queda cada subtitulo despues de que Eve termina de\n"
    "hablar. Hasta ahora solo se podia cambiar editando el config.":
        "How long each subtitle stays after Eve finishes speaking.\n"
        "Until now this could only be changed by editing the config.",
    "Cuentas":
        "Accounts",
    "Degradado (si no hay imagen)":
        "Gradient (when there is no image)",
    "Degradado: color 1":
        "Gradient: color 1",
    "Degradado: color 2":
        "Gradient: color 2",
    "Descargala primero.":
        "Download it first.",
    "Descargando...":
        "Downloading...",
    "Descargar":
        "Download",
    "Deshacer":
        "Undo",
    "Despertarla diciendo su nombre":
        "Wake it by saying its name",
    "Destildar uno lo saca del prompt: deja de gastar tokens y Eve deja de\n"
    "ofrecerlo. Si no hay ninguno tildado, se usan todos los disponibles.":
        "Unchecking one takes it out of the prompt: it stops costing tokens and\n"
        "Eve stops offering it. If none are checked, all available ones are used.",
    "Discord: URL del avatar":
        "Discord: avatar URL",
    "Discord: URL del webhook":
        "Discord: webhook URL",
    "Discord: escribir como tu (maneja tu cliente; verifica el canal por titulo)":
        "Discord: type as you (drives your client; checks the channel by title)",
    "Discord: nombre a mostrar":
        "Discord: display name",
    "Dispositivo":
        "Device",
    "Duplicar":
        "Duplicate",
    "Effort":
        "Effort",
    "El GIF se anima solo. La opacidad se mezcla en la imagen y no en la ventana,\n"
    "asi que bajarla atenua el fondo pero el texto sigue entero.":
        "The GIF animates on its own. Opacity is blended into the image and not\n"
        "into the window, so lowering it dims the background but the text stays solid.",
    "El cartel esta suelto: arrastralo a donde quieras y sueltalo.\n"
    "\n"
    "Al soltarlo se guarda la posicion y vuelve a dejar pasar los clics.":
        "The card is loose: drag it wherever you want and drop it.\n"
        "\n"
        "On drop the position is saved and it goes back to letting clicks through.",
    "El cartel normalmente deja pasar los clics al programa de atras.\n"
    "  nunca   nunca los toma\n"
    "  hover   solo mientras el puntero esta sobre un modulo marcado\n"
    "          como 'interactivo'; si no marcaste ninguno, es igual\n"
    "          que 'nunca'\n"
    "  fijo    siempre los toma, y siempre tapa lo que este debajo\n"
    "Se pregunta donde esta el puntero treinta veces por segundo en vez\n"
    "de escuchar eventos, porque una ventana que deja pasar los clics\n"
    "tampoco recibe los de movimiento: esperarlos seria esperar para\n"
    "siempre. Ese mismo poll es el que hace andar 'cuando = hover'.":
        "The card normally lets clicks through to the program behind it.\n"
        "  nunca   never takes them\n"
        "  hover   only while the pointer is over a module marked as\n"
        "          'interactivo'; if you marked none, this is the same\n"
        "          as 'nunca'\n"
        "  fijo    always takes them, and always covers whatever is underneath\n"
        "The pointer position is polled thirty times a second instead of\n"
        "listening for events, because a window that lets clicks through does\n"
        "not receive motion events either: waiting for them would mean waiting\n"
        "forever. That same poll is what makes 'when = hover' work.",
    "El cartel vuelve a la esquina de arriba a la izquierda.":
        "The card goes back to the top-left corner.",
    "El catalogo de programas viaja en CADA llamada al modelo, y entero\n"
    "es un tercio del prompt. 'usados' manda solo los que aparecen en tu\n"
    "log de acciones, ordenados por frecuencia, y el resto se busca con\n"
    "`E programa NOMBRE`. Medido: 1551 tokens menos por llamada, un 36%.\n"
    "'completo' los manda todos, por si prefieres pagar y no buscar.":
        "The program catalog travels on EVERY call to the model, and in full it\n"
        "is a third of the prompt. 'usados' sends only the ones that show up in\n"
        "your action log, ordered by frequency, and the rest are looked up with\n"
        "`E programa NAME`. Measured: 1551 fewer tokens per call, 36%.\n"
        "'completo' sends them all, in case you would rather pay than look up.",
    "El marco es parametrico: eliges cuantos lados, cuanto gira y cuanto se\n"
    "redondean las puntas. Las formas de abajo son atajos que llenan esos\n"
    "numeros; despues los puedes tocar a mano.":
        "The frame is parametric: you pick how many sides, how much it rotates\n"
        "and how rounded the corners are. The shapes below are shortcuts that\n"
        "fill in those numbers; you can tweak them by hand afterwards.",
    "El nombre no puede estar vacio.":
        "The name cannot be empty.",
    "Elegir imagen del icono...":
        "Choose icon image...",
    "Elegir...":
        "Choose...",
    "ElevenLabs voice_id":
        "ElevenLabs voice_id",
    "Elige un contacto de la lista primero.":
        "Pick a contact from the list first.",
    "Elige un modulo de la lista para ajustarlo.":
        "Pick a module from the list to edit it.",
    "Elige un perfil de la lista primero.":
        "Pick a profile from the list first.",
    "Elige un perfil de la lista.":
        "Pick a profile from the list.",
    "Elige una variante primero.":
        "Pick a variant first.",
    "Elige una voz de la lista.":
        "Pick a voice from the list.",
    "Es la tercera ventana de Eve, aparte del panel y del cartel. Ahi se\n"
    "ve que esta haciendo: los modulos que le pongas, el grafo de lo que\n"
    "ejecuto, el medidor de contexto y el lector de paginas.\n"
    "\n"
    "Tiene dos modos arriba, y no son dos pantallas sino quien puede\n"
    "escribir. En 'Work' se mira; en 'Edit' se agarran los modulos con el\n"
    "mouse: clic elige, Ctrl suma, Shift agrega un rango, arrastrar mueve\n"
    "y Ctrl+Z deshace. Con varios elegidos se editan las propiedades que\n"
    "TIENEN EN COMUN, y si el valor difiere el campo arranca vacio para\n"
    "que aplicar no los iguale sin querer.":
        "This is Eve's third window, apart from the panel and the card. It shows\n"
        "what she is doing: the modules you give it, the graph of what she ran,\n"
        "the context meter and the page reader.\n"
        "\n"
        "It has two modes at the top, and they are not two screens but who gets\n"
        "to write. In 'Work' you watch; in 'Edit' you grab the modules with the\n"
        "mouse: click selects, Ctrl adds, Shift adds a range, dragging moves and\n"
        "Ctrl+Z undoes. With several selected you edit the properties they HAVE\n"
        "IN COMMON, and if the value differs the field starts empty so that\n"
        "applying does not level them by accident.",
    "Escala (%)":
        "Scale (%)",
    "Eso no parece una app password":
        "That does not look like an app password",
    "Esto cierra tu sesion de Claude Code en toda la PC, no solo en Eve.\n"
    "\n"
    "El motor 'claude-code' va a dejar de funcionar hasta que vuelvas a entrar.\n"
    "\n"
    "Seguro?":
        "This signs you out of Claude Code on the whole PC, not just in Eve.\n"
        "\n"
        "The 'claude-code' engine will stop working until you sign back in.\n"
        "\n"
        "Are you sure?",
    "Estos archivos no se estan cargando. Un addon es codigo que corre\n"
    "con tus permisos y no pasa por el freno, asi que hay que mirarlo\n"
    "antes. Si Eve escribio alguno, aca es donde lo revisas.":
        "These files are not being loaded. An addon is code that runs with your\n"
        "permissions and does not go through the brake, so it has to be looked\n"
        "at first. If Eve wrote one, this is where you review it.",
    "Estos se cargan. Revocar no borra el archivo: lo devuelve a la\n"
    "lista de sin revisar, para que puedas volver a mirarlo antes de\n"
    "decidir de nuevo. Editar un addon aprobado lo saca solo, porque\n"
    "la aprobacion es de la huella del contenido y no del nombre.":
        "These are loaded. Revoking does not delete the file: it sends it back\n"
        "to the not-reviewed list, so you can look at it again before deciding\n"
        "anew. Editing an approved addon un-approves it on its own, because the\n"
        "approval is of the content hash and not of the name.",
    "Eve usa esta lista cuando nombras a alguien. En 'alias' pon como le dices\n"
    "de verdad, separado por comas (lucho, el lucas) — la voz rara vez dice el\n"
    "nombre completo.\n"
    "\n"
    "discord_user  = su @ (para mencionarlo dentro del mensaje)\n"
    "discord_dm    = su chat privado. Activa Ajustes > Avanzado > Modo desarrollador,\n"
    "                boton derecho sobre la conversacion > Copiar ID\n"
    "discord_canal = un canal de servidor. Boton derecho > Copiar enlace":
        "Eve uses this list when you name somebody. Under 'alias' put what you\n"
        "actually call them, comma separated (lucho, el lucas) — speech rarely\n"
        "uses the full name.\n"
        "\n"
        "discord_user  = their @ (to mention them inside the message)\n"
        "discord_dm    = their private chat. Turn on Settings > Advanced > Developer\n"
        "                mode, right-click the conversation > Copy ID\n"
        "discord_canal = a server channel. Right-click > Copy link",
    "Eve va a ejecutar cualquier comando que decida, sin preguntarte:\n"
    "borrar carpetas, apagar la PC, modificar el registro.\n"
    "\n"
    "El reconocimiento de voz se equivoca, y en este modo un error de\n"
    "transcripcion se ejecuta directo.\n"
    "\n"
    "Queda registrado en la pestaña Acciones, pero nada lo va a frenar.\n"
    "\n"
    "Activar igual?":
        "Eve will run any command she decides on, without asking you:\n"
        "deleting folders, shutting the PC down, editing the registry.\n"
        "\n"
        "Speech recognition makes mistakes, and in this mode a transcription\n"
        "error runs straight through.\n"
        "\n"
        "It is recorded in the Actions tab, but nothing is going to stop it.\n"
        "\n"
        "Turn it on anyway?",
    "Exportar":
        "Export",
    "Exportar genera un archivo .evecontact que puedes mandarle a un amigo por\n"
    "WhatsApp o Discord; el lo abre con Importar y le queda el contacto cargado.":
        "Export produces an .evecontact file you can send a friend over WhatsApp\n"
        "or Discord; they open it with Import and the contact is loaded for them.",
    "Exportar perfil":
        "Export profile",
    "Exportar...":
        "Export...",
    "Falta el CLI":
        "The CLI is missing",
    "Falta el nombre":
        "The name is missing",
    "Fondo de los subtitulos":
        "Subtitle background",
    "Fondo del cartel":
        "Card background",
    "Forma":
        "Shape",
    "Formas":
        "Shapes",
    "Fuente de los subtitulos":
        "Subtitle font",
    "Fuente del cartel":
        "Card font",
    "Fuente del panel":
        "Panel font",
    "General":
        "General",
    "Giro (grados)":
        "Rotation (degrees)",
    "Gmail":
        "Gmail",
    "Gmail: si 'Contrasenas de aplicaciones' no te aparece, tu cuenta no tiene 2FA\n"
    "o la administra tu organizacion. Alternativa sin claves: agrega el Gmail a\n"
    "Outlook (Archivo > Agregar cuenta) y Eve lo lee y escribe por ahi.\n"
    "Webhook: Editar canal > Integraciones > Webhooks. Steam key: steamcommunity.com/dev/apikey":
        "Gmail: if 'App passwords' does not show up, your account has no 2FA or\n"
        "your organization manages it. Key-free alternative: add the Gmail to\n"
        "Outlook (File > Add account) and Eve reads and writes through there.\n"
        "Webhook: Edit channel > Integrations > Webhooks. Steam key: steamcommunity.com/dev/apikey",
    "Grosor del trazo":
        "Stroke width",
    "Guardado":
        "Saved",
    "Guardar":
        "Save",
    "Guardar como...":
        "Save as...",
    "Guardar contacto para compartir":
        "Save a contact to share",
    "Habla ahora... (3 segundos)":
        "Speak now... (3 seconds)",
    "Hablando...":
        "Speaking...",
    "Hablante":
        "Speaker",
    "Hablante solo sirve en las voces que traen varias.":
        "Speaker only matters on voices that ship several.",
    "Hasta donde arma sola":
        "How much it can build on its own",
    "Hasta donde llega con los archivos":
        "How far it goes with files",
    "Hasta donde puede meterse":
        "How far it is allowed to go",
    "Que puede hacer Eve DENTRO de las rutas de arriba. Las rutas\n"
    "siguen siendo el limite: esto no agranda lo permitido, decide\n"
    "que hace adentro.\n"
    "  exacto     leer un archivo si le dictas la ruta entera\n"
    "  explorar   ademas listar una carpeta y buscar por nombre;\n"
    "             sin esto, encontrar algo dependia de que vos\n"
    "             supieras y dictaras la ruta\n"
    "  escribir   ademas crear y reemplazar. Pisar un archivo que\n"
    "             ya existe te pregunta primero, salvo que hayas\n"
    "             apagado la confirmacion aca arriba\n"
    "Con 'exacto' los comandos de explorar no existen para ella y\n"
    "tampoco se nombran en el prompt: una capacidad que no se puede\n"
    "usar solo gasta lugar e invita a que pruebe y le digan que no.":
        "What Eve may do INSIDE the paths above. Those paths are still\n"
        "the limit: this does not widen what is allowed, it decides what\n"
        "it does inside.\n"
        "  exacto     read a file if you dictate the whole path\n"
        "  explorar   plus list a folder and search by name; without it,\n"
        "             finding anything depended on you knowing and\n"
        "             dictating the path\n"
        "  escribir   plus create and replace. Overwriting a file that\n"
        "             already exists asks you first, unless you turned\n"
        "             the confirmation above off\n"
        "With 'exacto' the exploring commands do not exist for it and are\n"
        "not named in the prompt either: a capability that cannot be used\n"
        "only wastes room and invites it to try and be told no.",
    "Historial limpiado":
        "History cleared",
    "Icono":
        "Icon",
    "Idioma":
        "Language",
    "Idioma del panel":
        "Panel language",
    "Idioma en que te habla":
        "Language it speaks",
    "Imagen (PNG o GIF)":
        "Image (PNG or GIF)",
    "Imagen de cabecera":
        "Header image",
    "Imagen para el icono":
        "Icon image",
    "Importar":
        "Import",
    "Importar .plist":
        "Import .plist",
    "Importar perfil":
        "Import profile",
    "Importar...":
        "Import...",
    "Indice actualizado.":
        "Index updated.",
    "Iniciar sesion":
        "Sign in",
    "Instalados":
        "Installed",
    "La agenda que Eve usa cuando nombras a alguien.":
        "The address book Eve uses when you name someone.",
    "La clave de cada uno va en la pestaña Cuentas. 'propio' sirve para\n"
    "cualquier servidor que hable /chat/completions.":
        "The key for each one goes in the Accounts tab. 'propio' works for\n"
        "any server that speaks /chat/completions.",
    "La configuracion cambio por fuera. Guarda o cierra para recargarla.":
        "The config changed outside. Save or close to reload it.",
    "La tecla la escucha el asistente, no este panel: si el asistente no\n"
    "esta corriendo, el boton te lo dice en vez de dejarte probando una\n"
    "tecla que nadie escucha.":
        "The key is listened for by the assistant, not by this panel: if the\n"
        "assistant is not running, the button tells you so instead of leaving\n"
        "you testing a key nobody is listening for.",
    "La ventana de actividad":
        "The activity window",
    "Lados (menos de 3 = circulo)":
        "Sides (fewer than 3 = circle)",
    "Le manda una pregunta trivial y muestra la respuesta y cuanto tardo.\n"
    "Es la unica forma de saber que el motor esta bien configurado sin\n"
    "tener que hablarle y quedarse esperando a ver si contesta.":
        "Sends it a trivial question and shows the answer and how long it took.\n"
        "It is the only way to know the engine is configured right without\n"
        "having to talk to her and wait to see whether she answers.",
    "Leer las respuestas en voz alta":
        "Read answers out loud",
    "Limpiar campos":
        "Clear fields",
    "Limpiar historial":
        "Clear history",
    "Limpiar historial y contexto":
        "Clear history and context",
    "Lineas maximas":
        "Maximum lines",
    "Listener reiniciado":
        "Listener restarted",
    "Listo":
        "Done",
    "Lo esencial":
        "Essentials",
    "Lo hace aparecer unos segundos aunque este en modo 'auto'. Es lo que\n"
    "separa 'el cartel esta mal configurado' de 'el cartel no arranca'.":
        "Makes it appear for a few seconds even in 'auto' mode. It is what\n"
        "separates 'the card is misconfigured' from 'the card never starts'.",
    "Lo mas simple es agregarlo a Outlook con el boton de arriba: Google hace el\n"
    "login y no queda ninguna clave tuya guardada aca.\n"
    "\n"
    "La otra via es una contrasena de aplicacion (16 letras minusculas). Si Google\n"
    "dice que no esta disponible, es que tu cuenta no tiene verificacion en dos\n"
    "pasos, o la administra tu organizacion.":
        "The simplest way is to add it to Outlook with the button above: Google\n"
        "handles the login and none of your keys end up stored here.\n"
        "\n"
        "The other way is an app password (16 lowercase letters). If Google says\n"
        "it is not available, your account has no two-step verification, or your\n"
        "organization manages it.",
    "Lo que Eve puede manejar ademas de tu PC. Cada uno trae sus comandos.":
        "What Eve can drive besides your PC. Each one brings its own commands.",
    "Los colores de todo, y el cartel que Eve muestra encima de lo que estes haciendo.":
        "The colors of everything, and the card Eve shows over whatever you are doing.",
    "Los dos vacios = el modelo sugerido y la URL del proveedor.":
        "Both empty = the suggested model and the provider's URL.",
    "Los editores de particulas --Particle Designer, Particle2dx--\n"
    "exportan el .plist de cocos2d, que es XML de numeros: vida,\n"
    "gravedad, color, velocidad. Se importa la CONFIGURACION y la\n"
    "corre el simulador que ya esta, asi que no entra ninguna\n"
    "libreria nueva. Llena los campos de arriba; despues Aplicar.\n"
    "No viaja lo que el simulador no sabe hacer: modo radial,\n"
    "texturas por particula y mezclas aditivas.":
        "Particle editors --Particle Designer, Particle2dx-- export the cocos2d\n"
        ".plist, which is XML full of numbers: life, gravity, color, speed.\n"
        "What gets imported is the CONFIGURATION, and the simulator that is\n"
        "already here runs it, so no new library comes in. It fills the fields\n"
        "above; then press Apply.\n"
        "What the simulator cannot do does not travel: radial mode, per-particle\n"
        "textures and additive blending.",
    "Marco del icono":
        "Icon frame",
    "Max tokens":
        "Max tokens",
    "Menos de 10 se trata como 10: por debajo de eso el cartel no se ve\n"
    "y no habria forma de encontrarlo para subirlo de nuevo. La opacidad\n"
    "de cada modulo se MULTIPLICA con esta, asi que 20% de ventana por\n"
    "20% de modulo da 4% de verdad.":
        "Anything under 10 is treated as 10: below that the card cannot be seen\n"
        "and there would be no way to find it to raise it again. Each module's\n"
        "opacity is MULTIPLIED with this one, so 20% window times 20% module is\n"
        "really 4%.",
    "Minutos de contexto":
        "Context minutes",
    "Modelo (motor api)":
        "Model (api engine)",
    "Modelo (motor claude-code)":
        "Model (claude-code engine)",
    "Modelo Whisper local":
        "Local Whisper model",
    "Modelo de la puerta":
        "Gate model",
    "Modulos":
        "Modules",
    "Mostrar el cartel":
        "Show the card",
    "Mostrar un subtitulo de prueba":
        "Show a test subtitle",
    "Motor":
        "Engine",
    "Mover el cartel":
        "Move the card",
    "Mover en pantalla":
        "Move on screen",
    "Nada elegido.":
        "Nothing selected.",
    "Necesitas al menos una ruta de trabajo permitida.":
        "You need at least one allowed working path.",
    "No animar los GIF (dejar el primer cuadro)":
        "Do not animate GIFs (keep the first frame)",
    "No encontre 'claude' en el PATH.":
        "I could not find 'claude' on the PATH.",
    "No hay ninguno cargado.":
        "None loaded.",
    "No hay webhook cargado.":
        "No webhook saved.",
    "No necesita ninguna clave: Eve usa la sesion que ya tiene Outlook en esta PC.":
        "No key needed: Eve uses the session Outlook already has on this PC.",
    "No pude actualizar":
        "I could not update",
    "No pude cambiar de perfil":
        "I could not switch profiles",
    "No pude leer ese archivo. Tiene que ser un .plist de cocos2d (el que exportan Particle Designer y Particle2dx).":
        "I could not read that file. It has to be a cocos2d .plist (the one Particle Designer and Particle2dx export).",
    "No pude leerlo":
        "I could not read it",
    "No pude reiniciar el listener":
        "I could not restart the listener",
    "Nombre de la IA":
        "Assistant name",
    "Nombres que el reconocimiento suele errar, separados por comas.":
        "Names the recognizer usually gets wrong, comma separated.",
    "Obtener app password":
        "Get an app password",
    "Ollama: host":
        "Ollama: host",
    "Ollama: modelo":
        "Ollama: model",
    "Onda":
        "Waveform",
    "Opacidad (%)":
        "Opacity (%)",
    "Opacidad de la imagen (%)":
        "Image opacity (%)",
    "Otros motores":
        "Other engines",
    "Outlook":
        "Outlook",
    "Palabra para despertarla":
        "Wake word",
    "Pantalla":
        "Display",
    "Parakeet: cuantizacion":
        "Parakeet: quantization",
    "Particulas":
        "Particles",
    "Particulas de Particle Designer":
        "Particle Designer particles",
    "Pausar listener":
        "Pause the listener",
    "Perfil activo":
        "Active profile",
    "Perfiles":
        "Profiles",
    "Permisos":
        "Permissions",
    "Permisos (motor claude-code)":
        "Permissions (claude-code engine)",
    "Permitir todo":
        "Allow everything",
    "Personalidad":
        "Personality",
    "Pintar el panel obliga a dibujar los controles por nuestra cuenta: Windows\n"
    "no deja cambiarle el color a los suyos. El cambio se ve al instante.":
        "Painting the panel forces us to draw the controls ourselves: Windows\n"
        "does not let you recolor its own. The change shows up instantly.",
    "Pintar tambien este panel con el tema":
        "Paint this panel with the theme too",
    "Posicion":
        "Position",
    "Probar":
        "Test",
    "Probar GPU":
        "Test the GPU",
    "Probar conexion":
        "Test the connection",
    "Probar el motor":
        "Test the engine",
    "Probar el webhook":
        "Test the webhook",
    "Probar la palabra":
        "Test the wake word",
    "Probar la tecla":
        "Test the key",
    "Probar que te escucha":
        "Test that it hears you",
    "Probar que te habla":
        "Test that it speaks",
    "Programas":
        "Programs",
    "Programas que Eve conoce":
        "Programs Eve knows about",
    "Que catalogo viaja":
        "Which catalog travels",
    "Que espanol habla":
        "Which Spanish it speaks",
    "Que se dijo y que se ejecuto en tu PC.":
        "What was said and what ran on your PC.",
    "Que se muestra":
        "What is shown",
    "Que voz se entiende mejor. Medido sobre diez frases, sintetizando\n"
    "y volviendo a transcribir --si el mejor reconocedor que hay no la\n"
    "entiende, tu con el juego de fondo tampoco:\n"
    "  es_ES-sharvard-medium   6.4%     es_ES-carlfm-x_low  10.0%\n"
    "  es_MX-claude-high       6.8%     es_MX-ald-medium    10.4%\n"
    "  es_ES-davefx-medium     8.4%     es_MX-ald-x_low     11.2%\n"
    "                                   es_AR-daniela-high  20.5%\n"
    "Es la media de tres corridas, y hacen falta las tres: Piper no es\n"
    "determinista y una misma voz se mueve hasta 8 puntos. Con una sola\n"
    "medicion casi todo este orden seria ruido.\n"
    "Lo que sobrevive: es_AR-daniela-high es la peor por mucho y la mas\n"
    "lenta por cinco veces. Por eso ninguna variante la sugiere: la voz\n"
    "es el canal, no el acento del que habla. Si aun asi la quieres,\n"
    "eligela a mano en Voz de Piper.":
        "Which voice is easiest to understand. Measured over ten sentences,\n"
        "synthesizing them and transcribing them back --if the best recognizer\n"
        "there is cannot understand it, neither can you with a game behind:\n"
        "  es_ES-sharvard-medium   6.4%     es_ES-carlfm-x_low  10.0%\n"
        "  es_MX-claude-high       6.8%     es_MX-ald-medium    10.4%\n"
        "  es_ES-davefx-medium     8.4%     es_MX-ald-x_low     11.2%\n"
        "                                   es_AR-daniela-high  20.5%\n"
        "That is the mean of three runs, and all three are needed: Piper is not\n"
        "deterministic and the same voice moves by up to 8 points. With a single\n"
        "measurement almost all of this ordering would be noise.\n"
        "What survives: es_AR-daniela-high is the worst by far and five times the\n"
        "slowest. That is why no variant suggests it: the voice is the channel,\n"
        "not the accent of the speaker. If you still want it, pick it by hand\n"
        "under Piper voice.",
    "Quien es Eve":
        "Who Eve is",
    "Quien es Eve, quien piensa por ella y hasta donde puede meterse.":
        "Who Eve is, who thinks for her, and how far she is allowed to go.",
    "Quien manda sobre un ajuste":
        "Who wins on a setting",
    "Quien piensa por ella":
        "Who thinks for her",
    "Quitar":
        "Remove",
    "Recortar silencios antes de transcribir (VAD)":
        "Trim silence before transcribing (VAD)",
    "Redondeo de las puntas":
        "Corner rounding",
    "Reescanear programas":
        "Rescan programs",
    "Reglas por horario":
        "Time-of-day rules",
    "Reiniciar listener (aplicar config)":
        "Restart the listener (apply config)",
    "Revocar":
        "Revoke",
    "Rutas de trabajo permitidas (una por linea)":
        "Allowed working paths (one per line)",
    "Rutas vacias":
        "No paths",
    "STT (reconocimiento)":
        "STT (recognition)",
    "Salir":
        "Quit",
    "Se abrio una consola con el login de Claude Code.\n"
    "Cuando termines, toca 'Actualizar' para ver el estado.":
        "A console opened with the Claude Code login.\n"
        "When you are done, press 'Refresh' to see the status.",
    "Se guardan en el gestor de credenciales de Windows, nunca en texto plano.\n"
    "Anthropic solo hace falta con el motor 'api'; con 'claude-code' se usa tu suscripcion.\n"
    "Las otras habilitan proveedores opcionales de voz.":
        "They are stored in the Windows credential manager, never in plain text.\n"
        "Anthropic is only needed with the 'api' engine; with 'claude-code' your\n"
        "subscription is used. The others enable optional voice providers.",
    "Se manda un mensaje de prueba al canal de Discord de ese webhook.\n"
    "\n"
    "Lo van a ver todos los que esten en el canal.\n"
    "\n"
    "Mandarlo?":
        "A test message is sent to the Discord channel of that webhook.\n"
        "\n"
        "Everybody in the channel will see it.\n"
        "\n"
        "Send it?",
    "Se ve arriba de cada pestaña y se aplica al reabrir el panel. No hay fondo\n"
    "para todo el panel: los controles de Windows pintan su propio fondo opaco\n"
    "y lo taparian.":
        "It shows at the top of every tab and applies when the panel is reopened.\n"
        "There is no background for the whole panel: Windows controls paint their\n"
        "own opaque background and would cover it.",
    "Segunda linea":
        "Second line",
    "Segundos en pantalla":
        "Seconds on screen",
    "Sensibilidad":
        "Sensitivity",
    "Separacion del cartel (px)":
        "Distance from the card (px)",
    "Sesion de Claude Code (motor 'claude-code')":
        "Claude Code session ('claude-code' engine)",
    "Sin esto Eve igual abre WhatsApp, Discord, Telegram y el mail con el\n"
    "mensaje escrito, para que lo mandes tu. Estas claves solo agregan leer\n"
    "y enviar sin pasar por la app.":
        "Without this Eve still opens WhatsApp, Discord, Telegram and mail with\n"
        "the message already typed, for you to send. These keys only add reading\n"
        "and sending without going through the app.",
    "Sin revisar":
        "Not reviewed",
    "Steam: Web API key":
        "Steam: Web API key",
    "Subtitulo de prueba mostrado. Si no aparecio, revisa 'Que se muestra' y los segundos en pantalla.":
        "Test subtitle shown. If nothing appeared, check 'What is shown' and the seconds on screen.",
    "Subtitulos":
        "Subtitles",
    "TTS (voz)":
        "TTS (voice)",
    "Tamano de letra":
        "Font size",
    "Tamaño (0 = el de la fuente)":
        "Size (0 = whatever the font brings)",
    "Te abri la pagina de contrasenas de aplicacion.\n"
    "\n"
    "Si dice que no esta disponible para tu cuenta, es porque no tienes\n"
    "verificacion en dos pasos activada, o la administra tu organizacion.\n"
    "\n"
    "En ese caso usa el boton de Outlook: agregas el Gmail ahi y listo.":
        "I opened the app passwords page for you.\n"
        "\n"
        "If it says it is not available for your account, it is because you do\n"
        "not have two-step verification on, or your organization manages it.\n"
        "\n"
        "In that case use the Outlook button: you add the Gmail there and done.",
    "Tecla del keypad":
        "Keypad key",
    "Tema":
        "Theme",
    "Tema (vacio = el del panel)":
        "Theme (empty = the panel's)",
    "Tinte con el acento (%)":
        "Accent tint (%)",
    "Tipo de computo":
        "Compute type",
    "Tipografia":
        "Typography",
    "Titulo (vacio = nombre IA)":
        "Title (empty = assistant name)",
    "Todo":
        "Everything",
    "Todo lo de aca esta medido sobre las mismas 24 grabaciones propias.\n"
    "\n"
    "Sensibilidad:\n"
    "  normal  cuarto tranquilo         WER 10.9%  (con ruido 12.5%)\n"
    "  ruido   musica o el juego atras  WER  8.7%  (con ruido  0.0%)\n"
    "  bajo    de madrugada, voz suave  WER 12.0%  (con ruido 18.8%)\n"
    "  manual  usa el umbral y el aire de mas abajo\n"
    "\n"
    "Que modelo conviene:\n"
    "  small     WER 10.9%   0.9s por orden en gpu,  3.3s en cpu\n"
    "  medium    WER  4.9%   1.8s en gpu, 10.2s en cpu  <- pide gpu\n"
    "  large-v3  WER  4.9%   2.7s en gpu, y PEOR en nombres propios\n"
    "            (34.8% contra 17.4% de medium): mas grande no es\n"
    "            mejor aca.":
        "Everything here is measured on the same 24 recordings of our own.\n"
        "\n"
        "Sensitivity:\n"
        "  normal  quiet room                WER 10.9%  (noisy group 12.5%)\n"
        "  ruido   music or a game behind    WER  8.7%  (noisy group  0.0%)\n"
        "  bajo    late at night, soft voice WER 12.0%  (noisy group 18.8%)\n"
        "  manual  uses the threshold and padding below\n"
        "\n"
        "Which model is worth it:\n"
        "  small     WER 10.9%   0.9s per command on gpu,  3.3s on cpu\n"
        "  medium    WER  4.9%   1.8s on gpu, 10.2s on cpu  <- wants a gpu\n"
        "  large-v3  WER  4.9%   2.7s on gpu, and WORSE on proper nouns\n"
        "            (34.8% against medium's 17.4%): bigger is not\n"
        "            better here.",
    "Toma clics":
        "Takes clicks",
    "Tono":
        "Tone",
    "Traer los del cartel actual":
        "Bring the ones from the current card",
    "Tu SteamID64 (autodetectado)":
        "Your SteamID64 (auto-detected)",
    "Tu direccion de Gmail":
        "Your Gmail address",
    "Turnos de contexto":
        "Context turns",
    "Umbral del detector":
        "Detector threshold",
    "Un perfil guarda como se ve y como suena Eve: colores, forma, fuente,\n"
    "voz, velocidad, tono y el nombre del asistente.\n"
    "NO toca el motor, el modelo, la tecla, los permisos ni tus datos: un\n"
    "perfil que te pasan no puede cambiarte como trabaja el asistente.":
        "A profile stores how Eve looks and sounds: colors, shape, font, voice,\n"
        "speed, tone and the assistant's name.\n"
        "It does NOT touch the engine, the model, the key, the permissions or\n"
        "your data: a profile somebody hands you cannot change how the assistant\n"
        "works.",
    "Usar esta":
        "Use this one",
    "Usar la voz que le corresponde":
        "Use the matching voice",
    "Vacio = el cartel usa el mismo tema que el panel, que es lo que\n"
    "quiere casi todo el mundo. Los colores de abajo solo se usan con\n"
    "el tema 'personalizado'.":
        "Empty = the card uses the same theme as the panel, which is what almost\n"
        "everybody wants. The colors below are only used with the\n"
        "'personalizado' theme.",
    "Valor invalido":
        "Invalid value",
    "Van separadas por coma y solo pisan al modo 'auto':\n"
    "  00:00-06:00=bajo, 20:00-23:59=ruido\n"
    "Si eliges un modo a mano, el reloj no te lo cambia.":
        "Comma separated, and they only override the 'auto' mode:\n"
        "  00:00-06:00=bajo, 20:00-23:59=ruido\n"
        "If you pick a mode by hand, the clock does not change it on you.",
    "Variante":
        "Variant",
    "Velocidad":
        "Speed",
    "Velocidad 1.0 = normal, mas alto = mas lento. Volumen 1.0 = como sale del sintetizador.":
        "Speed 1.0 = normal, higher = slower. Volume 1.0 = as the synthesizer produces it.",
    "Ventana de actividad":
        "Activity window",
    "Ver":
        "Show",
    "Ver el codigo":
        "View the code",
    "Vocabulario extra":
        "Extra vocabulary",
    "Voces":
        "Voices",
    "Voces entrenadas por la comunidad (Piper). Gratis, offline, y las unicas\n"
    "que suenan igual en Windows, macOS y Linux. Se verifica el md5 al descargar.":
        "Community-trained voices (Piper). Free, offline, and the only ones that\n"
        "sound the same on Windows, macOS and Linux. The md5 is checked on download.",
    "Volumen":
        "Volume",
    "Volver a la esquina":
        "Back to the corner",
    "Voz":
        "Voice",
    "Voz de Piper":
        "Piper voice",
    "Voz de Windows":
        "Windows voice",
    "WhatsApp: enviar solo (simula el Enter; exige numero, no nombre)":
        "WhatsApp: send on its own (fakes the Enter; needs a number, not a name)",
    "Ya existe":
        "Already there",
    "Ya existen":
        "Already there",
    "actividad":
        "activity",
    "activo":
        "running",
    "ambos = lo que dijiste tu (para ver si te entendio) y lo que responde Eve,\n"
    "revelandose mientras lo dice.":
        "ambos = what you said (to see whether it understood you) and what Eve\n"
        "answers, revealed as she says it.",
    "auto = aparece al hablarle y se va sola. Nunca se lleva el foco de lo que\n"
    "estes haciendo, y los clics la atraviesan.":
        "auto = it appears when you talk to her and leaves on its own. It never\n"
        "takes focus away from what you are doing, and clicks pass through it.",
    "clic para elegir · Ctrl suma · Shift agrega un rango · arrastra para mover":
        "click to select · Ctrl adds · Shift adds a range · drag to move",
    "compat: URL propia":
        "compat: your own URL",
    "compat: modelo":
        "compat: model",
    "compat: proveedor":
        "compat: provider",
    "consultando catalogo...":
        "fetching the catalog...",
    "consultando...":
        "checking...",
    "cuda necesita las librerias de NVIDIA instaladas; si faltan, cae a cpu\n"
    "solo y avisa. Medido en una GTX 1660 SUPER: 3.42s por orden en cpu\n"
    "contra 0.71s en gpu. 'auto' elige int8 en cpu e int8_float16 en gpu.":
        "cuda needs the NVIDIA libraries installed; if they are missing it falls\n"
        "back to cpu on its own and says so. Measured on a GTX 1660 SUPER: 3.42s\n"
        "per command on cpu against 0.71s on gpu. 'auto' picks int8 on cpu and\n"
        "int8_float16 on gpu.",
    "descargando actualizacion...":
        "downloading the update...",
    "listo: el cartel de siempre, ahora como modulos":
        "done: the usual card, now made of modules",
    "mandando...":
        "sending...",
    "nada con esas palabras":
        "nothing matches those words",
    "no hay nada para deshacer":
        "nothing to undo",
    "parakeet es el modelo de NVIDIA. Entro porque gano medido sobre las\n"
    "mismas 24 grabaciones, con la misma cuenta:\n"
    "  whisper small en gpu   WER 10.9%   RTF 0.27    464 MB\n"
    "  whisper small en cpu   WER 10.9%   RTF 1.38    464 MB\n"
    "  whisper medium en gpu  WER  5.4%   RTF 0.61    1.5 GB\n"
    "  parakeet int8 en CPU   WER  7.1%   RTF 0.19    639 MB\n"
    "Lo que importa no es el punto y medio de WER: es que ese 0.19 es EN\n"
    "CPU. Whisper small tarda siete veces mas sin GPU, y la mayoria de las\n"
    "instalaciones no tienen CUDA configurado.\n"
    "\n"
    "Donde pierde: nombres propios, 30.4% contra 21.7%, que es justo el\n"
    "grupo que decide si abre el programa correcto -- no acepta el sesgo\n"
    "de vocabulario que si acepta whisper. Por eso no es el default.\n"
    "Sin cuantizar mejora los nombres propios pero pesa 2.4 GB.":
        "parakeet is NVIDIA's model. It got in because it won, measured on the\n"
        "same 24 recordings with the same arithmetic:\n"
        "  whisper small on gpu   WER 10.9%   RTF 0.27    464 MB\n"
        "  whisper small on cpu   WER 10.9%   RTF 1.38    464 MB\n"
        "  whisper medium on gpu  WER  5.4%   RTF 0.61    1.5 GB\n"
        "  parakeet int8 on CPU   WER  7.1%   RTF 0.19    639 MB\n"
        "What matters is not the point and a half of WER: it is that the 0.19 is\n"
        "ON CPU. Whisper small takes seven times longer without a GPU, and most\n"
        "installs have no CUDA configured.\n"
        "\n"
        "Where it loses: proper nouns, 30.4% against 21.7%, which is exactly the\n"
        "group that decides whether it opens the right program -- it does not\n"
        "accept the vocabulary bias that whisper does. That is why it is not the\n"
        "default. Un-quantized it does better on proper nouns but weighs 2.4 GB.",
    "pausado":
        "paused",
    "preguntando...":
        "asking...",
    "probando, puede tardar unos segundos...":
        "testing, this can take a few seconds...",
    "probando...":
        "testing...",
    "recortado = el cartel deja de ser un rectangulo y por las esquinas cortadas\n"
    "de los contornos hexagonal y biselado se ve lo que hay atras.":
        "recortado = the card stops being a rectangle, and through the cut\n"
        "corners of the hexagonal and beveled outlines you see what is behind.",
    "tablero armado: abre la ventana de actividad":
        "board built: open the activity window",
    "usuario: lo que cambies a mano queda trabado y Eve no lo pisa.\n"
    "eve: puede cambiar lo que quiera.  preguntar: pide permiso cada vez.\n"
    "Para soltar lo trabado, dile 'destraba <clave>' o borra la lista abajo.":
        "usuario: whatever you change by hand is locked and Eve does not\n"
        "overwrite it. eve: she can change whatever she wants.  preguntar: she\n"
        "asks permission every time.\n"
        "To release what is locked, tell her 'destraba <key>' or clear the list below.",
    "ventana de actividad abierta":
        "activity window opened",
}
TABLA = {"en": EN}
