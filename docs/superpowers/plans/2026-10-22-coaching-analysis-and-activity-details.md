# Coaching Analysis and Activity Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將活動分段取得、歷史回填、可追溯分析與兩種結構化教練回覆接進 Johnny，讓跑者理解今天怎麼執行及昨日差異的意義。

**Architecture:** 沿用 Garmin Connect、SQLAlchemy 與 durable task queue，新增不可變明細證據、分段分析及批次協調。兩種生成流程共用確定性 findings 與結構化 LLM/fallback，保留歷史課表、計分及 Recommendation 接受流程。前端雙讀新舊 payload，逐步切換，回滾不刪除資料。

**Tech Stack:** 現有 Python/FastAPI/Pydantic、SQLAlchemy/Alembic/PostgreSQL、`garminconnect==0.3.11`、既有 ModelGateway、pytest、Vue 3/TypeScript/Vitest；FIT decoder 在 Task 1 驗證相容版本後鎖版。無新增 queue 或 object-storage 服務。

**Spec:** [已確認的完整改善評估](../../verification/2026-10-22-coaching-complete-improvement-assessment.md)；[Garmin 可行性研究](../../verification/2026-10-22-garmin-activity-detail-feasibility.md)；`CONTEXT.md`、`DESIGN.md`。使用者於 2026-10-22 確認完整範圍並要求準備 implementation plan。

**Status:** Task 1 completed in `81771ee`, pending user review. Tasks 2–12 not started. Live probe completed; no migration, backfill or deployment. User requires a pause after every task.

## Global Constraints

- 「分段取得、歷史資料回填、資料模型遷移、分析、LLM、fallback、前端，以及避免重複產生，全部屬於同一完整改善的交付範圍。」
- 「七日 Execution Score 的日期與定義維持原有版本。」保留 `execution-v1`，不是訓練品質或恢復評分。
- 「Migration 本身只建 schema 和必要索引，不進行 Garmin 網路呼叫或長時間回填。」
- 「Workout Advice 維持使用者請求產生；新證據只使相關建議／待接受 Recommendation 失效。」只有接受有效 Recommendation 可改 canonical workout。
- 「同一批資料只自動更新最新已發布且受影響的回顧；較早的受影響日期標記『資料已更新』，在明確重算時更新。」
- 「時間語意區分 elapsed、timer、moving」；missing 不等於 0，lap 不等於 Workout Step，降採樣不等於完整逐秒紀錄。
- 「API 保留舊 `guidance/narrative` 相容摘要，新 UI 優先讀結構化欄位。」舊 revision 不補造新 findings。
- 使用者／連線／活動／revision 擁有者檢查適用所有工作及讀取；不把憑證、GPS、原始 FIT 或 samples 傳給 LLM。
- 繁體中文、深綠連續畫布、薄荷重點、細分隔線；遵守既有 tabs、獨立 loading/error/freshness 與接受前比較。
- 不改無關課表生成／通知功能；不建立新官方 Garmin partner integration。

## Review Focus

1. 回填與新活動同步同時完成、worker crash 後重送，仍只能發布一份有效結果；Task 4、7、12 以真 PostgreSQL 雙 session 測試。
2. 今日只有局部健康資料到達，不應抹掉昨日仍有效的個別訊號，亦不能拼湊成「今日完整恢復」；Task 6、9 測試。
3. 不同帳戶相同 provider ID、重新連線、手動活動無 provider ID，不得串錯證據或覆蓋人工配對；Task 2–4、10 測試。
4. DST、午夜、跨兩筆活動、重複 interval index、pause、部分降採樣，不能製造精確 step 達標率；Task 3、5 測試。
5. 新後端＋舊前端、舊 revision＋新前端、模型輸出含指令或未支持的數字，不得破壞畫面或繞過調整接受；Task 8–12 測試。

## Execution boundaries and dependency order

這是一條共享 evidence contract 的完整改善，保持一份整合計畫，按四個可獨立驗收的里程碑交付：資料取得與遷移（1–4）、分析與協調（5–7）、生成與 API（8–10）、UI 與切換（11–12）。前一里程碑完成不代表整體完成。

依賴：`1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12`。Task 1 實帳樣本不足時可繼續離線 contracts／schema，但不得以 fixtures 宣稱帳戶資料已驗證或直接啟用深度分析。

執行開始時先依 worktree skill 建隔離工作區。此工作目錄已有尚未提交的 recovery 改善及本次文件：`coaching_approval.py`、`workout_advice_generation.py`、`workout_advice.py`、新 `workout_recovery.py`、`test_workout_advice_recovery.py`、`docs/workout-advice-recovery.md`。記錄 diff 並把這些已授權變更完整帶入隔離工作區；worktree 不會自動複製它們。不要重設、覆蓋或混入其他使用者修改。每個 task commit 只包含其明確檔案。

