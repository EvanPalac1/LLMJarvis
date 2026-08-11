#!/usr/bin/env bash
# Instalador de LLMJarvis para macOS y Linux. Idempotente: correlo las veces que quieras.
#
#   ./setup.sh              instalacion normal (entorno aislado en .venv)
#   ./setup.sh --sin-modelo no predescarga el modelo de voz (~460 MB)
#   ./setup.sh --sin-venv   usa el Python del sistema
#
# El equivalente para Windows es setup.ps1.

set -u
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

SIN_MODELO=0; SIN_VENV=0
for arg in "$@"; do
    case "$arg" in
        --sin-modelo) SIN_MODELO=1 ;;
        --sin-venv)   SIN_VENV=1 ;;
    esac
done

paso=0
Paso() { paso=$((paso+1)); printf '\n\033[36m[%d] %s\033[0m\n' "$paso" "$1"; }
Ok()    { printf '    \033[32mOK  %s\033[0m\n' "$1"; }
Aviso() { printf '    \033[33m!   %s\033[0m\n' "$1"; }

SISTEMA="$(uname -s)"
echo "=== LLMJarvis / Eve - instalacion ($SISTEMA) ==="

# --- 1. Python -------------------------------------------------------------
Paso "Buscando Python 3.10 o superior"
PY=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
            PY="$cmd"; Ok "$($cmd --version) en $(command -v $cmd)"; break
        fi
    fi
done
if [ -z "$PY" ]; then
    cat <<'EOF'
    No encontre Python 3.10+.
      macOS:  brew install python@3.13
      Debian: sudo apt install python3 python3-venv python3-pip python3-tk
      Fedora: sudo dnf install python3 python3-tkinter
    Despues volve a correr este script.
EOF
    exit 1
fi

# --- 2. Entorno aislado ----------------------------------------------------
if [ "$SIN_VENV" -eq 1 ]; then
    Aviso "Usando el Python del sistema (--sin-venv)."
else
    Paso "Preparando el entorno aislado (.venv)"
    [ -d "$RAIZ/.venv" ] || "$PY" -m venv "$RAIZ/.venv"
    if [ -x "$RAIZ/.venv/bin/python" ]; then
        PY="$RAIZ/.venv/bin/python"; Ok ".venv listo"
    else
        Aviso "No pude crear .venv (falta python3-venv?), sigo con el Python del sistema."
    fi
fi

# --- 3. Dependencias -------------------------------------------------------
Paso "Instalando dependencias (tarda unos minutos la primera vez)"
"$PY" -m pip install --upgrade pip --quiet
if ! "$PY" -m pip install -r "$RAIZ/requirements.txt"; then
    echo "    Fallo pip. Revisa el error de arriba."
    exit 1
fi
Ok "dependencias instaladas"

# --- 4. Icono e indice -----------------------------------------------------
Paso "Generando el icono"
"$PY" -m eve.icon >/dev/null && Ok "assets/eve.png"

Paso "Indexando programas y juegos instalados"
"$PY" -m eve.apps

# --- 5. Modelo de voz ------------------------------------------------------
if [ "$SIN_MODELO" -eq 1 ]; then
    Aviso "Modelo de voz salteado. Se baja la primera vez que hables."
else
    Paso "Descargando el modelo de reconocimiento de voz (~460 MB, una sola vez)"
    if "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" 2>/dev/null; then
        Ok "modelo 'small' en cache"
    else
        Aviso "No se pudo predescargar; se baja al primer uso."
    fi
fi

# --- 6. Voz de salida ------------------------------------------------------
Paso "Voz de salida"
Aviso "macOS y Linux no tienen SAPI. Abri el panel > Voces y descarga una voz de Piper;"
Aviso "despues elegi 'piper' como proveedor de TTS."

# --- 7. Motor --------------------------------------------------------------
Paso "Configurando el motor"
if command -v claude >/dev/null 2>&1 && claude auth status 2>/dev/null | grep -q '"loggedIn": *true'; then
    Ok "Claude Code con sesion iniciada: uso tu suscripcion, no hace falta API key."
    MOTOR="claude-code"
elif command -v ollama >/dev/null 2>&1; then
    Ok "Ollama detectado: se usa el modelo local, sin claves ni nube."
    MOTOR="ollama"
else
    Aviso "Sin Claude Code ni Ollama. Vas a necesitar una API key de Anthropic (panel > Claves),"
    Aviso "o instalar Ollama desde ollama.com para correr todo local."
    MOTOR="api"
fi
if [ ! -f "$RAIZ/config.json" ]; then
    "$PY" - "$MOTOR" <<'EOF'
import json, os, sys
raiz = os.path.dirname(os.path.abspath("setup.sh"))
json.dump({"engine": sys.argv[1], "workdirs": [os.path.expanduser("~/Documents")],
           "tts_provider": "piper"},
          open("config.json", "w", encoding="utf-8"), indent=2)
EOF
    Ok "config.json creado con el motor '$MOTOR'"
else
    Aviso "Ya existe config.json, no lo toco."
fi

# --- 8. Lanzador -----------------------------------------------------------
Paso "Creando el lanzador"
cat > "$RAIZ/eve.sh" <<EOF
#!/usr/bin/env bash
cd "\$(dirname "\${BASH_SOURCE[0]}")"
exec "$PY" main.py "\$@"
EOF
chmod +x "$RAIZ/eve.sh"
Ok "$RAIZ/eve.sh"

if [ "$SISTEMA" = "Linux" ]; then
    APPS="$HOME/.local/share/applications"
    mkdir -p "$APPS"
    cat > "$APPS/eve.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Eve
Comment=Asistente de voz local
Exec=$RAIZ/eve.sh
Icon=$RAIZ/assets/eve.png
Terminal=false
Categories=Utility;
EOF
    Ok "$APPS/eve.desktop"
fi

# --- 9. Chequeo final ------------------------------------------------------
Paso "Chequeo final"
"$PY" diagnostico.py

cat <<EOF

=== Listo ===

  1. Abri el panel:   $PY -m eve.gui
     Revisa las rutas permitidas y descarga una voz en la pestaña Voces.
  2. Que tecla manda tu keypad:   $PY diagnostico.py --tecla
  3. Arranca Eve:   ./eve.sh

EOF
if [ "$SISTEMA" = "Darwin" ]; then
    cat <<'EOF'
  macOS pide permiso para leer el teclado:
  Ajustes del Sistema > Privacidad y seguridad > Accesibilidad, y agrega la
  Terminal (o el .app si armaste el ejecutable con `python build.py`).
EOF
else
    cat <<'EOF'
  En Linux el atajo global necesita acceso a /dev/input:
      sudo usermod -aG input "$USER"    (y volver a iniciar sesion)
  Bajo Wayland solo llegan eventos de apps sobre Xwayland.
EOF
fi
