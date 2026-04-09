# Scrpr - One-click startup
$Host.UI.RawUI.WindowTitle = "Scrpr"
Clear-Host

Write-Host ""
Write-Host "   SSSSS   CCCCC  RRRR   PPPP   RRRR  " -ForegroundColor Cyan
Write-Host "   S       C       R   R  P   P  R   R " -ForegroundColor Cyan
Write-Host "   SSSSS   C       RRRR   PPPP   RRRR  " -ForegroundColor DarkCyan
Write-Host "       S   C       R  R   P      R  R  " -ForegroundColor DarkCyan
Write-Host "   SSSSS   CCCCC   R   R  P      R   R " -ForegroundColor Cyan
Write-Host ""
Write-Host "   AI-Powered Data Enrichment" -ForegroundColor DarkGray
Write-Host ""

Set-Location $PSScriptRoot

# Kill any existing servers first
Write-Host "   Cleaning up old processes..." -ForegroundColor DarkGray
Get-Process -Name "python*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Step 1: Ollama
$ollamaRunning = $false
try {
    $response = curl.exe -s http://localhost:11434/api/tags 2>$null
    if ($response) { $ollamaRunning = $true }
} catch {}

if ($ollamaRunning) {
    Write-Host "   [1/3] Ollama already running" -ForegroundColor Green
} else {
    Write-Host "   [1/3] Starting Ollama on NVIDIA GPU..." -ForegroundColor Yellow
    $env:CUDA_VISIBLE_DEVICES = "0"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# Step 2: Backend
Write-Host "   [2/3] Starting backend API..." -ForegroundColor Yellow
$env:DATABASE_URL = "sqlite+aiosqlite:///./scrpr.db"
Start-Process -FilePath "python" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$PSScriptRoot\backend" -WindowStyle Hidden

Write-Host "         Waiting for backend" -ForegroundColor DarkGray -NoNewline
$attempts = 0
$backendReady = $false
while (-not $backendReady -and $attempts -lt 30) {
    Start-Sleep -Seconds 1
    Write-Host "." -ForegroundColor DarkGray -NoNewline
    $attempts++
    try {
        $result = curl.exe -s http://localhost:8000/health 2>$null
        if ($result -match "ok") { $backendReady = $true }
    } catch {}
}

if ($backendReady) {
    Write-Host " Ready!" -ForegroundColor Green
} else {
    Write-Host " FAILED!" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Backend failed to start. Check that Python is installed:" -ForegroundColor Red
    Write-Host "   cd $PSScriptRoot\backend" -ForegroundColor Yellow
    Write-Host "   python -m uvicorn app.main:app --port 8000" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Press any key to exit..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# Step 3: Frontend
Write-Host "   [3/3] Starting frontend..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/c cd /d `"$PSScriptRoot\frontend`" && npm run dev" -WindowStyle Hidden

Write-Host "         Waiting for frontend" -ForegroundColor DarkGray -NoNewline
$attempts = 0
$frontendReady = $false
while (-not $frontendReady -and $attempts -lt 30) {
    Start-Sleep -Seconds 1
    Write-Host "." -ForegroundColor DarkGray -NoNewline
    $attempts++
    try {
        $result = curl.exe -s -o NUL -w "%{http_code}" http://localhost:3000 2>$null
        if ($result -match "200") { $frontendReady = $true }
    } catch {}
}

if ($frontendReady) {
    Write-Host " Ready!" -ForegroundColor Green
} else {
    Write-Host " FAILED!" -ForegroundColor Red
    Write-Host "   Frontend failed. Check: cd frontend && npm run dev" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "   ==========================================" -ForegroundColor DarkCyan
Write-Host "     Scrpr is running!" -ForegroundColor White
Write-Host "     Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "     API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "   ==========================================" -ForegroundColor DarkCyan
Write-Host ""

# Open browser
Start-Process "http://localhost:3000"

Write-Host "   Press any key to stop all services..." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Cleanup
Write-Host ""
Write-Host "   Stopping services..." -ForegroundColor Yellow
Get-Process -Name "python*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "node*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "   Done. Goodbye!" -ForegroundColor Green
Start-Sleep -Seconds 1