命令由 repo root 執行；Python 使用 `PYTHONPATH=.:backend ./.venv/bin/python -m pytest`，frontend 使用 `npm --prefix frontend`。下文 `pytest …` 指前述完整 Python 命令。每個 test step 先確認因尚未實作的行為而失敗，不能把 import/environment 錯誤當有意義的 red。

## Shared interfaces and engineering defaults

以下型別在指定 task 定義；DTO 可用 frozen dataclass，API/LLM boundary 用 Pydantic。JSON payload 使用 `to_payload()`，schema version 不依 Python 類名推導。

- Task 2：`DetailResource = Literal['splits','typed_splits','split_summaries','hr_zones','details','fit']`；`DetailCoverage` 包含 `state: complete|partial|unknown`、`sampling: recorded|chart|unknown`、`covered_seconds: float|None`、`missing_channels: tuple[str,...]`、`limitations: tuple[str,...]`。
- Task 2：`NormalizedDetails` 保存 activity ID、resource、schema version、segments、sample chunks、coverage、經篩選 source payload；`DetailSnapshot` 再含 id、hash、fetched_at。時間為 UTC instant 或明確秒數 offset；timer 與 elapsed 欄位不能互換。
- Task 5：`ExecutionAnalysis` 保存 fingerprint、prescription revision ID、snapshot IDs、`mapping: exact|estimated|unmatched`、`facts`、`findings`、`limitations`、`algorithm_version='execution-analysis-v1'`。Fact 具有 id、metric、value、unit、scope、evidence_refs；Finding 具有 code、fact_ids、支持／不支持的結論範圍。
- Task 6：`CoachingEvidenceBundle` 保存 owner、kind、local date／window、處方、使用者限制、分析、恢復、coverage、允許 actions、semantic fingerprint。fingerprint 排除生成／抓取時間、run ID、文案，但包含被使用的日期、有效版本、資料完整度與 evidence ID/hash。
- Task 8：`CoachingAnalysis` 使用 `schema_version='coaching-analysis-v2'`，包含 headline、summary、findings、actions、limitations、evidence_refs、analysis_mode、fallback_reason、input_fingerprint、versions。`analysis_mode=llm|rules`，fallback_reason 可為 disabled、timeout、provider_error、invalid_schema、invalid_evidence、unsupported_claim。
- 工程預設：backfill 最近 28 個已完成當地日期，優先最近 7 日；手動建議另外取得當日已有活動。連線內同時 1 個 provider 細節呼叫；每個資源最多 3 次嘗試，退避 30/120 秒加 jitter，Retry-After 有值則至少等待該值。
- 批次等待預設 120 秒；到期發布 partial manifest，完成前不逐資源觸發回顧。最近 2 個當地日期的 partial/unknown 明細最多於 15 分鐘及 2 小時再查；不支持的資源不反覆輪詢。這些是應用程式預設，不是 Garmin 官方額度。
- 樣本 chunk 每塊至多 2,000 點；FIT ZIP 處理限制 compressed 20 MiB、expanded 100 MiB、至多 20 members，超限標示 limited；原始檔僅暫存且 finally 清除，不抽取任意路徑。這些是保護處理量的可配置預設，需 Task 1 樣本確認。
- LLM 最多 2 次嘗試、每次 20 秒；沿用設定模型，不硬編碼型號。headline ≤40 字、summary ≤160 字、findings/actions 各最多 3、limitations 最多 3；每個 observation／interpretation／action ≤160 字。JSON 不含 Markdown 或任意 HTML。
- Feature flags 預設關閉：`JOHNNY_ACTIVITY_DETAILS_ENABLED`、`JOHNNY_COACHING_ANALYSIS_V2_ENABLED`；前者關閉仍可讀既有資料，後者關閉恢復舊生成／呈現相容摘要。

## File responsibility map

