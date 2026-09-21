' Golden AI Studio - Launcher sem janela de console
' Inicia o Studio com pythonw.exe (sem tela preta/CMD visivel)
' Preserva ConPTY, logs e auditoria internos

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\GoldenAI"

pythonExe = "C:\GoldenAI\.venv\Scripts\pythonw.exe"
studioApp = "C:\GoldenAI\studio\golden_ai_studio.py"

' Verifica se pythonw.exe existe; fallback para python.exe se necessario
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(pythonExe) Then
    pythonExe = "C:\GoldenAI\.venv\Scripts\python.exe"
End If

If Not fso.FileExists(pythonExe) Then
    MsgBox "ERRO: Python do ambiente GoldenAI nao encontrado." & vbCrLf & _
           "Esperado: C:\GoldenAI\.venv\Scripts\pythonw.exe", 16, "Golden AI Studio"
    WScript.Quit 1
End If

If Not fso.FileExists(studioApp) Then
    MsgBox "ERRO: Golden AI Studio nao encontrado." & vbCrLf & _
           "Esperado: C:\GoldenAI\studio\golden_ai_studio.py", 16, "Golden AI Studio"
    WScript.Quit 1
End If

' Run com estilo de janela 0 (oculto) - sem CMD/PowerShell visivel
' O Studio (PySide6) abre sua propria janela GUI
WshShell.Run """" & pythonExe & """ """ & studioApp & """", 0, False