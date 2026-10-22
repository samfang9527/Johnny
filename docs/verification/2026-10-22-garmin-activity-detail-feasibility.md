# Garmin activity detail feasibility — 2026-10-22

## Finding and scope

Activity-level segments and time-series acquisition are feasible with Johnny's existing dependency. They belong in the full `workout_advice` / `daily_review` improvement, alongside persistence, historical backfill and assessment changes. The installed `garminconnect==0.3.11` already exposes the required read methods; the missing part is Johnny's acquisition and interpretation pipeline. Availability of a method does **not** prove that any particular athlete/activity supplies every field.

This is a source-based feasibility assessment. No authenticated Garmin request, credential read, production access or application-code change was made. Account-specific response shapes, completeness and exact Connect JSON units remain unverified.

Local evidence: [dependency pin](../../backend/requirements/base.txt), [resource adapter](../../backend/src/infrastructure/integrations/garminconnect_adapter.py), [summary normalizer](../../backend/src/infrastructure/integrations/garmin_normalizer.py). The adapter currently requests activity lists through `get_activities_by_date`; the normalizer retains start time, sport, distance, duration, average HR and ascent, without fetching segment/sample resources. Primary dependency source inspected: `.venv/lib/python3.14/site-packages/garminconnect/__init__.py` and `activity_details.py`, installed distribution metadata version `0.3.11`.

## Existing SDK surface

