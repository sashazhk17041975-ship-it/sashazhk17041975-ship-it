#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export DOCKER_CONFIG="${DOCKER_CONFIG:-/tmp/autoparts-docker}"
python3 scripts/init_env.py
python3 scripts/cloud_build.py
docker compose up -d --no-build --wait
docker compose exec -T web python manage.py bootstrap_admin
docker compose exec -T web python manage.py seed_catalog
docker compose exec -T web python manage.py check
