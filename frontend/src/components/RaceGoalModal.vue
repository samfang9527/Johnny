<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { RaceGoalCreatePayload } from '../types'
import { kilometersToMeters, optionalCourseMeters, optionalCutoffSeconds, racePriorityOptions, targetFinishSeconds, type RacePriority } from '../raceGoalForm'
import AppButton from './AppButton.vue'
import DatePicker from './DatePicker.vue'

const props = defineProps<{
  error?: string
  busy?: boolean
  minDate: string
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: RaceGoalCreatePayload]
}>()

const raceName = ref('')
const raceDate = ref('')
const racePriority = ref<RacePriority | ''>('')
const raceDistanceKilometers = ref('')
const targetFinishHours = ref('')
const targetFinishMinutes = ref('')
const targetFinishSecondsValue = ref('')
const ascentMeters = ref('')
const descentMeters = ref('')
const terrainDifficulty = ref<'' | 'runnable' | 'mixed' | 'technical'>('')
const cutoffHours = ref('')
const goalIntent = ref<'' | 'complete' | 'perform'>('')
const fieldError = ref('')
const dateTouched = ref(false)
const priorityRef = ref<HTMLSelectElement | null>(null)

const isDirty = computed(() =>
  Boolean(
    raceName.value.trim() ||
      raceDate.value.trim() ||
      racePriority.value ||
      raceDistanceKilometers.value.trim() ||
      targetFinishHours.value.trim() ||
      targetFinishMinutes.value.trim() ||
      targetFinishSecondsValue.value.trim() ||
      ascentMeters.value.trim() || descentMeters.value.trim() || terrainDifficulty.value || cutoffHours.value.trim() || goalIntent.value,
  ),
)

defineExpose({ isDirty })

function requestClose() {
  emit('close')
}

function handleDateBlur() {
  dateTouched.value = true
  if (!raceDate.value.trim()) {
    return
  }
  if (!isValidDate(raceDate.value)) {
    fieldError.value = '請輸入 YYYY-MM-DD 格式的日期'
    return
  }
  if (raceDate.value < props.minDate) {
    fieldError.value = '日期不能早於今天'
    return
  }
  if (fieldError.value.includes('日期') || fieldError.value.includes('YYYY-MM-DD')) {
    fieldError.value = ''
  }
}

async function submitForm() {
  fieldError.value = ''
  dateTouched.value = true
  if (!raceName.value.trim()) {
    fieldError.value = '請輸入目標名稱'
    return
  }
  if (!racePriority.value) {
    fieldError.value = '請選擇目標優先度'
    await nextTick()
    priorityRef.value?.focus()
    return
  }
  if (!isValidDate(raceDate.value)) {
    fieldError.value = '請輸入 YYYY-MM-DD 格式的日期'
    return
  }
  if (raceDate.value < props.minDate) {
    fieldError.value = '日期不能早於今天'
    return
  }
  const distanceMeters = kilometersToMeters(raceDistanceKilometers.value)
  if (!distanceMeters) {
    fieldError.value = '請輸入 0 到 500 之間、最多三位小數的公里數'
    return
  }
  const parsedTargetSeconds = targetFinishSeconds(targetFinishHours.value, targetFinishMinutes.value, targetFinishSecondsValue.value)
  const ascent = optionalCourseMeters(ascentMeters.value)
  const descent = optionalCourseMeters(descentMeters.value)
  const cutoff = optionalCutoffSeconds(cutoffHours.value)
  if (ascent === null || descent === null) {
    fieldError.value = '爬升與下降請輸入 0 到 20,000 公尺之間的數字'
    return
  }
  if (cutoff === null) {
    fieldError.value = '關門時間請輸入大於 0 的小時數'
    return
  }
  emit('submit', {
    name: raceName.value.trim(),
    race_date: raceDate.value,
    distance_meters: distanceMeters,
    target_finish_seconds: parsedTargetSeconds,
    priority: racePriority.value,
    ...(ascent !== undefined ? { ascent_meters: ascent } : {}),
    ...(descent !== undefined ? { descent_meters: descent } : {}),
    ...(terrainDifficulty.value ? { terrain_difficulty: terrainDifficulty.value } : {}),
    ...(cutoff !== undefined ? { cutoff_seconds: cutoff } : {}),
    ...(goalIntent.value ? { goal_intent: goalIntent.value } : {}),
  })
}

function isValidDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false
  }
  const date = new Date(`${value}T00:00:00`)
  return !Number.isNaN(date.getTime()) && value === `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
</script>

<template>
  <div class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="race-goal-modal-title" data-testid="race-goal-modal" @keydown.esc="requestClose">
    <section class="app-dialog__panel race-goal-modal">
      <div class="section-heading">
        <div>
          <p class="section-label">新增目標</p>
          <h3 id="race-goal-modal-title">設定訓練計畫</h3>
        </div>
        <button class="icon-button" type="button" aria-label="關閉新增目標" data-testid="race-modal-close" @click="requestClose">×</button>
      </div>

      <form class="race-form" data-testid="race-form" novalidate @submit.prevent="submitForm">
        <div class="form-grid race-goal-modal__grid">
          <label>
            名稱
            <input v-model="raceName" name="raceName" autocomplete="off" :aria-invalid="fieldError && !raceName.trim() ? 'true' : 'false'" />
          </label>
          <label>
            優先度
            <select ref="priorityRef" v-model="racePriority" name="racePriority" :aria-invalid="fieldError.includes('優先度') ? 'true' : 'false'">
              <option value="">選擇優先度</option>
              <option v-for="option in racePriorityOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label>
            距離（公里）
            <input v-model="raceDistanceKilometers" name="raceDistanceKilometers" inputmode="decimal" autocomplete="off" placeholder="42.195" />
          </label>
          <label class="race-goal-modal__date">
            日期
            <DatePicker v-model="raceDate" :min="minDate" :invalid="dateTouched && Boolean(fieldError.includes('日期') || fieldError.includes('YYYY-MM-DD'))" @blur="handleDateBlur" />
          </label>
        </div>

        <fieldset class="target-time-fieldset">
          <legend>目標完賽時間（選填）</legend>
          <div class="target-time-grid">
            <label>
              小時
              <input v-model="targetFinishHours" name="targetFinishHours" inputmode="numeric" autocomplete="off" />
            </label>
            <label>
              分鐘
              <input v-model="targetFinishMinutes" name="targetFinishMinutes" inputmode="numeric" autocomplete="off" />
            </label>
            <label>
              秒
              <input v-model="targetFinishSecondsValue" name="targetFinishSeconds" inputmode="numeric" autocomplete="off" />
            </label>
          </div>
        </fieldset>

        <fieldset class="target-time-fieldset">
          <legend>賽道與目標（選填）</legend>
          <div class="form-grid race-goal-modal__grid">
            <label>累積爬升（公尺）<input v-model="ascentMeters" name="ascentMeters" inputmode="decimal" autocomplete="off" placeholder="未知可留白" /></label>
            <label>累積下降（公尺）<input v-model="descentMeters" name="descentMeters" inputmode="decimal" autocomplete="off" placeholder="未知可留白" /></label>
            <label>賽道地形
              <select v-model="terrainDifficulty" name="terrainDifficulty">
                <option value="">未知</option><option value="runnable">可跑性高</option><option value="mixed">混合地形</option><option value="technical">技術地形</option>
              </select>
            </label>
            <label>關門時間（小時）<input v-model="cutoffHours" name="cutoffHours" inputmode="decimal" autocomplete="off" placeholder="未知可留白" /></label>
            <label>參賽目標
              <select v-model="goalIntent" name="goalIntent"><option value="">尚未決定</option><option value="complete">完成賽事</option><option value="perform">挑戰表現</option></select>
            </label>
          </div>
        </fieldset>

        <p v-if="fieldError || error" class="field-error" role="alert">{{ fieldError || error }}</p>
        <div class="form-footer">
          <div></div>
          <AppButton tone="primary" type="submit" :busy="busy">加入安排</AppButton>
        </div>
      </form>
    </section>
  </div>
</template>
