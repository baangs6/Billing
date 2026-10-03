$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$billingPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $billingPython)) {
    python -m venv .venv
    & $billingPython -m pip install -r requirements.txt
}
& $billingPython -c "import flask, pymongo, cryptography, reportlab, waitress"
if ($LASTEXITCODE -ne 0) { & $billingPython -m pip install -r requirements.txt }
& $billingPython scripts/init_saas.py
if ($LASTEXITCODE -ne 0) { throw 'SaaS initialization failed.' }
$billingAdminProcess = $null
if (-not (Get-NetTCPConnection -State Listen -LocalPort 5001 -ErrorAction SilentlyContinue)) {
    $billingAdminProcess = Start-Process -FilePath $billingPython -ArgumentList 'admin_app.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput 'instance/admin.stdout.log' -RedirectStandardError 'instance/admin.stderr.log' -PassThru
}
Write-Host 'Company app: http://127.0.0.1:5000. Owner panel: http://127.0.0.1:5001. Press Ctrl+C to stop.'
try { & $billingPython app.py }
finally { if ($billingAdminProcess -and -not $billingAdminProcess.HasExited) { Stop-Process -Id $billingAdminProcess.Id } }
