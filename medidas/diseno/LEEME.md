# Las nueve pestañas dibujadas

Esto es contra lo que se mide el éxito del proyecto. El acuerdo
(`handshake_eve.md`) lo dice con palabras del usuario: **el dolor principal es
cómo se ve el panel**, y el éxito se mide comparando capturas contra el diseño.
Por eso las nueve se dibujan **antes** de escribir una línea de panel: corregir
sobre el dibujo es barato, corregir sobre el código no.

## Por qué las capturas viven acá y los dibujos no

`.gitignore:29` ignora `*.dc.html`. Los artboards son borradores y nunca llegan
al repo: viven solo en el disco de esta máquina. **Las capturas son lo único que
sobrevive**, así que van acá adentro, que sí se versiona.

## El juego

| # | Pestaña | Artboard | Capturas | Estado |
|---|---|---|---|---|
| 1 | General | `General.dc.html` | `general-*.png` | Fiel |
| 2 | Modelos y claves | `Modelos.dc.html` | `modelos-*.png` | Fiel |
| 3 | Cuentas | `Cuentas.dc.html` | `cuentas-*.png` | Fiel |
| 4 | Comandos | `Comandos.dc.html` | `comandos-*.png` | Fiel, rehecho |
| 5 | Voz | `Voz.dc.html` | `voz-*.png` | Fiel |
| 6 | Contactos | `Contactos.dc.html` | `contactos-*.png` | Fiel |
| 7 | Addons | `Addons.dc.html` | `addons-*.png` | Fiel |
| 8 | Apariencia | `Apariencia.dc.html` | `apariencia-*.png` | Fiel, corregido · **cinco capturas más, ver abajo** |
| 9 | Actividad | `Actividad.dc.html` | `actividad-*.png` | Fiel |

Cada una en las dos paletas, clara y oscura, porque el programa entrega las dos.

## `Main.dc.html` está RETIRADO. No lo uses.

Sigue en la carpeta y **no corresponde a ninguna pestaña**. Está rotulado
"Cuentas" y dibuja la sección "Quien piensa por ella", que hoy vive en **Modelos
y claves**; y la pestaña Cuentas de hoy es otra cosa (webhook de Discord,
SteamID, Gmail, Outlook). Es un estado intermedio de una refactorización vieja,
congelado a mitad de camino.

Se descubrió tarde y de la peor forma: se contaron nueve archivos `.dc.html` y
se dio por hecho que eran nueve pestañas, sin abrir ninguno. **General no estaba
dibujada** y nadie lo había notado. Queda anotado acá porque el mismo descuido
se puede repetir: en esta carpeta, contar archivos no es verificar.

Lo que `Main.dc.html` dibujaba está cubierto, y mejor, por `Modelos.dc.html`.

## Comandos se rehizo, y por qué

El dibujo viejo mostraba un maestro-detalle que **no existe** en el panel, le
faltaban los botones Editar, Borrar y Recargar y la columna Estado, y no
reflejaba los dos cambios que importan: que **Probar** abre una ventana con la
salida completa, el código de retorno y la duración; y que **aprobar dejó de ser
un cuadro del sistema**.

El artboard nuevo muestra el panel de aprobación **desplegado**, a propósito. Es
el punto del cambio: el cuadro del sistema recortaba el texto largo sin decirlo
—y lo que se aprueba ES el texto—, no dejaba copiarlo y tapaba la lista. En la
captura se ve el comando entero, que en la lista de arriba aparece cortado.

## La regla que hace que esto sirva

**Cada rótulo, botón y texto de ayuda es el literal del código.** No una versión
mejorada. Si el diseño dice algo distinto de lo que dice el panel, el diseño
miente, y como el éxito se mide contra el diseño, el error se arrastra a la
implementación.

Eso obliga a dibujar cosas que se ven "mal" y están bien:

- En **Voz**, las columnas del catálogo dicen `key`, `calidad`, `mb`, `estado`
  en minúscula y sin traducir, porque el código las dibuja con el nombre de la
  columna tal cual.
- En **Contactos**, los campos del formulario son `nombre`, `alias`,
  `discord_user`, `discord_dm`, por lo mismo.
- En **Actividad**, las columnas son `hora`, `tool`, `detalle`, `resultado`.
- Varios textos van **sin tilde** ("Que espanol habla"), que es como el panel los
  muestra hoy.

Y obliga a leer el lugar correcto: **Cuentas, Contactos y Actividad no salen de
`registro.py`**, están escritas a mano en `gui.py`. Buscar sus rótulos en el
registro no da nada, y ahí es donde se empieza a inventar.

Un caso que sí hay que saber: **`registro.VOZ` en tiempo de ejecución no es lo
que dice su tupla literal.** `_partir` se lleva "Como te escucha", "Como te
habla" y "Despertarla diciendo su nombre" a la pestaña Modelos, aunque en el
código sigan escritas dentro de `VOZ`. El dibujo de Voz muestra lo que el panel
pinta, no lo que el archivo parece decir.

## Apariencia tiene cinco capturas más, y hay que saber por qué

