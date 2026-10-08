@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install-windows-native.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\serve_internet.py
if errorlevel 1 (
    echo.
    echo See the error above and WINDOWS-NATIVE.md.
    pause
    exit /b 1
)
exit /b 0
