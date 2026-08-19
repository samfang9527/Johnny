from sqlalchemy import JSON, inspect

from src.infrastructure.database.models import Base


EXPECTED_TABLES = {
    "users",
    "auth_identities",
    "athlete_profiles",
    "memory_items",
    "races",
    "training_plans",
    "workouts",
    "plan_adjustments",
    "activities",
    "health_metrics",
    "training_metric_snapshots",
    "recommendations",
    "agent_runs",
    "agent_run_steps",
    "agent_context_sources",
    "integration_connections",
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
    }

    for table_name, columns in expected_columns.items():
        table = Base.metadata.tables[table_name]
        assert columns.issubset(set(table.columns.keys()))


def test_flexible_payload_fields_are_json_columns() -> None:
    json_columns = {
        ("activities", "provider_summary"),
        ("health_metrics", "provider_summary"),
        ("recommendations", "evidence"),
        ("agent_runs", "trace"),
        ("agent_runs", "metadata_json"),
        ("agent_run_steps", "payload"),
        ("agent_context_sources", "metadata_json"),
        ("outbox_events", "payload"),
        ("integration_connections", "capabilities"),
        ("integration_connections", "provider_metadata"),
        ("integration_resource_cursors", "cursor_value"),
        ("integration_resource_cursors", "metadata_json"),
        ("auth_identities", "provider_claims"),
    }

    for table_name, column_name in json_columns:
        assert isinstance(Base.metadata.tables[table_name].c[column_name].type, JSON)


def test_metadata_can_create_all_tables(sqlite_engine) -> None:
    Base.metadata.create_all(sqlite_engine)

    table_names = set(inspect(sqlite_engine).get_table_names())

    assert EXPECTED_TABLES.issubset(table_names)
