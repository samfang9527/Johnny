# Workout Advice / Daily Review 完整改善評估

日期：2026-10-22。狀態：研究與設計建議，尚未實作或執行資料庫遷移。

## 目標與範圍

讓 Workout Advice 回答「依今天恢復、近期實際訓練與今日課表，我該如何執行」，讓 Daily Review 回答「這堂課達成了什麼、差異有什麼意義、下次如何做」。分段取得、歷史資料回填、資料模型遷移、分析、LLM、fallback、前端，以及避免重複產生，全部屬於同一完整改善的交付範圍。

使用者已明確要求納入分段與 migration。本文件建議最近 28 個當地日期作為首次活動明細回填範圍；這是可調整的工程預設，不是經驗證的生理分析窗口。七日 Execution Score 的日期與定義維持原有版本。

## 已確認的現況

- `backend/requirements/base.txt` 固定 `garminconnect==0.3.11`，現有 adapter 的 activities 路徑只呼叫活動列表。
- `ActivityModel` 保存活動識別、日期、總距離、總時間與 `provider_summary`，沒有分段或時間序列的獨立模型。Repository 會重建 summary，不適合把大量明細偷偷塞進既有欄位。
- `WorkoutStep` 支援 Repeat Block、時間／距離及 Target；Prescription Snapshot 已保存當時有效的課表。新分析應重用這些歷史處方，不以今日課表反推過去。
- `GenerateWorkoutAdviceHandler` 仍是規則判斷，沒有呼叫 LLM gateway；目前工作目錄的恢復改善加入昨／今健康資料及規則，輸出仍把數字拼成文字。
- `GenerateTrainingReviewHandler` 先產生事實與分數，再在有完成比較且 gateway 存在時請 LLM 補一句；限制 160 字、不得換行，失敗直接略過。這個契約不足以提供有層次的分析。
- `JohnnyPage.vue` 直接顯示 guidance／narrative，大段主文與分數重複；Today 與歷史頁也依賴舊字串。
- `CoachingRefreshService` 目前依 changed_dates 更新所有涵蓋該日期的歷史回顧；每個 evidence revision 使用不同修正工作 key。新增逐活動明細同步若沿用此策略，會產生更多工作。

原始碼入口：

- [Garmin adapter](../../backend/src/infrastructure/integrations/garminconnect_adapter.py)
- [活動儲存](../../backend/src/infrastructure/database/activity_repository.py)
- [Workout Advice](../../backend/src/application/workout_advice_generation.py)
- [Daily Review](../../backend/src/application/training_review_generation.py)
- [更新觸發](../../backend/src/application/coaching_refresh.py)
- [Execution Score](../../backend/src/domain/execution_score.py)
- [Johnny UI](../../frontend/src/pages/JohnnyPage.vue)

## 取得資料的路線

詳細來源、方法與限制見 [Garmin 可行性研究](2026-10-22-garmin-activity-detail-feasibility.md)。目前確認的是 pinned SDK 有這些方法；本次未對使用者帳戶做 authenticated live probe，不能宣稱使用者每堂活動都已有完整分段。

| 路線 | 優點 | 限制與建議 |
| --- | --- | --- |
| 擴充目前 Connect adapter | 可沿用目前連線及 activity ID；SDK 已有細節方法 | 建議主路線。非官方整合，需容忍欄位變動、限流、不同裝置與活動缺欄位 |
| 轉官方 Garmin developer API | 有正式產品與授權流程 | 需獨立確認方案、權限與歷史資料能力；現有 Connect credentials 不能直接替換，不能假設可回填所有歷史 |
| 取得原始活動檔並解析 FIT | 可補足圖表明細可能缺失的 records、laps、timer events | 納入本次完整範圍中的補充路徑；只在 JSON 明細不足且有原始檔時使用，增加 decoder、格式與儲存管理成本 |

建議取得順序：activity summary → splits → 視資料需要取得 typed splits／split summaries → HR time-in-zones → details → 必要時 original FIT。每種資源有獨立完成狀態，不為每堂活動無條件呼叫所有 endpoint。

`get_activity_details` 有 `maxchart` / `maxpoly` 參數。必須確認降採樣與時間覆蓋，不能把 chart points 當成完整逐秒記錄。`typed_splits` 名稱也不保證含暖身／主課語意。

SDK 也提供 `parse_activity_detail_metrics`；解析時依 `metricDescriptors` 的索引與 key 對應通道，不能硬編碼每個陣列位置。這個 helper 不是單位正規化器，單位與缺值仍由 adapter 驗證。來自 splits、typed splits、FIT 的重疊分段是同一活動的不同來源表示，分析必須選定來源與優先序，不能重複累加時間或距離。

