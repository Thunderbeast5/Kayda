@echo off
REM MootCourt Startup Script for Windows
REM Starts both frontend and backend servers

echo.
echo 🏛️  Starting MootCourt.ai...
echo.

REM Check if Python is installed
where python >nul 2>nul
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH. Please install Python first.
    pause
    exit /b 1
)

REM Check if npm is installed
where npm >nul 2>nul
if errorlevel 1 (
    echo ❌ Node.js/npm is not installed. Please install Node.js first.
    pause
    exit /b 1
)

REM Start backend
echo 📦 Starting backend server...
cd agents

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Install dependencies
python -m pip install -q -r requirements.txt

REM Start the backend in a new window
start "MootCourt Backend" python server.py
echo ✅ Backend started
echo.

cd ..\@interface

REM Start frontend
echo ⚛️  Starting frontend server...
if not exist "node_modules" (
    echo Installing node dependencies...
    npm install
)

start "MootCourt Frontend" npm run dev
echo ✅ Frontend started
echo.

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 MootCourt.ai is running!
echo.
echo Frontend:  http://localhost:5173
echo Backend:   http://localhost:5000
echo.
echo Separate windows have been opened for each service
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause
