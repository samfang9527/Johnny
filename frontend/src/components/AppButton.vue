<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'primary' | 'neutral' | 'warning' | 'danger'
    type?: 'button' | 'submit'
    busy?: boolean
    disabled?: boolean
  }>(),
  {
    tone: 'neutral',
    type: 'button',
    busy: false,
    disabled: false,
  },
)
</script>

<template>
  <button class="app-button" :class="`app-button--${tone}`" :type="type" :disabled="disabled || busy">
    <span class="app-button__content" :class="{ 'app-button__content--busy': busy }">
      <slot />
    </span>
    <span v-if="busy" class="app-button__busy" aria-hidden="true">處理中</span>
  </button>
</template>
