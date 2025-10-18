<template>
  <section class="space-y-6">
    <header class="flex flex-col gap-2">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-xl font-semibold text-slate-900">1. Naloži dokumentacijo</h2>
        <button class="btn btn-muted text-sm" type="button" @click="restore">Obnovi shranjeno sejo</button>
      </div>
      <p class="text-sm text-slate-600">
        Dodajte projektne PDF dokumente, po želji omejite strani za analizo in izberite občino za privzete metapodatke.
      </p>
    </header>

    <div class="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
      <div>
        <label class="mb-2 block text-sm font-semibold text-slate-700" for="municipality-select">Izbrana občina</label>
        <select
          id="municipality-select"
          class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          :value="store.municipalitySlug"
          @change="onMunicipalityChange"
        >
          <option v-for="municipality in store.municipalities" :key="municipality.slug" :value="municipality.slug">
            {{ municipality.name }}
          </option>
        </select>
      </div>
      <div class="rounded-xl border border-brand-200 bg-brand-50/60 px-4 py-3 text-sm text-brand-800">
        <p class="font-semibold">Namig</p>
        <p>Občina določa privzeto vsebino poročila, vključno z nagovorom in kontaktnimi podatki v Word predlogi.</p>
      </div>
    </div>

    <div>
      <div
        class="rounded-xl border-2 border-dashed border-brand-200 bg-white/80 px-6 py-12 text-center transition-all duration-200"
        :class="{ 'border-brand-500 bg-brand-50 shadow-card': store.isDragging }"
        @dragenter.prevent="store.isDragging = true"
        @dragover.prevent
        @dragleave.prevent="store.isDragging = false"
        @drop.prevent="onDrop"
      >
        <p class="text-base font-semibold text-slate-900">Spustite PDF dokumente ali uporabite gumb</p>
        <p class="text-sm text-slate-500">Podprti so izključno PDF zapisi. Posamezne strani lahko navedete po nalaganju.</p>
        <div class="mt-6 flex justify-center">
          <button class="btn btn-primary" type="button" @click="triggerFileDialog">Dodaj PDF datoteke</button>
        </div>
        <input ref="fileInput" type="file" class="hidden" accept="application/pdf" multiple @change="onFileSelect" />
      </div>
    </div>

    <div class="space-y-3" v-if="store.files.length">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Naloženi dokumenti</h3>
      <ul class="space-y-3">
        <li v-for="item in store.files" :key="item.id" class="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white/90 p-4 shadow-soft md:flex-row md:items-center md:justify-between">
          <div>
            <p class="font-medium text-slate-900">{{ item.file.name }}</p>
            <p class="text-xs text-slate-500">{{ store.formatFileEntrySize(item) }}</p>
          </div>
          <div class="flex flex-col items-start gap-2 md:flex-row md:items-center">
            <label class="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Strani za analizo
              <input
                class="mt-1 w-48 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                :value="store.pageOverrides[item.id]"
                placeholder="npr. 1-4,7"
                @input="(event) => updatePageOverride(item.id, (event.target as HTMLInputElement).value)"
              />
            </label>
            <button class="btn btn-muted text-sm" type="button" @click="store.removeFile(item.id)">Odstrani</button>
          </div>
        </li>
      </ul>
    </div>

    <footer class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-2 text-sm text-slate-500" v-if="store.sessionId">
        <span class="font-medium text-slate-700">Seja:</span>
        <span>{{ store.sessionId }}</span>
      </div>
      <div class="flex flex-wrap gap-3">
        <button class="btn btn-muted" type="button" :disabled="store.isBusy" @click="store.resetAnalysis">Ponastavi</button>
        <button class="btn btn-outline" type="button" :disabled="store.isBusy || !store.files.length" @click="store.extractData">
          Ekstrahiraj ključne podatke
        </button>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';

import { useSessionStore } from '@/stores/sessionStore';

const store = useSessionStore();
const fileInput = ref<HTMLInputElement | null>(null);

function triggerFileDialog() {
  fileInput.value?.click();
}

function onFileSelect(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (files.length) {
    store.appendFiles(files);
  }
  if (input) {
    input.value = '';
  }
}

function onDrop(event: DragEvent) {
  const files = Array.from(event.dataTransfer?.files ?? []);
  if (files.length) {
    store.appendFiles(files);
  }
  store.isDragging = false;
}

function updatePageOverride(id: string, value: string) {
  store.pageOverrides[id] = value;
  store.persistState(true);
}

function restore() {
  store.openSavedModal();
}

function onMunicipalityChange(event: Event) {
  const select = event.target as HTMLSelectElement;
  store.municipalityChanged(select.value);
}
</script>
