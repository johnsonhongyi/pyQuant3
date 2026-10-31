# Use the updating managed engine without changing shared daemon settings.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CodexArguments)

$ErrorActionPreference = 'Stop'
$taskCodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$taskCandidates = @(
    (Join-Path $taskCodexHome 'packages\app-server-daemon\current\bin\codex.exe'),
    (Join-Path $taskCodexHome 'packages\standalone\current\bin\codex.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\OpenAI\Codex\bin\codex.exe')
)
$taskAvailable = foreach ($taskCandidate in $taskCandidates) {
    if (-not (Test-Path -LiteralPath $taskCandidate -PathType Leaf)) { continue }
    $taskVersion = [version]'0.0.0'
    $taskCurrentDir = Split-Path (Split-Path $taskCandidate -Parent) -Parent
    $taskCurrent = Get-Item -LiteralPath $taskCurrentDir
    if ($taskCurrent.Target) {
        $taskReleaseName = Split-Path ([string]$taskCurrent.Target) -Leaf
        if ($taskReleaseName -match '^(\d+\.\d+\.\d+)-x86_64-pc-windows-msvc$') { $taskVersion = [version]$Matches[1] }
    }
    [PSCustomObject]@{ Engine=$taskCandidate; Version=$taskVersion; Priority=[array]::IndexOf($taskCandidates,$taskCandidate) }
}
$taskEngine = ($taskAvailable | Sort-Object @{Expression='Version';Descending=$true},Priority | Select-Object -First 1).Engine
if (-not $taskEngine) { throw 'Codex engine not found. Install Codex before launching.' }

& $taskEngine --no-daemon @CodexArguments
exit $LASTEXITCODE
