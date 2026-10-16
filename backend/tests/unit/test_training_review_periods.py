from datetime import date

from src.domain.training_review import review_period


def test_review_closes_yesterday_and_seven_completed_dates() -> None:
    period = review_period(date(2026, 10, 16))
    assert (period.reviewed_date, period.starts_on, period.ends_on) == (
        date(2026, 10, 15), date(2026, 10, 9), date(2026, 10, 15),
    )


def test_review_period_crosses_year_boundary_without_using_calendar_week() -> None:
    period = review_period(date(2027, 1, 2))
    assert (period.starts_on, period.ends_on) == (date(2026, 12, 26), date(2027, 1, 1))


def test_review_period_includes_leap_day() -> None:
    period = review_period(date(2024, 3, 2))
    assert (period.starts_on, period.ends_on) == (date(2024, 2, 24), date(2024, 3, 1))
