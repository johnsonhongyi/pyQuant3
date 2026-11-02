param(
    [Parameter(Mandatory = $true)][int]$TkProcessId,
    [Parameter(Mandatory = $true)][int]$AtsProcessId,
    [ValidateRange(2, 3600)][int]$DurationSeconds = 30,
    [ValidateRange(1, 60)][int]$IntervalSeconds = 1
)

# Run under the same workload for each comparison; no process is modified.
$ErrorActionPreference = 'Stop'
$targets = @(@{ role = 'TK'; id = $TkProcessId }, @{ role = 'ATS'; id = $AtsProcessId })
$previous = @{}
$samples = [System.Collections.Generic.List[object]]::new()
$started = [System.Diagnostics.Stopwatch]::StartNew()
$processorCount = [Environment]::ProcessorCount
while ($started.Elapsed.TotalSeconds -le $DurationSeconds) {
    foreach ($target in $targets) {
        try {
            $process = Get-Process -Id $target.id -ErrorAction Stop
            $elapsed = $started.Elapsed.TotalSeconds
            $key = $target.role
            $cpuPercent = $null
            if ($previous.ContainsKey($key)) {
                $dt = $elapsed - $previous[$key].elapsed
                if ($dt -gt 0) {
                    $cpuPercent = [Math]::Round(100 * ($process.CPU - $previous[$key].cpu) / $dt / $processorCount, 2)
                }
            }
            $previous[$key] = @{ elapsed = $elapsed; cpu = $process.CPU }
            $samples.Add([pscustomobject]@{
                role = $key; pid = $process.Id; name = $process.ProcessName
                elapsed_seconds = [Math]::Round($elapsed, 3); cpu_percent_total_capacity = $cpuPercent
                private_bytes = $process.PrivateMemorySize64; started = $process.StartTime.ToString('o')
                executable = $process.Path; error = $null
            })
        } catch {
            $samples.Add([pscustomobject]@{ role = $target.role; pid = $target.id; error = $_.Exception.Message })
            $previous.Remove($target.role)
        }
    }
    if ($started.Elapsed.TotalSeconds + $IntervalSeconds -gt $DurationSeconds) { break }
    Start-Sleep -Seconds $IntervalSeconds
}
[pscustomobject]@{
    sampled_at = (Get-Date).ToString('o'); duration_seconds = $started.Elapsed.TotalSeconds
    logical_processors = $processorCount; samples = $samples.ToArray()
} | ConvertTo-Json -Depth 5