Es la única pestaña con **sub-pestañas**: Tema, Cartel, Ventana, Modulos y
Subtitulos. Las dos capturas oficiales muestran solo **Tema, en modo "Lo
esencial"**, que es el estado por defecto.

Eso alcanzaba hasta que se corrigieron los desajustes de abajo, y ahí apareció
el problema: **todo lo corregido quedaba fuera de cuadro.** Los roles de color
viven en una sección avanzada que está plegada; el bloque de Fondo está en
Cartel; y Modulos, que se rehizo entera, es otra sub-pestaña. Las dos capturas
oficiales pesaban **exactamente los mismos bytes que antes de corregir**, y eso
fue lo que delató que no mostraban nada de lo cambiado.

Por eso hay cinco capturas más, **solo en tema oscuro**: acá lo que se verifica
es el CONTENIDO, no los colores, y las dos paletas ya están cubiertas por las
oficiales.

| Captura | Qué hay que poder ver ahí |
|---|---|
| `apariencia-tema-todo-oscuro.png` | Los ocho roles con su nombre real, en modo "Todo" |
| `apariencia-cartel-oscuro.png` | El bloque de Fondo con sus siete etiquetas |
| `apariencia-ventana-oscuro.png` | Los dos botones |
| `apariencia-modulos-oscuro.png` | **La más importante**: se rehizo entera |
| `apariencia-subtitulos-oscuro.png` | El bloque de Fondo de los subtítulos |

## Apariencia: los desajustes que TENÍA, y ya están corregidos

Se detectaron revisándola contra el código y se arreglaron. Quedan escritos
porque son el catálogo de cómo un diseño se despega del producto:

- **Los roles de color usan nombres genéricos.** El dibujo dice `panel`,
  `texto tenue`, `acento apagado`; los de verdad, en `ROLES_ETIQUETA`, son
  **"Cajas y campos"**, "Texto secundario", "Acento apagado", "Contorno".
- **Rótulos truncados o parafraseados**: "Tema (vacio = panel)" donde el literal
  es "Tema (vacio = el del panel)"; "Titulo" donde es "Titulo (vacio = nombre
  IA)"; "Tamano" sin la ñ.
- **El bloque de Fondo** usa siete etiquetas que no existen. Las reales están en
  `gui.py::_bloque_fondo`: "Imagen (PNG o GIF)", "Ajuste", "Opacidad de la
  imagen (%)", "Tinte con el acento (%)", "Degradado (si no hay imagen)",
  "Degradado: color 1", "Degradado: color 2".
- **La sub-pestaña Módulos era la más floja.** Inventaba una interacción y le
  ponía nombres bonitos a las propiedades (`Posicion x`, `Escala`) cuando el
  panel real muestra **la clave cruda sin capitalizar** (`x`, `escala`), porque
  `_mods_props` dibuja la etiqueta con el nombre de la propiedad tal cual. Y le
  faltaban los controles reales: los combos de tipo y destino, y los botones de
  agregar, duplicar, borrar, traer los del cartel y armar el tablero. Se rehizo
  entera, con las **18 propiedades crudas** y los seis botones.

## Y un bug del CÓDIGO que salió al corregir el dibujo

Corrigiendo el bloque de Fondo se encontró que **`registro._PARTES_FONDO` estaba
desfasado de `gui.py::_bloque_fondo`**, los siete rótulos. El comentario de esa
tabla decía que salían de ahí y hacía rato que no era cierto.

No era cosmético: esa tabla alimenta `catalogo()`, que es lo que usan **el
buscador del panel** y **`E ajustar`** (Eve cambiando una opción porque se lo
pediste hablando). Medido antes del arreglo:

```
buscar("Opacidad de la imagen") -> "Opacidad (%)", "Imagen de fondo"
buscar("Degradado: color 1")    -> "Degradado: color de arriba"
```

Buscabas un rótulo que estabas viendo en pantalla y te llevaba a otro ajuste.
Arreglado, con un test que compara contra los `tr(...)` de `_bloque_fondo` en
vez de contra una lista escrita a mano, que es justo lo que se había desfasado.

## Cómo se sacaron las capturas

Sin publicar nada online y sin tocar git. Se evalúa `Component.renderVals()` del
artboard con Node para obtener las dos paletas, se resuelven `{{holes}}`,
`sc-for` y `sc-if` sobre el bloque `<x-dc>`, y se fotografía con un navegador
headless, recortando al tamaño real del artboard.

Los colores no se inventan: salen de `eve/tema.py`, las mismas paletas que ya
comparten el panel, el cartel y la ventana de actividad.

## Los datos de ejemplo son inventados

Nada real del usuario. Los contactos son "Juan Perez" y "Ana Gomez" en
`example.com`; las frases del historial y las filas de acciones están escritas
para el dibujo. La agenda y el historial reales no se leen ni se muestran: el
diseño se mira y se comparte, esos datos no.

En **Actividad** los ejemplos incluyen **dos filas denegadas** a propósito. Esa
tabla existe para mostrar qué ejecutó Eve y **qué frenó el usuario**; llenarla
solo de operaciones exitosas vendería una idea equivocada de para qué está.
