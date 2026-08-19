from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_string() -> str:
    return str(uuid4())


naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    athlete_profile: Mapped[AthleteProfileModel | None] = relationship(back_populates="user", uselist=False)
    auth_identities: Mapped[list[AuthIdentityModel]] = relationship(back_populates="user", cascade="all, delete-orphan")
    races: Mapped[list[RaceModel]] = relationship(back_populates="user")
    training_plans: Mapped[list[TrainingPlanModel]] = relationship(back_populates="user")


class AuthIdentityModel(TimestampMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "issuer", "subject", name="uq_auth_identity_provider_subject"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    issuer: Mapped[str] = mapped_column(String(240), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    provider_claims: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="auth_identities")


class AthleteProfileModel(TimestampMixin, Base):
    __tablename__ = "athlete_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    experience_level: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="athlete_profile")


class MemoryItemModel(TimestampMixin, Base):
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120))


class RaceModel(TimestampMixin, Base):
    __tablename__ = "races"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    race_date: Mapped[date] = mapped_column(Date, nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="races")
    training_plans: Mapped[list[TrainingPlanModel]] = relationship(back_populates="race")


class TrainingPlanModel(TimestampMixin, Base):
    __tablename__ = "training_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    race_id: Mapped[str | None] = mapped_column(ForeignKey("races.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="training_plans")
    race: Mapped[RaceModel | None] = relationship(back_populates="training_plans")
    workouts: Mapped[list[WorkoutModel]] = relationship(
        back_populates="training_plan",
        cascade="all, delete-orphan",
        order_by="WorkoutModel.scheduled_for",
    )


class WorkoutModel(TimestampMixin, Base):
    __tablename__ = "workouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    training_plan_id: Mapped[str] = mapped_column(ForeignKey("training_plans.id"), nullable=False)
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    workout_type: Mapped[str] = mapped_column(String(80), nullable=False)
    planned_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    training_plan: Mapped[TrainingPlanModel] = relationship(back_populates="workouts")


class PlanAdjustmentModel(TimestampMixin, Base):
    __tablename__ = "plan_adjustments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    training_plan_id: Mapped[str] = mapped_column(ForeignKey("training_plans.id"), nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("recommendations.id"))
    status: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)
    adjustment_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class IntegrationConnectionModel(TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id", name="uq_integration_provider_account"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_account_id: Mapped[str | None] = mapped_column(String(200))
    provider_display_name: Mapped[str | None] = mapped_column(String(200))
    auth_scheme: Mapped[str] = mapped_column(String(80), default="oauth2", nullable=False)
    credential_secret_ref: Mapped[str | None] = mapped_column(String(500))
    credential_format: Mapped[str | None] = mapped_column(String(80))
    credential_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    credential_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credential_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_credential_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    last_sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(String(2000))
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class IntegrationResourceCursorModel(TimestampMixin, Base):
    __tablename__ = "integration_resource_cursors"
    __table_args__ = (
        UniqueConstraint(
            "integration_connection_id",
            "resource_type",
            name="uq_integration_resource_cursor_connection_resource",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    integration_connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    cursor_value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sync_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ActivityModel(TimestampMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint(
            "provider_connection_id",
            "provider_activity_id",
            name="uq_activity_provider_identifier",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider_connection_id: Mapped[str | None] = mapped_column(ForeignKey("integration_connections.id"))
    provider_activity_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    provider_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class HealthMetricModel(TimestampMixin, Base):
    __tablename__ = "health_metrics"
    __table_args__ = (
        UniqueConstraint(
            "provider_connection_id",
            "provider_metric_id",
            name="uq_health_metric_provider_identifier",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    activity_id: Mapped[str | None] = mapped_column(ForeignKey("activities.id"))
    provider_connection_id: Mapped[str | None] = mapped_column(ForeignKey("integration_connections.id"))
    provider_metric_id: Mapped[str | None] = mapped_column(String(240))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    provider_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class TrainingMetricSnapshotModel(TimestampMixin, Base):
    __tablename__ = "training_metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(80), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RecommendationModel(TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'decided', 'superseded')",
            name="recommendation_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('accepted', 'rejected', 'edited')",
            name="recommendation_decision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    training_plan_id: Mapped[str | None] = mapped_column(ForeignKey("training_plans.id"))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgentRunModel(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("recommendations.id"))
    status: Mapped[str] = mapped_column(String(32), default="started", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120))
    trigger_type: Mapped[str | None] = mapped_column(String(80))
    workflow_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(120))
    correlation_id: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_cents: Mapped[int | None] = mapped_column(Integer)
    input_summary: Mapped[str | None] = mapped_column(String(2000))
    output_summary: Mapped[str | None] = mapped_column(String(2000))
    error_type: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    trace_ref: Mapped[str | None] = mapped_column(String(500))
    trace: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgentRunStepModel(TimestampMixin, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (UniqueConstraint("agent_run_id", "sequence_number", name="uq_agent_run_step_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="started", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    tool_name: Mapped[str | None] = mapped_column(String(160))
    error_type: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    input_summary: Mapped[str | None] = mapped_column(String(2000))
    output_summary: Mapped[str | None] = mapped_column(String(2000))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AgentContextSourceModel(TimestampMixin, Base):
    __tablename__ = "agent_context_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(120))
    source_summary: Mapped[str | None] = mapped_column(String(2000))
    relevance_score: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SyncRunModel(TimestampMixin, Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    integration_connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="started", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class OutboxEventModel(TimestampMixin, Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    topic: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationIntentModel(TimestampMixin, Base):
    __tablename__ = "notification_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("recommendations.id"))
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class NotificationDeliveryModel(TimestampMixin, Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    notification_intent_id: Mapped[str] = mapped_column(ForeignKey("notification_intents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="attempted", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    response: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
