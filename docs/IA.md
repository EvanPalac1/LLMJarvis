# Qué hace la IA, y cuánto cuesta

Qué modelo corre en cada parte de Eve, qué se le manda, qué puede hacer y qué no,
y los números con los que se eligió cada cosa.

Todos los benchmarks de esta página se midieron en esta máquina con el banco del
proyecto. Ninguno viene de una hoja de datos ajena. El detalle de cómo se midió
cada uno está en el [README](../README.md).

---

## Las cuatro cabezas

Eve no es un modelo: son **cuatro motores intercambiables** detrás de la misma
interfaz. Se elige en **Panel → General → Motor**.

| Motor | Qué es | De fábrica | Necesita |
|---|---|---|---|
| `api` | La API de Anthropic directo | `claude-opus-5` | Una clave |
| `claude-code` | El CLI de Claude Code, con sus herramientas | `sonnet` | El CLI instalado |
| `ollama` | Un modelo local | el que tengas bajado | Ollama corriendo |
| `compat` | Cualquier API estilo OpenAI | Gemini `gemini-flash-latest` | Una clave, o nada si es local |

El motor `compat` trae presets para no ir a buscar la URL:

| | Modelo sugerido |
|---|---|
| `gemini` | `gemini-flash-latest` |
| `openai` | `gpt-5-mini` |
| `groq` | `llama-3.3-70b-versatile` |
| `deepseek` | `deepseek-chat` |
| `openrouter` | `deepseek/deepseek-chat-v3.1:free` |
| `xai` | `grok-4-fast` |
| `lmstudio` | local, sin clave |
| `omniroute` | local, **con** clave: es una pasarela |
| `propio` | la URL que le pongas |

**El botón `Buscar modelos`** se los pregunta al servicio en vez de que tengas
que saber el identificador exacto. `GET /v1/models` es parte del protocolo, así
que lo contestan los tres tipos: la nube, el local y el propio.

**Quién pide clave lo dice el proveedor, no el host.** La regla era "si escucha
en localhost no pide clave", y valía mientras los únicos locales eran LM Studio
y Ollama, que efectivamente no piden. **OmniRoute la rompe**: corre en tu
máquina y sí pide una, emitida por su propio panel —es una pasarela, y por
detrás habla con decenas de proveedores con tus claves de ellos—. Con la regla
vieja pasaba la comprobación y fallaba con un 401 a mitad de la primera
respuesta, que es justo lo que esa comprobación existe para evitar.

`propio` conserva la excusa del localhost: ahí la URL la ponés vos y puede
apuntar a cualquier cosa —un `llama.cpp` suelto no pide nada—, así que exigirle
una clave sería inventarle un requisito.

**Cambiar de motor no pierde la conversación.** El historial se guarda en un
formato neutro —`ts`, `role`, `text`, `engine`— y los cuatro motores lo leen.
Podés arrancar con Ollama y seguir en la API sin repetir el contexto.

Las claves **no se guardan en texto plano**. El botón de probar el motor recorre
exactamente el mismo camino que el asistente: si el botón dice que anda, anda.

**Un motor que no se puede armar NO impide que Eve abra.** Si Ollama está
apagado, la key venció o el CLI no está logueado, Eve arranca igual: la tecla,
el ícono de bandeja y el panel funcionan, te avisa qué le falta y te abre el
panel para arreglarlo. Lo único que no va a poder es contestarte, y cuando le
hablás te lo dice en vez de quedarse muda.

Antes no: el motor se armaba en el arranque y si fallaba Eve se iba con error,
o sea que **no abría nada** —ni siquiera la ventana que hacía falta para
arreglarlo—. Y el motor que fallaba no tenía por qué ser el que usabas: bastaba
con que `engine` hubiera quedado apuntando a Ollama para que alguien que solo
quería su API key se quedara sin poder abrir. Además se reintenta solo, porque
lo que falla suele ser algo de afuera —Ollama que todavía no arrancó, la red,
el CLI recién instalado— y eso se arregla sin tocar ningún ajuste.

**Y `ollama` no exige un modelo en particular.** Si el que dice la config no
está pero hay otros bajados, usa uno. `qwen3:8b` es el valor de fábrica, o sea
un nombre que nadie eligió, y plantarse con *"no tengo qwen3:8b"* teniendo un
Ollama sano con modelos adentro es negarse por un detalle que al usuario no le
importa. Si querés uno exacto, escribilo en el panel: ahí sí manda, porque
entonces es una elección.

