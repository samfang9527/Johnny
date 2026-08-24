<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  acceptRecommendation,
  ApiRequestError,
  connectGarminIntegration,
  createRaceGoal,
  discussRecommendation,
  getCurrentUser,
  getTodayContext,
  listRaceGoals,
  listRecommendations,
  listTrainingPlans,
  rejectRecommendation,
  signInWithEmail,
  signOut,
  signUpWithEmail,
  startGoogleSignIn,
  submitConversationMessage,
} from './api/client'
import AppButton from './components/AppButton.vue'
import EvidenceList from './components/EvidenceList.vue'
import ProviderCard from './components/ProviderCard.vue'
import RecommendationActions from './components/RecommendationActions.vue'
import StatusBadge from './components/StatusBadge.vue'
import {
  conversationThreads as fixtureConversationThreads,
  futureRaces as fixtureFutureRaces,
  inboxRecommendations as fixtureInboxRecommendations,
  plannedWorkouts as fixtureWorkouts,
  providers,
  raceSummary as fixtureRaceSummary,
  recommendation as fixtureRecommendation,
  recoveryEvidence as fixtureRecoveryEvidence,
  todayWorkout as fixtureTodayWorkout,
  unavailableSignals as fixtureUnavailableSignals,
} from './fixtures'
import type {
  ConversationThread,
  CurrentUser,
  InboxRecommendation,
  LinkedRecommendationContext,
  ProviderOption,
  RecommendationStatus,
  RecommendationSummary,
  RaceSummary,
  ViewKey,
  WorkoutSummary,
  EvidenceItem,
  IntegrationConnectionResponse,
  SyncResourceSummary,
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
  { key: 'calendar', label: '訓練安排' },
  { key: 'inbox', label: 'Agent 收件匣' },
  { key: 'sources', label: '資料來源' },
]

function viewFromHash(): ViewKey | undefined {
  if (typeof window === 'undefined') {
    return undefined
  }
  const hashView = window.location.hash.replace('#', '') as ViewKey
  return navItems.some((item) => item.key === hashView) ? hashView : undefined
}

const activeView = ref<ViewKey>(props.initialView ?? viewFromHash() ?? 'today')
const busyAction = ref('')
const recommendationStatus = ref(fixtureRecommendation.status)
const apiRaceSummary = ref<RaceSummary | null>(null)
const apiTodayWorkout = ref<WorkoutSummary | null>(null)
const apiWorkouts = ref<WorkoutSummary[]>([])
const apiRecommendation = ref<RecommendationSummary | null>(null)
const apiRecoveryEvidence = ref<EvidenceItem[]>([])
const apiUnavailableSignals = ref<string[]>([])
const apiInboxItems = ref<InboxRecommendation[]>([])
const selectedProvider = ref<ProviderOption>(providers[0])
const garminEmail = ref('')
const garminPassword = ref('')
const garminRegion = ref<'global' | 'china'>('global')
const garminConnection = ref<IntegrationConnectionResponse | null>(null)
const providerMessage = ref('')
const providerError = ref('')
const providerBusy = ref(false)
const conversationMessage = ref('')
const conversationError = ref('')
const conversationStatus = ref('')
const conversationBusy = ref(false)
const isComposing = ref(false)
const linkedRecommendation = ref<LinkedRecommendationContext | null>(null)
const inboxBusyRecommendationId = ref('')
const inboxBusyAction = ref('')
const recommendationDecisions = ref<Record<string, RecommendationStatus>>({})
const raceEntries = ref<RaceSummary[]>(fixtureFutureRaces)
const raceName = ref('')
const raceDate = ref('')
const raceDistance = ref('')
const raceGoal = ref('')
const raceFormError = ref('')
const raceFormMessage = ref('')
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

