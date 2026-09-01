"""Cada opcion del panel como DATO, en vez de como codigo de interfaz.

El panel son dos mil lineas de tkinter donde cada control se escribe a mano y se
registra a mano en `self.vars`. Agregar una opcion es tocar codigo de UI, y
olvidarse de una linea deja un ajuste que existe en la config y no se puede
tocar. Ya paso once veces: un test que arma el panel de verdad y lo compara con
`DEFAULTS` las encontro todas de golpe.

Esto no es un framework nuevo. **El formulario de modulos ya es un panel generado
desde un registro** --`modulos.TIPOS` mas `modulos.OPCIONES`, que arma sus
veintiun controles solo-- y lo que sigue es ese mismo patron aplicado al resto.
Los que dibujan siguen siendo los helpers que ya existen: `_row`, `_check`,
`_ayuda`, `_seccion` y `_bloque_fondo`.

El freno esta escrito en el plan y vale: **si un control necesita codigo propio,
se escribe a mano y se registra como excepcion** --para eso esta `Propio`. Si mas
de un tercio de una pestaña son excepciones, esa pestaña no se migra.
"""

from typing import NamedTuple

# Los niveles viven en `gui`, pero repetirlos aca como texto evita que este
# modulo importe la interfaz: el registro tiene que poder leerse sin tkinter,
# que es lo que hace que un test lo revise sin abrir una ventana.
BASICO, AVANZADO = "basico", "avanzado"

# Los roles de la paleta con su rotulo, en el orden en que se muestran. Viven
# aca y no en `gui` por dos motivos: el registro tiene que poder enumerar las
# claves de un `Colores` sin importar la interfaz, y los rotulos son texto de
# pantalla, asi que el chequeo de traduccion los tiene que ver.
ROLES_ETIQUETA = (
    ("fondo", "Fondo"), ("panel", "Cajas y campos"), ("texto", "Texto"),
    ("texto_tenue", "Texto secundario"), ("acento", "Acento"),
    ("acento2", "Acento apagado"), ("borde", "Contorno"), ("alerta", "Alerta"),
)
ROLES = tuple(rol for rol, _ in ROLES_ETIQUETA)

# Las listas cerradas que hasta ahora vivian en `gui.py` como constantes de
# modulo y llegaban al registro por el NOMBRE de un metodo (`_modelos_api`).
# Estan aca porque son datos del panel, no interfaz: mientras vivieron en
# `gui.py` nadie podia leerlas sin importar tkinter, y eso es justo lo que un
# frontend que no es tkinter --y un test sin pantalla-- necesita hacer.
MODELOS_API = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
MODELOS_CC = ["opus", "sonnet", "haiku"]
PERMISOS_CC = ["acceptEdits", "auto", "manual"]
ESFUERZOS = ["low", "medium", "high", "xhigh", "max"]


class Campo(NamedTuple):
    """Una fila: etiqueta, clave de config y opciones si son cerradas.

    `opciones` acepta una lista, o el NOMBRE de un metodo del panel para las que
    se arman al abrir --las voces de Windows salen de consultar el sistema, y
    congelarlas al importar daria la lista de la maquina que compilo. Por nombre
    y no por referencia, igual que `Boton.metodo`.
    """

    clave: str
    etiqueta: str
    opciones: list | str | None = None
    ancho: int = 44
    # Con `abierto`, las opciones son SUGERENCIAS y se puede escribir otra
    # cosa. El modelo de un servicio compatible es el caso: se ofrecen los que
    # ese servicio dijo tener, pero nadie puede garantizar que la lista este
    # completa, y un desplegable cerrado ahi impediria usar uno nuevo hasta la
    # proxima version del programa.
    abierto: bool = False


class Interruptor(NamedTuple):
    """Una casilla. Se separa de `Campo` porque la dibuja `_check` y no `_row`."""

    clave: str
    etiqueta: str


class Clave(NamedTuple):
    """Una clave de API. Enmascarada, y su valor NO vive en la config.

    Se separa de `Campo` por donde se guarda, no por como se dibuja: el valor
    va al llavero del sistema --`store.set_key`-- y nunca a `config.json`, que
    es la regla escrita del proyecto para las claves. Por eso `proveedor` no es
    una clave de config y `claves()` no la cuenta: contarla haria que el test
    que compara el registro contra `DEFAULTS` reclamara una clave que no existe
    ahi, y con razon.

    Y por eso tampoco entra a `catalogo()`: ese alimenta `E ajustar`, o sea Eve
    cambiando una opcion porque se lo pediste hablando. Una clave de API no se
    dicta en voz alta.
    """

    proveedor: str
    etiqueta: str


class Ayuda(NamedTuple):
    """Texto explicativo. Va suelto porque no toca ninguna clave."""

    texto: str


class Boton(NamedTuple):
    """Un boton que llama a un metodo del panel, por nombre.

    Por nombre y no por referencia: el registro se importa antes que el panel
    exista, y guardar un metodo sin ligar seria guardar una funcion suelta que
    no sabe de que ventana es.
    """

    etiqueta: str
    metodo: str


class Fondo(NamedTuple):
    """Los siete controles de imagen de fondo, con `_bloque_fondo`."""

    prefijo: str
    titulo: str


class Propio(NamedTuple):
    """La excepcion: un metodo del panel que dibuja lo suyo a mano.

    Existe para que el registro NO tenga que crecer hasta describir cualquier
    cosa. Un control con logica propia se escribe en tkinter y se anota aca.

    Y DECLARA que claves toca. Sin eso, una excepcion seria un agujero en la
    verificacion: lo que dibuja a mano no se podria enumerar, y el test que
    compara el registro contra la config dejaria de ver esa parte.
    """

    metodo: str
    claves_propias: tuple = ()


class Colores(NamedTuple):
    """Las ocho filas de color de un tema, para un prefijo.

    Ya estaba escrito como un bucle sobre `ROLES_ETIQUETA`; declararlo hace que
    las claves se puedan enumerar sin abrir una ventana.
    """

    prefijo: str


class Vivo(NamedTuple):
    """Claves cuyo cambio repinta la vista previa, al instante.

    Estaba como bucles de `trace_add` sueltos en medio del bloque: logica
    mezclada con layout, y facil de olvidar al agregar un campo.
    """

    claves: tuple


class Salida(NamedTuple):
    """Una etiqueta vacia que el panel llena despues, guardada en `self.<attr>`.

    Es donde aparece el resultado de un boton de prueba. Se declara aca --y no se
    arma a mano-- porque si no, la mitad de una seccion queda en el registro y la
    otra mitad en tkinter, que es peor que tener las dos en el mismo lado.
    """

    atributo: str


class Fila(NamedTuple):
    """Varias cosas en el mismo renglon, en vez de una debajo de otra.

    Es layout y nada mas: el registro sigue sin saber pintar, solo dice que va
    junto con que. Sin esto, dos botones que van al lado se apilarian.
    """

    hijos: tuple


class Seccion(NamedTuple):
    """Un grupo plegable con su nivel y lo que lleva adentro."""

    titulo: str
    hijos: tuple
    nivel: str = BASICO


# --- las pestañas migradas ------------------------------------------------
# Se migran de a una, y solo cuando la generada produce las mismas claves, los
# mismos tipos y los mismos valores que la escrita a mano. Lo que todavia no
# esta aca sigue escrito a mano, y eso NO es deuda: es el orden que el plan
# pidio para no tocar de golpe lo unico que hoy funciona bien.

SUBTITULOS = (
    Seccion(
        "Subtitulos",
        (
            Boton("Mostrar un subtitulo de prueba", "probar_subtitulo"),
            Campo("sub_segundos", "Segundos en pantalla"),
            Ayuda("Cuanto se queda cada subtitulo despues de que Eve termina de\n"
                  "hablar. Hasta ahora solo se podia cambiar editando el config."),
            Campo("sub_muestra", "Que se muestra", ["ambos", "eve", "usuario"]),
            Ayuda("ambos = lo que dijiste tu (para ver si te entendio) y lo que "
                  "responde Eve,\nrevelandose mientras lo dice."),
            Campo("sub_tam", "Tamano de letra"),
            Campo("sub_lineas", "Lineas maximas"),
            Campo("sub_opacidad", "Opacidad (%)"),
            Campo("sub_separacion", "Separacion del cartel (px)"),
        ),
    ),
    Fondo("sub", "Fondo de los subtitulos"),
)


def textos(bloque=None) -> list:
    """Todo lo que este bloque le muestra al usuario.

    Recorriendo los objetos y no el codigo: los datos estan aca mismo, asi que
    esto no se puede desfasar de lo que el panel dibuja. El chequeo de
    traduccion lo suma a lo que encuentra dentro de `tr("...")`.
    """
    if bloque is None:
        bloque = [item for tabla in TABLAS for item in tabla]
    salida = []
    for item in bloque:
        if isinstance(item, Seccion):
            salida.append(item.titulo)
            salida.extend(textos(item.hijos))
        elif isinstance(item, Fila):
            salida.extend(textos(item.hijos))
        elif isinstance(item, Propio):
            pass  # lo suyo lo dibuja el panel, y ahi los textos van con `tr`
        elif isinstance(item, (Campo, Interruptor, Boton, Clave)):
            salida.append(item.etiqueta)
        elif isinstance(item, Ayuda):
            salida.append(item.texto)
        elif isinstance(item, Colores):
            salida.extend(etiqueta for _rol, etiqueta in ROLES_ETIQUETA)
        elif isinstance(item, Fondo):
            salida.append(item.titulo)
    return salida


