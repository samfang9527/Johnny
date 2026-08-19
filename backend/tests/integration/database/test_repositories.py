from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.infrastructure.database.models import (
    ActivityModel,
    AgentContextSourceModel,
    AgentRunModel,
    AgentRunStepModel,
    AuthIdentityModel,
    AthleteProfileModel,
    Base,
    HealthMetricModel,
    IntegrationResourceCursorModel,
    RaceModel,
    UserModel,
)
from src.infrastructure.database.repositories import (
    SqlAlchemyActivityRepository,
    SqlAlchemyRecommendationRepository,
    SqlAlchemyTrainingPlanRepository,
    SqlAlchemyUserRepository,
)
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_repositories_create_and_load_current_training_plan(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = SqlAlchemyUserRepository(uow.session).create_user(
            email="runner@example.com",
            display_name="Runner",
        )
        race = RaceModel(
            user_id=user.id,
            name="Taipei Half",
            race_date=date(2027, 3, 1),
            distance_meters=21097,
        )
        uow.session.add(race)
        uow.session.flush()

        plans = SqlAlchemyTrainingPlanRepository(uow.session)
        plan = plans.create_plan(
            user_id=user.id,
            race_id=race.id,
            name="Half Marathon Build",
            starts_on=date(2027, 1, 1),
            ends_on=date(2027, 2, 28),
        )
        plans.add_workout(
            training_plan_id=plan.id,
            scheduled_for=date(2027, 1, 2),
            workout_type="easy_run",
            planned_duration_minutes=45,
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyTrainingPlanRepository(uow.session).get_current_plan_for_user(user.id)

        assert loaded is not None
        assert loaded.name == "Half Marathon Build"
        assert [workout.workout_type for workout in loaded.workouts] == ["easy_run"]


def test_repositories_update_recommendation_decision(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = SqlAlchemyUserRepository(uow.session).create_user(
            email="decision@example.com",
            display_name="Decision Runner",
        )
        recommendations = SqlAlchemyRecommendationRepository(uow.session)
        recommendation = recommendations.create_recommendation(
            user_id=user.id,
            title="Reduce tomorrow's workout",
            rationale="High fatigue trend",
            evidence={"fatigue_score": 82},
        )
        recommendations.record_decision(recommendation.id, decision="accepted")
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyRecommendationRepository(uow.session).get(recommendation.id)

        assert loaded is not None
        assert loaded.decision == "accepted"
        assert loaded.decision_at is not None


def test_duplicate_provider_activity_is_rejected(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="activity@example.com", display_name="Activity Runner")
        uow.session.add(user)
        uow.session.flush()
        connection = SqlAlchemyActivityRepository(uow.session).create_connection(
            user_id=user.id,
            provider="strava",
            provider_account_id="acct-1",
        )
        activity = ActivityModel(
            user_id=user.id,
            provider_connection_id=connection.id,
            provider_activity_id="provider-activity-1",
            started_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            activity_type="run",
        )
        duplicate = ActivityModel(
            user_id=user.id,
            provider_connection_id=connection.id,
            provider_activity_id="provider-activity-1",
            started_at=datetime(2027, 1, 2, tzinfo=timezone.utc),
            activity_type="run",
        )
        uow.session.add_all([activity, duplicate])

        with pytest.raises(IntegrityError):
            uow.session.flush()


def test_orphan_workout_is_rejected(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        with pytest.raises(IntegrityError):
            SqlAlchemyTrainingPlanRepository(uow.session).add_workout(
                training_plan_id="missing-plan",
                scheduled_for=date(2027, 1, 2),
                workout_type="easy_run",
                planned_duration_minutes=45,
            )
            uow.session.flush()


def test_athlete_profile_can_be_linked_to_user(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="profile@example.com", display_name="Profile Runner")
        uow.session.add(user)
        uow.session.flush()
        profile = AthleteProfileModel(
            user_id=user.id,
            timezone="Asia/Taipei",
            experience_level="intermediate",
        )
        uow.session.add(profile)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(UserModel, user.id)

        assert loaded is not None
        assert loaded.athlete_profile.timezone == "Asia/Taipei"


def test_google_identity_can_be_linked_without_auth_broker_coupling(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="sso@example.com", display_name="SSO Runner")
        uow.session.add(user)
        uow.session.flush()
        identity = AuthIdentityModel(
            user_id=user.id,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-user-123",
            email="sso@example.com",
            provider_claims={"email_verified": True, "broker": None},
        )
        uow.session.add(identity)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(AuthIdentityModel, identity.id)

        assert loaded is not None
        assert loaded.user_id == user.id
        assert loaded.provider == "google"
        assert loaded.provider_claims["broker"] is None


def test_duplicate_sso_subject_for_provider_is_rejected(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="dupe-sso@example.com", display_name="SSO Runner")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add_all(
            [
                AuthIdentityModel(
                    user_id=user.id,
                    provider="github",
                    issuer="https://github.com/login/oauth",
                    subject="github-user-123",
                    email="dupe-sso@example.com",
                ),
                AuthIdentityModel(
                    user_id=user.id,
                    provider="github",
                    issuer="https://github.com/login/oauth",
                    subject="github-user-123",
                    email="dupe-sso@example.com",
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            uow.session.flush()


def test_garminconnect_connection_tracks_tokenstore_credential_lifecycle(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="garmin@example.com", display_name="Garmin Runner")
        uow.session.add(user)
        uow.session.flush()
        connection = SqlAlchemyActivityRepository(uow.session).create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            provider_display_name="Garmin Runner",
            auth_scheme="garminconnect_tokenstore",
            credential_format="garminconnect_tokenstore",
            credential_secret_ref="secret://garmin/runner/tokenstore",
            capabilities={"read": ["activities", "sleep", "steps", "heart_rates", "stress", "spo2"]},
            provider_metadata={"region": "global"},
        )
        SqlAlchemyActivityRepository(uow.session).record_credential_refresh(connection.id)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(type(connection), connection.id)

        assert loaded is not None
        assert loaded.provider == "garmin_connect"
        assert loaded.provider_display_name == "Garmin Runner"
        assert loaded.auth_scheme == "garminconnect_tokenstore"
        assert loaded.credential_format == "garminconnect_tokenstore"
        assert loaded.credential_status == "active"
        assert loaded.credential_secret_ref == "secret://garmin/runner/tokenstore"
        assert loaded.capabilities["read"] == ["activities", "sleep", "steps", "heart_rates", "stress", "spo2"]
        assert loaded.provider_metadata == {"region": "global"}
        assert loaded.last_credential_refresh_at is not None
        assert loaded.credential_rotated_at is not None


def test_garmin_health_metric_keeps_provider_summary_without_credentials(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="garmin-health@example.com", display_name="Garmin Health Runner")
        uow.session.add(user)
        uow.session.flush()
        connection = SqlAlchemyActivityRepository(uow.session).create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            auth_scheme="garminconnect_tokenstore",
            credential_format="garminconnect_tokenstore",
            credential_secret_ref="secret://garmin/runner/tokenstore",
        )
        metric = HealthMetricModel(
            user_id=user.id,
            provider_connection_id=connection.id,
            provider_metric_id="garmin-resting-heart-rate-2027-01-01",
            measured_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            metric_type="resting_heart_rate",
            value=47,
            unit="bpm",
            provider_summary={"source_method": "get_rhr_day", "calendarDate": "2027-01-01"},
        )
        uow.session.add(metric)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(HealthMetricModel, metric.id)

        assert loaded is not None
        assert loaded.provider_connection_id == connection.id
        assert loaded.provider_summary["source_method"] == "get_rhr_day"
        assert "password" not in loaded.provider_summary
        assert "session_data" not in loaded.provider_summary


def test_agent_observability_records_steps_and_context_sources(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="agent-observe@example.com", display_name="Observed Runner")
        uow.session.add(user)
        uow.session.flush()
        agent_run = AgentRunModel(
            user_id=user.id,
            status="completed",
            provider="openai",
            model="gpt-5",
            trigger_type="scheduled",
            workflow_name="daily_recommendation",
            prompt_version="daily-v1",
            correlation_id="corr-123",
            latency_ms=1520,
            input_tokens=1200,
            output_tokens=320,
            total_tokens=1520,
            estimated_cost_cents=4,
            input_summary="Daily context for runner",
            output_summary="Recommended reducing workout intensity",
            metadata_json={"environment": "test"},
        )
        uow.session.add(agent_run)
        uow.session.flush()
        uow.session.add_all(
            [
                AgentRunStepModel(
                    agent_run_id=agent_run.id,
                    sequence_number=1,
                    step_type="context_build",
                    name="Build daily context",
                    status="completed",
                    latency_ms=100,
                    output_summary="Loaded plan and recovery context",
                    payload={"context_items": 3},
                ),
                AgentRunStepModel(
                    agent_run_id=agent_run.id,
                    sequence_number=2,
                    step_type="tool_call",
                    name="Load recovery",
                    tool_name="recovery_context",
                    status="completed",
                    latency_ms=240,
                    input_summary="Need recovery context",
                    output_summary="Recovery score high fatigue",
                    payload={"fatigue_score": 82},
                ),
                AgentContextSourceModel(
                    agent_run_id=agent_run.id,
                    source_type="health_metric",
                    source_id="metric-1",
                    source_summary="Resting heart rate elevated",
                    relevance_score=0.91,
                    metadata_json={"metric_type": "resting_heart_rate"},
                ),
            ]
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded_run = uow.session.get(AgentRunModel, agent_run.id)
        steps = uow.session.query(AgentRunStepModel).filter_by(agent_run_id=agent_run.id).order_by(
            AgentRunStepModel.sequence_number
        )
        sources = uow.session.query(AgentContextSourceModel).filter_by(agent_run_id=agent_run.id).all()

        assert loaded_run is not None
        assert loaded_run.workflow_name == "daily_recommendation"
        assert loaded_run.total_tokens == 1520
        assert [step.step_type for step in steps] == ["context_build", "tool_call"]
        assert sources[0].source_type == "health_metric"
        assert sources[0].metadata_json == {"metric_type": "resting_heart_rate"}


def test_integration_resource_cursors_track_independent_sync_progress(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="cursor@example.com", display_name="Cursor Runner")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            auth_scheme="garminconnect_tokenstore",
            credential_format="garminconnect_tokenstore",
            credential_secret_ref="secret://garmin/runner/tokenstore",
        )
        activities_cursor = repository.upsert_resource_cursor(
            integration_connection_id=connection.id,
            resource_type="activities",
            cursor_value={"last_activity_id": "12345"},
            sync_until=datetime(2027, 1, 3, tzinfo=timezone.utc),
            status="ready",
        )
        sleep_cursor = repository.upsert_resource_cursor(
            integration_connection_id=connection.id,
            resource_type="sleep",
            cursor_value={"date": "2027-01-01"},
            sync_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
            status="error",
            metadata_json={"last_error": "provider temporarily unavailable"},
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        cursors = {
            cursor.resource_type: cursor
            for cursor in uow.session.query(IntegrationResourceCursorModel)
            .filter_by(integration_connection_id=connection.id)
            .all()
        }

        assert set(cursors) == {"activities", "sleep"}
        assert cursors["activities"].id == activities_cursor.id
        assert cursors["activities"].cursor_value == {"last_activity_id": "12345"}
        assert cursors["activities"].status == "ready"
        assert cursors["sleep"].id == sleep_cursor.id
        assert cursors["sleep"].cursor_value == {"date": "2027-01-01"}
        assert cursors["sleep"].status == "error"
        assert cursors["sleep"].metadata_json["last_error"] == "provider temporarily unavailable"
