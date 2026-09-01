"""Config (JSON), claves (keyring del SO) e historial (SQLite).

Nada de esto vive en la API: el programa es dueño del historial, la API solo
recibe una ventana corta. El panel lee de aca, no de Anthropic.
"""

import contextlib
import json
import os
import shutil
import sqlite3
import time

from . import plataforma

# Datos del usuario: escribibles, sobreviven a desinstalar y reinstalar.
BASE = plataforma.datos_usuario()
# Archivos que viajan con el programa y no se tocan.
RECURSOS = plataforma.recursos()

CONFIG_PATH = os.path.join(BASE, "config.json")
DB_PATH = os.path.join(BASE, "eve.db")


def _migrar_desde_codigo() -> None:
    """Mueve los datos de una instalacion vieja, cuando vivian junto al codigo.

    Se corre una sola vez: si el archivo ya existe en la carpeta nueva, no se
    pisa. Sin esto, actualizar a la version instalable perderia la agenda, la
    memoria y el historial.
    """
    viejo = plataforma.recursos()
    if os.path.abspath(viejo) == os.path.abspath(BASE):
        return
    for nombre in ("config.json", "contactos.json", "eve.db", "apps.json", "MEMORIA.md"):
        origen, destino = os.path.join(viejo, nombre), os.path.join(BASE, nombre)
        if os.path.exists(origen) and not os.path.exists(destino):
            try:
                shutil.copy2(origen, destino)
            except OSError:
                pass
    # Las voces son descargas de decenas de MB: no hacerlas bajar de nuevo.
    # Archivo por archivo, no copytree: la carpeta destino puede existir ya con
    # el catalogo adentro y copytree se saltearia todo.
    origen, destino = os.path.join(viejo, "voices"), os.path.join(BASE, "voices")
    if os.path.isdir(origen):
        os.makedirs(destino, exist_ok=True)
        for nombre in os.listdir(origen):
            src, dst = os.path.join(origen, nombre), os.path.join(destino, nombre)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass


_migrar_desde_codigo()

SERVICE = "LLMJarvis"
KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "openai": "OPENAI_API_KEY",
    # Conexiones con apps. Todas opcionales: sin ellas, Eve compone el mensaje y
    # lo abre en la app para que lo mandes vos.
    "gmail": "GMAIL_APP_PASSWORD",
    "discord_webhook": "DISCORD_WEBHOOK_URL",
    "steam": "STEAM_API_KEY",
    # Motores compatibles con OpenAI. Cada proveedor guarda la suya aparte para
    # poder tener varias cargadas y cambiar de motor sin volver a pegarlas.
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "xai": "XAI_API_KEY",
    "compat": "COMPAT_API_KEY",
    # De addons. get_key igual funciona con cualquier nombre via keyring; estan
    # aca para que tambien se puedan poner por variable de entorno.
    "spotify_client_id": "SPOTIFY_CLIENT_ID",
    "spotify_client_secret": "SPOTIFY_CLIENT_SECRET",
}