def opciones_de(clave: str, bloque=None):
    """Las opciones cerradas que el panel ofrece para una clave, o None.

    Sirve para preguntar "esto se puede elegir?" sin abrir una ventana ni hacer
    grep sobre `gui.py`. Antes esa pregunta se contestaba buscando el texto en
    el fuente, y al migrar una pestaña al registro la respuesta se volvia que no
    --aunque la opcion siguiera ahi.
    """
    if bloque is None:
        bloque = [item for tabla in TABLAS for item in tabla]
    for item in bloque:
        if isinstance(item, (Seccion, Fila)):
            hallado = opciones_de(clave, item.hijos)
            if hallado is not None:
                return hallado
        elif isinstance(item, Campo) and item.clave == clave:
            return item.opciones
    return None


def claves(bloque) -> list:
    """Todas las claves de config que toca un bloque del registro.

    Sirve para comprobar, sin abrir una ventana, que la version generada cubre
    exactamente lo mismo que la escrita a mano. `Fondo` aporta las suyas por
    prefijo, que es como las nombra `_bloque_fondo`.
    """
    salida = []
    for item in bloque:
        if isinstance(item, (Seccion, Fila)):
            salida.extend(claves(item.hijos))
        elif isinstance(item, Propio):
            salida.extend(item.claves_propias)
        elif isinstance(item, (Campo, Interruptor)):
            salida.append(item.clave)
        elif isinstance(item, Colores):
            salida.extend(f"{item.prefijo}_color_{rol}" for rol in ROLES)
        elif isinstance(item, Fondo):
            salida.extend([
                f"{item.prefijo}_fondo",
                f"{item.prefijo}_fondo_ajuste",
                f"{item.prefijo}_fondo_opacidad",
                f"{item.prefijo}_fondo_tinte",
                f"{item.prefijo}_grad",
                f"{item.prefijo}_grad_a",
                f"{item.prefijo}_grad_b",
            ])
    return salida


VENTANA = (
    Seccion(
        "La ventana de actividad",
        (
            Ayuda("Es la tercera ventana de Eve, aparte del panel y del cartel. Ahi se\n"
                  "ve que esta haciendo: los modulos que le pongas, el grafo de lo que\n"
                  "ejecuto, el medidor de contexto y el lector de paginas.\n"
                  "\nTiene dos modos arriba, y no son dos pantallas sino quien puede\n"
                  "escribir. En 'Work' se mira; en 'Edit' se agarran los modulos con el\n"
                  "mouse: clic elige, Ctrl suma, Shift agrega un rango, arrastrar mueve\n"
                  "y Ctrl+Z deshace. Con varios elegidos se editan las propiedades que\n"
                  "TIENEN EN COMUN, y si el valor difiere el campo arranca vacio para\n"
                  "que aplicar no los iguale sin querer."),
            Campo("consola_modo", "Cuando se abre", ["nunca", "con_eve"]),
            Ayuda("'nunca' = solo cuando la abres tu. 'con_eve' = se abre junto con\n"
                  "Eve y queda ahi. Corre como proceso aparte, asi que si se cuelga no\n"
                  "se lleva puesto al asistente."),
            Fila((
                Boton("Abrir la ventana de actividad", "_abrir_consola"),
                Boton("Armar el tablero de arranque", "_mods_semilla_tablero"),
                Ayuda("  si la abres y esta vacia, es porque no hay modulos en el tablero"),
            )),
        ),
    ),
)


