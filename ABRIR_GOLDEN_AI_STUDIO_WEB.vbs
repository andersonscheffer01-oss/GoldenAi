Set WshShell = CreateObject("WScript.Shell")
GoldenAIPath = "C:\GoldenAI\studio\golden_ai_studio_web"
GoldenAIRoot = "C:\GoldenAI"

WshShell.CurrentDirectory = GoldenAIPath
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""$p=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique); $p | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500; Start-Process -FilePath 'C:\GoldenAI\.venv\Scripts\python.exe' -ArgumentList 'server_agent.py','--port','8765' -WorkingDirectory 'C:\GoldenAI\studio\golden_ai_studio_web' -WindowStyle Hidden""", 0, True
WScript.Sleep 5000

WshShell.Run "http://127.0.0.1:8765/studio_v7.html", 1, False
