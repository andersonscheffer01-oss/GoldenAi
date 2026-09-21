param(
    [switch]$FirstOnly
)

$ignoredAdapters = 'Loopback|vEthernet|Hyper-V|Docker|WSL|VPN|Tailscale|ZeroTier|VirtualBox|VMware'

$addresses = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
    Where-Object {
        $_.NetAdapter.Status -eq 'Up' -and
        $_.InterfaceAlias -notmatch $ignoredAdapters -and
        $_.IPv4Address
    } |
    ForEach-Object {
        $hasGateway = [bool]$_.IPv4DefaultGateway
        foreach ($address in $_.IPv4Address.IPAddress) {
            if ($address -match '^10\.' -or
                $address -match '^192\.168\.' -or
                $address -match '^172\.(1[6-9]|2[0-9]|3[01])\.') {
                [pscustomobject]@{
                    Address = $address
                    HasGateway = $hasGateway
                    InterfaceIndex = $_.InterfaceIndex
                }
            }
        }
    } |
    Sort-Object @{ Expression = 'HasGateway'; Descending = $true }, InterfaceIndex, Address |
    Select-Object -ExpandProperty Address -Unique

if ($FirstOnly) {
    $addresses | Select-Object -First 1
} else {
    $addresses
}
