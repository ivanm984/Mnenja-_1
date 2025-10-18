<template>
  <aside class="space-y-6">
    <header class="space-y-2">
      <h3 class="text-lg font-semibold text-slate-900">Akcije rezultatov</h3>
      <p class="text-sm text-slate-600">Ponovno poženi analizo, naloži popravke ali prenesi končno poročilo.</p>
    </header>

    <section class="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-soft">
      <h4 class="text-sm font-semibold text-slate-800">Popravljena dokumentacija</h4>
      <p class="mt-1 text-xs text-slate-500">
        Dodajte popravljene PDF datoteke in označite zahteve, ki jih želite ponovno preveriti. Če nič ne izberete, bomo uporabili zadnje neskladne.
      </p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button class="btn btn-muted text-sm" type="button" @click="triggerRevisionDialog">Dodaj popravek (PDF)</button>
        <input ref="revisionInput" type="file" class="hidden" accept="application/pdf" multiple @change="onRevisionSelect" />
      </div>
      <ul class="mt-4 space-y-3" v-if="store.revisionFiles.length">
        <li v-for="item in store.revisionFiles" :key="item.id" class="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white/80 px-3 py-2 text-sm">
          <div>
            <p class="font-medium text-slate-800">{{ item.file.name }}</p>
            <p class="text-xs text-slate-500">{{ store.formatFileEntrySize(item) }}</p>
          </div>
          <button class="text-xs font-semibold text-rose-600" type="button" @click="store.removeRevisionFile(item.id)">Odstrani</button>
        </li>
      </ul>
      <p v-else class="mt-3 text-xs text-slate-500">Ni naloženih popravkov.</p>
      <label class="mt-4 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        Opomba (neobvezno)
        <textarea class="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" rows="2" v-model="store.revisionInfo" @input="store.persistState(true)"></textarea>
      </label>
      <button class="btn btn-outline mt-4 w-full text-sm" type="button" :disabled="store.isBusy || !store.sessionId || !store.revisionFiles.length || !store.revisionTargetIds.length" @click="store.submitRevision">
        Naloži popravek in ponovno preveri
      </button>
    </section>

    <section class="space-y-3">
      <button class="btn btn-outline w-full" type="button" :disabled="store.isBusy || !store.latestNonCompliantIds.length" @click="store.rerunNonCompliant">
        Analiziraj neskladne
      </button>
      <button class="btn btn-outline w-full" type="button" :disabled="store.isBusy || !store.selectedRequirementIds.length" @click="store.rerunSelected">
        Ponovno preveri izbrane
      </button>
      <button class="btn btn-muted w-full" type="button" :disabled="store.isBusy" @click="store.resetSelection">
        Počisti izbor
      </button>
      <button class="btn btn-muted w-full" type="button" :disabled="store.isBusy || !store.sessionId" @click="store.saveProgress">
        Shrani napredek
      </button>
      <button class="btn btn-primary w-full" type="button" :disabled="store.isBusy || !store.sessionId" @click="store.confirmReport">
        Potrdi in ustvari poročilo
      </button>
      <a v-if="store.downloadReady" class="btn btn-outline w-full text-center" :href="store.downloadHref" download>Prenesi poročilo (.docx)</a>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue';

import { useSessionStore } from '@/stores/sessionStore';

const store = useSessionStore();
const revisionInput = ref<HTMLInputElement | null>(null);

function triggerRevisionDialog() {
  revisionInput.value?.click();
}

function onRevisionSelect(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (files.length) {
    store.appendRevisionFiles(files);
  }
  if (input) {
    input.value = '';
  }
}
</script>
