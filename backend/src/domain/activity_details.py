"""Versioned, owner-scoped activity detail evidence; no provider transport here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

DetailResource = Literal['splits', 'typed_splits', 'split_summaries', 'hr_zones', 'details', 'fit']
DetailState = Literal['complete', 'partial', 'unknown']
DetailSampling = Literal['recorded', 'chart', 'unknown']


@dataclass(frozen=True)
class DetailCoverage:
    state: DetailState
    sampling: DetailSampling
    covered_seconds: float | None = None
    missing_channels: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_payload(self) -> dict:
        return {'state': self.state, 'sampling': self.sampling,
                'covered_seconds': self.covered_seconds,
                'missing_channels': list(self.missing_channels), 'limitations': list(self.limitations)}

    @classmethod
    def from_payload(cls, payload: dict) -> DetailCoverage:
        return cls(state=payload['state'], sampling=payload['sampling'],
                   covered_seconds=payload.get('covered_seconds'),
                   missing_channels=tuple(payload.get('missing_channels') or ()),
                   limitations=tuple(payload.get('limitations') or ()))


@dataclass(frozen=True)
class ActivitySegment:
    source_index: int
    source_kind: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    timer_seconds: float | None = None
    elapsed_seconds: float | None = None
    distance_meters: float | None = None
    average_heart_rate_bpm: float | None = None
    average_pace_seconds_per_km: float | None = None
    step_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict:
        return {'source_index': self.source_index, 'source_kind': self.source_kind,
                'start_at': self.start_at.isoformat() if self.start_at else None,
                'end_at': self.end_at.isoformat() if self.end_at else None,
                'timer_seconds': self.timer_seconds, 'elapsed_seconds': self.elapsed_seconds,
                'distance_meters': self.distance_meters,
                'average_heart_rate_bpm': self.average_heart_rate_bpm,
                'average_pace_seconds_per_km': self.average_pace_seconds_per_km,
                'step_path': self.step_path, 'metadata': self.metadata}

    @classmethod
    def from_payload(cls, payload: dict) -> ActivitySegment:
        return cls(source_index=payload['source_index'], source_kind=payload['source_kind'],
                   start_at=datetime.fromisoformat(payload['start_at']) if payload.get('start_at') else None,
                   end_at=datetime.fromisoformat(payload['end_at']) if payload.get('end_at') else None,
                   timer_seconds=payload.get('timer_seconds'), elapsed_seconds=payload.get('elapsed_seconds'),
                   distance_meters=payload.get('distance_meters'),
                   average_heart_rate_bpm=payload.get('average_heart_rate_bpm'),
                   average_pace_seconds_per_km=payload.get('average_pace_seconds_per_km'),
                   step_path=payload.get('step_path'), metadata=dict(payload.get('metadata') or {}))


@dataclass(frozen=True)
class ActivitySampleChunk:
    ordinal: int
    samples: tuple[dict[str, Any], ...]

    def to_payload(self) -> dict:
        return {'ordinal': self.ordinal, 'samples': list(self.samples)}

    @classmethod
    def from_payload(cls, payload: dict) -> ActivitySampleChunk:
        return cls(ordinal=payload['ordinal'], samples=tuple(payload['samples']))


@dataclass(frozen=True)
class NormalizedDetails:
    activity_id: str
    resource: DetailResource
    schema_version: str
    coverage: DetailCoverage
    segments: tuple[ActivitySegment, ...] = ()
    sample_chunks: tuple[ActivitySampleChunk, ...] = ()
    source_payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict:
        return {'activity_id': self.activity_id, 'resource': self.resource,
                'schema_version': self.schema_version, 'coverage': self.coverage.to_payload(),
                'segments': [item.to_payload() for item in self.segments],
                'sample_chunks': [item.to_payload() for item in self.sample_chunks],
                'source_payload': self.source_payload}


@dataclass(frozen=True)
class DetailSnapshot:
    id: str
    user_id: str
    details: NormalizedDetails
    semantic_hash: str
    fetched_at: datetime

    @property
    def activity_id(self) -> str:
        return self.details.activity_id

    @property
    def resource(self) -> DetailResource:
        return self.details.resource

    @property
    def segments(self) -> tuple[ActivitySegment, ...]:
        return self.details.segments

    @property
    def sample_chunks(self) -> tuple[ActivitySampleChunk, ...]:
        return self.details.sample_chunks


@dataclass(frozen=True)
class DetailFetch:
    id: str
    user_id: str
    activity_id: str
    resource: DetailResource
    status: str
    current_snapshot_id: str | None
    last_successful_sync_at: datetime | None
    last_error_type: str | None = None
    retry_count: int = 0
