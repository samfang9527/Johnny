<script setup lang="ts">
import { ref } from 'vue'
import { useModalFocus } from './useModalFocus'
import AppButton from './AppButton.vue'

const props = defineProps<{
  title: string
  description: string
  confirmLabel: string
  cancelLabel?: string
  busy?: boolean
  error?: string
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
const dialogRef = ref<HTMLElement | null>(null)
function cancel() { if (!props.busy) emit('cancel') }
function confirm() { if (!props.busy) emit('confirm') }
useModalFocus(dialogRef, cancel, '[data-testid="confirm-dialog-cancel"]')
</script>

<template>
  <div ref="dialogRef" tabindex="-1" class="app-dialog app-dialog--alert" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-description" :aria-busy="busy" data-testid="confirm-dialog">
    <section class="app-dialog__panel confirm-dialog">
      <div>
        <p class="section-label">確認</p>
        <h3 id="confirm-dialog-title">{{ title }}</h3>
      </div>
      <p id="confirm-dialog-description">{{ description }}</p>
      <p v-if="error" class="field-error" role="alert">{{ error }}</p>
      <div class="app-dialog__actions">
        <AppButton tone="neutral" type="button" data-testid="confirm-dialog-cancel" :disabled="busy" @click="cancel">
          {{ cancelLabel || '繼續編輯' }}
        </AppButton>
        <AppButton tone="danger" type="button" data-testid="confirm-dialog-confirm" :busy="busy" @click="confirm">
          {{ confirmLabel }}
        </AppButton>
      </div>
    </section>
  </div>
</template>
