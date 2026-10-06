# 訓練計畫真實 LLM 整合驗證

本文件是可重複執行的操作說明；是否已跑過真實模型以另存的驗證證據為準。目的為完整 `training_plan_generation` 驗證，而非僅驗證對話。
依據：[README](../README.md)、[專用 PostgreSQL runbook](training_plan_postgresql_verification.md)、[Plan Skeleton ADR](adr/0001-deterministic-training-plan-skeletons.md)。
所有命令從 repo 根目錄、全新專用 Bash shell 執行；只用合成 Athlete Baseline、虛構賽事，不匯入 Garmin 或真實健康資料。
產品 POST 會在排隊時依 key 與 model 固定 `provider/model`；worker 使用 run 中的值，不依當下環境改選。成功標準包含真實 gateway 呼叫、run completed 與持久化計畫，不只看 queued metadata。
## 1. 執行前核准與界線
1. 記錄核准人、明確選定的模型、可接受總費用與停止條件；取得核准後才執行第 4、5 節付費步驟。
2. 首輪只核准一個合成 maintenance 案例、一次 worker 執行；其餘五個案例需要另行核准。
3. 每次最多一次模型修復，即首次生成加一次修復；禁止為追求漂亮結果無限重跑。
4. 正式 worker 沒有請求級費用／時間上限；監看單次執行並在核准上限前停止。中斷單次請求不保證免計費。
5. 超時以 `Ctrl+C` 停止，先確認 process 已退出與資料庫狀態，再決定是否重新核准。中斷不保證免計費。
6. Repo 沒有 CLI 費用上限、輸出 token 上限或 workflow 硬期限；harness timeout 不是總費用保證。
7. 正常 workflow 的 `ValueError` 路徑最多一次 repair；gateway/schema 錯誤不一定進 repair/fallback。
8. 不記錄 API key、Cookie、環境變數全集或原始 HTTP debug；勿開 `set -x`，分享證據前再次遮蔽敏感內容。

`LLM_MODEL` 必須由使用者明確選定；repo 的 `gpt-5-nano` 僅是既有範例，不是新推薦。本文不提供現行價格，超出核准預算立即停跑。
## 2. 獨立資料庫與本機認證
先依專用 PostgreSQL runbook **第 1–3 節**執行最新版安全前置條件、local Docker context guard、全新 Bash、容器建立與唯讀身分確認；不跑其測試、seed 或 API。
只使用該流程新建的 `PG_VERIFY_CID`，`postgres:16`、`127.0.0.1:15432`、`verify_only/verify_disposable`、tmpfs；不得碰既有 Compose、5432 或 volume。
另建不同 LLM DB；同名已存在即停止，不清空或重用。下方命令供日後操作者執行：

```bash
set -euo pipefail
test "$(docker inspect -f '{{index .Config.Labels "johnny.purpose"}}' "$PG_VERIFY_CID")" = training-plan-pg-verification
docker exec "$PG_VERIFY_CID" psql -U verify_only -d postgres -c "SELECT datname FROM pg_database WHERE datname = 'training_plan_llm_verify';"
docker exec "$PG_VERIFY_CID" createdb -U verify_only training_plan_llm_verify
export DATABASE_URL='postgresql+psycopg://verify_only:verify_disposable@127.0.0.1:15432/training_plan_llm_verify'
export ENV=test
make migrate DATABASE_URL="$DATABASE_URL"
DATABASE_URL="$DATABASE_URL" ./.venv/bin/alembic -c backend/alembic.ini current
```

預期：查詢無同名資料庫、建立成功、migration 到 head。建立失敗時不得改連預設庫繼續。
不執行 `make seed-demo`。`get_database_url()` 通常用 `load_dotenv(override=False)` 保留 shell 值，但 `ENV=test` 完全不載入 `backend/.env`；全程保留此隔離，勿顯示或提交秘密。
在專用 shell 內輸入核准的 model 與 key；API 與 worker 必須使用**相同**的 key/model、`ENV=test`、專用 DB URL。不要 `source backend/.env` 或輸出金鑰。header 認證僅限 loopback，絕不套用於正式部署：

```bash
export LLM_PROVIDER=openai
export LLM_MODEL='已核准的模型名稱'
export LLM_API_KEY=''
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
test -n "$OPENAI_API_KEY" && test -n "$LLM_MODEL"
export JOHNNY_AUTH_REQUIRED=true
export JOHNNY_AUTH_ALLOW_HEADER_USER=true
if lsof -nP -iTCP:18001 -sTCP:LISTEN; then exit 1; fi
PYTHONPATH=backend ./.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 18001
```

