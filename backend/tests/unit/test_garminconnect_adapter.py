from datetime import date

import pytest

from src.application.integrations import GarminAuthenticationError, GarminCredentialBlockedError, GarminRateLimitError
from src.domain.integrations_notifications import IntegrationConnectionRef, IntegrationCredential
from src.infrastructure.integrations.garminconnect_adapter import GarminConnectLoginAdapter, GarminConnectResourceAdapter


def test_garminconnect_login_adapter_uses_region_discovers_profile_and_returns_inline_session_payload() -> None:
    factory = _FakeGarminFactory(
        profile={"profileId": 12345, "displayName": "Garmin Runner"},
        settings={"userData": {"timeZone": "Asia/Taipei"}},
        dumped_session='{"di_token":"refreshed-token","di_refresh_token":"refresh-token"}',
    )

    profile = GarminConnectLoginAdapter(garmin_factory=factory).exchange_credentials(
        email="runner@example.com",
        password="garmin-password",
        region="china",
    )

    assert profile.provider_account_id == "12345"
    assert profile.display_name == "Garmin Runner"
    assert profile.timezone == "Asia/Taipei"
    assert profile.session_payload == '{"di_token":"refreshed-token","di_refresh_token":"refresh-token"}'
    assert factory.calls == [{"email": "runner@example.com", "password": "garmin-password", "is_cn": True}]
    assert factory.instances[0].login_tokenstore is None


def test_garminconnect_login_adapter_rejects_mfa_with_manual_import_error() -> None:
    factory = _FakeGarminFactory(login_result=("needs_mfa", None))

    with pytest.raises(GarminAuthenticationError, match="manual token import"):
        GarminConnectLoginAdapter(garmin_factory=factory).exchange_credentials(
            email="runner@example.com",
            password="garmin-password",
            region="global",
        )


def test_garminconnect_login_adapter_rejects_profile_without_stable_account_id() -> None:
    factory = _FakeGarminFactory(profile={"displayName": "Garmin Runner"})

    with pytest.raises(GarminAuthenticationError, match="account identity"):
        GarminConnectLoginAdapter(garmin_factory=factory).exchange_credentials(
            email="runner@example.com",
            password="garmin-password",
            region="global",
        )


def test_garminconnect_resource_adapter_uses_inline_decrypted_token_json_and_saves_refreshed_session() -> None:
    credentials = _FakeCredentialStore(
        IntegrationCredential.create(
            connection_id="conn-1",
            credential_format="garminconnect-session-json",
            encrypted_payload="fernet:stored-session",
            key_id="old-key",
            lifecycle_metadata={"region": "global"},
        )
    )
    cipher = _FakeCipher(decrypted='{"di_token":"stored-token","di_refresh_token":"stored-refresh"}')
    factory = _FakeGarminFactory(
        activities=[{"activityId": 99, "startTimeGMT": "2027-01-02 08:00:00", "distance": 5000, "duration": 1500}],
        dumped_session='{"di_token":"refreshed-token","di_refresh_token":"stored-refresh"}',
    )

    result = GarminConnectResourceAdapter(
        credentials=credentials,
        cipher=cipher,
        garmin_factory=factory,
    ).fetch_resource(
        connection=_connection(provider_metadata={"region": "global"}),
        resource_type="activities",
        start_date=date(2027, 1, 2),
        end_date=date(2027, 1, 31),
        timezone_name="Asia/Taipei",
        cursor={"after": "old"},
    )

    assert result.items == (
        {"activityId": 99, "startTimeGMT": "2027-01-02 08:00:00", "distance": 5000, "duration": 1500},
    )
    assert result.cursor == {"start_date": "2027-01-02", "end_date": "2027-01-31"}
    assert factory.calls == [{"email": None, "password": None, "is_cn": False}]
    assert factory.instances[0].login_tokenstore == '{"di_token":"stored-token","di_refresh_token":"stored-refresh"}'
    assert credentials.saved is not None
    assert credentials.saved.encrypted_payload == "fernet:encrypted-refreshed-session"
    assert credentials.saved.key_id == "new-key"
    assert "refreshed-token" not in repr(credentials.saved.to_safe_summary())


