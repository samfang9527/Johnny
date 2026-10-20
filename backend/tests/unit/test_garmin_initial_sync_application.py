from dataclasses import replace
from datetime import date, datetime, timezone

from src.application.integrations import (
    GARMIN_SYNC_RESOURCES,
    GarminCredentialBlockedError,
    GarminInitialSyncCommand,
    GarminInitialSyncHandler,
    GarminRateLimitError,
    GarminResourceFetchResult,
)
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.athlete_race import AthleteProfile
from src.domain.integrations_notifications import IntegrationConnectionRef, SyncRun, SyncSummary
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_daily_health, normalize_garmin_training_evidence


def test_garmin_initial_sync_imports_each_resource_with_independent_cursors_and_partial_failure() -> None:
    integrations = _FakeIntegrationStore()
    activities = _FakeActivityStore()
    outbox = _FakeOutboxStore()
    adapter = _FakeGarminResourceAdapter(
        results={
            "activities": GarminResourceFetchResult(
                items=[{"id": "activity-1"}], cursor={"after": "activity-1"}, pagination_complete=True),
            "sleep": GarminResourceFetchResult(items=[{"date": "2027-01-01", "kind": "sleep"}], cursor={"date": "2027-01-01"}),
            "hrv": GarminResourceFetchResult(items=[{"date": "2027-01-01", "kind": "hrv"}], cursor={"date": "2027-01-01"}),
            "resting_heart_rate": GarminResourceFetchResult(
                items=[{"date": "2027-01-01", "kind": "resting_heart_rate"}],
                cursor={"date": "2027-01-01"},
            ),
            "stress": GarminResourceFetchResult(items=[{"date": "2027-01-01", "kind": "stress"}], cursor={"date": "2027-01-01"}),
        },
        failures={"body_battery": RuntimeError("body battery endpoint unavailable")},
    )

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=activities,
        outbox=outbox,
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("Asia/Taipei"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, 8, 30, tzinfo=timezone.utc),
        )
    )

    payload = summary.to_payload()["resources"]
    assert payload["activities"]["fetched"] == 1
    assert payload["activities"]["stored"] == 1
    assert summary.to_payload()["stored_dates"]["activities"] == ["2027-01-10"]
    assert payload["sleep"]["stored"] == 1
    assert payload["hrv"]["stored"] == 1
    assert payload["resting_heart_rate"]["stored"] == 1
    assert payload["stress"]["stored"] == 1
    assert payload["body_battery"]["failed"] == 1
    assert "steps" not in payload
    assert "spo2" not in payload
    assert adapter.calls[0]["resource_type"] == "activities"
    assert adapter.calls[0]["timezone_name"] == "Asia/Taipei"
    assert adapter.calls[0]["start_date"] == date(2027, 1, 2)
    assert adapter.calls[0]["end_date"] == date(2027, 1, 31)
    checkpoint = {"start_date": "2027-01-02", "end_date": "2027-01-31", "timezone_name": "Asia/Taipei"}
    assert integrations.advanced_cursors == {
        "activities": {**checkpoint, "after": "activity-1"},
        "sleep": {**checkpoint, "date": "2027-01-01"},
        "hrv": {**checkpoint, "date": "2027-01-01"},
        "resting_heart_rate": {**checkpoint, "date": "2027-01-01"},
        "stress": {**checkpoint, "date": "2027-01-01"},
        "heart_rate_zones": checkpoint,
        "lactate_threshold": checkpoint,
    }
    assert "body_battery" not in integrations.advanced_cursors
    assert [metric.metric_date for metric in activities.health] == [date(2027, 1, 1)] * 4
    assert len(outbox.events) == 1


