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
})
