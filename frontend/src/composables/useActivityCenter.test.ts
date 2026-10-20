import { describe, expect, it } from 'vitest'
import { useActivityCenter } from './useActivityCenter'
import type { AgentRunResponse } from '../types'

function run(id: string, workflow_name: string, status: string): AgentRunResponse {
  return { id, workflow_name, status, finished_at: status === 'completed' || status === 'failed' ? new Date().toISOString() : null,
    error_message: null }
}

describe('activity center', () => {
  it('tracks multiple runs and announces a completion only after an observed transition', () => {
    const center = useActivityCenter()
    center.applyRuns([run('plan-1', 'training_plan_generation', 'queued'), run('review-1', 'daily_review', 'started')])
    expect(center.activeCount.value).toBe(2)
    expect(center.currentToast.value).toBeNull()

    center.applyRuns([run('plan-1', 'training_plan_generation', 'completed'), run('review-1', 'daily_review', 'started')])
    expect(center.activeCount.value).toBe(1)
    expect(center.currentToast.value?.message).toBe('訓練計畫已完成')
    expect(center.currentToast.value?.view).toBe('plan')
    center.dismissToast()
    center.applyRuns([run('plan-1', 'training_plan_generation', 'completed'), run('review-1', 'daily_review', 'started')])
    expect(center.currentToast.value).toBeNull()
  })

  it('keeps failures in the list and never announces historical work on first load', () => {
    const center = useActivityCenter()
    center.applyRuns([run('old-review', 'daily_review', 'completed')])
    expect(center.currentToast.value).toBeNull()
    center.registerRun('new-review', 'daily_review')
    center.applyRuns([run('new-review', 'daily_review', 'failed'), run('old-review', 'daily_review', 'completed')])
    expect(center.currentToast.value?.message).toBe('每日回顧更新失敗')
    expect(center.tasks.value.find(task => task.id === 'new-review')?.detail).toContain('上次結果')
  })

  it('shows sync as running and reports a partial result distinctly', () => {
    const center = useActivityCenter()
    center.startSync('garmin-1')
    expect(center.activeCount.value).toBe(1)
    center.finishSync('garmin-1', 'partial')
    expect(center.activeCount.value).toBe(0)
    expect(center.currentToast.value?.message).toBe('Garmin 同步完成，部分資料未取得')
    expect(center.tasks.value[0].status).toBe('partial')
  })
})
