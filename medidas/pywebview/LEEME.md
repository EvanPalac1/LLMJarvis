# Las dos puertas de pywebview, medidas

Sostienen una decisión del handshake. Estaban en una carpeta temporal que
Windows limpia sola, así que viven acá.

Medido el 29/08/2026, sobre el commit `3753fad`, con **pywebview 6.2.1** en un
entorno virtual aparte. Sin instalar nada en el entorno del usuario.

## Puerta del panel: VERDE (Windows)

`wv_panel.py`. No alcanza con que la ventana abra: lo que el panel necesita es
el camino completo.

```
{"js": "el js corrio", "puente": "hola desde el panel", "dom": 3, "error": null}
```

- El HTML se dibuja: tres controles contados en el DOM.
- El JavaScript corre.
- **El puente JS -> Python funciona**, que es lo que decide.

Peso del entorno con todas sus dependencias: **22 MB** (pythonnet, bottle,
cffi, clr_loader), contra los 92 MB que costaba PySide6 en la misma máquina.

**Falta**: congelarlo con PyInstaller, y los otros cuatro objetivos. En Linux
pywebview necesita paquetes del sistema que **no se pueden empaquetar**
(`python3-gi`, `gir1.2-webkit2-4.1`), así que el `.deb` y el `.rpm` tendrían que
declararlos.

## Puerta del cartel: ROJA (Windows)

`wv_cartel.py`. El cartel necesita cuatro cosas a la vez: sin borde, siempre
encima, transparente y que deje pasar los clics. Es lo que `overlay.py` hace hoy
con `overrideredirect(True)`, `-topmost`, `-transparentcolor` y
`WS_EX_TRANSPARENT`.

**Preguntándole a la API de Windows**, todo bien:

```
sin_borde: true   redimensionable: false   layered: true   deja_pasar_clics: true
```

**Pero esas banderas mienten, y por eso hay capturas.** Dos cosas que el número
solo no dice:

1. `layered` y `deja_pasar_clics` solo dieron `true` **después de forzarlos a
   mano** con `SetWindowLongPtrW`. pywebview aceptó `transparent=True` sin error
   y sin aplicarlo: venía en `false`.
2. Los píxeles no acompañan.

| Captura | Qué se ve |
|---|---|
| `cartel_web.png` | Con color clave negro: **rectángulo blanco opaco**, con barras de desplazamiento |
| `cartel_web2.png` | Con el mecanismo real de Eve, la página pintando el color clave (magenta) igual que `-transparentcolor`: la ventana **desaparece entera, la tarjeta incluida** |

**Y hay un problema de diseño arriba del resultado.** Calar por color sobre una
superficie web significa que **cualquier píxel del contenido que coincida con el
color clave se vuelve un agujero**. El cartel muestra texto y contenido del
usuario, así que eso no es un caso raro: es una falla esperable.

Mata la idea aunque la transparencia llegara a funcionar.

## Cómo repetirlo

```
python -m venv wvspike
wvspike/Scripts/python.exe -m pip install pywebview pillow
wvspike/Scripts/python.exe wv_panel.py
wvspike/Scripts/python.exe wv_cartel.py
```

Las dos imprimen una línea `RESULTADO {...}` con JSON.
