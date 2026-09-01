"""El panel servido como DATOS, para un frontend que no es tkinter.

`registro.py` ya describe cada opcion como dato y `registro.esquema()` lo pasa
entero a JSON. Lo que falta entre eso y una pantalla HTML son cuatro cosas que
hoy solo sabe hacer `gui.Panel`, y las sabe hacer mezcladas con el dibujo:

1. **los valores** que tiene la config ahora mismo, por clave;
2. **el tipo** de cada clave, que sale de `DEFAULTS` y decide como se castea al
   guardar --un `sub_tam` que pasa de entero a texto guarda igual y se rompe
   recien al leerlo--;
3. **las opciones que se arman al abrir**: las voces de SAPI salen de
   consultarle al sistema, y congelarlas al importar daria la lista de la
   maquina que compilo el paquete;
4. **la paleta**, que sale de `tema.resolver` --la MISMA que ya usan el panel,
   el cartel y la ventana de actividad-- para que el HTML no invente colores.

Este modulo no importa tkinter, y eso no es un detalle de prolijidad: es lo que
hace que los dos tests guardianes --los que existen porque olvidarse de una
linea dejo once ajustes sin donde tocarse-- corran sin pantalla, y por lo tanto
tambien en las cinco compilaciones. Hoy se saltean solos donde no hay display.

Con una excepcion medida: `tema.fuentes_disponibles()` le pregunta las familias
al `tkinter.font` que ya estaba ahi. Sin pantalla no explota --devuelve solo la
fuente por defecto-- asi que el esquema se arma igual; la lista completa espera
a que el frontend sepa pedirsela al navegador, que es quien de verdad la sabe.

Lo que NO hace: dibujar, y decidir. Las excepciones (`Propio`) siguen siendo
huecos declarados; aca viajan tal cual para que el frontend sepa que tiene que
poner algo propio ahi, igual que hoy lo sabe `_pintar_registro`.
"""

from . import modulos, plataforma, registro, store, tema, voice
from .textos import t as tr

# --- las opciones que se arman al abrir ------------------------------------
# Por nombre, que es como las nombra el registro (`Campo.opciones` como texto).
# Cada una es una funcion de la config y nada mas: no hay ventana de la que
# depender, que es lo que las ataba a `gui.Panel`.


def _temas_disponibles(_cfg):
    return list(tema.NOMBRES)


def _temas_del_cartel(_cfg):
    """Igual que los del panel, mas el vacio: heredar el del panel."""
    return ["", *tema.NOMBRES]


def _fuentes_disponibles(_cfg):
    return tema.fuentes_disponibles()


def _modelos_api(_cfg):
    return list(registro.MODELOS_API)


def _modelos_cc(_cfg):
    return list(registro.MODELOS_CC)


def _permisos_cc(_cfg):
    return list(registro.PERMISOS_CC)


def _niveles_de_effort(_cfg):
    return list(registro.ESFUERZOS)


def _voces_de_windows(_cfg):
    """Las voces de SAPI instaladas. Se consultan al abrir, no al importar."""
    return voice.list_sapi_voices() or None


def _pantallas(_cfg):
    """Los numeros de monitor que se pueden elegir.

    Se le pregunta al sistema en vez de ofrecer un entero a ciegas: elegir "2"
    sin saber cual es el 2 es adivinar. Si no se pueden enumerar --pasa en
    Linux sin xrandr-- queda solo el 0, que es el comportamiento de siempre, y
    no se ofrece una opcion que no haria nada.
    """
    return ["0", *(str(i) for i, _m in enumerate(plataforma.monitores(), 1))]


def _modelos_del_proveedor(cfg):
    """Los que se le pueden ofrecer al proveedor que este elegido.

    El sugerido del preset mas los que ese servicio contesto la ultima vez que
    se apreto Buscar modelos. No hay lista escrita a mano a proposito: los
    catalogos cambian todas las semanas y una congelada quedaria mintiendo.

    En `gui.py` esto lee `self.vars["compat_proveedor"]` --lo que el usuario
    tiene tipeado ahora, aunque no haya guardado--. Aca lee la config que se le
    pasa, y el frontend le pasa la editada: mismo comportamiento, sin widget.
    """
    from . import compat_engine

    prov = str(cfg.get("compat_proveedor", "")).strip()
    preset = compat_engine.PROVEEDORES.get(prov)
    salida = [preset[2]] if preset and preset[2] else []
    for nombre in store.modelos_vistos(prov):
        if nombre not in salida:
            salida.append(nombre)
    return salida


OPCIONES = {
    "_temas_disponibles": _temas_disponibles,
    "_temas_del_cartel": _temas_del_cartel,
    "_fuentes_disponibles": _fuentes_disponibles,
    "_modelos_api": _modelos_api,
    "_modelos_cc": _modelos_cc,
    "_permisos_cc": _permisos_cc,
    "_niveles_de_effort": _niveles_de_effort,
    "_voces_de_windows": _voces_de_windows,
    "_pantallas": _pantallas,
    "_modelos_del_proveedor": _modelos_del_proveedor,
}


# --- que pestana muestra que tabla del registro ----------------------------
# Los mismos nueve rotulos que arma `gui.Panel`, con su subtitulo y la tabla
# que le toca a cada una. Los rotulos y los subtitulos son los literales de
# `_componer`, no una version mejorada: el chequeo de traduccion los busca por
# el texto en espanol, y un rotulo "mejorado" sale sin traducir.
#
# Ya no hay ninguna con la lista vacia. Hubo cuatro --Cuentas, Contactos,
# Addons y Actividad-- y esa lista vacia era el trabajo que faltaba, escrito
# donde se veia.
PESTANAS = (
    # Dos tablas y UNA pantalla: `gui.py` las compone igual, una abajo de la
    # otra. Las sub-pestanas son solo de Apariencia, que es la unica que las
    # tiene de verdad --y las tiene porque diez secciones apiladas en un scroll
    # obligaban a pasar por delante de todo para cambiar un tamano--.
    ("General", "General",
     "Quien es Eve, quien piensa por ella y hasta donde puede meterse.",
     ("PERFILES", "GENERAL")),
    ("Modelos", "Modelos y claves",
     "Cual piensa, cual te escucha, cual te habla, y la clave de cada uno.",
     ("MODELOS", "SESION_CC")),
    ("Cuentas", "Cuentas",
     "Las apps a las que Eve le escribe. Todo opcional.",
     ("CUENTAS",)),
    ("Comandos", "Comandos",
     "Frases tuyas que hacen algo fijo, sin pasar por el modelo.",
     ("COMANDOS",)),
    ("Voz", "Voz",
     "Como te escucha y como te responde.",
     ("VOZ",)),
    ("Contactos", "Contactos",
     "La agenda que Eve usa cuando nombras a alguien.",
     ("CONTACTOS",)),
    ("Addons", "Addons",
     "Lo que Eve puede manejar ademas de tu PC. Cada uno trae sus comandos.",
     ("ADDONS",)),
    ("Apariencia", "Apariencia",
     "Los colores de todo, y el cartel que Eve muestra "
     "encima de lo que estes haciendo.",
     ("TEMA", "CARTEL", "VENTANA", "SUBTITULOS")),
    ("Actividad", "Actividad",
     "Que se dijo y que se ejecuto en tu PC.",
     ("ACTIVIDAD",)),
)

# Los rotulos de las sub-pestanas de Apariencia, en el orden en que se
# muestran. Salen de `_tab_apariencia`; Modulos no esta porque no es una tabla
# del registro --lo dibuja `modulos.py` con su propio registro de tipos--.
SUBPESTANAS = {"TEMA": "Tema", "CARTEL": "Cartel", "VENTANA": "Ventana",
               "SUBTITULOS": "Subtitulos"}


def claves_declaradas() -> set:
    """Todas las claves de config que el registro dice cubrir."""
    return {c for tabla in registro.TABLAS for c in registro.claves(tabla)}


def _tipo(clave: str, cfg: dict) -> str:
    """Como hay que castear esta clave al guardar.

    Sale de `DEFAULTS`, igual que en `Panel.save()`. Las de modulo se inventan
    en runtime y no estan ahi, asi que las declara su tipo de modulo: sin eso
    una posicion se guardaria como "40" y la cuenta siguiente sumaria cadenas.
    """
    defecto = store.DEFAULTS.get(clave)
    if defecto is None and clave.startswith(modulos.PREFIJO):
        clase = modulos.tipo_de_clave(cfg, clave)
        defecto = clase() if clase else None
    if isinstance(defecto, bool):
        return "bool"
    if isinstance(defecto, int):
        return "int"
    if isinstance(defecto, float):
        return "float"
    if isinstance(defecto, list):
        return "lista"
    return "str"


def _traducir(nodo: dict) -> dict:
    """Los textos de pantalla ya traducidos, para que el frontend no traduzca.

    Se hace de este lado porque el diccionario de `textos.py` tiene la frase en
    espanol como clave: mandarla cruda obligaria a llevar una copia del
    diccionario al HTML, y dos copias es lo que se desfasa.
    """
    salida = dict(nodo)
    for campo in ("etiqueta", "titulo", "texto"):
        if isinstance(salida.get(campo), str) and salida[campo]:
            salida[campo] = tr(salida[campo])
    if isinstance(salida.get("hijos"), list):
        salida["hijos"] = [_traducir(h) for h in salida["hijos"]]
    return salida


def _opciones_vivas(nodos, cfg, destino: dict) -> None:
    """Resuelve las listas que se arman al abrir, por clave."""
    for nodo in nodos:
        if isinstance(nodo.get("hijos"), list):
            _opciones_vivas(nodo["hijos"], cfg, destino)
        opciones = nodo.get("opciones")
        if isinstance(opciones, dict) and "metodo" in opciones:
            arma = OPCIONES.get(opciones["metodo"])
            # Una lista que no se puede armar --no hay voces SAPI en Linux-- no
            # es un error: queda un campo de texto libre, que es exactamente lo
            # que hace hoy `_voces_de_windows` devolviendo None.
            destino[nodo["clave"]] = arma(cfg) if arma else None


def _proveedores_con_clave() -> set:
    """Los nombres de llavero que el registro declara con un nodo `Clave`."""
    def recorrer(bloque, acc):
        for item in bloque:
            if isinstance(item, (registro.Seccion, registro.Fila)):
                recorrer(item.hijos, acc)
            elif isinstance(item, registro.Clave):
                acc.add(item.proveedor)
        return acc

    salida = set()
    for tabla in registro.TABLAS:
        recorrer(tabla, salida)
    return salida


