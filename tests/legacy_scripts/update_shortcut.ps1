$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("C:\Users\Anderson\Desktop\Golden AI.lnk")
$sc.TargetPath = "C:\GoldenAI\ABRIR_GOLDEN_AI_STUDIO.vbs"
$sc.WorkingDirectory = "C:\GoldenAI"
$sc.IconLocation = "C:\GoldenAI\assets\golden_ai.ico, 0"
$sc.Description = "Golden AI Studio"
$sc.Save()

$sc2 = $ws.CreateShortcut("C:\Users\Anderson\Desktop\Golden AI.lnk")
Write-Host "IconLocation:" $sc2.IconLocation
Write-Host "Target:" $sc2.TargetPath
Write-Host "WorkingDir:" $sc2.WorkingDirectory