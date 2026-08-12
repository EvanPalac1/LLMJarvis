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

### Dos procesos, una señal

El panel y el listener son procesos separados: el icono lanza `python -m eve.gui` aparte,
asi que si el panel se cuelga el listener sigue andando, y viceversa.

Al guardar, **el listener se rearma solo en unos segundos**. No hace falta tocar nada:
vigila el `mtime` de `config.json` en un hilo, y el archivo que el panel ya escribe *es*
la señal — no hay canal de IPC que mantener. Funciona igual si editas el JSON a mano.

Dos detalles que importan: espera a que el archivo deje de cambiar antes de releer
(guardar no es atomico, y a medio escribir el JSON es invalido), y no recarga mientras hay
un pedido de voz en curso — reintenta cuando termina.

**Reiniciar listener** sigue en el menu de la bandeja para forzarlo a mano.

El arranque automatico se elige durante la instalacion.

Windows 11 manda los iconos nuevos al desbordamiento ocultos. Para fijarlo visible:
arrastralo desde la flechita a la barra.

---

## Los tres motores

Se elige en el panel (**General > Motor**). Misma interfaz, distinto backend.

| | `api` | `claude-code` | `ollama` |
|---|---|---|---|
| Auth | `ANTHROPIC_API_KEY` | tu suscripcion | ninguna |
| Costo | por token | tu limite de uso | gratis |
| Datos | a Anthropic | a Anthropic | **no salen de tu PC** |
| Latencia | menor | mayor | depende de tu GPU |
| Tools | 4 propias | las de Claude Code | las mismas 4 |
| Freno | `safety.py` | hook `PreToolUse` | `safety.py` |

**Ollama es notablemente peor encadenando varias tools.** Para un pedido de un paso anda
bien; para tareas de varios pasos se pierde, y por eso corta a los 6 pasos en vez de 12.
Es el precio de no mandar nada a la nube, no un bug.

Reusa `brain.TOOLS` tal cual — Ollama acepta el mismo JSON Schema — y la misma ejecucion,
asi que el freno y el log de auditoria son identicos en los tres motores.

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
en el resto del prompt:

```
antes, sin manual:  10666 chars  (~2963 tokens)
ahora, con manual:   9554 chars  (~2653 tokens)
```

Los recortes: el catalogo abrevia la raiz del menu inicio a `SMU`/`SMP` (definidos una
vez en el encabezado) en vez de repetir `C:\Users\...\Start Menu\Programs` en cada linea,
y la lista de comandos usa el prefijo `E` en vez de repetir la ruta de Python y del script
diez veces. Ademas las reglas de comportamiento estaban duplicadas en los dos motores;
ahora viven solo en `EVE.md`.

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

Es una CLI (`eve/integrations.py`), asi que los dos motores la usan igual — el motor
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

---

## Arquitectura

```
keypad --> grabar --> faster-whisper --> [motor] --> SAPI (voz)
                                            |
                                    freno de confirmacion
                                            |
                                 SQLite (historial + auditoria)
```

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
| `eve/voice.py` | STT (faster-whisper / OpenAI) y TTS (SAPI / ElevenLabs) |
| `eve/store.py` | config.json, keyring, SQLite, ventana de contexto |
| `eve/gui.py` | Panel tkinter |
| `eve/tray.py` | Icono de bandeja |
| `eve/icon.py` | Genera el icono |

---

## Desarrollo

```bash
python test_eve.py       # freno, allowlist, contexto, indice, fuga de hooks
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
