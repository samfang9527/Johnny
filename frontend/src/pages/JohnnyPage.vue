<script setup lang="ts">
import { computed, ref } from 'vue'
import { acceptRecommendation, rejectRecommendation } from '../api/client'
import AppButton from '../components/AppButton.vue'
import RecommendationActions from '../components/RecommendationActions.vue'
import { useJohnny } from '../composables/useJohnny'
import type { WorkoutAdviceConstraints } from '../types'

const emit = defineEmits<{ decision: []; navigateToday: [] }>()
const johnny = useJohnny()
const selectedWorkoutId = ref('')
const availableInput = ref('')
const feeling = ref<'usual' | 'more_tired'>('usual')
const cannotTrain = ref(false)
const formError = ref('')
const decidingId = ref('')
const decidingAction = ref<'accept' | 'keep' | ''>('')
let retryRequestId: string | null = null
let retryBody = ''

const latestAdvice = computed(() => johnny.workoutAdvices.value.find(item => item.current)?.current ?? null)
const score = computed(() => johnny.dailyReview.value?.current?.score ?? null)

function scoreReason(reason: string | null | undefined): string {
  const labels: Record<string, string> = {
    no_prescribed_sessions: '這七天沒有可評分的跑步課表。',
    incomplete_activity_coverage: '活動同步尚未涵蓋所有課表日期，暫不判定漏課。',
    ambiguous_pairing: '有活動尚未確認對應課表，請先完成配對。',
    uncertain_prescription: '舊課表的生效順序無法確認，暫不計分。',
    missing_comparison_metric: '課表或活動缺少可比較的時間／距離。',
  }
  return labels[reason ?? ''] ?? '目前資料不足，暫不顯示分數。'
}

function executionLabel(state: string): string {
  const labels: Record<string, string> = {
    completed: '已完成', missed: '確認未完成', approved_skip: '已同意略過', needs_pairing: '待確認活動配對',
    unknown_coverage: '活動資料未完整', uncertain_prescription: '原課表待確認',
  }
  return labels[state] ?? '待確認'
}

function formatMinutes(value: unknown): string {
  return typeof value === 'number' ? `${value} 分鐘` : '未設定'
}

function proposalAction(proposal: { evidence: Record<string, unknown> }) {
  const action = proposal.evidence.proposed_action
  if (!action || typeof action !== 'object') return {}
  const payload = (action as Record<string, unknown>).payload
  return payload && typeof payload === 'object' ? payload as Record<string, unknown> : {}
}

function proposalDiff(proposal: { evidence: Record<string, unknown> }) {
  const action = proposalAction(proposal)
  const before = action.before_payload as Record<string, unknown> | undefined
  const after = action.after_payload as Record<string, unknown> | undefined
  if (!before || !after) return []
  const changes: Array<{ label: string; before: string; after: string }> = []
  if (before.status !== after.status) changes.push({ label: '課表狀態',
    before: before.status === 'planned' ? '原定訓練' : String(before.status),
    after: after.status === 'skipped' ? '同意略過' : String(after.status) })
  if (before.planned_duration_minutes !== after.planned_duration_minutes) changes.push({
    label: '總時間', before: formatMinutes(before.planned_duration_minutes),
    after: formatMinutes(after.planned_duration_minutes),
  })
  if (before.planned_distance_meters !== after.planned_distance_meters) changes.push({
    label: '計畫距離',
    before: typeof before.planned_distance_meters === 'number' ? `${before.planned_distance_meters} 公尺` : '未設定',
    after: typeof after.planned_distance_meters === 'number' ? `${after.planned_distance_meters} 公尺` : '未設定',
  })
  const beforeStep = Array.isArray(before.steps) ? before.steps[0] as Record<string, unknown> | undefined : undefined
  const afterStep = Array.isArray(after.steps) ? after.steps[0] as Record<string, unknown> | undefined : undefined
  if (beforeStep?.duration_seconds !== afterStep?.duration_seconds) changes.push({
    label: '跑步步驟',
    before: typeof beforeStep?.duration_seconds === 'number' ? `${Math.round(beforeStep.duration_seconds / 60)} 分鐘` : '未設定',
    after: typeof afterStep?.duration_seconds === 'number' ? `${Math.round(afterStep.duration_seconds / 60)} 分鐘` : '未設定',
  })
  return changes
}

