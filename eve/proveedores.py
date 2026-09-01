"""Los servicios compatibles con /chat/completions, como DATOS.

Viven aparte de `compat_engine` por una razon medida: leer este diccionario
importaba el motor entero --que arrastra `ollama_engine` y `brain`, y con
ellos los SDK de los modelos-- y eso costaba **5.1 de los 6.6 segundos** que
tardaba en abrir el panel nuevo. Cinco segundos de ventana en blanco para
llenar un desplegable.

Este archivo no importa nada, y esa es toda su gracia.
"""

PROVEEDORES = {
    # El alias `-latest` y no un numero de version: Google va sacando modelos
    # concretos de circulacion y una cuenta nueva se come un 404 diciendo "this
    # model is no longer available to new users". El alias siempre apunta a uno
    # vigente.
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "gemini", "gemini-flash-latest"),
    "openai": ("https://api.openai.com/v1", "openai", "gpt-5-mini"),
    "groq": ("https://api.groq.com/openai/v1", "groq", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek", "deepseek-chat"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter",
                   "deepseek/deepseek-chat-v3.1:free"),
    "xai": ("https://api.x.ai/v1", "xai", "grok-4-fast"),
    # Servidor local: no necesita clave y no sale nada de la maquina.
    "lmstudio": ("http://localhost:1234/v1", "", "local"),
    # OmniRoute es una pasarela: corre en TU maquina y por detras habla con
    # decenas de proveedores. Emite su propia clave, pero NO la exige: su
    # `REQUIRE_API_KEY` viene en `false`. Medido contra el servicio corriendo:
    # `/v1/models` y `/v1/chat/completions` contestan sin ninguna clave.
    #
    # El modelo venia VACIO, con el argumento de que enruta a cientos y elegir
    # uno seria adivinar. Eso hacia que instalarlo tirara `RuntimeError: Falta
    # el nombre del modelo` con solo abrir el programa. Y dejarlo pasar tampoco
    # servia: preguntado con el modelo vacio, OmniRoute contesta
    # `{"error": "Missing model"}`, o sea que solo se mudaba la falla del
    # arranque a la primera orden hablada, que es peor.
    #
    # `auto/best-chat` no es adivinar: es un modelo que la pasarela publica en
    # su propia lista para que ELLA elija. Comprobado: contesta, y por detras
    # resolvio a mistral. El boton de buscar modelos sigue estando para
    # cambiarlo por uno concreto.
    "omniroute": ("http://localhost:20128/v1", "omniroute", "auto/best-chat"),
    # "propio" usa lo que el usuario haya escrito en compat_url / compat_modelo.
    "propio": ("", "compat", ""),
}

GRATIS = ("gemini", "groq", "openrouter", "lmstudio")
