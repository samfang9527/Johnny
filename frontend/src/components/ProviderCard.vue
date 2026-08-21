<script setup lang="ts">
import type { ProviderOption } from '../types'
import AppButton from './AppButton.vue'
import StatusBadge from './StatusBadge.vue'

defineProps<{
  provider: ProviderOption
}>()

const emit = defineEmits<{
  select: [provider: ProviderOption]
}>()
</script>

<template>
  <article class="provider-card">
    <div class="provider-card__header">
      <h3>{{ provider.name }}</h3>
      <StatusBadge :tone="provider.status === 'future' ? 'warning' : 'info'">{{ provider.statusLabel }}</StatusBadge>
    </div>
    <p>{{ provider.description }}</p>
    <ul class="signal-list">
      <li v-for="signal in provider.coverage" :key="signal">{{ signal }}</li>
    </ul>
    <AppButton
      tone="primary"
      :disabled="provider.status === 'future'"
      @click="emit('select', provider)"
    >
      {{ provider.status === 'future' ? '尚未開放' : '連接資料來源' }}
    </AppButton>
  </article>
</template>
