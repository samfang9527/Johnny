---
version: alpha
name: "Johnny"
description: "Chinese-first AI sports companion interface built around daily training decisions, recovery evidence, and human-approved recommendations."
colors:
  primary: "#83B7A5"
  track-night: "#171B1A"
  pit-black: "#111514"
  rubber-gray: "#2F3430"
  lane-chalk: "#F6EFE4"
  muted-chalk: "#C8C0B3"
  recovery-blue: "#83B7A5"
  split-amber: "#E8B86D"
  effort-red: "#B85A50"
  easy-green: "#8FB879"
  line-white: "#FFFFFF"
typography:
  body:
    fontFamily: "'IBM Plex Sans', 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', system-ui, sans-serif"
    fontSize: "1rem"
    lineHeight: "1.65"
  display:
    fontFamily: "'IBM Plex Sans Condensed', 'Noto Sans TC', 'PingFang TC', system-ui, sans-serif"
    fontSize: "2.75rem"
    lineHeight: "1.08"
  data:
    fontFamily: "'IBM Plex Mono', 'Noto Sans Mono CJK TC', 'SFMono-Regular', ui-monospace, monospace"
    fontSize: "0.9375rem"
    lineHeight: "1.45"
rounded:
  DEFAULT: "0.5rem"
  sm: "0.25rem"
  md: "0.5rem"
  lg: "0.75rem"
  full: "999px"
spacing:
  page-max: "76rem"
  shell-gap: "1.5rem"
  section-gap: "2rem"
  card-pad: "1.25rem"
  control-y: "0.75rem"
  control-x: "1rem"
components:
  app-shell:
    backgroundColor: "{colors.track-night}"
    textColor: "{colors.lane-chalk}"
  top-nav:
    backgroundColor: "{colors.pit-black}"
    textColor: "{colors.muted-chalk}"
    height: "4rem"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.pit-black}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-neutral:
    backgroundColor: "{colors.rubber-gray}"
    textColor: "{colors.lane-chalk}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-warning:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.pit-black}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-danger:
    backgroundColor: "{colors.effort-red}"
    textColor: "{colors.line-white}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  card:
    backgroundColor: "{colors.rubber-gray}"
    textColor: "{colors.lane-chalk}"
    rounded: "{rounded.md}"
    padding: "{spacing.card-pad}"
  recommendation-card:
    backgroundColor: "{colors.pit-black}"
    textColor: "{colors.lane-chalk}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card-pad}"
  evidence-list:
    textColor: "{colors.muted-chalk}"
    typography: "{typography.data}"
  provider-card:
    backgroundColor: "{colors.rubber-gray}"
    textColor: "{colors.lane-chalk}"
    rounded: "{rounded.md}"
    padding: "{spacing.card-pad}"
  status-success:
    backgroundColor: "{colors.easy-green}"
    textColor: "{colors.pit-black}"
    rounded: "{rounded.full}"
  status-info:
    backgroundColor: "{colors.recovery-blue}"
    textColor: "{colors.pit-black}"
    rounded: "{rounded.full}"
  status-warning:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.pit-black}"
    rounded: "{rounded.full}"
  status-danger:
    backgroundColor: "{colors.effort-red}"
    textColor: "{colors.line-white}"
    rounded: "{rounded.full}"
---

# Johnny Design System

## Overview

### Creative North Star

Johnny 的視覺世界來自「跑者每天訓練前看的狀態板」：夜訓後的暖色低光、跑道線的清楚分隔、手錶與訓練日誌上的數字節奏。它不應該像一般 AI 聊天工具，也不應該像健身社群 App。Johnny 的第一印象是：今天要不要照課表跑，證據是什麼，使用者要做哪個決定。

### Product context and register

