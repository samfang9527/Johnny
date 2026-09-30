from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from src.application import training_plan_regeneration as regeneration
from tests.unit.test_training_plan_regeneration import TODAY, _request, _service


ROOT = Path(__file__).resolve().parents[2] / "src"


def test_regeneration_import_boundaries() -> None:
    forbidden = {
        ROOT / "api/routes/training_plan_regeneration.py": ("src.infrastructure", "sqlalchemy"),
        ROOT / "application/training_plan_regeneration.py": ("src.api", "src.infrastructure"),
        ROOT / "domain/training_plan_regeneration.py": ("src.api", "src.infrastructure"),
    }
    for path, prefixes in forbidden.items():
        tree = ast.parse(path.read_text())
        imports = [
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        ] + [
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        ]
        assert not [name for name in imports if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)], path


def test_start_handler_locks_before_any_state_read_or_queue() -> None:
    service, runs, tasks = _service()
    events: list[str] = []
    original = service._profiles.get_profile_for_user

    def read_profile(user_id: str):
        events.append("read")
        return original(user_id)

    service._profiles.get_profile_for_user = read_profile
    handler = regeneration.StartRegenerationHandler(
        profiles=service._profiles,
        race_goals=service._race_goals,
        runs=runs,
        queue_agent_runs=service._queue_agent_runs,
        lock_user=lambda user_id: events.append("lock"),
        current_instant=service._current_instant,
    )
    result = handler.handle(user_id="athlete-1", request=_request("new"), today=TODAY)
    assert result.run is not None
    assert events == ["lock", "read"]
    assert len(tasks.items) == 1


def test_start_handler_replays_failed_request_before_unrelated_in_flight() -> None:
    service, runs, tasks = _service()
    handler = regeneration.StartRegenerationHandler(
        profiles=service._profiles, race_goals=service._race_goals,
        runs=runs,
        queue_agent_runs=service._queue_agent_runs, lock_user=lambda user_id: None,
        current_instant=service._current_instant,
    )
    first = handler.handle(user_id="athlete-1", request=_request("first"), today=TODAY)
    tasks.set_status("training_plan_generation:athlete-1", "failed")
    runs.set_status(first.run.run_id, "failed")
    second = handler.handle(user_id="athlete-1", request=_request("second"), today=TODAY)
    replay = handler.handle(user_id="athlete-1", request=_request("first"), today=TODAY)
    assert second.run.run_id != first.run.run_id
    assert replay.run.run_id == first.run.run_id
    assert replay.run.status == "failed"
    assert len(tasks.items) == 1


def test_start_handler_reuses_in_flight_and_respects_quota_and_unavailable_race() -> None:
    from tests.unit.test_training_plan_regeneration import _completed_manual_run

    service, runs, tasks = _service()
    handler = regeneration.StartRegenerationHandler(
        profiles=service._profiles, race_goals=service._race_goals,
        runs=runs,
        queue_agent_runs=service._queue_agent_runs, lock_user=lambda user_id: None,
        current_instant=service._current_instant,
    )
    first = handler.handle(user_id="athlete-1", request=_request("first"), today=TODAY)
    other = handler.handle(user_id="athlete-1", request=_request("other"), today=TODAY)
    assert other.run.run_id == first.run.run_id
    assert other.in_flight_run == other.run
    assert len(tasks.items) == 1
    runs.set_status(first.run.run_id, "failed")
    unavailable = handler.handle(user_id="athlete-1", request=_request("missing", race_id="gone"), today=TODAY)
    assert unavailable.run is None
    assert len(tasks.items) == 1
    runs.add(_completed_manual_run(quota_day=TODAY, created_plan_id="plan-1"))
    exhausted = handler.handle(user_id="athlete-1", request=_request("new"), today=TODAY)
    assert exhausted.quota.available is False
    assert exhausted.run is None
    assert len(tasks.items) == 1


def test_options_handler_reads_without_locking() -> None:
    service, runs, _ = _service()
    handler = regeneration.GetRegenerationOptionsHandler(
        profiles=service._profiles, race_goals=service._race_goals,
        training_plans=service._training_plans, runs=runs,
        current_instant=service._current_instant,
    )
    options = handler.handle(user_id="athlete-1", today=TODAY)
    assert options.quota.quota_day == date(2026, 9, 17)
    assert options.default_strategy.plan_type == "race"


def test_composed_user_lock_targets_the_current_user_row() -> None:
    from sqlalchemy.dialects import postgresql
    from src.api.regeneration_composition import _lock_user

    class Session:
        statement = None

        def scalar(self, statement):
            self.statement = statement

    session = Session()
    _lock_user(session, "athlete-1")
    compiled = session.statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    assert "FOR UPDATE" in sql
    assert "athlete-1" in sql
