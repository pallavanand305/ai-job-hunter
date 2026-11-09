$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Missing .venv. Run .\scripts\setup.ps1 first."
}

Write-Host "Compiling Python..."
& ".\.venv\Scripts\python.exe" -m compileall -q app
if ($LASTEXITCODE -ne 0) { throw "Python compile failed." }

Write-Host "Running tests..."
Remove-Item -Force "data\test_jobhunter.db" -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "Checking dashboard JavaScript..."
    & node --check "app\static\app.js"
    if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed." }
}

Write-Host "All checks passed."
