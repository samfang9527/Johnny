import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SessionReviews from './SessionReviews.vue'
import { listSessionReviews, saveSessionReviews, type SessionReview } from '../api/client'
vi.mock('../api/client', () => ({ listSessionReviews: vi.fn(), saveSessionReviews: vi.fn() }))
const review: SessionReview = {
  id: 's1', local_date: '2026-10-14', status: 'automatic', workout_id: 'w1',
  activities: [
    { id: 'a1', started_at: '2026-10-14T00:00:00Z', sport_type: 'trail_running', duration_seconds: 1200, distance_meters: 3000 },
    { id: 'a2', started_at: '2026-10-14T00:25:00Z', sport_type: 'running', duration_seconds: 1800, distance_meters: 5000 },
  ],
  candidates: [{ id: 'w1', scheduled_for: '2026-10-14', workout_type: 'easy', purpose: '輕鬆跑' }],
  duration_seconds: 3000, distance_meters: 8000,
}
const wrappers: ReturnType<typeof mount>[] = []
async function render(item = review) {
  vi.mocked(listSessionReviews).mockResolvedValue({ data: [item] } as never)
  const wrapper = mount(SessionReviews, { props: { anchorDate: '2026-10-14', timeZone: 'Asia/Taipei' } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
async function click(wrapper: ReturnType<typeof mount>, label: string) {
  const button = wrapper.findAll('button').find(item => item.text() === label)
  expect(button, label).toBeTruthy()
  if (button!.attributes('type') === 'submit') await wrapper.find('form').trigger('submit')
  else await button!.trigger('click')
  await flushPromises()
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(saveSessionReviews).mockResolvedValue({ data: { saved: true } }) })
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))
describe('SessionReviews', () => {
  it('shows original recordings, local times, totals and confirms automatic matching', async () => {
    const wrapper = await render()
    expect(wrapper.text()).toContain('越野跑')
    expect(wrapper.text()).toContain('08:00')
    expect(wrapper.text()).toContain('50 分鐘')
    expect(wrapper.text()).toContain('8.00 公里')
    expect(wrapper.text()).toContain('這樣正確嗎')
    await click(wrapper, '確認配對')
    expect(saveSessionReviews).toHaveBeenCalledWith({ activity_ids: ['a1', 'a2'], groups: [{ activity_ids: ['a1', 'a2'], workout_id: 'w1' }] })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('asks to check ambiguous recordings and can mark them unplanned', async () => {
    const wrapper = await render({ ...review, status: 'needs_review', workout_id: null })
    expect(wrapper.text()).toContain('請確認')
    expect(wrapper.text()).not.toContain('未完成')
    await click(wrapper, '標記為課表外活動')
    expect(saveSessionReviews).toHaveBeenCalledWith({ activity_ids: ['a1', 'a2'], groups: [{ activity_ids: ['a1', 'a2'], workout_id: null }] })
  })
  it('splits recordings and saves individual workout assignments', async () => {
    const wrapper = await render()
    await click(wrapper, '修正配對')
    await click(wrapper, '拆成獨立活動')
    const selects = wrapper.findAll('select')
    await selects[0].setValue('w1')
    await selects[1].setValue(null)
    await click(wrapper, '儲存配對')
    expect(saveSessionReviews).toHaveBeenCalledWith({ activity_ids: ['a1', 'a2'], groups: [{ activity_ids: ['a1'], workout_id: 'w1' }, { activity_ids: ['a2'], workout_id: null }] })
  })
  it('keeps confirmed history collapsed and editable', async () => {
    const wrapper = await render({ ...review, status: 'confirmed' })
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    await click(wrapper, '修正配對')
    expect(wrapper.find('select').exists()).toBe(true)
  })
  it('preserves the editor and shows recoverable save failures', async () => {
    vi.mocked(saveSessionReviews).mockRejectedValue(new Error('offline'))
    const wrapper = await render()
    await click(wrapper, '修正配對')
    await click(wrapper, '儲存配對')
    expect(wrapper.find('[role="alert"]').text()).toContain('儲存失敗')
    expect(wrapper.find('select').element.value).toBe('w1')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
  it('offers retry after load errors', async () => {
    vi.mocked(listSessionReviews).mockRejectedValue(new Error('offline'))
    const wrapper = mount(SessionReviews, { props: { anchorDate: '2026-10-14', timeZone: 'Asia/Taipei' } })
    wrappers.push(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain('載入失敗')
    vi.mocked(listSessionReviews).mockResolvedValue({ data: [] })
    await click(wrapper, '重新載入')
    expect(wrapper.text()).toContain('目前沒有需要確認的活動')
  })
  it('ignores a response after the athlete date changes', async () => {
    let resolveOld!: (result: { data: SessionReview[] }) => void
    vi.mocked(listSessionReviews).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = mount(SessionReviews, { props: { anchorDate: '2026-10-13', timeZone: 'Asia/Taipei' } })
    wrappers.push(wrapper)
    vi.mocked(listSessionReviews).mockResolvedValue({ data: [] })
    await wrapper.setProps({ anchorDate: '2026-10-14' })
    await flushPromises()
    resolveOld({ data: [review] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('越野跑')
    expect(wrapper.text()).toContain('目前沒有需要確認的活動')
  })
  it('does not emit a save result after unmount', async () => {
    let resolveSave!: (result: { data: { saved: boolean } }) => void
    vi.mocked(saveSessionReviews).mockImplementationOnce(() => new Promise(resolve => { resolveSave = resolve }))
    const wrapper = await render()
    await click(wrapper, '確認配對')
    wrapper.unmount()
    resolveSave({ data: { saved: true } })
    await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

})