---

## Qué se le manda en cada turno

El prompt de sistema se arma en un solo lugar (`eve/prompt.py`) y **se puede ver
desglosado**: el módulo `contexto` dibuja cuánto pesa cada parte.

Medido sobre esta instalación, todo de fábrica:

| Parte | Caracteres | |
|---|---:|---:|
| Integraciones (los comandos `E …`) | 5 494 | 50.3% |
| Tu resumen personal (`brief`) | 3 481 | 31.8% |
| Tono | 421 | 3.9% |
| Encabezado del catálogo | 352 | 3.2% |
| Catálogo de programas | 349 | 3.2% |
| Andamiaje de la plantilla | 333 | 3.0% |
| Vocabulario de interfaz | 310 | 2.8% |
| Dialecto | 145 | 1.3% |
| Rutas, idioma, nombre | 45 | 0.4% |
| **Total** | **10 930** | ≈ 2 730 tokens |

La suma cierra exactamente con el prompt armado: el andamiaje es la plantilla con
los huecos vaciados, y hay un test que lo comprueba.

Cuatro ajustes mueven ese número de verdad:

| Ajuste | Total | Diferencia |
|---|---:|---|
| **de fábrica** | 10 930 | — |
| `catalogo_modo = completo` | 14 791 | **+3 861** (+35%) |
| `ayuda_vocabulario = completo` | 11 972 | **+1 042** (+9.5%) |
| `ayuda_vocabulario = minimo` | 11 105 | +175 (+1.6%) |
| `archivos_alcance = escribir` | 11 279 | +349 (+3.2%) |
| `archivos_alcance = explorar` | 11 177 | +247 (+2.3%) |
| `ayuda_alcance = nada` | 10 620 | −310 (−2.8%) |

**El que más sorprende es `ayuda_vocabulario`, porque hasta hace poco no
existía y su valor era el caro.** El diccionario entero de módulos —los trece
tipos con todas sus props, 1 352 caracteres— viajaba en **cada** llamada,
incluida "qué hora es". Y de las 121 opciones de config que Eve sí puede
escribir, no viajaba ninguna: adivinaba el nombre de la clave, `E ajustar`
contestaba *"No existe la opción X"*, y reintentaba. Se pagaba siempre por lo
que casi nunca se usa, y **una vuelta perdida cuesta una llamada entera**,
bastante más que 1 352 caracteres.

De fábrica ya no lleva el diccionario: lleva **cómo pedirlo**. `E ui buscar
transparencia` devuelve la clave exacta, cuánto vale ahora y qué valores acepta,
buscando sobre el mismo índice que dibuja el buscador del panel —o sea que lo
que Eve encuentra es exactamente lo que vos ves, y no una segunda lista que se
despega. Se paga una consulta extra las veces que sí toca la interfaz, y se
ahorra el 9.5% en todas las demás. Si preferís lo de antes, `completo` sigue
estando.

Los dos de `archivos_alcance` **suman en vez de restar**, y eso es lo correcto:
son capacidades que de fábrica Eve no tiene. Lo que importa de esa fila es que
con `exacto` el costo es **cero** —no aparece ni el nombre del comando— en vez
de mandar una capacidad apagada y esperar que no la use.

El catálogo recortado manda solo los programas que aparecen en el log de uso. Si
Eve no encuentra uno, lo busca con `E programa`: recortar no le quita capacidad,
le quita peso muerto.

Y **el consumo real se guarda**: la tabla `turns` lleva `engine`, `tokens_in`,
`tokens_out` y `cache_read` por turno. Ollama devuelve `prompt_eval_count` y
`eval_count`; los demás, `usage`.

---

## Qué puede hacer

La IA no ejecuta lo que se le ocurre: emite **comandos con nombre**, y cada uno
tiene su implementación del lado de Eve.