def test_garminconnect_resource_adapter_maps_daily_recovery_resources_without_steps_or_spo2() -> None:
    factory = _FakeGarminFactory(
        sleep={"dailySleepDTO": {"sleepTimeSeconds": 28800}},
        hrv={"hrvSummary": {"lastNightAvg": 55}},
        rhr={"restingHeartRate": 48},
        stress={"avgStressLevel": 31},
        body_battery=[
            {"calendarDate": "2027-01-30", "charged": 71},
            {"calendarDate": "2027-01-31", "charged": 72},
        ],
    )
    adapter = GarminConnectResourceAdapter(
        credentials=_FakeCredentialStore(
            IntegrationCredential.create(
                connection_id="conn-1",
                credential_format="garminconnect-session-json",
                encrypted_payload="fernet:stored-session",
                key_id="old-key",
            )
        ),
        cipher=_FakeCipher(decrypted='{"di_token":"stored-token"}'),
        garmin_factory=factory,
    )
    connection = _connection()

    sleep = adapter.fetch_resource(
        connection=connection,
        resource_type="sleep",
        start_date=date(2027, 1, 30),
        end_date=date(2027, 1, 31),
        timezone_name="UTC",
        cursor=None,
    )
    hrv = adapter.fetch_resource(
        connection=connection,
        resource_type="hrv",
        start_date=date(2027, 1, 31),
        end_date=date(2027, 1, 31),
        timezone_name="UTC",
        cursor=None,
    )
    resting = adapter.fetch_resource(
        connection=connection,
        resource_type="resting_heart_rate",
        start_date=date(2027, 1, 31),
        end_date=date(2027, 1, 31),
        timezone_name="UTC",
        cursor=None,
    )
    stress = adapter.fetch_resource(
        connection=connection,
        resource_type="stress",
        start_date=date(2027, 1, 31),
        end_date=date(2027, 1, 31),
        timezone_name="UTC",
        cursor=None,
    )
    body_battery = adapter.fetch_resource(
        connection=connection,
        resource_type="body_battery",
        start_date=date(2027, 1, 30),
        end_date=date(2027, 1, 31),
        timezone_name="UTC",
        cursor=None,
    )

    assert sleep.items == (
        {"calendarDate": "2027-01-30", "get_sleep_data": {"dailySleepDTO": {"sleepTimeSeconds": 28800}}},
        {"calendarDate": "2027-01-31", "get_sleep_data": {"dailySleepDTO": {"sleepTimeSeconds": 28800}}},
    )
    assert hrv.items == ({"calendarDate": "2027-01-31", "get_hrv_data": {"hrvSummary": {"lastNightAvg": 55}}},)
    assert resting.items == ({"calendarDate": "2027-01-31", "get_rhr_day": {"restingHeartRate": 48}},)
    assert stress.items == ({"calendarDate": "2027-01-31", "get_stress_data": {"avgStressLevel": 31}},)
    assert body_battery.items == (
        {"calendarDate": "2027-01-30", "get_body_battery": {"calendarDate": "2027-01-30", "charged": 71}},
        {"calendarDate": "2027-01-31", "get_body_battery": {"calendarDate": "2027-01-31", "charged": 72}},
    )
    assert "get_steps_data" not in repr(sleep.items + hrv.items + resting.items + stress.items + body_battery.items)
    assert "get_spo2_data" not in repr(sleep.items + hrv.items + resting.items + stress.items + body_battery.items)


def test_garminconnect_resource_adapter_classifies_missing_or_rate_limited_credentials() -> None:
    with pytest.raises(GarminCredentialBlockedError):
        GarminConnectResourceAdapter(
            credentials=_FakeCredentialStore(None),
            cipher=_FakeCipher(decrypted="{}"),
            garmin_factory=_FakeGarminFactory(),
        ).fetch_resource(
            connection=_connection(),
            resource_type="activities",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 1),
            timezone_name="UTC",
            cursor=None,
        )

    with pytest.raises(GarminRateLimitError):
        GarminConnectResourceAdapter(
            credentials=_FakeCredentialStore(
                IntegrationCredential.create(
                    connection_id="conn-1",
                    credential_format="garminconnect-session-json",
                    encrypted_payload="fernet:stored-session",
                    key_id="old-key",
                )
            ),
            cipher=_FakeCipher(decrypted='{"di_token":"stored-token"}'),
            garmin_factory=_FakeGarminFactory(login_error=_TooManyRequestsError("HTTP 429")),
        ).fetch_resource(
            connection=_connection(),
            resource_type="activities",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 1),
            timezone_name="UTC",
            cursor=None,
        )


def _connection(provider_metadata: dict | None = None) -> IntegrationConnectionRef:
    return IntegrationConnectionRef.create(
        id="conn-1",
        user_id="user-1",
        provider="garmin_connect",
        provider_account_id="garmin-account-1",
        provider_display_name="Garmin Runner",
        credential_format="garminconnect-session-json",
        provider_metadata=provider_metadata or {},
    )


