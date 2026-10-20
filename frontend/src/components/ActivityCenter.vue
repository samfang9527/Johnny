<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { ViewKey } from '../types'
import type { ActivityTask, ActivityToast, ActivityWorkflow } from '../composables/useActivityCenter'

const props = defineProps<{ tasks: ActivityTask[]; activeCount: number; toast: ActivityToast | null; refreshError?: boolean }>()
const emit = defineEmits<{ navigate: [view: ViewKey, workflow: ActivityWorkflow]; dismissToast: []; refresh: [] }>()
const isOpen = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const visibleTasks = computed(() => props.tasks.filter(item => item.status === 'queued' || item.status === 'running').concat(
  props.tasks.filter(item => item.status !== 'queued' && item.status !== 'running').slice(0, 5),
))
const triggerLabel = computed(() => {
  if (props.activeCount > 1) return `${props.activeCount} 項處理中`
  if (props.activeCount === 1) {
    const workflow = props.tasks.find(item => item.status === 'queued' || item.status === 'running')?.workflow
    return workflow === 'training_plan_generation' ? '計畫產生中' : workflow === 'daily_review' ? '回顧更新中'
      : workflow === 'workout_advice' ? '建議產生中' : workflow === 'garmin_sync' ? '同步資料中' : '工作處理中'
  }
  return '工作狀態'
})

function close() {
  if (!isOpen.value) return
  isOpen.value = false
  trigger.value?.focus()
}

function navigate(view: ViewKey, workflow: ActivityWorkflow) {
  isOpen.value = false
  trigger.value?.focus()
  emit('navigate', view, workflow)
}

function onDocumentPointerDown(event: PointerEvent) {
  if (isOpen.value && event.target instanceof Node && !root.value?.contains(event.target)) isOpen.value = false
}

function onDocumentKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && isOpen.value) close()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeyDown)
})
onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeyDown)
})
</script>

<template>
  <div ref="root" class="activity-center">
    <button ref="trigger" type="button" class="activity-center__trigger" data-testid="activity-trigger"
      :class="{ 'activity-center__trigger--active': activeCount > 0 }"
      :aria-expanded="isOpen" aria-controls="activity-center-panel" @click="isOpen = !isOpen">
      <span class="activity-center__mark" :class="{ 'activity-center__mark--running': activeCount > 0 }" aria-hidden="true"></span>
      <span>{{ triggerLabel }}</span>
    </button>
    <section v-show="isOpen" id="activity-center-panel" class="activity-center__panel" data-testid="activity-panel" aria-label="工作狀態">
      <div class="activity-center__heading">
        <div><span class="section-label">Johnny 正在處理</span><h2>工作狀態</h2></div>
        <button type="button" class="activity-center__close" aria-label="關閉工作狀態" @click="close">關閉</button>
      </div>
      <p v-if="refreshError" class="activity-center__refresh-error">暫時無法確認最新進度。<button type="button" @click="emit('refresh')">重新整理</button></p>
      <ul v-if="visibleTasks.length" class="activity-center__list">
        <li v-for="item in visibleTasks" :key="item.id" class="activity-center__task">
          <span class="activity-center__task-mark" :class="`activity-center__task-mark--${item.status}`" aria-hidden="true"></span>
          <div class="activity-center__task-body">
            <div class="activity-center__task-head"><strong>{{ item.title }}</strong><span>{{ item.status === 'queued' ? '已排入' : item.status === 'running' ? '處理中' : item.status === 'completed' ? '已完成' : item.status === 'partial' ? '部分完成' : '未完成' }}</span></div>
            <p>{{ item.detail }}</p>
            <button type="button" class="activity-center__task-action" data-testid="activity-task-action" @click="navigate(item.view, item.workflow)">{{ item.action }}</button>
          </div>
        </li>
      </ul>
      <p v-else class="activity-center__empty">目前沒有正在處理的工作。</p>
    </section>
    <div v-if="toast" class="activity-center__toast" :class="`activity-center__toast--${toast.tone}`" data-testid="activity-toast" role="status">
      <span>{{ toast.message }}</span>
      <button type="button" class="activity-center__toast-action" @click="navigate(toast.view, toast.workflow); emit('dismissToast')">{{ toast.action }}</button>
      <button type="button" class="activity-center__toast-close" aria-label="關閉通知" @click="emit('dismissToast')">關閉</button>
    </div>
  </div>
</template>
