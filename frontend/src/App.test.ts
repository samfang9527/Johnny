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
    expect(wrapper.get('nav').text()).toContain('課表')
    expect(wrapper.get('nav').text()).toContain('Agent 收件匣')
    expect(wrapper.get('nav').text()).toContain('對話')
    expect(wrapper.get('nav').text()).toContain('資料來源')
    expect(wrapper.text()).toContain('今天的訓練決策')
    expect(wrapper.text()).toContain('Sydney Marathon')
  })

  it('renders the recommendation decision strip with stable Chinese action labels', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toContain('訊號')
    expect(wrapper.text()).toContain('證據')
    expect(wrapper.text()).toContain('建議')
    expect(wrapper.text()).toContain('決定')
    expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('接受調整')
    expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('編輯調整')
    expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('保留原課表')
    expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('討論原因')
  })

  it('keeps stable Chinese recommendation action labels across Today, Conversation, and Agent Inbox', () => {
    const today = mount(App)
    const conversation = mount(App, { props: { initialView: 'conversation' } })
    const inbox = mount(App, { props: { initialView: 'inbox' } })

    for (const wrapper of [today, conversation, inbox]) {
      expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('接受調整')
      expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('編輯調整')
      expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('保留原課表')
      expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('討論原因')
    }
  })

  it('keeps recommendation action geometry stable while accept is pending', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => undefined) as unknown as Promise<Response>)
    const wrapper = mount(App)

    await wrapper.get('[data-testid="recommendation-actions"] button').trigger('click')

    expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('處理中')
    expect(wrapper.get('[data-testid="recommendation-actions"]').text()).toContain('編輯調整')
  })

  it('shows Today loading, error, and empty states with Chinese guidance', () => {
    expect(mount(App, { props: { todayState: 'loading' } }).text()).toContain('正在整理今天的訓練資料')
    expect(mount(App, { props: { todayState: 'error' } }).text()).toContain('今天資料載入失敗')
    expect(mount(App, { props: { todayState: 'empty' } }).text()).toContain('連接資料來源後')
  })

  it('opens the schedule as a list-first calendar surface', async () => {
    const wrapper = mount(App)

    await wrapper.get('button[data-view="calendar"]').trigger('click')

    expect(wrapper.text()).toContain('本週課表')
    expect(wrapper.text()).toContain('週三')
    expect(wrapper.text()).toContain('Easy Run')
    expect(wrapper.text()).toContain('8 km')
  })

  it('shows an empty schedule state without losing the Calendar surface', () => {
    const wrapper = mount(App, {
      props: {
        initialView: 'calendar',
        workouts: [],
      },
    })

    expect(wrapper.text()).toContain('本週課表')
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
    expect(fetch).not.toHaveBeenCalled()
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
    expect(fetch).not.toHaveBeenCalled()
  })

  it('does not submit Conversation text while Traditional Chinese IME composition is active', async () => {
    const wrapper = mount(App, { props: { initialView: 'conversation' } })
    const textarea = wrapper.get('textarea[name="conversationMessage"]')

    await textarea.setValue('今天要不要改課表')
    await textarea.trigger('compositionstart')
    await textarea.trigger('keydown', { key: 'Enter' })

    expect(fetch).not.toHaveBeenCalled()
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

  it('renders Agent Inbox as a pending decision queue with quieter history', () => {
    const wrapper = mount(App, { props: { initialView: 'inbox' } })

    expect(wrapper.text()).toContain('Agent 收件匣')
    expect(wrapper.text()).toContain('高優先')
    expect(wrapper.text()).toContain('今天 21:00 前決定')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"]').text()).toContain('待決定')
    expect(wrapper.get('[data-testid="inbox-history"]').text()).toContain('已接受')
    expect(wrapper.get('[data-testid="inbox-history"]').text()).toContain('已套用')
    expect(wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-testid="recommendation-actions"]').text()).toContain('討論原因')
  })

  it('shows a Chinese-first Agent Inbox empty state', () => {
    const wrapper = mount(App, { props: { initialView: 'inbox', inboxItems: [] } })

    expect(wrapper.text()).toContain('目前沒有新的主動建議')
    expect(wrapper.text()).toContain('Johnny 之後會把需要你決定的主動建議放在 Agent 收件匣')
  })

  it('opens Conversation with linked recommendation context from Agent Inbox discussion', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: { run_ref: 'discussion-run-test', message: { recommendation_id: 'rec-race-taper' } } }),
    } as Response)
    const wrapper = mount(App, { props: { initialView: 'inbox' } })

    await wrapper.get('[data-testid="inbox-card-rec-race-taper"] [data-action="discuss"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/recommendations/rec-race-taper/discuss',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '我想了解這次建議的原因。' }),
      }),
    )
    expect(wrapper.text()).toContain('已連結建議')
    expect(wrapper.text()).toContain('賽前 9 天降低長跑壓力')
    expect(wrapper.text()).toContain('HRV -18%')
    expect(wrapper.text()).toContain('discussion-run-test')
  })
})
