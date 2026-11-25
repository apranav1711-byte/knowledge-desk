# Starts the Knowledge Desk backend on this PC and opens the website. Keep this window open while you use the app.
# The website (https://accenture-knowledge-desk.vercel.app) talks to it at http://localhost:8000.
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Knowledge Desk backend - keep this window open'
$Site = 'https://accenture-knowledge-desk.vercel.app'
Set-Location (Join-Path $PSScriptRoot 'backend')

# Already running? Then just open the website.
try {
  Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2 | Out-Null
  Write-Host 'Knowledge Desk is already running. Opening the website...'
  Start-Process $Site
  Start-Sleep -Seconds 3
  exit 0
} catch { }

if (-not (Test-Path '.venv\Scripts\python.exe')) {
  Write-Host 'First run: setting up Python packages (a few minutes)...'
  python -m venv .venv
  & .\.venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements.txt
}

Write-Host ''
Write-Host '  Knowledge Desk is starting on this computer. Keep this window open.'
Write-Host "  Website: $Site"
Write-Host '  To stop: close this window (or press Ctrl+C).'
Write-Host ''

# Open the website once the backend answers (in the background, so the server can start in this window).
Start-Job -ArgumentList $Site {
  param($Site)
  for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2 | Out-Null; Start-Process $Site; break }
    catch { Start-Sleep -Seconds 1 }
  }
} | Out-Null

& .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
