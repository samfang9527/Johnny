import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
  afterEach(() => vi.unstubAllGlobals())

  it('shows structured findings once, keeps the legacy text and offers stored-evidence recalculation for stale history', async () => {
    const structured = review('舊敘述')
    structured.current!.analysis = {
      schema_version: 'coaching-analysis-v2', headline: '今天先守住輕鬆強度', summary: '昨天的主課已足夠。',
      findings: [{ observation: '主課時間偏長', interpretation: '不需再補強度。', evidence_refs: [] }],
      actions: [{ action_id: 'follow_plan', text: '下次照原定強度執行。', evidence_refs: [], recommendation_id: null }],
      limitations: [], evidence_refs: [], analysis_mode: 'llm', fallback_reason: null,
      input_fingerprint: 'fp', versions: { prompt_version: 'v2' },
    }
    structured.current!.analysis.findings[0].evidence_refs = ['execution:fp:duration']
    structured.current!.analysis.evidence_refs = ['execution:fp:duration']
    structured.current!.evidence_manifest = { analyses: [{ activity_ids: ['run-1'], fingerprint: 'fp', analysis_id: 'analysis-1' }] }
    const old = advice('舊版建議原文')
    const historyReview = review('歷史舊敘述')
    historyReview.freshness = 'stale'
    const state = {
      dailyReview: ref<JohnnyReviewSlot | null>(structured), workoutAdvices: ref<JohnnyAdviceSlot[]>([old]),
      workoutChoices: ref([]), actionableProposals: ref([]),
      history: ref([{ kind: 'daily_review', id: 'history-review', at: '2026-10-17T02:00:00Z', result: historyReview }]),
      historyOffset: ref(0), reviewLoading: ref(false), adviceLoading: ref(false), historyLoading: ref(false),
      reviewError: ref(''), adviceError: ref(''), historyError: ref(''),
      reviewPendingRunId: ref<string | null>(null), advicePendingRunId: ref<string | null>(null),
      retryPendingId: ref<string | null>(null), refreshReview: vi.fn(), refreshAdvice: vi.fn(), loadHistory: vi.fn(),
      requestAdvice: vi.fn(), retryReview: vi.fn(), stop: vi.fn(),
    }
    vi.mocked(useJohnny).mockReturnValue(state as unknown as ReturnType<typeof useJohnny>)
    const wrapper = mount(JohnnyPage, { props: { timeZone: 'Asia/Taipei' } })
    await wrapper.get('[data-tab="review"]').trigger('click')
    const panel = wrapper.get('[data-testid="johnny-daily-review"]')
    expect(panel.text()).toContain('今天先守住輕鬆強度')
    expect(panel.text()).not.toContain('舊敘述')
    expect(panel.findAll('[data-testid="johnny-execution-score"]')).toHaveLength(1)
    const fetchEvidence = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: {
      activity_id: 'run-1', analysis_id: 'analysis-1', freshness: 'current',
      analysis: { activity_id: 'run-1', activity_ids: ['run-1'], fingerprint: 'fp', mapping: 'exact', findings: [] },
      used_details: [], current_details: [],
    } }) })
    vi.stubGlobal('fetch', fetchEvidence)
    await panel.get('[data-testid="open-evidence"]').trigger('click')
    await flushPromises()
    expect(String(fetchEvidence.mock.calls[0][0])).toContain('/activities/run-1/execution?analysis_id=analysis-1')
    expect(wrapper.get('[data-testid="execution-segments"]').text()).toContain('課表段落已確認')
    await wrapper.get('[data-tab="advice"]').trigger('click')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('舊版建議原文')
    await wrapper.get('[data-tab="history"]').trigger('click')
    const row = wrapper.get('[data-testid="johnny-history"] li')
    expect(row.text()).toContain('2026-10-16')
    expect(row.text()).toContain('資料已更新')
    await row.get('[data-testid="history-retry-stored"]').trigger('click')
    expect(state.retryReview).toHaveBeenCalledWith('history-review', 'stored_evidence')
    wrapper.unmount()
  })

  it('puts each pending decision before the tabs and reveals approval only with its comparison', async () => {
    const state = {
      dailyReview: ref<JohnnyReviewSlot | null>(review('R1')),
      workoutAdvices: ref<JohnnyAdviceSlot[]>([advice('A1')]),
      workoutChoices: ref([]),
      actionableProposals: ref([{ id: 'proposal', title: '縮短今日課表', rationale: '可用時間減少',
        expires_at: '2026-10-17T00:00:00+08:00', evidence: { proposed_action: { payload: {
          before_payload: { display_name: '輕鬆跑', status: 'planned', planned_duration_minutes: 40, steps: [{ duration_seconds: 2400 }] },
          after_payload: { display_name: '輕鬆跑', status: 'planned', planned_duration_minutes: 25, steps: [{ duration_seconds: 1500 }] },
        } } },
      }]),
      history: ref([]), historyOffset: ref(0),
      reviewLoading: ref(false), adviceLoading: ref(false), historyLoading: ref(false),
      reviewError: ref(''), adviceError: ref(''), historyError: ref(''),
      reviewPendingRunId: ref<string | null>(null), advicePendingRunId: ref<string | null>(null),
      refreshReview: vi.fn(), refreshAdvice: vi.fn(), loadHistory: vi.fn(),
      requestAdvice: vi.fn(), retryReview: vi.fn(), stop: vi.fn(),
    }
    vi.mocked(useJohnny).mockReturnValue(state as unknown as ReturnType<typeof useJohnny>)
    const wrapper = mount(JohnnyPage, { props: { timeZone: 'Asia/Taipei' } })

    const decision = wrapper.get('[data-testid="johnny-proposals"]')
    const tabs = wrapper.get('[role="tablist"]')
    expect(decision.element.compareDocumentPosition(tabs.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(decision.text()).toContain('40 分鐘 → 25 分鐘')
    expect(decision.get('summary').text()).toContain('查看完整變更並做決定')
    expect(decision.get('[data-action="accept"]').isVisible()).toBe(false)
    expect(decision.get('[data-action="keep"]').isVisible()).toBe(false)
    ;(decision.get('details').element as HTMLDetailsElement).open = true
    await nextTick()
    expect(decision.get('[data-action="accept"]').isVisible()).toBe(true)
    expect(decision.get('[data-action="keep"]').text()).toBe('維持原課表')

    state.actionableProposals.value = []
    await nextTick()
    expect(wrapper.find('[data-testid="johnny-proposals"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="johnny-decision-empty"]').text()).toContain('沒有需要你決定的調整')
    wrapper.unmount()
  })

  it('keeps advice and review mounted while accessible tabs change focus and visible content', async () => {
    const state = {
      dailyReview: ref<JohnnyReviewSlot | null>(review('R1')),
      workoutAdvices: ref<JohnnyAdviceSlot[]>([advice('A1')]),
      workoutChoices: ref([]), actionableProposals: ref([]),
      history: ref([]), historyOffset: ref(0),
      reviewLoading: ref(false), adviceLoading: ref(false), historyLoading: ref(false),
      reviewError: ref(''), adviceError: ref(''), historyError: ref(''),
      reviewPendingRunId: ref<string | null>(null), advicePendingRunId: ref<string | null>(null),
      refreshReview: vi.fn(), refreshAdvice: vi.fn(), loadHistory: vi.fn(),
      requestAdvice: vi.fn(), retryReview: vi.fn(), stop: vi.fn(),
    }
    vi.mocked(useJohnny).mockReturnValue(state as unknown as ReturnType<typeof useJohnny>)
    const wrapper = mount(JohnnyPage, { props: { timeZone: 'Asia/Taipei' }, attachTo: document.body })

    expect(wrapper.get('[data-tab="advice"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').isVisible()).toBe(true)
    const formDisclosure = wrapper.get('[data-testid="johnny-advice-disclosure"]')
    ;(formDisclosure.element as HTMLDetailsElement).open = true
    await wrapper.get('[data-tab="review"]').trigger('click')
    expect(wrapper.get('[data-testid="johnny-daily-review"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').isVisible()).toBe(false)
    expect(wrapper.get('[data-tab="review"]').attributes('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(wrapper.get('[data-tab="review"]').element)

    state.workoutAdvices.value = [advice('A2')]
    state.adviceError.value = '稍後再試'
    await nextTick()
    await wrapper.get('[data-tab="review"]').trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.get('[data-tab="advice"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('A2')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('稍後再試')
    expect((wrapper.get('[data-testid="johnny-advice-disclosure"]').element as HTMLDetailsElement).open).toBe(true)
    wrapper.unmount()
  })

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
      }]), history: ref([{ kind: 'workout_advice', id: 'history-1', at: '2026-10-17T02:19:11.935335+00:00' }]), historyOffset: ref(0),
      reviewLoading: ref(false), adviceLoading: ref(false), historyLoading: ref(false),
      reviewError: ref(''), adviceError: ref(''), historyError: ref(''),
      reviewPendingRunId: ref<string | null>(null), advicePendingRunId: ref<string | null>(null),
      refreshReview: vi.fn(), refreshAdvice: vi.fn(), loadHistory: vi.fn(),
      requestAdvice: vi.fn(), retryReview: vi.fn(), stop: vi.fn(),
    }
    vi.mocked(useJohnny).mockReturnValue(state as unknown as ReturnType<typeof useJohnny>)
    const wrapper = mount(JohnnyPage, { props: { timeZone: 'Asia/Taipei' } })
    expect(wrapper.get('[data-testid="johnny-daily-review"]').text()).toContain('R1')
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toContain('A1')
    expect(wrapper.get('[data-testid="johnny-proposals"]').text()).toContain('40 分鐘 → 25 分鐘')
    expect(wrapper.get('[data-testid="johnny-daily-review"]').text()).toMatch(/2026\/10\/16\s+04:05/u)
    expect(wrapper.get('[data-testid="johnny-workout-advice"]').text()).toMatch(/2026\/10\/16\s+06:00/u)
    expect(wrapper.get('[data-testid="johnny-history"]').text()).toMatch(/2026\/10\/17\s+10:19/u)
    expect(wrapper.get('[data-testid="johnny-proposals"]').text()).toMatch(/2026\/10\/17\s+00:00/u)
    expect(wrapper.text()).not.toContain('T02:19:11')
    expect(wrapper.get('.johnny-advice-form__availability').text()).toContain('不填則依原課表建議')
    await wrapper.get('#johnny-available-minutes').setValue('45')
    await wrapper.get('input[name="johnny-training-availability"][value="cannot"]').setValue()
    expect(wrapper.find('#johnny-available-minutes').exists()).toBe(false)
    expect(wrapper.get('.johnny-advice-form__feeling').text()).toContain('今天的感覺')
    await wrapper.get('.johnny-advice-form').trigger('submit')
    expect(state.requestAdvice).toHaveBeenCalledWith(null, {
      available_minutes: null, feeling: 'usual', cannot_train_today: true,
    }, expect.any(String))
    await wrapper.get('input[name="johnny-training-availability"][value="can"]').setValue()
    expect((wrapper.get('#johnny-available-minutes').element as HTMLInputElement).value).toBe('')
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
    state.workoutAdvices.value = []
    state.advicePendingRunId.value = 'run-1'
    await nextTick()
    expect(wrapper.get('.johnny-advice-form__action').text()).toContain('正在分析今天的資料')
    expect(wrapper.get('.johnny-advice-form__action').text()).not.toContain('尚未取得今天的建議')
    wrapper.unmount()
  })
})
