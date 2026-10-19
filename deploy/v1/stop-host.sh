#!/usr/bin/env bash
set -euo pipefail
test -L /opt/johnny/current
BACKEND_IMAGE=$(cat /opt/johnny/current-image)
export BACKEND_IMAGE
cd /opt/johnny/current
docker compose -f compose.yml stop scheduler worker api
