# Johnny UX Contract

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Date | Native date input in `frontend/src/App.vue` race-entry form | `premium-ui.json` ownership and `DESIGN.md` layout/form guidance | native | component test, build, premium audit |
| Form | App-owned Vue form markup with `novalidate` and inline validation | `frontend/src/App.vue`, `DESIGN.md` Forms and overlays | provider binding, race entry, hidden conversation composer | component test, premium audit |
| Scrollbar | Global application stylesheet in `frontend/src/styles.css` | `DESIGN.md` token mapping and CSS custom properties | global baseline | token verifier, premium audit |

## Workflow Rules

- Production navigation shows `今日`, `訓練安排`, `Agent 收件匣`, and `資料來源`.
- Conversation remains hidden from production navigation while the code path is retained for later reactivation and tests.
- Today shows race, workout, recovery evidence, and an Agent Inbox entry point. Recommendation cards are rendered in Agent Inbox only.
- Agent Inbox recommendation decisions use exactly two actions: `接受調整` and `保留課表`.
- `訓練安排` owns the six-month future target calendar and race-entry form. Race entries persist through `POST /api/v1/races`; the calendar hydrates from `GET /api/v1/races` for the active six-month window. The workout list remains supporting context.
