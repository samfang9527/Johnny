---
version: alpha
name: "Johnny"
description: "Chinese-first AI running companion interface built around a light mint start-line cockpit, daily Run/Adjust/Rest decisions, athlete baselines, signal coverage, and human-approved recommendations."
colors:
  primary: "#0F4A32"
  mint-track: "#EEF9F1"
  mint-surface: "#F8FCF8"
  card-white: "#FFFFFF"
  deep-green: "#0F4A32"
  lane-green: "#2D7A58"
  soft-mint: "#BFE8D2"
  split-amber: "#D89422"
  rest-blue: "#6C9ECF"
  effort-red: "#B85A50"
  ink-green: "#14382A"
  muted-green: "#5F7B6B"
  line-mint: "#D9ECDD"
typography:
  body:
    fontFamily: "'IBM Plex Sans', 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', system-ui, sans-serif"
    fontSize: "1rem"
    lineHeight: "1.65"
  display:
    fontFamily: "'IBM Plex Sans Condensed', 'Noto Sans TC', 'PingFang TC', system-ui, sans-serif"
    fontSize: "2.5rem"
    lineHeight: "1.08"
  data:
    fontFamily: "'IBM Plex Mono', 'Noto Sans Mono CJK TC', 'SFMono-Regular', ui-monospace, monospace"
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
  page-max: "72rem"
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
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.muted-green}"
  button-primary:
    backgroundColor: "{colors.deep-green}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-neutral:
    backgroundColor: "{colors.line-mint}"
    textColor: "{colors.deep-green}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-warning:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  button-danger:
    backgroundColor: "{colors.effort-red}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.md}"
    padding: "{spacing.control-x}"
  card:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card-pad}"
  today-decision-run:
    backgroundColor: "{colors.deep-green}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.xl}"
    padding: "{spacing.card-pad}"
  today-decision-adjust:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.xl}"
    padding: "{spacing.card-pad}"
  today-decision-rest:
    backgroundColor: "{colors.rest-blue}"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.xl}"
    padding: "{spacing.card-pad}"
  evidence-chip:
    backgroundColor: "{colors.mint-surface}"
    textColor: "{colors.lane-green}"
    rounded: "{rounded.md}"
  divider:
    backgroundColor: "{colors.line-mint}"
    textColor: "{colors.ink-green}"
  status-success:
    backgroundColor: "{colors.soft-mint}"
    textColor: "{colors.deep-green}"
    rounded: "{rounded.full}"
  status-info:
    backgroundColor: "{colors.rest-blue}"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.full}"
  status-warning:
    backgroundColor: "{colors.split-amber}"
    textColor: "{colors.ink-green}"
    rounded: "{rounded.full}"
  status-danger:
    backgroundColor: "{colors.effort-red}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.full}"
---

# Johnny Design System

## Overview

### Creative North Star

Johnny 的新視覺世界是「每天站上起跑線前，身邊有一個懂你的跑步夥伴」。介面預設是 light mint，像清晨跑前打開的訓練 App；真正需要決策的地方使用深綠、琥珀與休息藍，讓 `我可以`、`不太對勁`、`先收一下` 三種狀態一眼可判讀。

Johnny 不應該像一般 SaaS dashboard，也不應該像聊天機器人。它的第一印象是：今天身體狀態如何、Johnny 建議 Run / Adjust / Rest、證據是什麼、下一步要做什麼。

每日建議沿用既有白色卡片與深綠重點線，依序呈現本週執行回顧、今天怎麼執行、這堂課的重點。過期內容以琥珀色提示與原產生時間標示。這張卡不放接受或拒絕按鈕；需要確認的課表調整仍由 Johnny 的 Recommendation 卡片處理。

### Product context and register

- **Audience and primary job:** 以繁體中文為主要介面的耐力跑者、馬拉松訓練者與長期訓練中的使用者。主要工作是每天快速理解訓練、恢復、風險與 Johnny 的建議，並決定今天要跑、調整或休息。
- **Register:** Product-first app experience. 沒有行銷首頁；登入後第一畫面是 `今日`。
- **Signature:** `start-line cockpit`。Today 以一張高層級決策卡開始，卡片內有 Johnny 的短句、Today Decision、今日課表、2-3 個證據 chip，以及明確 action。
- **Interaction loop:** Observe -> Understand -> Reason -> Recommend -> User Decision -> Act -> Learn.
- **Tone:** Johnny 像懂訓練的跑友：直接、會開一點跑者懂的玩笑，但不幼稚。Rest copy 可以像 `今天不要硬撐，跑鞋先放假。`
- **Anti-references:** 不做深色 AI chatbot、不做等寬數據牆、不做社群健身打卡牆、不做單調醫療健康儀表板、不做米色筆記本風。
- **Token ownership/runtime mapping:** 本檔是 Johnny 前端視覺 source of truth。實作應將 frontmatter token 對應到 `frontend/src/styles.css` 的 CSS custom properties，再由 Vue components 透過語意 class 使用；不要在 component 內直接重複 hex 值。

## Colors

Johnny 使用 light mint 作為預設 app shell。`mint-track` 是頁面背景，`mint-surface` 是輕量區塊背景，`card-white` 是主要卡片表面。文字主色使用 `ink-green`，次要文字使用 `muted-green`，分隔線使用 `line-mint`。

決策狀態色：

