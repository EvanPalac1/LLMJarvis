"""Saca las medidas del panel de los ARTBOARDS, en vez de copiarlas a mano.

    python medidas/tokens.py            reescribe web/tokens.css
    python medidas/tokens.py --check    dice si el CSS quedo desfasado
    python medidas/tokens.py --informe  muestra de donde sale cada numero

El pedido fue "que se parezca lo maximo posible, evitando hardcodeos al
maximo", y las dos mitades tiran para lados opuestos si uno las toma de la
forma obvia: parecerse pide copiar cada medida del dibujo al CSS, y copiar es
hardcodear. La copia ademas se desfasa sola --se corrige el dibujo y el panel
sigue con el numero viejo, sin que nada lo diga--.

La salida es no copiar ninguna: **los numeros viven en el artboard y el CSS los
lee**. Este archivo hace esa lectura y escribe `web/tokens.css`, que es
generado y no se edita a mano. Cambiar el dibujo y volver a correr esto mueve
el panel entero.

Es el mismo patron que ya usa el color: la paleta sale de `eve/tema.py` y el
CSS no tiene ni un `#hex`. Esto lo estira a las medidas.

## Lo que este archivo NO puede sacar del dibujo

Y es importante que este escrito, porque es donde "pixel perfect" tiene techo:

* **los iconos de seccion**, que son SVG dibujados uno por uno;
* **el contenido**, que en el dibujo es texto de ejemplo y en el panel son tus
  datos, con otro largo;
* **lo que el dibujo no muestra**: los estados de foco, de hover y de error.

## Y una contradiccion del propio dibujo

La columna de rotulos mide **150px** en Modelos, Apariencia, Voz y Addons (40
usos) y **200px** en General (10 usos); Comandos tiene las dos. No hay ningun
valor unico que sea pixel perfect contra las nueve, porque las nueve no se
ponen de acuerdo. Se resuelve con `POR_PESTANA`, abajo, que es deliberado y
esta a la vista: seguir el dibujo pestana por pestana da diferencia cero, y
unificar da un panel coherente con una diferencia conocida en una pestana.
"""

import collections
import glob
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "web", "tokens.css")

# `Main.dc.html` esta RETIRADO: no corresponde a ninguna pestana y quedo a
# mitad de una refactorizacion vieja. Contarlo mezclaria medidas de un diseno
# que nadie aprobo. Esta escrito en `medidas/diseno/LEEME.md`.
RETIRADOS = {"Main.dc.html"}


def artboards() -> list:
    """Los .dc.html que SI valen, ordenados."""
    return [f for f in sorted(glob.glob(os.path.join(RAIZ, "*.dc.html")))
            if os.path.basename(f) not in RETIRADOS]


def _declaraciones(ruta: str) -> list:
    """Cada `style="..."` del artboard, como dict de propiedad a valor."""
    with open(ruta, encoding="utf-8") as f:
        fuente = f.read()
    salida = []
    for est in re.findall(r'style="([^"]*)"', fuente):
        d = {}
        for decl in est.split(";"):
            if ":" in decl:
                k, _, v = decl.partition(":")
                d[k.strip()] = v.strip()
        if d:
            salida.append(d)
    return salida


