# Feature 08: Agent Runtime and Tools

## Order

8 of 12. This follows recommendation workflow and precedes integrations, API, and frontend agent surfaces.

## Layer

Agent application layer and observability.

## Goal

Add a single Running Companion Agent that reasons over structured context through domain tools and creates recommendations or conversation responses.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `03-athlete-race-domain`
- `04-training-plan-domain`
- `05-activity-health-domain`
- `06-training-analytics`
- `07-recommendation-approval`

## Delivers

- Agent run model usage
- Tool interface definitions
- Athlete context tool
- Training and recovery tools
- Recommendation creation tool
- Agent observability records
- Safety boundaries for medical and injury topics

## Non-Goals

- No multi-agent architecture
- No direct database access from agent
- No notification channel delivery
- No frontend chat UI

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Agent runtime choice for MVP
- Initial model provider abstraction
- Prompt versioning format
- Safety response boundaries
- Which tools are allowed to write proposals

## Testable Outcome

Agent orchestration tests can run with a fake LLM and fake tools, verify tool calls, create an agent run record, and produce a recommendation proposal without directly mutating plans.

