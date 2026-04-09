#!/bin/bash

# MootCourt Startup Script
# Starts both frontend and backend servers

echo "🏛️  Starting MootCourt.ai..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# Check if Node.js is installed
if ! command -v npm &> /dev/null; then
    echo "❌ Node.js/npm is not installed. Please install Node.js first."
    exit 1
fi

# Start backend
echo "📦 Starting backend server..."
cd agents
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv and install/run
if command -v pip3 &> /dev/null; then
    pip3 install -q -r requirements.txt
else
    pip install -q -r requirements.txt
fi

# Start the backend in the background
python3 server.py &
BACKEND_PID=$!
echo "✅ Backend started (PID: $BACKEND_PID)"
echo ""

cd ..

# Start frontend
echo "⚛️  Starting frontend server..."
if [ ! -d "node_modules" ]; then
    echo "Installing node dependencies..."
    npm install
fi

npm run dev &
FRONTEND_PID=$!
echo "✅ Frontend started (PID: $FRONTEND_PID)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 MootCourt.ai is running!"
echo ""
echo "Frontend:  http://localhost:5173"
echo "Backend:   http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Trap Ctrl+C to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; echo '👋 MootCourt.ai stopped'; exit" INT TERM

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
