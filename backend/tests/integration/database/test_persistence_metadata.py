from sqlalchemy import JSON, inspect

from src.infrastructure.database.models import Base


EXPECTED_TABLES = {
    "users",
    "auth_identities",
    "password_credentials",
    "auth_sessions",
    "athlete_profiles",
    "memory_items",
    "races",
    "training_plans",
    "workouts",
    "plan_adjustments",
    "activities",
    "activity_detail_fetches",
    "activity_detail_snapshots",
    "activity_segments",
    "activity_sample_chunks",
    "activity_execution_analyses",
    "activity_detail_batches",
    "activity_detail_batch_items",
    "health_metrics",
    "training_metric_snapshots",
    "recommendations",
    "agent_runs",
    "daily_advices",
    "plan_activation_revisions",
    "workout_prescription_revisions",
    "coaching_input_versions",
    "coaching_generation_requests",
    "training_reviews",
    "training_review_revisions",
    "workout_advices",
    "workout_advice_revisions",
    "agent_run_steps",
    "agent_context_sources",
    "agent_tasks",
    "integration_connections",
    "integration_credentials",
    "integration_resource_cursors",
    "sync_runs",
    "outbox_events",
    "notification_intents",
    "notification_deliveries",
}


def test_metadata_contains_mvp_table_groups() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_core_tables_expose_queryable_columns() -> None:
    expected_columns = {
        "users": {"id", "email", "display_name", "status", "created_at", "updated_at"},
        "auth_identities": {"id", "user_id", "provider", "issuer", "subject", "email", "created_at", "updated_at"},
        "password_credentials": {"id", "user_id", "email", "password_hash", "created_at", "updated_at"},
        "auth_sessions": {"id", "user_id", "token_hash", "expires_at", "revoked_at", "user_agent", "created_at", "updated_at"},
        "races": {"id", "user_id", "name", "race_date", "distance_meters", "status", "metadata_json"},
        "training_plans": {"id", "user_id", "race_id", "name", "status", "starts_on", "ends_on"},
        "workouts": {"id", "training_plan_id", "scheduled_for", "workout_type", "status"},
        "activities": {"id", "user_id", "provider_connection_id", "provider_activity_id", "started_at"},
        "health_metrics": {
            "id",
            "user_id",
            "activity_id",
            "provider_connection_id",
            "provider_metric_id",
            "measured_at",
            "metric_type",
            "value",
            "unit",
            "provider_summary",
        },
        "recommendations": {"id", "user_id", "status", "decision", "decision_at", "evidence"},
        "agent_runs": {
            "id",
            "user_id",
            "status",
            "provider",
            "model",
            "trigger_type",
            "workflow_name",
            "prompt_version",
            "correlation_id",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_cents",
            "error_type",
            "error_message",
            "trace_ref",
            "trace",
            "metadata_json",
        },
        "daily_advices": {
            "id", "user_id", "advice_date", "state", "data_freshness",
            "reserved_observed_at", "reserved_run_id", "refresh_source_sync_run_id",
            "plan_version_id", "workout_id", "week_start", "week_end", "execution_mode",
            "facts", "week_summary", "today_execution", "workout_guide", "generated_at",
            "source_sync_run_id", "source_run_id", "created_at", "updated_at",
        },
        "agent_run_steps": {
            "id",
            "agent_run_id",
            "sequence_number",
            "step_type",
            "name",
            "status",
            "started_at",
            "finished_at",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "tool_name",
            "error_type",
            "error_message",
            "input_summary",
            "output_summary",
            "payload",
        },
        "agent_context_sources": {
            "id",
            "agent_run_id",
            "source_type",
            "source_id",
            "source_summary",
            "relevance_score",
            "metadata_json",
        },
        "agent_tasks": {
            "id",
            "task_type",
            "status",
            "correlation_id",
            "idempotency_key",
            "payload",
            "available_at",
            "claimed_at",
            "completed_at",
            "failed_at",
            "retry_count",
            "max_attempts",
            "last_error_type",
            "last_error_message",
            "created_at",
            "updated_at",
        },
        "integration_connections": {
            "id",
            "user_id",
            "provider",
            "provider_account_id",
            "provider_display_name",
            "auth_scheme",
            "credential_secret_ref",
            "credential_format",
            "credential_status",
            "credential_expires_at",
            "credential_rotated_at",
            "last_credential_refresh_at",
            "connected_at",
            "disconnected_at",
            "last_verified_at",
            "sync_status",
            "last_sync_started_at",
            "last_sync_completed_at",
            "last_sync_error",
            "capabilities",
            "provider_metadata",
        },
        "integration_resource_cursors": {
            "id",
            "integration_connection_id",
            "resource_type",
            "cursor_value",
            "sync_from",
            "sync_until",
            "last_successful_sync_at",
            "status",
            "metadata_json",
        },
        "integration_credentials": {
            "id",
            "integration_connection_id",
            "credential_format",
            "encrypted_payload",
            "key_id",
            "lifecycle_metadata",
            "created_at",
            "updated_at",
        },
    }

    for table_name, columns in expected_columns.items():
        table = Base.metadata.tables[table_name]
        assert columns.issubset(set(table.columns.keys()))