# Cada medida del panel, con como se la reconoce en el dibujo.
#
# La firma es un conjunto de propiedades que tienen que estar TODAS: es lo que
# distingue un boton de un campo cuando los dos tienen el mismo radio. Y de ahi
# se saca UNA propiedad, la que interesa.
#
# Esto es lo unico escrito a mano en todo el camino, y es una descripcion de
# como se ve cada cosa, no una medida. Si manana el dibujo cambia el radio de
# las tarjetas, esta tabla no se toca: el numero sale solo.
ROLES = (
    # (nombre, firma, propiedad que se lee)
    ("pagina-ancho", {"width": "980px"}, "width"),
    ("riel-ancho", {"width": "178px"}, "width"),
    ("riel-alto", {"height": "34px"}, "height"),
    ("riel-radio", {"height": "34px"}, "border-radius"),
    ("riel-padding", {"height": "34px"}, "padding"),
    ("tarjeta-radio", {"padding": "14px 16px"}, "border-radius"),
    ("tarjeta-padding", {"padding": "14px 16px"}, "padding"),
    ("campo-radio", {"padding": "6px 10px"}, "border-radius"),
    ("campo-padding", {"padding": "6px 10px"}, "padding"),
    ("boton-radio", {"padding": "5px 14px"}, "border-radius"),
    ("boton-padding", {"padding": "5px 14px"}, "padding"),
    ("pildora-radio", {"border-radius": "999px"}, "border-radius"),
    ("titulo-tam", {"font-size": "17px"}, "font-size"),
    ("subtitulo-peso", {"font-weight": "600"}, "font-weight"),

    # Tipografia. El cuerpo sale del elemento raiz del artboard --el de 980px--
    # y da 13px en los nueve, sin una sola excepcion.
    ("cuerpo-tam", {"width": "980px"}, "font-size"),
    ("rotulo-tam", {"color": "{{c.textoTenue}}", "font-size": "12px"}, "font-size"),
    ("ayuda-tam", {"color": "{{c.textoTenue}}", "font-size": "11px"}, "font-size"),

    # Los huecos. El dibujo NO usa la escala de `tema.ESPACIO` (4, 8, 12, 16,
    # 24, 32): usa 12 entre tarjetas, 8 adentro de una, y 10 en varios lados.
    # Se leen del dibujo en vez de forzarlos a la escala del programa, porque
    # lo que se esta copiando es el dibujo.
    ("tablero-gap", {"flex-direction": "column", "gap": "12px"}, "gap"),
    ("seccion-gap", {"flex-direction": "column", "gap": "8px"}, "gap"),
    ("fila-gap", {"align-items": "center", "gap": "12px"}, "gap"),

    # La muestra de perfil: panel arriba, cartel abajo. Las tres medidas las
    # tenia copiadas a mano y una estaba MAL --el cartel a 44px cuando el
    # dibujo dice 58-- que es catorce pixeles en cada muestra y a ojo no se ve.
    ("muestra-ancho", {"width": "210px"}, "width"),
    ("muestra-panel-alto", {"width": "210px", "border-radius": "6px 6px 0 0"}, "height"),
    ("muestra-cartel-alto", {"width": "210px", "border-radius": "0 0 6px 6px"}, "height"),
    ("muestra-radio-arriba", {"width": "210px", "border-radius": "6px 6px 0 0"},
     "border-radius"),
    ("muestra-radio-abajo", {"width": "210px", "border-radius": "0 0 6px 6px"},
     "border-radius"),
    ("muestra-cartel-padding", {"width": "210px", "border-radius": "0 0 6px 6px"},
     "padding"),
    # El anillo de la muestra. La firma nombra el color del acento del cartel
    # porque hay varios circulos en el dibujo --el del riel, el de la onda-- y
    # sin eso se mezclaban: daba 14px, que es OTRO circulo.
    ("anillo-muestra", {"border-radius": "50%", "border": "2px solid {{p.hudAcento}}"},
     "width"),
    ("galeria-gap", {"flex-wrap": "wrap", "gap": "14px"}, "gap"),

    # La estructura de la pagina: barra de arriba, el cuerpo, la cabecera de
    # cada pestana. Los cinco dan lo mismo en los nueve artboards.
    ("barra-padding", {"padding": "8px 12px"}, "padding"),
    ("cuerpo-gap", {"min-height": "0"}, "gap"),
    ("cuerpo-padding", {"min-height": "0"}, "padding"),
    ("riel-pad-derecha", {"width": "178px"}, "padding-right"),
    ("cabecera-padding", {"border-bottom": "1px solid {{c.borde}}"}, "padding"),

    # El par de botones Lo esencial / Todo, y la pildora de "avanzado". Los dos
    # los tenia copiados a mano y los dos estaban MAL: la pildora a `1px 8px`
    # cuando el dibujo dice `2px 9px`.
    ("modo-padding", {"padding": "3px 10px"}, "padding"),
    ("modo-radio", {"padding": "3px 10px"}, "border-radius"),
    ("pildora-padding", {"border-radius": "999px", "padding": "2px 9px"}, "padding"),

    # El buscador y las tablas. Las dos medidas de la tabla las tenia a `10px`
    # de costado y el dibujo dice `9px`; y la franja del panel adentro de la
    # muestra de perfil mide 46, no 40. Ninguno de los tres se ve a ojo.
    ("buscador-padding", {"flex-grow": "1", "padding": "4px 10px"}, "padding"),
    ("tabla-th-padding", {"padding": "6px 9px"}, "padding"),
    ("tabla-td-padding", {"padding": "5px 9px"}, "padding"),
    ("muestra-riel-ancho", {"width": "46px"}, "width"),
)

# Lo que cambia de pestana a pestana. Hoy es uno solo, y es el unico lugar del
# dibujo donde las nueve no se ponen de acuerdo.
POR_PESTANA = (
    # (nombre, como se lo reconoce, propiedad)
    ("rotulo-ancho", {"color": "{{c.textoTenue}}", "font-size": "12px"}, "width"),
)


