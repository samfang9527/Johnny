<script setup lang="ts">
import { computed, ref } from 'vue'
import { acceptRecommendation, connectIntegration, discussRecommendation, rejectRecommendation } from './api/client'
import AppButton from './components/AppButton.vue'
import EvidenceList from './components/EvidenceList.vue'
import ProviderCard from './components/ProviderCard.vue'
import RecommendationActions from './components/RecommendationActions.vue'
import StatusBadge from './components/StatusBadge.vue'
import { plannedWorkouts as fixtureWorkouts, providers, raceSummary, recommendation, recoveryEvidence, todayWorkout, unavailableSignals } from './fixtures'
import type { ProviderOption, ViewKey, WorkoutSummary } from './types'

const props = withDefaults(
  defineProps<{
    initialView?: ViewKey
    todayState?: 'full' | 'loading' | 'error' | 'empty'
    workouts?: WorkoutSummary[]
  }>(),
  {
    initialView: 'today',
    todayState: 'full',
    workouts: undefined,
  },
)

const navItems: Array<{ key: ViewKey; label: string }> = [
  { key: 'today', label: '今日' },
  { key: 'calendar', label: '課表' },
  { key: 'inbox', label: 'Agent 收件匣' },
  { key: 'conversation', label: '對話' },
  { key: 'sources', label: '資料來源' },
]

const activeView = ref<ViewKey>(props.initialView)
const busyAction = ref('')
const recommendationStatus = ref(recommendation.status)
const selectedProvider = ref<ProviderOption>(providers[0])
const providerAccountId = ref('')
const credentialSecretRef = ref('')
const providerMessage = ref('')
const providerError = ref('')

const activeTitle = computed(() => navItems.find((item) => item.key === activeView.value)?.label || '今日')
const displayWorkouts = computed(() => props.workouts ?? fixtureWorkouts)

function showView(view: ViewKey) {
  activeView.value = view
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
    activeView.value = 'conversation'
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
