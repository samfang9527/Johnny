# Workout Advice recovery evidence

Requested Workout Advice uses stored sleep duration, HRV plus its baseline, stress,
and Body Battery for the athlete's current and previous local calendar dates.
The existing Garmin sync stage fetches these resources before generation; its
incremental window includes today and at least the preceding three completed dates.
Daily health dates are provider calendar-date buckets, not activity timestamps to
convert a second time from UTC.

`build_workout_recovery` reuses `RecoveryService` thresholds independently for each
date. It does not combine yesterday's measurements with today's to manufacture a
complete observation. This workflow does not include training load or resting heart
rate in its recovery assessment. A missing or zero HRV baseline is unavailable HRV
evidence, not a divisor. At least two usable signals are required by the existing
policy; missing signals are recorded explicitly.

Today's daily record takes precedence. If it exists but is insufficient, the current
assessment remains `unknown`; yesterday's assessment remains visible as context.
If today's record is absent, yesterday is used as a dated reference. Older dates,
future dates and other athletes' data cannot supply the assessment.

| Evidence | Result when no higher-priority constraint applies |
| --- | --- |
| Today's assessment is `rest` | Propose skipping today's workout; acceptance is required before changing it. |
| Today's assessment is `caution` | Conservative guidance without inventing a numeric workout adjustment. |
| Yesterday's assessment is `rest` or `caution` | Dated caution, without treating it as today's evidence or proposing a skip. |
| Yesterday's assessment is `ready` | Explain that yesterday does not establish today's recovery. |
| Insufficient or missing recovery | Explain the uncertainty instead of claiming normal recovery. |

Existing eligibility checks still block changes to completed, unresolved, absent,
or unsupported workouts. Explicit athlete constraints retain their existing behavior,
including a requested skip or supported shortening. The resulting guidance includes
both dates' observed values and missing signals.

The advice revision stores a `recovery` object with `policy_version`, `observed_date`,
`readiness_label`, and two dated `days` entries. Each day has `signals` (including the
existing policy's levels) and `missing_signals`. This evidence participates in the
advice's evidence fingerprint. Recovery proposals also distinguish which signals
caused caution/rest in the decision fingerprint, so unchanged substantive reasons do
not bypass rejection suppression just because a measured number fluctuated.

Acceptance rebuilds the two-day recovery evidence and rejects a changed snapshot with
`recovery_evidence_changed`, in addition to existing freshness checks. Existing health
writes and sync invalidation continue to stale previous advice and supersede pending
proposals. This feature does not enqueue advice automatically or change Daily Review.

## Verification

```bash
PYTHONPATH=.:backend ./.venv/bin/python -m pytest \
  backend/tests/integration/application/test_workout_advice_recovery.py \
  backend/tests/integration/application/test_workout_advice_flow.py \
  backend/tests/unit/test_workout_advice_policy.py -q
```

Long-running workers must restart to load these code changes. Previously published
advice is retained; a new explicit request generates advice using the new policy.
