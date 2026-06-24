@echo off
cd /d "%~dp0..\backend"

echo [%date% %time%] Starting backend API...
start /B "backend" python -m uvicorn main:app --host 127.0.0.1 --port 8000

timeout /t 10 /nobreak > nul

echo [%date% %time%] Starting scheduler...
curl -s -X POST http://localhost:8000/api/scheduler/start -H "Content-Type: application/json" -d "{\"mode\":\"burst\",\"batch_size\":5}"

echo [%date% %time%] Scanner is running.
