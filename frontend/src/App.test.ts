import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGoogleSignInRedirectUrl, getLocalApiBaseUrl } from './api/client'
import App from './App.vue'

function okJson(data: unknown): Response {
  return {
    ok: true,
    json: () => Promise.resolve({ data }),
  } as Response
}

function garminConnectionData(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'conn-garmin-1',
    provider: 'garmin_connect',
    provider_display_name: 'Garmin Runner',
    status: 'active',
    credential_status: 'active',
    sync_status: 'idle',
    last_sync_completed_at: '2026-08-25T15:42:00Z',
    sync_warning: null,
    has_partial_failures: false,
    sync_summary: {
      resources: {
        activities: { fetched: 2, stored: 1, duplicates: 1, failed: 0, errors: [] },
        sleep: { fetched: 1, stored: 1, duplicates: 0, failed: 0, errors: [] },
        hrv: { fetched: 1, stored: 1, duplicates: 0, failed: 0, errors: [] },
        body_battery: { fetched: 1, stored: 1, duplicates: 0, failed: 0, errors: [] },
      },
    },
    ...overrides,
  }
}

function mockAuthenticatedToday({
  userId,
  todayData,
  recommendations = [],
}: {
  userId: string
  todayData: Record<string, unknown>
  recommendations?: Array<Record<string, unknown>>
}) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/v1/me')) {
      return Promise.resolve(
        okJson({
          id: userId,
          email: 'runner@example.com',
          display_name: 'Runner',
          capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
        }),
      )
    }
    if (url.endsWith('/api/v1/integrations/connections') && init?.method === 'GET') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [garminConnectionData()] }) } as Response)
    }
    if (url.includes('/api/v1/today')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: todayData }) } as Response)
    }
    if (url.endsWith('/api/v1/recommendations')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: recommendations }) } as Response)
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) } as Response)
  })
}

