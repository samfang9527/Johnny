import { onMounted, onUnmounted, ref } from 'vue'
import { getAgentRun, getJohnnyOverview, listJohnnyHistory, requestWorkoutAdvice, retryJohnnyReview } from '../api/client'
import type { JohnnyAdviceSlot, JohnnyHistoryEntry, JohnnyReviewSlot, WorkoutAdviceConstraints } from '../types'

export function useJohnny() {
  const dailyReview = ref<JohnnyReviewSlot | null>(null)
  const workoutAdvices = ref<JohnnyAdviceSlot[]>([])
  const workoutChoices = ref<Array<{ id: string; display_name: string; workout_type: string; status: string }>>([])
  const actionableProposals = ref<Array<{ id: string; title: string; rationale: string;
    evidence: Record<string, unknown>; expires_at: string | null }>>([])
  const history = ref<JohnnyHistoryEntry[]>([])
  const historyOffset = ref(0)
  const reviewLoading = ref(false)
  const adviceLoading = ref(false)
  const historyLoading = ref(false)
  const reviewError = ref('')
  const adviceError = ref('')
  const historyError = ref('')
  const reviewPendingRunId = ref<string | null>(null)
  const advicePendingRunId = ref<string | null>(null)
  let reviewEpoch = 0
  let adviceEpoch = 0
  let disposed = false
  const timers = new Set<ReturnType<typeof setTimeout>>()
  let dateTimer: ReturnType<typeof setInterval> | null = null
  let serverLocalDate = ''
  let serverTimezone = 'UTC'

  function trackLocalContext(localDate: string, timezoneName: string) {
    serverLocalDate = localDate
    serverTimezone = timezoneName
  }

  function currentLocalDate(): string {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: serverTimezone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(new Date())
    const value = Object.fromEntries(parts.map(part => [part.type, part.value]))
    return `${value.year}-${value.month}-${value.day}`
  }

  async function refreshReview() {
    const epoch = ++reviewEpoch
    reviewLoading.value = true
    reviewError.value = ''
    try {
      const response = await getJohnnyOverview()
      if (disposed || epoch !== reviewEpoch) return
      trackLocalContext(response.data.local_date, response.data.timezone_name)
      dailyReview.value = response.data.daily_review
      const slot = response.data.daily_review
      if (slot?.reserved_run_id && ['queued', 'syncing', 'analyzing'].includes(slot.attempt_state)
          && reviewPendingRunId.value !== slot.reserved_run_id) {
        reviewPendingRunId.value = slot.reserved_run_id
        observeRun(slot.reserved_run_id, 'review')
      }
    } catch {
      if (!disposed && epoch === reviewEpoch) reviewError.value = '每日回顧暫時無法更新，先保留上次結果。'
    } finally {
      if (!disposed && epoch === reviewEpoch) reviewLoading.value = false
    }
  }

  async function refreshAdvice() {
    const epoch = ++adviceEpoch
    adviceLoading.value = true
    adviceError.value = ''
    try {
      const response = await getJohnnyOverview()
      if (disposed || epoch !== adviceEpoch) return
      trackLocalContext(response.data.local_date, response.data.timezone_name)
      workoutAdvices.value = response.data.workout_advices
      workoutChoices.value = response.data.workout_choices
      actionableProposals.value = response.data.actionable_proposals
      const active = response.data.workout_advices.find(item => item.reserved_run_id &&
        ['queued', 'syncing', 'analyzing'].includes(item.attempt_state))
      if (active?.reserved_run_id && advicePendingRunId.value !== active.reserved_run_id) {
        advicePendingRunId.value = active.reserved_run_id
        observeRun(active.reserved_run_id, 'advice')
      }
    } catch {
      if (!disposed && epoch === adviceEpoch) adviceError.value = '今日課表建議暫時無法更新，先保留上次結果。'
    } finally {
      if (!disposed && epoch === adviceEpoch) adviceLoading.value = false
    }
  }

  async function loadHistory(offset = 0) {
    historyLoading.value = true
    historyError.value = ''
    try {
      const response = await listJohnnyHistory(20, offset)
      if (disposed) return
      history.value = response.data
      historyOffset.value = offset
    } catch {
      if (!disposed) historyError.value = '歷史紀錄暫時無法讀取，請再試一次。'
    } finally {
      if (!disposed) historyLoading.value = false
    }
  }

  function observeRun(runId: string, stream: 'review' | 'advice', attempt = 0) {
    const timer = setTimeout(async () => {
      timers.delete(timer)
      if (disposed) return
      try {
        const response = await getAgentRun(runId)
        if (disposed) return
        if (response.data.status === 'completed' || response.data.status === 'failed') {
          if (stream === 'review') {
            reviewPendingRunId.value = null
            await refreshReview()
            if (response.data.status === 'failed') reviewError.value = '每日回顧更新失敗，先保留上次結果。'
          } else {
            advicePendingRunId.value = null
            await refreshAdvice()
            if (response.data.status === 'failed') adviceError.value = '今日建議產生失敗，可調整條件後重試。'
          }
          await loadHistory()
          return
        }
      } catch {
        // Keep observing a queued run through brief network interruptions.
      }
      if (attempt < 20) observeRun(runId, stream, attempt + 1)
      else if (stream === 'review') reviewError.value = '每日回顧仍在處理，稍後回到此頁查看。'
      else adviceError.value = '今日建議仍在處理，稍後回到此頁查看。'
    }, Math.min(2000 + attempt * 500, 8000))
    timers.add(timer)
  }

  async function requestAdvice(workoutId: string | null, constraints: WorkoutAdviceConstraints,
                               clientRequestId: string = crypto.randomUUID()) {
    if (advicePendingRunId.value) return
    adviceError.value = ''
    adviceLoading.value = true
    try {
      const response = await requestWorkoutAdvice({ client_request_id: clientRequestId,
        workout_id: workoutId, constraints })
      advicePendingRunId.value = response.data.run_id
      observeRun(response.data.run_id, 'advice')
    } catch {
      adviceError.value = '無法取得今日建議。請檢查資料連線或稍後再試。'
    } finally {
      adviceLoading.value = false
    }
  }

  async function retryReview() {
    if (!dailyReview.value || reviewPendingRunId.value) return
    reviewError.value = ''
    try {
      const response = await retryJohnnyReview(dailyReview.value.id)
      reviewPendingRunId.value = response.data.run_id
      observeRun(response.data.run_id, 'review')
    } catch {
      reviewError.value = '無法重新產生每日回顧，請稍後再試。'
    }
  }

  function stop() {
    disposed = true
    reviewEpoch++
    adviceEpoch++
    for (const timer of timers) clearTimeout(timer)
    timers.clear()
    window.removeEventListener('focus', revalidate)
    if (dateTimer) clearInterval(dateTimer)
  }

  function revalidate() {
    void refreshReview()
    void refreshAdvice()
  }

  onMounted(() => {
    revalidate()
    void loadHistory()
    window.addEventListener('focus', revalidate)
    dateTimer = setInterval(() => {
      if (serverLocalDate && currentLocalDate() !== serverLocalDate) revalidate()
    }, 60_000)
  })
  onUnmounted(stop)
  return { dailyReview, workoutAdvices, workoutChoices, actionableProposals, history, historyOffset,
    reviewLoading, adviceLoading, historyLoading, reviewError, adviceError, historyError,
    reviewPendingRunId, advicePendingRunId, refreshReview, refreshAdvice, loadHistory,
    requestAdvice, retryReview, stop }
}
