<template>
  <section class="space-y-8">
    <header class="space-y-2">
      <h2 class="text-xl font-semibold text-slate-900">2. Preglej ključne podatke</h2>
      <p class="text-sm text-slate-600">
        Uredi izvleček namenske rabe, preveri ključne parametre in dopolni metapodatke, ki se izpišejo v Word poročilu.
      </p>
    </header>

    <div class="space-y-3">
      <div class="flex items-center justify-between gap-3">
        <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Namenska raba in EUP</h3>
        <button class="btn btn-muted text-xs" type="button" @click="addPair">Dodaj par</button>
      </div>
      <div class="grid gap-3 lg:grid-cols-2">
        <div v-for="(pair, index) in store.eupPairs" :key="pair.id" class="rounded-xl border border-slate-200 bg-white/70 p-4 shadow-soft">
          <div class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-slate-600">Par {{ index + 1 }}</p>
            <button class="text-xs font-semibold text-rose-600" type="button" @click="removePair(index)" v-if="store.eupPairs.length > 1">
              Odstrani
            </button>
          </div>
          <label class="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            EUP oznaka
            <input
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              v-model="pair.eup"
              @input="markPairsDirty"
            />
          </label>
          <label class="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            Namenska raba
            <textarea
              class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              rows="2"
              v-model="pair.raba"
              @input="markPairsDirty"
            ></textarea>
          </label>
          <p v-if="store.pairModified(pair)" class="mt-2 text-xs font-semibold text-brand-600">Spremenjeno</p>
        </div>
      </div>
    </div>

    <div class="space-y-4">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Ključni parametri projekta</h3>
      <div class="grid gap-3 md:grid-cols-2">
        <div
          v-for="field in store.keyFieldList"
          :key="field.key"
          class="rounded-xl border border-slate-200 bg-white/70 p-4 shadow-soft"
          :class="{ 'border-brand-400 ring-2 ring-brand-200': store.keyFieldModified(field.key) }"
        >
          <label class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ field.label }}</label>
          <textarea
            class="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            rows="3"
            v-model="store.keyData[field.key]"
            @input="persist"
            ref="keyTextarea"
          ></textarea>
        </div>
      </div>
    </div>

    <div class="space-y-4">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Metapodatki poročila</h3>
      <div class="grid gap-4 md:grid-cols-2">
        <div v-for="(value, key) in store.metadata" :key="key" class="rounded-xl border border-slate-200 bg-white/70 p-4 shadow-soft">
          <label class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ prettify(key) }}</label>
          <textarea class="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" rows="2" v-model="store.metadata[key]" @input="persist"></textarea>
        </div>
      </div>
    </div>

    <footer class="flex flex-wrap items-center justify-between gap-4">
      <p class="text-sm text-slate-500" v-if="store.analysisSummary">{{ store.analysisSummary }}</p>
      <div class="flex flex-wrap gap-3">
        <button class="btn btn-muted" type="button" :disabled="store.isBusy" @click="store.saveProgress">Shrani napredek</button>
        <button class="btn btn-primary" type="button" :disabled="store.isBusy" @click="store.runAnalysis()">Izvedi podrobno analizo</button>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted } from 'vue';

import { useSessionStore } from '@/stores/sessionStore';

const store = useSessionStore();

function persist() {
  store.persistState(true);
  queueResize();
}

function queueResize() {
  nextTick(() => {
    const textareas = document.querySelectorAll<HTMLTextAreaElement>('.surface-card textarea');
    store.ensureTextareasResize(textareas);
  });
}

function addPair() {
  store.addPair();
}

function removePair(index: number) {
  store.removePair(index);
  persist();
}

function markPairsDirty() {
  persist();
}

function prettify(value: string) {
  return value.replace(/_/g, ' ').toUpperCase();
}

onMounted(() => {
  queueResize();
});
</script>
