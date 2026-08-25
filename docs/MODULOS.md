# Módulos y assets

Guía para armar la cara de Eve sin escribir una línea de código.

Esto es la referencia práctica. El **por qué** de cada decisión está en el
[README](../README.md); acá está el **cómo**.

---

## Qué es un módulo

Una pieza que se dibuja: un icono, una onda que reacciona a tu voz, un reloj, el
texto de lo que Eve está diciendo, un documento, un botón.

Un módulo **no es una ventana**. Es una fila de datos —dónde va, de qué tamaño,
con cuánta transparencia— más una función que dibuja. Por eso el mismo módulo
sirve en las tres superficies sin tres implementaciones.

### Las tres superficies

| | Qué es | Cómo se llega |
|---|---|---|
| **Cartel** (`overlay`) | La tarjeta flotante sobre el escritorio. Deja pasar los clics | Apariencia → Cartel |
| **Tablero** (`tablero`) | La ventana de actividad, donde Eve muestra lo que hace | El botón **Ventana de actividad** del pie del panel |
| **Panel** | Donde se configuran todos | El icono de la bandeja |

Cada módulo elige su superficie con la prop `superficie`. El mismo tipo puede
estar en las dos a la vez, con tamaños distintos.

---

## Agregar un módulo

Hay dos caminos, y los dos sirven.

### Desde el panel

**Apariencia → Módulos**, y arriba de la lista:

    [ tipo ▾ ]  en  [ tablero ▾ ]  [ Agregar ]

**Elegí dónde antes de agregar.** `tablero` es la ventana de actividad y
`cartel` es la tarjeta flotante sobre el escritorio. De fábrica va al tablero.

El formulario de propiedades **se genera solo** a partir del tipo: no hay una
pantalla distinta por cada uno, así que un tipo nuevo trae sus controles puesto.

### Desde la propia ventana de actividad

Abrila con el botón **Ventana de actividad** del pie del panel, pasá a **Edit**,
y usá el **Agregar** de ahí. Ese siempre pone el módulo en el tablero, porque es
donde estás mirando.

Si la abrís y está vacía, te lo dice y trae un botón para armar un tablero de
arranque.

> **Si agregaste uno y no aparece**, casi siempre es una de dos: quedó en el
> `cartel` en vez del tablero —fijate la columna en la lista de módulos— o el
> cartel está en `auto`, que lo esconde hasta que Eve trabaja.

Para acomodarlos con el mouse: **ventana de actividad → Edit**.

| En Edit | |
|---|---|
| Clic | Elegir |
| Ctrl + clic | Sumar a la selección |
| Shift + clic | Agregar un rango |
| Arrastrar | Mover |
| `Ctrl+Z` | Deshacer (20 pasos) |
| `Supr` | Borrar |

Con varios elegidos se editan **las propiedades que tienen en común**. Agrupar
una onda con unas partículas te deja cambiar la opacidad de las dos —lo único
que comparten— y no te ofrece `estilo`, que es solo de la onda. Si el valor
difiere entre los elegidos, el campo arranca vacío: así aplicar no los iguala
sin querer.

---

## Los trece tipos

### Los que muestran estado

| Tipo | Qué muestra | Props propias |
|---|---|---|
| `texto` | Un texto fijo, el nombre de Eve, lo que dijiste vos, o lo que responde | `contenido`, `origen`, `tam` |
| `reloj` | La hora | `formato` (como en `strftime`: `%H:%M`) |
| `contexto` | Cuánto del presupuesto de tokens se lleva cada parte del prompt | `detalle` (`barra` o `numeros`) |
| `grafo` | Qué ejecutó Eve y en qué proyectos, sacado del log de auditoría | `cuantas`, `etiquetas` |
| `historial` | La conversación | `tam`, `lineas`, `cuantos` |
| `acciones` | El log de auditoría: qué corrió y cómo salió | `tam`, `lineas`, `cuantas`, `resultado` |

`origen` del texto: `fijo` (lo que escribas en `contenido`), `nombre`, `detalle`
(en qué anda), `usuario` (lo que dijiste), `eve` (lo que responde).

