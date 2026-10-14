<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  type SessionReviewSaveResult,
  acceptRecommendation,
  ApiRequestError,
  connectGarminIntegration,
  createRaceGoal,
  getRaceGoal,
  updateRaceGoal,
  deleteRaceGoal,
  disconnectIntegrationConnection,
  discussRecommendation,
  getAgentRun,
  getAthleteProfile,
  getCurrentUser,
  getGoogleSignInRedirectUrl,
  getTrainingPlanRegenerationOptions,
  getTodayContext,
  listIntegrationConnections,
  listRaceGoals,
  listRecommendations,
  listTrainingPlans,
  rejectRecommendation,
  saveAthleteProfile,
  signInWithEmail,
  signOut,
  signUpWithEmail,
  startTrainingPlanRegeneration,
  syncIntegrationConnection,
  submitConversationMessage,
} from './api/client'
import AppButton from './components/AppButton.vue'
import EvidenceList from './components/EvidenceList.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import DailyAdviceCard from './components/DailyAdviceCard.vue'
import SessionReviews from './components/SessionReviews.vue'
import ProviderCard from './components/ProviderCard.vue'
import RaceGoalModal from './components/RaceGoalModal.vue'
import RecommendationActions from './components/RecommendationActions.vue'
import StatusBadge from './components/StatusBadge.vue'
import TrainingPlanRegenerationSheet from './components/TrainingPlanRegenerationSheet.vue'
import { formatRaceDistance, formatRacePriority } from './raceGoalForm'
import {
  conversationThreads as fixtureConversationThreads,
  futureRaces as fixtureFutureRaces,
  inboxRecommendations as fixtureInboxRecommendations,
  planPhases as fixturePlanPhases,
  plannedWorkouts as fixtureWorkouts,
  providers,
  raceSummary as fixtureRaceSummary,
  recommendation as fixtureRecommendation,
  recoveryEvidence as fixtureRecoveryEvidence,
  todayWorkout as fixtureTodayWorkout,
  unavailableSignals as fixtureUnavailableSignals,
  weeklyActivity as fixtureWeeklyActivity,
} from './fixtures'
import type {
  ConversationThread,
  DailyAdvice,
  CurrentUser,
  InboxRecommendation,
  LinkedRecommendationContext,
  ProviderOption,
  RecommendationStatus,
  RecommendationSummary,
  RaceSummary,
  TodayDecision,
  ViewKey,
  WorkoutSummary,
  EvidenceItem,
  IntegrationConnectionResponse,
  SyncResourceSummary,
  RaceGoalCreatePayload,
  RaceGoalUpdatePayload,
  AthleteProfileResponse,
  AthleteProfileSavePayload,
  TrainingPlanRegenerationOptions,
  TrainingPlanRegenerationRequest,
  TrainingPlanRegenerationRun,
  TrainingPlanPhase,
  TrainingPlanResponse,
  PlanPhase,
  AthleteBaselineSnapshot,
  SignalCoverageItem,
  WorkoutStep,
  WorkoutTarget,
} from './types'

const props = withDefaults(
  defineProps<{
    initialView?: ViewKey
    todayState?: 'full' | 'loading' | 'error' | 'empty'
    conversationState?: 'loaded' | 'loading' | 'error' | 'empty'
    inboxState?: 'loaded' | 'loading' | 'error' | 'empty'
    workouts?: WorkoutSummary[]
    conversationThreads?: ConversationThread[]
    inboxItems?: InboxRecommendation[]
    requireAuth?: boolean
  }>(),
  {
    todayState: 'full',
    conversationState: 'loaded',
    inboxState: 'loaded',
    workouts: undefined,
    conversationThreads: undefined,
    inboxItems: undefined,
    requireAuth: false,
  },
)

const navItems: Array<{ key: ViewKey; label: string }> = [
  { key: 'today', label: '今日' },
  { key: 'plan', label: '計畫' },
  { key: 'johnny', label: 'Johnny' },
  { key: 'athlete', label: '運動員' },
  { key: 'data', label: '資料' },
]

const timezoneOptions = [
  { value: 'Asia/Taipei', label: '台北 (Asia/Taipei)' },
  { value: 'Asia/Tokyo', label: '東京 (Asia/Tokyo)' },
  { value: 'Asia/Hong_Kong', label: '香港 (Asia/Hong_Kong)' },
  { value: 'Asia/Shanghai', label: '上海 (Asia/Shanghai)' },
  { value: 'Asia/Singapore', label: '新加坡 (Asia/Singapore)' },
  { value: 'UTC', label: 'UTC' },
  { value: 'America/Los_Angeles', label: '洛杉磯 (America/Los_Angeles)' },
  { value: 'America/Denver', label: '丹佛 (America/Denver)' },
  { value: 'America/Chicago', label: '芝加哥 (America/Chicago)' },
  { value: 'America/New_York', label: '紐約 (America/New_York)' },
  { value: 'Europe/London', label: '倫敦 (Europe/London)' },
  { value: 'Europe/Paris', label: '巴黎 (Europe/Paris)' },
  { value: 'Australia/Sydney', label: '雪梨 (Australia/Sydney)' },
]

const legacyViewMap: Partial<Record<string, ViewKey>> = {
  calendar: 'plan',
  inbox: 'johnny',
  'athlete-settings': 'athlete',
  sources: 'data',
}

function viewFromHash(): ViewKey | undefined {
  if (typeof window === 'undefined') {
    return undefined
  }
  const rawHashView = window.location.hash.replace('#', '')
  const mappedView = legacyViewMap[rawHashView] ?? (rawHashView as ViewKey)
  return navItems.some((item) => item.key === mappedView) ? mappedView : undefined
}

const activeView = ref<ViewKey>(props.initialView ?? viewFromHash() ?? 'today')
const busyAction = ref('')
const recommendationStatus = ref(fixtureRecommendation.status)
const apiRaceSummary = ref<RaceSummary | null>(null)
const apiTodayWorkoutPayload = ref<Record<string, unknown> | null>(null)
const apiDailyAdvice = ref<DailyAdvice | null>(null)
const sessionReviewsRefreshKey = ref(0)
const apiTodayWorkout = computed(() => {
  const raw = apiTodayWorkoutPayload.value
  if (!raw) return null
  // The Today API selects the source ID; history can only fill details for that exact ID.
  const original = typeof raw.id === 'string' && raw.id ? apiTrainingPlans.value.flatMap((plan) => Array.isArray(plan.workouts) ? plan.workouts : []).map(asRecord).find((workout) => workout?.id === raw.id) : undefined
  return mapWorkout({ ...original, ...raw })
})
const apiTrainingPlans = ref<TrainingPlanResponse[]>([])
const activePlan = computed(() => apiTrainingPlans.value.find((plan) => plan.status === 'active'))
const apiWorkouts = computed(() => {
  const plan = activePlan.value
  const workouts = plan && Array.isArray(plan.workouts) ? [...plan.workouts] : []
  const mapped = workouts.map(mapWorkout).filter((workout): workout is WorkoutSummary => workout !== null)
  // Today owns predecessor selection; do not infer provenance from superseded plan dates.
  const today = apiTodayWorkout.value
  return today?.scheduledFor === todayIsoDate.value ? [today, ...mapped.filter((workout) => workout.id !== today.id && workout.scheduledFor !== todayIsoDate.value)] : mapped
})
const apiRecommendation = ref<RecommendationSummary | null>(null)
const apiRecoveryEvidence = ref<EvidenceItem[]>([])
const apiUnavailableSignals = ref<string[]>([])
const apiInboxItems = ref<InboxRecommendation[]>([])
const selectedProvider = ref<ProviderOption>(providers[0])
const garminEmail = ref('')
const garminPassword = ref('')
const garminRegion = ref<'global' | 'china'>('global')
const garminConnection = ref<IntegrationConnectionResponse | null>(null)
const isProviderDialogOpen = ref(false)
const providerMessage = ref('')
const providerError = ref('')
const providerBusy = ref<'' | 'connect' | 'sync' | 'disconnect'>('')
const pendingDisconnectConnectionId = ref('')
const userTimezone = ref('UTC')
const calendarNow = ref(new Date())
let calendarTimer: ReturnType<typeof setInterval> | undefined
let advicePollTimer: ReturnType<typeof setTimeout> | undefined
let advicePollGeneration = 0
let advicePollAttempts = 0
let lastMorningAdviceCheck = ''
let sessionGeneration = 0
let trainingReadVersion = 0
let trainingReadPending = false
let trainingReadDate = ''
const todayPayloadDate = ref('')
const todayReadFailed = ref(false)
const conversationMessage = ref('')
const conversationError = ref('')
const conversationStatus = ref('')
const conversationBusy = ref(false)
const isComposing = ref(false)
const linkedRecommendation = ref<LinkedRecommendationContext | null>(null)
const inboxBusyRecommendationId = ref('')
const inboxBusyAction = ref('')
const recommendationDecisions = ref<Record<string, RecommendationStatus>>({})
const raceEntries = ref<RaceSummary[]>(shouldRequireAuth() ? [] : fixtureFutureRaces)
const planRegenerationRaceOptions = ref<RaceSummary[]>(shouldRequireAuth() ? [] : fixtureFutureRaces)
const editingRace = ref<{ id: string; values: RaceGoalUpdatePayload } | null>(null)
const deletingRace = ref<RaceSummary | null>(null)
const raceActionError = ref('')
const racePlanReminder = ref('')
const raceDeleteError = ref('')
const raceEditLoading = ref(false)
let raceReturnFocus: HTMLElement | null = null
const raceFormError = ref('')
const raceFormMessage = ref('')
const isRaceGoalModalOpen = ref(false)
const isRaceGoalConfirmOpen = ref(false)
const raceGoalModalRef = ref<InstanceType<typeof RaceGoalModal> | null>(null)
const raceGoalBusy = ref(false)
let raceSuccessTimer: ReturnType<typeof setTimeout> | undefined
const isPlanRegenerationSheetOpen = ref(false)
const planRegenerationOptions = ref<TrainingPlanRegenerationOptions | null>(null)
const planRegenerationLoading = ref(false)
const planRegenerationBusy = ref(false)
const planRegenerationError = ref('')
const inFlightPlanRegeneration = ref<TrainingPlanRegenerationRun | null>(null)
const planRegenerationLoadingDialogRef = ref<HTMLElement | null>(null)
const regenerationPollIntervalMs = 2_000
const regenerationFastPollCount = 12
let planRegenerationPollTimer: ReturnType<typeof setTimeout> | undefined
let planRegenerationPollAttempts = 0
let planRegenerationObservation = 0
let isUnmounted = false
let planRegenerationReturnFocus: HTMLElement | null = null
const apiPlanPhases = computed(() => activePlan.value && activePlan.value.ends_on >= todayIsoDate.value ? mapPhaseSegments(activePlan.value.metadata) : [])
const authStatus = ref<'checking' | 'anonymous' | 'authenticated'>(shouldRequireAuth() ? 'checking' : 'authenticated')
const currentUser = ref<CurrentUser | null>(null)
const authMode = ref<'login' | 'signup'>('login')
const authDisplayName = ref('')
const authEmail = ref('')
const authPassword = ref('')
const authPasswordConfirm = ref('')
const authError = ref('')
const authMessage = ref('')
const authBusy = ref(false)
const hasBackendHydrated = ref(false)
const athleteSettings = ref<AthleteSettingsForm>(defaultAthleteSettingsForm())
const garminTrainingEvidence = ref<NonNullable<AthleteProfileResponse['garmin_training_evidence']>>({})
const athleteSettingsError = ref('')
const athleteSettingsFieldErrors = ref<Record<string, string>>({})
const athleteSettingsMessage = ref('')
const athleteSettingsBusy = ref(false)
const athleteMileageDisplayUnit = ref<'metric' | 'imperial'>('metric')