DEFAULTS = {
    "assistant_name": "Eve",
    "language": "es",
    # Juego de opciones activo. Los perfiles viven en perfiles.json.
    "perfil_activo": "",
    # "api"         -> Messages API directa. Necesita ANTHROPIC_API_KEY.
    # "claude-code" -> CLI de Claude Code headless. Usa tu suscripcion, sin key.
    # "ollama"      -> modelo local. Sin key, sin nube, pero peor con tools.
    "engine": "api",
    # "compat" -> cualquier servicio con el protocolo de OpenAI. Un solo motor
    # para Gemini, Groq, DeepSeek, OpenRouter, xAI, LM Studio y OpenAI: todos
    # hablan el mismo /chat/completions y solo cambian URL, clave y modelo.
    "compat_proveedor": "gemini",  # ver compat_engine.PROVEEDORES
    "compat_url": "",              # vacio = la del proveedor elegido
    "compat_modelo": "",           # vacio = el sugerido del proveedor
    "ollama_host": "http://localhost:11434",
    "ollama_model": "qwen3:8b",
    # Opus 5 por defecto. Cambialo a claude-sonnet-5 o claude-haiku-4-5 desde
    # el panel si preferis latencia sobre capacidad.
    "model": "claude-opus-5",
    "cc_model": "sonnet",
    "cc_permission_mode": "acceptEdits",
    "effort": "medium",
    "max_tokens": 8000,
    "hotkey": "f13",
    "workdirs": [os.path.join(os.path.expanduser("~"), "Documents")],
    "stt_provider": "faster-whisper",  # faster-whisper | openai
    # 'base' destroza los nombres propios en ingles ("rainbow six siege" ->
    # "Haberé en Vox XC"). 'small' con vocabulario los acierta.
    "stt_model": "small",
    "stt_device": "cpu",   # cpu | cuda. Con cuda hacen falta las libs de NVIDIA.
    # auto = int8 en CPU, int8_float16 en GPU. Estaba fijo en int8 aunque
    # pusieras la GPU, o sea usandola con el tipo pensado para procesador.
    "stt_computo": "auto",  # auto|int8|int8_float32|int8_float16|float16|float32
    # Recorta los silencios antes de transcribir. Medido: 1.19x -> 1.09x de
    # tiempo real sobre el mismo audio, sin cambiar el texto.
    "stt_vad": True,
    # Como escuchar. Los valores de cada modo salen de un barrido medido sobre el
    # banco de voz; estan en `voice.MODOS` con la tabla al lado.
    #   auto      normal, salvo que una regla de horario diga otra cosa
    #   normal    para un cuarto tranquilo
    #   ruido     musica o el juego de fondo, y vos hablando fuerte
    #   bajo      de madrugada, hablando suave
    #   manual    usa stt_vad_umbral y stt_vad_aire_ms tal cual
    # int8 o vacio para sin cuantizar. Solo aplica con stt_provider=parakeet.
    # Medido: int8 pesa 639 MB contra 2.4 GB, anda igual de rapido y saca mejor
    # WER total. Sin cuantizar solo gana en nombres propios.
    "parakeet_cuantizacion": "int8",
    # Que espanol habla Eve: "", rioplatense, neutro, mexicano o castellano.
    # Vacio = no se le dice nada y escribe como le salga.
    "dialecto": "neutro",
    "stt_sensibilidad": "auto",
    # Activacion por palabra clave. Apagada de fabrica y a proposito: prenderla
    # deja el microfono abierto todo el tiempo, y eso lo elige el usuario.
    "wake_activo": False,
    # Variantes separadas por `|`. La primera es la que conviene decir: medido,
    # "Computadora" despierta 4 de 4 con el modelo mas chico y "Eve" 2 de 4,
    # porque tres letras no le dan al reconocedor con que agarrarse. Las de Eve
    # quedan igual, para el que prefiera llamarla por el nombre.
    "wake_palabra": "computadora|eve|ebe|eva",
    # El modelo de la puerta, aparte del de transcribir. Chico porque solo tiene
    # que reconocer una palabra que ya conoce.
    "wake_modelo": "tiny",
    # Quien decide que terminaste de hablar. `fijo` es el cronometro de siempre
    # --0.7s de silencio--; `modelo` le pregunta a smart-turn-v3, que hay que
    # bajar aparte desde el panel.
    #
    # `fijo` de fabrica y no por precaucion generica: la medicion que falta es
    # si ese modelo reconoce el final de turno en espanol rioplatense. Los 23
    # idiomas son los que el modelo DECLARA, no los que se comprobaron aca, y
    # poner de fabrica algo que corta frases a mitad seria peor que el numero
    # fijo que ya se conoce.
    "cierre_modo": "fijo",
    # A partir de que probabilidad se da la frase por terminada. Mas alto =
    # espera mas y corta menos; mas bajo = corta antes y a veces de mas.
    "cierre_umbral": 0.6,
    # Reglas de horario, separadas por coma: `00:00-06:00=bajo, 20:00-23:59=ruido`.
    # Solo pisan al modo `auto`. Vacio = sin reglas.
    "stt_horario": "",
    # Perfiles contextuales. Misma sintaxis que las reglas de horario de arriba,
    # y la condicion puede ser un rango de horas o el programa en foco:
    #   22:00-06:00=noche, discord=gaming
    # Vacio = no cambia nada solo, que es lo que corresponde de fabrica.
    "perfil_reglas": "",
    # Los dos de abajo solo se usan con stt_sensibilidad = manual.
    "stt_vad_umbral": 0.5,
    "stt_vad_aire_ms": 100,
    "stt_vocabulary": "",
    # Como viaja el catalogo de programas en el system prompt.
    #   usados    solo los que aparecen en el log, ordenados por frecuencia.
    #             El resto se pide con `E programa NOMBRE`. Medido en esta
    #             maquina: 4363 -> 349 caracteres, o sea 1115 tokens menos en
    #             CADA llamada, casi un tercio del prompt.
    #   completo  las 80 lineas de siempre.
    # Sin historial se manda el completo igual: recortar por falta de datos
    # dejaria a una instalacion nueva sin saber abrir nada.
    "catalogo_modo": "usados",  # palabras extra que el STT suele errar
    # 1 = greedy. Medido: beam 5 tarda 4.4s y beam 1 tarda 3.5s con el mismo
    # texto en una orden corta. Subilo solo si dictas frases largas.
    "stt_beam": 1,
    # piper es el unico que funciona igual en los tres sistemas; sapi es solo
    # Windows, y dejarlo de default afuera hacia que Eve no pudiera hablar en una
    # instalacion limpia de Linux o macOS.
    "tts_provider": "sapi" if plataforma.WINDOWS else "piper",  # sapi|piper|elevenlabs
    "tts_voice": "",
    "piper_voice": "",  # clave del catalogo, ej. es_ES-davefx-medium
    # Hablante dentro de un modelo multi-voz (es_ES-sharvard-medium trae M y F).
    # En los de una sola voz da igual lo que diga.
    "piper_hablante": 0,
    # 1.0 = la velocidad del modelo. Mas alto habla mas lento. Es la forma barata
    # de que dos personajes con la misma voz no suenen igual.
    "piper_velocidad": 1.0,
    "elevenlabs_voice_id": "",
    # Como suena el asistente, no que hace. Va al final del system prompt y
    # subordinado al manual (ver bloque_tono). Vacio = sin personaje.
    "persona_tono": "",
    # Ganancia al reproducir. 1.0 = como salio del sintetizador. Se aplica sobre
    # el audio ya generado y NO en la sintesis: horneado en el wav invalidaria
    # el cache de frases del disco cada vez que movieras el control.
    "volumen": 1.0,
    "context_turns": 6,
    "context_minutes": 10,
    # False = "allow all": ni el freno propio ni el de Claude Code preguntan nada.
    # Todo lo ejecutado sigue quedando en el log de auditoria (tabla `actions`),
    # que pasa a ser el unico registro de lo que hizo Eve.
    "confirm_destructive": True,
    # Quien manda sobre un valor cuando los dos quieren cambiarlo.
    #   usuario   lo que tocaste a mano queda trabado y Eve no lo pisa
    #   eve       Eve cambia lo que quiera
    #   preguntar Eve pide permiso antes de cada cambio
    # Sin esto la app se siente poseida: pones opacidad 40, Eve la vuelve a 80
    # y no hay forma de saber quien gano.
    "autoridad": "usuario",
    # Las claves que editaste vos, separadas por coma. Las escribe el panel.
    "claves_del_usuario": "",
    "speak_replies": True,
    "gmail_address": "",
    "steam_id": "",
    # Simula el Enter final en WhatsApp. El destino lo garantiza la URI con el
    # numero, no una busqueda por nombre.
    "whatsapp_autosend": True,
    # Escribe en Discord manejando tu cliente. Es la via fragil: depende del foco
    # de la ventana. El webhook con `discord_username` es mas confiable.
    "discord_autosend": True,
    # Nombre y foto con los que aparecen los mensajes del webhook.
    "discord_username": "",
    "discord_avatar": "",
    # Addons prendidos, separados por coma. Vacio = todos los que se puedan usar.
    "addons_activos": "",
    # Addons del usuario que se revisaron, como `nombre:huella`. Un `.py` suelto
    # en la carpeta de datos es codigo que corre con tus permisos; si Eve puede
    # escribirlos, cargar sin mirar seria automatizar el unico agujero que le
    # queda al freno. Al cambiar el archivo, la huella cambia y hay que aprobar
    # de nuevo.
    "addons_aprobados": "",

    # --- aspecto ----------------------------------------------------------
    # Planas y no anidadas a proposito: Panel.save() decide el tipo de cada
    # valor con type(DEFAULTS[clave]), y un dict adentro romperia ese bucle.
    #
    # El idioma de la INTERFAZ, que no es `language`: aquel es en que idioma te
    # escucha y te contesta Eve, este en que idioma estan los menus. Se separan
    # porque no tienen por que coincidir --alguien puede querer el panel en
    # ingles y que Eve le hable en espanol, o al reves.
    "ui_idioma": "es",     # ver textos.IDIOMAS
    # Cuadros por segundo del cartel y de la ventana de actividad.
    #
    # Medido en el escritorio donde se desarrolla: componer 1100x700 con seis
    # capas y quinientas particulas cuesta 21.6 ms de mediana y 23.1 de p95, asi
    # que a 30 fps quedan 11 ms de margen. En una maquina lenta --el plan
    # estimaba 60-90 ms en linux-arm64-- eso no alcanza, y sin esta clave no
    # habria forma de bajarlo salvo recompilando. `plataforma.fps_sugerido()`
    # arranca mas bajo en ARM.
    "ui_fps": 0,           # 0 = el que sugiera la plataforma
    # Quien dibuja los modulos. `auto` usa la GPU si la hay; ver `eve/gpu.py`.
    # Elegirlo a mano NO lo pisa la deteccion, igual que `sensibilidad`.
    "motor_dibujo": "auto",
    # Cuanto se muestra del panel de una. `esencial` deja a la vista lo que usa
    # cualquiera y esconde las secciones de ajuste fino; `completo` muestra todo.
    # No hay una tercera opcion "experto" con cosas ocultas: si una opcion existe
    # tiene que poder verse, y esconderla en un modo que no sabes que existe es
    # lo mismo que no tenerla.
    "ui_modo_panel": "esencial",
    # Claro en el panel y oscuro en el cartel, y las dos son las paletas
    # neutras --las unicas disenadas contra `tema.PISOS`.
    #
    # Antes esto era `tactico` con `ui_pintar_panel` apagado, y esa combinacion
    # mandaba DOS identidades que se contradecian: una tarjeta cian sobre negro
    # flotando en el escritorio, y un panel gris estandar de Windows. No es que
    # el panel estuviera mal disenado; es que no estaba disenado, porque el
    # tema no lo alcanzaba.
    #
    # Las cuatro paletas con color siguen ahi y siguen exportandose en los
    # perfiles: son la personalidad de alguien. Lo que cambia es cual viene de
    # fabrica, que es una responsabilidad distinta.
    "ui_tema": "claro",  # ver tema.NOMBRES
    # Pintar el panel obliga a cambiar los widgets al tema `clam`: el nativo de
    # Windows los dibuja el sistema y no respeta colores. Ahora se pinta de
    # fabrica, que es lo que hace que la app tenga UNA cara.
    "ui_pintar_panel": True,
    # Como se dibujan las secciones del panel.
    #   tarjeta  cada una en una tarjeta con esquinas redondeadas, pintada
    #            sobre un Canvas porque ttk no las tiene
    #   plano    filas sueltas, como era antes
    # Los CONTROLES son ttk de verdad en los dos casos: lo que se dibuja es el
    # marco. Un control pintado sobre un Canvas es invisible para un lector de
    # pantalla, y eso no se negocia por una esquina redondeada.
    "ui_cromo": "tarjeta",
    # Como se navega entre las siete secciones del panel.
    #   lateral    una barra a la izquierda (por defecto)
    #   pestanas   las pestañas de arriba, como era antes
    # Siete pestañas arriba ya rozan el ancho de la ventana y no dejan lugar a
    # nada mas; Ajustes de Windows 11 y de macOS usan barra lateral por lo
    # mismo. La barra esta DIBUJADA pero se maneja con el teclado igual: entra
    # en el tabulador, las flechas mueven y Enter activa.
    "ui_nav": "lateral",
    "ui_color_fondo": "",
    "ui_color_panel": "",
    "ui_color_texto": "",
    "ui_color_texto_tenue": "",
    "ui_color_acento": "",
    "ui_color_acento2": "",
    "ui_color_borde": "",
    "ui_color_alerta": "",
    # Imagen de cabecera de las pestañas. No hay fondo para todo el panel: los
    # controles de ttk pintan su propio fondo opaco y taparian la imagen.
    "ui_banner": "",
    "ui_banner_opacidad": 100,
    "ui_fuente": "",       # vacio = la del sistema
    "ui_fuente_tam": 0,    # 0 = la que traiga la fuente
    # El cartel puede tener su propio tema; vacio = hereda el del panel.
    # Viene en oscuro a proposito y no vacio: flota sobre el escritorio, donde
    # una tarjeta clara compite con todo lo que tenga detras, y ademas es donde
    # vivia la identidad del proyecto.
    "hud_tema": "oscuro",
    "hud_color_fondo": "",
    "hud_color_panel": "",
    "hud_color_texto": "",
    "hud_color_texto_tenue": "",
    "hud_color_acento": "",
    "hud_color_acento2": "",
    "hud_color_borde": "",
    "hud_color_alerta": "",
    "hud_fuente": "",
    "sub_fuente": "",

    # --- overlay ----------------------------------------------------------
    "overlay_modo": "auto",  # auto (aparece y se va) | siempre | nunca
    # Lo prende el panel para poder arrastrarlo; el overlay lo apaga al soltar.
    "overlay_mover": False,
    "hud_x": 40,
    "hud_y": 40,
    "hud_escala": 100,      # porcentaje
    # Hasta donde puede llegar Eve armando cosas cuando se lo pedis hablando.
    #   nada     no toca nada; es la voz y nada mas
    #   datos    modulos, ajustes y perfiles: todo lo que ya es una clave de
    #            config y pasa por el mismo freno que el panel
    #   codigo   ademas puede DEJAR ESCRITO un addon .py, que igual no corre
    #            hasta que lo apruebes a mano en el panel
    # Por defecto `datos`, que es lo que ya se podia hacer. No hay un cuarto
    # nivel donde apruebe sus propios addons, y no deberia haberlo: la huella
    # del contenido es lo unico que separa un plugin de un agujero.
    "ayuda_alcance": "datos",
    # Cuanto vocabulario de interfaz viaja en el prompt. `ayuda_alcance`
    # dice QUE puede hacer Eve; esta dice CUANTO le contamos de antemano.
    #   consultar  dos renglones, y busca con `E ui buscar` (lo mas barato)
    #   minimo     ademas los trece nombres de tipo
    #   completo   el esquema entero, como era antes
    "ayuda_vocabulario": "consultar",
    # Hasta donde llega Eve con los archivos. `exacto` es lo que hacia
    # antes de que esto existiera: leer uno si le das la ruta entera.
    #   exacto     leer una ruta que le dictes
    #   explorar   ademas listar carpetas y buscar por nombre, solo lectura
    #   escribir   ademas crear y reemplazar, preguntando antes de pisar
    # En los tres, `workdirs` sigue siendo el limite: esto mueve QUE puede
    # hacer adentro de lo permitido, nunca cuanto alcanza.
    "archivos_alcance": "exacto",
    "skills_alcance": "consultar",
    "comandos_voz": "si",
    "comandos_aprobados": "",
    # apagado | prompt | cliente. Apagado por defecto: encender esto es
    # una decision del usuario, no algo que se descubra andando.
    "mcp_modo": "apagado",
    # Cuando se abre la ventana de actividad.
    #   nunca      solo si la abris a mano desde la bandeja
    #   con_eve    se abre junto con Eve y queda ahi
    # `nunca` de fabrica: es una ventana grande y quien no la pidio no tiene por
    # que encontrarsela. El plan la nombraba desde el principio y nunca existio,
    # asi que la unica forma de abrirla era un boton escondido en Modulos.
    "consola_modo": "nunca",
    # En que monitor vive el cartel. 0 = donde lo dejes, sin restriccion; 1 en
    # adelante lo fija a ese monitor y lo mantiene adentro. El panel llena la
    # lista preguntandole al sistema, asi que el numero es el de ahi.
    "overlay_pantalla": 0,
    # `trabajo` descuenta la barra de tareas, `completa` no. Solo cambia algo en
    # Windows: en macOS y Linux no hay forma de saberlo sin mas dependencias.
    "overlay_area": "trabajo",
    # Cuando el cartel deja de ser fantasma y toma los clics.
    #   nunca   nunca los toma; es lo de siempre
    #   hover   solo mientras el puntero esta sobre un modulo `interactivo`
    #   fijo    siempre los toma (y siempre tapa lo que este debajo)
    # `hover` es el default porque no hay que aprender nada: si no configuraste
    # ningun modulo interactivo, se comporta igual que `nunca`.
    "overlay_clics": "hover",
    "hud_opacidad": 92,     # porcentaje
    "hud_titulo": "",       # vacio = el nombre de la IA
    "hud_subtitulo": "Canal de Seguridad 7",
    "hud_icono": "hexagono",   # hexagono | circulo | cuadrado | ninguno | ruta .png
    "hud_contorno": "redondeado",  # ninguno|linea|esquinas|doble|hexagonal|biselado
    "hud_onda": "barras",        # barras|espejo|linea|puntos|ninguna
    # Imagen de fondo del cartel: PNG o GIF (se anima solo). Vacio = color liso.
    "hud_fondo": "",
    "hud_fondo_ajuste": "recortar",  # recortar | estirar | mosaico
    # Cuanto se ve la imagen. Se mezcla contra el color del panel al cargarla, no
    # con el alpha de la ventana: asi el fondo queda tenue y el texto entero.
    "hud_fondo_opacidad": 100,
    "hud_fondo_tinte": 0,   # cuanto se tiñe con el acento, para que se lea encima
    # "caja" = rectangulo relleno. "recortado" = solo la forma del contorno, y lo
    # de afuera deja ver el escritorio.
    "hud_forma": "caja",
    # Degradado de fondo cuando no hay imagen.
    "hud_grad": "ninguno",   # ninguno|vertical|horizontal|diagonal|radial
    "hud_grad_a": "",        # vacio = el color del panel
    "hud_grad_b": "",        # vacio = el acento
    "sub_grad": "ninguno",
    "sub_grad_a": "",
    "sub_grad_b": "",
    # El marco del icono es parametrico: lados, giro, redondeo y grosor. Las
    # "formas" del panel son nada mas que valores guardados de estos cuatro.
    "hud_marco_lados": 6,      # menos de 3 = circulo
    "hud_marco_rot": 0,        # grados
    "hud_marco_redondeo": 0,   # 0 = vertices en punta
    "hud_marco_grosor": 2,
    # Los GIF quietos, para quien no tolera el movimiento en pantalla.
    "ui_sin_animacion": False,
    "sub_muestra": "ambos",      # ambos | eve | usuario
    "sub_tam": 15,
    "sub_lineas": 2,
    "sub_segundos": 6,
    "sub_opacidad": 88,
    "sub_separacion": 10,
    "sub_fondo": "",
    "sub_fondo_ajuste": "recortar",
    "sub_fondo_opacidad": 100,
    "sub_fondo_tinte": 0,
}


