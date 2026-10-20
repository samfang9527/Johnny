"""Independent retrospective review and athlete-requested workout advice APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiConflictError, ApiNotFoundError
from src.api.schemas.agent_runs import QueuedAgentRunResponse
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.api.schemas.johnny import WorkoutAdviceRequest
from src.application.async_agent_runs import QueueAgentRunHandler
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import (
    AgentRunModel, AgentTaskModel, AthleteProfileModel, RecommendationModel,
    TrainingReviewModel, WorkoutAdviceModel, WorkoutAdviceRevisionModel,
)
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.llm.settings import resolve_queued_training_plan_provider


router = APIRouter(prefix="/johnny", tags=["johnny"])


def _local_context(session, user_id: str):
    profile = session.scalar(select(AthleteProfileModel).where(AthleteProfileModel.user_id == user_id))
    name = profile.timezone if profile else "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiConflictError("timezone_invalid") from exc
    return datetime.now(timezone.utc).astimezone(zone).date(), name


def _queue_handler(session, *, review: bool = False):
    provider, model = (resolve_queued_training_plan_provider() if review else
                       ("local", "deterministic-local-companion"))
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session), queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="johnny-review-analysis-v1" if review else "johnny-coaching-v1",
        provider=provider, model=model,
    )


def _queued(result):
    return QueuedAgentRunResponse(run_id=result.run.id, status=result.run.status,
                                  workflow_name=result.run.workflow_name, poll_url=result.poll_url)


@router.get("/overview", response_model=DataEnvelope[dict])
def overview(current_user: CurrentUserDependency, session: SessionDependency) -> DataEnvelope[dict]:
    ensure_current_user(session, current_user)
    today, timezone_name = _local_context(session, current_user.id)
    coaching = SqlAlchemyCoachingRepository(session)
    review_model = session.scalar(select(TrainingReviewModel).where(
        TrainingReviewModel.user_id == current_user.id,
        TrainingReviewModel.publication_date <= today,
    ).order_by(TrainingReviewModel.publication_date.desc()).limit(1))
    review = coaching.get_review_slot(current_user.id, review_model.publication_date) if review_model else None
    advice_models = session.scalars(select(WorkoutAdviceModel).where(
        WorkoutAdviceModel.user_id == current_user.id,
        WorkoutAdviceModel.advice_date == today,
    ).order_by(WorkoutAdviceModel.created_at.desc())).all()
    advices = [coaching.get_advice_slot(current_user.id, today, item.slot_key) for item in advice_models]
    plan = SqlAlchemyTrainingPlanRepository(session).get_plan_for_date_raw(current_user.id, today)
    choices = [{"id": item.id, "display_name": item.display_name,
                "workout_type": item.workout_type, "status": item.status}
               for item in plan.workouts if item.scheduled_for == today] if plan else []
    pending = session.scalars(select(RecommendationModel).where(
        RecommendationModel.user_id == current_user.id,
        RecommendationModel.status == "pending",
        RecommendationModel.source_advice_revision_id.is_not(None),
    )).all()
    proposals = []
    for item in pending:
        if item.expires_at and item.expires_at.replace(
            tzinfo=item.expires_at.tzinfo or timezone.utc) <= datetime.now(timezone.utc):
            continue
        revision = session.get(WorkoutAdviceRevisionModel, item.source_advice_revision_id)
        slot = session.get(WorkoutAdviceModel, revision.advice_id) if revision else None
        if (slot is None or slot.user_id != current_user.id or slot.advice_date != today
                or slot.current_revision_id != item.source_advice_revision_id
                or slot.freshness != "current"):
            continue
        proposals.append({"id": item.id, "title": item.title,
                          "rationale": item.rationale, "evidence": item.evidence,
                          "expires_at": item.expires_at.isoformat() if item.expires_at else None})
    return DataEnvelope(data={"local_date": today.isoformat(), "timezone_name": timezone_name,
                              "daily_review": review, "workout_advices": advices,
                              "workout_choices": choices, "actionable_proposals": proposals})


@router.get("/reviews", response_model=ListEnvelope[dict])
def list_reviews(current_user: CurrentUserDependency, session: SessionDependency,
                 limit: PageLimit = DEFAULT_PAGE_LIMIT, offset: PageOffset = 0) -> ListEnvelope[dict]:
    models = session.scalars(select(TrainingReviewModel).where(
        TrainingReviewModel.user_id == current_user.id,
    ).order_by(TrainingReviewModel.publication_date.desc(), TrainingReviewModel.id.desc())
        .offset(offset).limit(page_query_limit(limit))).all()
    coaching = SqlAlchemyCoachingRepository(session)
    return list_envelope([coaching.get_review_slot(current_user.id, item.publication_date)
                          for item in models], limit=limit, offset=offset)


@router.get("/reviews/{review_id}", response_model=DataEnvelope[dict])
def get_review(review_id: str, current_user: CurrentUserDependency,
               session: SessionDependency) -> DataEnvelope[dict]:
    model = session.scalar(select(TrainingReviewModel).where(
        TrainingReviewModel.id == review_id, TrainingReviewModel.user_id == current_user.id,
    ))
    if model is None:
        raise ApiNotFoundError("review not found")
    return DataEnvelope(data=SqlAlchemyCoachingRepository(session).get_review_slot(
        current_user.id, model.publication_date))


@router.post("/reviews/{review_id}/retry", response_model=DataEnvelope[QueuedAgentRunResponse], status_code=202)
def retry_review(review_id: str, current_user: CurrentUserDependency,
                 session: SessionDependency) -> DataEnvelope[QueuedAgentRunResponse]:
    model = session.scalar(select(TrainingReviewModel).where(
        TrainingReviewModel.id == review_id, TrainingReviewModel.user_id == current_user.id,
    ))
    if model is None:
        raise ApiNotFoundError("review not found")
    if model.attempt_state not in {"sync_failed", "generation_failed", "inputs_changed"} and model.freshness != "stale":
        raise ApiConflictError("review_retry_not_needed")
    result = _queue_handler(session, review=True).queue_run(
        user_id=current_user.id, workflow_name="daily_review", trigger_type="manual",
        idempotency_key=f"daily_review:{current_user.id}:{model.publication_date.isoformat()}",
        payload={"publication_date": model.publication_date.isoformat(),
                 "timezone_name": model.timezone_name}, task_type="coaching.sync",
        requeue_terminal=True,
    )
    SqlAlchemyCoachingRepository(session).reserve_review(
        current_user.id, model.publication_date, model.timezone_name, result.run.id)
    return DataEnvelope(data=_queued(result))


@router.post("/workout-advice", response_model=DataEnvelope[QueuedAgentRunResponse], status_code=202)
def request_workout_advice(payload: WorkoutAdviceRequest,
                           current_user: CurrentUserDependency,
                           session: SessionDependency) -> DataEnvelope[QueuedAgentRunResponse]:
    ensure_current_user(session, current_user)
    today, timezone_name = _local_context(session, current_user.id)
    plan = SqlAlchemyTrainingPlanRepository(session).get_plan_for_date_raw(current_user.id, today)
    workouts = tuple(item for item in plan.workouts if item.scheduled_for == today) if plan else ()
    workout_id = str(payload.workout_id) if payload.workout_id else None
    if workout_id and not any(item.id == workout_id for item in workouts):
        raise ApiNotFoundError("workout not found")
    if workout_id is None and len(workouts) > 1:
        raise HTTPException(status_code=422, detail="workout_choice_required")
    slot_key = workout_id or (workouts[0].id if workouts else "no-workout")
    body = {"advice_date": today.isoformat(), "timezone_name": timezone_name,
            "workout_id": workout_id, "constraints": payload.constraints.model_dump()}
    key = f"workout_advice:{current_user.id}:{payload.client_request_id}"
    queue = SqlAlchemyAgentTaskQueue(session)
    existing = queue.get_by_idempotency_key(key)
    if existing is not None:
        if (existing.payload.get("input") or {}) != body:
            raise ApiConflictError("client_request_id_conflict")
        run = SqlAlchemyAgentRunRepository(session).get_run_for_user(current_user.id,
            existing.payload.get("run_id"))
        if run is None:
            raise ApiConflictError("client_request_id_conflict")
        return DataEnvelope(data=QueuedAgentRunResponse(run_id=run.id, status=run.status,
            workflow_name=run.workflow_name, poll_url=f"/api/v1/agent-runs/{run.id}"))
    coaching = SqlAlchemyCoachingRepository(session)
    slot = coaching.get_advice_slot(current_user.id, today, slot_key)
    if slot and slot["attempt_state"] in {"queued", "syncing", "analyzing"}:
        run_model = session.get(AgentRunModel, slot["reserved_run_id"]) if slot["reserved_run_id"] else None
        if run_model and run_model.status in {"queued", "started"}:
            raise ApiConflictError(f"advice_in_progress:{run_model.id}")
    result = _queue_handler(session).queue_run(
        user_id=current_user.id, workflow_name="workout_advice", trigger_type="manual",
        idempotency_key=key, payload=body, task_type="coaching.sync", reuse_terminal=True,
    )
    coaching.reserve_advice(current_user.id, today, slot_key, result.run.id,
                            body["constraints"])
    return DataEnvelope(data=_queued(result))


@router.get("/workout-advice/{advice_id}", response_model=DataEnvelope[dict])
def get_workout_advice(advice_id: str, current_user: CurrentUserDependency,
                       session: SessionDependency) -> DataEnvelope[dict]:
    model = session.scalar(select(WorkoutAdviceModel).where(
        WorkoutAdviceModel.id == advice_id, WorkoutAdviceModel.user_id == current_user.id,
    ))
    if model is None:
        raise ApiNotFoundError("workout advice not found")
    return DataEnvelope(data=SqlAlchemyCoachingRepository(session).get_advice_slot(
        current_user.id, model.advice_date, model.slot_key))


@router.get("/history", response_model=ListEnvelope[dict])
def history(current_user: CurrentUserDependency, session: SessionDependency,
            limit: PageLimit = DEFAULT_PAGE_LIMIT, offset: PageOffset = 0) -> ListEnvelope[dict]:
    coaching = SqlAlchemyCoachingRepository(session)
    reviews = session.scalars(select(TrainingReviewModel).where(TrainingReviewModel.user_id == current_user.id)).all()
    advices = session.scalars(select(WorkoutAdviceModel).where(WorkoutAdviceModel.user_id == current_user.id)).all()
    decisions = session.scalars(select(RecommendationModel).where(
        RecommendationModel.user_id == current_user.id,
        RecommendationModel.source_advice_revision_id.is_not(None),
        RecommendationModel.decision.is_not(None),
    )).all()
    entries = [
        {"kind": "daily_review", "id": item.id, "at": item.updated_at.isoformat(),
         "result": coaching.get_review_slot(current_user.id, item.publication_date)} for item in reviews
    ] + [
        {"kind": "workout_advice", "id": item.id, "at": item.updated_at.isoformat(),
         "result": coaching.get_advice_slot(current_user.id, item.advice_date, item.slot_key)} for item in advices
    ] + [
        {"kind": "recommendation_decision", "id": item.id,
         "at": (item.decision_at or item.updated_at).isoformat(), "decision": item.decision}
        for item in decisions
    ]
    entries.sort(key=lambda item: (item["at"], item["id"]), reverse=True)
    return list_envelope(entries[offset:offset + page_query_limit(limit)], limit=limit, offset=offset)