預期 API 綁定 `127.0.0.1:18001`；埠已占用即停止，不刪占用者。另開全新專用 Bash terminal，明確設定相同 LLM DB URL、`ENV=test`、核准的 model 與 key，再設定：

```bash
set -euo pipefail
export API='http://127.0.0.1:18001'
export VERIFY_USER='llm-verify-maintenance'
curl -fsS "$API/health"
curl -fsS "$API/ready"
```

預期：`health` 為 ok、`ready` 為 ready。`X-Johnny-User-Id` 使用虛構 ID；不使用真實 OAuth session。

## 3. 建立六組合成案例
每個案例獨立 user ID，避免 Active Projection、配額與 smoke idempotency 干擾。先令 `VERIFY_USER` 為案例 ID，再建立基準，不呼叫模型：

```bash
curl -sS -X PUT "$API/api/v1/athlete/profile" \
  -H "X-Johnny-User-Id: $VERIFY_USER" -H 'Content-Type: application/json' \
  -d '{"timezone":"Asia/Taipei","experience_level":"intermediate","current_weekly_mileage_km":30,"preferred_training_days":["tuesday","thursday","sunday"],"preferred_long_run_day":"sunday","max_runs_per_week":3,"max_hard_sessions_per_week":2,"unit_preference":"metric","injury_status":"none"}'
```

預期：`data.user_id` 等於案例 ID，輸入限制完整回傳。記錄 profile JSON 作為預期 skeleton 的依據。
需要驗證心率區間時，在完整 profile 中加入 `resting_heart_rate_bpm` 與 `max_heart_rate_bpm`（最高須大於靜息）；缺少任一值的案例應以 RPE 為主要 Target。若設定閾值配速，可加入 `threshold_pace_seconds_per_km`，並分別記錄估算配速的來源與信心。
賽事案例用下方命令；`RACE_DATE` 必須替換為相對執行日的實際 ISO 日期，勿照抄過期日期：

```bash
export RACE_DATE='YYYY-MM-DD'
curl -sS -X POST "$API/api/v1/races" \
  -H "X-Johnny-User-Id: $VERIFY_USER" -H 'Content-Type: application/json' \
  -d "{\"name\":\"Synthetic Half\",\"race_date\":\"$RACE_DATE\",\"distance_meters\":21097,\"target_finish_seconds\":7200,\"priority\":\"primary\"}"
```

預期回傳 `data.id`；記錄 ID、日期、距離與目標，不自造 ID。以 Athlete Baseline 時區的明天為產品起日，按下表準備並記錄完整請求：

| 案例 ID 尾碼 | 準備與操作 | 預期策略／結構 |
| --- | --- | --- |
| maintenance | 不建立賽事；再生成傳 `plan_type: maintenance` | Aerobic Maintenance Block，連續 4 週，共 28 日 |
| race-goal | 建立起日後 8 週的半馬，7200 秒目標；指定回傳 race ID | 選定該 Race Strategy，終日為比賽日，完整涵蓋各週與階段 |
| race-no-goal | 同樣 21097 公尺，省略 `target_finish_seconds` | 仍為 race，不因缺目標退成 maintenance；不臆測高信心目標配速 |
| far-future | 建立起日後 24 週賽事 | 最多 16 週／112 日；本投影以有氧為主，不提前 peak/taper |
| priority | 建立較近 secondary、較遠 primary、另一更遠 primary；省略 race ID | 先 primary，再同優先級最近日期；不是所有賽事中最近者 |
| weak-baseline | profile 改為里程 0、experience_level null、hard 上限 0；無活動資料 | 保守負荷、不安排 Hard Session、不編造活動、配速或健康證據 |

priority 建立多場賽事時改 `name`、`race_date`、`priority`；合法順位為 `primary`、`secondary`、`tune_up`。
在已選 Race Strategy 的計畫期間，另建 secondary 與 tune-up 賽事，至少一場放在非偏好訓練日。預期每場在 event date 有獨立 race workout，距離等於賽事距離；secondary 預設完整表現強度，tune-up 預設受控訓練強度。賽事新增、改期、取消或刪除後，既有 Active Projection 不會自動改寫；介面應提示手動重新產生。
weak-baseline 重送完整 profile，保留必要欄位；受傷降載與更多距離變體先由第 7 節 fixtures 驗證，增加 live 樣本須另行核准。