| Boundary | Files created or changed | Responsibility |
| --- | --- | --- |
| Acquisition | 新 `integrations/garmin_activity_details.py`、`garmin_fit_decoder.py`、`scripts/probe_activity_details.py`；改 `garminconnect_adapter.py` | 驗證來源、登入重用、單位及 FIT 解碼，與生成流程無依賴 |
| Domain/store | 新 `domain/activity_details.py`、`application/interfaces/activity_detail_store.py`、`database/activity_detail_repository.py`；改 `database/models.py` | DTO、不變 snapshot、分段／樣本及分析 persistence |
| Ingestion | 新 `application/activity_detail_sync.py`、`activity_detail_backfill.py`、`scripts/backfill_activity_details.py`；改 `agent_runtime.py` | durable batch、有限 retry、checkpoint、provider lease |
| Analytics | 新 `domain/activity_execution.py`、`domain/coaching_analysis.py`、`application/coaching_analysis_evidence.py`；改 `workout_recovery.py` | 對應處方、確定性 findings、manifest、恢復 freshness |
| Orchestration | 新 `application/coaching_generation_requests.py`；改 `coaching_refresh.py`、`coaching_repository.py`、`agent_task_queue.py` | desired input 合併、只修正最新回顧、發布競態 |
| Generation | 新 `application/coaching_analysis_generation.py`；改兩種 generation handler、`coaching_approval.py`、LLM settings、API queue/runtime wiring | JSON validation、fallback、provider provenance、安全提議 |
| UI/API | 改 Johnny/Today/activity routes、schemas、frontend types/client/composable/App/JohnnyPage；新 `CoachingAnalysis.vue`、`ExecutionSegments.vue` | 相容讀取、owner-scoped evidence、短摘要與揭露式細節 |

後端表中的短路徑皆位於 `backend/src/`；各 task 下列出完整檔案。不因新增功能大規模搬動既有模組。

### Task 1: Verify actual Garmin detail contracts

**Files:** Create `scripts/probe_activity_details.py`, `backend/tests/unit/test_activity_detail_probe.py`, `backend/tests/fixtures/activity_details/`, `docs/verification/2026-10-22-activity-detail-probe.md`; inspect existing `backend/src/infrastructure/integrations/garminconnect_adapter.py`; update `backend/requirements/base.txt` only when pinning verified FIT decoder.
**Interfaces:** `probe_activity_details(*, client: GarminClient, activity_ids: tuple[str,...]) -> dict` returns endpoint/field/unit/count/coverage/error summaries, never credentials or GPS. CLI `--user-id`, `--activity-id` (repeatable), `--output`; no implicit all-account scan.

- [x] Write tests `test_probe_redacts_identifiers_and_tracks`, `test_probe_calls_read_methods_only`, `test_partial_resource_does_not_abort_report`; assertions include `assert 'session_data' not in serialized_report`, `assert mutation_calls == []` and supported resources remain reported after a missing resource.
- [x] Run `pytest backend/tests/unit/test_activity_detail_probe.py -q`; confirm missing behavior fails.
- [x] Implement the bounded probe using existing encrypted session login, without saving activity/coaching results or plaintext sessions. Inspect easy/auto-lap/interval/pause examples if present; preserve descriptor unit evidence and timer semantics. Verify the official FIT Python decoder supports the project's deployed Python, pin the verified exact version and record it; do not guess a version or silently skip FIT work.
- [x] Run probe tests and a small authorized live read; write sanitized contract report and fixtures with synthetic IDs/dates. Report missing sample categories explicitly. Source unavailable is a recorded gate, not permission to fabricate a successful probe.
- [x] Commit only probe, sanitized fixtures, verification note and dependency pin: `test: verify Garmin activity detail contracts`.

### Task 2: Add versioned detail persistence and additive migration

**Files:** Create `backend/src/domain/activity_details.py`, `backend/src/application/interfaces/activity_detail_store.py`, `backend/src/infrastructure/database/activity_detail_repository.py`, `backend/migrations/versions/0013_activity_details.py`, `backend/tests/integration/database/test_activity_detail_repository.py`, `backend/tests/integration/database/test_activity_detail_migration.py`; modify `backend/src/infrastructure/database/models.py`.
**Interfaces:** Define shared DTOs and `ActivityDetailStore.save_snapshot(*, user_id: str, details: NormalizedDetails, fetched_at: datetime) -> DetailSnapshot`, `get_snapshots(user_id: str, activity_id: str) -> tuple[DetailSnapshot,...]`, `save_analysis(user_id: str, analysis: ExecutionAnalysis) -> str`. Use a forward type reference to Task 5's analysis DTO until defined; no circular import.

- [x] Write upgrade/idempotency/ownership tests: `assert second.id == first.id` for unchanged semantic payload; changed content yields new snapshot; equal provider IDs on separate connections stay isolated; unauthorized reads return no data. Seed 0012 data and assert activity IDs, summary, manual pairing and prescription payload survive upgrade byte-for-byte.
- [x] Run `pytest backend/tests/integration/database/test_activity_detail_repository.py backend/tests/integration/database/test_activity_detail_migration.py -q`; confirm feature failures.
- [x] Add `activity_detail_fetches`, `activity_detail_snapshots`, `activity_segments`, `activity_sample_chunks`, `activity_execution_analyses`, `activity_detail_batches`, `activity_detail_batch_items`. Batch items join activity/resource work to multiple batches; fetch state is not restricted to one batch. Use owner-scoped keys and indexes on batch/state and activity/resource. Revision `0013_activity_details` follows `0012_coaching_history`; no provider calls in Alembic. Store samples once and reference snapshot IDs from analyses.
- [x] Run the suites on SQLite, including real Alembic upgrade from a simulated deployed 0012 schema and fresh install; full backend suite: 772 passed, 7 skipped.
- [ ] Run the isolated-schema migration suite on disposable PostgreSQL (`JOHNNY_TEST_DATABASE_URL`). The configured local test database was unreachable during Task 2; the test is ready but PostgreSQL validation remains open.
- [x] Commit task files: `feat: persist versioned activity detail evidence`.

