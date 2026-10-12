from datetime import date

import pytest

from src.application.daily_advice_generation import DailyAdviceGenerator, execution_mode
from src.domain.agent_runtime import ModelResponse, ToolCallRequest
from src.domain.daily_advice import WeekExecution
from src.domain.training_plan import Workout
from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway


def _facts(status: str = "on_plan", *, today_completed: bool = False) -> WeekExecution:
    return WeekExecution(
        week_start=date(2027, 1, 22), week_end=date(2027, 1, 28), status=status,
        planned_count=3, completed_count=2, missed_count=1 if status == "behind" else 0,
        extra_count=1 if status == "above" else 0, planned_minutes=120, actual_minutes=90,
        planned_distance_meters=20_000, actual_distance_meters=15_000,
        today_completed=today_completed, evidence={"activity_coverage_complete": True},
    )


def _workout(workout_type: str = "easy_run") -> Workout:
    return Workout.create(
        id="workout-1", scheduled_for=date(2027, 1, 28), workout_type=workout_type,
        purpose="建立有氧基礎", planned_duration_minutes=40,
    )


@pytest.mark.parametrize(
    ("status", "workout", "recovery", "completed", "expected"),
    [
        ("on_plan", "easy_run", "ready", False, "follow_plan"),
        ("above", "easy_run", "ready", False, "ease_off"),
        ("behind", "easy_run", "ready", False, "ease_off"),
        ("mixed", "easy_run", "ready", False, "ease_off"),
        ("on_plan", "easy_run", "caution", False, "ease_off"),
        ("on_plan", "rest", "ready", False, "rest"),
        ("on_plan", "easy_run", "rest", False, "rest"),
        ("on_plan", "easy_run", "ready", True, "completed"),
        ("insufficient_evidence", "easy_run", "unknown", False, "follow_plan"),
    ],
)
def test_local_advice_has_three_traditional_chinese_sections_and_deterministic_mode(
    status, workout, recovery, completed, expected,
) -> None:
    facts = _facts(status, today_completed=completed)
    selected = _workout(workout)
    assert execution_mode(facts, selected, {"readiness_label": recovery}) == expected

    sections = DailyAdviceGenerator(prompt_version="v1").generate(
        user_id="athlete", facts=facts, workout=selected,
        recovery={"readiness_label": recovery}, gateway=LocalCompanionModelGateway(),
    )

    assert "本週" in sections.week_summary
    assert "3" in sections.week_summary and "2" in sections.week_summary
    assert sections.today_execution
    assert sections.workout_guide.purpose
    assert sections.workout_guide.expected_feel
    assert sections.workout_guide.if_too_hard
    assert sections.workout_guide.if_too_easy
    if status == "insufficient_evidence":
        assert "資料" in sections.week_summary
        assert "大致符合計畫" not in sections.week_summary


class BadGateway:
    def __init__(self, arguments):
        self.arguments = arguments

    def complete(self, request):
        assert request.tools == ("composeDailyAdvice",)
        assert request.require_tool_call is True
        return ModelResponse(
            content="", tool_calls=(ToolCallRequest("composeDailyAdvice", self.arguments),),
            provider="openai", model="test",
        )


@pytest.mark.parametrize("arguments", [{}, {"week_summary": "", "today_execution": "", "workout_guide": {}}, {
    "week_summary": "訓練超量", "today_execution": "照常加量", "workout_guide": {
        "purpose": "目的", "expected_feel": "感受", "if_too_hard": "變慢", "if_too_easy": "加速",
    },
}])
def test_generation_rejects_empty_or_factually_changed_model_output(arguments) -> None:
    with pytest.raises(ValueError):
        DailyAdviceGenerator(prompt_version="v1").generate(
            user_id="athlete", facts=_facts(), workout=_workout(),
            recovery={"readiness_label": "ready"}, gateway=BadGateway(arguments),
        )
