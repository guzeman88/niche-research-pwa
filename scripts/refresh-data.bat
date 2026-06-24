@echo off
cd /d "%~dp0.."

echo [%date% %time%] Pulling fresh data from local scanner...
set VITE_API_URL=http://localhost:8000
node scripts\build-data.cjs

echo.
echo [%date% %time%] Building frontend with fresh data...
call npm run build

echo.
echo [%date% %time%] Deploying to Netlify...
call npx netlify deploy --prod --dir=dist

echo.
echo [%date% %time%] Done.
