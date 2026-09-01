"""Cuanto se parece el panel al diseno, en un numero por pestana.

    python medidas/comparar.py               compara las que tengan captura
    python medidas/comparar.py Voz Modelos   solo esas
    python medidas/comparar.py --claro       contra las capturas en tema claro
    python medidas/comparar.py --ver         ademas escribe las imagenes

"Se parece bastante" es una discusion sin final: uno mira, le parece que si, y
al lado hay catorce pixeles de diferencia que nadie ve pero que estan. Esto lo
convierte en un porcentaje, y en una imagen donde lo que no coincide se ve
prendido.

## Como compara

Los dos lados se llevan al mismo tamano y se restan:

1. **El panel** se dibuja con Chrome headless a 980 px de ancho --que es el
   ancho del artboard-- con la paleta del tema que se este comparando y la
   pestana abierta. Y en modo FLUJO: sin la barra de scroll interna, para que
   la pestana entera entre en la imagen igual que en el dibujo.
2. **El diseno** sale de `medidas/diseno/*.png`, que es lo unico del diseno que
   se versiona: los artboards son borradores y estan en `.gitignore`.
3. Las capturas no estan todas a la misma escala --varias se sacaron a 2x-- asi
   que se llevan a 980 de ancho antes de restar.
4. Se alinean por el borde de arriba del contenido, no por el del archivo: los
   recortes tienen distinto aire alrededor.

## Que significa el numero

El porcentaje de pixeles que difieren mas que la tolerancia. NO es una nota:
es una pista de donde mirar, y la imagen de diferencia es lo que dice que
esta mal.

Y no va a dar cero nunca, por tres motivos que ya estan escritos en
`medidas/tokens.py` y conviene repetir aca:

* **los iconos de seccion** del dibujo son SVG dibujados uno por uno, y el
  panel todavia no los tiene;
* **el contenido** en el dibujo es texto de ejemplo y en el panel son tus
  datos, con otro largo y otra cantidad de renglones;
* **la fuente** la resuelve el navegador; el dibujo se capturo en esta maquina
  y el panel se dibuja en la que lo abra.

Lo que si tiene que dar cero es la ESTRUCTURA: donde empieza cada tarjeta,
cuanto mide el riel, donde cae la columna de rotulos. Eso es lo que este
numero sirve para vigilar.
"""

import glob
import json
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

DISENO = os.path.join(RAIZ, "medidas", "diseno")
ANCHO = 980          # el del artboard
ALTO_LIENZO = 5000   # de sobra: despues se recorta a lo que ocupe
TOLERANCIA = 24      # cuanto puede diferir un canal sin contar como distinto

# Como se llama cada pestana del panel en el archivo de captura.
CAPTURAS = {
    "General": "general", "Modelos": "modelos", "Cuentas": "cuentas",
    "Comandos": "comandos", "Voz": "voz", "Contactos": "contactos",
    "Addons": "addons", "Apariencia": "apariencia", "Actividad": "actividad",
}


def navegador() -> str:
    """El Chrome o el Edge que haya. Si no hay ninguno, no se puede comparar."""
    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome", "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    raise SystemExit("no encontre Chrome ni Edge; sin navegador no hay con que "
                     "dibujar el panel para compararlo.")


# El CSS que pone el panel en modo FLUJO. Va aparte y no adentro de
# `panel.css`: es andamio de la comparacion, no del producto, y meterlo alla
# seria dejar reglas que solo existen para una medicion.
FLUJO = """
  html, body { height: auto !important; overflow: visible !important; }
  .cuerpo { min-height: 0 !important; }
  .contenido, .riel { overflow: visible !important; }
  .historial, .lista { max-height: none !important; overflow: visible !important; }
  /* El pie es fijo abajo en el panel y en el dibujo no existe como tal. */
  .pie { display: none !important; }
"""