## 4. 產品再生成與正式 worker
對各案例先取得 options，再送一次產品請求（付費呼叫發生在 worker，而非 queue POST）：

```bash
curl -sS -H "X-Johnny-User-Id: $VERIFY_USER" "$API/api/v1/training-plans/regeneration-options"
curl -sS -X POST "$API/api/v1/training-plans/regenerations" \
  -H "X-Johnny-User-Id: $VERIFY_USER" -H 'Content-Type: application/json' \
  -d '{"client_request_id":"verify-maintenance-001","plan_type":"maintenance"}'
```

race 案例改 `plan_type` 為 `race`，需要明選時加 `race_id`；priority 不傳 race ID。
各案例使用不同 `client_request_id`；產品 schema 不接受自訂起日／終日。預期 `data.run` 含 `run_id`、`poll_url`，`default_strategy` 給出起日、horizon、reason。
先以 GET run 確認排隊時 `provider=openai`、`model` 為核准值；若不是，停止，不執行 worker。確認專用 DB 恰好一個 queued `agent.workflow` task，且屬於上方 `run_id`。worker shell 的 `ENV=test`、`DATABASE_URL`、key/model 必須與 API 相同。只執行一次正式 worker 命令：

```bash
test "$ENV" = test
test "$DATABASE_URL" = 'postgresql+psycopg://verify_only:verify_disposable@127.0.0.1:15432/training_plan_llm_verify'
test -n "$LLM_MODEL" && test -n "${LLM_API_KEY:-}${OPENAI_API_KEY:-}"
PYTHONPATH=backend ./.venv/bin/python scripts/agent_runtime.py \
  --database-url "$DATABASE_URL" work-one
```

不得啟 scheduler/loop 或改 patch gateway。預期 `processed=1`；必須再查 linked run、steps、plan，不能把 processed 當成功。失敗不自動重跑；先記錄 error type、確認是否已計費，再重新取得核准。

## 6. 每次結果、結構與證據
```bash
export RUN_ID='回傳的 run_id'
curl -sS -H "X-Johnny-User-Id: $VERIFY_USER" "$API/api/v1/agent-runs/$RUN_ID"
curl -sS -H "X-Johnny-User-Id: $VERIFY_USER" "$API/api/v1/agent-runs/$RUN_ID/steps"
curl -sS -H "X-Johnny-User-Id: $VERIFY_USER" "$API/api/v1/training-plans"
```

比較前後 plans；由 `createTrainingPlan` step 的 `payload.training_plan.id` 找新版本，再 GET `/api/v1/training-plans/{plan_id}`。列表以 `limit`／`offset` 讀完，不將截斷清單當全量證據。
逐項記錄實際值與判定，不僅閱讀摘要或 Coach Note：

- run：`workflow_name=training_plan_generation`、completed、model 為核准模型或回傳版本；`_merge_model_metadata` 會以 ModelResponse 更新 provider/model，成功診斷可為 openai，仍須對照實際 gateway、steps、usage 與持久化輸出，不能只看 metadata。
- 完整性：從 starts_on 每 7 日分週，最後可為部分週；每週都有 skeleton 預定 workouts，而非每天必須跑步。
- Plan Phase：`metadata.phase_segments` 全期連續、無缺口／重疊，workout 日期、phase、type、負荷與 skeleton 一致。
- 安全：每週 runs 不超 profile；interval、tempo、hill、long_run 均計入 Hard Session，跨週也不可相鄰。
- hard 上限：不超 `min(max_hard_sessions_per_week, ceil(max_runs_per_week/2), 2)`；current/recent injury 再降至最多 1，弱基準或遠期策略另依 skeleton 降載。
- Workout Step：關鍵課有可執行暖身、工作／恢復與收操；Repeat Block 有正整數次數與巢狀 steps，總量不超 skeleton。
- 數值 Target：檢查實際 `steps[].target`，不是新增 `numericTarget` 欄位；pace/bpm 範圍有效、RPE 為 1–10，不能只給 zone 標籤。數值範圍必須由可信 Athlete Baseline 與活動證據在生成／修復後推算，不採模型提供的數值。
- 配速估算：每個 running target 可在 RPE 或 HR 主目標外附 `pace_range_seconds_per_km`、`pace_source`、`confidence`。來源依序為閾值配速、符合條件的已完成賽事、三筆配對輕鬆跑、目標完賽時間；無足夠證據時不顯示配速。坡跑配速僅為平地參考。
- 心率：完整有效靜息／最高心率組合可為持續跑提供 HRR 估計範圍；缺失、無效組合及短間歇、坡跑、賽事強度以 RPE 為主。`display_name`／`compact_summary` 由結構決定，不採模型取名。
- 賽事：檢查每場 in-horizon target、secondary、tune-up 的 `race_goal_id`、日期、距離與 priority；缺漏須經修復後才可成為 Active Projection。
- repair：核對 failed steps、`metadata.internal.model_repair`、`internal.completion_repair` 的原因、週索引及 workout IDs，並比對 step 的 `payload.completion_repair`。
- 分類：無修復的有效 LLM、一次模型修復後有效、deterministic completion repair/fallback、failed，分開統計。
- fallback：即使 run completed 且 provider openai，`generation_mode=fallback` 或 deterministic fallback 摘要仍不得記為純 LLM 有效通過。
- 原子性：failed 時不可出現部分新計畫或替換既有 Active Projection；用前後 ID、status、workouts 比較，非只看 run.failed。

