from src.application.interfaces.activity_store import ActivityStore
from src.application.interfaces.athlete_race_store import AthleteProfileStore, RaceGoalStore
from src.application.interfaces.job_provider import DueJobProvider, ScheduledJobRecord
from src.application.interfaces.persistence_repositories import (
    ActivityStore as ExportedActivityStore,
    AthleteProfileStore as ExportedAthleteProfileStore,
    DueJobProvider as ExportedDueJobProvider,
    RaceGoalStore as ExportedRaceGoalStore,
    RecommendationStore as ExportedRecommendationStore,
    ScheduleProvider as ExportedScheduleProvider,
    TrainingAnalyticsDataProvider as ExportedTrainingAnalyticsDataProvider,
    TrainingMetricSnapshotStore as ExportedTrainingMetricSnapshotStore,
    TrainingPlanStore as ExportedTrainingPlanStore,
    UserStore as ExportedUserStore,
)
from src.application.interfaces.recommendation_store import RecommendationStore
from src.application.interfaces.schedule_provider import DueSchedule, ScheduleProvider
from src.application.interfaces.training_analytics_store import TrainingAnalyticsDataProvider, TrainingMetricSnapshotStore
from src.application.interfaces.training_plan_store import TrainingPlanStore
from src.application.interfaces.user_store import UserStore


def test_application_interfaces_use_role_names() -> None:
    assert ExportedActivityStore is ActivityStore
    assert ExportedAthleteProfileStore is AthleteProfileStore
    assert ExportedRaceGoalStore is RaceGoalStore
    assert ExportedRecommendationStore is RecommendationStore
    assert ExportedTrainingPlanStore is TrainingPlanStore
    assert ExportedTrainingAnalyticsDataProvider is TrainingAnalyticsDataProvider
    assert ExportedTrainingMetricSnapshotStore is TrainingMetricSnapshotStore
    assert ExportedUserStore is UserStore
    assert ExportedDueJobProvider is DueJobProvider
    assert ExportedScheduleProvider is ScheduleProvider
    assert ScheduledJobRecord.__name__ == "ScheduledJobRecord"
    assert DueSchedule.__name__ == "DueSchedule"