def _html(pestana: str, tema: str, destino: str) -> str:
    """Arma la previa con el tema y la pestana forzados, en modo flujo."""
    from eve import panel_api

    from medidas import previa_panel

    # El riel muestra el ROTULO, no la clave: "Modelos y claves", no "Modelos".
    pestana_rotulo = next(r for c, r, _s, _t in panel_api.PESTANAS if c == pestana)

    ruta = previa_panel.armar(destino)
    with open(ruta, encoding="utf-8") as f:
        html = f.read()
    # El tema del artboard, no el de la config de quien corre esto: las
    # capturas se sacaron con las paletas `claro` y `oscuro` de `eve/tema.py`.
    from eve import tema as tema_mod

    paleta = tema_mod.PALETAS[tema]
    inyeccion = (
        "<style>" + FLUJO + "</style>\n"
        "<script>\n"
        # El tema del artboard, no el de la config de quien corre esto.
        f"ESQUEMA_FIJO.paleta = {json.dumps(paleta)};\n"
        # "Lo esencial", que es como se sacaron las capturas y es el estado de
        # fabrica: en "Todo" las avanzadas arrancan abiertas y la pestana sale
        # tres veces mas larga que el dibujo.
        'ESQUEMA_FIJO.modo = "esencial";\n'
        # La pestana se abre CLICKEANDO su boton del riel, que es lo que hace
        # una persona. Manejar la variable interna del panel seria mas corto y
        # probaria menos: asi se recorre el mismo camino que en el uso real.
        #
        # A intervalo y no con un `setTimeout` unico: el panel se dibuja cuando
        # le contesta el puente --que es una promesa-- y no hay forma de saber
        # desde afuera cuando termino. Se intenta hasta que el boton aparece.
        f"const QUIERO = {json.dumps(pestana_rotulo)};\n"
        "const reloj = setInterval(() => {\n"
        "  const b = [...document.querySelectorAll('.riel button')]\n"
        "    .find(x => x.textContent === QUIERO);\n"
        "  if (!b) return;\n"
        "  clearInterval(reloj);\n"
        "  b.click();\n"
        # El tema, DESPUES de que el panel ya se dibujo. Cambiar el
        # esquema no alcanza: `aplicarTema` corre una sola vez al arrancar
        # y ya habia pintado con la paleta de la config de esta maquina
        # --el panel salia morado contra un dibujo gris--. Se lo vuelve a
        # llamar con la del artboard, que es contra la que se compara.
        f"  ESQ.paleta = {json.dumps(paleta)}; aplicarTema(ESQ);\n"
        "  document.title = 'listo';\n"
        "}, 50);\n"
        "</script>\n")
    # DESPUES del puente y del panel, no en el `<head>`: ahi `ESQUEMA_FIJO`
    # todavia no existe, la primera linea reventaba, y con ella se caia todo lo
    # de abajo. El sintoma era doble y desorientador --ni cambiaba el tema ni
    # cambiaba la pestana-- por una sola causa.
    html = html.replace("</body>", inyeccion + "</body>", 1)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta


def _foto(ruta_html: str, salida: str) -> None:
    subprocess.run(
        [navegador(), "--headless", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1",
         # Le damos tiempo a que corra el `setTimeout` que abre la pestana.
         "--virtual-time-budget=15000",
         f"--screenshot={salida}", f"--window-size={ANCHO},{ALTO_LIENZO}",
         ruta_html],
        capture_output=True, check=False, timeout=120)


def _normalizar(im):
    """La captura a escala 1:1, recortada al ancho del artboard.

    Estaba mal y era EL error del comparador: se reescalaba por el ancho del
    archivo, asumiendo que el archivo era el artboard. No lo es. Las capturas
    salieron a distinto tamano --980, 1020, 1040, 1960-- y las de 1040 son 1:1
    con sesenta pixeles de mas a la derecha, no un artboard estirado. Al
    llevarlas a 980 se achicaba TODO un 5.8%, y con eso cada pixel difiere.

    Se nota en un numero que no miente: el borde del riel cae en x=198 en las
    capturas de 1040 y el artboard lo declara en 199. Estaban 1:1 desde el
    principio.

    La escala real es 1 o 2 --las de 1960 son 2x-- y de ahi sale todo lo demas.
    """
    from PIL import Image

    escala = 2 if im.width >= ANCHO * 2 - 40 else 1
    if escala == 2:
        im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
    # Y al ancho del artboard: lo que sobra a la derecha es aire de la captura.
    if im.width > ANCHO:
        im = im.crop((0, 0, ANCHO, im.height))
    return im


