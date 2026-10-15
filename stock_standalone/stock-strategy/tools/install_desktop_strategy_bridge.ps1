[CmdletBinding()]
param([string]$Backend = 'http://192.168.50.60:20073')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'Existing pythonw.exe is required; no runtime is installed automatically.' }
$runtime = Join-Path $root 'logs\desktop-strategy-live'
$script = Join-Path $PSScriptRoot 'run_desktop_strategy_bridge.py'
& $python $script --backend $Backend --runtime $runtime --prepare-only
if ($LASTEXITCODE -ne 0) { throw 'Desktop strategy bridge preflight failed.' }
$taskName = 'StockStrategy-CodexATSBridge'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --backend "{1}" --runtime "{2}"' -f $script,$Backend,$runtime) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.State -eq 'Running') { throw 'Existing desktop bridge is running; stop it deliberately before replacing its task definition.' }
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Private HMAC IPC and paper-only Codex/ATS strategy research' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
