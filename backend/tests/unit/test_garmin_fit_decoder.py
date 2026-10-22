"""Original FIT evidence is validated and decoded without extracting ZIP members."""
from io import BytesIO
from datetime import datetime, timezone
from zipfile import ZIP_DEFLATED, ZipFile

from garmin_fit_sdk import Encoder
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.infrastructure.integrations.garmin_fit_decoder import decode_activity_fit
from src.infrastructure.integrations.garmin_activity_details import select_execution_evidence, normalize_activity_details
from src.infrastructure.database.activity_detail_repository import SqlAlchemyActivityDetailRepository
from src.infrastructure.database.models import ActivityModel, Base, IntegrationConnectionModel, UserModel


def _archive(messages, name='activity.fit'):
    encoder = Encoder()
    for message in messages:
        encoder.write_mesg(message)
    out = BytesIO()
    with ZipFile(out, 'w', compression=ZIP_DEFLATED) as zipped:
        zipped.writestr(name, encoder.close())
    return out.getvalue()


def _recording(with_steps=True):
    messages = [
        {'mesg_num': 21, 'timestamp': 1000000, 'event': 'timer', 'event_type': 'start'},
        {'mesg_num': 20, 'timestamp': 1000010, 'heart_rate': 130, 'speed': 2.5, 'distance': 10},
        {'mesg_num': 21, 'timestamp': 1000300, 'event': 'timer', 'event_type': 'stop_all'},
        {'mesg_num': 20, 'timestamp': 1000310, 'speed': 0, 'distance': 300},
        {'mesg_num': 21, 'timestamp': 1000360, 'event': 'timer', 'event_type': 'start'},
        {'mesg_num': 20, 'timestamp': 1000370, 'heart_rate': 140, 'speed': 3, 'distance': 310},
        {'mesg_num': 21, 'timestamp': 1000540, 'event': 'timer', 'event_type': 'stop_all'},
        {'mesg_num': 19, 'start_time': 1000000, 'timestamp': 1000300,
         'total_timer_time': 300, 'total_elapsed_time': 300, 'total_distance': 300,
         'lap_trigger': 'manual', 'wkt_step_index': 1},
        {'mesg_num': 19, 'start_time': 1000360, 'timestamp': 1000540,
         'total_timer_time': 180, 'total_elapsed_time': 180, 'total_distance': 200,
         'lap_trigger': 'manual', 'wkt_step_index': 1},
    ]
    if with_steps:
        messages.append({'mesg_num': 27, 'message_index': 1, 'duration_type': 'time',
                         'duration_value': 180000, 'target_type': 'open'})
    return _archive(messages)


def test_fit_timer_events_pause_samples_and_repeated_step_occurrences():
    result = decode_activity_fit(activity_id='a', archive=_recording())
    assert result.coverage.sampling == 'recorded'
    assert result.coverage.state == 'partial'  # sparse synthetic record stream
    assert [segment.step_path for segment in result.segments] == ['fit_step/1', 'fit_step/1']
    assert [segment.metadata['repeat_occurrence'] for segment in result.segments] == [1, 2]
    assert [segment.timer_seconds for segment in result.segments] == [300, 180]
    samples = result.sample_chunks[0].samples
    assert [sample['timer_running'] for sample in samples] == [True, False, True]
    assert samples[1].get('pace_seconds_per_km') is None
    assert samples[1].get('heart_rate_bpm') is None
    assert all('position' not in str(sample) for sample in samples)


def test_lap_step_index_without_workout_steps_is_not_exact_mapping():
    result = decode_activity_fit(activity_id='a', archive=_recording(with_steps=False))
    assert all(segment.step_path is None for segment in result.segments)
    assert 'workout_steps_unverified' in result.coverage.limitations


def test_automatic_distance_lap_is_not_exact_step_even_with_index():
    archive = _archive([
        {'mesg_num': 27, 'message_index': 1, 'duration_type': 'time',
         'duration_value': 180000, 'target_type': 'open'},
        {'mesg_num': 19, 'total_timer_time': 180, 'total_distance': 1000,
         'lap_trigger': 'distance', 'wkt_step_index': 1},
    ])
    result = decode_activity_fit(activity_id='a', archive=archive)
    assert result.segments[0].step_path is None