VOZ = (
    Seccion(
        "Como te escucha",
        (
            Campo("stt_provider", "STT (reconocimiento)",
                  ["faster-whisper", "parakeet", "openai"]),
            Campo("stt_model", "Modelo Whisper local",
                  ["tiny", "base", "small", "medium", "large-v3"]),
            Campo("stt_sensibilidad", "Sensibilidad",
                  ["auto", "normal", "ruido", "bajo", "manual"]),
            Fila((
                Boton("Probar que te escucha", "probar_stt"),
                Boton("Probar GPU", "gpu_probar"),
            )),
            Salida("gpu_label"),
            Ayuda("Probar recorre el camino entero y no una pieza suelta: graba de tu\n"
                  "microfono de verdad y transcribe con el modelo que tengas elegido.\n"
                  "\nSensibilidad: 'normal' para un cuarto tranquilo, 'ruido' si hay\n"
                  "musica o un juego atras, 'bajo' de madrugada. 'auto' la elige por\n"
                  "hora; las reglas y los numeros medidos estan en el ajuste fino.\n"
                  "\n'auto' NO se envia todavia, y por eso: el modo correcto mira el\n"
                  "ruido del ambiente y elige solo, pero el banco con el que se mide\n"
                  "todo esto se corto por silencio y quedo sin silencios: mediana de\n"
                  "90 ms antes de la primera palabra, y uno solo de 24 llega a los\n"
                  "300 que hacen falta. 'Grabar el banco de voz' arregla eso: guia\n"
                  "la grabacion y no acepta una toma donde te adelantaste."),
        ),
    ),
    Seccion(
        "Ajuste fino del reconocimiento",
        (
            Ayuda("Todo lo de aca esta medido sobre las mismas 24 grabaciones propias.\n"
                  "\nSensibilidad:\n"
                  "  normal  cuarto tranquilo         WER 10.9%  (con ruido 12.5%)\n"
                  "  ruido   musica o el juego atras  WER  8.7%  (con ruido  0.0%)\n"
                  "  bajo    de madrugada, voz suave  WER 12.0%  (con ruido 18.8%)\n"
                  "  manual  usa el umbral y el aire de mas abajo\n"
                  "\nQue modelo conviene:\n"
                  "  small     WER 10.9%   0.9s por orden en gpu,  3.3s en cpu\n"
                  "  medium    WER  4.9%   1.8s en gpu, 10.2s en cpu  <- pide gpu\n"
                  "  large-v3  WER  4.9%   2.7s en gpu, y PEOR en nombres propios\n"
                  "            (34.8% contra 17.4% de medium): mas grande no es\n"
                  "            mejor aca."),
            Campo("parakeet_cuantizacion", "Parakeet: cuantizacion", ["int8", ""]),
            Ayuda("parakeet es el modelo de NVIDIA. Entro porque gano medido sobre las\n"
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
                  "Sin cuantizar mejora los nombres propios pero pesa 2.4 GB."),
            Campo("stt_device", "Dispositivo", ["cpu", "cuda"]),
            Campo("stt_computo", "Tipo de computo",
                  ["auto", "int8", "int8_float32", "int8_float16", "float16", "float32"]),
            Ayuda("cuda necesita las librerias de NVIDIA instaladas; si faltan, cae a cpu\n"
                  "solo y avisa. Medido en una GTX 1660 SUPER: 3.42s por orden en cpu\n"
                  "contra 0.71s en gpu. 'auto' elige int8 en cpu e int8_float16 en gpu."),
            Interruptor("stt_vad", "Recortar silencios antes de transcribir (VAD)"),
            Campo("stt_horario", "Reglas por horario", None, 40),
            Campo("perfil_reglas", "Perfil segun el contexto", None, 40),
            Ayuda("Cambia de perfil solo, segun la hora o el programa que\n"
                  "tengas adelante. Misma sintaxis que la linea de arriba:\n"
                  "  22:00-06:00=noche, discord=gaming\n"
                  "\nLa condicion es un rango de horas si tiene forma de rango,\n"
                  "y si no el nombre del programa. GANA LA PRIMERA QUE ENTRA,\n"
                  "asi que el orden en que las escribes es el orden de\n"
                  "prioridad -- es lo unico de esto que no se adivina.\n"
                  "\nEl nombre del programa se compara por pedazo: `discord`\n"
                  "agarra tambien `Discord.exe` y `discordptb`, para no tener\n"
                  "que abrir el administrador de tareas para escribir una\n"
                  "regla.\n"
                  "\nVacio no cambia nada. Y un perfil solo toca como se VE y\n"
                  "como suena Eve: no puede cambiarte el motor, la tecla, los\n"
                  "permisos ni tus datos."),
            Ayuda("Van separadas por coma y solo pisan al modo 'auto':\n"
                  "  00:00-06:00=bajo, 20:00-23:59=ruido\n"
                  "Si eliges un modo a mano, el reloj no te lo cambia."),
            Campo("stt_beam", "Busqueda por haz (beam)", None, 10),
            Ayuda("Cuantas ramas explora el reconocedor. Medido sobre una orden\n"
                  "tipica: beam 5 tarda 4.4s y beam 1 tarda 3.5s, con el MISMO texto.\n"
                  "Sirve para dictado largo, no para ordenes de ocho palabras."),
            Campo("stt_vad_umbral", "Umbral del detector", None, 10),
            Campo("stt_vad_aire_ms", "Aire del detector (ms)", None, 10),
        ),
        AVANZADO,
    ),
    Seccion(
        "Cuando se da cuenta de que terminaste",
        (
            Campo("cierre_modo", "Quien lo decide", ["fijo", "modelo"]),
            Campo("cierre_umbral", "Umbral del modelo", None, 10),
            Fila((
                Boton("Bajar el modelo (8 MB)", "turno_bajar"),
                Salida("turno_label"),
            )),
            Ayuda("fijo    espera 0.7 segundos de silencio y corta. Es un numero\n"
                  "        para dos situaciones que no se parecen --pensar en medio\n"
                  "        de una orden larga, y terminar de decirla-- asi que se\n"
                  "        equivoca en las dos: te corta pensando, y te hace\n"
                  "        esperar cuando ya terminaste.\n"
                  "modelo  le pregunta a smart-turn-v3 si la frase esta completa.\n"
                  "        Son 8 MB, licencia BSD-2, y corre sobre el mismo\n"
                  "        onnxruntime que ya usa el detector de voz: no agrega\n"
                  "        ninguna dependencia. Unos 12 ms por consulta.\n"
                  "\nEl modelo NO se baja solo. El boton de arriba es el momento en\n"
                  "que decides bajarlo, y hasta entonces manda el cronometro.\n"
                  "\nLo que TODAVIA no se midio: si reconoce el final de turno en\n"
                  "espanol rioplatense. Los 23 idiomas son los que el modelo dice\n"
                  "soportar, no los que se comprobaron aca. Por eso viene en\n"
                  "'fijo' de fabrica: un numero conocido que a veces molesta es\n"
                  "mejor que un modelo sin medir que corta a mitad de frase."),
        ),
        AVANZADO,
    ),
    Seccion(
        "Despertarla diciendo su nombre",
        (
            Interruptor("wake_activo",
                        "Activar diciendo una palabra (deja el microfono abierto)"),
            Campo("wake_palabra", "Palabra (vacio = su nombre)", None, 20),
            Campo("wake_modelo", "Modelo de la puerta", ["tiny", "base", "small"]),
            Fila((
                Boton("Probar la palabra", "probar_wake"),
                Salida("wake_label"),
            )),
            Ayuda("Apagado de fabrica: prenderlo deja el microfono abierto todo el\n"
                  "tiempo. Dile el nombre y la orden de un tiron, en la misma frase:\n"
                  "  \"Eve, abre Spotify\"\n"
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
                  "varias formas, separadas por | o por coma, y de fabrica vienen\n"
                  "las dos.\n"
                  "\nDejalo VACIO y la despierta su nombre, el de la pestana General.\n"
                  "Antes eran dos ajustes que de afuera se ven como uno: renombrarla\n"
                  "no cambiaba la palabra, y nada en pantalla lo decia."),
        ),
        # Deja de ser AVANZADO: en modo "esencial" las avanzadas arrancan
        # CERRADAS, asi que la seccion del despertar estaba plegada adentro de
        # una pestana que ni se llama como ella. Sigue apagada de fabrica --deja
        # el microfono abierto todo el dia y eso lo elige el usuario-- pero
        # apagada y escondida son dos cosas distintas.
    ),
    Seccion(
        "Como te habla",
        (
            Campo("tts_provider", "TTS (voz)", ["sapi", "piper", "elevenlabs"]),
            Campo("piper_voice", "Voz de Piper"),
            Campo("piper_velocidad", "Velocidad"),
            Campo("volumen", "Volumen"),
            Ayuda("Velocidad 1.0 = normal, mas alto = mas lento. "
                  "Volumen 1.0 = como sale del sintetizador."),
            Interruptor("speak_replies", "Leer las respuestas en voz alta"),
            Fila((Boton("Probar que te habla", "probar_tts"),)),
        ),
    ),
    Seccion(
        "Ajuste fino de la voz",
        (
            Ayuda("Que voz se entiende mejor. Medido sobre diez frases, sintetizando\n"
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
                  "eligela a mano en Voz de Piper."),
            Campo("piper_hablante", "Hablante"),
            Ayuda("Hablante solo sirve en las voces que traen varias."),
            Campo("tts_voice", "Voz de Windows", "_voces_de_windows"),
            Campo("elevenlabs_voice_id", "ElevenLabs voice_id"),
        ),
        AVANZADO,
    ),
    Seccion(
        "Que espanol habla",
        (
            Campo("dialecto", "Variante",
                  ["", "neutro", "colombiano", "mexicano", "rioplatense", "castellano"]),
            Fila((Boton("Usar la voz que le corresponde", "voz_del_dialecto"),)),
            Ayuda("Cambia como ESCRIBE: tu contra vos, vale contra dale. La voz va\n"
                  "aparte, y el boton de arriba le pone la que le corresponde.\n"
                  "No hay voz colombiana en el catalogo de Piper, asi que esa variante\n"
                  "comparte la mexicana y cambia solo el vocabulario."),
        ),
    ),
    Seccion(
        "Personalidad",
        (
            Campo("persona_tono", "Tono", None, 44),
            Ayuda("Como habla, no que hace. Va al final del prompt y siempre pierde\n"
                  "contra el manual: no puede hacerla hablar de mas ni narrar en vez\n"
                  "de actuar. Vacio = sin personaje. Lo setea cada perfil."),
        ),
    ),
    Seccion(
        "Programas que Eve conoce",
        (
            Salida("apps_label"),
            Campo("stt_vocabulary", "Vocabulario extra", None, 40),
            Ayuda("Nombres que el reconocimiento suele errar, separados por comas."),
            Campo("catalogo_modo", "Que catalogo viaja", ["usados", "completo"]),
            Ayuda("El catalogo de programas viaja en CADA llamada al modelo, y entero\n"
                  "es un tercio del prompt. 'usados' manda solo los que aparecen en tu\n"
                  "log de acciones, ordenados por frecuencia, y el resto se busca con\n"
                  "`E programa NOMBRE`. Medido: 1551 tokens menos por llamada, un 36%.\n"
                  "'completo' los manda todos, por si prefieres pagar y no buscar."),
            Fila((Boton("Reescanear programas", "rescan_apps"),)),
            Propio("_apps_al_abrir"),
        ),
        AVANZADO,
    ),
)


