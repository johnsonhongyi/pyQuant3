[CmdletBinding()]
param([string]$Server = '192.168.50.60')

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$sourceRoot = Join-Path $projectRoot 'source'
$backendRoot = Join-Path $sourceRoot 'easy-stock-analysis\backend'
$webRoot = Join-Path $sourceRoot 'easy-stock-web'
$deployHelper = Join-Path $projectRoot 'docker\deploy-prebuilt.sh'
$expectedFingerprint = 'SHA256:H4t+8TqzvkFssky/qlmhXJTH9QGUS3KfxEbszc1ZEM8'
$releaseId = Get-Date -Format 'yyyyMMddHHmmss'
$target = "root@$Server"
$remoteStage = "/root/johnson/stock-strategy/.build-staging/$releaseId"
$cacheRoot = Join-Path $projectRoot '.build-cache'
$work = Join-Path $env:TEMP ("stockstrategy-build-$releaseId-" + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $work 'payload'
$archive = Join-Path $work "stockstrategy-$releaseId.tar.gz"
$knownHosts = Join-Path $work 'known_hosts'
$sshOptions = @()
$remoteStageCreated = $false
$envNames = @('GOTOOLCHAIN','GOMAXPROCS','GOGC','GOMEMLIMIT','GOCACHE','GOMODCACHE','GOPROXY','GOOS','GOARCH','CGO_ENABLED','NODE_OPTIONS','NPM_CONFIG_CACHE','VITE_A_STOCK_TOKEN')
$oldEnv = @{}
foreach ($name in $envNames) { $oldEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

function Invoke-CheckedNative([string]$File, [string[]]$Arguments, [string]$Description) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit $LASTEXITCODE)." }
}

