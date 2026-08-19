# Johnny AI Sports Companion

## 1. 專案概述

Johnny 是一個以「運動好朋友」為核心概念的 AI Sports Companion Web App。

產品目標不是單純提供訓練課表，也不是做成一個只靠聊天互動的 AI Chatbot，而是建立一個能夠長期理解使用者、持續觀察運動與恢復狀態、主動提出建議，並在使用者同意後協助執行調整的 AI Agent 系統。

核心概念：

> Observe → Understand → Reason → Recommend → User Decision → Act → Learn

Johnny 應該逐步建立對使用者的理解，例如：

- 訓練目標
- 比賽日期
- 運動習慣
- 過去訓練紀錄
- 睡眠與恢復狀態
- 運動偏好
- 可接受的訓練量
- 過往受傷或疲勞情況
- 對不同訓練類型的適應程度

最終目標是讓使用者感覺：

> Johnny 不只是回答我的問題，而是真的長期了解我的訓練狀況。

---

## 2. 核心使用情境

### 2.1 設定比賽與訓練目標

使用者可以建立：

- Race
- Race Date
- Race Distance
- Target Time
- Training Goal
- Training Period

例如：

```text
Race: Sydney Marathon
Date: 2026-08-30
Distance: Marathon
Goal: Sub 4:00
```

系統可以依據目標建立 Training Plan。

---

### 2.2 串接個人運動與健康數據

預計支援：

- Garmin
- Apple Health
- Strava
- 其他 wearable / health platforms

可取得資料包含：

- Running activity
- Distance
- Pace
- Heart rate
- Training load
- HRV
- Resting heart rate
- Sleep duration
- Sleep quality
- Recovery metrics

這些資料會成為 AI Agent 判斷使用者狀態的重要 Context。

---

## 3. AI Training Coach

Johnny 會依據：

- 使用者目標
- Training Plan
- 最近訓練紀錄
- Training Load
- Sleep
- HRV
- Resting Heart Rate
- Recovery State
- 使用者主觀回饋

產生訓練建議。

例如：

```text
原訂課表：
10 km Recovery Run

目前狀態：
Sleep: 5h 42m
HRV: -18%
7-day load: +21%
Yesterday: 12 km Tempo

Johnny 建議：
將今天課表調整為 6 km Easy Run，
或改為完整休息。
```

原則：

> AI 提供 Recommendation，但重大調整由使用者確認。

---

## 4. Race Strategy

Johnny 可以根據：

- Target Finish Time
- Recent Fitness
- Training Performance
- Course Profile
- Weather
- Elevation
- Aid Stations

建立比賽策略。

例如：

```text
Goal:
Marathon Sub 4

Target average pace:
5:41 / km

Race Strategy:

0–5 km
5:45–5:50

5–30 km
5:38–5:42

30–37 km
5:40–5:45

37–42 km
依照體感與心率決定是否加速
```

未來也可加入：

- Fuel strategy
- Hydration strategy
- Pace adjustment
- Weather adjustment
- Race-day checklist

---

# 5. UI / UX Interaction Model

Johnny 不應該被設計成純 ChatGPT Clone。

建議採用三種主要 Interaction Surface：

1. Today
2. Conversation
3. Agent Inbox

---

## 5.1 Today

Today 是使用者每天最常打開的頁面。

主要顯示：

- 下一場比賽
- 倒數時間
- 今日訓練
- Recovery
- Sleep
- HRV
- Training Load
- AI Recommendation

例如：

```text
Good Morning

Sydney Marathon
16 days remaining
Goal: Sub 4:00

Recovery
----------------

Sleep          6h 12m
HRV            52 ms ↓
Resting HR     58 ↑
Training Load  Moderate

Today's Workout
----------------

Easy Run
8 km @ 6:20–6:40/km

Johnny's Suggestion

Your recovery is slightly below baseline.
Keep today's run easy and skip strides.

[Start Workout]
[Adjust Workout]
[Why?]
```

重要 UX 原則：

> AI 給 Recommendation，UI 提供 Evidence。

不要只顯示：

```text
Johnny 認為你今天應該休息。
```

而是：

```text
Recommendation:
30 min easy / rest

Reason:

HRV        -18%
Sleep      5h42m
7-day Load +21%
Yesterday  Tempo 12km
```

---

## 5.2 Conversation

Conversation 用來處理：

- 模糊問題
- 臨時狀況
- 複雜分析
- 課表調整
- 身體數據分析
- 比賽推薦
- Race strategy

