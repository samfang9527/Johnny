"""Garmin summary and detail transports share a cross-process connection lock."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import IntegrationConnectionModel, UserModel
from src.domain.integrations_notifications import IntegrationCredential


def test_postgresql_provider_lease_serializes_two_sessions():
    url = os.getenv('JOHNNY_TEST_DATABASE_URL')
    if not url:
        pytest.skip('disposable PostgreSQL URL not configured')
    parsed = make_url(url)
    if not parsed.drivername.startswith('postgresql') or 'test' not in (parsed.database or ''):
        pytest.fail('provider lease test requires a disposable test database')
    engine = create_engine(parsed)
    first_acquired = Event()
    release_first = Event()
    second_acquired = Event()

    def first():
        with Session(engine) as session:
            with SqlAlchemyIntegrationRepository(session).provider_lease('same-connection'):
                first_acquired.set()
                assert release_first.wait(5)

    def second():
        assert first_acquired.wait(5)
        with Session(engine) as session:
            with SqlAlchemyIntegrationRepository(session).provider_lease('same-connection'):
                second_acquired.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(first)
            b = pool.submit(second)
            assert first_acquired.wait(5)
            assert not second_acquired.wait(0.2)
            release_first.set()
            a.result(timeout=5)
            b.result(timeout=5)
            assert second_acquired.is_set()
    finally:
        release_first.set()
        engine.dispose()


def test_refreshed_credential_is_visible_before_outer_transaction_commits():
    url = os.getenv('JOHNNY_TEST_DATABASE_URL')
    if not url:
        pytest.skip('disposable PostgreSQL URL not configured')
    parsed = make_url(url)
    if not parsed.drivername.startswith('postgresql') or 'test' not in (parsed.database or ''):
        pytest.fail('credential durability test requires a disposable test database')
    engine = create_engine(parsed)
    user_id, connection_id = str(uuid4()), str(uuid4())
    try:
        with Session(engine) as session:
            session.add(UserModel(id=user_id, email=f'{user_id}@example.invalid', display_name='Owner'))
            session.flush()
            session.add(IntegrationConnectionModel(id=connection_id, user_id=user_id,
                                                   provider='garmin_connect'))
            session.commit()
            repo = SqlAlchemyIntegrationRepository(session)
            repo.upsert_credential(IntegrationCredential.create(
                connection_id=connection_id, credential_format='garminconnect-session-json',
                encrypted_payload='fernet:old-payload', key_id='key-1'))
            session.commit()

            assert repo.get_credential_for_connection(connection_id).encrypted_payload == 'fernet:old-payload'
            with repo.provider_lease(connection_id):
                repo.upsert_credential_durably(IntegrationCredential.create(
                    connection_id=connection_id, credential_format='garminconnect-session-json',
                    encrypted_payload='fernet:new-payload', key_id='key-1'))
                with Session(engine) as observer:
                    assert SqlAlchemyIntegrationRepository(observer).get_credential_for_connection(
                        connection_id).encrypted_payload == 'fernet:new-payload'
            assert repo.get_credential_for_connection(connection_id).encrypted_payload == 'fernet:new-payload'
    finally:
        engine.dispose()