### Task 3: Normalize JSON and decode original FIT

**Files:** Create `backend/src/infrastructure/integrations/garmin_activity_details.py`, `backend/src/infrastructure/integrations/garmin_fit_decoder.py`, `backend/tests/unit/test_garmin_activity_details.py`, `backend/tests/unit/test_garmin_fit_decoder.py`; modify `backend/src/infrastructure/integrations/garminconnect_adapter.py`.
**Interfaces:** `normalize_activity_details(*, activity_id: str, resource: DetailResource, payload: dict) -> NormalizedDetails`; `decode_activity_fit(*, activity_id: str, archive: bytes) -> NormalizedDetails`; adapter `fetch_activity_detail(*, connection: IntegrationConnectionRef, activity_id: str, resource: DetailResource) -> NormalizedDetails`. A short-lived authenticated client is reused within a job; preserve existing session refresh encryption.

- [ ] Write fixtures/tests for reordered descriptors, unknown units, null HR, zero speed, typed summary overlap, repeated step index, pause events, truncated chart, corrupt FIT and archive traversal/limits. Assertions: `assert result.coverage.state != 'complete'` for unknown units; `assert result.segments[0].step_path is None` for auto lap; `assert totals_not_double_counted` when two resources describe the same laps.
- [ ] Run `pytest backend/tests/unit/test_garmin_activity_details.py backend/tests/unit/test_garmin_fit_decoder.py -q`; confirm failures.
- [ ] Normalize using Task 1 verified units; unknown fields remain unsupported. Retain source kind and chronological occurrence. Use FIT timer events and valid explicit workout links when present; chart sampling stays `chart`. Prefer verified recorded FIT evidence for overlapping complete channels, then JSON, without adding duplicate totals. Archive parsing is in memory or safe temporary files with unconditional cleanup.
- [ ] Run both suites plus `pytest backend/tests/unit/test_garminconnect_adapter.py -q`; existing summary/health behavior remains green.
- [ ] Commit: `feat: normalize Garmin segments and FIT recordings`.

### Task 4: Acquire detail in durable batches and backfill existing activities

**Files:** Create `backend/src/application/activity_detail_sync.py`, `backend/src/application/activity_detail_backfill.py`, `scripts/backfill_activity_details.py`, `backend/tests/integration/application/test_activity_detail_sync.py`, `backend/tests/integration/application/test_activity_detail_backfill.py`; modify `scripts/agent_runtime.py`, `backend/src/infrastructure/database/agent_task_queue.py`.
**Interfaces:** `ActivityDetailSyncService.start_batch(*, user_id: str, activity_ids: tuple[str,...], source_sync_run_id: str|None, now: datetime) -> str`; `process_resource(*, fetch_id: str, now: datetime) -> None`; `finalize_batch(*, batch_id: str, now: datetime) -> tuple[str,...]` returns changed activity IDs once. Backfill CLI supports `--user-id`, `--days 28`, `--dry-run`, `--resume BATCH_ID`, `--pause BATCH_ID`; CLI plans/enqueues, workers fetch.

- [ ] Write tests for idempotent resume, identical summary but newly available details, 429 backoff, 401 block, no provider ID, concurrent manual/backfill, crash after snapshot write and before acknowledgement. Assert `assert snapshot_count == 1`, `assert generation_calls == []` before batch finalization and valid old snapshots survive failed retry.
- [ ] Run `pytest backend/tests/integration/application/test_activity_detail_sync.py backend/tests/integration/application/test_activity_detail_backfill.py -q`; confirm failures.
- [ ] Implement `activity.detail.fetch.v1` and `activity.detail.finalize.v1` jobs. Persist leases/checkpoints outside network transactions; share an owner-scoped connection lease with summary sync so concurrent login/token refresh cannot overwrite newer credentials. Acquire supported resources conditionally; immutable batch membership plus durable deadline finalizer closes a batch even if no resource completes. Paused batches stop claiming new work; resumed batches retain successes.
- [ ] Run both suites with a fake clock; verify 120-second partial finalization, capped late rechecks and cancellation/reauth recovery. Execute backfill dry-run only; do not fetch all historical activities during this task's local verification.
- [ ] Commit: `feat: batch and resume activity detail enrichment`.

