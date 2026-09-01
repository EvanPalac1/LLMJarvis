# Handshake · Eve (LLMJarvis)

Status: complete · 2026-08-27

> Este documento vive en el archivo del plan porque el modo plan no deja
> escribir otros archivos. Al salir, se mueve a `handshake_eve.md` en el repo.

## La idea en palabras simples

Eve es un programa que vive en tu computadora y te escucha. Le hablás y hace
cosas: abre programas, escribe mensajes, busca archivos. No piensa sola. Le
manda lo que dijiste a una inteligencia artificial grande, y esa contesta.

Eve no es solo tuya. Cualquiera la puede bajar. Por eso tiene que andar en cinco
tipos de computadora, no solo en la tuya.

Hay un problema y es uno solo: la pantalla de configuración es fea. Vos dibujaste
cómo tenía que quedar, y lo que hay no se parece. Ese es el dolor. No es que el
código sea difícil de tocar. No es que falten funciones. Es que no se ve bien.

Entonces vamos a rehacer esa pantalla con las mismas piezas con las que se hacen
las páginas web. Son buenas para esto: saben hacer esquinas redondeadas,
sombras, y respetan las medidas que uno les dice. La de ahora no.

El orden es este. Primero dibujamos las nueve pantallas, todas, antes de escribir
una línea. Vos las mirás y las corregís en el dibujo, que es barato. Después
probamos que la ventana web se pueda abrir en los cinco tipos de computadora.
Recién ahí escribimos.

Cuando la reescribamos, aprovechamos y acomodamos tres cosas que hoy están mal
puestas. Cuando elegís quién piensa por Eve, ahí mismo van a estar su modelo y su
clave, en vez de estar repartidos en tres lugares, que es por lo que hoy te dice
que el modelo no existe: tenés elegido uno y guardado el de otro. Las skills se
mudan al mismo lugar que los addons. Y vas a poder prender y apagar de a una las
skills y los servidores MCP.

El cartel que flota en pantalla es aparte. Hoy se ve bien: lo dibuja un pintor
propio y hasta usa la placa de video. Pero puede que la ventana web no sepa ser
transparente en Windows, y entonces quedaría un rectángulo opaco tapando cosas.
Así que primero lo probamos, un día de trabajo. Si sale, lo movemos. Si no sale,
se queda como está.

También hay que arreglar que Eve despierte cuando decís su nombre, porque hoy
anda mal por cinco motivos distintos. No corre apuro: sale todo junto con la
pantalla nueva, no antes.

Y del proyecto ajeno que pediste mirar sirve una sola cosa, chica: un modelo que
escucha y se da cuenta de cuándo terminaste de hablar. Hoy Eve espera un tiempo
fijo, siempre el mismo, y por eso a veces corta cuando estás pensando y a veces
hace esperar cuando ya terminaste.

## Por qué importa

**El dolor principal es cómo se ve.** No es el mantenimiento, no es el costo de
sumar funciones, no es la accesibilidad. Es que el panel no se parece al diseño.
Con tus palabras: *"muy bonito lo que se hizo con el /design pero no lo veo nada
parecido a lo que hay en realidad"*.

Eso ordena todo lo demás:

- **El éxito se mide con capturas contra el diseño**, no con líneas de código.
- **La accesibilidad es un beneficio de regalo, no el motivo.** Conviene decirlo
  porque yo la venía tratando como el argumento principal y no lo es. Igual es
  real y medible: con el árbol de UI Automation de Windows, que es lo que leen
  NVDA y el Narrador, el panel de hoy expone **0 controles con nombre de 68
  descendientes**. Pasar a HTML lo arregla solo, sin trabajo extra.
- **Lo que se elija tiene que andar en los cinco sistemas.**

## Para quién es

**Cualquiera que la baje.** Es un producto, no una herramienta personal.

Coincide con lo que el repo ya hace: público, MIT, 7 instaladores para 5
sistemas, actualización automática, panel en español e inglés.

## Qué hay hoy

Hechos verificados leyendo el código.

**Forma del programa.** Un binario que despacha por bandera: `Eve.exe`,
`--panel`, `--overlay`, `--consola`. Son **cuatro procesos** y no hay canal de
comunicación entre ellos: se hablan por archivos JSON en la carpeta de datos.

**El panel.** `eve/gui.py`, **4 911 líneas**, una sola clase, nueve pestañas. Lo
que se genera solo desde `registro.py` sale de un intérprete de 79 líneas sobre
unos 140 nodos declarativos. El resto, entre **1 300 y 2 500 líneas** según qué
se cuente, es interfaz escrita a mano.

