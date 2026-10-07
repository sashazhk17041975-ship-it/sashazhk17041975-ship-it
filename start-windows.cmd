@echo off
setlocal
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
    echo Start Docker Desktop, wait until its engine is running, and try again.
    goto error
)
docker compose version >nul 2>&1
if errorlevel 1 (
    echo Docker Compose v2 is required. Update Docker Desktop and try again.
    goto error
)
if not exist .env (
    docker run --rm --mount "type=bind,source=%cd%,target=/project" --workdir /project python:3.12-slim-bookworm python scripts/init_env.py
    if errorlevel 1 goto error
)
docker compose up -d --build --wait --wait-timeout 240
if errorlevel 1 goto error
docker compose exec -T web python manage.py bootstrap_admin
if errorlevel 1 goto error
docker compose exec -T web python manage.py seed_catalog
if errorlevel 1 goto error
echo.
echo AutoAnalogs is ready at http://localhost:8000
echo Initial login: admin
echo Initial password: DJANGO_SUPERUSER_PASSWORD in the local .env file.
echo Existing accounts and catalogue records are preserved.
start "" "http://localhost:8000"
pause
exit /b 0
:error
echo.
echo Startup failed. See the error above and WINDOWS.md for help.
pause
exit /b 1