def _escribir_json(ruta: str, datos) -> None:
    """Guarda de forma atomica: archivo temporal y despues os.replace.

    Abrir el definitivo en modo 'w' lo trunca antes de escribir, asi que
    quedarse sin bateria o matar el proceso a mitad del guardado dejaba un JSON
    cortado. Con os.replace, o esta el contenido viejo entero o el nuevo entero.
    """
    tmp = f"{ruta}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def _leer_json(ruta: str, por_defecto):
    """Lee un JSON del usuario. Si esta roto lo aparta en vez de ignorarlo.

    Devolver el default en silencio era peor que fallar: con contactos.json
    cortado el panel mostraba la agenda vacia, y el primer guardado la
    sobrescribia con esa nada. Renombrarlo a .roto deja los datos recuperables.
    """
    if not os.path.exists(ruta):
        return por_defecto
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Contenido roto de verdad: se aparta para poder recuperarlo a mano.
        try:
            os.replace(ruta, f"{ruta}.roto")
        except OSError:
            pass
        return por_defecto
    except OSError:
        # No se pudo abrir (el antivirus lo tiene tomado, permisos, disco): el
        # archivo puede estar perfecto, asi que no se toca.
        return por_defecto


# Todo lo que solo cambia como se ve. Cambiar esto no justifica rearmar el motor
# ni, por lo tanto, perder la conversacion que venias teniendo.
# `mod_` son los modulos: posicion, forma, animacion, que se ve y cuando. Un
# layout entero es cosmetico, asi que moverlo no corta la conversacion y
# viaja solo en los perfiles exportables.
PREFIJOS_COSMETICOS = ("ui_", "hud_", "sub_", "overlay_", "mod_")


def solo_cosmetico(antes: dict, despues: dict) -> bool:
    """True si entre las dos configs lo unico distinto es el aspecto."""
    claves = set(antes) | set(despues)
    for clave in claves:
        if clave.startswith(PREFIJOS_COSMETICOS):
            continue
        if antes.get(clave) != despues.get(clave):
            return False
    return True


TOPE_TONO = 400


# Las variantes de espanol que se pueden elegir. Cada una es UNA linea porque
# viaja en cada llamada, y el proyecto se paso un dia entero recortando el prompt
# como para gastarlo en un ensayo sobre dialectologia.
#
# `voz` es la voz de Piper que le corresponde, y no es una eleccion de gusto.
# Las siete voces en espanol de Piper, tres corridas cada una, sintetizando diez
# frases y volviendo a transcribirlas con el mejor reconocedor que hay:
#
#   es_ES-sharvard-medium   4.8  6.0  8.4  ->  6.4%   RTF 0.09
#   es_MX-claude-high       7.2  6.0  7.2  ->  6.8%   RTF 0.08
#   es_ES-davefx-medium     8.4  7.2  9.6  ->  8.4%   RTF 0.09
#   es_ES-carlfm-x_low     10.8  9.6  9.6  -> 10.0%   RTF 0.05
#   es_MX-ald-medium        9.6 12.0  9.6  -> 10.4%   RTF 0.09
#   es_MX-ald-x_low        14.5  8.4 10.8  -> 11.2%   RTF 0.08
#   es_AR-daniela-high     24.1 21.7 15.7  -> 20.5%   RTF 0.43
#
# Hacen falta las tres corridas: Piper no es determinista y una misma voz se
# mueve entre 1.2 y 8.4 puntos, mediana 2.4. Con una sola medicion, casi todo
# este orden seria ruido.
#
# Lo que sobrevive a esa banda: `es_AR-daniela-high` es la peor de las siete por
# mucho y la mas lenta por cinco veces. Por eso hasta el dialecto rioplatense
# sugiere una voz mexicana: la voz es el canal, no el acento del que habla.
# Y `es_MX-claude-high` le gana a `es_MX-ald-medium` de verdad --su PEOR corrida
# es mejor que la mejor de la otra-- asi que el dialecto mexicano tambien la usa.
DIALECTOS = {
    "": ("", ""),
    "rioplatense": (
        "Hablas rioplatense: vos y nunca tu. Abri, pone, cerra, tenes, queres, "
        "mira. Dale, listo, joya. Nada de vosotros ni de vale.",
        "es_MX-claude-high"),
    "neutro": (
        "Hablas espanol latinoamericano neutro: tu, sin regionalismos de ningun "
        "pais. Abre, pon, cierra, tienes, quieres.",
        "es_MX-claude-high"),
    "mexicano": (
        "Hablas espanol de Mexico: tu, con giros de ahi. Ahorita, ya quedo, "
        "orale, sale.",
        "es_MX-claude-high"),
    # No hay voz colombiana en el catalogo de Piper --ni es_CO ni nada cercano--
    # asi que comparte la mexicana, que es la mejor medida de las latinas. El
    # acento del sintetizador y el vocabulario que elige Eve son dos cosas
    # distintas: esta clave cambia la segunda.
    "colombiano": (
        "Hablas espanol de Colombia: tu y usted, con giros de ahi. Listo, "
        "de una, que pena, hagale, chevere. Nada de vos ni de vosotros.",
        "es_MX-claude-high"),
    "castellano": (
        "Hablas espanol de Espana: tu, con giros de ahi. Vale, ordenador, movil, "
        "vosotros cuando hablas de varios.",
        "es_ES-sharvard-medium"),
}