### Los que muestran contenido

| Tipo | Qué muestra | Props propias |
|---|---|---|
| `documento` | Lo que Eve te muestra con "muéstrame tal cosa" | `tam`, `lineas`, `titulo`, `desplazar` |
| `lector` | El texto de la última página que le pediste leer | `tam`, `lineas` |

### Los que se dibujan

| Tipo | Qué es | Props propias |
|---|---|---|
| `icono` | Una imagen o un marco paramétrico | `imagen`, `lados`, `redondeo` |
| `onda` | La forma de onda de tu voz | `estilo` (`barras`/`espejo`/`linea`/`puntos`), `muestras` |
| `particulas` | Partículas simuladas | `cantidad`, `vida`, `gravedad` |
| `lottie` | Animación vectorial de After Effects | `archivo`, `cuadro` |

### El que hace algo

| Tipo | Qué es | Props propias |
|---|---|---|
| `boton` | Dispara una acción al tocarlo, en modo Work | `accion`, `etiqueta`, `tam` |

Las acciones son una **lista cerrada**: `panel`, `cartel`, `escuchar`, `hablar`.
Ninguna borra nada. Un módulo que corriera cualquier comando sería un addon sin
el freno de los addons, y "limpiar historial" a un clic de distancia en un
tablero es un accidente esperando.

Un botón nace **interactivo**: uno que hubiera que habilitar con una casilla para
que responda al clic no sería un botón.

---

## Las propiedades que tienen todos

### Dónde y de qué tamaño

`x`, `y`, `ancho`, `alto` en píxeles · `z` (más alto se dibuja encima) ·
`pantalla` (0 = donde lo dejes; 1 en adelante lo fija a ese monitor).

### Cuándo se ve

`cuando` = `siempre` | `trabajando` | `hover`.

Un reloj o el medidor conviene dejarlos fijos; la onda que aparezca solo al
hablar.

### Si recibe clics

`interactivo`. **Lo que no es interactivo deja pasar el clic**, igual que el
cartel deja pasar los clics al programa de atrás. Por eso un botón debajo de un
documento grande se puede tocar igual.

### Cómo se ve

`opacidad` (0-100) · `escala` (%) · `rotacion` (grados) · `tinte` (un color que
se mezcla) · `color` (qué rol de la paleta usa: `texto`, `acento`, `alerta`…).

> Las opacidades **se multiplican**: 20% de ventana por 20% de módulo da 4% de
> verdad.

### Cómo se anima

`velocidad` (multiplicador) · `easing` (`lineal` | `suave` | `rebote`).

Y la que separa una animación de un adorno:

**`fuente`** = `reloj` | `microfono`.

Con `microfono`, el módulo **late con tu voz**. Vale para cualquier tipo: un GIF,
un sprite sheet, un reloj, un PNG quieto. Es lo que separa "tiene animaciones" de
"reacciona a lo que decís".

---

## Assets: qué formatos entran y cómo se hacen

Todo lo que sigue se importa **eligiendo un archivo en el panel**. No hay que
tocar código ni convertir nada a un formato propio.

### Imágenes y animación por cuadros

| Formato | Para qué | Con qué se hace |
|---|---|---|
| **PNG** | Iconos, fondos | Cualquier editor |
| **GIF** | Animación simple | Aseprite, ezgif |
| **APNG** | Animación con **alpha de 8 bits** y color de 24 | Aseprite, ezgif |
| **WebP animado** | Igual que APNG, archivo más chico | ezgif, Photoshop |
| **JPG / BMP** | Fondos sin transparencia | Cualquiera |

> **Preferí APNG o WebP sobre GIF.** El GIF tiene 256 colores y transparencia de
> un bit: un borde suave sobre el escritorio te queda dentado. APNG y WebP no.

Se animan solos. La velocidad de reproducción sale del propio archivo, y
`velocidad` la multiplica.

### Sprite sheets

Un PNG con todos los cuadros pegados y un `.json` al lado que dice dónde está
cada uno.

