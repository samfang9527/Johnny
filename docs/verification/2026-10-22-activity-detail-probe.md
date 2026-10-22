# Task 1 — Garmin activity detail contract verification

Date: 2026-10-22. Task scope: bounded read-only acquisition/probe and decoder verification. No migration, ingestion, backfill, coaching generation, provider mutation or worker restart was performed. Task 2 is not started; stop here for user review.

## Delivered

- [Probe CLI](../../scripts/probe_activity_details.py): explicit owner and 1–8 activity IDs, one stored Garmin connection; checks ownership before decrypting/login. Reads only, with a read-only PostgreSQL transaction. Reuses the existing inline encrypted session format; does not persist refreshed credentials or original files. Refuses a connection observed to be syncing (this is a probe precondition, not a durable provider lease).
- [Boundary tests](../../backend/tests/unit/test_activity_detail_probe.py): privacy, descriptor indexing, missing resource, rate-limit stop, bounded requests, ownership, no database writes, genuine FIT decoding, unknown numeric FIT fields and archive limits.
- [Captured contract report](../../backend/tests/fixtures/activity_details/live_contract_report.json): field types, collection sizes, allowed unit descriptors, missing counts, resource timings and decoded FIT counts. No raw provider IDs, names, dates, coordinates, tokens or sample trace values. FIT/JSON inputs exist in memory only. Payload bytes are SDK-decoded content re-serialized as JSON or downloaded ZIP bytes, not measured HTTP transfer size.
- [Synthetic descriptor fixture](../../backend/tests/fixtures/activity_details/synthetic_details.json): deliberate sentinel secrets/coordinates, reordered metric indices and missing HR. These are invented test values.
- [Synthetic steps/pause fixture](../../backend/tests/fixtures/activity_details/synthetic_steps_and_pause.json): explicitly artificial repeated step indices and pause/resume events for subsequent normalization tests. It does not claim real-account support.
- `garmin-fit-sdk==21.218.0` pinned in [base requirements](../../backend/requirements/base.txt). Added `backend/tests/__init__.py` to avoid the dependency wheel's bundled top-level `tests` package shadowing Johnny's test helpers.

## Real account observations

Three explicit existing Garmin activities from the account owning the user's original agent run were probed. References below are synthetic labels; no activity identifiers were committed. All seven requested resources were available after fixing the probe's FIT reader.

| Evidence | sample-1 | sample-2 | sample-3 |
| --- | ---: | ---: | ---: |
| JSON laps | 22 | 6 | 13 |
| Typed splits | 2 | 10 | 5 |
| Split summaries | 2 | 4 | 4 |
| HR zone rows | 5 | 5 | 5 |
| Chart points (`maxchart=2000`) | 1,321 | 1,032 | 1,970 |
| FIT record messages | 2,624 | 2,038 | 3,916 |
| FIT lap messages | 22 | 6 | 13 |
| FIT workout/workout_step messages | 0 / 0 | 0 / 0 | 0 / 0 |
| Laps with `wkt_step_index` | 0 | 0 | 0 |
| FIT CRC/integrity | pass | pass | pass |
| FIT decode errors | 0 | 0 | 0 |
| Original ZIP bytes | 83,652 | 78,313 | 135,527 |

The FIT lap triggers establish automatic distance laps in all three recordings; sample-3 also includes one manual lap. This proves lap acquisition, **not** correspondence with Johnny's Workout Steps. Each recording has two timer events; this does not verify a mid-session pause/resume example. Structured interval linkage and actual paused recordings remain unverified for this account. Do not label these samples as confirmed easy/interval sessions merely from totals or names.

Chart point counts differ substantially from original recording counts. Preserve chart sampling as a separate evidence quality. The probe does not promise one-second regular recording or complete temporal coverage from counts alone.

Details descriptors differ between activities: HR is at index 1 in sample-1 and index 3 in sample-2; duration and speed also move. Observed descriptor keys/factors include `bpm/1`, `second/1000`, `meter/100` and `mps/0.1`. Those are returned metadata, **not yet a proved conversion formula**. Task 3 must compare known values/timing against FIT before applying conversions. Units outside the probe's explicit vocabulary remain `unverified`; this does not mean the source omitted a unit.