**El registro.** `eve/registro.py` describe el panel como datos y trae su propia
regla escrita: *"si más de un tercio de una pestaña son excepciones, esa pestaña
no se migra"*. Hay 79 campos, 5 interruptores, 45 ayudas, 17 botones, 26
secciones y **10 excepciones** (`Propio`). El árbol crudo **no se puede pasar a
JSON tal cual**: al serializar un NamedTuple se pierde el nombre de la clase y un
campo y un interruptor quedan indistinguibles.

**El cartel y la ventana de actividad.** `eve/overlay.py` (912 líneas) y
`eve/consola.py` (1 307). Canvas de tkinter, procesos aparte, y **no importan
nada de `gui.py`**. El cartel es sin borde, siempre encima, con color
transparente, deja pasar los clics, y alterna eso cuadro a cuadro según si el
puntero está sobre un módulo interactivo.

**El despertar por nombre.** Roto por varias causas medibles, detalladas abajo.
Apagado en la config real: prendido el 20/08 16:12, apagado 16:23.

**Servidor web.** No hay ninguno. Solo clientes. Habría que introducir uno.

**Dependencias.** Doce de núcleo, con una regla escrita: no entra la que no
publique para los cinco objetivos. Ya rechazó `mediapipe`, `cairosvg`,
`pyopengltk`, `Vosk`, `openWakeWord` y `Porcupine`, cada uno con su medición.

**Agentes.** Existe **uno solo**, `.claude/agents/qa-eve.md`, que es el tester.
No hay builder, researcher ni planner en disco, ni en `~/.claude/agents/` (esa
carpeta no existe), ni en ningún `settings.json`.

## Qué sería el éxito

**Que el panel se parezca al diseño.** Se mide mirando: capturas del panel nuevo,
pestaña por pestaña, en tema claro y oscuro, al lado de los artboards.

**Contra qué se compara: las nueve pestañas dibujadas antes de codear.** El
`/design` que ya existe cubre unas tres. Se dibujan las otras seis primero.

Criterios de apoyo, que salen solos si el principal se cumple:

- Un lector de pantalla encuentra y nombra los controles. Hoy: 0 de 68.
- Las cinco compilaciones en verde antes de cada tag.

## Decisiones ya tomadas

Cerradas. El plan no las reabre.

1. **El frontend va a HTML y CSS**, no a Qt.
2. **Webview embebido** (pywebview), no el navegador del sistema.
3. **Migrar primero, arreglar la interfaz en el panel nuevo.**
4. Eve es para cualquiera que la baje.
5. El dolor principal es cómo se ve.
6. **Las nueve pantallas se dibujan antes de escribir código.**
7. **No hay apuro por sacar versiones.** Nada sale hasta que el panel nuevo esté
   listo, incluido el arreglo del despertar.
8. **El cartel se queda en Canvas.** Cerrada el 29/08 con la medición hecha, no
   con una opinión. La evidencia está en `medidas/pywebview/`: con color clave
   negro la ventana sale un rectángulo blanco opaco, y con el mecanismo real de
   Eve (la página pintando el color clave, igual que `-transparentcolor`)
   desaparece entera, la tarjeta incluida. Encima, calar por color sobre una
   superficie web hace que **cualquier píxel del contenido que coincida con el
   color clave se vuelva un agujero**, y el cartel muestra texto del usuario:
   eso mata la idea aunque la transparencia llegara a funcionar.
   **No se vuelve a medir.** El panel nuevo en HTML convive con el cartel de
   siempre; `overlay.py` y `consola.py` no importan nada de `gui.py`, así que
   conviven sin tocarse.

9. **El lazo puede usar git, SOLO en ramas descartables.** Cambiado el 29/08.
   Puede commitear y empujar a ramas con prefijo `medida/`, para poder correr
   la CI y medir en los cinco objetivos. **Nunca `main`, nunca un tag, nunca una
   release.** El resto del trabajo sigue quedando sin commitear para que lo
   revises.

## Decisiones todavía abiertas

Solo vos las podés cerrar. Cada una con mi recomendación, para que el planner
nunca quede trabado.

1. ~~A dónde va el cartel.~~ **CERRADA el 29/08: se queda en Canvas.** Ver
   decisión tomada 8.
2. **Cuánto tiene que parecerse al diseño.**
   · Recomendación: que se note que es el mismo sistema (mismos colores,
   espaciados, radios, tipografía), no pixel por pixel. Pixel por pixel duplica
   el trabajo por pestaña y nadie lo nota.
