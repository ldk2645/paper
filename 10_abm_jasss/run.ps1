param(
    [ValidateSet('test','pilot','suite','feedback','core','core-suite')][string]$Mode = 'test',
    [string]$PythonPath = '',
    [int]$Workers = 2
)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) { $PythonPath = $bundledPython }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
$runStamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
Push-Location $PSScriptRoot
try {
    switch ($Mode) {
        'test' { & $PythonPath -m unittest discover -s tests -v }
        'pilot' { & $PythonPath -m abm_jasss.cli --config configs/pilot.json --output "outputs/pilot_$runStamp" --workers $Workers }
        'suite' { & $PythonPath scripts/run_pilot_suite.py --output "outputs/suite_$runStamp" --workers $Workers }
        'feedback' { & $PythonPath -m abm_jasss.cli --config configs/smoke_feedback.json --output "outputs/feedback_$runStamp" --workers $Workers }
        'core' { & $PythonPath -m abm_jasss.cli --config configs/restored_core.json --output "outputs/core_$runStamp" --workers $Workers }
        'core-suite' { & $PythonPath scripts/run_core_suite.py --output "outputs/core_suite_$runStamp" --workers $Workers }
    }
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}
finally { Pop-Location }
