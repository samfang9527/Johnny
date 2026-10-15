import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { vMotionDetails } from './motionDetails'

function mountDisclosure() {
  return mount({
    template: '<details v-motion-details><summary>展開</summary><div class="motion-details__content"><button>內容</button></div></details>',
  }, { global: { directives: { motionDetails: vMotionDetails } } })
}

describe('motion details', () => {
  it('preserves native disclosure state when animation is unavailable', async () => {
    const wrapper = mountDisclosure()
    const details = wrapper.get('details').element as HTMLDetailsElement
    const content = wrapper.get('.motion-details__content').element as HTMLElement
    Object.defineProperty(content, 'animate', { configurable: true, value: undefined })

    await wrapper.get('summary').trigger('click')
    expect(details.open).toBe(true)
    expect(content.inert).toBe(false)

    await wrapper.get('summary').trigger('click')
    expect(details.open).toBe(false)
    expect(content.inert).toBe(true)
  })

  it('keeps content open until the close motion finishes', async () => {
    const wrapper = mountDisclosure()
    const details = wrapper.get('details').element as HTMLDetailsElement
    const content = wrapper.get('.motion-details__content').element as HTMLElement
    const animations: Array<{ onfinish: (() => void) | null; cancel: ReturnType<typeof vi.fn> }> = []
    Object.defineProperty(content, 'animate', { configurable: true, value: () => {
      const animation = { onfinish: null, cancel: vi.fn() }
      animations.push(animation)
      return animation
    } })

    await wrapper.get('summary').trigger('click')
    animations[0].onfinish?.()
    await wrapper.get('summary').trigger('click')

    expect(details.open).toBe(true)
    expect(content.inert).toBe(true)
    animations[1].onfinish?.()
    expect(details.open).toBe(false)
  })
})
