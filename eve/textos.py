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
    'El panel se cierra para volver a armarse con el tema nuevo. Abrelo otra vez para verlo.':
        'The panel closes so it can be rebuilt with the new theme. Open it again to see it.',
    'Catalogo de voces':
        'Voice catalogue',
    'El panel se cierra para volver a armarse con el tema nuevo. Abrelo otra vez para verlo.':
        'The panel closes so it can be rebuilt with the new theme. Open it again to see it.',
    'Ese viene con el programa y no se borra. Guarda uno propio con el mismo nombre si quieres cambiarlo.':
        'That one ships with the program and cannot be deleted. Save your own with the same name to change it.',
    'Un clic para elegirlo, dos para aplicarlo. Los que dicen (de fabrica)\nno se borran: guardar uno propio con el mismo nombre no los pisa.':
        'One click to pick it, two to apply it. The ones marked (stock) cannot\nbe deleted: saving your own with the same name does not overwrite them.',
    'Abrir contactos compartidos':
        'Open shared contacts',
    'Entraron':
        'Imported',
    'Guardarlo con el nombre:':
        'Save it under the name:',
    'Importar perfiles':
        'Import profiles',
    'No entraron':
        'Not imported',
    'Se reemplaza?':
        'Replace it?',
    'Ya hay un perfil':
        'There is already a profile named',
    'de fabrica':
        'stock',
    'Abrir Comandos.md':
        'Open Comandos.md',
    'Al decir':
        'Saying',
    'Comandos':
        'Commands',
    'Comandos por voz':
        'Voice commands',
    "Con 'si', una frase que coincida con las de Comandos.md se\nresuelve sin llamar al modelo. Con 'no', todo va al modelo\ncomo antes, y el archivo se ignora.\nLa coincidencia es EXACTA --sin mayusculas ni acentos-- y no\ndifusa a proposito: un comando que a veces agarra es peor que\nuno que no existe.":
        "With 'si', a phrase matching one in Comandos.md resolves\nwithout calling the model. With 'no', everything goes to the\nmodel as before and the file is ignored.\nMatching is EXACT --no case, no accents-- and deliberately not\nfuzzy: a command that works sometimes is worse than one that\ndoes not exist.",
    'Elige uno de la lista.':
        'Pick one from the list.',
    'Ese no corre nada: no hace falta aprobarlo.':
        'That one runs nothing: no approval needed.',
    'Frases que hacen algo fijo':
        'Phrases that do something fixed',
    'Frases tuyas que hacen algo fijo, sin pasar por el modelo.':
        'Phrases of yours that do something fixed, without going through the model.',
    'Lo apruebo?':
        'Approve it?',
    'Recargar':
        'Reload',
    'Revisar y aprobar':
        'Review and approve',
    'SIN APROBAR':
        'NOT APPROVED',
    'Todavia no hay comandos. Abre el archivo y escribe uno.':
        'No commands yet. Open the file and write one.',
    'Todos listos.':
        'All set.',
    'aprobado':
        'approved',
    'le mandaria al modelo':
        'would send to the model',
    'se va a correr':
        'will run',
    'sin aprobar: esas frases no hacen nada todavia.':
        'not approved: those phrases do nothing yet.',
    'sin riesgo':
        'harmless',
    'no necesita clave':
        'no key needed',
    'clave cargada':
        'key loaded',
    'sin clave':
        'no key',
    'falta la clave, cargala abajo':
        'key missing, load it below',
    'Skills que le pasas':
        'Skills you hand her',
    "Una skill es un .md tuyo con instrucciones: como quieres un\ninforme, como se hace un deploy, con que tono le escribes a un\ncliente.\n  nada        no existen para ella\n  consultar   viaja el INDICE --nombre y un renglon-- y el texto\n              entero lo pide con 'E skill ver' cuando hace falta\n  completo    viajan enteras, siempre\nLa diferencia se paga en CADA frase que le digas, incluido 'que\nhora es'. Medido con cinco skills de una pagina: 'consultar'\nsuma 4% al prompt y 'completo' 145%, o sea que lo duplica.":
        "A skill is a .md of yours with instructions: how you want a\nreport, how a deploy is done, what tone you use with a client.\n  nada        they do not exist for her\n  consultar   the INDEX travels --name and one line-- and the\n              full text is fetched with 'E skill ver' when needed\n  completo    they travel whole, always\nThe difference is paid on EVERY sentence you say, 'what time is\nit' included. Measured with five one-page skills: 'consultar'\nadds 4% to the prompt and 'completo' 145%, i.e. it doubles it.",
    'Skills':
        'Skills',
    'Importar skill...':
        'Import a skill...',
    'Elige los .md de las skills':
        "Pick the skill's .md",
    'Cuanto de las skills viaja':
        'How much of the skills travels',
    '(ninguna todavia)':
        '(none yet)',
    'Modelos y claves':
        'Models and keys',
    'Cual piensa, cual te escucha, cual te habla, y la clave de cada uno.':
        "Which one thinks, which one hears you, which one speaks, and each one's key.",
    'Las apps a las que Eve le escribe. Todo opcional.':
        'The apps Eve writes to. All optional.',
    'Asignar tecla':
        'Assign a key',
    'presiona la tecla que quieras...':
        'press whichever key you want...',
    '(Escape cancela)':
        '(Escape cancels)',
    'cancelado':
        'cancelled',
    'Recuerda Guardar.':
        'Remember to hit Save.',
    'no llego ninguna tecla':
        'no key came through',
    'Importar voz...':
        'Import a voice...',
    'Elige los .onnx de las voces':
        "Pick the voice's .onnx",
    'Voz de Piper':
        'Piper voice',
    'Todos':
        'All',
    'importada':
        'imported',
    'instalada':
        'installed',
    'propia':
        'yours',
    'no pude copiarla':
        'could not copy it',
    'Buscar modelos':
        'Find models',
    'Modelos disponibles':
        'Available models',
    'Usar este':
        'Use this one',
    'disponibles':
        'available',
    'preguntando...':
        'asking...',
    'no pude preguntarle':
        'could not ask it',
    'el servicio no publica ninguno':
        'the service does not publish any',
    'El modelo era un campo de texto libre, y eso obliga a saber el\nidentificador exacto: OpenRouter publica cientos y LM Studio\nsirve el que hayas cargado. El boton se los pregunta al propio\nservicio --`GET /v1/models` es parte del protocolo-- y te deja\nelegir de la lista.\n\nLM Studio y Ollama NO piden clave: escuchan en tu maquina. Los de\nla nube si, y va en Cuentas.':
        'The model used to be a free text field, which means knowing the exact\nidentifier: OpenRouter publishes hundreds and LM Studio serves\nwhichever one you loaded. The button asks the service itself --\n`GET /v1/models` is part of the protocol -- and lets you pick from\nthe list.\n\nLM Studio and Ollama do NOT ask for a key: they listen on your own\nmachine. The cloud ones do, and that goes under Accounts.',
    'elegido':
        'picked',
    'Navegacion':
        'Navigation',
    'Como se pasa de una seccion a otra:\n  lateral    una barra a la izquierda\n  pestanas   las de arriba, como era antes\nSiete pestañas arriba ya rozan el ancho de la ventana. La barra\nesta dibujada pero se maneja con el teclado igual: entra en el\ntabulador, las flechas mueven y Enter activa.\n\nEl cambio se ve al reabrir el panel.':
        "How you move from one section to another:\n  lateral    a bar on the left\n  pestanas   the tabs on top, the way it used to be\nSeven tabs across the top already push the window's width. The bar\nis drawn but it still works from the keyboard: it joins the tab\norder, the arrows move and Enter activates.\n\nThe change shows when you reopen the panel.",
    'Secciones':
        'Sections',
    'Como se ve cada seccion:\n  tarjeta  en una tarjeta con esquinas redondeadas\n  plano    filas sueltas, como era antes\nLas esquinas redondeadas ttk no las tiene, asi que el marco se\ndibuja aparte. Los CONTROLES siguen siendo los de siempre en los\ndos casos: uno dibujado seria invisible para un lector de\npantalla, y eso no se cambia por una esquina.\n\nNecesita el tema aplicado al panel, aca arriba.':
        'How each section looks:\n  tarjeta  in a card with rounded corners\n  plano    plain rows, the way it used to be\nRounded corners are not something ttk has, so the frame is drawn\nseparately. The CONTROLS are the usual ones either way: a drawn\none would be invisible to a screen reader, and that is not worth\ntrading for a corner.\n\nNeeds the theme applied to the panel, just above.',
    'Cerrar':
        'Close',
    'Grabar':
        'Record',
    'Grabar el banco de voz':
        'Record the voice bank',
    'HABLA':
        'SPEAK',
    'Listo':
        'Done',
    'Saltar esta':
        'Skip this one',
    'callate...':
        'stay quiet...',
    'no entro audio':
        'no audio came in',
    'no pude abrir el microfono':
        'could not open the microphone',
    'falta el banco viejo: de ahi salen las frases':
        'the old bank is missing: that is where the phrases come from',
    'Ya estan las 24. Corre banco_voz.py para medir.':
        'All 24 are in. Run banco_voz.py to measure.',
    "Probar recorre el camino entero y no una pieza suelta: graba de tu\nmicrofono de verdad y transcribe con el modelo que tengas elegido.\n\nSensibilidad: 'normal' para un cuarto tranquilo, 'ruido' si hay\nmusica o un juego atras, 'bajo' de madrugada. 'auto' la elige por\nhora; las reglas y los numeros medidos estan en el ajuste fino.\n\n'auto' NO se envia todavia, y por eso: el modo correcto mira el\nruido del ambiente y elige solo, pero el banco con el que se mide\ntodo esto se corto por silencio y quedo sin silencios: mediana de\n90 ms antes de la primera palabra, y uno solo de 24 llega a los\n300 que hacen falta. 'Grabar el banco de voz' arregla eso: guia\nla grabacion y no acepta una toma donde te adelantaste.":
        "Testing walks the whole path and not one piece of it: it records from\nyour real microphone and transcribes with the model you picked.\n\nSensitivity: 'normal' for a quiet room, 'ruido' if there is music or a\ngame behind, 'bajo' late at night. 'auto' picks by the clock; the rules\nand the measured numbers are under fine tuning.\n\n'auto' does NOT ship yet, and here is why: the right mode looks at the\nroom noise and picks on its own, but the bank everything is measured\nagainst was cut by silence and ended up with no silences: a median of\n90 ms before the first word, and only one clip out of 24 reaches the\n300 that are needed. 'Record the voice bank' fixes that: it guides the\nrecording and refuses a take where you spoke too early.",
    'Revisar listener':
        'Check listener',
    'abriendo el listener...':
        'opening the listener...',
    'el listener no llego a dar señales; revisa Acciones':
        'the listener never reported in; check the Actions tab',
    'el listener ya esta abierto':
        'the listener is already open',
    'listener abierto':
        'listener open',
    'no pude abrir el listener':
        'could not open the listener',
    'Agregalos con el boton de aca al lado. Sin ninguno, el\ncartel dibuja el diseno de siempre y no cambia nada.':
        'Add them with the button next to this one. With none, the\ncard draws its usual design and nothing changes.',
    'Editando':
        'Editing',
    'Editando el cartel. El recuadro es su tamano real.':
        'Editing the card. The outline is its real size.',
    'Editando el tablero.':
        'Editing the board.',
    'El cartel no tiene modulos propios.':
        'The card has no modules of its own.',
    'borde del cartel':
        'edge of the card',
    'Cuadros por segundo':
        'Frames per second',
    'Fluidez':
        'Smoothness',
    'Vale para el cartel y para la ventana de actividad. 0 = el que\nsugiere tu maquina: 30 en un PC normal, 20 en ARM.\n\nMedido en un escritorio x64: componer la ventana entera con seis\ncapas y quinientas particulas cuesta 21.6 ms de mediana y 23.1 de\np95, asi que a 30 cuadros quedan 11 ms de margen. Si ves tirones,\nbajalo antes que apagar modulos: 20 cuadros con todo puesto se ve\nmejor que 30 a medias.':
        'Applies to the card and to the activity window. 0 = whatever your\nmachine suggests: 30 on a normal PC, 20 on ARM.\n\nMeasured on an x64 desktop: compositing the whole window with six\nlayers and five hundred particles costs 21.6 ms median and 23.1 at\np95, so at 30 frames there are 11 ms of headroom. If you see stutter,\nlower this before turning modules off: 20 frames with everything on\nlooks better than 30 with half of it.',
    'Acento':
        'Accent',
    'Acento apagado':
        'Muted accent',
    'Alerta':
        'Alert',
    'Cajas y campos':
        'Boxes and fields',
    'Fondo':
        'Background',
    'Texto':
        'Text',
    'Texto secundario':
        'Secondary text',
    'Eve no ejecuto nada todavia':
        'Eve has not run anything yet',
    'accion desconocida':
        'unknown action',
    'cartel mostrado unos segundos':
        'card shown for a few seconds',
    'ejecutando':
        'running',
    'listo, hablo':
        'done, it spoke',
    'no entendi nada':
        'I did not understand anything',
    'no entro audio; el microfono puede estar tomado':
        'no audio came in; the microphone may be taken',
    'panel abierto':
        'panel opened',
    'pidele que lea una pagina':
        'ask it to read a page',
    'pidele que te muestre algo':
        'ask it to show you something',
    'te escuche':
        'I heard you',
    'todavia no hablaron':
        'you have not talked yet',
    'Eve esta corriendo':
        'Eve is running',
    'en':
        'on',
    'tablero':
        'board',
    'cartel':
        'overlay',
    'Perfil segun el contexto':
        'Profile by context',
    'Cambia de perfil solo, segun la hora o el programa que\ntengas adelante. Misma sintaxis que la linea de arriba:\n  22:00-06:00=noche, discord=gaming\n\nLa condicion es un rango de horas si tiene forma de rango,\ny si no el nombre del programa. GANA LA PRIMERA QUE ENTRA,\nasi que el orden en que las escribes es el orden de\nprioridad -- es lo unico de esto que no se adivina.\n\nEl nombre del programa se compara por pedazo: `discord`\nagarra tambien `Discord.exe` y `discordptb`, para no tener\nque abrir el administrador de tareas para escribir una\nregla.\n\nVacio no cambia nada. Y un perfil solo toca como se VE y\ncomo suena Eve: no puede cambiarte el motor, la tecla, los\npermisos ni tus datos.':
        'Switches profile on its own, by the time of day or by the program\nyou have in front. Same syntax as the line above:\n  22:00-06:00=night, discord=gaming\n\nThe condition is a time range if it looks like one, and otherwise\nthe name of the program. THE FIRST MATCH WINS, so the order you\nwrite them in is their priority -- it is the only part of this you\ncannot guess.\n\nThe program name matches by substring: `discord` also catches\n`Discord.exe` and `discordptb`, so you do not have to open the task\nmanager to write a rule.\n\nEmpty changes nothing. And a profile only touches how Eve LOOKS and\nsounds: it cannot change your engine, your key, your permissions or\nyour data.',
    'Motor de dibujo':
        'Drawing engine',
    'Quien pinta los modulos. `auto` usa la GPU si tu maquina la\ntiene, y si no cae a Pillow por CPU, que es lo de siempre.\n\nMedido en un escritorio x64 sobre 1100x700 con seis capas y\nquinientas particulas: Pillow por CPU cuesta 20.3 ms de\nmediana y Skia por GPU 2.0. Pero Skia SIN GPU cuesta 214, o\nsea diez veces peor que no usarlo: por eso pedirlo a mano no\nlo fuerza si no se puede, y la linea de abajo dice que quedo.\n\nLo que gana no son cuadros por segundo --con un modulo\nanimando ya sobra-- sino techo: shaders y miles de\nparticulas no entran por el camino de CPU.':
        'Who paints the modules. `auto` uses the GPU if your machine has\none, and falls back to Pillow on the CPU, which is the usual path.\n\nMeasured on an x64 desktop at 1100x700 with six layers and five\nhundred particles: Pillow on the CPU costs 20.3 ms median and Skia\non the GPU 2.0. But Skia WITHOUT a GPU costs 214, ten times worse\nthan not using it at all: that is why asking for it by hand does\nnot force it, and the line below tells you what you got.\n\nWhat it buys is not frames per second --with one module animating\nthere is already room to spare-- but headroom: shaders and\nthousands of particles do not fit through the CPU path.',
    'agregado':
        'added',
    'Estoy en el desplegable de la flechita de la barra de tareas, con Steam y Discord. Arrastrame fuera para fijarme en la barra.':
        'I am in the flyout behind the arrow on the taskbar, with Steam and Discord. Drag me out to pin me to the taskbar.',
    'Buscar un ajuste...   (Ctrl+F)':
        'Search a setting...   (Ctrl+F)',
    'Cartel':
        'Card',
    'Ventana':
        'Window',
    'asistente corriendo':
        'assistant running',
    'asistente detenido':
        'assistant stopped',
    'configuracion':
        'settings',
    'motor':
        'engine',
    'tecla':
        'key',
    'Armar el tablero':
        'Build the board',
    'Esta ventana esta vacia porque el tablero no tiene modulos.':
        'This window is empty because the board has no modules.',
    "Toca 'Armar el tablero' aqui arriba para poner los de arranque,\no agregalos uno por uno desde el panel, en Apariencia > Modulos.":
        "Press 'Build the board' above to add the starter ones,\nor add them one by one from the panel, under Appearance > Modules.",
    'listo, ahi estan':
        'done, there they are',
    'Colores a mano':
        'Colors by hand',
    "Solo se usan con el tema 'personalizado'.":
        "Only used with the 'personalizado' theme.",
    '  ahi se acomodan los modulos del tablero con el mouse':
        '  that is where you arrange the board modules with the mouse',
    '  si la abres y esta vacia, es porque no hay modulos en el tablero':
        '  if you open it and it is empty, there are no modules on the board',
    "'Permitir todo' desactiva la confirmacion y tambien los permisos internos\nde Claude Code. Todo queda igual registrado en la pestaña Acciones.":
        "'Allow everything' turns off the confirmation and also Claude Code's own\ninternal permissions. Everything is still recorded in the Actions tab.",
    "'nunca' = solo cuando la abres tu. 'con_eve' = se abre junto con\nEve y queda ahi. Corre como proceso aparte, asi que si se cuelga no\nse lleva puesto al asistente.":
        "'nunca' = only when you open it. 'con_eve' = it opens together with\nEve and stays there. It runs as its own process, so if it hangs it does\nnot take the assistant down with it.",
    '(no hay perfiles guardados)':
        '(no saved profiles)',
    "0 = donde lo dejes, sin restriccion, y puedes arrastrarlo de un\nmonitor al otro. 1 en adelante lo fija a ese monitor y lo mantiene\nadentro aunque lo arrastres. Si desenchufas el que elegiste, vuelve\nal escritorio entero en vez de quedar en un lugar que no existe.\n'trabajo' descuenta la barra de tareas; solo cambia algo en Windows.":
        "0 = wherever you leave it, no constraint, and you can drag it from one\nmonitor to the other. 1 and up pins it to that monitor and keeps it\ninside even if you drag it. If you unplug the one you picked, it falls\nback to the whole desktop instead of sitting somewhere that no longer exists.\n'trabajo' subtracts the taskbar; it only changes anything on Windows.",
    'Abrir la carpeta de addons':
        'Open the addons folder',
    'Abrir la ventana de actividad':
        'Open the activity window',
    'Abrir panel':
        'Open the panel',
    'Activar diciendo una palabra (deja el microfono abierto)':
        'Wake it by saying a word (keeps the microphone open)',
    'Actividad':
        'Activity',
    'Actualizar':
        'Refresh',
    'Actualizar Eve':
        'Update Eve',
    'Addons':
        'Addons',
    'Agregar':
        'Add',
    'Agregar / actualizar':
        'Add / update',
    'Agregar / gestionar cuentas':
        'Add / manage accounts',
    'Agregar los tuyos':
        'Add your own',
    'Aire del detector (ms)':
        'Detector padding (ms)',
    'Ajuste':
        'Fit',
    'Ajuste fino de la voz':
        'Voice fine tuning',
    'Ajuste fino del modelo':
        'Model fine tuning',
    'Ajuste fino del reconocimiento':
        'Recognition fine tuning',
    'Ajustes del modulo':
        'Module settings',
    'Apagado de fabrica: prenderlo deja el microfono abierto todo el\ntiempo. Dile el nombre y la orden de un tiron, en la misma frase:\n  "Eve, abre Spotify"\nEl nombre tiene que ir al principio. Aceptarlo en cualquier lado\nconvertiria en orden cualquier charla que te lo mencione.\n\nNo corre ningun modelo de lenguaje en reposo: primero un detector\nde voz de 1.2 MB que ya viaja en el paquete decide si hay alguien\nhablando --medido, 0.20% de un core-- y recien sobre ese pedazo\ncorre el modelo de la puerta. Ese es chico a proposito: solo tiene\nque reconocer una palabra que ya conoce.\n\nLa palabra pesa mas que el modelo. Medido, 4 ordenes y 6 frases\nde control que NO tienen que despertarla:\n  Computadora  tiny   desperto 4/4    falsos 0/6\n  Eve          small  desperto 3/4    falsos 0/6\n  Eve          tiny   desperto 2/4    falsos 0/6\nTres letras no alcanzan para ser una puerta. Por eso se aceptan\nvariantes separadas por |, y de fabrica vienen las dos.':
        'Off by default: turning it on leaves the microphone open all the time.\nSay the name and the command in one go, in the same sentence:\n  "Eve, open Spotify"\nThe name has to come first. Accepting it anywhere would turn any\nconversation that mentions it into a command.\n\nNo language model runs while idle: first a 1.2 MB voice detector that\nalready ships in the package decides whether somebody is talking\n--measured, 0.20% of one core-- and only then does the gate model run\non that slice. That one is small on purpose: all it has to do is\nrecognize a word it already knows.\n\nThe word matters more than the model. Measured over 4 commands and 6\ncontrol sentences that must NOT wake it:\n  Computadora  tiny   woke 4/4    false 0/6\n  Eve          small  woke 3/4    false 0/6\n  Eve          tiny   woke 2/4    false 0/6\nThree letters are not enough to be a gate. That is why variants\nseparated by | are accepted, and both ship by default.',
    'Apariencia':
        'Appearance',
    'Aplicar':
        'Apply',
    'Aplicar a los elegidos':
        'Apply to selection',
    'Aprobados':
        'Approved',
    'Aprobar':
        'Approve',
    'Aprobar addon':
        'Approve addon',
    'Area':
        'Area',
    'Armar el tablero de arranque':
        'Build the starter board',
    'Autoridad':
        'Authority',
    "Borra la conversacion guardada y deja la ventana de contexto en cero.\n\nEl registro de acciones (pestaña Acciones) NO se toca.\n\nSi el listener esta corriendo, usa tambien la bandeja > 'Limpiar historial y\ncontexto' para vaciar lo que ya tiene en memoria.\n\nBorrar?":
        "Deletes the saved conversation and resets the context window to zero.\n\nThe action log (Actions tab) is NOT touched.\n\nIf the listener is running, also use the tray > 'Clear history and\ncontext' to flush what it already holds in memory.\n\nDelete?",
    'Borrar':
        'Delete',
    'Borrar perfil':
        'Delete profile',
    'Buscar':
        'Search',
    'Buscar actualizaciones':
        'Check for updates',
    'Busqueda por haz (beam)':
        'Beam search',
    'Cabecera del panel':
        'Panel header',
    'Cada modulo es una pieza del cartel: un icono, una onda, particulas,\nel reloj o el medidor de contexto. Se puede elegir donde va, de que\ntamano, con cuanta transparencia y cuando se muestra.':
        'Each module is a piece of the card: an icon, a waveform, particles,\nthe clock or the context meter. You choose where it goes, how big,\nhow transparent, and when it shows.',
    'Cambia como ESCRIBE: tu contra vos, vale contra dale. La voz va\naparte, y el boton de arriba le pone la que le corresponde.\nNo hay voz colombiana en el catalogo de Piper, asi que esa variante\ncomparte la mexicana y cambia solo el vocabulario.':
        "Changes how it WRITES: tu against vos, vale against dale. The voice is\na separate thing, and the button above sets the matching one.\nThere is no Colombian voice in Piper's catalog, so that variant shares\nthe Mexican one and only changes the vocabulary.",
    'Cargar':
        'Load',
    'Cargar perfil':
        'Load profile',
    'Cartel en pantalla':
        'On-screen card',
    "Cartel mostrado unos segundos. Si no aparecio, revisa 'Cuando se ve' y 'Pantalla' mas abajo.":
        "Card shown for a few seconds. If nothing appeared, check 'When it shows' and 'Display' below.",
    'Cerrar sesion':
        'Sign out',
    'Cierra y abre el panel para verlo cargado.':
        'Close and reopen the panel to see it loaded.',
    'Claves que fijaste tu':
        'Settings you pinned yourself',
    'Colores del cartel flotante':
        'Floating card colors',
    'Colores del panel':
        'Panel colors',
    'Como habla, no que hace. Va al final del prompt y siempre pierde\ncontra el manual: no puede hacerla hablar de mas ni narrar en vez\nde actuar. Vacio = sin personaje. Lo setea cada perfil.':
        'How it talks, not what it does. It goes at the end of the prompt and\nalways loses against the manual: it cannot make her talk more or narrate\ninstead of acting. Empty = no character. Every profile sets it.',
    'Como te escucha':
        'How it hears you',
    'Como te escucha y como te responde.':
        'How it hears you and how it answers.',
    'Como te habla':
        'How it speaks to you',
    'Compartir:':
        'Share:',
    'Con capa gratuita: ':
        'With a free tier: ',
    'Con que nombre y foto aparecen los mensajes que manda por webhook.\nVacio = lo que tenga configurado el webhook en Discord. Andaba\ndesde siempre; lo que faltaba era donde escribirlo sin editar el\nconfig a mano.':
        'The name and picture the webhook messages show up with.\nEmpty = whatever the webhook has configured in Discord. It always\nworked; what was missing was somewhere to type it without editing\nthe config by hand.',
    'Conexiones con apps (todas opcionales)':
        'App connections (all optional)',
    'Configuracion guardada.\n\nSi el listener esta corriendo, aplica los\ncambios solo en unos segundos. Los de aspecto no le cortan la\nconversacion; los de motor o tecla si lo rearman.':
        'Settings saved.\n\nIf the listener is running, it applies the changes\non its own within a few seconds. Appearance changes do not cut the\nconversation; engine or key changes do rebuild it.',
    'Contactos':
        'Contacts',
    'Contorno':
        'Outline',
    'Contrasena de aplicacion':
        'App password',
    'Corriendo desde el codigo: actualiza con git pull.':
        'Running from source: update with git pull.',
    "Cuando le pides algo hablando, hasta donde puede llegar:\n  nada    no toca nada; es la voz y nada mas\n  datos   modulos, ajustes y perfiles -- todo lo que ya es una\n          clave de config y pasa por el mismo freno que el panel\n  codigo  ademas puede DEJAR ESCRITO un addon .py, que igual no\n          corre hasta que lo apruebes a mano en Addons\nNo hay un cuarto nivel donde apruebe sus propios addons, y no\ndeberia haberlo: la huella del contenido es lo unico que separa un\nplugin de un agujero.\n\nEs OTRO eje que 'Quien manda'. Aquel decide quien gana cuando los\ndos quieren el mismo valor; este, que clase de cosa puede crear.\nCon 'nada' el prompt tampoco lleva el vocabulario de modulos.\nCuanto de ese vocabulario viaja lo decide el ajuste de abajo.":
        "When you ask for something out loud, how far it can go:\n  nada    touches nothing; it is the voice and nothing else\n  datos   modules, settings and profiles -- everything that is already\n          a config key and goes through the same brake as the panel\n  codigo  it can also LEAVE WRITTEN a .py addon, which still does not\n          run until you approve it by hand under Addons\nThere is no fourth level where it approves its own addons, and there\nshould not be: the content hash is the only thing separating a plugin\nfrom a hole.\n\nThis is a DIFFERENT axis from 'Who wins'. That one decides who wins\nwhen both want the same value; this one, what kind of thing it may\ncreate. With 'nada' the prompt also drops the module vocabulary.\nHow much of that vocabulary travels is up to the setting below.",
    'Cuanto le contamos de antemano':
        'How much we tell it up front',
    "Cuanto vocabulario de interfaz viaja en CADA llamada:\n  consultar  dos renglones, y Eve pregunta con 'E ui buscar'\n             cuando le hace falta. 310 caracteres.\n  minimo     ademas los trece nombres de tipo. 485.\n  completo   el esquema entero, con sus props. 1352.\nMedido con el mismo contador que dibuja el modulo\n'contexto': de 11 972 caracteres de prompt, 'completo' se\nlleva el 11.3% y 'consultar' el 2.8%. O sea 8.7% menos en\nTODO lo que le digas, incluido 'que hora es', a cambio de\nuna consulta extra las veces que si toca la interfaz.\n\nEs OTRO eje que los dos de arriba: aquellos dicen QUE puede\nhacer y quien gana cuando los dos quieren el mismo valor;\neste, solo cuanto le adelantamos. Con 'Hasta donde arma\nsola' en nada no viaja nada y este no hace diferencia.":
        "How much interface vocabulary travels on EVERY call:\n  consultar  two lines, and Eve asks with 'E ui buscar'\n             when it needs to. 310 characters.\n  minimo     plus the thirteen type names. 485.\n  completo   the whole schema, with each type's props. 1352.\nMeasured with the same counter that draws the 'contexto'\nmodule: out of 11,972 characters of prompt, 'completo' takes\n11.3% and 'consultar' 2.8%. That is 8.7% less on EVERYTHING\nyou say, 'what time is it' included, in exchange for one\nextra lookup the times it does touch the interface.\n\nThis is a DIFFERENT axis from the two above: those say WHAT it\nmay do and who wins when both want the same value; this one,\nonly how much we tell it beforehand. With 'How far it goes on\nits own' set to nada, nothing travels and this makes no difference.",
    'Cuando se abre':
        'When it opens',
    'Cuando se ve':
        'When it shows',
    'Cuantas ramas explora el reconocedor. Medido sobre una orden\ntipica: beam 5 tarda 4.4s y beam 1 tarda 3.5s, con el MISMO texto.\nSirve para dictado largo, no para ordenes de ocho palabras.':
        'How many branches the recognizer explores. Measured on a typical\ncommand: beam 5 takes 4.4s and beam 1 takes 3.5s, with the SAME text.\nUseful for long dictation, not for eight-word commands.',
    'Cuanto se queda cada subtitulo despues de que Eve termina de\nhablar. Hasta ahora solo se podia cambiar editando el config.':
        'How long each subtitle stays after Eve finishes speaking.\nUntil now this could only be changed by editing the config.',
    'Cuentas':
        'Accounts',
    'Degradado (si no hay imagen)':
        'Gradient (when there is no image)',
    'Degradado: color 1':
        'Gradient: color 1',
    'Degradado: color 2':
        'Gradient: color 2',
    'Descargala primero.':
        'Download it first.',
    'Descargando...':
        'Downloading...',
    'Descargar':
        'Download',
    'Deshacer':
        'Undo',
    'Despertarla diciendo su nombre':
        'Wake it by saying its name',
    'Destildar uno lo saca del prompt: deja de gastar tokens y Eve deja de\nofrecerlo. Si no hay ninguno tildado, se usan todos los disponibles.':
        'Unchecking one takes it out of the prompt: it stops costing tokens and\nEve stops offering it. If none are checked, all available ones are used.',
    'Discord: URL del avatar':
        'Discord: avatar URL',
    'Discord: URL del webhook':
        'Discord: webhook URL',
    'Discord: escribir como tu (maneja tu cliente; verifica el canal por titulo)':
        'Discord: type as you (drives your client; checks the channel by title)',
    'Discord: nombre a mostrar':
        'Discord: display name',
    'Dispositivo':
        'Device',
    'Duplicar':
        'Duplicate',
    'Effort':
        'Effort',
    'El GIF se anima solo. La opacidad se mezcla en la imagen y no en la ventana,\nasi que bajarla atenua el fondo pero el texto sigue entero.':
        'The GIF animates on its own. Opacity is blended into the image and not\ninto the window, so lowering it dims the background but the text stays solid.',
    'El cartel esta suelto: arrastralo a donde quieras y sueltalo.\n\nAl soltarlo se guarda la posicion y vuelve a dejar pasar los clics.':
        'The card is loose: drag it wherever you want and drop it.\n\nOn drop the position is saved and it goes back to letting clicks through.',
    "El cartel normalmente deja pasar los clics al programa de atras.\n  nunca   nunca los toma\n  hover   solo mientras el puntero esta sobre un modulo marcado\n          como 'interactivo'; si no marcaste ninguno, es igual\n          que 'nunca'\n  fijo    siempre los toma, y siempre tapa lo que este debajo\nSe pregunta donde esta el puntero treinta veces por segundo en vez\nde escuchar eventos, porque una ventana que deja pasar los clics\ntampoco recibe los de movimiento: esperarlos seria esperar para\nsiempre. Ese mismo poll es el que hace andar 'cuando = hover'.":
        "The card normally lets clicks through to the program behind it.\n  nunca   never takes them\n  hover   only while the pointer is over a module marked as\n          'interactivo'; if you marked none, this is the same\n          as 'nunca'\n  fijo    always takes them, and always covers whatever is underneath\nThe pointer position is polled thirty times a second instead of\nlistening for events, because a window that lets clicks through does\nnot receive motion events either: waiting for them would mean waiting\nforever. That same poll is what makes 'when = hover' work.",
    'El cartel vuelve a la esquina de arriba a la izquierda.':
        'The card goes back to the top-left corner.',
    "El catalogo de programas viaja en CADA llamada al modelo, y entero\nes un tercio del prompt. 'usados' manda solo los que aparecen en tu\nlog de acciones, ordenados por frecuencia, y el resto se busca con\n`E programa NOMBRE`. Medido: 1551 tokens menos por llamada, un 36%.\n'completo' los manda todos, por si prefieres pagar y no buscar.":
        "The program catalog travels on EVERY call to the model, and in full it\nis a third of the prompt. 'usados' sends only the ones that show up in\nyour action log, ordered by frequency, and the rest are looked up with\n`E programa NAME`. Measured: 1551 fewer tokens per call, 36%.\n'completo' sends them all, in case you would rather pay than look up.",
    'El marco es parametrico: eliges cuantos lados, cuanto gira y cuanto se\nredondean las puntas. Las formas de abajo son atajos que llenan esos\nnumeros; despues los puedes tocar a mano.':
        'The frame is parametric: you pick how many sides, how much it rotates\nand how rounded the corners are. The shapes below are shortcuts that\nfill in those numbers; you can tweak them by hand afterwards.',
    'El nombre no puede estar vacio.':
        'The name cannot be empty.',
    'Elegir imagen del icono...':
        'Choose icon image...',
    'Elegir...':
        'Choose...',
    'ElevenLabs voice_id':
        'ElevenLabs voice_id',
    'Elige un contacto de la lista primero.':
        'Pick a contact from the list first.',
    'Elige un modulo de la lista para ajustarlo.':
        'Pick a module from the list to edit it.',
    'Elige un perfil de la lista primero.':
        'Pick a profile from the list first.',
    'Elige un perfil de la lista.':
        'Pick a profile from the list.',
    'Elige una variante primero.':
        'Pick a variant first.',
    'Elige una voz de la lista.':
        'Pick a voice from the list.',
    "Es la tercera ventana de Eve, aparte del panel y del cartel. Ahi se\nve que esta haciendo: los modulos que le pongas, el grafo de lo que\nejecuto, el medidor de contexto y el lector de paginas.\n\nTiene dos modos arriba, y no son dos pantallas sino quien puede\nescribir. En 'Work' se mira; en 'Edit' se agarran los modulos con el\nmouse: clic elige, Ctrl suma, Shift agrega un rango, arrastrar mueve\ny Ctrl+Z deshace. Con varios elegidos se editan las propiedades que\nTIENEN EN COMUN, y si el valor difiere el campo arranca vacio para\nque aplicar no los iguale sin querer.":
        "This is Eve's third window, apart from the panel and the card. It shows\nwhat she is doing: the modules you give it, the graph of what she ran,\nthe context meter and the page reader.\n\nIt has two modes at the top, and they are not two screens but who gets\nto write. In 'Work' you watch; in 'Edit' you grab the modules with the\nmouse: click selects, Ctrl adds, Shift adds a range, dragging moves and\nCtrl+Z undoes. With several selected you edit the properties they HAVE\nIN COMMON, and if the value differs the field starts empty so that\napplying does not level them by accident.",
    'Escala (%)':
        'Scale (%)',
    'Eso no parece una app password':
        'That does not look like an app password',
    "Esto cierra tu sesion de Claude Code en toda la PC, no solo en Eve.\n\nEl motor 'claude-code' va a dejar de funcionar hasta que vuelvas a entrar.\n\nSeguro?":
        "This signs you out of Claude Code on the whole PC, not just in Eve.\n\nThe 'claude-code' engine will stop working until you sign back in.\n\nAre you sure?",
    'Estos archivos no se estan cargando. Un addon es codigo que corre\ncon tus permisos y no pasa por el freno, asi que hay que mirarlo\nantes. Si Eve escribio alguno, aca es donde lo revisas.':
        'These files are not being loaded. An addon is code that runs with your\npermissions and does not go through the brake, so it has to be looked\nat first. If Eve wrote one, this is where you review it.',
    'Estos se cargan. Revocar no borra el archivo: lo devuelve a la\nlista de sin revisar, para que puedas volver a mirarlo antes de\ndecidir de nuevo. Editar un addon aprobado lo saca solo, porque\nla aprobacion es de la huella del contenido y no del nombre.':
        'These are loaded. Revoking does not delete the file: it sends it back\nto the not-reviewed list, so you can look at it again before deciding\nanew. Editing an approved addon un-approves it on its own, because the\napproval is of the content hash and not of the name.',
    "Eve usa esta lista cuando nombras a alguien. En 'alias' pon como le dices\nde verdad, separado por comas (lucho, el lucas) — la voz rara vez dice el\nnombre completo.\n\ndiscord_user  = su @ (para mencionarlo dentro del mensaje)\ndiscord_dm    = su chat privado. Activa Ajustes > Avanzado > Modo desarrollador,\n                boton derecho sobre la conversacion > Copiar ID\ndiscord_canal = un canal de servidor. Boton derecho > Copiar enlace":
        "Eve uses this list when you name somebody. Under 'alias' put what you\nactually call them, comma separated (lucho, el lucas) — speech rarely\nuses the full name.\n\ndiscord_user  = their @ (to mention them inside the message)\ndiscord_dm    = their private chat. Turn on Settings > Advanced > Developer\n                mode, right-click the conversation > Copy ID\ndiscord_canal = a server channel. Right-click > Copy link",
    'Eve va a ejecutar cualquier comando que decida, sin preguntarte:\nborrar carpetas, apagar la PC, modificar el registro.\n\nEl reconocimiento de voz se equivoca, y en este modo un error de\ntranscripcion se ejecuta directo.\n\nQueda registrado en la pestaña Acciones, pero nada lo va a frenar.\n\nActivar igual?':
        'Eve will run any command she decides on, without asking you:\ndeleting folders, shutting the PC down, editing the registry.\n\nSpeech recognition makes mistakes, and in this mode a transcription\nerror runs straight through.\n\nIt is recorded in the Actions tab, but nothing is going to stop it.\n\nTurn it on anyway?',
    'Exportar':
        'Export',
    'Exportar genera un archivo .evecontact que puedes mandarle a un amigo por\nWhatsApp o Discord; el lo abre con Importar y le queda el contacto cargado.':
        'Export produces an .evecontact file you can send a friend over WhatsApp\nor Discord; they open it with Import and the contact is loaded for them.',
    'Exportar perfil':
        'Export profile',
    'Exportar...':
        'Export...',
    'Falta el CLI':
        'The CLI is missing',
    'Falta el nombre':
        'The name is missing',
    'Fondo de los subtitulos':
        'Subtitle background',
    'Fondo del cartel':
        'Card background',
    'Forma':
        'Shape',
    'Formas':
        'Shapes',
    'Fuente de los subtitulos':
        'Subtitle font',
    'Fuente del cartel':
        'Card font',
    'Fuente del panel':
        'Panel font',
    'General':
        'General',
    'Giro (grados)':
        'Rotation (degrees)',
    'Gmail':
        'Gmail',
    "Gmail: si 'Contrasenas de aplicaciones' no te aparece, tu cuenta no tiene 2FA\no la administra tu organizacion. Alternativa sin claves: agrega el Gmail a\nOutlook (Archivo > Agregar cuenta) y Eve lo lee y escribe por ahi.\nWebhook: Editar canal > Integraciones > Webhooks. Steam key: steamcommunity.com/dev/apikey":
        "Gmail: if 'App passwords' does not show up, your account has no 2FA or\nyour organization manages it. Key-free alternative: add the Gmail to\nOutlook (File > Add account) and Eve reads and writes through there.\nWebhook: Edit channel > Integrations > Webhooks. Steam key: steamcommunity.com/dev/apikey",
    'Grosor del trazo':
        'Stroke width',
    'Guardado':
        'Saved',
    'Guardar':
        'Save',
    'Guardar como...':
        'Save as...',
    'Guardar contacto para compartir':
        'Save a contact to share',
    'Habla ahora... (3 segundos)':
        'Speak now... (3 seconds)',
    'Hablando...':
        'Speaking...',
    'Hablante':
        'Speaker',
    'Hablante solo sirve en las voces que traen varias.':
        'Speaker only matters on voices that ship several.',
    'Hasta donde arma sola':
        'How much it can build on its own',
    'Hasta donde llega con los archivos':
        'How far it goes with files',
    'Hasta donde puede meterse':
        'How far it is allowed to go',
    "Que puede hacer Eve DENTRO de las rutas de arriba. Las rutas\nsiguen siendo el limite: esto no agranda lo permitido, decide\nque hace adentro.\n  exacto     leer un archivo si le dictas la ruta entera\n  explorar   ademas listar una carpeta y buscar por nombre;\n             sin esto, encontrar algo dependia de que tu\n             supieras y dictaras la ruta\n  escribir   ademas crear y reemplazar. Pisar un archivo que\n             ya existe te pregunta primero, salvo que hayas\n             apagado la confirmacion aca arriba\nCon 'exacto' los comandos de explorar no existen para ella y\ntampoco se nombran en el prompt: una capacidad que no se puede\nusar solo gasta lugar e invita a que pruebe y le digan que no.":
        "What Eve may do INSIDE the paths above. Those paths are still\nthe limit: this does not widen what is allowed, it decides what\nit does inside.\n  exacto     read a file if you dictate the whole path\n  explorar   plus list a folder and search by name; without it,\n             finding anything depended on you knowing and\n             dictating the path\n  escribir   plus create and replace. Overwriting a file that\n             already exists asks you first, unless you turned\n             the confirmation above off\nWith 'exacto' the exploring commands do not exist for it and are\nnot named in the prompt either: a capability that cannot be used\nonly wastes room and invites it to try and be told no.",
    'Historial limpiado':
        'History cleared',
    'Icono':
        'Icon',
    'Idioma':
        'Language',
    'Idioma del panel':
        'Panel language',
    'Idioma en que te habla':
        'Language it speaks',
    'Imagen (PNG o GIF)':
        'Image (PNG or GIF)',
    'Imagen de cabecera':
        'Header image',
    'Imagen para el icono':
        'Icon image',
    'Importar':
        'Import',
    'Importar .plist':
        'Import .plist',
    'Importar perfil':
        'Import profile',
    'Importar...':
        'Import...',
    'Indice actualizado.':
        'Index updated.',
    'Iniciar sesion':
        'Sign in',
    'Instalados':
        'Installed',
    'La agenda que Eve usa cuando nombras a alguien.':
        'The address book Eve uses when you name someone.',
    "La clave de cada uno va en la pestaña Cuentas. 'propio' sirve para\ncualquier servidor que hable /chat/completions.":
        "The key for each one goes in the Accounts tab. 'propio' works for\nany server that speaks /chat/completions.",
    'La configuracion cambio por fuera. Guarda o cierra para recargarla.':
        'The config changed outside. Save or close to reload it.',
    'La tecla la escucha el asistente, no este panel: si el asistente no\nesta corriendo, el boton te lo dice en vez de dejarte probando una\ntecla que nadie escucha.':
        'The key is listened for by the assistant, not by this panel: if the\nassistant is not running, the button tells you so instead of leaving\nyou testing a key nobody is listening for.',
    'La ventana de actividad':
        'The activity window',
    'Lados (menos de 3 = circulo)':
        'Sides (fewer than 3 = circle)',
    'Le manda una pregunta trivial y muestra la respuesta y cuanto tardo.\nEs la unica forma de saber que el motor esta bien configurado sin\ntener que hablarle y quedarse esperando a ver si contesta.':
        'Sends it a trivial question and shows the answer and how long it took.\nIt is the only way to know the engine is configured right without\nhaving to talk to her and wait to see whether she answers.',
    'Leer las respuestas en voz alta':
        'Read answers out loud',
    'Limpiar campos':
        'Clear fields',
    'Limpiar historial':
        'Clear history',
    'Limpiar historial y contexto':
        'Clear history and context',
    'Lineas maximas':
        'Maximum lines',
    'Listener reiniciado':
        'Listener restarted',
    'Lo esencial':
        'Essentials',
    "Lo hace aparecer unos segundos aunque este en modo 'auto'. Es lo que\nsepara 'el cartel esta mal configurado' de 'el cartel no arranca'.":
        "Makes it appear for a few seconds even in 'auto' mode. It is what\nseparates 'the card is misconfigured' from 'the card never starts'.",
    'Lo mas simple es agregarlo a Outlook con el boton de arriba: Google hace el\nlogin y no queda ninguna clave tuya guardada aca.\n\nLa otra via es una contrasena de aplicacion (16 letras minusculas). Si Google\ndice que no esta disponible, es que tu cuenta no tiene verificacion en dos\npasos, o la administra tu organizacion.':
        'The simplest way is to add it to Outlook with the button above: Google\nhandles the login and none of your keys end up stored here.\n\nThe other way is an app password (16 lowercase letters). If Google says\nit is not available, your account has no two-step verification, or your\norganization manages it.',
    'Lo que Eve puede manejar ademas de tu PC. Cada uno trae sus comandos.':
        'What Eve can drive besides your PC. Each one brings its own commands.',
    'Los colores de todo, y el cartel que Eve muestra encima de lo que estes haciendo.':
        'The colors of everything, and the card Eve shows over whatever you are doing.',
    'Los dos vacios = el modelo sugerido y la URL del proveedor.':
        "Both empty = the suggested model and the provider's URL.",
    'Los editores de particulas --Particle Designer, Particle2dx--\nexportan el .plist de cocos2d, que es XML de numeros: vida,\ngravedad, color, velocidad. Se importa la CONFIGURACION y la\ncorre el simulador que ya esta, asi que no entra ninguna\nlibreria nueva. Llena los campos de arriba; despues Aplicar.\nNo viaja lo que el simulador no sabe hacer: modo radial,\ntexturas por particula y mezclas aditivas.':
        'Particle editors --Particle Designer, Particle2dx-- export the cocos2d\n.plist, which is XML full of numbers: life, gravity, color, speed.\nWhat gets imported is the CONFIGURATION, and the simulator that is\nalready here runs it, so no new library comes in. It fills the fields\nabove; then press Apply.\nWhat the simulator cannot do does not travel: radial mode, per-particle\ntextures and additive blending.',
    'Marco del icono':
        'Icon frame',
    'Max tokens':
        'Max tokens',
    'Menos de 10 se trata como 10: por debajo de eso el cartel no se ve\ny no habria forma de encontrarlo para subirlo de nuevo. La opacidad\nde cada modulo se MULTIPLICA con esta, asi que 20% de ventana por\n20% de modulo da 4% de verdad.':
        "Anything under 10 is treated as 10: below that the card cannot be seen\nand there would be no way to find it to raise it again. Each module's\nopacity is MULTIPLIED with this one, so 20% window times 20% module is\nreally 4%.",
    'Minutos de contexto':
        'Context minutes',
    'Modelo (motor api)':
        'Model (api engine)',
    'Modelo (motor claude-code)':
        'Model (claude-code engine)',
    'Modelo Whisper local':
        'Local Whisper model',
    'Modelo de la puerta':
        'Gate model',
    'Modulos':
        'Modules',
    'Mostrar el cartel':
        'Show the card',
    'Mostrar un subtitulo de prueba':
        'Show a test subtitle',
    'Mover el cartel':
        'Move the card',
    'Mover en pantalla':
        'Move on screen',
    'Nada elegido.':
        'Nothing selected.',
    'Necesitas al menos una ruta de trabajo permitida.':
        'You need at least one allowed working path.',
    'No animar los GIF (dejar el primer cuadro)':
        'Do not animate GIFs (keep the first frame)',
    "No encontre 'claude' en el PATH.":
        "I could not find 'claude' on the PATH.",
    'No hay ninguno cargado.':
        'None loaded.',
    'No hay webhook cargado.':
        'No webhook saved.',
    'No necesita ninguna clave: Eve usa la sesion que ya tiene Outlook en esta PC.':
        'No key needed: Eve uses the session Outlook already has on this PC.',
    'No pude actualizar':
        'I could not update',
    'No pude cambiar de perfil':
        'I could not switch profiles',
    'No pude leer ese archivo. Tiene que ser un .plist de cocos2d (el que exportan Particle Designer y Particle2dx).':
        'I could not read that file. It has to be a cocos2d .plist (the one Particle Designer and Particle2dx export).',
    'No pude leerlo':
        'I could not read it',
    'No pude reiniciar el listener':
        'I could not restart the listener',
    'Nombre de la IA':
        'Assistant name',
    'Nombres que el reconocimiento suele errar, separados por comas.':
        'Names the recognizer usually gets wrong, comma separated.',
    'Obtener app password':
        'Get an app password',
    'Ollama: host':
        'Ollama: host',
    'Ollama: modelo':
        'Ollama: model',
    'Onda':
        'Waveform',
    'Opacidad (%)':
        'Opacity (%)',
    'Opacidad de la imagen (%)':
        'Image opacity (%)',
    'Otros motores':
        'Other engines',
    'Outlook':
        'Outlook',
    'Palabra para despertarla':
        'Wake word',
    'Pantalla':
        'Display',
    'Parakeet: cuantizacion':
        'Parakeet: quantization',
    'Particulas':
        'Particles',
    'Particulas de Particle Designer':
        'Particle Designer particles',
    'Pausar listener':
        'Pause the listener',
    'Perfil activo':
        'Active profile',
    'Perfiles':
        'Profiles',
    'Permisos':
        'Permissions',
    'Permisos (motor claude-code)':
        'Permissions (claude-code engine)',
    'Permitir todo':
        'Allow everything',
    'Personalidad':
        'Personality',
    'Pintar el panel obliga a dibujar los controles por nuestra cuenta: Windows\nno deja cambiarle el color a los suyos. El cambio se ve al instante.':
        'Painting the panel forces us to draw the controls ourselves: Windows\ndoes not let you recolor its own. The change shows up instantly.',
    'Pintar tambien este panel con el tema':
        'Paint this panel with the theme too',
    'Posicion':
        'Position',
    'Probar':
        'Test',
    'Probar GPU':
        'Test the GPU',
    'Probar conexion':
        'Test the connection',
    'Probar el motor':
        'Test the engine',
    'Probar el webhook':
        'Test the webhook',
    'Probar la palabra':
        'Test the wake word',
    'Probar la tecla':
        'Test the key',
    'Probar que te escucha':
        'Test that it hears you',
    'Probar que te habla':
        'Test that it speaks',
    'Programas':
        'Programs',
    'Programas que Eve conoce':
        'Programs Eve knows about',
    'Que catalogo viaja':
        'Which catalog travels',
    'Que espanol habla':
        'Which Spanish it speaks',
    'Que se dijo y que se ejecuto en tu PC.':
        'What was said and what ran on your PC.',
    'Que se muestra':
        'What is shown',
    'Que voz se entiende mejor. Medido sobre diez frases, sintetizando\ny volviendo a transcribir --si el mejor reconocedor que hay no la\nentiende, tu con el juego de fondo tampoco:\n  es_ES-sharvard-medium   6.4%     es_ES-carlfm-x_low  10.0%\n  es_MX-claude-high       6.8%     es_MX-ald-medium    10.4%\n  es_ES-davefx-medium     8.4%     es_MX-ald-x_low     11.2%\n                                   es_AR-daniela-high  20.5%\nEs la media de tres corridas, y hacen falta las tres: Piper no es\ndeterminista y una misma voz se mueve hasta 8 puntos. Con una sola\nmedicion casi todo este orden seria ruido.\nLo que sobrevive: es_AR-daniela-high es la peor por mucho y la mas\nlenta por cinco veces. Por eso ninguna variante la sugiere: la voz\nes el canal, no el acento del que habla. Si aun asi la quieres,\neligela a mano en Voz de Piper.':
        'Which voice is easiest to understand. Measured over ten sentences,\nsynthesizing them and transcribing them back --if the best recognizer\nthere is cannot understand it, neither can you with a game behind:\n  es_ES-sharvard-medium   6.4%     es_ES-carlfm-x_low  10.0%\n  es_MX-claude-high       6.8%     es_MX-ald-medium    10.4%\n  es_ES-davefx-medium     8.4%     es_MX-ald-x_low     11.2%\n                                   es_AR-daniela-high  20.5%\nThat is the mean of three runs, and all three are needed: Piper is not\ndeterministic and the same voice moves by up to 8 points. With a single\nmeasurement almost all of this ordering would be noise.\nWhat survives: es_AR-daniela-high is the worst by far and five times the\nslowest. That is why no variant suggests it: the voice is the channel,\nnot the accent of the speaker. If you still want it, pick it by hand\nunder Piper voice.',
    'Quien es Eve':
        'Who Eve is',
    'Quien es Eve, quien piensa por ella y hasta donde puede meterse.':
        'Who Eve is, who thinks for her, and how far she is allowed to go.',
    'Quien manda sobre un ajuste':
        'Who wins on a setting',
    'Quien piensa por ella':
        'Who thinks for her',
    'Quitar':
        'Remove',
    'Recortar silencios antes de transcribir (VAD)':
        'Trim silence before transcribing (VAD)',
    'Redondeo de las puntas':
        'Corner rounding',
    'Reescanear programas':
        'Rescan programs',
    'Reglas por horario':
        'Time-of-day rules',
    'Reiniciar listener (aplicar config)':
        'Restart the listener (apply config)',
    'Revocar':
        'Revoke',
    'Rutas de trabajo permitidas (una por linea)':
        'Allowed working paths (one per line)',
    'Rutas vacias':
        'No paths',
    'STT (reconocimiento)':
        'STT (recognition)',
    'Salir':
        'Quit',
    "Se abrio una consola con el login de Claude Code.\nCuando termines, toca 'Actualizar' para ver el estado.":
        "A console opened with the Claude Code login.\nWhen you are done, press 'Refresh' to see the status.",
    "Se guardan en el gestor de credenciales de Windows, nunca en texto plano.\nAnthropic solo hace falta con el motor 'api'; con 'claude-code' se usa tu suscripcion.\nLas otras habilitan proveedores opcionales de voz.":
        "They are stored in the Windows credential manager, never in plain text.\nAnthropic is only needed with the 'api' engine; with 'claude-code' your\nsubscription is used. The others enable optional voice providers.",
    'Se manda un mensaje de prueba al canal de Discord de ese webhook.\n\nLo van a ver todos los que esten en el canal.\n\nMandarlo?':
        'A test message is sent to the Discord channel of that webhook.\n\nEverybody in the channel will see it.\n\nSend it?',
    'Se ve arriba de cada pestaña y se aplica al reabrir el panel. No hay fondo\npara todo el panel: los controles de Windows pintan su propio fondo opaco\ny lo taparian.':
        'It shows at the top of every tab and applies when the panel is reopened.\nThere is no background for the whole panel: Windows controls paint their\nown opaque background and would cover it.',
    'Segunda linea':
        'Second line',
    'Segundos en pantalla':
        'Seconds on screen',
    'Sensibilidad':
        'Sensitivity',
    'Separacion del cartel (px)':
        'Distance from the card (px)',
    "Sesion de Claude Code (motor 'claude-code')":
        "Claude Code session ('claude-code' engine)",
    'Sin esto Eve igual abre WhatsApp, Discord, Telegram y el mail con el\nmensaje escrito, para que lo mandes tu. Estas claves solo agregan leer\ny enviar sin pasar por la app.':
        'Without this Eve still opens WhatsApp, Discord, Telegram and mail with\nthe message already typed, for you to send. These keys only add reading\nand sending without going through the app.',
    'Sin revisar':
        'Not reviewed',
    'Steam: Web API key':
        'Steam: Web API key',
    "Subtitulo de prueba mostrado. Si no aparecio, revisa 'Que se muestra' y los segundos en pantalla.":
        "Test subtitle shown. If nothing appeared, check 'What is shown' and the seconds on screen.",
    'Subtitulos':
        'Subtitles',
    'TTS (voz)':
        'TTS (voice)',
    'Tamano de letra':
        'Font size',
    'Tamaño (0 = el de la fuente)':
        'Size (0 = whatever the font brings)',
    'Te abri la pagina de contrasenas de aplicacion.\n\nSi dice que no esta disponible para tu cuenta, es porque no tienes\nverificacion en dos pasos activada, o la administra tu organizacion.\n\nEn ese caso usa el boton de Outlook: agregas el Gmail ahi y listo.':
        'I opened the app passwords page for you.\n\nIf it says it is not available for your account, it is because you do\nnot have two-step verification on, or your organization manages it.\n\nIn that case use the Outlook button: you add the Gmail there and done.',
    'Tecla del keypad':
        'Keypad key',
    'Tema':
        'Theme',
    'Tema (vacio = el del panel)':
        "Theme (empty = the panel's)",
    'Tinte con el acento (%)':
        'Accent tint (%)',
    'Tipo de computo':
        'Compute type',
    'Tipografia':
        'Typography',
    'Titulo (vacio = nombre IA)':
        'Title (empty = assistant name)',
    'Todo':
        'Everything',
    'Todo lo de aca esta medido sobre las mismas 24 grabaciones propias.\n\nSensibilidad:\n  normal  cuarto tranquilo         WER 10.9%  (con ruido 12.5%)\n  ruido   musica o el juego atras  WER  8.7%  (con ruido  0.0%)\n  bajo    de madrugada, voz suave  WER 12.0%  (con ruido 18.8%)\n  manual  usa el umbral y el aire de mas abajo\n\nQue modelo conviene:\n  small     WER 10.9%   0.9s por orden en gpu,  3.3s en cpu\n  medium    WER  4.9%   1.8s en gpu, 10.2s en cpu  <- pide gpu\n  large-v3  WER  4.9%   2.7s en gpu, y PEOR en nombres propios\n            (34.8% contra 17.4% de medium): mas grande no es\n            mejor aca.':
        "Everything here is measured on the same 24 recordings of our own.\n\nSensitivity:\n  normal  quiet room                WER 10.9%  (noisy group 12.5%)\n  ruido   music or a game behind    WER  8.7%  (noisy group  0.0%)\n  bajo    late at night, soft voice WER 12.0%  (noisy group 18.8%)\n  manual  uses the threshold and padding below\n\nWhich model is worth it:\n  small     WER 10.9%   0.9s per command on gpu,  3.3s on cpu\n  medium    WER  4.9%   1.8s on gpu, 10.2s on cpu  <- wants a gpu\n  large-v3  WER  4.9%   2.7s on gpu, and WORSE on proper nouns\n            (34.8% against medium's 17.4%): bigger is not\n            better here.",
    'Toma clics':
        'Takes clicks',
    'Tono':
        'Tone',
    'Traer los del cartel actual':
        'Bring the ones from the current card',
    'Tu SteamID64 (autodetectado)':
        'Your SteamID64 (auto-detected)',
    'Tu direccion de Gmail':
        'Your Gmail address',
    'Turnos de contexto':
        'Context turns',
    'Umbral del detector':
        'Detector threshold',
    'Un perfil guarda como se ve y como suena Eve: colores, forma, fuente,\nvoz, velocidad, tono y el nombre del asistente.\nNO toca el motor, el modelo, la tecla, los permisos ni tus datos: un\nperfil que te pasan no puede cambiarte como trabaja el asistente.':
        "A profile stores how Eve looks and sounds: colors, shape, font, voice,\nspeed, tone and the assistant's name.\nIt does NOT touch the engine, the model, the key, the permissions or\nyour data: a profile somebody hands you cannot change how the assistant\nworks.",
    'Usar esta':
        'Use this one',
    'Usar la voz que le corresponde':
        'Use the matching voice',
    "Vacio = el cartel usa el mismo tema que el panel, que es lo que\nquiere casi todo el mundo. Los colores de abajo solo se usan con\nel tema 'personalizado'.":
        "Empty = the card uses the same theme as the panel, which is what almost\neverybody wants. The colors below are only used with the\n'personalizado' theme.",
    'Valor invalido':
        'Invalid value',
    "Van separadas por coma y solo pisan al modo 'auto':\n  00:00-06:00=bajo, 20:00-23:59=ruido\nSi eliges un modo a mano, el reloj no te lo cambia.":
        "Comma separated, and they only override the 'auto' mode:\n  00:00-06:00=bajo, 20:00-23:59=ruido\nIf you pick a mode by hand, the clock does not change it on you.",
    'Variante':
        'Variant',
    'Velocidad':
        'Speed',
    'Velocidad 1.0 = normal, mas alto = mas lento. Volumen 1.0 = como sale del sintetizador.':
        'Speed 1.0 = normal, higher = slower. Volume 1.0 = as the synthesizer produces it.',
    'Ventana de actividad':
        'Activity window',
    'Ver':
        'Show',
    'Ver el codigo':
        'View the code',
    'Vocabulario extra':
        'Extra vocabulary',
    'Voces':
        'Voices',
    'Voces entrenadas por la comunidad (Piper). Gratis, offline, y las unicas\nque suenan igual en Windows, macOS y Linux. Se verifica el md5 al descargar.':
        'Community-trained voices (Piper). Free, offline, and the only ones that\nsound the same on Windows, macOS and Linux. The md5 is checked on download.',
    'Volumen':
        'Volume',
    'Volver a la esquina':
        'Back to the corner',
    'Voz':
        'Voice',
    'Voz de Windows':
        'Windows voice',
    'WhatsApp: enviar solo (simula el Enter; exige numero, no nombre)':
        'WhatsApp: send on its own (fakes the Enter; needs a number, not a name)',
    'Ya existe':
        'Already there',
    'Ya existen':
        'Already there',
    'actividad':
        'activity',
    'activo':
        'running',
    'ambos = lo que dijiste tu (para ver si te entendio) y lo que responde Eve,\nrevelandose mientras lo dice.':
        'ambos = what you said (to see whether it understood you) and what Eve\nanswers, revealed as she says it.',
    'auto = aparece al hablarle y se va sola. Nunca se lleva el foco de lo que\nestes haciendo, y los clics la atraviesan.':
        'auto = it appears when you talk to her and leaves on its own. It never\ntakes focus away from what you are doing, and clicks pass through it.',
    'clic para elegir · Ctrl suma · Shift agrega un rango · arrastra para mover':
        'click to select · Ctrl adds · Shift adds a range · drag to move',
    'compat: URL propia':
        'compat: your own URL',
    'compat: modelo':
        'compat: model',
    'consultando catalogo...':
        'fetching the catalog...',
    'consultando...':
        'checking...',
    "cuda necesita las librerias de NVIDIA instaladas; si faltan, cae a cpu\nsolo y avisa. Medido en una GTX 1660 SUPER: 3.42s por orden en cpu\ncontra 0.71s en gpu. 'auto' elige int8 en cpu e int8_float16 en gpu.":
        "cuda needs the NVIDIA libraries installed; if they are missing it falls\nback to cpu on its own and says so. Measured on a GTX 1660 SUPER: 3.42s\nper command on cpu against 0.71s on gpu. 'auto' picks int8 on cpu and\nint8_float16 on gpu.",
    'descargando actualizacion...':
        'downloading the update...',
    'listo: el cartel de siempre, ahora como modulos':
        'done: the usual card, now made of modules',
    'mandando...':
        'sending...',
    'nada con esas palabras':
        'nothing matches those words',
    'no hay nada para deshacer':
        'nothing to undo',
    'parakeet es el modelo de NVIDIA. Entro porque gano medido sobre las\nmismas 24 grabaciones, con la misma cuenta:\n  whisper small en gpu   WER 10.9%   RTF 0.27    464 MB\n  whisper small en cpu   WER 10.9%   RTF 1.38    464 MB\n  whisper medium en gpu  WER  5.4%   RTF 0.61    1.5 GB\n  parakeet int8 en CPU   WER  7.1%   RTF 0.19    639 MB\nLo que importa no es el punto y medio de WER: es que ese 0.19 es EN\nCPU. Whisper small tarda siete veces mas sin GPU, y la mayoria de las\ninstalaciones no tienen CUDA configurado.\n\nDonde pierde: nombres propios, 30.4% contra 21.7%, que es justo el\ngrupo que decide si abre el programa correcto -- no acepta el sesgo\nde vocabulario que si acepta whisper. Por eso no es el default.\nSin cuantizar mejora los nombres propios pero pesa 2.4 GB.':
        "parakeet is NVIDIA's model. It got in because it won, measured on the\nsame 24 recordings with the same arithmetic:\n  whisper small on gpu   WER 10.9%   RTF 0.27    464 MB\n  whisper small on cpu   WER 10.9%   RTF 1.38    464 MB\n  whisper medium on gpu  WER  5.4%   RTF 0.61    1.5 GB\n  parakeet int8 on CPU   WER  7.1%   RTF 0.19    639 MB\nWhat matters is not the point and a half of WER: it is that the 0.19 is\nON CPU. Whisper small takes seven times longer without a GPU, and most\ninstalls have no CUDA configured.\n\nWhere it loses: proper nouns, 30.4% against 21.7%, which is exactly the\ngroup that decides whether it opens the right program -- it does not\naccept the vocabulary bias that whisper does. That is why it is not the\ndefault. Un-quantized it does better on proper nouns but weighs 2.4 GB.",
    'pausado':
        'paused',
    'probando, puede tardar unos segundos...':
        'testing, this can take a few seconds...',
    'probando...':
        'testing...',
    'recortado = el cartel deja de ser un rectangulo y por las esquinas cortadas\nde los contornos hexagonal y biselado se ve lo que hay atras.':
        'recortado = the card stops being a rectangle, and through the cut\ncorners of the hexagonal and beveled outlines you see what is behind.',
    'tablero armado: abre la ventana de actividad':
        'board built: open the activity window',
    "usuario: lo que cambies a mano queda trabado y Eve no lo pisa.\neve: puede cambiar lo que quiera.  preguntar: pide permiso cada vez.\nPara soltar lo trabado, dile 'destraba <clave>' o borra la lista abajo.":
        "usuario: whatever you change by hand is locked and Eve does not\noverwrite it. eve: she can change whatever she wants.  preguntar: she\nasks permission every time.\nTo release what is locked, tell her 'destraba <key>' or clear the list below.",
    'ventana de actividad abierta':
        'activity window opened',
    'Frase':
        'Phrase',
    'Tipo':
        'Kind',
    'Hace':
        'Does',
    'Estado':
        'State',
}



TABLA = {"en": EN}
