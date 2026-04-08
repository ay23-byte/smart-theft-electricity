param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "Running backend smoke tests..." -ForegroundColor Cyan
if ($Full) {
    python backend/smoke_test.py --retrain
} else {
    python backend/smoke_test.py
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "npm was not found, so the browser smoke suite was skipped." -ForegroundColor Yellow
    Write-Host "Install Node.js to run the Playwright browser checks." -ForegroundColor Yellow
    Write-Host "Backend smoke tests completed successfully." -ForegroundColor Green
    exit 0
}

Remove-Item -LiteralPath (Join-Path $PSScriptRoot 'test-results/.last-run.json') -Force -ErrorAction SilentlyContinue

Write-Host "Running browser smoke tests..." -ForegroundColor Cyan
if ($Full) {
    $env:SMART_THEFT_E2E_RETRAIN = "true"
}

npm run test:e2e
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "All tests completed successfully." -ForegroundColor Green
