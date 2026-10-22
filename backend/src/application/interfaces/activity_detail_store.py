"""Persistence interface for normalized, immutable activity evidence."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from src.domain.activity_details import DetailSnapshot, NormalizedDetails

if TYPE_CHECKING:
    from src.domain.activity_execution import ExecutionAnalysis


class ActivityDetailStore(Protocol):
    def save_snapshot(self, *, user_id: str, details: NormalizedDetails,
                      fetched_at: datetime) -> DetailSnapshot: ...

    def get_snapshots(self, user_id: str, activity_id: str) -> tuple[DetailSnapshot, ...]: ...

    def save_analysis(self, user_id: str, analysis: ExecutionAnalysis) -> str: ...