def _recortar(im, fondo=None):
    """Saca el aire de ARRIBA y de ABAJO. A lo ancho no se toca.

    Solo vertical, y la razon es concreta: el panel se dibuja a 980 px de ancho
    por construccion --se lo pide la ventana-- y el dibujo tambien mide 980. Si
    ademas se recortara a los costados, el panel salia a 960 porque su margen
    exterior es del mismo color que el fondo, y entonces TODO quedaba corrido
    diez pixeles a la izquierda. Con eso, cada pixel difiere y el numero deja
    de decir nada: daba 70% cuando lo unico que pasaba era el corrimiento.

    Arriba y abajo si, porque los recortes de las capturas tienen distinto aire
    y eso si hay que emparejarlo.
    """
    from PIL import Image, ImageChops

    im = im.convert("RGB")
    fondo = fondo or im.getpixel((0, 0))
    caja = ImageChops.difference(im, Image.new("RGB", im.size, fondo)).getbbox()
    if not caja:
        return im
    return im.crop((0, caja[1], im.width, caja[3]))


def comparar(pestana: str, tema: str, ver: bool = False) -> dict:
    """El porcentaje de pixeles distintos entre el panel y su dibujo."""
    from PIL import Image, ImageChops

    nombre = CAPTURAS[pestana]
    png = os.path.join(DISENO, f"{nombre}-{tema}.png")
    if not os.path.exists(png):
        return {"pestana": pestana, "error": "sin captura del diseno"}

    carpeta = tempfile.mkdtemp(prefix=f"eve_cmp_{nombre}_")
    ruta = _html(pestana, tema, carpeta)
    foto = os.path.join(carpeta, "panel.png")
    _foto(ruta, foto)
    if not os.path.exists(foto):
        return {"pestana": pestana, "error": "el navegador no saco la foto"}

    panel = _recortar(Image.open(foto))
    dibujo = _normalizar(Image.open(png).convert("RGB"))
    dibujo = _recortar(dibujo)

    # Al mismo tamano, quedandose con lo que los dos tienen: comparar contra
    # aire de mas seria contar como diferencia lo que simplemente no esta.
    ancho = min(panel.width, dibujo.width)
    alto = min(panel.height, dibujo.height)
    panel_r = panel.crop((0, 0, ancho, alto))
    dibujo_r = dibujo.crop((0, 0, ancho, alto))

    dif = ImageChops.difference(panel_r, dibujo_r).convert("L")
    distintos = sum(1 for p in dif.getdata() if p > TOLERANCIA)
    total = ancho * alto

    salida = {"pestana": pestana, "tema": tema,
              "distintos": 100.0 * distintos / total,
              "panel": f"{panel.width}x{panel.height}",
              "dibujo": f"{dibujo.width}x{dibujo.height}",
              "alto_comparado": alto}

    if ver:
        destino = os.path.join(DISENO, "comparacion")
        os.makedirs(destino, exist_ok=True)
        lado = Image.new("RGB", (ancho * 2 + 20, alto), (0, 0, 0))
        lado.paste(dibujo_r, (0, 0))
        lado.paste(panel_r, (ancho + 20, 0))
        lado.save(os.path.join(destino, f"{nombre}-{tema}-lado-a-lado.png"))
        # Lo que no coincide, prendido sobre negro.
        dif.point(lambda p: 255 if p > TOLERANCIA else 0).save(
            os.path.join(destino, f"{nombre}-{tema}-diferencia.png"))
        salida["imagenes"] = destino
    return salida


