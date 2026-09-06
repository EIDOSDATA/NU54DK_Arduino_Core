param([string[]]$Cases)
$ErrorActionPreference = 'Stop'
$caseWork = 'C:\Users\eidos\Documents\Codex\2026-09-06\new-chat\work\t09-connected'
foreach ($case in $Cases)
{
    $parts = $case.Split('-')
    if ($parts.Length -ne 2) { throw 'Invalid case name' }
    $logPath = Join-Path $caseWork ($case + '-373d98d.log')
    if (Test-Path -LiteralPath $logPath) { throw 'Existing attempt is immutable' }
    & 'C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe' -B -u (Join-Path $caseWork 'run_case.py') $parts[0] $parts[1] *> $logPath
    $caseExit = $LASTEXITCODE
    Get-Content -LiteralPath $logPath -Tail 3
    if ($caseExit -ne 0) { exit $caseExit }
}
