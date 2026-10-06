import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App.vue'

const original = { id: 'race-1', user_id: 'runner', name: 'Mountain race', race_date: '2027-02-01', distance_meters: 42195, target_finish_seconds: 14401, priority: 'secondary', status: 'active', ascent_meters: 1200, descent_meters: 1100, terrain_difficulty: 'technical', cutoff_seconds: 28801, goal_intent: 'complete' }
const json = (data: unknown) => ({ ok: true, json: async () => ({ data }) }) as Response
let races: typeof original[]
let writes: RequestInit[]
let failWrite: boolean
let writeStatus: number
let planId: string
let planRaceId: string
let wrapper: ReturnType<typeof mount>

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-05T04:00:00Z'))
  races = [{ ...original }]
  writes = []
  failWrite = false
  writeStatus = 500
  planId = 'plan-1'
  planRaceId = 'race-1'
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/auth/login')) return json({ user: { id: 'runner', capabilities: ['today', 'races', 'training-plans'] } })
    if (url.endsWith('/me')) return json({ id: 'runner', capabilities: ['today', 'races', 'training-plans'] })
    if (url.endsWith('/races/race-1')) {
      if (init?.method === 'PUT' || init?.method === 'DELETE') {
        writes.push(init)
        if (failWrite) return { ok: false, status: writeStatus } as Response
        if (init.method === 'DELETE') { races = []; return json({ id: 'race-1' }) }
        races = [{ ...original, ...JSON.parse(String(init.body)) }]
      }
      return json(races[0])
    }
    if (url.includes('/races?')) return json(races)
    if (url.endsWith('/training-plans')) return json([{ id: planId, user_id: 'runner', race_id: planRaceId, name: 'Plan', status: 'active', starts_on: '2026-10-01', ends_on: '2027-02-01', metadata: {}, workouts: [] }])
    return json([])
  }))
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals(); vi.useRealTimers() })
async function render() {
  wrapper = mount(App, { attachTo: document.body, props: { initialView: 'plan', requireAuth: true } })
  await flushPromises()
}

it('edits saved canonical values, preserves status and precise cutoff, and refreshes the race', async () => {
  await render()
  await wrapper.get('[data-testid="edit-race"]').trigger('click')
  await flushPromises()
  expect((wrapper.get('[name="raceDistanceKilometers"]').element as HTMLInputElement).value).toBe('42.195')
  expect((wrapper.get('[name="targetFinishSeconds"]').element as HTMLInputElement).value).toBe('1')
  await wrapper.get('[data-testid="race-modal-close"]').trigger('click')
  expect(wrapper.find('[data-testid="confirm-dialog"]').exists()).toBe(false)
  await wrapper.get('[data-testid="edit-race"]').trigger('click')
  await flushPromises()
  await wrapper.get('[name="raceName"]').setValue('Updated race')
  await wrapper.get('[name="ascentMeters"]').setValue('')
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(JSON.parse(String(writes[0].body))).toMatchObject({ name: 'Updated race', status: 'active', cutoff_seconds: 28801 })
  expect(JSON.parse(String(writes[0].body)).ascent_meters ?? null).toBeNull()
  expect(wrapper.get('.plan-race-goal').text()).toContain('Updated race')
  expect(wrapper.find('[data-testid="race-goal-modal"]').exists()).toBe(false)
  expect(wrapper.get('[data-testid="race-plan-reminder"]').text()).toContain('重新產生')
})

it('reminds regeneration after changing a secondary race inside the remaining plan', async () => {
  planRaceId = 'another-primary-race'
  await render()
  await wrapper.get('[data-testid="edit-race"]').trigger('click')
  await flushPromises()
  await wrapper.get('[name="raceName"]').setValue('Updated secondary race')
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[data-testid="race-plan-reminder"]').text()).toContain('重新產生計畫')
})

it('keeps edits on failure and confirms before discarding changed values', async () => {
  await render()
  await wrapper.get('[data-testid="edit-race"]').trigger('click')
  await flushPromises()
  await wrapper.get('[name="raceName"]').setValue('Retry race')
  failWrite = true
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('失敗')
  expect((wrapper.get('[name="raceName"]').element as HTMLInputElement).value).toBe('Retry race')
  await wrapper.get('[data-testid="race-modal-close"]').trigger('click')
  expect(wrapper.get('[data-testid="confirm-dialog"]').text()).toContain('放棄編輯')
  await wrapper.get('[data-testid="confirm-dialog-cancel"]').trigger('click')
  failWrite = false
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.get('.plan-race-goal').text()).toContain('Retry race')
})

