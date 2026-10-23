@echo off
setlocal
cd /d "%~dp0frontend"
if not exist node_modules (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)
echo Starting STREAM SENTINEL at http://localhost:5173
call npm run dev
