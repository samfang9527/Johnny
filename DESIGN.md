---
version: alpha
name: "Johnny"
description: "Chinese-first running companion with the approved dark Morning Start Line visual language on the Split Board structure."
colors:
  primary: "#BDE8C9"
  mint-track: "#17291E"
  mint-surface: "#1D3525"
  card-white: "#203727"
  deep-green: "#BDE8C9"
  lane-green: "#A0D3AD"
  soft-mint: "#315F3F"
  split-amber: "#EFBC76"
  rest-blue: "#A9CCE1"
  effort-red: "#E49286"
  ink-green: "#EAF5ED"
  muted-green: "#B5D2BD"
  line-mint: "#47664E"
  rail-mint: "#BDE8C9"
  rail-ink: "#163C29"
typography:
  body:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "1rem"
    lineHeight: "1.65"
  display:
    fontFamily: "'DM Sans', 'Noto Sans TC', sans-serif"
    fontSize: "2.5rem"
    lineHeight: "1.08"
  data:
    fontFamily: "'IBM Plex Mono', 'Noto Sans TC', monospace"
    fontSize: "0.9375rem"
    lineHeight: "1.45"
rounded:
  DEFAULT: "0.75rem"
  sm: "0.375rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.35rem"
  full: "999px"
spacing:
  page-max: "100%"
  app-column: "26rem"
  shell-gap: "1.25rem"
  section-gap: "1.6rem"
  card-pad: "1.1rem"
  control-y: "0.75rem"
  control-x: "1rem"
components:
  app-shell:
    backgroundColor: "{colors.mint-track}"
    textColor: "{colors.ink-green}"
  bottom-nav:
    backgroundColor: "{colors.rail-mint}"
    textColor: "{colors.rail-ink}"
  button-primary:
    backgroundColor: "{colors.deep-green}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-neutral:
    backgroundColor: "{colors.deep-green}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-warning:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-danger:
    backgroundColor: "{colors.effort-red}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  card:
    backgroundColor: "{colors.mint-track}"
    textColor: "{colors.ink-green}"
    rounded: "0"
    padding: "{spacing.card-pad}"
  today-decision-run:
    backgroundColor: "{colors.mint-track}"
    textColor: "{colors.deep-green}"
    rounded: "0"
    padding: "{spacing.card-pad}"
  today-decision-adjust:
    backgroundColor: "{colors.mint-track}"
    textColor: "{colors.split-amber}"
    rounded: "0"
    padding: "{spacing.card-pad}"
  today-decision-rest:
    backgroundColor: "{colors.mint-track}"
    textColor: "{colors.rest-blue}"
    rounded: "0"
    padding: "{spacing.card-pad}"
  evidence-chip:
    backgroundColor: "{colors.mint-track}"
    textColor: "{colors.ink-green}"
    rounded: "0"
  divider:
    backgroundColor: "{colors.line-mint}"
    textColor: "{colors.ink-green}"
  status-success:
    backgroundColor: "{colors.soft-mint}"
    textColor: "{colors.deep-green}"
    rounded: "{rounded.full}"
  status-info:
    backgroundColor: "{colors.rest-blue}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.full}"
  status-warning:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.full}"
  status-danger:
    backgroundColor: "{colors.effort-red}"
    textColor: "{colors.mint-track}"
    rounded: "{rounded.full}"
---

# Johnny Design System

## Overview

### Creative North Star

Johnny 的視覺世界是「每天站上起跑線前，身邊有一個懂你的跑步夥伴」。已選定的 Morning Start Line 示意以深綠連續畫布、薄荷色導覽 rail、細分隔線與清晰的大字建立辨識度；Split Board 把今日決策與實際課表放在同一平面並列，讓跑者先判斷，再看證據與下一步。薄荷綠、琥珀與休息藍分別標示 Run、Adjust 與 Rest；Completed 有獨立的完成語意。

Johnny 不應該像一般 SaaS dashboard，也不應該像聊天機器人。它的第一印象是：今天身體狀態如何、Johnny 建議 Run / Adjust / Rest、證據是什麼、下一步要做什麼。

Johnny 頁沿用深綠畫布與分隔線節奏，固定分成「每日回顧」和「今日課表建議」兩個可同時存在的區域。前者先顯示昨天、七日執行分數與逐堂紀錄；後者由跑者主動要求，顯示當日條件、建議與必要時的課表調整。待決定提案緊接回顧摘要，展示原課表與接受後的差異；明確接受前，Today 的正規課表不變。各區的 loading、錯誤、過期與產生時間獨立呈現，更新其中一區不能使另一區消失。Today 只取當日建議的一句摘要與 Johnny 連結，不複製完整回顧或對話介面。

### Product context and register

