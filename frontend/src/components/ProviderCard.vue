<script setup lang="ts">
import { computed } from 'vue'
import type { IntegrationConnectionResponse, ProviderOption } from '../types'
import AppButton from './AppButton.vue'
import StatusBadge from './StatusBadge.vue'

const props = withDefaults(
  defineProps<{
  provider: ProviderOption
  connection?: IntegrationConnectionResponse | null
  resourceRows?: string[]
  lastSyncLabel?: string
  busyAction?: '' | 'connect' | 'sync' | 'disconnect'
  disconnectConfirming?: boolean
}>(),
  {
    connection: null,
    resourceRows: () => [],
    lastSyncLabel: '',
    busyAction: '',
    disconnectConfirming: false,
  },
)

const emit = defineEmits<{
  select: [provider: ProviderOption]
  sync: [connection: IntegrationConnectionResponse]
  disconnect: [connection: IntegrationConnectionResponse]
  confirmDisconnect: [connection: IntegrationConnectionResponse]
  cancelDisconnect: []
}>()

const isFuture = computed(() => props.provider.status === 'future')
const isDisconnected = computed(() => props.connection?.status === 'disconnected' || props.connection?.credential_status === 'deleted')
const requiresReauth = computed(() => props.connection?.credential_status === 'requires_reauth')
const isSyncing = computed(() => props.connection?.sync_status === 'running' || props.busyAction === 'sync')
const canSync = computed(() => Boolean(props.connection && !isDisconnected.value && !requiresReauth.value && !isSyncing.value))
const canDisconnect = computed(() => Boolean(props.connection && !isDisconnected.value))

const status = computed((): { label: string; tone: 'info' | 'warning' | 'danger' | 'success' } => {
  if (isFuture.value) {
    return { label: props.provider.statusLabel, tone: 'warning' }
  }
  if (isDisconnected.value) {
    return { label: '已中斷', tone: 'info' }
  }
  if (requiresReauth.value) {
    return { label: '已連接，需要重新登入', tone: 'warning' }
  }
  if (isSyncing.value) {
    return { label: '同步中', tone: 'warning' }
  }
  if (props.connection?.sync_status === 'failed') {
    return { label: '同步失敗', tone: 'warning' }
  }
  if (props.connection?.has_partial_failures) {
    return { label: '部分資料同步失敗', tone: 'warning' }
  }
  if (props.connection) {
    return { label: '已連接', tone: 'success' }
  }
  return { label: props.provider.statusLabel, tone: 'info' }
})

function selectProvider() {
  emit('select', props.provider)
}
</script>

<template>
  <article class="provider-card" :data-testid="`provider-card-${provider.id}`">
    <div class="provider-card__header">
      <h3>{{ provider.name }}</h3>
      <StatusBadge :tone="status.tone">{{ status.label }}</StatusBadge>
    </div>
    <p>{{ provider.description }}</p>
    <div v-if="connection" class="provider-card__account" aria-live="polite">
      <strong>{{ connection.provider_display_name || 'Garmin' }}</strong>
      <span>{{ lastSyncLabel || '尚未同步' }}</span>
    </div>
    <ul class="signal-list">
      <li v-for="signal in provider.coverage" :key="signal">{{ signal }}</li>
    </ul>
    <div v-if="connection && (resourceRows.length || requiresReauth || connection.has_partial_failures || connection.sync_status === 'failed' || connection.sync_warning)" class="provider-card__sync-summary">
      <p v-if="connection.has_partial_failures" class="provider-card__warning">部分資料同步失敗</p>
      <p v-if="connection.sync_warning" class="provider-card__warning">{{ connection.sync_warning }}</p>
      <p v-if="requiresReauth" class="provider-card__recovery">請重新連接 Garmin，更新登入資料後再同步。</p>
      <p v-else-if="connection.has_partial_failures || connection.sync_status === 'failed'" class="provider-card__recovery">檢查失敗的資料後，可再次手動同步。</p>
      <ul v-if="resourceRows.length">
        <li v-for="row in resourceRows" :key="row">{{ row }}</li>
      </ul>
    </div>
    <div v-if="disconnectConfirming && connection" class="provider-card__confirm" role="alert">
      <p>中斷 Garmin 連接？歷史匯入資料會保留，但未來同步會停止。</p>
      <div class="provider-card__actions">
        <AppButton data-action="confirm-disconnect" tone="danger" :busy="busyAction === 'disconnect'" @click="emit('confirmDisconnect', connection)">確認中斷</AppButton>
        <AppButton data-action="cancel-disconnect" tone="neutral" :disabled="busyAction === 'disconnect'" @click="emit('cancelDisconnect')">取消</AppButton>
      </div>
    </div>
    <div v-else class="provider-card__actions">
      <AppButton
        v-if="isFuture || !connection || isDisconnected || requiresReauth"
        data-action="select-provider"
        tone="primary"
        :busy="busyAction === 'connect'"
        :disabled="isFuture"
        @click="selectProvider"
      >
        {{ isFuture ? '尚未開放' : connection ? '重新連接' : '連接資料' }}
      </AppButton>
      <AppButton
        v-if="connection && !isDisconnected && !requiresReauth"
        data-action="manual-sync"
        tone="primary"
        :busy="busyAction === 'sync'"
        :disabled="!canSync"
        @click="emit('sync', connection)"
      >
        手動同步
      </AppButton>
      <AppButton
        v-if="canDisconnect && connection"
        data-action="disconnect"
        tone="neutral"
        :disabled="busyAction === 'sync' || busyAction === 'connect'"
        @click="emit('disconnect', connection)"
      >
        中斷連接
      </AppButton>
    </div>
  </article>
</template>
