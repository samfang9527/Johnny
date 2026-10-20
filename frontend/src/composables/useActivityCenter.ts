import { computed, ref } from 'vue'
import type { AgentRunResponse, ViewKey } from '../types'

export type ActivityStatus = 'queued' | 'running' | 'completed' | 'failed' | 'partial'
export type ActivityWorkflow = 'training_plan_generation' | 'daily_review' | 'workout_advice' | 'garmin_sync'

export interface ActivityTask {
  id: string
  workflow: ActivityWorkflow
  title: string
  status: ActivityStatus
  detail: string
  view: ViewKey
  action: string
}

export interface ActivityToast {
  message: string
  view: ViewKey
  workflow: ActivityWorkflow
  action: string
  tone: 'success' | 'warning' | 'danger'
}

const workflows: Record<ActivityWorkflow, { title: string; view: ViewKey; action: string; failure: string }> = {
  training_plan_generation: { title: '訓練計畫', view: 'plan', action: '查看計畫', failure: '原課表已保留，請到計畫頁重試。' },
  daily_review: { title: '每日回顧', view: 'johnny', action: '查看回顧', failure: '上次結果已保留，請到 Johnny 查看或重試。' },
  workout_advice: { title: '今日課表建議', view: 'johnny', action: '查看建議', failure: '請到 Johnny 調整條件後重試。' },
  garmin_sync: { title: 'Garmin 同步', view: 'data', action: '查看資料', failure: '請檢查連接狀態後再次同步。' },
}

const trackedRunNames = new Set<ActivityWorkflow>(['training_plan_generation', 'daily_review', 'workout_advice'])

function statusForRun(status: string): ActivityStatus {
  if (status === 'queued') return 'queued'
  if (status === 'completed') return 'completed'
  if (status === 'failed' || status === 'cancelled') return 'failed'
  return 'running'
}

function detailFor(workflow: ActivityWorkflow, status: ActivityStatus): string {
  if (status === 'queued') return '已排入，完成後會更新結果。'
  if (status === 'running') return workflow === 'garmin_sync' ? '正在取得訓練資料，可繼續使用 Johnny。' : '正在處理，可繼續使用 Johnny。'
  if (status === 'failed') return workflows[workflow].failure
  if (status === 'partial') return '部分資料未取得，請到資料頁查看。'
  return '已完成，查看最新結果。'
}

function task(id: string, workflow: ActivityWorkflow, status: ActivityStatus): ActivityTask {
  const config = workflows[workflow]
  return { id, workflow, title: config.title, status, detail: detailFor(workflow, status), view: config.view, action: config.action }
}

function toastFor(item: ActivityTask): ActivityToast {
  const message = item.status === 'failed'
    ? `${item.title}${item.workflow === 'training_plan_generation' ? '產生' : item.workflow === 'garmin_sync' ? '' : '更新'}失敗`
    : item.status === 'partial' ? 'Garmin 同步完成，部分資料未取得'
      : item.workflow === 'training_plan_generation' ? '訓練計畫已完成'
        : item.workflow === 'garmin_sync' ? 'Garmin 同步完成'
          : `${item.title}已更新`
  return { message, view: item.view, workflow: item.workflow, action: item.action,
    tone: item.status === 'failed' ? 'danger' : item.status === 'partial' ? 'warning' : 'success' }
}

export function useActivityCenter() {
  const tasks = ref<ActivityTask[]>([])
  const currentToast = ref<ActivityToast | null>(null)
  const toastQueue: ActivityToast[] = []
  const activeCount = computed(() => tasks.value.filter(item => item.status === 'queued' || item.status === 'running').length)

  function announce(item: ActivityTask) {
    const message = toastFor(item)
    if (currentToast.value) toastQueue.push(message)
    else currentToast.value = message
  }

  function upsert(item: ActivityTask, announceTransition = true) {
    const previous = tasks.value.find(existing => existing.id === item.id)
    tasks.value = [item, ...tasks.value.filter(existing => existing.id !== item.id)].slice(0, 12)
    if (announceTransition && previous && (previous.status === 'queued' || previous.status === 'running')
        && ['completed', 'failed', 'partial'].includes(item.status)) announce(item)
  }

  function applyRuns(runs: AgentRunResponse[]) {
    const recentBoundary = Date.now() - 24 * 60 * 60 * 1000
    for (const run of [...runs].reverse()) {
      if (!run.id || !trackedRunNames.has(run.workflow_name as ActivityWorkflow)) continue
      const workflow = run.workflow_name as ActivityWorkflow
      const status = statusForRun(run.status)
      const known = tasks.value.some(item => item.id === run.id)
      if (!known && status !== 'queued' && status !== 'running'
          && (!run.finished_at || new Date(run.finished_at).getTime() < recentBoundary)) continue
      upsert(task(run.id, workflow, status))
    }
  }

  function registerRun(id: string, workflow: ActivityWorkflow) {
    if (!trackedRunNames.has(workflow)) return
    const previous = tasks.value.find(item => item.id === id)
    if (previous && previous.status !== 'queued' && previous.status !== 'running') return
    upsert(task(id, workflow, previous?.status ?? 'queued'), false)
  }

  function startSync(connectionId: string) {
    upsert(task(`sync:${connectionId}`, 'garmin_sync', 'running'), false)
  }

  function finishSync(connectionId: string, result: 'completed' | 'failed' | 'partial') {
    upsert(task(`sync:${connectionId}`, 'garmin_sync', result))
  }

  function dismissToast() {
    currentToast.value = toastQueue.shift() ?? null
  }

  function clear() {
    tasks.value = []
    currentToast.value = null
    toastQueue.length = 0
  }

  return { tasks, activeCount, currentToast, applyRuns, registerRun, startSync, finishSync, dismissToast, clear }
}
