param(
    [string]$OutputPath = (Join-Path $HOME "Desktop\DroneStream-source.zip")
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$stagingRoot = Join-Path $env:TEMP ("DroneStream-transfer-" + [guid]::NewGuid())
$excludedDirectories = @(
    (Join-Path $projectRoot ".git"),
    (Join-Path $projectRoot ".venv"),
    (Join-Path $projectRoot "frontend\node_modules"),
    (Join-Path $projectRoot "frontend\dist"),
    (Join-Path $projectRoot "backend\recordings\saved"),
    (Join-Path $projectRoot "backend\screenshots\saved")
)

try {
    New-Item -ItemType Directory -Path $stagingRoot | Out-Null

    & robocopy.exe $projectRoot $stagingRoot /E /R:1 /W:1 `
        /XD $excludedDirectories `
        /XF .env .env.local *.db *.sqlite *.sqlite3 *.pyc capture-test.png .local-admin-credentials.txt `
        /NFL /NDL /NJH /NJS /NP

    if ($LASTEXITCODE -gt 7) {
        throw "Source copy failed with robocopy exit code $LASTEXITCODE."
    }

    $destination = [System.IO.Path]::GetFullPath($OutputPath)
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    if (Test-Path $destination) {
        throw "The output file already exists; choose a different path: $destination"
    }

    Compress-Archive -Path (Join-Path $stagingRoot "*") `
        -DestinationPath $destination -CompressionLevel Optimal

    Write-Host "Transfer package created: $destination"
    Write-Host "Excluded: .env secrets, virtual environments, node_modules, builds, SQLite files, saved recordings, and saved screenshots."
    Write-Host "The first run on the destination PC creates its own local admin login and database. Existing accounts/media require separate backup migration."
}
finally {
    if (Test-Path $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}