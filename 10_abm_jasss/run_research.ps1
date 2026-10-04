param(
    [ValidateSet('test','s0','validate','compare','s1','validate-s1','compare-s1')][string]$Mode = 'test',
    [string]$PythonPath = '',
    [string]$Output = '',
    [string]$CompareWith = '',
    [int]$Workers = 2
)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) { $PythonPath = $bundledPython }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
Push-Location $PSScriptRoot
try {
    switch ($Mode) {
        'test' { & $PythonPath -B -m unittest discover -s tests -v }
        's0' {
            if (-not $Output) { $Output = 'outputs/research_s0_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') }
            & $PythonPath -B -m abm_jasss.research_cli --config configs/research_s0.json --output $Output --workers $Workers
        }
        'validate' {
            if (-not $Output) { throw 'Supply the existing research output path with -Output.' }
            & $PythonPath -B scripts/validate_research_outputs.py $Output
        }
        'compare' {
            if (-not $Output -or -not $CompareWith) { throw 'Supply both existing outputs with -Output and -CompareWith.' }
            & $PythonPath -B scripts/compare_research_outputs.py $Output $CompareWith
        }
        's1' {
            if (-not $Output) { $Output = 'outputs/research_s1_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') }
            & $PythonPath -B -m abm_jasss.research_s1_cli --config configs/research_s1.json --output $Output --workers $Workers
        }
        'validate-s1' {
            if (-not $Output) { throw 'Supply the existing S1 output path with -Output.' }
            & $PythonPath -B scripts/validate_s1_outputs.py $Output
        }
        'compare-s1' {
            if (-not $Output -or -not $CompareWith) { throw 'Supply both S1 outputs with -Output and -CompareWith.' }
            & $PythonPath -B scripts/validate_s1_outputs.py $Output --compare $CompareWith
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Research command failed with exit code $LASTEXITCODE" }
}
finally { Pop-Location }