| Grupo | Ejemplos |
|---|---|
| Mostrar | `E mostrar --texto`, `E mostrar --archivo` (txt, md, html) |
| Recordar | `E recordar`, `E recordado TEMA` |
| Mensajería | `E componer`, `E whatsapp-enviar`, `E discord-postear` |
| Correo | `E outlook-leer`, `E outlook-contacto`, `E gmail-enviar` |
| Web | `E leer URL` (texto limpio, sin publicidad), `E buscar` |
| La propia Eve | `E modulo crear`, `E modulo editar`, `E perfil aplicar`, `E ajustar` |
| Buscar un ajuste | `E ui buscar <palabras>`, `E ui ver CLAVE` |
| Archivos | `E archivo listar`, `E archivo buscar`, `E archivo escribir` — solo los que `archivos_alcance` habilite |
| Programas | `E programa NOMBRE`, más el catálogo |
| Addons | `E addon obs …`, `E addon spotify …` |

Todo lo que no entre en dos frases habladas **va a la ventana de actividad**, no
al navegador. Abrir Chrome para leer tres renglones es salirse del programa.

---

## Qué no puede hacer

Los frenos no son configurables desde adentro. Eso es a propósito.

**Nueve claves que Eve nunca puede escribir**, ni con `E ajustar` ni pidiéndolo
amablemente:

```
confirm_destructive · workdirs · addons_aprobados · autoridad
claves_del_usuario · cc_permission_mode · ayuda_alcance · archivos_alcance
skills_alcance
```

Son exactamente las que le sueltan las manos. Se encontró que `E ajustar` podía
escribir las seis primeras —incluida la de aprobar addons, o sea que todo el
trabajo de meter los addons bajo el freno era decorativo.

**`skills_alcance` es la novena, y la atrapó el mismo test el día que se
agregó.** Parece de la familia de `ayuda_vocabulario` —las dos deciden cuánto
texto viaja— y no lo es: pasarla de `nada` a `consultar` hace *existir*
`E skill ver`, o sea que le da acceso a archivos tuyos que antes no podía leer.
Cuánto viaja no compra permisos; que el comando exista, sí. Por eso
`ayuda_vocabulario` sigue fuera de la lista y esta entró.

**Las dos anteriores se sumaron por el mismo camino.** Son los dos
techos que elegís vos —hasta dónde arma sola, y hasta dónde llega con los
archivos— y estuvieron escribibles por ella hasta que se agregaron: con
`ayuda_alcance` suelta podía pasarse de `datos` a `codigo` y habilitarse a
dejar escrito un addon `.py`; con `archivos_alcance` suelta, de `exacto` a
`escribir`. **Un techo que el limitado puede subir no es un techo.** El chequeo
que debía atraparlas era una heurística sobre el nombre de la clave que no
miraba la palabra `alcance`; ahora la mira, así que la tercera que aparezca no
va a depender de que alguien se acuerde.

Lo demás:

- **Rutas permitidas.** Fuera de ellas el sistema pide confirmación, y
  `E mostrar --archivo` solo lee adentro. `archivos_alcance` decide qué hace
  **dentro** de esas rutas, sin agrandarlas nunca: `exacto` (de fábrica) solo
  lee una ruta que le dictes, `explorar` además lista y busca por nombre, y
  `escribir` además crea y reemplaza —pisar un archivo que ya existe pasa por
  la misma confirmación que los destructivos, y queda en el log de acciones.
- **Acciones riesgosas de addons.** Cada addon declara sus riesgos y pasa por el
  mismo freno que todo lo demás, que es *fail-closed*: lo que no reconoce, lo
  pregunta.
- **Modo ayuda en tres niveles**, no un interruptor: `nada` | `datos` (de
  fábrica) | `codigo`. Con `nada`, el vocabulario de módulos ni siquiera viaja
  en el prompt.
- **Autoridad por ajuste**: `usuario` (lo que tocaste queda trabado y Eve no lo
  pisa) | `eve` | `preguntar`.
- **Los addons de código completo se muestran antes de instalarse.**

---

## Reconocer lo que decís (STT)

Banco propio: **24 clips grabados acá**, en seis grupos —limpio, nombres propios,
lejos, con ruido, rápido, susurro— con las transcripciones de referencia escritas
a mano. Viven en la carpeta de datos y **no en el repo**: son la voz de una
persona.

WER por grupo, en porcentaje (más bajo es mejor):

