# Repeatable offline execution only. Never connects to a camera or emits an SD update.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
Push-Location $taskRoot
try {
    $env:JAVA_HOME = Join-Path $taskRoot 'tooling/jdk-25.0.5+8'
    $proofRoot = 'analysis/button-af/readiness'
    $runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $runRoot = "$proofRoot/live-runs/$runStamp"
    New-Item -ItemType Directory -Force $runRoot | Out-Null
    $sources = Get-ChildItem scripts/OM3*.java, scripts/*om3_live*.py, scripts/run_om3_live_offline.ps1
    $before = @{}
    foreach ($source in $sources) { $before[$source.Name] = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    $before | ConvertTo-Json | Set-Content "$runRoot/source-hashes-before.json"
    $phaseOne = @(
        'ghidra-projects', 'OM3_main_full', '-process', '*', '-noanalysis', '-readOnly', '-scriptPath', 'scripts',
        '-postScript', 'OM3CoreRAMSettingsProof.java', "$proofRoot/integration",
        '-postScript', 'OM3LiveProfiles.java', "$proofRoot/live-profiles",
        '-postScript', 'OM3LiveShooting.java', "$proofRoot/live-shooting",
        '-postScript', 'OM3LiveShootingErrors.java', "$proofRoot/live-shooting-errors",
        '-postScript', 'OM3LiveDispatch.java', "$proofRoot/live-dispatch",
        '-postScript', 'OM3ReceiverStartupProof.java', "$proofRoot/receiver-startup",
        '-postScript', 'OM3StockReceiverControl.java', "$proofRoot/stock-receiver-control",
        '-postScript', 'OM3CaptureConnectedProof.java', "$proofRoot/capture-connected",
        '-postScript', 'OM3NativeCodecProof.java', "$proofRoot/live-component",
        '-postScript', 'OM3MutexOwnershipProof.java', "$proofRoot/live-component",
        '-log', "$runRoot/phase-one.log"
    )
    & tooling/ghidra_12.2_PUBLIC/support/analyzeHeadless.bat @phaseOne
    if ($LASTEXITCODE -ne 0) { throw 'Headless phase one process failed' }
    if (Select-String -Quiet -Path "$runRoot/phase-one.log" -Pattern 'SCRIPT ERROR|Error running script|WARN.*Uninitialized memory') { throw 'Headless phase one script or unprovided-memory failure' }
    python scripts/audit_om3_live_package.py
    if ($LASTEXITCODE -ne 0) { throw 'Host integrated package audit failed' }
    python scripts/check_om3_live_diff.py
    if ($LASTEXITCODE -ne 0) { throw 'Integrated byte-range audit failed' }
    & tooling/ghidra_12.2_PUBLIC/support/analyzeHeadless.bat ghidra-projects OM3_main_full -process '*' -noanalysis -readOnly -scriptPath scripts -postScript OM3FullComponentProof.java "$proofRoot/live-component" integrated -log "$runRoot/phase-two.log"
    if ($LASTEXITCODE -ne 0) { throw 'Headless phase two process failed' }
    if (Select-String -Quiet -Path "$runRoot/phase-two.log" -Pattern 'SCRIPT ERROR|Error running script|WARN.*Uninitialized memory') { throw 'Headless phase two script or unprovided-memory failure' }
    foreach ($source in $sources) { if ((Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $before[$source.Name]) { throw "Source changed during proof run: $($source.Name)" } }
    python scripts/verify_om3_live_evidence.py $runRoot
    if ($LASTEXITCODE -ne 0) { throw 'Evidence verification failed' }
} finally { Pop-Location }
