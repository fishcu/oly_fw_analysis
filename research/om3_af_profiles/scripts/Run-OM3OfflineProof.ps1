$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
$previousJavaHome = $env:JAVA_HOME
$env:JAVA_HOME = Join-Path $researchRoot 'tooling\jdk-25.0.5+8'
$proofOutput = Join-Path $researchRoot 'analysis\button-af\closure'
$proofLog = Join-Path $proofOutput ('offline-suite-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '.log')
Push-Location $researchRoot
try {
    & (Join-Path $researchRoot 'tooling\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat') (Join-Path $researchRoot 'ghidra-projects') OM3_main_full -process '*' -noanalysis -readOnly -scriptPath $PSScriptRoot -postScript OM3OfflineSuite.java $proofOutput -log $proofLog
    if ($LASTEXITCODE -ne 0) { throw "Headless process failed: $LASTEXITCODE" }
    & python -X utf8 (Join-Path $PSScriptRoot 'validate_offline_af_proof.py') --log $proofLog
    if ($LASTEXITCODE -ne 0) { throw 'Proof validation failed; no success manifest was accepted.' }
    Copy-Item -LiteralPath $proofLog -Destination (Join-Path $proofOutput 'offline-suite-verified-run.log')
} finally {
    Pop-Location
    $env:JAVA_HOME = $previousJavaHome
}
