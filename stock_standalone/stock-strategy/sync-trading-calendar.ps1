[CmdletBinding()]
param(
    [string]$CalendarPath = (Join-Path $PSScriptRoot 'source/easy-stock-service/trading-calendar.json'),
    [string]$Server = '192.168.50.60'
)

$ErrorActionPreference = 'Stop'

if ($Server -notmatch '^[A-Za-z0-9.-]+$') {
    throw 'Server must be an IP address or DNS name.'
}
$calendarPath = (Resolve-Path -LiteralPath $CalendarPath).Path
$calendar = Get-Content -LiteralPath $calendarPath -Raw | ConvertFrom-Json
if ($calendar.schema_version -ne 1 -or $null -eq $calendar.markets) {
    throw 'Trading calendar JSON has an unsupported schema.'
}

$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -ErrorAction Stop).Source
$target = "root@$Server"
$remoteName = 'stockstrategy-calendar-' + [Guid]::NewGuid().ToString('N') + '.json'
$remoteTmp = "/tmp/$remoteName"

Write-Host "Uploading the local trading calendar to $target. Enter the SSH password when prompted."
& $scp -o HostKeyAlgorithms=ecdsa-sha2-nistp256 -o ConnectTimeout=15 -o ServerAliveInterval=30 `
    $calendarPath ($target + ':' + $remoteTmp)
if ($LASTEXITCODE -ne 0) {
    throw "Calendar upload failed (exit $LASTEXITCODE)."
}

$remoteCommand = @'
set -eu
source=/tmp/REMOTE_NAME
target=/mnt/4TB/dockerf/stockstrategy/config/trading-calendar.json
test -d "$(dirname "$target")"
temporary="$(dirname "$target")/.trading-calendar.json.$$"
install -m 0644 "$source" "$temporary"
mv -f "$temporary" "$target"
rm -f "$source"
printf 'Calendar synchronized: %s\n' "$target"
'@
$remoteCommand = $remoteCommand.Replace('REMOTE_NAME', $remoteName)
& $ssh -o HostKeyAlgorithms=ecdsa-sha2-nistp256 -o ConnectTimeout=15 -o ServerAliveInterval=30 $target $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote calendar synchronization failed (exit $LASTEXITCODE)."
}

Write-Host 'The API reloads the calendar when the file changes; no container restart is needed.'
