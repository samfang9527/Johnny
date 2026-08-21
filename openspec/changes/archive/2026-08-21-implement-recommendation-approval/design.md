## Context

Johnny now has normalized athlete/race data, training plans, activities, health metrics, deterministic training analytics, and persistence tables for recommendations and plan adjustments. The next product loop is not agent generation itself; it is the human-in-the-loop path that records what was recommended, why, what the user decided, and whether a training-plan mutation was applied.

Current persistence already has `recommendations` with `pending`, `decided`, and `superseded` status support plus `accepted`, `rejected`, and `edited` decisions. `plan_adjustments` already stores before/after payloads with `proposed`, `approved`, `rejected`, and `applied` statuses. This change should use those existing tables and add domain/application behavior around them.

## Goals / Non-Goals

**Goals:**

- Model evidence-backed recommendations with explicit type, priority, title, rationale, evidence, proposed action, and lifecycle status.
- Require user approval before applying significant workout adjustments.
- Preserve decision history for accepted, rejected, and edited recommendations.
- Apply accepted workout adjustments through an application service that validates tenant ownership and current plan state.
- Provide a deterministic daily recommendation service shell that can create recommendations from Today context without LLM output.

**Non-Goals:**

- No LLM prompt execution, generated coaching prose, or agent tool runtime.
- No notification delivery.
- No frontend approval UI or API endpoints.
- No automatic application of recommendations without a recorded user decision.
- No new database migration unless implementation proves the current JSON payload columns cannot hold the required shape.

## Decisions

### Recommendation Domain Shape

Represent a recommendation as a domain object with:

- `recommendation_type`: MVP values `workout_adjustment`, `recovery_warning`, and `informational`.
- `priority`: MVP values `low`, `medium`, `high`.
- `status`: `pending`, `decided`, or `superseded`.
- `decision`: `accepted`, `rejected`, `edited`, or `None`.
- `title` and `rationale`.
- `evidence`: structured evidence items.
- `proposed_action`: structured action payload.
- Optional `training_plan_id`, `workout_id`, `agent_run_id`, and `id`.

Rationale: this keeps the recommendation workflow independent from agent generation while preserving a shape future agents and UI can consume.

Alternative considered: keep using `RecommendationModel` directly as the application object. That would leak persistence constraints into lifecycle rules and make tests less clear.

### Evidence Payload Shape

Use a normalized JSON-friendly evidence shape:

```json
{
  "items": [
    {
      "source": "training_analytics",
      "metric": "readiness_label",
      "value": "rest",
      "unit": null,
      "observed_at": "2027-01-28",
      "summary": "Recovery context indicates rest"
    }
  ]
}
```

Each evidence item must include `source`, `metric`, and `value`; `unit`, `observed_at`, and `summary` are optional. Unknown or missing signals should be represented as evidence values or unavailable signal lists, not hidden in prose.

Rationale: structured evidence lets future UI show "why" and lets agent evaluation inspect recommendation quality without parsing text.

Alternative considered: arbitrary evidence dictionaries. That is easier initially but makes UI and evaluation brittle.

### Proposed Action Shape

Use JSON-friendly proposed actions with MVP action types:

- `adjust_workout`: references `training_plan_id`, `workout_id`, `before_payload`, `after_payload`, and `reason`.
- `no_plan_change`: records an informational or warning recommendation that does not mutate a plan.

Significant workout changes are any proposed change to scheduled date, workout type, planned duration, planned distance, pace range, heart-rate zone, purpose, or status. These changes require an accepted decision before application.

Rationale: explicit before/after payloads give the approval service enough data to validate and apply changes while keeping audit history.

Alternative considered: store only a natural-language action summary. That would be impossible to apply safely.

### Decision And Edit Lifecycle

Pending recommendations can be:

- Accepted: mark recommendation as `decided` with decision `accepted`, approve the linked adjustment, then apply the adjustment.
- Rejected: mark recommendation as `decided` with decision `rejected`; leave all plan/workout state unchanged.
- Edited: mark original recommendation as `decided` with decision `edited`; create a new pending recommendation with the revised proposed action and a supersedes/original reference in evidence or proposed action metadata.

Rationale: editing should preserve the original proposal instead of mutating history. A new pending version keeps approval semantics simple.

Alternative considered: mutate the same recommendation payload in place. That loses the original recommendation and weakens auditability.

### Application Service Boundary

Add application services for:

- Creating daily deterministic recommendations from Today context.
- Recording user decisions.
- Applying accepted workout adjustments.
- Rejecting and editing recommendations.

Services should use trusted `user_id` parameters and repository methods that filter by user. Domain objects enforce lifecycle validity; repositories enforce persistence and ownership lookups.

Rationale: plan mutation crosses recommendation and training-plan boundaries, so it belongs in an application service rather than a repository method.

Alternative considered: let the recommendation repository mutate plans. That would couple persistence adapters and bypass domain rules.

## Risks / Trade-offs

- Evidence schema may evolve as agent/runtime features arrive -> keep evidence JSON versionable and validate only MVP required keys.
- Edited recommendation history may be harder to query without a dedicated parent column -> store original/supersedes references in JSON for MVP and add typed columns only after query needs stabilize.
- Approval services could apply stale before/after payloads -> validate the current workout still matches the expected `before_payload` before applying.
- Recommendation priority can become subjective -> keep priority deterministic in the service shell and avoid user-facing claims until UI work.
- Tenant leakage would be high impact -> every service method accepts trusted `user_id`; repository reads and writes must filter by it.

## Migration Plan

No migration is expected for MVP. Existing `recommendations.evidence` and `plan_adjustments.adjustment_payload` JSON fields can hold structured evidence, proposed action metadata, before/after payloads, and edit links. If implementation finds a strongly queried relationship such as `supersedes_recommendation_id`, propose it as a separate persistence change.

## Open Questions

- None for MVP. The implementation should use the statuses, action types, evidence shape, and edit-version behavior defined here.
