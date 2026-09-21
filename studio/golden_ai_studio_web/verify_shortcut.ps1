$shortcutPath = 'C:\Users\Anderson\Desktop\GOLDEN JARVIS V4.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
Write-Host "TargetPath: $($shortcut.TargetPath)"
Write-Host "WorkingDirectory: $($shortcut.WorkingDirectory)"
Write-Host "Description: $($shortcut.Description)"
Write-Host "IconLocation: $($shortcut.IconLocation)"