const activeTitle = computed(() => navItems.find((item) => item.key === activeView.value)?.label || '今日')
const isAuthenticated = computed(() => authStatus.value === 'authenticated')
const effectiveTodayState = computed(() => {
  if (props.todayState !== 'full') {
    return props.todayState
  }
  return hasBackendHydrated.value && shouldRequireAuth() && !apiRaceSummary.value && !apiTodayWorkout.value ? 'empty' : 'full'
})
const raceSummary = computed(() => apiRaceSummary.value ?? (hasBackendHydrated.value && shouldRequireAuth() ? emptyRaceSummary() : fixtureRaceSummary))
const todayWorkout = computed(() => apiTodayWorkout.value ?? (hasBackendHydrated.value && shouldRequireAuth() ? emptyWorkoutSummary() : fixtureTodayWorkout))
const recoveryEvidence = computed(() => {
  if (apiRecoveryEvidence.value.length) {
    return apiRecoveryEvidence.value
  }
  return hasBackendHydrated.value && shouldRequireAuth() ? [] : fixtureRecoveryEvidence
})
const unavailableSignals = computed(() => {
  if (apiUnavailableSignals.value.length) {
    return apiUnavailableSignals.value
  }
  return hasBackendHydrated.value && shouldRequireAuth() ? [] : fixtureUnavailableSignals
})
const recommendation = computed(() => apiRecommendation.value ?? fixtureRecommendation)
const displayWorkouts = computed(() => props.workouts ?? (apiWorkouts.value.length ? apiWorkouts.value : hasBackendHydrated.value && shouldRequireAuth() ? [] : fixtureWorkouts))
const displayThreads = computed(() => props.conversationThreads ?? fixtureConversationThreads)
const displayInboxItems = computed(() => {
  const source = props.inboxItems ?? (apiInboxItems.value.length ? apiInboxItems.value : hasBackendHydrated.value && shouldRequireAuth() ? [] : fixtureInboxRecommendations)
  return source.map((item) => {
    const status = recommendationDecisions.value[item.id]
    return status ? { ...item, status, statusLabel: statusLabel(status) } : item
  })
})
const activeThreadId = ref(displayThreads.value[0]?.id ?? '')
const activeThread = computed(() => displayThreads.value.find((thread) => thread.id === activeThreadId.value) ?? displayThreads.value[0])
const pendingInboxItems = computed(() => displayInboxItems.value.filter((item) => item.status === 'pending'))
const historicalInboxItems = computed(() => displayInboxItems.value.filter((item) => item.status !== 'pending'))
const raceCalendarMonths = computed(() => buildRaceCalendarMonths(raceEntries.value))

