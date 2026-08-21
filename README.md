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

Arma lo del sistema donde lo corras. `build.py` no sabe armar instaladores: llama al
guion de `packaging/` que corresponda, con la version y la arquitectura como argumentos.

| Sistema | Guion | Hace falta |
|---|---|---|
| Windows | `packaging/windows/eve.iss` | [Inno Setup](https://jrsoftware.org/isinfo.php) — `winget install JRSoftware.InnoSetup` |
| macOS | `packaging/macos/dmg.sh` | `hdiutil`, que ya viene |
| Debian, Ubuntu | `packaging/linux/build_deb.sh` | `dpkg-deb` |
| Fedora, RHEL | `packaging/linux/build_rpm.sh` | `rpmbuild` |

En Linux se intentan los dos y **se saltea en silencio el que no tenga su herramienta**,
asi que un runner con solo `dpkg-deb` saca el `.deb` y sigue. Lo que no se saltea es un
guion que falla: se corren con `check=True` a proposito, porque con `check=False` un
script roto dejaba el job en verde sin ningun paquete, y asi se publico una release vacia.

Los dos de Linux comparten `packaging/linux/eve.desktop`, que es lo que pone a Eve en el
menu de aplicaciones; el `.dmg` usa `packaging/macos/Info.plist` para el bundle.

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

El cartel y los subtitulos aceptan una imagen de fondo, cada uno por su lado: **PNG, GIF,
APNG y WebP animado**. Se elige el ajuste (recortar, estirar o mosaico), la opacidad y
cuanto se tiñe con el color de acento.

Los dos ultimos entraron sin escribir una linea de codigo nuevo. El recorrido de cuadros
pide `n_frames`, hace `seek` y lee `info["duration"]`, y en PIL eso vale igual para los
cuatro formatos: **ya andaban, y lo unico que los tapaba era el filtro `*.png *.gif` del
dialogo de archivos**. Vale la pena porque el GIF es de 1998: paleta de 256 colores y
alpha de un bit. El mismo dibujo de tres cuadros con un degradado suave da 2 colores
unicos guardado como GIF y 92 como APNG, con alpha de 8 bits en vez de "transparente o
no".

La opacidad de la imagen **no** es el `-alpha` de la ventana. Se mezcla contra el color
del panel al cargarla, con PIL: asi el fondo queda tenue y las letras siguen enteras. Con
el alpha de la ventana, bajar el fondo se llevaria puesto tambien el texto.

Aca no se usa `PIL.ImageTk`, que seria el puente natural: PIL escala y mezcla, guarda un
PNG temporal (cacheado por hash de los parametros) y lo carga `tk.PhotoImage`, que lee PNG
de forma nativa desde Tk 8.6. El motivo original era el miedo a que ese submodulo no
viajara en el binario empaquetado, porque `build.py` verificaba **archivos** presentes y
no que un import funcionara: un submodulo que PyInstaller no ve no deja ningun archivo
faltante a la vista y el programa recien falla cuando el usuario usa la funcion.

Ese miedo ya no aplica. `python build.py --probar-imports` corre **el binario recien
armado** y le pide que importe lo critico, en los cinco objetivos de la CI, y `ImageTk`
esta en la lista. Por eso el compositor de modulos (`eve/lienzo.py`) si lo usa: ahi no
alcanza con escribir un PNG por cuadro. Este camino sigue como esta porque para un fondo
estatico el PNG cacheado es mas barato, no porque haya algo que temer.

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

### El banco de voz

Todo lo de arriba se midio con audio **sintetizado**, y eso tiene un techo: la voz de
Piper no tiene ruido de fondo, no se aleja del microfono y no susurra. Asi que hay un
banco de grabaciones de verdad, 24 clips en seis grupos --limpio, nombres propios, lejos,
con ruido, rapido y susurro-- con nivel de pico controlado en cada uno.

```bash
python banco_voz.py                     # WER por grupo con la config actual
python banco_voz.py --modelo medium     # pisa el modelo sin tocar la config
python banco_voz.py --borrador          # transcribe todo para corregir a mano
```

Saca el WER desglosado en sustituciones, inserciones y borrados por separado --un motor
que inventa palabras y otro que se las come dan el mismo numero y se arreglan distinto--
y el RTF, que es la mitad del argumento de cualquier modelo nuevo. Compara sin acentos y
sin puntuacion, a proposito: el matcher de comandos y de contactos ya es insensible a los
dos, asi que contarlos como error inflaria la cuenta con fallas que a la aplicacion no le
cambian nada.

**Las grabaciones no viajan en el repo.** Son la voz de una persona, asi que viven en la
carpeta de datos junto a los contactos y los perfiles, en `banco_voz/`.

Con las 24 referencias escritas, la linea base quedo asi --y de paso decide que modelo
conviene, que hasta ahora era una corazonada:

```
modelo      lejos  limpio  propios  rapido   ruido  susurro   TOTAL   por orden de 2s
tiny        36.4%   22.2%    52.2%   66.7%   25.0%    20.0%   33.2%
base        21.2%   17.5%    78.3%   44.4%   12.5%     0.0%   26.1%
small       15.2%    3.2%    21.7%   22.2%   12.5%     0.0%   10.9%   0.9s gpu / 3.3s cpu
medium       0.0%    1.6%    17.4%   22.2%    0.0%     0.0%    4.9%   1.8s gpu / 10.2s cpu
large-v3     0.0%    1.6%    34.8%    0.0%    0.0%     0.0%    4.9%   2.7s gpu
```

Tres cosas que salieron de ahi:

- **Mas grande no es mejor.** `large-v3` empata a `medium` en total y es el **doble de malo
  en nombres propios**, 34.8% contra 17.4%, que es justo el grupo que decide si Eve abre el
  programa correcto. Y tarda un 50% mas.
- **`medium` solo con GPU.** Baja el WER a la mitad por +0.9s en GPU, pero en CPU una orden
  de dos segundos tarda **10 segundos**. Por eso el default sigue siendo `small`.
- **El vocabulario casi no sirve donde se suponia que servia.** El catalogo de programas
  como `initial_prompt` mueve nombres propios de 30.4% a 26.1%, y servirle **los nombres
  exactos en bandeja** deja el mismo 26.1%. No es un problema de vocabulario, es acustico:
  ahi la unica palanca es el modelo.

### Que espanol habla

En **Voz > Que espanol habla**. Cambia como Eve **escribe**: `rioplatense` (vos, abri,
pone, dale), `neutro` (tu, sin regionalismos), `mexicano` (ahorita, ya quedo) o
`castellano` (vale, ordenador). Vacio no le dice nada. Cuesta unos **40 tokens por
llamada**, que es todo lo que puede costar algo que viaja en cada una.

**La voz va aparte, y eso no es un descuido.** Se midieron las siete voces de Piper en
espanol sobre las mismas diez frases, sintetizando y volviendo a transcribir con el mejor
reconocedor que hay: si el reconocedor no la entiende, una persona con el juego de fondo
tampoco.

```
voz                     las tres corridas    media    RTF
es_ES-sharvard-medium     4.8   6.0   8.4     6.4%   0.09
es_MX-claude-high         7.2   6.0   7.2     6.8%   0.08
es_ES-davefx-medium       8.4   7.2   9.6     8.4%   0.09
es_ES-carlfm-x_low       10.8   9.6   9.6    10.0%   0.05
es_MX-ald-medium          9.6  12.0   9.6    10.4%   0.09
es_MX-ald-x_low          14.5   8.4  10.8    11.2%   0.08
es_AR-daniela-high       24.1  21.7  15.7    20.5%   0.43
```

**Las tres corridas estan a la vista porque hacen falta.** Piper no es determinista
--sintetiza con algo de azar-- y una misma voz se mueve entre 1.2 y 8.4 puntos, con
mediana 2.4. Con una sola medicion casi todo este orden seria ruido: `es_MX-ald-x_low`
sola da 8.4% o 14.5% segun el dia.

Lo que sobrevive a esa banda son dos cosas. `es_AR-daniela-high` es la peor de las siete
por mucho --su MEJOR corrida, 15.7%, es peor que la peor de casi todas las demas-- y la
mas lenta por cinco veces. Y `es_MX-claude-high` le gana a `es_MX-ald-medium` de verdad,
porque su peor corrida es mejor que la mejor de la otra.

Este numero costo tres correcciones y vale la pena dejarlas escritas. La primera tabla daba
RTF 1.06 para la voz argentina, y de ahi salio la afirmacion --falsa-- de que era la unica
que tardaba mas en generarse que en escucharse: era el tiempo de CARGA adentro del
cronometro, porque `voices.precargar()` no alcanza y Piper termina de armar cosas en la
primera sintesis. La segunda tabla, ya con calentamiento, tenia una sola corrida por voz y
estimaba el ruido midiendo una sola: dio "un punto largo" cuando en realidad son ocho. La
tercera es esta. **La conclusion no cambio nunca; las razones que la sostenian, dos veces.**

Por eso **hasta la variante rioplatense sugiere una voz mexicana**, y hay un test que
impide que alguna variante recomiende la argentina. La voz es el canal, no el acento del
que habla: que Eve escriba "abri" y lo diga con acento neutro se entiende; que lo diga con
una voz que se escucha mal, no. Si igual la queres, elegila a mano en **Voz de Piper** --el
boton "usar la voz que le corresponde" sugiere, no impone, que es la misma regla de
**Quien manda sobre un ajuste**.

**Del lado de entender, no hizo falta nada.** La idea de instalar vocabularios por
variante se probo y no mueve la aguja:

```
sesgo del reconocedor              TOTAL
catalogo de programas (hoy)        10.9%
+ vocabulario rioplatense          10.9%
+ vocabulario neutro               12.0%
solo rioplatense, sin catalogo     17.4%
sin ningun sesgo                   15.8%
```

Agregar palabras rioplatenses **no cambia nada**, agregar vocabulario neutro **empeora**, y
reemplazar el catalogo de programas por vocabulario de dialecto empeora mucho. Lo que se
gana con el sesgo lo gana el catalogo de programas instalados, no el dialecto: whisper ya
sabe voseo, y lo que no sabe son los nombres de tus juegos. Un ajuste que no mueve un
numero no entra, aunque quede lindo en el panel.

---

### Parakeet y Kokoro, medidos contra la linea base

La regla era que entraban solo si ganaban medidos. Se midieron los dos sobre el mismo banco
y con la misma cuenta.

**Parakeet TDT 0.6B v3 (NVIDIA) entra, como opcion.**

```
sistema                     lejos  limpio  propios  rapido   ruido  susurro   TOTAL   RTF   disco
whisper small en gpu        15.2%    3.2%    21.7%   22.2%   12.5%     0.0%   10.9%  0.27   464 MB
whisper small en cpu        15.2%    3.2%    21.7%   22.2%   12.5%     0.0%   10.9%  1.38   464 MB
whisper medium en gpu        0.0%    1.6%    21.7%   22.2%    0.0%     0.0%    5.4%  0.61   1.5 GB
parakeet v3 int8 en CPU      0.0%    1.6%    30.4%   16.7%    6.2%     0.0%    7.1%  0.19   639 MB
parakeet v3 fp32 en CPU      0.0%    1.6%    21.7%   11.1%   28.1%     0.0%    9.2%  0.18   2.4 GB
```

Lo que decide no es el punto y medio de WER: es que ese **0.19 es en CPU**. Whisper `small`
tarda siete veces mas en la misma maquina sin GPU, y la mayoria de las instalaciones no
tienen CUDA configurado. Un reconocedor mejor deja de costar una placa de video.

Donde pierde es en **nombres propios**: 30.4% contra 21.7%, y ese es justo el grupo que
decide si Eve abre el programa correcto. No acepta un sesgo de vocabulario como el
`initial_prompt` de whisper, asi que el indice de programas instalados no lo puede ayudar.
Por eso es una opcion en **Voz > STT** y no el default.

Cuesta **cero dependencias nativas nuevas**: `onnx-asr` es rueda pura y sus unicas
dependencias --numpy, onnxruntime, huggingface-hub-- ya viajaban por faster-whisper. Un
test lo fija, para que el dia que eso deje de ser cierto se sepa antes que lo diga un build
de linux-arm64.

**Kokoro no entra.** No gana en ninguno de los dos ejes que se pueden medir:

```
motor                        RTF   WER al re-oirla   disco
piper es_MX-claude-high     0.30              6.0%   109 MB
piper es_ES-davefx-medium   0.43              8.4%    60 MB
kokoro v1.0 ef_dora         0.74              6.0%   325 MB
piper es_AR-daniela-high    1.07             16.9%   109 MB
kokoro v1.0 int8 ef_dora    1.88              6.0%    92 MB
```

La calidad de una voz es subjetiva y no se mide con un banco, pero dos cosas si: la
velocidad, y la **inteligibilidad** --se sintetiza una frase conocida, se la vuelve a
transcribir con el mejor reconocedor que hay, y se cuentan los errores. Si un reconocedor
entrenado con miles de horas no la entiende, una persona con el juego de fondo tampoco.

Kokoro empata en inteligibilidad con una voz de Piper que es **2.5 veces mas rapida y 3
veces mas chica**, y solo trae tres voces en espanol, ninguna rioplatense. Su version
cuantizada es mas lenta que la original, no mas rapida. Y como TTS de un asistente el RTF
importa de verdad: arriba de 1.0 la frase tarda mas en generarse que en escucharse.

Un hallazgo lateral que vale para el uso diario: **la voz argentina `es_AR-daniela-high` es
la peor medida de todas** --16.9% y RTF 1.07, la unica que pasa de tiempo real. Si te
importa que se entienda mas que el acento, `es_MX-claude-high` gana por lejos.

---

### Sensibilidad: los modos y de donde salen

En **Voz > Sensibilidad**. Los dos valores que la componen son el umbral del detector de
voz y el aire que deja alrededor de cada tramo, y los numeros salen de barrer el banco:

```
umbral/aire      lejos  limpio  propios  rapido   ruido  susurro   TOTAL
0.5/400 (antes)  15.2%    3.2%    26.1%   16.7%   18.8%     0.0%   12.0%
0.5/100 normal   15.2%    3.2%    21.7%   22.2%   12.5%     0.0%   10.9%
0.85/250 ruido   15.2%    3.2%    26.1%   16.7%    0.0%     0.0%    8.7%
0.5/250 bajo     15.2%    3.2%    26.1%   16.7%   18.8%     0.0%   12.0%
sin VAD          15.2%    3.2%    26.1%   22.2%   18.8%     0.0%   12.5%
```

**El modo `ruido` deja su grupo en 0.0%**, que era el pedido: musica de fondo y vos
hablando fuerte. Y el aire de 400 ms que trae la libreria resulto ser demasiado: bajarlo a
100 gana un punto entero de WER y encima acelera.

Lo que salio al reves de la intuicion: **para hablar bajo no sirve un detector permisivo**.
Con umbral 0.35 el susurro empeora a 26.7% y con 0.25 a 46.7%. El motivo es mecanico: un
detector flojo encuentra "voz" adentro del ruido, devuelve algo en vez de vacio, y asi le
tapa la puerta al reintento sin VAD, que es lo que de verdad rescata un susurro.

**Reglas por horario**, separadas por coma: `00:00-06:00=bajo, 20:00-23:59=ruido`. Cruzan
la medianoche. Solo pisan al modo `auto`: si elegiste un modo a mano, el reloj no te lo
cambia, que es la misma regla que **Quien manda sobre un ajuste**.

Y una advertencia honesta: **el reloj es un proxy peor que el audio**. A las 3 AM podes
estar gritando en Discord. Lo correcto seria medir el ruido de fondo del propio clip y
elegir solo, pero no se puede validar con este banco --el cortador por silencio elimino
justo los silencios, que es donde vive el ruido, y por eso `ruido` y `propios` miden la
misma relacion senal-ruido, 23.1 dB los dos. Queda pendiente y necesita grabaciones sin
recortar.

### Despertarla diciendo su nombre

En **Voz**, apagado de fabrica: prenderlo deja el microfono abierto todo el tiempo, y eso
lo elige el usuario. Se le dice el nombre y la orden de un tiron, en la misma frase:

```
"Computadora, abri Spotify"
```

**Sin una sola dependencia nueva.** Porcupine cubre los cinco objetivos pero exige una
AccessKey de cuenta, y no podes embeber la tuya en un instalador que distribuis; los
modelos preentrenados de openWakeWord son CC-BY-NC y `tflite-runtime` no publica ruedas
aarch64; Vosk no tiene rueda para mac-arm64 ni linux-aarch64, o sea 3 de 5. Lo que sirve ya
estaba adentro de la casa: faster-whisper trae `silero_vad_v6.onnx` (1.2 MB) y depende de
onnxruntime, asi que los dos viajan en los cinco paquetes desde siempre.

Son dos etapas. Silero decide **cuando** hay voz --medido, **0.20% de un core**, que es lo
que puede estar prendido todo el dia-- y recien sobre ese pedazo corre un whisper chico que
decide **que** dijo. En reposo no corre ningun modelo de lenguaje. Como el recorte ya trae
la palabra Y la orden, no hace falta maquina de estados ni pitido en el medio.

**La palabra pesa mas que el modelo.** Cuatro ordenes y seis frases de control:

```
palabra              modelo   desperto   falsos
Computadora          tiny        4 / 4    0 / 6
Computadora          small       4 / 4    0 / 6
Eve (+ ebe, eva)     small       3 / 4    0 / 6
Eve (+ ebe, eva)     tiny        2 / 4    0 / 6
Eve (+ ebe, eva)     base        0 / 4    0 / 6
```

"Computadora" con el modelo mas chico le gana a "Eve" con uno cuatro veces mas grande, y
tarda menos de la mitad. **Tres letras no alcanzan para ser una puerta**, y no hay
heuristica difusa que lo arregle: aceptar una letra de diferencia sobre "eve" abre la
puerta a "ese", "ave" y "eco". Por eso la clave acepta variantes separadas por `|` y de
fabrica vienen las dos. Para ver como te escribe a vos:
`Eve --probar-voz "Eve, abri Spotify"`.

Cero falsos positivos en las seis de control, incluida *"le dije a Eve que abriera Steam"*
--la que rompe cualquier puerta que acepte la palabra en cualquier posicion. Por eso se
exige al principio.

Dos detalles que aparecieron midiendo y que no se ven de otra forma. La transcripcion **no
es determinista**: la libreria prueba temperaturas de 0 a 1.0 hasta que el resultado le
convence, asi que la misma onda daba `Eve, Avris, Spotify` una corrida y `Ede, Abris,
Spotify` la siguiente; para dictar da igual, para una puerta significa despertar al azar,
y por eso la puerta fija la temperatura en 0. Y servirle el catalogo de 80 juegos a un
modelo que solo tiene que reconocer un nombre lo empuja a escribir cualquier cosa menos ese
nombre: `Eve, abri Spotify` salia `Mb.Avris.phi.`.

**Lo que garantiza mientras esta prendido**: el buffer rodante vive en RAM y se pisa solo;
nada llega al disco salvo el segmento que disparo; pausar cierra el stream de verdad, no lo
ignora; y cada despertar queda anotado en el log de acciones.

**Con el juego y Discord de verdad.** Las seis frases de control de arriba son voz
sintetica en una habitacion en silencio: sirven para descartar lo obvio y no para decir si
esto se puede dejar prendido. Eso se midio aparte, con Rainbow Six corriendo y una
conversacion por Discord:

```
                            5 minutos     20 minutos
tramos de voz detectados      18 (21%)      113 (31% del tiempo hablando)
despertares                    0             3, y los tres eran ordenes de prueba
despertares espurios           0             0
el modelo de la puerta corrio  3.6/min       5.6/min
```

Los tres despertares de la corrida larga fueron la persona diciendo a proposito
"Computadora, abri Spotify" y "Computadora, pone el clima" en medio de la partida, y la
puerta los agarro. **Ninguno espurio en 25 minutos** de juego y conversacion.

Tres cosas que solo se ven asi:

- **El microfono ABRE** con los dos programas tomandolo. WASAPI en modo compartido
  convive, y esa era la duda principal antes de escribir la funcion.
- **El modelo de la puerta corre 5.6 veces por minuto**, no continuamente: son 368
  segundos con voz sobre 1200, y el resto es silero al 0.20% de un core. El costo de
  tener esto prendido esta acotado por cuanto hablas, no por cuanto dura la sesion.
- Uno de los despertares llego con la **orden vacia**: la puerta agarro el nombre y
  perdio el resto. Ahi Eve contesta "decime la orden junto con mi nombre", que es lo
  correcto, pero significa repetir. Es el caso a vigilar con ruido fuerte.

Y lo que el numero **no** dice: con cero espurios en 25 minutos, el techo al 95% queda en
unos 7 por hora. Alcanza para decidir que se puede dejar prendido; para afirmar "menos de
uno por hora" harian falta unas tres horas limpias.

El banco de esto no vive en el repo y hay una razon: **no puede distinguir un despertar
espurio de uno deliberado**. Su primera version imprimio "9.0 falsos positivos por hora" y
los tres eran la persona hablandole. Un numero con la etiqueta equivocada es peor que
ningun numero.


### La camara, y por que no

Se evaluo activarla por gestos vistos por la webcam. **No entra**, y no es una opinion:
**no existe ninguna version de mediapipe que cubra los cinco objetivos**. Las 0.10.20 a
0.10.35 no publican `aarch64`; de la 0.10.30 en adelante tampoco mac Intel; `aarch64`
vuelve recien en la 1.0.0, ya sin mac Intel. La ultima con las dos es la 0.10.18, de
noviembre de 2024, que pide `numpy<2` --y choca con el resto del proyecto-- mas `jax` y
`jaxlib`, que tampoco tiene rueda para mac Intel. Es el mismo caso que `cairosvg`.

Sin mediapipe no hay puntos de la mano, o sea que los gestos configurables mueren ahi.
Quedaria detectar cara si/no con `opencv-python-headless`, y **tampoco conviene**: son
+85 MB por objetivo (el wheel de linux-arm64 descomprime 85.6 MB), un permiso nuevo en tres
sistemas --y `packaging/macos/Info.plist` ni siquiera declara `NSCameraUsageDescription`--,
y sobre todo **la camara es exclusiva de facto**: tenerla tomada ocho horas significa que
no podes entrar a una reunion. El microfono no tiene ese problema porque Eve solo lo agarra
mientras apretas la tecla.

Y el valor que prometia ya lo da la arquitectura: Eve es push-to-talk, no escucha si no se
lo pedis. Si lo que se queria era activarla sin tocar nada, **la palabra clave es la misma
funcion cuarenta veces mas barata**: onnxruntime ya viaja en el paquete, no pide permiso de
camara y no se pelea con OBS.

Para que entrara habria que dejar de publicar para mac Intel. No es un capricho:
onnxruntime, mediapipe y jaxlib ya lo hicieron.

### Lo que encontro apenas se enchufo

Cuatro de esos clips volvian **vacios**, y no era el modelo: con el detector de voz
apagado, tres de los cuatro se transcribian perfecto. El VAD no "se come alguna palabra
dicha bajo" como decia el comentario en `voice.py`: se come **la frase entera**, y el
turno se pierde sin dejar rastro de por que.

Ahora, si con VAD no salio nada y el audio tenia senal, se reintenta una vez sin VAD. En
el caso normal no cuesta nada porque no se dispara, y cuando se dispara el turno ya
estaba perdido igual. No inventa texto sobre ruido: probado con silencio puro y con ruido
blanco a -30 y -20 dB, las tres veces devuelve vacio. El piso de -42 dBFS sale del mismo
banco, donde un susurro real pica en -27 y un clip inservible en -39.

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
| Sprite sheet | Aseprite, TexturePacker | el PNG y su JSON al lado |
| Particulas | Particle Designer, Particle2dx | el `.plist` de cocos2d |
| Vectorial | After Effects, LottieFiles | pendiente, ver abajo |

**Sprite sheets.** Aseprite y TexturePacker exportan un PNG con todos los cuadros pegados y
un JSON diciendo donde esta cada uno. El JSON se llama igual que la imagen, asi que no hay
ningun ajuste nuevo que tocar: se deja el par de archivos en la carpeta, se elige el PNG, y
si el JSON esta se usa. Andan los dos modos de exportacion --lista y diccionario-- porque
elegir el equivocado en el exportador no es culpa de nadie. Sin JSON, o con uno roto, sigue
siendo una imagen comun: un sprite sheet mal exportado no puede dejar de mostrar hasta la
imagen entera.

**Particulas por archivo.** Los editores de particulas exportan el `.plist` de cocos2d, que
es el formato con mas archivos publicados dando vueltas, y es **XML de numeros**: vida,
gravedad, color inicial, angulo, dispersion. `plistlib` esta en la stdlib, asi que no se
importa un runtime sino la CONFIGURACION, y la corre el simulador de numpy que ya existe.
Mismo criterio que con Graphify: se toma la arquitectura, no la dependencia.

Hay un detalle que solo aparece probandolo: **en cocos2d la `y` crece hacia arriba y en
pantalla crece hacia abajo**. Sin invertir el signo, una fuente importada dispara sus
particulas al piso. Lo que no viaja es lo que el simulador no sabe hacer --modo radial,
texturas por particula, mezclas aditivas y la varianza de cada parametro-- porque importar
mas seria guardar numeros que nadie lee. El boton llena los campos y **no** aplica: que un
archivo ajeno pise el modulo sin que lo veas es la misma sorpresa que el ajuste de
autoridad existe para evitar.

Todas comparten `velocidad`, `easing`, `escala`, `rotacion`, `opacidad`, `tinte`, `color`
y `cuando` (siempre, trabajando, al pasar el mouse). La que las separa es **`fuente`**:
`reloj` o `microfono`.

**Cualquier modulo puede reaccionar a tu voz**, no solo los dos que la calculan. Con
`fuente = microfono` el nivel del microfono agranda el modulo hasta un 35%, y `easing`
decide con que curva: `lineal` sigue el volumen tal cual, `suave` ignora los ruiditos y
exagera los picos, y `rebote` se pasa un poco de largo, que es lo que hace que algo
parezca vivo y no una barra de progreso. Asi late un GIF, un sprite sheet, un reloj o un
PNG quieto, que es justo lo que una animacion importada no puede calcular sola.

La onda y las particulas siguen siendo distintas: no se agrandan con tu voz, la **dibujan**
--la forma de la onda ES el historial de niveles-- y eso ninguna animacion importada lo
puede hacer.

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
| `banco_voz.py` | Mide el WER del reconocimiento sobre grabaciones reales, y compara modelos |
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
| `eve/despertar.py` | Palabra clave: silero decide cuando, un whisper chico decide que |
| `eve/tema.py` | Paletas por roles, para el panel y para el cartel |
| `eve/imagenes.py` | Fondos e iconos: PNG, GIF, APNG, WebP animado y sprite sheets, con cache |
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
