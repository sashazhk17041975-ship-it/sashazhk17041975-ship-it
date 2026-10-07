@echo off
setlocal
cd /d "%~dp0"
docker compose stop
if errorlevel 1 (
    echo Could not stop the services. Check that Docker Desktop is running.
    pause
    exit /b 1
)
echo Services stopped. Database records are preserved.
pause
exit /b 0
