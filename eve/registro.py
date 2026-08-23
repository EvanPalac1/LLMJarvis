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


class Campo(NamedTuple):
    """Una fila: etiqueta, clave de config y opciones si son cerradas."""

    clave: str
    etiqueta: str
    opciones: list | None = None
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
    """

    metodo: str


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
        elif isinstance(item, (Campo, Interruptor, Boton)):
            salida.append(item.etiqueta)
        elif isinstance(item, Ayuda):
            salida.append(item.texto)
        elif isinstance(item, Fondo):
            salida.append(item.titulo)
    return salida


def claves(bloque) -> list:
    """Todas las claves de config que toca un bloque del registro.

    Sirve para comprobar, sin abrir una ventana, que la version generada cubre
    exactamente lo mismo que la escrita a mano. `Fondo` aporta las suyas por
    prefijo, que es como las nombra `_bloque_fondo`.
    """
    salida = []
    for item in bloque:
        if isinstance(item, Seccion):
            salida.extend(claves(item.hijos))
        elif isinstance(item, (Campo, Interruptor)):
            salida.append(item.clave)
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



# Todas las tablas migradas. Va al final porque nombra las de arriba, y existe
# para que el chequeo de traduccion las recorra sin que nadie tenga que
# acordarse de sumar cada pestaña nueva a mano.
TABLAS = (SUBTITULOS,)