TEMA = (
    Seccion(
        "Colores del panel",
        (
            Campo("ui_tema", "Tema", "_temas_disponibles"),
            Interruptor("ui_pintar_panel", "Pintar tambien este panel con el tema"),
            Ayuda("Pintar el panel obliga a dibujar los controles por nuestra cuenta: Windows\n"
                  "no deja cambiarle el color a los suyos. El cambio se ve al instante."),
            Campo("ui_nav", "Navegacion", ["lateral", "pestanas"]),
            Ayuda("Como se pasa de una seccion a otra:\n"
                  "  lateral    una barra a la izquierda\n"
                  "  pestanas   las de arriba, como era antes\n"
                  "Siete pestañas arriba ya rozan el ancho de la ventana. La barra\n"
                  "esta dibujada pero se maneja con el teclado igual: entra en el\n"
                  "tabulador, las flechas mueven y Enter activa.\n"
                  "\nEl cambio se ve al reabrir el panel."),
            Campo("ui_cromo", "Secciones", ["tarjeta", "plano"]),
            Ayuda("Como se ve cada seccion:\n"
                  "  tarjeta  en una tarjeta con esquinas redondeadas\n"
                  "  plano    filas sueltas, como era antes\n"
                  "Las esquinas redondeadas ttk no las tiene, asi que el marco se\n"
                  "dibuja aparte. Los CONTROLES siguen siendo los de siempre en los\n"
                  "dos casos: uno dibujado seria invisible para un lector de\n"
                  "pantalla, y eso no se cambia por una esquina.\n"
                  "\nNecesita el tema aplicado al panel, aca arriba."),
            Interruptor("ui_sin_animacion", "No animar los GIF (dejar el primer cuadro)"),
        ),
    ),
    Seccion(
        "Colores a mano",
        (
            Ayuda("Solo se usan con el tema 'personalizado'."),
            Colores("ui"),
        ),
        AVANZADO,
    ),
    Seccion(
        "Tipografia",
        (
            Campo("ui_fuente", "Fuente del panel", "_fuentes_disponibles"),
            Campo("ui_fuente_tam", "Tamaño (0 = el de la fuente)"),
            Campo("hud_fuente", "Fuente del cartel", "_fuentes_disponibles"),
            Campo("sub_fuente", "Fuente de los subtitulos", "_fuentes_disponibles"),
        ),
        AVANZADO,
    ),
    Seccion(
        "Colores del cartel flotante",
        (
            # El tema del cartel NO va aca: vive en la pestaña Cartel, junto a
            # lo demas del cartel. Estuvo en los dos lados y el de aca era un
            # combo muerto --se podia tocar y no guardaba, porque `self.vars`
            # es un dict y la segunda asignacion pisaba a la primera.
            Colores("hud"),
            Ayuda("Vacio = el cartel usa el mismo tema que el panel, que es lo que\n"
                  "quiere casi todo el mundo. Los colores de abajo solo se usan con\n"
                  "el tema 'personalizado'."),
        ),
        AVANZADO,
    ),
    Seccion(
        "Fluidez",
        (
            # La lista va literal y no importada de `gpu`: este modulo
            # no importa nada del proyecto a proposito, para que un test
            # lo pueda leer sin tkinter. Un test comprueba que no se
            # despeguen.
            Campo("motor_dibujo", "Motor de dibujo",
                  ["auto", "skia", "pillow"]),
            Ayuda("Quien pinta los modulos. `auto` usa la GPU si tu maquina la\n"
                  "tiene, y si no cae a Pillow por CPU, que es lo de siempre.\n"
                  "\nMedido en un escritorio x64 sobre 1100x700 con seis capas y\n"
                  "quinientas particulas: Pillow por CPU cuesta 20.3 ms de\n"
                  "mediana y Skia por GPU 2.0. Pero Skia SIN GPU cuesta 214, o\n"
                  "sea diez veces peor que no usarlo: por eso pedirlo a mano no\n"
                  "lo fuerza si no se puede, y la linea de abajo dice que quedo.\n"
                  "\nLo que gana no son cuadros por segundo --con un modulo\n"
                  "animando ya sobra-- sino techo: shaders y miles de\n"
                  "particulas no entran por el camino de CPU."),
            Salida("motor_dibujo_label"),
            Campo("ui_fps", "Cuadros por segundo"),
            Ayuda("Vale para el cartel y para la ventana de actividad. 0 = el que\n"
                  "sugiere tu maquina: 30 en un PC normal, 20 en ARM.\n"
                  "\nMedido en un escritorio x64: componer la ventana entera con seis\n"
                  "capas y quinientas particulas cuesta 21.6 ms de mediana y 23.1 de\n"
                  "p95, asi que a 30 cuadros quedan 11 ms de margen. Si ves tirones,\n"
                  "bajalo antes que apagar modulos: 20 cuadros con todo puesto se ve\n"
                  "mejor que 30 a medias."),
        ),
        AVANZADO,
    ),
    Seccion(
        "Cabecera del panel",
        (
            Propio("_cabecera_del_panel", ("ui_banner",)),
            Campo("ui_banner_opacidad", "Opacidad (%)"),
            Ayuda("Se ve arriba de cada pestaña y se aplica al reabrir el panel. No hay fondo\n"
                  "para todo el panel: los controles de Windows pintan su propio fondo opaco\n"
                  "y lo taparian."),
        ),
        AVANZADO,
    ),
    # Lo que repinta la vista previa al instante. Junto y al final, en vez de
    # tres bucles de `trace_add` sueltos en medio del bloque.
    Vivo(("ui_tema", "ui_sin_animacion", "ui_fuente", "ui_fuente_tam",
          "hud_fuente", "sub_fuente")),
)


GENERAL = (
    Seccion(
        "Quien es Eve",
        (
            Campo("assistant_name", "Nombre de la IA"),
            Campo("language", "Idioma en que te habla"),
            Campo("hotkey", "Tecla del keypad"),
            Fila((
                Boton("Asignar tecla", "hotkey_capturar"),
                Boton("Probar la tecla", "probar_tecla"),
                Salida("tecla_label"),
            )),
            Ayuda("La tecla la escucha el asistente, no este panel: si el asistente no\n"
                  "esta corriendo, el boton te lo dice en vez de dejarte probando una\n"
                  "tecla que nadie escucha."),
        ),
    ),
    Seccion(
        "Quien piensa por ella",
        (
            # Un control en lugar de dos. `engine` y `compat_proveedor` eran
            # campos separados y en SECCIONES distintas, asi que elegir quien
            # piensa eran dos pasos y despues habia que deducir cual de las
            # nueve claves quedaba viva. Declara las dos porque las escribe.
            Propio("_selector_proveedor", ("engine", "compat_proveedor")),
            Campo("model", "Modelo (motor api)", "_modelos_api"),
            Campo("cc_model", "Modelo (motor claude-code)", "_modelos_cc"),
            Campo("cc_permission_mode", "Permisos (motor claude-code)", "_permisos_cc"),
            Fila((
                Boton("Probar el motor", "probar_motor"),
                Salida("motor_label"),
            )),
            Ayuda("Le manda una pregunta trivial y muestra la respuesta y cuanto tardo.\n"
                  "Es la unica forma de saber que el motor esta bien configurado sin\n"
                  "tener que hablarle y quedarse esperando a ver si contesta."),
        ),
    ),
    Seccion(
        "Otros motores",
        (
            # `compat_proveedor` se elige arriba, en el selector.
            Campo("compat_modelo", "compat: modelo",
                  "_modelos_del_proveedor", abierto=True),
            Campo("compat_url", "compat: URL propia", None, 40),
            Fila((
                Boton("Buscar modelos", "compat_buscar_modelos"),
                Salida("compat_estado"),
            )),
            Ayuda("El modelo era un campo de texto libre, y eso obliga a saber el\n"
                  "identificador exacto: OpenRouter publica cientos y LM Studio\n"
                  "sirve el que hayas cargado. El boton se los pregunta al propio\n"
                  "servicio --`GET /v1/models` es parte del protocolo-- y te deja\n"
                  "elegir de la lista.\n"
                  "\nLM Studio y Ollama NO piden clave: escuchan en tu maquina. Los de\n"
                  "la nube si, y va en Cuentas."),
            Propio("_ayuda_compat"),
            Campo("ollama_host", "Ollama: host"),
            Campo("ollama_model", "Ollama: modelo"),
        ),
        AVANZADO,
    ),
    Seccion(
        "Ajuste fino del modelo",
        (
            Campo("effort", "Effort", "_niveles_de_effort"),
            Campo("max_tokens", "Max tokens"),
            Campo("context_turns", "Turnos de contexto"),
            Campo("context_minutes", "Minutos de contexto"),
        ),
        AVANZADO,
    ),
    Seccion(
        "Hasta donde puede meterse",
        (
            # Los dos frenos van a mano: uno es un cuadro de texto de varias
            # lineas y el otro un desplegable que guarda la NEGACION de su
            # clave. Declaran lo que tocan para no salirse de la verificacion.
            Propio("_rutas_permitidas", ("workdirs",)),
            Propio("_selector_de_permisos", ("confirm_destructive",)),
            Campo("archivos_alcance", "Hasta donde llega con los archivos",
                  ["exacto", "explorar", "escribir"]),
            Ayuda("Que puede hacer Eve DENTRO de las rutas de arriba. Las rutas\n"
                  "siguen siendo el limite: esto no agranda lo permitido, decide\n"
                  "que hace adentro.\n"
                  "  exacto     leer un archivo si le dictas la ruta entera\n"
                  "  explorar   ademas listar una carpeta y buscar por nombre;\n"
                  "             sin esto, encontrar algo dependia de que tu\n"
                  "             supieras y dictaras la ruta\n"
                  "  escribir   ademas crear y reemplazar. Pisar un archivo que\n"
                  "             ya existe te pregunta primero, salvo que hayas\n"
                  "             apagado la confirmacion aca arriba\n"
                  "Con 'exacto' los comandos de explorar no existen para ella y\n"
                  "tampoco se nombran en el prompt: una capacidad que no se puede\n"
                  "usar solo gasta lugar e invita a que pruebe y le digan que no."),
            Ayuda("'Permitir todo' desactiva la confirmacion y tambien los permisos internos\n"
                  "de Claude Code. Todo queda igual registrado en la pestaña Acciones."),
        ),
    ),
    Seccion(
        "Skills que le pasas",
        (
            Propio("_skills_lista", ()),
            Campo("skills_alcance", "Cuanto de las skills viaja",
                  ["nada", "consultar", "completo"]),
            Ayuda("Una skill es un .md tuyo con instrucciones: como quieres un\n"
                  "informe, como se hace un deploy, con que tono le escribes a un\n"
                  "cliente.\n"
                  "  nada        no existen para ella\n"
                  "  consultar   viaja el INDICE --nombre y un renglon-- y el texto\n"
                  "              entero lo pide con 'E skill ver' cuando hace falta\n"
                  "  completo    viajan enteras, siempre\n"
                  "La diferencia se paga en CADA frase que le digas, incluido 'que\n"
                  "hora es'. Medido con cinco skills de una pagina: 'consultar'\n"
                  "suma 4% al prompt y 'completo' 145%, o sea que lo duplica."),
        ),
    ),
    Seccion(
        "Quien manda sobre un ajuste",
        (
            Campo("autoridad", "Autoridad", ["usuario", "eve", "preguntar"]),
            Ayuda("usuario: lo que cambies a mano queda trabado y Eve no lo pisa.\n"
                  "eve: puede cambiar lo que quiera.  preguntar: pide permiso cada vez.\n"
                  "Para soltar lo trabado, dile 'destraba <clave>' o borra la lista abajo."),
            Campo("ayuda_alcance", "Hasta donde arma sola", ["nada", "datos", "codigo"]),
            Ayuda("Cuando le pides algo hablando, hasta donde puede llegar:\n"
                  "  nada    no toca nada; es la voz y nada mas\n"
                  "  datos   modulos, ajustes y perfiles -- todo lo que ya es una\n"
                  "          clave de config y pasa por el mismo freno que el panel\n"
                  "  codigo  ademas puede DEJAR ESCRITO un addon .py, que igual no\n"
                  "          corre hasta que lo apruebes a mano en Addons\n"
                  "No hay un cuarto nivel donde apruebe sus propios addons, y no\n"
                  "deberia haberlo: la huella del contenido es lo unico que separa un\n"
                  "plugin de un agujero.\n"
                  "\nEs OTRO eje que 'Quien manda'. Aquel decide quien gana cuando los\n"
                  "dos quieren el mismo valor; este, que clase de cosa puede crear.\n"
                  "Con 'nada' el prompt tampoco lleva el vocabulario de modulos.\n"
                  "Cuanto de ese vocabulario viaja lo decide el ajuste de abajo."),
            Campo("ayuda_vocabulario", "Cuanto le contamos de antemano",
                  ["consultar", "minimo", "completo"]),
            Ayuda("Cuanto vocabulario de interfaz viaja en CADA llamada:\n"
                  "  consultar  dos renglones, y Eve pregunta con 'E ui buscar'\n"
                  "             cuando le hace falta. 310 caracteres.\n"
                  "  minimo     ademas los trece nombres de tipo. 485.\n"
                  "  completo   el esquema entero, con sus props. 1352.\n"
                  "Medido con el mismo contador que dibuja el modulo\n"
                  "'contexto': de 11 972 caracteres de prompt, 'completo' se\n"
                  "lleva el 11.3% y 'consultar' el 2.8%. O sea 8.7% menos en\n"
                  "TODO lo que le digas, incluido 'que hora es', a cambio de\n"
                  "una consulta extra las veces que si toca la interfaz.\n"
                  "\nEs OTRO eje que los dos de arriba: aquellos dicen QUE puede\n"
                  "hacer y quien gana cuando los dos quieren el mismo valor;\n"
                  "este, solo cuanto le adelantamos. Con 'Hasta donde arma\n"
                  "sola' en nada no viaja nada y este no hace diferencia."),
            Campo("claves_del_usuario", "Claves que fijaste tu", None, 44),
        ),
        AVANZADO,
    ),
)


