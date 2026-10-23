import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getJohnnyOverview, listJohnnyHistory, retryJohnnyReview } from '../api/client'
import { useJohnny } from './useJohnny'

vi.mock('../api/client', () => ({
  getJohnnyOverview: vi.fn(), listJohnnyHistory: vi.fn(),
  getAgentRun: vi.fn(), requestWorkoutAdvice: vi.fn(), retryJohnnyReview: vi.fn(),
}))

const today = '2026-10-16'
function overview(review: string, advice: string) {
  return { data: {
    local_date: today, timezone_name: 'Asia/Taipei',
    daily_review: { id: 'review', publication_date: today, revision_id: review,
      attempt_state: 'ready', attempt_error: null, freshness: 'current', reserved_run_id: null,
      current: { narrative: review } },
    workout_advices: [{ id: 'advice', advice_date: today, slot_key: 'workout',
      revision_id: advice, attempt_state: 'ready', attempt_error: null,
      freshness: 'current', reserved_run_id: null, current: { guidance: advice } }],
    workout_choices: [], actionable_proposals: [],
  } }
}

describe('useJohnny independent streams', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getJohnnyOverview).mockResolvedValue(overview('R1', 'A1') as never)
    vi.mocked(listJohnnyHistory).mockResolvedValue({ data: [] } as never)
  })

  it('retains the review while advice changes, then retains advice while review changes', async () => {
    let state!: ReturnType<typeof useJohnny>
    const Probe = defineComponent({
      setup() {
        state = useJohnny()
        return () => h('div', `${state.dailyReview.value?.current?.narrative ?? ''}|${state.workoutAdvices.value[0]?.current?.guidance ?? ''}`)
      },
    })
    const wrapper = mount(Probe)
    await flushPromises()
    expect(wrapper.text()).toBe('R1|A1')
    vi.mocked(getJohnnyOverview).mockResolvedValue(overview('R1', 'A2') as never)
    await state.refreshAdvice()
    expect(wrapper.text()).toBe('R1|A2')
    vi.mocked(getJohnnyOverview).mockResolvedValue(overview('R2', 'A2') as never)
    await state.refreshReview()
    expect(wrapper.text()).toBe('R2|A2')
    vi.mocked(getJohnnyOverview).mockRejectedValue(new Error('network'))
    await state.refreshAdvice()
    expect(wrapper.text()).toBe('R2|A2')
    expect(state.adviceError.value).toContain('保留上次結果')
    await state.refreshReview()
    expect(wrapper.text()).toBe('R2|A2')
    expect(state.reviewError.value).toContain('保留上次結果')
    wrapper.unmount()
  })

  it('retries a selected historical review from stored evidence without changing the advice stream', async () => {
    vi.mocked(retryJohnnyReview).mockResolvedValue({ data: { run_id: 'retry-1', status: 'queued' } } as never)
    let state!: ReturnType<typeof useJohnny>
    const Probe = defineComponent({ setup() { state = useJohnny(); return () => h('div') } })
    const wrapper = mount(Probe)
    await flushPromises()
    await state.retryReview('old-review', 'stored_evidence')
    expect(retryJohnnyReview).toHaveBeenCalledWith('old-review', 'stored_evidence')
    expect(state.retryPendingId.value).toBe('old-review')
    expect(state.advicePendingRunId.value).toBeNull()
    wrapper.unmount()
  })

  it('reports a historical retry failure in History without replacing the current review error', async () => {
    vi.mocked(retryJohnnyReview).mockRejectedValue(new Error('offline'))
    let state!: ReturnType<typeof useJohnny>
    const Probe = defineComponent({ setup() { state = useJohnny(); return () => h('div') } })
    const wrapper = mount(Probe)
    await flushPromises()
    await state.retryReview('old-review', 'stored_evidence')
    expect(state.historyError.value).toContain('重新分析')
    expect(state.reviewError.value).toBe('')
    expect(state.retryPendingId.value).toBeNull()
    wrapper.unmount()
  })
})
