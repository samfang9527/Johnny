# Activity Session Matching Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Do not commit before user review.

**Goal:** Count split running recordings as one completed workout and let athletes review and correct matches.

**Architecture:** Shared running classification and deterministic session grouping feed daily execution facts and review cards. Persist explicit partitions and workout decisions in activity metadata, preserving imported records and idempotent sync. Owner-scoped API validates complete partitions and queues advice refresh after decisions.

**Tech Stack:** Python domain services, SQLAlchemy, FastAPI, Vue/TypeScript.

**Spec:** User-approved conversation of October 14: same local day, non-overlap, running family, gaps at most 30 minutes; automatic clear match, review ambiguous cases, correction available for all.

## Global Constraints
- Preserve existing Garmin target work and do not commit.
- Running includes track and trail; trail pace is not road target evidence.
- Activity volume counts regardless of match; gaps do not count as active time.
- Saved decisions survive repeated sync and take precedence over automatic grouping.
- Traditional Chinese UI and existing mint tokens.

## Review Focus
- Cross-user activity/workout IDs rejected (API tests).
- Exact 30-minute boundary, overlap and local midnight (domain tests).
- Later imports must not overwrite saved partitions (repository tests).
- Several sessions versus several workouts remain uncertain (domain tests).
- Stale UI responses and saving failures preserve correct user state (UI tests).

### Task 1: Shared classification and deterministic sessions
- [x] Add failing domain tests for track/trail, gaps, overlaps, ambiguity, explicit decisions.
- [x] Implement domain/running.py and domain/activity_sessions.py; integrate daily_advice and shared workload/target filters.
- [x] Run domain tests and existing advice tests.

### Task 2: Persist decisions and expose review API
- [x] Add owner isolation, partition validation and repeated-import tests.
- [x] Add activity decision metadata; GET /activities/session-reviews and POST partition decisions. Use existing advice queue with fresh observation version.
- [x] Run API/database tests.

### Task 3: Review cards
- [x] Add frontend component/tests for automatic confirmation, ambiguous selection, split, unplanned and corrections.
- [x] Integrate Today and refresh after save, exposing cutoff timestamp.
- [x] Run frontend suite/build/token validation.

### Task 4: Verify and regenerate
- [x] Run full backend/frontend tests and review diff.
- [x] Recompute real user's facts read-only; queue today's advice and verify result when local worker is available.
- [x] Report outcome and leave uncommitted for review.

## Verification record

- Backend: 677 passed, 1 skipped. Frontend: 147 passed; focused session review tests and production build rerun after localized labels and select styling.
- Actual October 13 data: three recordings, 3077 active seconds, one automatic workout match.
- Restarted the idle local worker to load the changed backend. The first new-code OpenAI response failed strict trusted-facts validation; the user explicitly approved retrying with training/recovery context. The retry published ready advice with one completed and zero missed workouts.
- Independent reviewer could not run because its usage limit was reached; implementation was checked locally against domain, API, owner isolation, persistence, and browser regressions.
- No commits.
- Final refresh preserved source-sync recovery coverage and published fresh advice with execution mode rest, one completed workout, and zero missed. Desktop/mobile review and split controls verified without saving a match on the athlete’s behalf.
