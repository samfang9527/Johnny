#!/usr/bin/env bash
set -euo pipefail

mountpoint -q /srv/johnny/data
test -L /opt/johnny/current
BACKUP_BUCKET=$(cat /etc/johnny/backup-bucket)
BACKEND_IMAGE=$(cat /opt/johnny/current-image)
export BACKEND_IMAGE
cd /opt/johnny/current
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
KEY="production/postgres/$STAMP.dump"
docker compose -f compose.yml exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -h 127.0.0.1 -U johnny -d johnny' \
  | aws s3 cp - "s3://$BACKUP_BUCKET/$KEY" --sse AES256 --only-show-errors
aws s3api head-object --bucket "$BACKUP_BUCKET" --key "$KEY" --query ContentLength --output text >/dev/null
echo "Database backup uploaded: s3://$BACKUP_BUCKET/$KEY"
