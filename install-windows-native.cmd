@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 (
    echo Install Python 3.12 for Windows 64-bit, including its launcher or PATH entry.
    goto error
)
set "APP_PYTHON_CMD=python"
goto venv
:launcher
set "APP_PYTHON_CMD=py -3.12"
:venv
%APP_PYTHON_CMD% -m venv .venv
if errorlevel 1 goto error
:install
".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8"
if errorlevel 1 (
    echo This local installer requires Python 3.12 64-bit. Use a clean project folder with that version.
    goto error
)
if exist "vendor\wheels" (
    ".venv\Scripts\python.exe" -m pip install --no-index --find-links=vendor\wheels --require-hashes -r requirements-windows-lock.txt
) else (
    ".venv\Scripts\python.exe" -m pip install --only-binary=mysqlclient -r requirements-windows.txt
)
if errorlevel 1 goto error
".venv\Scripts\python.exe" scripts\setup_native.py
if errorlevel 1 goto error
echo.
echo Installation complete. Double-click start-windows-native.cmd to open the site.
pause
exit /b 0
:error
echo.
echo Installation failed. See the error above and WINDOWS-NATIVE.md.
pause
exit /b 1
