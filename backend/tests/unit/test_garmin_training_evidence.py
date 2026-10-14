from src.application.training_targets import build_target_profile_from_payloads
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_training_evidence


def zones(sport='RUNNING'):
    return {'sport': sport, 'maxHeartRateUsed': 190, 'restingHeartRateUsed': 50,
            'zone1Floor': 100, 'zone2Floor': 120, 'zone3Floor': 140,
            'zone4Floor': 160, 'zone5Floor': 180}


def test_running_zones_win_over_default_and_ignore_cycling():
    result = normalize_garmin_training_evidence('heart_rate_zones', [zones('DEFAULT'), {**zones(), 'zone2Floor': 125}, zones('CYCLING')])
    assert result['sport'] == 'RUNNING'
    assert result['heart_rate_zones']['easy'] == [125, 139]
    assert result['heart_rate_zones']['threshold'] == [160, 179]
    fallback = normalize_garmin_training_evidence('heart_rate_zones', [zones('DEFAULT'), zones('CYCLING')])
    assert fallback['sport'] == 'DEFAULT'
    assert normalize_garmin_training_evidence('heart_rate_zones', [zones('CYCLING')]) is None


def test_invalid_running_zones_fall_back_to_valid_default():
    assert normalize_garmin_training_evidence('heart_rate_zones', [{**zones(), 'zone3Floor': 110}, zones('DEFAULT')])['sport'] == 'DEFAULT'


def test_lactate_speed_converts_metres_per_second_and_keeps_measurement_date():
    result = normalize_garmin_training_evidence('lactate_threshold', {'speed_and_heart_rate': {'speed': 3.125, 'calendarDate': '2026-10-10', 'heartRate': 168}})
    assert result['threshold_pace_seconds_per_km'] == 320
    assert result['measured_on'] == '2026-10-10'
    for speed in (None, 0, -1, float('nan'), float('inf'), True):
        assert normalize_garmin_training_evidence('lactate_threshold', {'speed_and_heart_rate': {'speed': speed}}) is None


def test_garmin_targets_use_configured_zones_and_manual_pace_override():
    evidence = {'heart_rate_zones': {'heart_rate_zones': {'easy': [125, 139]}, 'sport': 'RUNNING'}, 'lactate_threshold': {'threshold_pace_seconds_per_km': 320}}
    prefs = {'garmin_training_evidence': evidence}
    def target():
        return build_target_profile_from_payloads({'training_preferences': prefs}, None, (), None)
    assert target().heart_rate_zones['easy'] == (125, 139)
    assert target().pace_zones['easy'] == (384, 432)
    assert target().pace_source == 'garmin_lactate_threshold'
    prefs['threshold_pace_seconds_per_km'] = 300
    assert target().pace_zones['easy'] == (360, 405)
    assert target().pace_source == 'threshold_pace'


def test_garmin_zone_profile_survives_agent_payload_round_trip():
    from src.application.training_targets import TargetProfile
    profile = TargetProfile(None, None, {'easy': (125, 139)}, 'garmin_lactate_threshold', 'high', {'easy': (384, 432)})
    assert TargetProfile.from_payload(profile.to_payload()).heart_rate_zones == {'easy': (125, 139)}


def test_empty_garmin_zones_do_not_resurrect_legacy_manual_hr_in_agent_roundtrip():
    from src.application.training_targets import TargetProfile
    profile = build_target_profile_from_payloads({'training_preferences': {
        'garmin_training_evidence': {}, 'resting_heart_rate_bpm': 50, 'max_heart_rate_bpm': 190,
    }}, None, (), None)
    assert TargetProfile.from_payload(profile.to_payload()).heart_rate_zones == {}