SALTO = chr(10)


def bloque_interfaz(cfg: dict) -> str:
    """El vocabulario de interfaz, en la cantidad que el usuario haya elegido.

    Eve puede escribir 121 opciones de config y trece tipos de modulo, y hasta
    ahora el prompt resolvia eso de la unica forma cara: mandando el diccionario
    entero de modulos --1 352 caracteres, 11% del prompt-- en CADA llamada, y
    de los 121 ajustes, ninguno. O sea que pagaba siempre por lo que casi nunca
    se usa, y para lo que si se usa Eve tenia que adivinar el nombre de la
    clave, fallar, y reintentar.

    `ayuda_vocabulario` deja elegir cuanto viaja, porque el equilibrio depende
    de para que uses a Eve y no de lo que yo suponga:

        consultar  dos renglones. Eve busca con `E ui buscar` cuando le hace
                   falta. Lo mas barato por llamada; una ida y vuelta extra las
                   veces que si toca la interfaz.
        minimo     ademas los trece nombres de tipo, sin sus props.
        completo   el esquema entero, como estaba.

    Con `ayuda_alcance = nada` no viaja nada, igual que antes: ese ajuste dice
    QUE puede hacer Eve y este CUANTO le contamos, y son preguntas distintas.
    """
    if str(cfg.get("ayuda_alcance", "datos")) == "nada":
        return ""
    from . import modulos

    cuanto = str(cfg.get("ayuda_vocabulario", "consultar"))
    cabecera = (
        "## Armar la interfaz\n\n"
        "Si te piden algo visual --\"ponete unas particulas\", \"agranda la "
        "onda\", \"mostrame el grafo\"-- se hace con `E modulo` y `E ajustar`, "
        "no describiendolo. Un modulo se ajusta con `E ajustar mod_<id>_<prop>`. "
        "Una personalidad entera es un perfil.\n\n")

    if cuanto == "completo":
        return cabecera + modulos.esquema_corto() + "\n"

    # En los modos baratos la cabecera tambien se acorta. Con el diccionario
    # puesto hace falta explicar cuando usarlo; con un buscador, el propio
    # comando lo explica al llamarlo, y repetirlo aca es pagar dos veces.
    cabecera = ("## Armar la interfaz" + SALTO * 2
                + "Lo visual se hace con `E modulo` y `E ajustar`, no "
                  "describiendolo: `E ajustar mod_<id>_<prop>`." + SALTO * 2)

    # El resto NO lleva el diccionario: lleva como pedirlo. `E ui buscar` acepta
    # palabras humanas --"transparencia", "que no me escuche de noche"-- y
    # devuelve la clave, el valor de ahora y las opciones.
    buscador = (
        "NO adivines nombres de opciones: son 121 y no estan aca. "
        "`E ui buscar <lo que quieras cambiar>` te da la clave exacta, cuanto "
        "vale ahora y que valores acepta. `E ui ver CLAVE` para una sola.\n")
    if cuanto == "minimo":
        return (cabecera + buscador
                + "Tipos de modulo: " + ", ".join(modulos.TIPOS) + ".\n"
                + "Sus props salen de `E ui ver mod_<id>_<prop>`.\n")
    return cabecera + buscador


def bloque_dialecto(cfg: dict) -> str:
    """Una linea diciendo que espanol hablar, o '' si al usuario le da igual.

    Va aparte del tono a proposito: el tono es COMO sonas --de eso ya se ocupa
    `persona_tono`, que es texto libre-- y esto es QUE espanol, que es una
    eleccion cerrada y por eso se puede acompanar de una voz medida.
    """
    texto = DIALECTOS.get(str(cfg.get("dialecto", "") or ""), ("", ""))[0]
    return f"## Como hablas\n\n{texto}\n\n" if texto else ""


def voz_del_dialecto(dialecto: str) -> str:
    """La voz de Piper que le corresponde, o '' si no hay preferencia."""
    return DIALECTOS.get(str(dialecto or ""), ("", ""))[1]


def bloque_tono(cfg: dict) -> str:
    """Seccion de personalidad para el system prompt. '' si no hay ninguna.

    Va ULTIMO en el prompt y con el encuadre pegado adelante. Las dos cosas
    importan. Ultimo porque el motor de Claude Code recibe todo esto por
    --append-system-prompt y ahi el orden interno es lo unico que controlo. Y con
    el encuadre porque sin el, un personaje verboso se come la disciplina del
    manual: el tono elige las palabras del acuse de recibo, no autoriza a narrar
    en vez de actuar ni a hablar de mas. Si el personaje no sobrevive a esa
    restriccion, ese personaje no sirve como asistente.
    """
    tono = str(cfg.get("persona_tono", "") or "").strip()
    if not tono:
        return ""
    return (
        "## Tono\n\n"
        "Lo que sigue es COMO suenas, no QUE hacer. No cambia ninguna regla del "
        "manual, no agranda cuantas frases dices, y no te autoriza a narrar en "
        "vez de actuar. Es la eleccion de palabras dentro del presupuesto que ya "
        "tenias. Si el tono choca con el manual, gana el manual.\n\n"
        f"{tono[:TOPE_TONO]}\n"
    )


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    guardado = _leer_json(CONFIG_PATH, {})
    if isinstance(guardado, dict):
        cfg.update(guardado)
    return cfg


def save_config(cfg: dict) -> None:
    _escribir_json(CONFIG_PATH, cfg)


PERFILES_PATH = os.path.join(BASE, "perfiles.json")

# Datos del duenio. No entran a un perfil ni viajan al exportar.
PERSONALES = ("gmail_address", "steam_id", "discord_username", "discord_avatar",
              "workdirs")

# Lo que un perfil SI puede tocar, mas alla de lo cosmetico: como se llama el
# asistente, como suena y con que tono habla. El nombre es del asistente, no
# tuyo: un perfil de personaje existe justamente para cambiarlo.
EXTRA_PERFILABLE = ("assistant_name", "persona_tono", "tts_provider", "tts_voice",
                    "piper_voice", "piper_hablante", "piper_velocidad",
                    "speak_replies")

# De tu pantalla y del momento, no de tu modo de trabajo. `hud_titulo` no esta
# aca: empieza con hud_ y es parte del personaje.
NO_PERFILABLE = ("perfil_activo", "hud_x", "hud_y", "overlay_mover",
                 "ui_idioma", "ui_modo_panel")


def perfilable(clave: str) -> bool:
    """Si esa clave puede vivir dentro de un perfil.

    Lista blanca, no negra. Antes se enumeraba lo que habia que EXCLUIR, y una
    lista de exclusiones se pudre: cada opcion nueva del programa nacia viajando
    dentro de los perfiles sin que nadie lo decidiera. Asi fue como el mail y el
    usuario de Discord terminaron adentro, y cargar un perfil viejo te devolvia
    los datos de contacto de cuando lo guardaste. Ahora una clave nueva no entra
    salvo que sea cosmetica o este listada a mano aca.

    El motor y el modelo quedan afuera a proposito: elegir un personaje no tiene
    por que bajarte de Opus a un modelo local sin avisarte.
    """
    if clave in NO_PERFILABLE:
        return False
    return clave.startswith(PREFIJOS_COSMETICOS) or clave in EXTRA_PERFILABLE


def rango_horario(txt: str, ahora) -> bool:
    """`22:30-06:00` incluye la medianoche; `08:00-12:00` no.

    Sin el caso que cruza la medianoche, el horario que el usuario pidio --de
    las 12 de la noche a las 6-- no entraria nunca. Lo usan la sensibilidad del
    reconocedor y los perfiles contextuales: mismo parser, misma sintaxis.
    """
    desde, hasta = (x.strip() for x in txt.split("-", 1))
    h = ahora.hour * 60 + ahora.minute
    m = lambda t: int(t[:2]) * 60 + int(t[3:5])  # noqa: E731
    a, b = m(desde), m(hasta)
    return a <= h < b if a <= b else (h >= a or h < b)


def perfil_por_contexto(cfg: dict, ahora=None, app: str | None = None) -> str:
    """El perfil que pide el contexto, o "" si ninguna regla entra.

    Formato, igual al de las reglas de horario del reconocedor para no inventar
    una segunda sintaxis:

        22:00-06:00=noche, discord=gaming, code=trabajo

    La condicion es un RANGO DE HORAS si tiene forma de rango, y si no el
    nombre del programa en foco. Gana la primera que entra, asi que el orden
    que escribe el usuario es el orden de prioridad -- y eso hay que decirlo en
    la ayuda, porque es lo unico que no se adivina.

    El nombre del programa se compara por PEDAZO y no exacto: el usuario
    escribe `discord` y el proceso puede llamarse `discord`, `Discord.exe` o
    `discordptb`. Exigir el nombre exacto seria pedirle que abra el
    administrador de tareas para escribir una regla.

    Devuelve "" tambien cuando no se puede saber que hay en foco. Ahi NO se
    aplica ninguna regla de programa, que es distinto de aplicar la del
    escritorio: una capacidad que falta se dice, no se inventa.
    """
    reglas = str(cfg.get("perfil_reglas", "")).strip()
    if not reglas:
        return ""
    import datetime

    ahora = ahora or datetime.datetime.now()
    if app is None:
        from . import plataforma

        app = plataforma.app_en_foco()
    app = (app or "").lower()
    perfiles = listar_perfiles()

    for regla in reglas.split(","):
        if "=" not in regla:
            continue
        cond, nombre = (x.strip() for x in regla.split("=", 1))
        if nombre not in perfiles:
            continue   # un perfil borrado no puede romper el arranque
        try:
            if ":" in cond and "-" in cond:
                if rango_horario(cond, ahora):
                    return nombre
            elif app and cond.lower() in app:
                return nombre
        except (ValueError, IndexError):
            continue   # una regla mal escrita no cambia nada, y no explota
    return ""


