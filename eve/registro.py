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
            Campo("hud_tema", "Tema del cartel", "_temas_del_cartel"),
            Colores("hud"),
            Ayuda("Vacio = el cartel usa el mismo tema que el panel, que es lo que\n"
                  "quiere casi todo el mundo. Los colores de abajo solo se usan con\n"
                  "el tema 'personalizado'."),
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


# Todas las tablas migradas. Va al final porque nombra las de arriba, y existe
# para que el chequeo de traduccion las recorra sin que nadie tenga que
# acordarse de sumar cada pestaña nueva a mano.
TABLAS = (SUBTITULOS, VENTANA, VOZ, TEMA)
