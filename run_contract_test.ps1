<#
.SYNOPSIS
    run_contract_test.ps1 — Runs the Specmatic contract test against the accounts stub server.

.DESCRIPTION
    Flow:
        1. Start accounts_stub_server.py on port 3000
        2. Wait until the server is ready (health check)
        3. Run Specmatic in TEST mode via Docker
        4. Stop the stub server
        5. Open the HTML report

    Architecture:
        [specmatic/specmatic Docker] ──GET /v1/accounts──▶ [accounts_stub_server.py :3000]
                                           ↓
                              Validates responses vs stripe-accounts-contract.json
                                           ↓
                            Writes report → build/reports/specmatic/accounts/

.EXAMPLE
    # From repo root:
    .\run_contract_test.ps1

.NOTES
    Requirements:
        - Python 3.x in PATH
        - Docker Desktop running
        - Docker image: specmatic/specmatic:2.49.1 (pulled automatically if missing)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$StubPort       = 3000
$StubHost       = "0.0.0.0"
$HealthUrl      = "http://127.0.0.1:$StubPort/health"
$StubScript     = "specmatic_test\accounts_stub_server.py"
$SpecmaticImage = "specmatic/specmatic:2.49.1"
$ConfigFile     = "specmatic-accounts-test.yaml"
$ReportDir      = "build\reports\specmatic"
$MaxWaitSecs    = 15
$TestTimeout    = 30

# ---------------------------------------------------------------------------
# Helper: coloured output
# ---------------------------------------------------------------------------
function Write-Step([string]$msg) { Write-Host "`n▶  $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "✅ $msg" -ForegroundColor Green }
function Write-Err([string]$msg)  { Write-Host "❌ $msg" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# Ensure we're at the repo root
# ---------------------------------------------------------------------------
if (-not (Test-Path $StubScript)) {
    Write-Err "Script must be run from the repository root (airbyte-master)."
    Write-Err "Could not find: $StubScript"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 1 — Start stub server
# ---------------------------------------------------------------------------
Write-Step "Starting accounts stub server on port $StubPort..."

$stubProcess = Start-Process `
    -FilePath "python" `
    -ArgumentList $StubScript, "--port", $StubPort, "--host", $StubHost `
    -PassThru `
    -NoNewWindow

Write-Host "  PID: $($stubProcess.Id)"

# ---------------------------------------------------------------------------
# Step 2 — Wait for stub server to be ready
# ---------------------------------------------------------------------------
Write-Step "Waiting for stub server to be ready..."

$ready = $false
for ($i = 1; $i -le $MaxWaitSecs; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Write-Host "  [$i/$MaxWaitSecs] Waiting..." -ForegroundColor DarkGray
    }
}

if (-not $ready) {
    Write-Err "Stub server failed to start within $MaxWaitSecs seconds."
    Stop-Process -Id $stubProcess.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Ok "Stub server is ready at http://127.0.0.1:$StubPort"

# ---------------------------------------------------------------------------
# Step 3 — Run Specmatic contract test via Docker
# ---------------------------------------------------------------------------
Write-Step "Running Specmatic contract test (Docker)..."
Write-Host "  Image  : $SpecmaticImage"
Write-Host "  Config : $ConfigFile"
Write-Host "  Target : host.docker.internal:$StubPort"
Write-Host "  Report : $ReportDir"
Write-Host ""

# Ensure report output directory exists
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$dockerArgs = @(
    "run", "--rm",
    "-v", "${PWD}:/usr/src/app",
    "-v", "$env:USERPROFILE/.specmatic:/root/.specmatic",
    "-w", "/usr/src/app",
    $SpecmaticImage,
    "test",
    "--host=host.docker.internal",
    "--port=$StubPort",
    "--config", $ConfigFile,
    "--timeout=$TestTimeout",
    "--junitReportDir=build/reports/specmatic/junit"
)

Write-Host "  Command: docker $($dockerArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""

$testExitCode = 0
try {
    & docker @dockerArgs
    $testExitCode = $LASTEXITCODE
} catch {
    Write-Err "Docker command failed: $_"
    $testExitCode = 1
}

# Convert JUnit XML to CTRF JSON locally if npx is available
if ($testExitCode -eq 0 -and (Get-Command npx -ErrorAction SilentlyContinue)) {
    Write-Step "Converting JUnit XML report to CTRF JSON format..."
    npx junit-to-ctrf build/reports/specmatic/junit/*.xml --output build/reports/specmatic/ctrf-report.json
}

# ---------------------------------------------------------------------------
# Step 4 — Stop stub server
# ---------------------------------------------------------------------------
Write-Step "Stopping stub server (PID $($stubProcess.Id))..."
Stop-Process -Id $stubProcess.Id -Force -ErrorAction SilentlyContinue
Write-Ok "Stub server stopped."

# ---------------------------------------------------------------------------
# Step 5 — Open report
# ---------------------------------------------------------------------------
Write-Step "Looking for HTML report..."

$htmlReport = Get-ChildItem -Path $ReportDir -Filter "*.html" -Recurse -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending |
              Select-Object -First 1

if ($htmlReport) {
    Write-Ok "Report generated: $($htmlReport.FullName)"
    Write-Host "  Opening report in browser..." -ForegroundColor Cyan
    Start-Process $htmlReport.FullName
} else {
    Write-Host "  ⚠️  No HTML report found in $ReportDir" -ForegroundColor Yellow
    Write-Host "     Check build/reports/specmatic/accounts/ for CTRF JSON report." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------
Write-Host ""
if ($testExitCode -eq 0) {
    Write-Ok "Contract test PASSED -- all responses matched the spec."
} else {
    Write-Err "Contract test FAILED (exit code: $testExitCode) -- see report for details."
}

exit $testExitCode