def listar_perfiles() -> dict:
    """{nombre: config}. Un perfil es una config entera, no un parche.

    Entera para que se pueda mirar y editar a mano, y para que agregar una clave
    nueva al programa no deje los perfiles viejos a medio aplicar: lo que no
    tengan lo completa DEFAULTS al cargarlos.
    """
    datos = _leer_json(PERFILES_PATH, {})
    return datos if isinstance(datos, dict) else {}


def perfiles_de_ejemplo() -> dict:
    """{nombre: config} de los `.eveperfil` que viajan con el programa.

    Son ocho y hasta ahora solo se llegaba a ellos por Importar y un dialogo de
    archivos: habia que saber que existian, saber donde estaban, y abrirlos de
    a uno para ver cual era cual. Un tema que no se puede ver antes de
    aplicarlo no se elige, se sortea.

    No se mezclan con `listar_perfiles`, que son los TUYOS: estos no se pueden
    borrar ni pisar, y que se distingan es lo que evita que guardar uno propio
    con el mismo nombre haga desaparecer al de fabrica.
    """
    import glob

    from . import plataforma

    carpeta = os.path.join(plataforma.recursos(), "perfiles")
    salida = {}
    for ruta in sorted(glob.glob(os.path.join(carpeta, "*.eveperfil"))):
        try:
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            continue   # un archivo roto no puede tumbar el panel
        cfg = datos.get("config")
        nombre = str(datos.get("nombre") or "").strip()
        if isinstance(cfg, dict) and nombre:
            # Se filtra por `perfilable` igual que al guardar: un archivo
            # editado a mano no puede colar el motor ni los permisos.
            salida[nombre] = {k: v for k, v in cfg.items() if perfilable(k)}
    return salida


MODELOS_PATH = os.path.join(BASE, "modelos.json")


def modelos_vistos(proveedor: str) -> list:
    """Los modelos que ESE servicio contesto la ultima vez que se le pregunto.

    Aprendidos y no escritos a mano. Una lista de modelos por proveedor dentro
    del codigo se pudre sola --Google saca modelos de circulacion, OpenRouter
    publica cientos y cambian todas las semanas-- y quedaria mintiendo hasta la
    proxima release. Esto se llena con lo que el propio servicio contesta en
    `/v1/models`, que es la unica fuente que no envejece.

    Vacio hasta que se aprete Buscar modelos una vez. Ahi el desplegable
    muestra solo el modelo sugerido del preset, que es lo que ya habia.
    """
    datos = _leer_json(MODELOS_PATH, {})
    lista = datos.get(str(proveedor)) if isinstance(datos, dict) else None
    return [str(x) for x in lista] if isinstance(lista, list) else []


def recordar_modelos(proveedor: str, lista: list) -> None:
    """Guarda lo que el servicio contesto, para no tener que volver a preguntar."""
    proveedor = str(proveedor or "").strip()
    if not proveedor or not lista:
        return
    datos = _leer_json(MODELOS_PATH, {})
    if not isinstance(datos, dict):
        datos = {}
    datos[proveedor] = [str(x) for x in lista]
    _escribir_json(MODELOS_PATH, datos)


def perfiles_disponibles() -> dict:
    """{nombre: (config, de_fabrica)} de TODOS: los tuyos y los de ejemplo.

    Existe porque tenerlos en dos listas separadas era un bug con forma de
    diseño. La galeria del panel pintaba `perfiles_de_ejemplo()` y el
    desplegable de al lado listaba `listar_perfiles()`, que son los tuyos:
    elegir una muestra dejaba en el desplegable un nombre que el desplegable no
    conocia, y el boton Cargar tiraba `ValueError: No existe el perfil` sin
    atrapar. Desde afuera se veia exactamente como lo reporto el usuario: "no
    me deja usar los de los botones, solo los importados manualmente" --los
    importados si estaban en la lista de los tuyos.

    Si un nombre esta en las dos, gana el TUYO: guardar uno propio llamado
    igual que uno de fabrica es pisarlo para vos, no borrarlo del programa.
    """
    salida = {n: (cfg, True) for n, cfg in perfiles_de_ejemplo().items()}
    salida.update({n: (cfg, False) for n, cfg in listar_perfiles().items()})
    return salida


def guardar_perfil(nombre: str, cfg: dict) -> None:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El perfil necesita un nombre.")
    perfiles = listar_perfiles()
    perfiles[nombre] = {k: v for k, v in cfg.items() if perfilable(k)}
    _escribir_json(PERFILES_PATH, perfiles)


def borrar_perfil(nombre: str) -> None:
    perfiles = listar_perfiles()
    if perfiles.pop(nombre, None) is not None:
        _escribir_json(PERFILES_PATH, perfiles)


def aplicar_perfil(nombre: str) -> dict:
    """Deja la config del perfil como la activa. Devuelve la config resultante.

    Se parte de la config ACTUAL, no de DEFAULTS: un perfil guardado con una
    version vieja no conoce las claves que se agregaron despues, y arrancando de
    DEFAULTS todas esas volvian a su valor de fabrica. Cargar un perfil para
    cambiar el tema te resetaba la voz, el modelo y media docena de opciones que
    el perfil ni menciona. El filtro se repite al aplicar, no solo al guardar,
    porque los perfiles de antes de este arreglo si traen esas claves adentro.
    """
    perfil = listar_perfiles().get(nombre)
    if perfil is None:
        # Los de fabrica tambien se aplican. Antes solo se miraba entre los
        # tuyos, asi que aplicar una muestra exigia guardarla primero como
        # propia y cualquier otro camino --el boton Cargar, la bandeja, un
        # perfil por contexto que nombre uno de ejemplo-- reventaba. La guarda
        # va aca, en la funcion por la que pasan todos, y no en cada llamador.
        perfil = perfiles_de_ejemplo().get(nombre)
    if perfil is None:
        raise ValueError(f"No existe el perfil {nombre!r}.")
    nueva = {**load_config(),
             **{k: v for k, v in perfil.items() if perfilable(k)},
             "perfil_activo": nombre}
    save_config(nueva)
    return nueva


FORMATO_PERFIL = "eveperfil"


def exportar_perfil(nombre: str, destino: str) -> str:
    """Deja el perfil en un archivo para pasarselo a alguien.

    Las claves de API NO viajan: viven en el gestor de credenciales del sistema,
    no en la config, asi que mandar un perfil no puede filtrar una key sin
    querer. Los datos personales que si estan en la config (mail, telefono,
    SteamID) se sacan explicitamente.
    """
    perfil = listar_perfiles().get(nombre)
    if perfil is None:
        raise ValueError(f"No existe el perfil {nombre!r}.")
    limpio = {k: v for k, v in perfil.items() if k not in PERSONALES}
    _escribir_json(destino, {
        "formato": FORMATO_PERFIL, "version": 1, "nombre": nombre, "config": limpio,
    })
    return f"Perfil {nombre!r} exportado a {destino}"


def _clave_de_modulo(k: str) -> bool:
    """Si `k` es una clave `mod_<id>_<prop>` con una prop que conocemos.

    No alcanza con mirar el prefijo: la idea de la guarda es que nada
    desconocido entre a la config, y eso vale igual para los modulos.
    """
    from . import modulos

    if not k.startswith(modulos.PREFIJO):
        return False
    _, prop = modulos._partir(k)
    if not prop:
        return False
    if prop in modulos.COMUNES:
        return True
    return any(prop in propias for propias in modulos.TIPOS.values())


def leer_perfil_archivo(ruta: str) -> tuple[str, dict]:
    """(nombre, config) de un .eveperfil validado. ValueError si no sirve."""
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No pude leer el archivo: {exc}") from exc
    if not isinstance(datos, dict) or datos.get("formato") != FORMATO_PERFIL:
        raise ValueError("Eso no es un perfil de Eve.")
    config = datos.get("config")
    if not isinstance(config, dict) or not config:
        raise ValueError("El archivo no tiene ninguna configuracion.")
    # Solo claves que el programa conoce: un perfil de una version futura no
    # mete basura en la config ni pisa nada raro. Las de modulo se inventan en
    # runtime y por eso no estan en DEFAULTS, pero se reconocen igual por su
    # forma: sin esto un perfil exportado perdia el layout entero al importarlo,
    # que es justo lo que un perfil tendria que llevar.
    limpio = {k: v for k, v in config.items()
              if (k in DEFAULTS or _clave_de_modulo(k)) and k not in PERSONALES}
    if not limpio:
        raise ValueError("El perfil no trae ninguna opcion que este programa entienda.")
    return str(datos.get("nombre") or os.path.basename(ruta).rsplit(".", 1)[0]), limpio


CONTACTS_PATH = os.path.join(BASE, "contactos.json")
# El manual viaja con el programa; la memoria es del usuario.
BRIEF_PATH = os.path.join(RECURSOS, "EVE.md")


def load_contacts() -> list[dict]:
    """Agenda propia: nombre, alias, mail, telefono y canal de Discord.

    Aparte de config.json porque crece, se edita en su propia tabla, y no tiene
    que perderse si alguien toca la config a mano.
    """
    datos = _leer_json(CONTACTS_PATH, [])
    if not isinstance(datos, list):
        return []
    for c in datos:
        # Antes habia un solo campo `discord`; ahora estan separados. Se migra al
        # vuelo para no perder lo ya cargado.
        if c.get("discord") and not c.get("discord_dm"):
            c["discord_dm"] = c.pop("discord")
    return datos


