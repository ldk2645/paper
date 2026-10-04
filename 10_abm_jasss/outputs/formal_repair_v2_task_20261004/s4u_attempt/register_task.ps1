$ErrorActionPreference = 'Stop'
function Get-TaskSha256 {
    param([string]$LiteralPath)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $inputStream = [System.IO.File]::OpenRead($LiteralPath)
    try { return ([System.BitConverter]::ToString($algorithm.ComputeHash($inputStream))).Replace('-', '').ToLowerInvariant() }
    finally { $inputStream.Dispose(); $algorithm.Dispose() }
}
$taskDirectory = $PSScriptRoot
$configuration = Get-Content -LiteralPath (Join-Path $taskDirectory 'task_configuration.json') -Raw | ConvertFrom-Json
$taskName = $configuration.task_name
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Task name already exists; inspect before retrying' }
if (Test-Path -LiteralPath (Join-Path $taskDirectory 'registration.json')) { throw 'Task registration evidence already exists' }
if ((Get-TaskSha256 -LiteralPath $configuration.wrapper) -ne $configuration.wrapper_sha256) { throw 'Retry wrapper changed' }
if (-not (Test-Path -LiteralPath $configuration.pythonw)) { throw 'Windowless Python is unavailable' }
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$runnerPath = Join-Path $taskDirectory 'run_task.py'
$actionArguments = '-B "' + $runnerPath + '"'
$taskAction = New-ScheduledTaskAction -Execute $configuration.pythonw -Argument $actionArguments -WorkingDirectory $configuration.root
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType S4U -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$taskDefinition = New-ScheduledTask -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Description 'One manual ABM_JASSS formal recovery, full validation, frozen analysis and reports. No recurring trigger or automatic retry. Disables itself when finished.'
$registered = Register-ScheduledTask -TaskName $taskName -InputObject $taskDefinition
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $taskDirectory 'registered_task.xml') -Encoding utf8
[pscustomobject]@{task_name=$taskName; registered_at=(Get-Date).ToUniversalTime().ToString('o'); user=$taskUser; logon_type='S4U'; run_level='Limited'; recurring=$false; automatic_retry=$false; wrapper_hash=$configuration.wrapper_sha256; runner_hash=(Get-TaskSha256 -LiteralPath $runnerPath)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskDirectory 'registration.json') -Encoding utf8
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State | ConvertTo-Json
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime,LastTaskResult,NextRunTime | ConvertTo-Json