HR zones return `secsInZone`, `zoneLowBoundary` and `zoneNumber`; the report retains shape, not personal zone values. Historical zone configuration and exact segment-level zone adherence are not established by this endpoint alone.

JSON details were approximately 0.31–0.58 MB serialized per activity, original ZIP approximately 0.08–0.14 MB. These three samples inform initial capacity estimates only; no backfill throughput or long-activity storage guarantee has been measured. A JSON resource call took roughly 0.2–1.2 seconds in this run, with FIT acquisition plus summary decoding roughly 0.8–1.7 seconds; these are observations, not service limits.

## Decoder and dependency verification

Version `21.218.0` was checked against [official PyPI metadata](https://pypi.org/pypi/garmin-fit-sdk/21.218.0/json): Python >=3.6 and a universal pure-Python wheel. Downloaded wheel SHA-256 was checked against metadata. It was installed and exercised on the project's Python 3.14.3, matching the 3.14 major/minor in `backend/Dockerfile.api`; an Alpine container build was not performed in this task. The upstream source is [Garmin's official FIT Python SDK](https://github.com/garmin/fit-python-sdk).

Two observed integration pitfalls have regression coverage:

1. `Decoder.check_integrity()` consumes the stream in this version. Calling `read()` on that decoder returned zero messages despite a valid file. The probe now uses a fresh decoder/stream for reading. The regression test first failed `0 == 1`, then passed with genuine encoded FIT records.
2. Unknown FIT fields can have numeric dictionary keys. Treating every key as a string caused a TypeError when summarizing live recordings. A constructed valid FIT containing unknown field 254 reproduced the failure; the report omits unsupported field names while retaining valid record/lap counts.

A third integration issue was caught by the full suite: the decoder wheel includes a regular top-level `tests` package, which shadowed Johnny's implicit test namespace and caused nine collection errors (`No module named tests.unit`). An explicit Johnny test-package marker fixes resolution; no production dependency files were modified or deleted to hide the conflict.

## Reproduction

Run from the repository root with the configured local database/session. Substitute IDs locally; never put credential material on the CLI:

```sh
PYTHONPATH=.:backend ./.venv/bin/python scripts/probe_activity_details.py \
  --user-id USER_ID --activity-id ACTIVITY_ID --output /private/tmp/activity-contract.json
PYTHONPATH=.:backend ./.venv/bin/python -m pytest backend/tests/unit/test_activity_detail_probe.py -q
PYTHONPATH=.:backend ./.venv/bin/python -m pytest backend/tests -q -rs
```

The CLI writes only the schema/count report to the explicit output path. Status is per resource; exit 0 means a report was produced, not that all resources are complete. Rate-limit/auth/access failures stop subsequent calls and return exit 2; initialization/report-write failures return exit 1 with a generic diagnostic. Other unavailable resources remain visible without discarding successful ones. SDK authentication/network transport may refresh tokens in memory, but the probe never saves them.

## Verification and review boundary

- Initial baseline: **744 passed, 6 skipped, 2 warnings**.
- New probe tests: **14 passed** (including the two FIT regression cases).
- Full backend suite after dependency/test-package fix: **758 passed, 6 skipped, 2 warnings**.
- Six skips remain the existing disposable-PostgreSQL concurrency/persistence tests; `JOHNNY_TEST_DATABASE_URL` was not configured. Task 1 changes no schema. The two warnings are existing Starlette/httpx and pytest-asyncio deprecations.
- Initial report attempts exposed FIT summarization failures; the committed report contains the final corrected FIT observations and earlier successful JSON schema observations for the same samples, not a claim that every intermediate attempt succeeded.

The native worktree tool failed with `mmap failed: Operation canceled` and left no new registered worktree. Work proceeded on `codex/coaching-activity-details` in the original checkout. Prior uncommitted recovery changes remain untouched and are excluded from the Task 1 commit. This is branch isolation, not filesystem isolation.

Task 1 establishes usable acquisition paths and explicitly records the account-specific gaps. Stop for user review before Task 2; do not claim migration, normalization, exact step matching or new coaching output is implemented.
