param([switch]$NoWebots)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup commands in README first.' }
foreach ($demoPort in @(8000, 5173)) {
    if (Get-NetTCPConnection -LocalPort $demoPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $demoPort is already in use. Close the existing demo before starting another."
    }
}
$logDir = Join-Path $repoRoot 'artifacts'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$backend = $null
$frontend = $null
try {
    $backend = Start-Process -FilePath $pythonPath -ArgumentList 'scripts/start_backend.py' -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logDir/backend.log" -RedirectStandardError "$logDir/backend-error.log"
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try { $null = Invoke-RestMethod 'http://localhost:8000/api/health'; $ready = $true; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Backend did not start. Inspect artifacts/backend-error.log.' }
    $seedJson = & $pythonPath -c 'import json; from scripts.seed_demo import seed; print(json.dumps(seed()))'
    if ($LASTEXITCODE -ne 0) { throw 'Demo seeding failed.' }
    $space = $seedJson | ConvertFrom-Json
    $env:INVITE_CODE = $space.invite_code
    $frontend = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c npm run dev -- --host 127.0.0.1' -WorkingDirectory "$repoRoot/frontend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logDir/frontend.log" -RedirectStandardError "$logDir/frontend-error.log"
    Write-Host "Robotic Mind: http://localhost:5173 | Invite: $($space.invite_code)"
    if ($NoWebots) { Read-Host 'Press Enter to stop' } else { & $pythonPath scripts/launch_webots.py --invite $space.invite_code }
} finally {
    foreach ($process in @($backend, $frontend)) {
        if ($process -and -not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    }
}