def esquema(cfg: dict = None) -> dict:
    """Todo lo que hace falta para dibujar el panel, de una sola vez.

    Una sola llamada y no cinco porque el frontend la hace al abrir: cinco idas
    y vueltas por el puente de pywebview son cinco oportunidades de que una
    llegue tarde y la pantalla se dibuje a medias.
    """
    cfg = store.load_config() if cfg is None else cfg
    tablas = {nombre: [_traducir(n) for n in nodos]
              for nombre, nodos in registro.esquema().items()}
    opciones: dict = {}
    for nodos in tablas.values():
        _opciones_vivas(nodos, cfg, opciones)

    declaradas = claves_declaradas()
    cuerpo = 0
    try:
        cuerpo = int(cfg.get("ui_fuente_tam", 0) or 0)
    except (TypeError, ValueError):
        cuerpo = 0
    from . import __version__

    return {
        "version": __version__,
        "tablas": tablas,
        "pestanas": [{"clave": clave, "rotulo": tr(rotulo),
                      "subtitulo": tr(sub), "tablas": list(tabs)}
                     for clave, rotulo, sub, tabs in PESTANAS],
        "subpestanas": {k: tr(v) for k, v in SUBPESTANAS.items()},
        "valores": {c: cfg.get(c, store.DEFAULTS.get(c, "")) for c in declaradas},
        "tipos": {c: _tipo(c, cfg) for c in declaradas},
        "opciones": opciones,
        # Las dos tablas que un nodo NO lleva adentro: un `Fondo` viaja con su
        # prefijo y un `Colores` con el suyo, y las siete piezas y los ocho
        # roles estan al lado en el registro. Van servidas y no copiadas al
        # HTML porque justamente los siete rotulos del fondo YA se desfasaron
        # una vez de lo que el panel dibuja, y una copia mas es una copia mas
        # que se puede desfasar.
        "partes_fondo": [[sufijo, tr(etiqueta)]
                         for sufijo, etiqueta in registro._PARTES_FONDO],
        "roles": [[rol, tr(etiqueta)] for rol, etiqueta in registro.ROLES_ETIQUETA],
        # Los diez huecos declarados con sus datos, y lo que cada `Salida` dice
        # antes de que nadie apriete nada. Viajan con el esquema y no en una
        # llamada aparte por lo mismo que todo el resto: el frontend hace UNA
        # ida y vuelta al abrir, y una pantalla que se dibuja a medias porque
        # una de cinco llamadas llego tarde es peor que una que tarda un poco.
        **propios(cfg),
        "salida_de": dict(SALIDA_DE),
        "salidas_al_abrir": list(SALIDAS_AL_ABRIR),
        # Que proveedores YA tienen clave guardada. Solo eso: el valor vive en
        # el llavero y no tiene por que pasar por el HTML para que se dibuje un
        # rotulo. Una clave que viaja al frontend se puede leer desde la
        # consola del navegador.
        "con_clave": sorted(prov for prov in _proveedores_con_clave()
                            if _tiene_clave(prov)),
        "paleta": tema.resolver(cfg, "ui"),
        "escala": {nombre: tema.pt(nombre, cuerpo) for nombre in tema.ESCALA},
        "espacio": list(tema.ESPACIO),
        "modo": str(cfg.get("ui_modo_panel", "esencial")),
    }


def castear(clave: str, valor, cfg: dict):
    """El valor que entro por el puente, con el tipo que le toca.

    Levanta `ValueError` con un mensaje para mostrar. Es la misma decision que
    toma `Panel.save()`, y esta aca en vez de alla porque el frontend no la
    puede tomar: JavaScript manda todo como texto o como booleano.
    """
    tipo = _tipo(clave, cfg)
    if tipo == "bool":
        return bool(valor)
    if tipo == "int":
        try:
            return int(str(valor).strip())
        except ValueError:
            raise ValueError(f"'{clave}' debe ser un numero entero.") from None
    if tipo == "float":
        try:
            return float(str(valor).strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"'{clave}' debe ser un numero.") from None
    if tipo == "lista":
        # Una por renglon, que es como las escribe el cuadro de texto de rutas
        # permitidas. Es la misma regla que `Panel.save()`: sin ella, la unica
        # clave de config que no es un escalar se guardaria como el texto
        # "['C:\\Users\\...']" y quien la lee recorreria sus letras.
        if isinstance(valor, list):
            return [str(x).strip() for x in valor if str(x).strip()]
        return [linea.strip() for linea in str(valor).splitlines() if linea.strip()]
    return valor


def guardar(cambios: dict) -> dict:
    """Escribe SOLO lo que cambio, encima de lo que hay en disco.

    El panel de tkinter guarda las noventa y pico de claves de una y se defiende
    de pisar lo que no tocaste comparando cada widget contra la foto que tomo al
    abrirse. Aca el frontend manda unicamente lo que el usuario edito, asi que
    esa defensa sale de arriba: lo que no viaja, no se toca.

    Devuelve `{"ok", "error", "valores"}`. Los valores que vuelven son los que
    quedaron escritos, para que el frontend no se quede mostrando lo que tipeo
    si el casteo lo cambio --"7,5" queda 7.5--.
    """
    if not isinstance(cambios, dict):
        return {"ok": False, "error": "cambios tiene que ser un objeto"}
    cfg = store.load_config()
    escritas = {}
    for clave, valor in cambios.items():
        try:
            escritas[clave] = castear(clave, valor, cfg)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "clave": clave}
    # Sin ninguna ruta permitida, Eve no puede tocar un solo archivo: el panel
    # de tkinter frena ahi mismo y este tiene que frenar igual. Guardar la
    # lista vacia deja un programa que no dice que no puede hacer nada.
    if "workdirs" in escritas and not escritas["workdirs"]:
        return {"ok": False, "clave": "workdirs",
                "error": tr("Necesitas al menos una ruta de trabajo permitida.")}
    if not escritas:
        return {"ok": True, "error": "", "valores": {}}
    cfg.update(escritas)
    store.save_config(cfg)
    # Lo que cambiaste vos queda anotado: con `autoridad = usuario`, Eve no lo
    # pisa despues. Va tras guardar para no anotar algo que no se escribio.
    store.marcar_tocadas(list(escritas))
    return {"ok": True, "error": "", "valores": escritas}


# --- quien piensa por ella: el catalogo de proveedores ---------------------
# Vive aca y no en `gui.py` porque los dos paneles muestran el MISMO selector,
# y una copia por panel es la copia que se desfasa.

# Los tres motores que no son `compat`. El resto sale de
# `compat_engine.PROVEEDORES`, para que agregar uno alla lo muestre aca sin
# tocar nada: una lista escrita al lado habria que acordarse de actualizarla.
MOTORES_PROPIOS = (
    ("api", "Anthropic", "api", "anthropic", "la nube - Messages API"),
    ("claude-code", "Claude Code", "claude-code", "", "tu suscripcion, sin clave"),
    ("ollama", "Ollama", "ollama", "", "tu maquina - localhost:11434"),
)

# Como se escribe cada uno. La clave del diccionario es un identificador
# --`lmstudio`, `xai`-- y mostrarlo crudo al lado de "Claude Code" queda como
# si faltara terminarlo. Lo que no este aca sale con su id, que es mejor que
# no salir.
NOMBRE_PROVEEDOR = {
    "gemini": "Gemini", "openai": "OpenAI", "groq": "Groq",
    "deepseek": "DeepSeek", "openrouter": "OpenRouter", "xai": "xAI",
    "lmstudio": "LM Studio", "omniroute": "OmniRoute",
    "propio": "Otro servidor",
}


def catalogo_proveedores() -> list:
    """(id, rotulo, engine, clave, donde) de todo lo que puede pensar."""
    from . import compat_engine as ce

    salida = list(MOTORES_PROPIOS)
    for nombre, (url, clave, _modelo) in ce.PROVEEDORES.items():
        donde = "tu maquina" if url.startswith("http://localhost") else "la nube"
        if nombre == "propio":
            # No es un proveedor: es "poneme vos la URL". Se queda, pero dicho
            # como lo que es.
            donde = "el servidor que le pongas abajo"
        salida.append((nombre, NOMBRE_PROVEEDOR.get(nombre, nombre),
                       "compat", clave, donde))
    return salida


def _tiene_clave(clave: str) -> bool:
    try:
        return bool(store.get_key(clave))
    except Exception:  # noqa: BLE001 - el llavero puede no estar disponible
        return False


def proveedores(cfg: dict) -> dict:
    """El selector entero: quien esta elegido, y como esta cada uno.

    Es el pedido que motivo la mudanza: **cada proveedor con su modelo y su
    clave en el mismo lugar**. Antes eran dos controles en dos secciones
    distintas mas una pared de nueve campos de clave sin ninguna senal de cual
    estaba en uso, y por eso podias tener elegido uno y guardado el modelo de
    otro --que es el "el modelo no existe" que aparecia recien al hablarle--.

    Las claves SIEMPRE fueron mutuamente excluyentes: `brain` lee la de
    Anthropic y `compat_engine` la del proveedor elegido, nunca hay dos en
    juego. Esto no cambia el comportamiento, hace visible el que ya habia.

    Nunca viaja una clave, solo si HAY una: el valor vive en el llavero del
    sistema y no tiene por que pasar por el HTML para que se muestre un rotulo.
    """
    from . import compat_engine as ce

    motor = str(cfg.get("engine", "api"))
    prov = str(cfg.get("compat_proveedor", "")).strip()
    cat = catalogo_proveedores()
    elegido = (prov or cat[3][0]) if motor == "compat" else motor
    salida = []
    for ident, rotulo, engine, clave, donde in cat:
        preset = ce.PROVEEDORES.get(ident)
        salida.append({
            "id": ident, "rotulo": rotulo, "engine": engine,
            "clave": clave, "donde": tr(donde),
            "necesita_clave": bool(clave),
            "tiene_clave": _tiene_clave(clave) if clave else False,
            "modelo_sugerido": preset[2] if preset else "",
            "url": preset[0] if preset else "",
        })
    return {"elegido": elegido, "lista": salida}


def elegir_proveedor(cfg: dict, quien: str) -> dict:
    """Las DOS claves que deja escritas elegir uno, sin escribirlas todavia.

    Devuelve el par para que el frontend lo ponga como cambio pendiente: el
    usuario sigue teniendo que apretar Guardar, igual que en el panel viejo.
    Escribirlo solo seria la app poseida que el ajuste de autoridad existe
    para evitar.
    """
    for ident, _rot, motor, _clave, _donde in catalogo_proveedores():
        if ident != quien:
            continue
        valores = {"engine": motor}
        # `compat_proveedor` solo tiene sentido con `compat`; con los otros se
        # deja lo que habia, para no perderle la eleccion si despues vuelve.
        if motor == "compat":
            valores["compat_proveedor"] = ident
        # Y el modelo: cambiar de Groq a Gemini dejaba
        # `llama-3.3-70b-versatile` escrito, que Gemini contesta con un 404
        # recien cuando le hablas. Se pisa SOLO si el que habia no es de este
        # proveedor: uno escrito a mano que sigue valiendo se respeta.
        lista = _modelos_del_proveedor({**cfg, **valores})
        if (motor == "compat" and lista
                and str(cfg.get("compat_modelo", "")).strip() not in lista):
            valores["compat_modelo"] = lista[0]
        return {"ok": True, "valores": valores, "modelos": lista,
                "salida": "   ".join(f"{k}={v}" for k, v in valores.items())}
    return {"ok": False, "salida": f"no conozco el proveedor {quien!r}"}


# --- las acciones ---------------------------------------------------------
# Cada boton del registro es una funcion de aca: recibe la config que el
# usuario tiene EN PANTALLA --no la del disco, porque uno cambia algo y prueba
# sin guardar-- y devuelve texto para mostrar, y opcionalmente claves para
# dejar como cambio pendiente.
#
# Todas son BLOQUEANTES a proposito, incluidas las que salen a la red o abren
# el microfono. pywebview atiende cada llamada del HTML en un hilo propio, asi
# que la ventana no se congela; en tkinter hacia falta un `threading.Thread`
# mas `self.after` para volver al hilo de la interfaz, y ese ida y vuelta es
# justo donde el panel se quedo sordo una vez.
#
# ponytail: sin cancelacion. Si una prueba tarda de mas, el usuario espera.
# Cortarlas pide un protocolo de trabajos con id y sondeo, y todavia no hace
# falta: ninguna de las siete pasa de unos segundos.


def _probar_motor(cfg, _args):
    """Le hace una pregunta trivial al motor configurado y muestra que dijo.

    Arma el MISMO motor que usa el asistente --`listener.armar_motor`-- y no
    una version simplificada: un boton que prueba otro camino puede decir que
    todo anda mientras el camino real esta roto.
    """
    import time as _t

    try:
        from . import listener as lis

        arranque = _t.perf_counter()
        motor = lis.armar_motor(cfg)
        # Sin herramientas ni contexto: lo que se prueba es que la conexion, la
        # clave y el modelo existan, no que sepa razonar.
        respuesta = motor.ask("Responde solo con la palabra: listo")
        tardo = _t.perf_counter() - arranque
        corto = " ".join(str(respuesta).split())[:70]
        return {"salida": f"{cfg.get('engine')} contesto en {tardo:.1f}s: {corto!r}"}
    except Exception as exc:  # noqa: BLE001 - el panel no puede morir
        return {"ok": False, "salida": f"{type(exc).__name__}: {str(exc)[:150]}"}