- **Audience and primary job:** 以繁體中文為主要介面的耐力跑者、馬拉松訓練者與長期訓練中的使用者。主要工作是每天快速理解訓練、恢復、風險與 Johnny 的建議，並決定是否接受調整。
- **Target market(s) and evidence:** MVP 以中文使用者為主要內容策略，但產品資料結構與 provider 名稱保持國際化。需求依據 `docs/Johnny_AI_Sports_Companion_Project_Concept.md`、Today/Calendar OpenSpec、Conversation/Inbox OpenSpec，以及既有 FastAPI route contract。
- **Locale(s) and language policy:** UI copy、錯誤、空狀態、按鈕、輔助文字優先使用繁體中文 `zh-TW`。Provider 名稱、活動來源、API 狀態可保留英文專名，例如 Garmin、Strava、Apple Health。數字與日期使用 `zh-TW` 顯示，時間依使用者 profile timezone。
- **Usage scene:** 手機與筆電都重要。使用者可能在早上、跑前、跑後或臨時調整行程時打開 Johnny。資訊密度應該比行銷頁高，但每個畫面只能服務一個主要決策。
- **Register:** Product-first。沒有行銷首頁；登入後第一畫面是「今日」。品牌感放在系統節奏、資料呈現與語氣，不放在大型插畫或裝飾 hero。
- **Memorable signature:** `decision strip`。Agent 收件匣的推薦卡以「訊號 -> 證據 -> 建議 -> 決定」的橫向或縱向節奏呈現，像跑道分道線一樣引導使用者從原因走到行動。
- **Restraint:** 對話頁不能主導整個產品。Johnny 是能聊天的訓練夥伴，不是 ChatGPT clone。Today、Agent 收件匣、資料來源狀態必須比聊天輸入框更重要。
- **Anti-references:** 不做單色深藍 SaaS 儀表板、不做霓虹 AI chatbot、不做社群健身打卡牆、不做米色筆記本風。Johnny 可以更柔和溫暖，但仍然要像可判讀的訓練工具。
- **Token ownership/runtime mapping:** 本檔是 Johnny 前端視覺 source of truth。後續實作應將 frontmatter token 對應到 `frontend/src/styles.css` 的 CSS custom properties，再由 Vue components 透過語意 class 使用；不要在 component 內直接重複 hex 值。

## Colors

Johnny 採深色 product shell，但不是純黑。`track-night` 是主要背景，帶暖灰而不是冷藍；`pit-black` 用於較深的頂部列與沉浸式面板。`rubber-gray` 是卡片、表面和分隔線的基礎色，帶有跑道橡膠感但不生硬。

文字以 `lane-chalk` 作為主要文字，`muted-chalk` 作為次要標籤、說明與 disabled text。`line-white` 只保留給需要最大對比的圖標、焦點內線和少量高亮，不作為大面積背景。

語意色：

- `recovery-blue`: 恢復、睡眠、HRV、健康訊號。
- `split-amber`: 倒數、今天需要注意但不危急的事項、同步中狀態。
- `effort-red`: 過高訓練負荷、疲勞風險、同步失敗、破壞性或不可逆行動。
- `easy-green`: 已連接、已接受、完成、低風險狀態。

資料視覺化不要只靠色彩判斷。每個狀態都要同時有文字、圖標或標籤，例如 `偏低`、`同步失敗`、`已接受`。

## Typography

主要介面使用 `IBM Plex Sans` 搭配繁中 fallback `Noto Sans TC`、`PingFang TC`、`Microsoft JhengHei`。中文不使用 italic，避免產生不自然的字形傾斜。英文專名與 provider 名稱依原字母大小寫呈現。

數字、配速、日期、HRV、負荷、距離和狀態代碼使用 `IBM Plex Mono` 或等寬 fallback。這是 Johnny 的資料語氣：像跑錶、split table、訓練日誌。等寬字只用於資料與短標籤，不用於長篇中文說明。

Display 字體只用在頁面主標題、比賽名稱、倒數數字和 Today's decision，不在卡片內濫用大字。中文正文基準約 16px，line-height 1.65，保留足夠行距處理繁中、英文與數字混排。