def save_contacts(contactos: list[dict]) -> None:
    _escribir_json(CONTACTS_PATH, contactos)


def _plano(texto: str) -> str:
    """Minusculas sin tildes: la voz transcribe 'Nicolas' tanto como 'Nicolás'."""
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower()) if not unicodedata.combining(c)
    ).strip()


def buscar_contacto(texto: str) -> list[dict]:
    """Coincidencias por nombre o alias. Devuelve varias si son ambiguas."""
    objetivo = _plano(texto)
    if not objetivo:
        return []
    exactos, parciales = [], []
    for c in load_contacts():
        campos = [c.get("nombre", "")] + str(c.get("alias", "")).split(",")
        campos = [_plano(x) for x in campos if x and x.strip()]
        if objetivo in campos:
            exactos.append(c)
        elif any(objetivo in campo or campo in objetivo for campo in campos):
            parciales.append(c)
    return exactos or parciales


FORMATO_CONTACTO = "evecontact"
CAMPOS_CONTACTO = (
    "nombre", "alias", "email", "telefono",
    "discord_user", "discord_dm", "discord_canal",
)


def exportar_contactos(nombres: list[str], destino: str) -> str:
    """Guarda contactos en un .evecontact para mandarselos a alguien.

    Siempre una lista, aunque sea uno solo: el mismo archivo sirve para compartir
    un contacto o la agenda entera, y quien lo recibe usa el mismo boton.
    """
    elegidos = []
    for nombre in nombres:
        hits = buscar_contacto(nombre)
        if not hits:
            return f"No encontre a {nombre!r} en la agenda."
        elegidos.append({k: hits[0].get(k, "") for k in CAMPOS_CONTACTO if hits[0].get(k)})
    if not elegidos:
        return "No hay nada para exportar."

    with open(destino, "w", encoding="utf-8") as f:
        json.dump(
            {"formato": FORMATO_CONTACTO, "version": 1, "contactos": elegidos},
            f, indent=2, ensure_ascii=False,
        )
    cuantos = len(elegidos)
    return f"{cuantos} contacto{'s' if cuantos > 1 else ''} exportado{'s' if cuantos > 1 else ''} a {destino}"


def leer_contactos_archivo(ruta: str) -> list[dict]:
    """Contactos de un .evecontact, validados. Lanza ValueError si no sirve."""
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No pude leer el archivo: {exc}") from exc

    if not isinstance(datos, dict) or datos.get("formato") != FORMATO_CONTACTO:
        raise ValueError("Eso no es un archivo de contactos de Eve.")

    salida = []
    for c in datos.get("contactos", []):
        if not isinstance(c, dict) or not c.get("nombre"):
            continue
        # Solo campos conocidos: un archivo de una version futura no rompe nada
        # ni mete claves raras en la agenda.
        salida.append({k: str(c[k]) for k in CAMPOS_CONTACTO if c.get(k)})
    if not salida:
        raise ValueError("El archivo no tiene ningun contacto valido.")
    return salida


def importar_contactos(nuevos: list[dict], reemplazar: set[str] | None = None) -> tuple[int, int, list[str]]:
    """Fusiona contactos en la agenda.

    Devuelve (agregados, reemplazados, nombres_en_conflicto). Los que ya existen
    y no estan en `reemplazar` se dejan como estan: pisar la agenda de alguien en
    silencio no es aceptable.
    """
    reemplazar = reemplazar or set()
    agenda = load_contacts()
    por_nombre = {_plano(c.get("nombre", "")): i for i, c in enumerate(agenda)}

    agregados = cambiados = 0
    conflictos = []
    for c in nuevos:
        clave = _plano(c["nombre"])
        if clave in por_nombre:
            if c["nombre"] in reemplazar or clave in {_plano(x) for x in reemplazar}:
                agenda[por_nombre[clave]] = c
                cambiados += 1
            else:
                conflictos.append(c["nombre"])
            continue
        agenda.append(c)
        por_nombre[clave] = len(agenda) - 1
        agregados += 1

    if agregados or cambiados:
        save_contacts(agenda)
    return agregados, cambiados, conflictos


MEMORIA_PATH = os.path.join(BASE, "MEMORIA.md")


def load_brief() -> str:
    """Manual de comportamiento + memoria. Va entero en cada system prompt, asi
    que los archivos estan escritos telegraficos a proposito.

    Son dos archivos separados a proposito: `EVE.md` es el manual, igual para
    todos y versionado; `MEMORIA.md` son los datos del usuario, que no van al
    repositorio.

    La memoria pasa por `memoria.podar()`: le saca la cabecera --que esta escrita
    para la persona que edita el archivo, no para el modelo-- y la acota si
    crecio de mas. `recordar` solo agrega y nunca saca, asi que sin esto el
    archivo crece para siempre adentro de cada llamada.
    """
    partes = []
    if os.path.exists(BRIEF_PATH):
        with open(BRIEF_PATH, encoding="utf-8") as f:
            texto = f.read()
        # La primera linea es el titulo y la segunda una nota para quien lo
        # edita: el modelo no las necesita.
        cuerpo = texto.split("\n## ", 1)
        partes.append("## " + cuerpo[1] if len(cuerpo) > 1 else texto)
    if os.path.exists(MEMORIA_PATH):
        from . import memoria

        with open(MEMORIA_PATH, encoding="utf-8") as f:
            recordado = memoria.podar(f.read())
        if recordado:
            partes.append("## Memoria\n\n" + recordado)
    return "\n\n".join(partes)


def get_key(provider: str) -> str:
    """Clave desde el gestor de credenciales del SO; env var como fallback."""
    env = os.environ.get(KEY_NAMES.get(provider, ""))
    if env:
        return env
    import keyring  # import perezoso: los tests de logica no lo necesitan

    try:
        return keyring.get_password(SERVICE, provider) or ""
    except Exception:  # noqa: BLE001 - keyring tira su propia jerarquia de errores
        # Un Linux sin escritorio no tiene llavero, y ahi keyring no devuelve
        # vacio: revienta. Sin esta red, cualquier consulta de clave -no solo la
        # del motor- tumbaba a Eve entera en vez de comportarse como si la clave
        # no estuviera cargada, que es lo que de hecho pasa. La variable de
        # entorno de arriba sigue siendo la salida para esas maquinas.
        return ""


def set_key(provider: str, value: str) -> None:
    import keyring

    if value:
        keyring.set_password(SERVICE, provider, value)
    else:
        try:
            keyring.delete_password(SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            pass


# --- historial -------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    engine TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cache_read INTEGER
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    tool TEXT NOT NULL,
    detail TEXT NOT NULL,
    outcome TEXT NOT NULL
);
"""


# Columnas que se agregaron despues. `CREATE TABLE IF NOT EXISTS` no las suma a
# una tabla que ya existe, y la base del usuario ya existe hace versiones.
_COLUMNAS_TURNS = {"engine": "TEXT", "tokens_in": "INTEGER",
                   "tokens_out": "INTEGER", "cache_read": "INTEGER"}
_migradas: set = set()


@contextlib.contextmanager
def db():
    """Conexion que hace commit y CIERRA.

    Antes esto devolvia la conexion pelada y los seis lugares la usaban como
    `with db() as conn`. El `with` de sqlite hace commit pero no cierra: la
    conexion queda viva hasta que el recolector pase. En Windows eso deja el
    archivo trabado, y con la base en un directorio temporal el borrado falla.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(_SCHEMA)
        # Una vez por archivo: los tests cambian DB_PATH, asi que no alcanza con
        # una bandera global.
        if DB_PATH not in _migradas:
            tiene = {fila[1] for fila in conn.execute("PRAGMA table_info(turns)")}
            for nombre, tipo in _COLUMNAS_TURNS.items():
                if nombre not in tiene:
                    conn.execute(f"ALTER TABLE turns ADD COLUMN {nombre} {tipo}")
            _migradas.add(DB_PATH)
        yield conn
        conn.commit()
    finally:
        conn.close()


def sumar_uso(acumulado: dict, entrada=0, salida=0, cache=0) -> None:
    """Suma el gasto de UNA llamada al acumulado del turno.

    Un turno puede hacer varias llamadas al modelo: cada tool que se ejecuta
    obliga a otra vuelta. Contar solo la ultima diria que un turno que abrio
    tres programas costo lo mismo que decir la hora.
    """
    acumulado["entrada"] = acumulado.get("entrada", 0) + int(entrada or 0)
    acumulado["salida"] = acumulado.get("salida", 0) + int(salida or 0)
    acumulado["cache"] = acumulado.get("cache", 0) + int(cache or 0)


def log_turn(role: str, text: str, motor: str = "", uso: dict | None = None) -> None:
    """Un turno. `uso` es lo que devolvio el modelo: los 4 motores lo tiraban."""
    uso = uso or {}
    with db() as conn:
        conn.execute(
            "INSERT INTO turns (ts, role, text, engine, tokens_in, tokens_out, cache_read)"
            " VALUES (?,?,?,?,?,?,?)",
            (time.time(), role, text, motor,
             uso.get("entrada"), uso.get("salida"), uso.get("cache")),
        )


