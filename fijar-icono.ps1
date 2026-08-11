# Saca el icono de Eve del desbordamiento (la flechita) y lo fija visible en la
# barra de tareas.
#
# Requisito: haber corrido Eve.bat al menos una vez, para que Windows registre
# el icono. Reinicia el Explorador de Windows al final (se cierran las ventanas
# del explorador; las demas apps no se tocan).

$entries = Get-ChildItem 'HKCU:\Control Panel\NotifyIconSettings' -ErrorAction SilentlyContinue |
    Where-Object { (Get-ItemProperty $_.PSPath).ExecutablePath -like '*pythonw.exe' }

if (-not $entries) {
    Write-Host "No encontre el icono registrado. Corre Eve.bat primero, esperá a que"
    Write-Host "aparezca en la flechita, cerralo, y volvé a correr este script."
    exit 1
}

foreach ($e in $entries) {
    Set-ItemProperty $e.PSPath -Name IsPromoted -Value 1 -Type DWord
    Write-Host "promovido: $($e.PSChildName)"
}

Write-Host "Reiniciando el Explorador..."
Stop-Process -Name explorer -Force
Write-Host "Listo. El icono deberia quedar visible en la barra."
