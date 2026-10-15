import type { Directive } from 'vue'

const cleanupByElement = new WeakMap<HTMLElement, () => void>()

function motionDuration(token: string, fallback: number): number {
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  const amount = Number.parseFloat(value)
  if (!Number.isFinite(amount)) return fallback
  return value.endsWith('ms') ? amount : value.endsWith('s') ? amount * 1000 : fallback
}

export const vMotionDetails: Directive<HTMLElement> = {
  mounted(element) {
    if (!(element instanceof HTMLDetailsElement)) return
    const detailsElement = element
    const summary = Array.from(element.children).find((child): child is HTMLElement => child instanceof HTMLElement && child.tagName === 'SUMMARY')
    const content = Array.from(element.children).find((child): child is HTMLElement => child instanceof HTMLElement && child.classList.contains('motion-details__content'))
    if (!summary || !content) return
    const summaryElement = summary
    const contentElement = content

    let animation: Animation | null = null
    let shouldOpen = detailsElement.open
    contentElement.inert = !shouldOpen

    function clearInlineStyles() {
      contentElement.style.removeProperty('height')
      contentElement.style.removeProperty('overflow')
    }

    function toggle(event: MouseEvent) {
      if (!(event.target instanceof Element) || !summaryElement.contains(event.target)) return
      event.preventDefault()
      shouldOpen = !shouldOpen
      const opening = shouldOpen
      const fromHeight = detailsElement.open ? contentElement.getBoundingClientRect().height : 0
      const fromOpacity = animation ? Number.parseFloat(getComputedStyle(contentElement).opacity) || 0 : opening ? 0 : 1

      if (animation) {
        animation.onfinish = null
        animation.cancel()
        animation = null
      }
      if (opening) detailsElement.open = true
      contentElement.inert = !opening

      const reduceMotion = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
      if (reduceMotion || typeof contentElement.animate !== 'function') {
        detailsElement.open = opening
        clearInlineStyles()
        return
      }

      const toHeight = opening ? contentElement.scrollHeight : 0
      contentElement.style.height = `${fromHeight}px`
      contentElement.style.overflow = 'hidden'
      animation = contentElement.animate([
        { height: `${fromHeight}px`, opacity: fromOpacity },
        { height: `${toHeight}px`, opacity: opening ? 1 : 0 },
      ], {
        duration: opening ? motionDuration('--motion-reveal', 240) : motionDuration('--motion-exit', 180),
        easing: getComputedStyle(document.documentElement).getPropertyValue('--motion-ease').trim() || 'ease-out',
      })
      const current = animation
      current.onfinish = () => {
        if (animation !== current) return
        detailsElement.open = opening
        animation = null
        clearInlineStyles()
      }
    }

    summaryElement.addEventListener('click', toggle)
    cleanupByElement.set(element, () => {
      summaryElement.removeEventListener('click', toggle)
      if (animation) {
        animation.onfinish = null
        animation.cancel()
      }
      contentElement.inert = false
      clearInlineStyles()
    })
  },
  unmounted(element) {
    cleanupByElement.get(element)?.()
    cleanupByElement.delete(element)
  },
}