例如：

```text
我今天腿有點酸，但沒有痛，要不要跑？

下週六臨時要去爬山，可以幫我調整課表嗎？

最近五次 Long Run 為什麼後段心率一直上升？

幫我找十月日本適合我的半馬。
```

Agent 可以透過 Tools 取得：

```text
getTrainingPlan()
getRecentActivities()
getSleepData()
getRecoveryMetrics()
getRaceCalendar()
calculateTrainingLoad()
```

重要原則：

> LLM 不應該直接擁有所有資料。

而應該：

> LLM 知道如何透過 Tools 取得需要的資料。

---

## 5.3 Agent Inbox

Agent Inbox 用來承接 Johnny 主動產生的 Recommendation。

例如：

```text
Johnny
Today 08:12

Your HRV has been below baseline
for 3 consecutive days.

Tomorrow's interval session:

6 × 1 km @ 4:50/km

Suggested adjustment:

4 × 1 km @ 5:00/km

[Apply]
[Keep Original]
[Discuss]
```

也可以包含：

- Training warning
- Recovery warning
- Race recommendation
- Weekly summary
- News recommendation
- Equipment discussion
- Training insight

---

# 6. Interaction Pattern

建議採用：

```text
Suggest
↓
Explain
↓
Approve
↓
Execute
```

例如：

```text
Johnny:

I recommend changing tomorrow's
10K Tempo to 8K Easy.

Why?

HRV          ↓ 20%
Sleep Deficit 2.1h
Training Load ↑ 18%

[Accept]
[Edit]
[Keep Original]
```

涉及訓練計畫調整時應盡量保留 Human-in-the-loop。

---

# 7. Backend Architecture

Johnny 的後端不應該設計成：

```text
Frontend
↓
LLM
↓
Database
```

而應該將 Agent 視為 Application Layer 的一部分。

建議架構：

```text
Clients

Web
iOS
LINE

        ↓

API Gateway / BFF

        ↓

Application Layer

User
Athlete
Training
Race
Health
Notification

        ↓

Domain Services

TrainingPlanService
TrainingLoadService
RecoveryService
RaceStrategyService
AthleteProfileService
RecommendationService

        ↓

PostgreSQL
Redis
Event Bus
```

---

# 8. Agent Runtime

V1 不建議一開始建立 Multi-Agent System。

建議使用：

```text
Running Companion Agent
```

作為 Single Orchestrator Agent。

架構：

```text
                Running Companion Agent
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼

 Training Tools       Health Tools      Race Tools

        │                 │                 │

 Notification Tools  Content Tools      User Tools
```

等未來系統複雜度真的增加，再拆成：

```text
Companion Orchestrator

├── Coach Agent
├── Research Agent
└── Race Agent
```

---

# 9. Tool-centric Agent Architecture

Agent 不應該直接存取 Database。

例如不要讓 Agent：

```sql
SELECT *
FROM activities;
```

而應該提供 Domain Tools：

```text
getRecentTraining()

getAthleteTrainingContext()

getRecoveryState()

getTrainingPlan()

getRaceContext()

updateTrainingPlan()

createRecommendation()
```

例如：

```json
{
  "weeklyDistance": 52.3,
  "previousWeeklyDistance": 43.1,
  "acuteLoad": 482,
  "chronicLoad": 438,
  "sleepScore": 68,
  "hrvBaseline": 58,
  "currentHrv": 49,
  "nextWorkout": {
    "type": "interval",
    "distance": 10
  }
}
```

Agent 再針對這些 Structured Context 進行 Reasoning。

---

# 10. Deterministic Analytics

不要讓 LLM 負責計算核心 Training Metrics。

例如：

```text
calculateTrainingLoad()

calculateRecoveryScore()

calculatePaceZones()

calculateRacePrediction()

calculateWeeklyMileage()

calculateAcuteChronicLoad()
```

應該由 deterministic code 執行。

資料流：

```text
Raw Data

↓

// deterministic

Training Analytics Engine

↓

Structured Metrics

↓

LLM

↓

Recommendation
```

而不是：

```text
Raw Data
↓
LLM
↓
Magic
```

---

# 11. Agent Execution Modes

Johnny 可以有三種主要執行方式。

---

## 11.1 Reactive

由使用者觸發。

```text
User

↓

Conversation

↓

Agent

↓

Tools

↓

Response
```

例如：

