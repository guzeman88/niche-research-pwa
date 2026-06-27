@echo off
cd /d "%~dp0..\backend"
set PORT=8001

echo [%date% %time%] Starting backend API...
start /B "backend" python -m uvicorn main:app --host 127.0.0.1 --port %PORT%

timeout /t 10 /nobreak > nul

echo [%date% %time%] Starting scheduler...
curl -s -X POST http://localhost:%PORT%/api/scheduler/start -H "Content-Type: application/json" -d "{\"mode\":\"performance\",\"batch_size\":5}"

echo [%date% %time%] Scanner is running.
