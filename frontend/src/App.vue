<script setup lang="ts">
import { computed, ref } from 'vue'
import { acceptRecommendation, connectIntegration, discussRecommendation, rejectRecommendation, submitConversationMessage } from './api/client'
import AppButton from './components/AppButton.vue'
import EvidenceList from './components/EvidenceList.vue'
import ProviderCard from './components/ProviderCard.vue'
import RecommendationActions from './components/RecommendationActions.vue'
import StatusBadge from './components/StatusBadge.vue'
import {
  conversationThreads as fixtureConversationThreads,
  inboxRecommendations as fixtureInboxRecommendations,
  plannedWorkouts as fixtureWorkouts,
  providers,
  raceSummary,
  recommendation,
  recoveryEvidence,
  todayWorkout,
  unavailableSignals,
} from './fixtures'
import type {
  ConversationThread,
  InboxRecommendation,
  LinkedRecommendationContext,
  ProviderOption,
  RecommendationStatus,
  ViewKey,
  WorkoutSummary,
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
  }>(),
  {
    todayState: 'full',
    conversationState: 'loaded',
    inboxState: 'loaded',
    workouts: undefined,
    conversationThreads: undefined,
    inboxItems: undefined,
  },
)

const navItems: Array<{ key: ViewKey; label: string }> = [
  { key: 'today', label: '今日' },
  { key: 'calendar', label: '課表' },
  { key: 'inbox', label: 'Agent 收件匣' },
  { key: 'conversation', label: '對話' },
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
const recommendationStatus = ref(recommendation.status)
const selectedProvider = ref<ProviderOption>(providers[0])
const providerAccountId = ref('')
const credentialSecretRef = ref('')
const providerMessage = ref('')
const providerError = ref('')
const conversationMessage = ref('')
const conversationError = ref('')
const conversationStatus = ref('')
const conversationBusy = ref(false)
const isComposing = ref(false)
const linkedRecommendation = ref<LinkedRecommendationContext | null>(null)
const inboxBusyRecommendationId = ref('')

const activeTitle = computed(() => navItems.find((item) => item.key === activeView.value)?.label || '今日')
const displayWorkouts = computed(() => props.workouts ?? fixtureWorkouts)
const displayThreads = computed(() => props.conversationThreads ?? fixtureConversationThreads)
const displayInboxItems = computed(() => props.inboxItems ?? fixtureInboxRecommendations)
const activeThreadId = ref(displayThreads.value[0]?.id ?? '')
const activeThread = computed(() => displayThreads.value.find((thread) => thread.id === activeThreadId.value) ?? displayThreads.value[0])
const pendingInboxItems = computed(() => displayInboxItems.value.filter((item) => item.status === 'pending'))
const historicalInboxItems = computed(() => displayInboxItems.value.filter((item) => item.status !== 'pending'))

function showView(view: ViewKey) {
  activeView.value = view
  if (typeof window !== 'undefined') {
    window.history.replaceState(null, '', `#${view}`)
  }
}

async function handleAccept() {
  busyAction.value = 'accept'
  try {
    await acceptRecommendation(recommendation.id)
    recommendationStatus.value = 'accepted'
  } finally {
    busyAction.value = ''
  }
}

async function handleKeepOriginal() {
  busyAction.value = 'keep'
  try {
    await rejectRecommendation(recommendation.id)
    recommendationStatus.value = 'kept'
  } finally {
    busyAction.value = ''
  }
}

async function handleDiscuss() {
  busyAction.value = 'discuss'
  try {
    await discussRecommendation(recommendation.id, '我想了解這次調整的原因。')
    linkedRecommendation.value = {
      id: recommendation.id,
      title: recommendation.title,
      status: 'pending',
      statusLabel: '待決定',
      evidenceSummary: 'HRV -18% · 7 日負荷 +21%',
      evidence: recoveryEvidence,
    }
    showView('conversation')
  } finally {
    busyAction.value = ''
  }
}

function handleEdit() {
  providerMessage.value = '編輯調整會在下一階段加入完整表單。'
}

function selectProvider(provider: ProviderOption) {
  selectedProvider.value = provider
}

async function submitProvider() {
  providerError.value = ''
  if (!providerAccountId.value.trim()) {
    providerError.value = '請輸入 Provider account ID'
    return
  }
  await connectIntegration({
    provider: selectedProvider.value.id,
    provider_account_id: providerAccountId.value.trim(),
    credential_secret_ref: credentialSecretRef.value || undefined,
  })
  providerMessage.value = `${selectedProvider.value.name} 連接已送出`
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
  } catch {
    conversationError.value = '訊息送出失敗，請稍後再試。'
  } finally {
    conversationBusy.value = false
  }
}

function handleActionPlaceholder() {
  providerMessage.value = '這個決策會在下一階段同步到訓練計畫。'
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
  } catch {
    conversationError.value = '討論原因送出失敗，請稍後再試。'
  } finally {
    inboxBusyRecommendationId.value = ''
  }
}
</script>

