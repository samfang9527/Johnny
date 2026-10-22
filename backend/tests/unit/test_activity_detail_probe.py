"""Probe boundary tests: secrets/owner escape, unsupported resources and chart fidelity."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'backend/tests/fixtures/activity_details/synthetic_details.json'


def probe_module():
    path = ROOT / 'scripts/probe_activity_details.py'
    assert path.exists(), 'bounded activity detail probe has not been implemented'
    spec = importlib.util.spec_from_file_location('activity_probe_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReadOnlyClient:
    """External boundary only; unexpected mutation/list calls fail immediately."""
    ActivityDownloadFormat = SimpleNamespace(ORIGINAL='original')

    def get_activity(self, activity_id):
        return {'activityId': int(activity_id), 'summaryDTO': {'duration': 2, 'elapsedDuration': 3}}

    def get_activity_splits(self, activity_id):
        return {'lapDTOs': [{'lapIndex': 1, 'duration': 2, 'distance': 10}]}

    def get_activity_typed_splits(self, activity_id):
        return {'splitsMap': {}}

    def get_activity_split_summaries(self, activity_id):
        return {'splitSummaries': []}

    def get_activity_hr_in_timezones(self, activity_id):
        return [{'zoneNumber': 1, 'secsInZone': 2}]

    def get_activity_details(self, activity_id, maxchart=2000, maxpoly=0):
        assert maxpoly == 0, 'probe must not request polyline points'
        return json.loads(FIXTURE.read_text())

    def download_activity(self, activity_id, dl_fmt):
        assert dl_fmt == 'original', 'default TCX is not an original FIT recording'
        return b'not a ZIP'

    def __getattr__(self, name):
        raise AssertionError(f'Unexpected client access: {name}')


def test_probe_redacts_identifiers_and_tracks():
    result = probe_module().probe_activity_details(client=ReadOnlyClient(), activity_ids=('111111111',))
    serialized = json.dumps(result)
    for private in ('111111111', 'PRIVATE', 'session_data', 'geoPolyline', '121.55555', '2000-01-01'):
        assert private not in serialized
    sample = result['samples'][0]
    assert sample['sample_id'] == 'sample-1'
    detail = sample['resources']['details']
    assert detail['status'] == 'available'
    assert detail['sample_count'] == 3
    assert detail['sampling'] == 'chart'
    assert detail['complete_recording_verified'] is False
    assert detail['metrics'][0] == {'index': 2, 'key': 'directHeartRate', 'unit': 'bpm', 'factor': 1.0, 'present': 2, 'missing': 1}
    assert detail['metrics'][1]['factor'] == 1000.0
    assert len(detail['metrics']) == 2


def test_probe_calls_read_methods_only():
    result = probe_module().probe_activity_details(client=ReadOnlyClient(), activity_ids=('123',))
    resources = result['samples'][0]['resources']
    assert set(resources) == {'summary', 'splits', 'typed_splits', 'split_summaries', 'hr_zones', 'details', 'fit'}
    assert resources['splits']['collection_counts']['lapDTOs'] == 1
    assert resources['fit']['status'] == 'invalid_archive'


def test_partial_resource_does_not_abort_report():
    class Partial(ReadOnlyClient):
        def get_activity_typed_splits(self, activity_id):
            raise RuntimeError('private URL?token=DO NOT LOG')
    result = probe_module().probe_activity_details(client=Partial(), activity_ids=('123',))
    resources = result['samples'][0]['resources']
    assert resources['typed_splits']['status'] == 'failed'
    assert resources['details']['sample_count'] == 3
    assert 'DO NOT LOG' not in json.dumps(result)


@pytest.mark.parametrize('ids', [(), ('0',), ('abc',), ('1',)*9])
def test_probe_rejects_unbounded_or_invalid_requests(ids):
    with pytest.raises(ValueError):
        probe_module().probe_activity_details(client=ReadOnlyClient(), activity_ids=ids)


def test_rate_limit_stops_further_calls_including_next_activity():
    from garminconnect import GarminConnectTooManyRequestsError
    class Limited(ReadOnlyClient):
        def get_activity_splits(self, activity_id):
            raise GarminConnectTooManyRequestsError('secret')
        def get_activity_details(self, *args, **kwargs):
            pytest.fail('must stop after rate limit')
    result = probe_module().probe_activity_details(client=Limited(), activity_ids=('123', '456'))
    assert result['stop_reason'] == 'rate_limited'
    assert len(result['samples']) == 1
    assert result['samples'][0]['resources']['splits']['status'] == 'rate_limited'


def test_cli_failure_does_not_emit_credentials_or_write_report(tmp_path, monkeypatch, capsys):
    module = probe_module()
    def fail(**kwargs):
        raise RuntimeError('DATABASE password PRIVATE SESSION')
    monkeypatch.setattr(module, 'load_probe_client', fail)
    output = tmp_path / 'report.json'
    assert module.main(['--user-id', 'u', '--activity-id', '123', '--output', str(output)]) == 1
    assert 'PRIVATE' not in capsys.readouterr().err
    assert not output.exists()


def synthetic_fit_zip():
    from garmin_fit_sdk import Encoder
    from io import BytesIO
    from zipfile import ZipFile
    encoder = Encoder()
    encoder.write_mesg({'mesg_num': 0, 'type': 'activity', 'manufacturer': 'garmin', 'serial_number': 999999})
    encoder.write_mesg({'mesg_num': 20, 'timestamp': 1000000, 'heart_rate': 130, 'distance': 10, 'position_lat': 10000})
    encoder.write_mesg({'mesg_num': 19, 'total_timer_time': 2, 'lap_trigger': 'manual', 'wkt_step_index': 0})
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('private-athlete-activity.fit', encoder.close())
    return output.getvalue()


def test_integrity_check_does_not_consume_recording_before_decode():
    class WithFit(ReadOnlyClient):
        def download_activity(self, activity_id, dl_fmt):
            return synthetic_fit_zip()
    result = probe_module().probe_activity_details(client=WithFit(), activity_ids=('123',))
    fit = result['samples'][0]['resources']['fit']
    assert fit['status'] == 'available'
    recording = fit['recordings'][0]
    assert recording['integrity'] is True
    assert recording['message_counts']['record_mesgs'] == 1
    assert recording['laps_with_step_index'] == 1
    assert recording['lap_triggers'] == {'manual': 1}
    assert 'position_lat' not in json.dumps(fit)
    assert 'private-athlete' not in json.dumps(fit)


@pytest.fixture
def probe_database(tmp_path):
    from datetime import datetime, timezone
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.infrastructure.database.models import Base, UserModel, ActivityModel, IntegrationConnectionModel, IntegrationCredentialModel
    engine = create_engine(f'sqlite:///{tmp_path / "probe.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as s:
        s.add_all([UserModel(id='owner', email='owner@example.invalid', display_name='Owner'),
                   UserModel(id='other', email='other@example.invalid', display_name='Other')])
        s.flush()
        s.add(IntegrationConnectionModel(id='conn', user_id='owner', provider='garmin_connect'))
        s.flush()
        s.add(IntegrationCredentialModel(id='cred', integration_connection_id='conn', credential_format='garminconnect-session-json', encrypted_payload='encrypted', key_id='test'))
        s.add(ActivityModel(id='activity', user_id='owner', provider_connection_id='conn', provider_activity_id='123', started_at=datetime(2000,1,1,tzinfo=timezone.utc), activity_type='running'))
    yield factory
    engine.dispose()


def test_probe_checks_ownership_before_decrypting_or_logging_in(probe_database):
    class ForbiddenCipher:
        def decrypt(self, value):
            pytest.fail('foreign user must never reach the credential boundary')
    with pytest.raises(ValueError, match='owned by this user'):
        probe_module().load_probe_client(user_id='other', activity_ids=('123',), session_factory=probe_database, cipher=ForbiddenCipher())


def test_client_login_does_not_update_saved_session_or_activity(probe_database):
    from sqlalchemy import select
    from src.infrastructure.database.models import IntegrationCredentialModel, ActivityModel
    client = ReadOnlyClient()
    client.login = lambda token: (None, None)
    loaded = probe_module().load_probe_client(user_id='owner', activity_ids=('123',), session_factory=probe_database,
        cipher=SimpleNamespace(decrypt=lambda value: 'ephemeral token'), garmin_factory=lambda **kwargs: client)
    assert loaded is client
    with probe_database() as s:
        assert s.scalar(select(IntegrationCredentialModel)).encrypted_payload == 'encrypted'
        assert s.scalar(select(ActivityModel)).provider_summary == {}


def test_fit_archive_member_limit_does_not_decode_or_extract():
    from io import BytesIO
    from zipfile import ZipFile
    output = BytesIO()
    with ZipFile(output, 'w') as z:
        for i in range(21):
            z.writestr(f'../../private-{i}.fit', b'not a recording')
    class Oversized(ReadOnlyClient):
        def download_activity(self, activity_id, dl_fmt):
            return output.getvalue()
    result = probe_module().probe_activity_details(client=Oversized(), activity_ids=('123',))
    assert result['samples'][0]['resources']['fit']['status'] == 'size_limited'


def test_fit_unknown_numeric_field_does_not_discard_valid_recording():
    import struct
    from io import BytesIO
    from zipfile import ZipFile
    from garmin_fit_sdk import CrcCalculator
    # A record message with known HR field 3 and unknown field 254, both uint8.
    data = b'\x40\x00\x00' + struct.pack('<H', 20) + b'\x02\x03\x01\x02\xfe\x01\x02\x00\x82\x01'
    header = struct.pack('<BBHI4s', 12, 16, 2180, len(data), b'.FIT')
    raw = header + data
    raw += struct.pack('<H', CrcCalculator.calculate_crc(raw, 0, len(raw)))
    archive = BytesIO()
    with ZipFile(archive, 'w') as z:
        z.writestr('sample.fit', raw)
    class UnknownField(ReadOnlyClient):
        def download_activity(self, activity_id, dl_fmt):
            return archive.getvalue()
    result = probe_module().probe_activity_details(client=UnknownField(), activity_ids=('123',))
    fit = result['samples'][0]['resources']['fit']
    assert fit['status'] == 'available'
    assert fit['recordings'][0]['message_counts']['record_mesgs'] == 1
    assert 'heart_rate' in fit['recordings'][0]['message_fields']['record_mesgs']