# Las propiedades de tamano, con lo que hay que sumarles para pasar de la caja
# que el dibujo DECLARA a la que RENDERIZA.
_EJES = {
    "width": (("padding-left", "padding-right", "border-left-width",
               "border-right-width"), ("padding", 1, 3), ("border", "right")),
    "height": (("padding-top", "padding-bottom", "border-top-width",
                "border-bottom-width"), ("padding", 0, 2), ("border", "top")),
}


def _px(valor: str) -> float:
    valor = (valor or "").strip()
    if valor.endswith("px"):
        try:
            return float(valor[:-2])
        except ValueError:
            return 0.0
    return 0.0


def _lados(atajo: str) -> list:
    """Los cuatro lados de un `padding` corto, en orden arriba/der/abajo/izq."""
    partes = [p for p in (atajo or "").split() if p]
    if len(partes) == 1:
        return partes * 4
    if len(partes) == 2:
        return [partes[0], partes[1], partes[0], partes[1]]
    if len(partes) == 3:
        return [partes[0], partes[1], partes[2], partes[1]]
    return partes[:4]


def caja_renderizada(d: dict, prop: str) -> str:
    """El tamano que el elemento OCUPA, no el que declara.

    Los artboards no traen ningun reset, asi que el navegador los dibuja con
    `box-sizing: content-box`: `width: 178px` mas `padding-right: 10px` mas un
    borde de 1px ocupa **189**. El panel usa `box-sizing: border-box` --que es
    lo sano para maquetar-- donde ese mismo 178 es el total.

    Sin esta cuenta, el token copiaba el numero declarado y el riel del panel
    salia ONCE PIXELES mas angosto que el del dibujo, con todo lo de al lado
    corrido. Lo encontro el comparador, no la vista: once pixeles en un panel
    de 980 no se ven, y estaban en las nueve pestanas.

    Se hace aca y no en el CSS a proposito: lo que se quiere es el numero que
    el dibujo produce, y esa cuenta es parte de leer el dibujo.
    """
    base = _px(d.get(prop, ""))
    if not base:
        return d.get(prop, "")
    sumar = 0.0
    lados = _lados(d.get("padding", ""))
    if prop == "width":
        sumar += _px(d.get("padding-right", "")) or _px(lados[1] if lados else "")
        sumar += _px(d.get("padding-left", "")) or _px(lados[3] if lados else "")
        for lado in ("right", "left"):
            atajo = d.get(f"border-{lado}") or d.get("border") or ""
            sumar += _px(atajo.split()[0]) if atajo.split() else 0.0
    else:
        sumar += _px(d.get("padding-top", "")) or _px(lados[0] if lados else "")
        sumar += _px(d.get("padding-bottom", "")) or _px(lados[2] if lados else "")
        for lado in ("top", "bottom"):
            atajo = d.get(f"border-{lado}") or d.get("border") or ""
            # `border-top: none` resta el que puso el atajo `border`.
            if atajo.strip() in ("none", "0"):
                continue
            sumar += _px(atajo.split()[0]) if atajo.split() else 0.0
    total = base + sumar
    return f"{total:g}px"


def _dominante(decls: list, firma: dict, prop: str):
    """El valor mas usado de `prop` entre los que cumplen la firma.

    El mas usado y no el primero: un artboard puede tener un caso suelto --una
    fila mas angosta porque al lado hay un boton-- y tomar el primero que
    aparece convertiria esa excepcion en la regla.
    """
    cuenta = collections.Counter()
    for d in decls:
        if all(d.get(k) == v for k, v in firma.items()) and prop in d:
            # Los tamanos se miden como los dibuja el navegador; el resto
            # --rellenos, radios, huecos-- se lee tal cual.
            valor = (caja_renderizada(d, prop) if prop in ("width", "height")
                     else d[prop])
            cuenta[valor] += 1
    if not cuenta:
        return None, 0
    valor, n = cuenta.most_common(1)[0]
    return valor, n