def test_repeated_garmin_evidence_does_not_report_unchanged_health_or_targets_as_stored() -> None:
    integrations = _FakeIntegrationStore()
    activities = _FakeActivityStore()
    handler = GarminInitialSyncHandler(
        integrations=integrations,
        activities=activities,
        outbox=_FakeOutboxStore(),
        garmin=_FakeGarminResourceAdapter(results={}),
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=lambda user_id, payload: DailyHealthMetrics.create(
            user_id=user_id, metric_date=date(2027, 1, 1), source="garmin_connect",
            hrv_ms=payload["hrv_ms"],
        ),
        normalize_training_evidence=lambda resource, payload: payload,
    )

    first_health = handler._store_resource(
        "user-1", "conn-1", "hrv", ({"hrv_ms": 42},), SyncSummary.empty())
    repeated_health = handler._store_resource(
        "user-1", "conn-1", "hrv", ({"hrv_ms": 42},), SyncSummary.empty())
    changed_health = handler._store_resource(
        "user-1", "conn-1", "hrv", ({"hrv_ms": 43},), SyncSummary.empty())
    first_target = handler._store_resource(
        "user-1", "conn-1", "heart_rate_zones", ({"profiles": {"easy": [120, 140]}},), SyncSummary.empty())
    repeated_target = handler._store_resource(
        "user-1", "conn-1", "heart_rate_zones", ({"profiles": {"easy": [120, 140]}},), SyncSummary.empty())
    changed_target = handler._store_resource(
        "user-1", "conn-1", "heart_rate_zones", ({"profiles": {"easy": [125, 145]}},), SyncSummary.empty())

    assert first_health.resources["hrv"]["stored"] == 1
    assert first_health.to_payload()["stored_dates"] == {"hrv": ["2027-01-01"]}
    assert SyncSummary.from_payload(first_health.to_payload()).stored_dates == {"hrv": ("2027-01-01",)}
    assert repeated_health.resources["hrv"]["stored"] == 0
    assert changed_health.resources["hrv"]["stored"] == 1
    assert first_target.resources["heart_rate_zones"]["stored"] == 1
    assert repeated_target.resources["heart_rate_zones"]["stored"] == 0
    assert changed_target.resources["heart_rate_zones"]["stored"] == 1


def test_garmin_initial_sync_falls_back_to_garmin_profile_timezone_then_utc() -> None:
    for profile_timezone, provider_timezone, expected in [
        (None, "America/Los_Angeles", "America/Los_Angeles"),
        (None, None, "UTC"),
    ]:
        integrations = _FakeIntegrationStore(provider_timezone=provider_timezone)
        adapter = _FakeGarminResourceAdapter(
            results={resource: GarminResourceFetchResult() for resource in GARMIN_SYNC_RESOURCES}
        )

        GarminInitialSyncHandler(
            normalize_training_evidence=normalize_garmin_training_evidence,
            integrations=integrations,
            activities=_FakeActivityStore(),
            outbox=_FakeOutboxStore(),
            garmin=adapter,
            athlete_profiles=_FakeAthleteProfileStore(profile_timezone),
            normalize_activity=_normalize_activity,
            normalize_health=_normalize_health,
        ).handle(
            GarminInitialSyncCommand(
                user_id="user-1",
                connection_id="conn-1",
                as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
            )
        )

        assert {call["timezone_name"] for call in adapter.calls} == {expected}