CARTEL = (
    Seccion(
        "Cartel en pantalla",
        (
            Fila((Boton("Mostrar el cartel", "probar_overlay"),)),
            Ayuda("Lo hace aparecer unos segundos aunque este en modo 'auto'. Es lo que\n"
                  "separa 'el cartel esta mal configurado' de 'el cartel no arranca'."),
            Campo("overlay_modo", "Cuando se ve", ["auto", "siempre", "nunca"]),
            # El tema del cartel vive aca, junto a lo demas del cartel, y no
            # mezclado con los colores del panel.
            Campo("hud_tema", "Tema (vacio = el del panel)", "_temas_del_cartel"),
            Ayuda("auto = aparece al hablarle y se va sola. Nunca se lleva el foco de lo que\n"
                  "estes haciendo, y los clics la atraviesan."),
            Campo("hud_titulo", "Titulo (vacio = nombre IA)"),
            Campo("hud_subtitulo", "Segunda linea"),
            Campo("hud_icono", "Icono", ["hexagono", "ninguno"]),
            Campo("hud_contorno", "Contorno",
                  ["redondeado", "ninguno", "linea", "esquinas", "doble",
                   "hexagonal", "biselado"]),
            Campo("hud_onda", "Onda",
                  ["barras", "espejo", "linea", "puntos", "ninguna"]),
            Campo("hud_escala", "Escala (%)"),
            Campo("hud_opacidad", "Opacidad (%)"),
            Ayuda("Menos de 10 se trata como 10: por debajo de eso el cartel no se ve\n"
                  "y no habria forma de encontrarlo para subirlo de nuevo. La opacidad\n"
                  "de cada modulo se MULTIPLICA con esta, asi que 20% de ventana por\n"
                  "20% de modulo da 4% de verdad."),
            Campo("overlay_pantalla", "Pantalla", "_pantallas"),
            Campo("overlay_area", "Area", ["trabajo", "completa"]),
            Ayuda("0 = donde lo dejes, sin restriccion, y puedes arrastrarlo de un\n"
                  "monitor al otro. 1 en adelante lo fija a ese monitor y lo mantiene\n"
                  "adentro aunque lo arrastres. Si desenchufas el que elegiste, vuelve\n"
                  "al escritorio entero en vez de quedar en un lugar que no existe.\n"
                  "'trabajo' descuenta la barra de tareas; solo cambia algo en Windows."),
            Campo("overlay_clics", "Toma clics", ["nunca", "hover", "fijo"]),
            Ayuda("El cartel normalmente deja pasar los clics al programa de atras.\n"
                  "  nunca   nunca los toma\n"
                  "  hover   solo mientras el puntero esta sobre un modulo marcado\n"
                  "          como 'interactivo'; si no marcaste ninguno, es igual\n"
                  "          que 'nunca'\n"
                  "  fijo    siempre los toma, y siempre tapa lo que este debajo\n"
                  "Se pregunta donde esta el puntero treinta veces por segundo en vez\n"
                  "de escuchar eventos, porque una ventana que deja pasar los clics\n"
                  "tampoco recibe los de movimiento: esperarlos seria esperar para\n"
                  "siempre. Ese mismo poll es el que hace andar 'cuando = hover'."),
            Campo("hud_forma", "Forma", ["caja", "recortado"]),
            Ayuda("recortado = el cartel deja de ser un rectangulo y por las esquinas cortadas\n"
                  "de los contornos hexagonal y biselado se ve lo que hay atras."),
            Fila((
                Boton("Elegir imagen del icono...", "_icono_elegir"),
                Boton("Mover en pantalla", "_overlay_mover"),
                Boton("Volver a la esquina", "_overlay_esquina"),
            )),
        ),
    ),
    Seccion(
        "Marco del icono",
        (
            Ayuda("El marco es parametrico: eliges cuantos lados, cuanto gira y cuanto se\n"
                  "redondean las puntas. Las formas de abajo son atajos que llenan esos\n"
                  "numeros; despues los puedes tocar a mano."),
            Propio("_atajos_de_forma"),
            Campo("hud_marco_lados", "Lados (menos de 3 = circulo)"),
            Campo("hud_marco_rot", "Giro (grados)"),
            Campo("hud_marco_redondeo", "Redondeo de las puntas"),
            Campo("hud_marco_grosor", "Grosor del trazo"),
        ),
        AVANZADO,
    ),
    Fondo("hud", "Fondo del cartel"),
    Vivo(("hud_tema", "hud_titulo", "hud_subtitulo", "hud_icono", "hud_contorno",
          "hud_onda", "hud_forma", "hud_marco_lados", "hud_marco_rot",
          "hud_marco_redondeo", "hud_marco_grosor")),
    Propio("_previa_primera_vez"),
)


# Todas las tablas migradas. Va al final porque nombra las de arriba, y existe
# para que el chequeo de traduccion las recorra sin que nadie tenga que
# acordarse de sumar cada pestaña nueva a mano.
# Las secciones que hablan de MODELOS se juntan en una tabla propia.
#
# Estaban repartidas en tres lados --el motor y su ajuste fino en General, el
# reconocimiento y la voz en Voz, las claves en Cuentas-- y configurar un
# proveedor obligaba a saltar entre las tres: elegis `compat`, vas a Cuentas a
# cargar la clave, volves a General a poner el modelo. Son un solo trabajo.
#
# Se COMPONEN por titulo en vez de mudar el texto de las declaraciones. Asi
# cada seccion se sigue leyendo donde un lector la busca --lo del habla, junto
# a lo del habla-- y el diff no es mover doscientas lineas de un lado a otro,
# que es donde se pierde una fila sin que nadie lo note.
COMANDOS = (
    Seccion(
        "Frases que hacen algo fijo",
        (
            Propio("_comandos_lista", ()),
            Campo("comandos_voz", "Comandos por voz", ["si", "no"]),
            Ayuda("Con 'si', una frase que coincida con las de Comandos.md se\n"
                  "resuelve sin llamar al modelo. Con 'no', todo va al modelo\n"
                  "como antes, y el archivo se ignora.\n"
                  "La coincidencia es EXACTA --sin mayusculas ni acentos-- y no\n"
                  "difusa a proposito: un comando que a veces agarra es peor que\n"
                  "uno que no existe."),
        ),
    ),
)

