# Instalador de LLMJarvis. Idempotente: correlo las veces que quieras.
#
#   .\setup.ps1              instalacion normal (entorno aislado en .venv)
#   .\setup.ps1 -NoVenv      usa el Python del sistema, sin entorno aislado
#   .\setup.ps1 -SkipModel   no predescarga el modelo de voz (~460 MB)

param([switch]$NoVenv, [switch]$SkipModel)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root  # los `python -m eve.*` necesitan el paquete en el directorio actual
$paso = 0
function Paso($txt) { $script:paso++; Write-Host "`n[$script:paso] $txt" -ForegroundColor Cyan }
function Ok($txt)   { Write-Host "    OK  $txt" -ForegroundColor Green }
function Aviso($t)  { Write-Host "    !   $t" -ForegroundColor Yellow }

Write-Host "=== LLMJarvis / Eve - instalacion ===" -ForegroundColor White

# --- 1. Python -------------------------------------------------------------
Paso "Buscando Python 3.10 o superior"
$py = $null
foreach ($cmd in @("python", "py")) {
    $exe = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
    if (-not $exe) { continue }
    $v = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($v -and [version]$v -ge [version]"3.10") { $py = $exe; Ok "$exe (Python $v)"; break }
}
if (-not $py) {
    Write-Host @"
    No encontre Python 3.10+.

    Instalalo con:      winget install Python.Python.3.13
    o descargalo de:    https://www.python.org/downloads/

    IMPORTANTE: en el instalador marca "Add python.exe to PATH".
    Despues volve a correr este script.
"@ -ForegroundColor Red
    exit 1
}

# --- 2. Entorno aislado ----------------------------------------------------
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if ($NoVenv) {
    Aviso "Usando el Python del sistema (-NoVenv)."
} else {
    Paso "Preparando el entorno aislado (.venv)"
    if (-not (Test-Path $venvPy)) { & $py -m venv (Join-Path $root ".venv") }
    if (Test-Path $venvPy) { $py = $venvPy; Ok ".venv listo" }
    else { Aviso "No pude crear .venv, sigo con el Python del sistema." }
}

# --- 3. Dependencias -------------------------------------------------------
Paso "Instalando dependencias (tarda unos minutos la primera vez)"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "    Fallo pip. Revisa el error de arriba." -ForegroundColor Red; exit 1 }
Ok "dependencias instaladas"

# --- 4. Icono e indice de programas ---------------------------------------
Paso "Generando el icono"
& $py -m eve.icon | Out-Null
Ok "assets/eve.ico"

Paso "Indexando programas y juegos instalados"
& $py -m eve.apps

# --- 5. Modelo de voz ------------------------------------------------------
if ($SkipModel) {
    Aviso "Modelo de voz salteado. Se va a descargar la primera vez que hables."
} else {
    Paso "Descargando el modelo de reconocimiento de voz (~460 MB, una sola vez)"
    & $py -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok "modelo 'small' en cache" } else { Aviso "No se pudo predescargar; se bajara al primer uso." }
}

# --- 6. Motor: suscripcion o API key --------------------------------------
Paso "Configurando el motor"
$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
$logueado = $false
if ($claude) {
    try { $logueado = ((& claude auth status 2>$null) | ConvertFrom-Json).loggedIn } catch { $logueado = $false }
}
$cfgPath = Join-Path $root "config.json"
if ($logueado) {
    Ok "Claude Code con sesion iniciada: uso tu suscripcion, no hace falta API key."
    if (-not (Test-Path $cfgPath)) {
        # Config minima: el resto sale de eve/store.py DEFAULTS.
        @{ engine = "claude-code"; workdirs = @("$env:USERPROFILE\Documents") } |
            ConvertTo-Json | Set-Content $cfgPath -Encoding UTF8
        Ok "config.json creado con el motor 'claude-code'"
    } else {
        Aviso "Ya existe config.json, no lo toco. Revisa el motor en el panel."
    }
} elseif ($claude) {
    Aviso "Claude Code esta instalado pero sin sesion. Corre 'claude auth login', o carga una API key en el panel."
} else {
    Aviso "Sin Claude Code. Vas a necesitar una API key de Anthropic (pestaña Claves del panel),"
    Aviso "o instalar Claude Code para usar tu suscripcion: https://claude.com/claude-code"
}

# --- 7. Accesos directos ---------------------------------------------------
Paso "Creando accesos directos en el Escritorio"
& (Join-Path $root "crear-accesos.ps1")

# --- 8. Chequeo final ------------------------------------------------------
Paso "Chequeo final"
& $py diagnostico.py

Write-Host @"

=== Listo ===

  1. Abri "Eve - configuracion" en el Escritorio y revisa las rutas permitidas.
  2. Corre:  python diagnostico.py --tecla   y presiona el boton de tu keypad,
     para saber que tecla poner en el panel.
  3. Abri "Eve" en el Escritorio. Aparece en la bandeja (la flechita).
  4. Manten presionada la tecla, habla, solta.

  Arranque automatico con Windows:  .\crear-accesos.ps1 -Autostart
"@ -ForegroundColor White