### Task 5: Compare recorded execution with historical Workout Steps

**Files:** Create `backend/src/domain/activity_execution.py`, `backend/tests/unit/test_activity_execution.py`; modify `backend/src/application/coaching_evidence.py` only to expose existing matched session/prescription evidence without changing score behavior.
**Interfaces:** `analyze_execution(*, prescription: PrescriptionSnapshot|None, activities: tuple[CompletedActivity,...], details: tuple[DetailSnapshot,...]) -> ExecutionAnalysis`. Step identity is stable `(step_path, repeat_occurrence)`, never display name alone.

- [ ] Write paired cases extending a 35-minute prescription to 44 minutes: `assert finding.code == 'cooldown_volume_over'` vs `'work_volume_over'` only when links are exact; auto lap must have `mapping != 'exact'`. Also cover missed repeats, unmatched tail, gaps between recordings, DST/local dates, incomplete charts, missing historical zones and uncertain prescriptions.
- [ ] Run `pytest backend/tests/unit/test_activity_execution.py -q`; confirm failures.
- [ ] Implement Repeat Block expansion, validated explicit mapping, and conservative estimated mapping for unique ordered time/distance boundaries (no claim of measured step identity). Ambiguous boundaries stay unmatched. Compute duration/distance deltas, lap variation and target-time intervals only for valid recorded intervals, excluding pause/gaps; expose denominator/coverage. Do not infer RPE, physiological cause or new readiness thresholds. Feed averages as averages, never interval compliance.
- [ ] Run new tests and `pytest backend/tests/unit/test_execution_score.py -q`; existing score fixtures must be unchanged, including approved skip and missing-data reasons.
- [ ] Commit: `feat: derive traceable workout execution findings`.

### Task 6: Build workflow-specific evidence and dated recovery context

**Files:** Create `backend/src/application/coaching_analysis_evidence.py`, `backend/tests/unit/test_coaching_analysis_evidence.py`; modify `backend/src/domain/workout_recovery.py`, `backend/tests/integration/application/test_workout_advice_recovery.py`.
**Interfaces:** `build_coaching_evidence(*, user_id: str, kind: Literal['daily_review','workout_advice'], local_date: date, timezone_name: str, workout_id: str|None, constraints: WorkoutAdviceConstraints|None, as_of: datetime, store: CoachingAnalysisEvidenceStore) -> CoachingEvidenceBundle`. Define `AdviceContext` here with current plan/workout, today sessions, Athlete Baseline and next workouts. Protocol signatures: `load_review_evidence(user_id: str, publication_date: date, timezone_name: str, as_of: datetime) -> ReviewEvidence`; `load_advice_context(user_id: str, local_date: date, timezone_name: str, workout_id: str|None, as_of: datetime) -> AdviceContext`; `list_execution_analyses(user_id: str, starts_on: date, ends_on: date, as_of: datetime) -> tuple[ExecutionAnalysis,...]`; `list_recovery_metrics(user_id: str, starts_on: date, ends_on: date) -> tuple[DailyHealthMetrics,...]`. Implement in new `backend/src/infrastructure/database/coaching_analysis_evidence_repository.py`.

- [ ] Write fingerprint/date/coverage tests: `assert before.fingerprint == after_fetch_timestamp_only.fingerprint`; actual changed step or used health value changes it; foreign/unreferenced historical detail does not. Test today sleep-only + yesterday HRV, zero HRV baseline, partial-day stress, future evidence, timezone midnight and no-plan/rest/completed distinctions.
- [ ] Run `pytest backend/tests/unit/test_coaching_analysis_evidence.py backend/tests/integration/application/test_workout_advice_recovery.py -q`; distinguish expected recovery-policy changes from regressions.
- [ ] Implement review context from yesterday + seven closed dates, advice context from today + 28 closed dates (most recent 7 analyses and aggregate counts) + next 2 scheduled workouts within 7 days. Keep source periods visible. Select each recovery signal's latest usable yesterday/today value with date/quality; do not blend mixed dates into a current-day readiness. Preserve v1 threshold policy for same-day decisions and add `workout-recovery-v2` provenance; historical signals inform qualified prose only. Bundle declares every dependency and available/missing action facts.
- [ ] Run tests; assert evidence bundle contains no samples/GPS, bounds per-activity findings to 3, and preserves uncertainty rather than suppressing it to meet context limits.
- [ ] Commit: `feat: assemble dated coaching evidence manifests`.

### Task 7: Coalesce refreshes and reject stale publication

