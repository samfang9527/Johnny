<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const model = defineModel<string>({ default: '' })
const props = withDefaults(
  defineProps<{
    min?: string
    invalid?: boolean
    describedBy?: string
  }>(),
  {
    min: '',
    invalid: false,
    describedBy: undefined,
  },
)

const emit = defineEmits<{
  blur: []
}>()

const today = new Date()
const initialMonth = model.value && isValidDate(model.value) ? parseDate(model.value) : new Date(today.getFullYear(), today.getMonth(), 1)
const visibleMonth = ref(new Date(initialMonth.getFullYear(), initialMonth.getMonth(), 1))

watch(model, (value) => {
  if (isValidDate(value)) {
    const date = parseDate(value)
    visibleMonth.value = new Date(date.getFullYear(), date.getMonth(), 1)
  }
})

const monthLabel = computed(() => visibleMonth.value.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long' }))
const calendarDays = computed(() => {
  const year = visibleMonth.value.getFullYear()
  const month = visibleMonth.value.getMonth()
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const blanks = Array.from({ length: firstDay }, (_, index) => ({ key: `blank-${index}`, date: '', label: '', disabled: true, selected: false }))
  const days = Array.from({ length: daysInMonth }, (_, index) => {
    const day = index + 1
    const date = formatDate(new Date(year, month, day))
    return {
      key: date,
      date,
      label: String(day),
      disabled: Boolean(props.min && date < props.min),
      selected: model.value === date,
    }
  })
  return [...blanks, ...days]
})
const blankDays = computed(() => calendarDays.value.filter((day) => !day.date))
const selectableDays = computed(() => calendarDays.value.filter((day) => day.date))

function updateTypedValue(event: Event) {
  model.value = (event.target as HTMLInputElement).value
}

function chooseDate(date: string) {
  model.value = date
}

function shiftMonth(delta: number) {
  visibleMonth.value = new Date(visibleMonth.value.getFullYear(), visibleMonth.value.getMonth() + delta, 1)
}

function isValidDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(parseDate(value).getTime())
}

function parseDate(value: string): Date {
  return new Date(`${value}T00:00:00`)
}

function formatDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
</script>

<template>
  <div class="date-picker">
    <input
      :value="model"
      name="raceDate"
      inputmode="numeric"
      placeholder="YYYY-MM-DD"
      autocomplete="off"
      :aria-invalid="invalid ? 'true' : 'false'"
      :aria-describedby="describedBy"
      @input="updateTypedValue"
      @blur="emit('blur')"
    />
    <div class="date-picker__calendar" aria-label="選擇日期">
      <div class="date-picker__header">
        <button type="button" aria-label="上一個月" @click="shiftMonth(-1)">‹</button>
        <strong>{{ monthLabel }}</strong>
        <button type="button" aria-label="下一個月" data-testid="date-picker-next-month" @click="shiftMonth(1)">›</button>
      </div>
      <div class="date-picker__weekdays" aria-hidden="true">
        <span>日</span>
        <span>一</span>
        <span>二</span>
        <span>三</span>
        <span>四</span>
        <span>五</span>
        <span>六</span>
      </div>
      <div class="date-picker__grid">
        <span v-for="day in blankDays" :key="day.key" aria-hidden="true"></span>
        <button
          v-for="day in selectableDays"
          :key="day.key"
          type="button"
          :disabled="day.disabled"
          :class="{ 'date-picker__day--selected': day.selected }"
          :data-testid="`date-picker-day-${day.date}`"
          @click="chooseDate(day.date)"
        >
          {{ day.label }}
        </button>
      </div>
    </div>
  </div>
</template>
