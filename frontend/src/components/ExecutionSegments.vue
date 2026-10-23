<script setup lang="ts">
import type { ActivityExecutionResponse } from '../types'

defineProps<{ execution: ActivityExecutionResponse }>()
const mapping = { exact: '課表段落已確認', estimated: '推估配對', unmatched: '尚未配對課表' }
const coverage = { complete: '完整涵蓋', partial: '部分涵蓋', unknown: '涵蓋範圍未知' }
const precision = { recorded: '原始記錄', sampled: '圖表抽樣', unknown: '精度未知' }
const channelLabels: Record<string, string> = {
  heart_rate: '心率', pace: '配速', speed: '速度', distance: '距離', cadence: '步頻',
  elevation: '海拔', power: '功率', timer: '計時',
}
function missingChannelLabel(channel: string): string {
  return channelLabels[channel] ?? channel.replace(/_/g, ' ')
}
function duration(seconds: number | null): string {
  return seconds == null ? '時間不詳' : `${Math.round(seconds / 60)} 分鐘`
}
</script>

<template>
  <div class="execution-segments" data-testid="execution-segments">
    <p v-if="execution.freshness === 'stale'" class="johnny-stream__meta">這是當時分析使用的資料；目前細節已有更新。</p>
    <p v-if="!execution.analysis" class="johnny-stream__meta">這項活動尚無可用的分段分析。</p>
    <template v-else>
      <p class="execution-segments__mapping">{{ mapping[execution.analysis.mapping] }}</p>
      <ul v-if="execution.analysis.findings.length" class="execution-segments__findings">
        <li v-for="(finding, index) in execution.analysis.findings" :key="index"><strong>{{ finding.supports }}</strong><span>{{ finding.does_not_support }}</span></li>
      </ul>
      <div v-for="detail in execution.used_details" :key="detail.snapshot_id" class="execution-segments__resource">
        <p class="johnny-stream__meta">{{ detail.resource.toUpperCase() }} · {{ coverage[detail.coverage.state] }} · {{ precision[detail.precision] }}</p>
        <p v-if="detail.coverage.missing_channels.length" class="johnny-stream__meta">缺少{{ detail.coverage.missing_channels.map(missingChannelLabel).join('、') }}，相關判斷僅供參考。</p>
        <ol v-if="detail.segments.length">
          <li v-for="segment in detail.segments" :key="segment.source_index">
            <strong>{{ segment.step_path ? `課表 ${segment.step_path}` : `分段 ${segment.source_index + 1}` }}</strong>
            <span>{{ duration(segment.timer_seconds) }}<template v-if="segment.distance_meters != null"> · {{ Math.round(segment.distance_meters) }} 公尺</template></span>
          </li>
        </ol>
        <p v-else class="johnny-stream__meta">目前沒有可顯示的分段摘要。</p>
      </div>
      <p v-if="!execution.used_details.length" class="johnny-stream__meta">分段細節尚未取得；活動摘要仍可用。</p>
    </template>
  </div>
</template>
