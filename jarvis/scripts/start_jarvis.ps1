param([switch]$Once)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$LogDir = Join-Path $Root 'logs'
$StartupLog = Join-Path $LogDir 'startup.log'
$StateFile = Join-Path $LogDir 'startup-state.json'
$StdoutLog = Join-Path $LogDir 'server_stdout.log'
$StderrLog = Join-Path $LogDir 'server_stderr.log'
$HealthUrl = 'http://127.0.0.1:8780/api/health'
$OllamaUrl = 'http://127.0.0.1:11434/api/tags'
$Mutex = [Threading.Mutex]::new($false, 'Local\GoldenJarvisSupervisor')

function Write-StartupLog([string]$Message) {
    Add-Content -LiteralPath $StartupLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" -Encoding UTF8
}

function Save-State([string]$Status, [string]$ErrorSummary = '') {
    $ip = & (Join-Path $PSScriptRoot 'detect_local_ipv4.ps1') -FirstOnly
    [ordered]@{
        status = $Status
        last_startup = (Get-Date).ToString('o')
        last_health_check = (Get-Date).ToString('o')
        port = 8780
        local_ip = $ip
        error = $ErrorSummary
    } | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Test-Url([string]$Url, [int]$Timeout = 3) {
    try {
        $result = Invoke-RestMethod -Uri $Url -TimeoutSec $Timeout
        return $null -ne $result
    } catch { return $false }
}

function Wait-Url([string]$Url, [int]$Seconds) {
    $until = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-Url $Url) { return $true }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $until)
    return $false
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not $Mutex.WaitOne(0)) { Write-StartupLog 'Supervisor já está em execução; segunda instância ignorada.'; exit 0 }

try {
    if (-not (Test-Path $Backend)) { throw 'Diretório backend não encontrado.' }
    if (-not (Test-Path (Join-Path $Root '.env'))) { throw 'Arquivo de configuração .env não encontrado.' }
    $Python = if (Test-Path (Join-Path $Root '.venv\Scripts\python.exe')) { Join-Path $Root '.venv\Scripts\python.exe' } else { (Get-Command python -ErrorAction Stop).Source }
    $Ollama = (Get-Command ollama -ErrorAction Stop).Source

    if (-not (Test-Url $OllamaUrl)) {
        Write-StartupLog 'Ollama offline; iniciando serviço local.'
        Start-Process -FilePath $Ollama -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
        if (-not (Wait-Url $OllamaUrl 45)) { throw 'Ollama não respondeu ao health check local.' }
    }
    Write-StartupLog 'Ollama online.'

    do {
        if (Test-Url $HealthUrl) {
            Write-StartupLog 'Jarvis já está online na porta 8780; nenhuma duplicata iniciada.'
            Save-State 'online'
            if ($Once) { break }
            Start-Sleep -Seconds 15
            continue
        }

        $listener = Get-NetTCPConnection -LocalPort 8780 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) { throw "Porta 8780 ocupada por outro processo (PID $($listener.OwningProcess))." }

        Write-StartupLog 'Iniciando backend FastAPI na porta 8780.'
        $process = Start-Process -FilePath $Python -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8780') -WorkingDirectory $Backend -WindowStyle Hidden -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -PassThru
        if (-not (Wait-Url $HealthUrl 45)) {
            if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
            throw 'Backend iniciou, mas o health check não respondeu.'
        }
        Write-StartupLog "Jarvis online; processo $($process.Id), porta 8780, health check OK."
        Save-State 'online'
        if ($Once) { break }
        Wait-Process -Id $process.Id
        Write-StartupLog 'Processo do Jarvis foi encerrado; reinício em 5 segundos.'
        Save-State 'restarting'
        Start-Sleep -Seconds 5
    } while ($true)
} catch {
    $summary = ($_.Exception.Message -replace '[\r\n]+',' ') -replace '(?i)(secret|token|password|senha)\s*[=:]\s*\S+','$1=[protegido]'
    Write-StartupLog "ERRO: $summary"
    Save-State 'error' $summary
    exit 1
} finally {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