def test_garmin_initial_sync_records_empty_successful_resource_cursors_and_uses_valid_timezone_fallback() -> None:
    integrations = _FakeIntegrationStore(provider_timezone="Not/AZone")
    adapter = _FakeGarminResourceAdapter(
        results={resource: GarminResourceFetchResult(pagination_complete=True) for resource in GARMIN_SYNC_RESOURCES}
    )

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("Also/Invalid"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    assert set(integrations.advanced_cursors) == set(GARMIN_SYNC_RESOURCES)
    assert all(cursor == {"start_date": "2027-01-02", "end_date": "2027-01-31", "timezone_name": "UTC"}
               for cursor in integrations.advanced_cursors.values())
    assert {call["timezone_name"] for call in adapter.calls} == {"UTC"}
    assert all(summary.to_payload()["resources"][resource]["failed"] == 0 for resource in GARMIN_SYNC_RESOURCES)


def test_garmin_initial_sync_does_not_advance_cursor_for_resource_with_item_failures() -> None:
    integrations = _FakeIntegrationStore()
    adapter = _FakeGarminResourceAdapter(
        results={
            "activities": GarminResourceFetchResult(
                items=[{"id": "activity-1"}, {"missing_id": True}],
                cursor={"after": "activity-2"},
            )
        }
    )

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    assert summary.to_payload()["resources"]["activities"]["stored"] == 1
    assert summary.to_payload()["resources"]["activities"]["failed"] == 1
    assert "activities" not in integrations.advanced_cursors
    assert "sleep" in integrations.advanced_cursors


def test_garmin_initial_sync_skips_empty_supported_health_metric_records_and_logs_once(monkeypatch) -> None:
    import src.application.integrations as integrations_module

    log_calls: list[tuple[str, dict]] = []

    def capture_warning(message: str, *, extra: dict) -> None:
        log_calls.append((message, extra))

    monkeypatch.setattr(integrations_module.logger, "warning", capture_warning)
    integrations = _FakeIntegrationStore()
    adapter = _FakeGarminResourceAdapter(
        results={
            "resting_heart_rate": GarminResourceFetchResult(
                items=[
                    {"calendarDate": "2027-01-01", "get_rhr_day": {"metricId": 60, "values": []}},
                    {"calendarDate": "2027-01-02", "get_rhr_day": {"metricId": 60, "values": []}},
                ],
                cursor={"date": "2027-01-02"},
            )
        }
    )

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=lambda user_id, payload: normalize_garmin_daily_health(user_id=user_id, payload=payload),
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    payload = summary.to_payload()["resources"]["resting_heart_rate"]
    assert payload["fetched"] == 2
    assert payload["stored"] == 0
    assert payload["failed"] == 0
    assert integrations.advanced_cursors["resting_heart_rate"] == {
        "date": "2027-01-02", "start_date": "2027-01-02", "end_date": "2027-01-31", "timezone_name": "UTC",
    }
    assert len(log_calls) == 1
    message, extra = log_calls[0]
    assert message == "Garmin sync skipped provider records"
    assert extra["resource_type"] == "resting_heart_rate"
    assert extra["reason_code"] == "empty_supported_health_metrics"
    assert extra["count"] == 2
    assert extra["sample"] == {"calendarDate": "2027-01-01"}


def test_garmin_initial_sync_marks_requires_reauth_and_stops_fetching_after_credential_block() -> None:
    integrations = _FakeIntegrationStore()
    adapter = _FakeGarminResourceAdapter(
        results={},
        failures={"activities": GarminCredentialBlockedError("oauth2_token expired; cookie=session-secret")},
    )

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    payload = summary.to_payload()["resources"]
    assert payload["activities"]["failed"] == 1
    assert payload["activities"]["errors"] == ["Garmin connection requires reauth"]
    assert integrations.connection.credential_status == "requires_reauth"
    assert integrations.completed_status == "failed"
    assert integrations.advanced_cursors == {}
    assert [call["resource_type"] for call in adapter.calls] == ["activities"]


def test_garmin_initial_sync_records_rate_limit_backoff_without_reauth() -> None:
    integrations = _FakeIntegrationStore()
    adapter = _FakeGarminResourceAdapter(
        results={},
        failures={"activities": GarminRateLimitError("Garmin rate limit exceeded", retry_after_seconds=900)},
    )

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    payload = summary.to_payload()["resources"]
    assert payload["activities"]["failed"] == 1
    assert payload["activities"]["errors"] == ["Garmin rate limit exceeded"]
    assert payload["activities"]["backoff"] == {"retry_after_seconds": 900}
    assert integrations.connection.credential_status == "active"
    assert integrations.completed_status == "failed"
    assert integrations.advanced_cursors == {}
    assert [call["resource_type"] for call in adapter.calls] == ["activities"]


def test_garmin_initial_sync_classifies_raw_provider_auth_and_rate_limit_errors() -> None:
    auth_integrations = _FakeIntegrationStore()
    GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=auth_integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=_FakeGarminResourceAdapter(results={}, failures={"activities": RuntimeError('MFA required for {"sid":"abc"}')}),
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    rate_integrations = _FakeIntegrationStore()
    rate_summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=rate_integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=_FakeGarminResourceAdapter(
            results={},
            failures={"activities": RuntimeError("HTTP 429 Too Many Requests Retry-After: 120 opaque-provider-value")},
        ),
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    assert auth_integrations.connection.credential_status == "requires_reauth"
    assert auth_integrations.completed_status == "failed"
    assert rate_integrations.connection.credential_status == "active"
    assert rate_integrations.completed_status == "failed"
    assert rate_summary.to_payload()["resources"]["activities"]["backoff"] == {"retry_after_seconds": 120}
    assert rate_summary.to_payload()["resources"]["activities"]["errors"] == ["Garmin rate limit exceeded"]


def test_garmin_initial_sync_logs_failed_resource_reason_without_sensitive_values(monkeypatch) -> None:
    import src.application.integrations as integrations_module

    log_calls: list[tuple[str, dict]] = []

    def capture_warning(message: str, *, extra: dict) -> None:
        log_calls.append((message, extra))

    monkeypatch.setattr(integrations_module.logger, "warning", capture_warning)
    integrations = _FakeIntegrationStore()

    GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=_FakeGarminResourceAdapter(
            results={},
            failures={"activities": RuntimeError('MFA required for {"sid":"abc", "cookie":"session-secret"}')},
        ),
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    assert log_calls
    message, extra = log_calls[-1]
    assert message == "Garmin sync resource classified as requiring reauth"
    assert extra["resource_type"] == "activities"
    assert extra["connection_id"] == "conn-1"
    assert extra["sync_run_id"] == "sync-1"
    assert "RuntimeError" in extra["error"]
    assert "redacted" in extra["error"]
    assert "abc" not in extra["error"]
    assert "session-secret" not in extra["error"]


def test_garmin_initial_sync_classifies_temporary_403_block_as_failed_sync_not_reauth() -> None:
    integrations = _FakeIntegrationStore()

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=_FakeGarminResourceAdapter(
            results={},
            failures={"activities": RuntimeError("HTTP 403 temporarily blocked Retry-After: 900")},
        ),
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    assert integrations.connection.credential_status == "active"
    assert integrations.completed_status == "failed"
    assert summary.to_payload()["resources"]["activities"]["errors"] == ["Garmin temporary sync failure"]
    assert summary.to_payload()["resources"]["activities"]["backoff"] == {"retry_after_seconds": 900}


def test_garmin_initial_sync_does_not_fetch_when_connection_already_requires_reauth() -> None:
    integrations = _FakeIntegrationStore(credential_status="requires_reauth")
    adapter = _FakeGarminResourceAdapter(results={resource: GarminResourceFetchResult() for resource in GARMIN_SYNC_RESOURCES})

    summary = GarminInitialSyncHandler(
        normalize_training_evidence=normalize_garmin_training_evidence,
        integrations=integrations,
        activities=_FakeActivityStore(),
        outbox=_FakeOutboxStore(),
        garmin=adapter,
        athlete_profiles=_FakeAthleteProfileStore("UTC"),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    ).handle(
        GarminInitialSyncCommand(
            user_id="user-1",
            connection_id="conn-1",
            as_of=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
    )

    assert summary.to_payload()["resources"]["sync"]["errors"] == ["Garmin connection requires reauth"]
    assert integrations.started_count == 0
    assert adapter.calls == []


class _FakeIntegrationStore:
    def __init__(self, provider_timezone: str | None = "Asia/Taipei", credential_status: str = "active") -> None:
        self.connection = IntegrationConnectionRef.create(
            id="conn-1",
            user_id="user-1",
            provider="garmin_connect",
            provider_metadata={"timezone": provider_timezone} if provider_timezone else {},
            credential_status=credential_status,
        )
        self.sync_run = SyncRun.start(
            id="sync-1",
            integration_connection_id="conn-1",
            started_at=datetime(2027, 1, 31, tzinfo=timezone.utc),
        )
        self.cursors = {"activities": {"after": "old-activity"}}
        self.advanced_cursors: dict[str, dict] = {}
        self.completed_summary: SyncSummary | None = None
        self.completed_status: str | None = None
        self.started_count = 0

    def update_training_evidence(self, *args, **kwargs):
        resource = args[2]
        value = args[3]
        metadata = dict(self.connection.provider_metadata)
        evidence = dict(metadata.get("training_evidence") or {})
        evidence[resource] = {**(value or {}), "source": "garmin", "status": "ready"}
        metadata["training_evidence"] = evidence
        self.connection = replace(self.connection, provider_metadata=metadata)

    def get_connection_for_user(self, user_id: str, connection_id: str) -> IntegrationConnectionRef | None:
        if user_id == self.connection.user_id and connection_id == self.connection.id:
            return self.connection
        return None

    def start_sync_run(self, integration_connection_id: str) -> SyncRun:
        self.started_count += 1
        return self.sync_run

    def complete_sync_run(self, sync_run_id: str, summary: SyncSummary, *, status: str = "succeeded") -> SyncRun:
        self.completed_summary = summary
        self.completed_status = status
        return self.sync_run.complete(summary, finished_at=datetime(2027, 1, 31, 0, 1, tzinfo=timezone.utc), status=status)

    def fail_sync_run(self, sync_run_id: str, error: str) -> SyncRun:
        raise AssertionError("initial sync should record resource failures without failing the whole run")

    def mark_connection_requires_reauth(self, connection_id: str, error: str) -> IntegrationConnectionRef:
        self.connection = IntegrationConnectionRef.create(
            id=self.connection.id,
            user_id=self.connection.user_id,
            provider=self.connection.provider,
            provider_account_id=self.connection.provider_account_id,
            provider_display_name=self.connection.provider_display_name,
            auth_scheme=self.connection.auth_scheme,
            credential_secret_ref=self.connection.credential_secret_ref,
            credential_format=self.connection.credential_format,
            credential_status="requires_reauth",
            status=self.connection.status,
            capabilities=self.connection.capabilities,
            provider_metadata=self.connection.provider_metadata,
        )
        return self.connection

    def get_resource_cursor(self, integration_connection_id: str, resource_type: str) -> dict | None:
        return self.cursors.get(resource_type)

    def upsert_resource_cursor(
        self,
        integration_connection_id: str,
        resource_type: str,
        cursor_value: dict,
        **kwargs,
    ) -> dict:
        self.advanced_cursors[resource_type] = dict(cursor_value)
        return self.advanced_cursors[resource_type]


class _FakeActivityStore:
    def __init__(self) -> None:
        self.activities: dict[tuple[str, str], CompletedActivity] = {}
        self.health: list[DailyHealthMetrics] = []

    def get_activity_by_provider_identifier(
        self,
        user_id: str,
        provider_connection_id: str,
        source_activity_id: str,
    ) -> CompletedActivity | None:
        return self.activities.get((provider_connection_id, source_activity_id))

    def save_activity(self, user_id: str, activity: CompletedActivity) -> CompletedActivity | None:
        saved = replace(activity, id=f"activity-{len(self.activities) + 1}")
        self.activities[(activity.provider_connection_id or "", activity.source_activity_id or "")] = saved
        return saved

    def save_daily_health_metrics(self, user_id: str, metrics: DailyHealthMetrics) -> DailyHealthMetrics:
        self.health.append(metrics)
        return metrics

    def get_daily_health_metrics_for_user(self, user_id: str, metric_date: date) -> DailyHealthMetrics | None:
        values = {}
        for metrics in self.health:
            if metrics.user_id == user_id and metrics.metric_date == metric_date:
                values.update(metrics.values_by_metric_type())
        if not values:
            return None
        return DailyHealthMetrics.create(
            user_id=user_id, metric_date=metric_date, source="garmin_connect", **values)


class _FakeOutboxStore:
    def __init__(self) -> None:
        self.events = []

    def create_event(self, event):
        self.events.append(event)
        return replace(event, id=f"event-{len(self.events)}")


class _FakeGarminResourceAdapter:
    def __init__(self, *, results: dict[str, GarminResourceFetchResult], failures: dict[str, Exception] | None = None) -> None:
        self._results = results
        self._failures = failures or {}
        self.calls: list[dict] = []

    def fetch_resource(
        self,
        *,
        connection: IntegrationConnectionRef,
        resource_type: str,
        start_date: date,
        end_date: date,
        timezone_name: str,
        cursor: dict | None,
    ) -> GarminResourceFetchResult:
        self.calls.append(
            {
                "resource_type": resource_type,
                "start_date": start_date,
                "end_date": end_date,
                "timezone_name": timezone_name,
                "cursor": cursor,
            }
        )
        if resource_type in self._failures:
            raise self._failures[resource_type]
        return self._results.get(resource_type, GarminResourceFetchResult())


class _FakeAthleteProfileStore:
    def __init__(self, timezone_name: str | None) -> None:
        self._timezone_name = timezone_name

    def get_profile_for_user(self, user_id: str) -> AthleteProfile | None:
        if self._timezone_name is None:
            return None
        return AthleteProfile.create(
            user_id=user_id,
            timezone=self._timezone_name,
            experience_level="intermediate",
            current_weekly_mileage_km=40,
            preferred_training_days=("tuesday", "thursday", "sunday"),
            preferred_long_run_day="sunday",
            max_runs_per_week=4,
        )


def _normalize_activity(user_id: str, provider_connection_id: str, payload: dict) -> CompletedActivity:
    return CompletedActivity.create(
        user_id=user_id,
        source="garmin_connect",
        source_activity_id=str(payload["id"]),
        provider_connection_id=provider_connection_id,
        started_at=datetime(2027, 1, 10, 7, tzinfo=timezone.utc),
        sport_type="running",
        distance_meters=5000,
        duration_seconds=1500,
    )


def _normalize_health(user_id: str, payload: dict) -> DailyHealthMetrics:
    values = {
        "sleep": {"sleep_duration_minutes": 480},
        "hrv": {"hrv_ms": 55, "hrv_baseline_ms": 52},
        "resting_heart_rate": {"resting_heart_rate": 48},
        "stress": {"stress_score": 31},
        "body_battery": {"body_battery_score": 72},
    }[payload["kind"]]
    return DailyHealthMetrics.create(
        user_id=user_id,
        source="garmin_connect",
        metric_date=date.fromisoformat(payload["date"]),
        **values,
    )
