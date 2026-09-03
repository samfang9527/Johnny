# Direct Active Training Plan Generation

The training-plan generation agent should create the user's generated plan as active immediately. It should not create a draft plan, should not create a training-plan recommendation, and should not rely on recommendation acceptance to activate generated plans.

`createTrainingPlan` and `createRecommendation` are separate flows. Recommendations may still be created by daily or conversation triggers, but generated training-plan creation is handled by its own workflow and write tool.
