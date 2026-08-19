from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import (
    ActivityModel,
    IntegrationConnectionModel,
    IntegrationResourceCursorModel,
    RecommendationModel,
    TrainingPlanModel,
    UserModel,
    WorkoutModel,
    utc_now,
)


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_user(self, *, email: str, display_name: str) -> UserModel:
        user = UserModel(email=email, display_name=display_name)
        self._session.add(user)
        self._session.flush()
        return user

    def get(self, user_id: str) -> UserModel | None:
        return self._session.get(UserModel, user_id)

    def get_by_email(self, email: str) -> UserModel | None:
        return self._session.scalar(select(UserModel).where(UserModel.email == email))


class SqlAlchemyTrainingPlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_plan(
        self,
        *,
        user_id: str,
        race_id: str | None,
        name: str,
        starts_on: date,
        ends_on: date,
    ) -> TrainingPlanModel:
        plan = TrainingPlanModel(
            user_id=user_id,
            race_id=race_id,
            name=name,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        self._session.add(plan)
        self._session.flush()
        return plan

    def add_workout(
        self,
        *,
        training_plan_id: str,
        scheduled_for: date,
        workout_type: str,
        planned_duration_minutes: int | None = None,
    ) -> WorkoutModel:
        workout = WorkoutModel(
            training_plan_id=training_plan_id,
            scheduled_for=scheduled_for,
            workout_type=workout_type,
            planned_duration_minutes=planned_duration_minutes,
        )
        self._session.add(workout)
        self._session.flush()
        return workout

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlanModel | None:
        statement = (
            select(TrainingPlanModel)
            .options(selectinload(TrainingPlanModel.workouts))
            .where(TrainingPlanModel.user_id == user_id, TrainingPlanModel.status == "active")
            .order_by(TrainingPlanModel.starts_on.desc())
            .limit(1)
        )
        return self._session.scalar(statement)


class SqlAlchemyActivityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_connection(
        self,
        *,
        user_id: str,
        provider: str,
        provider_account_id: str | None = None,
        provider_display_name: str | None = None,
        auth_scheme: str = "oauth2",
        credential_secret_ref: str | None = None,
        credential_format: str | None = None,
        capabilities: dict | None = None,
        provider_metadata: dict | None = None,
    ) -> IntegrationConnectionModel:
        connection = IntegrationConnectionModel(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_display_name=provider_display_name,
            auth_scheme=auth_scheme,
            credential_secret_ref=credential_secret_ref,
            credential_format=credential_format,
            capabilities=capabilities or {},
            provider_metadata=provider_metadata or {},
        )
        self._session.add(connection)
        self._session.flush()
        return connection

    def record_credential_refresh(self, connection_id: str) -> IntegrationConnectionModel:
        connection = self._session.get(IntegrationConnectionModel, connection_id)
        if connection is None:
            raise ValueError(f"Integration connection not found: {connection_id}")
        refreshed_at = utc_now()
        connection.last_credential_refresh_at = refreshed_at
        connection.credential_rotated_at = refreshed_at
        self._session.flush()
        return connection

    def upsert_resource_cursor(
        self,
        *,
        integration_connection_id: str,
        resource_type: str,
        cursor_value: dict | None = None,
        sync_from: datetime | None = None,
        sync_until: datetime | None = None,
        status: str = "ready",
        metadata_json: dict | None = None,
    ) -> IntegrationResourceCursorModel:
        cursor = self._session.scalar(
            select(IntegrationResourceCursorModel).where(
                IntegrationResourceCursorModel.integration_connection_id == integration_connection_id,
                IntegrationResourceCursorModel.resource_type == resource_type,
            )
        )
        if cursor is None:
            cursor = IntegrationResourceCursorModel(
                integration_connection_id=integration_connection_id,
                resource_type=resource_type,
            )
            self._session.add(cursor)

        cursor.cursor_value = cursor_value or {}
        cursor.sync_from = sync_from
        cursor.sync_until = sync_until
        if status == "ready":
            cursor.last_successful_sync_at = utc_now()
        cursor.status = status
        cursor.metadata_json = metadata_json or {}
        self._session.flush()
        return cursor

    def list_for_user(self, user_id: str) -> list[ActivityModel]:
        return list(self._session.scalars(select(ActivityModel).where(ActivityModel.user_id == user_id)))


class SqlAlchemyRecommendationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_recommendation(
        self,
        *,
        user_id: str,
        title: str,
        rationale: str,
        evidence: dict | None = None,
        training_plan_id: str | None = None,
    ) -> RecommendationModel:
        recommendation = RecommendationModel(
            user_id=user_id,
            training_plan_id=training_plan_id,
            title=title,
            rationale=rationale,
            evidence=evidence or {},
        )
        self._session.add(recommendation)
        self._session.flush()
        return recommendation

    def get(self, recommendation_id: str) -> RecommendationModel | None:
        return self._session.get(RecommendationModel, recommendation_id)

    def record_decision(self, recommendation_id: str, *, decision: str) -> RecommendationModel:
        recommendation = self._session.get(RecommendationModel, recommendation_id)
        if recommendation is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        recommendation.decision = decision
        recommendation.decision_at = utc_now()
        recommendation.status = "decided"
        self._session.flush()
        return recommendation
