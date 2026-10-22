"""Plan or queue a bounded owner-scoped activity detail backfill.

Enqueueing persists jobs only; Garmin requests happen in enabled workers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import sessionmaker

from src.application.activity_detail_backfill import ActivityDetailBackfill
from src.application.activity_detail_sync import ActivityDetailSyncService
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.session import create_database_engine, get_database_url
from src.infrastructure.integrations.garminconnect_adapter import GarminConnectResourceAdapter
from src.infrastructure.security.integration_credentials import load_garmin_credential_cipher


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=None)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--days', type=int, default=28)
    parser.add_argument('--as-of', default=None, help='timezone-aware ISO instant; defaults to now')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--dry-run', action='store_true')
    action.add_argument('--resume', metavar='BATCH_ID')
    action.add_argument('--pause', metavar='BATCH_ID')
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc)
    engine = create_database_engine(args.database_url or get_database_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def adapter_factory(session):
        return GarminConnectResourceAdapter(
            credentials=SqlAlchemyIntegrationRepository(session),
            cipher=load_garmin_credential_cipher())

    try:
        service = ActivityDetailSyncService(factory, adapter_factory)
        if args.pause:
            service.pause_batch(user_id=args.user_id, batch_id=args.pause)
            print(json.dumps({'status': 'paused', 'batch_id': args.pause}))
        elif args.resume:
            service.resume_batch(user_id=args.user_id, batch_id=args.resume, now=now)
            print(json.dumps({'status': 'resumed', 'batch_id': args.resume}))
        else:
            backfill = ActivityDetailBackfill(factory)
            plan = backfill.plan(user_id=args.user_id, days=args.days, now=now)
            if args.dry_run:
                print(json.dumps({'status': 'dry_run', 'activity_count': len(plan.activity_ids),
                                  'recent_count': plan.recent_count, 'older_count': plan.older_count}))
            else:
                if os.getenv('JOHNNY_ACTIVITY_DETAILS_ENABLED', '').lower() not in {'1', 'true', 'yes'}:
                    print('JOHNNY_ACTIVITY_DETAILS_ENABLED is required to enqueue backfill', file=sys.stderr)
                    return 2
                batches = backfill.enqueue(plan, service=service, now=now)
                print(json.dumps({'status': 'queued', 'activity_count': len(plan.activity_ids),
                                  'batch_ids': batches}))
        return 0
    except (ValueError, LookupError) as exc:
        print(f'Backfill request rejected: {exc}', file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
