<script setup lang="ts">
import { computed } from 'vue'
import type { DailyAdvice } from '../types'

const props = defineProps<{ advice: DailyAdvice; timeZone: string }>()

const hasContent = computed(() => Boolean(props.advice.weekSummary && props.advice.todayExecution && props.advice.workoutGuide))
const timeLabel = computed(() => {
  if (!props.advice.generatedAt) return ''
  const instant = new Date(props.advice.generatedAt)
  if (Number.isNaN(instant.getTime())) return ''
  try {
    return new Intl.DateTimeFormat('zh-TW', {
      timeZone: props.timeZone,
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(instant)
  } catch {
    return ''
  }
})
const modeLabels: Record<string, string> = {
  follow_plan: '照計畫執行', ease_off: '保守執行', rest: '今天休息', completed: '今天已完成',
}
const modeLabel = computed(() => modeLabels[props.advice.executionMode ?? ''] ?? '')
const stateMessage = computed(() => {
  if (props.advice.state === 'no_plan') return '今天沒有可用的訓練計畫。請先確認課表日期。'
  if (props.advice.state === 'sync_failed') return '活動同步失敗。請到「資料」檢查連接後再試一次。'
  if (props.advice.state === 'generation_failed') return '建議更新失敗。請稍後重新同步資料。'
  if (props.advice.state === 'pending') return '正在更新今天的建議。'
  return ''
})
</script>

<template>
  <article class="daily-advice-card surface-card" aria-label="Johnny 今日建議" aria-live="polite">
    <div class="daily-advice-card__heading">
      <div>
        <p class="section-label">Johnny 今日建議</p>
        <h3>{{ modeLabel || '今天的訓練提醒' }}</h3>
      </div>
      <span v-if="advice.planWeek" class="daily-advice-card__week">{{ advice.planWeek.startsOn }}–{{ advice.planWeek.endsOn }}</span>
    </div>
    <p v-if="stateMessage" class="daily-advice-card__notice" :class="{ 'daily-advice-card__notice--warning': advice.state !== 'pending' }" role="status">{{ stateMessage }}</p>
    <p v-if="advice.dataFreshness === 'stale' && hasContent" class="daily-advice-card__notice daily-advice-card__notice--warning">以下是先前建議，資料可能已過時。</p>
    <p v-else-if="advice.dataFreshness === 'limited' && hasContent" class="daily-advice-card__notice">資料有限；建議以目前可用的活動紀錄與課表為準。</p>
    <p v-if="timeLabel" class="daily-advice-card__time">{{ advice.dataFreshness === 'stale' ? '先前產生' : '更新時間' }} · {{ timeLabel }}</p>
    <div v-if="hasContent" class="daily-advice-card__sections">
      <section>
        <h4>本週執行回顧</h4>
        <p>{{ advice.weekSummary }}</p>
      </section>
      <section>
        <h4>今天怎麼執行</h4>
        <p>{{ advice.todayExecution }}</p>
      </section>
      <section>
        <h4>這堂課的重點</h4>
        <p>{{ advice.workoutGuide?.purpose }}</p>
        <dl class="daily-advice-card__guide">
          <div><dt>跑完的感覺</dt><dd>{{ advice.workoutGuide?.expectedFeel }}</dd></div>
          <div><dt>如果太吃力</dt><dd>{{ advice.workoutGuide?.ifTooHard }}</dd></div>
          <div><dt>如果太輕鬆</dt><dd>{{ advice.workoutGuide?.ifTooEasy }}</dd></div>
        </dl>
      </section>
    </div>
  </article>
</template>