**Files:** Create `backend/src/application/coaching_generation_requests.py`, `backend/migrations/versions/0014_coaching_generation_requests.py`, `backend/tests/integration/application/test_coaching_refresh_coalescing.py`; modify `backend/src/application/coaching_refresh.py`, `backend/src/infrastructure/database/coaching_repository.py`, `backend/src/infrastructure/database/models.py`, `scripts/agent_runtime.py`, `backend/tests/integration/database/test_coaching_postgres_concurrency.py`.
**Interfaces:** `CoachingGenerationRequests.request(*, user_id: str, kind: str, slot_id: str, fingerprint: str, reason: str) -> str|None`; `finish(*, request_id: str, completed_fingerprint: str) -> str|None` returns at most one successor. Add `coaching_generation_requests` with unique owner/kind/slot, desired fingerprint, active fingerprint/run ID and status. Migration revision `0014_coaching_requests` follows `0013_activity_details` (revision IDs ≤32 characters). Both generations and pending Recommendations reference the committed evidence manifest, persisted in their revision payload alongside snapshot IDs; generation requests hold the desired manifest fingerprint.

- [ ] Write tests with five existing review dates and three detail resources in one batch: `assert len(auto_runs) == 1`, old affected slots stale, advice not auto-generated. Same fingerprint yields no new revision/model call; a genuine new manifest during execution produces at most one successor. Assert generation/publishing itself does not bump evidence version or start sync.
- [ ] Run `pytest backend/tests/integration/application/test_coaching_refresh_coalescing.py -q`; confirm new policy failures, then update old expectations intentionally.
- [ ] Implement latest affected published slot selection, batched change notification and per-slot row-lock/CAS request merge. Reuse generation reservation ownership but check relevant manifest at publication and approval, not every unrelated global revision. New versions may remain globally tracked for audit. Network/LLM runs outside locks; publishing can fail currentness without erasing last result. Pre-detail synchronous `record_sync` must feed the batch rather than schedule independently.
- [ ] Run new tests, existing invalidation tests and real PostgreSQL two-worker/acceptance races. Confirm changed relevant evidence makes an existing proposal unacceptably stale immediately, even while the detail batch is still waiting; do not delay invalidation until generation.
- [ ] Commit: `fix: coalesce coaching refreshes by effective evidence`.

### Task 8: Add structured LLM analysis and useful deterministic fallback

**Files:** Create `backend/src/domain/coaching_analysis.py`, `backend/src/application/coaching_analysis_generation.py`, `backend/tests/unit/test_coaching_analysis_generation.py`; modify `backend/src/infrastructure/llm/settings.py` and existing gateway only for bounded call timeout/retry configuration if needed.
**Interfaces:** `generate_coaching_analysis(*, evidence: CoachingEvidenceBundle, gateway: ReviewModelGateway|None) -> AnalysisGenerationResult`; result holds validated `CoachingAnalysis`, actual provider/model/token usage and error category. `build_basic_analysis(evidence: CoachingEvidenceBundle, reason: str) -> CoachingAnalysis` uses exactly the same facts and display schema.

- [ ] Write gateway stub tests for JSON, fenced/invalid response, fabricated fact IDs, unsupported numeric/causal claims, proposed canonical changes without recommendation, malicious activity name, timeout, disabled provider and fallback with rich detail. Assert `analysis.analysis_mode == 'rules'` and nonempty interpretation/action on fallback; score cannot be supplied by model.
- [ ] Run `pytest backend/tests/unit/test_coaching_analysis_generation.py -q`; confirm failures.
- [ ] Implement versioned Traditional Chinese prompts (`johnny-workout-analysis-v2`, `johnny-review-analysis-v2`) and strict parsing. Model findings select existing fact IDs and actions select allowed action IDs; numeric statements must match referenced fact values/units, otherwise reject. Exact numeric plan changes come from approved action data, not prose. Unknown fields, too-long output and unresolved evidence references fail validation. Enforce shared call limits at transport as well as app level so SDK retries do not multiply attempts. Record fallback reason, not raw provider errors or secrets.
- [ ] Run tests and a fixed adversarial quality fixture set: check observation → meaning → action, evidence limits, no duplicated score, no unsupported recovery guarantees. Record that validation/evals constrain but do not mathematically guarantee all natural-language truthfulness.
- [ ] Commit: `feat: generate structured coaching analysis with fallback`.

### Task 9: Wire both workflows, provenance and safe approvals

**Files:** Modify `backend/src/application/workout_advice_generation.py`, `backend/src/application/training_review_generation.py`, `backend/src/application/coaching_approval.py`, `backend/src/api/routes/johnny.py`, `scripts/agent_runtime.py`; create `backend/tests/integration/application/test_structured_coaching_flows.py`; extend `backend/tests/unit/test_johnny_api.py`, `backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`.
**Interfaces:** Both handler constructors accept `analysis_evidence` and `analysis_generator`; existing handle arguments remain compatible. Result adds `analysis: CoachingAnalysis payload`; guidance/narrative is derived short compatibility text. `_queue_handler` resolves configured provider for both workflows and stores matching prompt/model provenance.