def test_flexible_payload_fields_are_json_columns() -> None:
    json_columns = {
        ("activities", "provider_summary"),
        ("activity_detail_snapshots", "coverage"),
        ("activity_detail_snapshots", "source_payload"),
        ("activity_segments", "payload"),
        ("activity_sample_chunks", "samples"),
        ("activity_execution_analyses", "snapshot_ids"),
        ("activity_execution_analyses", "payload"),
        ("health_metrics", "provider_summary"),
        ("recommendations", "evidence"),
        ("agent_runs", "trace"),
        ("agent_runs", "metadata_json"),
        ("daily_advices", "facts"),
        ("daily_advices", "workout_guide"),
        ("agent_run_steps", "payload"),
        ("agent_context_sources", "metadata_json"),
        ("agent_tasks", "payload"),
        ("outbox_events", "payload"),
        ("integration_connections", "capabilities"),
        ("integration_connections", "provider_metadata"),
        ("integration_credentials", "lifecycle_metadata"),
        ("integration_resource_cursors", "cursor_value"),
        ("integration_resource_cursors", "metadata_json"),
        ("auth_identities", "provider_claims"),
        ("races", "metadata_json"),
    }

    for table_name, column_name in json_columns:
        assert isinstance(Base.metadata.tables[table_name].c[column_name].type, JSON)


def test_metadata_can_create_all_tables(sqlite_engine) -> None:
    Base.metadata.create_all(sqlite_engine)

    table_names = set(inspect(sqlite_engine).get_table_names())

    assert EXPECTED_TABLES.issubset(table_names)


def test_async_agent_tables_define_status_and_idempotency_constraints() -> None:
    agent_tasks = Base.metadata.tables["agent_tasks"]
    agent_runs = Base.metadata.tables["agent_runs"]
    training_plans = Base.metadata.tables["training_plans"]

    assert "ck_agent_tasks_agent_task_status" in {constraint.name for constraint in agent_tasks.constraints}
    assert "uq_agent_tasks_idempotency_key" in {constraint.name for constraint in agent_tasks.constraints}
    assert "ck_agent_runs_agent_run_status" in {constraint.name for constraint in agent_runs.constraints}
    assert "ck_training_plans_training_plan_status" in {constraint.name for constraint in training_plans.constraints}


def test_agent_run_children_cascade_when_agent_run_is_deleted() -> None:
    child_tables = (
        Base.metadata.tables["agent_run_steps"],
        Base.metadata.tables["agent_context_sources"],
    )

    for table in child_tables:
        agent_run_fk = next(
            fk_constraint
            for fk_constraint in table.foreign_key_constraints
            if {element.parent.name for element in fk_constraint.elements} == {"agent_run_id"}
        )
        assert agent_run_fk.ondelete == "CASCADE"


def test_workouts_cascade_when_training_plan_is_deleted() -> None:
    workouts = Base.metadata.tables["workouts"]

    training_plan_fk = next(
        fk_constraint
        for fk_constraint in workouts.foreign_key_constraints
        if {element.parent.name for element in fk_constraint.elements} == {"training_plan_id"}
    )
    assert training_plan_fk.ondelete == "CASCADE"