describe('Johnny product shell', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-26T12:00:00Z'))
    window.location.hash = ''
    document.body.innerHTML = ''
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      }),
    )
  })
  afterEach(() => { vi.useRealTimers() })

  it('renders the Today adjust decision card with factual evidence', () => {
    const wrapper = mount(App)
    const decisionCard = wrapper.get('[data-testid="today-decision-card"]')

    expect(decisionCard.text()).toContain('不太對勁')
    expect(wrapper.get('[data-testid="today-decision-action"]').text()).toContain('接受調整')
    expect(wrapper.findAll('[data-testid="today-evidence-chip"]').length).toBeGreaterThanOrEqual(3)
    expect(decisionCard.text()).toContain('近期訓練負荷偏高')
    expect(wrapper.text()).toContain('依照你過去的恢復模式')
  })

  it('shows weekly activity rhythm below the Today decision', () => {
    const wrapper = mount(App)

    expect(wrapper.get('[data-testid="weekly-activity"]').text()).toContain('本週活動')
    const plot = wrapper.get('[data-testid="weekly-activity-plot"]')
    expect(plot.classes()).toContain('weekly-activity__plot--spread')
    expect(plot.findAll('[data-testid="weekly-activity-column"]')).toHaveLength(7)
    expect(wrapper.findAll('[data-testid="weekly-activity-bar"]').length).toBe(7)
    expect(wrapper.findAll('[data-testid="weekly-activity-bar"]').map((bar) => bar.attributes('style'))).toEqual([
      '--bar-size: 33%;',
      '--bar-size: 0%;',
      '--bar-size: 44%;',
      '--bar-size: 56%;',
      '--bar-size: 0%;',
      '--bar-size: 28%;',
      '--bar-size: 100%;',
    ])
  })

  it('marks auth inputs with the readable light input treatment', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: { code: 'unauthorized', message: 'Authentication required', details: [] } }),
    } as Response)
    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    expect(wrapper.get('input[name="authEmail"]').classes()).toContain('auth-form__input')
    expect(wrapper.get('input[name="authPassword"]').classes()).toContain('auth-form__input')
  })

  it('fills the desktop Today context rail with plan and signal context', () => {
    const wrapper = mount(App)
    const rail = wrapper.get('.today-context-rail')

    expect(rail.text()).toContain('目標賽事')
    expect(rail.text()).toContain('目前階段')
    expect(rail.text()).toContain('Build')
    expect(rail.text()).toContain('Signal Coverage')
    expect(rail.text()).toContain('Johnny 已有')
    expect(rail.text()).toContain('Johnny 待決定')
  })

  it('shows Athlete baseline before the settings form', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="athlete"]').trigger('click')

    expect(wrapper.get('[data-testid="athlete-baseline"]').text()).toContain('Athlete Baseline')
    expect(wrapper.get('[data-testid="athlete-baseline"]').text()).toContain('週跑量')
    expect(wrapper.find('[data-testid="athlete-baseline"]').element.compareDocumentPosition(wrapper.get('[data-testid="athlete-settings-form"]').element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('uses a fixed timezone dropdown in Athlete settings', async () => {
    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('button[data-view="athlete"]').trigger('click')

    const timezone = wrapper.get('select[name="athleteTimezone"]')
    expect(wrapper.find('input[name="athleteTimezone"]').exists()).toBe(false)
    expect(timezone.text()).toContain('台北')
    expect(timezone.text()).toContain('UTC')
    await timezone.setValue('America/Los_Angeles')
    expect((timezone.element as HTMLSelectElement).value).toBe('America/Los_Angeles')
  })

  it('shows Data signal coverage before provider details', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="data"]').trigger('click')

    const signalCoverage = wrapper.get('[data-testid="signal-coverage"]')
    const providerDetails = wrapper.get('.provider-grid')

    expect(signalCoverage.text()).toContain('Johnny 已有')
    expect(signalCoverage.text()).toContain('Activity')
    expect(signalCoverage.text()).toContain('Athlete Baseline')
    expect(signalCoverage.findAll('.signal-pill')).toHaveLength(6)
    expect(signalCoverage.findAll('.signal-pill--covered').length).toBeGreaterThan(0)
    expect(signalCoverage.element.compareDocumentPosition(providerDetails.element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('derives signal coverage from canonical backend signals', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-signal-coverage',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-signal-coverage',
            scheduled_for: '2026-09-02',
            workout_type: 'easy_run',
            purpose: '維持有氧節奏',
            planned_distance_meters: 8000,
            status: 'planned',
          },
        ],
        recovery: {
          hrv_ms: 58,
          hrv_delta_percentage: 1,
          sleep_minutes: 480,
          sleep_debt_minutes: 0,
          body_battery_score: 72,
          stress_score: 35,
        },
        training_load: {
          acute_chronic_ratio: 1.6,
        },
        unavailable_signals: ['resting_heart_rate_baseline'],
      },
      recommendations: [],
    })
    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    await wrapper.get('button[data-view="data"]').trigger('click')

    const pills = wrapper.findAll('.signal-pill')
    const pillByLabel = (label: string) => {
      const pill = pills.find((item) => item.text().includes(label))
      expect(pill, `missing ${label}`).toBeTruthy()
      return pill!
    }
    expect(pillByLabel('Training Load').classes()).toContain('signal-pill--covered')
    expect(pillByLabel('Resting HR').classes()).not.toContain('signal-pill--covered')
  })

  it('renders rest guidance for a high-priority Today recommendation', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-rest-decision',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-rest',
            scheduled_for: '2026-09-02',
            workout_type: 'easy_run',
            purpose: '維持有氧節奏',
            planned_distance_meters: 8000,
            heart_rate_zone: 'Zone 2',
            status: 'planned',
          },
        ],
        recovery: {
          hrv_ms: 52,
          hrv_delta_percentage: -18,
        },
        unavailable_signals: [],
      },
      recommendations: [
        {
          id: 'rest-recommendation',
          priority: 'high',
          title: '今天先休息',
          rationale: '恢復訊號需要更多時間消化。',
          status: 'pending',
          evidence: [],
          proposed_action: { type: 'rest', reason: '今天先休息' },
        },
      ],
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    const decisionCard = wrapper.get('[data-testid="today-decision-card"]')
    expect(decisionCard.text()).toContain('先收一下')
    expect(decisionCard.text()).toContain('今天不要硬撐，跑鞋先放假。')
    expect(wrapper.get('[data-testid="today-decision-action"]').text()).toContain('記錄休息')
  })

  it('uses all recovery evidence for Today Decision even when dangerous evidence is not displayed', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-danger-load',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-danger-load',
            scheduled_for: '2026-09-02',
            workout_type: 'easy_run',
            purpose: '維持有氧節奏',
            planned_distance_meters: 8000,
            heart_rate_zone: 'Zone 2',
            status: 'planned',
          },
        ],
        recovery: {
          hrv_ms: 58,
          hrv_delta_percentage: 1,
          sleep_minutes: 480,
          sleep_debt_minutes: 0,
          body_battery_score: 72,
          stress_score: 35,
        },
        training_load: {
          acute_chronic_ratio: 1.6,
        },
        unavailable_signals: [],
      },
      recommendations: [],
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    const decisionCard = wrapper.get('[data-testid="today-decision-card"]')
    expect(decisionCard.text()).toContain('先收一下')
    expect(wrapper.get('[data-testid="today-decision-action"]').text()).toContain('記錄休息')
    expect(wrapper.findAll('[data-testid="today-evidence-chip"]')).toHaveLength(3)
  })

  it('routes the Today adjust action into Johnny recommendations', async () => {
    const wrapper = mount(App)

    await wrapper.get('[data-testid="today-decision-action"]').trigger('click')

    expect(wrapper.get('.top-nav__item--active').text()).toContain('Johnny')
    expect(wrapper.get('[data-testid="johnny-page"]').text()).toContain('待決定')
    expect(document.title).toBe('Johnny — Johnny')
  })

  it('shows the login screen when the session is missing or expired', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: { code: 'unauthorized', message: 'Authentication required', details: [] } }),
    } as Response)

    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()

    expect(wrapper.text()).toContain('登入 Johnny')
    expect(wrapper.text()).toContain('使用 Google 登入')
    expect(wrapper.text()).toContain('Email 登入')
    expect(wrapper.find('nav').exists()).toBe(false)
  })

  it('updates the route title when changing public views', async () => {
    const wrapper = mount(App)

    expect(document.title).toBe('今日 — Johnny')
    await wrapper.get('button[data-view="plan"]').trigger('click')
    expect(document.title).toBe('計畫 — Johnny')
    await wrapper.get('button[data-view="athlete"]').trigger('click')
    expect(document.title).toBe('運動員 — Johnny')
  })

  it('derives the local API host from the active frontend host', () => {
    expect(getLocalApiBaseUrl('http://localhost:5173/#today')).toBe('http://localhost:8000')
    expect(getLocalApiBaseUrl('http://127.0.0.1:5173/#today')).toBe('http://127.0.0.1:8000')
  })

  it('builds Google login as a backend redirect with the active frontend origin', () => {
    expect(getGoogleSignInRedirectUrl('#today', undefined, 'http://127.0.0.1:5175', 'Asia/Taipei')).toBe(
      'http://localhost:8000/api/v1/auth/google/start?callback_url=%23today&redirect=true&frontend_origin=http%3A%2F%2F127.0.0.1%3A5175&timezone=Asia%2FTaipei',
    )
  })

  it('lets a new user sign up with display name and enters the app without demo data', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve({
          ok: false,
          status: 401,
          json: () => Promise.resolve({ error: { code: 'unauthorized', message: 'Authentication required', details: [] } }),
        } as Response)
      }
      if (url.endsWith('/api/v1/auth/signup') && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                user: {
                  id: 'user-auth-1',
                  email: 'runner@example.com',
                  display_name: 'Johnny Chen',
                  capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
                },
              },
            }),
        } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      } as Response)
    })
    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    await wrapper.get('button[data-auth-mode="signup"]').trigger('click')
    await wrapper.get('input[name="displayName"]').setValue('Johnny Chen')
    await wrapper.get('input[name="authEmail"]').setValue('runner@example.com')
    await wrapper.get('input[name="authPassword"]').setValue('password123')
    await wrapper.get('input[name="authPasswordConfirm"]').setValue('password123')
    await wrapper.get('form[data-testid="auth-form"]').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/signup',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          display_name: 'Johnny Chen',
          email: 'runner@example.com',
          password: 'password123',
        }),
      }),
    )
    expect(wrapper.text()).toContain('Johnny Chen')
    expect(wrapper.text()).toContain('今天的訓練決策')
    expect(wrapper.text()).not.toContain('Sydney Marathon')
    expect(wrapper.text()).toContain('連接資料後')
  })

  it('shows the Chinese-first navigation and Today as the primary surface', () => {
    const wrapper = mount(App)

    expect(wrapper.get('nav').text()).toContain('今日')
    expect(wrapper.get('nav').text()).toContain('計畫')
    expect(wrapper.get('nav').text()).toContain('Johnny')
    expect(wrapper.get('nav').text()).toContain('運動員')
    expect(wrapper.get('nav').text()).toContain('資料')
    expect(wrapper.get('nav').text()).not.toContain('對話')
    expect(wrapper.text()).toContain('今天的訓練決策')
    expect(wrapper.text()).toContain('Sydney Marathon')
  })

  it('shows the start-line navigation and keeps conversation hidden', () => {
    const wrapper = mount(App)

    const navText = wrapper.get('nav').text()
    expect(navText).toContain('今日')
    expect(navText).toContain('計畫')
    expect(navText).toContain('Johnny')
    expect(navText).toContain('運動員')
    expect(navText).toContain('資料')
    expect(navText).not.toContain('訓練安排')
    expect(navText).not.toContain('Agent 收件匣')
    expect(navText).not.toContain('運動員設定')
    expect(navText).not.toContain('資料來源')
    expect(navText).not.toContain('對話')
  })

  it('edits athlete settings with structured validation, unit conversion, and canonical km save payload', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/athlete/profile') && init?.method === 'GET') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                timezone: 'Asia/Taipei',
                experience_level: null,
                current_weekly_mileage_km: 32.1868,
                preferred_training_days: ['tuesday', 'thursday', 'sunday'],
                preferred_long_run_day: 'sunday',
                max_runs_per_week: 3,
                max_hard_sessions_per_week: 2,
                unit_preference: 'metric',
                threshold_pace_seconds_per_km: 300,
                resting_heart_rate_bpm: 55,
                max_heart_rate_bpm: 190,
                training_preferences: { surface: 'trail' },
                injury_status: 'none',
                injury_areas: [],
                injury_notes: null,
              },
            }),
        } as Response)
      }
      if (url.endsWith('/api/v1/athlete/profile') && init?.method === 'PUT') {
        expect(JSON.parse(String(init.body))).toEqual({
          timezone: 'Asia/Taipei',
          experience_level: 'intermediate',
          current_weekly_mileage_km: 40.2335,
          preferred_training_days: ['tuesday', 'thursday', 'sunday'],
          preferred_long_run_day: 'sunday',
          max_runs_per_week: 3,
          max_hard_sessions_per_week: 0,
          unit_preference: 'imperial',
          threshold_pace_seconds_per_km: 315,
          resting_heart_rate_bpm: 56,
          max_heart_rate_bpm: 189,
          injury_status: 'current',
          injury_areas: ['other'],
          injury_notes: 'Left calf watch',
        })
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                timezone: 'Asia/Taipei',
                experience_level: 'intermediate',
                current_weekly_mileage_km: 40.2335,
                preferred_training_days: ['tuesday', 'thursday', 'sunday'],
                preferred_long_run_day: 'sunday',
                max_runs_per_week: 3,
                max_hard_sessions_per_week: 0,
                unit_preference: 'imperial',
                threshold_pace_seconds_per_km: 315,
                resting_heart_rate_bpm: 56,
                max_heart_rate_bpm: 189,
                training_preferences: { surface: 'trail' },
                injury_status: 'current',
                injury_areas: ['other'],
                injury_notes: 'Left calf watch',
              },
            }),
        } as Response)
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) } as Response)
    })
    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('button[data-view="athlete"]').trigger('click')

    expect(wrapper.text()).toContain('運動員')
    expect(wrapper.get('select[name="experienceLevel"]').text()).toContain('未設定')
    expect((wrapper.get('input[name="currentWeeklyMileage"]').element as HTMLInputElement).value).toBe('32.2')
    expect((wrapper.get('input[name="maxHardSessionsPerWeek"]').element as HTMLInputElement).value).toBe('2')
    expect((wrapper.get('input[name="thresholdPace"]').element as HTMLInputElement).value).toBe('5:00')
    expect((wrapper.get('input[name="restingHeartRate"]').element as HTMLInputElement).value).toBe('55')
    expect((wrapper.get('input[name="maxHeartRate"]').element as HTMLInputElement).value).toBe('190')

    await wrapper.get('input[name="maxHardSessionsPerWeek"]').setValue('')
    await wrapper.get('form[data-testid="athlete-settings-form"]').trigger('submit')

    expect(wrapper.get('input[name="maxHardSessionsPerWeek"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#athlete-max-hard-sessions-error').text()).toBe('質量課表必須介於 0 到 2')
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PUT')).toHaveLength(0)

    await wrapper.get('input[name="maxHardSessionsPerWeek"]').setValue('2')
    await wrapper.get('input[name="thresholdPace"]').setValue('5:99')
    await wrapper.get('form[data-testid="athlete-settings-form"]').trigger('submit')
    expect(wrapper.get('input[name="thresholdPace"]').attributes('aria-invalid')).toBe('true')
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PUT')).toHaveLength(0)

    await wrapper.get('select[name="unitPreference"]').setValue('imperial')
    expect((wrapper.get('input[name="currentWeeklyMileage"]').element as HTMLInputElement).value).toBe('20.0')

    await wrapper.get('select[name="experienceLevel"]').setValue('intermediate')
    await wrapper.get('input[name="currentWeeklyMileage"]').setValue('25.0')
    await wrapper.get('input[name="maxHardSessionsPerWeek"]').setValue('0')
    await wrapper.get('input[name="thresholdPace"]').setValue('5:15')
    await wrapper.get('input[name="restingHeartRate"]').setValue('56')
    await wrapper.get('input[name="maxHeartRate"]').setValue('50')
    await wrapper.get('form[data-testid="athlete-settings-form"]').trigger('submit')
    expect(wrapper.get('input[name="maxHeartRate"]').attributes('aria-invalid')).toBe('true')
    await wrapper.get('input[name="maxHeartRate"]').setValue('189')
    await wrapper.get('select[name="injuryStatus"]').setValue('current')
    await wrapper.get('input[name="injuryArea-other"]').setValue(true)
    await wrapper.get('form[data-testid="athlete-settings-form"]').trigger('submit')

    expect(wrapper.text()).toContain('其他傷痛部位需要補充說明')
    expect(wrapper.get('textarea[name="injuryNotes"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#athlete-injury-notes-error').text()).toBe('其他傷痛部位需要補充說明')
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PUT')).toHaveLength(0)

    await wrapper.get('textarea[name="injuryNotes"]').setValue('Left calf watch')
    await wrapper.get('form[data-testid="athlete-settings-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('運動員已更新')
  })

  it('clears saved heart-rate settings without requiring a replacement pair', async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/athlete/profile') && init?.method === 'GET') {
        return { ok: true, json: async () => ({ data: { timezone: 'Asia/Taipei', resting_heart_rate_bpm: 55, max_heart_rate_bpm: 190 } }) } as Response
      }
      if (url.endsWith('/api/v1/athlete/profile') && init?.method === 'PUT') {
        expect(JSON.parse(String(init.body))).toMatchObject({ resting_heart_rate_bpm: null, max_heart_rate_bpm: null })
        return { ok: true, json: async () => ({ data: { timezone: 'Asia/Taipei', resting_heart_rate_bpm: null, max_heart_rate_bpm: null } }) } as Response
      }
      return { ok: true, json: async () => ({ data: [] }) } as Response
    })
    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('button[data-view="athlete"]').trigger('click')
    await wrapper.get('input[name="restingHeartRate"]').setValue('')
    await wrapper.get('input[name="maxHeartRate"]').setValue('')
    await wrapper.get('form[data-testid="athlete-settings-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('運動員已更新')
  })

  it('does not show the connect-source empty block after a provider is connected', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve(
          okJson({
            id: 'user-auth-1',
            email: 'runner@example.com',
            display_name: 'Runner',
            capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
          }),
        )
      }
      if (url.endsWith('/api/v1/integrations/connections') && init?.method === 'GET') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [garminConnectionData()] }) } as Response)
      }
      if (url.endsWith('/api/v1/athlete/profile') && init?.method === 'GET') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { timezone: 'Asia/Taipei' } }) } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      } as Response)
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    expect(wrapper.text()).toContain('今天的訓練決策')
    expect(wrapper.text()).not.toContain('尚未有足夠資料建立今日建議')
  })

  it('does not leak frontend demo races or workouts into an authenticated empty account', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve(
          okJson({
            id: 'user-auth-empty',
            email: 'runner@example.com',
            display_name: 'Runner',
            capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
          }),
        )
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      } as Response)
    })

    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()

    expect(wrapper.text()).toContain('計畫')
    expect(wrapper.text()).not.toContain('Sydney Marathon')
    expect(wrapper.text()).not.toContain('Taipei Half Tune-up')
    expect(wrapper.text()).not.toContain('Tokyo Marathon Prep Race')
    expect(wrapper.text()).not.toContain('Easy Run')
    expect(wrapper.text()).not.toContain('8 km')
    expect(wrapper.text()).toContain('尚未設定目標')
    expect(wrapper.text()).toContain('目前沒有已排定課表')
  })

  it('keeps recommendation cards out of Today while showing a compact recommendation strip', () => {
    const wrapper = mount(App)

    expect(wrapper.find('[data-testid="recommendation-actions"]').exists()).toBe(false)
    const strip = wrapper.get('[data-testid="today-recommendation-strip"]')
    expect(strip.text()).toContain('Johnny 建議')
    expect(strip.text()).toContain('今天保持輕鬆，不做加速')
    expect(strip.text()).toContain('建議保守')
    expect(strip.text()).toContain('查看待決定建議')
  })

  it('orders Today as workout, recommendation, recovery, race, then inbox for narrow layouts', () => {
    const wrapper = mount(App)
    const section = wrapper.get('[data-testid="today-decision-flow"]')

    const order = section
      .findAll('[data-today-section]')
      .map((element) => element.attributes('data-today-section'))

    expect(order).toEqual(['workout', 'recommendation', 'recovery', 'race', 'inbox'])
  })

  it('shows no-recommendation and insufficient-data states in the Today recommendation strip', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-1',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-today',
            scheduled_for: '2026-09-02',
            workout_type: 'easy_run',
            purpose: '維持有氧節奏',
            planned_distance_meters: 8000,
            heart_rate_zone: 'Zone 2',
            status: 'planned',
          },
        ],
        recovery: {
          readiness_label: 'ready',
          hrv_ms: 52,
          hrv_delta_percentage: 2,
        },
        unavailable_signals: [],
      },
    })

    const noRecommendation = mount(App, { props: { requireAuth: true } })
    await flushPromises()
    const noRecommendationStrip = noRecommendation.get('[data-testid="today-recommendation-strip"]')
    expect(noRecommendationStrip.text()).toContain('目前可以照課表執行')
    expect(noRecommendationStrip.text()).toContain('查看 Johnny 建議')
    expect(noRecommendation.text()).not.toContain('readiness_label')

    mockAuthenticatedToday({
      userId: 'user-auth-2',
      todayData: {
        scheduled_workouts: [],
        recovery: {},
        unavailable_signals: ['sleep_debt_minutes'],
      },
    })

    const insufficientData = mount(App, { props: { requireAuth: true } })
    await flushPromises()
    const insufficientDataStrip = insufficientData.get('[data-testid="today-recommendation-strip"]')
    expect(insufficientDataStrip.text()).toContain('目前資料不足')
    expect(insufficientDataStrip.text()).not.toContain('連接資料')
  })

  it('shows structured workout steps from Today in a detail modal', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-structured-workout',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-interval',
            scheduled_for: '2026-09-02',
            workout_type: 'interval',
            purpose: '提升 10K 配速耐受',
            planned_distance_meters: 9000,
            planned_duration_minutes: 56,
            compact_summary: '15 分 warmup + 4 x (800m interval / 400m easy) + 10 分 cooldown',
            coach_note: '維持可控，不要把前兩組跑成測驗。',
            phase: 'build',
            status: 'planned',
            steps: [
              {
                type: 'warmup',
                duration_seconds: 900,
                target: { kind: 'pace', zone: 'easy', pace_range_seconds_per_km: [360, 390], confidence: 'high' },
              },
              {
                type: 'repeat',
                repeat_count: 4,
                steps: [
                  {
                    type: 'work',
                    distance_meters: 800,
                    target: { kind: 'pace', zone: 'interval', pace_range_seconds_per_km: [278, 286], rpe: 8, confidence: 'high' },
                  },
                  {
                    type: 'recovery',
                    distance_meters: 400,
                    target: { kind: 'pace', zone: 'easy', pace_range_seconds_per_km: [360, 390], confidence: 'high' },
                  },
                ],
              },
              {
                type: 'cooldown',
                duration_seconds: 600,
                target: { kind: 'rpe', rpe: 3 },
              },
            ],
          },
        ],
        recovery: {
          readiness_label: 'ready',
          hrv_ms: 52,
          hrv_delta_percentage: 2,
        },
        unavailable_signals: [],
      },
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    expect(wrapper.get('[data-today-section="workout"]').text()).toContain('主課表 4 組 × 0.8 km')
    await wrapper.get('button[data-testid="today-workout-detail"]').trigger('click')

    const modal = wrapper.get('[data-testid="workout-detail-modal"]')
    expect(modal.text()).toContain('4 組')
    expect(modal.text()).toContain('0.8 km')
    expect(modal.text()).toContain('間歇配速')
    expect(modal.text()).toContain('RPE 8')
    expect(modal.text()).toContain('0.4 km')
    expect(modal.text()).toContain('維持可控')
    expect(modal.get('#workout-detail-title').text()).toContain('間歇跑')
    expect(modal.get('[data-testid="workout-detail-steps"]').text()).toContain('暖身')
    expect(modal.get('[data-testid="workout-detail-coach-note"]').text()).toContain('維持可控')
  })

  it('keeps missing signals in recovery when Today has enough data and no recommendation', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-missing-signal',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-today',
            scheduled_for: '2026-09-02',
            workout_type: 'easy_run',
            purpose: '維持有氧節奏',
            planned_distance_meters: 8000,
            heart_rate_zone: 'Zone 2',
            status: 'planned',
          },
        ],
        recovery: {
          readiness_label: 'ready',
          hrv_ms: 52,
          hrv_delta_percentage: 2,
        },
        unavailable_signals: ['sleep_debt_minutes'],
      },
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    expect(wrapper.get('[data-testid="today-recommendation-strip"]').text()).toContain('Johnny 沒有新的待決定調整')
    expect(wrapper.get('[data-testid="today-recovery-card"]').text()).toContain('1 個訊號待補，包含睡眠資料')
  })

  it('shows formatted recovery metrics instead of Today facts when a data source is connected', async () => {
    mockAuthenticatedToday({
      userId: 'user-auth-recovery-metrics',
      todayData: {
        scheduled_workouts: [
          {
            id: 'backend-workout-today',
            scheduled_for: '2026-09-02',
            workout_type: 'easy_run',
            purpose: '維持有氧節奏',
            planned_distance_meters: 8000,
            heart_rate_zone: 'Zone 2',
            status: 'planned',
          },
        ],
        recovery: {
          user_id: 'user-auth-recovery-metrics',
          anchor_date: '2026-09-02',
          readiness_label: 'caution',
          hrv_ms: 52,
          hrv_delta_percentage: -18,
          sleep_minutes: 342,
          sleep_debt_minutes: 78,
          resting_heart_rate: 53,
          resting_heart_rate_delta_bpm: 6,
          body_battery_score: 62,
        },
        unavailable_signals: [],
      },
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()
    const card = wrapper.get('[data-testid="today-recovery-card"]')
    const chips = card.findAll('[data-testid="recovery-signal-chip"]')

    expect(chips).toHaveLength(3)
    expect(chips[0].text()).toContain('HRV')
    expect(chips[0].text()).toContain('52 ms')
    expect(chips[0].text()).toContain('低於基準 18%')
    expect(chips[1].text()).toContain('睡眠')
    expect(chips[1].text()).toContain('5 小時 42 分')
    expect(chips[1].text()).toContain('少 1 小時 18 分')
    expect(chips[2].text()).toContain('靜息心率')
    expect(chips[2].text()).toContain('53 bpm')
    expect(chips[2].text()).toContain('高於基準 6 bpm')
    expect(card.text()).not.toContain('user-auth-recovery-metrics')
    expect(card.text()).not.toContain('2026-09-02')
    expect(card.text()).not.toContain('readiness_label')
    expect(card.find('[data-testid="today-recovery-source-action"]').exists()).toBe(false)
    expect(card.text()).toContain('Garmin 已同步')
  })

  it('shows Today source action only when the connected source needs attention', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve(
          okJson({
            id: 'user-auth-source-attention',
            email: 'runner@example.com',
            display_name: 'Runner',
            capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
          }),
        )
      }
      if (url.endsWith('/api/v1/integrations/connections') && init?.method === 'GET') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [garminConnectionData({ credential_status: 'requires_reauth' })] }),
        } as Response)
      }
      if (url.includes('/api/v1/today')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { recovery: {}, unavailable_signals: [] } }) } as Response)
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) } as Response)
    })

    const wrapper = mount(App, { props: { requireAuth: true } })
    await flushPromises()

    expect(wrapper.get('[data-testid="today-recommendation-strip"]').text()).toContain('檢查資料')
    expect(wrapper.get('[data-testid="today-recovery-card"]').text()).toContain('檢查資料')
    await wrapper.get('[data-testid="today-recovery-source-action"]').trigger('click')
    expect(wrapper.text()).toContain('連接資料')
  })

  it('shows only accept and keep buttons on Agent Inbox recommendation cards', () => {
    const inbox = mount(App, { props: { initialView: 'johnny' } })
    const actions = inbox.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]')

    expect(actions.text()).toContain('接受調整')
    expect(actions.text()).toContain('保留課表')
    expect(actions.text()).not.toContain('編輯調整')
    expect(actions.text()).not.toContain('討論原因')
    expect(actions.findAll('button')).toHaveLength(2)
  })

  it('shows Johnny as recommendations first and hides public conversation', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="johnny"]').trigger('click')

    expect(wrapper.get('[data-testid="johnny-page"]').text()).toContain('待決定')
    expect(wrapper.get('[data-testid="johnny-page"]').text()).toContain('賽前 9 天降低長跑壓力')
    expect(wrapper.text()).not.toContain('送出')
    expect(wrapper.text()).not.toContain('今天原本有 8 km')
  })

  it('keeps Johnny weekly review visible when there are no recommendations', () => {
    const wrapper = mount(App, { props: { initialView: 'johnny', inboxItems: [] } })

    expect(wrapper.text()).toContain('目前沒有新的主動建議')
    expect(wrapper.get('[data-testid="johnny-weekly-review"]').text()).toContain('這週先守住連續性')
  })

  it('keeps Agent Inbox recommendation action geometry stable while accept is pending', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => undefined) as unknown as Promise<Response>)
    const wrapper = mount(App, { props: { initialView: 'johnny' } })

    await wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-action="accept"]').trigger('click')

    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('處理中')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('保留課表')
  })

  it('shows Today loading, error, and empty states with Chinese guidance', () => {
    expect(mount(App, { props: { todayState: 'loading' } }).text()).toContain('正在整理今天的訓練資料')
    expect(mount(App, { props: { todayState: 'error' } }).text()).toContain('今天資料載入失敗')
    expect(mount(App, { props: { todayState: 'empty' } }).text()).toContain('連接資料後')
  })

  it('keeps the Today recovery card compact with fixed action-oriented labels', () => {
    const wrapper = mount(App)
    const card = wrapper.get('[data-testid="today-recovery-card"]')

    expect(card.text()).toContain('建議保守')
    expect(card.find('[data-testid="today-recovery-summary"]').exists()).toBe(true)
    expect(card.findAll('[data-testid="recovery-signal-chip"]')).toHaveLength(3)
    expect(card.text()).toContain('2 個訊號待補，包含尚未連接靜息心率來源')
    expect(card.find('.evidence-list').exists()).toBe(false)
    expect(card.find('.unavailable-signals').exists()).toBe(false)
  })

  it('lays out Today with a wider workout card and contextual race card', () => {
    const wrapper = mount(App)

    expect(wrapper.get('.workout-card').classes()).toContain('today-card--primary')
    expect(wrapper.get('.race-card').classes()).toContain('today-card--context')
    expect(wrapper.get('.race-card').text()).toContain('今天的輕鬆跑是為了累積有氧基礎')
    expect(wrapper.get('.workout-card').find('button').exists()).toBe(false)
  })

  it('shows Plan as an inclusive training journey with schedule underneath', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="plan"]').trigger('click')

    const journey = wrapper.get('[data-testid="plan-training-journey"]')
    const stops = journey.findAll('[data-testid="plan-journey-stop"]')

    expect(journey.find('[data-testid="plan-journey-track"]').exists()).toBe(true)
    expect(journey.findAll('[data-testid="plan-journey-node"]')).toHaveLength(5)
    expect(stops).toHaveLength(5)
    expect(stops[0].classes()).toContain('plan-journey__stop--done')
    expect(stops[1].classes()).toContain('plan-journey__stop--current')
    expect(stops.slice(2).every((stop) => stop.classes().includes('plan-journey__stop--next'))).toBe(true)
    expect(journey.findAll('.plan-phase')).toHaveLength(0)
    expect(journey.text()).toContain('Build')
    expect(journey.text()).toContain('目前訓練週期')
    expect(wrapper.text()).toContain('接下來課表')
  })

  it('opens Plan with journey phases, race goals, and workout context', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="plan"]').trigger('click')

    expect(wrapper.text()).toContain('Training journey')
    expect(wrapper.text()).not.toContain('Race journey')
    expect(wrapper.get('[data-testid="plan-training-journey"]').text()).toContain('Build')
    expect(wrapper.text()).toContain('Taipei Half Tune-up')
    expect(wrapper.text()).toContain('週三')
    expect(wrapper.text()).toContain('Easy Run')
    expect(wrapper.text()).toContain('8 km')
  })

  it('renders only active plan phase labels from authenticated API metadata', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve(
          okJson({
            id: 'user-phase-timeline',
            email: 'runner@example.com',
            display_name: 'Runner',
            capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
          }),
        )
      }
      if (url.endsWith('/api/v1/training-plans')) {
        return Promise.resolve(
          okJson([
            {
              id: 'plan-superseded',
              user_id: 'user-phase-timeline',
              race_id: null,
              name: '舊版維持計畫',
              status: 'superseded',
              starts_on: '2026-08-01',
              ends_on: '2026-08-31',
              metadata: {
                phase_segments: [
                  {
                    phase: 'base',
                    starts_on: '2026-08-01',
                    ends_on: '2026-08-31',
                    focus: '舊版訓練內容不應顯示',
                  },
                ],
              },
              workouts: [],
            },
            {
              id: 'plan-maintenance',
              user_id: 'user-phase-timeline',
              race_id: null,
              name: '秋季維持計畫',
              status: 'active',
              starts_on: '2026-09-01',
              ends_on: '2026-09-28',
              metadata: {
                phase_segments: [
                  {
                    phase: 'maintenance',
                    starts_on: '2026-09-01',
                    ends_on: '2026-09-28',
                    focus: '維持穩定有氧節奏',
                  },
                ],
              },
              workouts: [],
            },
          ]),
        )
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) } as Response)
    })

    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()

    const timeline = wrapper.get('[data-testid="plan-phase-timeline"]')
    expect(timeline.text()).toContain('維持期')
    expect(timeline.text()).toContain('維持穩定有氧節奏')
    expect(timeline.text()).not.toContain('舊版訓練內容不應顯示')
  })

  it('does not render stale API phase metadata when no active plan exists', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve(
          okJson({
            id: 'user-no-active-plan',
            email: 'runner@example.com',
            display_name: 'Runner',
            capabilities: ['today', 'races', 'training-plans', 'recommendations', 'integrations'],
          }),
        )
      }
      if (url.endsWith('/api/v1/training-plans')) {
        return Promise.resolve(
          okJson([
            {
              id: 'plan-superseded',
              user_id: 'user-no-active-plan',
              race_id: null,
              name: '舊版維持計畫',
              status: 'superseded',
              starts_on: '2026-08-01',
              ends_on: '2026-08-31',
              metadata: {
                phase_segments: [
                  {
                    phase: 'base',
                    starts_on: '2026-08-01',
                    ends_on: '2026-08-31',
                    focus: '舊版 phase 不應顯示',
                  },
                ],
              },
              workouts: [],
            },
          ]),
        )
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) } as Response)
    })

    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()

    expect(wrapper.find('[data-testid="plan-phase-timeline"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('舊版 phase 不應顯示')
  })

  it('opens regeneration with Race Strategy selected by default and allows maintenance even when a race is available', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null },
            default_strategy: {
              race_id: 'race-taipei-half',
              plan_type: 'race',
              reason: 'primary_race',
              starts_on: '2026-09-25',
              plan_horizon_weeks: 12,
            },
            in_flight_run: null,
            run: null,
          }),
        )
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan' } })

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="training-plan-regeneration-sheet"]').text()).toContain('比賽策略')
    expect((wrapper.get('input[value="race"]').element as HTMLInputElement).checked).toBe(true)

    await wrapper.get('input[value="maintenance"]').setValue(true)

    expect((wrapper.get('input[value="maintenance"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('disables regeneration confirmation when the daily quota is exhausted and shows the next availability', async () => {
    const BrowserDateTimeFormat = Intl.DateTimeFormat
    function BrowserTimezoneDateTimeFormat(locales?: Intl.LocalesArgument, options?: Intl.DateTimeFormatOptions) {
      return new BrowserDateTimeFormat(locales, { ...options, timeZone: options?.timeZone ?? 'America/Los_Angeles' })
    }
    vi.stubGlobal(
      'Intl',
      {
        ...Intl,
        DateTimeFormat: BrowserTimezoneDateTimeFormat as unknown as typeof Intl.DateTimeFormat,
      } as typeof Intl,
    )
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/athlete/profile')) {
        return Promise.resolve(okJson({ timezone: 'Asia/Taipei' }))
      }
      if (url.endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: {
              quota_day: '2026-09-24',
              limit: 1,
              used: 1,
              remaining: 0,
              available: false,
              next_available_at: '2026-09-25T00:00:00+08:00',
            },
            default_strategy: {
              race_id: null,
              plan_type: 'maintenance',
              reason: 'no_future_race',
              starts_on: '2026-09-25',
              plan_horizon_weeks: 4,
            },
            in_flight_run: null,
            run: null,
          }),
        )
      }
      return Promise.resolve(okJson([]))
    })
    try {
      const wrapper = mount(App, { props: { initialView: 'plan' } })

      await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
      await flushPromises()

      expect(wrapper.get('[data-testid="training-plan-regeneration-sheet"]').text()).toContain('今日重新產生額度已用完')
      expect(wrapper.get('[data-testid="training-plan-regeneration-next-available"]').text()).toContain('2026年9月25日')
      expect(wrapper.get('[data-testid="training-plan-regeneration-confirm"]').attributes('disabled')).toBeDefined()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('disables regeneration confirmation when another regeneration is already in flight', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null },
            default_strategy: {
              race_id: 'race-taipei-half',
              plan_type: 'race',
              reason: 'primary_race',
              starts_on: '2026-09-25',
              plan_horizon_weeks: 12,
            },
            in_flight_run: { run_id: 'regeneration-run-1', status: 'processing', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
            run: null,
          }),
        )
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan' } })

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="training-plan-regeneration-confirm"]').attributes('disabled')).toBeDefined()
  })

  it('clears a failed in-flight regeneration and keeps the current workouts', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null },
            default_strategy: { race_id: 'race-taipei-half', plan_type: 'race', reason: 'primary_race', starts_on: '2026-09-25', plan_horizon_weeks: 12 },
            in_flight_run: { run_id: 'regeneration-run-1', status: 'processing', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
            run: null,
          }),
        )
      }
      if (url.endsWith('/api/v1/agent-runs/regeneration-run-1')) {
        return Promise.resolve(okJson({ id: 'regeneration-run-1', status: 'failed', workflow_name: 'training_plan_generation', finished_at: '2026-09-25T04:00:00Z', error_message: '計畫產生失敗' }))
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan' } })

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 2_100))
    await flushPromises()

    expect(wrapper.text()).toContain('計畫產生失敗')
    expect(wrapper.text()).toContain('Easy Run')
    expect(wrapper.find('[data-testid="training-plan-regeneration-in-flight"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="training-plan-regeneration-confirm"]').attributes('disabled')).toBeUndefined()
  })

  it('submits an explicitly selected future Race Strategy for regeneration', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null },
            default_strategy: {
              race_id: 'race-default',
              plan_type: 'race',
              reason: 'primary_race',
              starts_on: '2026-09-25',
              plan_horizon_weeks: 12,
            },
            in_flight_run: null,
            run: null,
          }),
        )
      }
      if (url.includes('/api/v1/races?')) {
        return Promise.resolve(
          okJson([
            { id: 'race-default', name: 'Default Marathon', race_date: '2026-11-01', distance_meters: 42195, target_finish_seconds: 14400, priority: 'primary', status: 'planned' },
            { id: 'race-alternate', name: 'Alternate Half', race_date: '2026-10-15', distance_meters: 21100, target_finish_seconds: 6300, priority: 'secondary', status: 'planned' },
          ]),
        )
      }
      if (url.endsWith('/api/v1/training-plans/regenerations') && init?.method === 'POST') {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 1, remaining: 0, available: false, next_available_at: '2026-09-25T00:00:00+08:00' },
            default_strategy: { race_id: 'race-default', plan_type: 'race', reason: 'primary_race', starts_on: '2026-09-25', plan_horizon_weeks: 12 },
            in_flight_run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
            run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
          }),
        )
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan' } })
    await flushPromises()

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await wrapper.get('select[name="regenerationRaceId"]').setValue('race-alternate')
    await wrapper.get('[data-testid="training-plan-regeneration-sheet"] form').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/training-plans/regenerations',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"race_id":"race-alternate"'),
      }),
    )
  })

  it('selects and submits a far-future race for regeneration even when it is outside the calendar window', async () => {
    let raceListCalls = 0
    const raceListUrls: string[] = []
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null },
            default_strategy: { race_id: 'race-far-future', plan_type: 'race', reason: 'primary_race', starts_on: '2026-09-25', plan_horizon_weeks: 12 },
            in_flight_run: null,
            run: null,
          }),
        )
      }
      if (url.includes('/api/v1/races?')) {
        raceListCalls += 1
        raceListUrls.push(url)
        return Promise.resolve(
          okJson(
            raceListCalls === 1
              ? [{ id: 'race-calendar', name: 'Calendar Race', race_date: '2026-11-01', distance_meters: 10000, target_finish_seconds: 2700, priority: 'secondary', status: 'planned' }]
              : [{ id: 'race-far-future', name: 'Far Future Marathon', race_date: '2028-09-25', distance_meters: 42195, target_finish_seconds: 14400, priority: 'primary', status: 'planned' }],
          ),
        )
      }
      if (url.endsWith('/api/v1/training-plans/regenerations') && init?.method === 'POST') {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 1, remaining: 0, available: false, next_available_at: '2026-09-25T00:00:00+08:00' },
            default_strategy: { race_id: 'race-far-future', plan_type: 'race', reason: 'primary_race', starts_on: '2026-09-25', plan_horizon_weeks: 12 },
            in_flight_run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
            run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
          }),
        )
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()

    expect(raceListUrls).toHaveLength(2)
    expect(raceListUrls[0]).toContain('race_date_to=')
    expect(raceListUrls[1]).not.toContain('race_date_to=')
    const raceSelect = wrapper.get('select[name="regenerationRaceId"]')
    expect(raceSelect.text()).toContain('Far Future Marathon')
    expect((raceSelect.element as HTMLSelectElement).value).toBe('race-far-future')

    await wrapper.get('[data-testid="training-plan-regeneration-sheet"] form').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/training-plans/regenerations',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"race_id":"race-far-future"'),
      }),
    )
  })

  it('refreshes the Active Projection after a completed regeneration run', async () => {
    let trainingPlansCalls = 0
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) {
        return Promise.resolve(okJson({ id: 'runner-1', email: 'runner@example.com', display_name: 'Runner', capabilities: ['training-plans'] }))
      }
      if (url.endsWith('/api/v1/training-plans') && init?.method === 'GET') {
        trainingPlansCalls += 1
        return Promise.resolve(
          okJson([
            {
              id: trainingPlansCalls === 1 ? 'plan-old' : 'plan-new',
              user_id: 'runner-1',
              race_id: null,
              name: trainingPlansCalls === 1 ? '舊計畫' : '新計畫',
              status: 'active',
              starts_on: '2026-09-25',
              ends_on: '2026-10-22',
              metadata: { phase_segments: [{ phase: trainingPlansCalls === 1 ? 'base' : 'maintenance', starts_on: '2026-09-25', ends_on: '2026-10-22', focus: trainingPlansCalls === 1 ? '舊的基礎訓練' : '新的維持訓練' }] },
              workouts: [{ id: trainingPlansCalls === 1 ? 'workout-old' : 'workout-new', scheduled_for: '2026-09-26', workout_type: 'easy_run', purpose: trainingPlansCalls === 1 ? 'Old Run' : 'New Run', status: 'planned' }],
            },
          ]),
        )
      }
      if (url.endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(okJson({ quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null }, default_strategy: { race_id: null, plan_type: 'maintenance', reason: 'no_future_race', starts_on: '2026-09-25', plan_horizon_weeks: 4 }, in_flight_run: null, run: null }))
      }
      if (url.endsWith('/api/v1/training-plans/regenerations') && init?.method === 'POST') {
        return Promise.resolve(okJson({ quota: { quota_day: '2026-09-24', limit: 1, used: 1, remaining: 0, available: false, next_available_at: '2026-09-25T00:00:00+08:00' }, default_strategy: { race_id: null, plan_type: 'maintenance', reason: 'no_future_race', starts_on: '2026-09-25', plan_horizon_weeks: 4 }, in_flight_run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' }, run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' } }))
      }
      if (url.endsWith('/api/v1/agent-runs/regeneration-run-1')) {
        return Promise.resolve(okJson({ id: 'regeneration-run-1', status: 'completed', workflow_name: 'training_plan_generation', finished_at: '2026-09-25T04:00:00Z', error_message: null }))
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()

    expect(wrapper.text()).toContain('Old Run')
    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="training-plan-regeneration-sheet"] form').trigger('submit')
    await new Promise((resolve) => setTimeout(resolve, 2_100))
    await flushPromises()

    expect(trainingPlansCalls).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).toContain('New Run')
    expect(wrapper.text()).toContain('新的維持訓練')
    expect(wrapper.find('[data-testid="training-plan-regeneration-in-flight"]').exists()).toBe(false)
  })

  it('closes the loading regeneration dialog with Escape and restores focus to its trigger', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/v1/training-plans/regeneration-options')) {
        return new Promise<Response>(() => undefined)
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { attachTo: document.body, props: { initialView: 'plan' } })
    const openButton = wrapper.get('[data-testid="open-plan-regeneration-sheet"]')
    ;(openButton.element as HTMLButtonElement).focus()

    await openButton.trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="training-plan-regeneration-loading"] [role="dialog"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(wrapper.find('[data-testid="training-plan-regeneration-loading"]').exists()).toBe(false)
    expect(document.activeElement).toBe(openButton.element)
  })

  it('keeps initial Shift+Tab within the loading regeneration dialog', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/v1/training-plans/regeneration-options')) {
        return new Promise<Response>(() => undefined)
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { attachTo: document.body, props: { initialView: 'plan' } })

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()

    const closeButton = wrapper.get('[data-testid="training-plan-regeneration-loading"] button')
    const dialog = wrapper.get('[data-testid="training-plan-regeneration-loading"] [role="dialog"]')
    const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true })
    dialog.element.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(closeButton.element)
  })

  it('starts regeneration, keeps the current plan visible, and shows its in-progress state', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/training-plans/regeneration-options')) {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 0, remaining: 1, available: true, next_available_at: null },
            default_strategy: {
              race_id: 'race-taipei-half',
              plan_type: 'race',
              reason: 'primary_race',
              starts_on: '2026-09-25',
              plan_horizon_weeks: 12,
            },
            in_flight_run: null,
            run: null,
          }),
        )
      }
      if (url.endsWith('/api/v1/training-plans/regenerations') && init?.method === 'POST') {
        return Promise.resolve(
          okJson({
            quota: { quota_day: '2026-09-24', limit: 1, used: 1, remaining: 0, available: false, next_available_at: '2026-09-25T00:00:00+08:00' },
            default_strategy: {
              race_id: 'race-taipei-half',
              plan_type: 'race',
              reason: 'primary_race',
              starts_on: '2026-09-25',
              plan_horizon_weeks: 12,
            },
            in_flight_run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
            run: { run_id: 'regeneration-run-1', status: 'queued', workflow_name: 'training_plan_generation', poll_url: '/api/v1/agent-runs/regeneration-run-1' },
          }),
        )
      }
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan' } })

    await wrapper.get('[data-testid="open-plan-regeneration-sheet"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="training-plan-regeneration-sheet"] form').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/training-plans/regenerations',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"race_id":"race-taipei-half"'),
      }),
    )
    expect(wrapper.text()).toContain('正在重新產生訓練計畫')
    expect(wrapper.text()).toContain('Easy Run')
    expect(wrapper.find('[data-testid="training-plan-regeneration-sheet"]').exists()).toBe(false)
  })

  it('lets the user add a race entry from a modal with priority, kilometers, and calendar date picking', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/races') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({
          name: 'Taipei Half',
          race_date: '2026-11-15',
          distance_meters: 21100,
          target_finish_seconds: 6300,
          priority: 'secondary',
        })
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                id: 'backend-created-race',
                name: 'Taipei Half',
                race_date: '2026-11-15',
                distance_meters: 21100,
                target_finish_seconds: 6300,
                priority: 'secondary',
                status: 'planned',
              },
            }),
        } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      } as Response)
    })
    const wrapper = mount(App, {
      props: {
        initialView: 'plan',
      },
    })

    expect(wrapper.find('form[data-testid="race-form"]').exists()).toBe(false)
    await wrapper.get('button[data-testid="open-race-goal-modal"]').trigger('click')
    await wrapper.get('input[name="raceName"]').setValue('Taipei Half')
    await wrapper.get('select[name="racePriority"]').setValue('secondary')
    await wrapper.get('input[name="raceDistanceKilometers"]').setValue('21.1')
    await wrapper.get('button[data-testid="date-picker-next-month"]').trigger('click')
    await wrapper.get('button[data-testid="date-picker-next-month"]').trigger('click')
    await wrapper.get('button[data-testid="date-picker-day-2026-11-15"]').trigger('click')
    await wrapper.get('input[name="targetFinishHours"]').setValue('1')
    await wrapper.get('input[name="targetFinishMinutes"]').setValue('45')
    await wrapper.get('form[data-testid="race-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Taipei Half')
    expect(wrapper.text()).toContain('21.1 km')
    expect(wrapper.text()).toContain('1:45:00')
    expect(wrapper.text()).toContain('賽事已新增')
    expect(wrapper.find('[data-testid="race-goal-modal"]').exists()).toBe(false)
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/races',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'Taipei Half',
          race_date: '2026-11-15',
          distance_meters: 21100,
          target_finish_seconds: 6300,
          priority: 'secondary',
        }),
      }),
    )
  })

  it('submits optional trail demands in canonical units', async () => {
    const wrapper = mount(App, { props: { initialView: 'plan' } })
    await wrapper.get('button[data-testid="open-race-goal-modal"]').trigger('click')
    await wrapper.get('input[name="raceName"]').setValue('山徑 40K')
    await wrapper.get('select[name="racePriority"]').setValue('primary')
    await wrapper.get('input[name="raceDistanceKilometers"]').setValue('40')
    await wrapper.get('input[name="raceDate"]').setValue('2026-11-15')
    await wrapper.get('input[name="ascentMeters"]').setValue('1800')
    await wrapper.get('input[name="descentMeters"]').setValue('1750')
    await wrapper.get('select[name="terrainDifficulty"]').setValue('technical')
    await wrapper.get('input[name="cutoffHours"]').setValue('9')
    await wrapper.get('select[name="goalIntent"]').setValue('complete')
    await wrapper.get('form[data-testid="race-form"]').trigger('submit')
    await flushPromises()
    const call = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith('/api/v1/races') && init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ distance_meters: 40000, ascent_meters: 1800, descent_meters: 1750, terrain_difficulty: 'technical', cutoff_seconds: 32400, goal_intent: 'complete' })
  })

  it.each([
    ['gap', '尚有準備落差'], ['unknown', '資料不足'], ['on_track', '達到規劃參考'],
  ])('shows %s preparation assessment beside its race', async (status, label) => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) return Promise.resolve(okJson({ id: 'runner', capabilities: ['today', 'races', 'training-plans'] }))
      if (url.endsWith('/api/v1/training-plans')) return Promise.resolve(okJson([{ id: 'plan-1', user_id: 'runner', race_id: 'race-1', name: '山徑計畫', status: 'active', starts_on: '2026-09-01', ends_on: '2026-11-15', metadata: {}, workouts: [], preparation_assessment: { status, factors: ['weekly_volume'], explanation_zh: '每週跑量尚需提升', policy_version: 'race-workload-v1' } }]))
      if (url.includes('/api/v1/races')) return Promise.resolve(okJson([{ id: 'race-1', name: '山徑 40K', race_date: '2026-11-15', distance_meters: 40000, priority: 'primary', status: 'planned', ascent_meters: 1400, descent_meters: 1300, terrain_difficulty: 'technical', cutoff_seconds: 32400, goal_intent: 'complete' }]))
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()
    const assessment = wrapper.get('[data-testid="preparation-assessment"]')
    expect(assessment.attributes('role')).toBe('status')
    expect(assessment.text()).toContain(label)
    expect(assessment.text()).toContain('每週跑量尚需提升')
    expect(wrapper.get('.plan-race-goal__course').text()).toContain('爬升 1400 公尺')
    expect(wrapper.get('.plan-race-goal__course').text()).toContain('技術地形')
  })

  it('shows saved course demands before a plan exists', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/me')) return Promise.resolve(okJson({ id: 'runner', capabilities: ['today', 'races', 'training-plans'] }))
      if (url.includes('/api/v1/races')) return Promise.resolve(okJson([{ id: 'race-1', name: '山徑 40K', race_date: '2026-11-15', distance_meters: 40000, priority: 'primary', status: 'planned', ascent_meters: 1400, terrain_difficulty: 'technical' }]))
      return Promise.resolve(okJson([]))
    })
    const wrapper = mount(App, { props: { initialView: 'plan', requireAuth: true } })
    await flushPromises()
    expect(wrapper.get('.plan-race-goal__course').text()).toContain('爬升 1400 公尺')
  })

  it('requires race priority and confirms before discarding dirty modal changes', async () => {
    const wrapper = mount(App, { attachTo: document.body, props: { initialView: 'plan' } })

    await wrapper.get('button[data-testid="open-race-goal-modal"]').trigger('click')
    await wrapper.get('input[name="raceName"]').setValue('Taipei Half')
    await wrapper.get('form[data-testid="race-form"]').trigger('submit')

    expect(wrapper.text()).toContain('請選擇目標優先度')
    expect(document.activeElement).toBe(wrapper.get('select[name="racePriority"]').element)
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)

    await wrapper.get('button[data-testid="race-modal-close"]').trigger('click')
    expect(wrapper.get('[data-testid="confirm-dialog"]').text()).toContain('放棄新增目標')
    await wrapper.get('button[data-testid="confirm-dialog-cancel"]').trigger('click')
    expect(wrapper.find('[data-testid="race-goal-modal"]').exists()).toBe(true)

    await wrapper.get('button[data-testid="race-modal-close"]').trigger('click')
    await wrapper.get('button[data-testid="confirm-dialog-confirm"]').trigger('click')
    expect(wrapper.find('[data-testid="race-goal-modal"]').exists()).toBe(false)
  })

  it('validates manually typed race dates on blur', async () => {
    const wrapper = mount(App, { props: { initialView: 'plan' } })

    await wrapper.get('button[data-testid="open-race-goal-modal"]').trigger('click')
    await wrapper.get('input[name="raceDate"]').setValue('2026/11/15')
    await wrapper.get('input[name="raceDate"]').trigger('blur')

    expect(wrapper.text()).toContain('請輸入 YYYY-MM-DD 格式的日期')
  })

  it('shows an empty workout state without losing the training arrangements surface', () => {
    const wrapper = mount(App, {
      props: {
        initialView: 'plan',
        workouts: [],
      },
    })

    expect(wrapper.text()).toContain('計畫')
    expect(wrapper.text()).toContain('目前沒有已排定課表')
  })

  it('opens data sources and connects Garmin through experimental login without provider account id', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/integrations/garmin/connect') && init?.method === 'POST') {
        return Promise.resolve(okJson(garminConnectionData()))
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      } as Response)
    })
    const wrapper = mount(App)

    await wrapper.get('button[data-view="data"]').trigger('click')

    expect(wrapper.text()).toContain('資料連接')
    expect(wrapper.text()).toContain('Garmin Connect experimental login')
    expect(wrapper.text()).not.toContain('Apple Health')
    expect(wrapper.text()).not.toContain('Strava')
    expect(wrapper.find('input[name="providerAccountId"]').exists()).toBe(false)
    expect(wrapper.find('form[data-testid="provider-form"]').exists()).toBe(false)

    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="select-provider"]').trigger('click')
    await wrapper.get('input[name="garminEmail"]').setValue('runner@example.com')
    const password = wrapper.get('input[name="garminPassword"]')
    expect(password.attributes('type')).toBe('password')
    expect(password.attributes('autocomplete')).toBe('off')
    await password.setValue('garmin-password')
    await wrapper.get('select[name="garminRegion"]').setValue('china')
    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Garmin Runner 已連接')
    expect(wrapper.find('form[data-testid="provider-form"]').exists()).toBe(false)
    const garminCard = wrapper.get('[data-testid="provider-card-garmin_connect"]')
    expect(garminCard.text()).toContain('Garmin Runner')
    expect(garminCard.text()).toContain('已連接')
    expect(garminCard.text()).toContain('上次同步')
    expect(garminCard.text()).toContain('活動：取得 2，新增 1，重複 1')
    expect(garminCard.text()).toContain('Body Battery：取得 1，新增 1')
    expect(garminCard.text()).toContain('手動同步')
    expect(garminCard.text()).toContain('中斷連接')
    expect(wrapper.text()).not.toContain('garmin-password')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/integrations/garmin/connect',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          email: 'runner@example.com',
          password: 'garmin-password',
          region: 'china',
        }),
      }),
    )
  })

  it('keeps Garmin validation in the app instead of submitting empty credentials', async () => {
    const wrapper = mount(App, {
      props: {
        initialView: 'data',
      },
    })

    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="select-provider"]').trigger('click')
    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')

    expect(wrapper.text()).toContain('請輸入 Garmin 電子郵件')
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('hydrates an existing Garmin connection into the provider card on page load', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/athlete/profile') && init?.method === 'GET') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { timezone: 'America/Los_Angeles' } }) } as Response)
      }
      if (url.endsWith('/api/v1/integrations/connections') && init?.method === 'GET') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [garminConnectionData()] }) } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      } as Response)
    })

    const wrapper = mount(App, { props: { initialView: 'data' } })
    await flushPromises()

    const garminCard = wrapper.get('[data-testid="provider-card-garmin_connect"]')
    expect(garminCard.text()).toContain('Garmin Runner')
    expect(garminCard.text()).toContain('已連接')
    expect(garminCard.text()).toContain('上次同步')
    expect(garminCard.text()).toContain('08:42')
    expect(garminCard.text()).toContain('活動：取得 2，新增 1，重複 1')
    expect(garminCard.text()).toContain('手動同步')
  })

  it('runs manual Garmin sync from the provider card and renders partial failure details', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/integrations/garmin/connect') && init?.method === 'POST') {
        return Promise.resolve(okJson(garminConnectionData()))
      }
      if (url.endsWith('/api/v1/integrations/connections/conn-garmin-1/sync') && init?.method === 'POST') {
        return Promise.resolve(
          okJson(
            garminConnectionData({
              has_partial_failures: true,
              sync_warning: 'HRV 暫時無法同步',
              sync_summary: {
                resources: {
                  activities: { fetched: 4, stored: 2, duplicates: 2, failed: 0, errors: [] },
                  hrv: { fetched: 0, stored: 0, duplicates: 0, failed: 1, errors: ['HRV 暫時無法同步'] },
                  body_battery: { fetched: 1, stored: 1, duplicates: 0, failed: 0, errors: [] },
                },
              },
            }),
          ),
        )
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      } as Response)
    })
    const wrapper = mount(App, { props: { initialView: 'data' } })

    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="select-provider"]').trigger('click')
    await wrapper.get('input[name="garminEmail"]').setValue('runner@example.com')
    await wrapper.get('input[name="garminPassword"]').setValue('garmin-password')
    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="manual-sync"]').trigger('click')
    await flushPromises()

    const garminCard = wrapper.get('[data-testid="provider-card-garmin_connect"]')
    expect(garminCard.text()).toContain('部分資料同步失敗')
    expect(garminCard.text()).toContain('HRV 暫時無法同步')
    expect(garminCard.text()).toContain('活動：取得 4，新增 2，重複 2')
    expect(garminCard.text()).toContain('HRV：取得 0，新增 0，失敗 1')
    expect(wrapper.text()).toContain('Garmin 手動同步完成')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/integrations/connections/conn-garmin-1/sync',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(wrapper.text()).not.toContain('garmin-password')
  })

  it('shows Garmin partial failures and reauth-needed state without echoing the password', async () => {
    vi.mocked(fetch).mockResolvedValue(
      okJson(
        garminConnectionData({
          id: 'conn-garmin-reauth',
          credential_status: 'requires_reauth',
          sync_status: 'failed',
          sync_warning: 'Garmin connection requires reauth',
          has_partial_failures: true,
          sync_summary: {
            resources: {
              activities: { fetched: 1, stored: 1, duplicates: 0, failed: 0, errors: [] },
              body_battery: { fetched: 0, stored: 0, duplicates: 0, failed: 1, errors: ['Garmin connection requires reauth'] },
            },
          },
        }),
      ),
    )
    const wrapper = mount(App, { props: { initialView: 'data' } })

    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="select-provider"]').trigger('click')
    await wrapper.get('input[name="garminEmail"]').setValue('runner@example.com')
    await wrapper.get('input[name="garminPassword"]').setValue('garmin-password')
    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('已連接，需要重新登入')
    expect(wrapper.text()).toContain('部分資料同步失敗')
    expect(wrapper.get('[data-testid="provider-card-garmin_connect"]').text()).toContain('重新連接')
    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="select-provider"]').trigger('click')
    expect(wrapper.text()).toContain('請重新輸入 Garmin 電子郵件與密碼後連接。')
    expect(wrapper.text()).toContain('Body Battery：取得 0，新增 0，失敗 1')
    expect(wrapper.text()).not.toContain('garmin-password')
  })

  it('disconnects Garmin from the provider card while preserving imported-data copy', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/integrations/garmin/connect') && init?.method === 'POST') {
        return Promise.resolve(okJson(garminConnectionData()))
      }
      if (url.endsWith('/api/v1/integrations/connections/conn-garmin-1') && init?.method === 'DELETE') {
        return Promise.resolve(
          okJson(
            garminConnectionData({
              status: 'disconnected',
              credential_status: 'deleted',
              sync_status: 'idle',
            }),
          ),
        )
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      } as Response)
    })
    const wrapper = mount(App, { props: { initialView: 'data' } })

    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="select-provider"]').trigger('click')
    await wrapper.get('input[name="garminEmail"]').setValue('runner@example.com')
    await wrapper.get('input[name="garminPassword"]').setValue('garmin-password')
    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="disconnect"]').trigger('click')

    expect(wrapper.get('[data-testid="provider-card-garmin_connect"]').text()).toContain('歷史匯入資料會保留')

    await wrapper.get('[data-testid="provider-card-garmin_connect"] button[data-action="confirm-disconnect"]').trigger('click')
    await flushPromises()

    const garminCard = wrapper.get('[data-testid="provider-card-garmin_connect"]')
    expect(garminCard.text()).toContain('已中斷')
    expect(garminCard.text()).toContain('重新連接')
    expect(wrapper.text()).toContain('Garmin 已中斷連接；歷史匯入資料會保留。')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/integrations/connections/conn-garmin-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('renders Conversation as a support surface with threads, evidence, and proposed actions', () => {
    const wrapper = mount(App, { props: { initialView: 'conversation' } })

    expect(wrapper.text()).toContain('對話')
    expect(wrapper.text()).toContain('賽前恢復調整')
    expect(wrapper.text()).toContain('Johnny 回覆')
    expect(wrapper.text()).toContain('Garmin · HRV')
    expect(wrapper.text()).toContain('改成 8 km Easy Run')
    expect(wrapper.get('[data-testid="conversation-proposed-action"]').text()).toContain('接受調整')
    expect(wrapper.get('[data-testid="conversation-form"]').attributes('novalidate')).toBeDefined()
  })

  it('switches Conversation threads without losing the compact composer', async () => {
    const wrapper = mount(App, { props: { initialView: 'conversation' } })

    await wrapper.get('button[data-thread-id="thread-long-run"]').trigger('click')

    expect(wrapper.text()).toContain('週末長跑安排')
    expect(wrapper.text()).toContain('18 km Long Run')
    expect(wrapper.find('textarea[name="conversationMessage"]').exists()).toBe(true)
  })

  it('shows Conversation loading, error, and empty states with Chinese guidance', () => {
    expect(mount(App, { props: { initialView: 'conversation', conversationState: 'loading' } }).text()).toContain('正在整理對話脈絡')
    expect(mount(App, { props: { initialView: 'conversation', conversationState: 'error' } }).text()).toContain('對話載入失敗')
    expect(mount(App, { props: { initialView: 'conversation', conversationState: 'empty' } }).text()).toContain('還沒有對話紀錄')
  })

  it('keeps Conversation validation in the app and does not submit whitespace', async () => {
    const wrapper = mount(App, { props: { initialView: 'conversation' } })

    await wrapper.get('textarea[name="conversationMessage"]').setValue('   ')
    await wrapper.get('[data-testid="conversation-form"]').trigger('submit')

    expect(wrapper.text()).toContain('請輸入想問 Johnny 的問題')
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('does not submit Conversation text while Traditional Chinese IME composition is active', async () => {
    const wrapper = mount(App, { props: { initialView: 'conversation' } })
    const textarea = wrapper.get('textarea[name="conversationMessage"]')

    await textarea.setValue('今天要不要改課表')
    await textarea.trigger('compositionstart')
    await textarea.trigger('keydown', { key: 'Enter' })

    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    expect((textarea.element as HTMLTextAreaElement).value).toBe('今天要不要改課表')
  })

  it('submits a non-empty Conversation message and renders the returned run reference', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: { run_ref: 'conversation-run-test', message: { content: '今天要不要改課表' } } }),
    } as Response)
    const wrapper = mount(App, { props: { initialView: 'conversation' } })

    await wrapper.get('textarea[name="conversationMessage"]').setValue('今天要不要改課表')
    await wrapper.get('[data-testid="conversation-form"]').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/conversations/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '今天要不要改課表' }),
      }),
    )
    expect(wrapper.text()).toContain('conversation-run-test')
  })

  it('hydrates Today, Calendar, and Agent Inbox from backend GET responses when available', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/v1/today')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                next_race: {
                  name: 'Backend Half Marathon',
                  race_date: '2026-10-18',
                  distance_meters: 21097,
                },
                scheduled_workouts: [
                  {
                    id: 'backend-workout-today',
                    scheduled_for: '2026-08-22',
                    workout_type: 'easy_run',
                    purpose: 'Backend aerobic check-in',
                    planned_distance_meters: 10000,
                    planned_duration_minutes: 55,
                    heart_rate_zone: 'Z2',
                    status: 'planned',
                  },
                ],
                recovery: {
                  readiness_label: 'caution',
                  hrv_status: 'low',
                },
                unavailable_signals: ['missing resting heart rate'],
              },
            }),
        } as Response)
      }
      if (url.includes('/api/v1/recommendations') && init?.method !== 'POST') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: [
                {
                  id: 'backend-rec-1',
                  priority: 'high',
                  title: 'Backend says keep it easy',
                  rationale: 'Backend recommendation rationale.',
                  status: 'pending',
                  evidence: [{ source: 'backend', metric: 'hrv', value: 'low', summary: 'Backend HRV low' }],
                  proposed_action: { type: 'no_plan_change', reason: 'No change in backend smoke.' },
                },
              ],
            }),
        } as Response)
      }
      if (url.includes('/api/v1/training-plans')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: [
                {
                  id: 'backend-plan-1',
                  workouts: [
                    {
                      id: 'backend-workout-calendar',
                      scheduled_for: '2026-08-24',
                      workout_type: 'tempo',
                      purpose: 'Backend tempo',
                      planned_duration_minutes: 45,
                      status: 'planned',
                    },
                  ],
                },
              ],
            }),
        } as Response)
      }
      if (url.includes('/api/v1/races') && init?.method !== 'POST') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: [
                {
                  id: 'backend-race-calendar',
                  name: 'Backend Calendar 10K',
                  race_date: '2026-11-08',
                  distance_meters: 10000,
                  target_finish_seconds: 3000,
                  priority: 'tune_up',
                  status: 'planned',
                },
              ],
            }),
        } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      } as Response)
    })
    const wrapper = mount(App, { props: { initialView: 'today' } })
    await flushPromises()

    expect(wrapper.text()).toContain('Backend Half Marathon')
    expect(wrapper.text()).toContain('10 km')

    await wrapper.get('button[data-view="plan"]').trigger('click')
    expect(wrapper.text()).toContain('Backend Calendar 10K')
    expect(wrapper.text()).toContain('50:00')

    await wrapper.get('button[data-view="johnny"]').trigger('click')
    await wrapper.get('[data-testid="inbox-card-backend-rec-1"] [data-action="accept"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/recommendations/backend-rec-1/accept',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('renders Agent Inbox as a pending decision queue with quieter history', () => {
    const wrapper = mount(App, { props: { initialView: 'johnny' } })

    expect(wrapper.text()).toContain('Johnny 建議')
    expect(wrapper.text()).toContain('高優先')
    expect(wrapper.text()).toContain('今天 21:00 前決定')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"]').text()).toContain('待決定')
    expect(wrapper.get('[data-testid="inbox-history"]').text()).toContain('已接受')
    expect(wrapper.get('[data-testid="inbox-history"]').text()).toContain('已套用')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('保留課表')
  })
})
