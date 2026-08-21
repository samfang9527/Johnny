import type { EvidenceItem, ProviderOption, RaceSummary, RecommendationSummary, WorkoutSummary } from './types'

export const raceSummary: RaceSummary = {
  name: 'Sydney Marathon',
  date: '2026-08-30',
  distance: 'Marathon',
  goal: 'Sub 4:00',
  daysRemaining: 16,
}

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

export const providers: ProviderOption[] = [
  {
    id: 'garmin',
    name: 'Garmin',
    status: 'available',
    statusLabel: '可連接',
    coverage: ['Running activity', 'HRV', 'Sleep', 'Training Load'],
    description: '適合提供跑步、恢復與訓練負荷資料。',
  },
  {
    id: 'apple-health',
    name: 'Apple Health',
    status: 'available',
    statusLabel: '可連接',
    coverage: ['Sleep', 'Resting HR', 'Daily health metrics'],
    description: '補足日常健康與睡眠訊號。',
  },
  {
    id: 'strava',
    name: 'Strava',
    status: 'future',
    statusLabel: '即將支援',
    coverage: ['Running activity', 'Route history'],
    description: '未來用於活動紀錄與路線脈絡。',
  },
]
