<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import type { RaceSummary, TrainingPlanRegenerationOptions, TrainingPlanRegenerationRequest, TrainingPlanType } from '../types'
import AppButton from './AppButton.vue'

const props = withDefaults(
  defineProps<{
    options: TrainingPlanRegenerationOptions
    raceOptions: RaceSummary[]
    timeZone: string
    busy?: boolean
    error?: string
  }>(),
  { busy: false, error: '' },
)

const emit = defineEmits<{
  close: []
  confirm: [payload: TrainingPlanRegenerationRequest]
}>()

const defaultRaceId = props.raceOptions.some((race) => race.id === props.options.default_strategy.race_id)
  ? props.options.default_strategy.race_id
  : props.raceOptions[0]?.id ?? null
const selectedPlanType = ref<TrainingPlanType>(props.options.default_strategy.plan_type === 'race' && defaultRaceId ? 'race' : 'maintenance')
const selectedRaceId = ref<string | null>(defaultRaceId)
const dialogRef = ref<HTMLElement | null>(null)
const selectedRace = computed(() => props.raceOptions.find((race) => race.id === selectedRaceId.value) ?? null)
const canUseRaceStrategy = computed(() => props.raceOptions.length > 0)
const canConfirm = computed(() =>
  props.options.quota.available && !props.busy && !props.options.in_flight_run && (selectedPlanType.value !== 'race' || Boolean(selectedRaceId.value)),
)
const nextAvailableLabel = computed(() => {
  const value = props.options.quota.next_available_at
  return value ? new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: props.timeZone }).format(new Date(value)) : ''
})

function submit() {
  if (!canConfirm.value) {
    return
  }
  emit('confirm', {
    client_request_id: globalThis.crypto?.randomUUID?.() || `regeneration-${Date.now()}`,
    race_id: selectedPlanType.value === 'race' ? selectedRaceId.value : null,
    plan_type: selectedPlanType.value,
  })
}

function requestClose() {
  if (!props.busy) {
    emit('close')
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose()
    return
  }
  if (event.key !== 'Tab' || !dialogRef.value) {
    return
  }
  const focusable = Array.from(dialogRef.value.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
  if (!focusable.length) {
    event.preventDefault()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  await nextTick()
  dialogRef.value?.querySelector<HTMLButtonElement>('[data-testid="training-plan-regeneration-cancel"]')?.focus()
})
</script>

<template>
  <div class="app-dialog" role="presentation" data-testid="training-plan-regeneration-sheet" @click.self="requestClose" @keydown="handleKeydown">
    <section ref="dialogRef" class="app-dialog__panel training-plan-regeneration-sheet" role="dialog" aria-modal="true" aria-labelledby="training-plan-regeneration-title" tabindex="-1">
      <div>
        <p class="section-label">訓練計畫</p>
        <h3 id="training-plan-regeneration-title">重新產生計畫</h3>
        <p>目前課表會保留到新的訓練安排完成。</p>
      </div>

      <form novalidate @submit.prevent="submit">
        <fieldset>
          <legend>這次計畫要以什麼為主？</legend>
          <label class="training-plan-regeneration-sheet__choice">
            <input v-model="selectedPlanType" type="radio" name="regenerationPlanType" value="race" :disabled="!canUseRaceStrategy || busy" />
            <span>
              <strong>比賽策略</strong>
              <small>依照下一個比賽目標安排。</small>
            </span>
          </label>
          <label class="training-plan-regeneration-sheet__choice">
            <input v-model="selectedPlanType" type="radio" name="regenerationPlanType" value="maintenance" :disabled="busy" />
            <span>
              <strong>維持訓練</strong>
              <small>先以穩定訓練節奏為主。</small>
            </span>
          </label>
          <label v-if="selectedPlanType === 'race'" class="training-plan-regeneration-sheet__race-select">
            選擇比賽
            <select v-model="selectedRaceId" name="regenerationRaceId" :disabled="busy">
              <option v-for="race in raceOptions" :key="race.id" :value="race.id">{{ race.name }} · {{ race.raceDate }} · {{ race.distance }} · {{ race.goal }}</option>
            </select>
          </label>
          <p v-if="selectedPlanType === 'race' && selectedRace" class="inline-note" data-testid="training-plan-regeneration-race-detail">
            {{ selectedRace.name }} · {{ selectedRace.raceDate }} · {{ selectedRace.distance }} · {{ selectedRace.goal }}
          </p>
        </fieldset>

        <p class="training-plan-regeneration-sheet__quota" :class="{ 'training-plan-regeneration-sheet__quota--exhausted': !options.quota.available }">
          今日可重新產生 {{ options.quota.remaining }}/{{ options.quota.limit }} 次
        </p>
        <p v-if="!options.quota.available" class="field-error" role="status">今日重新產生額度已用完</p>
        <p v-if="!options.quota.available && nextAvailableLabel" class="inline-note" data-testid="training-plan-regeneration-next-available">下次可用：{{ nextAvailableLabel }}</p>
        <p v-if="options.in_flight_run" class="inline-note" role="status">已有計畫正在重新產生，請先保留目前課表。</p>
        <p v-if="error" class="field-error" role="alert">{{ error }}</p>

        <div class="app-dialog__actions">
          <AppButton tone="neutral" type="button" :disabled="busy" data-testid="training-plan-regeneration-cancel" @click="requestClose">取消</AppButton>
          <AppButton tone="primary" type="submit" :busy="busy" :disabled="!canConfirm" data-testid="training-plan-regeneration-confirm">確認重新產生</AppButton>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.training-plan-regeneration-sheet,
.training-plan-regeneration-sheet form,
.training-plan-regeneration-sheet fieldset {
  display: grid;
  gap: 1rem;
}

.training-plan-regeneration-sheet {
  width: min(30rem, 100%);
}

.training-plan-regeneration-sheet fieldset {
  margin: 0;
  padding: 0;
  border: 0;
}

.training-plan-regeneration-sheet legend {
  font-weight: 700;
}

.training-plan-regeneration-sheet__choice {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.8rem;
  border: 1px solid rgba(246, 239, 228, 0.18);
  border-radius: var(--radius-md);
}

.training-plan-regeneration-sheet__choice span {
  display: grid;
  gap: 0.15rem;
}

.training-plan-regeneration-sheet__race-select {
  display: grid;
  gap: 0.4rem;
  font-weight: 700;
}

.training-plan-regeneration-sheet__choice small,
.training-plan-regeneration-sheet__quota {
  color: var(--color-muted-chalk);
}

.training-plan-regeneration-sheet__quota {
  margin: 0;
}

.training-plan-regeneration-sheet__quota--exhausted {
  color: var(--color-split-amber);
}
</style>
