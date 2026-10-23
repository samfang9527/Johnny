from datetime import datetime, timedelta, timezone

import pytest

from src.api.dependencies import get_session
from src.api.routes.johnny import _queue_handler
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import AgentTaskModel, IntegrationConnectionModel, TrainingReviewModel
from sqlalchemy import select
from tests.unit.api_test_helpers import create_sqlite_test_client


def test_v2_queue_freezes_same_configured_provider_for_review_and_advice(monkeypatch):
    client = create_sqlite_test_client()
    monkeypatch.setenv('JOHNNY_COACHING_ANALYSIS_V2_ENABLED', 'true')
    monkeypatch.setenv('LLM_API_KEY', 'fake-key')
    monkeypatch.setenv('LLM_MODEL', 'fake-model')
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    review = _queue_handler(session, review=True)
    advice = _queue_handler(session)
    assert review._prompt_version == 'johnny-review-analysis-v2'
    assert advice._prompt_version == 'johnny-workout-analysis-v2'
    assert (review._provider, review._model) == ('openai', 'fake-model')
    assert (advice._provider, advice._model) == ('openai', 'fake-model')
    scope.close()


def test_overview_keeps_review_and_advice_independent():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "athlete"}
    today = datetime.now(timezone.utc).date()
    assert client.get("/api/v1/johnny/overview", headers=headers).status_code == 200
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    store = SqlAlchemyCoachingRepository(session)
    review = store.reserve_review("athlete", today, "UTC", "r1")
    store.publish_review(review, {"narrative": "R1", "score": {"value": 50}})
    advice = store.reserve_advice("athlete", today, "no-workout", "a1", {})
    store.publish_advice(advice, {"guidance": "A1"}, None)
    session.commit()
    first = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert first["daily_review"]["current"]["narrative"] == "R1"
    assert first["workout_advices"][0]["current"]["guidance"] == "A1"
    advice2 = store.reserve_advice("athlete", today, "no-workout", "a2", {})
    store.publish_advice(advice2, {"guidance": "A2"}, None)
    session.commit()
    second = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert second["daily_review"]["current"]["narrative"] == "R1"
    assert second["workout_advices"][0]["current"]["guidance"] == "A2"
    review2 = store.reserve_review("athlete", today, "UTC", "r2")
    store.publish_review(review2, {"narrative": "R2", "score": {"value": 75}})
    session.commit()
    third = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert third["daily_review"]["current"]["narrative"] == "R2"
    assert third["workout_advices"][0]["current"]["guidance"] == "A2"
    scope.close()


@pytest.mark.parametrize('structured', [False, True])
def test_manual_advice_request_is_idempotent_and_never_enqueues_review(monkeypatch, structured):
    if structured:
        monkeypatch.setenv('JOHNNY_COACHING_ANALYSIS_V2_ENABLED', 'true')
        monkeypatch.delenv('LLM_API_KEY', raising=False)
        monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "manual-athlete"}
    body = {"client_request_id": "63e9c25b-1af0-4277-9e6f-710aa3b3fb06",
            "workout_id": None,
            "constraints": {"feeling": "more_tired", "cannot_train_today": False}}
    first = client.post("/api/v1/johnny/workout-advice", headers=headers, json=body)
    assert first.status_code == 202, first.text
    second = client.post("/api/v1/johnny/workout-advice", headers=headers, json=body)
    assert second.status_code == 202
    assert first.json()["data"]["run_id"] == second.json()["data"]["run_id"]
    changed = {**body, "constraints": {"feeling": "usual"}}
    assert client.post("/api/v1/johnny/workout-advice", headers=headers, json=changed).status_code == 409
    assert client.get("/api/v1/johnny/overview", headers=headers).json()["data"]["daily_review"] is None


def test_stale_historical_review_retries_stored_evidence_without_provider_sync(monkeypatch):
    from scripts import agent_runtime

    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'historical-runner'}
    assert client.get('/api/v1/johnny/overview', headers=headers).status_code == 200
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    day = datetime.now(timezone.utc).date() - timedelta(days=3)
    store = SqlAlchemyCoachingRepository(session)
    reservation = store.reserve_review('historical-runner', day, 'Asia/Taipei', 'old-run')
    assert store.publish_review(reservation, {'narrative': '舊回顧', 'score': {'value': None}})
    slot = session.scalar(select(TrainingReviewModel).where(
        TrainingReviewModel.user_id == 'historical-runner'))
    slot.freshness = 'stale'
    session.add(IntegrationConnectionModel(id='historical-connection',
        user_id='historical-runner', provider='garmin_connect'))
    session.commit()
    scope.close()

    provider_calls = []
    def unexpected_provider_call(*args, **kwargs):
        provider_calls.append(1)
        raise AssertionError('stored evidence retry must not call Garmin')
    monkeypatch.setattr(agent_runtime.GarminInitialSyncHandler, 'handle', unexpected_provider_call)
    response = client.post(f'/api/v1/johnny/reviews/{slot.id}/retry',
        headers=headers, json={'source': 'stored_evidence'})
    assert response.status_code == 202, response.text
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    task = session.scalar(select(AgentTaskModel).where(
        AgentTaskModel.payload['run_id'].as_string() == response.json()['data']['run_id']))
    assert task.task_type == 'agent.workflow'
    assert task.payload['input']['publication_date'] == day.isoformat()
    assert task.payload['input']['timezone_name'] == 'Asia/Taipei'
    assert agent_runtime.work_drain(session, max_tasks=1) == 1
    session.commit()
    refreshed = SqlAlchemyCoachingRepository(session).get_review_slot('historical-runner', day)
    assert refreshed['current']['publication_date'] == day.isoformat()
    assert refreshed['current']['timezone_name'] == 'Asia/Taipei'
    assert provider_calls == []
    scope.close()