- `deep-green`: `我可以` / Run，主 workout decision card、primary safe action。
- `split-amber`: `不太對勁` / Adjust，代表需要調整但可恢復。
- `rest-blue`: `先收一下` / Rest，代表保護性休息，不是失敗。
- `effort-red`: 高風險、錯誤、傷痛警示、不可逆或破壞性動作。

深色不再是全域背景，而是 Today 決策卡與高焦點區塊的局部強調。資料視覺化不要只靠色彩判斷；每個狀態都要同時有文字、標籤或 icon。

## Typography

主要介面使用 `IBM Plex Sans` 搭配繁中 fallback `Noto Sans TC`、`PingFang TC`、`Microsoft JhengHei`。中文不使用 italic。

Display 字體只用於頁面主標題、Today Decision、race countdown、phase title。卡片內標題保持緊湊，避免 hero-scale type 擠壓行動資訊。

數字、配速、日期、HRV、負荷、距離和 signal coverage 使用 `IBM Plex Mono` 或等寬 fallback。等寬字只用於資料與短標籤，不用於長篇中文說明。

Copy 原則：

- State labels 可以有個性：`我可以`、`不太對勁`、`先收一下`。
- Buttons 使用明確動詞：`開始跑步`、`接受調整`、`記錄休息`、`查看證據`、`連接資料來源`。
- Memory insight 不直白暴露資料庫感：使用 `依照你過去的恢復模式，今天建議保守。`
- 錯誤不道歉，直接說明狀況與下一步：`Garmin 連接失敗。請檢查授權狀態後再試一次。`

## Layout

主架構是五個 product surfaces：

- `今日`: start-line cockpit，預設入口。
- `計畫`: inclusive training journey + weekly schedule。Race goals can appear inside the journey, but non-race athletes still see a useful training cycle.
- `Johnny`: pending recommendations first, weekly review/check-ins below. Conversation remains hidden until public-ready.
- `運動員`: Athlete Baseline snapshot first, profile/settings below. Athlete Memory is not a browsable frontend page.
- `資料`: Signal Coverage first, provider connection details below.

Mobile 使用底部 navigation，label 為 `今日`、`計畫`、`Johnny`、`運動員`、`資料`。Desktop 可使用 compact top/side navigation，但必須保留同一 vocabulary 和 current-page affordance。

Today mobile follows a centered vertical flow similar to a training app:

1. Compact brand/session header.
2. Main Today Decision card.
3. Weekly activity rhythm chart.
4. Upcoming training / next plan steps.
5. Secondary nudges to Johnny recommendations and Data.

Today desktop uses a main decision column plus a right-side context rail. The left column keeps the mobile flow and remains visually dominant. The right rail can show race countdown, plan phase, signal coverage, and pending recommendation count.

`計畫` begins with a training journey: base, build, peak, taper, and goal week. Race goals are optional highlights, not a prerequisite for the page to make sense. Weekly schedule sits underneath as execution detail.

`資料` begins with Signal Coverage, e.g. `Johnny 已有 4/6 個訓練訊號`。The six MVP signals are activity, sleep, HRV, resting heart rate, training load, and athlete baseline.

## Elevation & Depth

Johnny 的新預設比舊版更輕。卡片使用白色表面、細邊線和少量柔和 shadow，讓 mobile column 有 app-like tactility。不要把每個區塊都做成同等卡片；Today Decision card 是最高層級。

Static cards may use a subtle shadow on light mint backgrounds. Interactive cards should primarily signal hover/focus through border and background shifts. Modal、drawer、toast 可以使用更強陰影，但不能模糊整個產品成裝飾背景。

## Shapes

標準 radius 是 `0.75rem`。Main decision card 可使用 `xl`，但 controls 和 smaller cards 保持 `md` 或 `lg`。Pill 只用於 status badge、signal chip、短 filter chip。

Track/race identity should come from lane lines, phase segments, data rhythm, and start-line hierarchy, not from decorative blobs or unrelated gradients.

## Components

### Today Decision Card

Today Decision card owns the Run / Adjust / Rest moment:

- `我可以`: deep green card, button `開始跑步`.
- `不太對勁`: amber card, button `接受調整`.
- `先收一下`: rest blue card, button `記錄休息`.

The card shows Johnny voice inside the decision moment, not above the page as a generic greeting. It includes the planned workout, action button, top 2-3 evidence chips, and when relevant one subtle memory-derived insight.

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

Motion should feel like a training state change: short, useful, and stateful. Run/Adjust/Rest transitions may use a quick card tone shift or rail reveal. Respect `prefers-reduced-motion`; no continuous floating backgrounds.

### Data visualization

The weekly activity rhythm chart belongs below Today Decision. It should show the week at a glance without becoming a full analytics dashboard. Chart labels need text equivalents and cannot depend on color alone.

## Do's and Don'ts

- **Do:** Make Today answer `我今天要跑、調整，還是休息？`
- **Do:** Use the light mint shell and deep green decision card as Johnny's memorable first impression.
- **Do:** Keep evidence visible when Johnny suggests Adjust or Rest.
- **Do:** Let Athlete Memory appear only through relevant recommendation/conversation wording, never as a browsable memory database.
- **Do:** Put Signal Coverage before provider admin details on `資料`.
- **Don't:** Bring back a full dark cockpit shell as the default.
- **Don't:** Make Johnny a mascot-heavy or childish character.
- **Don't:** Turn the app into a generic dashboard grid of equal cards.
- **Don't:** Hide decision evidence behind chat.
- **Don't:** Use `我不行` for rest state; rest should feel strategic, not like failure.
