param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$environmentFile = Join-Path $projectRoot ".env"
$frontendRoot = Join-Path $projectRoot "frontend"
$npmModules = Join-Path $frontendRoot "node_modules"
$setupScript = Join-Path $projectRoot "Setup-DroneStream-Windows.ps1"

function Test-HttpReady {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

$apiReady = Test-HttpReady "http://127.0.0.1:8000/health"
$webReady = Test-HttpReady "http://127.0.0.1:5173/"
$runtimeReady = (Test-Path $pythonPath) -and (Test-Path $environmentFile) -and (Test-Path $npmModules)

if ($CheckOnly) {
    Write-Host "Runtime files: $(if ($runtimeReady) { 'ready' } else { 'first-run setup required' })"
    Write-Host "API port 8000: $(if ($apiReady) { 'already responding' } else { 'available to start' })"
    Write-Host "Frontend port 5173: $(if ($webReady) { 'already responding' } else { 'available to start' })"
    exit 0
}

$firstRunSetup = $false
if (-not $runtimeReady) {
    if (-not (Test-Path $setupScript)) {
        throw "First-run setup script is missing: $setupScript"
    }
    & $setupScript
    if ($LASTEXITCODE -ne 0) {
        throw "First-run setup failed. Review the setup output above."
    }
    $firstRunSetup = $true
}

foreach ($requiredPath in @($pythonPath, $environmentFile, $npmModules)) {
    if (-not (Test-Path $requiredPath)) {
        throw "Required local setup is missing after first-run setup: $requiredPath"
    }
}

$quotedRoot = $projectRoot.Replace("'", "''")
$quotedFrontendRoot = $frontendRoot.Replace("'", "''")
$quotedPythonPath = $pythonPath.Replace("'", "''")

if (-not $apiReady) {
    Push-Location $projectRoot
    try {
        & $pythonPath -m backend.app.init_db
        if ($LASTEXITCODE -ne 0) {
            throw "Database initialization failed. Check .env and the database service."
        }
    } finally {
        Pop-Location
    }

    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-Command",
        "Set-Location -LiteralPath '$quotedRoot'; & '$quotedPythonPath' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
    )
}

if (-not $webReady) {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-Command",
        "Set-Location -LiteralPath '$quotedFrontendRoot'; npm.cmd run dev -- --host 127.0.0.1"
    )
}

$deadline = (Get-Date).AddSeconds(60)
do {
    $apiReady = Test-HttpReady "http://127.0.0.1:8000/health"
    $webReady = Test-HttpReady "http://127.0.0.1:5173/"
    if ($apiReady -and $webReady) {
        break
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

if (-not $apiReady -or -not $webReady) {
    throw "DroneStream did not become ready. Check the API and frontend PowerShell windows for errors."
}

Start-Process "http://localhost:5173/"
Write-Host "DroneStream is ready at http://localhost:5173/"
Write-Host "Broadcaster page: http://localhost:5173/broadcast"
if ($firstRunSetup) {
    Write-Host "First-run admin credentials are stored under $env:LOCALAPPDATA\DroneStream."
    Read-Host "Press Enter to close this setup window"
}

function Import-ProjectEnvironment {
    foreach ($line in Get-Content -LiteralPath $environmentFile) {
        $trimmedLine = $line.Trim()
        if (-not $trimmedLine -or $trimmedLine.StartsWith("#")) { continue }
        $separator = $trimmedLine.IndexOf("=")
        if ($separator -lt 1) { continue }
        $name = $trimmedLine.Substring(0, $separator).Trim()
        $value = $trimmedLine.Substring($separator + 1).Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

Import-ProjectEnvironment