# Remove only inactive older releases; never touch desktop app resources.
$ErrorActionPreference = 'Stop'
$taskCodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
foreach ($taskPackage in @('standalone', 'app-server-daemon')) {
    $taskPackageRoot = Join-Path $taskCodexHome "packages\$taskPackage"
    $taskCurrent = Get-Item -LiteralPath (Join-Path $taskPackageRoot 'current')
    if ($taskCurrent.LinkType -ne 'Junction' -or -not $taskCurrent.Target) {
        throw "Cannot validate current release for $taskPackage"
    }
    $taskCurrentPath = [IO.Path]::GetFullPath([string]$taskCurrent.Target).TrimEnd('\')
    $taskCurrentName = Split-Path $taskCurrentPath -Leaf
    if ($taskCurrentName -notmatch '^(\d+\.\d+\.\d+)-x86_64-pc-windows-msvc$') {
        throw "Unrecognized current release: $taskCurrentName"
    }
    $taskCurrentVersion = [version]$Matches[1]
    $taskReleaseRoot = [IO.Path]::GetFullPath((Join-Path $taskPackageRoot 'releases')).TrimEnd('\')
    foreach ($taskRelease in Get-ChildItem -LiteralPath $taskReleaseRoot -Directory) {
        if ($taskRelease.Name -notmatch '^(\d+\.\d+\.\d+)-x86_64-pc-windows-msvc$') { continue }
        if ([version]$Matches[1] -ge $taskCurrentVersion) { continue }
        $taskTarget = [IO.Path]::GetFullPath($taskRelease.FullName).TrimEnd('\')
        if ($taskRelease.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing linked release: $taskTarget" }
        if ((Split-Path $taskTarget -Parent) -ne $taskReleaseRoot -or $taskTarget -eq $taskCurrentPath) {
            throw "Refusing target outside the inactive release boundary: $taskTarget"
        }
        # Re-read owners before each delete. Failure to enumerate stops cleanup.
        $taskOwners = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($taskTarget + '\', [StringComparison]::OrdinalIgnoreCase)
        })
        if ($taskOwners.Count) { Write-Output "Skipped active release: $taskTarget"; continue }
        Remove-Item -LiteralPath $taskTarget -Recurse -Force
        Write-Output "Removed inactive release: $taskTarget"
    }
}
