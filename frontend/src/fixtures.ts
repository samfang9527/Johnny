import type { ConversationThread, InboxRecommendation, EvidenceItem, ProviderOption, RaceSummary, RecommendationSummary, WorkoutSummary } from './types'

export const raceSummary: RaceSummary = {
  name: 'Sydney Marathon',
  date: '2026-08-30',
  distance: 'Marathon',
  goal: 'Sub 4:00',
  daysRemaining: 16,
}

export const futureRaces: RaceSummary[] = [
  raceSummary,
  {
    name: 'Taipei Half Tune-up',
    date: '2026-11-15',
    distance: 'Half Marathon',
    goal: '穩定配速',
    daysRemaining: 85,
  },
  {
    name: 'Tokyo Marathon Prep Race',
    date: '2027-01-24',
    distance: '30 km',
    goal: '檢查補給與節奏',
    daysRemaining: 155,
  },
]

export const recoveryEvidence: EvidenceItem[] = [
  {
    source: 'Garmin',
    metric: 'HRV',
    value: '52 ms',
    summary: '低於基準 18%',
    tone: 'warning',
  },
  {
    source: 'Apple Health',
    metric: '睡眠',
    value: '5 小時 42 分',
    summary: '比平常少 1 小時 20 分',
    tone: 'warning',
  },
  {
    source: 'Johnny Analytics',
    metric: '7 日負荷',
    value: '+21%',
    summary: '近期訓練負荷偏高',
    tone: 'danger',
  },
]

export const unavailableSignals = ['尚未連接靜息心率來源', '缺少最近 3 天睡眠品質資料']

export const todayWorkout: WorkoutSummary = {
  id: 'workout-today',
  weekday: '今日',
  dateLabel: '8/21',
  type: 'Easy Run',
  purpose: '恢復跑，維持輕鬆體感',
  distance: '8 km',
  pace: '6:20-6:40 /km',
  heartRateZone: 'Zone 2',
  status: 'planned',
}

export const recommendation: RecommendationSummary = {
  id: 'rec-today',
  priority: 'warning',
  title: '今天保持輕鬆，不做加速',
  rationale: '恢復訊號低於基準，昨天已有節奏跑刺激。',
  proposedAction: '8 km Easy Run，取消 strides',
  status: 'pending',
}

export const plannedWorkouts: WorkoutSummary[] = [
  todayWorkout,
  {
    id: 'workout-wed',
    weekday: '週三',
    dateLabel: '8/26',
    type: 'Easy Run',
    purpose: '有氧恢復',
    distance: '8 km',
    pace: '6:20-6:40 /km',
    heartRateZone: 'Zone 2',
    status: 'planned',
  },
  {
    id: 'workout-fri',
    weekday: '週五',
    dateLabel: '8/28',
    type: 'Tempo',
    purpose: '馬拉松配速耐受',
    duration: '45 分',
    pace: '5:35-5:45 /km',
    status: 'planned',
  },
  {
    id: 'workout-sun',
    weekday: '週日',
    dateLabel: '8/30',
    type: 'Long Run',
    purpose: '賽前最後長距離',
    distance: '18 km',
    pace: '6:00-6:20 /km',
    status: 'planned',
  },
]

const raceTaperEvidence: EvidenceItem[] = [
  {
    source: 'Garmin',
    metric: 'HRV',
    value: '52 ms',
    summary: 'HRV -18%',
    tone: 'warning',
  },
  {
    source: 'Training Load',
    metric: '7 日負荷',
    value: '+21%',
    summary: '高於近 4 週均值',
    tone: 'danger',
  },
]

const longRunEvidence: EvidenceItem[] = [
  {
    source: 'Johnny Plan',
    metric: 'Race countdown',
    value: '9 天',
    summary: '進入賽前遞減',
    tone: 'info',
  },
  {
    source: 'Apple Health',
    metric: '睡眠',
    value: '5 小時 42 分',
    summary: '恢復不足',
    tone: 'warning',
  },
]

