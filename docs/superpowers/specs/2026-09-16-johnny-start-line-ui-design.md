# Johnny Start-Line UI Design

## Purpose

Redesign Johnny from a dark dashboard-style training cockpit into a light mint, mobile-first running companion app. The new UI centers the product around a Today Decision: Johnny helps the athlete decide whether to run, adjust, or rest, then routes them into plan, recommendation, athlete baseline, and data coverage surfaces.

## Source Decisions

- The design spine is **A + C**: running companion plus training journey.
- The visual theme is a **light mint default** with deeper race/track accents.
- Today is the product start line.
- Johnny's presence is distinct but not mascot-heavy.
- Athlete Memory is private Johnny context and not a frontend destination.
- Conversation remains hidden for this release.
- Implementation scope covers the coherent shell: Today plus first-pass `計畫`, `Johnny`, `運動員`, and `資料`.

## Information Architecture

Production navigation has five surfaces:

1. `今日`
2. `計畫`
3. `Johnny`
4. `運動員`
5. `資料`

The old `訓練安排` capability becomes `計畫`. The old `Agent 收件匣` capability becomes the first section of `Johnny`. The old `運動員設定` capability becomes the settings section of `運動員`. The old `資料來源` capability becomes provider details inside `資料`.

Conversation remains hidden from navigation and from the main Johnny page for now.

## Today

Today is a start-line cockpit. The first major card is the Today Decision card.

### Today Decision States

| State | Meaning | Card label | Primary action | Tone |
|---|---|---|---|---|
| Run | The athlete can execute today's plan | `我可以` | `開始跑步` | deep green |
| Adjust | The plan should be modified | `不太對勁` | `接受調整` | amber |
| Rest | Rest is the smarter training decision | `先收一下` | `記錄休息` | soft blue |

Supporting copy for rest may be playful but not childish, e.g. `今天不要硬撐，跑鞋先放假。`

The card shows:

- Johnny voice inside the card.
- Workout title, distance/duration, target, and purpose.
- Top 2-3 evidence chips.
- One subtle Athlete Memory insight when relevant, phrased like `依照你過去的恢復模式，今天建議保守。`
- One clear primary action.

### Weekly Activity Rhythm

Today includes a weekly activity rhythm chart below the decision card. It is an overview of weekly movement and training rhythm, not a full analytics dashboard.

### Responsive Layout

Mobile uses a centered vertical flow. Desktop uses:

- Main column: Today Decision, weekly activity, upcoming training.
- Context rail: race countdown, plan phase, signal coverage, and pending Johnny recommendation count.

## Plan

`計畫` begins with a race-track journey timeline. The top-level phase model is:

1. Base
2. Build
3. Peak
4. Taper
5. Race

The weekly schedule sits below as execution detail. The plan page should feel like progress toward race day, not only a list of workouts.

## Johnny

`Johnny` is the reasoning center. It shows:

1. Pending recommendations first.
2. Weekly review and check-ins below.
3. Historical recommendations after current work.

Recommendation cards may include Run / Adjust / Rest state labels, but their action buttons use clear decision verbs such as `接受調整` and `保留課表`.

Conversation is not public in this release and must remain hidden.

## Athlete

`運動員` starts with an Athlete Baseline snapshot:

- Weekly mileage.
- Experience level.
- Injury status.
- Preferred training rhythm.
- Recent baseline metrics.

Profile and settings editing remains below the snapshot and continues to save through the existing athlete profile API.

Athlete Memory must not appear as a page, table, tab, navigation item, or browsable list. It may appear only as contextual wording in recommendations or future conversation.

## Data

`資料` starts with Signal Coverage:

`Johnny 已有 4/6 個訓練訊號`

The six MVP signals are:

1. Activity
2. Sleep
3. HRV
4. Resting heart rate
5. Training load
6. Athlete baseline

Provider cards and sync health appear below Signal Coverage. The page answers whether Johnny has enough evidence to coach well before it exposes provider administration.

## Visual System

`DESIGN.md` owns the durable token and visual rules. Runtime implementation maps those values into `frontend/src/styles.css`.

Key visual changes:

- Light mint shell replaces the dark default shell.
- Deep green decision card anchors Today.
- Adjust uses amber and Rest uses soft blue.
- Cards become white or near-white with subtle borders and soft elevation.
- Mobile bottom navigation becomes the primary narrow-screen nav.
- Track/race identity comes from phase lanes, evidence rhythm, and journey segments rather than decorative backgrounds.

## Testing And Verification Requirements

Implementation must verify:

- Navigation labels are `今日`, `計畫`, `Johnny`, `運動員`, `資料`.
- Conversation is absent from production navigation and public Johnny page.
- Today shows the state label, action label, evidence chips, and weekly activity chart.
- Plan shows phase timeline and schedule.
- Johnny shows pending recommendations first.
- Athlete shows baseline snapshot before settings form.
- Data shows Signal Coverage before provider details.
- Existing athlete settings save behavior and race-goal create behavior still work.
- `npm run test`, `npm run build`, and `npm run verify:tokens` pass from `frontend`.
- Premium audit strict mode is run or any inability to run it is reported.

## Out Of Scope

- New backend APIs.
- Public conversation launch.
- New external provider integrations.
- A browsable Athlete Memory database.
- Full analytics dashboard beyond the weekly activity rhythm overview.
