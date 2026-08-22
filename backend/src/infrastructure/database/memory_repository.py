from __future__ import annotations

from sqlalchemy.orm import Session

from .models import MemoryItemModel


class SqlAlchemyMemoryCandidateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def store_memory_candidate(self, user_id: str, candidate: dict) -> dict:
        model = MemoryItemModel(
            user_id=user_id,
            memory_type=str(candidate["memory_type"]),
            content=str(candidate["summary"]),
            source="agent_candidate",
        )
        self._session.add(model)
        self._session.flush()
        return {
            "id": model.id,
            "user_id": model.user_id,
            "memory_type": model.memory_type,
            "summary": model.content,
            "source": model.source,
            "status": candidate.get("status", "pending"),
        }