def historial_neutro(cfg: dict, ahora: float = 0.0) -> list[dict]:
    """Los ultimos turnos en el unico formato que entienden los cuatro motores.

    La tabla `turns` la escriben los cuatro desde siempre y hasta ahora nadie la
    leia de vuelta. Cada motor guardaba lo suyo en su propio formato -- objetos
    del SDK de Anthropic, dicts de Ollama, un session_id opaco del CLI -- asi que
    cambiar de motor, o reiniciar Eve, borraba la conversacion.

    Van solo pregunta y respuesta. Los pasos intermedios de tools son del
    protocolo de cada motor y no se pueden traducir; para seguir el hilo de una
    charla tampoco hacen falta.
    """
    ahora = ahora or time.time()
    tope = max(1, int(cfg.get("context_turns", 6) or 6))
    minutos = float(cfg.get("context_minutes", 10) or 10)
    with db() as conn:
        # Lo anterior al ultimo corte no cuenta: si el usuario pidio olvidar, no
        # puede volver porque un cambio de config rearmo el motor.
        corte = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM turns WHERE role = 'corte'"
        ).fetchone()[0]
        filas = conn.execute(
            "SELECT ts, role, text FROM turns WHERE role IN ('user','assistant')"
            " AND id > ? ORDER BY id DESC LIMIT ?", (corte, tope)
        ).fetchall()
    recientes = [
        {"ts": f[0], "role": f[1], "content": f[2]}
        for f in reversed(filas) if ahora - f[0] <= minutos * 60
    ]
    # La misma normalizacion que usan los motores: tiene que empezar en `user`.
    return trim_history(recientes, tope, minutos, ahora)


AUTORIDADES = ("usuario", "eve", "preguntar")

# Las claves que Eve NO puede escribir por `E ajustar`, pase lo que pase.
#
# No es una preferencia y por eso no es configurable: son las claves que
# gobiernan sus propios frenos, y un freno que el frenado puede soltar no es un
# freno. Sin esta lista, cualquiera de estas ocho lineas desarmaba el resto del
# programa, y las ocho andaban:
#
#   E ajustar confirm_destructive false   apaga la confirmacion de destructivos
#   E ajustar workdirs C:\                el allowlist de rutas deja de existir
#   E ajustar addons_aprobados x:abc123   se auto-aprueba un addon sin mostrarlo
#   E ajustar autoridad eve               se da permiso a si misma
#   E ajustar claves_del_usuario ""       borra lo que el usuario habia trabado
#   E ajustar cc_permission_mode bypass   le saca el hook al motor claude-code
#   E ajustar ayuda_alcance codigo       se habilita a escribir addons .py
#   E ajustar archivos_alcance escribir  se habilita a pisar tus archivos
#
# La aprobacion de addons por huella vivia en la misma config que Eve podia
# escribir, asi que ese freno entero era decorativo. La asimetria es a proposito:
# vos las cambias en el panel cuando quieras; ella no, ni preguntando.
NUNCA_POR_EVE = (
    "confirm_destructive",
    # Encender los servidores MCP es autorizar que corra codigo de terceros en
    # tu maquina. Que Eve pudiera pasar `mcp_modo` de `prompt` a `cliente`
    # seria darle la llave del cajon donde esta guardada la llave: es
    # exactamente la clase de ajuste que esta lista existe para cerrar.
    "mcp_modo",
    "workdirs",
    "addons_aprobados",
    "autoridad",
    "claves_del_usuario",
    "cc_permission_mode",
    # La ultima se sumo despues, y por el mismo camino que las otras: se
    # encontro agregandole el hermano `ayuda_vocabulario`. Decide si Eve
    # puede DEJAR ESCRITO un addon .py, o sea que es el techo de su propia
    # autonomia; que ella pueda subirlo de `datos` a `codigo` volvia
    # decorativo el nivel que el usuario eligio. `ayuda_vocabulario` NO
    # esta aca a proposito: solo cambia cuanto texto viaja, no lo que
    # puede hacer, asi que tocarlo no le compra ningun permiso.
    "ayuda_alcance",
    "archivos_alcance",
    # Y la novena la encontro el mismo test, apenas se agrego. Parece de la
    # familia de `ayuda_vocabulario` --las dos deciden CUANTO texto viaja-- y
    # no lo es: pasar de `nada` a `consultar` hace existir `E skill ver`, o
    # sea que le da acceso a archivos del usuario que antes no podia leer.
    # Cuanto viaja no compra permisos; que el comando exista, si.
    "skills_alcance",
    # La decima, por la misma razon exacta que `addons_aprobados`: un comando
    # `sistema` corre lo que diga el archivo, y la aprobacion es lo unico que
    # separa "escrito" de "corriendo". Si Eve pudiera escribir esta clave, se
    # aprobaria sola lo que ella misma dejo escrito en Comandos.md --y puede
    # escribir archivos si `archivos_alcance` esta en `escribir`.
    "comandos_aprobados",
)


def marcar_tocadas(claves) -> None:
    """Anota que estas claves las cambio el usuario a mano."""
    claves = [c for c in claves if c]
    if not claves:
        return
    cfg = load_config()
    previas = {c.strip() for c in str(cfg.get("claves_del_usuario", "")).split(",") if c.strip()}
    nuevas = previas | set(claves)
    if nuevas != previas:
        cfg["claves_del_usuario"] = ",".join(sorted(nuevas))
        save_config(cfg)


def trabada(clave: str, cfg: dict = None) -> bool:
    """Si Eve NO puede tocar esta clave porque manda el usuario."""
    cfg = cfg if cfg is not None else load_config()
    if str(cfg.get("autoridad", "usuario")) != "usuario":
        return False
    marcadas = {c.strip() for c in str(cfg.get("claves_del_usuario", "")).split(",") if c.strip()}
    return clave in marcadas


def destrabar(clave: str = "") -> str:
    """Suelta una clave, o todas si no se dice cual."""
    cfg = load_config()
    if not clave:
        cfg["claves_del_usuario"] = ""
        save_config(cfg)
        return "Listo, ninguna clave queda trabada."
    marcadas = {c.strip() for c in str(cfg.get("claves_del_usuario", "")).split(",") if c.strip()}
    marcadas.discard(clave)
    cfg["claves_del_usuario"] = ",".join(sorted(marcadas))
    save_config(cfg)
    return f"{clave} queda libre."


def olvidar() -> None:
    """Corta el hilo: lo de antes deja de ser conversacion en curso.

    Se marca en la misma tabla en vez de borrar nada. El log sigue sirviendo
    para el historial del panel y para medir el gasto; lo unico que cambia es
    que `historial_neutro` no lo trae de vuelta.
    """
    with db() as conn:
        conn.execute("INSERT INTO turns (ts, role, text) VALUES (?,?,?)",
                     (time.time(), "corte", ""))


def gasto_reciente(limite: int = 50) -> list[dict]:
    """Lo que costaron los ultimos turnos. Lo lee el medidor de contexto."""
    with db() as conn:
        filas = conn.execute(
            "SELECT ts, engine, tokens_in, tokens_out, cache_read FROM turns"
            " WHERE tokens_in IS NOT NULL ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [{"ts": f[0], "motor": f[1] or "", "entrada": f[2] or 0,
             "salida": f[3] or 0, "cache": f[4] or 0} for f in filas]


def log_action(tool: str, detail: str, outcome: str) -> None:
    """Log de auditoria. Sin esto, 'se ejecuto algo mal' es indepurable."""
    with db() as conn:
        conn.execute(
            "INSERT INTO actions (ts, tool, detail, outcome) VALUES (?,?,?,?)",
            (time.time(), tool, detail[:2000], outcome[:2000]),
        )


