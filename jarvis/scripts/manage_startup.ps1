param(
    [ValidateSet('install','status','enable','disable','remove','start','stop')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Golden Jarvis - Inicializa' + [char]0x00E7 + [char]0x00E3 + 'o Autom' + [char]0x00E1 + 'tica'
$FirewallName = 'Golden Jarvis 8780 Local Network'
$Root = Split-Path -Parent $PSScriptRoot
$Starter = Join-Path $PSScriptRoot 'start_jarvis.ps1'

switch ($Action) {
    'install' {
        $taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Starter`""
        $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
        $trigger.Delay = 'PT30S'
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings -Description 'Mantém o Golden Jarvis disponível somente na rede local.' -Force | Out-Null
        try {
            if (-not (Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue)) {
                New-NetFirewallRule -DisplayName $FirewallName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8780 -Profile Private -RemoteAddress LocalSubnet | Out-Null
            }
            Write-Output 'Tarefa e firewall privado instalados.'
        } catch {
            Write-Warning 'Tarefa instalada. Execute este comando como Administrador para criar a regra de firewall.'
        }
    }
    'status' { Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object TaskName,State; Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue | Select-Object DisplayName,Enabled,Profile }
    'enable' { Enable-ScheduledTask -TaskName $TaskName | Out-Null; Write-Output 'Inicialização automática ativada.' }
    'disable' { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Disable-ScheduledTask -TaskName $TaskName | Out-Null; Write-Output 'Inicialização automática desativada.' }
    'remove' { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue; Write-Output 'Tarefa removida; projeto e banco preservados.' }
    'start' { Start-ScheduledTask -TaskName $TaskName; Write-Output 'Inicialização solicitada.' }
    'stop' {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn app\.main:app' -and $_.CommandLine -match '8780' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
        Write-Output 'Backend do Jarvis interrompido.'
    }
}