def test_timed_lap_needs_matching_explicit_workout_duration_for_step_link():
    archive = _archive([
        {'mesg_num': 27, 'message_index': 1, 'duration_type': 'time',
         'duration_value': 180000, 'target_type': 'open'},
        {'mesg_num': 19, 'total_timer_time': 60, 'lap_trigger': 'time', 'wkt_step_index': 1},
        {'mesg_num': 19, 'total_timer_time': 180, 'lap_trigger': 'time', 'wkt_step_index': 1},
    ])
    result = decode_activity_fit(activity_id='a', archive=archive)
    assert [segment.step_path for segment in result.segments] == [None, 'fit_step/1']


def test_fit_recorded_channels_win_over_json_overlap_without_double_counting():
    fit = decode_activity_fit(activity_id='a', archive=_recording())
    json_laps = normalize_activity_details(activity_id='a', resource='splits', payload={
        'lapDTOs': [{'duration': 300, 'distance': 300}, {'duration': 180, 'distance': 200}]})
    selected = select_execution_evidence((json_laps, fit))
    assert selected.segment_resource == 'fit'
    assert selected.sample_resource == 'fit'
    assert len(selected.segments) == 2
    assert sum(segment.distance_meters or 0 for segment in selected.segments) == 500


def test_unverified_chart_factor_cannot_override_decoded_fit_speed():
    fit = decode_activity_fit(activity_id='a', archive=_recording())
    chart = normalize_activity_details(activity_id='a', resource='details', payload={
        'metricDescriptors': [
            {'metricsIndex': 1, 'key': 'directSpeed', 'unit': {'key': 'mps', 'factor': 0.1}},
            {'metricsIndex': 0, 'key': 'sumElapsedDuration',
             'unit': {'key': 'second', 'factor': 1000}},
        ], 'activityDetailMetrics': [{'metrics': [10000, 25]},
                                     {'metrics': [310000, 0]}, {'metrics': [370000, 30]}]})
    fit_points = fit.sample_chunks[0].samples
    chart_points = chart.sample_chunks[0].samples
    assert chart_points[0]['raw_elapsed_value'] == 10000
    assert chart_points[0]['raw_speed_value'] == 25
    assert chart_points[0].get('speed_mps') is None
    assert fit_points[0]['elapsed_seconds'] == 10
    assert fit_points[0]['speed_mps'] == 2.5
    assert select_execution_evidence((chart, fit)).sample_resource == 'fit'
    assert chart.coverage.state == 'partial'


def test_corrupt_fit_returns_unknown_coverage_without_samples():
    out = BytesIO()
    with ZipFile(out, 'w') as zipped:
        zipped.writestr('activity.fit', b'not fit bytes')
    result = decode_activity_fit(activity_id='a', archive=out.getvalue())
    assert result.coverage.state == 'unknown'
    assert not result.sample_chunks and not result.segments


def test_archive_traversal_and_member_limits_are_rejected_before_decode():
    traversal = _archive([{'mesg_num': 20, 'timestamp': 1000000, 'heart_rate': 130}], '../escape.fit')
    assert decode_activity_fit(activity_id='a', archive=traversal).coverage.state == 'unknown'
    out = BytesIO()
    with ZipFile(out, 'w') as zipped:
        for index in range(21):
            zipped.writestr(f'{index}.fit', b'x')
    limited = decode_activity_fit(activity_id='a', archive=out.getvalue())
    assert limited.coverage.state == 'unknown'
    assert 'archive_limit' in limited.coverage.limitations


def test_normalized_fit_and_json_can_be_saved_as_separate_immutable_resources(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'details.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(UserModel(id='owner', email='owner@example.invalid', display_name='Owner'))
        session.flush()
        session.add(IntegrationConnectionModel(id='conn', user_id='owner', provider='garmin_connect'))
        session.flush()
        session.add(ActivityModel(id='activity', user_id='owner', provider_connection_id='conn',
                                  provider_activity_id='123', started_at=now, activity_type='running'))
        session.flush()
        repo = SqlAlchemyActivityDetailRepository(session)
        fit = decode_activity_fit(activity_id='activity', archive=_recording())
        chart = normalize_activity_details(activity_id='activity', resource='details', payload={
            'metricDescriptors': [{'metricsIndex': 0, 'key': 'sumDuration',
                                   'unit': {'key': 'second', 'factor': 1000}}],
            'activityDetailMetrics': [{'metrics': [1000]}]})
        fit_row = repo.save_snapshot(user_id='owner', details=fit, fetched_at=now)
        chart_row = repo.save_snapshot(user_id='owner', details=chart, fetched_at=now)
        session.commit()
        assert fit_row.id != chart_row.id
        assert {row.resource for row in repo.get_snapshots('owner', 'activity')} == {'fit', 'details'}
    engine.dispose()