已有 telemetry：run 的 latency_ms、input_tokens、output_tokens、total_tokens；成功路徑可累計模型修復 usage，無 usage 時記「不可取得」，不是 0。
未實作：逐請求完整 usage／成本台帳、帳單金額、失敗呼叫 usage 保證、硬費用封頂；需人工記錄開始／結束與供應商帳務資料，勿以 tokens 當實際費用。
證據至少含 commit SHA、案例輸入、核准範圍、正式產品路徑、run/plan ID、遮蔽後 run/steps/plan、逐項結果與清理確認。

## 7. 配額、冪等與故障案例
產品手動測試：worker 前重送相同 request ID，預期同 run；不同 ID 在 in-flight 時也共用既有 run，不新增 task。
成功後重送相同 ID仍回同 run；新 ID受每日 1 次限制，回 `run:null`，options 顯示 used 1、remaining 0、available false。
以 Athlete Baseline 時區的成功完成日計費；有合法 fallback 的 completed 也屬成功，不能當失敗免配額。
真正 failed 不扣配額；相同 ID回原 failed run，新 ID可再排隊，但再次付費前必須重新核准。
失敗、跨午夜、畸形 schema、漏週或原子 rollback 不要求隨機 LLM 重現；以現有 fake gateway fixtures 驗證：

```bash
ENV=test LLM_PROVIDER='' LLM_API_KEY='' OPENAI_API_KEY='' ./.venv/bin/python -m pytest -q backend/tests/unit/test_training_plan_generation.py backend/tests/unit/test_training_plan_generation_domain.py backend/tests/unit/test_training_targets.py backend/tests/unit/test_running_companion_agent.py backend/tests/unit/test_training_plan_regeneration.py backend/tests/unit/test_openai_gateway.py backend/tests/unit/test_openai_agent_composition.py backend/tests/integration/application/test_agent_runtime_worker_scheduler.py backend/tests/integration/application/test_race_aware_generation_flow.py
```

預期 tests passed；fixtures 涵蓋漏週、一次 repair、fallback、numeric Target、持久化失敗與配額／冪等。未覆蓋的 PostgreSQL 故障原子性須列未驗證，不由 unit pass 推論。
OpenAI [function calling 官方文件](https://developers.openai.com/api/docs/guides/function-calling) 說明 strict schema、required 與禁止額外 properties；schema 合法不等於週數、階段或負荷語意完整，仍需 Johnny domain 驗證。

## 8. 清理與結論
停止 API、harness，確認沒有存活 worker；先保存遮蔽證據，再確認專用庫名稱、沒有其他連線，取得刪除核准後執行：

```bash
test "$(docker inspect -f '{{index .Config.Labels "johnny.purpose"}}' "$PG_VERIFY_CID")" = training-plan-pg-verification
docker exec "$PG_VERIFY_CID" dropdb -U verify_only training_plan_llm_verify
unset OPENAI_API_KEY LLM_API_KEY LLM_PROVIDER LLM_MODEL DATABASE_URL VERIFY_USER API RUN_ID RACE_DATE
```

不強制斷線、不刪 volume、不跑 downgrade 或 `make db-down`。若容器僅供本次流程，保存證據後依專用 PG runbook 以已核對的 CID 清理；若仍供 PG 驗證使用，僅刪本 LLM DB。
結論分列「真實 LLM 樣本結果」「repair/fallback 安全性」「產品配額」「未驗證事項」，不可合成單一全通過。
