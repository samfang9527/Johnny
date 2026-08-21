<script setup lang="ts">
import AppButton from './AppButton.vue'

defineProps<{
  busyAction?: string
}>()

const emit = defineEmits<{
  accept: []
  edit: []
  keep: []
  discuss: []
}>()
</script>

<template>
  <div class="action-row" data-testid="recommendation-actions">
    <AppButton tone="primary" :busy="busyAction === 'accept'" @click="emit('accept')">接受調整</AppButton>
    <AppButton tone="neutral" @click="emit('edit')">編輯調整</AppButton>
    <AppButton tone="neutral" @click="emit('keep')">保留原課表</AppButton>
    <AppButton tone="warning" @click="emit('discuss')">討論原因</AppButton>
  </div>
</template>
