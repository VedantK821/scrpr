@echo off
title Scrpr - Starting...
color 0B
echo.
echo    ____   ____ ____  ____  ____
echo   / ___) / ___(  _ \(  _ \(  _ \
echo   \___ \( (__  )   / )___/ )   /
echo   (____/ \___)(_)\_)(__)  (_)\_)
echo.
echo   Starting services...
echo.

cd /d "%~dp0"

:: Start Ollama if not running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo   [1/3] Starting Ollama (NVIDIA GPU)...
    set CUDA_VISIBLE_DEVICES=0
    start /min "" ollama serve
    timeout /t 3 /nobreak >nul
) else (
    echo   [1/3] Ollama already running
)

:: Start backend
echo   [2/3] Starting backend API...
cd backend
start /min "" cmd /c "set DATABASE_URL=sqlite+aiosqlite:///./scrpr.db && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
cd ..

:: Wait for backend
echo         Waiting for backend...
:wait_backend
timeout /t 1 /nobreak >nul
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 goto wait_backend
echo         Backend ready!

:: Start frontend
echo   [3/3] Starting frontend...
cd frontend
start /min "" cmd /c "npm run dev"
cd ..

:: Wait for frontend
echo         Waiting for frontend...
:wait_frontend
timeout /t 1 /nobreak >nul
curl -s http://localhost:3000 >nul 2>&1
if errorlevel 1 goto wait_frontend
echo         Frontend ready!

echo.
echo   ==========================================
echo     Scrpr is running!
echo     Opening browser...
echo   ==========================================
echo.
echo   Press any key to STOP all services.
echo.

:: Open browser
start http://localhost:3000

:: Wait for user to press a key to stop
pause >nul

:: Cleanup
echo.
echo   Stopping services...
taskkill /f /im "uvicorn.exe" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq npm*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTEN"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTEN"') do taskkill /f /pid %%a >nul 2>&1
echo   Done. Goodbye!
timeout /t 2 /nobreak >nul
