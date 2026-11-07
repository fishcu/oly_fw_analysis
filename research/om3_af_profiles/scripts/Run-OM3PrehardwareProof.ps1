$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
$previousJavaHome = $env:JAVA_HOME
$env:JAVA_HOME = Join-Path $researchRoot 'tooling\jdk-25.0.5+8'
$proofOutput = Join-Path $researchRoot 'analysis\button-af\prehardware'
$proofLog = Join-Path $proofOutput ('prehardware-suite-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '.log')
$headlessArguments = @((Join-Path $researchRoot 'ghidra-projects'), 'OM3_main_full', '-process', '*', '-noanalysis', '-readOnly', '-scriptPath', $PSScriptRoot)
foreach ($scriptName in @('OM3RecoveryAudit','OM3RevisionChecks','OM3RevisionCoverage','OM3AdmissionOrdering','OM3TargetSizeProof','OM3PrehardwareContracts','OM3WakeBeforeAudit','OM3WakeAudit','OM3PackedRelocation','OM3ShootingContinuation','OM3ShootingRuntime','OM3HumanWindows')) {
    $headlessArguments += @('-postScript', ($scriptName + '.java'), $proofOutput)
}
$headlessArguments += @('-log', $proofLog)
Push-Location $researchRoot
try {
    & (Join-Path $researchRoot 'tooling\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat') @headlessArguments
    if ($LASTEXITCODE -ne 0) { throw "Headless process failed: $LASTEXITCODE" }
    foreach ($pythonScript in @('audit_om3_prehardware.py','audit_om3_packed_container.py')) {
        & python -X utf8 (Join-Path $PSScriptRoot $pythonScript)
        if ($LASTEXITCODE -ne 0) { throw "Audit failed: $pythonScript" }
    }
    & python -X utf8 (Join-Path $PSScriptRoot 'validate_om3_prehardware.py') --log $proofLog
    if ($LASTEXITCODE -ne 0) { throw 'Prehardware validation failed.' }
    Copy-Item -LiteralPath $proofLog -Destination (Join-Path $proofOutput 'prehardware-verified-run.log')
} finally {
    Pop-Location
    $env:JAVA_HOME = $previousJavaHome
}
