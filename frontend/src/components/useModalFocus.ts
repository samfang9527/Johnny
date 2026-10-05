import { nextTick, onMounted, onUnmounted, type Ref } from 'vue'

type ModalEntry = { element: HTMLElement; initialSelector: string }
const modalStack: ModalEntry[] = []
const isolated = new Map<HTMLElement, boolean>()
let pageOverflow = ''
let pageFocus: HTMLElement | null = null
const focusableSelector = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function topModal() { return modalStack[modalStack.length - 1] }

function isolateTopModal() {
  for (const [node, wasInert] of isolated) node.inert = wasInert
  isolated.clear()
  let branch = topModal()?.element
  while (branch?.parentElement) {
    for (const sibling of branch.parentElement.children) {
      if (sibling instanceof HTMLElement && sibling !== branch) {
        isolated.set(sibling, sibling.inert)
        sibling.inert = true
      }
    }
    branch = branch.parentElement
    if (branch === document.body) break
  }
}

export function useModalFocus(root: Ref<HTMLElement | null>, close: () => void, initialSelector: string) {
  let previousFocus: HTMLElement | null = null
  let entry: ModalEntry | null = null

  function handleKeydown(event: KeyboardEvent) {
    if (!entry || topModal() !== entry) return
    const element = entry.element
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      close()
    }
    if (event.key !== 'Tab') return
    const controls = Array.from(element.querySelectorAll<HTMLElement>(focusableSelector))
      .filter((node) => !node.closest('[inert]'))
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (!first || !last) { event.preventDefault(); element.focus(); return }
    if (!element.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
      event.preventDefault()
      ;(event.shiftKey ? last : first).focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  onMounted(async () => {
    if (!root.value) return
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (!modalStack.length) {
      pageOverflow = document.body.style.overflow
      pageFocus = previousFocus
    }
    entry = { element: root.value, initialSelector }
    modalStack.push(entry)
    isolateTopModal()
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeydown, true)
    await nextTick()
    if (entry?.element.isConnected) (entry.element.querySelector<HTMLElement>(initialSelector) ?? entry.element).focus()
  })

  onUnmounted(() => {
    if (!entry) return
    const wasTop = topModal() === entry
    modalStack.splice(modalStack.indexOf(entry), 1)
    document.removeEventListener('keydown', handleKeydown, true)
    isolateTopModal()
    if (!modalStack.length) {
      document.body.style.overflow = pageOverflow
      if (pageFocus?.isConnected) pageFocus.focus()
      pageFocus = null
    } else if (wasTop) {
      const top = topModal()!
      const target = previousFocus?.isConnected && top.element.contains(previousFocus)
        ? previousFocus : top.element.querySelector<HTMLElement>(top.initialSelector)
      target?.focus()
    }
    entry = null
  })
}