_A_MODELOS = (
    "Quien piensa por ella", "Otros motores", "Ajuste fino del modelo",
    "Como te escucha", "Ajuste fino del reconocimiento",
    "Cuando se da cuenta de que terminaste",
    "Despertarla diciendo su nombre",
    "Como te habla", "Ajuste fino de la voz",
)


def _partir(tabla):
    """(las que se van a Modelos, las que se quedan), en su orden original."""
    van = tuple(s for s in tabla if s.titulo in _A_MODELOS)
    quedan = tuple(s for s in tabla if s.titulo not in _A_MODELOS)
    return van, quedan


_de_general, GENERAL = _partir(GENERAL)
_de_voz, VOZ = _partir(VOZ)

# Los dos bloques que `gui.py` componia AL LADO del registro, y que por eso no
# estaban declarados en ningun lado: la galeria de perfiles arriba de General,
# y la sesion de Claude Code abajo de Modelos. Se agregan despues de `_partir`
# porque van en la pestana final, no en la tabla de la que salieron.
#
# Que hayan quedado afuera tanto tiempo tiene una explicacion incomoda: cada
# pestana se arma con `_componer(rotulo, subtitulo, [bloques])`, y un bloque
# que no sale del registro no se distingue de uno que si. Contar tablas no
# alcanzaba para saber que faltaba.


# Primero quien piensa, despues quien te escucha, despues quien te habla: es el
# orden en que se configura, no el orden en que estaban escritas.
MODELOS = _de_general + _de_voz



# Si un titulo de `_A_MODELOS` deja de existir --un renombre-- esa seccion se
# quedaria callada donde estaba y nadie se enteraria. Se avisa al importar.
_perdidos = set(_A_MODELOS) - {s.titulo for s in MODELOS}
assert not _perdidos, f"secciones que _A_MODELOS nombra y no existen: {_perdidos}"

# --- las cuatro que faltaban ----------------------------------------------
# Cuentas, Contactos, Addons y Actividad eran las unicas escritas a mano de
# punta a punta. Entran aca por el mismo motivo que las otras siete: mientras
# vivieron solo en `gui.py`, sus ajustes no aparecian en el buscador del panel
# ni en `catalogo()`, asi que `E ajustar` --Eve cambiando una opcion porque se
# lo pediste hablando-- no las podia tocar. No era una decision, era el efecto
# de no estar declaradas.
#
# Cada rotulo es el LITERAL que dibuja `gui.py`, incluidos los saltos de linea
# y las tildes que faltan. Mejorarlos aca los dejaria sin traducir --la clave
# del diccionario de `textos.py` es la frase en espanol-- y ademas haria que
# el buscador te llevara a un rotulo que no vas a ver en pantalla.

CUENTAS = (
    Seccion(
        "Conexiones con apps (todas opcionales)",
        (
            Ayuda("Sin esto Eve igual abre WhatsApp, Discord, Telegram y el mail con el\n"
                  "mensaje escrito, para que lo mandes tu. Estas claves solo agregan leer\n"
                  "y enviar sin pasar por la app."),
            Clave("discord_webhook", "Discord: URL del webhook"),
            Boton("Probar el webhook", "probar_webhook"),
            Salida("webhook_label"),
            Campo("discord_username", "Discord: nombre a mostrar", ancho=40),
            Campo("discord_avatar", "Discord: URL del avatar", ancho=40),
            Ayuda("Con que nombre y foto aparecen los mensajes que manda por webhook.\n"
                  "Vacio = lo que tenga configurado el webhook en Discord. Andaba\n"
                  "desde siempre; lo que faltaba era donde escribirlo sin editar el\n"
                  "config a mano."),
            # Se autodetecta del disco al abrir, por eso es una excepcion: no
            # alcanza con mostrar la clave, hay que ir a buscarla si esta vacia.
            Propio("_steam_id", ("steam_id",)),
            Clave("steam", "Steam: Web API key"),
            Interruptor("whatsapp_autosend",
                        "WhatsApp: enviar solo (simula el Enter; exige numero, no nombre)"),
            Interruptor("discord_autosend",
                        "Discord: escribir como tu (maneja tu cliente; verifica el canal por titulo)"),
            Ayuda("Gmail: si 'Contrasenas de aplicaciones' no te aparece, tu cuenta no tiene 2FA\n"
                  "o la administra tu organizacion. Alternativa sin claves: agrega el Gmail a\n"
                  "Outlook (Archivo > Agregar cuenta) y Eve lo lee y escribe por ahi.\n"
                  "Webhook: Editar canal > Integraciones > Webhooks. Steam key: steamcommunity.com/dev/apikey"),
        ),
    ),
    Seccion(
        "Outlook",
        (
            Ayuda("No necesita ninguna clave: Eve usa la sesion que ya tiene Outlook en esta PC."),
            Salida("outlook_label"),
            Fila((
                Boton("Agregar / gestionar cuentas", "outlook_login"),
                Boton("Actualizar", "refresh_outlook"),
            )),
        ),
    ),
    Seccion(
        "Gmail",
        (
            Ayuda("Lo mas simple es agregarlo a Outlook con el boton de arriba: Google hace el\n"
                  "login y no queda ninguna clave tuya guardada aca.\n\n"
                  "La otra via es una contrasena de aplicacion (16 letras minusculas). Si Google\n"
                  "dice que no esta disponible, es que tu cuenta no tiene verificacion en dos\n"
                  "pasos, o la administra tu organizacion."),
            Campo("gmail_address", "Tu direccion de Gmail", ancho=38),
            Clave("gmail", "Contrasena de aplicacion"),
            Salida("gmail_label"),
            Fila((
                Boton("Obtener app password", "gmail_login"),
                Boton("Probar conexion", "gmail_probar"),
            )),
        ),
    ),
)

# Contactos no tiene secciones y no se le inventa una: `gui.py` dibuja una
# ayuda y abajo la tabla. Un titulo puesto aca seria un rotulo que el panel
# viejo no muestra, y el chequeo de traduccion pediria traducirlo.
CONTACTOS = (
    Ayuda("Eve usa esta lista cuando nombras a alguien. En 'alias' pon como le dices\n"
          "de verdad, separado por comas (lucho, el lucas) — la voz rara vez dice el\n"
          "nombre completo.\n\n"
          "discord_user  = su @ (para mencionarlo dentro del mensaje)\n"
          "discord_dm    = su chat privado. Activa Ajustes > Avanzado > Modo desarrollador,\n"
          "                boton derecho sobre la conversacion > Copiar ID\n"
          "discord_canal = un canal de servidor. Boton derecho > Copiar enlace"),
    # La agenda entera: tabla, formulario de siete campos y cinco botones. No
    # toca NINGUNA clave de config --vive en su propio archivo-- asi que
    # declara la tupla vacia y no miente sobre lo que cubre.
    Propio("_contactos", ()),
    Ayuda("Exportar genera un archivo .evecontact que puedes mandarle a un amigo por\n"
          "WhatsApp o Discord; el lo abre con Importar y le queda el contacto cargado."),
)

ADDONS = (
    Seccion(
        "Instalados",
        (
            # Los addons se prenden y se apagan por huella, no por una clave de
            # config con un valor escribible: `addons_activos` la escribe el
            # propio panel juntando las casillas. Y cada addon DICE que claves
            # necesita, asi que agregar uno no obliga a tocar esta pantalla.
            Propio("_addons_lista", ("addons_activos",)),
            Ayuda("Destildar uno lo saca del prompt: deja de gastar tokens y Eve deja de\n"
                  "ofrecerlo. Si no hay ninguno tildado, se usan todos los disponibles."),
        ),
    ),
    Seccion(
        "Agregar los tuyos",
        (
            # El texto lleva la ruta de la carpeta adentro, asi que no es un
            # literal: se arma al abrir, como la ayuda del motor compatible.
            Propio("_addons_carpeta_ayuda", ()),
            Boton("Abrir la carpeta de addons", "_addons_carpeta"),
        ),
    ),
    Seccion(
        "Sin revisar",
        (
            Ayuda("Estos archivos no se estan cargando. Un addon es codigo que corre\n"
                  "con tus permisos y no pasa por el freno, asi que hay que mirarlo\n"
                  "antes. Si Eve escribio alguno, aca es donde lo revisas."),
            Propio("_addons_pendientes", ("addons_aprobados",)),
        ),
    ),
    Seccion(
        "Aprobados",
        (
            Ayuda("Estos se cargan. Revocar no borra el archivo: lo devuelve a la\n"
                  "lista de sin revisar, para que puedas volver a mirarlo antes de\n"
                  "decidir de nuevo. Editar un addon aprobado lo saca solo, porque\n"
                  "la aprobacion es de la huella del contenido y no del nombre."),
            Propio("_addons_aprobados", ()),
        ),
    ),
    Seccion(
        "Servidores MCP",
        (
            Campo("mcp_modo", "Modo", "_modos_mcp", ancho=16),
            Ayuda("apagado   no viaja nada al modelo y no se conecta a nada.\n"
                  "prompt    el modelo ve QUE herramientas tienes, y no las puede\n"
                  "          llamar. Eve no levanta ningun servidor.\n"
                  "cliente   Eve levanta el servidor, descubre sus herramientas y\n"
                  "          se las ofrece al modelo. Es correr codigo de terceros\n"
                  "          en tu maquina, y por eso te pregunta antes de cada una."),
            Propio("_mcp_lista", ()),
        ),
    ),
)

