# Johnny review and workout advice verification — 2026-10-16

Implementation plan: `docs/superpowers/plans/2026-10-16-johnny-review-and-workout-advice.md`. Tracking: [#13](https://github.com/samfang9527/Johnny/issues/13), [#14](https://github.com/samfang9527/Johnny/issues/14#issuecomment-6218823832).

## Verified locally

- `JOHNNY_TEST_DATABASE_URL='postgresql+psycopg://johnny:johnny-test@127.0.0.1:55432/johnny_coaching_test' ./.venv/bin/python -m pytest backend/tests -q --tb=short`: **702 passed, 2 warnings**. Backend fixtures use fake dates, provider data and deterministic generation; no live Garmin or model request was made.
- The PostgreSQL concurrency subset alone: **5 passed, 1 warning** against a disposable `postgres:16` container. These use two sessions and barriers for accept/accept, accept/reject, accept/activity import, accept/plan activation and older/newer review publication. Assertions check the final plan and adjustment records. Without `JOHNNY_TEST_DATABASE_URL`, these six parametrized cases skip.
- Fresh PostgreSQL schema: `alembic upgrade head` succeeded. Upgrade fixture: downgraded the disposable database to `0011`, seeded an existing user/plan/workout, upgraded to `0012_coaching_history`, and checked that the workout remains and its backfilled prescription is marked `legacy_uncertain`.
- `npm --prefix frontend run build`: passed (`vue-tsc -b` and Vite production build), including type checking of the added Vue tests.
- `npm --prefix frontend run verify:tokens`: passed.
- `./.venv/bin/python -m alembic -c backend/alembic.ini heads`: `0012_coaching_history (head)`.
- `git diff --check`: passed.
- Static frontend design audit: `docs/verification/2026-10-16-johnny-premium-audit.json`, zero findings. The pre-existing root `premium-audit.json` edit was preserved untouched.

The disposable database was started with `docker run -d --name johnny-coaching-20261016-pg -e POSTGRES_USER=johnny -e POSTGRES_PASSWORD=johnny-test -e POSTGRES_DB=johnny_coaching_test -p 55432:5432 postgres:16`. Migration commands used `DATABASE_URL='postgresql+psycopg://johnny:johnny-test@127.0.0.1:55432/johnny_coaching_test' ./.venv/bin/python -m alembic -c backend/alembic.ini upgrade head` (and `downgrade 0011` for the upgrade fixture). This was an empty disposable database, never a populated development or production database.

## Browser and runner limits

The Johnny page was opened in the local test-mode Vite app at desktop, 375px and 320px widths. Its empty/error state, manual request form and checkbox interaction rendered; measured page `scrollWidth` matched the viewport at both mobile widths. This was an empty/error-state inspection, not a browser pass of a populated review, proposal or approval flow. No screenshot artifact was saved.

`npm --prefix frontend run test` could not execute tests in this host: Vitest 4.1.11 timed out starting a worker (`[vitest-pool-runner]: Timeout waiting for worker to respond`) before transform, import or any test. A single new component test reproduced it; threads, forks and VM thread pools were also attempted, including outside the sandbox. The added `useJohnny.test.ts` and `JohnnyPage.test.ts` are type checked by the build but **have not run**. This remains a release verification gap, along with populated browser acceptance and live-provider behavior.

Isolation check: `npm --prefix frontend run test -- src/raceGoalForm.test.ts --environment=node --pool=threads --maxWorkers=1 --no-file-parallelism` passed 4 tests. A direct `require('./frontend/node_modules/jsdom')` did not finish after 60 seconds; the loader trace continued through jsdom's generated modules. The startup problem is specific to the installed jsdom environment on this host, rather than Vitest's ability to start every worker.

## Cutover and rollback

1. Pause old schedulers and drain already-running `daily_advice.sync` and `daily_recommendation` work before switching producers. Deploy the additive `0012` migration and new API/worker code before enabling the 04:00 reviewer and Johnny UI.
2. The new worker terminally fails any unstarted legacy task with `LegacyDailyAdviceRetired` and fails its linked run. It never reinterprets a legacy scheduled task as an athlete-requested `workout_advice`. Historical Daily Advice rows remain in storage for compatibility; they are not shown as new retrospective reviews.
3. After deployment, verify one local 04:00 review, one explicit same-day advice request, and current Today/Plan state after an accepted decision using a non-production athlete. Monitor sync failures, review correction backlog and `inputs_changed` attempts.
4. On rollback, disable new review/advice producers first. Keep accepted workout changes, recommendation decisions and revision history; do not downgrade or delete `0012` data. Do not let an old worker consume new `coaching.sync` tasks. Resume only a worker version that understands the persisted task types.

## 2026-10-17 review recovery

A pre-cutover worker was still consuming the shared queue and terminally rejected a `coaching.sync` task as `UnknownTaskType`. Its linked review run remained `queued`, so the scheduler's original idempotency path reused that failed task on each tick. A successful manual sync could update evidence but could not publish a review from the missing slot. The old worker was stopped, and the affected review was requeued through the current handler; the replacement run completed and published a narrative. Its seven-day score is null with `uncertain_prescription` because older workout timing cannot be established by the additive backfill.

The regression coverage now exercises scheduler and completed-sync recovery of that exact terminal task state, including a one-retry cap if an incompatible worker remains. Manual sync never creates `workout_advice`; athletes request that stream explicitly on Johnny. Restart running scheduler/worker processes when deploying this recovery code, and ensure all consumers of the shared queue use the same task-type version.

Recovery verification: `./.venv/bin/python -m pytest backend/tests -q --tb=short` reported **698 passed, 6 skipped, 2 warnings** on 2026-10-17; the six skipped cases require the disposable PostgreSQL URL. `npm --prefix frontend run build` and `git diff --check` passed. The read-only athlete review assertion changed from missing to published after the targeted requeue.