# Que elemento del panel encarna cada medida del dibujo. Es el puente entre el
# token --que salio del artboard-- y lo que el navegador termina dibujando.
#
# Existe porque el diff de pixeles mide sobre todo el CONTENIDO: el panel
# muestra doce proveedores y doscientos renglones de historial donde el dibujo
# muestra tres de mentira, asi que la pestana sale mas larga y el porcentaje se
# llena de diferencias que no son de diseno. Esto mide lo que si es de diseno:
# cuanto ocupa cada cosa.
WIDGETS = (
    # (token, selector, que se le mide)
    ("riel-ancho", ".riel", "width"),
    ("riel-alto", ".riel button", "height"),
    ("tarjeta-radio", ".seccion", "border-top-left-radius"),
    ("tarjeta-padding", ".seccion", "padding"),
    ("campo-radio", ".campo input, .campo select", "border-top-left-radius"),
    ("campo-padding", ".campo input, .campo select", "padding"),
    ("boton-radio", ".boton", "border-top-left-radius"),
    ("boton-padding", ".boton", "padding"),
    ("rotulo-ancho", ".campo:not(.chico) > label", "width"),
    ("titulo-tam", ".cabecera h1", "font-size"),
    ("cuerpo-tam", "body", "font-size"),
    ("ayuda-tam", ".ayuda", "font-size"),
    ("rotulo-tam", ".campo:not(.chico) > label", "font-size"),
    ("tablero-gap", ".tablero", "row-gap"),
    ("seccion-gap", ".cuerpo-seccion", "row-gap"),
    ("fila-gap", ".campo", "column-gap"),
    ("barra-padding", ".barra", "padding"),
    ("cuerpo-gap", ".cuerpo", "column-gap"),
    ("cuerpo-padding", ".cuerpo", "padding"),
    ("cabecera-padding", ".cabecera", "padding"),
    ("pildora-radio", ".nivel", "border-top-left-radius"),
    ("pildora-padding", ".nivel", "padding"),
    ("modo-padding", ".modo", "padding"),
    ("modo-radio", ".modo", "border-top-left-radius"),
    ("buscador-padding", ".buscador", "padding"),
    ("tabla-th-padding", ".tabla th", "padding"),
    ("tabla-td-padding", ".tabla td", "padding"),
    ("muestra-ancho", ".muestra", "width"),
    ("muestra-panel-alto", ".muestra-panel", "height"),
    ("muestra-cartel-alto", ".muestra-cartel", "height"),
    ("anillo-muestra", ".muestra-punto", "width"),
    ("muestra-riel-ancho", ".muestra-riel", "width"),
    ("galeria-gap", ".galeria", "column-gap"),
)


def _tokens(pestana: str = "") -> dict:
    """Lo que `tokens.css` dice que tiene que medir cada cosa, EN esta pestana.

    Con la pestana y no sin ella: el ancho de la columna de rotulos cambia
    --150 en casi todas, 200 en General, 220 en Cuentas-- porque el dibujo lo
    cambia. Leer el archivo de corrido se quedaba con el ultimo bloque que
    apareciera y comparaba Comandos contra el valor de General.
    """
    import re

    with open(os.path.join(RAIZ, "web", "tokens.css"), encoding="utf-8") as f:
        css = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    salida = {}
    for selector, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        selector = selector.strip()
        propio = f'[data-pestana="{pestana}"]'
        if selector != ":root" and selector != propio:
            continue
        for n, v in re.findall(r"--([a-z0-9-]+):\s*([^;]+);", cuerpo):
            salida[n] = v.strip()
    return salida


def _normal(v: str) -> str:
    """`5px 14px` y `5px 14px 5px 14px` son lo mismo. Y `0` es `0px`."""
    partes = [("0px" if p == "0" else p) for p in str(v).split()]
    if len(partes) == 4 and partes[0] == partes[2] and partes[1] == partes[3]:
        partes = partes[:2]
    if len(partes) == 2 and partes[0] == partes[1]:
        partes = partes[:1]
    return " ".join(partes)


