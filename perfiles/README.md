# Perfiles de ejemplo

Ocho temas listos para el cartel y el panel. Cada `.eveperfil` trae paleta,
forma del icono, contorno, tipo de onda, fuente, velocidad de habla y un tono
de personalidad.

**Para usarlos**: panel de configuración → pestaña *General* → **Importar**.

| Perfil | Acento | Forma | Onda | Velocidad |
|---|---|---|---|---|
| Cian Táctico | `#33c9ff` | hexágono | espejo | 1.00 |
| Mayordomo Dorado | `#ffc247` | círculo | línea | 1.05 |
| Laboratorio Naranja | `#ff8c1a` | octógono | puntos | 1.22 |
| Núcleo Azul | `#4aa8e0` | círculo | barras | 0.85 |
| Bronce Estratega | `#c9a227` | pentágono | línea | 1.08 |
| Taller Naranja | `#ffa726` | triángulo | barras | 0.90 |
| Runa Verde | `#4fd1b0` | heptágono | línea | 1.12 |
| Cromo Rojo | `#ff2d55` | rombo | barras | 1.00 |

La velocidad es el `length_scale` de Piper: más alto habla más lento. Lo hace el
sintetizador, no un efecto encima, así que no ensucia el audio.

## Qué NO tocan

Un tema que te bajás de internet no debería poder cambiarte cómo trabaja el
asistente. Estos archivos no pueden traer:

- tu tecla, tu motor ni tu modelo;
- el freno de acciones destructivas;
- tus datos (mail, Discord, Steam, carpetas de trabajo);
- el nombre de tu asistente;
- una voz concreta de Piper, que quizá no tengas descargada.

No es confianza: lo impone `store.perfilable()`, y hay un test que recorre estos
mismos archivos y falla si alguno trae algo de esa lista.

## El tono

Cada perfil trae un `persona_tono`: una línea sobre **cómo** habla, no sobre qué
hace. Va al final del prompt con un encuadre que lo subordina al manual, así que
no puede hacer que el asistente hable de más ni que narre en vez de actuar. Si
no lo querés, borrá ese campo en la pestaña *Voz*.

## Hacer el tuyo

Configurá todo a gusto en el panel, después **Guardar como...** y **Exportar**.
Sale un `.eveperfil` que podés pasarle a quien quieras, ya filtrado de tus datos.
