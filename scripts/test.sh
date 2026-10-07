#!/bin/sh
set -eu
# MySQL's application user intentionally cannot create arbitrary databases.
# Root is used only for Django's isolated test database, never for the web service.
docker compose run --rm tests