3. **Cuánto puede crecer el instalador.** Hoy pesa 387 MB; Qt costaba +92 MB.
   · Recomendación: tope de +50 MB. Si pywebview con `pythonnet` lo pasa, se
   revisa.
4. **Si el despertar sigue siendo `AVANZADO` y apagado de fábrica.**
   · Recomendación: sigue apagado (deja el micrófono abierto todo el día, es una
   decisión del usuario), pero sale de AVANZADO, porque hoy está plegado y
   escondido en una pestaña que ni se llama como él.

## Límites y reglas que no se rompen

Del propio proyecto, no inventadas:

- Una dependencia no entra si no publica para los cinco objetivos.
- Las claves de API nunca en texto plano, van al llavero del sistema.
- Los perfiles con nombres reales de personas nunca al repositorio.
- Toda herramienta ajena pasa por confirmación y queda anotada en Acciones.
- Once claves de config que Eve nunca puede escribirse a sí misma.
- Sin auto-atribución en los commits ni en el README.

## Fuera de alcance

- **El framework de pipecat.** Es de servidor y giraría todo el listener
  alrededor de su arquitectura de frames. Solo se toma su modelo de fin de turno.
- **Servidor MCP.** Eve es cliente. Un servidor sería un JSON-RPC para hablar
  consigo misma.
- **Reescribir el motor de dibujo por GPU** ni los trece tipos de módulo.
- **Router de modelos** (un modelo barato clasificando antes de ejecutar).

## Preguntas para investigar

1. **¿pywebview congelado con PyInstaller abre y ejecuta JavaScript en los cinco
   objetivos?** En Linux necesita paquetes del sistema (`gir1.2-webkit2-4.1`,
   `python3-gi`) que **no se pueden empaquetar**: el `.deb` y el `.rpm` tendrían
   que declararlos. En Windows arrastra `pythonnet` y el runtime de WebView2.
   Importa porque si falla un objetivo, la decisión 2 se cae entera.
2. **¿Se puede hacer una ventana pywebview sin borde, siempre encima,
   transparente y que deje pasar los clics, en Windows?** La documentación dice
   que la transparencia no está disponible ahí. Decide la pregunta abierta 1.
3. **¿Cuánto pesa pywebview con sus dependencias en el instalador?** Decide la
   pregunta abierta 3.
4. **¿`smart-turn-v3` reconoce el final de turno en español rioplatense?** El
   modelo dice soportar español entre 23 idiomas. Hay que medirlo con voz real,
   no confiar en la lista.

## Los cinco motivos por los que el despertar no anda

Verificados, varios ejecutando código.

| # | Qué pasa | Dónde |
|---|---|---|
| 1 | **Está apagado.** `wake_activo=False` en tu config real | log `actions` ids 71 y 75 |
| 2 | **Los valores de fábrica son la PEOR fila de la tabla que el propio proyecto midió.** `tiny` + `eve` da **2 de 4**; `Computadora` con `tiny` da 4 de 4 | `store.py:142,145` vs `despertar.py:70-74` |
| 3 | **`assistant_name` no se usa nunca para despertar.** La sección se llama "Despertarla diciendo su nombre" y lee otro campo, en otra pestaña. Renombrar la IA no cambia la palabra | 8 usos de `wake_palabra`, ninguno cruza `assistant_name` |
| 4 | **Puntuación en la palabra rompe la puerta para siempre, en silencio.** Al texto oído se le saca; a la variante configurada, no. Verificado: `separar('Eve, abre Spotify', 'eve, computadora')` da `None` | `despertar.py:91` vs `:94` |
| 5 | **El hilo de escucha puede morir y no revive.** `_lazo` tiene `try/finally` **sin `except`**, y `voice.speak` está fuera del try | `despertar.py:221-233`, `listener.py:163-182` |

Aparte, dos que degradan sin romper: la puerta pide `tiny` y la transcripción
`small` sobre **una sola caché global** de whisper, así que en CUDA cada
despertar descarga y carga; y **nada pausa la escucha mientras Eve habla**, así
que se oye a sí misma.

Y un dato para no perder tiempo: las 16 filas de "micrófono no disponible" en
`eve.db` **son falsas**, las escribió un test que no aísla la base
(`test_eve.py:5065-5066`, parchea `CONFIG_PATH` y `OVERLAY_PATH` pero no
`DB_PATH`).

## Notas para el que planifique

**Orden sugerido**

1. Dibujar las nueve pestañas. Nada de código hasta que estén aprobadas.
2. La puerta de pywebview en los cinco objetivos, y la del cartel en Windows.
   Las dos son medición, no discusión.
3. `registro.esquema()`: el árbol entero a JSON con `tipo` en cada nodo. Es la
   pieza que habilita todo y hoy no existe.
