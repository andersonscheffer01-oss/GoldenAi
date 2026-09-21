$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'GOLDEN JARVIS V4.lnk'
$launcher = 'C:\GoldenAI\studio\golden_ai_studio_web\start_jarvis_desktop_v4.bat'
$workDir = 'C:\GoldenAI\studio\golden_ai_studio_web'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $workDir
$shortcut.Description = 'Golden Jarvis Desktop V4 - Interface nativa PySide6'
$shortcut.Save()
Write-Host "Shortcut created at: $shortcutPath"