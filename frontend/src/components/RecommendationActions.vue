<script setup lang="ts">
import AppButton from './AppButton.vue'

defineProps<{
  busyAction?: string
  keepLabel?: string
}>()

const emit = defineEmits<{
  accept: []
  keep: []
}>()
</script>

<template>
  <div class="action-row" data-testid="recommendation-actions">
    <AppButton data-action="accept" tone="primary" :busy="busyAction === 'accept'" @click="emit('accept')">接受調整</AppButton>
    <AppButton data-action="keep" tone="neutral" :busy="busyAction === 'keep'" @click="emit('keep')">{{ keepLabel ?? '保留課表' }}</AppButton>
  </div>
</template>