**Cómo hacerlo:** Aseprite (`Archivo → Exportar hoja de sprites`, marcando
*Output JSON data*) o TexturePacker.

**Cómo usarlo:** dejá los dos archivos **en la misma carpeta y con el mismo
nombre** (`nave.png` + `nave.json`), y elegí el PNG. Si el JSON está, se usa.

Se aceptan los dos modos de exportación (lista o diccionario): elegir el modo
equivocado en el exportador no es culpa tuya.

### Partículas

No se importan cuadros: se importa la **configuración**, y la corre el simulador
que ya está adentro de Eve. Por eso no entra ninguna librería nueva.

**Cómo hacerlo:** [Particle2dx](https://www.particle2dx.com/) (web, gratis) o
Particle Designer. Exportá el `.plist` de cocos2d.

**Cómo usarlo:** Módulos → un módulo de tipo `particulas` → **Importar .plist**.
Llena los campos de arriba; después **Aplicar**.

> **Lo que no viaja:** modo radial, texturas por partícula y mezclas aditivas.
> El simulador no las hace, y se prefiere no importarlas a importarlas mal.

### Animación vectorial (Lottie)

Escala sin pixelarse y pasa el tope de 60 cuadros de un GIF.

**Cómo hacerlo:** After Effects + [Bodymovin](https://aescripts.com/bodymovin/),
o bajar una de [LottieFiles](https://lottiefiles.com/) (hay miles gratis).

**Cómo usarlo:** módulo de tipo `lottie`, y en `archivo` la ruta al `.json`.
`cuadro` = `-1` lo anima; `0` o más lo deja fijo en ese cuadro.

Cuesta 0.22 ms por cuadro a 200×200, así que podés tener varios sin que se note.

### Fondos

Cada módulo puede tener su propio fondo: imagen con ajuste, opacidad, tinte con
el acento, o un degradado de dos colores si no hay imagen.

La opacidad del fondo **se mezcla en la imagen y no en la ventana**, así que
bajarla atenúa el fondo pero el texto sigue entero.

---

## Dónde vive todo

```
%APPDATA%\LLMJarvis\          (Windows)
~/.config/LLMJarvis/          (Linux)
~/Library/Application Support/LLMJarvis/   (macOS)
```

| | |
|---|---|
| `config.json` | Todos los ajustes, incluidos los módulos como `mod_<id>_<prop>` |
| `perfiles.json` | Los perfiles guardados |
| `arte/`, `assets/` | Dónde conviene dejar tus imágenes |
| `addons/` | Los `.py` que agregás vos |

Los módulos se guardan en el mismo `config.json` que todo lo demás, con claves
planas tipo `mod_reloj1_x`. Eso les da gratis dos cosas: **entran a los perfiles**
(se exportan y se comparten) y **se aplican en vivo** sin cortarle la
conversación a Eve.

---

## Perfiles: compartir una cara entera

**Panel → General → Perfiles.**

Un perfil guarda cómo se ve y cómo suena Eve: colores, forma, fuente, voz,
velocidad, tono y el nombre del asistente.

**No toca** el motor, el modelo, la tecla, los permisos ni tus datos. Un perfil
que te pasan no puede cambiarte cómo trabaja el asistente ni llevarse tus claves.

`Exportar` genera un `.eveperfil` que podés mandar; el otro lo abre con
`Importar`. Vienen ocho de ejemplo.

---

## Si algo no se ve

| Síntoma | Qué mirar |
|---|---|
| La ventana de actividad está vacía | Te lo dice ella misma, con el botón para armar el tablero |
| El cartel no aparece | **Apariencia → Cartel → Mostrar el cartel**. Si aparece, el problema es `Cuando se ve` |
| Un módulo no se ve | `opacidad` (se multiplica con la de la ventana), `cuando`, y `pantalla` si tenés dos monitores |
| Un botón no responde | Tiene que estar en modo **Work**. En Edit el clic elige, no acciona |
| Va a tirones | **Apariencia → Tema → Fluidez**: bajá `ui_fps` antes que apagar módulos |