- [ ] Write end-to-end fake-provider tests: requested advice reaches gateway; review reaches gateway for no-plan activity/missed/uncertain cases too; model failure publishes useful basic result; `assert plan_before == plan_after` until acceptance; invalidated manifest cannot be accepted. Assert one workflow result does not overwrite the other's content and unchanged evidence leaves the other's freshness intact.
- [ ] Run `pytest backend/tests/integration/application/test_structured_coaching_flows.py backend/tests/unit/test_johnny_api.py -q`; confirm failures.
- [ ] Wire completed summary sync through detail batch continuation, then evidence/analysis/generation. Persist actual model usage and mode in run/output; local-only is explicit rules mode. Keep same-day scope, race/started workout restrictions, constraints and exact before/after recommendation semantics. Remove raw recovery-value dump from default guidance, retain values in evidence. Honor manual request IDs and date expiration throughout delayed sync.
- [ ] Run suites plus existing workout advice flow/recovery/invalidation, training review generation and worker scheduler tests; verify unavailable detail reduces analysis depth without declaring a completed activity missed.
- [ ] Commit: `feat: connect coaching analysis to review and advice workflows`.

### Task 10: Expose compatible APIs and evidence freshness

**Files:** Modify `backend/src/api/routes/johnny.py`, `backend/src/api/routes/today.py`, `backend/src/api/routes/activity_health.py`, `backend/src/api/schemas/johnny.py`, `backend/src/api/schemas/activity_health.py`, `backend/tests/unit/test_johnny_api.py`; create `backend/tests/unit/test_activity_detail_api.py`; update `docs/backend_api.md`.
**Interfaces:** Existing overview/history keep envelopes and old fields. Add `GET /api/v1/activities/{activity_id}/execution` for summarized segments/current analysis (no raw samples), with optional `analysis_id` to retrieve the exact immutable historical analysis after checking activity and owner and `GET /api/v1/activities/detail-coverage` for owner counts/status; register fixed route before dynamic route. Existing `POST /johnny/reviews/{id}/retry` gains optional `source: Literal['stored_evidence','sync']='stored_evidence'`; absent body on sync_failed defaults to sync, other absent-body retries use stored evidence.

- [ ] Write tests for v1/v2 response compatibility, owner-only evidence lookup, missing activity 404, summaries with missing details, retry historical stale review without provider calls. Assertions: `assert provider_calls == 0` for explicit stored_evidence; new generation uses original review date/timezone; compatibility guidance remains a string.
- [ ] Run `pytest backend/tests/unit/test_johnny_api.py backend/tests/unit/test_activity_detail_api.py -q`; confirm failures.
- [ ] Implement explicit freshness/analysis mode/detail coverage without conflating them. Store/retrieve the snapshot IDs used by a historical analysis, not today's latest detail. Add additive response schemas; missing analysis remains absent for v1 revisions. API never reports chart coverage as full recording precision.
- [ ] Run both suites and relevant Today/activity API tests; update API examples for normal, rules, partial, stale and legacy responses.
- [ ] Commit: `feat: expose compatible coaching analysis and evidence APIs`.

### Task 11: Present decisions and findings across Johnny, Today and Data

**Files:** Create `frontend/src/components/CoachingAnalysis.vue`, `frontend/src/components/ExecutionSegments.vue`, `frontend/src/components/CoachingAnalysis.test.ts`; modify `frontend/src/pages/JohnnyPage.vue`, `frontend/src/types.ts`, `frontend/src/api/client.ts`, `frontend/src/composables/useJohnny.ts`, `frontend/src/App.vue`, `frontend/src/styles.css`, `frontend/src/JohnnyPage.test.ts`, `frontend/src/App.test.ts`, `frontend/src/composables/useJohnny.test.ts`, `DESIGN.md`.
**Interfaces:** TS `CoachingAnalysis` mirrors backend schema; components accept `analysis`, `freshness`, `kind` and emit `openEvidence({activityId, analysisId})` / `openRecommendation(id)`. `ExecutionSegments` accepts analyzed rows with mapping/coverage; legacy renderer uses the existing guidance/narrative unchanged. API client exposes `getActivityExecution`, `getActivityDetailCoverage` and retry source.

