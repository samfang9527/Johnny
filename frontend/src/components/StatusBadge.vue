<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'info' | 'warning' | 'danger' | 'success'
  }>(),
  {
    tone: 'info',
  },
)
</script>

<template>
  <span class="status-badge" :class="`status-badge--${tone}`">
    <slot />
  </span>
</template>
