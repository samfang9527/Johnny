# Coaching detail Task 12 release acceptance — 2026-10-23

This is a **local release rehearsal**, not a production deployment or a claim about live Garmin coverage. The 2027-01-11 activity/date below is synthetic. No production flags were enabled and no provider or model network call was made.

## Verified behavior

- The PostgreSQL `0012_coaching_history` → head migration test passed in the complete backend suite. A fresh disposable test database migrated through `0014_coaching_requests`. A synthetic owner, provider activity with a manual-pairing reference, and a legacy review revision were seeded *after* the suite. A `pg_dump -Fc` of that test database restored with `pg_restore --exit-on-error` into a second disposable database; both reported revision `0014_coaching_requests`, 42 tables, the same pairing reference and legacy review payload, and zero preseeded detail snapshots. The restored database was separate from the local `johnny` database.
- The acceptance fixture used one owner, five published historical Daily Review slots, one user-requested Workout Advice, and one provider activity on 2027-01-11. Its three resources (`fit`, `splits`, `details`) finished with **3 complete, 0 partial, 0 unsupported, 0 failed**, and **0 retrying fetches**. It simulated an interrupted fetch, replayed it, then fetched a real changed second version and an identical third version. Across the three batches there were 9 fake provider calls and 6 immutable snapshots; the identical replay added **0** snapshots and **0** review revisions.
- The initial batch generated one new latest-date review revision using **1 local fake model call**. The other four historical slots stayed present and stale. Replaying the same effective evidence generated **0** extra review requests or model calls. A late real change coalesced into one successor request; repeated completion produced no third request. The fixture ended with 6 review revisions (5 original, 1 corrected), 2 evidence-change runs (initial and successor), and the original Workout Advice revision intact. It made no canonical workout adjustment.
- A separate approval-race test added a new detail snapshot after a pending Workout Advice Recommendation and verified acceptance fails with `evidence_manifest_changed`; the canonical workout remains planned. Flag-off tests verified existing detail tasks defer and legacy advice is still readable. Contract tests verified current version `1`, legacy unversioned `0`, and that unknown/malformed future versions and unknown task types remain unclaimed; the malformed-version query was also tested on PostgreSQL.
- The fake fixture contains 248 UTF-8 bytes of *normalized sample JSON* across its six stored sample payloads for one activity (excluding database overhead, segments, and source metadata). The PostgreSQL acceptance test ran in about 2–3 seconds for 9 in-process fake calls; this is **not** Garmin backfill throughput. Real per-activity storage and network throughput remain a release measurement gate.

## Automated checks

| Check | Result |
| --- | --- |
| Backend full suite with `DATABASE_URL` and `JOHNNY_TEST_DATABASE_URL` set to the disposable PostgreSQL test database | 944 passed, 0 skipped, 2 existing deprecation warnings (2026-10-24 pre-merge rerun) |
| Frontend Vitest | 192 passed in 12 files |
| Frontend production build | Passed |
| Palette token verification | Passed |
| Task 12 isolated PostgreSQL acceptance | 7 passed |

The first full PostgreSQL run caught an older worker test expecting unknown task types to fail after claim; the documented contract now keeps those tasks queued, and the test was updated. A new end-to-end replay test caught a real cascade: after correcting the latest review, replay selected the next older stale review for automatic correction. The refresh service now selects the latest *affected published slot* before comparing fingerprints, so replay cannot walk backward through history. Both failures were resolved before the passing full run.

Pre-merge review on 2026-10-24 found that a fetch result arriving after its lease expired could overwrite a newer worker's status or miss coaching refresh after batch closure. The fetch lease now fences success and failure writes, a changed provider identity rejects in-flight evidence, and a late changed snapshot queues a new finalization batch. SQLite regressions and a two-worker PostgreSQL test cover both completion orders; the full PostgreSQL suite result above includes these tests.

## Production release gate

| Required field | Local evidence | Production status |
| --- | --- | --- |
| Covered dates | Synthetic 2027-01-11 only | Not measured |
| Complete / partial / unsupported / failed activity-resources | 3 / 0 / 0 / 0 synthetic | Not measured |
| Remaining retry jobs | 0 fetch retries synthetic; fixture queue tasks are not a worker-drain rehearsal | Not measured |
| Generated / skipped revisions | 1 corrected review, 0 extra on identical replay; 1 late successor queued | Not measured |
| Model / fallback | 1 fake model result / 0 fallback, synthetic only | Not measured |
| Restored database | Separate disposable PostgreSQL restore matched revision, 42 tables, synthetic activity pairing, and legacy review payload | Production backup restore still requires operator rehearsal |
| Worker builds / contracts | Source worker accepts versions 0 and 1; API exposes declared build SHA; Docker production worker/scheduler use the same image as API | Running image digests and stray old workers not inspected |
| Sample bytes/activity and backfill throughput | 248 B normalized fixture samples for one activity; in-process timing only | Live-account measurement required |

The authorized local `johnny` database was inspected read-only and does **not** yet contain `activity_detail_snapshots`; it was not migrated or changed for this rehearsal. Consequently, no live athlete coverage or real backfill throughput can be reported. Task 3 calibrated chart units against three actual FIT traces, but Task 1's structured-interval and mid-session-pause samples remain live-data gates. Use the staged [deployment runbook](../deployment-v1.md#coaching-detail-cutover-additive-release) and fill the production column from the actual release cohort before enabling the flags. Disable flags and stop new producers for rollback; retain the additive tables and historical evidence.
