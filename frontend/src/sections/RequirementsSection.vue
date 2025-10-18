<template>
  <section class="space-y-6">
    <header class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="text-xl font-semibold text-slate-900">3. Rezultati analize</h2>
        <p class="text-sm text-slate-600">Uredite ugotovitve AI, določite statuse posameznih zahtev in pripravite končno poročilo.</p>
      </div>
      <label class="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Razvrsti zahteve
        <select class="mt-1 rounded-lg border border-slate-200 px-3 py-2 text-sm" :value="store.sortOption" @change="onSortChange">
          <option v-for="option in store.requirementSortOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
    </header>

    <p v-if="!store.sortedRequirements.length" class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
      Rezultati še niso na voljo. Po ekstrakciji podatkov zaženite podrobno analizo.
    </p>

    <div v-else class="space-y-4 requirements-grid">
      <article
        v-for="requirement in store.sortedRequirements"
        :key="requirement.id"
        class="rounded-xl border border-slate-200 bg-white/80 p-5 shadow-soft"
      >
        <div class="flex flex-col gap-4 md:flex-row md:justify-between">
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-3">
              <label class="inline-flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" class="h-4 w-4 rounded border-slate-300" :checked="store.selectedRequirementIds.includes(stringId(requirement.id))" @change="() => store.toggleRequirementSelection(requirement.id)" />
                Izberi
              </label>
              <span class="status-chip" :data-status="store.currentStatus(requirement.id)">
                {{ store.displayStatus(requirement.id) }}
              </span>
              <select
                class="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                :value="store.currentStatus(requirement.id)"
                @change="(event) => store.updateRequirementStatus(requirement.id, (event.target as HTMLSelectElement).value)"
              >
                <option v-for="option in store.statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
            <h3 class="text-lg font-semibold text-slate-900">{{ requirement.naslov || 'Neimenovana zahteva' }}</h3>
            <div class="text-xs uppercase tracking-wide text-slate-500">
              <span v-if="requirement.clen">Člen {{ requirement.clen }}</span>
              <span v-if="requirement.skupina"> • {{ requirement.skupina }}</span>
              <span v-if="requirement.kategorija"> • {{ requirement.kategorija }}</span>
            </div>
            <p class="text-sm text-slate-600 whitespace-pre-wrap">{{ requirement.besedilo || 'Ni dodatnega besedila.' }}</p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <button class="btn btn-muted text-xs" type="button" @click="store.toggleRequirementExclusion(requirement.id)">
              {{ store.excludedIds.includes(stringId(requirement.id)) ? 'Vključi v poročilo' : 'Izloči iz poročila' }}
            </button>
            <p v-if="store.requirementRevisions[stringId(requirement.id)]" class="text-xs text-brand-600">Na voljo so popravki ({{ store.requirementRevisions[stringId(requirement.id)].length }})</p>
          </div>
        </div>

        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <p class="text-sm font-semibold text-slate-700">AI ugotovitve</p>
              <span v-if="store.isResultModified(requirement.id)" class="text-xs font-semibold text-brand-600">Ročno urejeno</span>
            </div>
            <textarea
              class="min-h-[120px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              v-model="store.editableFindings[stringId(requirement.id)]"
              @input="() => store.onEditableChange(requirement.id)"
            ></textarea>
          </div>
          <div class="space-y-2">
            <p class="text-sm font-semibold text-slate-700">Predlagani ukrepi</p>
            <textarea
              class="min-h-[120px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              v-model="store.editableActions[stringId(requirement.id)]"
              @input="() => store.onEditableChange(requirement.id)"
            ></textarea>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/sessionStore';
import { stringId } from '@/utils/format';

const store = useSessionStore();

function onSortChange(event: Event) {
  const select = event.target as HTMLSelectElement;
  store.sortOption = select.value;
}
</script>
