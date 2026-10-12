from datetime import date, datetime, timezone

import pytest

from scripts.agent_runtime import _due_local_date


@pytest.mark.parametrize(
    ("instant", "zone", "expected"),
    [
        (datetime(2027, 1, 28, 3, 59, tzinfo=timezone.utc), "UTC", None),
        (datetime(2027, 1, 28, 4, 0, tzinfo=timezone.utc), "UTC", date(2027, 1, 28)),
        (datetime(2027, 1, 28, 20, 0, tzinfo=timezone.utc), "Asia/Taipei", date(2027, 1, 29)),
        (datetime(2027, 3, 14, 7, 59, tzinfo=timezone.utc), "America/New_York", None),
        (datetime(2027, 3, 14, 8, 0, tzinfo=timezone.utc), "America/New_York", date(2027, 3, 14)),
        (datetime(2027, 11, 7, 8, 59, tzinfo=timezone.utc), "America/New_York", None),
        (datetime(2027, 11, 7, 9, 0, tzinfo=timezone.utc), "America/New_York", date(2027, 11, 7)),
        (datetime(2027, 1, 29, 7, 59, tzinfo=timezone.utc), "America/Los_Angeles", date(2027, 1, 28)),
    ],
)
def test_due_local_date(instant, zone, expected) -> None:
    assert _due_local_date(instant, zone) == expected


def test_due_local_date_requires_aware_instant() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _due_local_date(datetime(2027, 1, 28, 4), "UTC")
