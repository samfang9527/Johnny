import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useJohnny } from './composables/useJohnny'
import JohnnyPage from './pages/JohnnyPage.vue'
import type { JohnnyAdviceSlot, JohnnyReviewSlot } from './types'

vi.mock('./composables/useJohnny', () => ({ useJohnny: vi.fn() }))

function review(label: string): JohnnyReviewSlot {
  return {
    id: 'review', publication_date: '2026-10-16', revision_id: label,
    reserved_run_id: null, attempt_state: 'ready', attempt_error: null, freshness: 'current',
    current: {
      kind: 'daily_review', publication_date: '2026-10-16', reviewed_date: '2026-10-15',
      starts_on: '2026-10-09', ends_on: '2026-10-15', timezone_name: 'Asia/Taipei',
      generated_at: '2026-10-16T04:05:00+08:00', narrative: label,
      score: { value: 85, completion_component: 100, volume_component: 70,
        eligible_count: 2, completed_count: 2, missed_count: 0, extra_count: 0,
        covered_date_count: 7, reason: null, policy_version: 'execution-v1' },
      yesterday: [], week: [], coverage: { covered_dates: [], cutoff_at: '2026-10-16T04:05:00+08:00' },
    },
  }
}

function advice(label: string): JohnnyAdviceSlot {
  return {
    id: 'advice', advice_date: '2026-10-16', slot_key: 'workout', revision_id: label,
    reserved_run_id: null, attempt_state: 'ready', attempt_error: null, freshness: 'current',
    current: {
      kind: 'workout_advice', advice_date: '2026-10-16', workout_id: 'workout',
      guidance: label, mode: 'no_supported_adjustment', reason_code: 'follow_plan',
      constraints: { available_minutes: null, feeling: 'usual', cannot_train_today: false },
      before: null, after: null, generated_at: '2026-10-16T06:00:00+08:00',
      expires_at: '2026-10-17T00:00:00+08:00',
    },
  }
}

describe('Johnny page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders review and advice together through independent replacements and errors', async () => {
    const state = {
      dailyReview: ref<JohnnyReviewSlot | null>(review('R1')),
      workoutAdvices: ref<JohnnyAdviceSlot[]>([advice('A1')]),
      workoutChoices: ref([]), actionableProposals: ref([{ id: 'proposal', title: '縮短今日課表',
        rationale: '可用時間減少', expires_at: '2026-10-17T00:00:00+08:00',
        evidence: { proposed_action: { action_type: 'adjust_workout', payload: {
          before_payload: { display_name: '輕鬆跑', status: 'planned', planned_duration_minutes: 40,
            planned_distance_meters: null, steps: [{ duration_seconds: 2400 }] },
          after_payload: { display_name: '輕鬆跑', status: 'planned', planned_duration_minutes: 25,
            planned_distance_meters: null, steps: [{ duration_seconds: 1500 }] },
        } } },
      }]), history: ref([]), historyOffset: ref(0),
      reviewLoading: ref(false), adviceLoading: ref(false), historyLoading: ref(false),
      reviewError: ref(''), adviceError: ref(''), historyError: ref(''),
      reviewPendingRunId: ref(null), advicePendingRunId: ref(null),
      refreshReview: vi.fn(), refreshAdvice: vi.fn(), loadHistory: vi.fn(),
      requestAdvice: vi.fn(), retryReview: vi.fn(), stop: vi.fn(),
    }
    vi.mocked(useJohnny).mockReturnValue(state as unknown as ReturnType<typeof useJohnny>)
    const wrapper = mount(JohnnyPage)
    expect(wrapper.get('[data-testid="johnny-daily-review"]').text()).toContain('R1')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('A1')
    expect(wrapper.get('[data-testid="johnny-proposals"]').text()).toContain('40 分鐘 → 25 分鐘')
    state.workoutAdvices.value = [advice('A2')]
    state.adviceError.value = '稍後再試'
    await nextTick()
    expect(wrapper.get('[data-testid="johnny-daily-review"]').text()).toContain('R1')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('A2')
    state.dailyReview.value = review('R2')
    state.reviewError.value = '回顧暫停'
    await nextTick()
    expect(wrapper.get('[data-testid="johnny-daily-review"]').text()).toContain('R2')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('A2')
    expect(wrapper.text()).not.toContain('開始對話')
    wrapper.unmount()
  })
})
