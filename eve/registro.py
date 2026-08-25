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


class Interruptor(NamedTuple):
    """Una casilla. Se separa de `Campo` porque la dibuja `_check` y no `_row`."""

    clave: str
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
        elif isinstance(item, (Campo, Interruptor, Boton)):
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
                  "hora; las reglas y los numeros medidos estan en el ajuste fino."),
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
        "Despertarla diciendo su nombre",
        (
            Interruptor("wake_activo",
                        "Activar diciendo una palabra (deja el microfono abierto)"),
            Campo("wake_palabra", "Palabra para despertarla", None, 20),
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
                  "variantes separadas por |, y de fabrica vienen las dos."),
        ),
        AVANZADO,
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
            Campo("engine", "Motor", ["api", "claude-code", "ollama", "compat"]),
            Ayuda("  api = Messages API, necesita tu ANTHROPIC_API_KEY.\n"
                  "  claude-code = CLI de Claude Code, usa tu suscripcion sin key (mas lento).\n"
                  "  ollama = modelo local, sin key ni nube. Peor encadenando varias tools.\n"
                  "  compat = cualquier servidor que hable el protocolo de OpenAI."),
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
            Campo("compat_proveedor", "compat: proveedor", "_proveedores_compat"),
            Campo("compat_modelo", "compat: modelo"),
            Campo("compat_url", "compat: URL propia", None, 40),
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
            Ayuda("'Permitir todo' desactiva la confirmacion y tambien los permisos internos\n"
                  "de Claude Code. Todo queda igual registrado en la pestaña Acciones."),
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
                  "Con 'nada' el prompt tampoco lleva el vocabulario de modulos, que\n"
                  "son ~190 tokens por llamada."),
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
                  ["ninguno", "linea", "esquinas", "doble", "hexagonal", "biselado"]),
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
TABLAS = (SUBTITULOS, VENTANA, VOZ, TEMA, GENERAL, CARTEL)