const activeTitle = computed(() => navItems.find((item) => item.key === activeView.value)?.label || '今日')
watch(activeTitle, updateDocumentTitle, { immediate: true })
const isAuthenticated = computed(() => authStatus.value === 'authenticated')
const hasActiveDataProvider = computed(() =>
  Boolean(garminConnection.value && garminConnection.value.status !== 'disconnected' && garminConnection.value.credential_status !== 'deleted'),
)
const effectiveTodayState = computed(() => {
  if (props.todayState !== 'full') {
    return props.todayState
  }
  if (hasBackendHydrated.value && shouldRequireAuth() && todayPayloadDate.value !== todayIsoDate.value) {
    return todayReadFailed.value ? 'error' : 'loading'
  }
  if (hasBackendHydrated.value && shouldRequireAuth() && hasActiveDataProvider.value) {
    return 'full'
  }
  return hasBackendHydrated.value && shouldRequireAuth() && !apiRaceSummary.value && !apiTodayWorkout.value && (!apiDailyAdvice.value || apiDailyAdvice.value.state === 'no_plan') ? 'empty' : 'full'
})
const raceSummary = computed(() => apiRaceSummary.value ?? (shouldRequireAuth() ? emptyRaceSummary() : fixtureRaceSummary))
const todayWorkout = computed(() => apiTodayWorkout.value ?? (shouldRequireAuth() ? emptyWorkoutSummary() : fixtureTodayWorkout))
const recoveryEvidence = computed(() => {
  if (apiRecoveryEvidence.value.length) {
    return apiRecoveryEvidence.value
  }
  return shouldRequireAuth() ? [] : fixtureRecoveryEvidence
})
const unavailableSignals = computed(() => {
  if (apiUnavailableSignals.value.length) {
    return apiUnavailableSignals.value
  }
  return shouldRequireAuth() ? [] : fixtureUnavailableSignals
})
const athleteBaselineSnapshot = computed<AthleteBaselineSnapshot>(() => ({
  weeklyMileage: `${athleteSettings.value.currentWeeklyMileage || '0'} ${athleteMileageDisplayUnit.value === 'imperial' ? 'mi' : 'km'}`,
  experience: athleteSettings.value.experienceLevel || '未設定',
  injuryStatus: formatInjuryStatusLabel(athleteSettings.value.injuryStatus),
  rhythm: `${athleteSettings.value.preferredTrainingDays.length} 天訓練 · 長跑 ${formatWeekdayLabel(athleteSettings.value.preferredLongRunDay)}`,
  recentMetrics: recoveryEvidence.value.slice(0, 3).map((item) => `${item.metric} ${item.value}`),
}))
const unavailableSignalKeys = computed(() => new Set(unavailableSignals.value.map(normalizeSignalKey)))
const hasRecoverySignal = computed(() => {
  const metrics = new Set(recoveryEvidence.value.map((item) => normalizeSignalKey(item.metric)))
  return {
    sleep: metrics.has('睡眠') || metrics.has('sleep'),
    hrv: metrics.has('hrv'),
    restingHeartRate: metrics.has('靜息心率') || metrics.has('resting_heart_rate') || metrics.has('resting_hr'),
    trainingLoad: metrics.has('負荷比') || metrics.has('7_日負荷') || metrics.has('training_load'),
  }
})
const signalCoverage = computed<SignalCoverageItem[]>(() => {
  return [
    { id: 'activity', label: 'Activity', covered: hasActiveDataProvider.value, source: 'Garmin' },
    { id: 'sleep', label: 'Sleep', covered: hasRecoverySignal.value.sleep && !isSignalUnavailable('sleep'), source: 'Garmin' },
    { id: 'hrv', label: 'HRV', covered: hasRecoverySignal.value.hrv && !isSignalUnavailable('hrv'), source: 'Garmin' },
    { id: 'resting_hr', label: 'Resting HR', covered: hasRecoverySignal.value.restingHeartRate && !isSignalUnavailable('resting_heart_rate'), source: 'Garmin' },
    { id: 'training_load', label: 'Training Load', covered: hasRecoverySignal.value.trainingLoad && !isSignalUnavailable('training_load'), source: 'Johnny Analytics' },
    { id: 'athlete_baseline', label: 'Athlete Baseline', covered: Boolean(athleteSettings.value.timezone), source: '運動員' },
  ]
})
const coveredSignalCount = computed(() => signalCoverage.value.filter((item) => item.covered).length)
const recommendation = computed(() => apiRecommendation.value ?? (shouldRequireAuth() ? null : fixtureRecommendation))
const displayWorkouts = computed(() => props.workouts ?? (apiWorkouts.value.length ? apiWorkouts.value : shouldRequireAuth() ? [] : fixtureWorkouts))
const visibleTrainingWeeks = ref(1)
const journeyPhases = computed<PlanPhase[]>(() => shouldRequireAuth() ? apiPlanPhases.value.map((segment) => ({
  id: `${segment.phase}-${segment.startsOn}`,
  label: segment.label,
  summary: segment.focus,
  status: segment.endsOn < todayIsoDate.value ? 'done' : segment.startsOn > todayIsoDate.value ? 'next' : 'current',
})) : fixturePlanPhases)
const displayThreads = computed(() => props.conversationThreads ?? fixtureConversationThreads)
const displayInboxItems = computed(() => {
  const source = props.inboxItems ?? (apiInboxItems.value.length ? apiInboxItems.value : shouldRequireAuth() ? [] : fixtureInboxRecommendations)
  return source.map((item) => {
    const status = recommendationDecisions.value[item.id]
    return status ? { ...item, status, statusLabel: statusLabel(status) } : item
  })
})
const planPhases = computed(() => (apiPlanPhases.value.length ? apiPlanPhases.value : shouldRequireAuth() ? [] : demoPlanPhases))
const activeThreadId = ref(displayThreads.value[0]?.id ?? '')
const activeThread = computed(() => displayThreads.value.find((thread) => thread.id === activeThreadId.value) ?? displayThreads.value[0])
const pendingInboxItems = computed(() => displayInboxItems.value.filter((item) => item.status === 'pending'))
const historicalInboxItems = computed(() => displayInboxItems.value.filter((item) => item.status !== 'pending'))
const todayIsoDate = computed(() => {
  const parts = new Intl.DateTimeFormat('en', { timeZone: userTimezone.value, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(calendarNow.value)
  return ['year', 'month', 'day'].map((key) => parts.find((part) => part.type === key)!.value).join('-')
})
const scheduleWeekStart = computed(() => {
  const plan = activePlan.value
  if (plan && isIsoDate(plan.starts_on) && isIsoDate(plan.ends_on)) {
    if (todayIsoDate.value < plan.starts_on && apiTodayWorkout.value?.scheduledFor === todayIsoDate.value) {
      return todayIsoDate.value
    }
    const elapsed = Math.floor((Date.parse(`${todayIsoDate.value}T00:00:00Z`) - Date.parse(`${plan.starts_on}T00:00:00Z`)) / 604_800_000)
    const lastWeek = Math.floor((Date.parse(`${plan.ends_on}T00:00:00Z`) - Date.parse(`${plan.starts_on}T00:00:00Z`)) / 604_800_000)
    return addCalendarDays(plan.starts_on, Math.min(Math.max(elapsed, 0), lastWeek) * 7)
  }
  const dates = displayWorkouts.value.map((workout) => workout.scheduledFor).filter(isIsoDate).sort()
  return dates.find((value) => value >= todayIsoDate.value) ?? dates[dates.length - 1] ?? null
})
const visibleScheduleEnd = computed(() => scheduleWeekStart.value ? addCalendarDays(scheduleWeekStart.value, visibleTrainingWeeks.value * 7 - 1) : null)
const visibleScheduleWorkouts = computed(() => {
  if (!scheduleWeekStart.value || !visibleScheduleEnd.value) return displayWorkouts.value
  return displayWorkouts.value
    .filter((workout) => isIsoDate(workout.scheduledFor) && workout.scheduledFor >= scheduleWeekStart.value! && workout.scheduledFor <= visibleScheduleEnd.value!)
    .sort((left, right) => left.scheduledFor!.localeCompare(right.scheduledFor!))
})
const hasMoreTrainingWeeks = computed(() => Boolean(visibleScheduleEnd.value && displayWorkouts.value.some((workout) => isIsoDate(workout.scheduledFor) && workout.scheduledFor > visibleScheduleEnd.value!)))
watch([scheduleWeekStart, () => activePlan.value?.id], () => { visibleTrainingWeeks.value = 1 })
const recoveryWindow = computed(() => {
  if (!shouldRequireAuth() || (activePlan.value && activePlan.value.starts_on <= todayIsoDate.value && activePlan.value.ends_on >= todayIsoDate.value)) return null
  const previous = apiTrainingPlans.value
    .filter((plan) => ['active', 'completed', 'superseded'].includes(plan.status) && isIsoDate(plan.ends_on) && plan.ends_on < todayIsoDate.value)
    .sort((a, b) => b.ends_on.localeCompare(a.ends_on))[0]
  if (!previous) return null
  const startsOn = addCalendarDays(previous.ends_on, 1)
  const endsOn = addCalendarDays(previous.ends_on, 7)
  if (todayIsoDate.value > endsOn) return null
  const day = Math.round((Date.parse(`${todayIsoDate.value}T00:00:00Z`) - Date.parse(`${previous.ends_on}T00:00:00Z`)) / 86_400_000)
  return { startsOn, endsOn, day }
})
const upcomingRaceEntries = computed(() => raceEntries.value.filter((race) => race.date >= todayIsoDate.value))
const dataSourceNeedsAttention = computed(() =>
  Boolean(
    garminConnection.value &&
      (garminConnection.value.credential_status === 'requires_reauth' || garminConnection.value.sync_status === 'failed'),
  ),
)
const recoveryFooterText = computed(() => {
  if (unavailableSignals.value.length) {
    return `${unavailableSignals.value.length} 個訊號待補，包含${formatUnavailableSignal(unavailableSignals.value[0])}`
  }
  if (hasActiveDataProvider.value && !dataSourceNeedsAttention.value) {
    return 'Garmin 已同步'
  }
  return ''
})
const recoveryDecision = computed(() => buildRecoveryDecision(recommendation.value, recoveryEvidence.value))
const dailyAdvice = computed(() => apiDailyAdvice.value?.adviceDate === todayIsoDate.value ? apiDailyAdvice.value : null)
const todayDecision = computed<TodayDecision>(() => {
  const decision = dailyAdvice.value ? buildAdviceDecision(dailyAdvice.value) : buildTodayDecision(recommendation.value, recoveryEvidence.value)
  if (decision.state === 'run') {
    return { ...decision, actionLabel: hasWorkoutDetails(todayWorkout.value) ? '查看課表細節' : '查看計畫' }
  }
  return { ...decision, actionLabel: dailyAdvice.value ? '查看 Johnny 建議' : recommendation.value?.status === 'pending' ? '查看待決定建議' : '查看計畫' }
})
const todayEvidenceChips = computed(() => recoveryEvidence.value.slice(0, 3))
const currentPlanPhase = computed(() => journeyPhases.value.find((phase) => phase.status === 'current') ?? (recoveryWindow.value ? {
  label: '恢復週 · Recovery Window', summary: `上一份計畫已結束，安排七天恢復。第 ${recoveryWindow.value.day} / 7 天`,
} : { label: journeyPhases.value.length ? '計畫尚未開始' : '尚無有效訓練計畫', summary: journeyPhases.value.length ? '接下來的訓練階段已排定。' : '請重新產生計畫，安排接下來的訓練。' }))
const signalCoverageSummary = computed(() => `Johnny 已有 ${coveredSignalCount.value}/${signalCoverage.value.length} 個訓練訊號`)
const weeklyActivityPoints = computed(() => fixtureWeeklyActivity)
const maxWeeklyDistance = computed(() => Math.max(...weeklyActivityPoints.value.map((point) => point.distanceKm), 1))
const athleteTimezoneOptions = computed(() => {
  const currentTimezone = athleteSettings.value.timezone
  if (currentTimezone && !timezoneOptions.some((option) => option.value === currentTimezone)) {
    return [{ value: currentTimezone, label: `${currentTimezone}（目前）` }, ...timezoneOptions]
  }
  return timezoneOptions
})
const todayRecommendationStrip = computed(() =>
  buildTodayRecommendationStrip(
    recommendation.value,
    recoveryDecision.value.label,
    recoveryEvidence.value,
    todayWorkout.value,
    hasActiveDataProvider.value,
    dataSourceNeedsAttention.value,
  ),
)
const raceTrainingRationale = computed(() => buildRaceTrainingRationale(todayWorkout.value))
const selectedWorkoutId = ref<string | null>(null)
const selectedWorkoutDetail = computed(() => {
  const id = selectedWorkoutId.value
  if (!id) {
    return null
  }
  return [todayWorkout.value, ...displayWorkouts.value].find((workout) => workout.id === id) ?? null
})
const selectedWorkoutRows = computed(() => (selectedWorkoutDetail.value ? buildWorkoutStepRows(selectedWorkoutDetail.value.steps ?? [], selectedWorkoutDetail.value.workoutType) : []))
const selectedWorkoutStages = computed(() => {
  const stages: Array<{ key: WorkoutStageKey; label: string; rows: WorkoutStepRow[] }> = []
  for (const row of selectedWorkoutRows.value) {
    const last = stages[stages.length - 1]
    if (last?.key === row.stage) last.rows.push(row)
    else stages.push({ key: row.stage, label: workoutStageLabel(row.stage), rows: [row] })
  }
  return stages
})

type RecoveryDecision = {
  label: '可以照課表' | '建議保守' | '建議休息'
  tone: 'success' | 'warning' | 'danger'
}

type TodayRecommendationStrip = {
  summary: string
  actionLabel?: string
  actionView?: ViewKey
  actionTone?: 'primary' | 'neutral'
}

type WorkoutStepRow = {
  key: string
  label: string
  load: string
  target: string
  note: string
  depth: number
  stage: WorkoutStageKey
}

type WorkoutStageKey = 'warmup' | 'main' | 'recovery' | 'cooldown'

type PlanPhaseTimelineSegment = {
  phase: TrainingPlanPhase
  label: string
  focus: string
  dateRange: string
}

const demoPlanPhases: PlanPhaseTimelineSegment[] = [
  { phase: 'base', label: '基礎期', focus: '建立輕鬆跑與長跑節奏', dateRange: '8/3 - 8/16' },
  { phase: 'build', label: '建立期', focus: '逐步提高品質課表比重', dateRange: '8/17 - 8/23' },
  { phase: 'peak', label: '高峰期', focus: '完成關鍵長跑與配速練習', dateRange: '8/24 - 8/29' },
  { phase: 'taper', label: '減量期', focus: '保留節奏，降低疲勞', dateRange: '8/30 - 9/5' },
]

type AthleteSettingsForm = {
  timezone: string
  experienceLevel: '' | 'beginner' | 'intermediate' | 'advanced'
  currentWeeklyMileage: string
  preferredTrainingDays: string[]
  preferredLongRunDay: string
  maxRunsPerWeek: string
  maxHardSessionsPerWeek: string
  thresholdPace: string
  thresholdPaceSource: 'manual' | 'garmin'
  unitPreference: 'metric' | 'imperial'
  injuryStatus: 'none' | 'current' | 'recent' | 'recurring'
  injuryAreas: string[]
  injuryNotes: string
}

const weekDayOptions = [
  { value: 'monday', label: '週一' },
  { value: 'tuesday', label: '週二' },
  { value: 'wednesday', label: '週三' },
  { value: 'thursday', label: '週四' },
  { value: 'friday', label: '週五' },
  { value: 'saturday', label: '週六' },
  { value: 'sunday', label: '週日' },
]
const injuryAreaOptions = [
  { value: 'knee', label: '膝蓋' },
  { value: 'calf', label: '小腿' },
  { value: 'shin', label: '脛骨' },
  { value: 'ankle', label: '腳踝' },
  { value: 'foot', label: '足部' },
  { value: 'hamstring', label: '腿後肌' },
  { value: 'quad', label: '股四頭肌' },
  { value: 'hip', label: '髖部' },
  { value: 'back', label: '背部' },
  { value: 'other', label: '其他' },
]
const KILOMETERS_PER_MILE = 1.60934

function buildTodayDecision(recommendation: RecommendationSummary | null, evidence: EvidenceItem[]): TodayDecision {
  const hasDangerEvidence = evidence.some((item) => item.tone === 'danger')
  const hasWarningEvidence = evidence.some((item) => item.tone === 'warning')
  const pendingRecommendation = recommendation?.status === 'pending' ? recommendation : null
  const hasWarningRecommendation = pendingRecommendation?.priority === 'warning' || pendingRecommendation?.priority === 'danger'
  const actionLabel = pendingRecommendation ? '查看待決定建議' : '查看計畫'

  if (hasDangerEvidence || pendingRecommendation?.priority === 'danger') {
    return {
      state: 'rest',
      label: '先收一下',
      actionLabel,
      tone: 'rest',
      voice: '今天不要硬撐，跑鞋先放假。',
      memoryInsight: '依照你過去的恢復模式，今天建議保守。',
    }
  }

  if (hasWarningEvidence || hasWarningRecommendation) {
    return {
      state: 'adjust',
      label: '不太對勁',
      actionLabel,
      tone: 'adjust',
      voice: '今天先穩住節奏，保留訓練目的就好。',
      memoryInsight: '依照你過去的恢復模式，今天建議保守。',
    }
  }

  return {
    state: 'run',
    label: '我可以',
    actionLabel: '查看計畫',
    tone: 'run',
    voice: '狀態可以，照計畫跑，節奏不要偷加。',
  }
}

function buildAdviceDecision(advice: DailyAdvice): TodayDecision {
  if (advice.state !== 'ready' || advice.dataFreshness === 'stale' || !advice.executionMode) {
    return {
      state: 'adjust', label: '建議更新中', actionLabel: '查看 Johnny 建議', tone: 'adjust',
      voice: '今天的建議還在更新，先依課表與身體感受保守執行。',
    }
  }
  if (advice.executionMode === 'completed') {
    return { state: 'completed', label: '今天已完成', actionLabel: '查看 Johnny 建議', tone: 'completed', voice: advice.todayExecution || '今天的訓練已完成。' }
  }
  if (advice.executionMode === 'rest') {
    return { state: 'rest', label: '先收一下', actionLabel: '查看 Johnny 建議', tone: 'rest', voice: advice.todayExecution || '今天先休息。' }
  }
  if (advice.executionMode === 'ease_off') {
    return { state: 'adjust', label: '不太對勁', actionLabel: '查看 Johnny 建議', tone: 'adjust', voice: advice.todayExecution || '今天保守執行。' }
  }
  return { state: 'run', label: '我可以', actionLabel: '查看計畫', tone: 'run', voice: advice.todayExecution || '照計畫執行。' }
}

function buildRecoveryDecision(
  currentRecommendation: RecommendationSummary | null,
  evidence: EvidenceItem[],
): RecoveryDecision {
  if (currentRecommendation?.priority === 'danger') {
    return { label: '建議休息', tone: 'danger' }
  }
  if (currentRecommendation?.priority === 'warning') {
    return { label: '建議保守', tone: 'warning' }
  }
  if (evidence.some((item) => item.tone === 'danger')) {
    return { label: '建議休息', tone: 'danger' }
  }
  if (evidence.some((item) => item.tone === 'warning')) {
    return { label: '建議保守', tone: 'warning' }
  }
  return { label: '可以照課表', tone: 'success' }
}

function buildTodayRecommendationStrip(
  currentRecommendation: RecommendationSummary | null,
  recoveryLabel: RecoveryDecision['label'],
  evidence: EvidenceItem[],
  workout: WorkoutSummary,
  hasConnectedSource: boolean,
  sourceNeedsAttention: boolean,
): TodayRecommendationStrip {
  if (currentRecommendation?.status === 'pending') {
    return {
      summary: currentRecommendation.title,
      actionLabel: '查看待決定建議',
      actionView: 'johnny',
      actionTone: 'primary',
    }
  }
  if (!evidence.length || workout.status === 'empty') {
    return {
      summary: '目前資料不足，連接睡眠或 HRV 後 Johnny 會給出更穩定判斷。',
      actionLabel: sourceNeedsAttention ? '檢查資料' : hasConnectedSource ? undefined : '連接資料',
      actionView: sourceNeedsAttention || !hasConnectedSource ? 'data' : undefined,
      actionTone: 'neutral',
    }
  }
  return {
    summary: recoveryLabel === '可以照課表' ? '目前可以照課表執行，Johnny 沒有新的待決定調整。' : '目前沒有新的待決定調整，請依恢復狀態保守執行。',
    actionLabel: '查看 Johnny 建議',
    actionView: 'johnny',
    actionTone: 'neutral',
  }
}

function buildRaceTrainingRationale(workout: WorkoutSummary): string {
  if (workout.status === 'empty') {
    return '設定目標與課表後，Johnny 會說明今天如何服務下一場比賽。'
  }
  if (workout.type.includes('Easy')) {
    return '今天的輕鬆跑是為了累積有氧基礎，不是測驗速度。'
  }
  if (workout.type.includes('Tempo')) {
    return '今天的節奏課是為了穩定比賽配速，重點是控制強度。'
  }
  if (workout.type.includes('Long')) {
    return '今天的長距離是為了建立後段耐力，配速應該保留餘裕。'
  }
  return `今天的${workout.type}會服務下一場目標，請用恢復狀態決定執行強度。`
}

function buildRecoveryEvidenceItems(recovery: Record<string, unknown>, trainingLoad: Record<string, unknown> | undefined): EvidenceItem[] {
  const evidence = asRecord(recovery.evidence)
  const items = [
    buildHrvEvidence(recovery, asRecord(evidence?.hrv)),
    buildSleepEvidence(recovery, asRecord(evidence?.sleep)),
    buildRestingHeartRateEvidence(recovery, asRecord(evidence?.resting_heart_rate)),
    buildBodyBatteryEvidence(recovery, asRecord(evidence?.body_battery)),
    buildStressEvidence(recovery, asRecord(evidence?.stress)),
    buildTrainingLoadEvidence(trainingLoad),
  ]
  return items.filter((item): item is EvidenceItem => item !== null)
}

function buildHrvEvidence(recovery: Record<string, unknown>, evidence: Record<string, unknown> | undefined): EvidenceItem | null {
  const value = numberValue(evidence?.value ?? recovery.hrv_ms)
  const delta = numberValue(recovery.hrv_delta_percentage)
  if (value === null) {
    return null
  }
  return {
    source: 'Garmin',
    metric: 'HRV',
    value: `${formatNumber(value)} ms`,
    summary: delta === null ? '尚未建立基準變化' : `${delta < 0 ? '低於' : '高於'}基準 ${formatNumber(Math.abs(delta))}%`,
    tone: recoveryTone(evidence?.level, delta !== null && delta < -10),
  }
}

function buildSleepEvidence(recovery: Record<string, unknown>, evidence: Record<string, unknown> | undefined): EvidenceItem | null {
  const sleepMinutes = numberValue(evidence?.value ?? recovery.sleep_minutes ?? recovery.sleep_duration_minutes)
  const sleepDebt = numberValue(recovery.sleep_debt_minutes)
  if (sleepMinutes === null) {
    return null
  }
  return {
    source: 'Garmin',
    metric: '睡眠',
    value: formatDuration(sleepMinutes),
    summary: sleepDebt === null ? '尚未建立睡眠目標差距' : sleepDebt > 0 ? `少 ${formatDuration(sleepDebt)}` : '達到目標睡眠',
    tone: recoveryTone(evidence?.level, sleepDebt !== null && sleepDebt > 60),
  }
}

function buildRestingHeartRateEvidence(recovery: Record<string, unknown>, evidence: Record<string, unknown> | undefined): EvidenceItem | null {
  const delta = numberValue(recovery.resting_heart_rate_delta_bpm)
  const value = numberValue(evidence?.value ?? recovery.resting_heart_rate)
  if (delta === null && value === null) {
    return null
  }
  return {
    source: 'Garmin',
    metric: '靜息心率',
    value: value === null ? `${formatSignedNumber(delta || 0)} bpm` : `${formatNumber(value)} bpm`,
    summary: delta === null ? '尚未建立基準變化' : delta > 0 ? `高於基準 ${formatNumber(delta)} bpm` : delta < 0 ? `低於基準 ${formatNumber(Math.abs(delta))} bpm` : '接近基準',
    tone: recoveryTone(evidence?.level, delta !== null && delta >= 5),
  }
}

function buildBodyBatteryEvidence(recovery: Record<string, unknown>, evidence: Record<string, unknown> | undefined): EvidenceItem | null {
  const value = numberValue(evidence?.value ?? recovery.body_battery_score)
  if (value === null) {
    return null
  }
  return {
    source: 'Garmin',
    metric: 'Body Battery',
    value: formatNumber(value),
    summary: value < 40 ? '能量偏低' : '能量可用',
    tone: recoveryTone(evidence?.level, value < 40),
  }
}

function buildStressEvidence(recovery: Record<string, unknown>, evidence: Record<string, unknown> | undefined): EvidenceItem | null {
  const value = numberValue(evidence?.value ?? recovery.stress_score)
  if (value === null) {
    return null
  }
  return {
    source: 'Garmin',
    metric: '壓力',
    value: formatNumber(value),
    summary: value >= 70 ? '壓力偏高' : '壓力可控',
    tone: recoveryTone(evidence?.level, value >= 70),
  }
}

function buildTrainingLoadEvidence(trainingLoad: Record<string, unknown> | undefined): EvidenceItem | null {
  if (!trainingLoad) {
    return null
  }
  const ratio = numberValue(trainingLoad.acute_chronic_ratio)
  if (ratio === null) {
    return null
  }
  return {
    source: 'Johnny Analytics',
    metric: '負荷比',
    value: `${formatNumber(ratio)}x`,
    summary: ratio > 1.3 ? '短期負荷偏高' : '負荷穩定',
    tone: ratio > 1.5 ? 'danger' : ratio > 1.3 ? 'warning' : 'info',
  }
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

function numberValue(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : Number.NaN
  return Number.isFinite(numeric) ? numeric : null
}

function formatNumber(value: number | null): string {
  if (value === null) {
    return ''
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function formatSignedNumber(value: number): string {
  return `${value > 0 ? '+' : ''}${formatNumber(value)}`
}

function formatDuration(minutes: number): string {
  const rounded = Math.max(0, Math.round(minutes))
  const hours = Math.floor(rounded / 60)
  const remainingMinutes = rounded % 60
  if (!hours) {
    return `${remainingMinutes} 分`
  }
  return remainingMinutes ? `${hours} 小時 ${remainingMinutes} 分` : `${hours} 小時`
}

function recoveryTone(level: unknown, fallbackWarning: boolean): EvidenceItem['tone'] {
  if (level === 'rest') {
    return 'danger'
  }
  if (level === 'caution' || fallbackWarning) {
    return 'warning'
  }
  return 'info'
}

function formatUnavailableSignal(signal: string): string {
  const signalLabels: Record<string, string> = {
    hrv_delta_percentage: 'HRV',
    sleep_debt_minutes: '睡眠資料',
    resting_heart_rate_baseline: '靜息心率',
    acute_chronic_ratio: '負荷比',
    chronic_load: '長期負荷',
    mileage_ramp_percentage: '里程變化',
  }
  return signalLabels[signal] || signal
}

function normalizeSignalKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function isSignalUnavailable(signal: 'sleep' | 'hrv' | 'resting_heart_rate' | 'training_load'): boolean {
  const aliases: Record<typeof signal, string[]> = {
    sleep: ['sleep', 'sleep_debt_minutes', 'sleep_duration_minutes', 'sleep_quality'],
    hrv: ['hrv', 'hrv_delta_percentage', 'hrv_status'],
    resting_heart_rate: ['resting_heart_rate', 'resting_hr', 'resting_heart_rate_baseline', '靜息心率'],
    training_load: ['training_load', 'acute_chronic_ratio', 'chronic_load', 'mileage_ramp_percentage', 'load'],
  }
  const keys = [...unavailableSignalKeys.value]
  return aliases[signal].some((alias) => keys.some((key) => key === alias || key.includes(alias)))
}

function updateDocumentTitle(label: string) {
  if (typeof document !== 'undefined') {
    document.title = `${label} — Johnny`
  }
}

async function initializeAuth() {
  const session = sessionGeneration
  if (!shouldRequireAuth()) {
    authStatus.value = 'authenticated'
    await hydrateFromBackend()
    return
  }

  authStatus.value = 'checking'
  authError.value = ''
  try {
    const response = await getCurrentUser()
    if (isUnmounted || session !== sessionGeneration) return
    currentUser.value = response.data
    authStatus.value = 'authenticated'
    await hydrateFromBackend()
  } catch (error) {
    if (isUnmounted || session !== sessionGeneration) return
    authStatus.value = 'anonymous'
    authError.value = error instanceof ApiRequestError && error.status === 401 ? '' : '登入狀態檢查失敗，請重新登入。'
  }
}

function selectAuthMode(mode: 'login' | 'signup') {
  authMode.value = mode
  authError.value = ''
  authMessage.value = ''
}

async function submitAuth() {
  authError.value = ''
  authMessage.value = ''
  const email = authEmail.value.trim()
  const password = authPassword.value
  if (!email || !password) {
    authError.value = '請輸入 Email 與密碼'
    return
  }
  if (password.length < 8) {
    authError.value = '密碼至少需要 8 個字元'
    return
  }
  if (authMode.value === 'signup') {
    if (!authDisplayName.value.trim()) {
      authError.value = '請輸入顯示名稱'
      return
    }
    if (authPasswordConfirm.value !== password) {
      authError.value = '兩次輸入的密碼不一致'
      return
    }
  }

  authBusy.value = true
  const session = ++sessionGeneration
  trainingReadVersion += 1
  trainingReadPending = false
  try {
    const response =
      authMode.value === 'signup'
        ? await signUpWithEmail({ display_name: authDisplayName.value.trim(), email, password })
        : await signInWithEmail({ email, password })
    if (isUnmounted || session !== sessionGeneration) return
    hasBackendHydrated.value = false
    todayPayloadDate.value = ''
    currentUser.value = response.data.user
    authDisplayName.value = response.data.user.display_name || authDisplayName.value
    authPassword.value = ''
    authPasswordConfirm.value = ''
    authStatus.value = 'authenticated'
    authMessage.value = authMode.value === 'signup' ? '帳號已建立' : '已登入'
    await hydrateFromBackend()
  } catch (error) {
    if (isUnmounted || session !== sessionGeneration) return
    authError.value = error instanceof ApiRequestError && error.status === 401 ? 'Email 或密碼不正確' : '登入失敗，請檢查資料後再試。'
  } finally {
    authBusy.value = false
  }
}

async function handleGoogleSignIn() {
  authError.value = ''
  authBusy.value = true
  if (typeof window === 'undefined') {
    authBusy.value = false
    return
  }
  const callbackUrl = window.location.hash || '#today'
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  window.location.assign(
    getGoogleSignInRedirectUrl(
      callbackUrl,
      authMode.value === 'signup' ? authDisplayName.value.trim() || undefined : undefined,
      window.location.origin,
      timezone,
    ),
  )
}

async function handleSignOut() {
  stopPlanRegenerationObservation()
  await signOut()
  currentUser.value = null
  authStatus.value = shouldRequireAuth() ? 'anonymous' : 'authenticated'
}

function handleSessionExpiry(error: unknown): boolean {
  if (shouldRequireAuth() && error instanceof ApiRequestError && error.status === 401) {
    stopPlanRegenerationObservation()
    currentUser.value = null
    authStatus.value = 'anonymous'
    authError.value = '登入已過期，請重新登入。'
    return true
  }
  return false
}

function showView(view: ViewKey) {
  activeView.value = view
  if (typeof window !== 'undefined') {
    window.history.replaceState(null, '', `#${view}`)
  }
}

function handleTodayDecisionAction() {
  if (todayDecision.value.state === 'run') {
    if (hasWorkoutDetails(todayWorkout.value)) {
      openWorkoutDetails(todayWorkout.value)
      return
    }
    showView('plan')
    return
  }
  showView(dailyAdvice.value || recommendation.value?.status === 'pending' ? 'johnny' : 'plan')
}

async function handleAccept() {
  const currentRecommendation = recommendation.value
  if (!currentRecommendation) {
    return
  }
  busyAction.value = 'accept'
  try {
    await acceptRecommendation(currentRecommendation.id)
    recommendationStatus.value = 'accepted'
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    busyAction.value = ''
  }
}

async function handleKeepOriginal() {
  const currentRecommendation = recommendation.value
  if (!currentRecommendation) {
    return
  }
  busyAction.value = 'keep'
  try {
    await rejectRecommendation(currentRecommendation.id)
    recommendationStatus.value = 'kept'
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    busyAction.value = ''
  }
}

async function handleDiscuss() {
  const currentRecommendation = recommendation.value
  if (!currentRecommendation) {
    return
  }
  busyAction.value = 'discuss'
  try {
    await discussRecommendation(currentRecommendation.id, '我想了解這次調整的原因。')
    linkedRecommendation.value = {
      id: currentRecommendation.id,
      title: currentRecommendation.title,
      status: 'pending',
      statusLabel: '待決定',
      evidenceSummary: 'HRV -18% · 7 日負荷 +21%',
      evidence: recoveryEvidence.value,
    }
    showView('conversation')
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    busyAction.value = ''
  }
}

function handleEdit() {
  providerMessage.value = '編輯調整會在下一階段加入完整表單。'
}

function selectProvider(provider: ProviderOption) {
  selectedProvider.value = provider
  providerError.value = ''
  pendingDisconnectConnectionId.value = ''
  if (provider.id === 'garmin_connect' && garminConnection.value?.credential_status === 'requires_reauth') {
    providerMessage.value = '請重新輸入 Garmin 電子郵件與密碼後連接。'
    isProviderDialogOpen.value = true
    return
  }
  if (provider.id === 'garmin_connect') {
    isProviderDialogOpen.value = true
  }
  providerMessage.value = ''
}

function closeProviderDialog() {
  if (providerBusy.value === 'connect') {
    return
  }
  isProviderDialogOpen.value = false
  providerError.value = ''
  garminPassword.value = ''
}

async function submitProvider() {
  if (providerBusy.value) {
    return
  }
  providerError.value = ''
  providerMessage.value = ''
  pendingDisconnectConnectionId.value = ''
  if (selectedProvider.value.id !== 'garmin_connect') {
    providerError.value = '這個資料整合尚未開放。'
    return
  }
  if (!garminEmail.value.trim()) {
    providerError.value = '請輸入 Garmin 電子郵件'
    return
  }
  if (!garminPassword.value) {
    providerError.value = '請輸入 Garmin 密碼'
    return
  }
  try {
    providerBusy.value = 'connect'
    const response = await connectGarminIntegration({
      email: garminEmail.value.trim(),
      password: garminPassword.value,
      region: garminRegion.value,
    })
    garminConnection.value = response.data
    await refreshGarminTrainingEvidence()
    providerMessage.value = `${response.data.provider_display_name || 'Garmin'} 已連接`
    await refreshCalendarPayloads(todayIsoDate.value)
    if (response.data.daily_advice_run) observeDailyAdviceRun(response.data.daily_advice_run.run_id)
    isProviderDialogOpen.value = false
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      providerError.value = 'Garmin 連接失敗。請檢查登入資料後再試一次。'
    }
  } finally {
    garminPassword.value = ''
    providerBusy.value = ''
  }
}

async function syncGarminConnection(connection: IntegrationConnectionResponse) {
  if (providerBusy.value || connection.credential_status === 'requires_reauth' || connection.status === 'disconnected') {
    return
  }
  providerError.value = ''
  providerMessage.value = ''
  pendingDisconnectConnectionId.value = ''
  providerBusy.value = 'sync'
  try {
    const response = await syncIntegrationConnection(connection.id)
    garminConnection.value = response.data
    await refreshGarminTrainingEvidence()
    sessionReviewsRefreshKey.value += 1
    providerMessage.value = response.data.has_partial_failures ? 'Garmin 手動同步完成，部分資料需要處理。' : 'Garmin 手動同步完成'
    await refreshCalendarPayloads(todayIsoDate.value)
    if (response.data.daily_advice_run) observeDailyAdviceRun(response.data.daily_advice_run.run_id)
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      providerError.value = error instanceof ApiRequestError && error.status === 409 ? 'Garmin 同步已在進行中，請稍後再試。' : 'Garmin 手動同步失敗。請稍後再試。'
      await refreshCalendarPayloads(todayIsoDate.value)
    }
  } finally {
    providerBusy.value = ''
  }
}

async function handleSessionReviewChanged(result: SessionReviewSaveResult) {
  const session = sessionGeneration
  if (apiDailyAdvice.value) apiDailyAdvice.value = { ...apiDailyAdvice.value, state: 'pending', dataFreshness: 'stale' }
  await refreshCalendarPayloads(todayIsoDate.value)
  if (isUnmounted || session !== sessionGeneration) return
  const refresh = result.refresh_runs?.find(run => run.anchor_date === todayIsoDate.value)
  if (refresh) observeDailyAdviceRun(refresh.run_id)
}

function stopDailyAdviceObservation() {
  advicePollGeneration += 1
  if (advicePollTimer) clearTimeout(advicePollTimer)
  advicePollTimer = undefined
  advicePollAttempts = 0
}

function observeDailyAdviceRun(runId: string) {
  stopDailyAdviceObservation()
  const observation = advicePollGeneration
  const session = sessionGeneration
  const anchorDate = todayIsoDate.value
  const poll = async () => {
    if (isUnmounted || observation !== advicePollGeneration || session !== sessionGeneration) return
    advicePollAttempts += 1
    try {
      const response = await getAgentRun(runId)
      if (isUnmounted || observation !== advicePollGeneration || session !== sessionGeneration) return
      if (response.data.status === 'completed' || response.data.status === 'failed') {
        if (anchorDate === todayIsoDate.value) await refreshCalendarPayloads(anchorDate)
        return
      }
    } catch (error) {
      if (handleSessionExpiry(error)) return
    }
    if (advicePollAttempts < 20) advicePollTimer = setTimeout(() => { void poll() }, Math.min(30_000, 2_000 * advicePollAttempts))
  }
  advicePollTimer = setTimeout(() => { void poll() }, 2_000)
}

function requestDisconnectGarmin(connection: IntegrationConnectionResponse) {
  if (providerBusy.value || connection.status === 'disconnected') {
    return
  }
  providerError.value = ''
  providerMessage.value = ''
  pendingDisconnectConnectionId.value = connection.id
}

function cancelDisconnectGarmin() {
  pendingDisconnectConnectionId.value = ''
}

async function confirmDisconnectGarmin(connection: IntegrationConnectionResponse) {
  if (providerBusy.value || pendingDisconnectConnectionId.value !== connection.id) {
    return
  }
  providerError.value = ''
  providerMessage.value = ''
  providerBusy.value = 'disconnect'
  try {
    const response = await disconnectIntegrationConnection(connection.id)
    garminConnection.value = response.data
    garminTrainingEvidence.value = {}
    await refreshCalendarPayloads(todayIsoDate.value)
    providerMessage.value = 'Garmin 已中斷連接；歷史匯入資料會保留。'
    pendingDisconnectConnectionId.value = ''
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      providerError.value = 'Garmin 中斷連接失敗。請稍後再試。'
    }
  } finally {
    providerBusy.value = ''
  }
}

function garminStatus(connection: IntegrationConnectionResponse | null): {
  label: string
  tone: 'info' | 'warning' | 'danger' | 'success'
} {
  if (connection?.credential_status === 'requires_reauth') {
    return { label: '已連接，需要重新登入', tone: 'warning' }
  }
  if (connection?.has_partial_failures) {
    return { label: '部分資料同步失敗', tone: 'warning' }
  }
  if (connection) {
    return { label: '初始同步完成', tone: 'success' }
  }
  return { label: '等待連接', tone: 'info' }
}

function garminSyncRows(connection: IntegrationConnectionResponse | null): string[] {
  const resources = connection?.sync_summary?.resources
  if (!resources) {
    return []
  }
  return Object.entries(resources).map(([resource, summary]) => formatSyncResource(resource, summary))
}

function providerConnection(provider: ProviderOption): IntegrationConnectionResponse | null {
  return provider.id === 'garmin_connect' ? garminConnection.value : null
}

function providerSyncRows(provider: ProviderOption): string[] {
  return provider.id === 'garmin_connect' ? garminSyncRows(garminConnection.value) : []
}

function providerLastSyncLabel(provider: ProviderOption): string {
  if (provider.id !== 'garmin_connect') {
    return ''
  }
  return formatLastSyncLabel(garminConnection.value)
}

function providerBusyAction(provider: ProviderOption): '' | 'connect' | 'sync' | 'disconnect' {
  return provider.id === 'garmin_connect' ? providerBusy.value : ''
}

function isDisconnectConfirming(provider: ProviderOption): boolean {
  return provider.id === 'garmin_connect' && Boolean(garminConnection.value?.id && pendingDisconnectConnectionId.value === garminConnection.value.id)
}

function formatLastSyncLabel(connection: IntegrationConnectionResponse | null): string {
  const value = connection?.last_sync_completed_at || connection?.last_sync_started_at
  if (!value) {
    return '尚未同步'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '尚未同步'
  }
  return `上次同步：${date.toLocaleString('zh-TW', {
    timeZone: userTimezone.value,
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

function formatSyncResource(resource: string, summary: SyncResourceSummary): string {
  const parts = [`取得 ${summary.fetched ?? 0}`, `新增 ${summary.stored ?? 0}`]
  if (summary.duplicates) {
    parts.push(`重複 ${summary.duplicates}`)
  }
  if (summary.failed) {
    parts.push(`失敗 ${summary.failed}`)
  }
  return `${syncResourceLabel(resource)}：${parts.join('，')}`
}

function syncResourceLabel(resource: string): string {
  const labels: Record<string, string> = {
    activities: '活動',
    sleep: '睡眠',
    hrv: 'HRV',
    resting_heart_rate: '靜息心率',
    stress: '壓力',
    body_battery: 'Body Battery',
  }
  return labels[resource] || resource
}

function statusTone(status: RecommendationStatus): 'info' | 'warning' | 'danger' | 'success' {
  if (status === 'pending') {
    return 'warning'
  }
  if (status === 'accepted' || status === 'applied') {
    return 'success'
  }
  if (status === 'rejected' || status === 'expired') {
    return 'danger'
  }
  return 'info'
}

function priorityTone(priority: InboxRecommendation['priority']): 'info' | 'warning' | 'danger' | 'success' {
  if (priority === 'high') {
    return 'danger'
  }
  if (priority === 'medium') {
    return 'warning'
  }
  return 'info'
}

function recommendationPriorityTone(priority: InboxRecommendation['priority']): RecommendationSummary['priority'] {
  if (priority === 'high') {
    return 'danger'
  }
  if (priority === 'medium') {
    return 'warning'
  }
  return 'info'
}

function selectThread(threadId: string) {
  activeThreadId.value = threadId
  conversationError.value = ''
  conversationStatus.value = ''
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || isComposing.value || event.isComposing) {
    return
  }
  event.preventDefault()
  void submitConversation()
}

async function submitConversation() {
  const content = conversationMessage.value.trim()
  conversationError.value = ''
  conversationStatus.value = ''
  if (!content) {
    conversationError.value = '請輸入想問 Johnny 的問題'
    return
  }

  conversationBusy.value = true
  try {
    const response = await submitConversationMessage(content)
    const runRef = response.data.run_ref
    conversationMessage.value = ''
    conversationStatus.value = runRef ? `Johnny 已收到問題 · ${runRef}` : 'Johnny 已收到問題'
    appendConversationMessages(content, response)
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      conversationError.value = '訊息送出失敗，請稍後再試。'
    }
  } finally {
    conversationBusy.value = false
  }
}

async function handleInboxAccept(item: InboxRecommendation) {
  inboxBusyRecommendationId.value = item.id
  inboxBusyAction.value = 'accept'
  try {
    await acceptRecommendation(item.id)
    recommendationDecisions.value = { ...recommendationDecisions.value, [item.id]: 'accepted' }
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    inboxBusyRecommendationId.value = ''
    inboxBusyAction.value = ''
  }
}

async function handleInboxKeep(item: InboxRecommendation) {
  inboxBusyRecommendationId.value = item.id
  inboxBusyAction.value = 'keep'
  try {
    await rejectRecommendation(item.id)
    recommendationDecisions.value = { ...recommendationDecisions.value, [item.id]: 'rejected' }
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    inboxBusyRecommendationId.value = ''
    inboxBusyAction.value = ''
  }
}

function handleActionPlaceholder() {
  providerMessage.value = '這個決策會在下一階段同步到訓練計畫。'
}

watch(() => activePlan.value?.id, (id, previousId) => {
  if (id !== previousId) racePlanReminder.value = ''
})

function openRaceGoalModal(event?: MouseEvent) {
  if (raceGoalBusy.value || raceEditLoading.value) return
  raceReturnFocus = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null
  editingRace.value = null
  raceFormError.value = ''
  isRaceGoalModalOpen.value = true
}

async function editRaceEntry(race: RaceSummary, event?: MouseEvent) {
  if (raceGoalBusy.value || raceEditLoading.value) return
  raceReturnFocus = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null
  raceActionError.value = ''
  raceFormError.value = ''
  raceEditLoading.value = true
  const session = sessionGeneration
  try {
    const response = await getRaceGoal(race.id)
    if (isUnmounted || session !== sessionGeneration) return
    editingRace.value = { id: race.id, values: response.data }
    isRaceGoalModalOpen.value = true
  } catch (error) {
    if (!isUnmounted && session === sessionGeneration && !handleSessionExpiry(error)) {
      raceActionError.value = '載入賽事失敗，請再試一次。'
    }
  } finally {
    if (session === sessionGeneration) raceEditLoading.value = false
  }
}

function requestDeleteRace(race: RaceSummary) {
  if (raceGoalBusy.value || raceEditLoading.value) return
  raceDeleteError.value = ''
  deletingRace.value = race
}

function raceFallsInRemainingPlan(...dates: Array<string | undefined>): boolean {
  const plan = activePlan.value
  if (!plan) return false
  const remainingStart = plan.starts_on > todayIsoDate.value ? plan.starts_on : todayIsoDate.value
  return dates.some((date) => Boolean(date && date >= remainingStart && date <= plan.ends_on))
}

async function confirmDeleteRace() {
  const race = deletingRace.value
  if (!race || raceGoalBusy.value) return
  raceGoalBusy.value = true
  raceDeleteError.value = ''
  const session = sessionGeneration
  const affectsPlan = raceFallsInRemainingPlan(race.date)
  try {
    await deleteRaceGoal(race.id)
    if (isUnmounted || session !== sessionGeneration) return
    trainingReadVersion += 1
    raceEntries.value = raceEntries.value.filter((entry) => entry.id !== race.id)
    planRegenerationRaceOptions.value = planRegenerationRaceOptions.value.filter((entry) => entry.id !== race.id)
    if (apiRaceSummary.value?.id === race.id) apiRaceSummary.value = null
    deletingRace.value = null
    showRaceSuccess('賽事已刪除，既有課表與訓練紀錄已保留。')
    if (affectsPlan) racePlanReminder.value = '賽事已變更，目前課表仍保留原安排。請重新產生計畫，讓 Johnny 納入賽事。'
    await refreshCalendarPayloads(todayIsoDate.value)
    await nextTick()
    document.querySelector<HTMLButtonElement>('[data-testid="open-race-goal-modal"]')?.focus()
  } catch (error) {
    if (!isUnmounted && session === sessionGeneration && !handleSessionExpiry(error)) {
      raceDeleteError.value = '刪除賽事失敗，請再試一次。'
    }
  } finally {
    if (session === sessionGeneration) raceGoalBusy.value = false
  }
}

function showRaceSuccess(message: string) {
  raceFormMessage.value = message
  if (raceSuccessTimer) clearTimeout(raceSuccessTimer)
  raceSuccessTimer = setTimeout(() => { raceFormMessage.value = '' }, 3500)
}

async function openPlanRegenerationSheet(event?: MouseEvent) {
  const observation = planRegenerationObservation
  planRegenerationReturnFocus = event?.currentTarget instanceof HTMLElement ? event.currentTarget : document.activeElement instanceof HTMLElement ? document.activeElement : null
  isPlanRegenerationSheetOpen.value = true
  planRegenerationOptions.value = null
  planRegenerationError.value = ''
  planRegenerationLoading.value = true
  await nextTick()
  planRegenerationLoadingDialogRef.value?.querySelector<HTMLButtonElement>('button')?.focus()
  try {
    const anchorDate = todayIsoDate.value
    const [optionsResult, racesResult] = await Promise.allSettled([
      getTrainingPlanRegenerationOptions(),
      listRaceGoals(anchorDate),
    ])
    if (isUnmounted || observation !== planRegenerationObservation) return
    if (optionsResult.status === 'rejected') {
      throw optionsResult.reason
    }
    if (racesResult.status === 'fulfilled') {
      applyPlanRegenerationRaceGoalsPayload(Array.isArray(racesResult.value.data) ? racesResult.value.data : [])
    }
    planRegenerationOptions.value = optionsResult.value.data
    if (optionsResult.value.data.in_flight_run) {
      observePlanRegeneration(optionsResult.value.data.in_flight_run)
    }
  } catch (error) {
    if (isUnmounted || observation !== planRegenerationObservation) return
    if (!handleSessionExpiry(error)) {
      planRegenerationError.value = '無法取得重新產生選項，請稍後再試。'
    }
  } finally {
    planRegenerationLoading.value = false
  }
}

function closePlanRegenerationSheet() {
  if (planRegenerationBusy.value) {
    return
  }
  isPlanRegenerationSheetOpen.value = false
  void nextTick(() => planRegenerationReturnFocus?.focus())
}

async function confirmPlanRegeneration(payload: TrainingPlanRegenerationRequest) {
  const observation = planRegenerationObservation
  planRegenerationBusy.value = true
  planRegenerationError.value = ''
  try {
    const response = await startTrainingPlanRegeneration(payload)
    if (isUnmounted || observation !== planRegenerationObservation) return
    planRegenerationOptions.value = response.data
    const run = response.data.run ?? response.data.in_flight_run
    if (run) {
      observePlanRegeneration(run)
      isPlanRegenerationSheetOpen.value = false
      void nextTick(() => planRegenerationReturnFocus?.focus())
      return
    }
    planRegenerationError.value = '目前無法重新產生計畫，請等待下次可用時間。'
  } catch (error) {
    if (isUnmounted || observation !== planRegenerationObservation) return
    if (!handleSessionExpiry(error)) {
      planRegenerationError.value = '重新產生計畫失敗，請稍後再試。'
    }
  } finally {
    planRegenerationBusy.value = false
  }
}

function observePlanRegeneration(run: TrainingPlanRegenerationRun) {
  clearPlanRegenerationPollTimer()
  planRegenerationObservation += 1
  inFlightPlanRegeneration.value = run
  planRegenerationPollAttempts = 0
  schedulePlanRegenerationPoll(run.run_id, planRegenerationObservation)
}

function schedulePlanRegenerationPoll(runId: string, observation: number) {
  if (isUnmounted || observation !== planRegenerationObservation) return
  const delay = planRegenerationPollAttempts < regenerationFastPollCount ? regenerationPollIntervalMs : Math.min(30_000, regenerationPollIntervalMs * 2 ** Math.min(4, planRegenerationPollAttempts - regenerationFastPollCount + 1))
  planRegenerationPollTimer = setTimeout(() => {
    void pollPlanRegeneration(runId, observation)
  }, delay)
}

async function pollPlanRegeneration(runId: string, observation: number) {
  if (isUnmounted || observation !== planRegenerationObservation || inFlightPlanRegeneration.value?.run_id !== runId) {
    return
  }
  planRegenerationPollAttempts += 1
  try {
    const response = await getAgentRun(runId)
    if (isUnmounted || observation !== planRegenerationObservation || inFlightPlanRegeneration.value?.run_id !== runId) {
      return
    }
    if (response.data.status === 'completed') {
      inFlightPlanRegeneration.value = null
      await refreshCompletedPlanRegeneration(observation)
      return
    }
    if (response.data.status === 'failed' || response.data.status === 'cancelled') {
      inFlightPlanRegeneration.value = null
      if (planRegenerationOptions.value) {
        planRegenerationOptions.value = { ...planRegenerationOptions.value, in_flight_run: null, run: null }
      }
      planRegenerationError.value = `${response.data.error_message || '重新產生計畫未完成。'} 已保留目前課表，請稍後重新產生計畫。`
      return
    }
  } catch (error) {
    if (isUnmounted || observation !== planRegenerationObservation) return
    if (handleSessionExpiry(error)) {
      return
    }
  }
  schedulePlanRegenerationPoll(runId, observation)
}

async function refreshCompletedPlanRegeneration(observation: number) {
  const read = beginTrainingRead(todayIsoDate.value)
  const [todayResult, plansResult, racesResult, optionsResult] = await Promise.allSettled([
    getTodayContext(read.anchorDate), listTrainingPlans(), listRaceGoals(read.anchorDate, sixMonthWindowEnd(read.anchorDate)), getTrainingPlanRegenerationOptions(),
  ])
  finishTrainingRead(read)
  if (!isCurrentTrainingRead(read) || observation !== planRegenerationObservation) {
    ensureCurrentToday()
    return
  }
  if ([todayResult, plansResult, racesResult, optionsResult].some((result) => result.status === 'rejected' && handleSessionExpiry(result.reason))) return
  publishTrainingRead(read, todayResult, plansResult, racesResult)
  if (plansResult.status === 'rejected') {
    planRegenerationError.value = '新的訓練計畫已完成，但暫時無法更新畫面。'
  }
  if (optionsResult.status === 'fulfilled') {
    planRegenerationOptions.value = optionsResult.value.data
  }
}

function clearPlanRegenerationPollTimer() {
  if (planRegenerationPollTimer) {
    clearTimeout(planRegenerationPollTimer)
    planRegenerationPollTimer = undefined
  }
}

function stopPlanRegenerationObservation() {
  stopDailyAdviceObservation()
  editingRace.value = null
  deletingRace.value = null
  isRaceGoalModalOpen.value = false
  isRaceGoalConfirmOpen.value = false
  raceGoalBusy.value = false
  raceEditLoading.value = false
  raceFormError.value = ''
  raceDeleteError.value = ''
  raceActionError.value = ''
  raceFormMessage.value = ''
  racePlanReminder.value = ''
  if (raceSuccessTimer) clearTimeout(raceSuccessTimer)
  sessionGeneration += 1
  garminTrainingEvidence.value = {}
  trainingReadVersion += 1
  trainingReadPending = false
  planRegenerationObservation += 1
  clearPlanRegenerationPollTimer()
  inFlightPlanRegeneration.value = null
  planRegenerationOptions.value = null
  isPlanRegenerationSheetOpen.value = false
}

function handlePlanRegenerationLoadingKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closePlanRegenerationSheet()
    return
  }
  if (event.key !== 'Tab' || !planRegenerationLoadingDialogRef.value) {
    return
  }
  const focusable = Array.from(planRegenerationLoadingDialogRef.value.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex]:not([tabindex="-1"])'))
  if (!focusable.length) {
    event.preventDefault()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function restoreRaceFocus() {
  void nextTick(() => {
    if (isUnmounted || activeView.value !== 'plan') return
    const target = raceReturnFocus?.isConnected ? raceReturnFocus : document.querySelector<HTMLButtonElement>('[data-testid="open-race-goal-modal"]')
    target?.focus()
  })
}

function requestCloseRaceGoalModal() {
  if (raceGoalBusy.value) return
  if (raceGoalModalRef.value?.isDirty) {
    isRaceGoalConfirmOpen.value = true
    return
  }
  isRaceGoalModalOpen.value = false
  restoreRaceFocus()
}

function cancelRaceGoalDiscard() {
  isRaceGoalConfirmOpen.value = false
}

function confirmRaceGoalDiscard() {
  isRaceGoalConfirmOpen.value = false
  isRaceGoalModalOpen.value = false
  restoreRaceFocus()
}

async function submitRaceEntry(payload: RaceGoalCreatePayload) {
  if (raceGoalBusy.value) return
  raceFormError.value = ''
  raceGoalBusy.value = true
  const session = sessionGeneration
  const editing = editingRace.value
  const affectsPlan = raceFallsInRemainingPlan(editing?.values.race_date, payload.race_date)
  try {
    const response = editing
      ? await updateRaceGoal(editing.id, { ...payload, status: editing.values.status })
      : await createRaceGoal(payload)
    if (isUnmounted || session !== sessionGeneration) return
    trainingReadVersion += 1
    const saved = mapRaceGoal(response.data)
    if (saved) {
      raceEntries.value = [...raceEntries.value.filter((race) => race.id !== saved.id), saved]
        .sort((a, b) => a.date.localeCompare(b.date))
      planRegenerationRaceOptions.value = [...planRegenerationRaceOptions.value.filter((race) => race.id !== saved.id), saved]
      if (apiRaceSummary.value?.id === saved.id) apiRaceSummary.value = saved
    }
    isRaceGoalModalOpen.value = false
    showRaceSuccess(editing ? '賽事已更新' : '賽事已新增')
    if (affectsPlan) racePlanReminder.value = '賽事已變更，目前課表仍保留原安排。請重新產生計畫，讓 Johnny 納入賽事。'
    await refreshCalendarPayloads(todayIsoDate.value)
  } catch (error) {
    if (!isUnmounted && session === sessionGeneration && !handleSessionExpiry(error)) {
      raceFormError.value = '賽事儲存失敗，請稍後再試。'
    }
  } finally {
    if (session === sessionGeneration) {
      raceGoalBusy.value = false
      if (!isRaceGoalModalOpen.value) restoreRaceFocus()
    }
  }
}

async function handleInboxDiscuss(item: InboxRecommendation) {
  linkedRecommendation.value = {
    id: item.id,
    title: item.title,
    status: item.status,
    statusLabel: item.statusLabel,
    evidenceSummary: item.evidence.map((evidence) => evidence.summary).join(' · '),
    evidence: item.evidence,
  }
  showView('conversation')
  inboxBusyRecommendationId.value = item.id
  conversationError.value = ''
  try {
    const response = await discussRecommendation(item.id, '我想了解這次建議的原因。')
    const runRef = (response as { data?: { run_ref?: string } }).data?.run_ref
    conversationStatus.value = runRef ? `Johnny 已開啟討論 · ${runRef}` : 'Johnny 已開啟討論'
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      conversationError.value = '討論原因送出失敗，請稍後再試。'
    }
  } finally {
    inboxBusyRecommendationId.value = ''
  }
}

onMounted(() => {
  calendarTimer = setInterval(refreshCalendarDate, 60_000)
  window.addEventListener('focus', refreshCalendarDate)
  void initializeAuth()
})

onUnmounted(() => {
  isUnmounted = true
  stopPlanRegenerationObservation()
  clearInterval(calendarTimer)
  if (raceSuccessTimer) clearTimeout(raceSuccessTimer)
  window.removeEventListener('focus', refreshCalendarDate)
})

function refreshCalendarDate() {
  calendarNow.value = new Date()
  const localHour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: userTimezone.value, hour: '2-digit', hourCycle: 'h23' }).format(calendarNow.value))
  const localMinute = Number(new Intl.DateTimeFormat('en-GB', { timeZone: userTimezone.value, minute: '2-digit' }).format(calendarNow.value))
  const morningCheck = `${todayIsoDate.value}:04`
  if ((localHour > 4 || (localHour === 4 && localMinute >= 5)) && lastMorningAdviceCheck !== morningCheck && shouldRequireAuth() && hasBackendHydrated.value && isAuthenticated.value) {
    lastMorningAdviceCheck = morningCheck
    void refreshCalendarPayloads(todayIsoDate.value)
  }
  void nextTick(ensureCurrentToday)
}

watch(todayIsoDate, (anchorDate, previousDate) => {
  if (anchorDate !== previousDate && hasBackendHydrated.value && shouldRequireAuth() && isAuthenticated.value) {
    ensureCurrentToday()
  }
})

function ensureCurrentToday() {
  if (!isUnmounted && hasBackendHydrated.value && shouldRequireAuth() && isAuthenticated.value && todayPayloadDate.value !== todayIsoDate.value && (!trainingReadPending || trainingReadDate !== todayIsoDate.value)) {
    void refreshCalendarPayloads(todayIsoDate.value)
  }
}

function beginTrainingRead(anchorDate: string) {
  trainingReadPending = true
  trainingReadDate = anchorDate
  return { version: ++trainingReadVersion, session: sessionGeneration, anchorDate }
}

type TrainingRead = ReturnType<typeof beginTrainingRead>

function isCurrentTrainingRead(read: TrainingRead) {
  return !isUnmounted && read.session === sessionGeneration && read.version === trainingReadVersion && read.anchorDate === todayIsoDate.value
}

function finishTrainingRead(read: TrainingRead) {
  if (read.version === trainingReadVersion) trainingReadPending = false
}

function publishTrainingRead(
  read: TrainingRead,
  todayResult: PromiseSettledResult<Awaited<ReturnType<typeof getTodayContext>>>,
  plansResult: PromiseSettledResult<Awaited<ReturnType<typeof listTrainingPlans>>>,
  racesResult: PromiseSettledResult<Awaited<ReturnType<typeof listRaceGoals>>>,
) {
  if (!isCurrentTrainingRead(read)) return
  if (todayResult.status === 'fulfilled') {
    applyTodayPayload(todayResult.value.data)
    todayPayloadDate.value = read.anchorDate
    todayReadFailed.value = false
  } else {
    todayReadFailed.value = true
  }
  if (plansResult.status === 'fulfilled') applyTrainingPlansPayload(Array.isArray(plansResult.value.data) ? plansResult.value.data : [])
  if (racesResult.status === 'fulfilled') applyRaceGoalsPayload(Array.isArray(racesResult.value.data) ? racesResult.value.data : [])
  hasBackendHydrated.value = true
}

async function refreshCalendarPayloads(anchorDate: string) {
  const read = beginTrainingRead(anchorDate)
  const [todayResult, plansResult, racesResult] = await Promise.allSettled([
    getTodayContext(anchorDate),
    listTrainingPlans(),
    listRaceGoals(anchorDate, sixMonthWindowEnd(anchorDate)),
  ])
  finishTrainingRead(read)
  if (!isCurrentTrainingRead(read)) {
    ensureCurrentToday()
    return
  }
  if ([todayResult, plansResult, racesResult].some((result) => result.status === 'rejected' && handleSessionExpiry(result.reason))) return
  publishTrainingRead(read, todayResult, plansResult, racesResult)
}

async function hydrateFromBackend() {
  const session = sessionGeneration
  try {
    const profileResult = await getAthleteProfile()
    if (isUnmounted || session !== sessionGeneration) return
    applyAthleteProfilePayload(profileResult.data)
  } catch (error) {
    if (isUnmounted || session !== sessionGeneration || handleSessionExpiry(error)) return
  }
  const anchorDate = todayIsoDate.value
  const read = beginTrainingRead(anchorDate)
  const [todayResult, recommendationsResult, plansResult, racesResult, integrationsResult] = await Promise.allSettled([
    getTodayContext(anchorDate),
    listRecommendations(),
    listTrainingPlans(),
    listRaceGoals(anchorDate, sixMonthWindowEnd(anchorDate)),
    listIntegrationConnections(),
  ])
  finishTrainingRead(read)
  if (isUnmounted || session !== sessionGeneration) return
  if (anchorDate !== todayIsoDate.value) {
    await hydrateFromBackend()
    return
  }
  if (!isCurrentTrainingRead(read)) return
  const results = [todayResult, recommendationsResult, plansResult, racesResult, integrationsResult]
  if (results.some((result) => result.status === 'rejected' && handleSessionExpiry(result.reason))) {
    return
  }

  publishTrainingRead(read, todayResult, plansResult, racesResult)
  if (recommendationsResult.status === 'fulfilled') {
    applyRecommendationsPayload(Array.isArray(recommendationsResult.value.data) ? recommendationsResult.value.data : [])
  }
  if (integrationsResult.status === 'fulfilled') {
    applyIntegrationsPayload(Array.isArray(integrationsResult.value.data) ? integrationsResult.value.data : [])
  }
}

async function refreshGarminTrainingEvidence() {
  const session = sessionGeneration
  try {
    const response = await getAthleteProfile()
    if (isUnmounted || session !== sessionGeneration) return
    garminTrainingEvidence.value = response.data.garmin_training_evidence ?? {}
  } catch (error) {
    if (!isUnmounted && session === sessionGeneration) handleSessionExpiry(error)
  }
}

function garminEvidenceStatus(resource: string): string {
  const reading = garminTrainingEvidence.value[resource]
  if (!reading?.synced_at) return '尚無可用資料，請至「資料」連接或同步 Garmin。'
  const status = reading.status === 'stale' ? '同步未更新，保留上次資料' : '已同步'
  const measured = reading.measured_on ? ` · 測量日期 ${reading.measured_on}` : ''
  const timestamp = new Date(reading.synced_at)
  const syncedAt = Number.isNaN(timestamp.getTime()) ? '時間不詳' : new Intl.DateTimeFormat('zh-TW', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: userTimezone.value,
  }).format(timestamp)
  return `${status} · 上次成功同步 ${syncedAt}${measured}`
}

function applyAthleteProfilePayload(profile: AthleteProfileResponse) {
  if (!profile || Array.isArray(profile)) {
    return
  }
  garminTrainingEvidence.value = profile.garmin_training_evidence ?? {}
  const timezone = typeof profile.timezone === 'string' && isValidTimezone(profile.timezone) ? profile.timezone : ''
  if (timezone) {
    userTimezone.value = timezone
  }
  const unitPreference = profile.unit_preference === 'imperial' ? 'imperial' : 'metric'
  const mileageKm = numberValue(profile.current_weekly_mileage_km) ?? 0
  const thresholdPace = numberValue(profile.threshold_pace_seconds_per_km ?? profile.training_preferences?.threshold_pace_seconds_per_km)
  athleteSettings.value = {
    timezone: timezone || userTimezone.value,
    experienceLevel: isExperienceLevel(profile.experience_level) ? profile.experience_level : '',
    currentWeeklyMileage: formatMileageForUnit(mileageKm, unitPreference),
    preferredTrainingDays: Array.isArray(profile.preferred_training_days) ? profile.preferred_training_days.map(String) : ['tuesday', 'thursday', 'sunday'],
    preferredLongRunDay: typeof profile.preferred_long_run_day === 'string' ? profile.preferred_long_run_day : 'sunday',
    maxRunsPerWeek: String(numberValue(profile.max_runs_per_week) ?? 3),
    maxHardSessionsPerWeek: String(numberValue(profile.max_hard_sessions_per_week) ?? 2),
    thresholdPace: thresholdPace && thresholdPace > 0 ? formatPace(thresholdPace) : '',
    thresholdPaceSource: thresholdPace ? 'manual' : 'garmin',
    unitPreference,
    injuryStatus: isInjuryStatus(profile.injury_status) ? profile.injury_status : 'none',
    injuryAreas: Array.isArray(profile.injury_areas) ? profile.injury_areas.map(String) : [],
    injuryNotes: typeof profile.injury_notes === 'string' ? profile.injury_notes : '',
  }
  athleteMileageDisplayUnit.value = unitPreference
}

function defaultAthleteSettingsForm(): AthleteSettingsForm {
  return {
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    experienceLevel: '',
    currentWeeklyMileage: '0.0',
    preferredTrainingDays: ['tuesday', 'thursday', 'sunday'],
    preferredLongRunDay: 'sunday',
    maxRunsPerWeek: '3',
    maxHardSessionsPerWeek: '2',
    thresholdPace: '',
    thresholdPaceSource: 'garmin',
    unitPreference: 'metric',
    injuryStatus: 'none',
    injuryAreas: [],
    injuryNotes: '',
  }
}

function isInjuryStatus(value: unknown): value is AthleteSettingsForm['injuryStatus'] {
  return value === 'none' || value === 'current' || value === 'recent' || value === 'recurring'
}

function isExperienceLevel(value: unknown): value is AthleteSettingsForm['experienceLevel'] {
  return value === 'beginner' || value === 'intermediate' || value === 'advanced'
}

function formatInjuryStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    none: '無目前傷痛',
    current: '目前有傷痛',
    recent: '近期傷痛觀察',
    recurring: '反覆傷痛觀察',
  }
  return labels[status] ?? '未設定'
}

function formatWeekdayLabel(day: string): string {
  const labels: Record<string, string> = {
    monday: '週一',
    tuesday: '週二',
    wednesday: '週三',
    thursday: '週四',
    friday: '週五',
    saturday: '週六',
    sunday: '週日',
  }
  return labels[day] ?? day
}

function formatPlanPhaseLabel(label: string): string {
  return label === 'Race' ? 'Goal week' : label
}

function formatMileageForUnit(kilometers: number, unit: 'metric' | 'imperial'): string {
  const value = unit === 'imperial' ? kilometers / KILOMETERS_PER_MILE : kilometers
  return value.toFixed(1)
}

function weeklyMileageKilometers(): number | null {
  const mileage = Number(athleteSettings.value.currentWeeklyMileage)
  if (!Number.isFinite(mileage) || mileage < 0) {
    return null
  }
  const kilometers = athleteSettings.value.unitPreference === 'imperial' ? mileage * KILOMETERS_PER_MILE : mileage
  return Math.round(kilometers * 10_000) / 10_000
}

function handleAthleteUnitChange() {
  const previousUnit = athleteMileageDisplayUnit.value
  const displayedMileage = Number(athleteSettings.value.currentWeeklyMileage)
  if (Number.isFinite(displayedMileage) && displayedMileage >= 0) {
    const kilometers = previousUnit === 'imperial' ? displayedMileage * KILOMETERS_PER_MILE : displayedMileage
    athleteSettings.value.currentWeeklyMileage = formatMileageForUnit(kilometers, athleteSettings.value.unitPreference)
  }
  athleteMileageDisplayUnit.value = athleteSettings.value.unitPreference
}

function validateAthleteSettings(): AthleteProfileSavePayload | null {
  athleteSettingsError.value = ''
  athleteSettingsFieldErrors.value = {}
  const form = athleteSettings.value
  const mileageKm = weeklyMileageKilometers()
  const maxRunsPerWeek = Number(form.maxRunsPerWeek)
  const maxHardSessionsPerWeekRaw = String(form.maxHardSessionsPerWeek ?? '').trim()
  const maxHardSessionsPerWeek = Number(maxHardSessionsPerWeekRaw)
  const thresholdPaceText = form.thresholdPaceSource === 'manual' ? form.thresholdPace.trim() : ''
  const thresholdPaceMatch = /^(\d{1,2}):([0-5]\d)$/.exec(thresholdPaceText)
  const thresholdPaceSeconds = thresholdPaceMatch ? Number(thresholdPaceMatch[1]) * 60 + Number(thresholdPaceMatch[2]) : null
  const normalizedDays = form.preferredTrainingDays.map((day) => day.trim().toLowerCase())
  const uniqueDays = new Set(normalizedDays)
  if (!form.timezone.trim() || !isValidTimezone(form.timezone.trim())) {
    setAthleteSettingsError('timezone', '請選擇有效的時區')
    return null
  }
  if (mileageKm === null) {
    setAthleteSettingsError('currentWeeklyMileage', '每週跑量必須是 0 以上')
    return null
  }
  if (!Number.isInteger(maxRunsPerWeek) || maxRunsPerWeek < 1 || maxRunsPerWeek > 7) {
    setAthleteSettingsError('maxRunsPerWeek', '每週最多跑步次數必須介於 1 到 7')
    return null
  }
  if (!maxHardSessionsPerWeekRaw || !Number.isInteger(maxHardSessionsPerWeek) || maxHardSessionsPerWeek < 0 || maxHardSessionsPerWeek > 2) {
    setAthleteSettingsError('maxHardSessionsPerWeek', '質量課表必須介於 0 到 2')
    return null
  }
  if (thresholdPaceText && (thresholdPaceSeconds === null || thresholdPaceSeconds < 120 || thresholdPaceSeconds > 900)) {
    setAthleteSettingsError('thresholdPace', '請輸入 2:00 到 15:00 的分/公里配速')
    return null
  }
  if (uniqueDays.size !== normalizedDays.length) {
    setAthleteSettingsError('preferredTrainingDays', '偏好訓練日不可重複')
    return null
  }
  if (normalizedDays.length > 0 && !uniqueDays.has(form.preferredLongRunDay)) {
    setAthleteSettingsError('preferredLongRunDay', '長跑日必須包含在偏好訓練日中')
    return null
  }
  if (form.injuryAreas.includes('other') && !form.injuryNotes.trim()) {
    setAthleteSettingsError('injuryNotes', '其他傷痛部位需要補充說明')
    return null
  }
  return {
    timezone: form.timezone.trim(),
    experience_level: form.experienceLevel || null,
    current_weekly_mileage_km: mileageKm,
    preferred_training_days: normalizedDays,
    preferred_long_run_day: form.preferredLongRunDay,
    max_runs_per_week: maxRunsPerWeek,
    max_hard_sessions_per_week: maxHardSessionsPerWeek,
    unit_preference: form.unitPreference,
    threshold_pace_seconds_per_km: thresholdPaceSeconds,
    injury_status: form.injuryStatus,
    injury_areas: form.injuryAreas.map((area) => area.trim().toLowerCase()),
    injury_notes: form.injuryNotes.trim() || null,
  }
}

function setAthleteSettingsError(field: string, message: string) {
  athleteSettingsFieldErrors.value = { [field]: message }
  athleteSettingsError.value = message
}

async function submitAthleteSettings() {
  if (athleteSettingsBusy.value) {
    return
  }
  athleteSettingsMessage.value = ''
  const payload = validateAthleteSettings()
  if (!payload) {
    return
  }
  athleteSettingsBusy.value = true
  try {
    const response = await saveAthleteProfile(payload)
    applyAthleteProfilePayload(response.data)
    athleteSettingsMessage.value = '運動員已更新'
    await refreshCalendarPayloads(todayIsoDate.value)
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      athleteSettingsError.value = '運動員儲存失敗，請檢查欄位後再試。'
    }
  } finally {
    athleteSettingsBusy.value = false
  }
}

function isValidTimezone(timezone: string): boolean {
  try {
    new Intl.DateTimeFormat('zh-TW', { timeZone: timezone })
    return true
  } catch {
    return false
  }
}

function applyIntegrationsPayload(connections: IntegrationConnectionResponse[]) {
  const garmin = connections.find((connection) => connection.provider === 'garmin_connect')
  if (garmin) {
    garminConnection.value = garmin
  }
}

function applyTodayPayload(payload: Record<string, unknown>) {
  apiDailyAdvice.value = mapDailyAdvice(payload.daily_advice)
  const nextRace = payload.next_race as Record<string, unknown> | null | undefined
  if (nextRace?.name && nextRace.race_date) {
    apiRaceSummary.value = {
      id: String(nextRace.id || ''),
      name: String(nextRace.name),
      date: String(nextRace.race_date),
      raceDate: String(nextRace.race_date),
      distance: formatDistance(Number(nextRace.distance_meters || 0)),
      goal: 'MVP goal',
      daysRemaining: daysUntil(String(nextRace.race_date)),
    }
  }

  if (!nextRace?.name || !nextRace.race_date) apiRaceSummary.value = null

  const workouts = Array.isArray(payload.scheduled_workouts) ? payload.scheduled_workouts : []
  apiTodayWorkoutPayload.value = workouts.map(asRecord).find((workout) => workout !== undefined) ?? null

  const recovery = payload.recovery as Record<string, unknown> | undefined
  const trainingLoad = payload.training_load as Record<string, unknown> | undefined
  apiRecoveryEvidence.value = recovery || trainingLoad ? buildRecoveryEvidenceItems(recovery ?? {}, trainingLoad) : []

  const unavailable = Array.isArray(payload.unavailable_signals) ? payload.unavailable_signals : []
  apiUnavailableSignals.value = unavailable.map(String)
}

function mapDailyAdvice(value: unknown): DailyAdvice | null {
  const raw = asRecord(value)
  if (!raw || typeof raw.id !== 'string' || !isIsoDate(raw.advice_date)) return null
  if (!['pending', 'ready', 'sync_failed', 'generation_failed', 'no_plan'].includes(String(raw.state))) return null
  if (!['fresh', 'limited', 'stale'].includes(String(raw.data_freshness))) return null
  const week = asRecord(raw.plan_week)
  const guide = asRecord(raw.workout_guide)
  const mode = ['follow_plan', 'ease_off', 'rest', 'completed'].includes(String(raw.execution_mode)) ? raw.execution_mode as DailyAdvice['executionMode'] : null
  return {
    id: raw.id,
    adviceDate: raw.advice_date,
    state: raw.state as DailyAdvice['state'],
    dataFreshness: raw.data_freshness as DailyAdvice['dataFreshness'],
    generatedAt: typeof raw.generated_at === 'string' ? raw.generated_at : null,
    sourceSyncRunId: typeof raw.source_sync_run_id === 'string' ? raw.source_sync_run_id : null,
    sourceRunId: typeof raw.source_run_id === 'string' ? raw.source_run_id : null,
    planVersionId: typeof raw.plan_version_id === 'string' ? raw.plan_version_id : null,
    workoutId: typeof raw.workout_id === 'string' ? raw.workout_id : null,
    executionMode: mode,
    planWeek: week && isIsoDate(week.starts_on) && isIsoDate(week.ends_on) ? { startsOn: week.starts_on, endsOn: week.ends_on } : null,
    facts: asRecord(raw.facts) ?? null,
    weekSummary: typeof raw.week_summary === 'string' ? raw.week_summary : null,
    todayExecution: typeof raw.today_execution === 'string' ? raw.today_execution : null,
    workoutGuide: guide && ['purpose', 'expected_feel', 'if_too_hard', 'if_too_easy'].every((key) => typeof guide[key] === 'string') ? {
      purpose: guide.purpose as string, expectedFeel: guide.expected_feel as string,
      ifTooHard: guide.if_too_hard as string, ifTooEasy: guide.if_too_easy as string,
    } : null,
  }
}

function applyRecommendationsPayload(items: Array<Record<string, unknown>>) {
  const mapped = items.map(mapRecommendation).filter((item): item is InboxRecommendation => item !== null)
  apiInboxItems.value = mapped
  const firstPending = mapped.find((item) => item.status === 'pending') ?? mapped[0]
  if (!firstPending) {
    apiRecommendation.value = null
    return
  }
  if (firstPending) {
    apiRecommendation.value = {
      id: firstPending.id,
      priority: recommendationPriorityTone(firstPending.priority),
      title: firstPending.title,
      rationale: firstPending.rationale,
      proposedAction: firstPending.proposedAction,
      status: firstPending.status,
    }
    recommendationStatus.value = firstPending.status
  }
}

function applyTrainingPlansPayload(items: TrainingPlanResponse[]) {
  apiTrainingPlans.value = items
}

function mapPhaseSegments(metadata: unknown): Array<PlanPhaseTimelineSegment & { startsOn: string; endsOn: string }> {
  const phaseSegments = asRecord(metadata)?.phase_segments
  const segments = Array.isArray(phaseSegments) ? phaseSegments : []
  return segments.flatMap((rawSegment) => {
    const segment = asRecord(rawSegment)
    if (!segment) {
      return []
    }
    if (!isTrainingPlanPhase(segment.phase) || !isIsoDate(segment.starts_on) || !isIsoDate(segment.ends_on)) {
      return []
    }
    return {
      phase: segment.phase,
      label: trainingPlanPhaseLabel(segment.phase),
      focus: typeof segment.focus === 'string' && segment.focus.trim() ? segment.focus : trainingPlanPhaseFocus(segment.phase),
      dateRange: formatPhaseDateRange(segment.starts_on, segment.ends_on),
      startsOn: segment.starts_on,
      endsOn: segment.ends_on,
    }
  })
}

function isTrainingPlanPhase(value: unknown): value is TrainingPlanPhase {
  return value === 'base' || value === 'build' || value === 'peak' || value === 'taper' || value === 'race' || value === 'maintenance'
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value
}

function addCalendarDays(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function trainingPlanPhaseLabel(phase: TrainingPlanPhase): string {
  const labels: Record<TrainingPlanPhase, string> = {
    base: '基礎期',
    build: '建立期',
    peak: '高峰期',
    taper: '減量期',
    race: '比賽期',
    maintenance: '維持期',
  }
  return labels[phase]
}

function trainingPlanPhaseFocus(phase: TrainingPlanPhase): string {
  const focus: Record<TrainingPlanPhase, string> = {
    base: '建立有氧基礎與跑步節奏',
    build: '提高品質課表與耐受度',
    peak: '完成關鍵配速與長跑練習',
    taper: '降低疲勞並保留節奏',
    race: '準備上場，依比賽策略執行',
    maintenance: '維持穩定有氧節奏',
  }
  return focus[phase]
}

function formatPhaseDateRange(startsOn: string, endsOn: string): string {
  const startsOnLabel = formatDateLabel(startsOn)
  const endsOnLabel = formatDateLabel(endsOn)
  return startsOnLabel === endsOnLabel ? startsOnLabel : `${startsOnLabel} - ${endsOnLabel}`
}

function applyRaceGoalsPayload(items: Array<Record<string, unknown>>) {
  const mapped = items.map(mapRaceGoal).filter((race): race is RaceSummary => race !== null)
  if (mapped.length || shouldRequireAuth()) {
    raceEntries.value = mapped
  }
}

function applyPlanRegenerationRaceGoalsPayload(items: Array<Record<string, unknown>>) {
  const mapped = items.map(mapRaceGoal).filter((race): race is RaceSummary => race !== null)
  if (mapped.length || shouldRequireAuth()) {
    planRegenerationRaceOptions.value = mapped
  }
}

function mapRaceGoal(raw: unknown): RaceSummary | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const race = raw as Record<string, unknown>
  const name = String(race.name || '')
  const raceDateValue = String(race.race_date || '')
  const distanceMeters = Number(race.distance_meters || 0)
  if (!name || !raceDateValue || !Number.isFinite(distanceMeters) || distanceMeters <= 0) {
    return null
  }
  return {
    id: String(race.id || ''),
    name,
    date: raceDateValue,
    raceDate: raceDateValue,
    distance: formatDistance(distanceMeters),
    goal: formatTargetFinish(race.target_finish_seconds) || formatRacePriority(race.priority) || String(race.status || 'planned'),
    daysRemaining: daysUntil(raceDateValue),
    ascentMeters: typeof race.ascent_meters === 'number' ? race.ascent_meters : null,
    descentMeters: typeof race.descent_meters === 'number' ? race.descent_meters : null,
    terrainDifficulty: race.terrain_difficulty === 'runnable' || race.terrain_difficulty === 'mixed' || race.terrain_difficulty === 'technical' ? race.terrain_difficulty : null,
    cutoffSeconds: typeof race.cutoff_seconds === 'number' ? race.cutoff_seconds : null,
    goalIntent: race.goal_intent === 'complete' || race.goal_intent === 'perform' ? race.goal_intent : null,
  }
}

function raceCourseDetails(race: RaceSummary): string {
  const details = [
    race.ascentMeters != null ? `爬升 ${race.ascentMeters} 公尺` : null,
    race.descentMeters != null ? `下降 ${race.descentMeters} 公尺` : null,
    race.terrainDifficulty ? ({ runnable: '可跑性高', mixed: '混合地形', technical: '技術地形' } as const)[race.terrainDifficulty] : null,
    race.cutoffSeconds != null ? `關門 ${Number((race.cutoffSeconds / 3600).toFixed(2))} 小時` : null,
    race.goalIntent ? (race.goalIntent === 'complete' ? '目標：完成賽事' : '目標：挑戰表現') : null,
  ].filter(Boolean)
  return details.length ? details.join(' · ') : '賽道資料未提供'
}

function preparationStatusLabel(status: string): string {
  return ({ gap: '尚有準備落差', unknown: '資料不足', on_track: '達到規劃參考' } as Record<string, string>)[status] ?? '資料不足'
}

function mapWorkout(raw: unknown): WorkoutSummary | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const workout = raw as Record<string, unknown>
  const scheduledFor = String(workout.scheduled_for || '')
  const steps = mapWorkoutSteps(workout.steps)
  const workoutType = String(workout.workout_type || 'workout')
  const canonicalName = typeof workout.display_name === 'string' ? workout.display_name.trim() : ''
  const raceName = workoutType === 'race' && workout.race_name ? String(workout.race_name) : ''
  const raceFallbackName = raceName && workout.planned_distance_meters
    ? `${raceName} · ${formatDistance(Number(workout.planned_distance_meters))}` : raceName
  return {
    id: String(workout.id || scheduledFor || crypto.randomUUID()),
    weekday: formatWeekday(scheduledFor),
    dateLabel: formatDateLabel(scheduledFor),
    scheduledFor,
    type: canonicalName || raceFallbackName || formatWorkoutType(workoutType),
    workoutType,
    raceName: raceName || undefined,
    raceGoalId: workoutType === 'race' && workout.race_goal_id ? String(workout.race_goal_id) : undefined,
    racePriority: workout.workout_type === 'race' && ['primary', 'secondary', 'tune_up'].includes(String(workout.race_priority)) ? workout.race_priority as WorkoutSummary['racePriority'] : undefined,
    purpose: workout.purpose ? String(workout.purpose) : workoutPurpose(String(workout.workout_type || 'workout')),
    distance: workout.planned_distance_meters ? formatDistance(Number(workout.planned_distance_meters)) : undefined,
    duration: workout.planned_duration_minutes ? `${workout.planned_duration_minutes} 分` : undefined,
    pace: formatPaceRange(workout.pace_range_seconds_per_km),
    heartRateZone: workout.heart_rate_zone ? String(workout.heart_rate_zone) : undefined,
    phase: workout.phase ? formatPlanPhase(String(workout.phase)) : undefined,
    coachNote: workout.coach_note ? String(workout.coach_note) : undefined,
    stepSummary: workout.compact_summary ? String(workout.compact_summary) : undefined,
    steps,
    status: formatWorkoutStatus(String(workout.status || 'planned')),
  }
}

function mapWorkoutSteps(raw: unknown): WorkoutStep[] | undefined {
  if (!Array.isArray(raw)) {
    return undefined
  }
  const steps = raw.map(mapWorkoutStep).filter((step): step is WorkoutStep => step !== null)
  return steps.length ? steps : undefined
}

function mapWorkoutStep(raw: unknown): WorkoutStep | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const step = raw as Record<string, unknown>
  const type = String(step.type || '')
  if (!type) {
    return null
  }
  return {
    type: type as WorkoutStep['type'],
    durationSeconds: optionalNumber(step.duration_seconds),
    distanceMeters: optionalNumber(step.distance_meters),
    target: mapWorkoutTarget(step.target),
    repeatCount: optionalNumber(step.repeat_count),
    steps: mapWorkoutSteps(step.steps) ?? [],
    notes: step.notes ? String(step.notes) : undefined,
    gradeNotes: step.grade_notes ? String(step.grade_notes) : undefined,
  }
}

function mapWorkoutTarget(raw: unknown): WorkoutTarget | undefined {
  if (!raw || typeof raw !== 'object') {
    return undefined
  }
  const target = raw as Record<string, unknown>
  const kind = String(target.kind || '')
  if (!kind) {
    return undefined
  }
  return {
    kind: kind as WorkoutTarget['kind'],
    zone: target.zone ? String(target.zone) : undefined,
    heartRateZone: target.heart_rate_zone ? String(target.heart_rate_zone) : undefined,
    rpe: optionalNumber(target.rpe),
    paceRangeSecondsPerKm: optionalNumberArray(target.pace_range_seconds_per_km),
    heartRateRangeBpm: optionalNumberArray(target.heart_rate_range_bpm),
    confidence: target.confidence ? (String(target.confidence) as WorkoutTarget['confidence']) : undefined,
    paceSource: target.pace_source ? (String(target.pace_source) as WorkoutTarget['paceSource']) : undefined,
  }
}

function optionalNumber(value: unknown): number | undefined {
  if (value === null || value === undefined || value === '') {
    return undefined
  }
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : undefined
}

function optionalNumberArray(value: unknown): number[] | undefined {
  if (!Array.isArray(value)) {
    return undefined
  }
  const numbers = value.map(Number).filter((item) => Number.isFinite(item))
  return numbers.length === value.length ? numbers : undefined
}

function hasWorkoutDetails(workout: WorkoutSummary): boolean {
  return Boolean((workout.steps && workout.steps.length) || workout.coachNote)
}

function openWorkoutDetails(workout: WorkoutSummary) {
  if (hasWorkoutDetails(workout)) {
    selectedWorkoutId.value = workout.id
  }
}

function closeWorkoutDetails() {
  selectedWorkoutId.value = null
}

function buildWorkoutStepRows(steps: WorkoutStep[], workoutType?: string, depth = 0, prefix = 'step', parentStage?: WorkoutStageKey): WorkoutStepRow[] {
  return steps.flatMap((step, index) => {
    const key = `${prefix}-${index}`
    const stage = parentStage ?? workoutStepStage(step.type)
    if (step.type === 'repeat') {
      return [
        {
          key,
          label: `${step.repeatCount || 1} 組`,
          load: '重複組',
          target: '',
          note: step.notes || '',
          depth,
          stage,
        },
        ...buildWorkoutStepRows(step.steps ?? [], workoutType, depth + 1, key, stage),
      ]
    }
    return [
      {
        key,
        label: formatWorkoutStepLabel(step.type),
        load: formatWorkoutStepLoad(step),
        target: formatWorkoutTarget(step.target, workoutType === 'hill' || step.type === 'hill'),
        note: [step.notes, step.gradeNotes].filter(Boolean).join(' · '),
        depth,
        stage,
      },
    ]
  })
}

function workoutStepStage(type: WorkoutStep['type']): WorkoutStageKey {
  if (type === 'warmup') return 'warmup'
  if (type === 'cooldown') return 'cooldown'
  if (type === 'recovery') return 'recovery'
  return 'main'
}

function workoutStageLabel(stage: WorkoutStageKey): string {
  return { warmup: '暖身', main: '主課表', recovery: '恢復', cooldown: '緩和' }[stage]
}

function workoutStagePreview(workout: WorkoutSummary): Array<{ label: string; load: string }> {
  return (workout.steps ?? []).map((step) => {
    const label = workoutStageLabel(workoutStepStage(step.type))
    if (step.type === 'repeat') {
      const work = step.steps?.find((part) => ['work', 'hill', 'stride'].includes(part.type))
      return { label, load: `${step.repeatCount || 1} 組${work ? ` × ${formatWorkoutStepLoad(work)}` : ''}` }
    }
    return { label, load: formatWorkoutStepLoad(step) }
  }).filter((item) => item.load)
}

function workoutPurpose(type: string): string {
  return ({ easy_run: '維持有氧基礎', recovery: '促進恢復', long_run: '建立長距離耐力', tempo: '提升持續配速能力', interval: '提升速度與有氧能力', hill: '建立爬坡力量與跑姿穩定性', race: '依賽事安排完成當日努力' } as Record<string, string>)[type] ?? '完成本次訓練'
}

function formatPlanPhase(value: string): string {
  return ({ base: '基礎期', build: '建構期', peak: '高峰期', taper: '減量期', race: '賽事期', maintenance: '維持期' } as Record<string, string>)[value] ?? value
}

function formatWorkoutStatus(value: string): string {
  return ({ planned: '已安排', adjusted: '已調整', completed: '已完成', skipped: '已跳過' } as Record<string, string>)[value] ?? value
}

function formatWorkoutStepLabel(value: WorkoutStep['type']): string {
  const labels: Record<WorkoutStep['type'], string> = {
    warmup: '暖身跑',
    work: '訓練段',
    recovery: '組間恢復',
    cooldown: '緩和跑',
    repeat: '重複組',
    drill: '跑姿練習',
    stride: '加速跑',
    hill: '坡跑',
    free_run: '自由跑',
  }
  return labels[value] ?? value
}

function formatWorkoutStepLoad(step: WorkoutStep): string {
  const parts = []
  if (step.distanceMeters) {
    parts.push(formatDistance(step.distanceMeters))
  }
  if (step.durationSeconds) {
    parts.push(formatSecondsDuration(step.durationSeconds))
  }
  return parts.join(' / ')
}

function workoutTargetSummary(workout: WorkoutSummary): string {
  const flatten = (steps: WorkoutStep[]): WorkoutStep[] => steps.flatMap(step => step.type === 'repeat' ? flatten(step.steps ?? []) : [step])
  const steps = flatten(workout.steps ?? [])
  const main = steps.find(step => ['work', 'free_run', 'hill', 'stride'].includes(step.type) && step.target) ?? steps.find(step => step.target)
  return main ? formatWorkoutTarget(main.target, workout.workoutType === 'hill') : ''
}

function formatWorkoutTarget(target?: WorkoutTarget | null, hillReference = false): string {
  if (!target) {
    return ''
  }
  const pace = formatPaceRange(target.paceRangeSecondsPerKm)
  const sourceLabels = { garmin_lactate_threshold: 'Garmin 閾值配速', threshold_pace: '閾值配速', completed_race: '已完成賽事', paired_easy_activities: '配對輕鬆跑', goal_time: '目標時間' }
  const confidenceLabels = { high: '高信心', medium: '中信心', low: '低信心' }
  const paceEvidence = pace ? [target.paceSource ? sourceLabels[target.paceSource] : '', target.confidence ? confidenceLabels[target.confidence] : ''].filter(Boolean).join(' · ') : ''
  const paceLabel = pace ? `${hillReference ? '平地參考配速' : '預估配速'} ${pace}` : ''
  if (target.kind === 'pace') {
    return [formatPaceZone(target.zone), paceLabel, target.rpe != null ? `RPE ${target.rpe}` : '', paceEvidence].filter(Boolean).join(' · ')
  }
  if (target.kind === 'heart_rate') {
    const range = target.heartRateRangeBpm && target.heartRateRangeBpm.length >= 2 ? `${target.heartRateRangeBpm[0]}-${target.heartRateRangeBpm[1]} bpm` : ''
    return [target.rpe != null ? `RPE ${target.rpe}` : '', range ? `心率 ${range}` : '', paceLabel, !range && !pace ? '配速與心率資料不足' : '', paceEvidence].filter(Boolean).join(' · ')
  }
  return [target.rpe != null ? `RPE ${target.rpe}` : 'RPE', paceLabel || '配速與心率資料不足', paceEvidence].filter(Boolean).join(' · ')
}

function mapRecommendation(raw: Record<string, unknown>): InboxRecommendation | null {
  if (!raw.id || !raw.title) {
    return null
  }
  const priority = normalizePriority(raw.priority)
  const status = normalizeStatus(raw.status, raw.decision)
  const evidence = Array.isArray(raw.evidence) ? raw.evidence : []
  const proposedAction = raw.proposed_action as Record<string, unknown> | undefined
  return {
    id: String(raw.id),
    title: String(raw.title),
    summary: String(raw.rationale || raw.title),
    proposedAction: String(proposedAction?.reason || proposedAction?.type || 'No plan change'),
    rationale: String(raw.rationale || ''),
    priority,
    priorityLabel: priorityLabel(priority),
    status,
    statusLabel: statusLabel(status),
    evidence: evidence.map(mapEvidence),
  }
}

function mapEvidence(raw: unknown): EvidenceItem {
  const item = (raw || {}) as Record<string, unknown>
  return {
    source: String(item.source || 'Johnny'),
    metric: String(item.metric || 'signal'),
    value: String(item.value ?? ''),
    summary: String(item.summary || `${item.metric || 'signal'} ${item.value ?? ''}`),
    tone: 'info',
  }
}

function appendConversationMessages(content: string, response: { data: { run_ref: string; message: { agent_output?: string } } }) {
  const thread = activeThread.value
  if (!thread) {
    return
  }
  thread.messages.push(
    {
      id: `msg-user-${Date.now()}`,
      role: 'user',
      authorLabel: '你',
      content,
      timestampLabel: '剛剛',
    },
    {
      id: `msg-johnny-${Date.now()}`,
      role: 'johnny',
      authorLabel: 'Johnny 回覆',
      content: response.data.message.agent_output || 'Johnny 已完成這次回覆。',
      timestampLabel: '剛剛',
      runRef: response.data.run_ref,
    },
  )
}

function normalizePriority(value: unknown): InboxRecommendation['priority'] {
  return value === 'high' || value === 'medium' || value === 'low' ? value : 'medium'
}

function normalizeStatus(status: unknown, decision: unknown): RecommendationStatus {
  if (decision === 'accepted') {
    return 'accepted'
  }
  if (decision === 'rejected') {
    return 'rejected'
  }
  if (decision === 'edited') {
    return 'edited'
  }
  return status === 'pending' ? 'pending' : 'applied'
}

function priorityLabel(priority: InboxRecommendation['priority']): string {
  return priority === 'high' ? '高優先' : priority === 'medium' ? '中優先' : '低優先'
}

function statusLabel(status: RecommendationStatus): string {
  if (status === 'pending') {
    return '待決定'
  }
  if (status === 'accepted') {
    return '已接受'
  }
  if (status === 'rejected') {
    return '已保留課表'
  }
  return '已套用'
}

function formatWorkoutType(value: string): string {
  return ({ easy_run: '輕鬆跑', recovery: '恢復跑', long_run: '長跑', tempo: '節奏跑', interval: '間歇跑', hill: '坡跑', race: '賽事', strength: '肌力訓練', cross_training: '交叉訓練', rest: '休息' } as Record<string, string>)[value] ?? '訓練'
}

function formatDistance(meters: number): string {
  return formatRaceDistance(meters)
}

function formatSecondsDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return ''
  }
  if (seconds % 60 === 0) {
    return `${seconds / 60} 分`
  }
  return `${seconds} 秒`
}

function formatPaceRange(value: unknown): string | undefined {
  const range = optionalNumberArray(value)
  if (!range || range.length < 2) {
    return undefined
  }
  return `${formatPace(range[0])}-${formatPace(range[1])} /km`
}

function formatPace(secondsPerKm: number): string {
  const minutes = Math.floor(secondsPerKm / 60)
  const seconds = Math.round(secondsPerKm % 60)
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function formatPaceZone(value?: string | null): string {
  if (!value) {
    return ''
  }
  const labels: Record<string, string> = {
    easy: '輕鬆配速',
    steady: '穩定配速',
    marathon: '馬拉松配速',
    threshold: '乳酸閾值配速',
    interval: '間歇配速',
    repetition: '短間歇配速',
    rpe_only: '體感強度',
  }
  return labels[value] ?? value
}

function formatTargetFinish(value: unknown): string {
  const seconds = Number(value)
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return ''
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
  }
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
}

function formatWeekday(value: string): string {
  if (!value) {
    return '待排'
  }
  const day = new Date(`${value}T00:00:00`).getDay()
  return ['週日', '週一', '週二', '週三', '週四', '週五', '週六'][day]
}

function formatDateLabel(value: string): string {
  if (!value) {
    return ''
  }
  const date = new Date(`${value}T00:00:00`)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function daysUntil(value: string): number {
  const target = new Date(`${value}T00:00:00`).getTime()
  const today = new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00').getTime()
  return Math.max(0, Math.ceil((target - today) / 86_400_000))
}

function sixMonthWindowEnd(anchorDate: string): string {
  const anchor = new Date(`${anchorDate}T00:00:00`)
  const end = new Date(anchor.getFullYear(), anchor.getMonth() + 6, 0)
  return end.toISOString().slice(0, 10)
}

function emptyRaceSummary(): RaceSummary {
  return {
    id: '',
    name: '尚未設定目標',
    date: '',
    raceDate: '',
    distance: 'N/A',
    goal: '先新增你的目標',
    daysRemaining: 0,
  }
}

function emptyWorkoutSummary(): WorkoutSummary {
  return {
    id: 'empty-workout',
    weekday: '待排',
    dateLabel: '',
    type: '尚未有今日課表',
    purpose: '連接資料或建立訓練計畫後，Johnny 會在這裡顯示今天的安排。',
    status: 'empty',
  }
}

function shouldRequireAuth(): boolean {
  return props.requireAuth || import.meta.env.MODE !== 'test'
}
</script>

<template>
  <div v-if="authStatus === 'checking' && shouldRequireAuth()" class="app-shell auth-shell">
    <main class="auth-surface">
      <section class="auth-panel" aria-live="polite">
        <p class="section-label">Johnny</p>
        <h1>正在確認登入狀態</h1>
        <p>如果 session 已過期，Johnny 會帶你回到登入頁。</p>
      </section>
    </main>
  </div>

  <div v-else-if="authStatus === 'anonymous' && shouldRequireAuth()" class="app-shell auth-shell">
    <main class="auth-surface">
      <section class="auth-panel" aria-labelledby="auth-title">
        <div class="auth-panel__header">
          <p class="section-label">Running Companion</p>
          <h1 id="auth-title">登入 Johnny</h1>
          <p>登入後 Johnny 才會讀取你的訓練計畫、資料連接與 Johnny 建議。</p>
        </div>

        <div class="auth-mode-switch" role="tablist" aria-label="登入方式">
          <button
            type="button"
            data-auth-mode="login"
            :class="{ 'auth-mode-switch__item--active': authMode === 'login' }"
            @click="selectAuthMode('login')"
          >
            Email 登入
          </button>
          <button
            type="button"
            data-auth-mode="signup"
            :class="{ 'auth-mode-switch__item--active': authMode === 'signup' }"
            @click="selectAuthMode('signup')"
          >
            建立帳號
          </button>
        </div>

        <button class="google-auth-button" type="button" :disabled="authBusy" @click="handleGoogleSignIn">
          使用 Google 登入
        </button>

        <form class="auth-form" data-testid="auth-form" novalidate @submit.prevent="submitAuth">
          <label v-if="authMode === 'signup'">
            顯示名稱
            <input v-model="authDisplayName" class="auth-form__input" name="displayName" autocomplete="name" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <label>
            Email
            <input v-model="authEmail" class="auth-form__input" name="authEmail" type="email" autocomplete="email" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <label>
            密碼
            <input v-model="authPassword" class="auth-form__input" name="authPassword" type="password" :autocomplete="authMode === 'signup' ? 'new-password' : 'current-password'" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <label v-if="authMode === 'signup'">
            確認密碼
            <input v-model="authPasswordConfirm" class="auth-form__input" name="authPasswordConfirm" type="password" autocomplete="new-password" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <p v-if="authError" class="field-error" role="alert">{{ authError }}</p>
          <p v-else-if="authMessage" class="inline-note">{{ authMessage }}</p>
          <p v-else class="auth-hint">密碼至少 8 個字元，可使用密碼管理器或貼上。</p>
          <AppButton tone="primary" type="submit" :busy="authBusy">
            {{ authMode === 'signup' ? '建立並進入 Johnny' : '登入 Johnny' }}
          </AppButton>
        </form>
      </section>
    </main>
  </div>

  <div v-else class="app-shell">
    <header class="top-bar">
      <div class="top-bar__inner">
        <div class="brand-lockup">
          <p class="section-label">Running Companion</p>
          <h1>Johnny</h1>
        </div>
        <nav class="top-nav" aria-label="主要導覽">
          <button
            v-for="item in navItems"
            :key="item.key"
            :data-view="item.key"
            :class="{ 'top-nav__item--active': activeView === item.key }"
            :aria-current="activeView === item.key ? 'page' : undefined"
            class="top-nav__item"
            type="button"
            @click="showView(item.key)"
          >
            {{ item.label }}
          </button>
        </nav>
        <div v-if="isAuthenticated && currentUser" class="user-menu" aria-label="目前使用者">
          <span>{{ currentUser.display_name || currentUser.email }}</span>
          <button type="button" @click="handleSignOut">登出</button>
        </div>
      </div>
    </header>

    <main class="main-surface">
      <section v-if="activeView === 'today'" class="today-grid" data-testid="today-decision-flow" aria-labelledby="today-title">
        <div class="page-heading today-grid__wide">
          <p class="section-label">今日</p>
          <h2 id="today-title">今天的訓練決策</h2>
          <p>Johnny 會把課表、恢復訊號和建議放在同一個決策脈絡裡。</p>
        </div>

        <div class="today-date-strip today-grid__wide" data-testid="today-date-strip">
          <time :datetime="todayIsoDate">{{ todayIsoDate }}</time>
          <span v-if="dailyAdvice?.planWeek">Plan Week · {{ dailyAdvice.planWeek.startsOn }}–{{ dailyAdvice.planWeek.endsOn }}</span>
          <span v-else-if="activePlan">{{ currentPlanPhase.label }}</span>
          <span v-else>今日安排</span>
        </div>

        <article v-if="effectiveTodayState === 'loading'" class="state-panel today-grid__wide" aria-live="polite">
          <p class="section-label">Loading</p>
          <h3>正在整理今天的訓練資料</h3>
          <p>Johnny 正在讀取課表、恢復訊號和推薦狀態。</p>
        </article>

        <article v-else-if="effectiveTodayState === 'error'" class="state-panel state-panel--danger today-grid__wide" role="alert">
          <p class="section-label">Error</p>
          <h3>今天資料載入失敗</h3>
          <p>請稍後再試，或先前往資料連接檢查同步狀態。</p>
          <AppButton v-if="todayReadFailed" tone="neutral" @click="ensureCurrentToday">重新讀取今日資料</AppButton>
          <AppButton tone="neutral" @click="showView('data')">檢查資料</AppButton>
        </article>

        <article v-else-if="effectiveTodayState === 'empty'" class="state-panel today-grid__wide">
          <p class="section-label">Empty</p>
          <h3>尚未有足夠資料建立今日建議</h3>
          <p>連接資料後，Johnny 會用近期訓練、睡眠與 HRV 判斷恢復狀態。</p>
          <AppButton tone="primary" @click="showView('data')">連接資料</AppButton>
        </article>

        <template v-else>
        <div class="today-primary-board today-grid__wide">
          <article
            class="today-decision-card"
            :class="`today-decision-card--${todayDecision.tone}`"
            :data-decision-state="todayDecision.state"
            data-testid="today-decision-card"
          >
            <div class="today-decision-card__header">
              <span class="card-kicker">Johnny 今天看起來</span>
              <strong>{{ todayDecision.label }}</strong>
            </div>
            <p>{{ todayDecision.voice }}</p>
            <p v-if="dailyAdvice" class="today-decision-card__freshness">
              {{ dailyAdvice.dataFreshness === 'stale' ? '先前建議 · 資料可能過時' : dailyAdvice.dataFreshness === 'limited' ? '資料有限 · 依可用紀錄判斷' : '最新建議' }}
            </p>
            <p v-if="todayDecision.memoryInsight" class="memory-insight">{{ todayDecision.memoryInsight }}</p>
            <AppButton tone="primary" data-testid="today-decision-action" @click="handleTodayDecisionAction">{{ todayDecision.actionLabel }}</AppButton>
          </article>

          <article class="surface-card workout-card" data-today-section="workout" data-today-workout-summary>
            <p class="section-label">今日課表</p>
            <h3>{{ todayWorkout.type }}</h3>
            <p>{{ todayWorkout.purpose }}</p>
            <p v-if="workoutTargetSummary(todayWorkout)" class="workout-step-summary">{{ workoutTargetSummary(todayWorkout) }}</p>
            <p v-if="workoutStagePreview(todayWorkout).length" class="workout-step-summary">{{ workoutStagePreview(todayWorkout).map((step) => `${step.label} ${step.load}`).join(' · ') }}</p>
            <div class="metric-row">
              <span v-if="todayWorkout.distance">{{ todayWorkout.distance }}</span>
              <span v-if="todayWorkout.duration">{{ todayWorkout.duration }}</span>
              <span v-if="todayWorkout.pace">{{ todayWorkout.pace }}</span>
              <span v-if="todayWorkout.heartRateZone">{{ todayWorkout.heartRateZone }}</span>
            </div>
            <div v-if="hasWorkoutDetails(todayWorkout)" class="workout-card__actions">
              <AppButton tone="neutral" type="button" data-testid="today-workout-detail" @click="openWorkoutDetails(todayWorkout)">查看細節</AppButton>
            </div>
          </article>
        </div>

        <section class="today-evidence today-grid__wide" data-testid="today-evidence" aria-label="今日決策證據">
          <div class="today-evidence-chip-list">
            <span v-for="item in todayEvidenceChips" :key="`${item.source}-${item.metric}`" class="today-evidence-chip" data-testid="today-evidence-chip">
              <span>{{ item.metric }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.summary }}</small>
            </span>
          </div>
        </section>

        <section class="surface-card weekly-activity" data-testid="weekly-activity" aria-labelledby="weekly-activity-title">
          <div class="section-heading-row">
            <h3 id="weekly-activity-title">本週活動</h3>
            <span>跑量節奏</span>
          </div>
          <div class="weekly-activity__bars" aria-label="本週跑步距離">
            <div class="weekly-activity__plot weekly-activity__plot--spread" data-testid="weekly-activity-plot" aria-hidden="true">
              <span
                v-for="point in weeklyActivityPoints"
                :key="`${point.dayLabel}-bar`"
                class="weekly-activity__column"
                data-testid="weekly-activity-column"
              >
                <span
                  class="weekly-activity__bar"
                  data-testid="weekly-activity-bar"
                  :style="{ '--bar-size': `${Math.round((point.distanceKm / maxWeeklyDistance) * 100)}%` }"
                ></span>
              </span>
            </div>
            <div class="weekly-activity__labels">
              <div v-for="point in weeklyActivityPoints" :key="point.dayLabel" class="weekly-activity__day">
                <strong>{{ point.dayLabel }}</strong>
                <small>{{ point.distanceKm }} km</small>
              </div>
            </div>
          </div>
        </section>

        <aside class="today-context-rail" aria-label="今日脈絡">
          <section class="surface-card">
            <span class="card-kicker">目標賽事</span>
            <strong>{{ raceSummary.name }}</strong>
            <p>{{ raceSummary.daysRemaining }} 天後 · {{ raceSummary.goal }}</p>
          </section>
          <section class="surface-card">
            <span class="card-kicker">目前階段</span>
            <strong>{{ currentPlanPhase.label }}</strong>
            <p>{{ currentPlanPhase.summary }}</p>
          </section>
          <section class="surface-card">
            <span class="card-kicker">Signal Coverage</span>
            <strong>{{ coveredSignalCount }}/{{ signalCoverage.length }}</strong>
            <p>{{ signalCoverageSummary }}</p>
          </section>
          <section class="surface-card">
            <span class="card-kicker">Johnny 待決定</span>
            <strong>{{ pendingInboxItems.length }}</strong>
            <p>目前待處理建議</p>
          </section>
        </aside>

        <article
          class="surface-card today-grid__wide recommendation-strip"
          data-testid="today-recommendation-strip"
          data-today-section="recommendation"
        >
          <div>
            <p class="section-label">Johnny 建議</p>
            <h3>{{ todayRecommendationStrip.summary }}</h3>
          </div>
          <div class="recommendation-strip__meta">
            <StatusBadge :tone="recoveryDecision.tone">{{ recoveryDecision.label }}</StatusBadge>
            <AppButton
              v-if="todayRecommendationStrip.actionLabel && todayRecommendationStrip.actionView"
              :tone="todayRecommendationStrip.actionTone"
              @click="showView(todayRecommendationStrip.actionView)"
            >
              {{ todayRecommendationStrip.actionLabel }}
            </AppButton>
          </div>
        </article>

        <article class="surface-card today-grid__wide evidence-card" data-testid="today-recovery-card" data-today-section="recovery">
          <div class="section-heading">
            <div>
              <p class="section-label">恢復證據</p>
              <h3>關鍵恢復指標</h3>
            </div>
            <StatusBadge :tone="recoveryDecision.tone">{{ recoveryDecision.label }}</StatusBadge>
          </div>
          <p class="recovery-summary" data-testid="today-recovery-summary">主要訊號用來判斷今天是否照課表、保守或休息。</p>
          <div class="recovery-signal-grid" aria-label="恢復關鍵訊號">
            <div v-for="item in recoveryEvidence.slice(0, 3)" :key="`${item.source}-${item.metric}`" class="recovery-signal-chip" data-testid="recovery-signal-chip">
              <span>{{ item.metric }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.summary }}</small>
            </div>
          </div>
          <div class="compact-card-footer">
            <span v-if="recoveryFooterText">{{ recoveryFooterText }}</span>
            <AppButton v-if="dataSourceNeedsAttention" data-testid="today-recovery-source-action" tone="neutral" @click="showView('data')">
              檢查資料
            </AppButton>
          </div>
        </article>

        <article class="surface-card today-top-card today-card--context race-card" data-today-section="race">
          <p class="section-label">下一場比賽</p>
          <h3>{{ raceSummary.name }}</h3>
          <p class="race-card__count">{{ raceSummary.daysRemaining }} 天</p>
          <p>{{ raceSummary.distance }} · {{ raceSummary.goal }} · {{ raceSummary.date }}</p>
          <p class="race-card__rationale">{{ raceTrainingRationale }}</p>
        </article>

        <article class="surface-card today-grid__wide inbox-nudge" data-today-section="inbox">
          <div>
            <p class="section-label">Johnny 建議</p>
            <h3>所有需要確認的調整集中處理</h3>
            <p>所有需要你確認的調整都會集中在 Johnny 建議。</p>
          </div>
          <AppButton tone="neutral" @click="showView('johnny')">查看待決定建議</AppButton>
        </article>
        </template>
        <SessionReviews v-if="currentUser" :key="currentUser.id" :anchor-date="todayIsoDate" :time-zone="userTimezone" :refresh-key="sessionReviewsRefreshKey" class="today-grid__wide" @changed="handleSessionReviewChanged" @error="handleSessionExpiry" />
        <DailyAdviceCard v-if="dailyAdvice" :advice="dailyAdvice" :time-zone="userTimezone" class="today-grid__wide" data-testid="today-daily-advice" />
      </section>

      <section v-else-if="activeView === 'plan'" class="page-stack plan-page" aria-labelledby="plan-title">
        <div class="page-heading page-heading--with-action">
          <div>
            <span>Training journey</span>
            <h2 id="plan-title">計畫</h2>
            <p v-if="raceFormError" class="field-error" role="alert">{{ raceFormError }}</p>
            <p v-else-if="raceFormMessage" class="inline-note" role="status">{{ raceFormMessage }}</p>
          </div>
          <div class="app-dialog__actions">
            <AppButton tone="neutral" type="button" data-testid="open-plan-regeneration-sheet" @click="openPlanRegenerationSheet">重新產生計畫</AppButton>
            <AppButton tone="primary" type="button" data-testid="open-race-goal-modal" @click="openRaceGoalModal">新增目標</AppButton>
          </div>
        </div>

        <article v-if="inFlightPlanRegeneration" class="state-panel" data-testid="training-plan-regeneration-in-flight" aria-live="polite">
          <p class="section-label">計畫更新中</p>
          <h3>正在重新產生訓練計畫</h3>
          <p>目前課表會繼續保留，完成後才會顯示新的安排。</p>
        </article>

        <article v-if="planPhases.length" class="surface-card" data-testid="plan-phase-timeline" aria-label="訓練計畫階段">
          <div class="section-heading">
            <div>
              <p class="section-label">訓練階段</p>
              <h3>目前計畫節奏</h3>
            </div>
            <StatusBadge tone="info">{{ planPhases.length }} 個階段</StatusBadge>
          </div>
          <div class="decision-strip decision-strip--compact" role="list">
            <div v-for="segment in planPhases" :key="`${segment.phase}-${segment.dateRange}`" role="listitem">
              <p class="section-label">{{ segment.label }}</p>
              <strong>{{ segment.focus }}</strong>
              <p>{{ segment.dateRange }}</p>
            </div>
          </div>
        </article>

        <section class="surface-card plan-journey plan-training-journey" data-testid="plan-training-journey" aria-label="訓練旅程">
          <div class="plan-journey__intro">
            <span class="card-kicker">目前訓練週期</span>
            <strong>{{ currentPlanPhase.label }}</strong>
            <p>{{ currentPlanPhase.summary }}</p>
            <div v-if="recoveryWindow" data-testid="plan-recovery-window" role="status">
              <p>{{ recoveryWindow.startsOn }} - {{ recoveryWindow.endsOn }} · {{ userTimezone }}</p>
              <p>上一份計畫已結束，這七天用於恢復，不是新的訓練計畫。第 {{ recoveryWindow.day }} / 7 天</p>
              <p v-if="activePlan && activePlan.starts_on > todayIsoDate">下一份計畫已排定於 {{ activePlan.starts_on }} 開始。</p>
              <p v-else-if="inFlightPlanRegeneration">下一份計畫產生中；恢復週結束後，預定 {{ addCalendarDays(recoveryWindow.endsOn, 1) }} 開始。</p>
              <p v-else-if="recoveryWindow.day === 7">今天是恢復週最後一天，可準備下一份計畫，最早 {{ addCalendarDays(recoveryWindow.endsOn, 1) }} 開始。</p>
            </div>
          </div>
          <div class="plan-journey__phases" :class="{ 'plan-journey__phases--empty': !journeyPhases.length }" data-testid="plan-journey-phases">
            <div class="plan-journey__track" data-testid="plan-journey-track" aria-hidden="true"></div>
            <article
              v-for="phase in journeyPhases"
              :key="phase.id"
              class="plan-journey__stop"
              :class="`plan-journey__stop--${phase.status}`"
              data-testid="plan-journey-stop"
            >
              <span class="plan-journey__node" data-testid="plan-journey-node"></span>
              <div class="plan-journey__meta">
                <span>{{ formatPlanPhaseLabel(phase.label) }}</span>
                <strong>{{ phase.summary }}</strong>
              </div>
            </article>
          </div>
          <template v-if="upcomingRaceEntries.length">
            <article v-for="race in upcomingRaceEntries" :key="race.id" class="plan-race-goal">
              <div class="plan-race-goal__identity"><strong>{{ race.name }}</strong><span>{{ race.distance }} · {{ race.goal }}</span></div>
              <div class="app-dialog__actions plan-race-goal__actions">
                <AppButton data-testid="edit-race" :aria-label="`編輯 ${race.name}`" :disabled="raceGoalBusy || raceEditLoading" @click="editRaceEntry(race, $event)">編輯</AppButton>
                <AppButton data-testid="delete-race" :aria-label="`刪除 ${race.name}`" :disabled="raceGoalBusy || raceEditLoading" @click="requestDeleteRace(race)">刪除</AppButton>
              </div>
              <p class="plan-race-goal__course">{{ raceCourseDetails(race) }}</p>
              <div v-if="activePlan?.race_id === race.id && activePlan.preparation_assessment" class="plan-race-goal__assessment" role="status" data-testid="preparation-assessment">
                <StatusBadge :tone="activePlan.preparation_assessment.status === 'gap' ? 'warning' : activePlan.preparation_assessment.status === 'on_track' ? 'success' : 'info'">{{ preparationStatusLabel(activePlan.preparation_assessment.status) }}</StatusBadge>
                <p>{{ activePlan.preparation_assessment.explanation_zh }}</p>
              </div>
            </article>
          </template>
          <p v-else>尚未設定目標</p>
        </section>

        <p v-if="raceEditLoading" role="status">正在載入賽事…</p>
        <p v-if="raceActionError" class="field-error" role="alert">{{ raceActionError }}</p>
        <p v-if="racePlanReminder" class="inline-note" role="status" data-testid="race-plan-reminder">{{ racePlanReminder }}</p>

        <ConfirmDialog
          v-if="deletingRace"
          title="刪除目標賽事"
          :description="`確定刪除「${deletingRace.name}」？此操作無法復原。既有課表與訓練紀錄會保留，計畫不會自動重新產生。`"
          confirm-label="刪除賽事"
          cancel-label="取消"
          :busy="raceGoalBusy"
          :error="raceDeleteError"
          @cancel="deletingRace = null"
          @confirm="confirmDeleteRace"
        />

        <RaceGoalModal
          v-if="isRaceGoalModalOpen"
          ref="raceGoalModalRef"
          :error="raceFormError"
          :busy="raceGoalBusy"
          :min-date="todayIsoDate"
          :initial-value="editingRace?.values"
          @close="requestCloseRaceGoalModal"
          @submit="submitRaceEntry"
        />

        <ConfirmDialog
          v-if="isRaceGoalConfirmOpen"
          :title="editingRace ? '放棄編輯目標' : '放棄新增目標'"
          description="目前輸入的比賽名稱、日期、距離或目標時間會被清除。"
          :confirm-label="editingRace ? '放棄編輯' : '放棄新增'"
          @cancel="cancelRaceGoalDiscard"
          @confirm="confirmRaceGoalDiscard"
        />

        <TrainingPlanRegenerationSheet
          v-if="isPlanRegenerationSheetOpen && planRegenerationOptions"
          :options="planRegenerationOptions"
          :race-options="planRegenerationRaceOptions"
          :time-zone="userTimezone"
          :busy="planRegenerationBusy"
          :error="planRegenerationError"
          @close="closePlanRegenerationSheet"
          @confirm="confirmPlanRegeneration"
        />
        <div v-else-if="isPlanRegenerationSheetOpen" class="app-dialog" role="presentation" data-testid="training-plan-regeneration-loading">
          <section ref="planRegenerationLoadingDialogRef" class="app-dialog__panel training-plan-regeneration-loading" role="dialog" aria-modal="true" aria-labelledby="training-plan-regeneration-loading-title" tabindex="-1" @keydown="handlePlanRegenerationLoadingKeydown">
            <p class="section-label">訓練計畫</p>
            <h3 id="training-plan-regeneration-loading-title">正在準備重新產生選項</h3>
            <p v-if="planRegenerationError" class="field-error" role="alert">{{ planRegenerationError }}</p>
            <p v-else aria-live="polite">正在確認今日額度與訓練策略。</p>
            <div class="app-dialog__actions">
              <AppButton tone="neutral" type="button" @click="closePlanRegenerationSheet">關閉</AppButton>
            </div>
          </section>
        </div>
        <p v-if="planRegenerationError && !isPlanRegenerationSheetOpen" class="field-error" role="alert">{{ planRegenerationError }}</p>

        <section class="schedule-section" aria-labelledby="schedule-title">
          <div class="section-heading">
            <div>
              <p class="section-label">課表安排</p>
              <h3 id="schedule-title">接下來課表</h3>
            </div>
            <StatusBadge tone="info">{{ visibleScheduleWorkouts.length }} 項</StatusBadge>
          </div>

          <div v-if="scheduleWeekStart && visibleScheduleEnd" class="schedule-week-heading" data-testid="training-week-range">
            <strong>{{ visibleTrainingWeeks === 1 ? '本週課表' : `已顯示 ${visibleTrainingWeeks} 週` }}</strong>
            <span>{{ formatDateLabel(scheduleWeekStart) }}–{{ formatDateLabel(visibleScheduleEnd) }}</span>
          </div>

          <div v-if="visibleScheduleWorkouts.length" class="schedule-list">
            <article v-for="workout in visibleScheduleWorkouts" :key="workout.id" class="schedule-row" :data-testid="`schedule-workout-${workout.id}`">
              <div class="schedule-row__date">
                <strong>{{ workout.weekday }}</strong>
                <span>{{ workout.dateLabel }}</span>
              </div>
              <div class="schedule-row__content">
                <h3>{{ workout.type }}</h3>
                <small v-if="workout.racePriority" class="schedule-row__race-priority">{{ formatRacePriority(workout.racePriority) }}<span v-if="workout.raceGoalId && activePlan?.race_id === workout.raceGoalId"> · 目標賽事</span></small>
                <div v-if="workoutStagePreview(workout).length" class="workout-stage-preview" aria-label="課表步驟摘要">
                  <span v-for="(stage, index) in workoutStagePreview(workout)" :key="`${stage.label}-${index}`"><small>{{ stage.label }}</small><strong>{{ stage.load }}</strong></span>
                </div>
                <p v-else class="schedule-row__purpose">{{ workout.purpose }}</p>
                <p v-if="workoutTargetSummary(workout)" class="workout-step-summary">{{ workoutTargetSummary(workout) }}</p>
              </div>
              <div class="schedule-row__meta">
                <div class="schedule-row__facts">
                  <span v-if="workout.distance">{{ workout.distance }}</span>
                  <span v-if="workout.duration">{{ workout.duration }}</span>
                  <span v-if="workout.phase">{{ workout.phase }}</span>
                </div>
                <AppButton
                  v-if="hasWorkoutDetails(workout)"
                  tone="neutral"
                  type="button"
                  :data-testid="`workout-detail-${workout.id}`"
                  @click="openWorkoutDetails(workout)"
                >
                  細節
                </AppButton>
              </div>
            </article>
          </div>
          <div v-if="hasMoreTrainingWeeks" class="schedule-load-more">
            <AppButton tone="neutral" type="button" data-testid="load-next-training-week" @click="visibleTrainingWeeks += 1">載入下一週</AppButton>
          </div>
          <article v-if="!visibleScheduleWorkouts.length" class="state-panel">
            <p class="section-label">Empty</p>
            <h3>目前沒有已排定課表</h3>
            <p>建立訓練計畫後，Johnny 會在這裡依日期整理接下來的課表。</p>
          </article>
        </section>
      </section>

      <section v-else-if="activeView === 'johnny'" class="page-stack johnny-page" data-testid="johnny-page" aria-labelledby="johnny-title">
        <div class="page-heading">
          <p class="section-label">Johnny 建議</p>
          <h2 id="johnny-title">Johnny</h2>
          <p>今日建議說明課表怎麼執行；需要你確認的課表調整另外列在下方。</p>
        </div>

        <DailyAdviceCard v-if="dailyAdvice" :advice="dailyAdvice" :time-zone="userTimezone" data-testid="johnny-daily-advice" />

        <article v-if="props.inboxState === 'loading'" class="state-panel" aria-live="polite">
          <p class="section-label">Loading</p>
          <h3>正在整理 Johnny 建議</h3>
          <p>Johnny 正在比對課表、恢復訊號和待決定建議。</p>
        </article>

        <article v-else-if="props.inboxState === 'error'" class="state-panel state-panel--danger" role="alert">
          <p class="section-label">Error</p>
          <h3>Johnny 建議載入失敗</h3>
          <p>請稍後再試，或先回到今日檢查主要訓練決策。</p>
          <AppButton tone="neutral" @click="showView('today')">回到今日</AppButton>
        </article>

        <article v-else-if="props.inboxState === 'empty' || displayInboxItems.length === 0" class="state-panel">
          <p class="section-label">Empty</p>
          <h3>目前沒有新的主動建議</h3>
          <p>Johnny 之後會把需要你決定的主動建議放在 Johnny 建議，已處理的建議會保留在歷史區。</p>
        </article>

        <div v-else class="inbox-layout">
          <section class="inbox-section" aria-labelledby="inbox-pending-title">
            <div class="section-heading">
              <div>
                <p class="section-label">Pending</p>
                <h3 id="inbox-pending-title">待決定</h3>
              </div>
              <StatusBadge tone="warning">{{ pendingInboxItems.length }} 項</StatusBadge>
            </div>

            <div class="inbox-list">
              <article
                v-for="item in pendingInboxItems"
                :key="item.id"
                class="recommendation-card inbox-card"
                :data-testid="`inbox-card-${item.id}`"
              >
                <div class="inbox-card__meta">
                  <StatusBadge :tone="priorityTone(item.priority)">{{ item.priorityLabel }}</StatusBadge>
                  <StatusBadge :tone="statusTone(item.status)">{{ item.statusLabel }}</StatusBadge>
                  <span v-if="item.expiresAtLabel" class="data-chip">{{ item.expiresAtLabel }}</span>
                </div>
                <h3>{{ item.title }}</h3>
                <p>{{ item.summary }}</p>
                <div class="decision-strip decision-strip--compact">
                  <div>
                    <p class="section-label">建議</p>
                    <strong>{{ item.proposedAction }}</strong>
                  </div>
                  <div>
                    <p class="section-label">決定脈絡</p>
                    <strong>{{ item.rationale }}</strong>
                  </div>
                </div>
                <EvidenceList :items="item.evidence" />
                <RecommendationActions
                  :busy-action="inboxBusyRecommendationId === item.id ? inboxBusyAction : ''"
                  @accept="handleInboxAccept(item)"
                  @keep="handleInboxKeep(item)"
                />
              </article>
            </div>
          </section>

          <section v-if="historicalInboxItems.length" class="inbox-section inbox-section--history" data-testid="inbox-history" aria-labelledby="inbox-history-title">
            <div class="section-heading">
              <div>
                <p class="section-label">History</p>
                <h3 id="inbox-history-title">已處理</h3>
              </div>
              <StatusBadge tone="info">{{ historicalInboxItems.length }} 項</StatusBadge>
            </div>
            <div class="inbox-list inbox-list--history">
              <article
                v-for="item in historicalInboxItems"
                :key="item.id"
                class="inbox-card inbox-card--historical"
                :data-testid="`inbox-card-${item.id}`"
              >
                <div class="inbox-card__meta">
                  <StatusBadge :tone="priorityTone(item.priority)">{{ item.priorityLabel }}</StatusBadge>
                  <StatusBadge :tone="statusTone(item.status)">{{ item.statusLabel }}</StatusBadge>
                </div>
                <h3>{{ item.title }}</h3>
                <p>{{ item.summary }}</p>
                <EvidenceList :items="item.evidence" />
              </article>
            </div>
          </section>
        </div>
        <section class="surface-card johnny-review" data-testid="johnny-weekly-review" aria-labelledby="johnny-review-title">
          <span class="card-kicker">Weekly review</span>
          <h3 id="johnny-review-title">這週先守住連續性</h3>
          <p>Johnny 會把待決定建議、恢復訊號和計畫變動放在這裡。Conversation 功能目前尚未公開。</p>
        </section>
      </section>

      <section v-else-if="activeView === 'conversation'" class="page-stack" aria-labelledby="conversation-title">
        <div class="page-heading">
          <p class="section-label">對話</p>
          <h2 id="conversation-title">Johnny 訓練對話</h2>
          <p>用來追問訓練原因、證據與下一步，不取代今日的主要決策面板。</p>
        </div>

        <article v-if="props.conversationState === 'loading'" class="state-panel" aria-live="polite">
          <p class="section-label">Loading</p>
          <h3>正在整理對話脈絡</h3>
          <p>Johnny 正在讀取最近的訊息、證據與建議狀態。</p>
        </article>

        <article v-else-if="props.conversationState === 'error'" class="state-panel state-panel--danger" role="alert">
          <p class="section-label">Error</p>
          <h3>對話載入失敗</h3>
          <p>請稍後再試，或先回到今日查看訓練決策。</p>
          <AppButton tone="neutral" @click="showView('today')">回到今日</AppButton>
        </article>

        <article v-else-if="props.conversationState === 'empty' || !activeThread" class="state-panel">
          <p class="section-label">Empty</p>
          <h3>還沒有對話紀錄</h3>
          <p>當你想追問訓練計畫、恢復證據或建議原因時，可以從這裡開始。</p>
        </article>

        <div v-else class="conversation-layout">
          <aside class="thread-list" aria-label="對話列表">
            <button
              v-for="thread in displayThreads"
              :key="thread.id"
              class="thread-button"
              :class="{ 'thread-button--active': activeThread?.id === thread.id }"
              type="button"
              :data-thread-id="thread.id"
              @click="selectThread(thread.id)"
            >
              <strong>{{ thread.title }}</strong>
              <span>{{ thread.summary }}</span>
              <small>{{ thread.updatedLabel }}</small>
            </button>
          </aside>

          <section class="message-panel" aria-label="訊息內容">
            <article v-if="linkedRecommendation || activeThread.linkedRecommendation" class="linked-context">
              <div class="section-heading">
                <div>
                  <p class="section-label">已連結建議</p>
                  <h3>{{ (linkedRecommendation || activeThread.linkedRecommendation)?.title }}</h3>
                </div>
                <StatusBadge :tone="statusTone((linkedRecommendation || activeThread.linkedRecommendation)?.status || 'pending')">
                  {{ (linkedRecommendation || activeThread.linkedRecommendation)?.statusLabel }}
                </StatusBadge>
              </div>
              <p>{{ (linkedRecommendation || activeThread.linkedRecommendation)?.evidenceSummary }}</p>
              <EvidenceList :items="(linkedRecommendation || activeThread.linkedRecommendation)?.evidence || []" />
            </article>

            <div class="message-stack">
              <article
                v-for="message in activeThread.messages"
                :key="message.id"
                class="message-card"
                :class="`message-card--${message.role}`"
              >
                <div class="message-card__meta">
                  <strong>{{ message.authorLabel }}</strong>
                  <span>{{ message.timestampLabel }}</span>
                </div>
                <p>{{ message.content }}</p>
                <EvidenceList v-if="message.evidence?.length" :items="message.evidence" />
                <article v-if="message.proposedAction" class="proposed-action" data-testid="conversation-proposed-action">
                  <div class="section-heading">
                    <div>
                      <p class="section-label">建議動作</p>
                      <h3>{{ message.proposedAction.title }}</h3>
                    </div>
                    <StatusBadge tone="warning">待決定</StatusBadge>
                  </div>
                  <p>{{ message.proposedAction.summary }}</p>
                  <div class="decision-strip decision-strip--compact">
                    <div>
                      <p class="section-label">建議</p>
                      <strong>{{ message.proposedAction.proposedAction }}</strong>
                    </div>
                    <div>
                      <p class="section-label">原因</p>
                      <strong>{{ message.proposedAction.rationale }}</strong>
                    </div>
                  </div>
                  <RecommendationActions
                    @accept="handleActionPlaceholder"
                    @keep="handleActionPlaceholder"
                  />
                </article>
              </article>
            </div>

            <form class="composer-form" data-testid="conversation-form" novalidate @submit.prevent="submitConversation">
              <label for="conversation-message">問 Johnny</label>
              <textarea
                id="conversation-message"
                v-model="conversationMessage"
                name="conversationMessage"
                rows="3"
                style="resize: none"
                autocomplete="off"
                :aria-invalid="conversationError ? 'true' : 'false'"
                aria-describedby="conversation-message-error conversation-message-status"
                @compositionstart="isComposing = true"
                @compositionend="isComposing = false"
                @keydown="handleComposerKeydown"
              />
              <div class="composer-form__footer">
                <p v-if="conversationError" id="conversation-message-error" class="field-error">{{ conversationError }}</p>
                <p v-else-if="conversationStatus" id="conversation-message-status" class="inline-note">{{ conversationStatus }}</p>
                <p v-else id="conversation-message-status">Enter 送出，Shift + Enter 換行。</p>
                <AppButton tone="primary" type="submit" :busy="conversationBusy">送出問題</AppButton>
              </div>
            </form>
          </section>
        </div>
      </section>

      <section v-else-if="activeView === 'athlete'" class="page-stack" aria-labelledby="athlete-settings-title">
        <div class="page-heading">
          <p class="section-label">Athlete Profile</p>
          <h2 id="athlete-settings-title">運動員</h2>
          <p>這些設定會成為 Johnny 產生建議與訓練計畫時的個人限制與偏好。</p>
        </div>

        <section class="surface-card athlete-baseline" data-testid="athlete-baseline" aria-labelledby="athlete-baseline-title">
          <span class="card-kicker">Athlete Baseline</span>
          <h3 id="athlete-baseline-title">Johnny 用來個人化你的基準</h3>
          <dl>
            <div><dt>週跑量</dt><dd>{{ athleteBaselineSnapshot.weeklyMileage }}</dd></div>
            <div><dt>經驗</dt><dd>{{ athleteBaselineSnapshot.experience }}</dd></div>
            <div><dt>傷痛狀態</dt><dd>{{ athleteBaselineSnapshot.injuryStatus }}</dd></div>
            <div><dt>訓練節奏</dt><dd>{{ athleteBaselineSnapshot.rhythm }}</dd></div>
          </dl>
          <p>{{ athleteBaselineSnapshot.recentMetrics.join(' · ') }}</p>
        </section>

        <form class="surface-card athlete-settings-form" data-testid="athlete-settings-form" novalidate @submit.prevent="submitAthleteSettings">
          <div class="form-grid">
            <label>
              時區
              <select
                v-model="athleteSettings.timezone"
                name="athleteTimezone"
                autocomplete="off"
                :aria-invalid="athleteSettingsFieldErrors.timezone ? 'true' : 'false'"
                aria-describedby="athlete-timezone-error athlete-settings-status"
              >
                <option v-for="timezone in athleteTimezoneOptions" :key="timezone.value" :value="timezone.value">{{ timezone.label }}</option>
              </select>
              <span v-if="athleteSettingsFieldErrors.timezone" id="athlete-timezone-error" class="field-error">{{ athleteSettingsFieldErrors.timezone }}</span>
            </label>

            <label>
              經驗程度
              <select v-model="athleteSettings.experienceLevel" name="experienceLevel" autocomplete="off">
                <option value="">未設定</option>
                <option value="beginner">初學</option>
                <option value="intermediate">中階</option>
                <option value="advanced">進階</option>
              </select>
            </label>

            <label>
              單位
              <select v-model="athleteSettings.unitPreference" name="unitPreference" autocomplete="off" @change="handleAthleteUnitChange">
                <option value="metric">公里</option>
                <option value="imperial">英里</option>
              </select>
            </label>

            <label>
              目前每週跑量
              <input
                v-model="athleteSettings.currentWeeklyMileage"
                name="currentWeeklyMileage"
                type="number"
                min="0"
                step="0.1"
                inputmode="decimal"
                :aria-invalid="athleteSettingsFieldErrors.currentWeeklyMileage ? 'true' : 'false'"
                aria-describedby="athlete-mileage-error athlete-settings-status"
              />
              <span v-if="athleteSettingsFieldErrors.currentWeeklyMileage" id="athlete-mileage-error" class="field-error">{{ athleteSettingsFieldErrors.currentWeeklyMileage }}</span>
            </label>

            <label>
              每週最多跑步次數
              <input
                v-model="athleteSettings.maxRunsPerWeek"
                name="maxRunsPerWeek"
                type="number"
                min="1"
                max="7"
                step="1"
                inputmode="numeric"
                :aria-invalid="athleteSettingsFieldErrors.maxRunsPerWeek ? 'true' : 'false'"
                aria-describedby="athlete-max-runs-error athlete-settings-status"
              />
              <span v-if="athleteSettingsFieldErrors.maxRunsPerWeek" id="athlete-max-runs-error" class="field-error">{{ athleteSettingsFieldErrors.maxRunsPerWeek }}</span>
            </label>

            <label>
              質量課表
              <input
                v-model="athleteSettings.maxHardSessionsPerWeek"
                name="maxHardSessionsPerWeek"
                type="number"
                min="0"
                max="2"
                step="1"
                inputmode="numeric"
                :aria-invalid="athleteSettingsFieldErrors.maxHardSessionsPerWeek ? 'true' : 'false'"
                aria-describedby="athlete-max-hard-sessions-error athlete-settings-status"
              />
              <span>包含間歇、節奏、坡跑與長跑。Johnny 會依恢復與傷痛狀態下修。</span>
              <span v-if="athleteSettingsFieldErrors.maxHardSessionsPerWeek" id="athlete-max-hard-sessions-error" class="field-error">{{ athleteSettingsFieldErrors.maxHardSessionsPerWeek }}</span>
            </label>

            <fieldset class="athlete-target-settings">
              <legend>訓練目標</legend>
            <label>
              閾值配速來源
              <select v-model="athleteSettings.thresholdPaceSource" name="thresholdPaceSource">
                <option value="garmin">Garmin 自動同步</option>
                <option value="manual">手動設定</option>
              </select>
            </label>
            <label v-if="athleteSettings.thresholdPaceSource === 'manual'">
              閾值配速（分/公里，可選）
              <input
                v-model="athleteSettings.thresholdPace"
                name="thresholdPace"
                type="text"
                inputmode="numeric"
                placeholder="5:00"
                autocomplete="off"
                :aria-invalid="athleteSettingsFieldErrors.thresholdPace ? 'true' : 'false'"
                aria-describedby="athlete-threshold-pace-error athlete-settings-status"
              />
              <span v-if="athleteSettingsFieldErrors.thresholdPace" id="athlete-threshold-pace-error" class="field-error">{{ athleteSettingsFieldErrors.thresholdPace }}</span>
            </label>

            <div class="athlete-target-status" data-testid="garmin-threshold-status">
              <strong>Garmin 閾值配速：{{ garminTrainingEvidence.lactate_threshold?.threshold_pace_seconds_per_km ? `${formatPace(garminTrainingEvidence.lactate_threshold.threshold_pace_seconds_per_km)} /km` : '尚無資料' }}</strong>
              <p>{{ garminEvidenceStatus('lactate_threshold') }}</p>
              <p v-if="athleteSettings.thresholdPaceSource === 'manual'">課表使用手動配速；選擇 Garmin 並儲存後才會改用同步值。</p>
            </div>
            <div class="athlete-target-status" data-testid="garmin-heart-rate-status">
              <strong>心率區間：{{ garminTrainingEvidence.heart_rate_zones?.sport === 'RUNNING' ? 'Garmin 跑步設定' : garminTrainingEvidence.heart_rate_zones?.sport === 'DEFAULT' ? 'Garmin 一般設定' : '尚無資料' }}</strong>
              <p>{{ garminEvidenceStatus('heart_rate_zones') }}</p>
              <p>心率區間由 Garmin 提供，無需填寫靜息或最高心率。</p>
            </div>

            </fieldset>

            <label>
              偏好長跑日
              <select
                v-model="athleteSettings.preferredLongRunDay"
                name="preferredLongRunDay"
                autocomplete="off"
                :aria-invalid="athleteSettingsFieldErrors.preferredLongRunDay ? 'true' : 'false'"
                aria-describedby="athlete-long-run-error athlete-settings-status"
              >
                <option v-for="day in weekDayOptions" :key="day.value" :value="day.value">{{ day.label }}</option>
              </select>
              <span v-if="athleteSettingsFieldErrors.preferredLongRunDay" id="athlete-long-run-error" class="field-error">{{ athleteSettingsFieldErrors.preferredLongRunDay }}</span>
            </label>
          </div>

          <fieldset class="choice-fieldset" :aria-invalid="athleteSettingsFieldErrors.preferredTrainingDays ? 'true' : 'false'" aria-describedby="athlete-training-days-error athlete-settings-status">
            <legend>偏好訓練日</legend>
            <label v-for="day in weekDayOptions" :key="day.value">
              <input v-model="athleteSettings.preferredTrainingDays" type="checkbox" name="preferredTrainingDays" :value="day.value" />
              <span>{{ day.label }}</span>
            </label>
            <span v-if="athleteSettingsFieldErrors.preferredTrainingDays" id="athlete-training-days-error" class="field-error">{{ athleteSettingsFieldErrors.preferredTrainingDays }}</span>
          </fieldset>

          <div class="form-grid">
            <label>
              傷痛狀態
              <select v-model="athleteSettings.injuryStatus" name="injuryStatus" autocomplete="off">
                <option value="none">沒有</option>
                <option value="current">目前有</option>
                <option value="recent">近期有</option>
                <option value="recurring">反覆發生</option>
              </select>
            </label>
          </div>

          <fieldset class="choice-fieldset">
            <legend>傷痛部位</legend>
            <label v-for="area in injuryAreaOptions" :key="area.value">
              <input
                v-model="athleteSettings.injuryAreas"
                type="checkbox"
                :name="`injuryArea-${area.value}`"
                :value="area.value"
              />
              <span>{{ area.label }}</span>
            </label>
          </fieldset>

          <label class="field-block">
            傷痛補充說明
            <textarea
              v-model="athleteSettings.injuryNotes"
              name="injuryNotes"
              rows="4"
              style="resize: none"
              :aria-invalid="athleteSettingsFieldErrors.injuryNotes ? 'true' : 'false'"
              aria-describedby="athlete-injury-notes-error athlete-settings-status"
            ></textarea>
            <span v-if="athleteSettingsFieldErrors.injuryNotes" id="athlete-injury-notes-error" class="field-error">{{ athleteSettingsFieldErrors.injuryNotes }}</span>
          </label>

          <div class="form-footer athlete-settings-form__footer">
            <p v-if="athleteSettingsError" id="athlete-settings-status" class="field-error" role="alert">{{ athleteSettingsError }}</p>
            <p v-else-if="athleteSettingsMessage" id="athlete-settings-status" class="inline-note" aria-live="polite">{{ athleteSettingsMessage }}</p>
            <p v-else id="athlete-settings-status">偏好訓練日可以留空，Johnny 會在產生計畫時自行安排。</p>
            <AppButton tone="primary" type="submit" :busy="athleteSettingsBusy">儲存設定</AppButton>
          </div>
        </form>
      </section>

      <section v-else-if="activeView === 'data'" class="page-stack" aria-labelledby="sources-title">
        <div class="page-heading">
          <p class="section-label">資料連接</p>
          <h2 id="sources-title">連接資料</h2>
          <p>Johnny 會用近期訓練、睡眠、HRV 和恢復訊號判斷今天是否該調整課表。</p>
        </div>

        <section class="surface-card signal-coverage" data-testid="signal-coverage" aria-labelledby="signal-coverage-title">
          <span class="card-kicker">Signal Coverage</span>
          <h3 id="signal-coverage-title">Johnny 已有 {{ coveredSignalCount }}/{{ signalCoverage.length }} 個訓練訊號</h3>
          <div class="signal-coverage__grid">
            <span v-for="item in signalCoverage" :key="item.id" class="signal-pill" :class="{ 'signal-pill--covered': item.covered }">
              <strong>{{ item.label }}</strong>
              <small>{{ item.source }}</small>
            </span>
          </div>
        </section>

        <div class="provider-grid">
          <ProviderCard
            v-for="provider in providers"
            :key="provider.id"
            :provider="provider"
            :connection="providerConnection(provider)"
            :resource-rows="providerSyncRows(provider)"
            :last-sync-label="providerLastSyncLabel(provider)"
            :busy-action="providerBusyAction(provider)"
            :disconnect-confirming="isDisconnectConfirming(provider)"
            @select="selectProvider"
            @sync="syncGarminConnection"
            @disconnect="requestDisconnectGarmin"
            @confirm-disconnect="confirmDisconnectGarmin"
            @cancel-disconnect="cancelDisconnectGarmin"
          />
        </div>

        <p v-if="providerMessage" class="inline-note" aria-live="polite">{{ providerMessage }}</p>

        <div
          v-if="isProviderDialogOpen"
          class="provider-dialog"
          role="presentation"
          @click.self="closeProviderDialog"
          @keydown.esc="closeProviderDialog"
        >
          <form
            class="provider-dialog__panel provider-form"
            data-testid="provider-form"
            role="dialog"
            aria-modal="true"
            aria-labelledby="provider-dialog-title"
            novalidate
            @submit.prevent="submitProvider"
          >
            <div class="section-heading">
              <div>
                <p class="section-label">Garmin Connect experimental login</p>
                <h3 id="provider-dialog-title">{{ selectedProvider.name }}</h3>
              </div>
              <StatusBadge :tone="garminStatus(garminConnection).tone">{{ garminStatus(garminConnection).label }}</StatusBadge>
            </div>
            <p>Johnny 會用這組登入資料建立 Garmin 連線工作階段。密碼只用於這次連接，不會顯示在訊息中。</p>
            <label>
              Garmin 電子郵件
              <input
                v-model="garminEmail"
                name="garminEmail"
                type="email"
                autocomplete="off"
                :aria-invalid="providerError ? 'true' : 'false'"
                aria-describedby="provider-form-error"
              />
            </label>
            <label>
              Garmin 密碼
              <input
                v-model="garminPassword"
                name="garminPassword"
                type="password"
                autocomplete="off"
                :aria-invalid="providerError ? 'true' : 'false'"
                aria-describedby="provider-form-error"
              />
            </label>
            <label>
              Garmin 區域
              <select v-model="garminRegion" name="garminRegion" autocomplete="off">
                <option value="global">全球</option>
                <option value="china">中國</option>
              </select>
            </label>
            <p v-if="providerError" id="provider-form-error" class="field-error">{{ providerError }}</p>
            <div class="provider-dialog__actions">
              <AppButton tone="primary" type="submit" :busy="providerBusy === 'connect'">連接 Garmin</AppButton>
              <AppButton tone="neutral" type="button" :disabled="providerBusy === 'connect'" @click="closeProviderDialog">取消</AppButton>
            </div>
          </form>
        </div>
      </section>

      <section v-else class="empty-panel" :aria-labelledby="`${activeView}-title`">
        <p class="section-label">{{ activeTitle }}</p>
        <h2 :id="`${activeView}-title`">{{ activeTitle }}</h2>
        <p>這個工作流會依照對應 OpenSpec change 補上完整互動。</p>
      </section>
    </main>

    <div
      v-if="selectedWorkoutDetail"
      class="app-dialog"
      role="presentation"
      data-testid="workout-detail-modal"
      @click.self="closeWorkoutDetails"
      @keydown.esc="closeWorkoutDetails"
    >
      <section class="app-dialog__panel workout-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="workout-detail-title" tabindex="-1">
        <div class="workout-detail-dialog__header">
          <div>
            <p class="workout-detail-dialog__eyebrow">{{ selectedWorkoutDetail.dateLabel }} · {{ selectedWorkoutDetail.weekday }}<span v-if="selectedWorkoutDetail.phase"> · {{ selectedWorkoutDetail.phase }}</span><span v-if="selectedWorkoutDetail.racePriority"> · {{ formatRacePriority(selectedWorkoutDetail.racePriority) }}</span><span v-if="selectedWorkoutDetail.raceGoalId && activePlan?.race_id === selectedWorkoutDetail.raceGoalId"> · 目標賽事</span></p>
            <h3 id="workout-detail-title">{{ selectedWorkoutDetail.type }}</h3>
          </div>
          <AppButton tone="neutral" type="button" data-testid="workout-detail-close" aria-label="關閉課表詳情" title="關閉" @click="closeWorkoutDetails"><span aria-hidden="true">×</span></AppButton>
        </div>
        <div class="workout-detail-dialog__facts" aria-label="課表資訊">
          <div v-if="selectedWorkoutDetail.distance"><small>距離</small><strong>{{ selectedWorkoutDetail.distance }}</strong></div>
          <div v-if="selectedWorkoutDetail.duration"><small>時間</small><strong>{{ selectedWorkoutDetail.duration }}</strong></div>
          <div v-if="selectedWorkoutDetail.pace"><small>目標配速</small><strong>{{ selectedWorkoutDetail.pace }}</strong></div>
          <div v-if="selectedWorkoutDetail.heartRateZone"><small>心率區間</small><strong>{{ selectedWorkoutDetail.heartRateZone }}</strong></div>
        </div>
        <div class="workout-detail-dialog__purpose"><strong>訓練目的</strong><p>{{ selectedWorkoutDetail.purpose }}</p></div>
        <div v-if="selectedWorkoutStages.length" class="workout-detail-dialog__section-label">課表步驟</div>
        <ol v-if="selectedWorkoutStages.length" class="workout-stage-list" aria-label="課表步驟" data-testid="workout-detail-steps">
          <li v-for="(stage, stageIndex) in selectedWorkoutStages" :key="`${stage.key}-${stageIndex}`" class="workout-stage" :class="`workout-stage--${stage.key}`">
            <div class="workout-stage__heading">
              <span class="workout-stage__index">{{ String(stageIndex + 1).padStart(2, '0') }}</span>
              <h4>{{ stage.label }}</h4>
            </div>
            <div class="workout-step-list">
              <div
                v-for="row in stage.rows"
                :key="row.key"
                class="workout-step-row"
                :class="`workout-step-row--depth-${row.depth}`"
              >
                <strong>{{ row.label }}</strong>
                <span>{{ row.load }}</span>
                <span v-if="row.target">{{ row.target }}</span>
                <small v-if="row.note">{{ row.note }}</small>
              </div>
            </div>
          </li>
        </ol>
        <article v-if="selectedWorkoutDetail.coachNote" class="coach-note" data-testid="workout-detail-coach-note">
          <p class="section-label">Johnny 提醒</p>
          <p>{{ selectedWorkoutDetail.coachNote }}</p>
        </article>
      </section>
    </div>
  </div>
</template>