第一個驗收關卡是小批實際樣本：一般有氧、自動分圈、結構化間歇、含暫停活動；帳戶若沒有某類，標示實帳未驗證並以去識別 fixture 覆蓋。記錄欄位、單位、缺值、時間覆蓋、點數、回應體大小及延遲，不記錄 token 或定位軌跡。probe 不建立 advice/review、不寫課表。

## 資料模型與 migration

建議以 additive Alembic migration 新增下列模型，保留既有 Activity、Prescription Snapshot、配對與 review revision 的識別及資料。

| 模型 | 內容與責任 |
| --- | --- |
| `activity_detail_fetches` | 每活動／資源的同步狀態、last success、retry、錯誤類別、批次 ID、current snapshot pointer；失敗不覆蓋最後可用內容 |
| `activity_detail_snapshots` | 不可變、經允許欄位篩選的來源內容，source/resource/schema version、semantic hash、fetched_at、coverage／sampling 說明 |
| `activity_segments` | snapshot 下的 lap／typed segment：原始索引、來源種類、start/end、timer/elapsed 時間、距離、平均／最高 HR、配速及可用性；未知型態保留 unknown |
| `activity_sample_chunks` | 分塊的必要時間序列：時間、距離／速度、HR、必要時海拔；記錄單位、資料密度、缺口、pause 訊號，不預設收集經緯度 |
| `activity_execution_analyses` | 明細 snapshot + Prescription Snapshot + baseline/zone evidence + algorithm version 的確定性分析結果及依據；相同輸入可重算重現 |

資料庫先沿用目前 SQLAlchemy JSON 與 PostgreSQL，避免為首批明細另起儲存服務。先以樣本測量實際 bytes/activity，再計算「活動數 × 平均 bytes × 保留版本數」的容量。大量序列分塊；原始 FIT 預設短期處理後清除，若需要長期留存則以獨立受控 blob 儲存，不塞入 review payload。保留的是能重現分析的必要 normalized evidence。

所有模型以 user/connection/activity 明確界定擁有者；snapshot 唯一鍵包含活動、資源、schema version、semantic hash。不同活動的相同內容不可合併。內容 hash 排除 fetched_at、工作 ID 等操作欄位；更正內容建立新 snapshot，不改寫舊分析依據。

Migration 本身只建 schema 和必要索引，不進行 Garmin 網路呼叫或長時間回填。獨立 backfill command 支援 dry-run、日期範圍、checkpoint、pause/resume、限速與失敗報告；先處理最新已完成活動及最近七日，再完成建議 28 日範圍。沒有 provider activity ID 的手動活動保持 summary-only。

部署順序：新增 schema → 支援雙讀的新 API／worker → 啟用 detail ingestion 與 backfill → 驗證分析 → 啟用新呈現。所有舊 worker 應 drain 並替換，工作 payload 帶契約版本，不支援者不得接單。回滾以 feature flag 恢復舊讀取與停用新 producer；保留新表及歷史證據，不靠破壞性 downgrade 回滾。

## 同步、完整度與重複觸發

活動列表完整度與活動明細完整度分開。明細 pending／partial／unsupported／failed，不表示活動未完成或應扣分；失敗時不能把既有明細當空陣列覆蓋。

沿用現有 durable task queue，細節擷取在可重試的活動工作執行。新／修改活動觸發抓取，另有有限次近期資料再確認，以處理來源延遲補齊而 summary 不變的情況。按連線限併發；429、暫時錯誤退避；401/403 與不支援分別處理，不假設 SDK 有公開固定額度。

每次明確同步請求建立可關閉的 batch。批次中的必要明細工作完成，或到達有設定的 deadline 後，再形成一次一致的分析 evidence manifest。不要讓每個 lap、每個 endpoint 各自呼叫 `record_change`。

建議同時調整 Daily Review 修正政策：

1. 同一批資料只自動更新最新已發布且受影響的回顧；較早的受影響日期標記「資料已更新」，在明確重算時更新。這是對現有「自動修正每個受影響歷史日期」的產品行為變更。
2. 每個 review slot 同時至多一個待處理工作，新的變更合併 desired fingerprint；執行中如 evidence 改變，舊輸出不得發布為 current，完成後至多排一個承接最新輸入的工作。
3. 去重 key 使用 slot + 分析輸入 fingerprint + 分析／prompt 版本；不是僅使用全域遞增 revision。日期、處方、分段、健康、配對、coverage 等真正被使用的依據納入 manifest。
4. 生成工作只讀 committed evidence，不反向啟動 provider sync。Workout Advice 維持使用者請求產生；新證據只使相關建議／待接受 Recommendation 失效。
5. 批次截止後若真的有新資料到達，可以有一次後續修正；驗收目標是消除相同有效輸入的重跑，不宣稱未來任何真實變更都永不再生成。

