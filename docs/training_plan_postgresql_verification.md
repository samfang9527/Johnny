# 訓練計畫 PostgreSQL 整合驗證

本文件是供操作者另行執行的步驟；撰寫時只檢查原始碼，未執行 Docker、資料庫或測試。請開全新專用終端並啟動 `bash --noprofile --norc`，從儲存庫根目錄依序執行；不要使用日常開發 shell，因本流程會覆寫 ENV、DB URL 並清空 API key 環境變數。任何檢查失敗立即停止，不可改連既有資料庫。

## 1. 範圍與破壞性警告

**`backend/tests/integration/database/test_postgresql_persistence.py` 會執行 `Base.metadata.drop_all(engine)`，並刪除 `alembic_version`，然後重建 schema。這會刪除目標資料庫內 ORM 管理的全部資料表與資料。**

- 只允許全新、可丟棄的 PostgreSQL 16 專用容器；綁定 `127.0.0.1:15432`，不用任何既有 volume。
- 不得碰觸 `docker-compose.yml` 的 `johnny-postgres`、5432、`johnny-postgres-data` 或任何使用者資料。
- 不沿用 `backend/.env.example` 的 URL；該檔的 `johnny_test` 名稱不代表安全隔離。
- 此流程不使用 `make db-up`、`make db-down`、`docker compose down -v` 或廣泛 volume 清理。
- 此單一 PostgreSQL 測試只涵蓋 migration、user／recommendation repository 與 commit 後重新讀取，**不涵蓋訓練計畫 activation、worker rollback 或真正併發**。
- 其他後端測試大多是 SQLite／記憶體替身等非 PostgreSQL 覆蓋，不是「全部通過 PostgreSQL」；項數需以當次收集結果為準。

## 2. 前置條件與隔離容器

需要 Docker、Bash、`curl`、`lsof`，以及已安裝 `backend/requirements/dev.txt` 的 `./.venv/bin/python`（含 pytest、Alembic、SQLAlchemy、psycopg、uvicorn）。不要為此修改 `.env`。15432 或容器名稱被占用時停止，交由操作者選擇另一個全新名稱／備用埠並同步更新全部檢查，不得刪除占用者。

```bash
cd /Users/fangchangseng/Desktop/Projects/Johnny
set -euo pipefail
test -x ./.venv/bin/python
./.venv/bin/python -m pip show pytest alembic sqlalchemy psycopg uvicorn
test -z "${DOCKER_HOST+x}" || { printf '停止：DOCKER_HOST override 已設定\n'; exit 1; }
export DOCKER_CONTEXT="$(docker context show)"
endpoint="$(docker context inspect "$DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}')"
case "$endpoint" in unix:///*) test -S "${endpoint#unix://}" ;; *) printf '停止：拒絕 SSH／TCP／非本機 socket daemon\n'; exit 1 ;; esac
printf 'Docker context=%s endpoint=%s\n' "$DOCKER_CONTEXT" "$endpoint"
read -r -p '確認此 context/socket 屬於本機 Docker Desktop／daemon，非遠端轉送；輸入 LOCAL-DOCKER: ' local_confirmation
test "$local_confirmation" = LOCAL-DOCKER
if lsof -nP -iTCP:15432 -sTCP:LISTEN; then exit 1; fi
export PG_VERIFY_CONTAINER=johnny-training-plan-pg16-verification
if docker container inspect "$PG_VERIFY_CONTAINER" >/dev/null 2>&1; then exit 1; fi
export PG_VERIFY_URL='postgresql+psycopg://verify_only:verify_disposable@127.0.0.1:15432/training_plan_verify'
export DATABASE_URL="$PG_VERIFY_URL" JOHNNY_TEST_DATABASE_URL="$PG_VERIFY_URL"
export ENV=test LLM_PROVIDER='' LLM_MODEL='' OPENAI_API_KEY='' LLM_API_KEY=''
export PG_EVIDENCE_DIR="$(mktemp -d /tmp/johnny-pg-verification.XXXXXX)"
git rev-parse HEAD > "$PG_EVIDENCE_DIR/commit.txt"
docker run -d --name "$PG_VERIFY_CONTAINER" \
  --label johnny.purpose=training-plan-pg-verification \
  --publish 127.0.0.1:15432:5432 \
  --tmpfs /var/lib/postgresql/data:rw \
  -e POSTGRES_USER=verify_only -e POSTGRES_PASSWORD=verify_disposable \
  -e POSTGRES_DB=training_plan_verify postgres:16 > "$PG_EVIDENCE_DIR/container-id.txt"
export PG_VERIFY_CID="$(cat "$PG_EVIDENCE_DIR/container-id.txt")"
docker inspect "$PG_VERIFY_CID" > "$PG_EVIDENCE_DIR/container-inspect.json"
docker port "$PG_VERIFY_CID" 5432/tcp
ready=0
for attempt in {1..30}; do
  if docker exec "$PG_VERIFY_CID" pg_isready -U verify_only -d training_plan_verify; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
```

