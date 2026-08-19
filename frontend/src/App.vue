<script setup lang="ts">
import StatusCard from './components/StatusCard.vue'
import { getApiBaseUrl } from './api/client'

const appName = import.meta.env.VITE_APP_NAME || 'Johnny'
</script>

<template>
  <main class="app-shell">
    <section class="hero">
      <p class="eyebrow">Running Companion</p>
      <h1>{{ appName }}</h1>
      <p class="lead">
        Local foundation for the Johnny MVP: a Vue frontend paired with the FastAPI backend.
      </p>
    </section>

    <section class="grid">
      <StatusCard
        title="Frontend"
        value="Vue + Vite"
        detail="A TypeScript app shell ready for routes, state, and API hooks."
      />
      <StatusCard
        title="Backend API"
        :value="getApiBaseUrl()"
        detail="Default API base URL used by the frontend client."
      />
    </section>
  </main>
</template>
