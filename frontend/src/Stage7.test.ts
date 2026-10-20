import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import type { TrainingPlanPhase, TrainingPlanResponse } from './types'

const json = (data: unknown) => ({ ok: true, json: async () => ({ data }) }) as Response
function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => { resolve = done })
  return { promise, resolve }
}
const workout = (id: string, date: string) => ({ id, scheduled_for: date, workout_type: 'easy_run', purpose: id, status: 'planned' })
function plan(phase: TrainingPlanPhase = 'maintenance', overrides: Partial<TrainingPlanResponse> = {}): TrainingPlanResponse {
  return { id: 'active', user_id: 'runner', race_id: null, name: 'Plan', status: 'active', starts_on: '2026-09-01', ends_on: '2026-09-30', metadata: { phase_segments: [{ phase, starts_on: '2026-09-01', ends_on: '2026-09-30', focus: `canonical-${phase}` }] }, workouts: [], ...overrides }
}
const run = { run_id: 'long-run', status: 'processing', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/long-run' }
const options = { quota: { quota_day: '2026-09-26', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null }, default_strategy: { race_id: null, plan_type: 'maintenance', reason: 'no_future_race', starts_on: '2026-09-27', plan_horizon_weeks: 4 }, in_flight_run: run, run: null }

describe('Stage 7 frontend acceptance', () => {
  let wrapper: VueWrapper | undefined
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-09-26T12:00:00Z'))
    window.location.hash = ''
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers(); vi.unstubAllGlobals() })
  async function render(plans: TrainingPlanResponse[], extra?: (url: string) => Response | Promise<Response> | undefined, timezone = 'Asia/Taipei') {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input)
      const response = extra?.(url)
      if (response) return response
      if (url.endsWith('/api/v1/me')) return json({ id: 'runner', capabilities: ['training-plans'] })
      if (url.endsWith('/api/v1/athlete/profile')) return json({ timezone })
      if (url.endsWith('/api/v1/training-plans')) return json(plans)
      return json([])
    })
    wrapper = mount(App, { props: { requireAuth: true, initialView: 'plan' } })
    await flushPromises()
    return wrapper
  }

  it.each(['base', 'maintenance', 'taper', 'race'] as const)('uses canonical %s metadata in the journey without workouts', async (phase) => {
    const app = await render([plan(phase)])
    expect(app.get('[data-testid="plan-training-journey"]').text()).toContain(`canonical-${phase}`)
    expect(app.find('[data-testid="plan-phase-timeline"]').exists()).toBe(false)
    expect(app.findAll('[data-testid="plan-journey-stop"]')).toHaveLength(1)
    expect(app.get('[data-testid="plan-journey-stop"]').classes()).toContain('plan-journey__stop--current')
    expect(app.get('[data-testid="plan-training-journey"]').text()).not.toContain('Build')
  })
  it('shows only races snapshotted into the active plan as its race context', async () => {
    const app = await render([plan('build', {
      race_id: 'target-race',
      ends_on: '2026-11-15',
      workouts: [
        { ...workout('supporting-race-workout', '2026-10-25'), workout_type: 'race', race_goal_id: 'supporting-race', race_name: 'Riverside 10K', race_priority: 'tune_up', planned_distance_meters: 10000 },
        { ...workout('target-race-workout', '2026-11-15'), workout_type: 'race', race_goal_id: 'target-race', race_name: 'Taipei Half Tune-up', race_priority: 'primary', planned_distance_meters: 21097 },
      ],
    })], (url) => url.includes('/api/v1/races') ? json([{
      id: 'new-race', name: 'New race outside this plan', race_date: '2026-11-01', distance_meters: 5000, priority: 'secondary', status: 'planned',
    }]) : undefined)

    const included = app.get('.plan-races__included')
    expect(included.text()).toContain('目標賽事 · 計畫以此為訓練方向')
    expect(included.text()).toContain('Taipei Half Tune-up')
    expect(included.text()).toContain('其他已納入賽事 · 影響附近課表')
    expect(included.text()).toContain('Riverside 10K')
    expect(included.text()).not.toContain('New race outside this plan')
    expect(app.get('.plan-races__management').text()).toContain('New race outside this plan')
  })
  it('has an honest authenticated no-active journey and Today rail', async () => {
    const app = await render([])
    expect(app.findAll('[data-testid="plan-journey-stop"]')).toHaveLength(0)
    expect(app.find('[data-testid="plan-training-journey"]').exists()).toBe(false)
    expect(app.get('[data-testid="plan-current-phase"]').text()).toContain('尚無有效訓練計畫')
    expect(app.get('[data-testid="plan-current-phase"]').find('[data-testid="open-plan-regeneration-sheet"]').exists()).toBe(true)
    await app.get('[data-view="today"]').trigger('click')
    expect(app.text()).not.toContain('Build')
  })
  it('keeps five canonical phase stops separate from bounded journey status prose', async () => {
    const phases = ['base', 'build', 'peak', 'taper', 'race'] as const
    const app = await render([plan('base', { metadata: { phase_segments: phases.map((phase) => ({
      phase, starts_on: '2026-09-01', ends_on: '2026-09-30', focus: `canonical-${phase}`,
    })) } })])
    const scroller = app.get('[data-testid="plan-journey-phases"]')
    expect(scroller.findAll('[data-testid="plan-journey-stop"]')).toHaveLength(5)
    for (const phase of phases) expect(scroller.text()).toContain(`canonical-${phase}`)
    expect(scroller.text()).not.toContain('目前計畫')
    expect(app.get('[data-testid="plan-current-phase"]').text()).toContain('canonical-base')
  })
  it.each([
    ['2026-09-25T15:59:59Z', 'base'],
    ['2026-09-25T16:00:00Z', 'taper'],
    ['2026-09-26T15:59:59Z', 'taper'],
  ])('uses inclusive athlete-local phase dates at %s', async (instant, current) => {
    vi.setSystemTime(new Date(instant))
    const app = await render([plan('base', { metadata: { phase_segments: [
      { phase: 'base', starts_on: '2026-09-01', ends_on: '2026-09-25', focus: 'canonical-base' },
      { phase: 'taper', starts_on: '2026-09-26', ends_on: '2026-09-30', focus: 'canonical-taper' },
    ] } })])
    expect(app.get('.plan-journey__stop--current').text()).toContain(`canonical-${current}`)
  })
  it('preserves the authoritative today predecessor ID but never unrelated or old future workouts', async () => {
    const app = await render([
      plan('base', { id: 'unrelated', status: 'superseded', starts_on: '2026-08-01', workouts: [workout('unrelated-today', '2026-09-26')] }),
      plan('base', { id: 'predecessor', status: 'superseded', starts_on: '2026-09-01', workouts: [workout('preserved-today', '2026-09-26'), workout('old-future', '2026-09-28')] }),
      plan('maintenance', { starts_on: '2026-09-27', metadata: { previous_plan_id: 'predecessor' }, workouts: [workout('new-future', '2026-09-28')] }),
    ], (url) => url.includes('/today') ? json({ scheduled_workouts: [workout('preserved-today', '2026-09-26')] }) : undefined)
    expect(app.text()).toContain('preserved-today')
    expect(app.text()).toContain('new-future')
    expect(app.text()).not.toContain('old-future')
    expect(app.text()).not.toContain('unrelated-today')
    await app.get('[data-view="today"]').trigger('click')
    expect(app.text()).toContain('preserved-today')
  })
  it('does not guess today from superseded plans when the authoritative Today payload is empty', async () => {
    const app = await render([plan('base', { status: 'superseded', workouts: [workout('untrusted-today', '2026-09-26')] }), plan('maintenance', { starts_on: '2026-09-27' })])
    expect(app.text()).not.toContain('untrusted-today')
  })
  it('hydrates Today using the athlete date rather than UTC', async () => {
    vi.setSystemTime(new Date('2026-09-25T16:00:00Z'))
    await render([])
    const todayRequests = vi.mocked(fetch).mock.calls.map(([input]) => String(input)).filter((url) => url.includes('/api/v1/today'))
    expect(todayRequests).toHaveLength(1)
    expect(todayRequests[0]).toContain('date=2026-09-26')
  })
  it('advances the Today date strip with the athlete-local workout after midnight', async () => {
    vi.setSystemTime(new Date('2026-09-26T15:59:59Z'))
    const app = await render([plan('base')], (url) => {
      if (!url.includes('/api/v1/today')) return undefined
      const day = url.includes('date=2026-09-27') ? '2026-09-27' : '2026-09-26'
      return json({ scheduled_workouts: [workout(`run-${day}`, day)], recovery: {} })
    })
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[data-testid="today-date-strip"]').attributes('datetime')).toBe('2026-09-26')
    expect(app.get('[data-today-workout-summary]').text()).toContain('run-2026-09-26')
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(app.get('[data-testid="today-date-strip"]').attributes('datetime')).toBe('2026-09-27')
    expect(app.get('[data-today-workout-summary]').text()).toContain('run-2026-09-27')
  })
  it('updates an open journey after athlete-local midnight', async () => {
    vi.setSystemTime(new Date('2026-09-25T15:59:59Z'))
    const app = await render([plan('base', { metadata: { phase_segments: [
      { phase: 'base', starts_on: '2026-09-01', ends_on: '2026-09-25' },
      { phase: 'taper', starts_on: '2026-09-26', ends_on: '2026-09-30' },
    ] } })])
    expect(app.get('.plan-journey__stop--current').text()).toContain('基礎期')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(app.get('.plan-journey__stop--current').text()).toContain('減量期')
  })
  it('shows the next eligible Plan workout instead of an earlier or completed session', async () => {
    const app = await render([plan('maintenance', { workouts: [
      { ...workout('earlier', '2026-09-23'), status: 'completed' },
      { ...workout('finished-today', '2026-09-26'), status: 'completed' },
      workout('next-run', '2026-09-27'),
    ] })])
    const summary = app.get('[data-testid="plan-summary"]')
    expect(summary.text()).toContain('2026-09-27')
    expect(summary.text()).not.toContain('2026-09-23')
    expect(summary.text()).not.toContain('2026-09-26')
  })
  it('advances the Plan next-workout summary at athlete-local midnight', async () => {
    vi.setSystemTime(new Date('2026-09-26T15:59:59Z'))
    const app = await render([plan('maintenance', { workouts: [
      workout('today-run', '2026-09-26'),
      workout('tomorrow-run', '2026-09-27'),
    ] })])
    expect(app.get('[data-testid="plan-summary"]').text()).toContain('2026-09-26')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(app.get('[data-testid="plan-summary"]').text()).toContain('2026-09-27')
  })
  it('does not restore calendar projection A after completion publishes B, and still refreshes new-day Today', async () => {
    vi.setSystemTime(new Date('2026-09-26T15:59:59Z'))
    const calendarToday = deferredResponse()
    let plansCalls = 0
    let todayCalls = 0
    const app = await render([], (url) => {
      if (url.endsWith('/regeneration-options')) return json(options)
      if (url.endsWith('/agent-runs/long-run')) return json({ status: 'completed' })
      if (url.endsWith('/training-plans')) return json([plan(plansCalls++ < 2 ? 'base' : 'maintenance', { workouts: [workout(plansCalls < 3 ? 'projection-A' : 'projection-B', '2026-09-28')] })])
      if (url.includes('/today')) {
        todayCalls++
        if (todayCalls === 2) return calendarToday.promise
        const date = new URL(url).searchParams.get('anchor_date')!
        return json({ scheduled_workouts: [workout(`fresh-${date}`, date)] })
      }
    })
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    vi.setSystemTime(new Date('2026-09-26T16:00:00Z'))
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(app.text()).toContain('projection-B')
    calendarToday.resolve(json({ scheduled_workouts: [workout('obsolete-calendar', '2026-09-27')] }))
    await flushPromises()
    expect(app.text()).toContain('projection-B')
    expect(app.text()).not.toContain('projection-A')
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[data-today-workout-summary]').text()).toContain('fresh-2026-09-27')
  })
  it('does not let an older completion batch replace a newer calendar snapshot', async () => {
    vi.setSystemTime(new Date('2026-09-26T15:59:55Z'))
    const completionOptions = deferredResponse()
    let optionsCalls = 0
    let plansCalls = 0
    const app = await render([], (url) => {
      if (url.endsWith('/regeneration-options')) return ++optionsCalls === 1 ? json(options) : completionOptions.promise
      if (url.endsWith('/agent-runs/long-run')) return json({ status: 'completed' })
      if (url.endsWith('/training-plans')) return json([plan(plansCalls++ < 2 ? 'base' : 'maintenance', { workouts: [workout(plansCalls < 3 ? 'projection-A' : 'projection-B', '2026-09-28')] })])
      if (url.includes('/today')) {
        const date = new URL(url).searchParams.get('anchor_date')!
        return json({ scheduled_workouts: [workout(`fresh-${date}`, date)] })
      }
    })
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    vi.setSystemTime(new Date('2026-09-26T16:00:00Z'))
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(app.text()).toContain('projection-B')
    completionOptions.resolve(json({ ...options, in_flight_run: null }))
    await flushPromises()
    expect(app.text()).toContain('projection-B')
    expect(app.text()).not.toContain('projection-A')
  })
  it('revalidates the current day when first hydration is held across midnight', async () => {
    vi.setSystemTime(new Date('2026-09-26T15:59:59Z'))
    const firstToday = deferredResponse()
    let todayCalls = 0
    const app = await render([], (url) => {
      if (url.includes('/today')) {
        if (++todayCalls === 1) return firstToday.promise
        const date = new URL(url).searchParams.get('anchor_date')!
        return json({ scheduled_workouts: [workout(`fresh-${date}`, date)] })
      }
    })
    vi.setSystemTime(new Date('2026-09-26T16:00:00Z'))
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    firstToday.resolve(json({ scheduled_workouts: [workout('yesterday-held', '2026-09-26')] }))
    await flushPromises()
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[data-today-workout-summary]').text()).toContain('fresh-2026-09-27')
    expect(app.text()).not.toContain('yesterday-held')
  })
  it.each([
    ['profile', 'success'], ['profile', '401'], ['batch', 'success'], ['batch', '401'],
  ])('ignores old-session %s %s responses after the same athlete logs in again', async (stage, outcome) => {
    const oldResponse = deferredResponse()
    let profileCalls = 0
    let todayCalls = 0
    const app = await render([], (url) => {
      if (url.endsWith('/athlete/profile')) {
        if (++profileCalls === 1 && stage === 'profile') return oldResponse.promise
        return json({ timezone: 'Asia/Taipei', current_weekly_mileage_km: 42 })
      }
      if (url.includes('/today')) {
        if (++todayCalls === 1 && stage === 'batch') return oldResponse.promise
        return json({ scheduled_workouts: [workout('fresh-session', '2026-09-26')] })
      }
      if (url.endsWith('/auth/login')) return json({ user: { id: 'runner', capabilities: ['training-plans'] } })
    })
    await app.get('.user-menu button').trigger('click')
    await flushPromises()
    await app.get('[name="authEmail"]').setValue('runner@example.com')
    await app.get('[name="authPassword"]').setValue('password123')
    await app.get('[data-testid="auth-form"]').trigger('submit')
    await flushPromises()
    oldResponse.resolve(outcome === '401' ? { ok: false, status: 401, json: async () => ({ error: { message: 'old session expired' } }) } as Response : json(stage === 'profile' ? { timezone: 'UTC', current_weekly_mileage_km: 999 } : { scheduled_workouts: [workout('obsolete-session', '2026-09-26')] }))
    await flushPromises()
    expect(app.find('[data-testid="auth-form"]').exists()).toBe(false)
    await app.get('[data-view="athlete"]').trigger('click')
    expect((app.get('[name="athleteTimezone"]').element as HTMLSelectElement).value).toBe('Asia/Taipei')
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[data-today-workout-summary]').text()).toContain('fresh-session')
    expect(app.text()).not.toContain('obsolete-session')
  })
  it.each(['focus', 'timer'])('exposes degraded midnight Today and retries the failed date on %s', async (trigger) => {
    vi.setSystemTime(new Date('2026-09-26T15:59:59Z'))
    let newDayCalls = 0
    const app = await render([], (url) => {
      if (url.includes('/today')) {
        const date = new URL(url).searchParams.get('anchor_date')!
        if (date === '2026-09-27' && ++newDayCalls === 1) return Promise.reject(new Error('transient network failure'))
        return json({ scheduled_workouts: [workout(`fresh-${date}`, date)] })
      }
    })
    vi.setSystemTime(new Date('2026-09-26T16:00:00Z'))
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[role="alert"]').text()).toContain('今天資料載入失敗')
    expect(app.find('[data-testid="today-decision-action"]').exists()).toBe(false)
    expect(app.text()).not.toContain('fresh-2026-09-26')
    if (trigger === 'focus') window.dispatchEvent(new Event('focus'))
    else await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(app.get('[data-today-workout-summary]').text()).toContain('fresh-2026-09-27')
    expect(app.find('[role="alert"]').exists()).toBe(false)
  })
  it.each(['timer', 'focus'])('refreshes recovery and authoritative Today/race anchors across local midnight via %s', async (trigger) => {
    vi.setSystemTime(new Date('2026-09-26T15:59:59Z'))
    const app = await render([plan('race', { status: 'completed', ends_on: '2026-09-19' })], (url) => {
      if (url.includes('/api/v1/today')) {
        const date = new URL(url).searchParams.get('anchor_date')!
        return json({ scheduled_workouts: [workout(`trusted-${date}`, date)] })
      }
    })
    expect(app.get('[data-testid="plan-recovery-window"]').text()).toContain('第 7 / 7 天')
    vi.mocked(fetch).mockClear()
    if (trigger === 'timer') await vi.advanceTimersByTimeAsync(60_000)
    else {
      vi.setSystemTime(new Date('2026-09-26T16:00:00Z'))
      window.dispatchEvent(new Event('focus'))
    }
    await flushPromises()
    expect(app.find('[data-testid="plan-recovery-window"]').exists()).toBe(false)
    const requests = vi.mocked(fetch).mock.calls.map(([input]) => new URL(String(input)))
    expect(requests.find((url) => url.pathname.endsWith('/today'))?.searchParams.get('anchor_date')).toBe('2026-09-27')
    expect(requests.find((url) => url.pathname.endsWith('/races'))?.searchParams.get('race_date_from')).toBe('2026-09-27')
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[data-today-workout-summary]').text()).toContain('trusted-2026-09-27')
    expect(app.get('[data-today-workout-summary]').text()).not.toContain('trusted-2026-09-26')
    vi.mocked(fetch).mockClear()
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    const repeatedCalendarRequests = vi.mocked(fetch).mock.calls
      .map(([input]) => new URL(String(input)).pathname)
      .filter((path) => path.endsWith('/today') || path.endsWith('/races'))
    expect(repeatedCalendarRequests).toHaveLength(0)
  })
  it('resolves original Today details by its exact ID without selecting a different predecessor', async () => {
    const app = await render([plan('base', { status: 'superseded', workouts: [{ ...workout('original', '2026-09-26'), display_name: 'Original canonical name', steps: [{ type: 'free_run', duration_seconds: 1800, target: { kind: 'rpe', rpe: 3 } }] }] }), plan('maintenance', { starts_on: '2026-09-27' })], (url) => url.includes('/today') ? json({ scheduled_workouts: [{ id: 'original', scheduled_for: '2026-09-26' }] }) : undefined)
    expect(app.text()).toContain('Original canonical name')
    await app.get('[data-testid="workout-detail-original"]').trigger('click')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('RPE 3')
  })
  it('prefers the authoritative Today workout over a conflicting current plan workout', async () => {
    const app = await render([plan('base', { workouts: [workout('conflicting-plan-today', '2026-09-26')] })], (url) => url.includes('/today') ? json({ scheduled_workouts: [workout('trusted-today', '2026-09-26')] }) : undefined)
    await app.get('[data-view="today"]').trigger('click')
    expect(app.get('[data-today-workout-summary]').text()).toContain('trusted-today')
    expect(app.get('[data-today-workout-summary]').text()).not.toContain('conflicting-plan-today')
  })
  it.each([
    ['2026-09-19T16:00:00Z', true, '第 1 / 7 天'],
    ['2026-09-25T15:59:59Z', true, '第 6 / 7 天'],
    ['2026-09-25T16:00:00Z', true, '第 7 / 7 天'],
    ['2026-09-26T16:00:00Z', false, '尚無有效訓練計畫'],
  ])('distinguishes recovery from stale plans at %s', async (instant, visible, text) => {
    vi.setSystemTime(new Date(instant))
    const app = await render([plan('race', { status: 'completed', ends_on: '2026-09-19' })])
    expect(app.find('[data-testid="plan-recovery-window"]').exists()).toBe(visible)
    expect(app.get('[data-testid="plan-current-phase"]').text()).toContain(text)
    if (visible) {
      const recovery = app.get('[data-testid="plan-recovery-window"]')
      expect(recovery.text()).toContain('2026-09-20')
      expect(recovery.text()).toContain('2026-09-26')
      expect(recovery.text()).toContain('上一份計畫已結束')
      expect(app.findAll('[data-testid="plan-journey-stop"]')).toHaveLength(0)
    }
  })
  it('keeps day seven recovery separate from a future day eight projection', async () => {
    const app = await render([plan('race', { status: 'completed', ends_on: '2026-09-19' }), plan('maintenance', { starts_on: '2026-09-27', metadata: { phase_segments: [{ phase: 'maintenance', starts_on: '2026-09-27', ends_on: '2026-10-24' }] } })])
    expect(app.get('[data-testid="plan-recovery-window"]').text()).toContain('第 7 / 7 天')
    expect(app.find('.plan-journey__stop--current').exists()).toBe(false)
    expect(app.get('[data-testid="plan-journey-stop"]').classes()).toContain('plan-journey__stop--next')
    expect(app.get('[data-testid="plan-recovery-window"]').text()).toContain('下一份計畫已排定')
  })
  it('shows day seven generation as in progress, not a newly active recovery plan', async () => {
    const app = await render([plan('race', { status: 'completed', ends_on: '2026-09-19' })], (url) => url.endsWith('/regeneration-options') ? json(options) : undefined)
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    expect(app.get('[data-testid="plan-recovery-window"]').text()).toContain('下一份計畫產生中')
    expect(app.findAll('[data-testid="plan-journey-stop"]')).toHaveLength(0)
  })
  it('shows the new canonical phase on day eight rather than recovery', async () => {
    vi.setSystemTime(new Date('2026-09-26T16:00:00Z'))
    const app = await render([plan('race', { status: 'completed', ends_on: '2026-09-19' }), plan('maintenance', { starts_on: '2026-09-27', metadata: { phase_segments: [{ phase: 'maintenance', starts_on: '2026-09-27', ends_on: '2026-10-24' }] } })])
    expect(app.find('[data-testid="plan-recovery-window"]').exists()).toBe(false)
    expect(app.get('.plan-journey__stop--current').text()).toContain('維持期')
  })
  it('derives recovery from the latest ended active projection without claiming a phase', async () => {
    const app = await render([plan('race', { status: 'completed', ends_on: '2026-09-10' }), plan('maintenance', { ends_on: '2026-09-25' })])
    expect(app.get('[data-testid="plan-recovery-window"]').text()).toContain('2026-09-26 - 2026-10-02')
    expect(app.find('[data-testid="plan-phase-timeline"]').exists()).toBe(false)
  })
  it('renders canonical names and repaired pace RPE with legacy compatibility', async () => {
    const app = await render([plan('maintenance', { workouts: [
      { ...workout('canonical', '2026-09-27'), display_name: '6 x 400m Intervals', steps: [{ type: 'work', duration_seconds: 120, target: { kind: 'pace', zone: 'I', rpe: 8 } }] },
      workout('legacy', '2026-09-28'),
    ] })])
    expect(app.text()).toContain('6 x 400m Intervals')
    expect(app.text()).toContain('輕鬆跑')
    await app.get('[data-testid="workout-detail-canonical"]').trigger('click')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('RPE 8')
    expect(app.get('#workout-detail-title').text()).toBe('6 x 400m Intervals')
  })
  it('shows each race workout with its event identity and distance', async () => {
    const races = [
      ['primary', 'Autumn Marathon', 42195],
      ['secondary', 'Riverside Half', 21097],
      ['tune_up', 'Park 10K', 10000],
    ] as const
    const app = await render([plan('race', { race_id: 'goal-0', workouts: races.map(([priority, name, distance], index) => ({
      ...workout(`race-${index}`, `2026-09-${27 + index}`), workout_type: 'race', race_goal_id: `goal-${index}`,
      race_name: name, race_priority: priority, planned_distance_meters: distance,
      display_name: `${name} · ${Number((distance / 1000).toFixed(3))} km`,
    })) })])
    await app.get('[data-testid="load-next-training-week"]').trigger('click')
    expect(app.get('[data-testid="schedule-workout-race-0"] h3').text()).toBe('Autumn Marathon · 42.195 km')
    expect(app.get('[data-testid="schedule-workout-race-0"]').text()).toContain('目標賽事')
    for (const [priority, name, distance] of races) {
      expect(app.text()).toContain(name)
      expect(app.text()).toContain(priority === 'tune_up' ? '暖身賽' : priority === 'secondary' ? '次要目標' : '主要目標')
      expect(app.text()).toContain(`${Number((distance / 1000).toFixed(3))} km`)
    }
  })
  it('shows primary effort and estimated pace evidence for RPE and heart-rate targets', async () => {
    const app = await render([plan('maintenance', { workouts: [
      { ...workout('rpe-pace', '2026-09-27'), steps: [{ type: 'work', duration_seconds: 1200, target: { kind: 'rpe', rpe: 6, zone: 'marathon', pace_range_seconds_per_km: [318, 336], pace_source: 'threshold_pace', confidence: 'high' } }] },
      { ...workout('hr-pace', '2026-09-28'), steps: [{ type: 'work', duration_seconds: 1200, target: { kind: 'heart_rate', heart_rate_zone: 'easy', heart_rate_range_bpm: [120, 140], rpe: 3, pace_range_seconds_per_km: [360, 390], pace_source: 'paired_easy_activities', confidence: 'medium' } }] },
      { ...workout('no-pace', '2026-09-29'), steps: [{ type: 'work', duration_seconds: 1200, target: { kind: 'rpe', rpe: 3 } }] },
      { ...workout('hill-pace', '2026-09-30'), workout_type: 'hill', steps: [{ type: 'hill', duration_seconds: 90, target: { kind: 'rpe', rpe: 8, pace_range_seconds_per_km: [300, 330], pace_source: 'goal_time', confidence: 'low' } }] },
    ] })])
    expect(app.get('[data-testid="schedule-workout-hr-pace"]').text()).toContain('RPE 3 · 心率 120-140 bpm · 預估配速 6:00-6:30 /km')
    await app.get('[data-testid="workout-detail-rpe-pace"]').trigger('click')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('RPE 6')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('預估配速 5:18-5:36 /km')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('閾值配速 · 高信心')
    await app.get('[data-testid="workout-detail-close"]').trigger('click')
    await app.get('[data-testid="workout-detail-hr-pace"]').trigger('click')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('120-140 bpm')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('預估配速 6:00-6:30 /km')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('配對輕鬆跑 · 中信心')
    await app.get('[data-testid="workout-detail-close"]').trigger('click')
    await app.get('[data-testid="load-next-training-week"]').trigger('click')
    await app.get('[data-testid="workout-detail-no-pace"]').trigger('click')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('RPE 3')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).not.toContain('預估配速')
    await app.get('[data-testid="workout-detail-close"]').trigger('click')
    await app.get('[data-testid="workout-detail-hill-pace"]').trigger('click')
    expect(app.get('[data-testid="workout-detail-modal"]').text()).toContain('平地參考配速')
  })
  it('shows one plan week first, loads the next, and labels executable workout stages', async () => {
    const app = await render([plan('maintenance', { starts_on: '2026-09-27', ends_on: '2026-10-24', workouts: [
      { ...workout('first-week', '2026-09-27'), workout_type: 'interval', display_name: 'Intervals', steps: [
        { type: 'warmup', duration_seconds: 600, target: { kind: 'rpe', rpe: 3 } },
        { type: 'repeat', repeat_count: 4, steps: [
          { type: 'work', distance_meters: 400, target: { kind: 'rpe', rpe: 8 } },
          { type: 'recovery', duration_seconds: 90, target: { kind: 'rpe', rpe: 2 } },
        ] },
        { type: 'cooldown', duration_seconds: 600, target: { kind: 'rpe', rpe: 3 } },
      ] },
      workout('second-week', '2026-10-04'),
      workout('third-week', '2026-10-11'),
    ] })])

    const schedule = app.get('.schedule-section')
    expect(schedule.find('[data-testid="schedule-workout-first-week"]').exists()).toBe(true)
    expect(schedule.find('[data-testid="schedule-workout-second-week"]').exists()).toBe(false)
    expect(schedule.find('[data-testid="schedule-workout-third-week"]').exists()).toBe(false)
    await app.get('[data-testid="workout-detail-first-week"]').trigger('click')
    const detail = app.get('[data-testid="workout-detail-modal"]')
    expect(detail.text()).toContain('暖身')
    expect(detail.text()).toContain('主課表')
    expect(detail.text()).toContain('緩和')
    expect(detail.text()).toContain('4 組')
    await app.get('[data-testid="workout-detail-close"]').trigger('click')
    await app.get('[data-testid="load-next-training-week"]').trigger('click')
    expect(schedule.find('[data-testid="schedule-workout-second-week"]').exists()).toBe(true)
    expect(schedule.find('[data-testid="schedule-workout-third-week"]').exists()).toBe(false)
  })
  it('shows scheduled workouts from the athlete-local today onward on Plan', async () => {
    vi.setSystemTime(new Date('2026-09-25T16:00:00Z'))
    const app = await render([plan('maintenance', { workouts: [
      workout('earlier-this-week', '2026-09-23'),
      workout('today', '2026-09-26'),
      workout('later-this-week', '2026-09-28'),
      workout('next-week', '2026-09-29'),
    ] })])

    const schedule = app.get('.schedule-section')
    expect(schedule.find('[data-testid="schedule-workout-earlier-this-week"]').exists()).toBe(false)
    expect(schedule.find('[data-testid="schedule-workout-today"]').exists()).toBe(true)
    expect(schedule.find('[data-testid="schedule-workout-later-this-week"]').exists()).toBe(true)
    expect(schedule.find('[data-testid="schedule-workout-next-week"]').exists()).toBe(false)
    expect(schedule.get('[data-testid="training-week-range"] span').text()).toBe('9/26–9/28')
  })
  it('does not show an expired plan week as an upcoming date range', async () => {
    const app = await render([plan('maintenance', { ends_on: '2026-09-19', workouts: [
      workout('past', '2026-09-18'),
    ] })])

    const schedule = app.get('.schedule-section')
    expect(schedule.find('[data-testid="schedule-workout-past"]').exists()).toBe(false)
    expect(schedule.find('[data-testid="training-week-range"]').exists()).toBe(false)
    expect(app.get('[data-testid="plan-summary"] > div').text()).toContain('尚未排定')
  })
  it.each([
    [null, 8, 'RPE 8 · 配速與心率資料不足'],
    [[150, 165], 8, 'RPE 8 · 心率 150-165 bpm'],
    [null, null, '配速與心率資料不足'],
  ])('renders heart-rate range %j with payload RPE %s without inventing effort', async (range, rpe, expected) => {
    const app = await render([plan('maintenance', { workouts: [{
      ...workout('heart-rate', '2026-09-27'),
      steps: [{ type: 'work', duration_seconds: 120, target: { kind: 'heart_rate', heart_rate_zone: 'threshold', heart_rate_range_bpm: range, rpe } }],
    }] })])
    await app.get('[data-testid="workout-detail-heart-rate"]').trigger('click')
    const detail = app.get('[data-testid="workout-detail-modal"]').text()
    expect(detail).toContain(expected)
    if (rpe == null) expect(detail).not.toContain('RPE')
    if (!range) expect(detail).not.toContain('bpm')
  })
  it.each(['completed', 'failed'])('observes long-running %s past the former cap, preserving workouts until terminal', async (terminal) => {
    let polls = 0
    let finished = false
    const app = await render([plan('base', { workouts: [workout('old-workout', '2026-09-27')] })], (url) => {
      if (url.endsWith('/regeneration-options')) return json(options)
      if (url.endsWith('/agent-runs/long-run')) {
        polls++
        finished = polls > 15
        return json({ id: run.run_id, status: finished ? terminal : 'processing', error_message: terminal === 'failed' ? '請稍後重新產生計畫' : null })
      }
      if (finished && url.endsWith('/training-plans')) return json([plan('maintenance', { workouts: [workout('replacement-workout', '2026-09-27')] })])
    })
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(34_000)
    await flushPromises()
    expect(app.text()).toContain('old-workout')
    expect(app.find('[data-testid="training-plan-regeneration-in-flight"]').exists()).toBe(true)
    await vi.advanceTimersByTimeAsync(180_000)
    await flushPromises()
    expect(app.find('[data-testid="training-plan-regeneration-in-flight"]').exists()).toBe(false)
    if (terminal === 'completed') {
      expect(app.text()).toContain('replacement-workout')
      expect(app.text()).not.toContain('old-workout')
    } else {
      expect(app.text()).toContain('old-workout')
      expect(app.text()).toContain('請稍後重新產生計畫')
      expect(app.get('[data-testid="training-plan-regeneration-confirm"]').attributes('disabled')).toBeUndefined()
    }
  })
  it('ignores an obsolete poll response when a new observation of the same run begins', async () => {
    let resolvePoll!: (response: Response) => void
    const app = await render([plan('base', { workouts: [workout('old-workout', '2026-09-27')] })], (url) => {
      if (url.endsWith('/regeneration-options')) return json(options)
      if (url.endsWith('/agent-runs/long-run')) return new Promise<Response>((resolve) => { resolvePoll = resolve })
    })
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    resolvePoll(json({ status: 'failed', error_message: 'obsolete failure' }))
    await flushPromises()
    expect(app.find('[data-testid="training-plan-regeneration-in-flight"]').exists()).toBe(true)
    expect(app.text()).not.toContain('obsolete failure')
    expect(app.text()).toContain('old-workout')
  })
  it('cancels timers on unmount and does not refresh for a late terminal response', async () => {
    let resolvePoll!: (response: Response) => void
    const app = await render([], (url) => {
      if (url.endsWith('/regeneration-options')) return json(options)
      if (url.endsWith('/agent-runs/long-run')) return new Promise<Response>((resolve) => { resolvePoll = resolve })
    })
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    app.unmount(); wrapper = undefined
    expect(vi.getTimerCount()).toBe(0)
    vi.mocked(fetch).mockClear()
    resolvePoll(json({ status: 'completed' }))
    await flushPromises()
    await vi.advanceTimersByTimeAsync(120_000)
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('does not resume observation from delayed sheet options after logout', async () => {
    let resolveOptions!: (response: Response) => void
    const app = await render([], (url) => url.endsWith('/regeneration-options') ? new Promise<Response>((resolve) => { resolveOptions = resolve }) : undefined)
    await app.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await app.get('.user-menu button').trigger('click')
    await flushPromises()
    resolveOptions(json(options))
    await flushPromises()
    vi.mocked(fetch).mockClear()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(fetch).not.toHaveBeenCalled()
  })
})