`127.0.0.1` publish 是相對於 daemon，不能證明 daemon 在本機；上述閘門須先通過，後續保持固定 context。預期埠顯示 `127.0.0.1:15432`。檢查 inspect 中 image 為 `postgres:16`、標籤正確、資料目錄為 tmpfs、無使用者 bind mount 或既有 volume；記錄 image ID。這是暫存資料，不保證容器重啟後保留。

## 3. 唯讀身分確認與人工安全閘門

以下透過**宿主機同一條 URL**查核 PostgreSQL，不只在容器內查詢。資料庫交易設為唯讀；查到非預期 DB／使用者／版本，或新 DB 已有資料表即停止。

```bash
./.venv/bin/python - <<'PY' | tee "$PG_EVIDENCE_DIR/database-identity.txt"
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
expected = 'postgresql+psycopg://verify_only:verify_disposable@127.0.0.1:15432/training_plan_verify'
assert os.environ['DATABASE_URL'] == os.environ['JOHNNY_TEST_DATABASE_URL'] == expected
url = make_url(expected)
assert (url.host, url.port, url.database, url.username) == ('127.0.0.1', 15432, 'training_plan_verify', 'verify_only')
engine = create_engine(expected)
with engine.begin() as connection:
    connection.execute(text('SET TRANSACTION READ ONLY'))
    row = connection.execute(text("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port(), current_setting('server_version_num')::int")).one()
    print(tuple(row))
    assert row[0] == 'training_plan_verify' and row[1] == 'verify_only'
    assert row[3] == 5432 and 160000 <= row[4] < 170000
    tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars().all()
    print('public tables:', tables)
    assert not tables, '新隔離資料庫應無資料表；停止，不可清空既有 DB'
engine.dispose()
PY
read -r -p '確認僅可刪除新建 training_plan_verify 資料表，輸入 DROP-ONLY-DISPOSABLE: ' confirmation
test "$confirmation" = DROP-ONLY-DISPOSABLE
```

容器內伺服器埠應為 5432；宿主映射才是 15432。需同時確認容器 inspect 與 URL，不能只因 DB 名稱相符就略過安全閘門。

## 4. Migration 與唯一現有真 PostgreSQL 測試

`Makefile` 的 `migrate` 會傳入 `DATABASE_URL`；`backend/migrations/env.py` 優先讀該環境變數。用明確參數覆蓋 Makefile 預設 5432。