function onCannotTrainChange() {
  if (cannotTrain.value) availableInput.value = ''
}

async function submitAdvice() {
  if (johnny.advicePendingRunId.value || johnny.adviceLoading.value) return
  formError.value = ''
  const minutes = availableInput.value.trim() ? Number(availableInput.value) : null
  if (minutes !== null && (!Number.isInteger(minutes) || minutes < 1 || minutes > 600)) {
    formError.value = '可用時間請填 1 到 600 分鐘。'
    return
  }
  if (cannotTrain.value && minutes !== null) {
    formError.value = '選擇「今天無法訓練」時，請清空可用時間。'
    return
  }
  if (johnny.workoutChoices.value.length > 1 && !selectedWorkoutId.value) {
    formError.value = '請先選擇要取得建議的課表。'
    return
  }
  const constraints: WorkoutAdviceConstraints = {
    available_minutes: minutes, feeling: feeling.value, cannot_train_today: cannotTrain.value,
  }
  const workoutId = selectedWorkoutId.value || johnny.workoutChoices.value[0]?.id || null
  const body = JSON.stringify({ workoutId, constraints })
  if (retryBody !== body) {
    retryBody = body
    retryRequestId = crypto.randomUUID()
  }
  await johnny.requestAdvice(workoutId, constraints, retryRequestId ?? crypto.randomUUID())
}

async function decide(id: string, action: 'accept' | 'keep') {
  if (decidingId.value) return
  decidingId.value = id
  decidingAction.value = action
  try {
    if (action === 'accept') await acceptRecommendation(id)
    else await rejectRecommendation(id)
    await johnny.refreshAdvice()
    await johnny.loadHistory()
    emit('decision')
  } catch {
    johnny.adviceError.value = '這份調整已無法套用，請重新讀取今日建議。'
    await johnny.refreshAdvice()
  } finally {
    decidingId.value = ''
    decidingAction.value = ''
  }
}
</script>