# Actividad es de solo lectura: lo que se dijo y lo que se ejecuto. Los dos son
# excepciones porque son vistas --un texto largo y una tabla-- y no ajustes.
ACTIVIDAD = (
    Propio("_historial", ()),
    Propio("_acciones", ()),
)

# La barra de arriba. No es una pestana: son las opciones que cambian como se
# ve TODO el resto, y por eso no pueden vivir escondidas adentro de una. Estan
# declaradas igual para que existan en un solo lugar --hasta ahora el panel las
# dibujaba a mano y eran las dos unicas claves de `DEFAULTS` que ninguna tabla
# nombraba--.
BARRA = (
    Campo("ui_idioma", "Idioma del panel", "_idiomas", ancho=12),
    Campo("ui_modo_panel", "Ver", ["esencial", "completo"], ancho=12),
)

# Los dos bloques que `gui.py` compone AL LADO del registro, en `_componer`.
#
# Van como tablas PROPIAS y no metidas dentro de GENERAL y MODELOS, y la razon
# es concreta: `gui.py` pinta esas dos tablas con `_pintar_registro`, asi que
# agregarles un `Propio` que solo entiende el panel web lo hace reventar al
# abrir. Las dos versiones leen el MISMO registro mientras dure la mudanza, y
# eso obliga a que lo nuevo entre por donde la vieja no mira.
PERFILES = (
    Seccion(
        "Perfiles",
        (
            Propio("_perfiles", ()),
            Ayuda("Un perfil guarda como se ve y como suena Eve: colores, forma, fuente,\n"
                  "voz, velocidad, tono y el nombre del asistente.\n"
                  "NO toca el motor, el modelo, la tecla, los permisos ni tus datos: un\n"
                  "perfil que te pasan no puede cambiarte como trabaja el asistente."),
        ),
    ),
)

SESION_CC = (
    Seccion(
        "Sesion de Claude Code (motor 'claude-code')",
        (
            Salida("auth_label"),
            Fila((
                Boton("Iniciar sesion", "auth_login"),
                Boton("Cerrar sesion", "auth_logout"),
                Boton("Actualizar", "refresh_auth"),
            )),
            Ayuda("Se guardan en el gestor de credenciales de Windows, nunca en texto plano.\n"
                  "Anthropic solo hace falta con el motor 'api'; con 'claude-code' se usa tu suscripcion.\n"
                  "Las otras habilitan proveedores opcionales de voz."),
        ),
    ),
)

# Cada tabla con su nombre, en un solo lugar. `esquema()` tenia el mismo
# diccionario escrito a mano adentro, y ese es exactamente el tipo de copia que
# se desfasa: se agregaron cuatro tablas y el esquema siguio sirviendo ocho, sin
# que nada lo dijera.
POR_NOMBRE = {
    "SUBTITULOS": SUBTITULOS, "VENTANA": VENTANA, "VOZ": VOZ, "TEMA": TEMA,
    "GENERAL": GENERAL, "CARTEL": CARTEL, "MODELOS": MODELOS,
    "COMANDOS": COMANDOS, "CUENTAS": CUENTAS, "CONTACTOS": CONTACTOS,
    "ADDONS": ADDONS, "ACTIVIDAD": ACTIVIDAD, "BARRA": BARRA,
    "PERFILES": PERFILES, "SESION_CC": SESION_CC,
}

TABLAS = tuple(POR_NOMBRE.values())


# Las siete piezas de un bloque de fondo, con el sufijo REAL de su clave. Los
# nombres salen de `_bloque_fondo`, que es quien las dibuja, y los sufijos de
# `claves()`, que es quien ya las enumeraba.
#
# Estos siete estuvieron DESFASADOS de lo que el panel muestra, y no era
# cosmetico: esta tabla alimenta `catalogo()`, que es lo que usan el buscador
# del panel y `E ajustar` --o sea, Eve cambiando una opcion porque se lo
# pediste hablando--. Buscar un rotulo que estabas viendo en pantalla te
# llevaba a otro ajuste:
#
#   buscar("Opacidad de la imagen") -> "Opacidad (%)" y "Imagen de fondo"
#   buscar("Degradado: color 1")    -> "Degradado: color de arriba"
#
# Lo agarro el test de abajo, que compara contra los `tr(...)` de
# `_bloque_fondo`. Sin ese test esto se vuelve a desfasar la proxima vez que
# alguien mejore un rotulo en gui.py, que es como paso.
_PARTES_FONDO = (
    ("_fondo", "Imagen (PNG o GIF)"),
    ("_fondo_ajuste", "Ajuste"),
    ("_fondo_opacidad", "Opacidad de la imagen (%)"),
    ("_fondo_tinte", "Tinte con el acento (%)"),
    ("_grad", "Degradado (si no hay imagen)"),
    ("_grad_a", "Degradado: color 1"),
    ("_grad_b", "Degradado: color 2"),
)

# Lo que dice una persona contra lo que dice el panel. NO es un tesauro: son las
# pocas palabras donde el rotulo tecnico y el humano no coinciden, que es
# exactamente donde buscar fallaba. "transparencia" no aparece en ningun rotulo
# --el ajuste se llama `hud_opacidad`, "Opacidad (%)"-- asi que pedirle a Eve
# que adivine ahi era pedirle que fallara.
# Palabras que aparecen en media docena de rotulos y no distinguen nada. Sin
# esta lista, "transparencia DEL cartel" premiaba a "Opacidad DEL fondo" por
# encima de la opacidad del cartel: la palabra vacia sumaba tanto como la que
# importaba, y ademas sumaba dos veces --por coincidir y por coincidir en el
# nombre-- asi que un rotulo con dos preposiciones le ganaba al ajuste correcto.
VACIAS = frozenset((
    "del", "las", "los", "una", "unos", "unas", "que", "por", "para", "con",
    "sin", "mas", "menos", "muy", "esta", "este", "eso", "esa",
    "todo", "toda", "poneme", "ponme", "hace", "hacer",
    # "cuando", "como" y "donde" NO estan: son rotulos de verdad --"Cuando se
    # ve", "Cuando se abre"-- y sacarlas rompia justo las preguntas que mas
    # naturalmente se hacen sobre esos ajustes.
    "quiero", "puedo", "puede", "dale", "vez", "veces", "algo", "cosa",
))

SINONIMOS = {
    "transparencia": "opacidad", "transparente": "opacidad",
    "translucido": "opacidad", "opaco": "opacidad",
    "letra": "fuente tam", "tipografia": "fuente",
    "tamano": "tam", "grande": "tam", "chico": "tam", "chica": "tam",
    "apagar": "nunca", "desactivar": "nunca", "prender": "siempre",
    "micro": "microfono", "sensibilidad": "vad umbral",
    "noche": "horario", "tirones": "fps", "trabado": "fps",
    "atajo": "hotkey tecla", "boton": "hotkey tecla",
    "ventana": "consola tablero", "actividad": "consola tablero",
    "color": "tema colores", "fondo": "fondo tema",
}


def campos(bloque=None) -> list:
    """Solo los `Campo`, en orden. Los `Interruptor` NO entran.

    Existe para una cosa concreta: el panel pone el rotulo de cada campo en una
    columna de ancho fijo, y ese ancho tiene que ser el del rotulo mas largo o
    los largos salen cortados. El de un interruptor no cuenta porque no vive en
    esa columna --va adentro de la casilla-- y el mas largo de todos es uno de
    esos, de 56 caracteres: contarlo empujaria todos los campos del panel
    contra el borde derecho por un rotulo que ni siquiera esta ahi.
    """
    if bloque is None:
        bloque = [item for tabla in TABLAS for item in tabla]
    salida = []
    for item in bloque:
        if isinstance(item, Campo):
            salida.append(item)
        elif isinstance(item, (Seccion, Fila)):
            salida.extend(campos(item.hijos))
    return salida