```text
幫我分析昨天的 Long Run。
```

---

## 11.2 Event-driven

由外部事件觸發。

例如：

```text
Garmin Activity

↓

Webhook

↓

ActivityIngested

↓

Event Bus

↓

Activity Analyzer

↓

Agent

↓

Recommendation
```

可能產生：

```text
你昨天的 Training Load 明顯高於近期平均，
建議明天降低訓練強度。
```

---

## 11.3 Scheduled

由排程觸發。

例如：

```text
06:00
Recovery Analysis

08:00
Daily Briefing

Monday
Weekly Training Review

Monthly
Training Progress Report
```

---

# 12. Memory Design

Johnny 建議至少包含四種 Memory。

---

## 12.1 Conversation Memory

只屬於目前 Conversation。

例如：

```text
User:
這週六我要去爬山。

Johnny:
知道。
```

---

## 12.2 Athlete Profile

長期資料。

例如：

```json
{
  "experience": "intermediate",
  "weeklyMileage": 45,
  "preferredTrainingDays": [
    "Tue",
    "Thu",
    "Sat"
  ]
}
```

---

## 12.3 Athlete Preferences

例如：

```text
不喜歡 Treadmill

週日偏好 Long Run

Interval 喜歡 1km Repeat

每週最多跑五天
```

---

## 12.4 Agent-derived Memory

Agent 可以從長期資料推論：

```text
User usually needs longer recovery
after interval sessions.

Sleep quality often decreases
before weekday morning training.
```

這類 Memory 應該有較高的寫入門檻。

建議：

```text
Observation

↓

Confidence Check

↓

Memory Policy

↓

Store
```

---

# 13. Data Integration

## Garmin

主要取得：

- Activities
- Heart Rate
- Sleep
- Stress
- Recovery
- Health Metrics

Garmin 適合 Server-side integration。

---

## Apple Health

Apple HealthKit 並不是一般 Web API。

架構可能需要：

```text
iPhone

↓

iOS Companion App

↓

HealthKit

↓

Johnny Backend

↓

Web App
```

因此未來 Johnny 可能演進成：

```text
Web
+
iOS Companion App
```

---

## Strava

主要可作為：

- Activity integration
- Training history
- Running data source

---

# 14. Notification System

Agent 不應該直接處理每一種 Notification Channel。

建議：

```text
Agent

↓

Notification Service

↓

Channel Adapter

├── LINE
├── Email
└── Push Notification
```

Agent 只建立：

```text
Notification Intent
```

例如：

```json
{
  "type": "training_adjustment",
  "priority": "medium"
}
```

Notification Service 再決定如何發送。

---

# 15. Running Content / News System

Johnny 可以每天整理：

- Running news
- Training discussions
- Race information
- Equipment discussions
- Sports science research

可能資料來源：

- 運動筆記
- Threads
- Instagram
- YouTube
- Reddit
- RSS
- Running blogs

架構：

```text
Scheduler

↓

Content Collector

↓

Content Normalizer

↓

Deduplication

↓

Classification

↓

Summarization

↓

Personalization

↓

Feed / Agent Inbox
```

資料來源應優先使用：

```text
Official API
↓
RSS
↓
Crawler
```

而不是預設全部使用 Web Scraping。

---

# 16. Backend Module

可能的 Domain Module：

```text
User

Athlete

Race

Training

Activity

Health

Recovery

Recommendation

Notification

Content

Agent
```

---

# 17. Event Model

初期可以考慮：

```text
ActivityIngested

HealthDataUpdated

SleepDataUpdated

RecoveryCalculated

TrainingPlanCreated

WorkoutCompleted

WorkoutSkipped

TrainingLoadChanged

RaceCreated

TrainingRecommendationCreated

TrainingPlanAdjusted
```

這些 Event 可以成為 Agent 的 Trigger。

---

# 18. AI Agent Observability

Agent 系統必須比一般 API 有更完整的 tracing。

每次 Agent Run 應至少保存：

```text
run_id

user_id

trigger

model

prompt_version

context

tool_calls

tool_results

latency

token_usage

result

feedback
```

建議建立：

```text
Agent Observability

├── Tracing
├── Evaluation
├── Prompt Versioning
├── User Feedback
├── Cost
└── Latency
```

---

# 19. Reliability 與 Safety

Johnny 會處理與健康及運動相關的資訊，因此不應把 LLM 當成 Medical Decision System。

基本原則：

