# Local training-plan regeneration

The product limit remains one successful manual regeneration per athlete-local day. To test repeated UI regenerations against a local backend, stop the API and restart it from the repo root with an explicit development-only limit:

```bash
ENV=development JOHNNY_DEV_REGENERATION_DAILY_LIMIT=10 make run-api
```

`ENV=local` also works. The override is ignored in production and test environments, and invalid values fall back to one. The UI regeneration sheet reads the effective limit from `/api/v1/training-plans/regeneration-options`; refresh the page after restarting the API. A queued or started run still prevents another concurrent run. A new confirmation must use a new `client_request_id`.

The API queues the run. To complete it locally, run the worker with the same database and LLM provider configuration used by the API:

```bash
make agent-work-one
```

For numeric pace estimates, enter a measured threshold pace under **運動員 → 閾值配速** in `m:ss` per kilometer, then save settings before regenerating. Johnny stores it as canonical seconds per kilometer, computes pace-zone ranges, and shows an estimated range alongside RPE on pace-targeted workout steps. Without a threshold baseline, Johnny keeps RPE-only targets. Hills and other RPE-only steps do not receive invented pace targets. Existing saved plans are not retroactively recalculated.

The override is for local development only. Do not change historical runs or enable the setting in a deployed environment.
