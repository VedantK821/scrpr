# Scrpr — One-click startup
$Host.UI.RawUI.WindowTitle = "Scrpr"
$Host.UI.RawUI.BackgroundColor = "Black"
$Host.UI.RawUI.ForegroundColor = "Cyan"
Clear-Host

Write-Host ""
Write-Host "   ███████╗ ██████╗██████╗ ██████╗ ██████╗ " -ForegroundColor Cyan
Write-Host "   ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗" -ForegroundColor Cyan
Write-Host "   ███████╗██║     ██████╔╝██████╔╝██████╔╝" -ForegroundColor DarkCyan
Write-Host "   ╚════██║██║     ██╔══██╗██╔═══╝ ██╔══██╗" -ForegroundColor DarkCyan
Write-Host "   ███████║╚██████╗██║  ██║██║     ██║  ██║" -ForegroundColor Cyan
Write-Host "   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "   AI-Powered Data Enrichment" -ForegroundColor DarkGray
Write-Host ""

Set-Location $PSScriptRoot

# Step 1: Ollama
try { $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "   [1/3] Ollama already running" -ForegroundColor Green
} catch {
    Write-Host "   [1/3] Starting Ollama on NVIDIA GPU..." -ForegroundColor Yellow
    $env:CUDA_VISIBLE_DEVICES = "0"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# Step 2: Backend
Write-Host "   [2/3] Starting backend API..." -ForegroundColor Yellow
$env:DATABASE_URL = "sqlite+aiosqlite:///./scrpr.db"
$backend = Start-Process -FilePath "python" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$PSScriptRoot\backend" -WindowStyle Hidden -PassThru

Write-Host "         Waiting for backend..." -ForegroundColor DarkGray -NoNewline
do {
    Start-Sleep -Seconds 1
    Write-Host "." -ForegroundColor DarkGray -NoNewline
    try { $null = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2 -ErrorAction Stop; $backendReady = $true } catch { $backendReady = $false }
} until ($backendReady)
Write-Host " Ready!" -ForegroundColor Green

# Step 3: Frontend
Write-Host "   [3/3] Starting frontend..." -ForegroundColor Yellow
$frontend = Start-Process -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory "$PSScriptRoot\frontend" -WindowStyle Hidden -PassThru

Write-Host "         Waiting for frontend..." -ForegroundColor DarkGray -NoNewline
do {
    Start-Sleep -Seconds 1
    Write-Host "." -ForegroundColor DarkGray -NoNewline
    try { $null = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 2 -ErrorAction Stop; $frontendReady = $true } catch { $frontendReady = $false }
} until ($frontendReady)
Write-Host " Ready!" -ForegroundColor Green

Write-Host ""
Write-Host "   ══════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host "     Scrpr is running!" -ForegroundColor White
Write-Host "     Frontend:  " -ForegroundColor DarkGray -NoNewline
Write-Host "http://localhost:3000" -ForegroundColor Cyan
Write-Host "     API Docs:  " -ForegroundColor DarkGray -NoNewline
Write-Host "http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "   ══════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""

# Open browser
Start-Process "http://localhost:3000"

Write-Host "   Press any key to stop all services..." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Cleanup
Write-Host ""
Write-Host "   Stopping services..." -ForegroundColor Yellow
if ($backend -and !$backend.HasExited) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
if ($frontend -and !$frontend.HasExited) { Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Write-Host "   Done. Goodbye!" -ForegroundColor Green
Start-Sleep -Seconds 1
