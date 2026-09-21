$ErrorActionPreference = 'Continue'
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsArchitecture, CsTotalPhysicalMemory, CsNumberOfLogicalProcessors
Get-Volume | Select-Object DriveLetter, Size, SizeRemaining
Write-Output "PUBLIC IP: $((Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 10))"
Get-NetTCPConnection -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess
docker --version
docker compose version
python --version
psql --version
