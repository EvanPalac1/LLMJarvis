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
| `ollama` | Un modelo local | `qwen3:8b` | Ollama corriendo |
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
| `propio` | la URL que le pongas |

**Cambiar de motor no pierde la conversación.** El historial se guarda en un
formato neutro —`ts`, `role`, `text`, `engine`— y los cuatro motores lo leen.
Podés arrancar con Ollama y seguir en la API sin repetir el contexto.

Las claves **no se guardan en texto plano**. El botón de probar el motor recorre
exactamente el mismo camino que el asistente: si el botón dice que anda, anda.

---

## Qué se le manda en cada turno

El prompt de sistema se arma en un solo lugar (`eve/prompt.py`) y **se puede ver
desglosado**: el módulo `contexto` dibuja cuánto pesa cada parte.

Medido sobre esta instalación, con el catálogo recortado y el modo ayuda en
`codigo`:

| Parte | Caracteres | |
|---|---:|---:|
| Integraciones (los comandos `E …`) | 5 458 | 46.1% |
| Tu resumen personal (`brief`) | 3 481 | 29.4% |
| Esquema de módulos (modo ayuda) | 1 352 | 11.4% |
| Tono | 435 | 3.7% |
| Encabezado del catálogo | 352 | 3.0% |
| Andamiaje de la plantilla | 333 | 2.8% |
| Catálogo de programas | 274 | 2.3% |
| Dialecto | 130 | 1.1% |
| Rutas, idioma, nombre | 34 | 0.3% |
| **Total** | **11 849** | ≈ 2 960 tokens |

La suma cierra exactamente con el prompt armado: el andamiaje es la plantilla con
los huecos vaciados, y hay un test que lo comprueba.

Dos ajustes mueven ese número de verdad:

| Ajuste | Total | Diferencia |
|---|---:|---|
| `catalogo_modo = usados` (de fábrica) | 11 849 | — |
| `catalogo_modo = completo` | 15 785 | **+3 936** (+33%) |
| `ayuda_alcance = codigo` o `datos` | 11 849 | — |
| `ayuda_alcance = nada` | 10 497 | **−1 352** (−11%) |

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
| Programas | `E programa NOMBRE`, más el catálogo |
| Addons | `E addon obs …`, `E addon spotify …` |

Todo lo que no entre en dos frases habladas **va a la ventana de actividad**, no
al navegador. Abrir Chrome para leer tres renglones es salirse del programa.

---

## Qué no puede hacer

Los frenos no son configurables desde adentro. Eso es a propósito.

**Seis claves que Eve nunca puede escribir**, ni con `E ajustar` ni pidiéndolo
amablemente:

```
confirm_destructive · workdirs · addons_aprobados
autoridad · claves_del_usuario · cc_permission_mode
```

Son exactamente las que le sueltan las manos. Se encontró que `E ajustar` podía
escribir las seis —incluida la de aprobar addons, o sea que todo el trabajo de
meter los addons bajo el freno era decorativo.

Lo demás:

- **Rutas permitidas.** Fuera de ellas el sistema pide confirmación, y
  `E mostrar --archivo` solo lee adentro.
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

### pocket-tts: la puerta de plataforma ya no lo bloquea

**Corrección.** Este apartado decía que pocket-tts estaba bloqueado por `torch`.
Eso valía para el camino oficial y ya no vale para el único que importa acá.

Lo bueno: código MIT, **pesos CC-BY-4.0** (son dos licencias distintas y conviene
no confundirlas), ~200 ms al primer fragmento, y **clonado de voz desde ~20 s de
audio**, que es algo que Piper no hace.

El bloqueo original, real: la ruta oficial en Python pide **`torch>=2.5.0`**, y
la última rueda de torch para **macOS Intel es la 2.2.2**. Ninguna versión
satisface las dos, y torch sumaría 116 MB en Windows, 106 en mac ARM, 502 en
Linux x64 y 407 en Linux ARM sobre instaladores de 133-229 MB.

**Pero torch no es el único camino, y el proyecto ya lleva el otro adentro.** El
propio repo de kyutai remite a `sherpa-onnx` para correr pocket-tts, y ahí los
números cambian de categoría:

| | ruta torch | ruta sherpa-onnx |
|---|---|---|
| Licencia del runtime | BSD | Apache-2.0 |
| mac Intel | **no existe** | `macosx_10_15_x86_64` ✅ |
| Los cinco objetivos | no | **sí, los cinco** |
| Peso por plataforma | 116-502 MB | **10-18 MB** |
| Dependencia nativa nueva | torch | ninguna: `onnxruntime` **ya viaja** |

O sea: la puerta que mató a mediapipe **no aplica por este lado**. Y `onnxruntime`
ya es dependencia dura del proyecto —la usan silero y parakeet— así que el costo
marginal es el binario de sherpa y los pesos, no un stack nuevo.

**Lo que sí sigue sin medirse, y es ahora la única razón para no enviarlo:**

1. **No hay WER de la voz en español.** Piper está medido re-transcribiendo:
   6.4%. pocket-tts tiene medidos RTF, latencia y tamaño — no calidad. Enviar un
   motor sin ese número sería exactamente el error por el que se rechazó Kokoro,
   al revés.
2. **El modelo en español es `spanish_24l`, de 24 capas.** El RTF de 0.17 y los
   100M parámetros son del inglés destilado de 6 capas. Cuatro veces las capas no
   se comparan de arriba: hay que medirlo aparte.
3. **Los pesos bajan en runtime** por `huggingface-hub`. Un asistente que arranca
   sin red no puede depender de eso sin una ruta de respaldo.

**La condición de reapertura, corregida.** La vieja —"si el proyecto deja de
soportar mac Intel"— era un disparador ajeno, que no depende del proyecto y que
además habría hecho entrar torch en piloto automático años después. La condición
buena es medible y propia:

> Entra cuando el WER de la voz en español, medido con el mismo banco de 24 clips
> y el mismo método de re-transcripción, quede por debajo del 6.4% de Piper; y su
> RTF real de 24 capas se mida en esta CPU, no se herede del modelo inglés.

Y sobre el clonado de voz: en un asistente local de un solo usuario, clonar la
voz propia no distribuye nada. La línea es no exportar ni guardar embeddings de
voces ajenas.

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
