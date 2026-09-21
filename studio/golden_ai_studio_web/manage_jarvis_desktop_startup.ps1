param(
    [ValidateSet('status', 'enable', 'disable')]
    [string]$Action = 'status'
)

$startupDir = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDir 'JARVIS.lnk'
$launcher = 'C:\GoldenAI\studio\golden_ai_studio_web\start_jarvis_desktop.bat'
$workingDirectory = 'C:\GoldenAI\studio\golden_ai_studio_web'

if ($Action -eq 'enable') {
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "Launcher não encontrado: $launcher"
    }
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = '--hidden'
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.Description = 'JARVIS Desktop - iniciar oculto com Windows'
    $shortcut.Save()
    Write-Output "Startup habilitado: $shortcutPath"
    exit 0
}

if ($Action -eq 'disable') {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath
    }
    Write-Output 'Startup desabilitado.'
    exit 0
}

if (Test-Path -LiteralPath $shortcutPath) {
    Write-Output "Startup habilitado: $shortcutPath"
} else {
    Write-Output 'Startup desabilitado.'
}