| modelo | lejos | limpio | propios | rápido | ruido | susurro | **TOTAL** | orden de 2 s |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `small` | 15.2 | 3.2 | 21.7 | 22.2 | 12.5 | 0.0 | **10.9** | 0.9 s gpu / 3.3 s cpu |
| `medium` | 0.0 | 1.6 | 17.4 | 22.2 | 0.0 | 0.0 | **4.9** | 1.8 s gpu / 10.2 s cpu |
| `large-v3` | 0.0 | 1.6 | **34.8** | 0.0 | 0.0 | 0.0 | **4.9** | 2.7 s gpu |

**Más grande no es mejor.** `large-v3` es el doble de malo en nombres propios que
`medium` y tarda 50% más. Y `medium` conviene **solo con GPU**: en CPU una orden
de dos segundos tarda diez.

El vocabulario como `initial_prompt` casi no sirve: 30.4% → 26.1% en nombres
propios, y servirle los nombres exactos deja el mismo 26.1%. El problema es
acústico, no de vocabulario.

### Parakeet TDT: entra como opción

| sistema | TOTAL | RTF | disco |
|---|---:|---:|---:|
| whisper `small` en gpu | 10.9% | 0.27 | 464 MB |
| whisper `small` en cpu | 10.9% | 1.38 | 464 MB |
| whisper `medium` en gpu | 5.4% | 0.61 | 1.5 GB |
| **parakeet v3 int8 en CPU** | 7.1% | **0.19** | 639 MB |

Lo que decide es que ese 0.19 es **en CPU**, donde whisper `small` tarda siete
veces más — y la mayoría de las instalaciones no tienen CUDA. No es el default
porque pierde en nombres propios (30.4% contra 21.7%) y no acepta sesgo de
vocabulario. Cuesta **cero dependencias nativas nuevas**.

### Tres bugs que solo aparecen con audio real

Ninguno se ve con audio sintetizado:

1. El detector de voz devolvía **vacío en 4 de 24 clips, todos susurrados**.
   Apagándolo, 3 de esos 4 transcribían perfecto. Se arregló reintentando sin
   detector cuando el resultado sale vacío y el pico supera −42 dBFS. Susurro:
   **100% → 0.0%**.
2. El aire que trae la librería (400 ms) es demasiado: bajarlo a 100 gana un
   punto entero de WER y acelera.
3. La transcripción **no es determinista** (escalera de temperatura). Para dictar
   da igual; para una puerta de palabra clave es fatal.

### Sensibilidad por modo

Tres modos con valores medidos, no elegidos:

| modo | umbral / silencio | qué resuelve |
|---|---|---|
| `normal` | 0.5 / 100 ms | 10.9% general |
| `ruido` | 0.85 / 250 ms | su grupo pasa de 18.8% a **0.0%** |
| `bajo` | 0.5 / 250 ms | hablar bajo |

**Contraintuitivo y medido:** para hablar bajo *no* sirve un detector permisivo.
Con 0.35 el susurro empeora a 26.7%, con 0.25 a 46.7%. Un detector flojo
encuentra "voz" en el ruido, devuelve algo en vez de vacío, y le tapa la puerta
al reintento sin VAD, que es lo que de verdad rescata un susurro.

Hay reglas de horario (`00:00-06:00 = bajo`, `20:00-23:59 = ruido`) que **solo
pisan al modo `auto`**: un modo elegido a mano no lo cambia el reloj.

---

## La palabra clave

Dos etapas y **cero dependencias nuevas**: silero decide *cuándo* hay voz
—**0.20% de un core**, medido— y sobre ese recorte corre un whisper chico que
decide *qué* dijo.

| palabra | modelo | despertó | falsos |
|---|---|---:|---:|
| `Computadora` | tiny | **4 / 4** | 0 / 6 |
| `Eve` (+ ebe, eva) | small | 3 / 4 | 0 / 6 |
| `Eve` (+ ebe, eva) | tiny | 2 / 4 | 0 / 6 |

**La palabra pesa más que el modelo.** Tres letras no alcanzan para ser una
puerta. La clave acepta variantes separadas por `|`.

**Medido en uso real** (Rainbow Six + Discord, 25 minutos en dos corridas): ~131
tramos de voz detectados, hablando el 21-31% del tiempo, **cero despertares
espurios**. El micrófono abre con los dos programas tomándolo, y el modelo de la
puerta corre 5.6 veces por minuto, no continuamente.

Con cero espurios en 25 minutos el techo al 95% de confianza queda en ~7 por
hora: alcanza para decidir que se puede dejar prendido, no para afirmar "menos de
uno por hora".

