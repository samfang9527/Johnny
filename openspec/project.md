# Johnny OpenSpec Project Context

## Product

Johnny is an AI running companion web app. The MVP proves the loop:

```text
Training data -> Analytics -> AI recommendation -> User approval -> Training adjustment -> Notification
```

## Development Rule

Before implementation starts for any change in `openspec/changes/`, the engineer SHALL review that change's `design.md` with the product owner and receive explicit approval.

## MVP Change Order

The active MVP changes are intentionally ordered bottom-up:

1. `01-project-foundation`
2. `02-persistence-schema`
3. `03-athlete-race-domain`
4. `04-training-plan-domain`
5. `05-activity-health-domain`
6. `06-training-analytics`
7. `07-recommendation-approval`
8. `08-agent-runtime-tools`
9. `09-integrations-notifications`
10. `10-backend-api`
11. `11-frontend-today-calendar`
12. `12-frontend-conversation-inbox`

## Technical Direction

- Frontend: Vue, Vite, TypeScript
- Backend: Python, FastAPI
- Database: PostgreSQL
- Async work: current dispatcher/worker abstraction first
- Queue/event bus: local abstraction first, SQS-compatible later
- Agent runtime: single Running Companion Agent behind application services
- LLM provider: infrastructure adapter, not a domain dependency
