<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { listSessionReviews, saveSessionReviews, type SessionReview, type SessionReviewDecision, type SessionReviewSaveResult } from '../api/client'
import AppButton from './AppButton.vue'

const props = defineProps<{ anchorDate: string; timeZone: string; refreshKey?: number }>()
const emit = defineEmits<{ changed: [result: SessionReviewSaveResult]; error: [error: unknown] }>()
const reviews = ref<SessionReview[]>([])
const loading = ref(false)
const loadError = ref('')
const saveError = ref('')
const message = ref('')
const busyId = ref('')
const editingId = ref('')
const groups = ref<SessionReviewDecision['groups']>([])
let generation = 0
let disposed = false
const editableReviews = computed(() => {
  const firstDay = new Date(`${props.anchorDate}T00:00:00Z`)
  firstDay.setUTCDate(firstDay.getUTCDate() - 6)
  const firstDate = firstDay.toISOString().slice(0, 10)
  return reviews.value.filter(item => firstDate <= item.local_date && item.local_date <= props.anchorDate)
})
const buckets = computed(() => [
  { history: false, items: editableReviews.value.filter(item => ['automatic', 'needs_review'].includes(item.status)) },
  { history: true, items: editableReviews.value.filter(item => ['confirmed', 'unplanned'].includes(item.status)) },
])

async function load() {
  const current = ++generation
  loading.value = true
  loadError.value = ''
  try {
    const response = await listSessionReviews(props.anchorDate)
    if (disposed || current !== generation) return
    reviews.value = Array.isArray(response.data) ? [...response.data].sort((a, b) => b.local_date.localeCompare(a.local_date)) : []
  } catch (error) {
    if (disposed || current !== generation) return
    loadError.value = '活動確認載入失敗。請重新載入。'
    emit('error', error)
  } finally {
    if (!disposed && current === generation) loading.value = false
  }
}
watch(() => [props.anchorDate, props.refreshKey], () => {
  reviews.value = []
  editingId.value = ''
  busyId.value = ''
  saveError.value = ''
  message.value = ''
  void load()
}, { immediate: true })
onUnmounted(() => { disposed = true; generation += 1 })