function Get-GoTool([string]$GoMinor, [string]$CacheRoot) {
    $toolsRoot = Join-Path $CacheRoot 'tools'
    $cached = Get-ChildItem -LiteralPath $toolsRoot -Directory -Filter "go$GoMinor*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'bin\go.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($cached) {
        $versionText = (& $cached version 2>$null | Out-String).Trim()
        if ($versionText -match "\bgo$([regex]::Escape($GoMinor))\.\d+\b") { return $cached }
    }

    Write-Host "Downloading the official Go $GoMinor Windows toolchain..."
    $releaseList = Invoke-RestMethod -Uri 'https://go.dev/dl/?mode=json&include=all' -TimeoutSec 45
    $release = $releaseList | Where-Object { $_.version -match "^go$([regex]::Escape($GoMinor))\.\d+$" } |
        Sort-Object { [version]($_.version -replace '^go', '') } -Descending | Select-Object -First 1
    if (-not $release) { throw "go.dev has no stable Go $GoMinor release matching go.mod." }
    $asset = $release.files | Where-Object { $_.filename -eq "$($release.version).windows-amd64.zip" } | Select-Object -First 1
    if (-not $asset) { throw "Official Windows amd64 archive is missing for $($release.version)." }
    $null = New-Item -ItemType Directory -Path $toolsRoot -Force
    $zipPath = Join-Path $CacheRoot $asset.filename
    Invoke-WebRequest -Uri "https://go.dev/dl/$($asset.filename)" -OutFile $zipPath -TimeoutSec 180
    if ((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256.ToLowerInvariant()) {
        throw 'Go archive SHA256 verification failed.'
    }
    $extractRoot = Join-Path $CacheRoot ("extract-" + [Guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $installRoot = Join-Path $toolsRoot $release.version
    if (Test-Path -LiteralPath $installRoot) { Remove-Item -LiteralPath $installRoot -Recurse -Force }
    Move-Item -LiteralPath (Join-Path $extractRoot 'go') -Destination $installRoot
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
    return (Join-Path $installRoot 'bin\go.exe')
}

function Test-ExcludedSourceFile([string]$Path) {
    $lower = $Path.ToLowerInvariant()
    if (($lower -split '/') | Where-Object { $_ -in @('.git','.venv','node_modules','dist','build','target','__pycache__') }) { return $true }
    if ($lower -match '^easy-stock-service/(data|logs|reviews|screenshots)(/|$)') { return $true }
    $leaf = [System.IO.Path]::GetFileName($Path).ToLowerInvariant()
    if ($leaf -in @('.env','push_config.json','credentials.json','secrets.json')) { return $true }
    if ($leaf -match '^\.env\.' -and $leaf -notmatch '\.(example|sample|template)$') { return $true }
    if ($Path -match '\.(db|sqlite|sqlite3|db-wal|db-shm|log|jsonl|parquet|h5|csv|png|jpe?g|gif|webp|mp4|zip|gz)$') { return $true }
    return $false
}

if ($Server -notmatch '^[A-Za-z0-9.-]+$') { throw 'Server must be an IP address or DNS name.' }
foreach ($path in @($backendRoot,$webRoot,$deployHelper,(Join-Path $backendRoot 'go.mod'),(Join-Path $webRoot 'package-lock.json'))) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required build input is missing: $path" }
}
$git = (Get-Command git.exe -ErrorAction Stop).Source
$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$scp = (Get-Command scp.exe -ErrorAction Stop).Source
$sshKeyscan = (Get-Command ssh-keyscan.exe -ErrorAction Stop).Source
$sshKeygen = (Get-Command ssh-keygen.exe -ErrorAction Stop).Source
$tar = (Get-Command tar.exe -ErrorAction Stop).Source
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$node = (Get-Command node.exe -ErrorAction Stop).Source
$gitRoot = (& $git -C $sourceRoot rev-parse --show-toplevel | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [System.IO.Path]::GetFullPath($gitRoot) -ne [System.IO.Path]::GetFullPath($sourceRoot)) {
    throw 'The source directory is not the expected Git root.'
}

try {
    $null = New-Item -ItemType Directory -Path $work,$cacheRoot -Force
    Write-Host "Checking pinned SSH identity for $Server..."
    $keys = & $sshKeyscan -T 10 -t ed25519 $Server 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $keys) { throw 'Could not read the server ED25519 host key.' }
    $key = $keys | Where-Object { $_ -and $_ -notmatch '^#' } | Select-Object -First 1
    Set-Content -LiteralPath $knownHosts -Value $key -Encoding utf8NoBOM
    $keyInfo = (& $sshKeygen -lf $knownHosts -E sha256 2>$null | Out-String)
    $fingerprint = [regex]::Match($keyInfo, 'SHA256:[A-Za-z0-9+/=]+').Value
    if ($fingerprint -ne $expectedFingerprint) { throw 'Server SSH identity differs from the approved ED25519 fingerprint.' }
    $sshOptions = @('-o',"UserKnownHostsFile=$knownHosts",'-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-o','BatchMode=yes')

    Write-Host 'Checking server health and available storage...'
    $preflight = @(
        'set -eu',
        'PROJECT=/root/johnson/stock-strategy',
        'DATA_ROOT=/mnt/4TB/dockerf/stockstrategy',
        'test -f "$PROJECT/.stockstrategy-managed"',
        'test -f "$DATA_ROOT/.stockstrategy-managed"',
        'mountpoint -q /mnt/4TB',
        'docker info >/dev/null',
        'test "$(docker inspect --format ''{{.State.Health.Status}}'' stockstrategy-api)" = healthy',
        'test "$(docker inspect --format ''{{.State.Health.Status}}'' stockstrategy-web)" = healthy',
        'test "$(docker inspect --format ''{{.HostConfig.RestartPolicy.Name}}'' stockstrategy-api)" = always',
        'test "$(docker inspect --format ''{{.HostConfig.RestartPolicy.Name}}'' stockstrategy-web)" = always',
        'available=$(awk ''/MemAvailable:/ {print $2}'' /proc/meminfo)',
        'disk_free=$(df -Pk /mnt/4TB | awk ''END {print $4}'')',
        'docker_root=$(docker info --format ''{{.DockerRootDir}}'')',
        'docker_free=$(df -Pk "$docker_root" | awk ''END {print $4}'')',
        'test "$available" -ge 524288',
        'test "$disk_free" -ge 1048576',
        'test "$docker_free" -ge 1048576',
        'printf ''MEM_AVAILABLE_KB=%s\n'' "$available"',
        'printf ''DATA_FREE_KB=%s\n'' "$disk_free"',
        'printf ''DOCKER_FREE_KB=%s\n'' "$docker_free"',
        'printf ''A_STOCK_TOKEN=''',
        'awk -F= ''$1 == "A_STOCK_TOKEN" {sub(/^[^=]*=/, ""); print; exit}'' "$DATA_ROOT/config/backend.env"'
    ) -join [char]10
    $preflightLines = & $ssh @sshOptions $target $preflight
    if ($LASTEXITCODE -ne 0) { throw 'Remote preflight failed; no build or deployment changes were made.' }
    $tokenLines = @($preflightLines | Where-Object { $_ -like 'A_STOCK_TOKEN=*' })
    if ($tokenLines.Count -ne 1) { throw 'Could not read the API token setting from the server.' }
    $apiToken = ([string]$tokenLines[0]).Substring('A_STOCK_TOKEN='.Length)
    if ($apiToken -match '[\r\n]') { throw 'The API token contains an unsupported line break.' }
    $preflightLines | Where-Object { $_ -notlike 'A_STOCK_TOKEN=*' } | ForEach-Object { Write-Host $_ }

    $nodeVersion = (& $node --version | Out-String).Trim()
    Write-Host "Building locally with Node $nodeVersion; compile processes run synchronously."
    $goMatch = [regex]::Match((Get-Content -LiteralPath (Join-Path $backendRoot 'go.mod') -Raw), '(?m)^\s*go\s+(\d+\.\d+)')
    if (-not $goMatch.Success) { throw 'Could not read Go version from go.mod.' }
    $goMinor = $goMatch.Groups[1].Value
    $go = Get-GoTool -GoMinor $goMinor -CacheRoot $cacheRoot
    $goText = (& $go version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $goText -notmatch "\bgo$([regex]::Escape($goMinor))\.\d+\b") { throw "Expected Go $goMinor; got '$goText'." }

    $env:GOTOOLCHAIN = 'local'; $env:GOMAXPROCS = '10'; $env:GOGC = '100'; $env:GOMEMLIMIT = '8GiB'
    $env:GOCACHE = Join-Path $cacheRoot 'go-build-cache'; $env:GOMODCACHE = Join-Path $cacheRoot 'go-mod-cache'
    $env:GOPROXY = 'https://goproxy.cn|https://proxy.golang.org|direct'; $env:GOOS = 'linux'; $env:GOARCH = 'amd64'; $env:CGO_ENABLED = '0'
    $null = New-Item -ItemType Directory -Path $env:GOCACHE,$env:GOMODCACHE -Force
    $backendOutput = Join-Path $work 'easy-stock-backend'
    Push-Location $backendRoot
    try {
        Invoke-CheckedNative -File $go -Arguments @('build','-p=10','-trimpath','-buildvcs=false','-ldflags=-s -w','-o',$backendOutput,'./cmd/server') -Description 'Local Go backend build'
    } finally { Pop-Location }
    if (-not (Test-Path -LiteralPath $backendOutput) -or (Get-Item -LiteralPath $backendOutput).Length -lt 1MB) { throw 'Backend build output is missing or unexpectedly small.' }

    $env:NODE_OPTIONS = '--max-old-space-size=4096'
    $env:NPM_CONFIG_CACHE = Join-Path $cacheRoot 'npm-cache'
    $env:VITE_A_STOCK_TOKEN = $apiToken
    $null = New-Item -ItemType Directory -Path $env:NPM_CONFIG_CACHE -Force
    Push-Location $webRoot
    try {
        Invoke-CheckedNative -File $npm -Arguments @('ci','--prefer-offline','--no-audit','--no-fund') -Description 'Frontend dependency restore'
        Invoke-CheckedNative -File $npm -Arguments @('run','build') -Description 'Local frontend build'
    } finally { Pop-Location }
    $webDist = Join-Path $webRoot 'dist'
    if (-not (Test-Path -LiteralPath (Join-Path $webDist 'index.html'))) { throw 'Frontend build did not produce dist/index.html.' }
    [Environment]::SetEnvironmentVariable('VITE_A_STOCK_TOKEN', $null, 'Process')

    Write-Host 'Preparing source sync package (local data, logs, reviews, screenshots, and secrets excluded)...'
    $null = New-Item -ItemType Directory -Path (Join-Path $payload 'backend'),(Join-Path $payload 'web-dist'),(Join-Path $payload 'source') -Force
    Copy-Item -LiteralPath $backendOutput -Destination (Join-Path $payload 'backend\easy-stock-backend')
    Get-ChildItem -LiteralPath $webDist -Force | Copy-Item -Destination (Join-Path $payload 'web-dist') -Recurse -Force
    $sourceFiles = & $git -C $sourceRoot ls-files --cached --others --exclude-standard
    if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate project source files.' }
    foreach ($entry in $sourceFiles) {
        $relative = ([string]$entry).Replace('\','/')
        if (-not $relative -or $relative.StartsWith('/') -or $relative -match '(^|/)\.\.?(/|$)' -or (Test-ExcludedSourceFile $relative)) { continue }
        $from = Join-Path $sourceRoot $relative
        if (-not (Test-Path -LiteralPath $from -PathType Leaf)) { continue }
        $to = Join-Path (Join-Path $payload 'source') ($relative.Replace('/','\'))
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $to) -Force
        Copy-Item -LiteralPath $from -Destination $to -Force
    }
    if (-not (Test-Path -LiteralPath (Join-Path $payload 'source\easy-stock-service\trading-calendar.json'))) { throw 'Source calendar was excluded from the package.' }
    Copy-Item -LiteralPath $deployHelper -Destination (Join-Path $payload 'deploy-prebuilt.sh')
    Invoke-CheckedNative -File $tar -Arguments @('-czf',$archive,'-C',$payload,'.') -Description 'Release packaging'

    Write-Host "Uploading release $releaseId to $target..."
    & $ssh @sshOptions $target "mkdir -p '$remoteStage' && chmod 700 '$remoteStage'"
    if ($LASTEXITCODE -ne 0) { throw 'Could not create remote staging directory.' }
    $remoteStageCreated = $true
    $scpOptions = @('-o',"UserKnownHostsFile=$knownHosts",'-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=15')
    Invoke-CheckedNative -File $scp -Arguments ($scpOptions + @($archive,("root@$($Server):$remoteStage/release.tar.gz"))) -Description 'Release upload'

    Write-Host 'Installing the prebuilt release with bounded Docker resource limits...'
    $remoteCommand = 'set +e; tar -xzf "{0}/release.tar.gz" -C "{0}"; result=$?; if [ "$result" -eq 0 ]; then bash "{0}/deploy-prebuilt.sh" "{0}/release.tar.gz" {1}; result=$?; fi; rm -rf -- "{0}"; exit $result' -f $remoteStage,$releaseId
    & $ssh @sshOptions $target $remoteCommand
    $remoteExit = $LASTEXITCODE
    if ($remoteExit -ne 0) { throw "Remote deployment failed (exit $remoteExit); persistent data was retained." }
    $remoteStageCreated = $false
    Write-Host "Completed: http://$($Server):20073 (release $releaseId)."
} finally {
    foreach ($name in $envNames) { [Environment]::SetEnvironmentVariable($name,$oldEnv[$name],'Process') }
    if ($remoteStageCreated -and $remoteStage.StartsWith('/root/johnson/stock-strategy/.build-staging/',[StringComparison]::Ordinal)) {
        & $ssh @sshOptions $target "rm -rf -- '$remoteStage'" 2>$null | Out-Null
    }
    $tempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    $resolvedWork = [System.IO.Path]::GetFullPath($work)
    if ($resolvedWork.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedWork)) {
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}
