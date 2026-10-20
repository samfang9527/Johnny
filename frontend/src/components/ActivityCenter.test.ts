import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ActivityCenter from './ActivityCenter.vue'

describe('ActivityCenter', () => {
  it('opens a task list, navigates to a result, and exposes completion feedback', async () => {
    const wrapper = mount(ActivityCenter, { props: {
      tasks: [{ id: 'plan-1', workflow: 'training_plan_generation', title: '訓練計畫', status: 'running',
        detail: '正在處理，可繼續使用 Johnny。', view: 'plan', action: '查看計畫' }],
      activeCount: 1,
      toast: { message: '訓練計畫已完成', view: 'plan', workflow: 'training_plan_generation', action: '查看計畫', tone: 'success' },
    } })
    expect(wrapper.get('[data-testid="activity-trigger"]').text()).toContain('計畫產生中')
    await wrapper.get('[data-testid="activity-trigger"]').trigger('click')
    expect(wrapper.get('[data-testid="activity-panel"]').text()).toContain('正在處理')
    await wrapper.get('[data-testid="activity-task-action"]').trigger('click')
    expect(wrapper.emitted('navigate')?.[0]).toEqual(['plan', 'training_plan_generation'])
    expect(wrapper.get('[data-testid="activity-toast"]').text()).toContain('訓練計畫已完成')
  })
})
