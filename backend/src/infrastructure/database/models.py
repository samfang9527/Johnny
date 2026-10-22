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
    Text,
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
    password_credentials: Mapped[list[PasswordCredentialModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    auth_sessions: Mapped[list[AuthSessionModel]] = relationship(back_populates="user", cascade="all, delete-orphan")
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


class PasswordCredentialModel(TimestampMixin, Base):
    __tablename__ = "password_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="password_credentials")


class AuthSessionModel(TimestampMixin, Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[UserModel] = relationship(back_populates="auth_sessions")


class AthleteProfileModel(TimestampMixin, Base):
    __tablename__ = "athlete_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    experience_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
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
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'archived', 'draft', 'superseded')",
            name="training_plan_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    race_id: Mapped[str | None] = mapped_column(ForeignKey("races.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

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
    training_plan_id: Mapped[str] = mapped_column(ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False)
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


class IntegrationCredentialModel(TimestampMixin, Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (
        UniqueConstraint("integration_connection_id", name="uq_integration_credentials_connection"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    integration_connection_id: Mapped[str] = mapped_column(ForeignKey("integration_connections.id"), nullable=False)
    credential_format: Mapped[str] = mapped_column(String(80), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(160), nullable=False)
    lifecycle_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


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


class PlanActivationRevisionModel(TimestampMixin, Base):
    __tablename__ = "plan_activation_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_plan_id: Mapped[str | None] = mapped_column(String(36))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_local_date: Mapped[date] = mapped_column(Date(), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(80), nullable=False)


class WorkoutPrescriptionRevisionModel(TimestampMixin, Base):
    __tablename__ = "workout_prescription_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workout_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scheduled_for: Mapped[date] = mapped_column(Date(), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workout_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(String(36))


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
    source_advice_revision_id: Mapped[str | None] = mapped_column(String(36))
    workout_fingerprint: Mapped[str | None] = mapped_column(String(64))
    evidence_fingerprint: Mapped[str | None] = mapped_column(String(64))
    decision_fingerprint: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(120))


class AgentRunModel(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'started', 'completed', 'failed')",
            name="agent_run_status",
        ),
    )

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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class DailyAdviceModel(TimestampMixin, Base):
    __tablename__ = "daily_advices"
    __table_args__ = (
        UniqueConstraint("user_id", "advice_date", name="uq_daily_advice_user_date"),
        CheckConstraint(
            "state IN ('pending', 'ready', 'sync_failed', 'generation_failed', 'no_plan')",
            name="daily_advice_state",
        ),
        CheckConstraint(
            "data_freshness IN ('fresh', 'limited', 'stale')",
            name="daily_advice_freshness",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    advice_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    data_freshness: Mapped[str] = mapped_column(String(32), nullable=False)
    reserved_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    refresh_source_sync_run_id: Mapped[str | None] = mapped_column(String(36))
    plan_version_id: Mapped[str | None] = mapped_column(String(36))
    workout_id: Mapped[str | None] = mapped_column(String(36))
    week_start: Mapped[date | None] = mapped_column(Date)
    week_end: Mapped[date | None] = mapped_column(Date)
    execution_mode: Mapped[str | None] = mapped_column(String(32))
    facts: Mapped[dict | None] = mapped_column(JSON)
    week_summary: Mapped[str | None] = mapped_column(Text)
    today_execution: Mapped[str | None] = mapped_column(Text)
    workout_guide: Mapped[dict | None] = mapped_column(JSON)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_sync_run_id: Mapped[str | None] = mapped_column(String(36))
    source_run_id: Mapped[str | None] = mapped_column(String(36))


class CoachingInputVersionModel(TimestampMixin, Base):
    __tablename__ = "coaching_input_versions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TrainingReviewModel(TimestampMixin, Base):
    __tablename__ = "training_reviews"
    __table_args__ = (UniqueConstraint("user_id", "publication_date", name="uq_training_review_slot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    publication_date: Mapped[date] = mapped_column(Date, nullable=False)
    reviewed_date: Mapped[date] = mapped_column(Date, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(80), nullable=False)
    current_revision_id: Mapped[str | None] = mapped_column(String(36))
    attempt_state: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempt_error: Mapped[str | None] = mapped_column(String(120))
    reserved_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_run_id: Mapped[str | None] = mapped_column(String(36))
    freshness: Mapped[str] = mapped_column(String(32), default="current", nullable=False)


class TrainingReviewRevisionModel(TimestampMixin, Base):
    __tablename__ = "training_review_revisions"
    __table_args__ = (UniqueConstraint("review_id", "content_fingerprint", name="uq_review_content"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    review_id: Mapped[str] = mapped_column(ForeignKey("training_reviews.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class WorkoutAdviceModel(TimestampMixin, Base):
    __tablename__ = "workout_advices"
    __table_args__ = (UniqueConstraint("user_id", "advice_date", "slot_key", name="uq_workout_advice_slot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    advice_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot_key: Mapped[str] = mapped_column(String(80), nullable=False)
    current_revision_id: Mapped[str | None] = mapped_column(String(36))
    attempt_state: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempt_error: Mapped[str | None] = mapped_column(String(120))
    reserved_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_run_id: Mapped[str | None] = mapped_column(String(36))
    freshness: Mapped[str] = mapped_column(String(32), default="current", nullable=False)


class WorkoutAdviceRevisionModel(TimestampMixin, Base):
    __tablename__ = "workout_advice_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    advice_id: Mapped[str] = mapped_column(ForeignKey("workout_advices.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class AgentTaskModel(TimestampMixin, Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed', 'dead_lettered')",
            name="agent_task_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_agent_tasks_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error_type: Mapped[str | None] = mapped_column(String(120))
    last_error_message: Mapped[str | None] = mapped_column(String(2000))


class AgentRunStepModel(TimestampMixin, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (UniqueConstraint("agent_run_id", "sequence_number", name="uq_agent_run_step_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
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
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
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


class ActivityDetailSnapshotModel(TimestampMixin, Base):
    __tablename__ = 'activity_detail_snapshots'
    __table_args__ = (UniqueConstraint('activity_id', 'resource', 'schema_version', 'semantic_hash',
                                      name='uq_activity_detail_snapshot_content'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    activity_id: Mapped[str] = mapped_column(ForeignKey('activities.id'), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    coverage: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ActivitySegmentModel(TimestampMixin, Base):
    __tablename__ = 'activity_segments'
    __table_args__ = (UniqueConstraint('snapshot_id', 'ordinal', name='uq_activity_segment_ordinal'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey('activity_detail_snapshots.id'), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ActivitySampleChunkModel(TimestampMixin, Base):
    __tablename__ = 'activity_sample_chunks'
    __table_args__ = (UniqueConstraint('snapshot_id', 'ordinal', name='uq_activity_sample_chunk_ordinal'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey('activity_detail_snapshots.id'), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    samples: Mapped[list] = mapped_column(JSON, nullable=False)


class ActivityExecutionAnalysisModel(TimestampMixin, Base):
    __tablename__ = 'activity_execution_analyses'
    __table_args__ = (UniqueConstraint('user_id', 'fingerprint', name='uq_activity_execution_analysis_content'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    activity_id: Mapped[str] = mapped_column(ForeignKey('activities.id'), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prescription_revision_id: Mapped[str | None] = mapped_column(ForeignKey('workout_prescription_revisions.id'))
    snapshot_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ActivityDetailFetchModel(TimestampMixin, Base):
    __tablename__ = 'activity_detail_fetches'
    __table_args__ = (UniqueConstraint('user_id', 'activity_id', 'resource', name='uq_activity_detail_fetch_slot'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    activity_id: Mapped[str] = mapped_column(ForeignKey('activities.id'), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending')
    current_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey('activity_detail_snapshots.id'))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_type: Mapped[str | None] = mapped_column(String(120))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityDetailBatchModel(TimestampMixin, Base):
    __tablename__ = 'activity_detail_batches'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    source_sync_run_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', index=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityDetailBatchItemModel(TimestampMixin, Base):
    __tablename__ = 'activity_detail_batch_items'
    __table_args__ = (UniqueConstraint('batch_id', 'activity_id', 'resource',
                                      name='uq_activity_detail_batch_item'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    batch_id: Mapped[str] = mapped_column(ForeignKey('activity_detail_batches.id'), nullable=False, index=True)
    activity_id: Mapped[str] = mapped_column(ForeignKey('activities.id'), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(32), nullable=False)
    fetch_id: Mapped[str | None] = mapped_column(ForeignKey('activity_detail_fetches.id'))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', index=True)
