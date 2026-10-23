<script setup lang="ts">
import { computed } from 'vue'
import type { CoachingAnalysis } from '../types'

const props = defineProps<{
  analysis: CoachingAnalysis
  freshness: string
  kind: 'daily_review' | 'workout_advice'
  evidenceTargets?: Array<{ ref: string; activityId: string; analysisId: string | null }>
}>()
const emit = defineEmits<{
  openEvidence: [target: { activityId: string; analysisId: string | null }]
  openRecommendation: [id: string]
}>()
const findings = computed(() => props.analysis.findings.slice(0, 3))
const actions = computed(() => props.analysis.actions.slice(0, 3))
function targetFor(refs: string[]) {
  return props.evidenceTargets?.find(target => refs.includes(target.ref))
}
</script>

<template>
  <div class="coaching-analysis" data-testid="coaching-analysis" :data-kind="kind">
    <p v-if="freshness === 'stale'" class="coaching-analysis__status" role="status">資料已更新，這是產生當時的判斷。</p>
    <p v-if="analysis.analysis_mode === 'rules'" class="coaching-analysis__mode">規則產生</p>
    <h4 class="coaching-analysis__headline">{{ analysis.headline }}</h4>
    <p class="coaching-analysis__summary">{{ analysis.summary }}</p>
    <div v-if="findings.length" class="coaching-analysis__findings">
      <div v-for="(finding, index) in findings" :key="`${index}-${finding.observation}`" class="coaching-analysis__finding">
        <p>{{ finding.interpretation }}</p>
        <button v-if="targetFor(finding.evidence_refs)" type="button" class="coaching-analysis__link" data-testid="open-evidence"
          @click="emit('openEvidence', { activityId: targetFor(finding.evidence_refs)!.activityId, analysisId: targetFor(finding.evidence_refs)!.analysisId })">查看活動分段證據</button>
      </div>
    </div>
    <ul v-if="actions.length" class="coaching-analysis__actions">
      <li v-for="action in actions" :key="action.action_id + action.text">
        <span>{{ action.text }}</span>
        <button v-if="action.recommendation_id && freshness === 'current'" type="button" class="coaching-analysis__link" data-testid="open-recommendation"
          @click="emit('openRecommendation', action.recommendation_id)">查看待決定調整</button>
      </li>
    </ul>
    <details v-if="findings.length || analysis.limitations.length" class="coaching-analysis__details">
      <summary>判斷依據與限制</summary>
      <ul><li v-for="(finding, index) in findings" :key="index">{{ finding.observation }}</li></ul>
      <p v-for="(limit, index) in analysis.limitations" :key="index">{{ limit }}</p>
    </details>
  </div>
</template>
