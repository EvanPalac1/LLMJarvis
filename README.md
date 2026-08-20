# LLMJarvis

Asistente de voz local. Manten presionada una tecla, habla, y la IA ejecuta la
instruccion en tu PC: abrir programas, crear archivos, correr comandos, escribir mensajes.

La IA se llama **Eve** (Ivi) por defecto — el nombre se cambia desde el panel.

**Tres motores a elegir**, incluido uno 100% local:

| Motor | Necesita | Datos |
|---|---|---|
| `ollama` | Ollama corriendo | **nada sale de tu maquina** |
| `claude-code` | suscripcion de Claude | van a Anthropic |
| `api` | API key de Anthropic | van a Anthropic |

**Voz de entrada y salida tambien offline**: Whisper local para escuchar, y voces de
la comunidad (Piper) para hablar. Con el motor `ollama`, Eve funciona sin internet.

| | Windows | macOS | Linux |
|---|---|---|---|
| Voz, motores, panel, bandeja, atajo | si | si | si |
| Abrir programas y juegos | si | si | si |
| Outlook, WhatsApp, Discord | si | no | no |

Las integraciones de Windows avisan "solo funciona en Windows" en el resto en vez de
romper. **macOS y Linux no estan probados en hardware real**: el codigo elige los caminos
correctos y los tests lo verifican simulando el sistema, pero nadie lo corrio ahi todavia.

---

## Instalacion