```bash
DATABASE_URL="$PG_VERIFY_URL" ./.venv/bin/python -m alembic -c backend/alembic.ini heads | tee "$PG_EVIDENCE_DIR/heads.txt"
make migrate DATABASE_URL="$PG_VERIFY_URL" 2>&1 | tee "$PG_EVIDENCE_DIR/migrate.txt"
DATABASE_URL="$PG_VERIFY_URL" ./.venv/bin/python -m alembic -c backend/alembic.ini current | tee "$PG_EVIDENCE_DIR/current-before.txt"
DATABASE_URL="$PG_VERIFY_URL" JOHNNY_TEST_DATABASE_URL="$PG_VERIFY_URL" ENV=test \
  ./.venv/bin/python -m pytest -vv -ra \
  backend/tests/integration/database/test_postgresql_persistence.py::test_postgresql_migrations_and_repositories_with_configured_database \
  --junitxml="$PG_EVIDENCE_DIR/postgresql.xml" 2>&1 | tee "$PG_EVIDENCE_DIR/postgresql-test.txt"
DATABASE_URL="$PG_VERIFY_URL" ./.venv/bin/python -m alembic -c backend/alembic.ini current | tee "$PG_EVIDENCE_DIR/current-after.txt"
```

預期 heads 與兩次 current revision 相符、單一測試 `1 passed`，不能把 skip 算成功。測試本身再次刪表並 upgrade head，所以必須在建立任何手動案例資料**之前**執行；後續不得再跑它，除非接受丟棄全部案例證據。migration head 不硬編碼，避免日後新增 migration 失效。

## 5. 現有 API／worker 的手動快樂路徑

僅使用隔離 DB 的 demo 使用者 `local-user`。先 seed，再啟動專用 API；18000 被占用時停止。API 啟動命令在第二個 shell 執行，明確重設 URL，不沿用既有 8000 API。

```bash
make seed-demo DATABASE_URL="$PG_VERIFY_URL" 2>&1 | tee "$PG_EVIDENCE_DIR/seed.txt"
if lsof -nP -iTCP:18000 -sTCP:LISTEN; then exit 1; fi
```

第二個 shell 也使用全新專用終端的 `bash --noprofile --norc`：
```bash
cd /Users/fangchangseng/Desktop/Projects/Johnny
DATABASE_URL='postgresql+psycopg://verify_only:verify_disposable@127.0.0.1:15432/training_plan_verify' \
  ENV=test LLM_PROVIDER='' OPENAI_API_KEY='' LLM_API_KEY='' \
  JOHNNY_AUTH_REQUIRED=false JOHNNY_AUTH_ALLOW_HEADER_USER=true PYTHONPATH=backend \
  ./.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 18000
```

第一個 shell：
```bash
export API=http://127.0.0.1:18000
curl -fsS "$API/ready" | tee "$PG_EVIDENCE_DIR/ready.json"
curl -fsS -H 'X-Johnny-User-Id: local-user' "$API/api/v1/training-plans" > "$PG_EVIDENCE_DIR/plans-before.json"
curl -fsS -H 'X-Johnny-User-Id: local-user' "$API/api/v1/training-plans/regeneration-options" > "$PG_EVIDENCE_DIR/options-before.json"
for n in 1 2; do
  curl -fsS -H 'X-Johnny-User-Id: local-user' -H 'Content-Type: application/json' \
    -d '{"client_request_id":"pg-manual-001","plan_type":"maintenance"}' \
    "$API/api/v1/training-plans/regenerations" > "$PG_EVIDENCE_DIR/start-$n.json"
done
DATABASE_URL="$PG_VERIFY_URL" PYTHONPATH=backend ENV=test LLM_PROVIDER='' \
  ./.venv/bin/python scripts/agent_runtime.py --database-url "$PG_VERIFY_URL" work-drain --max-tasks 10 \
  2>&1 | tee "$PG_EVIDENCE_DIR/worker.txt"
curl -fsS -H 'X-Johnny-User-Id: local-user' "$API/api/v1/training-plans" > "$PG_EVIDENCE_DIR/plans-after.json"
curl -fsS -H 'X-Johnny-User-Id: local-user' "$API/api/v1/training-plans/regeneration-options" > "$PG_EVIDENCE_DIR/options-after.json"
```

