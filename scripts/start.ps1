$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) {
    Write-Host "No .venv found. Run .\scripts\setup.ps1 first."
    exit 1
}

& ".\.venv\Scripts\python.exe" run.py
