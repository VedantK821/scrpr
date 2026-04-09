#!/bin/bash
# Scrpr — One-click startup script
# Usage: ./start.sh

echo "🚀 Starting Scrpr..."

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve &
    sleep 3
fi

# Kill any existing processes on our ports
echo "Cleaning up old processes..."
for port in 8000 3000; do
    pid=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTEN | awk '{print $5}' | head -1)
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
        taskkill //F //PID "$pid" 2>/dev/null
    fi
done
sleep 1

# Start backend
echo "Starting backend API (port 8000)..."
cd "$(dirname "$0")/backend"
DATABASE_URL="sqlite+aiosqlite:///./scrpr.db" python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend..."
for i in $(seq 1 20); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Backend ready"
        break
    fi
    sleep 1
done

# Start frontend
echo "Starting frontend (port 3000)..."
cd "$(dirname "$0")/frontend"
npm run dev &
FRONTEND_PID=$!

sleep 3
echo ""
echo "═══════════════════════════════════════"
echo "  Scrpr is running!"
echo "  Frontend:  http://localhost:3000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Health:    http://localhost:8000/health"
echo "═══════════════════════════════════════"
echo ""
echo "Press Ctrl+C to stop all services"

# Open browser
start http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null || open http://localhost:3000 2>/dev/null

# Wait for Ctrl+C
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
