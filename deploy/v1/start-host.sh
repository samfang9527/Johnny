#!/usr/bin/env bash
set -euo pipefail

mountpoint -q /srv/johnny/data
test -L /opt/johnny/current
cd /opt/johnny/current
python3 load_secrets.py
BACKEND_IMAGE=$(cat /opt/johnny/current-image)
export BACKEND_IMAGE
REGION=$(sed -n 's/^AWS_REGION=//p' /etc/johnny/production.env)
REGISTRY="${BACKEND_IMAGE%%/*}"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker compose -f compose.yml up -d --no-recreate postgres
docker compose -f compose.yml up -d --no-deps api worker scheduler
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/ready >/dev/null; then
    rm -f /run/johnny-maintenance
    exit 0
  fi
  sleep 2
done
echo "API did not become ready after restart" >&2
exit 1