Copy 原則：

- Button 使用明確動詞：`接受調整`、`保留原課表`、`討論原因`、`連接資料來源`。
- 狀態使用使用者看得懂的詞：`恢復偏低`、`同步中`、`缺少睡眠資料`。
- 錯誤不道歉，直接說明狀況與下一步：`Garmin 連接失敗。請檢查授權狀態後再試一次。`

## Layout

主架構是三個 product surface 加一個 setup surface，Conversation 暫時不在 production 導覽中：

- `今日`: daily decision cockpit，預設入口。
- `訓練安排`: 六個月時間視窗，顯示未來目標與接下來的課表。
- `Agent 收件匣`: Johnny 主動產生的推薦、警示、週報與待決策項目。
- `資料來源`: 連接 Garmin、Apple Health、Strava 等同步來源。

Desktop shell 使用頂部 navigation 搭配狀態列，品牌與導覽要在同一個 constrained shell 裡，不要各走各的路徑。內容最大寬度使用 `page-max`，核心 Today 區塊採 12 欄 grid：比賽、今日課表與恢復證據並列；窄螢幕改為單欄，順序固定為 race -> workout -> recovery -> inbox nudge。

Today top-row cards must stay visually balanced. Race, workout, and recovery cards should share comparable density and height. Recovery uses a compact summary with three signal chips; full evidence rows and unavailable-signal lists belong in Agent Inbox recommendation cards or other detailed decision contexts.

`decision strip` 在 desktop 可以橫向呈現，在 mobile 必須垂直堆疊且每一步保留同樣標籤。`訓練安排` 使用六個月卡片式時間視窗，顯示使用者設定的未來目標；課表列表作為時間脈絡，而不是主要頁面名稱。

資料來源頁使用 provider cards，但 cards 不應該像 marketplace。每張卡只回答三件事：是否連接、最近一次同步結果、Johnny 目前能使用哪些訊號。

## Elevation & Depth

Johnny 的層級主要靠 tonal layers、細邊線和資料分隔，不靠大量陰影。靜態卡片預設不使用 shadow；互動卡片 hover 可以提升邊線亮度或背景 tone。Modal、drawer、toast 可以使用單層陰影與更深 overlay，但不能模糊整個產品成裝飾背景。

Agent 收件匣的推薦卡應該比其他卡片更有層級：可以使用左側或上方 `split-amber` decision rail，搭配較厚邊線。Today 不顯示推薦卡，只提供前往 Agent 收件匣的安靜入口。

## Shapes

標準 radius 是 `0.5rem`。卡片和控制項可使用 `md` 或 `lg`，但不要使用過大的 pill card。Pill 只用在狀態 badge、provider status、短 filter chip。跑道線與資料表邊界保持清楚，有些區塊可以使用直線分隔來呼應 track lane。

圖標容器使用 8px radius，不使用圓形裝飾泡泡。焦點框應清楚可見，使用 `split-amber` 或 `recovery-blue`，並保留 2px offset。

## Components

### Foundational visual states

所有互動元件必須有 default、hover、focus-visible、active、disabled、busy 狀態。Busy 狀態不改變 button 尺寸；文字可替換為同寬短語，例如 `處理中`，並搭配 spinner 或進度點。

載入狀態以穩定幾何為先。Today 可以使用 section-level loading panel，不使用滿版 spinner。資料尚未連接時不要顯示空白圖表，改用明確空狀態：`連接資料來源後，Johnny 會用近期訓練、睡眠與 HRV 判斷恢復狀態。`

### Buttons and actions

Button 系統採 emphasis x intent：

- Primary solid: 畫面主要安全動作，例如 `接受調整`、`連接資料來源`。
- Neutral outline: 次要決策，例如 `保留原課表`、`稍後處理`。
- Ghost: 輕量 navigation 或 inspect action，例如 `查看證據`。
- Danger: 拒絕、移除連接、清除授權等高風險動作。一般畫面保持低 emphasis，確認 dialog 才使用高 emphasis danger。