def _probar_stt(cfg, _args):
    """Graba tres segundos del microfono y los transcribe.

    El camino entero y no una pieza: microfono, sensibilidad, modelo y
    vocabulario, que es donde de verdad falla.
    """
    try:
        import time as _t

        import numpy as np

        rec = voice.Recorder()
        rec.start()
        _t.sleep(3.0)
        audio = rec.stop()
        if audio.size < 1000:
            return {"ok": False, "salida":
                    "No entro audio. Esta tomado el microfono por otro programa?"}
        pico = 20 * np.log10(max(1e-9, float(np.abs(audio).max())))
        texto = voice.transcribe(audio, cfg)
        _umbral, _aire, modo = voice.sensibilidad(cfg)
        if not texto:
            return {"salida": f"No entendi nada. Pico {pico:.0f} dBFS, modo {modo}. "
                              "Si el pico es menor a -40 el microfono esta muy bajo."}
        return {"salida": f"Te escuche: {texto!r}   (pico {pico:.0f} dBFS, modo {modo})"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "salida": f"Fallo escuchando: {type(exc).__name__}: {exc}"}


def _probar_tts(cfg, _args):
    """Dice una frase con la voz configurada."""
    try:
        voice.speak("Hola, soy " + str(cfg.get("assistant_name", "Eve"))
                    + ". Si escuchas esto, la voz anda.", cfg)
        return {"salida": f"Listo. Voz: {cfg.get('tts_provider')} / "
                          f"{cfg.get('piper_voice') or '-'}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "salida": f"Fallo hablando: {type(exc).__name__}: {exc}"}


def _probar_wake(cfg, _args):
    """Abre el microfono unos segundos y dice si la puerta se habria abierto.

    Es la unica forma de probar la palabra clave sin dejar el microfono
    abierto todo el dia: se graba a mano, se le pasa el mismo recorte al mismo
    modelo de la puerta, y se dice que separo.
    """
    segundos = 4.0
    try:
        import time as _t

        from . import despertar

        rec = voice.Recorder()
        rec.start()
        _t.sleep(segundos)
        audio = rec.stop()
        if audio.size < 1000:
            return {"ok": False, "salida":
                    "no entro audio; el microfono puede estar tomado"}
        orden = despertar.escuchado(audio, cfg)
        if orden is None:
            texto = voice.transcribe(audio, cfg)
            return {"salida": f"la puerta NO se abrio. Se escucho {texto!r}; la "
                              f"palabra tiene que ir al principio y ser una de "
                              f"{cfg.get('wake_palabra')!r}"}
        if not orden:
            return {"salida": "se abrio, pero no quedo ninguna orden detras del nombre"}
        return {"salida": f"se abrio y quedo la orden: {orden!r}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "salida": f"{type(exc).__name__}: {str(exc)[:150]}"}


def _gpu_probar(cfg, _args):
    """Carga el modelo en la GPU y transcribe algo.

    Elegir 'cuda' en el desplegable no daba ninguna senal: si faltaba una DLL,
    Eve caia a CPU sola y en silencio, y la unica pista era que seguia tardando
    lo mismo. Esto contesta antes de hablarle.
    """
    return {"salida": voice.probar_gpu(cfg)}


def _probar_overlay(cfg, _args):
    """Hace aparecer el cartel unos segundos, este en el modo que este.

    Sirve para separar "el cartel esta mal configurado" de "el cartel no
    arranca": si aparece, el problema es cuando se muestra y no si existe.
    """
    from . import overlay

    overlay.asegurar(cfg)
    store.emitir_overlay({
        "estado": "hablando", "detalle": "PRUEBA DEL CARTEL", "nivel": 0.5,
        "titulo": str(cfg.get("assistant_name", "Eve")).upper(),
        "usuario": "probando el cartel", "eve": "Si ves esto, el cartel anda.",
    })
    return {"salida": tr("Cartel mostrado unos segundos. Si no aparecio, revisa "
                         "'Cuando se ve' y 'Pantalla' mas abajo.")}


def _probar_subtitulo(cfg, _args):
    """Muestra un subtitulo de prueba.

    Es un camino distinto al del cartel --otra ventana, otro tamano, otra
    cantidad de lineas-- asi que el boton del cartel no lo cubre: se puede ver
    el cartel perfecto y no leer nunca un subtitulo.
    """
    from . import overlay

    overlay.asegurar(cfg)
    store.emitir_overlay({
        "estado": "hablando", "detalle": "PRUEBA DE SUBTITULOS", "nivel": 0.4,
        "titulo": str(cfg.get("assistant_name", "Eve")).upper(),
        "usuario": "esto es lo que dijiste tu",
        "eve": "Y esto es lo que responde Eve. Si lees estas dos lineas, "
               "los subtitulos andan.",
    })
    return {"salida": tr("Subtitulo de prueba mostrado. Si no aparecio, revisa "
                         "'Que se muestra' y los segundos en pantalla.")}


def _rescan_apps(_cfg, args):
    """Vuelve a recorrer el disco buscando juegos y programas.

    Con `scan` en falso es lo que hacia `_apps_al_abrir`: llenar el conteo sin
    salir a recorrer el disco. Es la misma funcion porque es el mismo texto:
    tenerlas separadas fue lo que dejo dos formas de decir lo mismo.
    """
    from . import apps

    datos = apps.load(refresh=bool((args or {}).get("scan", True)))
    return {"salida": f"{len(datos['games'])} juegos (Steam, Ubisoft, Epic) y "
                      f"{len(datos['apps'])} programas del menu inicio."}


def _abrir_consola(_cfg, _args):
    from . import consola

    consola.abrir()
    return {"salida": tr("ventana de actividad abierta")}


def _mods_semilla_tablero(_cfg, _args):
    """Un tablero que ya muestre algo, en vez de una ventana en blanco."""
    from . import modulos as mods

    cfg = store.load_config()
    for ident, m in mods.por_defecto_tablero().items():
        cfg = mods.guardar(cfg, dict(m, id=ident))
    store.save_config(cfg)
    return {"salida": tr("tablero armado: abre la ventana de actividad"),
            "recargar": True}


def _overlay_mover(_cfg, _args):
    """Suelta el cartel para arrastrarlo con el mouse.

    Escribe en el disco y no como cambio pendiente, a diferencia de casi todo
    lo demas: el cartel es OTRO PROCESO y lee la config del archivo, asi que un
    cambio que se queda en el panel no lo suelta.
    """
    from . import overlay

    cfg = store.load_config()
    cfg["overlay_mover"] = True
    store.save_config(cfg)
    overlay.asegurar(cfg)
    return {"salida": tr("El cartel esta suelto: arrastralo a donde quieras y "
                         "sueltalo. Al soltarlo se guarda la posicion y vuelve "
                         "a dejar pasar los clics."),
            "recargar": True}


def _overlay_esquina(_cfg, _args):
    """Devuelve el cartel a la esquina de arriba a la izquierda."""
    cfg = store.load_config()
    cfg.update({"hud_x": 40, "hud_y": 40})
    store.save_config(cfg)
    return {"salida": tr("El cartel vuelve a la esquina de arriba a la izquierda."),
            "recargar": True}


def _hotkey_capturar(_cfg, args):
    """Toma la proxima tecla que aprietes y la devuelve.

    Pasa por `plataforma.hook_teclado`, que es **el mismo backend con el que el
    listener registra**: `Listener._on_event` compara contra el nombre que le
    llega de ese hook, asi que capturar por ahi hace que lo guardado sea
    reconocible por construccion. Con el keydown del navegador saldria `F13`
    donde el listener espera `f13`, y quedaria una tecla que no responde nunca.

    Y por eso NO se aceptan combinaciones aunque el hook las podria armar: el
    listener compara UN nombre, asi que guardar `ctrl+k` seria dejar puesta una
    tecla que no puede coincidir con nada. Una perilla que miente es peor que
    una que falta.
    """
    import threading

    from . import plataforma

    tope = float((args or {}).get("segundos", 15))
    listo = threading.Event()
    caja = {}

    def llego(nombre, tipo):
        if tipo == "down" and not caja:
            caja["nombre"] = nombre
            listo.set()

    handle = plataforma.hook_teclado(llego)
    try:
        # Con tope: esperar para siempre una tecla que nadie va a apretar es
        # peor que escribirla a mano.
        if not listo.wait(tope):
            return {"ok": False, "salida": tr("no llego ninguna tecla")}
    finally:
        plataforma.unhook_teclado(handle)
    nombre = caja["nombre"]
    if nombre in ("esc", "escape"):
        return {"ok": False, "salida": tr("cancelado")}
    return {"salida": f"{tr('tecla')}: {nombre}. {tr('Recuerda Guardar.')}",
            "valores": {"hotkey": nombre}}


def _probar_tecla(cfg, args):
    """Dice si la tecla que llego es la configurada, y si alguien la escucha.

    La mitad importante es lo que NO prueba: la tecla la escucha el asistente
    con un hook global desde otro proceso. Que este panel la reciba no
    garantiza que el asistente la reciba con un juego en primer plano, y hacer
    creer eso seria peor que no tener el boton.

    El navegador captura la tecla y la manda; aca se compara. Igual que en
    tkinter, donde la capturaba el `<Key>` de la ventana.
    """
    recibida = str((args or {}).get("recibida", "")).strip()
    if not recibida:
        return {"ok": False, "salida": tr("no llego ninguna tecla")}
    esperada = str(cfg.get("hotkey", ""))
    coincide = (recibida.lower().replace("kp_", "")
                == esperada.lower().replace("num ", ""))
    estado = ("el asistente esta corriendo" if store.latido()
              else "OJO: el asistente NO esta corriendo, asi que aunque la tecla "
                   "ande nadie la va a escuchar")
    if coincide:
        return {"salida": f"llego '{recibida}', que es la configurada. {estado}."}
    return {"salida": f"llego '{recibida}' y la configurada es '{esperada}'. "
                      f"Si es la que querias, ponla arriba. {estado}."}


def _voz_del_dialecto(cfg, _args):
    """Pone la voz que le corresponde a la variante elegida.

    Con un boton y no solo: cambiar la voz de alguien porque toco otro control
    es exactamente la app poseida que el ajuste de autoridad existe para
    evitar. Se ofrece, no se impone.
    """
    from . import voices

    elegido = str(cfg.get("dialecto", ""))
    clave = store.voz_del_dialecto(elegido)
    if not clave:
        return {"ok": False, "salida": tr("Elige una variante primero.")}
    aviso = ""
    if clave not in voices.instaladas():
        try:
            aviso = voices.descargar(clave) + " "
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "salida": f"No pude bajarla: {exc}"}
    return {"salida": f"{aviso}Voz puesta en {clave}. Guarda para aplicarlo.",
            "valores": {"piper_voice": clave, "tts_provider": "piper"}}


def _compat_buscar_modelos(cfg, _args):
    """Le pregunta al servicio que modelos tiene.

    Con la config de PANTALLA y no la del disco: uno cambia el proveedor y
    aprieta buscar sin guardar, y leer del disco preguntaria al servicio
    anterior y devolveria una lista que no tiene nada que ver con lo que se
    esta mirando. Eso ya lo resuelve `accion()`, que arma la base asi.
    """
    from . import compat_engine

    try:
        motor = compat_engine.CompatEve.__new__(compat_engine.CompatEve)
        motor.cfg = cfg
        motor._destino(motor.cfg)
        lista = motor.modelos()
    except Exception as exc:  # noqa: BLE001 - la red falla de mil formas
        return {"ok": False, "salida": f"{tr('no pude preguntarle')}: {str(exc)[:120]}"}
    store.recordar_modelos(motor.proveedor, lista)
    return {"salida": f"{len(lista)} modelos", "modelos": lista}


def _forma_elegida(_cfg, args):
    """Una forma del catalogo es un atajo que llena los cuatro numeros."""
    from . import overlay

    valores = overlay.FORMAS.get(str((args or {}).get("forma", "")))
    if not valores:
        return {"ok": False, "salida": tr("Elige una forma.")}
    lados, rot, redondeo = valores
    return {"valores": {"hud_marco_lados": lados, "hud_marco_rot": rot,
                        "hud_marco_redondeo": redondeo}}


def _icono_elegir(_cfg, _args):
    """La imagen del icono del cartel: elegir un archivo y dejar su RUTA.

    Este modulo no abre el cuadro del sistema --no tiene ventana, y tenerla
    seria depender de la interfaz-- asi que DECLARA que hay que elegir y para
    que clave, y el frontend lo hace. Es la misma division que en todo lo demas
    y la que deja el resto probable sin pantalla.

    La ruta y no el contenido: la imagen se lee cada vez que se dibuja el
    cartel, asi que lo que se guarda es donde esta.
    """
    return {"elegir_archivo": {
        "clave": "hud_icono",
        "titulo": tr("Imagen para el icono"),
        "filtros": ["Imagenes y sprite sheets (*.png;*.gif;*.webp;*.apng;"
                    "*.jpg;*.jpeg;*.bmp)", "*"]}}


def _turno_bajar(_cfg, args):
    """Baja smart-turn-v3, y solo cuando el usuario aprieta el boton.

    Es la unica descarga del programa que no arranca sola en ningun camino:
    ni al abrir, ni al primer uso, ni al prender el modo. Bajar 8 MB de un
    tercero lo decide quien usa el programa, y apretar este boton es esa
    decision. Si ya esta, no lo vuelve a bajar: dice donde quedo.
    """
    from . import turno

    if turno.disponible() and not (args or {}).get("de_nuevo"):
        return {"salida": turno.estado()}
    return {"salida": turno.descargar()}


def _texto_turno_label(_cfg):
    """Si el modelo esta, y si no, que es y de donde sale."""
    from . import turno

    return turno.estado()


def _elegir_proveedor(cfg, args):
    return elegir_proveedor(cfg, str((args or {}).get("id", "")))


def _guardar_clave(_cfg, args):
    """La clave del proveedor, al llavero del sistema. Nunca al config.json.

    Va aca, al lado de la eleccion del proveedor, porque ese era el pedido: cada
    proveedor con SU clave. Antes vivian todas juntas en otra pestana, nueve
    campos uno abajo del otro sin ninguna senal de cual estaba en uso.

    La clave viaja en UN solo sentido --entra cuando la escribis-- y nunca
    vuelve: el panel muestra "clave cargada" o "sin clave", no el valor. Una
    clave que viaja al HTML para dibujar asteriscos es una clave que se puede
    leer desde la consola del navegador.
    """
    clave = str((args or {}).get("proveedor", "")).strip()
    valor = str((args or {}).get("valor", ""))
    if not clave:
        return {"ok": False, "salida": tr("Ese proveedor no necesita clave.")}
    # Todo asteriscos es lo que muestra un campo enmascarado sin tocar: no es
    # una clave nueva, es que no la reescribiste.
    if valor and set(valor) == {"*"}:
        return {"ok": True, "salida": ""}
    try:
        store.set_key(clave, valor)
    except Exception as exc:  # noqa: BLE001 - el llavero puede no estar
        return {"ok": False, "salida": f"{tr('no pude guardarla')}: {exc}"}
    if not valor:
        return {"ok": True, "salida": f"{tr('clave borrada')}: {clave}",
                "tiene_clave": False}
    return {"ok": True, "salida": f"{tr('clave guardada')}: {clave}",
            "tiene_clave": True}


ACCIONES = {
    "probar_motor": _probar_motor,
    "probar_stt": _probar_stt,
    "probar_tts": _probar_tts,
    "probar_wake": _probar_wake,
    "gpu_probar": _gpu_probar,
    "probar_overlay": _probar_overlay,
    "probar_subtitulo": _probar_subtitulo,
    "rescan_apps": _rescan_apps,
    "_abrir_consola": _abrir_consola,
    "_mods_semilla_tablero": _mods_semilla_tablero,
    "_overlay_mover": _overlay_mover,
    "_overlay_esquina": _overlay_esquina,
    "hotkey_capturar": _hotkey_capturar,
    "probar_tecla": _probar_tecla,
    "voz_del_dialecto": _voz_del_dialecto,
    "compat_buscar_modelos": _compat_buscar_modelos,
    "_forma_elegida": _forma_elegida,
    "_icono_elegir": _icono_elegir,
    "turno_bajar": _turno_bajar,
    "elegir_proveedor": _elegir_proveedor,
    "guardar_clave": _guardar_clave,
}


def accion(nombre: str, cfg: dict = None, args: dict = None) -> dict:
    """Corre una accion y devuelve `{ok, salida, valores, ...}`.

    `cfg` es lo que el usuario tiene EN PANTALLA, con los cambios sin guardar
    aplicados encima de lo que hay en disco. Es lo que hacia `_cfg_de_pantalla`
    en el panel viejo, y hace falta por lo mismo: uno cambia el proveedor y
    aprieta Probar sin guardar, y probar el anterior seria mentir.

    `valores` NO se escriben: vuelven para que el frontend los deje como cambio
    pendiente y el usuario apriete Guardar. Las dos del cartel si escriben, y
    lo dicen con `recargar`, porque el cartel es otro proceso y lee del archivo.
    """
    fn = ACCIONES.get(nombre)
    if fn is None:
        return {"ok": False, "salida": f"no conozco la accion {nombre!r}",
                "valores": {}}
    base = store.load_config()
    if isinstance(cfg, dict):
        base.update(cfg)
    try:
        r = fn(base, args or {})
    except Exception as exc:  # noqa: BLE001 - una accion no puede tirar el panel
        return {"ok": False, "salida": f"{type(exc).__name__}: {str(exc)[:200]}",
                "valores": {}}
    r.setdefault("ok", True)
    r.setdefault("salida", "")
    r.setdefault("valores", {})
    return r


# --- los huecos declarados, con sus datos ---------------------------------
# Un `Propio` del registro es una excepcion DECLARADA: un control con logica
# propia. En tkinter cada uno es un metodo que dibuja a mano; aca cada uno es
# una funcion que devuelve DATOS y un componente del HTML que los dibuja. La
# division es la misma que en todo el modulo, y es lo que hace que se puedan
# probar sin abrir una ventana --lo de tkinter no se puede--.

# Los dos rotulos del selector de permisos. Salen de `gui.py` para que digan
# exactamente lo mismo: es el freno, y dos redacciones del mismo freno es como
# alguien termina creyendo que eligio otra cosa.
PERM_ASK = "Preguntar antes de acciones riesgosas (recomendado)"
PERM_ALL = "Permitir todo sin preguntar"


def _propio_rutas_permitidas(cfg):
    """El cuadro de rutas de trabajo: varias lineas, una por ruta."""
    return {"componente": "rutas", "clave": "workdirs",
            "etiqueta": tr("Rutas de trabajo permitidas (una por linea)"),
            "valor": list(cfg.get("workdirs", []))}


def _propio_selector_de_permisos(cfg):
    """El freno. Guarda la NEGACION de su clave, por eso no es una fila.

    El desplegable dice "permitir todo" y la clave se llama
    `confirm_destructive`: son opuestos, y por eso `save()` lo traduce en vez
    de guardarlo derecho.
    """
    return {"componente": "permisos", "clave": "confirm_destructive",
            "etiqueta": tr("Permisos"),
            "opciones": [tr(PERM_ASK), tr(PERM_ALL)],
            "valor": tr(PERM_ASK) if cfg.get("confirm_destructive", True) else tr(PERM_ALL)}


def _propio_selector_proveedor(cfg):
    """Quien piensa por ella: uno solo, con su modelo y su clave al lado."""
    return {"componente": "proveedores", **proveedores(cfg)}


def _propio_ayuda_compat(_cfg):
    """La ayuda del motor compatible, que arma su texto con una lista.

    No toca ninguna clave, pero el texto se concatena con los proveedores que
    tienen capa gratuita, y eso no es un literal: por eso es un `Propio` y no
    una `Ayuda`.
    """
    from .compat_engine import GRATIS

    return {"componente": "ayuda", "texto":
            tr("Los dos vacios = el modelo sugerido y la URL del proveedor.")
            + "\n" + tr("Con capa gratuita: ") + ", ".join(GRATIS) + ".\n"
            + tr("La clave de cada uno va arriba, al lado del proveedor. 'propio'\n"
                 "sirve para cualquier servidor que hable /chat/completions.")}


def _propio_cabecera_del_panel(cfg):
    """La imagen de cabecera: un campo, elegir archivo y quitar."""
    return {"componente": "archivo", "clave": "ui_banner",
            "etiqueta": tr("Imagen (PNG o GIF)"),
            "valor": str(cfg.get("ui_banner", "")),
            "filtros": ["Imagenes (*.png;*.gif;*.jpg;*.jpeg;*.webp;*.bmp)", "*"]}


def _propio_atajos_de_forma(_cfg):
    """El desplegable de formas: no guarda una clave, LLENA otras cuatro."""
    from . import overlay

    return {"componente": "formas", "etiqueta": tr("Formas"),
            "opciones": sorted(overlay.FORMAS)}


def _propio_skills_lista(_cfg):
    """Las skills instaladas. No es un `Campo` porque son archivos, no una clave."""
    return {"componente": "skills", "lista": [
        {"nombre": nombre, "resumen": renglon}
        for nombre, renglon in _skills().resumen()]}


def _propio_comandos_lista(cfg):
    """Lo que dice Comandos.md, con su estado de aprobacion."""
    return {"componente": "comandos", **_comandos_estado(cfg)}


def _propio_apps_al_abrir(_cfg):
    """Llena el conteo de programas SIN salir a escanear el disco."""
    return {"componente": "salida", "atributo": "apps_label",
            "texto": _rescan_apps(None, {"scan": False})["salida"]}


def _propio_previa_primera_vez(_cfg):
    """La vista previa del cartel. NO se porta, y esta escrito por que.

    El cartel se queda en Canvas: es una decision cerrada del acuerdo, tomada
    porque hoy es la parte que mejor se ve --la dibuja un pintor propio, con
    GPU-- y porque pywebview no hace transparencia en Windows. La previa es ese
    mismo pintor, asi que mudarla sola significaria tener dos dibujantes del
    cartel y que la previa mienta sobre el cartel de verdad.
    """
    return {"componente": "sin_portar", "metodo": "_previa_primera_vez",
            "razon": tr("La vista previa la dibuja el mismo pintor que el cartel, "
                        "y el cartel se queda en Canvas.")}


PROPIOS = {
    "_rutas_permitidas": _propio_rutas_permitidas,
    "_selector_de_permisos": _propio_selector_de_permisos,
    "_selector_proveedor": _propio_selector_proveedor,
    "_ayuda_compat": _propio_ayuda_compat,
    "_cabecera_del_panel": _propio_cabecera_del_panel,
    "_atajos_de_forma": _propio_atajos_de_forma,
    "_skills_lista": _propio_skills_lista,
    "_comandos_lista": _propio_comandos_lista,
    "_apps_al_abrir": _propio_apps_al_abrir,
    "_previa_primera_vez": _propio_previa_primera_vez,
}

# Lo que cada `Salida` del registro dice apenas se abre el panel, antes de que
# nadie apriete nada. En tkinter esto era un gancho por nombre
# (`_texto_<atributo>`); aca es una tabla, por lo mismo: para que el pintor no
# tenga que conocer casos particulares.
def _texto_motor_dibujo_label(cfg):
    """Que motor de dibujo quedo activo, y por que.

    `motor_dibujo` puede pedir Skia y quedarse en Pillow porque la maquina no
    da, y un ajuste que no hace lo que dice tiene que decirlo sin que se lo
    pregunten.
    """
    from . import gpu

    return gpu.por_que(cfg)


SALIDAS_INICIALES = {"motor_dibujo_label": _texto_motor_dibujo_label,
                     "turno_label": _texto_turno_label}

# Donde va a parar lo que dice cada boton. En tkinter esto no era una tabla:
# cada metodo escribia en el rotulo que conocia (`self.wake_label.config(...)`),
# asi que el registro declaraba la `Salida` en un lado y el metodo la elegia en
# el otro. Aca se declara, que es lo que le permite al frontend ponerlo donde
# va sin conocer una sola accion. Lo que no este nombrado va a la linea de
# estado del pie, que es donde iba en el panel viejo.
SALIDA_DE = {
    "probar_motor": "motor_label",
    "probar_wake": "wake_label",
    "gpu_probar": "gpu_label",
    "hotkey_capturar": "tecla_label",
    "probar_tecla": "tecla_label",
    "compat_buscar_modelos": "compat_estado",
    "rescan_apps": "apps_label",
    "turno_bajar": "turno_label",
}


def propios(cfg: dict = None) -> dict:
    """Los datos de cada hueco declarado, y los textos iniciales de las salidas.

    Uno que falle no puede tumbar el panel: se devuelve el hueco diciendo que
    fallo. Es la misma decision que ya toma `_pintar_registro` con las salidas
    iniciales --abrir el panel no puede fallar porque una etiqueta no se
    llene-- y aca vale mas, porque estos leen archivos y el llavero.
    """
    cfg = store.load_config() if cfg is None else cfg
    salida = {}
    for nombre, fn in PROPIOS.items():
        try:
            salida[nombre] = fn(cfg)
        except Exception as exc:  # noqa: BLE001
            salida[nombre] = {"componente": "error", "metodo": nombre,
                              "texto": f"{type(exc).__name__}: {str(exc)[:150]}"}
    iniciales = {}
    for atributo, fn in SALIDAS_INICIALES.items():
        try:
            iniciales[atributo] = fn(cfg)
        except Exception:  # noqa: BLE001
            iniciales[atributo] = ""
    return {"huecos": salida, "salidas": iniciales}


# --- skills ---------------------------------------------------------------


def _skills():
    from . import skills

    return skills


def _skills_listar(_cfg, _args):
    return {"salida": "", "skills": [
        {"nombre": n, "resumen": r} for n, r in _skills().resumen()]}


def _skills_importar(_cfg, args):
    """Copia los .md elegidos a la carpeta de skills, uno por uno.

    Uno que falla no cancela los demas, y se informan los dos lados: importar
    cinco y que uno este mal tiene que dejar cuatro puestas y decir cual no.
    """
    import os as _os

    rutas = list((args or {}).get("rutas") or [])
    if not rutas:
        return {"ok": False, "salida": tr("No elegiste ninguna.")}
    hechos, fallos = [], []
    for ruta in rutas:
        corto = _os.path.basename(str(ruta))
        try:
            _skills().importar(str(ruta))
        except ValueError as exc:
            fallos.append(f"{corto}: {exc}")
        except OSError as exc:
            fallos.append(f"{corto}: {tr('no pude copiarla')}: {exc}")
        else:
            hechos.append(corto)
    partes = []
    if hechos:
        partes.append(f"{len(hechos)} " + tr("importadas") + ": " + ", ".join(hechos))
    if fallos:
        partes.append(tr("no entraron") + ": " + "; ".join(fallos))
    return {"ok": bool(hechos), "salida": "  ".join(partes),
            "skills": [{"nombre": n, "resumen": r} for n, r in _skills().resumen()]}


def _skills_borrar(_cfg, args):
    nombre = str((args or {}).get("nombre", ""))
    if nombre not in _skills().instaladas():
        return {"ok": False, "salida": f"{tr('no encuentro')} {nombre}"}
    _skills().borrar(nombre)
    return {"salida": f"{tr('Borrada')}: {nombre}",
            "skills": [{"nombre": n, "resumen": r} for n, r in _skills().resumen()]}


# --- comandos -------------------------------------------------------------


def _comandos_estado(cfg: dict) -> dict:
    """La lista con el estado de cada uno, y cuantos frenan.

    Se lee del ARCHIVO cada vez y no de la config: el archivo es la fuente, y
    tener una copia al lado es garantizar que un dia digan cosas distintas.
    """
    from . import comandos as mod

    filas = mod.leer()
    lista = []
    for c in filas:
        if c["tipo"] == "sistema":
            estado = tr("aprobado") if mod.aprobado(c, cfg) else tr("SIN APROBAR")
        else:
            estado = tr("sin riesgo")
        lista.append({"frases": c["frases"], "tipo": c["tipo"],
                      "valor": c["valor"], "estado": estado,
                      "aprobado": mod.aprobado(c, cfg)})
    faltan = sum(1 for c in lista if not c["aprobado"])
    if not lista:
        resumen = tr("Todavia no hay comandos. Abre el archivo y escribe uno.")
    elif faltan:
        resumen = f"{faltan} {tr('sin aprobar: esas frases no hacen nada todavia.')}"
    else:
        resumen = tr("Todos listos.")
    return {"lista": lista, "resumen": resumen, "tipos": list(mod.TIPOS),
            "acciones": list(mod.ACCIONES),
            "columnas": [tr("Frase"), tr("Tipo"), tr("Hace"), tr("Estado")]}


def _cmd_de(args) -> dict:
    """El comando que el frontend nombro, buscado por CONTENIDO.

    Por contenido y no por indice: entre que se pinto la lista y llego este
    clic, el archivo pudo cambiar desde el editor. Es la misma razon por la que
    `comando_borrar` compara por identidad de contenido en el panel viejo.
    """
    from . import comandos as mod

    quiero = (list((args or {}).get("frases") or []), (args or {}).get("tipo", ""),
              (args or {}).get("valor", ""))
    for c in mod.leer():
        if (c["frases"], c["tipo"], c["valor"]) == tuple(quiero):
            return c
    return {}


def _comandos_listar(cfg, _args):
    return {"salida": "", "comandos": _comandos_estado(cfg)}


def _comandos_aprobar(cfg, args):
    """Aprueba ESTE texto. Editarlo despues lo vuelve a frenar.

    Se aprueba por hash del tipo y el valor, no de la frase: cambiarle el texto
    al comando invalida la aprobacion --es lo que se aprobo-- y renombrar la
    frase con la que lo llamas, no.
    """
    from . import comandos as mod

    cmd = _cmd_de(args)
    if not cmd:
        return {"ok": False, "salida": tr("Elige uno de la lista.")}
    if cmd["tipo"] != "sistema":
        return {"ok": False, "salida": tr("Ese no corre nada: no hace falta aprobarlo.")}
    mod.aprobar(cmd)
    cfg = store.load_config()
    return {"salida": f"{tr('Aprobado')}: {cmd['frases'][0]}",
            "comandos": _comandos_estado(cfg)}


def _comandos_borrar(cfg, args):
    from . import comandos as mod

    cmd = _cmd_de(args)
    if not cmd:
        return {"ok": False, "salida": tr("Elige uno de la lista.")}
    quedan = [c for c in mod.leer()
              if (c["frases"], c["tipo"], c["valor"])
              != (cmd["frases"], cmd["tipo"], cmd["valor"])]
    mod.escribir(quedan)
    return {"salida": f"{tr('Borrado')}: {cmd['frases'][0]}",
            "comandos": _comandos_estado(cfg)}


def _comandos_guardar(cfg, args):
    """Alta y edicion, sin salir del panel.

    El archivo sigue siendo la fuente: esto lee, cambia y lo reescribe entero.
    Tener el panel guardando en un lado y el .md en otro es como se terminan
    teniendo dos verdades.
    """
    from . import comandos as mod

    args = args or {}
    partes = [p.strip() for p in str(args.get("frases", "")).split("|") if p.strip()]
    if not partes:
        return {"ok": False, "salida": tr("Falta la frase.")}
    valor = str(args.get("valor", "")).strip()
    if not valor:
        return {"ok": False, "salida": tr("Falta lo que hace.")}
    tipo = str(args.get("tipo", "")) or list(mod.TIPOS)[0]
    nuevo = {"frases": partes, "tipo": tipo, "valor": valor}
    anterior = _cmd_de(args.get("anterior") or {})
    lista = mod.leer()
    if anterior:
        lista = [nuevo if (c["frases"], c["tipo"], c["valor"])
                 == (anterior["frases"], anterior["tipo"], anterior["valor"]) else c
                 for c in lista]
    else:
        lista.append(nuevo)
    # Dos comandos con la misma frase serian una moneda al aire: gana el
    # primero que aparezca en el archivo y el otro no anda nunca.
    dichas = [mod.normalizar(f) for c in lista for f in c["frases"]]
    repetida = next((d for d in dichas if dichas.count(d) > 1), "")
    if repetida:
        return {"ok": False, "salida": f"{tr('Esa frase ya esta usada')}: {repetida}"}
    mod.escribir(lista)
    return {"salida": f"{tr('Guardado')}: {partes[0]}",
            "comandos": _comandos_estado(cfg)}


def _comandos_probar(cfg, args):
    """Lo corre ahora y devuelve TODO lo que paso.

    Un `sistema` sin aprobar NO se corre, ni siquiera desde aca: probar seria
    el atajo perfecto para saltear el freno. Se dice, y el frontend deja el
    boton de aprobar a un clic.

    Vuelve la salida entera --con el codigo de retorno y cuanto tardo-- y no
    recortada a 300 caracteres: para un comando que falla, el principio del
    error es justo la parte que no sirve.
    """
    from . import comandos as mod

    cmd = _cmd_de(args)
    if not cmd:
        return {"ok": False, "salida": tr("Elige uno de la lista.")}
    if cmd["tipo"] == "sistema" and not mod.aprobado(cmd, cfg):
        return {"ok": False, "aprobar": True,
                "salida": tr("Sin aprobar: no se corre. Revisalo con "
                             "'Revisar y aprobar'.")}
    if cmd["tipo"] == "sistema":
        store.log_action("comandos", "probar",
                         f"{cmd['frases'][0]}: {cmd['valor'][:120]}")
        r = mod.correr_sistema(cmd["valor"])
        if r["timeout"]:
            cuerpo = (f"{tr('Se corto a los')} {r['timeout']}s.\n\n"
                      + tr("El comando seguia corriendo."))
        else:
            cuerpo = (f"{tr('codigo de retorno')}: {r['codigo']}\n"
                      f"{tr('tardo')}: {r['segundos']:.2f}s\n\n"
                      f"--- salida ---\n{r['salida'] or '(vacia)'}\n\n"
                      f"--- errores ---\n{r['error'] or '(ninguno)'}")
    else:
        que, dato = mod.ejecutar(cmd, cfg)
        cuerpo = (f"{tr('le mandaria al modelo')}:\n\n{dato}"
                  if que == "prompt" else str(dato))
    return {"salida": f"{tr('Probado')}: {cmd['frases'][0]}",
            "titulo": f"{tr('Probar')}: {cmd['frases'][0]}",
            "cuerpo": f"{cmd['tipo']}: {cmd['valor']}\n\n{cuerpo}"}


def _comandos_abrir_archivo(_cfg, _args):
    from . import comandos as mod, plataforma

    ruta = mod.asegurar_archivo()
    plataforma.abrir(ruta)
    return {"salida": ruta}


ACCIONES.update({
    "skills_listar": _skills_listar,
    "skills_importar": _skills_importar,
    "skills_borrar": _skills_borrar,
    "comandos_listar": _comandos_listar,
    "comandos_aprobar": _comandos_aprobar,
    "comandos_borrar": _comandos_borrar,
    "comandos_guardar": _comandos_guardar,
    "comandos_probar": _comandos_probar,
    "comandos_abrir_archivo": _comandos_abrir_archivo,
})


# --- las cuatro pestanas que faltaban -------------------------------------
# Cuentas, Contactos, Addons y Actividad, mas los dos bloques que `gui.py`
# componia al lado del registro: la galeria de perfiles y la sesion de Claude
# Code. Mismo reparto que todo lo de arriba: aca los DATOS y el trabajo, en el
# HTML el dibujo, y ninguna de las dos mitades sabe de la otra.


def _modos_mcp(_cfg):
    from . import mcp

    return list(mcp.MODOS)


def _idiomas(_cfg):
    """Los idiomas como (codigo, rotulo).

    El par y no la lista suelta porque lo que se guarda es `es`/`en` y lo que
    se lee es "Espanol"/"English". El panel viejo tiene DOS variables para eso
    --una con el nombre y otra con el codigo-- y hay que acordarse de mover las
    dos; con el par, el desplegable ya guarda lo que corresponde.
    """
    from . import textos as t

    return [[codigo, rotulo] for codigo, rotulo in t.IDIOMAS.items()]


OPCIONES["_modos_mcp"] = _modos_mcp
OPCIONES["_idiomas"] = _idiomas


# --- Cuentas --------------------------------------------------------------


def _propio_steam_id(cfg):
    """El SteamID, autodetectado del disco si esta vacio.

    Es un `Propio` y no un `Campo` por el autodetectado: mostrar el valor no
    alcanza, hay que salir a buscarlo cuando no hay ninguno. `gui.py` lo hace
    en medio de armar la pestana, que es donde nadie lo encuentra.
    """
    valor = str(cfg.get("steam_id", "") or "")
    if not valor:
        from . import integrations

        valor = integrations.steam_id_local() or ""
    return {"componente": "autodetectado", "clave": "steam_id",
            "etiqueta": tr("Tu SteamID64 (autodetectado)"), "valor": valor}


def _probar_webhook(cfg, args):
    """Manda un mensaje de prueba al webhook de Discord.

    Una URL de webhook mal copiada no da ninguna senal: Eve dice que mando y el
    mensaje no llega a ningun lado. Esto es lo unico que lo separa.

    El webhook vive en el llavero, no en la config. Se usa lo que el usuario
    haya tipeado ahora si tipeo algo, y lo guardado si no --que es lo mismo que
    hace el panel viejo con su campo enmascarado--.
    """
    import json as _j
    import urllib.request

    tipeado = str((args or {}).get("valor", "")).strip()
    url = tipeado if tipeado and set(tipeado) != {"*"} else ""
    if not url:
        url = str(_leer_clave("discord_webhook"))
    if not url:
        return {"ok": False, "salida": tr("No hay ningun webhook guardado.")}
    try:
        cuerpo = {"content": "Mensaje de prueba de Eve. Si lo lees, el webhook anda."}
        nombre = str(cfg.get("discord_username", "") or "")
        if nombre:
            cuerpo["username"] = nombre
        avatar = str(cfg.get("discord_avatar", "") or "")
        if avatar:
            cuerpo["avatar_url"] = avatar
        pedido = urllib.request.Request(
            url, data=_j.dumps(cuerpo).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(pedido, timeout=15) as r:
            return {"salida": f"Mandado (HTTP {r.status}). Revisa el canal."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "salida": f"No pude mandarlo: {type(exc).__name__}: {str(exc)[:120]}"}


def _leer_clave(proveedor: str) -> str:
    try:
        return store.get_key(proveedor) or ""
    except Exception:  # noqa: BLE001 - el llavero puede no estar
        return ""


def _refresh_outlook(_cfg, _args):
    """Las cuentas que Outlook tiene en esta PC. No necesita ninguna clave."""
    from . import integrations

    cuentas = integrations.outlook_cuentas()
    return {"salida": ("Cuentas: " + ", ".join(cuentas) if cuentas
                       else "Sin cuentas, o Outlook no responde.")}


def _outlook_login(_cfg, _args):
    from . import integrations

    return {"salida": integrations.outlook_agregar_cuenta()}


def _gmail_login(_cfg, _args):
    """Abre la pagina de contrasenas de aplicacion y explica el caso feo."""
    import webbrowser

    webbrowser.open("https://myaccount.google.com/apppasswords")
    return {"salida": tr("Te abri la pagina de contrasenas de aplicacion.\n\n"
                         "Si dice que no esta disponible para tu cuenta, es porque no tienes\n"
                         "verificacion en dos pasos activada, o la administra tu organizacion.\n\n"
                         "En ese caso usa el boton de Outlook: agregas el Gmail ahi y listo.")}


def _gmail_probar(_cfg, _args):
    from . import integrations

    return {"salida": integrations.gmail_probar()}


# --- la sesion de Claude Code ---------------------------------------------


def _refresh_auth(_cfg, _args):
    """Lee `claude auth status`. Tarda ~1s porque levanta el CLI."""
    import json as _j
    import shutil
    import subprocess

    from . import plataforma

    if not shutil.which("claude"):
        return {"salida": "CLI 'claude' no encontrado en el PATH."}
    try:
        r = plataforma.correr(["claude", "auth", "status"], capture_output=True,
                              text=True, timeout=60)
        datos = _j.loads(r.stdout)
    except (subprocess.TimeoutExpired, OSError, _j.JSONDecodeError):
        return {"salida": "No pude leer el estado de la sesion."}
    if not datos.get("loggedIn"):
        return {"salida": "Sin sesion iniciada."}
    return {"salida": f"Conectado como {datos.get('email', '?')}\n"
                      f"Plan: {datos.get('subscriptionType', '?')}   |   "
                      f"Metodo: {datos.get('authMethod', '?')}"}


def _auth_login(_cfg, _args):
    """Abre una consola con el login, que es interactivo."""
    import shutil
    import subprocess

    from . import plataforma

    if not shutil.which("claude"):
        return {"ok": False, "salida": tr("No encontre 'claude' en el PATH.")}
    banderas = getattr(plataforma, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(["claude", "auth", "login"], creationflags=banderas)
    return {"salida": tr("Se abrio una consola con el login de Claude Code.\n"
                         "Cuando termines, toca 'Actualizar' para ver el estado.")}


def _auth_logout(_cfg, args):
    """Cierra la sesion en TODA la PC, no solo en Eve. Por eso pide confirmar.

    La confirmacion la pide el frontend y llega como `confirmado`: aca no hay
    cuadros del sistema. Sin la marca no se hace nada, para que una llamada
    suelta no pueda cerrar la sesion de alguien.
    """
    from . import plataforma

    if not (args or {}).get("confirmado"):
        return {"ok": False, "confirmar": tr(
            "Esto cierra tu sesion de Claude Code en toda la PC, no solo en Eve.\n\n"
            "El motor 'claude-code' va a dejar de funcionar hasta que vuelvas a entrar.\n\nSeguro?")}
    r = plataforma.correr(["claude", "auth", "logout"], capture_output=True,
                          text=True, timeout=60)
    return {"salida": (r.stdout or r.stderr or "Sesion cerrada.").strip()[:500]}


# --- Contactos ------------------------------------------------------------

# Las columnas de la agenda, con el nombre CRUDO que muestra el panel. No se
# capitalizan ni se traducen: `discord_dm` es el nombre del campo y ponerle
# "Mensaje directo de Discord" haria que la ayuda de arriba --que los nombra
# asi-- deje de corresponderse con el formulario.
CONTACTO_COLS = ("nombre", "alias", "email", "telefono",
                 "discord_user", "discord_dm", "discord_canal")


def _propio_contactos(_cfg):
    """La agenda entera. Son datos de personas reales: no salen de esta maquina."""
    return {"componente": "contactos", "columnas": list(CONTACTO_COLS),
            "lista": [{c: x.get(c, "") for c in CONTACTO_COLS}
                      for x in store.load_contacts()]}


def _contactos_listar(_cfg, _args):
    return {"contactos": _propio_contactos(_cfg)}


def _contacto_guardar(_cfg, args):
    """Agrega o actualiza. Mismo nombre = actualizar, no duplicar."""
    datos = {c: str((args or {}).get(c, "")).strip() for c in CONTACTO_COLS}
    if not datos["nombre"]:
        return {"ok": False, "salida": tr("El nombre no puede estar vacio.")}
    # Se relee del disco antes de tocar nada: si Eve agrego un contacto por voz
    # mientras el panel estaba abierto, escribir la lista que el panel tenia
    # cargada lo borraba sin decir nada.
    contactos = store.load_contacts()
    for i, c in enumerate(contactos):
        if store._plano(c.get("nombre", "")) == store._plano(datos["nombre"]):
            contactos[i] = datos
            break
    else:
        contactos.append(datos)
    store.save_contacts(contactos)
    return {"salida": f"{tr('Guardado')}: {datos['nombre']}",
            "contactos": _propio_contactos(None)}


def _contacto_borrar(_cfg, args):
    nombre = str((args or {}).get("nombre", "")).strip()
    if not nombre:
        return {"ok": False, "salida": tr("Elige un contacto de la lista primero.")}
    quedan = [c for c in store.load_contacts()
              if store._plano(c.get("nombre", "")) != store._plano(nombre)]
    store.save_contacts(quedan)
    return {"salida": f"{tr('Borrado')}: {nombre}",
            "contactos": _propio_contactos(None)}


def _contacto_exportar(_cfg, args):
    """Un `.evecontact` para mandarle a un amigo.

    Declara el archivo a guardar en vez de abrirlo: el cuadro del sistema lo
    abre el frontend, que es quien tiene ventana. Vuelve con `destino` puesto.
    """
    nombre = str((args or {}).get("nombre", "")).strip()
    if not nombre:
        return {"ok": False, "salida": tr("Elige un contacto de la lista primero.")}
    destino = str((args or {}).get("destino", ""))
    if not destino:
        seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in nombre).strip()
        return {"guardar_archivo": {
            "accion": "contacto_exportar", "args": {"nombre": nombre},
            "nombre": f"{seguro}.evecontact",
            "filtros": ["Contacto de Eve (*.evecontact)", "JSON (*.json)"]}}
    return {"salida": store.exportar_contactos([nombre], destino)}


def _contacto_importar(_cfg, args):
    """Uno o varios `.evecontact`. Pisar la agenda en silencio no se hace.

    Si el archivo trae nombres que ya tenes, NO se reemplazan solos: vuelve la
    lista de conflictos para que el frontend pregunte, y recien con
    `reemplazar` se pisan. Es la misma linea del panel viejo.
    """
    rutas = list((args or {}).get("rutas") or [])
    if not rutas:
        return {"ok": False, "salida": tr("No elegiste ninguno.")}
    import os as _os

    nuevos, fallos = {}, []
    for ruta in rutas:
        try:
            nuevos.update(store.leer_contactos_archivo(str(ruta)))
        except ValueError as exc:
            fallos.append(f"{_os.path.basename(str(ruta))}: {exc}")
    if not nuevos:
        return {"ok": False, "salida": "; ".join(fallos) or tr("No entro ninguno.")}
    reemplazar = set((args or {}).get("reemplazar") or [])
    agregados, cambiados, conflictos = store.importar_contactos(
        nuevos, reemplazar=reemplazar) if reemplazar else store.importar_contactos(nuevos)
    if conflictos and not reemplazar:
        return {"ok": True, "conflictos": conflictos, "pendientes": nuevos,
                "salida": f"{agregados} " + tr("agregado(s)"),
                "contactos": _propio_contactos(None)}
    partes = [f"{agregados} " + tr("agregado(s)"), f"{cambiados} " + tr("actualizado(s)")]
    if fallos:
        partes.append(tr("no entraron") + ": " + "; ".join(fallos))
    return {"salida": ", ".join(partes), "contactos": _propio_contactos(None)}


# --- Addons ---------------------------------------------------------------


def _propio_addons_lista(cfg):
    """Los addons cargados, con si estan prendidos y que claves piden.

    Cada addon DICE que claves necesita (`CLAVES`), asi que agregar uno no
    obliga a tocar esta pantalla. Vacio en `addons_activos` significa TODOS: es
    lo que hace que uno nuevo aparezca prendido en vez de quedar apagado por no
    estar en una lista escrita antes.
    """
    from . import addons

    cargados = addons.todos(recargar=True)
    prendidos = {x.strip() for x in str(cfg.get("addons_activos", "")).split(",") if x.strip()}
    lista = []
    for nombre, modulo in sorted(cargados.items()):
        puede, motivo = addons.estado(modulo, cfg)
        lista.append({
            "nombre": nombre,
            "activo": (not prendidos) or nombre in prendidos,
            "descripcion": getattr(modulo, "DESCRIPCION", ""),
            "disponible": bool(puede),
            "motivo": "" if puede else motivo,
            "claves": [{"proveedor": c, "etiqueta": e, "tiene": _tiene_clave(c)}
                       for c, e, _secreta in getattr(modulo, "CLAVES", [])],
        })
    return {"componente": "addons", "lista": lista,
            "vacio": tr("No hay ninguno cargado.")}


def _propio_addons_carpeta_ayuda(_cfg):
    """El texto lleva la ruta adentro, asi que no es un literal traducible."""
    from . import addons

    return {"componente": "ayuda", "texto":
            f"Pon archivos .py en:\n  {addons.CARPETA_USUARIO}\n\n"
            "Cada uno define NOMBRE, un texto para el modelo y una funcion\n"
            "ejecutar(accion, args, cfg). Ojo: corren dentro de Eve, con los mismos\n"
            "permisos que el programa. Pon solo cosas en las que confies."}


def _propio_addons_pendientes(_cfg):
    """Los .py que NO se estan cargando porque nadie los miro todavia."""
    from . import addons

    return {"componente": "addons_pendientes",
            "lista": [{"nombre": n, "ruta": r, "marca": m}
                      for n, r, m in addons.pendientes()]}


def _propio_addons_aprobados(_cfg):
    from . import addons

    return {"componente": "addons_aprobados", "lista": list(addons.aprobados_ahora())}


def _addons_activar(cfg, args):
    """Prende o apaga uno. Devuelve `addons_activos` para dejarlo pendiente.

    Como valor y no escrito: es una clave de config como cualquier otra, y el
    usuario sigue apretando Guardar. Si estan todos prendidos se manda vacio,
    que es lo que significa "todos".
    """
    from . import addons

    nombre = str((args or {}).get("nombre", ""))
    si = bool((args or {}).get("activo"))
    todos = sorted(addons.todos())
    prendidos = {x.strip() for x in str(cfg.get("addons_activos", "")).split(",") if x.strip()}
    if not prendidos:
        prendidos = set(todos)
    prendidos.add(nombre) if si else prendidos.discard(nombre)
    valor = "" if prendidos == set(todos) else ",".join(sorted(prendidos))
    return {"salida": "", "valores": {"addons_activos": valor}}


def _addon_ver(_cfg, args):
    """El archivo entero, para leerlo ANTES de aprobarlo."""
    ruta = str((args or {}).get("ruta", ""))
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            codigo = f.read()
    except OSError as exc:
        return {"ok": False, "salida": f"{tr('No pude leerlo')}: {exc}"}
    import os as _os

    return {"titulo": _os.path.basename(ruta), "cuerpo": codigo,
            "salida": f"{len(codigo)} " + tr("caracteres")}


def _addon_aprobar(_cfg, args):
    """Aprueba por HUELLA del contenido: editarlo despues lo saca solo.

    Como el logout de Claude Code, pide `confirmado`: dejar que un archivo
    corra con tus permisos no puede pasar por una llamada suelta.
    """
    from . import addons

    nombre = str((args or {}).get("nombre", ""))
    if not (args or {}).get("confirmado"):
        return {"ok": False, "confirmar":
                f"Vas a dejar que {nombre}.py corra con tus permisos.\n\nLo miraste?"}
    salida = addons.aprobar(nombre, str((args or {}).get("marca", "")))
    return {"salida": salida, "recargar": True}


def _addon_revocar(_cfg, args):
    """Saca la aprobacion. NO borra el archivo: lo devuelve a sin revisar."""
    from . import addons

    return {"salida": addons.revocar(str((args or {}).get("nombre", ""))),
            "recargar": True}


def _addons_carpeta(_cfg, _args):
    import os as _os

    from . import addons, plataforma

    _os.makedirs(addons.CARPETA_USUARIO, exist_ok=True)
    plataforma.abrir(addons.CARPETA_USUARIO)
    return {"salida": addons.CARPETA_USUARIO}


# --- MCP ------------------------------------------------------------------


def _propio_mcp_lista(cfg):
    """Un renglon por servidor: encendido, nombre, comando y de donde salio."""
    from . import mcp

    srvs = mcp.servidores()
    return {"componente": "mcp", "modo": mcp.modo(cfg),
            "vacio": tr("Ninguno todavia. 'Buscar los que ya tienes' lee la config de "
                        "Claude Code, Claude Desktop, Cursor, LM Studio y VS Code."),
            "lista": [{
                "nombre": nombre,
                "activo": bool(srv.get("activo")),
                "comando": " ".join([srv.get("comando", "")] + srv.get("args", [])),
                "de": srv.get("de", ""),
                "vistas": len(srv.get("vistas") or []),
            } for nombre, srv in sorted(srvs.items())]}


def _mcp_activar(cfg, args):
    """Encender uno es autorizar que corra en tu maquina. Se escribe al toque.

    Al archivo de MCP y no a la config, asi que no hay nada que dejar
    pendiente: `mcp.activar` es la unica forma de escribirlo.
    """
    from . import mcp

    mcp.activar(str((args or {}).get("nombre", "")), bool((args or {}).get("activo")))
    return {"salida": "", "mcp": _propio_mcp_lista(cfg)}


def _mcp_importar(cfg, args):
    """Trae los servidores que ya tenes configurados en otros programas.

    Se ofrecen, no se importan solos, y entran APAGADOS: importar es traer la
    configuracion, no autorizar que se ejecute. Sin `elegidos` devuelve lo que
    encontro para que el frontend pregunte cuales.
    """
    from . import mcp

    hallados = mcp.descubrir()
    if not hallados:
        return {"ok": False,
                "salida": tr("No encontre ninguno configurado en otros programas.")}
    elegidos = list((args or {}).get("elegidos") or [])
    if not elegidos:
        ya = set(mcp.servidores())
        return {"ok": True, "hallados": [
            {"nombre": n, "de": d.get("de", ""), "ya": n in ya,
             "comando": " ".join([d["comando"]] + d["args"])}
            for n, d in sorted(hallados.items())],
            "aviso": tr("Entran apagados. Encender uno es autorizar que corra en tu "
                        "maquina, y eso lo eliges tu despues."),
            "salida": f"{len(hallados)} " + tr("encontrados")}
    puestos = 0
    for nombre in elegidos:
        datos = hallados.get(nombre)
        if not datos:
            continue
        mcp.agregar(nombre, datos["comando"], datos["args"], datos.get("env"),
                    datos.get("de", ""))
        puestos += 1
    return {"salida": f"{puestos} " + tr("agregado(s)"), "mcp": _propio_mcp_lista(cfg)}


def _mcp_agregar(cfg, args):
    """Uno a mano, para el que no este en ningun otro programa."""
    from . import mcp

    try:
        mcp.agregar(str((args or {}).get("nombre", "")),
                    str((args or {}).get("comando", "")),
                    str((args or {}).get("args", "")).split())
    except ValueError as exc:
        return {"ok": False, "salida": str(exc)}
    return {"salida": tr("Agregado"), "mcp": _propio_mcp_lista(cfg)}


def _mcp_quitar(cfg, args):
    from . import mcp

    nombre = str((args or {}).get("nombre", ""))
    if not nombre:
        return {"ok": False, "salida": tr("Elige un servidor de la lista.")}
    mcp.quitar(nombre)
    return {"salida": f"{tr('Quitado')}: {nombre}", "mcp": _propio_mcp_lista(cfg)}


def _mcp_herramientas(cfg, args):
    """Le pregunta al servidor que tiene. Levanta un proceso ajeno, asi que tarda.

    En modo lectura no se conecta: el modo `prompt` existe justamente para que
    el modelo vea QUE herramientas hay sin que Eve levante nada.
    """
    from . import mcp

    nombre = str((args or {}).get("nombre", ""))
    srv = mcp.servidores().get(nombre)
    if srv is None:
        return {"ok": False, "salida": tr("Elige un servidor de la lista.")}
    if mcp.modo(cfg) != "cliente" and not (srv.get("vistas") or []):
        return {"ok": False, "salida": tr(
            "En modo lectura no me conecto. Pasa el modo a 'cliente' para "
            "que pregunte que herramientas tiene.")}
    try:
        with mcp.Cliente(nombre, srv) as cli:
            hs = cli.herramientas()
    except Exception as exc:  # noqa: BLE001 - un servidor ajeno falla como quiere
        return {"ok": False,
                "salida": f"{tr('no pude hablarle a')} {nombre}: {str(exc)[:160]}"}
    datos = mcp.leer()
    if nombre in datos["servidores"]:
        datos["servidores"][nombre]["vistas"] = hs
        mcp.escribir(datos)
    srv = mcp.servidores().get(nombre, {})
    return {"salida": f"{nombre}: {len(hs)} {tr('herramientas')}",
            "servidor": nombre,
            "aviso": tr("La casilla de la izquierda la enciende. 'Sin preguntar' la deja "
                        "correr sin confirmacion:\nusalo solo con las que sepas que hacen, "
                        "porque el nombre lo eligio quien escribio el servidor."),
            "herramientas": [{
                "nombre": h["nombre"], "descripcion": h["descripcion"][:70],
                "activa": mcp.herramienta_activa(srv, h["nombre"]),
                "confiada": h["nombre"] in srv.get("confiadas", []),
            } for h in hs]}


def _mcp_herramienta(_cfg, args):
    """Enciende una herramienta, o la deja correr sin preguntar."""
    from . import mcp

    servidor = str((args or {}).get("servidor", ""))
    nombre = str((args or {}).get("nombre", ""))
    if "activa" in (args or {}):
        mcp.activar_herramienta(servidor, nombre, bool(args["activa"]))
    if "confiada" in (args or {}):
        mcp.confiar(servidor, nombre, bool(args["confiada"]))
    return {"salida": ""}


# --- Actividad ------------------------------------------------------------


def _propio_historial(_cfg):
    """Lo que se dijo. Es la conversacion del usuario: no sale de esta maquina."""
    import time as _t

    turnos = store.recent_turns()
    return {"componente": "historial",
            "cuantos": f"{len(turnos)} mensajes guardados",
            # Del mas nuevo al mas viejo, que es como lo muestra el panel viejo.
            "lista": [{"hora": _t.strftime("%d/%m %H:%M", _t.localtime(ts)),
                       "quien": rol, "texto": texto}
                      for ts, rol, texto in reversed(turnos)]}


def _propio_acciones(_cfg):
    """Que ejecuto Eve y que freno el usuario. Las dos mitades, no una."""
    import time as _t

    return {"componente": "acciones",
            "columnas": ["hora", "tool", "detalle", "resultado"],
            "lista": [[_t.strftime("%d/%m %H:%M", _t.localtime(ts)), tool, detalle, res]
                      for ts, tool, detalle, res in store.recent_actions()]}


def _historial_limpiar(_cfg, args):
    """Borra la conversacion guardada. El registro de Acciones NO se toca."""
    if not (args or {}).get("confirmado"):
        return {"ok": False, "confirmar": tr(
            "Borra la conversacion guardada y deja la ventana de contexto en cero.\n\n"
            "El registro de acciones (pestaña Acciones) NO se toca.\n\n"
            "Si el listener esta corriendo, usa tambien la bandeja > 'Limpiar historial y\n"
            "contexto' para vaciar lo que ya tiene en memoria.\n\nBorrar?")}
    n = store.clear_history()
    return {"salida": f"{n} mensajes borrados.", "historial": _propio_historial(None)}


def _actividad_refrescar(_cfg, _args):
    return {"salida": "", "historial": _propio_historial(None),
            "acciones": _propio_acciones(None)}


# --- Perfiles -------------------------------------------------------------


def _propio_perfiles(cfg):
    """Todos los perfiles con su paleta, para dibujar la muestra.

    Los de fabrica y los tuyos en UNA lista, que es el arreglo de un bug con
    forma de diseno: la galeria pintaba los de ejemplo y el desplegable de al
    lado listaba los tuyos, asi que elegir una muestra dejaba un nombre que el
    desplegable no conocia y Cargar tiraba un ValueError sin atrapar.

    Se manda la paleta RESUELTA de cada uno --panel y cartel-- y no el perfil
    entero: la muestra la dibuja el HTML con esos colores. El panel viejo la
    dibuja con el mismo `overlay.Pintor` que el cartel, y eso se queda en
    Canvas junto con el cartel; lo que se conserva es lo que la muestra tiene
    que MOSTRAR, que es panel arriba y cartel abajo.
    """
    salida = []
    for nombre, (perfil, de_fabrica) in sorted(store.perfiles_disponibles().items()):
        completa = {**store.DEFAULTS, **perfil}
        salida.append({
            "nombre": nombre,
            "de_fabrica": de_fabrica,
            "etiqueta": nombre + (" (de fabrica)" if de_fabrica else ""),
            "ui": tema.resolver(completa, "ui"),
            "hud": tema.resolver(completa, "hud"),
            "titulo": str(completa.get("hud_titulo")
                          or completa.get("assistant_name") or "Eve"),
        })
    return {"componente": "perfiles", "lista": salida,
            "activo": str(cfg.get("perfil_activo", "")),
            "etiqueta": tr("Perfil activo")}


def _perfil_cargar(_cfg, args):
    """Aplica el perfil. Cambia el tema, asi que hay que releer todo."""
    nombre = str((args or {}).get("nombre", ""))
    if not nombre:
        return {"ok": False, "salida": tr("Elige un perfil de la lista.")}
    if not (args or {}).get("confirmado"):
        return {"ok": False, "confirmar":
                f"Se va a aplicar el perfil {nombre!r} y se pierden los cambios "
                "sin guardar.\n\nSeguir?"}
    try:
        store.aplicar_perfil(nombre)
    except ValueError as exc:
        return {"ok": False, "salida": str(exc)}
    return {"salida": f"Perfil {nombre!r} aplicado.", "recargar": True}


def _perfil_guardar(_cfg, args):
    """Guarda lo que hay EN PANTALLA como perfil, y lo deja activo."""
    nombre = str((args or {}).get("nombre", "")).strip()
    if not nombre:
        return {"ok": False, "salida": tr("El perfil necesita un nombre.")}
    if nombre in store.listar_perfiles() and not (args or {}).get("confirmado"):
        return {"ok": False, "confirmar": f"Ya hay un perfil {nombre!r}. Se reemplaza?"}
    # Lo pendiente se guarda primero: un perfil que sale de la config del disco
    # no incluye lo que acabas de cambiar, que es justo lo que querias guardar.
    pendientes = (args or {}).get("pendientes") or {}
    if pendientes:
        r = guardar(pendientes)
        if not r["ok"]:
            return r
    store.guardar_perfil(nombre, store.load_config())
    cfg = store.load_config()
    cfg["perfil_activo"] = nombre
    store.save_config(cfg)
    return {"salida": f"Guardado como {nombre!r}.", "recargar": True}


def _perfil_borrar(_cfg, args):
    nombre = str((args or {}).get("nombre", ""))
    if not nombre:
        return {"ok": False, "salida": tr("Elige un perfil de la lista.")}
    if nombre not in store.listar_perfiles():
        # Ahora que la lista incluye los de fabrica se puede elegir uno y darle
        # Borrar. Sin este aviso el boton se veria simplemente roto.
        return {"ok": False, "salida": tr(
            "Ese viene con el programa y no se borra. Guarda uno propio "
            "con el mismo nombre si quieres cambiarlo.")}
    if not (args or {}).get("confirmado"):
        return {"ok": False, "confirmar": f"Borrar el perfil {nombre!r}?"}
    store.borrar_perfil(nombre)
    return {"salida": f"{tr('Borrado')}: {nombre}", "recargar": True}


def _perfil_exportar(_cfg, args):
    """Un `.eveperfil`. No incluye claves ni datos personales."""
    nombre = str((args or {}).get("nombre", ""))
    if not nombre:
        return {"ok": False, "salida": tr("Elige un perfil de la lista primero.")}
    destino = str((args or {}).get("destino", ""))
    if not destino:
        return {"guardar_archivo": {
            "accion": "perfil_exportar", "args": {"nombre": nombre},
            "nombre": f"{nombre}.eveperfil",
            "filtros": ["Perfil de Eve (*.eveperfil)", "*"]}}
    try:
        mensaje = store.exportar_perfil(nombre, destino)
    except (ValueError, OSError) as exc:
        return {"ok": False, "salida": str(exc)}
    return {"salida": mensaje + "\n\n" + tr(
        "No incluye tus claves de API ni tus datos personales:\n"
        "las claves viven en el gestor de credenciales de Windows, no en el perfil.")}


def _perfil_importar(_cfg, args):
    """Uno o varios `.eveperfil`, con el nombre que trae cada archivo."""
    import os as _os

    rutas = list((args or {}).get("rutas") or [])
    if not rutas:
        return {"ok": False, "salida": tr("No elegiste ninguno.")}
    reemplazar = set((args or {}).get("reemplazar") or [])
    hechos, fallos, chocan = [], [], []
    for ruta in rutas:
        corto = _os.path.basename(str(ruta))
        try:
            nombre, config = store.leer_perfil_archivo(str(ruta))
        except ValueError as exc:
            fallos.append(f"{corto}: {exc}")
            continue
        nombre = nombre.strip()
        if not nombre:
            continue
        if nombre in store.listar_perfiles() and nombre not in reemplazar:
            chocan.append(nombre)
            continue
        store.guardar_perfil(nombre, {**store.DEFAULTS, **config})
        hechos.append(nombre)
    partes = []
    if hechos:
        partes.append(f"{len(hechos)} " + tr("importadas") + ": " + ", ".join(hechos))
    if fallos:
        partes.append(tr("no entraron") + ": " + "; ".join(fallos))
    return {"ok": bool(hechos) or not fallos, "salida": "  ".join(partes),
            "conflictos": chocan, "recargar": bool(hechos)}


def _perfiles_carpeta_ejemplos(_cfg, _args):
    """Donde viven los perfiles que vienen con el programa.

    El cuadro de archivos tiene que ABRIR ahi: si no, abre donde haya quedado
    la ultima vez y los de ejemplo son invisibles en la practica --nadie sale a
    buscarlos adentro de _internal--.
    """
    import os as _os

    from . import plataforma

    ruta = _os.path.join(plataforma.recursos(), "perfiles")
    return {"salida": ruta if _os.path.isdir(ruta) else ""}


PROPIOS.update({
    "_steam_id": _propio_steam_id,
    "_contactos": _propio_contactos,
    "_addons_lista": _propio_addons_lista,
    "_addons_carpeta_ayuda": _propio_addons_carpeta_ayuda,
    "_addons_pendientes": _propio_addons_pendientes,
    "_addons_aprobados": _propio_addons_aprobados,
    "_mcp_lista": _propio_mcp_lista,
    "_historial": _propio_historial,
    "_acciones": _propio_acciones,
    "_perfiles": _propio_perfiles,
})

ACCIONES.update({
    "probar_webhook": _probar_webhook,
    "refresh_outlook": _refresh_outlook,
    "outlook_login": _outlook_login,
    "gmail_login": _gmail_login,
    "gmail_probar": _gmail_probar,
    "refresh_auth": _refresh_auth,
    "auth_login": _auth_login,
    "auth_logout": _auth_logout,
    "contactos_listar": _contactos_listar,
    "contacto_guardar": _contacto_guardar,
    "contacto_borrar": _contacto_borrar,
    "contacto_exportar": _contacto_exportar,
    "contacto_importar": _contacto_importar,
    "addons_activar": _addons_activar,
    "addon_ver": _addon_ver,
    "addon_aprobar": _addon_aprobar,
    "addon_revocar": _addon_revocar,
    "_addons_carpeta": _addons_carpeta,
    "mcp_activar": _mcp_activar,
    "mcp_importar": _mcp_importar,
    "mcp_agregar": _mcp_agregar,
    "mcp_quitar": _mcp_quitar,
    "mcp_herramientas": _mcp_herramientas,
    "mcp_herramienta": _mcp_herramienta,
    "historial_limpiar": _historial_limpiar,
    "actividad_refrescar": _actividad_refrescar,
    "perfil_cargar": _perfil_cargar,
    "perfil_guardar": _perfil_guardar,
    "perfil_borrar": _perfil_borrar,
    "perfil_exportar": _perfil_exportar,
    "perfil_importar": _perfil_importar,
    "perfiles_carpeta_ejemplos": _perfiles_carpeta_ejemplos,
})

SALIDA_DE.update({
    "probar_webhook": "webhook_label",
    "refresh_outlook": "outlook_label",
    "outlook_login": "outlook_label",
    "gmail_probar": "gmail_label",
    "gmail_login": "gmail_label",
    "refresh_auth": "auth_label",
    "auth_login": "auth_label",
    "auth_logout": "auth_label",
})

# Lo que cada `Salida` dice apenas se abre, sin que nadie apriete nada. Las tres
# nuevas salen a preguntarle a otro programa --Outlook por COM, el CLI de
# Claude-- asi que tardan; el frontend las pide aparte, despues de dibujar.
SALIDAS_AL_ABRIR = ("refresh_outlook", "refresh_auth")


def textos_de_pantalla() -> list:
    """Los literales que este modulo muestra y NO estan dentro de `tr("...")`.

    Son los que se traducen al vuelo con `tr(variable)` --los rotulos del
    catalogo de proveedores, los nombres de las sub-pestanas-- porque
    envolverlos donde se declaran congelaria el idioma al importar. Es el mismo
    caso que `registro.textos()`, y se resuelve igual: declarandolos, para que
    el chequeo de traduccion los vea.
    """
    salida = [rotulo for _c, rotulo, _s, _t in PESTANAS]
    salida.extend(sub for _c, _r, sub, _t in PESTANAS)
    salida.extend(SUBPESTANAS.values())
    salida.extend(donde for _i, _r, _m, _c, donde in catalogo_proveedores())
    salida.extend((PERM_ASK, PERM_ALL))
    return salida
