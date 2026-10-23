"""Durable task contracts accepted by the current agent worker."""

CURRENT_CONTRACT_VERSION = 1
SUPPORTED_TASK_CONTRACTS: dict[str, tuple[int, ...]] = {
    'agent.workflow': (0, 1),
    'daily_advice.sync': (0, 1),
    'coaching.sync': (0, 1),
    'training-plan.daily-check': (0, 1),
    'activity.detail.fetch.v1': (0, 1),
    'activity.detail.finalize.v1': (0, 1),
    'activity.detail.recheck.v1': (0, 1),
}