比對兩次 `data.run.run_id` 相同、僅一項生成工作；從回應取出實際 `poll_url`，用同一使用者 header GET 該 URL 與其 `/steps`，保存 JSON。此本機案例排隊時必須為 `provider=local`、`model=deterministic-local-companion`；若不是則先停下來檢查 shell key 變數，勿執行 worker。預期 run／task completed，唯一新 active projection、舊版 superseded、`previous_plan_id` 指向前版、phase segments 與 workouts 完整涵蓋要求期間。worker 的 `processed` 或退出碼單獨不能證明成功，要查 run 狀態與持久化內容。真實 OpenAI 案例另依 [live runbook](training_plan_live_llm_verification.md) 使用新專用 DB，不能在本資料庫上追加付費樣本。

再以相同 request ID 重送應取得原 completed run；換 `pg-manual-002` 重送則當日 quota 用盡、`data.run` 為 null，不新增 plan／run。options 應顯示 limit=1、used=1、remaining=0、available=false 與 next_available_at。這不是預期 HTTP 429。以選手時區的**完成日**計費，不是 payload 的 quota_day。

## 6. 真 PostgreSQL 尚缺的 Harness／驗收清單

**下列不是現有可直接執行的 PostgreSQL pytest 命令。** 需另外建立暫存 harness（本次不新增），以 `create_session_factory(PG_VERIFY_URL)` 取代 SQLite fixture，使用 migration 建好的 schema，不以 `create_all` 代替。每案例用獨立使用者、固定時鐘、獨立交易；寫入後 commit，再用新 session 讀取驗收。只改環境 URL 不會改變 `sqlite_session_factory`。

| 案例 | 操作／故障注入 | 必須持久化驗收的結果 |
| --- | --- | --- |
| activation rollback | 搬用 `test_worker_commit_rolls_back_failed_activation_and_quota` 七個 failure 參數；呼叫真 `worker.work_one(session)`，外層 commit | 注入確實發生在保存後；舊 plan／workouts 完全相同且 active；無殘留新 plan；run、task failed；無 created_training_plan_id；今日 quota=0；前日成功 run 與 quota=1 保留 |
| Completion Repair 成功 | 搬用 `test_same_run_repair_rolls_back_first_save_before_success`，首次 createTrainingPlan 記錄後拋 ValueError | 被拒 plan ID 不存在；僅舊 superseded 與新 active；同 run completed 指向新 ID；只計一次 quota；今日仍取舊 workout |
| Today／歷史 | 搬用 `test_today_survives_successive_supersession_and_completion`，固定 2027-01-28；連續替換兩次，保留昨天 completed workout，再補今日完成 activity | `GET /api/v1/today?anchor_date=2027-01-28` 與 TodayWorkoutTool 結果一致；今日 ID／steps 不變；完成後 status=completed、matched_workout_id 正確；昨天 ID／狀態不變；隔日無課表不得捏造 |
| 前版防護 | 搬用 `test_today_does_not_resurrect_unrelated_or_expired_predecessors` 的 missing／foreign／cycle／draft／recovery_window | 今日皆無 workouts；不得跨使用者讀取、循環復活或越過恢復空窗 |
| 冪等與 terminal 重試 | 相同 ID、不同 ID、failed／completed 原 run、已有別的 in-flight run 分別重送 | 相同 ID 始終回原 run；不同 ID 於失敗後可新建；in-flight 共用同使用者 execution key；不重複 activation／扣額 |
| API 真併發 | 新使用者先建好並 commit；兩個獨立 client／session 用 barrier 同時 POST regenerations，測相同及不同 request ID；未 drain 前比較回應 | 同使用者至多一個 in-flight run／task，回應引用同 run；無重複 active projection；記錄等待時間與鎖衝突；SQLite 無法證明 PostgreSQL `FOR UPDATE` 行為 |
| worker 真併發 | 準備一個已 commit 的 queued task，兩個獨立 session 同時 work_one，各自 commit；另測過期 claim 回收 | 每輪 task 僅成功 claim／dispatch 一次、唯一新 active；不可先後呼叫冒充併發；目前 claim_next 使用條件 UPDATE，不是 SKIP LOCKED |
| quota／跨午夜 | 參照 unit 測試固定選手時區與完成時間；queued、started、failed、scheduled、無 created ID、有效 manual completed 分別測試 | 只有有效 manual completed 消耗完成日 quota；跨午夜算新日；scheduled 不扣；next_available_at 為選手當地次日午夜 |
| 背景排程與失敗隔離 | 搬用 worker scheduler 的 repeated checks、candidate DB failure、discovery failure、stale dates／race refresh 案例 | 重複檢查僅一個背景 run；單一候選失敗不污染其他候選交易；過期策略執行前重選有效賽事／開始日；recovery window 不提前生成 |