歷史回顧的 freshness 必須在歷史頁可見。若產品希望仍自動重算所有歷史回顧，應作為另一個明確的批次重算操作，不能和使用者取得今日建議混在一起。

## 確定性分析與 LLM 的分工

先辨識活動與課表是否可靠配對，再把 Repeat Block 展開成穩定 step path。來源有可信 workout-step 關聯時優先使用；只有 lap 時保留 lap 身分。由時間／距離推導的對應標示 estimated 與理由，模糊時不硬配。跨多筆活動的 session 保留 pause/gap 邊界，不直接把錄製片段串成連續主課。

| 證據層級 | 可提供的分析 | 不能直接下的結論 |
| --- | --- | --- |
| 整場總量 | 計畫與實際量差、近期量的分布 | 多出的時間位於主課或收操；整段強度是否符合 |
| 分圈摘要 | 各 lap 的配速／HR 變化、圈間一致性 | lap 等於 Workout Step；平均 HR 代表整圈都在某區間 |
| 可信 step 對應 | 暖身／工作／恢復／收操分別的量差、組數與目標比較 | 未測到的主觀感受或生理恢復因果 |
| 充分時間序列與有效 Target | 按有效時間加權的目標區間時間、段內變化、pause-aware 比較 | 用降採樣點數比例冒充精確秒數；缺失值補成正常 |

時間語意區分 elapsed、timer、moving；配速統一單位，排除 pause 與缺值；HR 區間需確認活動當時邊界，不以今天設定冒充歷史設定。不能確認區間定義時降級比較。RPE 沒有使用者回報即未知。

心率隨時間增加可描述為觀察，但是否源自疲勞、天氣、坡度或補水不能由 LLM 斷言。將生理因果評估與 Execution Score 分開；此文件不提出新的醫療／訓練風險閾值。

LLM 接收後端算好的有限 `facts/findings`、可用 Target、依據引用與限制，產生「結論 → 意義 → 行動」。不傳全部 samples，也不把 Garmin 活動名稱或 Coach Note 當指令。數字、分數與課表變更由後端擁有；LLM 的引用必須可解析到 evidence，所有數值引用使用已驗證 fact ID，避免自行發明。

## 兩個功能的內容契約

共同輸出新增 `schema_version`、`headline`、`summary`、`findings[]`、`actions[]`、`limitations[]`、`evidence_refs[]`、`analysis_mode`、`fallback_reason`、`input_fingerprint` 與模型／prompt／分析版本。findings 包含 observation、interpretation、evidence_refs；action 分為執行提醒與需接受的 Recommendation reference。欄位有長度及項目上限，後端驗證 JSON 結構、引用、數字與允許行動。

Workout Advice 的輸入：今日 canonical workout/steps、近期可比活動的 execution analyses、昨／今恢復資料與各自日期／完整度、Athlete Baseline、使用者限制、鄰近課表。健康指標採各自 freshness，不將昨晚睡眠與今天尚未完成的壓力日平均誤當同一時間點；晚到的今天資料不應無條件讓完整昨日訊號消失。

Workout Advice 必須區分無計畫、未排課、明確休息日、今天已完成、可執行、需調整與證據不足。首頁給一句今日重點，下面最多三條如何執行與一至兩條原因。規則限定可提議的變更；涉及 canonical workout 的數字／步驟修改只走原有 Recommendation 接受流程，LLM 不能用文字繞過。

Daily Review 使用昨日活動對照當時 Prescription Snapshot，七日視窗補充趨勢；如使用更長趨勢，清楚標示期間。先說最有意義的執行情況與影響，再給下一次可做的調整，沒有分段證據就明確縮小結論。未完成、無課表活動、配對待確認也要有專用內容，不只在 completed 分支才分析。

對「35 分鐘跑成 44 分鐘」：總量是約增加 26%，但這不能單獨判定影響。若可靠分段顯示增加在收操，應說明主課執行與延長收操的區別；若在工作段，應說明主課量的差異；兩者均只能作證據支持的解讀，不能保證恢復沒有影響。此例是條件式說明，不是對使用者該次跑步的實際判定。

## Fallback 與品質驗證

使用同一份 facts/findings 建立規則版結構化內容。`analysis_mode=rules` 對使用者標示「基本建議／基本回顧」；有可靠分段時依然可以指出段落差異，不退回一整段數字報表。若只有摘要，明說目前只能確認總量與無法判斷的部分，提供適當下一步。

