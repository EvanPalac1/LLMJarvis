# Crea accesos directos en el Escritorio y (opcional) en el Inicio de Windows.
#   .\crear-accesos.ps1            -> solo Escritorio
#   .\crear-accesos.ps1 -Autostart -> Escritorio + arranque automatico

param([switch]$Autostart)

$root = $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell

python -c "import sys; sys.path.insert(0, r'$root'); from eve.icon import ensure_icon; ensure_icon()" | Out-Null
$icon = "$root\assets\eve.ico"
if (-not (Test-Path $icon)) { $icon = "$((Get-Command pythonw).Source),0" }

function New-Shortcut($path, $target, $desc) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $root
    $lnk.Description = $desc
    $lnk.IconLocation = $icon
    $lnk.Save()
    Write-Host "creado: $path"
}

$desktop = [Environment]::GetFolderPath('Desktop')
New-Shortcut "$desktop\Eve.lnk" "$root\Eve.bat" "LLMJarvis - asistente de voz"
New-Shortcut "$desktop\Eve - configuracion.lnk" "$root\Config.bat" "Panel de configuracion de LLMJarvis"

if ($Autostart) {
    $startup = [Environment]::GetFolderPath('Startup')
    New-Shortcut "$startup\Eve.lnk" "$root\Eve.bat" "LLMJarvis al iniciar sesion"
}