併發 harness 應設等待上限並保留雙方例外、SQL／交易時序；逾時、deadlock 或 IntegrityError 不得省略。每項逐一標記「未執行／通過／失敗」，不能以單一 repository 測試代替這些結論。

## 7. 原始碼依據、證據與清理

- 已核對：`AGENTS.md`、`docs/agents/*.md`、`CONTEXT.md`、`docs/adr/0001-deterministic-training-plan-skeletons.md`、`docs/manual_test_runbook.md`、`Makefile`、`docker-compose.yml`、`backend/.env.example`。
- DB 設定／測試：`backend/alembic.ini`、`backend/migrations/env.py`、`backend/tests/conftest.py`、`backend/tests/integration/database/test_postgresql_persistence.py`。conftest 的 SQLite fixture 是硬編碼，非 URL 切換。
- 行為依據：`backend/tests/integration/application/test_stage7_activation_repairs.py`、`backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`、`backend/tests/unit/test_training_plan_regeneration.py`；前兩者為 SQLite integration，後者使用替身，均不是 PostgreSQL 併發證據。
- 命令／API 依據：`scripts/agent_runtime.py`、`scripts/seed_demo_data.py`、`backend/src/api/dependencies.py`、`backend/src/api/routes/{training_plan_regeneration,today}.py`、`backend/src/api/schemas/training_plan_regeneration.py`、`backend/src/application/training_plan_regeneration.py`、database 的 session／models／training_plan_repository／agent_task_queue。LLM settings 不接受 `LLM_PROVIDER=local`；空白值使用 deterministic gateway。
- 保存 commit、套件版本、Docker inspect／image ID、唯讀 DB identity、migration revisions、pytest JUnit／完整輸出、API 前後 JSON、run／task／plan／workout IDs、故障注入與交易紀錄。附時間／選手時區、每項結果及未執行原因；不得保存真實金鑰或使用者資料。
- 本文命令已對照原始碼，尚未實跑；容器啟動、當前環境依賴、migration／API 結果及所有 PostgreSQL harness 案例仍待操作者驗證。

停止第二個 shell 的專用 uvicorn（Ctrl+C）；先保存證據，再以**本次建立的容器 ID**清理。不要刪除任何其他容器或 volume。

```bash
test "$(docker inspect -f '{{index .Config.Labels "johnny.purpose"}}' "$PG_VERIFY_CID")" = training-plan-pg-verification
test "$(docker inspect -f '{{.Name}}' "$PG_VERIFY_CID")" = /johnny-training-plan-pg16-verification
docker logs "$PG_VERIFY_CID" > "$PG_EVIDENCE_DIR/postgres.log" 2>&1
docker rm -f "$PG_VERIFY_CID"
printf '證據保留於 %s\n' "$PG_EVIDENCE_DIR"
unset DATABASE_URL JOHNNY_TEST_DATABASE_URL PG_VERIFY_URL PG_VERIFY_CONTAINER PG_VERIFY_CID
```

專用容器採 tmpfs，清理不需要 `docker volume rm`。文件索引與其他整理由控制者處理；本文件不要求提交 commit。
