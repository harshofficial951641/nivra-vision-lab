param([switch]$Classroom)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot 'service\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run the setup instructions in service/README.md first.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
if ($Classroom) {
    $env:NIVRA_PERSON_MODEL = 'rtmo'
    $env:NIVRA_FIGHT_MODEL = 'x3d'
    $env:NIVRA_ACTION_REGIONS = '1'
    & $pythonPath service/prepare_models.py --experimental
} else {
    & $pythonPath service/prepare_models.py
}
if ($LASTEXITCODE -ne 0) { throw 'Model verification failed.' }
Write-Host 'NIVRA local AI: http://127.0.0.1:8765 (experimental; Ctrl+C stops the service)'
Set-Location -LiteralPath (Join-Path $projectRoot 'service')
& $pythonPath -m nivra.server
