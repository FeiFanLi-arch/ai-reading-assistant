param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create virtual environment. Install Python 3.11 or newer with pip.' }
}
$readerPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $readerPython -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
Write-Host "Reading Assistant: http://127.0.0.1:$Port"
& $readerPython -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
