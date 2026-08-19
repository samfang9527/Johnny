<script setup lang="ts">
defineProps<{
  title: string
  value: string
  detail: string
}>()
</script>

<template>
  <article class="status-card">
    <p class="status-card__title">{{ title }}</p>
    <h2 class="status-card__value">{{ value }}</h2>
    <p class="status-card__detail">{{ detail }}</p>
  </article>
</template>
