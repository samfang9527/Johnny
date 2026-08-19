# Design: Agent Runtime and Tools

## Design Status

Discussion required before implementation.

## Approach

Use one Running Companion Agent for MVP. Keep the runtime behind an application service so the agent framework can change later.

Tool groups:

- Athlete tools: `getAthleteContext`, `getAthleteMemories`
- Training tools: `getTrainingPlan`, `getTodayWorkout`, `getRecentActivities`
- Health tools: `getRecoveryState`, `getTrainingMetrics`
- Recommendation tools: `createRecommendation`, `proposeWorkoutAdjustment`
- Memory tools: `storeMemoryCandidate`

## Design Decisions

- Agent tools return structured context.
- Deterministic analytics are computed before or inside tools, not by the LLM.
- Write tools create proposals unless the action is low-risk and explicitly allowed.
- Agent run records are created for reactive, scheduled, and event-driven runs.
- Medical diagnosis is out of scope; pain and injury topics use conservative escalation language.

## Testing Strategy

- Contract tests for each tool input/output.
- Agent orchestration tests with fake LLM responses.
- Tests proving write tools create proposals rather than applying changes.
- Observability tests verifying agent run records include required fields.

## Risks

- Tool payloads can become too broad. Keep them purpose-specific.
- Prompt behavior can drift. Prompt versions and evaluation fixtures reduce that risk.

