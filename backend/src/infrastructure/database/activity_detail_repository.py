"""Store normalized provider evidence without changing imported activities."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.activity_details import (
    ActivitySampleChunk, ActivitySegment, DetailCoverage, DetailFetch, DetailSnapshot,
    NormalizedDetails,
)
from src.domain.coaching_fingerprints import canonical_fingerprint

from .models import (
    ActivityDetailFetchModel, ActivityDetailSnapshotModel, ActivityExecutionAnalysisModel,
    ActivityModel, ActivitySampleChunkModel, ActivitySegmentModel,
)

if TYPE_CHECKING:
    from src.domain.activity_execution import ExecutionAnalysis

_PRIVATE = re.compile(
    r'latitude|longitude|polyline|coordinate|gps|position|location|'
    r'secret|password|token|cookie|credential|serial|name|email|address|'
    r'athlete|user|device|identifier', re.I,
)
_RAW_SERIES = re.compile(r'samples?|records?|chart(?:data|values)|data(?:points|series)', re.I)
_RESOURCES = frozenset(('splits', 'typed_splits', 'split_summaries', 'hr_zones', 'details', 'fit'))


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _ensure_safe(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if (not isinstance(key, str) or _PRIVATE.search(key)
                    or key == 'id' or key.endswith(('Id', '_id'))):
                raise ValueError('sensitive activity detail field is not permitted')
            _ensure_safe(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _ensure_safe(child)


def _ensure_source_metadata(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _RAW_SERIES.search(key):
                raise ValueError('raw sample series must be stored only in sample chunks')
            _ensure_source_metadata(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _ensure_source_metadata(child)


class SqlAlchemyActivityDetailRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _owned_provider_activity(self, user_id: str, activity_id: str) -> ActivityModel:
        activity = self._session.scalar(select(ActivityModel).where(
            ActivityModel.id == activity_id, ActivityModel.user_id == user_id,
            ActivityModel.provider_connection_id.is_not(None),
            ActivityModel.provider_activity_id.is_not(None)))
        if activity is None:
            raise ValueError('owned provider activity is required')
        return activity

    def save_snapshot(self, *, user_id: str, details: NormalizedDetails,
                      fetched_at: datetime) -> DetailSnapshot:
        self._owned_provider_activity(user_id, details.activity_id)
        if details.resource not in _RESOURCES or not details.schema_version:
            raise ValueError('unsupported resource or schema version')
        if fetched_at.tzinfo is None:
            raise ValueError('fetched_at must have a timezone')
        if any(len(chunk.samples) > 2000 for chunk in details.sample_chunks):
            raise ValueError('sample chunk exceeds 2000 points')
        _ensure_safe(details.source_payload)
        _ensure_source_metadata(details.source_payload)
        _ensure_safe([segment.metadata for segment in details.segments])
        _ensure_safe([chunk.samples for chunk in details.sample_chunks])
        semantic_hash = canonical_fingerprint(details.to_payload())
        lookup = (ActivityDetailSnapshotModel.activity_id == details.activity_id,
                  ActivityDetailSnapshotModel.resource == details.resource,
                  ActivityDetailSnapshotModel.schema_version == details.schema_version,
                  ActivityDetailSnapshotModel.semantic_hash == semantic_hash)
        model = self._session.scalar(select(ActivityDetailSnapshotModel).where(*lookup))
        if model is None:
            # Nested transaction handles a concurrent writer winning the unique key.
            try:
                with self._session.begin_nested():
                    model = ActivityDetailSnapshotModel(
                        user_id=user_id, activity_id=details.activity_id, resource=details.resource,
                        schema_version=details.schema_version, semantic_hash=semantic_hash,
                        fetched_at=fetched_at, coverage=details.coverage.to_payload(),
                        source_payload=details.source_payload)
                    self._session.add(model)
                    self._session.flush()
                    self._session.add_all([
                        ActivitySegmentModel(user_id=user_id, snapshot_id=model.id, ordinal=ordinal,
                                             payload=segment.to_payload())
                        for ordinal, segment in enumerate(details.segments)
                    ])
                    self._session.add_all([
                        ActivitySampleChunkModel(user_id=user_id, snapshot_id=model.id,
                                                 ordinal=chunk.ordinal, sample_count=len(chunk.samples),
                                                 samples=list(chunk.samples))
                        for chunk in details.sample_chunks
                    ])
                    self._session.flush()
            except IntegrityError:
                model = self._session.scalar(select(ActivityDetailSnapshotModel).where(*lookup))
                if model is None:
                    raise
        fetch = self._session.scalar(select(ActivityDetailFetchModel).where(
            ActivityDetailFetchModel.user_id == user_id,
            ActivityDetailFetchModel.activity_id == details.activity_id,
            ActivityDetailFetchModel.resource == details.resource).with_for_update())
        if fetch is None:
            fetch = ActivityDetailFetchModel(user_id=user_id, activity_id=details.activity_id,
                                             resource=details.resource, status='available')
            self._session.add(fetch)
        if fetch.last_successful_sync_at is None or fetched_at >= _utc(fetch.last_successful_sync_at):
            fetch.status = 'available'
            fetch.current_snapshot_id = model.id
            fetch.last_successful_sync_at = fetched_at
            fetch.last_error_type = None
            fetch.retry_count = 0
            fetch.next_retry_at = None
        self._session.flush()
        return self._hydrate(model)

    def get_snapshots(self, user_id: str, activity_id: str) -> tuple[DetailSnapshot, ...]:
        activity = self._session.scalar(select(ActivityModel.id).where(
            ActivityModel.id == activity_id, ActivityModel.user_id == user_id))
        if activity is None:
            return ()
        models = self._session.scalars(select(ActivityDetailSnapshotModel).where(
            ActivityDetailSnapshotModel.user_id == user_id,
            ActivityDetailSnapshotModel.activity_id == activity_id).order_by(
                ActivityDetailSnapshotModel.fetched_at, ActivityDetailSnapshotModel.id)).all()
        return tuple(self._hydrate(model) for model in models)

    def get_fetch(self, user_id: str, activity_id: str, resource: str) -> DetailFetch | None:
        model = self._session.scalar(select(ActivityDetailFetchModel).where(
            ActivityDetailFetchModel.user_id == user_id,
            ActivityDetailFetchModel.activity_id == activity_id,
            ActivityDetailFetchModel.resource == resource))
        if model is None:
            return None
        return DetailFetch(id=model.id, user_id=model.user_id, activity_id=model.activity_id,
                           resource=model.resource, status=model.status,
                           current_snapshot_id=model.current_snapshot_id,
                           last_successful_sync_at=_utc(model.last_successful_sync_at),
                           last_error_type=model.last_error_type, retry_count=model.retry_count)

    def save_analysis(self, user_id: str, analysis: ExecutionAnalysis) -> str:
        self._owned_provider_activity(user_id, analysis.activity_id)
        ids = tuple(analysis.snapshot_ids)
        payload = analysis.to_payload()
        if not ids or len(set(ids)) != len(ids):
            raise ValueError('analysis needs distinct snapshot evidence')
        owned = set(self._session.scalars(select(ActivityDetailSnapshotModel.id).where(
            ActivityDetailSnapshotModel.user_id == user_id,
            ActivityDetailSnapshotModel.activity_id == analysis.activity_id,
            ActivityDetailSnapshotModel.id.in_(ids))).all())
        if owned != set(ids):
            raise ValueError('snapshot ownership mismatch')
        if analysis.prescription_revision_id is not None:
            from .models import WorkoutPrescriptionRevisionModel
            prescribed = self._session.scalar(select(WorkoutPrescriptionRevisionModel.id).where(
                WorkoutPrescriptionRevisionModel.user_id == user_id,
                WorkoutPrescriptionRevisionModel.id == analysis.prescription_revision_id))
            if prescribed is None:
                raise ValueError('prescription ownership mismatch')
        existing = self._session.scalar(select(ActivityExecutionAnalysisModel).where(
            ActivityExecutionAnalysisModel.user_id == user_id,
            ActivityExecutionAnalysisModel.fingerprint == analysis.fingerprint))
        if existing is not None:
            self._check_analysis_match(existing, analysis, ids, payload)
            return existing.id
        try:
            with self._session.begin_nested():
                model = ActivityExecutionAnalysisModel(user_id=user_id, activity_id=analysis.activity_id,
                    fingerprint=analysis.fingerprint, algorithm_version=analysis.algorithm_version,
                    prescription_revision_id=analysis.prescription_revision_id,
                    snapshot_ids=list(ids), payload=payload)
                self._session.add(model)
                self._session.flush()
                return model.id
        except IntegrityError:
            existing = self._session.scalar(select(ActivityExecutionAnalysisModel).where(
                ActivityExecutionAnalysisModel.user_id == user_id,
                ActivityExecutionAnalysisModel.fingerprint == analysis.fingerprint))
            if existing is None:
                raise
            self._check_analysis_match(existing, analysis, ids, payload)
            return existing.id

    @staticmethod
    def _check_analysis_match(model: ActivityExecutionAnalysisModel, analysis: ExecutionAnalysis,
                              ids: tuple[str, ...], payload: dict) -> None:
        if (model.activity_id != analysis.activity_id
                or model.algorithm_version != analysis.algorithm_version
                or model.prescription_revision_id != analysis.prescription_revision_id
                or tuple(model.snapshot_ids) != ids or model.payload != payload):
            raise ValueError('analysis fingerprint collision with different evidence')

    def _hydrate(self, model: ActivityDetailSnapshotModel) -> DetailSnapshot:
        segments = self._session.scalars(select(ActivitySegmentModel).where(
            ActivitySegmentModel.snapshot_id == model.id,
            ActivitySegmentModel.user_id == model.user_id).order_by(ActivitySegmentModel.ordinal)).all()
        chunks = self._session.scalars(select(ActivitySampleChunkModel).where(
            ActivitySampleChunkModel.snapshot_id == model.id,
            ActivitySampleChunkModel.user_id == model.user_id).order_by(ActivitySampleChunkModel.ordinal)).all()
        details = NormalizedDetails(activity_id=model.activity_id, resource=model.resource,
            schema_version=model.schema_version, coverage=DetailCoverage.from_payload(model.coverage),
            segments=tuple(ActivitySegment.from_payload(item.payload) for item in segments),
            sample_chunks=tuple(ActivitySampleChunk(ordinal=item.ordinal, samples=tuple(item.samples))
                                for item in chunks), source_payload=dict(model.source_payload))
        return DetailSnapshot(id=model.id, user_id=model.user_id, details=details,
                              semantic_hash=model.semantic_hash, fetched_at=_utc(model.fetched_at))
