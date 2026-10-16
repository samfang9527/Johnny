# Johnny Coaching Specification

## Purpose

Define the current Johnny page and its two independent coaching workflows. This contract supersedes the older combined Daily Advice scheduling and automatic advice-after-sync behavior in earlier MVP specs.

## Requirements

### Requirement: Scheduled retrospective review

At or after 04:00 in the athlete's IANA timezone, Johnny SHALL review the previous local date and score the seven completed local dates ending yesterday. The scheduled workflow SHALL NOT create a workout-adjustment Recommendation.

#### Scenario: Evidence is incomplete
- **WHEN** activity pagination is incomplete, pairing is unresolved, or a historical prescription is uncertain
- **THEN** the score is null with a reason and an unknown workout is not counted as missed
- **AND** the prior successful review remains visible during a correction or failed attempt

### Requirement: Requested workout advice

Only an explicit athlete request SHALL generate Workout Advice for the current local date. Johnny SHALL sync available activity evidence first, accept only structured optional constraints, and return guidance even when no change is supported.

#### Scenario: Adjustment is supported
- **WHEN** the target workout is unstarted, evidence is usable, and the bounded adjustment policy supports a change
- **THEN** advice includes an exact before/after comparison and a Recommendation requiring approval
- **AND** the canonical workout remains unchanged until valid acceptance

### Requirement: Independent result streams

Daily Review and Workout Advice SHALL have separate date/workout slots, revisions, current pointers, attempt states, errors, freshness, polling, and display sections. Publishing or failing one output SHALL NOT clear, replace, or invalidate the other merely because that output exists.

#### Scenario: Different completion orders
- **WHEN** review `R1` is followed by advice `A1`, replacement advice `A2`, and corrected review `R2`
- **THEN** Johnny shows `R1 + A1`, then `R1 + A2`, then `R2 + A2`
- **AND** the same isolation holds when workflows complete in the opposite order or one refresh fails

### Requirement: Evidence-driven correction

Manual sync, imported activity changes, pairing changes, and relevant plan/evidence writes SHALL invalidate affected current results and queue correction of existing retrospective reviews. They SHALL NOT synthesize a new manual advice request. Pairing remains editable for the latest eight athlete-local dates including today.

### Requirement: Page responsibilities

Johnny SHALL show the latest review, seven-day score/components and individual workouts, an actionable proposal with exact diff, requested advice, and paginated history. Today SHALL show the canonical workout with at most concise current requested guidance and a link to Johnny. The public page SHALL NOT show a conversation composer.