function edit(review: SessionReview) {
  editingId.value = review.id
  saveError.value = ''
  groups.value = [{ activity_ids: review.activities.map(item => item.id), workout_id: review.workout_id }]
}
function split(review: SessionReview) {
  // Explicitly assign each recording so a split cannot silently claim a workout twice.
  groups.value = review.activities.map(item => ({ activity_ids: [item.id], workout_id: null }))
}
async function save(review: SessionReview, decisions: SessionReviewDecision['groups']) {
  if (busyId.value) return
  const current = generation
  busyId.value = review.id
  saveError.value = ''
  message.value = ''
  try {
    const response = await saveSessionReviews({ activity_ids: review.activities.map(item => item.id), groups: decisions.map(group => ({ ...group, workout_id: group.workout_id || null })) })
    if (disposed || current !== generation) return
    editingId.value = ''
    message.value = '配對已儲存，Johnny 正在更新建議。'
    emit('changed', response.data)
    await load()
  } catch (error) {
    if (disposed || current !== generation) return
    saveError.value = '配對儲存失敗。已保留你的選擇，請再試一次。'
    emit('error', error)
  } finally {
    if (!disposed && busyId.value === review.id) busyId.value = ''
  }
}
function timestamp(value: string) {
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return value
  return new Intl.DateTimeFormat('zh-TW', { timeZone: props.timeZone, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(instant)
}
function sportLabel(sport: string) {
  if (['trail_run', 'trail_running'].includes(sport)) return '越野跑'
  if (['track_run', 'track_running'].includes(sport)) return '田徑場跑步'
  if (['treadmill_run', 'treadmill_running', 'indoor_running'].includes(sport)) return '室內跑步'
  if (['virtual_run', 'virtual_running'].includes(sport)) return '虛擬跑步'
  return '跑步'
}
function summary(seconds: number, meters: number) {
  return `${Math.round(seconds / 60)} 分鐘 · ${(meters / 1000).toFixed(2)} 公里`
}
function workoutLabel(review: SessionReview) {
  const workout = review.candidates.find(item => item.id === review.workout_id)
  return workout ? `${workout.scheduled_for} · ${workout.purpose || workout.workout_type}` : review.workout_id ? '已配對課表' : '課表外活動'
}
</script>

<template>
  <section class="surface-card session-reviews" aria-label="活動與課表確認" :aria-busy="loading || Boolean(busyId)">
    <div class="section-heading"><div><p class="section-label">跑後確認</p><h3>活動與課表</h3></div></div>
    <p class="inline-note">只可確認或修正最近 7 天的活動（含今天）。</p>
    <p v-if="loading" role="status">正在載入活動紀錄…</p>
    <div v-if="loadError"><p class="field-error" role="alert">{{ loadError }}</p><AppButton :busy="loading" @click="load">重新載入</AppButton></div>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="saveError" class="field-error" role="alert">{{ saveError }}</p>
    <p v-if="!loading && !loadError && !buckets[0].items.length" class="inline-note">目前沒有需要確認的活動。</p>
    <template v-for="bucket in buckets" :key="String(bucket.history)">
      <component :is="bucket.history ? 'details' : 'div'" v-if="bucket.items.length" class="session-reviews__list">
        <summary v-if="bucket.history">已確認與課表外活動（{{ bucket.items.length }}）· 可修正</summary>
        <article v-for="review in bucket.items" :key="review.id" class="session-reviews__item" :aria-label="`${review.local_date} 活動確認`">
          <h4>{{ review.local_date }} · {{ summary(review.duration_seconds, review.distance_meters) }}</h4>
          <p v-if="review.status === 'automatic'">Johnny 已{{ review.activities.length > 1 ? '將這些紀錄合併並' : '' }}配對到課表，這樣正確嗎？</p>
          <p v-else-if="review.status === 'needs_review'">這些紀錄的課表歸屬還不確定，請確認是否同一堂訓練。</p>
          <p v-else>{{ review.status === 'confirmed' ? '已確認配對' : '已確認為課表外活動' }}</p>
          <p>{{ workoutLabel(review) }}</p>
          <ul class="session-reviews__recordings">
            <li v-for="activity in review.activities" :key="activity.id"><time :datetime="activity.started_at">{{ timestamp(activity.started_at) }}</time> · {{ sportLabel(activity.sport_type) }}<br>{{ summary(activity.duration_seconds, activity.distance_meters) }}</li>
          </ul>
          <form v-if="editingId === review.id" novalidate @submit.prevent="save(review, groups)">
            <p class="inline-note">選擇對應課表；若是不同訓練，可先拆成獨立活動。</p>
            <label v-for="(group, index) in groups" :key="index" class="session-reviews__field">
              {{ groups.length > 1 ? `活動 ${index + 1} · ${timestamp(review.activities[index].started_at)}` : '這堂訓練的課表' }}
              <select v-model="group.workout_id" :disabled="Boolean(busyId)">
                <option :value="null">課表外活動</option>
                <option v-if="review.workout_id && !review.candidates.some(item => item.id === review.workout_id)" :value="review.workout_id">目前配對課表</option>
                <option v-for="candidate in review.candidates" :key="candidate.id" :value="candidate.id">{{ candidate.scheduled_for }} · {{ candidate.purpose || candidate.workout_type }}</option>
              </select>
            </label>
            <div class="session-reviews__actions">
              <AppButton v-if="review.activities.length > 1 && groups.length === 1" :disabled="Boolean(busyId)" @click="split(review)">拆成獨立活動</AppButton>
              <AppButton tone="primary" type="submit" :busy="busyId === review.id" :disabled="Boolean(busyId)">儲存配對</AppButton>
              <AppButton :disabled="Boolean(busyId)" @click="editingId = ''; saveError = ''">取消</AppButton>
            </div>
          </form>
          <div v-else class="session-reviews__actions">
            <AppButton v-if="review.status === 'automatic' && review.workout_id" tone="primary" :busy="busyId === review.id" :disabled="Boolean(busyId)" @click="save(review, [{ activity_ids: review.activities.map(item => item.id), workout_id: review.workout_id }])">確認配對</AppButton>
            <AppButton :disabled="Boolean(busyId)" @click="edit(review)">修正配對</AppButton>
            <AppButton v-if="!bucket.history" :disabled="Boolean(busyId)" @click="save(review, [{ activity_ids: review.activities.map(item => item.id), workout_id: null }])">標記為課表外活動</AppButton>
          </div>
        </article>
      </component>
    </template>
  </section>
</template>

<style scoped>
.session-reviews { min-width: 0; }
.session-reviews__list { margin-top: 1rem; }
.session-reviews__item { border-top: 1px solid var(--color-line-mint); padding: 1rem 0; overflow-wrap: anywhere; }
.session-reviews__item h4 { margin: 0; }
.session-reviews__recordings { padding-left: 1.3rem; font-family: var(--font-data); font-size: 0.85rem; }
.session-reviews__recordings li + li { margin-top: 0.6rem; }
.session-reviews__actions { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 0.8rem; }
.session-reviews__field { display: grid; gap: 0.4rem; margin-top: 0.8rem; }
.session-reviews__field select {
  width: 100%; min-width: 0; min-height: 2.75rem; padding: 0.7rem 0.8rem;
  font: inherit; color: var(--color-ink-green); background: var(--color-mint-surface);
  border: 1px solid var(--color-line-mint); border-radius: var(--radius-md); cursor: pointer;
}
.session-reviews__field select:hover { border-color: var(--color-lane-green); }
.session-reviews__field select:focus-visible { outline: 2px solid var(--color-lane-green); outline-offset: 2px; }
.session-reviews__field select:disabled { opacity: 0.65; cursor: wait; }
summary { cursor: pointer; color: var(--color-deep-green); }
summary:hover { color: var(--color-lane-green); }
summary:focus-visible { outline: 2px solid var(--color-lane-green); outline-offset: 4px; }
summary:active { opacity: 0.8; }
</style>