<template>
  <section class="page-stack johnny-page" data-testid="johnny-page" aria-labelledby="johnny-title">
    <div class="page-heading johnny-page__heading">
      <div>
        <p class="section-label">訓練回顧與今日決策</p>
        <h2 id="johnny-title">Johnny</h2>
        <p>先看昨天與最近七天怎麼執行，再決定今天是否需要調整。</p>
      </div>
      <a class="johnny-page__jump" href="#johnny-workout-advice">取得今日課表建議 ↓</a>
    </div>

    <section class="johnny-stream johnny-stream--review" data-testid="johnny-daily-review" aria-labelledby="daily-review-title">
      <div class="johnny-stream__heading">
        <div>
          <p class="section-label">Daily review</p>
          <h3 id="daily-review-title">每日回顧</h3>
        </div>
        <span v-if="johnny.dailyReview.value?.current" class="data-chip">{{ johnny.dailyReview.value.current.reviewed_date }}</span>
      </div>
      <p v-if="johnny.reviewLoading.value || johnny.reviewPendingRunId.value" class="johnny-stream__state" role="status">正在更新每日回顧，先保留上次結果。</p>
      <p v-if="johnny.reviewError.value" class="johnny-stream__error" role="alert">{{ johnny.reviewError.value }}</p>
      <template v-if="johnny.dailyReview.value?.current">
        <p class="johnny-stream__lead">{{ johnny.dailyReview.value.current.narrative }}</p>
        <p class="johnny-stream__meta">涵蓋 {{ johnny.dailyReview.value.current.starts_on }} 至 {{ johnny.dailyReview.value.current.ends_on }} · 產生於 {{ johnny.dailyReview.value.current.generated_at }}</p>
        <div class="johnny-score" data-testid="johnny-execution-score">
          <div>
            <p class="section-label">七日課表執行分數</p>
            <strong>{{ score?.value === null ? '資料不足' : `${score?.value} 分` }}</strong>
            <p v-if="score?.value === null">{{ scoreReason(score?.reason) }}</p>
          </div>
          <dl class="johnny-score__facts">
            <div><dt>計畫堂數</dt><dd>{{ score?.eligible_count ?? '—' }}</dd></div>
            <div><dt>已完成</dt><dd>{{ score?.completed_count ?? '—' }}</dd></div>
            <div><dt>確認未完成</dt><dd>{{ score?.missed_count ?? '—' }}</dd></div>
            <div><dt>額外活動</dt><dd>{{ score?.extra_count ?? '—' }}</dd></div>
          </dl>
        </div>
        <details class="johnny-score__explanation">
          <summary>分數怎麼算</summary>
          <p>完成率與訓練量符合度各占一半。額外活動會列出，但目前不扣分。資料不完整時不會把未知當成零分或漏課。</p>
          <p v-if="score?.value !== null">完成率 {{ Math.round(score?.completion_component ?? 0) }}% · 訓練量符合度 {{ Math.round(score?.volume_component ?? 0) }}%</p>
        </details>
        <div class="johnny-yesterday">
          <h4>昨日執行</h4>
          <p v-if="!johnny.dailyReview.value.current.yesterday.length">昨天沒有已排定的跑步課表。</p>
          <div v-for="item in johnny.dailyReview.value.current.yesterday" :key="item.workout_id" class="johnny-yesterday__row">
            <strong>{{ executionLabel(item.state) }}</strong>
            <span>計畫 {{ formatMinutes(item.planned_duration_minutes) }} · 實際 {{ Math.round(item.actual_duration_seconds / 60) }} 分鐘</span>
          </div>
        </div>
        <details v-if="johnny.dailyReview.value.current.week?.length" class="johnny-score__explanation">
          <summary>查看七天逐堂紀錄</summary>
          <ol class="johnny-week-list">
            <li v-for="item in johnny.dailyReview.value.current.week" :key="item.workout_id">
              <span>{{ item.scheduled_for }}</span>
              <strong>{{ executionLabel(item.state) }}</strong>
              <span>計畫 {{ formatMinutes(item.planned_duration_minutes) }} · 實際 {{ Math.round(item.actual_duration_seconds / 60) }} 分鐘</span>
            </li>
          </ol>
        </details>
        <AppButton v-if="['sync_failed', 'generation_failed', 'inputs_changed'].includes(johnny.dailyReview.value.attempt_state) || johnny.dailyReview.value.freshness === 'stale'" tone="neutral" @click="johnny.retryReview">重試每日回顧</AppButton>
      </template>
      <p v-else class="johnny-stream__empty">尚無每日回顧。Johnny 會在你的當地時間凌晨 4 點後整理前一天；資料不足時會說明原因。</p>
    </section>

    <section v-if="johnny.actionableProposals.value.length" class="johnny-stream johnny-stream--proposal" data-testid="johnny-proposals" aria-labelledby="johnny-proposals-title">
      <div class="johnny-stream__heading"><div><p class="section-label">Needs your decision</p><h3 id="johnny-proposals-title">待決定調整</h3></div></div>
      <article v-for="proposal in johnny.actionableProposals.value" :key="proposal.id" class="johnny-proposal">
        <h4>{{ proposal.title }}</h4>
        <p>{{ proposal.rationale }}</p>
        <div class="johnny-proposal__diff">
          <p>將調整 {{ (proposalAction(proposal).before_payload as Record<string, unknown> | undefined)?.display_name ?? '今日課表' }}：</p>
          <dl>
            <div v-for="change in proposalDiff(proposal)" :key="change.label">
              <dt>{{ change.label }}</dt><dd>{{ change.before }} → {{ change.after }}</dd>
            </div>
          </dl>
        </div>
        <p class="johnny-stream__meta">課表只會在你接受後更新。{{ proposal.expires_at ? `有效至 ${proposal.expires_at}` : '' }}</p>
        <RecommendationActions :busy-action="decidingId === proposal.id ? decidingAction : ''" @accept="decide(proposal.id, 'accept')" @keep="decide(proposal.id, 'keep')" />
      </article>
    </section>

    <section id="johnny-workout-advice" class="johnny-stream johnny-stream--advice" data-testid="johnny-workout-advice" aria-labelledby="workout-advice-title">
      <div class="johnny-stream__heading"><div><p class="section-label">On request</p><h3 id="workout-advice-title">今日課表建議</h3></div></div>
      <p>想知道今天怎麼跑，或需要縮短、略過課表時，再請 Johnny 分析一次最新活動。</p>
      <form class="johnny-advice-form" novalidate @submit.prevent="submitAdvice">
        <label v-if="johnny.workoutChoices.value.length > 1">選擇課表
          <select v-model="selectedWorkoutId"><option value="">請選擇</option><option v-for="choice in johnny.workoutChoices.value" :key="choice.id" :value="choice.id">{{ choice.display_name }}</option></select>
        </label>
        <label>今天可用時間（分鐘，可留空）<input v-model="availableInput" type="number" min="1" max="600" inputmode="numeric" :disabled="cannotTrain" /></label>
        <label>今天的感覺<select v-model="feeling"><option value="usual">和平常差不多</option><option value="more_tired">比平常疲倦</option></select></label>
        <label class="johnny-advice-form__check"><input v-model="cannotTrain" type="checkbox" @change="onCannotTrainChange" />今天無法訓練</label>
        <p v-if="formError" class="johnny-stream__error" role="alert">{{ formError }}</p>
        <AppButton tone="primary" type="submit" :busy="johnny.adviceLoading.value || !!johnny.advicePendingRunId.value">取得今日課表建議</AppButton>
      </form>
      <p v-if="johnny.advicePendingRunId.value" role="status">Johnny 正在同步並分析今天的資料；原有建議會保留。</p>
      <p v-if="johnny.adviceError.value" role="alert" class="johnny-stream__error">{{ johnny.adviceError.value }}</p>
      <article v-if="latestAdvice" class="johnny-advice-result">
        <p class="section-label">最近一次建議 · {{ latestAdvice.generated_at }}</p>
        <p class="johnny-stream__lead">{{ latestAdvice.guidance }}</p>
        <p v-if="latestAdvice.reason_code === 'needs_pairing'">活動配對待確認。請到「今日」整理活動後再取得建議。<AppButton @click="emit('navigateToday')">前往今日整理活動</AppButton></p>
        <p v-if="latestAdvice.after" class="johnny-stream__meta">有可套用的課表調整，請在上方「待決定調整」確認。</p>
        <p v-else class="johnny-stream__meta">目前沒有需要套用的課表變更。</p>
      </article>
      <p v-else class="johnny-stream__empty">尚未取得今天的課表建議。你可以填寫當天的條件，再請 Johnny 分析。</p>
    </section>

    <section class="johnny-stream johnny-stream--history" data-testid="johnny-history" aria-labelledby="johnny-history-title">
      <div class="johnny-stream__heading"><div><p class="section-label">Timeline</p><h3 id="johnny-history-title">歷史紀錄</h3></div></div>
      <p v-if="johnny.historyError.value" role="alert">{{ johnny.historyError.value }}</p>
      <ol v-if="johnny.history.value.length" class="johnny-history-list">
        <li v-for="entry in johnny.history.value" :key="`${entry.kind}-${entry.id}`">
          <span class="johnny-stream__meta">{{ entry.at }}</span>
          <strong>{{ entry.kind === 'daily_review' ? '每日回顧' : entry.kind === 'workout_advice' ? '今日課表建議' : '課表調整決定' }}</strong>
          <p v-if="entry.kind === 'recommendation_decision'">{{ entry.decision === 'accepted' ? '已接受調整' : '維持原課表' }}</p>
          <p v-else-if="entry.result?.current">{{ 'narrative' in entry.result.current ? entry.result.current.narrative : entry.result.current.guidance }}</p>
        </li>
      </ol>
      <p v-else>目前還沒有回顧或建議紀錄。</p>
      <div class="action-row">
        <AppButton v-if="johnny.historyOffset.value > 0" @click="johnny.loadHistory(Math.max(0, johnny.historyOffset.value - 20))">上一頁</AppButton>
        <AppButton v-if="johnny.history.value.length === 20" @click="johnny.loadHistory(johnny.historyOffset.value + 20)">下一頁</AppButton>
      </div>
    </section>
  </section>
</template>
