import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getGoogleSignInRedirectUrl, getLocalApiBaseUrl } from './api/client'
import App from './App.vue'

function okJson(data: Record<string, unknown>): Response {
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

describe('Johnny product shell', () => {
  beforeEach(() => {
    window.location.hash = ''
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      }),
    )
  })

  it('shows the login screen when the session is missing or expired', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: { code: 'unauthorized', message: 'Authentication required', details: [] } }),
    } as Response)

    const wrapper = mount(App, { props: { initialView: 'calendar', requireAuth: true } })
    await flushPromises()

    expect(wrapper.text()).toContain('登入 Johnny')
    expect(wrapper.text()).toContain('使用 Google 登入')
    expect(wrapper.text()).toContain('Email 登入')
    expect(wrapper.find('nav').exists()).toBe(false)
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
    expect(wrapper.text()).toContain('連接資料來源後')
  })

  it('shows the Chinese-first navigation and Today as the primary surface', () => {
    const wrapper = mount(App)

    expect(wrapper.get('nav').text()).toContain('今日')
    expect(wrapper.get('nav').text()).toContain('訓練安排')
    expect(wrapper.get('nav').text()).toContain('Agent 收件匣')
    expect(wrapper.get('nav').text()).toContain('資料來源')
    expect(wrapper.get('nav').text()).not.toContain('對話')
    expect(wrapper.text()).toContain('今天的訓練決策')
    expect(wrapper.text()).toContain('Sydney Marathon')
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

  it('keeps recommendation cards out of Today and routes recommendation decisions to Agent Inbox', () => {
    const wrapper = mount(App)

    expect(wrapper.find('[data-testid="recommendation-actions"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('主動建議會集中在 Agent 收件匣')
  })

  it('shows only accept and keep buttons on Agent Inbox recommendation cards', () => {
    const inbox = mount(App, { props: { initialView: 'inbox' } })
    const actions = inbox.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]')

    expect(actions.text()).toContain('接受調整')
    expect(actions.text()).toContain('保留課表')
    expect(actions.text()).not.toContain('編輯調整')
    expect(actions.text()).not.toContain('討論原因')
    expect(actions.findAll('button')).toHaveLength(2)
  })

  it('keeps Agent Inbox recommendation action geometry stable while accept is pending', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => undefined) as unknown as Promise<Response>)
    const wrapper = mount(App, { props: { initialView: 'inbox' } })

    await wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-action="accept"]').trigger('click')

    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('處理中')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('保留課表')
  })

  it('shows Today loading, error, and empty states with Chinese guidance', () => {
    expect(mount(App, { props: { todayState: 'loading' } }).text()).toContain('正在整理今天的訓練資料')
    expect(mount(App, { props: { todayState: 'error' } }).text()).toContain('今天資料載入失敗')
    expect(mount(App, { props: { todayState: 'empty' } }).text()).toContain('連接資料來源後')
  })

  it('keeps the Today recovery card compact so it balances the top row', () => {
    const wrapper = mount(App)
    const card = wrapper.get('[data-testid="today-recovery-card"]')

    expect(card.find('[data-testid="today-recovery-summary"]').exists()).toBe(true)
    expect(card.findAll('[data-testid="recovery-signal-chip"]')).toHaveLength(3)
    expect(card.find('.evidence-list').exists()).toBe(false)
    expect(card.find('.unavailable-signals').exists()).toBe(false)
  })

  it('stretches Today top-row cards to equal height regardless of content length', () => {
    const wrapper = mount(App)
    const topCards = [
      wrapper.get('.race-card'),
      wrapper.get('.workout-card'),
      wrapper.get('[data-testid="today-recovery-card"]'),
    ]

    for (const card of topCards) {
      expect(card.classes()).toContain('today-top-card')
    }
  })

  it('opens training arrangements as a six-month race calendar with workout context', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="calendar"]').trigger('click')

    expect(wrapper.text()).toContain('訓練安排')
    expect(wrapper.text()).toContain('未來六個月')
    expect(wrapper.findAll('[data-testid="race-month"]').length).toBe(6)
    expect(wrapper.text()).toContain('Sydney Marathon')
    expect(wrapper.text()).toContain('週三')
    expect(wrapper.text()).toContain('Easy Run')
    expect(wrapper.text()).toContain('8 km')
  })

  it('lets the user add a race entry to the six-month calendar', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/v1/races') && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: {
                id: 'backend-created-race',
                name: 'Taipei Half',
                race_date: '2026-11-15',
                distance_meters: 21097,
                target_finish_seconds: 6300,
                priority: 'primary',
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
        initialView: 'calendar',
      },
    })

    await wrapper.get('input[name="raceName"]').setValue('Taipei Half')
    await wrapper.get('input[name="raceDate"]').setValue('2026-11-15')
    await wrapper.get('input[name="raceDistance"]').setValue('Half Marathon')
    await wrapper.get('input[name="raceGoal"]').setValue('Sub 1:45')
    await wrapper.get('form[data-testid="race-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Taipei Half')
    expect(wrapper.text()).toContain('Half Marathon')
    expect(wrapper.text()).toContain('Sub 1:45')
    expect(wrapper.text()).toContain('賽事已加入訓練安排')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/races',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'Taipei Half',
          race_date: '2026-11-15',
          distance_meters: 21097,
          target_finish_seconds: 6300,
          priority: 'primary',
          status: 'planned',
        }),
      }),
    )
  })

  it('shows an empty workout state without losing the training arrangements surface', () => {
    const wrapper = mount(App, {
      props: {
        initialView: 'calendar',
        workouts: [],
      },
    })

    expect(wrapper.text()).toContain('訓練安排')
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

    await wrapper.get('button[data-view="sources"]').trigger('click')

    expect(wrapper.text()).toContain('資料來源')
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
        initialView: 'sources',
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

    const wrapper = mount(App, { props: { initialView: 'sources' } })
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
    const wrapper = mount(App, { props: { initialView: 'sources' } })

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
    const wrapper = mount(App, { props: { initialView: 'sources' } })

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
    const wrapper = mount(App, { props: { initialView: 'sources' } })

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

    await wrapper.get('button[data-view="calendar"]').trigger('click')
    expect(wrapper.text()).toContain('Backend Calendar 10K')
    expect(wrapper.text()).toContain('Sub 50:00')

    await wrapper.get('button[data-view="inbox"]').trigger('click')
    await wrapper.get('[data-testid="inbox-card-backend-rec-1"] [data-action="accept"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/recommendations/backend-rec-1/accept',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('renders Agent Inbox as a pending decision queue with quieter history', () => {
    const wrapper = mount(App, { props: { initialView: 'inbox' } })

    expect(wrapper.text()).toContain('Agent 收件匣')
    expect(wrapper.text()).toContain('高優先')
    expect(wrapper.text()).toContain('今天 21:00 前決定')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"]').text()).toContain('待決定')
    expect(wrapper.get('[data-testid="inbox-history"]').text()).toContain('已接受')
    expect(wrapper.get('[data-testid="inbox-history"]').text()).toContain('已套用')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('保留課表')
  })
})
