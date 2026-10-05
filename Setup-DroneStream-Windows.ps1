$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $projectRoot ".env"
$frontendRoot = Join-Path $projectRoot "frontend"
$credentialsDirectory = Join-Path $env:LOCALAPPDATA "DroneStream"
$credentialsFile = Join-Path $credentialsDirectory "local-admin-credentials.txt"

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Invoke-ExternalCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $commandExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }

    if ($commandExitCode -ne 0) {
        throw "$FailureMessage (exit code $commandExitCode)."
    }
}

function Install-WingetPackage {
    param([string]$PackageId)

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Windows Package Manager (winget) is unavailable. Install or update App Installer, then double-click Start-DroneStream.bat again."
    }

    Write-Host "Installing $PackageId..."
    Invoke-ExternalCommand -FilePath $winget.Source -Arguments @("install", "--id", $PackageId, "--exact", "--accept-source-agreements", "--accept-package-agreements", "--silent") -FailureMessage "winget could not install $PackageId"
    Refresh-ProcessPath
}

function Import-ProjectEnvironment {
    foreach ($line in Get-Content -LiteralPath $envFile) {
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

if (-not (Get-Command py.exe -ErrorAction SilentlyContinue) -and -not (Get-Command python.exe -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "Python.Python.3.13"
}

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "OpenJS.NodeJS.LTS"
}

if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) {
    Install-WingetPackage "Gyan.FFmpeg.Shared"
}

Refresh-ProcessPath

if (-not (Test-Path $venvPython)) {
    $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        Invoke-ExternalCommand -FilePath $pythonLauncher.Source -Arguments @("-3.13", "-m", "venv", (Join-Path $projectRoot ".venv")) -FailureMessage "Unable to create the project Python environment"
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python installation completed but python.exe was not found. Sign out and back in, then run this launcher again."
        }
        Invoke-ExternalCommand -FilePath $pythonCommand.Source -Arguments @("-m", "venv", (Join-Path $projectRoot ".venv")) -FailureMessage "Unable to create the project Python environment"
    }
}

$ffmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if (-not $ffmpegCommand) {
    throw "FFmpeg was installed but is not visible in PATH yet. Restart Windows, then run the launcher again."
}

$createdLocalProfile = $false
if (-not (Test-Path $envFile)) {
    $randomBytes = New-Object byte[] 32
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomGenerator.GetBytes($randomBytes)
    } finally {
        $randomGenerator.Dispose()
    }
    $adminPassword = [System.BitConverter]::ToString($randomBytes).Replace("-", "")

    $secretBytes = New-Object byte[] 32
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomGenerator.GetBytes($secretBytes)
    } finally {
        $randomGenerator.Dispose()
    }
    $secretKey = [Convert]::ToBase64String($secretBytes)
    $databaseUrl = "sqlite+aiosqlite:///backend/dronestream-local.db"
    $ffmpegPath = $ffmpegCommand.Source.Replace("\", "/")

    $envContents = @(
        "DATABASE_URL=$databaseUrl"
        "ADMIN_USERNAME=admin"
        "ADMIN_PASSWORD=$adminPassword"
        "SECRET_KEY=$secretKey"
        "ENVIRONMENT=development"
        "FORCE_LOOPBACK=true"
        "TURN_URLS=[]"
        "TURN_SHARED_SECRET="
        "CORS_ORIGINS=[`"http://localhost:5173`",`"http://127.0.0.1:5173`"]"
        "FFMPEG_PATH=$ffmpegPath"
    )
    Set-Content -LiteralPath $envFile -Value $envContents -Encoding ASCII

    New-Item -ItemType Directory -Path $credentialsDirectory -Force | Out-Null
    Set-Content -LiteralPath $credentialsFile -Value @(
        "DroneStream local administrator login"
        "Username: admin"
        "Password: $adminPassword"
        ""
        "Keep this file private. It is stored outside the project folder and is not included in transfer ZIPs."
    ) -Encoding UTF8
    $createdLocalProfile = $true
    Write-Host "Created a private SQLite database profile for this PC."
    Write-Host "First-run admin login saved to: $credentialsFile"
}

Push-Location $projectRoot
try {
    Write-Host "Installing/verifying Python packages..."
    Invoke-ExternalCommand -FilePath $venvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $projectRoot "requirements.txt")) -FailureMessage "Python package installation failed"

    Write-Host "Installing/verifying frontend packages..."
    Push-Location $frontendRoot
    try {
        $npmCommand = Get-Command npm.cmd -ErrorAction Stop
        Invoke-ExternalCommand -FilePath $npmCommand.Source -Arguments @("ci", "--no-audit", "--no-fund") -FailureMessage "Frontend package installation failed"
    } finally {
        Pop-Location
    }

    Write-Host "Creating missing database tables..."
    Import-ProjectEnvironment
    Invoke-ExternalCommand -FilePath $venvPython -Arguments @("-m", "backend.app.init_db") -FailureMessage "Database initialization failed. Check DATABASE_URL and database availability"
} finally {
    Pop-Location
}

Write-Host "DroneStream first-run setup completed."
if ($createdLocalProfile) {
    Write-Host "Open the local admin credentials file shown above to sign in."
}