4. Portar los dos tests guardianes ANTES de la primera pestaña.
5. Portar pestaña por pestaña, las más declarativas primero.
6. El despertar, los textos obsoletos y `smart-turn-v3`, que no dependen del
   panel.

**Los dos tests que no se pueden perder.**
`test_todo_ajuste_se_puede_tocar_desde_el_panel` y
`test_la_pestana_generada_cubre_lo_mismo_que_la_config` son los guardianes del
modo de falla que motivó `registro.py`: *"olvidarse de una línea deja un ajuste
que existe en la config y no se puede tocar. **Ya pasó once veces**"*. Hay 16
tests que construyen `gui.Panel()` y dependen de él como objeto Python.

**Archivos**

| | |
|---|---|
| `eve/registro.py` | `esquema()`; sigue siendo la única descripción del panel |
| `eve/panel_api.py`, `web/` | nuevos |
| `eve/gui.py` | se retira pestaña por pestaña |
| `eve/despertar.py`, `eve/listener.py`, `eve/voice.py` | el despertar |
| `eve/skills.py`, `eve/store.py` | `skills_activas`, copiando `addons_activos` |
| `eve/compat_engine.py` | textos que mandan a la pestaña equivocada |
| `build.py`, `main.py` | `web/` en el paquete, y en `IMPRESCINDIBLES` |

**De pipecat.** El framework no entra. Su modelo `smart-turn-v3` sí pasa todas
las puertas: BSD-2, 8 MB, corre sobre el `onnxruntime` que **ya viaja**, 12 ms en
CPU, 16 kHz y hasta 8 segundos, que es exactamente lo que el despertar ya
recorta. Reemplaza el `CIERRE_S = 0.7` fijo. Y una idea sin dependencia:
`voice.speak` es bloqueante y no se puede cortar desde afuera, así que **hoy no
podés interrumpir a Eve mientras habla**.

---

# Cómo se ejecuta: los cuatro roles y el lazo

## Los agentes

De los cuatro, en disco existe **uno**. Hay que escribir los otros tres.

| Rol | Estado | Qué hace |
|---|---|---|
| **tester** | **Ya existe**, `.claude/agents/qa-eve.md` | Prueba casos concretos y los registra con la evidencia al lado. No opina, mide. |
| **researcher** | Falta | Busca e investiga lo necesario. Solo lectura: no escribe código. Devuelve hechos con ruta y línea, nunca suposiciones. |
| **builder** | Falta | Construye código y diseños. Recibe una tarea acotada del planner y la deja terminada, con su prueba. |
| **planner** | Falta | Reparte el trabajo, controla que se cumpla el plan al pie de la letra y decide qué sigue. Es el único que ve el conjunto. |

Se escriben en `.claude/agents/` del proyecto de Eve, al lado de `qa-eve.md`, que
sirve de molde: ya tiene el tono, el formato de hallazgos y la lista de
herramientas acotada.

## El lazo

- **Ritmo propio.** Vuelve cuando hay algo que esperar (una compilación, una
  medición) y se toma veinte o treinta minutos cuando no hay nada.
- **git, solo en ramas `medida/`.** Cambiado el 29/08, porque medir en los cinco
  objetivos exige la CI y la CI exige un push. El lazo puede commitear y empujar
  a ramas con prefijo `medida/`, y nada más: **nunca `main`, nunca un tag, nunca
  una release.** Eve se actualiza sola en las máquinas donde esté instalada, así
  que una release sin que nadie la haya mirado se propaga sola.
- **El trabajo de verdad sigue sin commitear.** Solo lo que hace falta para
  medir va a una rama. El resto queda en el árbol y lo revisás con `git diff`.
- Eso significa que ese trabajo se **acumula**. Es la contrapartida y conviene
  saberla: si se junta mucho, revisar se vuelve pesado.

## El orden del trabajo

1. **Escribir los tres agentes que faltan.**
2. **Dibujar las nueve pestañas.** El builder las dibuja, vos las aprobás. Nada
   de código hasta entonces.
3. **Las dos puertas medidas**, en paralelo con el dibujo: pywebview congelado en
   los cinco objetivos, y la ventana transparente en Windows para el cartel.
4. **`registro.esquema()`** y los dos tests guardianes portados.
5. **Portar pestaña por pestaña**, las más declarativas primero.
6. **El despertar, los textos obsoletos y `smart-turn-v3`**, que no dependen del
   panel.

Nada de esto sale publicado hasta que el panel nuevo esté listo: lo decidiste
así y el lazo no puede publicar aunque quisiera.
