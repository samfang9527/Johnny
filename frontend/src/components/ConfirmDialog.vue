<script setup lang="ts">
import AppButton from './AppButton.vue'

defineProps<{
  title: string
  description: string
  confirmLabel: string
  cancelLabel?: string
}>()

defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<template>
  <div class="app-dialog app-dialog--alert" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" data-testid="confirm-dialog">
    <section class="app-dialog__panel confirm-dialog">
      <div>
        <p class="section-label">確認</p>
        <h3 id="confirm-dialog-title">{{ title }}</h3>
      </div>
      <p>{{ description }}</p>
      <div class="app-dialog__actions">
        <AppButton tone="neutral" type="button" data-testid="confirm-dialog-cancel" @click="$emit('cancel')">
          {{ cancelLabel || '繼續編輯' }}
        </AppButton>
        <AppButton tone="danger" type="button" data-testid="confirm-dialog-confirm" @click="$emit('confirm')">
          {{ confirmLabel }}
        </AppButton>
      </div>
    </section>
  </div>
</template>
