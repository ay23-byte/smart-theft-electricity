param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Get-EnvValues {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or $trimmed -notmatch "=") {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -eq 2) {
            $values[$parts[0].Trim()] = $parts[1].Trim()
        }
    }

    return $values
}

function Test-BackendReady {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5000/login" -TimeoutSec 2
        return $response.StatusCode -ge 200
    } catch {
        return $false
    }
}

function Wait-BackendReady {
    param([int]$TimeoutSeconds = 45)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-BackendReady) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

Write-Host "Running deploy preflight..." -ForegroundColor Cyan

$requiredFiles = @(
    "Procfile",
    "backend/app.py",
    "backend/requirements.txt",
    "backend/smoke_test.py",
    "playwright.config.cjs"
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $file))) {
        throw "Required deploy file missing: $file"
    }
}

$envPath = Join-Path $PSScriptRoot "backend/.env"
$envValues = Get-EnvValues -Path $envPath

if ($envValues.Count -eq 0) {
    Write-Host "No backend/.env file was found or it is empty. That is fine for hosted deploys, but make sure Render has the needed env vars." -ForegroundColor Yellow
} else {
    if (-not ($envValues.ContainsKey("FLASK_SECRET_KEY") -or $envValues.ContainsKey("SECRET_KEY"))) {
        Write-Host "Warning: FLASK_SECRET_KEY or SECRET_KEY is missing from backend/.env." -ForegroundColor Yellow
    }
    if (-not $envValues.ContainsKey("CESIUM_ION_TOKEN")) {
        Write-Host "Warning: CESIUM_ION_TOKEN is missing from backend/.env." -ForegroundColor Yellow
    }
    if (($envValues["SMS_ALERTS_ENABLED"] -as [string]) -and $envValues["SMS_ALERTS_ENABLED"].ToLower() -eq "true") {
        foreach ($twilioKey in @("TWILIO_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_FROM", "TWILIO_PHONE_TO")) {
            if (-not $envValues.ContainsKey($twilioKey)) {
                Write-Host "Warning: $twilioKey is missing while SMS_ALERTS_ENABLED=true." -ForegroundColor Yellow
            }
        }
    }
}

Write-Host "Preflight complete. Running full test check..." -ForegroundColor Cyan
if (-not (Test-BackendReady)) {
    Write-Host "Starting local Flask server for the deploy check..." -ForegroundColor Cyan
    $backendStdout = Join-Path $env:TEMP "smarttheft-backend.out.log"
    $backendStderr = Join-Path $env:TEMP "smarttheft-backend.err.log"
    $backendProcess = Start-Process `
        -FilePath "python" `
        -ArgumentList "app.py" `
        -WorkingDirectory (Join-Path $PSScriptRoot "backend") `
        -PassThru `
        -RedirectStandardOutput $backendStdout `
        -RedirectStandardError $backendStderr

    if (-not (Wait-BackendReady)) {
        try { Stop-Process -Id $backendProcess.Id -Force } catch {}
        throw "Backend server did not become ready on http://127.0.0.1:5000."
    }
    $startedBackend = $true
} else {
    $startedBackend = $false
}

try {
    if ($Full) {
        & (Join-Path $PSScriptRoot "run-all-tests.ps1") -Full
    } else {
        & (Join-Path $PSScriptRoot "run-all-tests.ps1")
    }
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    if ($startedBackend -and $backendProcess) {
        try {
            Stop-Process -Id $backendProcess.Id -Force
        } catch {
        }
    }
}

Write-Host "Deploy check completed successfully." -ForegroundColor Green
