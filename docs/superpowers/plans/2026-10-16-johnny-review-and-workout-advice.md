# Johnny Review and Workout Advice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute the tasks in dependency order; this document does not authorize starting implementation before the user reviews it.

**Goal:** Give Johnny a useful retrospective daily review and explainable seven-day execution score, plus athlete-requested workout advice that can propose an explicitly approved change to today's workout.

**Architecture:** Split the existing Daily Advice pipeline into `daily_review` and `workout_advice` workflows. Share committed activity evidence, historical prescriptions, deterministic execution facts, sync coordination, and version checks; keep their output models and mutation permissions separate. Reuse Recommendations for proposals, but make publication and approval transactional and resistant to stale evidence.

**Tech Stack:** Existing Python 3.11/FastAPI/Pydantic, SQLAlchemy/Alembic, database task queue, Garmin adapter, pytest, Vue 3/TypeScript, and Vitest. No new queue service, frontend framework, or provider integration.

**Spec:** The user-approved product conclusions from this task are reproduced in §1. Existing background: [Daily Advice issue #13](https://github.com/samfang9527/Johnny/issues/13), [cross-screen UX issue #14](https://github.com/samfang9527/Johnny/issues/14), `CONTEXT.md`, `DESIGN.md`, `UX-CONTRACT.md`, and `docs/adr/0001-deterministic-training-plan-skeletons.md`. This plan explicitly replaces issue #13's combined review/advice generation and automatic advice-after-sync behavior. §2 records newly proposed implementation policies; they were not part of the earlier approval.

**Status:** Written for review on 2026-10-16. Planning only; no application code, database, scheduler, or GitHub issue has been changed.

## Global Constraints

- Schedule the retrospective review at or after 04:00 in the athlete profile's IANA timezone.
- Yesterday means the previous local calendar date; the scored period is the seven completed local dates ending yesterday.
- Today’s workout advice is generated only after an explicit athlete request; the scheduled review cannot create a Recommendation or change a workout.
- `daily_review` and `workout_advice` are independent result streams. Both appear on Johnny simultaneously; creating, refreshing, failing, or expiring one never replaces, clears, or hides the other. Only a relevant underlying evidence change can separately invalidate an affected result.
- Only acceptance of a valid Johnny-generated Recommendation applies a proposed workout change. No general workout editor or public conversation UI is added.
- Activity grouping and pairing remain directly editable; imported activity measurements are not rewritten by pairing.
- Display missing evidence as uncertainty. Never infer missed training from a failed sync or unresolved pairing.
- The execution score measures adherence to a prescription, not fitness, readiness, or injury risk. The model cannot calculate the score or fabricate supporting measurements.
- Today remains the execution surface. Johnny owns detailed review, advice, proposals, and decision history.
- Preserve Traditional Chinese product copy, existing five-item navigation, dark-green ruled surfaces, shared controls, and athlete-local dates and units.
- Keep all reads, mutations, jobs, deduplication keys, and revision references owner-scoped. Reuse existing authentication, retry/backoff, and queue mechanisms.
- Preserve original workout structure, Targets, race identity, plan metadata, and unaffected workouts on approval.
- No notifications, arbitrary workout rescheduling, full-plan regeneration changes, or new activity-deletion feature are in scope.

## Review Focus

1. A review crossing Plan Versions must use the prescription that applied when training occurred, not whichever plan is active now. Tested in Tasks 1–2.
2. A late recording or corrected pairing must update the score without inventing a new manual advice request or leaving an old proposal actionable. Tested in Tasks 4 and 7.
3. Two requests, two workers, or acceptance racing a plan change must result in one current output and at most one applied adjustment. Tested in Tasks 3, 5–6.
4. Local midnight, DST, travel/timezone changes, and jobs finishing on another date must never score unfinished training or apply yesterday's proposal. Tested in Tasks 1, 4–6.
5. A successful HTTP sync with incomplete activity pagination or skipped malformed records must not count absent workouts as missed. Tested in Tasks 2 and 4.

## 1. Agreed product specification

### 1.1 Daily review

Automatically sync and review yesterday at 04:00 local time. Show yesterday's planned-versus-actual execution, an explanation, and the seven-completed-day execution score with its components and evidence coverage. The result can identify a concern and invite the athlete to request workout advice, but cannot create an adjustment proposal.

04:00 is a publication time, not a guarantee of complete data. Incomplete evidence produces a provisional review. Late imports and pairing corrections revise affected retrospective results. Keep the original generation time, latest update time, period, timezone, evidence cutoff, and revision reason distinguishable.

### 1.2 Workout advice

The athlete selects `取得今日課表建議`. Sync again before evaluating current evidence, including today's completed activity. Optional structured inputs express less available time, greater tiredness, or inability to train. No conversational composer is required.

Every successful request returns useful guidance, including when the current workout remains appropriate. A supported change produces an evidence-backed Recommendation with an exact before/after comparison and `接受調整` / `維持原課表`. Acceptance applies that change; rejection leaves the workout intact. Advice alone never mutates the plan.

### 1.3 Page responsibilities

Johnny shows a compact latest-review summary; an actionable proposal when present; yesterday's execution; the seven-day score and breakdown; today's advice/request action; and paginated history. Put an actionable proposal immediately below the summary so it is easy to find. Keep the advice action visible near the top through an anchor or compact action row; do not require scrolling past history to request advice.

Today shows the canonical workout, completion evidence, and concise current execution guidance. It links to Johnny for review and decisions and no longer repeats the full review/advice document. No conversation teaser or placeholder weekly-review section remains.

### 1.4 Independent results and simultaneous display

This is an explicit user requirement, not an optional presentation choice. Johnny has two independently rendered sections: `每日回顧` for the latest daily review and its seven-day score, and `今日課表建議` for today's requested workout advice. They may be stacked responsively, but must not be mutually exclusive views or a single card that displays whichever result was generated most recently.

- A new workout advice revision replaces only the current advice for its own date/workout slot. It leaves the daily review's content, score, current revision, freshness, and generation time untouched.
- A new or corrected daily review replaces only its own review slot. It leaves current workout advice and its pending proposal untouched unless actual underlying evidence changed and independently triggered the existing invalidation rules.
- Each section owns its content, pending state, error, freshness, timestamp, retry action, and polling lifecycle. One section loading or failing cannot hide the other section's successful result. Either section can exist when the other has no result.
- Starting, finishing, retrying, or cancelling generation is not an evidence change. Publishing one output must not increment the shared coaching-input version or automatically enqueue the other workflow.
- Shared provider sync is permitted. If that sync discovers genuinely changed activities or coverage, use the evidence-change rules to update affected results independently; do not attribute that update to the existence of another advice result. Unchanged shared evidence leaves the other result unchanged.

Required acceptance sequence with unchanged evidence: publish review `R1`; publish advice `A1`; both remain visible; publish replacement advice `A2`; `R1` and `A2` remain visible; publish corrected review `R2`; `R2` and `A2` remain visible. Fail either subsequent refresh and preserve the other result plus the failed section's last successful content. Run the same sequence with reversed completion order and overlapping requests.

## 2. Proposed implementation policies to review with this plan

These are concrete defaults to make implementation testable, rather than claims that the user already approved the exact policies.

### 2.1 Score policy `execution-v1`

Use equal-weight completion and volume adherence. Exclude intensity/Target adherence from the numeric score in v1: the current model exposes activity aggregates, not reliable per-step execution. Show actual Target-related evidence only where supported, without calling average pace proof that interval steps were executed correctly.

For each eligible prescribed running workout `i` in the closed seven-day window:

- `c_i = 1` when one or more valid matched recordings establish a completed session; otherwise `0`, but only when coverage supports an absent session.
- Pick the comparison metric from the prescription: duration in seconds when a planned duration exists; otherwise distance in meters. Race workouts use distance.
- Sum all matched recordings for that workout once. Gaps between recordings are excluded. Multiple groups pointing to one workout do not create multiple completed workouts.
- For planned amount `P > 0` and actual amount `A`, `v_i = 0` when `A = 0`, otherwise `min(A / P, P / A)`. This is bounded by 1 and treats both under- and over-execution as deviations.
- `completion_component = 100 * mean(c_i)`; `volume_component = 100 * mean(v_i)`.
- `score = ROUND_HALF_UP((completion_component + volume_component) / 2)` to an integer from 0 to 100. Retain full precision until display rounding.

Examples: two exactly executed workouts score 100; one exact and one confirmed missed workout score 50; a completed 60-minute session prescribed as 40 minutes scores 83. Extra unpaired running cannot fill a missed workout or increase the score; show it separately as additional load. Do not add a score penalty for extra training in this first policy; explicitly disclose that limitation in the score explanation.

Rest days and a prospectively approved skipped workout are outside the denominator. A week with no eligible workouts has `score = null`, reason `no_prescribed_sessions`, not 0 or 100. A week with insufficient comparable measurements, ambiguous pairing, uncertain historical prescription, or incomplete activity coverage also has `score = null`, with a reason and the known counts. Do not compute a deceptively favorable score by silently dropping unknown prescribed sessions. Dates with no plan are labeled `no_plan`; a partial first week may score its known prescribed sessions, with the covered dates/session count visible.

### 2.2 Initial adjustment envelope `adjustment-v1`

Only today's not-yet-started, non-race running workout is mutable through the new advice flow. Other upcoming workouts may provide context but are not automatically changed in v1. If there are multiple eligible workouts today, require selecting one by id; do not silently use the first.

Structured input contract:

```text
WorkoutAdviceConstraints:
  available_minutes: integer 1..600 | null
  feeling: "usual" | "more_tired"       (default "usual")
  cannot_train_today: boolean             (default false)
```

`cannot_train_today=true` cannot be combined with `available_minutes`; return 422 with a field-level explanation. These inputs are request-scoped, not permanent Athlete Baseline edits. Display them in the result so the athlete can correct and resubmit.

Deterministic proposal precedence:

1. Already completed, any recorded activity matched to this workout, an unresolved possible match for today, expired date, superseded plan, or rest/race workout: no editable proposal. Explain completed/rest/uncertain/not-supported status appropriately.
2. Athlete cannot train today: propose `skip_today`, changing only workout status to `skipped` after acceptance.
3. Existing recovery assessment is `rest`, supported by available same-local-date recovery evidence: propose `skip_today`. Reuse existing RecoveryService policy; do not introduce new physiological thresholds here. Missing signals cannot manufacture a `rest` result.
4. A smaller `available_minutes` on an `easy_run` consisting of one duration-based `free_run` step: propose `shorten_easy_run`, setting total duration and that step's duration to the requested minutes, preserving its Target and other fields. If a total distance was merely paired with the old duration, clear that total distance in the proposed payload and explain it in the diff; never leave inconsistent totals. Preserve the warmup/cooldown or repeat structures of all other workouts by refusing this transformation on them.
5. Greater tiredness, caution, extra training, missed sessions, or unsupported shortening: return specific conservative guidance and `no_supported_adjustment`, without inventing a percentage reduction or claiming the canonical workout changed.

No increases, automatic catch-up workouts, arbitrary Target rewrites, race modifications, rescheduling, or whole-plan regeneration. Preserve evidence and policy version on every proposal. Further transformations can be added independently with their own structured validation and tests.

### 2.3 Pairing correction window

Expand the editable range from seven local dates including today to **today plus the previous seven completed local dates**, inclusive `[today - 7 days, today]`. This is an intentional change to the 2026-10-14 session-matching policy: every day in the current publication date's score must remain correctable. Historical decisions older than that remain readable and retained. Before 04:00, a previous publication date's review may still be shown with its original dates and the next review time; its oldest day can already be outside the edit window. Label that review by its actual publication date rather than pretending it covers the current seven-day window. Do not broaden recording groups across local dates or alter the existing maximum 30-minute grouping gap.

### 2.4 Scheduling and freshness

- Run once per owner/local publication date at the first scheduler tick at or after 04:00; use stored IANA timezone, not a fixed UTC offset.
- Review date `D = publication_date - 1 day`; window `[D - 6 days, D]`. Store both dates and the timezone snapshot.
- Schedule when a prescription exists in that retrospective window, even if no Active Projection owns today. This fixes the existing current-plan-only eligibility gap at the end of a plan.
- On restart at or after 04:00, catch up the current publication date; before 04:00, wait for that boundary. Do not enqueue a separate historical daily review for every day of a long outage; the next review covers the preceding seven days and history displays the gap truthfully.
- Page reads do not call the model. Missing today's scheduled review is repaired by the scheduler; an explicit retry action can requeue a failed existing review using the same date.
- A timezone change invalidates today's advice/proposals and schedules a replacement of the current review after the new zone's 04:00 boundary. Do not rewrite older published reviews into the new timezone. Same publication-date uniqueness prevents two current reviews during travel; a revised timezone is a new revision of that review.
- A manual advice request is bound to its captured local date. If generation finishes after that date changes, fail it as `request_date_expired`; retain older output as history and ask for a new request. No late proposal is published for yesterday.
- Reject invalid IANA timezones at profile write. For a legacy invalid timezone, skip scheduled generation, expose `timezone_invalid`, and require profile correction before requesting advice; do not silently substitute UTC for a decision about today. Tests must cover this consistently across scheduler, pairing and advice APIs.

## 3. Implementation boundaries and existing integration points

| Responsibility | Existing implementation | Change |
|---|---|---|
| Scheduling and worker dispatch | `scripts/agent_runtime.py` | Replace scheduled combined Daily Advice with daily review; dispatch distinct workflows; move coaching orchestration into application modules |
| Existing advice facts/generation | `backend/src/domain/daily_advice.py`, `backend/src/application/daily_advice_context.py`, `daily_advice_generation.py` | Keep legacy compatibility isolated; new retrospective facts are independent of Plan Week |
| Sync completion | `backend/src/application/integrations.py`, `daily_advice_sync.py`, `backend/src/api/routes/integrations.py` | Record changed evidence and coverage; refresh retrospective results, invalidate advice; no implicit manual advice generation |
| Matching and corrections | `backend/src/domain/activity_sessions.py`, `backend/src/infrastructure/database/session_review_repository.py`, `backend/src/api/routes/session_reviews.py` | Reuse matching, expand edit window, route invalidation through one service |
| Historical prescriptions | `backend/src/infrastructure/database/training_plan_repository.py` | Record effective prescription revisions; read them without current-target enrichment |
| Approval | `backend/src/application/recommendation_approval.py`, repository and API | Compare-and-set decision and targeted workout update in one transaction; preserve all unrelated data |
| Today | `backend/src/api/routes/today.py`, `frontend/src/App.vue` | Consume current manual advice summary; remove full duplicated advice presentation |
| Johnny | `frontend/src/App.vue`, shared components | Extract a page component and data composable; remove placeholder review |

New domain modules: `training_review.py` (immutable types, period rules), `execution_score.py` (numeric policy), `workout_advice.py` (constraints, result, proposal transformation policy). New application modules: `coaching_evidence.py`, `training_review_generation.py`, `workout_advice_generation.py`, `coaching_refresh.py`, and `coaching_sync.py`. Do not move unrelated training-plan/conversation code in this change.

### 3.1 Persistence contract

Add migration `0012_add_training_reviews_and_workout_advice.py` after current head `0011_add_daily_advice` (rebase the revision number if another migration lands first).

| Table/change | Required contents and invariants |
|---|---|
| `workout_prescription_revisions` | Owner, workout/plan ids, effective timestamp, local scheduled date, complete canonical workout payload, source (`generation`, `approved_adjustment`, `legacy_backfill`), confidence (`known`, `legacy_uncertain`), originating recommendation. Append-only; an approved adjustment creates a new revision in the same transaction as the workout update. |
| `plan_activation_revisions` | Owner, plan id, effective timestamp, effective local date, timezone, predecessor reference. Resolve which projection owned each date, including plan gaps. Preserve pre-change effective intervals; do not infer history solely from current plan status. |
| `coaching_input_versions` | One owner row with monotonic `revision` and timestamp. A shared lock/CAS boundary for evidence writes, publication, and acceptance. Advance only on relevant content/coverage changes, not every no-op sync. |
| `training_reviews` | Unique `(user_id, publication_date)`; reviewed date, seven-day bounds, timezone, current revision pointer, latest attempt state/error, reserved generation number. Prior successful revision remains accessible during refresh/failure. |
| `training_review_revisions` | Owner/review/run ids, immutable facts, score/components/policy, coverage, narrative, concern codes, content fingerprint, input revision, evidence cutoff, source sync ids, created time and revision reason. Unique `(review_id, content_fingerprint)`. |
| `workout_advices` | Current slot unique `(user_id, advice_date, workout_id)`; use a non-null slot key for rest/no-workout results to avoid nullable uniqueness differences between SQLite and PostgreSQL. Holds current revision pointer, attempt status, reserved generation number, freshness and stale reasons. |
| `workout_advice_revisions` | Owner/slot/run ids, constraints, canonical workout snapshot and fingerprint, evidence fingerprint/input revision, validated mode/text, proposal reference if any, generated time, expiry at next local midnight, policy/prompt versions. Immutable. |
| Recommendation extension | Explicit source-advice-revision id, canonical workout fingerprint, evidence fingerprint, decision fingerprint, expiry, invalidation reason. Keep existing `pending`, `decided`, `superseded` states; expired/stale pending proposals become `superseded` with a reason. |
| Sync coverage metadata | Store the requested local-date window, timezone, completed-pagination flag, skipped/failed activity counts and completion instant on the sync result. A `failed=0` bucket alone does not prove complete coverage. |

Prescription snapshots must survive replacement/deletion of their source workout rows. Retain immutable logical source ids in the snapshot; any optional live-row FK uses `SET NULL`, never cascading deletion of historical evidence. Ownership remains a required FK. Record plan activation and any genuinely persisted prescription changes inside the same transaction as their source write; dynamically estimated display-only Targets do not silently become a historical prescription revision.

All output publication uses an owner lock plus CAS on the slot's reserved generation number. Generate text outside the transaction, then recheck the evidence fingerprint and reservation inside a short transaction. If relevant inputs changed, discard the output and mark the attempt `inputs_changed`; do not publish a proposal from that attempt. A retrospective refresh may queue one replacement; a manual advice request asks the athlete to retry. Changes irrelevant to the target period/workout do not reject a result merely because the owner's global revision advanced.

Generation reservations, execution slots, idempotency keys and current pointers are namespaced by workflow kind as well as owner/date/workout. Use `daily_review:{user_id}:{publication_date}` for a scheduled review and the separately defined `workout_advice` request keys. There is no owner/date-wide “latest coaching result” pointer or shared generation counter. Reject a review reservation passed to advice publication and vice versa. A brief shared owner lock coordinates genuine evidence races; it does not make the two workflows mutually exclusive for their entire run. Output publication itself does not advance `coaching_input_versions`.

Canonical fingerprints exclude display names, translated copy, timestamps with no content changes, and database update timestamps. Include canonical workout structure/Targets, relevant activity measurements and pairings, coverage, current recovery evidence, constraints, timezone/date, and policy version. Sort ids and serialize dates/numbers consistently. Separate `decision_fingerprint` from full evidence fingerprint: the former includes the target workout and normalized actionable policy findings/constraints, allowing rejection suppression when another sync produces the same proposal for the same substantive reasons.

Persist manual request identity using the existing unique AgentTask idempotency key `workout_advice:{user_id}:{client_request_id}` and its stored input/body hash, with terminal reuse enabled for transport retries. Reserve the owner/date/workout execution slot before enqueueing so distinct concurrent request ids cannot race into separate runs. A deliberate retry after a failed terminal run uses a new request UUID; a network retry reuses the original one. Normalize and compare the saved body before returning an existing run. Never silently replace the constraints attached to an existing key.

Historical scoring selects the prescription effective before the earliest matched activity start, or at the end of that local date when no activity exists. Acceptance is forbidden once there is any matching/possibly matching activity evidence. A later import proving activity began before an accepted adjustment uses the earlier prescription for retrospective scoring; it does not silently reverse the already recorded decision. Surface the corrected review reason.

Legacy backfill must not invent effective timestamps. Use persisted plan/adjustment history when it establishes ordering; otherwise mark the past prescription `legacy_uncertain` and withhold the score for affected windows. Capture trustworthy current/future snapshots at migration/cutover time. Legacy Daily Advice text is not migrated into a retrospective review because it has different meaning and periods.

Advice can become stale while an accepted Recommendation remains an accepted historical decision. On acceptance, show an applied-result receipt with the new canonical workout immediately; mark any execution text tied to its old prescription stale. Do not keep presenting the old text as current guidance and do not call the model automatically. The athlete may explicitly request advice for the adjusted workout.

### 3.2 API contract

All endpoints are under `/api/v1`, authenticated and owner-scoped; dates are ISO local dates and timestamps are timezone-aware UTC instants.

| Endpoint | Contract |
|---|---|
| `GET /johnny/overview` | Server-derived local date/timezone; separate named fields `daily_review` and `workout_advices`, each carrying its own result/revision, attempt state/error and freshness; actionable proposals independently of history pagination; available workout choices and no-plan/rest state. Both fields are present regardless of which result is newer. Missing review is represented by a null review result, missing advice by an empty slot list; no generic `latest_advice` field chooses between them. No generation side effect. |
| `GET /johnny/reviews?limit=20&offset=0` | Existing `ListEnvelope` pagination, newest publication date first; one current revision per date. |
| `GET /johnny/reviews/{id}` | Current revision and revision metadata, owner-scoped. |
| `POST /johnny/reviews/{id}/retry` | Only retries failed/stale retrospective output for its existing period; reuses existing in-flight run; no workout advice/proposal. |
| `POST /johnny/workout-advice` | Body `{client_request_id: UUID, workout_id: UUID|null, constraints: WorkoutAdviceConstraints}`. Server chooses today's date. 202 with `{run_id,status,workflow_name,poll_url}`. A repeated request id with the same body returns the same run; the same id with another body returns 409. Different simultaneous requests for the same slot return 409 `advice_in_progress` plus current run id, rather than silently discarding different constraints. |
| `GET /johnny/workout-advice/{id}` | Current slot/result, attempt stage, freshness, expiry, and proposal link. |
| `GET /johnny/history?limit=20&offset=0` | One row per daily review and manual advice request plus recommendation decisions; each row has `kind: daily_review|workout_advice|recommendation_decision` and a stable resource id. Stable newest-first ordering by event timestamp/id. Corrections update the daily-review row with revision metadata; retries/no-op syncs do not create duplicate content rows. Timeline ordering does not determine either current result slot. |
| Existing `GET /agent-runs/{id}` | Retain polling; add nullable `training_review_id`, `workout_advice_id`, and `result_state`. Agent status stays queued/started/completed/failed; review result states live in metadata. |
| Existing recommendation accept/reject | Typed 409 for stale, expired, conflicting, or already-oppositely-decided requests. Repeated identical acceptance/rejection returns the already-decided resource without applying again; owner mismatch is 404. |
| Existing `GET /today` | Add `workout_advice` summary and freshness; continue canonical scheduled workouts. During transition `daily_advice` is nullable/deprecated and must not masquerade as a new review. |

Result attempt states: `queued`, `syncing`, `analyzing`, `ready`, `needs_pairing`, `sync_failed`, `generation_failed`, `inputs_changed`, `request_date_expired`. Freshness is separate: `current`, `limited`, `stale`; a review can be ready with provisional coverage. An unresolved pairing that affects scoring withholds the score; one affecting today's workout blocks an editable proposal. No-plan/rest/completed are truthful content outcomes, not generic server errors.

### 3.3 Event behavior

| Event | Retrospective review | Manual advice/proposals |
|---|---|---|
| Scheduled 04:00 run | Sync then publish latest review | No generation or proposal |
| Manual sync elsewhere | Recompute affected existing reviews if relevant data/coverage changed | Mark relevant advice stale and supersede conflicting proposals; no generation |
| Pairing saved | Invalidate immediately; queue correction for reviews containing that date | Invalidate affected advice/proposals; no generation |
| Activity created/updated | Same as pairing, using old and new local dates if timestamp changed | Same invalidation |
| Health/Baseline/Target changes | Refresh only reviews whose explanatory inputs change; execution score depends on activity/prescription evidence | Invalidate relevant advice/proposals |
| Plan activation or status mutation | Preserve historical prescriptions; refresh affected review only if its historical truth changed | Invalidate proposals whose target plan/workout is no longer current |
| Accept | Historical periods unchanged; record prospective revision | Record applied decision, update Today/Plan, invalidate other affected advice; never automatically call the model |
| Reject | No change | Record decision, suppress same decision fingerprint until substantive reasons/constraints/workout change |
| Provider disconnect/failure | Retain last-good content; label freshness/coverage truthfully | Invalidate evidence-dependent proposals; never substitute missing recovery with normal readings |

Record invalidation and durable refresh intents in the same database transaction as the mutation. Coalesce retrospective refreshes in a per-review queue slot with a short 5-second delay; if more data arrives while running, one follow-up consumes the newest revision. Do not sleep in a request or start a sync per individual imported activity. No new advice request is synthesized from an invalidation event.

## 4. Ordered implementation tasks

All commands below run from the repository root. Use `./.venv/bin/python -m pytest` locally (the Makefile's Python default); CI uses `python -m pytest`. Each task follows red → green → focused review → commit. Keep the pre-existing modification to `premium-audit.json` out of commits unless the implementation deliberately regenerates and reviews it.

### Task 1: Preserve effective prescriptions and resolve retrospective periods

**Files:** Create `backend/src/domain/training_review.py`, `backend/src/application/interfaces/coaching_store.py`, `backend/src/infrastructure/database/coaching_repository.py`, and migration `backend/migrations/versions/0012_add_training_reviews_and_workout_advice.py`. Modify `backend/src/infrastructure/database/models.py`, `training_plan_repository.py`, `backend/src/application/interfaces/training_plan_store.py`. Tests: create `backend/tests/unit/test_training_review_periods.py`, `backend/tests/integration/database/test_prescription_history.py`; extend `test_alembic_migrations.py` and `test_persistence_metadata.py`.

**Interfaces:**
- `review_period(publication_date: date) -> ReviewPeriod` with `reviewed_date`, `starts_on`, `ends_on`.
- `PrescriptionSnapshot` contains owner, plan/workout ids, full canonical workout, effective interval and confidence.
- `CoachingStore.list_prescriptions(user_id: str, starts_on: date, ends_on: date, timezone_name: str, activity_starts: dict[str, datetime]) -> tuple[PrescriptionSnapshot, ...]` returns effective historical prescriptions, not enriched current workouts.
- `CoachingStore.record_plan_activation(*, user_id: str, plan_id: str, effective_at: datetime, effective_local_date: date, timezone_name: str, previous_plan_id: str | None) -> str` records activation inside the source transaction and returns the revision id.
- `CoachingStore.record_prescription_revision(*, user_id: str, plan_id: str, workout: Workout, effective_at: datetime, source: str, confidence: str, recommendation_id: str | None) -> str` records the complete canonical prescription inside the source transaction and returns the revision id. Validate `source` and `confidence` against §3.1; reject owner mismatches.

- [ ] Write period tests asserting publication `2026-10-16` reviews `2026-10-15` and scores `2026-10-09..2026-10-15`; test month/year/leap-day boundaries. Write history fixtures spanning two plan versions, an approved same-day adjustment, a late activity beginning before acceptance, a plan gap, and uncertain legacy ordering.
- [ ] Run `./.venv/bin/python -m pytest backend/tests/unit/test_training_review_periods.py backend/tests/integration/database/test_prescription_history.py -q`; confirm tests fail because the new behavior is absent.
- [ ] Add append-only activation/prescription persistence and migration/backfill from available evidence. Snapshot all canonical fields, including steps, phase, coach note and race identity. Resolve history without calling `_resolve_targets`; no later athlete setting may rewrite a past Target. Reject overlapping ambiguous effective ownership as `legacy_uncertain`.
- [ ] Run the two test files plus `backend/tests/integration/database/test_alembic_migrations.py` and `test_persistence_metadata.py`; verify fresh installation and upgrade from 0011 both pass with retained old data.
- [ ] Commit the tested schema/history slice: `feat: preserve effective workout prescriptions for reviews`.

**Done when:** A historical seven-day window has a deterministic prescription per scheduled session or an explicit uncertainty reason, even after plan replacement. No migration relabels old advice as new review content.

### Task 2: Compute execution facts, coverage, and the score

**Files:** Create `backend/src/domain/execution_score.py`, `backend/src/application/coaching_evidence.py`; extend `training_review.py`, `backend/src/domain/activity_sessions.py` only where necessary to reject invalid historical links. Modify `backend/src/application/integrations.py` to capture coverage, and its existing sync summary schema if needed. Tests: create `backend/tests/unit/test_execution_score.py`, `test_coaching_evidence.py`; extend existing integration sync tests for pagination/coverage.

**Interfaces:**
- `ReviewEvidence` contains period/timezone/cutoff, prescription snapshots, running sessions, extra sessions, per-date coverage and uncertainty reasons.
- `build_review_evidence(*, user_id: str, period: ReviewPeriod, timezone_name: str, as_of: datetime, store: CoachingStore) -> ReviewEvidence`.
- `score_execution(evidence: ReviewEvidence) -> ExecutionScore` with nullable integer value, completion/volume components, eligible/completed/missed/extra counts, reason codes and `policy_version='execution-v1'`.

- [ ] Add tests asserting exact scores 100, 50 and 83 from §2.1; duplicate groups never double-count completion; extra 60-minute activity cannot compensate for a missed 30-minute prescription; zero running on an all-rest week returns null. Assert missing comparison metrics, uncertain prescriptions, partial pagination and ambiguous pairing withhold the score rather than drop denominators.
- [ ] Run `./.venv/bin/python -m pytest backend/tests/unit/test_execution_score.py backend/tests/unit/test_coaching_evidence.py -q` and confirm the new tests fail.
- [ ] Implement the formula with explicit half-up rounding, duration-first comparison, race-distance fallback, and local-date boundaries. Query enough UTC margin then filter using `ZoneInfo`; a recording belongs to its local start date, including one crossing midnight. Persist per-sync coverage independently from recovery success. Provider omission is not an activity deletion; do not infer tombstones from an absent row in a later feed.
- [ ] Run these tests plus `backend/tests/unit/test_daily_advice_policy.py` and the sync test files touched. Add a 23:30-local/UTC-next-day fixture, same-day multi-session fixture, skipped-malformed-record fixture and one legitimate distance-only race; all must pass.
- [ ] Commit: `feat: calculate explainable seven-day execution scores`.

**Done when:** The same committed inputs always give the same facts and score; every withheld score explains why; incomplete current-day workouts never enter the closed-day denominator.

### Task 3: Persist separate review/advice outputs and revision-safe publication

**Files:** Extend migration 0012, `models.py`, `coaching_repository.py`, and `coaching_store.py`; create `backend/src/domain/workout_advice.py`. Extend `backend/src/domain/recommendation_approval.py` and `backend/src/infrastructure/database/recommendation_repository.py` for source/fingerprint metadata. Tests: create `backend/tests/integration/database/test_coaching_repository.py`, `backend/tests/unit/test_coaching_fingerprints.py`.

**Interfaces:**
- `reserve_review(user_id: str, publication_date: date, timezone_name: str, run_id: str) -> GenerationReservation`.
- `reserve_advice(user_id: str, advice_date: date, slot_key: str, run_id: str, constraints: WorkoutAdviceConstraints) -> GenerationReservation`.
- `GenerationReservation` contains owner, `workflow_kind: Literal['daily_review', 'workout_advice']`, slot id, generation number and input revision.
- `publish_review(reservation: GenerationReservation, revision: TrainingReviewRevision) -> bool`; `publish_advice(reservation: GenerationReservation, revision: WorkoutAdviceRevision, proposal: Recommendation | None) -> bool`.
- `mark_attempt_failed(reservation: GenerationReservation, state: str, reason_code: str) -> None` may update only the still-current reservation; it never deletes the previous revision.
- `EvidenceChange` contains owner, kind, old/new affected dates, affected workout ids and event id; this type is consumed by Task 7.

- [ ] Test two same-date reservations, out-of-order completions, repeated identical publication, failure after a previous success, different owners with identical dates, and null-workout rest slots. Assert an advice revision and its proposal either both commit or neither does. A deliberately failed older run must not mark the newer successful output failed.
- [ ] Add `test_review_and_advice_publication_are_independent`: reserve both workflows for the same owner/date and complete them in both orders. Assert advice publication changes neither the review row/revision nor its attempt state, freshness, timestamp or score; assert the reverse for review publication. Updating either result preserves the other's current pointer. Wrong-kind reservations are rejected and publication does not advance the input revision.
- [ ] Run `./.venv/bin/python -m pytest backend/tests/integration/database/test_coaching_repository.py backend/tests/unit/test_coaching_fingerprints.py -q`; confirm red.
- [ ] Implement §3.1 with unique constraints, owner locks/CAS and full transactional publication. Persist immutable successful revisions and separate mutable attempt state. Centralize canonical serialization and semantic decision fingerprints; equal content must hash equally despite ordering or no-op sync timestamps.
- [ ] Run both suites and migration tests; simulate a commit failure between proposal insertion and advice pointer update and verify rollback. Exercise real concurrent sessions on PostgreSQL in the database integration stage, not only a sequential SQLite approximation.
- [ ] Commit: `feat: persist independent coaching reviews and advice revisions`.

**Done when:** Each slot has one current successful revision, failures retain previous content, stale workers cannot publish, and no orphan pending proposal can escape a failed publication.

### Task 4: Replace the scheduled workflow with retrospective daily review

**Files:** Create `backend/src/application/coaching_sync.py`, `training_review_generation.py`, and `backend/src/infrastructure/llm/coaching_output.py`; modify `scripts/agent_runtime.py`, `backend/src/application/async_agent_runs.py`, `backend/src/infrastructure/llm/local_gateway.py`, `openai_gateway.py`, and relevant tool/schema registration. Tests: create `backend/tests/unit/test_training_review_schedule.py`, `test_training_review_generation.py`, `backend/tests/integration/application/test_training_review_flow.py`.

**Interfaces:**
- `CoachingSyncService.prepare(user_id: str, required_start: date, required_end: date, run_id: str) -> SyncEvidenceResult` with usable activity coverage, missing recovery signals, cutoff and source sync ids.
- `GenerateTrainingReviewHandler.handle(user_id: str, publication_date: date, timezone_name: str, run_id: str) -> TrainingReviewResult`.
- Workflow `daily_review`; task types `coaching.sync` and existing `agent.workflow`, carrying explicit workflow and scope. Preserve the independent `training-plan.daily-check` task.
- `composeTrainingReview` accepts constrained explanation fields tied to deterministic facts; no workout mutation or Recommendation tool is registered for this workflow.

- [ ] Add fake-clock tests for 03:59/04:00, repeated ticks, DST, invalid timezone, timezone change, restart catch-up and a just-ended plan with no current-day workout. Integration test sync → commit → facts → model → publication, and assert zero new Recommendations.
- [ ] Run the three new suites with pytest and confirm failure for the missing split workflow.
- [ ] Extract the reusable sync/lease/defer behavior from the current runtime script. Do not hold an application database transaction across model calls. Reuse an in-progress provider sync only after it commits and its covered dates meet the request; defer with existing backoff otherwise. Use §2.4 scheduling. Generate deterministic score/facts first; the model supplies concise explanation without changing facts. Missing health alone permits a limited result; failed activity sync retains prior content and publishes no fresh missed-session claim. With no connection, known manual activities may be described but missing activity remains unknown.
- [ ] Run the new suites and `backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`. Test invalid/extra model fields, fabricated score fields, empty narrative, provider timeout, no connection, and partial recovery. All failures preserve last-good content and never create a proposal.
- [ ] Commit: `feat: schedule retrospective daily training reviews`.

**Done when:** 04:00 creates exactly one current retrospective result for the due date, covers the correct seven closed days, and has no authority to create or apply workout changes.

### Task 5: Implement requested workout advice and bounded proposals

**Files:** Create `backend/src/application/workout_advice_generation.py`; extend `workout_advice.py`, `coaching_output.py`, `coaching_store.py`, `coaching_repository.py`, `scripts/agent_runtime.py` and `async_agent_runs.py`. Tests: create `backend/tests/unit/test_workout_advice_policy.py`, `test_workout_advice_generation.py`, `backend/tests/integration/application/test_workout_advice_flow.py`.

**Interfaces:**
- `WorkoutAdviceConstraints` exactly as §2.2.
- `assess_workout_advice(*, workout: Workout | None, evidence: AdviceEvidence, constraints: WorkoutAdviceConstraints, now: datetime) -> AdviceDecision` with mode, reason codes, guidance facts, and optional validated canonical after-payload.
- `AdviceEvidence` extends review evidence with today's matched/unresolved activity, same-day recovery assessment and signal dates, current canonical workout, relevant baseline and upcoming context. It excludes future observations.
- `RequestWorkoutAdviceHandler.handle(user_id: str, client_request_id: str, workout_id: str | None, constraints: WorkoutAdviceConstraints) -> QueuedAgentRun`.
- `GenerateWorkoutAdviceHandler.handle(user_id: str, run_id: str) -> WorkoutAdviceResult` reads the saved request; it cannot substitute newer constraints under the same request id.

- [ ] Write table-driven tests for every policy row in §2.2. Assert `cannot_train_today` proposes only status `skipped`; simple easy-run shortening changes only the approved duration/distance fields; tiredness alone does not invent a numeric reduction; completed/rest/race/multi-step or ambiguously matched workouts are not transformed. Tests assert equivalent decision fingerprints reuse a pending proposal or suppress a rejected one.
- [ ] Run the three new test suites and confirm red.
- [ ] Implement explicit request persistence, sync-before-assessment, canonical proposal validation, model-only explanation, and transactional advice/proposal publication. Advice plus proposal is one successful outcome. Use today's completion evidence even though the seven-day review excludes today. For unknown past coverage, advice can describe limits, but only a direct athlete constraint with a confirmed unstarted target can support a change independent of that missing history. On activity sync failure, block publication of a new actionable proposal.
- [ ] Run the new suites; exercise double-click with the same request id, conflicting body reuse, two different constraints while a request runs, midnight expiration, model failure, a new activity arriving during generation, and no material changes after sync. Keep the sync step but reuse a successful unchanged result after checking fingerprints; do not call the model unnecessarily.
- [ ] Commit: `feat: generate athlete-requested workout advice and proposals`.

**Done when:** Only an explicit request generates today's advice; useful no-change guidance exists; supported adjustments have exact validated diffs and fresh provenance; no request directly edits a workout.

### Task 6: Apply approved adjustments atomically without losing structure

**Files:** Modify `backend/src/application/recommendation_approval.py`, `backend/src/application/interfaces/recommendation_store.py`, `training_plan_store.py`, `backend/src/infrastructure/database/recommendation_repository.py`, `training_plan_repository.py`, `backend/src/api/routes/recommendations.py`, `training_plans.py`, and recommendation schemas/errors. Tests: extend `backend/tests/unit/test_recommendation_approval_application.py`, `backend/tests/integration/database/test_recommendation_approval_repositories.py`; create `backend/tests/integration/application/test_coaching_approval_races.py`.

**Interfaces:**
- `accept_coaching_proposal(user_id: str, recommendation_id: str, now: datetime) -> RecommendationDecisionResult` performs the owner/version checks and writes in one transaction.
- `RecommendationDecisionResult` exposes the saved Recommendation and `applied_workout_id`; errors distinguish not-found, stale/expired, and conflicting-decision.
- `update_workout_if_current(user_id: str, plan_id: str, workout_id: str, expected_fingerprint: str, after: Workout) -> bool` updates the target row only. It must not replace the parent plan's entire workout collection.

- [ ] Test full payload preservation using a plan containing structured repeats, Targets, phases, coach notes and race identity. Test approval twice, approval vs rejection concurrently, evidence update vs approval, plan supersession, matched activity discovered just before acceptance, expired proposal, and persistence failure after decision write. Assert one adjustment audit row and one prescription revision on success; assert no partial writes on failure.
- [ ] Run the existing approval suites plus the new race suite and confirm the new preservation/concurrency tests fail on current behavior.
- [ ] Replace partial reconstruction with validated full-domain parsing and targeted update. Serialize all relevant mutation paths using the owner's coaching-input lock/CAS; preserve lock order owner → proposal → workout. Recheck canonical/evidence fingerprints, current plan ownership, current date, and completion under that boundary. Save decision, workout, prescription revision and invalidations together. Return the existing decision for an identical retry, 409 for an opposite decision or stale payload, 404 for another owner's resource.
- [ ] Run focused tests on SQLite and PostgreSQL. Assert rejection stores the decision fingerprint and leaves the complete canonical workout unchanged. Only new server-created `workout_advice` revisions may originate an acceptable coaching proposal. Existing public `POST /recommendations` and `POST /recommendations/{id}/edit` return 403 `workout_advice_required` for `adjust_workout`; no client can set trusted provenance. Existing `PATCH /training-plans/{plan_id}/workouts/{workout_id}` rejects direct `adjusted`/`skipped` transitions with the same code. Retained completion-status behavior is execution metadata, not scoring evidence; score from activities. Existing plan generation/creation is still a distinct supported workflow, not a generic workout editor. Supersede incompatible legacy pending proposals at cutover rather than accepting unversioned snapshots.
- [ ] Commit: `fix: apply coaching adjustments atomically and preserve workout data`.

**Done when:** Accept changes precisely the previewed fields once, preserves every other field, and is impossible after a relevant conflict. Reject never changes training. Existing public status/create/edit routes cannot serve as a backdoor to the new approval contract.

### Task 7: Centralize invalidation and retrospective correction triggers

**Files:** Create `backend/src/application/coaching_refresh.py`; modify `backend/src/application/integrations.py`, `daily_advice_sync.py`, `backend/src/api/routes/integrations.py`, `session_reviews.py`, `activity_health.py`, `athlete_profile.py`, `training_plans.py`; modify `activity_repository.py`, `session_review_repository.py`, `training_plan_repository.py`, and profile persistence to report content changes. Tests: create `backend/tests/integration/application/test_coaching_invalidation.py`; extend `backend/tests/unit/test_session_reviews_api.py`.

**Interfaces:**
- `CoachingRefreshService.record_change(change: EvidenceChange) -> RefreshEffects` records the version bump, stale markers, proposal supersession and durable review refresh intent inside the caller's transaction.
- `RefreshEffects` contains affected review ids, invalidated advice ids, and superseded recommendation ids. No manual advice run id is produced.
- Repository content comparisons report changed fields/dates; no-op syncs do not invalidate results. Import batches emit one logical change set at successful commit.

- [ ] Test every row of §3.3, including direct activity/health APIs and target-evidence updates, not only the Garmin route. Assert old and new dates are included when an activity timestamp changes; review correction creates no manual advice or adjustment. Test day `today-7` pairing is editable and `today-8` is rejected.
- [ ] Run `./.venv/bin/python -m pytest backend/tests/integration/application/test_coaching_invalidation.py backend/tests/unit/test_session_reviews_api.py -q`; confirm expected failures.
- [ ] Implement coalesced transactional refresh intents, immediate invalidation and bounded follow-up on in-flight changes. Remove automatic combined Daily Advice generation from integration/session-review routes. Apply the eight-date window consistently in list/save APIs. Future deletion support must invoke `record_change` with the old date; do not add a deletion endpoint now or interpret provider omission as deletion.
- [ ] Run these suites and existing integration lifecycle/pairing tests. Verify a rolled-back mutation creates no visible invalidation/job, a batch of 50 activities creates bounded review jobs, and a worker crash after mutation commit does not lose the refresh intent. Test provider disconnect and partial failed imports; advice cannot continue appearing fresh merely because the overall sync failed.
- [ ] Commit: `feat: refresh retrospective reviews and invalidate outdated advice`.

**Done when:** Every existing relevant write path updates freshness consistently; stale proposals are blocked immediately; changes never implicitly request workout advice; every scored day remains correctable.

### Task 8: Expose the Johnny read/request API and migrate existing consumers

**Files:** Create `backend/src/api/routes/johnny.py`, `backend/src/api/schemas/johnny.py`; modify `backend/src/main.py`, `backend/src/api/routes/agent_runs.py`, `today.py`, `session_reviews.py`, integration/agent-run response schemas. Tests: create `backend/tests/unit/test_johnny_api.py`; update `test_daily_advice_api.py` for explicit compatibility behavior.

**Interfaces:** Implement §3.2 exactly. Typed frontend DTOs in Task 9 mirror snake_case transport fields and map once at the boundary. Return stable reason codes independently of localized display text.

- [ ] Write API tests for every route, owner isolation, 202/poll/read lifecycle, 409 idempotency conflicts, 422 invalid constraints, server-derived date, pagination and ordering, retry behavior, and overview pending proposals independent of history page size. Assert GET never enqueues work.
- [ ] Add `test_overview_returns_review_and_advice_independently`: complete the §1.4 sequence and assert both named fields retain the expected distinct ids and revision numbers. Test review-only, advice-only, both-present, one-pending, one-failed and one-expired states. A newer result's timestamp never removes the other field or substitutes its payload.
- [ ] Run `./.venv/bin/python -m pytest backend/tests/unit/test_johnny_api.py backend/tests/unit/test_daily_advice_api.py -q` and confirm red for new contracts.
- [ ] Implement routes/schemas/composition and response mapping. Keep `POST /agent-runs/daily-recommendation` as a documented deprecated manual-advice adapter during one transition release: accept only today's anchor, no scheduled calls, translate to the new request workflow and keep the polling contract. `force` cannot bypass concurrency, evidence freshness or approval. Legacy sync response `daily_advice_run` becomes null; add `review_refresh_runs` and `advice_invalidated` where needed. Document the adapter removal condition in release notes.
- [ ] Run API tests plus authentication/owner-scope regressions. Ensure unknown ids and other owners' ids have indistinguishable 404 behavior. Existing-resource ownership checks run before action-policy errors so 403 responses cannot expose another owner's ids. Test an old frontend reading nullable legacy fields and the new frontend on an empty database. Update direct status/Recommendation-edit tests to the deliberate Task 6 restriction rather than retaining an accidental bypass.
- [ ] Commit: `feat: expose Johnny review and workout advice contracts`.

**Done when:** The frontend can render every state and complete advice/approval flows using typed endpoints, while old combined-advice callers cannot restore scheduled proposals or automatic manual advice generation.

### Task 9: Build Johnny's page and connect Today without duplicate content

**Files:** Create `frontend/src/pages/JohnnyPage.vue`, `frontend/src/composables/useJohnny.ts`, `frontend/src/components/TrainingReview.vue`, `ExecutionScore.vue`, `WorkoutAdviceRequest.vue`, `WorkoutAdviceResult.vue`, `CoachingHistory.vue`; modify `frontend/src/App.vue`, `api/client.ts`, `types.ts`, `styles.css`, `components/RecommendationActions.vue`, `components/SessionReviews.vue` and fixtures. Tests: create `frontend/src/JohnnyPage.test.ts`, `frontend/src/composables/useJohnny.test.ts`, `frontend/src/components/ExecutionScore.test.ts`, `WorkoutAdviceRequest.test.ts`; extend `App.test.ts` and `components/SessionReviews.test.ts`.

**Interfaces:**
- `useJohnny()` owns `dailyReviewState`, `workoutAdviceStateBySlot`, and paginated history. Each stream has independent current data, error, pending run id, poll timer, request generation and cancellation; no shared `currentAdvice` ref or page-wide loading/error branch replaces both. A new advice request cancels only observation of its own slot; sign-out/unmount cancels all. Apply returned revisions per resource and ignore stale responses so an older overview response cannot undo newer advice or review state. Emit a successful decision callback so App refreshes Today and Plan.
- `JohnnyPage` consumes the composable and emits navigation requests to Plan/Data/activity pairing through the existing app shell. No new global router is required.
- `ExecutionScore` receives typed score/components/coverage; it never calculates or fills in a missing score.
- `WorkoutAdviceRequest` emits the selected workout and typed constraints, creates one request UUID per intended submit, and reuses it for transport retries.

- [ ] Write tests for initial review, no-review, no-plan/rest/completed, partial first week, null score with reason, pending proposal, no-change advice, limited data, sync/model failures, stale result, pairing correction and expiry. Assert the public page has neither conversation copy nor duplicated full Today advice. Assert one request for a double-click and editable constraints after failure.
- [ ] Add UI/composable tests `renders_daily_review_and_workout_advice_together`, `refreshing_or_failing_advice_keeps_review_visible`, `refreshing_or_failing_review_keeps_advice_visible`, and `independent_pollers_ignore_out_of_order_responses`. Use distinct fixture text/ids for `R1`, `R2`, `A1`, `A2` and assert the §1.4 sequence in the DOM. Include either result absent, simultaneous generation, advice expiry, and a late overview response. Both sections retain their own labels and timestamps on a narrow viewport.
- [ ] Run `npm --prefix frontend run test -- src/JohnnyPage.test.ts src/composables/useJohnny.test.ts src/components/ExecutionScore.test.ts src/components/WorkoutAdviceRequest.test.ts`; confirm red.
- [ ] Implement §1.3 using existing AppButton, StatusBadge, EvidenceList, RecommendationActions and modal primitives. Use text-labeled seven-day rows and an expandable score explanation rather than an unexplained gauge. Keep prior text visible while updating; display generation time separately from last sync. Poll existing agent runs with bounded backoff and cancel on unmount/sign-out/new request. At timeout show a recoverable pending state; resume by reading the server on page revisit. Revalidate date/expiry on focus and local midnight. Persist no sensitive constraints in URLs/local storage.
- [ ] Update Today to use current manual guidance only; missing/stale guidance falls back to canonical workout and existing conservative evidence, with a Johnny link. Accepted skip/shortening must immediately refresh Today and Plan. Expand pairing navigation/list bounds to the eight-date contract and preserve its existing controls. Run `npm --prefix frontend run test`, `npm --prefix frontend run build`, and `npm --prefix frontend run verify:tokens`; all must pass.
- [ ] Commit: `feat: make Johnny the training review and advice surface`.

**Done when:** An athlete can understand yesterday and the score, request advice, repair pairing, accept/keep a proposal, and inspect history on desktop and mobile without needing conversation or duplicating Today.

### Task 10: End-to-end verification, product docs, and controlled cutover

**Files:** Create `backend/tests/integration/application/test_johnny_coaching_lifecycle.py`, `docs/verification/2026-10-16-johnny-review-and-advice.md`; update `CONTEXT.md`, `DESIGN.md`, `UX-CONTRACT.md`, `scripts/agent_runtime.py` smoke coverage, and relevant `openspec/specs` contracts after reading `openspec/AGENTS.md`. Update GitHub requirements through `gh` during implementation so the tracker reflects the reviewed plan; use a body file and preserve links to #13/#14. Do not silently rewrite older historical planning documents.

- [ ] Add a fake-clock lifecycle test: at 04:00 publish a retrospective review without proposals; import a late activity; correct pairing; verify revised score; request today's advice; inspect before/after; accept; confirm exact canonical update and Today refresh; request again with unchanged evidence; assert no duplicate proposal. Add the reject branch and failed-sync branch.
- [ ] Add an unchanged-evidence isolation lifecycle: persist `R1`, request/publish `A1`, replace it with `A2`, independently revise the review to `R2`, and fail one subsequent generation. Verify database pointers and overview fields throughout; the unaffected workflow's content/state never changes. Separately import genuinely changed evidence during an advice sync and assert only the appropriate evidence-driven review correction occurs, with its own provenance.
- [ ] Run `./.venv/bin/python -m pytest backend/tests/integration/application/test_johnny_coaching_lifecycle.py -q`; confirm any unconnected integration path fails before completing the wiring.
- [ ] Update product vocabulary/contracts and deployment instructions. Pause/drain legacy `daily_advice.sync`/`daily_recommendation` jobs before enabling new producers; mark unstarted legacy jobs cancelled through a documented terminal failure reason, never reinterpret them as athlete requests. Keep schema additive and old advice rows readable internally. Deploy API/worker code before enabling new scheduler and UI. If rollback is required, disable new producers first and keep old workers from consuming new task types; do not downgrade away accepted adjustments/history.
- [ ] Run full verification below and record exact results, fixture dates, browser screenshots and any real limitations in the verification document. Do not claim live-provider/model verification unless it was actually performed. Routine tests use fake clocks, providers and model outputs; no Garmin credentials or external model calls are needed.
- [ ] Commit: `test: verify Johnny coaching lifecycle and document cutover`.

**Done when:** All completion criteria below have evidence, existing flows pass regression checks, and the deployment procedure cannot replay a legacy scheduled run as a manual request.

## 5. Verification and completion gate

### Automated verification

Run from the repo root after all tasks:

```bash
./.venv/bin/python -m pytest backend/tests
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run verify:tokens
./.venv/bin/python -m alembic -c backend/alembic.ini heads
git diff --check
```

Run migration upgrade/round-trip and concurrency integration tests against a disposable PostgreSQL database as well as the default SQLite fixtures. Record the disposable database command/configuration in the verification document; never use the user's populated development/production database as a migration test. PostgreSQL tests need two real sessions and barriers around the competing transactions, covering accept/accept, accept/reject, accept/import, accept/plan activation, and competing generation publication. Final database assertions, not merely HTTP statuses, prove atomicity.

For the UI, use the installed frontend design verification checklist and run its static audit with output directed to a new verification artifact, preserving the user's existing modified `premium-audit.json`. Audit success is supplementary; it does not replace runtime interaction tests. No formatter/linter command is invented: use existing repository commands if one is added before implementation.

### Browser acceptance

- Desktop and 375px mobile: latest review, score breakdown, manual advice action, proposal diff and history are readable without horizontal page overflow. At 320px the same workflow remains operable.
- Keyboard-only request, optional inputs, workout choice, pairing, accept/reject and history pagination; clear focus and announced progress/errors. Reused dialogs restore focus and support Escape; touch interactions do not depend on hover.
- Loading, failure and replacement do not move the active approval button under the pointer. A stale proposal loses its actions as soon as refreshed state arrives; server checks still protect a client that has not refreshed.
- Leave/revisit while generating, sign out while polling, reconnect after a network error, and cross local midnight. No previous athlete's result or expired approval action appears.
- Compare Today, Plan and Johnny after acceptance. They show the same canonical workout and distinguish the accepted adjustment from its execution status.
- On Johnny, verify review and workout advice remain simultaneously displayed while either one generates, refreshes, fails or expires. Exercise both completion orders; section-level errors and spinners must not replace the whole page. Advice expiry affects its own section/proposal actions, not the daily review.
- Reduced motion, long Traditional Chinese explanations, long workout names and missing metrics remain usable. No fabricated numbers or English developer-error messages leak into user-facing states.

### Definition of complete

- [ ] The scheduled workflow reviews yesterday plus seven completed days and cannot create an adjustment proposal.
- [ ] `daily_review` and `workout_advice` have independent stored revisions, API fields and frontend state. Both are displayed together; creating/replacing/failing/expiring either output cannot overwrite, clear, hide or invalidate the other merely because that output changed. Database, API, UI and lifecycle isolation tests pass in both completion orders.
- [ ] The execution score follows the versioned formula and exposes components/coverage; unknown is never rendered as zero or silently excluded.
- [ ] Historical expectations survive plan replacement and prospective changes; uncertain legacy expectations are explicitly unscorable.
- [ ] An explicit athlete request syncs and generates today's advice, including truthful no-change guidance and supported structured constraints.
- [ ] A proposal names the workout, shows exact before/after and evidence, and cannot be applied stale, expired, already completed, or against another user's data.
- [ ] Accept writes exactly one atomic adjustment and retains all unrelated plan/workout data; reject changes no workout and suppresses equivalent repeated proposals.
- [ ] Sync, pairing and plan/evidence changes revise retrospective results or invalidate advice without synthesizing manual advice requests.
- [ ] Every date included in the score can be corrected while it remains in the editable eight-date window.
- [ ] Johnny has real review/history content, no public conversation UI, and no duplicated full Today advice; Today/Plan refresh after decisions.
- [ ] Fresh install, upgrade, retry, concurrency, and browser evidence pass; the agreed contract is recorded in repo docs and GitHub Issues before release.

## 6. Explicit limitations and later work

- `execution-v1` scores completion and amount only. It is not a validated physiological score; Target adherence and calibration need a separate evidence/data design.
- Automated proposals initially support skipping today's eligible workout and shortening a simple easy run. Complex intervals, races, rescheduling and multi-day changes remain outside the mutation envelope and receive guidance with an explanation.
- Stored data can arrive late even after a technically complete provider sync. Coverage means the requested import succeeded, not that an athlete's watch has uploaded every activity. Reviews remain revisable and show their cutoff.
- The system cannot detect an activity still on an offline watch or infer whether the athlete is currently exercising. “Not started” means no recorded or unresolved candidate activity in the latest usable evidence, not a real-time tracking guarantee.
- Manual-only activity users have no proof that all absent activities have been recorded. Missing sessions remain unknown unless a future product feature adds explicit completion-of-log confirmation; this plan does not add that feature.
- No configurable schedule, reminders, notifications, general workout editor, automatic training increases, or conversation is added.

## 7. Plan self-review

Coverage checked: the seven agreed conclusions map to Tasks 4 (scheduled review), 2 (score), 5 (manual advice/no-change guidance), 6 (approval), 7 (freshness/corrections), 9 (page ownership/no conversation), and 10 (full integration). The user's explicit independent-result requirement is specified in §1.4 and tested at persistence, API, frontend and lifecycle boundaries in Tasks 3, 8, 9 and 10. Historical truth and compatibility are covered by Tasks 1, 3 and 8. All five Review Focus cases have named test owners. New policy values are isolated in §2 so the user can change them before implementation without confusing them with prior agreements.

Recommended execution: implement in this task, in order, because the output schema, historical prescriptions, invalidation and approval transaction share interfaces. Review each tested slice before proceeding; arrange a final independent review if the user chooses an execution workflow that includes one. Do not start application implementation merely because this plan has been written.