---

## Hablar (TTS)

Medido **re-transcribiendo lo que el motor sintetizó**: si el reconocedor no la
entiende, vos tampoco.

| voz | WER al re-oírla | RTF |
|---|---:|---:|
| `es_ES-sharvard-medium` | **6.4%** | — |
| `es_MX-claude-high` | 6.8% | 0.30 |
| `es_MX-davefx-medium` | 8.4% | — |
| `es_AR-daniela-high` | **20.5%** | 1.07 |

`daniela-high` es la peor voz medida de todas, y es la única rioplatense de
calidad `high`. Que una voz suene prometedora de nombre no dice nada.

**El juez importa, y esa tabla no lo decía.** Re-medido con whisper `medium`
como oyente, en una sola corrida y en la misma CPU:

| voz | WER | RTF |
|---|---:|---:|
| `es_MX-claude-high` | **2.2%** | 0.113 |
| `es_ES-sharvard-medium` | 6.0% | 0.145 |

`sharvard` reproduce (6.4 → 6.0); `claude-high` no (6.8 → 2.2). La diferencia es
el modelo que re-oye, no la voz: un juez mejor perdona menos y castiga distinto.
**Las dos tablas solo son comparables adentro de sí mismas** — por eso el
veredicto de abajo mide todo en la misma corrida en vez de comparar contra el
número escrito.

---

## Lo que Eve recuerda

`MEMORIA.md` viaja en cada llamada, así que crece hasta comerse el presupuesto.
La poda elige los hechos **siguiendo enlaces**: dos cosas están ligadas si algún
hecho las nombra a las dos, y se sigue hasta **dos enlaces** desde lo que Eve
viene haciendo. Un dato del router es relevante hablando de Minecraft si algún
hecho menciona los dos.

Medido sobre un caso con respuesta conocida —3 hechos que importan y 50 de
relleno, con presupuesto para pocos:

| enlaces | relevantes que entran | ruido |
|---:|---|---:|
| 0 (solo lo reciente) | 1 de 3 | 5 |
| **2** | **3 de 3** | **3** |
| 3 | 3 de 3 | 3 |

Con 3 no cambia nada: el grafo de una memoria real es chato. Si la memoria es
densa —pocos temas que se repiten— dos enlaces alcanzan todo y el criterio se
degrada al anterior. No elige peor: deja de aportar.

**El grafo no se guarda.** Armarlo son **0.6 ms con 200 hechos**, así que
persistirlo sería mantener un caché que puede quedar viejo a cambio de
microsegundos.

El tope de tokens es **duro**: antes se reservaba el pie después de elegir, así
que `podar(400)` devolvía 402 y `podar(800)` devolvía 810.

---

## Lo que se probó y no entró

Un "no" medido es un resultado. Estos se descartaron con datos, no por gusto.

| | Por qué no |
|---|---|
| **Kokoro** (TTS) | Empata en inteligibilidad (6.0%) con una voz de Piper **2.5× más rápida y 3× más chica**. Su versión cuantizada es *más lenta* (RTF 1.88 contra 0.74). Tres voces en español, ninguna rioplatense |
| **whisper `large-v3`** | Doble de errores en nombres propios que `medium`, y 50% más lento |
| **mediapipe** (gestos por cámara) | **Ninguna versión cubre los cinco objetivos.** La última con `aarch64` y mac Intel a la vez es la 0.10.18, que pide `numpy<2` más `jax`/`jaxlib`, que tampoco tiene rueda mac Intel. Aparte, la cámara es exclusiva de facto: tenerla tomada ocho horas es no poder entrar a una reunión |
| **Porcupine** (palabra clave) | AccessKey de cuenta: no se puede embeber en un instalador |
| **openWakeWord** | Modelos CC-BY-NC y sin ruedas `aarch64` |
| **Vosk** | Cubre 3 de 5 objetivos |
| **whisper continuo** como puerta | Un core entero, permanentemente |
| **Graphiti** (memoria) | Una llamada al LLM por ingesta, sobre un presupuesto de ~5 s por turno, más Neo4j |
| **Cliente MCP** | Los addons ya son el sistema de plugins y andan en los cuatro motores |
| **pocket-tts** | Ver abajo |

