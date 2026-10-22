"""Decode one bounded original Garmin FIT recording in memory.

Only workout/lap/timer/physiology fields leave the decoder. Location, device and
identity messages are never copied into normalized evidence.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from math import isfinite
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from src.domain.activity_details import ActivitySampleChunk, ActivitySegment, DetailCoverage, NormalizedDetails

SCHEMA_VERSION = 'garmin-fit-v1'
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_MEMBERS = 20
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_SAMPLE_CHUNK = 2000


def _unknown(activity_id: str, reason: str) -> NormalizedDetails:
    return NormalizedDetails(activity_id=activity_id, resource='fit', schema_version=SCHEMA_VERSION,
        coverage=DetailCoverage(state='unknown', sampling='unknown', limitations=(reason,)))


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    return float(value)


def _time(value) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not (path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name)


def _read_fit(archive: bytes) -> tuple[dict, list] | str:
    if not isinstance(archive, bytes) or len(archive) > MAX_ARCHIVE_BYTES:
        return 'archive_limit'
    try:
        with ZipFile(BytesIO(archive)) as zipped:
            members = zipped.infolist()
            if (len(members) > MAX_MEMBERS or
                    sum(member.file_size for member in members) > MAX_UNCOMPRESSED_BYTES):
                return 'archive_limit'
            if any(not _safe_member(member.filename) for member in members):
                return 'unsafe_archive_path'
            recordings = [member for member in members if not member.is_dir()
                          and member.filename.lower().endswith('.fit')]
            if len(recordings) != 1:
                return 'fit_recording_count_unverified'
            with zipped.open(recordings[0]) as stream:
                data = stream.read(MAX_UNCOMPRESSED_BYTES + 1)
            if len(data) > MAX_UNCOMPRESSED_BYTES:
                return 'archive_limit'
        from garmin_fit_sdk import Decoder, Stream
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            if not Decoder(Stream.from_byte_array(bytearray(data))).check_integrity():
                return 'fit_integrity_failed'
            # check_integrity consumes the stream in the pinned SDK version.
            messages, errors = Decoder(Stream.from_byte_array(bytearray(data))).read()
        return messages, errors
    except (BadZipFile, EOFError, ValueError, KeyError, RuntimeError):
        return 'invalid_fit_archive'


def _timer_intervals(events: list[dict]) -> tuple[tuple[tuple[datetime, datetime], ...], bool]:
    timer_events = sorted(((_time(event.get('timestamp')), event.get('event_type')) for event in events
                           if isinstance(event, dict) and event.get('event') == 'timer'),
                          key=lambda item: item[0] or datetime.max.replace(tzinfo=timezone.utc))
    intervals: list[tuple[datetime, datetime]] = []
    opened: datetime | None = None
    incomplete = False
    for at, kind in timer_events:
        if at is None:
            incomplete = True
            continue
        if kind == 'start':
            if opened is not None:
                incomplete = True
            opened = at
        elif kind in ('stop', 'stop_all'):
            if opened is None or at < opened:
                incomplete = True
            else:
                intervals.append((opened, at))
                opened = None
    return tuple(intervals), incomplete or opened is not None or not timer_events


def _laps(messages: dict) -> tuple[ActivitySegment, ...]:
    steps = {row['message_index']: row for row in messages.get('workout_step_mesgs', ())
             if isinstance(row, dict) and isinstance(row.get('message_index'), int)}
    occurrences: dict[int, int] = {}
    segments: list[ActivitySegment] = []
    for index, lap in enumerate(messages.get('lap_mesgs', ())):
        if not isinstance(lap, dict):
            continue
        step_index = lap.get('wkt_step_index')
        step_path = None
        metadata = {}
        trigger = lap.get('lap_trigger')
        planned = steps.get(step_index) if isinstance(step_index, int) else None
        timer = _number(lap.get('total_timer_time'))
        timed_step_matches = (planned is not None and trigger == 'time'
            and planned.get('duration_type') == 'time'
            and (planned_seconds := _number(planned.get('duration_time'))) is not None
            and timer is not None and abs(planned_seconds - timer) <= 5)
        if planned is not None and (trigger == 'manual' or timed_step_matches):
            occurrences[step_index] = occurrences.get(step_index, 0) + 1
            step_path = f'fit_step/{step_index}'
            metadata['repeat_occurrence'] = occurrences[step_index]
        if trigger in ('manual', 'time', 'distance', 'session_end'):
            metadata['lap_trigger'] = trigger
        start = _time(lap.get('start_time'))
        end = _time(lap.get('timestamp'))
        elapsed = _number(lap.get('total_elapsed_time'))
        if start is None and end is not None and elapsed is not None:
            start = end - timedelta(seconds=elapsed)
        speed = _number(lap.get('enhanced_avg_speed')) or _number(lap.get('avg_speed'))
        segments.append(ActivitySegment(source_index=index, source_kind='fit_lap',
            start_at=start, end_at=end, timer_seconds=timer,
            elapsed_seconds=elapsed, distance_meters=_number(lap.get('total_distance')),
            average_heart_rate_bpm=_number(lap.get('avg_heart_rate')),
            average_pace_seconds_per_km=1000 / speed if speed and speed > 0 else None,
            step_path=step_path, metadata=metadata))
    return tuple(segments)


def _records(messages: dict, intervals: tuple[tuple[datetime, datetime], ...]) -> tuple[tuple[ActivitySampleChunk, ...], bool]:
    records = [(index, _time(row.get('timestamp')), row) for index, row in
               enumerate(messages.get('record_mesgs', ())) if isinstance(row, dict)]
    records = [(index, at, row) for index, at, row in records if at is not None]
    records.sort(key=lambda item: (item[1], item[0]))
    origin = intervals[0][0] if intervals else records[0][1] if records else None
    samples = []
    for _, at, row in records:
        sample = {'at': at.isoformat(), 'elapsed_seconds': (at - origin).total_seconds(),
                  'timer_running': any(start <= at < end for start, end in intervals)}
        for source, target in (('heart_rate', 'heart_rate_bpm'), ('distance', 'distance_meters'),
                               ('enhanced_speed', 'speed_mps')):
            if (value := _number(row.get(source))) is not None:
                sample[target] = value
        if 'speed_mps' not in sample and (speed := _number(row.get('speed'))) is not None:
            sample['speed_mps'] = speed
        if (speed := sample.get('speed_mps')) is not None and speed > 0:
            sample['pace_seconds_per_km'] = 1000 / speed
        samples.append(sample)
    chunks = tuple(ActivitySampleChunk(ordinal=index // MAX_SAMPLE_CHUNK,
        samples=tuple(samples[index:index + MAX_SAMPLE_CHUNK]))
        for index in range(0, len(samples), MAX_SAMPLE_CHUNK))
    gap = False
    for start, end in intervals:
        times = [at for _, at, _ in records if start <= at < end]
        if not times or (times[0] - start).total_seconds() > 30 or (end - times[-1]).total_seconds() > 30:
            gap = True
        if any((right - left).total_seconds() > 30 for left, right in zip(times, times[1:])):
            gap = True
    return chunks, gap


def decode_activity_fit(*, activity_id: str, archive: bytes) -> NormalizedDetails:
    decoded = _read_fit(archive)
    if isinstance(decoded, str):
        return _unknown(activity_id, decoded)
    messages, errors = decoded
    if errors:
        return _unknown(activity_id, 'fit_decode_errors')
    intervals, timer_incomplete = _timer_intervals(messages.get('event_mesgs', []))
    segments = _laps(messages)
    chunks, record_gaps = _records(messages, intervals)
    limitations = []
    if timer_incomplete:
        limitations.append('timer_events_incomplete')
    if record_gaps:
        limitations.append('record_gaps')
    if not messages.get('workout_step_mesgs') and any(
            isinstance(lap, dict) and lap.get('wkt_step_index') is not None
            for lap in messages.get('lap_mesgs', ())):
        limitations.append('workout_steps_unverified')
    if not chunks:
        limitations.append('record_samples_missing')
    state = 'complete' if chunks and intervals and not timer_incomplete and not record_gaps else 'partial'
    return NormalizedDetails(activity_id=activity_id, resource='fit', schema_version=SCHEMA_VERSION,
        coverage=DetailCoverage(state=state, sampling='recorded',
            covered_seconds=sum((end - start).total_seconds() for start, end in intervals)
                            if intervals else None, limitations=tuple(limitations)),
        segments=segments, sample_chunks=chunks,
        source_payload={'lap_count': len(messages.get('lap_mesgs', ())),
                        'fit_message_count': len(messages.get('record_mesgs', ())),
                        'timer_event_count': sum(isinstance(event, dict) and event.get('event') == 'timer'
                                                 for event in messages.get('event_mesgs', ()))})