- [ ] Write Vitest assertions for conclusion/meaning/action ordering, one score display, rules label independent of missing data, mobile-equivalent DOM reading order, known vs estimated segment labels, legacy payload, stale result, independent pending states and Today short summary only. Ensure history stale row has explicit stored-evidence recalculation action; no default raw recovery dump.
- [ ] Run `npm --prefix frontend test -- src/components/CoachingAnalysis.test.ts src/JohnnyPage.test.ts src/App.test.ts src/composables/useJohnny.test.ts`; confirm failures.
- [ ] Read Impeccable craft-floor and applicable UI skills before edits. Implement on the incumbent dark ruled surface: compact no-proposal line, concise heading, 1–3 findings/actions, expandable reasons/segments, secondary score once. Data shows activity-detail coverage separately from whole-activity availability. Today uses new summary or legacy guidance; History retains correct date/version/freshness and explicit reanalysis. Maintain focus, native disclosure, keyboard tabs, responsive stacked rows and reduced-motion behavior; no raw Markdown/HTML injection.
- [ ] Run targeted Vitest, `npm --prefix frontend run build`, `npm --prefix frontend run verify:tokens`. Inspect desktop/mobile together for rich, rules, partial, stale and legacy cases; fix observed issues once and confirm. Record screenshots and test evidence, not invented visual results.
- [ ] Commit: `feat: present actionable coaching findings and segment evidence`.

### Task 12: Verify migration, backfill, worker cutover and rollback

**Files:** Create `backend/tests/integration/application/test_coaching_detail_acceptance.py`, `docs/verification/2026-10-22-coaching-detail-acceptance.md`; modify `docs/deployment-v1.md`, `docs/manual_test_runbook.md`, `docs/database_schema.md`, `docs/agent_runtime_tools.md`; document updated domain behavior in `CONTEXT.md` using applicable domain-doc skill. Include producer/runtime flag wiring in `scripts/agent_runtime.py` and settings if not already covered.
**Interfaces:** Task payloads carry `contract_version=1`; new worker claim filters accept only supported task types/versions. Existing unversioned task types remain explicitly supported as legacy v0; unknown versions remain unclaimed and observable. Old workers cannot be made safe by new filtering, so drain/stop them before enabling new producers. Feature flags follow shared defaults; health/readiness endpoints show worker build/contract compatibility without leaking configuration.

- [ ] Write acceptance fixture with five historical review slots, user-requested advice, three detail resources, worker interruption, late real change and acceptance race. Assert one automatic latest-review refresh for the initial batch, no new content for identical effective input, one successor for coalesced late change, preserved old history, and no unauthorized plan mutation. Add flag-off rollback/legacy reads and PostgreSQL 0012→head preservation tests.
- [ ] Run `pytest backend/tests/integration/application/test_coaching_detail_acceptance.py -q`; confirm expected failures before missing release wiring is implemented.
- [ ] Implement flag/claim compatibility and deployment runbook: inventory exact worker commands/builds; pause scheduler/producers, drain or requeue leases, backup and verify restore on disposable DB, migrate, deploy compatible API/workers, enable detail collection, dry-run then complete resumable backfill, validate coverage, enable analysis v2/UI. Preserve credentials and manual pairing. Do not use destructive DB downgrade for rollback; disable new producers/flags and retain evidence tables. Adapt existing deployment workflow instead of inventing another deployment system.
- [ ] Run `PYTHONPATH=.:backend ./.venv/bin/python -m pytest backend/tests -q -rs`, with disposable PostgreSQL configured for migration/concurrency tests; then `npm --prefix frontend test`, build and token checks. On test DB verify replay/backfill twice has identical snapshots/fingerprints and no additional model calls. Record sample bytes/activity and backfill throughput; report missing live/PG gates explicitly. Full UI verification re-runs only when this task changes UI behavior.
- [ ] Produce a concrete release report: covered dates, complete/partial/unsupported/failed activity/resource counts, remaining retry jobs, generated/skipped revisions, actual model/fallback ratios, restored-DB check and worker versions. Local verification does not authorize production deployment; present exact release/runbook for any required deployment approval. Commit: `test: verify coaching detail migration and release readiness`.

## Completion and handoff

完成代表：分段實際取得／不能取得的情況都有證據，歷史回填可續跑，分析能追溯到當時處方，兩種功能確實使用新分析與 LLM/fallback，跨頁相容，相關 PostgreSQL 和前端驗證通過，批次不再重複產生相同回顧。不能用「只改 prompt」、「只有 UI」或「schema 建好但未驗證回填」宣稱全部完成。

計畫自查覆蓋：取得/FIT 1–3；migration/backfill 2/4/12；分析/恢復 5–6；去重/競態 7/12；LLM/fallback 8–9；分數不變 5/9/11；API 相容/歷史重算 10；前端 11；部署/rollback 12。五個 Review Focus 均有對應測試，未把尚未執行的實帳驗證或 PostgreSQL 測試標成已通過。

建議採逐 task 實作與獨立審查：這份計畫跨資料遷移、併發與模型輸出，介面錯誤若累積到 UI 才發現會較難修正。也可由同一 agent 連續實作，再集中做完整 review；選定方式後按同一份依賴順序執行。