Agent 收件匣 Recommendation actions 固定語彙：

- `接受調整`
- `保留課表`

推薦卡不顯示 `編輯調整` 或 `討論原因`。使用者要快速做「接受 Johnny 調整」或「保留原本課表」兩種決定。

### Navigation and data display

Top nav label 使用中文：`今日`、`訓練安排`、`Agent 收件匣`、`資料來源`。目前頁面以底線、底色或 lane rail 表示，不只靠顏色。

Evidence list 使用 data typography，包含來源、metric、value、summary。不可只顯示 Johnny 結論；證據應緊貼推薦。Unavailable signals 需要以安靜但可見的方式列出，例如 `缺少睡眠資料`、`尚未連接 HRV 來源`。Today recovery card 是例外：它只顯示 compact signal chips 和缺少訊號數量，避免三欄卡片高度失衡。

Calendar 以 workout row 為主，包含日期、workout type、purpose、distance 或 duration、status。窄螢幕使用 list，不使用會擠壓文字的月曆格。

### Forms and overlays

Conversation composer 使用多行 textarea，預設 `resize: none`，並保留 `送出` button 固定寬度。Enter 行為必須與中文 IME composition 相容；輸入中文選字時不可送出。

資料來源連接 form 初期只收 backend 目前需要的 provider、provider account id、credential secret ref。敏感欄位預設遮蔽，不把 credential value 放進 toast、URL、localStorage 或 log。

Dialog 使用 app-owned modal，不使用 browser `alert()`、`confirm()`、`prompt()`。移除 provider binding、拒絕重要推薦、清除 credential reference 等行為需要清楚說明對象與後果。

### Iconography

可使用 lucide-style outline icons。Stroke 以 1.75px 到 2px 為主，圖標只輔助標籤，不取代中文文字。允許 icon-only 的地方只限全域工具，例如關閉、返回、清除搜尋，且必須有繁中 accessible label 與 tooltip。

### Motion

Motion 要像訓練狀態更新，不像 AI 裝飾。推薦卡進入可使用一次短暫 rail reveal；狀態切換使用 120ms 到 180ms。不要讓背景持續浮動。Respect `prefers-reduced-motion`; reduced motion 下保留 opacity/instant state，不做位置動畫。

### Content and data visualization

Johnny 的語氣是「有根據的訓練夥伴」：直接、具體、避免過度情緒化。建議要短，證據要清楚，決策要明確。

資料格式：

- 距離：`8 km`
- 配速：`6:20-6:40 /km`
- 倒數：`16 天`
- HRV：`52 ms`，變化可顯示 `低於基準 18%`
- 睡眠：`5 小時 42 分`
- 訓練負荷：`7 日負荷 +21%`

圖表色彩最多使用 `recovery-blue`、`split-amber`、`effort-red`、`easy-green` 加上灰階。每個圖表都要有文字摘要，不讓顏色成為唯一解讀方式。

## Do's and Don'ts

- **Do:** 讓每個 Today 區塊回答「今天要做什麼決定」。
- **Do:** 把證據放在推薦旁邊，而不是藏在展開區或聊天訊息深處。
- **Do:** 在資料不足時明確顯示缺少哪些 signal，並引導使用者到 `資料來源`。
- **Do:** 保持繁中 UI copy 一致，provider 名稱才使用英文專名。
- **Don't:** 把 Johnny 做成只有聊天輸入框的 AI 工具。
- **Don't:** 用大面積漸層、發光 orb 或裝飾圖案製造「AI 感」。
- **Don't:** 在每個卡片都使用過大圓角和陰影；Johnny 應該像可判讀的訓練儀表，不是卡片拼貼。
- **Don't:** 在 recommendation actions 使用不同詞彙，例如同一件事有時叫 `套用`、有時叫 `接受`。使用者決策語言必須穩定。