### pocket-tts: medido, y pierde

**Doble corrección.** Este apartado dijo primero que pocket-tts estaba bloqueado
por `torch`, y después que la puerta de plataforma se había caído. Las dos cosas
eran ciertas a medias. Ahora está medido con el banco propio y la respuesta es
clara.

**La puerta de plataforma sí se cayó.** El camino oficial pide `torch>=2.5.0`
contra la última rueda de torch para macOS Intel, que es la 2.2.2 — pero no es el
único camino. `sherpa-onnx` corre pocket-tts, publica rueda para **los cinco
objetivos** (`macosx_10_15_x86_64` incluida), es Apache-2.0, pesa 10-18 MB por
plataforma, y `onnxruntime` **ya viaja** en el proyecto. Comprobado cargando los
dos modelos, no leyendo el README.

**Y no importa, porque el motor pierde en todo lo que se puede medir.** Las 24
frases del banco, sintetizadas por cada motor y re-transcritas con whisper
`medium` como juez:

| motor | WER | RTF |
|---|---:|---:|
| **piper `es_MX-claude-high`** | **2.2%** | **0.113** |
| piper `es_ES-sharvard-medium` | 6.0% | 0.145 |
| pocket-tts español int8 | **16.8%** | **0.800** |

**7.6 veces más errores y 7 veces más lento.** Y no es un grupo que lo hunde:
pierde en los seis.

| | lejos | limpio | propios | rápido | ruido | susurro |
|---|---:|---:|---:|---:|---:|---:|
| piper `claude-high` | 3.0 | 0.0 | **13.0** | 0.0 | 0.0 | 0.0 |
| pocket-tts | 9.1 | 11.1 | **52.2** | 5.6 | 15.6 | 20.0 |

El peor grupo es el que más importa: **nombres propios, 52.2%**. En órdenes
cortas —`Abre Minecraft`, `Abre YouTube Kids`— devolvió **audio vacío**. Un
asistente de voz dice justamente frases cortas con nombres propios.

**Dos cosas más que aparecieron midiendo, y que ninguna hoja de datos dice:**

- **El RTF de 0.17 no es de esta máquina.** Acá da 0.800. Ese número venía de un
  M4, y comparado contra el Piper medido el mismo día en la misma CPU, la
  relación se da vuelta.
- **`kyutai/pocket-tts` es un repo con acceso restringido.** Las ocho voces
  predefinidas dan `401 GatedRepoError`: piden cuenta de Hugging Face con acceso
  aprobado a mano. Es el mismo modo de falla que descartó a Porcupine — una
  credencial de cuenta no se puede embeber en un instalador. Lo medido acá usa
  clonado desde un wav local, que sí funciona sin cuenta.

También quedan corregidos dos datos que este documento tuvo mal: la voz `lola`
**no existe** (las del bundle son `alba`, `azelma`, `cosette`, `eponine`,
`fantine`, `javert`, `jean`, `marius`), y el español destilado tiene **6 capas**,
no 24 — `spanish_24l` es la variante grande, aparte. Y la licencia son dos: el
código es MIT, **los pesos CC-BY-4.0**.

**Veredicto: no entra**, y ya no por una puerta de plataforma sino por el mismo
criterio que dejó afuera a Kokoro y a `large-v3` — se midió y perdió. El clonado
de voz es real y Piper no lo tiene, pero cuesta 7.6× el error, 7× el tiempo y 158
MB contra 60, para una capacidad que se usa una vez.

Se reabre si publican un modelo en español que **baje del 6.0%** con este mismo
banco. El número, no la promesa.

---

## La regla

Ninguna dependencia entra sin pasar dos puertas, y ninguna capacidad se envía sin
un número:

1. **Licencia** verificada, no asumida.
2. **Ruedas para los cinco objetivos**: win-x64, mac-x64 (Intel), mac-arm64,
   linux-x64, linux-arm64.
3. **Una medición que la justifique.** Sin mejora medida, no entra. Es lo que
   dejó afuera a Kokoro y a `large-v3`.

Y una que aplica a lo que ya está adentro: el modo `auto` de sensibilidad **no se
envía**, porque el banco actual no lo puede validar — el cortador por silencio
eliminó justo los silencios, que es donde vive el ruido de fondo. Mandar una
función que no se puede medir sería justo lo que este proyecto no hace.
