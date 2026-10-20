import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DailyAdviceCard from './DailyAdviceCard.vue'
import type { DailyAdvice } from '../types'

const ready: DailyAdvice = {
  id: 'advice-1', adviceDate: '2026-09-26', state: 'ready', dataFreshness: 'fresh',
  generatedAt: '2026-09-26T04:05:00Z', sourceSyncRunId: 'sync-1', sourceRunId: 'run-1',
  planVersionId: 'plan-1', workoutId: 'workout-1', executionMode: 'ease_off',
  planWeek: { startsOn: '2026-09-23', endsOn: '2026-09-29' },
  facts: { status: 'above', planned_count: 3, completed_count: 4 },
  weekSummary: '本週跑量比課表多，先留一點恢復空間。',
  todayExecution: '今天保留有氧目的，縮短容易累積疲勞的部分。',
  workoutGuide: { purpose: '建立有氧', expectedFeel: '跑完仍有餘裕', ifTooHard: '放慢或提早結束', ifTooEasy: '維持輕鬆，不加速' },
}

describe('DailyAdviceCard', () => {
  it('shows all three Chinese advice sections and no approval controls', () => {
    const wrapper = mount(DailyAdviceCard, { props: { advice: ready, timeZone: 'Asia/Taipei' } })
    expect(wrapper.text()).toContain('本週執行回顧')
    expect(wrapper.text()).toContain(ready.weekSummary)
    expect(wrapper.text()).toContain('今天怎麼執行')
    expect(wrapper.text()).toContain(ready.todayExecution)
    expect(wrapper.text()).toContain('這堂課的重點')
    expect(wrapper.text()).toContain('跑完仍有餘裕')
    expect(wrapper.text()).toContain('放慢或提早結束')
    expect(wrapper.text()).toContain('維持輕鬆，不加速')
    expect(wrapper.text()).not.toContain('接受調整')
    expect(wrapper.text()).not.toContain('保留課表')
    expect(wrapper.findAll('button')).toHaveLength(0)
  })

  it('shows stale prior text, generation failure, and the earlier generation time', () => {
    const wrapper = mount(DailyAdviceCard, { props: { advice: { ...ready, state: 'generation_failed', dataFreshness: 'stale' }, timeZone: 'Asia/Taipei' } })
    expect(wrapper.text()).toContain('更新失敗')
    expect(wrapper.text()).toContain('先前建議')
    expect(wrapper.text()).toContain('9/26')
    expect(wrapper.text()).toContain(ready.weekSummary)
  })

  it('shows no-plan, no-source, and completed workout states', () => {
    const pending = mount(DailyAdviceCard, { props: { advice: { ...ready, state: 'no_plan', dataFreshness: 'limited', generatedAt: null, weekSummary: null, todayExecution: null, workoutGuide: null, facts: null, planWeek: null, executionMode: null }, timeZone: 'Asia/Taipei' } })
    expect(pending.text()).toContain('今天沒有可用的訓練計畫')
    const limited = mount(DailyAdviceCard, { props: { advice: { ...ready, dataFreshness: 'limited', sourceSyncRunId: null }, timeZone: 'Asia/Taipei' } })
    expect(limited.text()).toContain('資料有限')
    const completed = mount(DailyAdviceCard, { props: { advice: { ...ready, executionMode: 'completed' }, timeZone: 'Asia/Taipei' } })
    expect(completed.text()).toContain('今天已完成')
    const rest = mount(DailyAdviceCard, { props: { advice: { ...ready, executionMode: 'rest' }, timeZone: 'Asia/Taipei' } })
    expect(rest.text()).toContain('今天休息')
    const syncFailed = mount(DailyAdviceCard, { props: { advice: { ...ready, state: 'sync_failed', dataFreshness: 'stale' }, timeZone: 'Asia/Taipei' } })
    expect(syncFailed.text()).toContain('活動同步失敗')
  })
  it('shows the activity evidence cutoff in the athlete timezone', () => {
    const wrapper = mount(DailyAdviceCard, { props: { advice: { ...ready, facts: { evidence: { activity_cutoff_at: '2026-09-26T03:00:00Z' } } }, timeZone: 'Asia/Taipei' } })
    expect(wrapper.text()).toMatch(/活動資料截至 · 9\/26\s+11:00/u)
  })

  it('keeps stale advice and its original time in an expandable reading detail on Today', () => {
    const wrapper = mount(DailyAdviceCard, { props: { advice: { ...ready, state: 'generation_failed', dataFreshness: 'stale' }, timeZone: 'Asia/Taipei', collapsed: true } })
    const detail = wrapper.get('details')
    expect(detail.attributes('open')).toBeUndefined()
    expect(detail.get('summary').text()).toContain('完整建議')
    expect(detail.text()).toContain('先前產生 · 9/26')
    expect(detail.text()).toContain(ready.weekSummary)
    expect(wrapper.find('[data-testid="recommendation-actions"]').exists()).toBe(false)
  })

})