The following is verified against the installed pinned source, rather than assuming methods on upstream `master` exist locally. Activity paths are under `/activity-service/activity/{activity_id}`. The matching [upstream 0.3.11 source](https://github.com/cyberjunky/python-garminconnect/blob/0.3.11/garminconnect/__init__.py) provides a portable reference; local installed line numbers are listed for reproducibility.

| Capability | Exact installed method | Endpoint / interpretation | Local line |
| --- | --- | --- | --- |
| Activity summary | `get_activity(activity_id)` | Base activity path; docstring mentions basic splits. | 2949 |
| Activity splits | `get_activity_splits(activity_id)` | `/splits`; fetch separately, preserve provider labels and boundaries. | 2873 |
| Typed splits | `get_activity_typed_splits(activity_id)` | `/typedsplits`; upstream docstring says some sports contain extra detail. | 2881 |
| Split summaries | `get_activity_split_summaries(activity_id)` | `/split_summaries`; a summary view, not proven to be chronological individual repeats. | 2891 |
| HR time in zones | `get_activity_hr_in_timezones(activity_id)` | `/hrTimeInZones`; activity-level distribution, not segment-level HR samples. | 2907 |
| Configured HR zones | `get_heart_rate_zones()` | `/biometric-service/heartRateZones`; all sport profiles, no historical date argument. | 2931 |
| Samples / charts | `get_activity_details(activity_id, maxchart=2000, maxpoly=4000)` | `/details?maxChartSize=...&maxPolylineSize=...`; size parameters are not a guarantee of full-resolution recording. | 2957 |
| Strength sets | `get_activity_exercise_sets(activity_id)` | `/exerciseSets`; separate sport-specific evidence. | 2970 |
| Original recording | `download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)` | Returns original **ZIP bytes**, caller extracts/identifies files. The default format is TCX, so specify ORIGINAL explicitly. CSV download is splits. | 2839 |
| Workout definition | `get_workout_by_id(workout_id)` | `/workout-service/workout/{id}`; definition, not proof of execution. | 3127 |
| Workout FIT | `download_workout(workout_id)` | `/workout-service/workout/FIT/{id}`; prescribed workout file. | 3140 |
| Workout library | `get_workouts(start=0, limit=100)` | Offset pagination; one page per call. | 3118 |
| Scheduled workout | `get_scheduled_workouts(year, month)` / `get_scheduled_workout_by_id(id)` | Calendar or schedule lookup; neither establishes completed-activity linkage on its own. | 3426 / 3445 |

No SDK upgrade is required to call these methods. Newer upstream endpoint documentation is useful context but is not evidence that newer methods, such as `get_heart_rate_zones_v2`, are present in this installed version. The upstream project explicitly documents its observations of the Garmin Connect **web application's** requests, which distinguishes this integration from an official partner API. [Upstream endpoint-map methodology](https://github.com/cyberjunky/python-garminconnect/blob/master/docs/API_ENDPOINTS.md)

## Segments, prescribed steps and actual execution

Garmin FIT distinguishes a recorded Activity file from a Workout file containing instructions. Activity recordings can carry sessions, laps, events and samples. Workout instructions contain individual step duration/target definitions and repetition structure. An Activity file may also contain Workout/Workout Step messages, but their presence depends on the device and whether that feature was used. [Garmin activity file specification](https://developer.garmin.com/fit/file-types/activity), [Garmin workout file specification](https://developer.garmin.com/fit/articles/file-types/workout.html), [Garmin decoding guide](https://developer.garmin.com/fit/articles/cookbook/decoding_activity_files.html)

The official FIT profile includes `lap.wkt_step_index`, `lap.intensity` and `lap.lap_trigger`. These are useful linkage evidence **when present**; the format having a field does not imply every recording supplies it. FIT record fields specify HR in bpm, distance in metres, speed in m/s and power in watts after decoding scales/offsets. [Garmin FIT Python profile](https://github.com/garmin/fit-python-sdk/blob/main/garmin_fit_sdk/profile.py)

Implementation implications (recommendations, not claims of existing behavior):

- Preserve provider laps, typed splits and aggregate summaries as different evidence types. Auto-distance laps and manually pressed laps must not automatically become planned warm-up/work/recovery steps.
- Prefer explicit recording-to-workout linkage and recorded step indices. Retain repeated occurrences independently; matching by a repeated step index alone loses iteration identity.
- Match execution to the immutable Johnny prescription effective before the activity. A later fetch of an editable Garmin workout library definition does not establish what was prescribed at execution time.
- If explicit linkage is absent, match ordered time/distance boundaries only with a confidence and reason. An inferred match can support qualified commentary; it must not silently become exact step adherence.
- Preserve unmatched laps, incomplete repeats, extra work, skipped steps, pause boundaries and multisport sessions. Never discard these merely to force a perfect plan match.

## Time-series and units

The pinned library includes `parse_activity_detail_metrics(details)`. It maps positional `activityDetailMetrics[].metrics` values using `metricDescriptors[].metricsIndex` and `key`; positions vary by device and activity type. It skips invalid descriptors and omits out-of-range channels. It **does not convert units**, and distinguishes `sumDuration`, `sumElapsedDuration` and `sumMovingDuration`. [Pinned helper source](https://github.com/cyberjunky/python-garminconnect/blob/0.3.11/garminconnect/activity_details.py)

Therefore the normalizer should retain original descriptors/units and explicitly validate conversion into a canonical schema: timestamp, elapsed seconds, timer seconds, distance metres, speed m/s, HR bpm and optional other channels. Do not assume details JSON shares the units of activity-list JSON or FIT. The inspected wrapper alone does not establish units for all Connect fields or `hrTimeInZones` durations. Unknown units should produce an explicit unsupported/uncertain status, not a guessed conversion.

Chart-size controls may yield a reduced representation; this assessment did not verify Garmin's sampling algorithm or an unlimited chart setting. Do not promise one-second samples, infer missing samples as zero or integrate a sample-count fraction as exact time in zone. Use timestamp-weighted coverage with gaps and pauses handled explicitly. When detailed adherence needs original recorded resolution, fetch the ORIGINAL ZIP and parse the recording instead of assuming increasing `maxchart` guarantees completeness.

Garmin publishes an official Python FIT decoder (`garmin-fit-sdk`). It returns decoded messages plus errors and supports integrity checking, scale/offset application and timestamp conversion. Pin the chosen decoder version and check errors rather than accepting partial decoding as complete. This is a file-format SDK, not a provider-authentication alternative. [Official FIT Python SDK](https://github.com/garmin/fit-python-sdk)

Current zone settings and recorded activity zone distributions are different evidence. Store the sport profile, zone bounds, source and observation time with each acquisition. Do not retroactively score an old activity against today's zones while presenting the result as Garmin's original classification. Missing HR data must remain missing; a session-average HR cannot establish interval-level zone compliance.

## Pagination, rate limits and acquisition strategy

Installed source observations (`__init__.py` lines 40–47, 225–307, 2334–2366 and 2624–2681):

- `get_activities(start=0, limit=20, ...)` uses offsets and locally rejects `limit > 1000`.
- `get_activities_by_date(...)` fetches pages of 20 until an empty response, with a client safety cap of 2,000 page requests and an exception on exhaustion.
- These are **SDK bounds**, not published Garmin request-per-minute limits. No numeric provider request quota was verified.
- The SDK retries transient network/5xx failures with bounded jitter. Authentication errors, HTTP 429 and other 4xx fail fast. The application must schedule rate-limit recovery; assuming automatic SDK 429 retries would be incorrect.
- Detail methods fetch one activity at a time; enabling several resources adds several calls per activity. Offset traversal while activities change can shift pages, so deduplication by provider activity identity and overlapping date reconciliation are prudent design measures.

Recommended complete acquisition path: import summary identity first; enqueue per-activity enrichment for splits, typed splits, HR distribution and details; acquire FIT where required for fidelity or missing linkage; preserve raw responses plus normalization version; build normalized ordered segments/samples; compute deterministic quality/adherence features; then pass compact evidence to both coaching flows. Use bounded resumable batches, per-resource statuses (`pending`, `available`, `empty`, `unsupported`, `retryable_failure`, `permanent_failure`), idempotent upserts and a retry cooldown for 429 responses. Honor provider `Retry-After` when available without assuming this wrapper always preserves it.

Historical enrichment is part of this feature's migration/backfill scope. Existing summary rows can seed an enrichment queue by provider activity ID; schema upgrades must not perform authenticated network fetches. Preserve existing reviews, identify the evidence revision used for each result, and issue a controlled corrected review when newly acquired detail changes a material finding. Backfill capability is not equivalent to confirmed complete historical availability: old originals, deleted activities, device-specific fields and unavailable resources may remain absent.

## Official Garmin APIs are a separate route

As checked on 2026-10-22, Garmin's current public developer portal describes Starter access with Activity API JSON/FIT, Health API JSON, push-only delivery and **no historical data**. Enterprise options include push or ping/pull and history described as **1 month+**; this does not promise unrestricted history. The portal directs developers to create apps/request keys. Detailed Start Guide and FAQ links returned 403 in this unauthenticated research session. [Current Garmin Connect Developer Program](https://developerportal.garmin.com/developer-programs/connect-developer-api)

Official OAuth documentation describes user consent, partner user IDs and distinct activity/health/workout permissions. Johnny's existing Garmin Connect session is not interchangeable with a registered partner integration or its consent model. [Garmin OAuth2 PKCE documentation](https://developerportal.garmin.com/sites/default/files/OAuth2PKCE.pdf)

The older Activity API marketing page still appears in search-index results advertising FIT and backfill, but direct opens of the old Activity/Health/FAQ paths returned 404. Treat the current portal as authoritative for current public access tiers, and verify actual program eligibility, permitted history and fields during a separate official-provider integration. This assessment does not claim approval or access for Johnny. The existing pinned Connect integration can deliver the planned enrichment work without making a switch to the official provider a prerequisite.

## Verification gates for implementation

These are completion requirements for the full improvement, not reasons to defer segment acquisition:

1. Offline fixtures cover descriptor reordering, unknown units, empty/missing HR, chart downsampling, pause/time semantics, manual/automatic laps, repeated workout steps, unmatched segments and multisport recordings.
2. At least representative real response shapes are obtained through an explicitly authorized read-only provider probe or supplied sanitized exports. Validate split chronology, JSON units, available linkage, HR-zone durations and FIT archive contents; never record credentials or full personal tracks in committed fixtures.
3. Enrichment backfill is resumable and idempotent; one unsupported resource does not erase valid summaries. 429, authentication changes and pagination failures remain distinguishable.
4. Derived scores disclose their coverage and confidence. Both `daily_review` and `workout_advice` consume the same versioned normalized evidence, so neither silently substitutes whole-activity averages for step execution.
5. New detail can invalidate/revise an earlier incomplete assessment without rewriting the historical prescription or duplicating activity totals.

No authenticated verification was performed here, so these gates remain implementation/acceptance work. SDK capability, data-format capability and the present summary-only integration gap are established by the sources above.