def recent_turns(limit: int = 200) -> list[tuple]:
    with db() as conn:
        return conn.execute(
            "SELECT ts, role, text FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def recent_actions(limit: int = 200) -> list[tuple]:
    with db() as conn:
        return conn.execute(
            "SELECT ts, tool, detail, outcome FROM actions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


LATIDO_PATH = os.path.join(BASE, "latido.json")
# Lo que esta haciendo Eve ahora mismo, para el overlay. Lo escribe el listener
# varias veces por segundo mientras hay actividad; en reposo no se escribe nada.
OVERLAY_PATH = os.path.join(BASE, "overlay.json")
# El overlay avisa que ya hay uno corriendo, para no apilar dos ventanas.
OVERLAY_VIVO_PATH = os.path.join(BASE, "overlay-vivo.json")
# Lo mismo para la ventana de actividad. No lo tenia, asi que cada `mostrar`
# habria abierto una ventana nueva encima de la anterior.
CONSOLA_VIVO_PATH = os.path.join(BASE, "consola-viva.json")
# Lo ultimo que Eve puso en pantalla con `E mostrar`. Archivo propio y no el
# canal del cartel: ese lo pisa el listener varias veces por segundo.
DOCUMENTO_PATH = os.path.join(BASE, "documento.json")
# Lo que entra en la ventana. Mas que esto no lo lee nadie de un tiron, y el
# archivo se relee una vez por segundo.
TOPE_DOCUMENTO = 20000


def _escribir_señal(ruta: str, datos: dict) -> None:
    """Escritura directa, sin el temporal + os.replace de la config.

    Aca la atomicidad no compensa: son varias escrituras por segundo y en
    Windows os.replace falla cuando el lector tiene el archivo abierto. Una
    lectura partida es un cuadro perdido de una animacion, no un dato perdido:
    quien lee lo trata como ruido y espera al siguiente.
    """
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({**datos, "ts": time.time(), "pid": os.getpid()}, f)
    except OSError:
        pass


def _leer_señal(ruta: str, max_edad: float) -> dict | None:
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        # Ojo: aca NO se usa _leer_json, que aparta el archivo como .roto. Una
        # lectura a medias es lo esperado en un canal a 10 Hz, no una corrupcion.
        return None
    return datos if time.time() - datos.get("ts", 0) < max_edad else None


def emitir_overlay(datos: dict) -> None:
    """Estado actual para el overlay: que hace Eve, nivel de audio y texto."""
    _escribir_señal(OVERLAY_PATH, datos)


def estado_overlay(max_edad: float = 3.0) -> dict | None:
    """Ultimo estado si es reciente. None significa 'Eve no esta haciendo nada'."""
    return _leer_señal(OVERLAY_PATH, max_edad)


def overlay_ya_corre(max_edad: float = 6.0) -> bool:
    """True si otro proceso de overlay esta vivo.

    Sin esto, el preview del panel y el que lanza el listener se apilan y quedan
    dos HUD dibujados uno encima del otro.
    """
    vivo = _leer_señal(OVERLAY_VIVO_PATH, max_edad)
    return bool(vivo and vivo.get("pid") != os.getpid())


def overlay_presente() -> None:
    """Lo llama el propio overlay cada par de segundos."""
    _escribir_señal(OVERLAY_VIVO_PATH, {})


def consola_ya_corre(max_edad: float = 6.0) -> bool:
    """True si la ventana de actividad ya esta abierta en otro proceso.

    Sin esto cada `E mostrar` abriria una ventana nueva encima de la anterior,
    que es peor que no abrir ninguna: el usuario termina con seis y sin saber
    cual mira el asistente.
    """
    vivo = _leer_señal(CONSOLA_VIVO_PATH, max_edad)
    return bool(vivo and vivo.get("pid") != os.getpid())


def consola_presente() -> None:
    """Lo llama la propia ventana de actividad cada par de segundos."""
    _escribir_señal(CONSOLA_VIVO_PATH, {})


def guardar_documento(titulo: str, texto: str, origen: str = "") -> None:
    """Deja lo que Eve quiere mostrar, para el modulo `documento`.

    Atomico y no como las señales del overlay: esto se escribe una vez por
    `mostrar` y se lee una vez por segundo, asi que la escritura partida no es
    "un cuadro perdido de una animacion" sino medio documento.
    """
    _escribir_json(DOCUMENTO_PATH, {
        "titulo": str(titulo or "")[:200],
        "texto": str(texto or "")[:TOPE_DOCUMENTO],
        "origen": str(origen or "")[:400],
        "ts": time.time(),
    })


def ultimo_documento() -> dict:
    datos = _leer_json(DOCUMENTO_PATH, {})
    return datos if isinstance(datos, dict) else {}


OVERLAY_SALIR_PATH = os.path.join(BASE, "overlay-salir")


def pedir_salida_overlay(esperar: float = 3.0) -> bool:
    """Le pide al overlay que se cierre y espera a que lo haga.

    Hace falta antes de instalar una actualizacion: el overlay corre desde el
    mismo .exe que el asistente, y si sigue vivo el instalador no puede
    reemplazarlo y se traba pidiendo que cierres las aplicaciones a mano.
    Tambien sirve al salir, para que el cartel se vaya en el acto.
    """
    if not os.path.exists(OVERLAY_VIVO_PATH):
        return True
    try:
        with open(OVERLAY_SALIR_PATH, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        return False
    limite = time.time() + esperar
    while time.time() < limite:
        if not overlay_ya_corre(max_edad=2.0):
            return True
        time.sleep(0.2)
    return False


def toca_salir_overlay(desde: float = 0.0) -> bool:
    """Lo consulta el overlay. Consume la señal para no repetirla.

    `desde` es cuando nacio quien pregunta: un pedido de salida anterior a eso
    no era para el. Sin esa comprobacion, una Eve que se estaba cerrando mataba
    al cartel de la Eve que acababa de arrancar, que es lo que pasaba al
    actualizar: el instalador reinicia Eve, la vieja termina de morir y su
    pedido de salida se lo comia el cartel nuevo.
    """
    if not os.path.exists(OVERLAY_SALIR_PATH):
        return False
    try:
        with open(OVERLAY_SALIR_PATH, encoding="utf-8") as f:
            cuando = float(f.read().strip() or 0)
    except (OSError, ValueError):
        cuando = time.time()  # ilegible: se le hace caso, por las dudas
    if cuando < desde:
        return False  # es de antes de que existieramos; no es para nosotros
    try:
        os.remove(OVERLAY_SALIR_PATH)
    except OSError:
        pass
    return True


def latir(datos: dict) -> None:
    """El asistente deja señales de vida para que el panel sepa si esta vivo."""
    datos = {**datos, "ts": time.time(), "pid": os.getpid()}
    try:
        with open(LATIDO_PATH, "w", encoding="utf-8") as f:
            json.dump(datos, f)
    except OSError:
        pass


def latido(max_edad: float = 20.0) -> dict | None:
    """Ultimo latido si es reciente, None si el asistente no esta corriendo.

    Un archivo en vez de preguntarle al SO por los procesos: consultar `tasklist`
    cada pocos segundos desde una app sin consola abria y cerraba una ventana
    negra todo el tiempo, y ademas es mucho mas caro que leer 80 bytes.
    """
    try:
        with open(LATIDO_PATH, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return datos if time.time() - datos.get("ts", 0) < max_edad else None


def otro_asistente(max_edad: float = 20.0) -> int:
    """PID de otro asistente vivo, o 0 si este es el unico.

    Sin esta guarda arrancar Eve dos veces -el acceso directo mas el autostart,
    o dos clics seguidos- deja dos listeners con un hook global cada uno sobre
    la misma tecla: apretas una vez y se graban dos, se mandan dos pedidos y
    contestan dos voces encima. Se nota tarde, porque a simple vista hay un solo
    icono en la bandeja y el sintoma parece de otra cosa.

    El latido caduca solo, asi que si el anterior murio mal esto no traba el
    arranque siguiente: a los 20 segundos deja de contar.
    """
    vivo = latido(max_edad)
    if not vivo or not vivo.get("pid") or vivo["pid"] == os.getpid():
        return 0
    return int(vivo["pid"]) if _proceso_vivo(int(vivo["pid"])) else 0


def asistente_corriendo() -> int:
    """El PID del asistente si esta vivo, 0 si no.

    Es `otro_asistente` con otro nombre y otra intencion, y por eso existe
    aparte: aquella la usa el arranque para NO abrir un segundo asistente --de
    ahi que excluya el propio proceso-- y esta la usa el panel para saber si
    hace falta abrir uno. Preguntar lo mismo con el nombre de lo que uno quiere
    saber es la diferencia entre leer el codigo y descifrarlo.
    """
    return otro_asistente()


def _proceso_vivo(pid: int) -> bool:
    """Si ese PID sigue existiendo.

    No alcanza con que el latido sea reciente: Eve lo borra al salir bien, pero
    matarla a la fuerza o un cuelgue no ejecutan ese `finally`. Sin comprobar el
    proceso, cerrarla mal la dejaba sin poder arrancar durante veinte segundos,
    diciendo que ya estaba corriendo cuando no habia nada.

    **En Windows `os.kill(pid, 0)` no pregunta si el proceso existe.** Alla
    `CTRL_C_EVENT` vale 0, asi que Python lee la señal 0 como "manda Ctrl+C al
    grupo de consola de ese pid" en vez de como el sondeo de POSIX. Para un
    proceso sin consola --o sea, para Eve, que corre sin ventana-- eso falla
    siempre con WinError 87, y la funcion devolvia False sobre un proceso vivo.

    Medido: con dos Eve abiertas a proposito, `_proceso_vivo` daba False para
    las dos. `otro_asistente()` devolvia 0 siempre, y la guarda de una sola Eve
    --que existe desde la v1.4.3-- nunca corrio en el sistema donde mas importa.
    Cada doble clic dejaba otro listener con su propio hook global sobre F12.

    El test no lo agarro porque comprobaba contra `os.getppid()`, que es el
    unico proceso ajeno que SI esta en el mismo grupo de consola. Elegido para
    arreglar otra cosa, y de paso volvio el caso real intesteable.
    """
    if pid <= 0:
        return False
    if plataforma.WINDOWS:
        import ctypes

        k32 = ctypes.windll.kernel32
        # QUERY_LIMITED_INFORMATION y no ALL_ACCESS: alcanza para preguntar y es
        # el unico que abre procesos de otra integridad sin pedir permisos.
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            if k32.GetExitCodeProcess(h, ctypes.byref(codigo)):
                # 259 es STILL_ACTIVE. Un proceso que termino con ese codigo
                # exacto se leeria como vivo; es el precio conocido de esta API
                # y no hay forma de distinguirlo sin abrir un handle de espera.
                return codigo.value == 259
            return True
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, es de otro usuario
    except OSError:
        return False
    return True


def clear_history(also_actions: bool = False) -> int:
    """Borra la conversacion guardada. El log de auditoria se conserva salvo que
    se pida lo contrario: es el registro de lo que Eve ejecuto en la PC."""
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        conn.execute("DELETE FROM turns")
        if also_actions:
            conn.execute("DELETE FROM actions")
    return n


def trim_history(history: list[dict], max_turns: int, max_minutes: float, now: float) -> list[dict]:
    """Ventana rodante: ni stateless puro ni chat infinito.

    Cada entrada es {"ts": float, "role": str, "content": ...}. Descarta lo
    viejo por tiempo y por cantidad, y garantiza que el primer mensaje que
    queda sea de rol `user` (la API rechaza historiales que arrancan en
    assistant, y un tool_result huerfano tambien).
    """
    cutoff = now - max_minutes * 60
    kept = [m for m in history if m["ts"] >= cutoff][-max_turns:]
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    # Un turno user que arranca con tool_result quedo huerfano de su tool_use.
    while kept and _starts_with_tool_result(kept[0]):
        kept.pop(0)
        while kept and kept[0]["role"] != "user":
            kept.pop(0)
    return kept


def _starts_with_tool_result(msg: dict) -> bool:
    content = msg.get("content")
    if not isinstance(content, list) or not content:
        return False
    first = content[0]
    if isinstance(first, dict):
        return first.get("type") == "tool_result"
    return getattr(first, "type", None) == "tool_result"