模型 timeout、格式錯誤、無效引用、provider 未啟用等原因分開記錄；有限重試後 fallback。模型失敗與資料缺少是兩個獨立維度：LLM 成功不代表證據完整，LLM 失敗也不代表分析事實不存在。產生失敗保留上次結果與其 freshness，不能把昨天的建議當成今天建議。

評估 fixtures 覆蓋：正常執行、收操延長、工作段延長、間歇組數不足、自動 lap 無 step 關聯、pause、降採樣、缺 HR、歷史處方不確定、只有昨日恢復、今日健康局部更新、多活動 session、未配對、模型錯誤。驗收不只檢查 JSON，還檢查是否解釋意義、是否有可行下一步、是否避免超出證據的推論。

## Execution Score

保留 `execution-v1`：完成率與量符合度各占一半；每堂量符合度為 `min(actual/planned, planned/actual)`，確認未完成為 0，最後對合格堂數平均並四捨五入。一般課表優先時間，race 使用距離；資料／處方／配對不確定則給具體 null reason。

分段品質分析與這個分數並列，不偷偷把 HR 或分段強度加入舊分數。44/35 的量符合度約為 79.5%，只表示偏離原定訓練量，不能解讀為這堂課品質只有 79.5%。七日得分還含其他課表及完成率。這是 UI 必須說清楚的區別。

## 前端與跨頁遷移

沿用 DESIGN.md 深綠連續畫布、薄荷重點與細分隔線。主文用正常中文字重、短段落，只有結論強調；不把所有內容做成同樣大小的卡片。

- 今日建議：結論 → 如何執行 → 為什麼 → 展開依據。原始 sleep/HRV/stress/Body Battery 數值留在依據或連至「今日／資料」。
- 訓練回顧：結論 → 最重要的 1–3 個發現及意義 → 下次怎麼做 → 展開分段比較。可信 step 對應才呈現暖身／主課／恢復／收操，否則顯示來源 lap。
- 分段比較使用有名稱與單位的計畫／實際列；mobile 直向排列，圖表如加入需有文字／表格替代。未知、未配對、推估必須有文字標示。
- 七日分數放在次要獨立區，只顯示一次，展開顯示計算及逐堂紀錄；不可占據解讀主文。
- 沒有待接受調整時，縮成一行狀態；有 Recommendation 時保留優先呈現及接受前比較。
- 新分析生成中保留舊結果；分開顯示取得分段、資料不足、基本分析、分析失敗與過期，避免泛用「同步失敗」。
- Today 只消費同一份短摘要與連結；歷史頁顯示對應版本、日期、模式與 freshness，不重複全文。
- API 保留舊 `guidance/narrative` 相容摘要，新 UI 優先讀結構化欄位。舊 revision 維持舊字串 renderer，不能假裝已有新分析或直接拆句製造 findings。

## 完整交付順序與驗收

這些是同一目標內的依賴順序，不把分段當成可有可無的未來功能。

1. **實帳資料驗證**：確認各資源實際可取欄位、單位、完整度與 FIT 補充必要性，建立去識別契約 fixtures。
2. **Schema 與同步遷移**：新增模型、批次抓取、重試、內容去重、獨立 backfill；現有 summary 與人工配對不變。
3. **分析**：歷史處方對應、分段／樣本 coverage、確定性 findings 與 evidence manifest；不可靠時誠實降級。
4. **兩條生成流程**：Workout Advice 實際接 LLM、Daily Review 改結構化分析、共同 validation/fallback、版本與用量可觀察。
5. **API／前端**：Johnny、Today、History、Data coverage 一致更新；桌機與手機、鍵盤、長中文、缺資料、過期狀態驗證。
6. **切換與回填驗收**：替換舊 worker、完成設定日期的 backfill；同批多活動／多 endpoint 不重複生成，相同輸入重跑不產生新內容版本；真實晚到資料最多合併成必要的後續工作。

測試涵蓋 PostgreSQL 實際 Alembic 升級與舊資料兼容、task 併發／重試／發布競態、provider schema、時間與單位、step 對應、evidence invalidation、LLM 格式與引用、Recommendation 接受時的有效性，以及前端新舊 payload。SQLite 測試不足以取代 PostgreSQL migration／concurrency 驗證。

本次確認可行的整合入口與完整範圍；未執行 live provider probe、migration、回填或產品程式修改。實際帳戶可用欄位、資料密度與來源穩定性仍須在第 1 關取得證據，不能用 SDK 方法存在取代驗證。