- **Audience and primary job:** 以繁體中文為主要介面的耐力跑者、馬拉松訓練者與長期訓練中的使用者。主要工作是每天快速理解訓練、恢復、風險與 Johnny 的建議，並決定今天要跑、調整或休息。
- **Register:** Product-first app experience. 沒有行銷首頁；登入後第一畫面是 `今日`。
- **Signature:** `Morning Start Line × Split Board`。Today 以「今日訓練」標題、右側日期與七格課表條起始；有下一場比賽時，在標題與課表條之間顯示精簡賽事資訊與倒數。今天那格高亮，點其他日期會在七格條下方就地預覽該日課表，明確點選「查看完整計畫」才進入 `計畫`；Today Decision 始終只代表今天。其下為同一平面的 Today Decision／今日課表雙欄、2–3 條判斷依據、最後一條計畫／下一堂與待決定項目的頁腳。各區以規則線相接，不能拆成獨立浮動卡片。無有效計畫時，未排定日期應顯示「待排」，不可捏造休息日。
- **Interaction loop:** Observe -> Understand -> Reason -> Recommend -> User Decision -> Act -> Learn.
- **Tone:** Johnny 像懂訓練的跑友：直接、會開一點跑者懂的玩笑，但不幼稚。Rest copy 可以像 `今天不要硬撐，跑鞋先放假。`
- **Anti-references:** 不做深色 AI chatbot、不做等寬數據牆、不做社群健身打卡牆、不做單調醫療健康儀表板、不做米色筆記本風。深色在這裡是訓練畫布，不是聊天氣泡介面。
- **Token ownership/runtime mapping:** 本檔是 Johnny 前端視覺 source of truth。實作應將 frontmatter token 對應到 `frontend/src/styles.css` 的 CSS custom properties，再由 Vue components 透過語意 class 使用；不要在 component 內直接重複 hex 值。

## Colors

Johnny 預設使用深綠畫布 `mint-track` 與薄荷色 rail `rail-mint`。`mint-surface`、`card-white` 和 `deep-green` 是保留給舊 class 的相容 token 名稱，實際值分別為深色層次與薄荷色重點色；不要從名稱推斷色相。文字主色使用 `ink-green`，次要文字使用 `muted-green`，分隔線使用 `line-mint`。選中的日期使用較亮綠色塊；整體不使用背景網格。

決策狀態色：

- `deep-green`: `我可以` / Run 的標題、primary safe action。
- `split-amber`: `不太對勁` / Adjust，代表需要調整但可恢復。
- `rest-blue`: `先收一下` / Rest，代表保護性休息，不是失敗。
- `effort-red`: 高風險、錯誤、傷痛警示、不可逆或破壞性動作。

狀態色用於文字或小面積標籤，不能將整張 Today 決策欄填滿。資料視覺化不要只靠色彩判斷；每個狀態都要同時有文字、標籤或 icon。

## Typography

主要介面使用 `Noto Sans TC`。品牌、拉丁字與顯示標題使用 `DM Sans` 搭配繁中 fallback `Noto Sans TC`。中文不使用 italic。

Display 字體用於頁面主標題、Today Decision、今日課表的 hero 標題、race countdown、phase title。Today 的決策與課表標題要明顯大於一般欄位；其他頁維持緊湊層級。

數字、配速、日期、HRV、負荷、距離和 signal coverage 使用 `IBM Plex Mono` 或等寬 fallback。等寬字只用於資料與短標籤，不用於長篇中文說明。

Copy 原則：

- State labels 可以有個性：`我可以`、`不太對勁`、`先收一下`。
- Buttons 使用真實目的地與明確動詞：開啟課表詳情用 `查看課表細節`，前往計畫用 `查看計畫`，前往 Johnny 待決定清單用 `查看待決定建議`。只有 Recommendation 提供 `接受調整`；目前沒有跑步追蹤或記錄休息功能。
- Memory insight 不直白暴露資料庫感：使用 `依照你過去的恢復模式，今天建議保守。`
- 錯誤不道歉，直接說明狀況與下一步：`Garmin 連接失敗。請檢查授權狀態後再試一次。`

## Layout

主架構是五個 product surfaces：

- `今日`: start-line cockpit，預設入口。
- `計畫`: current plan, inclusive training journey, and weekly schedule。The current plan reveals its included races on demand; non-race athletes still see a useful training cycle.
- `Johnny`: pending recommendations first, weekly review/check-ins below. Conversation remains hidden until public-ready.
- `運動員`: Athlete Baseline snapshot first, profile/settings below. Athlete Memory is not a browsable frontend page.
- `資料`: Signal Coverage first, provider connection details below.

Mobile 使用固定底部 navigation，label 為 `今日`、`計畫`、`Johnny`、`運動員`、`資料`。Desktop 使用 compact side rail。兩者都以文字與形狀標示目前頁面，並為底部安全區留足內容空間。

Today mobile follows the Split Board reading order:

1. 標題、athlete-local 日期、可用時的下一場比賽摘要與七格課表條；Plan Week 有資料時以其七日邊界為準，否則顯示當前日曆週。
2. Today Decision, then actual planned workout.
3. Two or three aligned evidence rows and the ruled plan/next-workout/pending footer, then expandable Daily Advice detail.
4. Session reviews; do not repeat the race summary below the board.