def medir() -> dict:
    """Todas las medidas, con de donde salieron y cuantas veces se vieron."""
    todas = {}
    globales = collections.defaultdict(collections.Counter)
    por_pestana = collections.defaultdict(dict)

    for ruta in artboards():
        pestana = os.path.basename(ruta)[: -len(".dc.html")]
        decls = _declaraciones(ruta)
        for nombre, firma, prop in ROLES:
            valor, n = _dominante(decls, firma, prop)
            if valor is not None:
                globales[nombre][valor] += n
        for nombre, firma, prop in POR_PESTANA:
            valor, n = _dominante(decls, firma, prop)
            if valor is not None:
                por_pestana[nombre][pestana] = (valor, n)

    # Un rol que no encuentra nada es un ERROR, no un token que se cae en
    # silencio. Varias firmas nombran el valor que leen --es lo que distingue
    # el hueco entre tarjetas del hueco adentro de una-- asi que si el dibujo
    # cambia ese numero, la firma deja de coincidir. Que eso reviente es
    # deliberado: significa "el dibujo cambio, vení a mirar", que es
    # exactamente lo que un script no puede decidir solo. En silencio, el panel
    # se quedaria sin la medida y nadie se enteraria hasta verlo roto.
    faltan = [n for n, _f, _p in ROLES if n not in globales]
    if faltan:
        raise SystemExit(
            "estos roles no aparecen en ningun artboard: " + ", ".join(faltan)
            + "\nO el dibujo cambio, o la firma de medidas/tokens.py quedo vieja.")

    for nombre, cuenta in globales.items():
        valor, n = cuenta.most_common(1)[0]
        todas[nombre] = {"valor": valor, "usos": n,
                         "discrepa": sorted(v for v in cuenta if v != valor)}
    return {"globales": todas, "por_pestana": dict(por_pestana)}


def css(m: dict) -> str:
    """El archivo generado, con su procedencia adentro."""
    lineas = [
        "/* GENERADO POR medidas/tokens.py -- NO SE EDITA A MANO.",
        " *",
        " * Cada numero de aca sale de los artboards del diseno, medido y no",
        " * copiado: se cuenta cuantas veces aparece cada valor y gana el mas",
        " * usado. Cambiar el dibujo y volver a correr el script mueve el panel.",
        " *",
        " * Se genera para no tener el diseno escrito dos veces. Cuando estaba",
        " * copiado a mano en panel.css, nada ataba una copia a la otra: se",
        " * corregia el dibujo y el panel seguia con el numero viejo, sin que",
        " * ninguna prueba lo dijera.",
        " *",
        f" * Medido sobre {len(artboards())} artboards.",
        " */",
        "",
        ":root {",
    ]
    for nombre in sorted(m["globales"]):
        d = m["globales"][nombre]
        nota = f"  /* {d['usos']} usos"
        if d["discrepa"]:
            nota += f"; el dibujo tambien trae {', '.join(d['discrepa'])}"
        nota += " */"
        lineas.append(f"  --{nombre}: {d['valor']};{nota}")
    lineas.append("}")

    for nombre, porp in sorted(m["por_pestana"].items()):
        valores = collections.Counter(v for v, _n in porp.values())
        comun, _ = valores.most_common(1)[0]
        lineas += [
            "",
            f"/* --{nombre}: el dibujo NO se pone de acuerdo consigo mismo.",
            " * Se sigue pestana por pestana, que es lo unico que da diferencia",
            " * cero contra cada uno. El valor de `:root` es el mas usado, y lo",
            " * hereda cualquier pestana que no aparezca abajo.",
            " */",
            ":root {",
            f"  --{nombre}: {comun};",
            "}",
        ]
        for pestana, (valor, n) in sorted(porp.items()):
            if valor == comun:
                continue
            lineas.append(f'[data-pestana="{pestana}"] {{ --{nombre}: {valor}; }}'
                          f"  /* {n} usos */")
    return "\n".join(lineas) + "\n"


def main() -> int:
    m = medir()
    texto = css(m)

    if "--informe" in sys.argv:
        for nombre in sorted(m["globales"]):
            d = m["globales"][nombre]
            extra = f"   (tambien: {', '.join(d['discrepa'])})" if d["discrepa"] else ""
            print(f"  {nombre:18} {d['valor']:12} {d['usos']:3} usos{extra}")
        for nombre, porp in m["por_pestana"].items():
            print(f"\n  {nombre}:")
            for pestana, (valor, n) in sorted(porp.items()):
                print(f"    {pestana:12} {valor:8} {n:3} usos")
        return 0

    if "--check" in sys.argv:
        actual = ""
        if os.path.exists(SALIDA):
            with open(SALIDA, encoding="utf-8") as f:
                actual = f.read()
        if actual == texto:
            print("tokens.css al dia")
            return 0
        print("tokens.css NO coincide con los artboards. Corre: "
              "python medidas/tokens.py")
        return 1

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    print(f"escrito {SALIDA} ({len(m['globales'])} medidas globales, "
          f"{len(m['por_pestana'])} por pestana)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