@pytest.mark.parametrize(('state', 'body', 'expected_task'), [
    ('sync_failed', None, 'coaching.sync'),
    ('generation_failed', None, 'agent.workflow'),
    ('sync_failed', {'source': 'stored_evidence'}, 'agent.workflow'),
    ('generation_failed', {'source': 'sync'}, 'coaching.sync'),
])
def test_retry_source_defaults_and_overrides(state, body, expected_task):
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': f'retry-{state}-{expected_task}'}
    client.get('/api/v1/johnny/overview', headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    store = SqlAlchemyCoachingRepository(session)
    store.reserve_review(headers['X-Johnny-User-Id'], day, 'UTC', 'old-run')
    slot = session.scalar(select(TrainingReviewModel).where(
        TrainingReviewModel.user_id == headers['X-Johnny-User-Id']))
    slot.attempt_state = state
    slot.freshness = 'stale'
    session.commit()
    review_id = slot.id
    scope.close()
    response = client.post(f'/api/v1/johnny/reviews/{review_id}/retry',
                           headers=headers, json=body) if body is not None else client.post(
                               f'/api/v1/johnny/reviews/{review_id}/retry', headers=headers)
    assert response.status_code == 202, response.text
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    task = session.scalar(select(AgentTaskModel).where(
        AgentTaskModel.payload['run_id'].as_string() == response.json()['data']['run_id']))
    assert task.task_type == expected_task
    scope.close()


def test_legacy_and_structured_coaching_payloads_remain_additive():
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'compatible-runner'}
    client.get('/api/v1/johnny/overview', headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = datetime.now(timezone.utc).date()
    store = SqlAlchemyCoachingRepository(session)
    review = store.reserve_review('compatible-runner', today, 'UTC', 'review-old')
    store.publish_review(review, {'narrative': '舊版回顧', 'score': {'value': None}})
    advice = store.reserve_advice('compatible-runner', today, 'no-workout', 'advice-new', {})
    store.publish_advice(advice, {'guidance': '今天先確認安排。',
        'analysis': {'schema_version': 'coaching-analysis-v2', 'headline': '先確認安排',
            'summary': '今天先保守安排。', 'analysis_mode': 'rules',
            'fallback_reason': 'disabled', 'findings': [], 'actions': [],
            'limitations': [], 'evidence_refs': [], 'input_fingerprint': 'x',
            'versions': {}}}, None)
    session.commit()
    scope.close()
    overview = client.get('/api/v1/johnny/overview', headers=headers).json()['data']
    assert overview['daily_review']['current']['narrative'] == '舊版回顧'
    assert 'analysis' not in overview['daily_review']['current']
    assert isinstance(overview['workout_advices'][0]['current']['guidance'], str)
    assert overview['workout_advices'][0]['analysis_mode'] == 'rules'
    history = client.get('/api/v1/johnny/history', headers=headers).json()['data']
    assert any(item['result']['current'].get('analysis') is None for item in history)
    today_payload = client.get(f'/api/v1/today?anchor_date={today}', headers=headers).json()['data']
    assert today_payload['workout_advice_summary']['analysis_mode'] == 'rules'
    assert today_payload['workout_advice_summary']['guidance'] == '今天先確認安排。'


def test_legacy_today_summary_does_not_invent_analysis():
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'legacy-today-runner'}
    client.get('/api/v1/johnny/overview', headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = datetime.now(timezone.utc).date()
    store = SqlAlchemyCoachingRepository(session)
    reservation = store.reserve_advice('legacy-today-runner', today, 'no-workout', 'legacy-run', {})
    store.publish_advice(reservation, {'guidance': '舊版今日建議。'}, None)
    session.commit()
    scope.close()
    payload = client.get(f'/api/v1/today?anchor_date={today}', headers=headers).json()['data']
    summary = payload['workout_advice_summary']
    assert summary['guidance'] == '舊版今日建議。'
    assert 'analysis_mode' not in summary
    assert 'analysis' not in payload['workout_advice']['current']


def test_retry_rejects_conflicting_source_while_previous_retry_is_queued():
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'conflicting-retry'}
    client.get('/api/v1/johnny/overview', headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    store = SqlAlchemyCoachingRepository(session)
    store.reserve_review('conflicting-retry', day, 'UTC', 'old-run')
    slot = session.scalar(select(TrainingReviewModel).where(
        TrainingReviewModel.user_id == 'conflicting-retry'))
    slot.attempt_state = 'sync_failed'
    slot.freshness = 'stale'
    review_id = slot.id
    session.commit()
    scope.close()
    sync = client.post(f'/api/v1/johnny/reviews/{review_id}/retry', headers=headers,
                       json={'source': 'sync'})
    assert sync.status_code == 202
    stored = client.post(f'/api/v1/johnny/reviews/{review_id}/retry', headers=headers,
                         json={'source': 'stored_evidence'})
    assert stored.status_code == 409
