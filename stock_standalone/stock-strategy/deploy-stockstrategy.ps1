[CmdletBinding()]
param(
    [string]$SourceRoot = (Join-Path $PSScriptRoot 'source'),
    [string]$Server = '192.168.50.60'
)

$ErrorActionPreference = 'Stop'

if ($Server -notmatch '^[A-Za-z0-9.-]+$') {
    throw 'Server must be an IP address or DNS name.'
}

$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$serviceSource = Join-Path $source 'easy-stock-service'
$webSource = Join-Path $source 'easy-stock-web'
$backendBinary = Join-Path $serviceSource 'bin\easy-stock-backend'
$assetRoot = Join-Path $PSScriptRoot 'docker'

foreach ($path in @($serviceSource, $webSource, $backendBinary, (Join-Path $assetRoot 'install.sh'), (Join-Path $assetRoot 'backend.Dockerfile'), (Join-Path $assetRoot 'web.Dockerfile'), (Join-Path $assetRoot 'nginx.conf'), (Join-Path $assetRoot 'web-entrypoint.sh'))) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required deployment input is missing: $path"
    }
}

$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -ErrorAction Stop).Source
$tar = (Get-Command tar.exe -ErrorAction Stop).Source
$releaseId = Get-Date -Format 'yyyyMMddHHmmss'
$work = Join-Path $env:TEMP ("stockstrategy-deploy-" + $releaseId + '-' + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $work 'payload'
$archiveName = "stockstrategy-$releaseId.tar.gz"
$archive = Join-Path $work $archiveName
$stageName = "stockstrategy-$releaseId"

function Copy-ProjectTree([string]$from, [string]$to, [switch]$SkipServiceState) {
    New-Item -ItemType Directory -Path $to -Force | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $from -Force) {
        if ($SkipServiceState -and $from -eq $serviceSource -and $item.Name -in @('data', 'logs', 'reviews', 'screenshots')) {
            continue
        }
        if ($item.PSIsContainer -and $item.Name -in @('.git', '.venv', 'node_modules', 'dist', 'build', 'target', '__pycache__')) {
            continue
        }
        if (-not $item.PSIsContainer -and $item.Name -in @('.env', 'push_config.json')) {
            continue
        }
        $destination = Join-Path $to $item.Name
        if ($item.PSIsContainer) {
            Copy-ProjectTree -from $item.FullName -to $destination -SkipServiceState:$SkipServiceState
        } else {
            Copy-Item -LiteralPath $item.FullName -Destination $destination
        }
    }
}

try {
    New-Item -ItemType Directory -Path (Join-Path $payload 'docker') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $payload 'initial-service-state') -Force | Out-Null
    Copy-ProjectTree -from $source -to (Join-Path $payload 'source') -SkipServiceState
    Get-ChildItem -LiteralPath $assetRoot -File | Copy-Item -Destination (Join-Path $payload 'docker') -Force
    foreach ($name in @('data', 'logs', 'reviews', 'screenshots')) {
        $statePath = Join-Path $serviceSource $name
        if (Test-Path -LiteralPath $statePath -PathType Container) {
            Copy-ProjectTree -from $statePath -to (Join-Path (Join-Path $payload 'initial-service-state') $name)
        }
    }
    Copy-Item -LiteralPath (Join-Path $assetRoot 'install.sh') -Destination (Join-Path $payload 'install.sh')

    & $tar -czf $archive -C $payload .
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create deployment archive (exit $LASTEXITCODE)."
    }

    $target = "root@$Server"
    Write-Host "Uploading release $releaseId to $target. Enter the SSH password when prompted."
    $remoteArchive = $target + ':/tmp/' + $archiveName
    & $scp -o ConnectTimeout=15 -o ServerAliveInterval=30 $archive $remoteArchive
    if ($LASTEXITCODE -ne 0) {
        throw "SCP upload failed (exit $LASTEXITCODE)."
    }

    $remoteCommand = @'
set -eu
stage=/tmp/STAGE_NAME
archive=/tmp/ARCHIVE_NAME
mkdir -p "$stage"
tar -xzf "$archive" -C "$stage"
set +e
bash "$stage/install.sh"
result=$?
set -e
rm -rf -- "$stage" "$archive"
exit "$result"
'@
    $remoteCommand = $remoteCommand.Replace('STAGE_NAME', $stageName).Replace('ARCHIVE_NAME', $archiveName)
    Write-Host 'Building and starting the Docker containers on the server.'
    & $ssh -o ConnectTimeout=15 -o ServerAliveInterval=30 $target $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Remote Docker deployment failed (exit $LASTEXITCODE)."
    }

    Write-Host 'Deployment completed: http://192.168.50.60:20073'
    Write-Host 'Project files: /root/johnson/stock-strategy'
    Write-Host 'Persistent files: /mnt/4TB/dockerf/stockstrategy/{data,logs,config,app}'
} finally {
    $tempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    $resolvedWork = [System.IO.Path]::GetFullPath($work)
    if ($resolvedWork.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedWork)) {
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}
