import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'

describe('Johnny product shell', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      }),
    )
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

  it('opens data sources and submits a provider connection request', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="sources"]').trigger('click')

    expect(wrapper.text()).toContain('資料來源')
    expect(wrapper.text()).toContain('Garmin')
    expect(wrapper.text()).toContain('Apple Health')
    expect(wrapper.text()).toContain('Strava')
    expect(wrapper.text()).toContain('Johnny 只保存 credential reference')

    await wrapper.get('input[name="providerAccountId"]').setValue('runner-001')
    await wrapper.get('input[name="credentialSecretRef"]').setValue('secret/garmin/runner-001')
    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Garmin 連接已送出')
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/integrations/connections',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          provider: 'garmin',
          provider_account_id: 'runner-001',
          credential_secret_ref: 'secret/garmin/runner-001',
        }),
      }),
    )
  })

  it('keeps provider validation in the app instead of submitting an empty account id', async () => {
    const wrapper = mount(App, {
      props: {
        initialView: 'sources',
      },
    })

    await wrapper.get('form[data-testid="provider-form"]').trigger('submit')

    expect(wrapper.text()).toContain('請輸入 Provider account ID')
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
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
