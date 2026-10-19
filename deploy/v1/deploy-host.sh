#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "usage: deploy-host.sh RELEASE_SHA RELEASE_BUCKET BACKUP_BUCKET AWS_REGION MODE" >&2
  exit 2
fi
RELEASE_SHA="$1"
RELEASE_BUCKET="$2"
BACKUP_BUCKET="$3"
AWS_REGION="$4"
MODE="$5"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid release SHA" >&2; exit 2; }
[[ "$MODE" = "deploy" || "$MODE" = "rollback" ]] || { echo "Invalid deployment mode" >&2; exit 2; }
RELEASE_DIR="/opt/johnny/releases/$RELEASE_SHA"
test -d "$RELEASE_DIR"
mountpoint -q /srv/johnny/data
exec 9>/run/johnny-deploy.lock
flock -n 9 || { echo "Another deployment is running" >&2; exit 1; }

MANIFEST=$(mktemp)
trap 'rm -f "$MANIFEST"' EXIT
aws s3 cp "s3://$RELEASE_BUCKET/production/v1/$RELEASE_SHA/manifest.json" "$MANIFEST" --region "$AWS_REGION" --only-show-errors
BACKEND_IMAGE=$(python3 - "$MANIFEST" "$RELEASE_SHA" <<'PY'
import json, re, sys
manifest = json.load(open(sys.argv[1]))
if manifest.get("sha") != sys.argv[2]:
    raise SystemExit("Release manifest SHA mismatch")
image = manifest.get("backend_image", "")
if not re.fullmatch(r"[0-9]+\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9/_-]+@sha256:[0-9a-f]{64}", image):
    raise SystemExit("Release manifest does not contain an immutable ECR digest")
print(image)
PY
)
export BACKEND_IMAGE

test -f /etc/johnny/production.env
python3 "$RELEASE_DIR/load_secrets.py"
REGISTRY="${BACKEND_IMAGE%%/*}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
cd "$RELEASE_DIR"
docker compose -f compose.yml config --quiet
docker compose -f compose.yml pull api worker scheduler

ROOT_FREE_MB=$(df -Pm / | awk 'NR == 2 {print $4}')
DATA_FREE_MB=$(df -Pm /srv/johnny/data | awk 'NR == 2 {print $4}')
test "$ROOT_FREE_MB" -ge 1500 && test "$DATA_FREE_MB" -ge 1000 || {
  echo "Insufficient free disk space for deployment" >&2
  exit 1
}

API_HOST=$(python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
settings = dict(line.split('=', 1) for line in Path('/etc/johnny/production.env').read_text().splitlines() if line and not line.startswith('#'))
print(urlsplit(settings['API_URL']).hostname)
PY
)
if [ ! -s "/etc/letsencrypt/live/$API_HOST/fullchain.pem" ]; then
  CERT_EMAIL=$(cat /etc/johnny/cert-email)
  certbot --nginx --non-interactive --agree-tos --email "$CERT_EMAIL" -d "$API_HOST"
fi
sed "s/__API_HOST__/$API_HOST/g" "$RELEASE_DIR/nginx-https.conf.template" > /etc/nginx/conf.d/johnny.conf
nginx -t
systemctl reload nginx

CURRENT_IMAGE=""
if [ -f /opt/johnny/current-image ]; then
  CURRENT_IMAGE=$(cat /opt/johnny/current-image)
fi
if [ "$MODE" = "rollback" ] && [ -z "$CURRENT_IMAGE" ]; then
  echo "Cannot roll back before the first deployment" >&2
  exit 2
fi
PHASE="before-migration"
on_error() {
  local status=$?
  if [ "$PHASE" = "before-migration" ] && [ -n "$CURRENT_IMAGE" ] && [ -L /opt/johnny/current ]; then
    echo "Deployment failed before migration; restoring previous services" >&2
    (cd /opt/johnny/current && BACKEND_IMAGE="$CURRENT_IMAGE" docker compose -f compose.yml up -d --no-deps api worker scheduler) || true
    rm -f /run/johnny-maintenance
  else
    echo "Deployment failed after migration or during first launch; maintenance remains enabled" >&2
    BACKEND_IMAGE="$BACKEND_IMAGE" docker compose -f compose.yml stop scheduler worker || true
  fi
  exit "$status"
}
trap on_error ERR

docker compose -f compose.yml up -d --no-recreate postgres
touch /run/johnny-maintenance
docker compose -f compose.yml stop -t 90 scheduler
WORKER_CONTAINER=$(docker compose -f compose.yml ps -q worker || true)
docker compose -f compose.yml stop -t 600 worker
if [ -n "$WORKER_CONTAINER" ]; then
  WORKER_EXIT=$(docker inspect -f '{{.State.ExitCode}}' "$WORKER_CONTAINER")
  test "$WORKER_EXIT" -eq 0 || { echo "Worker did not stop cleanly; aborting before migration" >&2; false; }
fi
API_CONTAINER=$(docker compose -f compose.yml ps -q api || true)
docker compose -f compose.yml stop -t 60 api
if [ -n "$API_CONTAINER" ]; then
  API_EXIT=$(docker inspect -f '{{.State.ExitCode}}' "$API_CONTAINER")
  test "$API_EXIT" -ne 137 || { echo "API was forced to stop; aborting before migration" >&2; false; }
fi

if [ -n "$CURRENT_IMAGE" ]; then
  BACKEND_IMAGE="$CURRENT_IMAGE" /bin/bash /opt/johnny/current/backup-db.sh
fi

PHASE="after-migration"
if [ "$MODE" = "deploy" ]; then
  docker compose -f compose.yml run --rm --no-deps api python -m alembic -c backend/alembic.ini upgrade head
  docker compose -f compose.yml run --rm --no-deps api python -m src.infrastructure.database.check_schema_revision
fi
docker compose -f compose.yml up -d --no-deps api worker scheduler
READY=false
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/ready >/dev/null; then
    READY=true
    break
  fi
  sleep 2
done
test "$READY" = true

printf '%s\n' "$BACKEND_IMAGE" > /opt/johnny/current-image
printf '%s\n' "$BACKUP_BUCKET" > /etc/johnny/backup-bucket
chmod 0600 /opt/johnny/current-image /etc/johnny/backup-bucket
ln -sfn "$RELEASE_DIR" /opt/johnny/current.next
mv -Tf /opt/johnny/current.next /opt/johnny/current
install -m 0755 "$RELEASE_DIR/start-host.sh" /usr/local/bin/johnny-start
install -m 0755 "$RELEASE_DIR/stop-host.sh" /usr/local/bin/johnny-stop
install -m 0755 "$RELEASE_DIR/backup-db.sh" /usr/local/bin/johnny-backup
install -m 0644 "$RELEASE_DIR/johnny.service" /etc/systemd/system/johnny.service
install -m 0644 "$RELEASE_DIR/johnny-backup.service" /etc/systemd/system/johnny-backup.service
install -m 0644 "$RELEASE_DIR/johnny-backup.timer" /etc/systemd/system/johnny-backup.timer
install -m 0644 "$RELEASE_DIR/johnny-cert-renew.service" /etc/systemd/system/johnny-cert-renew.service
install -m 0644 "$RELEASE_DIR/johnny-cert-renew.timer" /etc/systemd/system/johnny-cert-renew.timer
systemctl daemon-reload
systemctl enable johnny.service johnny-backup.timer johnny-cert-renew.timer
systemctl start johnny.service
systemctl start johnny-backup.timer johnny-cert-renew.timer
rm -f /run/johnny-maintenance
PHASE="complete"
echo "Deployed production v1 release $RELEASE_SHA"
