import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CoachingAnalysis from './CoachingAnalysis.vue'
import ExecutionSegments from './ExecutionSegments.vue'
import type { ActivityExecutionResponse, CoachingAnalysis as Analysis } from '../types'

const analysis: Analysis = {
  schema_version: 'coaching-analysis-v2', headline: '今天保守跑', summary: '先保留有氧目的。',
  findings: [{ observation: '昨天主課偏長', interpretation: '今天不必補強度。', evidence_refs: ['execution:fp:duration'] }],
  actions: [{ action_id: 'follow_plan', text: '依原定輕鬆配速跑。', evidence_refs: ['workout:today'], recommendation_id: null }],
  limitations: ['心率分段不完整'], evidence_refs: ['execution:fp:duration'],
  analysis_mode: 'rules', fallback_reason: 'timeout', input_fingerprint: 'fp', versions: { prompt_version: 'v2' },
}

describe('CoachingAnalysis', () => {
  it('reads conclusion, meaning, then action in DOM order; discloses reasons and labels rules independently of coverage', async () => {
    const wrapper = mount(CoachingAnalysis, { props: { analysis, freshness: 'current', kind: 'daily_review',
      evidenceTargets: [{ ref: 'execution:fp:duration', activityId: 'run-1', analysisId: 'analysis-1' }] } })
    const content = wrapper.get('[data-testid="coaching-analysis"]').text()
    expect(content.indexOf('今天保守跑')).toBeLessThan(content.indexOf('今天不必補強度'))
    expect(content.indexOf('今天不必補強度')).toBeLessThan(content.indexOf('依原定輕鬆配速跑'))
    expect(wrapper.text()).toContain('規則產生')
    expect(wrapper.text()).not.toContain('資料不足')
    expect(wrapper.get('details').text()).toContain('心率分段不完整')
    await wrapper.get('[data-testid="open-evidence"]').trigger('click')
    expect(wrapper.emitted('openEvidence')?.[0]).toEqual([{ activityId: 'run-1', analysisId: 'analysis-1' }])
  })

  it('marks a stale result without rewriting its original conclusion and emits an approved action', async () => {
    const wrapper = mount(CoachingAnalysis, { props: { analysis: { ...analysis, analysis_mode: 'llm', fallback_reason: null,
      actions: [{ ...analysis.actions[0], recommendation_id: 'rec-1' }] }, freshness: 'stale', kind: 'workout_advice' } })
    expect(wrapper.text()).toContain('資料已更新')
    expect(wrapper.text()).toContain('今天保守跑')
    expect(wrapper.text()).not.toContain('規則產生')
    expect(wrapper.find('[data-testid="open-recommendation"]').exists()).toBe(false)
    await wrapper.setProps({ freshness: 'current' })
    await wrapper.get('[data-testid="open-recommendation"]').trigger('click')
    expect(wrapper.emitted('openRecommendation')?.[0]).toEqual(['rec-1'])
  })
})

describe('ExecutionSegments', () => {
  it('separates known and estimated mapping and calls sampled chart data sampled', () => {
    const execution: ActivityExecutionResponse = { activity_id: 'run-1', analysis_id: 'analysis-1', freshness: 'current',
      analysis: { activity_id: 'run-1', activity_ids: ['run-1'], fingerprint: 'fp', prescription_revision_id: null,
        snapshot_ids: ['snapshot-1'], mapping: 'estimated', facts: [], findings: [], limitations: [], algorithm_version: 'v1' },
      used_details: [{ snapshot_id: 'snapshot-1', activity_id: 'run-1', resource: 'fit', precision: 'sampled',
        coverage: { state: 'partial', sampling: 'chart', covered_seconds: 600, missing_channels: ['heart_rate'], limitations: [] },
        segments: [{ source_index: 0, source_kind: 'lap', timer_seconds: 600, elapsed_seconds: 610,
          distance_meters: 1800, average_heart_rate_bpm: null, average_pace_seconds_per_km: 333, step_path: null }] }],
      current_details: [] }
    const wrapper = mount(ExecutionSegments, { props: { execution } })
    expect(wrapper.text()).toContain('推估配對')
    expect(wrapper.text()).toContain('圖表抽樣')
    expect(wrapper.text()).toContain('部分涵蓋')
    expect(wrapper.text()).toContain('缺少心率')
    expect(wrapper.text()).not.toContain('完整記錄')
  })
})
