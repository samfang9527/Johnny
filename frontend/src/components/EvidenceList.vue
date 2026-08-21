<script setup lang="ts">
import type { EvidenceItem } from '../types'
import StatusBadge from './StatusBadge.vue'

defineProps<{
  items: EvidenceItem[]
  unavailable?: string[]
}>()
</script>

<template>
  <div class="evidence-list">
    <article v-for="item in items" :key="`${item.source}-${item.metric}`" class="evidence-row">
      <div>
        <p class="evidence-row__label">{{ item.source }} · {{ item.metric }}</p>
        <strong class="evidence-row__value">{{ item.value }}</strong>
      </div>
      <StatusBadge :tone="item.tone || 'info'">{{ item.summary }}</StatusBadge>
    </article>

    <div v-if="unavailable?.length" class="unavailable-signals">
      <p class="section-label">缺少訊號</p>
      <ul>
        <li v-for="signal in unavailable" :key="signal">{{ signal }}</li>
      </ul>
    </div>
  </div>
</template>