it('confirms deletion, preserves the list on failure, and removes the final race on retry', async () => {
  await render()
  await wrapper.get('[data-testid="delete-race"]').trigger('click')
  expect(wrapper.get('[data-testid="confirm-dialog"]').text()).toContain('Mountain race')
  expect((wrapper.get('#confirm-dialog-description').element as HTMLElement).inert).not.toBe(true)
  expect(writes).toHaveLength(0)
  await wrapper.get('[data-testid="confirm-dialog-cancel"]').trigger('click')
  expect(wrapper.find('.plan-race-goal').exists()).toBe(true)
  await wrapper.get('[data-testid="delete-race"]').trigger('click')
  failWrite = true
  await wrapper.get('[data-testid="confirm-dialog-confirm"]').trigger('click')
  await flushPromises()
  expect(wrapper.get('[data-testid="confirm-dialog"] [role="alert"]').text()).toContain('失敗')
  expect(wrapper.find('.plan-race-goal').exists()).toBe(true)
  failWrite = false
  await wrapper.get('[data-testid="confirm-dialog-confirm"]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-testid="confirm-dialog"]').exists()).toBe(false)
  expect(wrapper.find('.plan-race-goal').exists()).toBe(false)
  expect(wrapper.text()).toContain('尚未設定目標')
  expect(wrapper.get('[data-testid="race-plan-reminder"]').text()).toContain('重新產生')
})

it('restores page interaction after discarding an edit through the nested confirmation', async () => {
  await render()
  const trigger = wrapper.get('[data-testid="edit-race"]')
  ;(trigger.element as HTMLButtonElement).focus()
  await trigger.trigger('click')
  await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('[name="raceName"]').element)
  await wrapper.get('[name="raceName"]').setValue('Unsaved')
  await wrapper.get('[data-testid="race-modal-close"]').trigger('click')
  await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('[data-testid="confirm-dialog-cancel"]').element)
  await wrapper.get('[data-testid="confirm-dialog-confirm"]').trigger('click')
  await flushPromises()
  expect(document.body.style.overflow).not.toBe('hidden')
  expect((trigger.element as HTMLElement).closest('[inert]')).toBeNull()
  expect(wrapper.find('[data-testid="race-goal-modal"]').exists()).toBe(false)
})

it.each(['edit', 'delete'])('clears the %s dialog after session expiry and reauthentication', async (action) => {
  await render()
  await wrapper.get(`[data-testid="${action}-race"]`).trigger('click')
  await flushPromises()
  failWrite = true
  writeStatus = 401
  if (action === 'edit') await wrapper.get('[data-testid="race-form"]').trigger('submit')
  else await wrapper.get('[data-testid="confirm-dialog-confirm"]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[name="authEmail"]').exists()).toBe(true)
  await wrapper.get('[name="authEmail"]').setValue('next@example.com')
  await wrapper.get('[name="authPassword"]').setValue('password123')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.find('[data-testid="race-goal-modal"]').exists()).toBe(false)
  expect(wrapper.find('[data-testid="confirm-dialog"]').exists()).toBe(false)
})

it('clears the regeneration reminder when a replacement active plan arrives', async () => {
  await render()
  await wrapper.get('[data-testid="edit-race"]').trigger('click')
  await flushPromises()
  await wrapper.get('[name="raceName"]').setValue('Changed target')
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.find('[data-testid="race-plan-reminder"]').exists()).toBe(true)
  planId = 'replacement-plan'
  // A later authoritative refresh publishes the replacement active projection.
  await wrapper.get('[data-testid="edit-race"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.find('[data-testid="race-plan-reminder"]').exists()).toBe(false)
})

it('returns focus to the edit action after saving', async () => {
  await render()
  const trigger = wrapper.get('[data-testid="edit-race"]')
  ;(trigger.element as HTMLButtonElement).focus()
  await trigger.trigger('click')
  await flushPromises()
  await wrapper.get('[name="raceName"]').setValue('Focus race')
  await wrapper.get('[data-testid="race-form"]').trigger('submit')
  await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('[data-testid="edit-race"]').element)
})
