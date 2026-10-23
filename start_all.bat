@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe python -m venv backend\.venv
if not exist backend\.venv\Scripts\python.exe (
	echo Could not create backend virtual environment.
	exit /b 1
)
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=
set NO_PROXY=*
set no_proxy=*
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=8000,5173; foreach($port in $ports){Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue}}"
backend\.venv\Scripts\python.exe -c "import fastapi,uvicorn,sqlalchemy" >nul 2>&1
if errorlevel 1 (
	echo Installing backend dependencies...
	backend\.venv\Scripts\python.exe -m pip install --isolated --disable-pip-version-check -r backend\requirements.txt
	if errorlevel 1 (
		echo Backend dependency installation failed.
		exit /b 1
	)
)
if not exist frontend\node_modules (
	echo Installing frontend dependencies...
	cd frontend
	call npm install
	if errorlevel 1 exit /b 1
	cd ..
)
backend\.venv\Scripts\python.exe backend\init_db.py
start "Twitch Sentinel Backend" cmd /k "cd /d %~dp0backend && set PYTHONUNBUFFERED=1 && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 2 /nobreak >nul
start "Twitch Sentinel Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --host 0.0.0.0"
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo Twitch OAuth callback: http://localhost:5173/auth/callback
