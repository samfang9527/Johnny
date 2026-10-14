"""Provider running variants share volume/completion semantics, not terrain pace."""

RUNNING_SPORTS = frozenset({
    'run', 'running', 'track_run', 'track_running', 'trail_run', 'trail_running',
    'virtual_run', 'virtual_running', 'treadmill_run', 'treadmill_running', 'indoor_running',
})
RUNNING_WORKOUT_TYPES = frozenset({'easy_run', 'long_run', 'tempo', 'interval', 'hill', 'recovery', 'race'})


def is_running(sport: str) -> bool:
    return sport.lower() in RUNNING_SPORTS


def is_road_pace_evidence(sport: str) -> bool:
    return is_running(sport) and sport.lower() not in {'trail_run', 'trail_running'}