class _FakeCredentialStore:
    def __init__(self, credential: IntegrationCredential | None) -> None:
        self.credential = credential
        self.saved: IntegrationCredential | None = None

    def get_credential_for_connection(self, integration_connection_id: str) -> IntegrationCredential | None:
        return self.credential if self.credential and self.credential.connection_id == integration_connection_id else None

    def upsert_credential(self, credential: IntegrationCredential) -> IntegrationCredential:
        self.saved = credential
        return credential

    def delete_credential_for_connection(self, integration_connection_id: str) -> None:
        self.credential = None


class _FakeCipher:
    key_id = "new-key"

    def __init__(self, *, decrypted: str) -> None:
        self._decrypted = decrypted

    def decrypt(self, encrypted_payload: str) -> str:
        assert encrypted_payload == "fernet:stored-session"
        return self._decrypted

    def encrypt(self, plaintext: str) -> str:
        assert plaintext.startswith('{"di_token"')
        return "fernet:encrypted-refreshed-session"


class _FakeGarminFactory:
    def __init__(
        self,
        *,
        login_result: tuple[str | None, str | None] = (None, None),
        login_error: Exception | None = None,
        profile: dict | None = None,
        settings: dict | None = None,
        dumped_session: str = '{"di_token":"stored-token"}',
        activities: list[dict] | None = None,
        sleep: dict | None = None,
        hrv: dict | None = None,
        rhr: dict | None = None,
        stress: dict | None = None,
        body_battery: list[dict] | None = None,
    ) -> None:
        self.login_result = login_result
        self.login_error = login_error
        self.profile = profile or {"profileId": "garmin-account-1", "displayName": "Garmin Runner"}
        self.settings = settings or {}
        self.dumped_session = dumped_session
        self.activities = activities or []
        self.sleep = sleep or {}
        self.hrv = hrv or {}
        self.rhr = rhr or {}
        self.stress = stress or {}
        self.body_battery = body_battery or []
        self.calls: list[dict] = []
        self.instances: list[_FakeGarminApi] = []

    def __call__(self, email=None, password=None, is_cn=False, **kwargs) -> "_FakeGarminApi":  # noqa: ANN001
        self.calls.append({"email": email, "password": password, "is_cn": is_cn})
        api = _FakeGarminApi(self)
        self.instances.append(api)
        return api


class _FakeGarminApi:
    def __init__(self, factory: _FakeGarminFactory) -> None:
        self._factory = factory
        self.client = _FakeGarminClient(factory.dumped_session)
        self.login_tokenstore = None

    def login(self, tokenstore=None):  # noqa: ANN001
        if self._factory.login_error is not None:
            raise self._factory.login_error
        self.login_tokenstore = tokenstore
        return self._factory.login_result

    def get_user_profile(self) -> dict:
        return self._factory.profile

    def get_userprofile_settings(self) -> dict:
        return self._factory.settings

    def get_activities_by_date(self, startdate, enddate=None, sortorder=None):  # noqa: ANN001
        return list(self._factory.activities)

    def get_sleep_data(self, day):  # noqa: ANN001
        return dict(self._factory.sleep)

    def get_hrv_data(self, day):  # noqa: ANN001
        return dict(self._factory.hrv)

    def get_rhr_day(self, day):  # noqa: ANN001
        return dict(self._factory.rhr)

    def get_stress_data(self, day):  # noqa: ANN001
        return dict(self._factory.stress)

    def get_body_battery(self, startdate, enddate=None):  # noqa: ANN001
        return list(self._factory.body_battery)


class _FakeGarminClient:
    def __init__(self, dumped_session: str) -> None:
        self._dumped_session = dumped_session

    def dumps(self) -> str:
        return self._dumped_session


class _TooManyRequestsError(RuntimeError):
    pass


def test_training_evidence_endpoints_are_fetched_once_per_sync_not_per_day():
    class Client:
        zone_calls = 0
        threshold_calls = 0

        def get_heart_rate_zones(self):
            self.zone_calls += 1
            return [{'sport': 'RUNNING', 'zone1Floor': 100}]

        def get_lactate_threshold(self):
            self.threshold_calls += 1
            return {'speed_and_heart_rate': {'speed': 3.125}}

    api = Client()
    adapter = GarminConnectResourceAdapter(credentials=None, cipher=None)
    zones = adapter._fetch_resource(api, 'heart_rate_zones', date(2026, 9, 1), date(2026, 10, 1))
    threshold = adapter._fetch_resource(api, 'lactate_threshold', date(2026, 9, 1), date(2026, 10, 1))
    assert zones.items == ({'profiles': [{'sport': 'RUNNING', 'zone1Floor': 100}]},)
    assert threshold.items == ({'speed_and_heart_rate': {'speed': 3.125}},)
    assert (api.zone_calls, api.threshold_calls) == (1, 1)
