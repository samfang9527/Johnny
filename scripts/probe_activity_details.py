"""Bounded read-only Garmin contract probe. Never writes provider data or raw recordings.

Run with PYTHONPATH=.:backend. Output is a schema/count report, not a raw export.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import json
import logging
from math import isfinite
from pathlib import Path
import re
import sys
from time import monotonic
from typing import Protocol
from zipfile import BadZipFile, ZipFile


class GarminClient(Protocol):
    def get_activity(self, activity_id: str) -> dict: ...
    def get_activity_splits(self, activity_id: str) -> dict: ...
    def get_activity_typed_splits(self, activity_id: str) -> dict: ...
    def get_activity_split_summaries(self, activity_id: str) -> dict: ...
    def get_activity_hr_in_timezones(self, activity_id: str) -> list: ...
    def get_activity_details(self, activity_id: str, maxchart: int, maxpoly: int) -> dict: ...
    def download_activity(self, activity_id: str, dl_fmt) -> bytes: ...


# Values are NEVER copied by the schema walker. Also omit identifying/location fields.
_PRIVATE = re.compile(r'id$|uuid|name|token|secret|session_data|credential|password|cookie|auth|serial|latitude|longitude|position|polyline|coordinate|location|address|email|starttime|timestamp', re.I)
_FIELD = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
_METRIC = re.compile(r'^(?:direct|sum|uncorrected|corrected)[A-Z][A-Za-z0-9]{0,48}$')
_UNITS = {'s', 'ms', 'min', 'h', 'm', 'km', 'cm', 'mm', 'bpm', 'mps', 'kph', 'mph', 'watt', 'watts', 'rpm', 'spm', 'percent', 'degree', 'semicircles', 'celsius', 'count', 'bpm', 'second', 'meter'}
_RESOURCES = (
    ('summary', 'get_activity'), ('splits', 'get_activity_splits'),
    ('typed_splits', 'get_activity_typed_splits'), ('split_summaries', 'get_activity_split_summaries'),
    ('hr_zones', 'get_activity_hr_in_timezones'), ('details', 'get_activity_details'),
    ('fit', 'download_activity'),
)


def _ids(activity_ids: tuple[str, ...]) -> tuple[str, ...]:
    if not 1 <= len(activity_ids) <= 8 or any(not re.fullmatch(r'[1-9][0-9]{0,19}', a) for a in activity_ids):
        raise ValueError('Select between one and eight explicit positive activity IDs')
    return tuple(dict.fromkeys(activity_ids))


def _shape(payload) -> dict:
    fields: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    def walk(value, path='', depth=0):
        if depth > 8:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or not _FIELD.fullmatch(key) or _PRIVATE.search(key):
                    continue
                nested = f'{path}.{key}' if path else key
                fields.setdefault(nested, set()).add(type(child).__name__)
                walk(child, nested, depth + 1)
        elif isinstance(value, list):
            counts[path or '$'] = max(counts.get(path or '$', 0), len(value))
            for child in value[:2000]:
                walk(child, path + '[]', depth + 1)
    walk(payload)
    return {'fields': {key: sorted(value) for key, value in sorted(fields.items())},
            'collection_counts': counts}


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) else None


def _details(payload: dict) -> dict:
    rows = payload.get('activityDetailMetrics') or []
    descriptors = payload.get('metricDescriptors') or []
    metrics = []
    for descriptor in descriptors:
        key = descriptor.get('key', '')
        index = descriptor.get('metricsIndex')
        if not isinstance(key, str) or not _METRIC.fullmatch(key) or _PRIVATE.search(key):
            continue
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            continue
        unit = descriptor.get('unit') or {}
        unit_key = unit.get('key') if isinstance(unit, dict) else unit
        present = sum(isinstance(r, dict) and isinstance(r.get('metrics'), list)
                      and index < len(r['metrics']) and _number(r['metrics'][index]) is not None for r in rows)
        metrics.append({'index': index, 'key': key, 'unit': unit_key if unit_key in _UNITS else 'unverified',
                        'factor': _number(unit.get('factor')) if isinstance(unit, dict) else None,
                        'present': present, 'missing': len(rows) - present})
    return {'sample_count': len(rows), 'metrics': metrics, 'sampling': 'chart',
            'complete_recording_verified': False}


def _fit_summary(archive: bytes) -> dict:
    """Decode in memory; only field presence/counts escape this function."""
    if len(archive) > 20 * 1024 * 1024:
        return {'status': 'size_limited'}
    try:
        with ZipFile(BytesIO(archive)) as zipped:
            members = zipped.infolist()
            if len(members) > 20 or sum(m.file_size for m in members) > 100 * 1024 * 1024:
                return {'status': 'size_limited'}
            recordings = [m for m in members if not m.is_dir() and m.filename.lower().endswith('.fit')]
            if not recordings:
                return {'status': 'no_fit_recording'}
            from garmin_fit_sdk import Decoder, Stream
            reports = []
            for member in recordings:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    data = bytearray(zipped.read(member))
                    integrity = Decoder(Stream.from_byte_array(data)).check_integrity()
                    # Integrity checking consumes the SDK stream; decode from a fresh one.
                    messages, errors = Decoder(Stream.from_byte_array(data)).read()
                report = {'integrity': bool(integrity), 'decode_error_count': len(errors),
                          'message_counts': {}, 'message_fields': {}}
                # Deliberately exclude device/file/user messages (identity-rich).
                for name in ('session_mesgs', 'lap_mesgs', 'record_mesgs', 'event_mesgs', 'workout_mesgs', 'workout_step_mesgs'):
                    items = messages.get(name, [])
                    report['message_counts'][name] = len(items)
                    report['message_fields'][name] = sorted({k for item in items for k in item
                                                            if isinstance(k, str) and _FIELD.fullmatch(k) and not _PRIVATE.search(k)})
                laps = messages.get('lap_mesgs', [])
                report['laps_with_step_index'] = sum(m.get('wkt_step_index') is not None for m in laps)
                report['lap_triggers'] = dict(Counter(m['lap_trigger'] for m in laps if m.get('lap_trigger') in
                                                     {'manual', 'time', 'distance', 'session_end', 'fitness_equipment', 'position_start', 'position_lap', 'position_waypoint', 'position_marked'}))
                report['timer_event_count'] = sum(m.get('event') == 'timer' for m in messages.get('event_mesgs', []))
                reports.append(report)
            return {'status': 'available' if all(r['integrity'] and not r['decode_error_count'] for r in reports) else 'partial',
                    'recordings': reports}
    except (BadZipFile, EOFError, ValueError):
        return {'status': 'invalid_archive'}


def _error_category(exc: Exception) -> str:
    from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return 'rate_limited'
    if isinstance(exc, GarminConnectAuthenticationError):
        return 'authentication_failed'
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', None)
    return {429: 'rate_limited', 401: 'authentication_failed', 403: 'access_denied', 404: 'unavailable'}.get(status, 'failed')


def probe_activity_details(*, client: GarminClient, activity_ids: tuple[str, ...]) -> dict:
    activity_ids = _ids(activity_ids)
    report = {'schema_version': 'activity-detail-probe-v1', 'samples': [], 'stop_reason': None}
    for index, activity_id in enumerate(activity_ids, 1):
        resources = {}
        report['samples'].append({'sample_id': f'sample-{index}', 'resources': resources})
        for resource, method in _RESOURCES:
            start = monotonic()
            try:
                if resource == 'details':
                    payload = client.get_activity_details(activity_id, maxchart=2000, maxpoly=0)
                elif resource == 'fit':
                    payload = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
                else:
                    payload = getattr(client, method)(activity_id)
                if resource == 'fit':
                    result = _fit_summary(payload)
                    size = len(payload)
                else:
                    result = {'status': 'available' if payload else 'empty', **_shape(payload)}
                    if resource == 'details':
                        result.update(_details(payload))
                    size = len(json.dumps(payload).encode())
                result['payload_bytes'] = size  # SDK-decoded/JSON serialized size, not HTTP wire size.
            except Exception as exc:
                result = {'status': _error_category(exc)}  # Never expose exception message/URL.
            result['elapsed_ms'] = round((monotonic() - start) * 1000)
            resources[resource] = result
            if result['status'] in {'rate_limited', 'authentication_failed', 'access_denied'}:
                report['stop_reason'] = result['status']
                return report
    return report


def load_probe_client(*, user_id: str, activity_ids: tuple[str, ...], session_factory=None, cipher=None, garmin_factory=None):
    """Authorize every explicit ID before decrypting/login; no database writes."""
    from sqlalchemy import select, text
    from src.infrastructure.database.models import ActivityModel, IntegrationConnectionModel, IntegrationCredentialModel
    from src.infrastructure.database.session import create_session_factory, load_local_env
    from src.infrastructure.security.integration_credentials import load_garmin_credential_cipher
    from garminconnect import Garmin
    activity_ids = _ids(activity_ids)
    load_local_env()
    factory = session_factory or create_session_factory()
    with factory() as session:
        if session.bind.dialect.name == 'postgresql':
            session.execute(text('SET TRANSACTION READ ONLY'))
        rows = session.execute(select(ActivityModel.provider_activity_id, ActivityModel.provider_connection_id)
                               .where(ActivityModel.user_id == user_id, ActivityModel.provider_activity_id.in_(activity_ids))).all()
        connection_ids = {r[1] for r in rows}
        if {r[0] for r in rows} != set(activity_ids) or len(connection_ids) != 1 or None in connection_ids:
            raise ValueError('Activities must belong to one connected account owned by this user')
        connection = session.scalar(select(IntegrationConnectionModel).where(
            IntegrationConnectionModel.id == next(iter(connection_ids)), IntegrationConnectionModel.user_id == user_id,
            IntegrationConnectionModel.provider == 'garmin_connect', IntegrationConnectionModel.status == 'active',
            IntegrationConnectionModel.credential_status == 'active'))
        if connection is None or connection.sync_status == 'running':
            raise ValueError('Connection unavailable or currently syncing')
        credential = session.scalar(select(IntegrationCredentialModel).where(
            IntegrationCredentialModel.integration_connection_id == connection.id))
        if credential is None:
            raise ValueError('Connection has no credential')
        encrypted = credential.encrypted_payload
        is_cn = (connection.provider_metadata or {}).get('region') == 'china'
    tokenstore = (cipher or load_garmin_credential_cipher()).decrypt(encrypted)
    client = (garmin_factory or Garmin)(is_cn=is_cn, return_on_mfa=True)
    mfa_status, _ = client.login(tokenstore)
    if mfa_status:
        raise ValueError('Manual reauthentication required')
    return client


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--activity-id', action='append', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    # Library debug logging can contain authentication or personal information.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        ids = _ids(tuple(args.activity_id))
        client = load_probe_client(user_id=args.user_id, activity_ids=ids)
        report = probe_activity_details(client=client, activity_ids=ids)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(f"Probe report written: {len(report['samples'])} sample(s)")
        return 0 if report['stop_reason'] is None else 2
    except Exception:
        print('Probe failed; no credential or provider exception details are logged.', file=sys.stderr)
        return 1
    finally:
        logging.disable(previous)


if __name__ == '__main__':
    raise SystemExit(main())