async function initializeAuth() {
  if (!shouldRequireAuth()) {
    authStatus.value = 'authenticated'
    await hydrateFromBackend()
    return
  }

  authStatus.value = 'checking'
  authError.value = ''
  try {
    const response = await getCurrentUser()
    currentUser.value = response.data
    authStatus.value = 'authenticated'
    await hydrateFromBackend()
  } catch (error) {
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
  try {
    const response =
      authMode.value === 'signup'
        ? await signUpWithEmail({ display_name: authDisplayName.value.trim(), email, password })
        : await signInWithEmail({ email, password })
    currentUser.value = response.data.user
    authDisplayName.value = response.data.user.display_name || authDisplayName.value
    authPassword.value = ''
    authPasswordConfirm.value = ''
    authStatus.value = 'authenticated'
    authMessage.value = authMode.value === 'signup' ? '帳號已建立' : '已登入'
    await hydrateFromBackend()
  } catch (error) {
    authError.value = error instanceof ApiRequestError && error.status === 401 ? 'Email 或密碼不正確' : '登入失敗，請檢查資料後再試。'
  } finally {
    authBusy.value = false
  }
}

async function handleGoogleSignIn() {
  authError.value = ''
  authBusy.value = true
  try {
    const callbackUrl = typeof window !== 'undefined' ? window.location.hash || '#today' : '#today'
    const response = await startGoogleSignIn(callbackUrl, authMode.value === 'signup' ? authDisplayName.value.trim() || undefined : undefined)
    if (typeof window !== 'undefined') {
      window.location.assign(response.data.authorization_url)
    }
  } catch {
    authError.value = 'Google 登入尚未設定完成，請先使用 Email 登入。'
    authBusy.value = false
  }
}

async function handleSignOut() {
  await signOut()
  currentUser.value = null
  authStatus.value = shouldRequireAuth() ? 'anonymous' : 'authenticated'
}

function handleSessionExpiry(error: unknown): boolean {
  if (shouldRequireAuth() && error instanceof ApiRequestError && error.status === 401) {
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

async function handleAccept() {
  busyAction.value = 'accept'
  try {
    await acceptRecommendation(recommendation.value.id)
    recommendationStatus.value = 'accepted'
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    busyAction.value = ''
  }
}

async function handleKeepOriginal() {
  busyAction.value = 'keep'
  try {
    await rejectRecommendation(recommendation.value.id)
    recommendationStatus.value = 'kept'
  } catch (error) {
    handleSessionExpiry(error)
  } finally {
    busyAction.value = ''
  }
}

async function handleDiscuss() {
  busyAction.value = 'discuss'
  try {
    await discussRecommendation(recommendation.value.id, '我想了解這次調整的原因。')
    linkedRecommendation.value = {
      id: recommendation.value.id,
      title: recommendation.value.title,
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
  providerMessage.value = ''
}

async function submitProvider() {
  providerError.value = ''
  providerMessage.value = ''
  if (selectedProvider.value.id !== 'garmin_connect') {
    providerError.value = '這個資料來源尚未開放連接。'
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
    providerBusy.value = true
    const response = await connectGarminIntegration({
      email: garminEmail.value.trim(),
      password: garminPassword.value,
      region: garminRegion.value,
    })
    garminConnection.value = response.data
    providerMessage.value = `${response.data.provider_display_name || 'Garmin'} 已連接`
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      providerError.value = 'Garmin 連接失敗。請檢查登入資料後再試一次。'
    }
  } finally {
    garminPassword.value = ''
    providerBusy.value = false
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
  providerMessage.value = '這個決策會在下一階段同步到訓練安排。'
}

async function submitRaceEntry() {
  raceFormError.value = ''
  raceFormMessage.value = ''
  if (!raceName.value.trim() || !raceDate.value) {
    raceFormError.value = '請輸入名稱與日期'
    return
  }

  const distanceMeters = parseDistanceMeters(raceDistance.value)
  if (!distanceMeters) {
    raceFormError.value = '請輸入距離，例如 Half Marathon、Marathon 或 10 km'
    return
  }

  try {
    const response = await createRaceGoal({
      name: raceName.value.trim(),
      race_date: raceDate.value,
      distance_meters: distanceMeters,
      target_finish_seconds: parseTargetFinishSeconds(raceGoal.value),
      priority: 'primary',
      status: 'planned',
    })
    const created = mapRaceGoal(response.data)
    if (created) {
      raceEntries.value = [...raceEntries.value.filter((race) => `${race.name}-${race.date}` !== `${created.name}-${created.date}`), created]
    }
    raceName.value = ''
    raceDate.value = ''
    raceDistance.value = ''
    raceGoal.value = ''
    raceFormMessage.value = '賽事已加入訓練安排'
  } catch (error) {
    if (!handleSessionExpiry(error)) {
      raceFormError.value = '訓練安排儲存失敗，請稍後再試。'
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
  void initializeAuth()
})

async function hydrateFromBackend() {
  const anchorDate = new Date().toISOString().slice(0, 10)
  const [todayResult, recommendationsResult, plansResult, racesResult] = await Promise.allSettled([
    getTodayContext(anchorDate),
    listRecommendations(),
    listTrainingPlans(),
    listRaceGoals(anchorDate, sixMonthWindowEnd(anchorDate)),
  ])
  const results = [todayResult, recommendationsResult, plansResult, racesResult]
  if (results.some((result) => result.status === 'rejected' && handleSessionExpiry(result.reason))) {
    return
  }

  if (todayResult.status === 'fulfilled') {
    applyTodayPayload(todayResult.value.data)
  }
  if (recommendationsResult.status === 'fulfilled') {
    applyRecommendationsPayload(Array.isArray(recommendationsResult.value.data) ? recommendationsResult.value.data : [])
  }
  if (plansResult.status === 'fulfilled') {
    applyTrainingPlansPayload(Array.isArray(plansResult.value.data) ? plansResult.value.data : [])
  }
  if (racesResult.status === 'fulfilled') {
    applyRaceGoalsPayload(Array.isArray(racesResult.value.data) ? racesResult.value.data : [])
  }
  hasBackendHydrated.value = true
}

function applyTodayPayload(payload: Record<string, unknown>) {
  const nextRace = payload.next_race as Record<string, unknown> | null | undefined
  if (nextRace?.name && nextRace.race_date) {
    apiRaceSummary.value = {
      name: String(nextRace.name),
      date: String(nextRace.race_date),
      distance: formatDistance(Number(nextRace.distance_meters || 0)),
      goal: 'MVP goal',
      daysRemaining: daysUntil(String(nextRace.race_date)),
    }
  }

  const workouts = Array.isArray(payload.scheduled_workouts) ? payload.scheduled_workouts : []
  const mappedWorkouts = workouts.map(mapWorkout).filter((workout): workout is WorkoutSummary => workout !== null)
  if (mappedWorkouts.length) {
    apiTodayWorkout.value = mappedWorkouts[0]
  }

  const recovery = payload.recovery as Record<string, unknown> | undefined
  if (recovery && Object.keys(recovery).length) {
    apiRecoveryEvidence.value = Object.entries(recovery).slice(0, 4).map(([metric, value]) => ({
      source: 'Johnny Analytics',
      metric,
      value: String(value),
      summary: `${metric}: ${String(value)}`,
      tone: metric.includes('status') || String(value).includes('low') ? 'warning' : 'info',
    }))
  }

  const unavailable = Array.isArray(payload.unavailable_signals) ? payload.unavailable_signals : []
  apiUnavailableSignals.value = unavailable.map(String)
}

function applyRecommendationsPayload(items: Array<Record<string, unknown>>) {
  const mapped = items.map(mapRecommendation).filter((item): item is InboxRecommendation => item !== null)
  apiInboxItems.value = mapped
  const firstPending = mapped.find((item) => item.status === 'pending') ?? mapped[0]
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

function applyTrainingPlansPayload(items: Array<Record<string, unknown>>) {
  const workouts = items.flatMap((plan) => (Array.isArray(plan.workouts) ? plan.workouts : []))
  apiWorkouts.value = workouts.map(mapWorkout).filter((workout): workout is WorkoutSummary => workout !== null)
}

function applyRaceGoalsPayload(items: Array<Record<string, unknown>>) {
  const mapped = items.map(mapRaceGoal).filter((race): race is RaceSummary => race !== null)
  if (mapped.length) {
    raceEntries.value = mapped
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
    name,
    date: raceDateValue,
    distance: formatDistance(distanceMeters),
    goal: formatTargetFinish(race.target_finish_seconds) || String(race.priority || race.status || 'planned'),
    daysRemaining: daysUntil(raceDateValue),
  }
}

function mapWorkout(raw: unknown): WorkoutSummary | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  const workout = raw as Record<string, unknown>
  const scheduledFor = String(workout.scheduled_for || '')
  return {
    id: String(workout.id || scheduledFor || crypto.randomUUID()),
    weekday: formatWeekday(scheduledFor),
    dateLabel: formatDateLabel(scheduledFor),
    type: formatWorkoutType(String(workout.workout_type || 'workout')),
    purpose: String(workout.purpose || workout.workout_type || 'Training session'),
    distance: workout.planned_distance_meters ? formatDistance(Number(workout.planned_distance_meters)) : undefined,
    duration: workout.planned_duration_minutes ? `${workout.planned_duration_minutes} 分` : undefined,
    heartRateZone: workout.heart_rate_zone ? String(workout.heart_rate_zone) : undefined,
    status: String(workout.status || 'planned'),
  }
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

function buildRaceCalendarMonths(races: RaceSummary[]) {
  const anchor = new Date()
  const firstMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  return Array.from({ length: 6 }, (_, offset) => {
    const monthStart = new Date(firstMonth.getFullYear(), firstMonth.getMonth() + offset, 1)
    const monthKey = `${monthStart.getFullYear()}-${String(monthStart.getMonth() + 1).padStart(2, '0')}`
    return {
      key: monthKey,
      label: monthStart.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long' }),
      races: races
        .filter((race) => race.date.startsWith(monthKey))
        .map((race) => ({ ...race, daysRemaining: daysUntil(race.date) }))
        .sort((a, b) => a.date.localeCompare(b.date)),
    }
  })
}

function formatWorkoutType(value: string): string {
  return value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatDistance(meters: number): string {
  if (!Number.isFinite(meters) || meters <= 0) {
    return 'N/A'
  }
  if (meters === 21097) {
    return 'Half Marathon'
  }
  if (meters === 42195) {
    return 'Marathon'
  }
  return `${Number((meters / 1000).toFixed(1)).toString()} km`
}

function parseDistanceMeters(value: string): number | null {
  const normalized = value.trim().toLowerCase()
  if (!normalized) {
    return null
  }
  if (normalized.includes('half') || normalized.includes('半馬')) {
    return 21097
  }
  if (normalized.includes('marathon') || normalized.includes('全馬')) {
    return 42195
  }
  const kmMatch = normalized.match(/(\d+(?:\.\d+)?)\s*(?:k|km|公里)/)
  if (kmMatch) {
    return Math.round(Number(kmMatch[1]) * 1000)
  }
  const meters = Number(normalized)
  return Number.isFinite(meters) && meters > 0 ? Math.round(meters) : null
}

function parseTargetFinishSeconds(value: string): number | undefined {
  const normalized = value.trim().replace(/^sub\s*/i, '')
  if (!normalized) {
    return undefined
  }
  const parts = normalized.split(':').map((part) => Number(part))
  if (parts.some((part) => !Number.isFinite(part) || part < 0)) {
    return undefined
  }
  if (parts.length === 2) {
    const [hoursOrMinutes, minutesOrSeconds] = parts
    return hoursOrMinutes >= 10 ? hoursOrMinutes * 60 + minutesOrSeconds : hoursOrMinutes * 3600 + minutesOrSeconds * 60
  }
  if (parts.length === 3) {
    const [hours, minutes, seconds] = parts
    return hours * 3600 + minutes * 60 + seconds
  }
  return undefined
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
    return remainingSeconds > 0
      ? `Sub ${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
      : `Sub ${hours}:${String(minutes).padStart(2, '0')}`
  }
  return `Sub ${minutes}:${String(remainingSeconds).padStart(2, '0')}`
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
    name: '尚未設定目標',
    date: '',
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
    purpose: '連接資料來源或建立訓練計畫後，Johnny 會在這裡顯示今天的安排。',
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
          <p>登入後 Johnny 才會讀取你的訓練安排、資料來源與 Agent 建議。</p>
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
            <input v-model="authDisplayName" name="displayName" autocomplete="name" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <label>
            Email
            <input v-model="authEmail" name="authEmail" type="email" autocomplete="email" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <label>
            密碼
            <input v-model="authPassword" name="authPassword" type="password" :autocomplete="authMode === 'signup' ? 'new-password' : 'current-password'" :aria-invalid="authError ? 'true' : 'false'" />
          </label>
          <label v-if="authMode === 'signup'">
            確認密碼
            <input v-model="authPasswordConfirm" name="authPasswordConfirm" type="password" autocomplete="new-password" :aria-invalid="authError ? 'true' : 'false'" />
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
            :data-view="item.key === 'sources' ? 'sources' : item.key"
            :class="{ 'top-nav__item--active': activeView === item.key }"
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
      <section v-if="activeView === 'today'" class="today-grid" aria-labelledby="today-title">
        <div class="page-heading today-grid__wide">
          <p class="section-label">今日</p>
          <h2 id="today-title">今天的訓練決策</h2>
          <p>Johnny 會把課表、恢復訊號和建議放在同一個決策脈絡裡。</p>
        </div>

        <article v-if="effectiveTodayState === 'loading'" class="state-panel today-grid__wide" aria-live="polite">
          <p class="section-label">Loading</p>
          <h3>正在整理今天的訓練資料</h3>
          <p>Johnny 正在讀取課表、恢復訊號和推薦狀態。</p>
        </article>

        <article v-else-if="effectiveTodayState === 'error'" class="state-panel state-panel--danger today-grid__wide" role="alert">
          <p class="section-label">Error</p>
          <h3>今天資料載入失敗</h3>
          <p>請稍後再試，或先前往資料來源檢查同步狀態。</p>
          <AppButton tone="neutral" @click="showView('sources')">檢查資料來源</AppButton>
        </article>

        <article v-else-if="effectiveTodayState === 'empty'" class="state-panel today-grid__wide">
          <p class="section-label">Empty</p>
          <h3>尚未有足夠資料建立今日建議</h3>
          <p>連接資料來源後，Johnny 會用近期訓練、睡眠與 HRV 判斷恢復狀態。</p>
          <AppButton tone="primary" @click="showView('sources')">連接資料來源</AppButton>
        </article>

        <template v-else>
        <article class="surface-card today-top-card race-card">
          <p class="section-label">下一場比賽</p>
          <h3>{{ raceSummary.name }}</h3>
          <p class="race-card__count">{{ raceSummary.daysRemaining }} 天</p>
          <p>{{ raceSummary.distance }} · {{ raceSummary.goal }} · {{ raceSummary.date }}</p>
        </article>

        <article class="surface-card today-top-card workout-card">
          <p class="section-label">今日課表</p>
          <h3>{{ todayWorkout.type }}</h3>
          <p>{{ todayWorkout.purpose }}</p>
          <div class="metric-row">
            <span>{{ todayWorkout.distance }}</span>
            <span>{{ todayWorkout.pace }}</span>
            <span>{{ todayWorkout.heartRateZone }}</span>
          </div>
        </article>

        <article class="surface-card today-top-card evidence-card" data-testid="today-recovery-card">
          <div class="section-heading">
            <div>
              <p class="section-label">恢復證據</p>
              <h3>恢復偏低</h3>
            </div>
            <StatusBadge tone="warning">需要保守</StatusBadge>
          </div>
          <p class="recovery-summary" data-testid="today-recovery-summary">主要訊號偏向保守調整；完整證據留在 Agent 收件匣決策卡。</p>
          <div class="recovery-signal-grid" aria-label="恢復關鍵訊號">
            <div v-for="item in recoveryEvidence.slice(0, 3)" :key="`${item.source}-${item.metric}`" class="recovery-signal-chip" data-testid="recovery-signal-chip">
              <span>{{ item.metric }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <div class="compact-card-footer">
            <span v-if="unavailableSignals.length">{{ unavailableSignals.length }} 個訊號待補</span>
            <AppButton tone="neutral" @click="showView('sources')">資料來源</AppButton>
          </div>
        </article>

        <article class="surface-card today-grid__wide inbox-nudge">
          <div>
            <p class="section-label">Agent 收件匣</p>
            <h3>主動建議會集中在 Agent 收件匣</h3>
            <p>今日保留訓練、恢復與下一場目標的快速判讀；需要你決定的 Johnny 建議會在收件匣處理。</p>
          </div>
          <AppButton tone="primary" @click="showView('inbox')">查看待決定建議</AppButton>
        </article>
        </template>
      </section>

      <section v-else-if="activeView === 'calendar'" class="page-stack" aria-labelledby="calendar-title">
        <div class="page-heading">
          <p class="section-label">訓練安排</p>
          <h2 id="calendar-title">未來六個月</h2>
          <p>把未來目標、重要活動與接下來的課表放在同一個時間脈絡裡。</p>
        </div>

        <section class="race-calendar" aria-label="未來六個月訓練安排">
          <article v-for="month in raceCalendarMonths" :key="month.key" class="race-month" data-testid="race-month">
            <div class="race-month__header">
              <p class="section-label">{{ month.key }}</p>
              <h3>{{ month.label }}</h3>
            </div>
            <div v-if="month.races.length" class="race-list">
              <article v-for="race in month.races" :key="`${race.name}-${race.date}`" class="race-entry">
                <div>
                  <strong>{{ race.name }}</strong>
                  <p>{{ race.distance }} · {{ race.goal }}</p>
                </div>
                <div class="race-entry__date">
                  <span>{{ formatDateLabel(race.date) }}</span>
                  <small>{{ race.daysRemaining }} 天</small>
                </div>
              </article>
            </div>
            <p v-else class="race-month__empty">尚未設定目標</p>
          </article>
        </section>

        <form class="surface-card race-form" data-testid="race-form" novalidate @submit.prevent="submitRaceEntry">
          <div class="section-heading">
            <div>
              <p class="section-label">新增目標</p>
              <h3>設定訓練安排</h3>
            </div>
            <StatusBadge tone="info">六個月視窗</StatusBadge>
          </div>
          <div class="form-grid">
            <label>
              名稱
              <input v-model="raceName" name="raceName" autocomplete="off" :aria-invalid="raceFormError ? 'true' : 'false'" />
            </label>
            <label>
              日期
              <input v-model="raceDate" name="raceDate" type="date" :aria-invalid="raceFormError ? 'true' : 'false'" />
            </label>
            <label>
              距離
              <input v-model="raceDistance" name="raceDistance" autocomplete="off" />
            </label>
            <label>
              目標
              <input v-model="raceGoal" name="raceGoal" autocomplete="off" />
            </label>
          </div>
          <div class="form-footer">
            <p v-if="raceFormError" class="field-error">{{ raceFormError }}</p>
            <p v-else-if="raceFormMessage" class="inline-note">{{ raceFormMessage }}</p>
            <p v-else>名稱與日期必填，其餘可以之後補上。</p>
            <AppButton tone="primary" type="submit">加入安排</AppButton>
          </div>
        </form>

        <div class="section-heading">
          <div>
            <p class="section-label">Workout context</p>
            <h3>接下來的課表</h3>
          </div>
          <StatusBadge tone="info">{{ displayWorkouts.length }} 項</StatusBadge>
        </div>

        <div v-if="displayWorkouts.length" class="schedule-list">
          <article v-for="workout in displayWorkouts" :key="workout.id" class="schedule-row">
            <div class="schedule-row__date">
              <strong>{{ workout.weekday }}</strong>
              <span>{{ workout.dateLabel }}</span>
            </div>
            <div>
              <h3>{{ workout.type }}</h3>
              <p>{{ workout.purpose }}</p>
            </div>
            <div class="metric-row">
              <span v-if="workout.distance">{{ workout.distance }}</span>
              <span v-if="workout.duration">{{ workout.duration }}</span>
              <span v-if="workout.pace">{{ workout.pace }}</span>
              <span>{{ workout.status }}</span>
            </div>
          </article>
        </div>
        <article v-else class="state-panel">
          <p class="section-label">Empty</p>
          <h3>目前沒有已排定課表</h3>
          <p>建立訓練計畫後，Johnny 會在這裡依日期整理接下來的課表。</p>
        </article>
      </section>

      <section v-else-if="activeView === 'inbox'" class="page-stack" aria-labelledby="inbox-title">
        <div class="page-heading">
          <p class="section-label">Agent 收件匣</p>
          <h2 id="inbox-title">主動建議決策佇列</h2>
          <p>Johnny 只把需要你做訓練決策的建議放在這裡，對話問題仍留在對話。</p>
        </div>

        <article v-if="props.inboxState === 'loading'" class="state-panel" aria-live="polite">
          <p class="section-label">Loading</p>
          <h3>正在整理 Agent 收件匣</h3>
          <p>Johnny 正在比對課表、恢復訊號和待決定建議。</p>
        </article>

        <article v-else-if="props.inboxState === 'error'" class="state-panel state-panel--danger" role="alert">
          <p class="section-label">Error</p>
          <h3>Agent 收件匣載入失敗</h3>
          <p>請稍後再試，或先回到今日檢查主要訓練決策。</p>
          <AppButton tone="neutral" @click="showView('today')">回到今日</AppButton>
        </article>

        <article v-else-if="props.inboxState === 'empty' || displayInboxItems.length === 0" class="state-panel">
          <p class="section-label">Empty</p>
          <h3>目前沒有新的主動建議</h3>
          <p>Johnny 之後會把需要你決定的主動建議放在 Agent 收件匣，已處理的建議會保留在歷史區。</p>
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
          <p>當你想追問訓練安排、恢復證據或建議原因時，可以從這裡開始。</p>
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

      <section v-else-if="activeView === 'sources'" class="page-stack" aria-labelledby="sources-title">
        <div class="page-heading">
          <p class="section-label">資料來源</p>
          <h2 id="sources-title">連接資料來源</h2>
          <p>Johnny 會用近期訓練、睡眠、HRV 和恢復訊號判斷今天是否該調整課表。</p>
        </div>

        <div class="provider-grid">
          <ProviderCard
            v-for="provider in providers"
            :key="provider.id"
            :provider="provider"
            @select="selectProvider"
          />
        </div>

        <form class="surface-card provider-form" data-testid="provider-form" novalidate @submit.prevent="submitProvider">
          <div class="section-heading">
            <div>
              <p class="section-label">Garmin Connect experimental login</p>
              <h3>{{ selectedProvider.name }}</h3>
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
          <AppButton tone="primary" type="submit" :busy="providerBusy">連接 Garmin</AppButton>
          <p v-if="providerMessage" class="inline-note">{{ providerMessage }}</p>
          <div v-if="garminConnection" class="sync-result" aria-live="polite">
            <div class="sync-result__header">
              <p class="section-label">初始同步</p>
              <StatusBadge :tone="garminStatus(garminConnection).tone">{{ garminStatus(garminConnection).label }}</StatusBadge>
            </div>
            <p v-if="garminConnection.has_partial_failures" class="sync-result__warning">部分資料同步失敗</p>
            <p v-if="garminConnection.sync_warning" class="sync-result__warning">{{ garminConnection.sync_warning }}</p>
            <ul class="sync-result__list">
              <li v-for="row in garminSyncRows(garminConnection)" :key="row">{{ row }}</li>
            </ul>
          </div>
        </form>
      </section>

      <section v-else class="empty-panel" :aria-labelledby="`${activeView}-title`">
        <p class="section-label">{{ activeTitle }}</p>
        <h2 :id="`${activeView}-title`">{{ activeTitle }}</h2>
        <p>這個工作流會依照對應 OpenSpec change 補上完整互動。</p>
      </section>
    </main>
  </div>
</template>
