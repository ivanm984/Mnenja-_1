<template>
  <section class="surface-card px-6 py-8">
    <div class="grid gap-6 lg:grid-cols-[1.6fr_1fr] lg:gap-10">
      <div class="space-y-4">
        <p class="text-sm font-semibold uppercase tracking-wide text-brand-600">Letno poročilo {{ year }}</p>
        <h1 class="text-3xl font-bold leading-tight sm:text-4xl">
          Avtomatizirana priprava mnenj o skladnosti s prostorskimi akti
        </h1>
        <p class="text-base leading-relaxed text-slate-600">
          Naložite projektno dokumentacijo, preverite ključne podatke ter pripravite deljeno poročilo v le nekaj korakih.
          Nova različica uporabniškega vmesnika uporablja modularne komponente, odziven dizajn in ohranja vse napredne možnosti iz obstoječe rešitve.
        </p>
        <div v-if="status.message" :class="statusClass" class="flex items-start justify-between rounded-xl border px-4 py-3 text-sm">
          <span>{{ status.message }}</span>
          <button type="button" class="text-xs font-semibold text-brand-600" @click="dismissStatus">Skrij</button>
        </div>
      </div>
      <ol class="space-y-4">
        <li
          v-for="step in heroSteps"
          :key="step.id"
          class="flex items-start gap-3 rounded-xl border border-slate-200/70 bg-white/80 px-4 py-3 shadow-soft transition-all duration-200"
          :class="heroStepState(step.id)"
        >
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-600">
            {{ step.id }}
          </span>
          <div>
            <p class="font-semibold text-slate-900">{{ step.title }}</p>
            <p class="text-sm text-slate-600">{{ step.description }}</p>
          </div>
        </li>
      </ol>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';

import { useSessionStore } from '@/stores/sessionStore';

const store = useSessionStore();

const year = computed(() => window.__APP_CONFIG__?.year ?? new Date().getFullYear().toString());
const status = computed(() => store.status);
const heroSteps = computed(() => store.heroSteps);

function heroStepState(stepId: number) {
  const state = store.heroStepClass(stepId);
  return {
    'border-brand-400 shadow-card': state.active,
    'border-emerald-400 shadow-card ring-1 ring-emerald-300/50': state.completed
  };
}

const statusClass = computed(() => {
  if (status.value.type === 'success') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (status.value.type === 'error') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  return 'border-brand-200 bg-brand-50 text-brand-700';
});

function dismissStatus() {
  store.setStatus('info', '');
}
</script>