<template>
  <div class="app-shell">
    <header class="top-bar">
      <div>
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
    </header>

    <main class="main-surface">
      <section v-if="activeView === 'today'" class="today-grid" aria-labelledby="today-title">
        <div class="page-heading today-grid__wide">
          <p class="section-label">今日</p>
          <h2 id="today-title">今天的訓練決策</h2>
          <p>Johnny 會把課表、恢復訊號和建議放在同一個決策脈絡裡。</p>
        </div>

        <article v-if="props.todayState === 'loading'" class="state-panel today-grid__wide" aria-live="polite">
          <p class="section-label">Loading</p>
          <h3>正在整理今天的訓練資料</h3>
          <p>Johnny 正在讀取課表、恢復訊號和推薦狀態。</p>
        </article>

        <article v-else-if="props.todayState === 'error'" class="state-panel state-panel--danger today-grid__wide" role="alert">
          <p class="section-label">Error</p>
          <h3>今天資料載入失敗</h3>
          <p>請稍後再試，或先前往資料來源檢查同步狀態。</p>
          <AppButton tone="neutral" @click="showView('sources')">檢查資料來源</AppButton>
        </article>

        <article v-else-if="props.todayState === 'empty'" class="state-panel today-grid__wide">
          <p class="section-label">Empty</p>
          <h3>尚未有足夠資料建立今日建議</h3>
          <p>連接資料來源後，Johnny 會用近期訓練、睡眠與 HRV 判斷恢復狀態。</p>
          <AppButton tone="primary" @click="showView('sources')">連接資料來源</AppButton>
        </article>

        <template v-else>
        <article class="surface-card race-card">
          <p class="section-label">下一場比賽</p>
          <h3>{{ raceSummary.name }}</h3>
          <p class="race-card__count">{{ raceSummary.daysRemaining }} 天</p>
          <p>{{ raceSummary.distance }} · {{ raceSummary.goal }} · {{ raceSummary.date }}</p>
        </article>

        <article class="surface-card workout-card">
          <p class="section-label">今日課表</p>
          <h3>{{ todayWorkout.type }}</h3>
          <p>{{ todayWorkout.purpose }}</p>
          <div class="metric-row">
            <span>{{ todayWorkout.distance }}</span>
            <span>{{ todayWorkout.pace }}</span>
            <span>{{ todayWorkout.heartRateZone }}</span>
          </div>
        </article>

        <article class="surface-card evidence-card">
          <div class="section-heading">
            <div>
              <p class="section-label">恢復證據</p>
              <h3>恢復偏低</h3>
            </div>
            <StatusBadge tone="warning">需要保守</StatusBadge>
          </div>
          <EvidenceList :items="recoveryEvidence" :unavailable="unavailableSignals" />
          <AppButton tone="neutral" @click="showView('sources')">前往資料來源</AppButton>
        </article>

        <article class="recommendation-card today-grid__wide">
          <div class="section-heading">
            <div>
              <p class="section-label">Johnny 建議</p>
              <h3>{{ recommendation.title }}</h3>
            </div>
            <StatusBadge tone="warning">{{ recommendationStatus === 'accepted' ? '已接受' : '待決定' }}</StatusBadge>
          </div>
          <div class="decision-strip">
            <div>
              <p class="section-label">訊號</p>
              <strong>恢復低於基準</strong>
            </div>
            <div>
              <p class="section-label">證據</p>
              <strong>HRV -18% · 7 日負荷 +21%</strong>
            </div>
            <div>
              <p class="section-label">建議</p>
              <strong>{{ recommendation.proposedAction }}</strong>
            </div>
            <div>
              <p class="section-label">決定</p>
              <strong>{{ recommendation.rationale }}</strong>
            </div>
          </div>
          <RecommendationActions
            :busy-action="busyAction"
            @accept="handleAccept"
            @edit="handleEdit"
            @keep="handleKeepOriginal"
            @discuss="handleDiscuss"
          />
          <p v-if="providerMessage" class="inline-note">{{ providerMessage }}</p>
        </article>
        </template>
      </section>

      <section v-else-if="activeView === 'calendar'" class="page-stack" aria-labelledby="calendar-title">
        <div class="page-heading">
          <p class="section-label">課表</p>
          <h2 id="calendar-title">本週課表</h2>
          <p>以週列表呈現下一次訓練，不用擠壓成月曆格。</p>
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
                class="inbox-card"
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
                  :busy-action="inboxBusyRecommendationId === item.id ? 'discuss' : ''"
                  @accept="handleActionPlaceholder"
                  @edit="handleActionPlaceholder"
                  @keep="handleActionPlaceholder"
                  @discuss="handleInboxDiscuss(item)"
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
                    @edit="handleActionPlaceholder"
                    @keep="handleActionPlaceholder"
                    @discuss="handleActionPlaceholder"
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
              <p class="section-label">MVP Binding</p>
              <h3>{{ selectedProvider.name }}</h3>
            </div>
            <StatusBadge tone="info">credential reference</StatusBadge>
          </div>
          <p>Johnny 只保存 credential reference，不保存 Garmin 密碼、token 或 cookie。</p>
          <label>
            Provider account ID
            <input
              v-model="providerAccountId"
              name="providerAccountId"
              autocomplete="off"
              :aria-invalid="providerError ? 'true' : 'false'"
              aria-describedby="provider-account-error"
            />
          </label>
          <p v-if="providerError" id="provider-account-error" class="field-error">{{ providerError }}</p>
          <label>
            Credential secret ref
            <input v-model="credentialSecretRef" name="credentialSecretRef" autocomplete="off" />
          </label>
          <AppButton tone="primary" type="submit">連接資料來源</AppButton>
          <p v-if="providerMessage" class="inline-note">{{ providerMessage }}</p>
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
