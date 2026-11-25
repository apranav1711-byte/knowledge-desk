# Starts the Knowledge Desk backend on this PC. Keep this window open while you use the app.
# The website (https://accenture-knowledge-desk.vercel.app) talks to it at http://localhost:8000.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'backend')
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  Write-Host 'First run: setting up Python packages (a few minutes)...'
  python -m venv .venv
  & .\.venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements.txt
}
Write-Host ''
Write-Host 'Knowledge Desk is running on this computer. Keep this window open.'
Write-Host 'Open: https://accenture-knowledge-desk.vercel.app   (Ctrl+C here to stop)'
Write-Host ''
Start-Process 'https://accenture-knowledge-desk.vercel.app'
& .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