def catalogo(bloque=None, seccion: str = "") -> list[dict]:
    """Cada ajuste con lo que hace falta para encontrarlo y explicarlo.

    Devuelve `[{clave, etiqueta, seccion, ayuda, opciones}]`. Sale del MISMO
    arbol que dibuja el panel, asi que no puede desfasarse de lo que el usuario
    ve -- que es toda la razon de que el registro exista.

    La `ayuda` se toma del `Ayuda` que viene JUSTO DESPUES del control, que es
    como estan escritas: el texto explica la fila de arriba. Sin esa regla habria
    que anotar a mano cual ayuda es de cual, y anotar a mano es lo que se
    desfasa.
    """
    if bloque is None:
        bloque = [item for tabla in TABLAS for item in tabla]
    salida: list[dict] = []
    ultimo: dict | None = None
    for item in bloque:
        if isinstance(item, Seccion):
            salida.extend(catalogo(item.hijos, item.titulo))
            ultimo = None
        elif isinstance(item, Fila):
            salida.extend(catalogo(item.hijos, seccion))
            ultimo = None
        elif isinstance(item, (Campo, Interruptor)):
            ultimo = {"clave": item.clave, "etiqueta": item.etiqueta,
                      "seccion": seccion, "ayuda": "",
                      # Un `str` es el NOMBRE de un metodo del panel y no la
                      # lista: esas se arman al abrir --las voces salen de
                      # consultar el sistema-- asi que aca no hay lista que
                      # dar. Devolverlo dejaba las opciones deletreadas letra
                      # por letra.
                      "opciones": (None
                                   if isinstance(getattr(item, "opciones", None), str)
                                   else getattr(item, "opciones", None))}
            salida.append(ultimo)
        elif isinstance(item, Colores):
            # Ocho por prefijo, con el rotulo de su rol. Sin esto, un tercio de
            # los ajustes del tema no se pueden encontrar por nombre.
            for rol, etiqueta in ROLES_ETIQUETA:
                salida.append({"clave": f"{item.prefijo}_color_{rol}",
                               "etiqueta": f"{etiqueta} (color)",
                               "seccion": seccion, "ayuda": "",
                               "opciones": None})
            ultimo = None
        elif isinstance(item, Fondo):
            for sufijo, etiqueta in _PARTES_FONDO:
                salida.append({"clave": f"{item.prefijo}{sufijo}",
                               "etiqueta": etiqueta,
                               "seccion": seccion or item.titulo, "ayuda": "",
                               "opciones": None})
            ultimo = None
        elif isinstance(item, Ayuda) and ultimo is not None:
            # Solo la primera: varias `Ayuda` seguidas suelen ser parrafos del
            # mismo texto, y pegarlos todos devuelve media pantalla por ajuste.
            if not ultimo["ayuda"]:
                ultimo["ayuda"] = item.texto
        else:
            ultimo = None
    return salida


def esquema() -> dict:
    """Todo TABLAS a un dict serializable, listo para dibujar en cualquier lado.

    `json.dumps` sobre un NamedTuple lo saca como array y pierde el nombre de
    la clase --un Campo y un Interruptor de dos campos salen indistinguibles--
    asi que cada nodo lleva `tipo` = type(x).__name__. Es la pieza que le
    falta al registro para que el panel HTML use la MISMA descripcion en vez
    de llevar su propia copia de los campos: hoy solo esta `catalogo()`, que
    es plano y esta pensado para buscar, no para dibujar --no lleva `ancho`,
    `abierto`, ni la jerarquia de secciones y filas.

    Las claves del dict son los mismos nombres que ya usa `gui.py` para pedir
    cada pestaña por separado (`registro.VOZ`, `registro.CARTEL`...), asi que
    no hay que inventar una agrupacion nueva.
    """
    return {nombre: [_nodo(item) for item in tabla]
            for nombre, tabla in POR_NOMBRE.items()}


def _nodo(item) -> dict:
    """Un objeto del registro a dict, recursivo en `hijos`.

    Los `Propio` viajan enteros --`metodo` y `claves_propias`-- y no se
    expanden ni se omiten: son el hueco declarado que el frontend rellena con
    un componente propio, igual que hoy lo rellena un metodo de tkinter.

    `Campo.opciones` como texto es el NOMBRE de un metodo del panel que arma
    la lista al abrir --las voces de Windows, los modelos del proveedor--.
    `catalogo()` lo pisa con `None` a proposito porque esta pensado para
    buscar; aca en cambio se envuelve en `{"metodo": ...}` para que el que
    dibuja sepa que tiene que PEDIRLAS, en vez de leerlo como una opcion mas.
    """
    salida = {"tipo": type(item).__name__}
    for campo, valor in zip(item._fields, item):
        if campo == "hijos":
            valor = [_nodo(hijo) for hijo in valor]
        elif campo == "opciones" and isinstance(valor, str):
            valor = {"metodo": valor}
        salida[campo] = valor
    return salida


def buscar(consulta: str, excluir=(), tope: int = 8) -> list[dict]:
    """Los ajustes que coinciden con lo que se pregunto, mejor primero.

    Existe para que Eve deje de ADIVINAR nombres de clave. Puede escribir 121
    opciones y ninguna viaja en el prompt, asi que hoy prueba un nombre,
    `ajustar` contesta "No existe la opcion X", y reintenta. Ese ciclo es el
    gasto que este plan viene a sacar.

    Se busca en rotulo, clave, seccion y ayuda, porque el usuario no habla en
    nombres de clave: dice "transparencia" y la clave es `hud_opacidad`. La
    ayuda es justamente donde vive esa palabra.

    `excluir` es para las claves que Eve no puede escribir. Ofrecerle una opcion
    frenada seria hacerle gastar una llamada para que le digan que no.

    Lo que este ranking SI garantiza, medido sobre nueve frases dichas como las
    diria una persona: 7 de 9 aciertan en el primer renglon y **9 de 9 caen
    dentro de los seis** que se devuelven. Ese es el criterio que importa y no
    el primer puesto, porque Eve lee los seis con su rotulo, su valor de ahora
    y sus opciones: con eso elige. Las dos que no salen primeras son del mismo
    tipo --"ponete en modo ruido" y "que el cartel se vea siempre"-- donde la
    palabra que nombra el concepto ("modo", "cartel") aparece literal en el
    NOMBRE de otras claves, y el nombre pesa 25. Subirle el peso a las opciones
    no las arregla; se probo con 4 y salio igual. Se deja asi: afinar mas seria
    pelearse con un caso a costa del resto.
    """
    palabras = [p for p in _normalizar(consulta).split()
                if len(p) > 2 and p not in VACIAS]
    # Cada palabra suma la suya y las que el panel usa para lo mismo. Sin esto,
    # "poneme el cartel mas transparente" no encontraba `hud_opacidad`.
    for palabra in list(palabras):
        palabras.extend(SINONIMOS.get(palabra, "").split())
    if not palabras:
        return []
    fuera = set(excluir)
    puntuadas = []
    for entrada in catalogo():
        if entrada["clave"] in fuera:
            continue
        campos = ((_normalizar(entrada["clave"]), 6),
                  (_normalizar(entrada["etiqueta"]), 5),
                  (_normalizar(entrada["seccion"]), 2),
                  # Los VALORES que acepta, porque la gente nombra el valor y
                  # no el ajuste: "que el cartel se vea siempre" no dice
                  # `overlay_modo` ni "Cuando se ve", dice `siempre`, que es
                  # una de sus opciones. Pesa poco --hay muchas listas con
                  # `siempre`-- pero sin esto no entraba ni entre las seis.
                  (_normalizar(" ".join(str(o) for o in (entrada["opciones"] or ()))), 2),
                  (_normalizar(entrada["ayuda"]), 1))
        punto = 0
        tocadas = 0
        en_nombre = 0
        for palabra in palabras:
            mejor = 0
            nombrada = False
            for i, (texto, peso) in enumerate(campos):
                if palabra in texto:
                    # Palabra entera vale mas que pedazo: buscando "voz" no
                    # tiene que ganar "vozarron" sobre el ajuste que se llama voz.
                    mejor = max(mejor, peso * (2 if f" {palabra} " in f" {texto} " else 1))
                    if i < 2:            # clave o etiqueta, no seccion ni ayuda
                        # UNA vez por palabra, aunque este en la clave Y en la
                        # etiqueta. Contando las dos, `hud_fondo_opacidad`
                        # --que dice "opacidad" en las dos-- le ganaba a
                        # `hud_opacidad` en "transparencia del cartel": el que
                        # se repite no es mas relevante, es mas largo.
                        nombrada = True
            if mejor:
                tocadas += 1
                punto += mejor
                en_nombre += 1 if nombrada else 0
        if not tocadas:
            continue
        # Que coincidan TODAS las palabras pesa mas que coincidir mucho con una.
        punto += tocadas * 10
        # Y coincidir en el NOMBRE pesa mas que coincidir en la ayuda. Sin esto
        # ganaba siempre el ajuste con la ayuda mas larga: `perfil_reglas`
        # explica horarios y programas, asi que se llevaba "cambiar la tecla" y
        # "que no me escuche de noche" por encima de `hotkey` y `stt_horario`.
        punto += en_nombre * 25
        puntuadas.append((punto, entrada))
    puntuadas.sort(key=lambda par: -par[0])
    return [entrada for _punto, entrada in puntuadas[:tope]]


def _normalizar(texto: str) -> str:
    """Minusculas y sin acentos: se busca por lo que se dice, no por como se
    escribe. Quien pregunta por "opacidad" no tiene por que poner la tilde."""
    import unicodedata

    sin = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in sin if unicodedata.category(c) != "Mn")