export const conversationThreads: ConversationThread[] = [
  {
    id: 'thread-race-taper',
    title: '賽前恢復調整',
    summary: '確認今天是否該取消加速段',
    updatedLabel: '今天 08:12',
    linkedRecommendation: {
      id: 'rec-race-taper',
      title: '賽前 9 天降低長跑壓力',
      status: 'pending',
      statusLabel: '待決定',
      evidenceSummary: 'HRV -18% · 7 日負荷 +21%',
      evidence: raceTaperEvidence,
    },
    messages: [
      {
        id: 'msg-user-1',
        role: 'user',
        authorLabel: '你',
        content: '今天原本有 8 km Easy Run 加 strides，恢復偏低時還要跑加速嗎？',
        timestampLabel: '08:09',
      },
      {
        id: 'msg-johnny-1',
        role: 'johnny',
        authorLabel: 'Johnny 回覆',
        content: '建議保留 Easy Run，但取消 strides。現在主要任務是吸收前一堂節奏跑，不是再製造神經肌肉刺激。',
        timestampLabel: '08:12',
        evidence: raceTaperEvidence,
        proposedAction: {
          id: 'action-race-taper',
          title: '改成 8 km Easy Run',
          summary: '維持 Zone 2，取消 strides，跑後 10 分鐘放鬆。',
          proposedAction: '8 km Easy Run，取消 strides',
          rationale: 'HRV 偏低且 7 日負荷上升，保守調整能降低賽前疲勞。',
          evidence: raceTaperEvidence,
        },
      },
    ],
  },
  {
    id: 'thread-long-run',
    title: '週末長跑安排',
    summary: '確認賽前最後一次長跑強度',
    updatedLabel: '昨天 21:30',
    messages: [
      {
        id: 'msg-user-2',
        role: 'user',
        authorLabel: '你',
        content: '週日 18 km Long Run 還需要加入馬拉松配速嗎？',
        timestampLabel: '昨天 21:24',
      },
      {
        id: 'msg-johnny-2',
        role: 'johnny',
        authorLabel: 'Johnny 回覆',
        content: '18 km Long Run 可以保留，但馬拉松配速段壓到 3 km 內。你現在需要維持節奏感，不需要再累積疲勞。',
        timestampLabel: '昨天 21:30',
        evidence: longRunEvidence,
      },
    ],
  },
]

export const inboxRecommendations: InboxRecommendation[] = [
  {
    id: 'rec-race-taper',
    title: '賽前 9 天降低長跑壓力',
    summary: '恢復低於基準，Johnny 建議把週日長跑從 18 km 調整為 14 km，取消後段馬拉松配速。',
    proposedAction: '14 km Easy Long Run，取消 MP finish',
    rationale: '賽前主目標是降低殘餘疲勞，保留有氧但避免品質段。',
    priority: 'high',
    priorityLabel: '高優先',
    status: 'pending',
    statusLabel: '待決定',
    expiresAtLabel: '今天 21:00 前決定',
    evidence: raceTaperEvidence,
  },
  {
    id: 'rec-sleep-recovery',
    title: '延後明天節奏跑',
    summary: '連續兩晚睡眠不足，已接受把節奏跑延到週五。',
    proposedAction: 'Tempo 延至週五',
    rationale: '睡眠缺口影響恢復，延後能保留訓練品質。',
    priority: 'medium',
    priorityLabel: '中優先',
    status: 'accepted',
    statusLabel: '已接受',
    evidence: [
      {
        source: 'Apple Health',
        metric: '睡眠',
        value: '5 小時 42 分',
        summary: '連續兩晚偏低',
        tone: 'warning',
      },
    ],
  },
  {
    id: 'rec-calendar-sync',
    title: '同步課表調整',
    summary: '已套用你接受的 Easy Run 調整，課表保留原本訓練目的。',
    proposedAction: '更新今日課表',
    rationale: '資料來源同步完成，Johnny 已把訓練決策反映到課表。',
    priority: 'low',
    priorityLabel: '低優先',
    status: 'applied',
    statusLabel: '已套用',
    evidence: [
      {
        source: 'Johnny Plan',
        metric: '課表',
        value: '已更新',
        summary: '與今日建議一致',
        tone: 'success',
      },
    ],
  },
]

export const providers: ProviderOption[] = [
  {
    id: 'garmin_connect',
    name: 'Garmin Connect experimental login',
    status: 'available',
    statusLabel: '可連接',
    coverage: ['活動', '睡眠', 'HRV', 'Body Battery'],
    description: '使用 Garmin 電子郵件與密碼建立實驗性連線，初次連接會自動同步 30 天資料。',
  },
  {
    id: 'apple-health',
    name: 'Apple Health',
    status: 'available',
    statusLabel: '可連接',
    coverage: ['睡眠', '靜息心率', '每日健康指標'],
    description: '補足日常健康與睡眠訊號。',
  },
  {
    id: 'strava',
    name: 'Strava',
    status: 'future',
    statusLabel: '即將支援',
    coverage: ['跑步活動', '路線紀錄'],
    description: '未來用於活動紀錄與路線脈絡。',
  },
]
