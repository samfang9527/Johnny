<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TrainingPlanRegenerationOptions, TrainingPlanRegenerationRequest, TrainingPlanType } from '../types'
import AppButton from './AppButton.vue'

const props = withDefaults(
  defineProps<{
    options: TrainingPlanRegenerationOptions
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

const selectedPlanType = ref<TrainingPlanType>(props.options.default_strategy.plan_type)
const canUseRaceStrategy = computed(() => Boolean(props.options.default_strategy.race_id))
const nextAvailableLabel = computed(() => {
  const value = props.options.quota.next_available_at
  return value ? new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: props.timeZone }).format(new Date(value)) : ''
})

function submit() {
  if (!props.options.quota.available || props.busy) {
    return
  }
  emit('confirm', {
    client_request_id: globalThis.crypto?.randomUUID?.() || `regeneration-${Date.now()}`,
    race_id: selectedPlanType.value === 'race' ? props.options.default_strategy.race_id : null,
    plan_type: selectedPlanType.value,
  })
}
</script>

<template>
  <div class="app-dialog" role="presentation" data-testid="training-plan-regeneration-sheet" @click.self="$emit('close')" @keydown.esc="$emit('close')">
    <section class="app-dialog__panel training-plan-regeneration-sheet" role="dialog" aria-modal="true" aria-labelledby="training-plan-regeneration-title" tabindex="-1">
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
        </fieldset>

        <p class="training-plan-regeneration-sheet__quota" :class="{ 'training-plan-regeneration-sheet__quota--exhausted': !options.quota.available }">
          今日可重新產生 {{ options.quota.remaining }}/{{ options.quota.limit }} 次
        </p>
        <p v-if="!options.quota.available" class="field-error" role="status">今日重新產生額度已用完</p>
        <p v-if="!options.quota.available && nextAvailableLabel" class="inline-note" data-testid="training-plan-regeneration-next-available">下次可用：{{ nextAvailableLabel }}</p>
        <p v-if="options.in_flight_run" class="inline-note" role="status">已有計畫正在重新產生，請先保留目前課表。</p>
        <p v-if="error" class="field-error" role="alert">{{ error }}</p>

        <div class="app-dialog__actions">
          <AppButton tone="neutral" type="button" :disabled="busy" @click="$emit('close')">取消</AppButton>
          <AppButton tone="primary" type="submit" :busy="busy" :disabled="!options.quota.available" data-testid="training-plan-regeneration-confirm">確認重新產生</AppButton>
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