Today desktop places decision and workout in one uninterrupted primary split with a one-pixel vertical rule. Supporting evidence and the plan/next-workout/pending footer continue on the same canvas beneath it. The product surface fills the desktop width between the side rail and balanced outer gutters. The seven-day strip shows actual scheduled workouts from the current Plan Version. The next-race line names the saved upcoming race, distance, date and athlete-local countdown without implying it is part of the current Plan Version; it disappears when no future race exists.

`計畫` begins with one current-plan section: the current phase and focus, this week's dates, the next workout, and the training journey (base, build, peak, taper, and goal week). An inline disclosure reveals races included in this plan, separating the target race from supporting races and from saved goals that are not in the plan snapshot. Goal management and regeneration live inside that disclosure; without an active plan, a visible action starts plan generation. Weekly schedule sits underneath as execution detail; a date chosen from Today is focused there with its workout or a truthful rest/pending state. Do not repeat phase details in another section.

`資料` begins with Signal Coverage, e.g. `Johnny 已有 4/6 個訓練訊號`。The six MVP signals are activity, sleep, HRV, resting heart rate, training load, and athlete baseline.

## Elevation & Depth

頁面以共同的深綠表面與細分隔線組織內容。一般資訊區、課表列、Recommendation 與 Signal Coverage 不使用白色浮動卡片或陰影；以字級、留白與規則線建立層級。Today 的決策與課表雙欄是第一焦點。

Interactive rows use border and background shifts for hover/focus. Modal、drawer、toast 可以使用有方向的陰影與較深獨立表面，以清楚區分它們和頁面；不使用裝飾性 halo。

## Shapes

頁面區段與列以直線邊緣呈現。控制項 radius 為 `0.55–0.75rem`；dialog 等浮層可較圓。Pill 只用於 status badge、signal chip、短 filter chip。

Track/race identity should come from lane lines, phase segments, data rhythm, and start-line hierarchy, not from decorative blobs or unrelated gradients.

## Components

### Today Decision Card

Today Decision owns the Run / Adjust / Rest / Completed moment:

- `我可以`: deep green emphasis, truthful link to workout details or Plan.
- `不太對勁`: amber emphasis, read-only execution guidance; plan changes remain in Johnny.
- `先收一下`: rest blue emphasis, with evidence and relevant next step.
- `今天已完成`: completion treatment distinct from Rest.

The decision side shows Johnny's voice and one clear next action. The adjacent workout side shows the planned session without repeating it in the decision. Evidence follows the split; Athlete Memory only appears as a relevant, non-browsable insight.

### Evidence and Signal Coverage

Evidence chips show label, value, and short context. Today shows only the strongest 2-3 current signals plus one memory insight when useful. Full evidence belongs in Johnny recommendation cards.

Signal Coverage is a first-class summary on `資料`: activity, sleep, HRV, resting HR, training load, athlete baseline. Provider cards explain which signals they contribute and the last sync result.

### Navigation

Navigation labels are Chinese-first: `今日`、`計畫`、`Johnny`、`運動員`、`資料`。Conversation is hidden from production navigation until public-ready. Current page must be indicated by shape/text/icon, not color alone.

### Forms and overlays

Athlete profile/settings remain app-owned Vue forms with `novalidate`, inline validation, stable busy buttons, and no browser `alert()` / `confirm()` / `prompt()`。Sensitive provider fields stay masked by default and never appear in toast、URL、localStorage 或 log。

### Iconography

Use lucide-style outline icons if an icon library is introduced; otherwise keep icon use minimal and text-led. Icon-only controls require Traditional Chinese accessible labels and tooltips.

### Motion

Motion should feel like a training state change: short, useful, and stateful. Control and selection feedback uses a shared 140 ms rhythm; inline previews, native disclosures, and overlays enter within 240 ms and leave within 180 ms. The seven-day strip's selected state responds first, then the preview reveals beneath it. Run/Adjust/Rest may use a quick tone shift. Page-to-page transitions are a separate future layer. Respect `prefers-reduced-motion`; no continuous floating backgrounds.

### Data visualization

The seven-day schedule strip is the weekly view on Today. Other dates open a compact inline workout preview beneath the strip; an explicit action opens `計畫`. Clicking today closes the preview and returns to the initial Today view. The Today Decision remains tied to today. Do not present fixture distances as completed activity. A future history chart needs real completed sessions, a clearly named measure and period, and text equivalents for every visual value.

## Do's and Don'ts

- **Do:** Make Today answer `我今天要跑、調整，還是休息？`
- **Do:** Use the mint rail, dark continuous canvas, seven-day strip and ruled Split Board as Johnny's memorable first impression.
- **Do:** Keep evidence visible when Johnny suggests Adjust or Rest.
- **Do:** Let Athlete Memory appear only through relevant recommendation/conversation wording, never as a browsable memory database.
- **Do:** Put Signal Coverage before provider admin details on `資料`.
- **Don't:** Replace the ruled canvas with independent white cards, shadows, background grids or a full-width colored decision tile.
- **Don't:** Make Johnny a mascot-heavy or childish character.
- **Don't:** Turn the app into a generic dashboard grid of equal cards.
- **Don't:** Hide decision evidence behind chat.
- **Don't:** Use `我不行` for rest state; rest should feel strategic, not like failure.