Descarga el paquete de tu sistema desde
[Releases](https://github.com/EvanPalac1/LLMJarvis/releases). **Traen Python y todas
las dependencias adentro**: no hace falta instalar nada mas.

| Sistema | Archivo | Se desinstala desde |
|---|---|---|
| Windows | `Eve-Setup-x64.exe` / `-arm64.exe` | Agregar o quitar programas |
| macOS | `Eve-AppleSilicon.dmg` / `Eve-Intel.dmg` | arrastrar a la Papelera |
| Debian, Ubuntu | `eve_*_amd64.deb` / `_arm64.deb` | `apt remove eve` |
| Fedora, RHEL | `eve-*.x86_64.rpm` / `.aarch64.rpm` | `dnf remove eve` |

El instalador de Windows pregunta por el motor de IA, la tecla para hablar, si arrancar
con Windows, y si bajar el modelo de voz y una voz en espanol durante la instalacion o
dejarlo para el primer uso. Al desinstalar **pregunta si borrar tambien tus datos**
(agenda, memoria, historial y voces) en vez de decidir por vos.

**No estan firmados digitalmente.** Windows muestra SmartScreen (*Mas informacion >
Ejecutar de todas formas*) y macOS pide abrirlo la primera vez con boton derecho > Abrir.
Firmar requiere un certificado pago.

### Donde queda cada cosa

| | Programa | Tus datos |
|---|---|---|
| Windows | donde lo instales | `%APPDATA%\LLMJarvis` |
| macOS | `/Applications/Eve.app` | `~/Library/Application Support/LLMJarvis` |
| Linux | `/opt/LLMJarvis` | `~/.config/LLMJarvis` |

Estan separados a proposito: desinstalar y reinstalar no borra la agenda ni la memoria.
Si venias de una version que corria desde el codigo, los datos se migran solos.

### Desde el codigo

```bash
pip install -r requirements.txt
python main.py            # asistente
python main.py --panel    # configuracion
python main.py --check       # diagnostico
python main.py --probar-voz  # autotest: sintetiza una frase y la transcribe
python main.py --actualizar  # busca una version nueva (--instalar para aplicarla)
```

### Actualizaciones

Eve avisa cuando hay una version nueva y se actualiza sola desde
[Releases](https://github.com/EvanPalac1/LLMJarvis/releases): bandeja >
**Buscar actualizaciones**, o el mismo boton en el panel.

Descargar y ejecutar un instalador merece cuidado, asi que el camino esta cerrado:

- Solo el repositorio oficial y solo por HTTPS; el repo no se lee de la config.
- **Se verifica el sha256** que publica la API de GitHub para cada archivo. Si no
  coincide, se borra y no se ejecuta nada.
- **Nunca instala solo**: busca, avisa, y decidis vos.
- Actualiza encima conservando tu configuracion, agenda, memoria y voces, porque
  viven en otra carpeta.

Corriendo desde el codigo no se actualiza: ahi es `git pull`.

### Armar los paquetes

```bash
pip install pyinstaller
python build.py --paquete
```

Arma lo del sistema donde lo corras: en Windows necesita
[Inno Setup](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`),
en Linux `dpkg-deb` y `rpmbuild`.

**PyInstaller no cross-compila**: cada paquete se arma en su sistema y arquitectura.
Los seis salen de `.github/workflows/release.yml`, que corre al empujar un tag `v*`.

### Que hace falta para hablarle

Una de estas tres:

- **[Ollama](https://ollama.com)** corriendo con un modelo que soporte tools
  (`ollama pull qwen3:8b`). Gratis, offline, sin cuenta.
- **Suscripcion de Claude (Pro/Max)** con [Claude Code](https://claude.com/claude-code)
  instalado y logueado. Sin API key, sin tarjeta.
- **API key de Anthropic**, que se carga en el panel (pestana Claves).

### Los ultimos dos pasos

```bash
python main.py --check --tecla
```

Presiona el boton de tu keypad: te dice que manda. Copialo al campo **Tecla del keypad**
del panel. El default es `f13` porque ningun otro programa lo usa.

Despues abri Eve. Aparece en la bandeja del sistema. Manten presionada la tecla, habla, solta.

---

## Uso

- **Clic izquierdo en el icono** → abre el panel de configuracion.
- **Clic derecho** → reiniciar listener / pausar / salir.
- El boton del keypad nunca abre el panel: son cosas independientes.

### Cuatro procesos, una señal

El listener, el cartel, el panel y la ventana de actividad son procesos separados: el
icono los lanza aparte, asi que si uno se cuelga los demas siguen andando. No es prolijidad
gratuita: `icon.run()` de pystray se queda con el hilo principal, y tkinter y pystray no
comparten mainloop sin dolor.

Al guardar, **el listener se rearma solo en unos segundos**. No hace falta tocar nada:
vigila el `mtime` de `config.json` en un hilo, y el archivo que el panel ya escribe *es*
la señal — no hay canal de IPC que mantener. Funciona igual si editas el JSON a mano.

Dos detalles que importan: espera a que el archivo deje de cambiar antes de releer
(guardar no es atomico, y a medio escribir el JSON es invalido), y no recarga mientras hay
un pedido de voz en curso — reintenta cuando termina.

**Reiniciar listener** sigue en el menu de la bandeja para forzarlo a mano.

Cambiar solo cosas de aspecto (colores, contorno, posicion del cartel, los modulos) **no
rearma el motor**: se aplican en caliente y la conversacion sigue. Cambiar el motor, la
tecla o los permisos si lo rearma — pero desde que el hilo vive en la base y no adentro de
cada motor, eso ya no borra la conversacion.

### Se le puede hablar mientras piensa

Apretas, hablas, y si vuelve a hacer falta apretas de nuevo aunque todavia este pensando:
lo que grabes queda en cola y se procesa cuando termine lo anterior. El cartel muestra
cuantas esperan turno.

La cola se atiende de a una a proposito. Dos pedidos a la vez se pisarian el microfono,
los parlantes y el contexto de la conversacion.

### Perfiles

Un perfil guarda **como se ve y como suena** Eve: colores, forma del cartel, fuente, voz,
velocidad de habla, tono de personalidad y el nombre del asistente. Sirve para tener uno
para jugar (cartel siempre visible, voz rapida) y otro para trabajar (cartel discreto,
tono seco).

Lo que un perfil **no** puede tocar, aunque te lo pase otra persona:

| Queda afuera | Por que |
|---|---|
| Motor y modelo | Elegir un tema no tiene por que bajarte de Opus a un modelo local |
| Tecla y permisos | Cargar un tema no puede apagarte el freno de acciones destructivas |
| Mail, Discord, Steam, carpetas | Son tuyos, no del modo de trabajo |
| Posicion del cartel | Es de tu pantalla, no de tu modo |

No es una lista de exclusiones sino al reves: `store.perfilable()` define lo que **si**
entra, asi que una opcion nueva del programa no empieza a viajar dentro de los perfiles
sola. Antes era al reves, y por eso cargar un perfil viejo te devolvia los datos de
contacto que tenias cuando lo guardaste.

Se manejan en **General > Perfiles**, y se cambia sin abrir el panel desde la bandeja
(clic derecho > Perfiles).

**Exportar e importar** deja pasarle un perfil a otra persona (`.eveperfil`). No viajan ni
tus claves de API ni tus datos personales: las claves viven en el gestor de credenciales
del sistema y nunca estuvieron en la config, y el mail, el SteamID y tus carpetas
permitidas se sacan al exportar. Al importar, las claves que este programa no conoce se
descartan en vez de entrar.

Vienen **ocho perfiles de ejemplo** en la carpeta `perfiles/` (y con el programa
instalado, en `perfiles` al lado del ejecutable). El boton **Importar** los abre ahi
directamente.

---

## Velocidad

Todo lo de abajo esta medido en un Ryzen 5 4500, no estimado.

**El sintetizador cargaba su modelo en cada frase.** `PiperVoice.load()` cuesta 2.3s y
sintetizar solo 0.24s: se pagaba diez veces el trabajo util, y eso dejaba a Piper mas lento
que la voz robotica de Windows, que es la razon por la que uno terminaba eligiendo la fea.
Cacheado por voz:

| | antes | ahora |
|---|---|---|
| frase nueva | 2.57s | **0.09s** |
| frase repetida | 2.57s | **0.00s** |
| SAPI (la robotica) | 0.55s | 0.55s |

Piper quedo seis veces mas rapido que la voz de Windows **y** suena mejor. No hay razon
para seguir con SAPI.

**Las frases que Eve repite se guardan en disco.** Dice siempre lo mismo — "Abriendo
Spotify", "Listo", "No te entendi" — asi que el wav se genera una vez y despues se lee.
Cambiar de voz limpia ese cache, o seguirias escuchando la voz vieja en las frases comunes.

**El reconocimiento usa busqueda greedy.** Medido sobre una orden tipica: `beam_size=5`
tarda 4.4s y `beam_size=1` tarda 3.5s **con el mismo texto**. La busqueda por haz sirve
para dictado largo; una orden de ocho palabras no cambia de resultado por explorar cinco
ramas. Se puede subir en el panel si dictas frases largas.

**Los modelos se cargan al arrancar**, no en la primera orden. Son ~2.5s de Whisper y
~2.3s de Piper que antes se pagaban justo cuando el usuario ya estaba esperando.

### Lo que se midio y se descarto

- **Modelos de voz mas chicos.** `tiny` y `base` son 3-5x mas rapidos pero destrozan el
  español: "Abrés Potisi" por "abre Spotify", "a Jera la tarde" por "ayer a la tarde".
  No sirve un asistente rapido que entiende mal.
- **Transcribir mientras hablas.** faster-whisper no tiene API de streaming: procesa el
  buffer entero rellenado a 30s, y transcribir pedazos sueltos garabatea el texto.
- **Buffer circular para no perder la primera palabra.** Medido: el microfono arranca en
  6-21 ms. No hay nada que recuperar.
- **Filtro contra alucinaciones del modelo sobre silencio.** Medido con silencio absoluto
  y con ruido de sala: devuelve vacio en los dos casos. El VAD ya lo cubre.

Los ultimos dos salieron de una revision del concilio como problemas "criticos". Se
midieron antes de construir nada y no aplicaban.

---

## Addons

Comandos que se le agregan al agente sin tocar el nucleo. Eve los llama con
`E addon NOMBRE ACCION ...`: un solo subcomando generico, asi sumar uno no obliga a tocar
el parser ni el despachador.

Se manejan en la pestaña **Addons**, que dibuja sola los campos que cada addon declara
necesitar. Destildar uno lo saca del prompt: deja de gastar tokens en cada llamada y Eve
deja de ofrecerlo.

### El de Spotify

Viene incluido. Poner musica, pausar, saltar, volumen y saber que suena.

**No usa OAuth de usuario.** Controlar la reproduccion por la Web API exige que autorices
la app, guardar y refrescar tokens, y ademas Premium. En vez de eso maneja el Spotify de
escritorio que ya tenes abierto: reproducir es abrir una URI `spotify:` y pausar es
mandarle un comando a su ventana.

**Los comandos van a la ventana de Spotify, no como teclas multimedia globales.** Una
tecla multimedia se la lleva el reproductor que el sistema tenga en foco, que puede ser el
navegador con un video de fondo. `WM_APPCOMMAND` a su ventana le pega solo a Spotify.

Que suena sale de **leer el titulo de su ventana**, que Spotify deja como "Artista - Tema".
Es informacion que ya esta en pantalla: no hace falta API ni permisos.

Lo unico que necesita claves es **buscar**, y son de aplicacion (client id y secret en
https://developer.spotify.com/dashboard), sin login tuyo. Sin ellas, "poné X" abre la
busqueda en la app y elegis vos, y Eve lo dice en vez de fingir que quedo sonando.

### El de OBS

Grabar, transmitir, cambiar de escena, silenciar el micro y sacar una captura, por voz.
Util justo cuando no podes tocar el teclado porque estas grabando.

**No hay que instalar ningun plugin en OBS.** Desde la version 28 trae obs-websocket
adentro. Lo unico que hay que hacer es prenderlo:

> OBS > Herramientas > **Configuracion del servidor WebSocket** > Activar servidor

Eve lee sola el puerto y la contraseña del `global.ini` de OBS, asi que no hay que copiar
nada. Si preferis ponerla a mano, el campo esta en el panel > Addons.

Escribir un plugin en Lua dentro de OBS habria sido mantener codigo en dos lados para
llegar al mismo lugar.

**Los nombres de escena se emparejan por parecido, no por igualdad.** El reconocimiento de
voz no escribe los nombres propios como estan en OBS: pedis "camara dos" y la escena se
llama "Cámara 2". Eve pide la lista real a OBS y busca la mas parecida. Sin eso, la mitad
de los pedidos fallarian con un "no existe esa escena" que no le sirve a nadie.

### Aprobar antes de que corra

Un addon es un `.py` en la carpeta de datos: **codigo que corre con tus permisos** y que,
a diferencia de todo lo demas, no pasa por `safety.py`. Mientras los escribiera una
persona era razonable cargarlos derecho. Desde que la idea es que Eve tambien pueda
escribirlos, cargar sin mirar seria automatizar justo ese agujero.

Asi que un archivo nuevo no se carga hasta que lo apruebes en **Addons**, con un boton
para ver el codigo completo antes de decidir. La aprobacion es de una **huella del
contenido**: editar uno ya aprobado lo vuelve a dejar afuera. Aprobar una version no
aprueba las que vengan despues, que es lo unico que importa si las escribe un modelo.

Ademas un addon puede declarar `RIESGOS = {"accion": "por que"}`, y esas acciones pasan
por el mismo dialogo de confirmacion que el resto del programa.

### Escribir uno propio

Archivos `.py` en `<datos>/addons/`. El minimo es:

```python
NOMBRE = "loquesea"
PROMPT = "  E addon loquesea hacer ALGO"     # lo que ve el modelo

def ejecutar(accion, args, cfg):
    return "lo que Eve le dice al usuario"
```

Opcionales: `DESCRIPCION`, `CLAVES` (para que el panel dibuje sus campos) y
`disponible(cfg) -> (bool, motivo)` para que no se ofrezca cuando le falta algo.

**Corren dentro de Eve, con los mismos permisos que el programa.** Poné ahi solo cosas en
las que confies. Uno que no importe o que reviente se reporta y se saltea, sin llevarse
puesto al resto.

Para **MCP**: con el motor `claude-code`, los servidores MCP se agregan por la
configuracion del propio Claude Code y quedan disponibles sin pasar por aca.

### El cartel en pantalla

Cuando le hablas aparece un cartel encima de todo con el nombre, en que anda y la onda
del audio, y debajo los subtitulos: lo que dijiste (para ver si te entendio antes de que
actue) y lo que responde, revelandose mientras lo dice.

**No te saca el foco de lo que estes haciendo y los clics lo atraviesan.** Podes estar
jugando y aparece encima sin sacarte del juego. Eso son tres estilos de ventana de
Windows (`WS_EX_NOACTIVATE`, `WS_EX_TOOLWINDOW` y `WS_EX_TRANSPARENT`) que se aplican en
`plataforma.ventana_fantasma`; el unico momento en que acepta el mouse es cuando lo
soltas para reubicarlo.

Corre como un tercer proceso (`Eve --overlay`) por lo mismo que el panel: el hilo
principal del listener ya es del icono de la bandeja. El listener le pasa el estado por
un archivo chico que escribe ~10 veces por segundo mientras hay actividad, y en reposo no
escribe nada. Se cierra solo cuando Eve deja de latir.

Todo se configura en **Apariencia**: tema de colores (o los ocho colores a mano), tipo de
contorno, tipo de onda, icono (o una imagen propia), escala, opacidad, que muestran los
subtitulos y donde va el cartel. **Mover en pantalla** lo suelta para arrastrarlo. El mismo
tema puede pintar tambien el panel de configuracion, que es opt-in porque obliga a dibujar
los controles por nuestra cuenta en vez de usar los de Windows.

### Fondos e imagenes

El cartel y los subtitulos aceptan una imagen de fondo, **PNG o GIF animado**, cada uno
por su lado. Se elige el ajuste (recortar, estirar o mosaico), la opacidad y cuanto se
tiñe con el color de acento.

La opacidad de la imagen **no** es el `-alpha` de la ventana. Se mezcla contra el color
del panel al cargarla, con PIL: asi el fondo queda tenue y las letras siguen enteras. Con
el alpha de la ventana, bajar el fondo se llevaria puesto tambien el texto.

Tampoco se usa `PIL.ImageTk`, que seria el puente natural: es un submodulo aparte que
puede no viajar en el binario empaquetado, y un fondo que solo falla en la version
instalada es la peor clase de falla. En vez de eso PIL escala y mezcla, guarda un PNG
temporal (cacheado por hash de los parametros) y lo carga `tk.PhotoImage`, que lee PNG de
forma nativa desde Tk 8.6.

**Forma recortada**: con `hud_forma = recortado` el cartel deja de ser un rectangulo. Los
contornos hexagonal y biselado pasan a dejar ver el escritorio por las esquinas cortadas.
Se hace con `-transparentcolor`, que vuelve invisible un color concreto (`#010203`, raro a
proposito). Un canvas no sabe recortar una imagen contra un poligono, asi que lo que sobra
se pinta de ese color.

En el **panel** hay imagen de cabecera por pestaña, pero no fondo para toda la ventana:
los controles de ttk pintan su propio fondo opaco y lo taparian. Medido: un `ttk.Label`
sobre una imagen roja da `(220,218,187)` donde la imagen da `(220,30,30)`.

### Degradados, fuentes y el marco

Sin imagen, el fondo puede ser un **degradado** de dos colores (vertical, horizontal,
diagonal o radial). Se genera con PIL y se carga como una imagen: simularlo con mil lineas
de un pixel en el canvas serian mil items que tk redibuja en cada cuadro.

Las **fuentes** se eligen por separado para el panel, el cartel y los subtitulos. La del
panel se aplica en vivo porque las fuentes con nombre de tk son objetos compartidos:
reconfigurar `TkDefaultFont` repinta todos los widgets que la usan, sin recorrer nada.

El **marco del icono es parametrico**: lados, giro, redondeo y grosor. Las "formas" del
panel son atajos que llenan esos cuatro numeros, no formas aparte. El redondeo no se
calcula con arcos: `create_polygon(..., smooth=True, splinesteps=N)` redondea los vertices
con splines, que es el radio de esquina gratis.

### Legibilidad

**El texto lleva halo siempre**, no solo cuando el contraste da mal. Sobre un cartel que
flota, el fondo real es tu escritorio, que el programa no controla: medir contraste WCAG
daria un numero contra el fondo equivocado. Cuatro copias del texto desplazadas un pixel
resuelven foto, degradado y GIF de una sola vez y no cuestan nada, que es lo que hacen los
subtitulos de cualquier reproductor.

Hay un **"no animar los GIF"** para quien no tolera el movimiento en pantalla: deja el
primer cuadro fijo.

Este diseño salio de pasar las tres decisiones por un concilio de asesores. La conclusion
que cambio el rumbo fue descartar el medidor de contraste: era infraestructura para una
decision que se toma una vez.

En juegos a **pantalla completa exclusiva** no se ve ningun overlay: es como funciona
DirectX, no un problema de Eve. En modo ventana o ventana sin bordes si.

Fuera de Windows el cartel se ve y se puede mover, pero el no-robar-foco y el
click-through son *best effort*: X11 necesita regiones de entrada por shape y macOS
`ignoresMouseEvents`, que tkinter no expone.

El arranque automatico se elige durante la instalacion.

Windows 11 manda los iconos nuevos al desbordamiento ocultos. Para fijarlo visible:
arrastralo desde la flechita a la barra.

---

## Los cuatro motores

Se elige en el panel (**General > Motor**). Misma interfaz, distinto backend.

| | `api` | `claude-code` | `ollama` | `compat` |
|---|---|---|---|---|
| Auth | `ANTHROPIC_API_KEY` | tu suscripcion | ninguna | la clave del proveedor |
| Costo | por token | tu limite de uso | gratis | segun el proveedor |
| Datos | a Anthropic | a Anthropic | **no salen de tu PC** | al proveedor |
| Latencia | menor | mayor | depende de tu GPU | menor |
| Tools | 4 propias | las de Claude Code | las mismas 4 | las mismas 4 |
| Freno | `safety.py` | hook `PreToolUse` | `safety.py` | `safety.py` |

`compat` es un motor para todo lo que hable el protocolo de OpenAI: Gemini, Groq,
DeepSeek, OpenRouter, xAI, LM Studio y el propio OpenAI. Es uno y no cinco porque todos
exponen el mismo `POST /chat/completions`; el proveedor es configuracion, no codigo.
Varios tienen capa gratuita de verdad.

**Cambiar de motor ya no borra la conversacion.** Cada uno guardaba el hilo en su propio
formato --objetos del SDK, dicts de Ollama, un session_id opaco del CLI-- asi que pasar de
uno a otro dejaba a Eve sin memoria de lo recien dicho. Ahora los cuatro leen el mismo log
de turnos, que ya venian escribiendo.

**Ollama es notablemente peor encadenando varias tools.** Para un pedido de un paso anda
bien; para tareas de varios pasos se pierde, y por eso corta a los 6 pasos en vez de 12.
Es el precio de no mandar nada a la nube, no un bug.

Reusa `brain.TOOLS` tal cual — Ollama acepta el mismo JSON Schema — y la misma ejecucion,
asi que el freno y el log de auditoria son identicos en los cuatro motores.

En la pestaña **Claves** podes iniciar y cerrar sesion de Claude Code sin salir del panel,
y ver con que cuenta y plan estas conectado.

---

## El freno

Reconocimiento de voz falible + LLM + ejecucion de comandos = perdes algo tarde o
temprano ("borra la carpeta temp" se transcribe "borra la carpeta Temu"). Por eso:

- Comandos destructivos (`rm -rf`, `Remove-Item -Recurse`, `format`, `shutdown`,
  `reg delete`, descarga-y-ejecuta...) piden un si/no antes de correr.
- Rutas fuera del allowlist piden confirmacion. El chequeo resuelve `..` y symlinks.
- Todo lo ejecutado queda en `eve.db` (pestaña **Acciones** del panel).

### Permitir todo

Panel > **General > Permisos > "Permitir todo sin preguntar"**. Desactiva los dos frenos:
el nuestro y la capa de permisos interna de Claude Code (`--dangerously-skip-permissions`).
Sin lo segundo el hook diria "allow" pero el CLI seguiria denegando en silencio, y las
tareas fallarian sin motivo visible.

Las acciones riesgosas se siguen guardando en el log, marcadas `AUTO-PERMITIDO (allow all)`.
En este modo el log es el unico registro que queda: nada frena una transcripcion mal
entendida antes de que se ejecute.

---

## Nombres propios en ingles

Whisper decodificando en espanol destroza los nombres de programas. Medido con audio
sintetizado, modelo `base` y sin vocabulario:

```
dicho:      "abre rainbow six siege"
transcrito: "Haberé en Vox XC"
```

Dos arreglos, ambos por defecto:

- **Modelo `small`** en vez de `base`.
- **`eve/apps.py`** indexa los juegos instalados (Steam, Ubisoft Connect, Epic) y los
  accesos del menu inicio. Ese indice se usa dos veces: como `initial_prompt` de whisper
  (sesga el reconocimiento hacia nombres que existen en tu PC) y como catalogo
  `Nombre => comando` en el system prompt, para que Eve sepa con que abrir cada cosa.

```
"abre rainbow six siege" -> Start-Process "uplay://launch/635/0"
"abri el balatro"        -> Start-Process "steam://rungameid/2379780"
```

El indice se cachea en `apps.json` y se refresca solo cada 7 dias. Para forzarlo:
panel > **Voz** > *Reescanear programas*. Ahi mismo hay un campo de vocabulario extra
para nombres que el reconocimiento siga errando.

---

## Voces de la comunidad

Panel > **Voces**. Son las voces de [Piper](https://github.com/rhasspy/piper): **173
modelos entrenados por la comunidad en 49 idiomas**, gratis y offline.

- Filtras por idioma, ves el tamaño, y descargas con un boton.
- **Se verifica el md5** que publica el indice: una descarga cortada se descarta en vez
  de dejarte un modelo truncado que despues falla sin decir por que.
- Boton *Probar* para escucharla antes de elegirla.
- En español hay 9, incluidas `es_AR`, `es_MX` y `es_ES`.

Piper es ademas el unico TTS que suena igual en los tres sistemas: SAPI solo existe en
Windows y `pyttsx3` en macOS y Linux es irregular. Si estas fuera de Windows, es la opcion.

```
es_ES-davefx-medium    medium    63.2 MB
es_AR-daniela-high     high     114.2 MB
```

## Modulos

Un modulo no es una ventana ni un widget: es **una fila de datos** mas una funcion que
dibuja. Se guarda como claves planas `mod_<id>_<prop>` en la misma config que todo lo
demas, y ese prefijo es lo que lo hace barato: una prop nueva entra sola a los perfiles
exportables y no rearma el motor al cambiar, asi que mover un modulo no corta la
conversacion y un layout entero viaja en un `.eveperfil`.

Tipos: `texto`, `icono`, `onda`, `particulas`, `reloj`, `contexto`, `grafo` y `lector`.

Se arman en **Apariencia > Modulos**, y el formulario de ajustes no esta escrito: se
genera recorriendo el esquema del tipo. Elegir una onda muestra `estilo` y `muestras`;
elegir particulas muestra `cantidad`, `vida` y `gravedad`, sin una linea de tkinter de
diferencia. Eso es lo que decide si esto escala: si cada perilla costara veinte lineas de
interfaz, no se llega. Y es lo que hace posible que Eve cree modulos sola, porque escribe
datos y no codigo de interfaz.

Hay dos botones para arrancar: uno convierte el cartel de siempre en modulos y otro arma
un tablero. Si no hay ningun modulo configurado, el cartel sigue siendo exactamente el de
antes.

**Como se anima.** Cuatro clases, y en ninguna se escribe codigo: o se mueve una perilla,
o se deja un archivo en la carpeta de assets y se lo elige, igual que con los fondos.

| Clase | Se crea con | Se importa |
|---|---|---|
| Procedural | perillas del panel | no hay archivo |
| Por cuadros | Aseprite, Photoshop, Blender, ezgif | GIF, APNG o WebP animado |
| Vectorial | After Effects, LottieFiles | pendiente |
| Particulas | Particle2dx, Particle Designer | pendiente |

Todas comparten `velocidad`, `easing`, `escala`, `rotacion`, `opacidad`, `tinte`, `color`
y `cuando` (siempre, trabajando, al pasar el mouse). La que las separa es **`fuente`**:
`reloj` o `microfono`. Una animacion importada se puede escalar, teñir y acelerar, pero
no puede **reaccionar**; para eso el dibujo lo tiene que calcular la maquina. Por eso las
particulas y la onda responden a tu voz de verdad.

El rendimiento sale de una medicion, no de un gusto. Sobre 1200x800 con seis modulos con
alpha y 500 particulas:

```
capas del tamaño del cuadro, PhotoImage nueva  ->  p95  53.1 ms   27 fps
cada modulo compuesto en su rectangulo         ->  p95  26.9 ms   57 fps
recomponiendo solo lo que cambio               ->  p95  21.7 ms   70 fps
una PhotoImage POR MODULO, uno animado         ->  p95   7.1 ms  217 fps
```

De ahi tres reglas: cada modulo se compone en su propio rectangulo y nunca en capas del
tamaño del cuadro; solo se repinta el que cambio; y la PhotoImage se crea una vez y
despues se le hace `paste`, porque reasignarla cada cuadro cuesta el doble.

---

## La ventana de actividad

`Eve.exe --consola`, o desde la bandeja. Dos modos arriba, que no son dos pantallas: son
quien puede escribir.

**Work** lee el estado y lo dibuja. **Edit** vuelve editable el mismo dibujo: clic elige,
Ctrl suma y saca, Shift agrega un rango, arrastrar mueve, `Ctrl+Z` deshace.

Con varios modulos elegidos se muestran las props que **tienen en comun**. Agrupar una
onda con unas particulas deja cambiar la opacidad de las dos --lo unico que comparten-- y
no ofrece `estilo`, que es solo de la onda. Ofrecer todo pisaria props que el otro no
tiene; no ofrecer nada volveria inutil agrupar. Si el valor difiere entre los elegidos, el
campo arranca vacio, asi que aplicar no los iguala sin querer.

Queda afuera a proposito: guias de alineacion, z-order anidado, copiar estilo y snapping.
Aceptar uno solo de esos es empezar a mantener un editor de diseño.

**El grafo** sale del log de auditoria que ya se escribia. Los nodos redondos son las
herramientas que se ejecutaron y los cuadrados los proyectos donde se ejecutaron; las
aristas, lo que sale una detras de otra. Un proyecto es la primera carpeta que cuelga de
un directorio permitido: no es arbitrario, es donde trabajas y lo unico que Eve puede
tocar sin preguntar. Extraccion determinista, sin una sola llamada a un modelo.

**El lector** no es un navegador y no pretende serlo. Renderizar un sitio arbitrario ES un
motor web, y lo que hace falta no son pixeles: es texto que entre al contexto y que se
pueda marcar como escrito por terceros antes de que lo vea el modelo. Eso ultimo es
justamente lo que un navegador embebido no puede dar. `E leer URL` y `E buscar "..."`.

---

## Quien manda sobre un ajuste

En **General > Quien manda**. Sin esto la app se siente poseida: pones opacidad 40, Eve la
vuelve a 80, y no hay forma de saber quien gano ni de trabar el valor.

| | |
|---|---|
| `usuario` | lo que cambiaste a mano queda trabado y Eve no lo pisa (por defecto) |
| `eve` | cambia lo que quiera |
| `preguntar` | sale un dialogo antes de cada cambio |

El panel anota que claves tocaste vos, y esa lista es lo que se traba. Se suelta con
`E destrabar CLAVE`. Del lado de Eve quedan `E ajustar CLAVE VALOR`, `E modulo crear` y
`E perfil guardar|aplicar`, que es lo que le permite armar una interfaz cuando se lo pedis
hablando.

---

## EVE.md — el manual del agente

`EVE.md` es lo que Eve lee en cada llamada: como decidir que hacer y como hablar. Editalo
directo, no hace falta tocar codigo.

Los datos **tuyos** van aparte, en `MEMORIA.md`, que no se versiona: rutas, preferencias,
como llamas a cada cosa. Eve lo amplia sola con `recordar "..."`.

**Regla cero:** si te llamaron apretando un botón, querés que *haga* algo o que te lo
*muestre*. La voz es el acuse de recibo, no el contenido. Lo que no entra en dos frases
habladas va a pantalla.

| Pedís | Hace | Dice |
|---|---|---|
| "buscame un artículo sobre X" | abre los resultados en el navegador | "Te abrí unos resultados" |
| "cuánto es 15 por 4" | nada | "Sesenta" |
| "explicame cómo funciona el DNS" | `mostrar` en una ventana | "Te lo puse en pantalla" |
| "abrí el Discord" | `Start-Process` | "Abriendo Discord" |
| "mandale un whatsapp a X" | `componer` (abre la app cargada) | "Revisalo y mandá" |

### Costo en tokens

El manual viaja en cada llamada, asi que esta escrito telegrafico y se pagó con recortes
en el resto del prompt. Medido contra Gemini, contando los tokens que reporta el propio
servicio y no estimandolos por caracteres:

```
catalogo entero, memoria entera:  13673 chars  ->  4318 tokens
catalogo solo lo que se usa:       9812 chars  ->  2810 tokens
mas la memoria podada:             9656 chars  ->  2767 tokens
```

**1551 tokens menos en cada llamada, un 36%.** Sale mejor que la cuenta por caracteres
porque las rutas del catalogo tokenizan mal.

De donde salen:

- **El catalogo viajaba entero**: 80 lineas, un tercio del prompt. Contar cuales aparecen
  en el log de acciones --leer datos que ya estaban, sin llamar a ningun modelo-- dice que
  en la practica se abren unos diez. Viajan esos, ordenados por frecuencia. Lo que no
  viaja se pide con `E programa NOMBRE`, y la cabecera le avisa al modelo que la lista es
  parcial: sin ese aviso contestaria "no tengo ese programa" en vez de buscarlo.
  Se apaga con `catalogo_modo = completo`.
- **La memoria crecia sin techo**: `recordar` agrega y nunca saca. Se le quita la cabecera
  --que esta escrita para la persona que edita el archivo, no para el modelo-- y si los
  hechos pasan del presupuesto van los relevantes, avisando cuantos quedaron afuera y como
  pedirlos. Medido con 121 hechos: 6360 -> 1818 caracteres.
- Y de antes: el catalogo abrevia la raiz del menu inicio a `SMU`/`SMP`, la lista de
  comandos usa el prefijo `E` en vez de repetir la ruta de Python diez veces, y las reglas
  de comportamiento viven solo en `EVE.md` en vez de duplicadas en cada motor.

**Sin historial se manda el catalogo completo.** Recortar por falta de datos dejaria una
instalacion nueva sin saber abrir nada.

## Conexiones con apps

Dos patrones, no cinco integraciones sueltas.

**1. Componer** — abre la app con el mensaje ya escrito. El humano aprieta enviar.

```
componer --app whatsapp|telegram|discord|mail --to DESTINO --text "MENSAJE"
```

Cero credenciales, cero terminos rotos. Es la unica via legitima para WhatsApp y
Discord personal: automatizar esas cuentas (whatsapp-web.js, self-bots) viola sus
terminos y hay bans documentados de numeros y cuentas reales. Ademas es el freno
natural — un mensaje que salio de una transcripcion de voz no se manda sin que
alguien lo lea.

**2. Leer y enviar** — donde es legitimo.

| App | Que hace | Que necesita |
|---|---|---|
| **Outlook** | leer bandeja, redactar, buscar contactos | nada, COM local |
| **Steam** | abrir juegos | nada (ya funciona) |
| **Steam** | biblioteca y horas jugadas | Web API key + SteamID64 |
| **Gmail** | leer y enviar | contrasena de aplicacion, o agregarlo a Outlook |
| **Discord** | postear como bot | URL de webhook |
| **Discord** | escribir como vos | nada, tu cliente ya esta logueado |
| **WhatsApp** | componer; leer lo que llega | nada |

Las credenciales van en el panel > **Claves** y se guardan en el gestor del SO. Todas
opcionales: sin ninguna, "componer" sigue funcionando para las cinco. El SteamID64 se
detecta solo desde `loginusers.vdf`, no hace falta buscarlo.

**Gmail sin app password:** si Google no te ofrece "Contrasenas de aplicaciones" (cuenta
sin 2FA, o administrada por una organizacion), agrega el Gmail a Outlook
(Archivo > Agregar cuenta). `outlook-leer` recorre **todas** las cuentas configuradas, asi
que Eve lo lee y escribe por ahi sin ninguna credencial nueva.

Es una CLI (`eve/integrations.py`), asi que los cuatro motores la usan igual — el motor
`api` desde `run_command`, el motor `claude-code` desde Bash. Una implementacion, no dos.

### WhatsApp: por que no envia sola

Se evaluaron las cuatro vias y se midieron en esta PC.

| Via | Resultado |
|---|---|
| Leer la UI con UI Automation | **imposible**: WhatsApp Desktop es UWP sobre WebView2. Cero `EditControl` en los 290 nodos del arbol, y solo 2 de 66 textos con contenido. No se puede leer que chat esta abierto. |
| **Mandar teclas** a la ventana | **funciona**. Probado: `Ctrl+F` + escribir llega perfecto al WebView2. |
| whatsapp-web.js / Baileys | descartada: cliente no oficial sobre un numero personal real. Meta lo detecta y banea. |
| Business Cloud API | no aplica: numero dedicado, aprobacion de Meta, costo por conversacion. |

### Enviar solo (opt-in)

Como no se puede leer que chat esta abierto, el destino **nunca** se busca escribiendo un
nombre. Va en la URI: `whatsapp://send?phone=NUMERO&text=MSJ` abre ESE chat con el texto
cargado, y lo unico que se simula es el Enter. Asi el riesgo de "mensaje correcto al chat
equivocado" desaparece por construccion, no por suerte.

```
whatsapp-enviar --to NUMERO --text "MSJ"
```

Cuatro guardas, en orden:

1. Apagado por defecto. Se activa en el panel > **Claves** > *WhatsApp: enviar solo*.
2. Exige numero con codigo de pais. Un nombre se rechaza sin abrir nada.
3. Verifica que WhatsApp este en primer plano antes de confirmar, y **otra vez** despues
   (el modal roba el foco; si no vuelve, el Enter iria a otra app).
4. Lectura del mensaje en voz alta + confirmacion, como Gmail y Discord.

Lo que sí se pudo conectar es la **lectura**, y sin tocar WhatsApp:
`notificaciones --app whatsapp` lee el centro de notificaciones de Windows con
`UserNotificationListener`, la API de accesibilidad del SO. Riesgo de ban: cero, porque
no se automatiza ningun cliente. Limite: solo lo que sigue en el centro de
notificaciones, no el historial ni los chats silenciados.

### Discord: webhook vs tu propia cuenta

| | `discord-postear` | `discord-enviar` |
|---|---|---|
| Aparece como | el bot del webhook | vos |
| Necesita | URL de webhook | nada |
| Canales | solo el del webhook | cualquiera donde tengas acceso |
| Leer | no | no (solo `notificaciones`) |

`discord-enviar` **no es un self-bot**: no hay token de usuario ni llamadas a la API con
tu cuenta, que es lo que Discord banea. Es el cliente oficial recibiendo teclas, igual que
si escribieras vos.

Sale mejor que WhatsApp porque el destino **se puede verificar**: el titulo de la ventana
dice el canal abierto (`#general | MiServidor - Discord`). El flujo navega con el deep
link, lee el titulo, lo muestra en la confirmacion con el nombre real del canal, y vuelve
a compararlo despues del modal — si cambio, aborta.

El destino (`--canal`) acepta cualquiera de estas, para no tener que pedirle un ID al
usuario a mitad de una orden hablada:

| Forma | De donde sale |
|---|---|
| `Lucas` o `lucho` | de la agenda: usa el campo `discord` de ese contacto |
| `https://discord.com/channels/123/456` | boton derecho en el canal > Copiar enlace |
| `1122334455667788990` | boton derecho en un chat privado > Copiar ID (pide modo desarrollador) |
| `123/456` o `@me/999` | a mano |
| vacio | el canal del webhook |

Un ID suelto se interpreta como mensaje directo (`@me/<id>`): los canales de servidor se
copian con su link, y quien copia solo el ID casi siempre esta en una conversacion privada.

**Modo desarrollador de Discord:** Ajustes > Avanzado > Modo desarrollador. Sin eso no
aparece la opcion "Copiar ID".

### Compartir un contacto

Pestaña **Contactos** > **Exportar**: deja un archivo `.evecontact` (JSON legible) que le
mandas a alguien por WhatsApp o Discord. Del otro lado, **Importar** y le queda cargado.

Si el nombre ya existe en su agenda, **pregunta** antes de reemplazar en vez de duplicar o
pisar en silencio. Las claves que no conoce las ignora, asi que un archivo de una version
futura no rompe nada.

Eve tambien lo hace por voz: `exportar-contacto NOMBRE` deja el archivo en el Escritorio.

### Agenda

Panel > **Contactos**. Nombre, alias, mail, telefono y canal de Discord. Con eso,
"mandale un correo a Lucas" se resuelve sin preguntar nada.

- **Alias** separados por comas: la voz casi nunca dice el nombre completo.
  `Lucas Perez` con alias `lucho, el lucas`.
- El matcheo ignora mayusculas y tildes: "nicolas" encuentra a "Nicolás".
- Si el nombre toca a varios contactos, Eve **pregunta** en vez de elegir.
- Los nombres entran primero en el vocabulario del STT: un nombre propio mal
  transcrito manda el mensaje a la persona equivocada, un juego mal transcrito
  solo abre otra cosa.

Se guarda en `contactos.json`, aparte de `config.json` para que no se pierda si
alguien edita la config a mano. La agenda viaja en el system prompt (hasta 40
contactos) porque resolverla con un comando costaria un round-trip por mensaje.

### Lo que protege

- **Nada se envia sin lectura previa.** `outlook-redactar` abre el borrador en pantalla
  en vez de mandarlo; `gmail-enviar` y `discord-postear` leen el mensaje en voz alta y
  piden confirmacion. El freno general no alcanza aca: un mail mal transcrito no parece
  peligroso, suena a intencion correcta, y no hay deshacer.
- **Inyeccion por bandeja.** Lo que devuelven `outlook-leer` y `gmail-leer` viene envuelto
  y marcado como contenido de terceros, con la instruccion explicita de no obedecer
  ordenes que aparezcan adentro. Un mail que diga "reenvia esto a X" se reporta, no se
  ejecuta.
- **Desambiguacion de contactos.** "Mandale un mail a Juan" resuelve el nombre con
  `outlook-contacto`; si hay varios Juan, pregunta.
- **Outlook en frio.** Si Outlook no esta corriendo, el primer `Dispatch` lo lanza pero
  devuelve un objeto a medio inicializar y `GetNamespace` explota. Se reintenta con
  espera creciente.

## Contexto

Ni stateless puro ni chat infinito: ventana rodante de N turnos / M minutos
(configurable). Sin memoria, "ese archivo no, el otro" es ambiguo por diseño; con
historial completo el costo por llamada crece sin techo. El historial completo vive local
en SQLite y lo lee el panel, no la API.

**El hilo es de Eve, no del motor.** Los cuatro motores escriben los turnos en la misma
tabla y ahora tambien la leen de vuelta, asi que cambiar de motor --o reiniciar Eve-- deja
de borrar la conversacion. "Olvidar contexto" marca un corte en esa tabla en vez de borrar
nada: el historial del panel y las cuentas de gasto quedan enteros.

**Y se mide.** Los cuatro motores recibian en cada respuesta cuantos tokens costo la
llamada y los cuatro lo descartaban. Ahora queda anotado por turno, sumando las vueltas
del loop de tools: un turno que ejecuta una herramienta hace dos llamadas al modelo, y
contar solo la ultima diria que abrir un programa cuesta lo mismo que decir la hora. El
modulo `contexto` de la ventana de actividad lo dibuja desglosado por seccion del prompt.

Un detalle que solo aparece midiendo contra el servicio de verdad: Gemini devuelve
`completion_tokens: 0` con `total_tokens: 13` sobre 6 de entrada. Cobra el razonamiento y
lo deja afuera del campo que todo el mundo lee, asi que un medidor ingenuo subestima cada
turno a menos de la mitad.

---

## Arquitectura

```
tecla --> grabar --> faster-whisper --> [motor] --> Piper / SAPI (voz)
                                           |
                                   freno de confirmacion
                                           |
                                SQLite (historial + auditoria)
                                           |
                            cartel flotante  +  ventana de actividad
```

Tres ventanas, tres procesos: el cartel (`--overlay`), el panel (`--panel`) y la ventana
de actividad (`--consola`). Se hablan por archivos JSON en la carpeta de datos, no por
sockets ni por hilos compartidos: tkinter y pystray no comparten mainloop sin dolor, y
este proyecto ya pago ese precio una vez.

Sin servidor MCP y sin router de modelos. MCP existe para exponer tools a clientes
externos; aca el unico cliente sos vos, asi que seria un servidor JSON-RPC para hablar
consigo mismo. El router (un modelo barato clasificando antes de ejecutar) agrega un
round-trip completo a cada frase para ahorrar centimos, en un sistema donde la latencia
percibida es todo. Tampoco se envuelve el `/voice` de Claude Code: es un REPL, no una API.

| Archivo | Que hace |
|---|---|
| `main.py` | Arranca listener + bandeja |
| `eve/listener.py` | Push-to-talk, filtra autorepeat, maneja mic ocupado |
| `eve/brain.py` | Motor `api`: loop de tools contra la Messages API |
| `eve/cc_engine.py` | Motor `claude-code`: CLI headless con tu suscripcion |
| `eve/hook_gate.py` | Freno del motor `claude-code` (hook PreToolUse) |
| `eve/safety.py` | Deteccion de destructivos + allowlist de rutas |
| `eve/apps.py` | Indice de programas y juegos instalados |
| `eve/integrations.py` | Conexiones con WhatsApp, Discord, Steam, Gmail y Outlook |
| `eve/plataforma.py` | Lo unico que sabe en que sistema corre: shell, dialogos, teclado |
| `eve/ollama_engine.py` | Motor `ollama`: modelo local, sin nube |
| `eve/voices.py` | Catalogo y descarga de voces de la comunidad |
| `build.py` | Arma los binarios y el instalador del sistema |
| `packaging/` | Instaladores: Inno Setup, dmg, deb y rpm |
| `eve/voice.py` | STT (faster-whisper / OpenAI) y TTS (Piper / SAPI / ElevenLabs) |
| `eve/store.py` | config.json, keyring, SQLite, ventana de contexto |
| `eve/gui.py` | Panel tkinter |
| `eve/tray.py` | Icono de bandeja |
| `eve/icon.py` | Genera el icono |
| `eve/compat_engine.py` | Motor `compat`: todo lo que hable el protocolo de OpenAI |
| `eve/prompt.py` | Arma el system prompt, en un solo lugar para los cuatro motores |
| `eve/modulos.py` | Que es un modulo: una fila de datos con prefijo `mod_` |
| `eve/lienzo.py` | Compositor: una PhotoImage por modulo, repintando solo lo sucio |
| `eve/consola.py` | Ventana de actividad, con modo Work y modo Edit |
| `eve/overlay.py` | El cartel flotante sobre el escritorio |
| `eve/grafo.py` | Que hizo Eve y en que proyectos, sacado del log |
| `eve/memoria.py` | Poda MEMORIA.md para que no crezca adentro de cada llamada |
| `eve/lector.py` | Lee una pagina web y devuelve texto, sin motor web |
| `eve/tema.py` | Paletas por roles, para el panel y para el cartel |
| `eve/imagenes.py` | Fondos e iconos: PNG, GIF, APNG y WebP animado, con cache |
| `eve/addons/` | Plugins del usuario, que no se cargan hasta aprobarlos |
| `eve/updater.py` | Busca e instala versiones nuevas |

---

## Desarrollo

```bash
python test_eve.py       # 71 tests: freno, allowlist, contexto, voz, modulos,
                         # grafo, memoria, perfiles y fuga de hooks
python diagnostico.py    # que falta en esta PC
```

Sin frameworks: los tests son `assert` sueltos. Cubren lo que no puede fallar en silencio.

## Problemas comunes

| Sintoma | Causa |
|---|---|
| El boton no hace nada | La tecla del panel no es la que manda tu keypad. `python diagnostico.py --tecla` |
| "No puedo usar el microfono" | Discord/OBS/Zoom lo tienen en modo exclusivo |
| Guarde la config y no cambio nada | Dale ~4 segundos; si no, **clic derecho > Reiniciar listener** |
| La primera frase tarda muchisimo | Esta descargando el modelo de voz. Pasa una sola vez |
| No entiende nombres de juegos | Panel > Voz > *Reescanear programas* |
| La voz no transcribe nada | `Eve.exe --probar-voz` para ver donde corta |
| No aparece el icono | Esta en el desbordamiento (la flechita); arrastralo a la barra |
| Windows dice que es peligroso | Sin firma digital. *Mas informacion > Ejecutar de todas formas* |
| macOS no lo deja abrir | Boton derecho sobre el `.app` > Abrir, solo la primera vez |