def widgets(pestana: str, tema: str) -> list:
    """Cada widget del panel contra la medida que el dibujo declara."""
    import json as _j

    carpeta = tempfile.mkdtemp(prefix="eve_wid_")
    ruta = _html(pestana, tema, carpeta)
    guion = _j.dumps([[t, sel, prop] for t, sel, prop in WIDGETS])
    with open(ruta, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("</body>", (
        "<script>\n"
        f"const PEDIDO = {guion};\n"
        "setTimeout(() => {\n"
        "  const out = {};\n"
        "  for (const [tok, sel, prop] of PEDIDO) {\n"
        "    const e = document.querySelector(sel);\n"
        "    if (!e) { out[tok] = null; continue; }\n"
        "    const cs = getComputedStyle(e);\n"
        "    out[tok] = prop === 'padding'\n"
        "      ? [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].join(' ')\n"
        "      : cs[prop.replace(/-([a-z])/g, (m,c) => c.toUpperCase())];\n"
        "  }\n"
        "  document.title = 'MEDIDO' + JSON.stringify(out);\n"
        "}, 1200);\n"
        "</script></body>"), 1)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)

    r = subprocess.run(
        [navegador(), "--headless", "--disable-gpu", "--virtual-time-budget=20000",
         "--dump-dom", ruta], capture_output=True, text=True, timeout=300)
    marca = (r.stdout or "").find("MEDIDO")
    if marca < 0:
        return [{"error": "el navegador no devolvio las medidas"}]
    crudo = r.stdout[marca + 6:]
    crudo = crudo[:crudo.index("</title>")]
    medido = _j.loads(crudo.replace("&quot;", '"'))

    declarado = _tokens(pestana)
    salida = []
    for token, sel, prop in WIDGETS:
        quiero = declarado.get(token)
        tengo = medido.get(token)
        if quiero is None or tengo is None:
            salida.append({"token": token, "estado": "sin dato", "sel": sel})
            continue
        salida.append({
            "token": token, "sel": sel,
            "dibujo": _normal(quiero), "panel": _normal(tengo),
            "igual": _normal(quiero) == _normal(tengo),
        })
    return salida


def main() -> int:
    tema = "claro" if "--claro" in sys.argv else "oscuro"
    ver = "--ver" in sys.argv

    if "--widgets" in sys.argv:
        pedidas = [a for a in sys.argv[1:] if not a.startswith("--")]
        pestana = pedidas[0] if pedidas else "General"
        print(f"caja por caja, pestana {pestana}, tema {tema}\n")
        mal = 0
        for r in widgets(pestana, tema):
            if r.get("error"):
                print("  " + r["error"])
                return 1
            if r.get("estado"):
                print(f"  {r['token']:22} {r['estado']}  ({r['sel']})")
                continue
            if r["igual"]:
                print(f"  {r['token']:22} OK    {r['panel']}")
            else:
                mal += 1
                print(f"  {r['token']:22} NO    dibujo {r['dibujo']:16} "
                      f"panel {r['panel']}")
        print(f"\n{mal} de {len(WIDGETS)} widgets no coinciden")
        return 0

    pedidas = [a for a in sys.argv[1:] if not a.startswith("--")]
    pestanas = pedidas or [p for p in CAPTURAS
                           if glob.glob(os.path.join(DISENO, f"{CAPTURAS[p]}-{tema}.png"))]

    print(f"panel a {ANCHO}px contra el diseno en tema {tema}, "
          f"tolerancia {TOLERANCIA}/255\n")
    print(f"  {'pestana':12} {'distinto':>9}   {'panel':>12} {'dibujo':>12}")
    peor = 0.0
    for p in pestanas:
        r = comparar(p, tema, ver)
        if "error" in r:
            print(f"  {p:12} {r['error']}")
            continue
        peor = max(peor, r["distintos"])
        print(f"  {p:12} {r['distintos']:8.2f}%   {r['panel']:>12} {r['dibujo']:>12}")
    if ver:
        print(f"\nimagenes en {os.path.join(DISENO, 'comparacion')}")
    print(f"\npeor pestana: {peor:.2f}% de pixeles distintos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