- 不進行疾病診斷
- 不替代醫療專業
- 不直接對疼痛或傷病做確定性判定
- 訓練調整應保留使用者確認
- 顯示 Recommendation 的依據
- 保存 Recommendation History
- 高風險操作需要 Human-in-the-loop

---

# 20. MVP

第一版建議先做：

1. User Profile
2. Race Goal
3. Garmin / Strava Integration
4. Training Calendar
5. AI Running Coach Chat
6. Daily Workout Recommendation
7. Training Adjustment
8. LINE Notification

核心閉環：

```text
Garmin

↓

Training Data

↓

Analytics

↓

AI Analysis

↓

Training Recommendation

↓

User Approval

↓

Training Adjustment

↓

LINE Notification
```

只要這條流程做得好，就已經具備完整產品價值。

---

# 21. 暫不列入 MVP

第一版先不處理：

- Apple Health
- Instagram integration
- Threads integration
- Large-scale content crawler
- Multi-agent
- Nutrition
- Full race discovery
- Advanced race travel planning

這些功能可以在核心 Training Loop 驗證後再逐步加入。

---

# 22. 未來 Multi-Agent Architecture

當功能變複雜後，可以演進成：

```text
                  Companion Orchestrator

          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼

      Coach Agent    Research Agent    Race Agent
```

### Coach Agent

負責：

- Training
- Recovery
- Sleep
- Workout adjustment

### Research Agent

負責：

- Running news
- Equipment
- Scientific research
- Community discussion

### Race Agent

負責：

- Race discovery
- Race analysis
- Course analysis
- Weather
- Race strategy

對使用者而言仍然維持：

```text
One Johnny
```

而不是暴露不同 Agent。

---

# 23. 技術架構方向

初期可以考慮：

```text
Frontend

Vue / Nuxt.js

Backend

TypeScript + NestJS
or
C# + .NET

Database

PostgreSQL

Cache

Redis

Message Queue

AWS SQS

Agent Runtime

OpenAI Agents SDK
or
custom orchestration

LLM

OpenAI / Other Provider
```

重要原則：

> Agent Framework 不應成為 System Architecture。

真正的架構應該是：

```text
Domain

+

Tools

+

Events

+

Memory

+

Agent Runtime

+

Observability
```

LangGraph、OpenAI Agents SDK 或其他框架只是 Runtime Implementation。

---

# 24. 整體架構

```text
                           Clients

              ┌────────────┬────────────┐
              │            │            │
             Web          iOS         LINE
              │            │            │
              └────────────┼────────────┘
                           │
                           ▼
                    API Gateway / BFF
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   Application Layer                      │
│                                                          │
│ User │ Athlete │ Training │ Race │ Health │ Notification │
└──────────────────────────┬───────────────────────────────┘
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼

      PostgreSQL         Redis           Event Bus

                                             │
             ┌───────────────────────────────┤
             │                               │
             ▼                               ▼

       Data Ingestion                 Background Workers

    Garmin │ Apple │ Strava          Content Collector
                                    Health Sync
                                    Daily Analysis
                                    Notifications

                           │
                           ▼

                ┌─────────────────────┐
                │    Agent Runtime    │
                │                     │
                │ Running Companion   │
                │       Agent         │
                └──────────┬──────────┘
                           │

          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼

     Training Tools    Health Tools      Race Tools

     Content Tools     User Tools      Notification Tools

                           │
                           ▼

                      LLM Provider
```

---

# 25. Product Moat

Johnny 真正的價值不只是 LLM。

核心競爭力會來自：

```text
Training Data

+

Athlete Context

+

Long-term Memory

+

Domain Analytics

+

Agent Tools

+

Event-driven Automation

+

Personalization

+

Evaluation
```

也就是：

> Harness Engineering for Running.

真正需要持續優化的不是單一 Prompt，而是整套 AI Agent Harness：

- Context
- Memory
- Tools
- Events
- Guardrails
- Domain Knowledge
- Analytics
- Evaluation

---

# 26. 下一階段

下一階段建議開始拆：

```text
Product Requirements
        ↓
Domain Model
        ↓
Use Cases
        ↓
Agent Tools
        ↓
Event Model
        ↓
Database Schema
        ↓
API Design
        ↓
MVP System Design
```

其中優先處理：

1. Domain Model
2. Use Case Definition
3. Agent Tool Definition

這三個完成後，再決定詳細的 DB Schema、API、Queue、Agent Framework 與 LLM Provider。
