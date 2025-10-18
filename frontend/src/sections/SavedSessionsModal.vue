<template>
  <teleport to="body">
    <div v-if="store.showSavedModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4 py-6">
      <div class="surface-card max-h-[80vh] w-full max-w-2xl overflow-hidden">
        <header class="flex items-start justify-between gap-3 border-b border-slate-200 px-6 py-4">
          <div>
            <h3 class="text-lg font-semibold text-slate-900">Shranjene analize</h3>
            <p class="text-sm text-slate-500">Izberite nadaljevanje lokalnih ali oddaljenih sej.</p>
          </div>
          <button class="btn btn-muted text-sm" type="button" @click="store.showSavedModal = false">Zapri</button>
        </header>
        <div class="divide-y divide-slate-100 overflow-y-auto">
          <div
            v-for="session in store.savedSessions"
            :key="session.session_id"
            class="flex flex-col gap-2 px-6 py-4 md:flex-row md:items-center md:justify-between"
          >
            <div>
              <p class="font-semibold text-slate-900">{{ session.project_name }}</p>
              <p class="text-sm text-slate-500">{{ session.summary || 'Povzetek ni na voljo.' }}</p>
              <p class="text-xs text-slate-400">Posodobljeno: {{ store.formatRevisionTimestamp(session.updated_at) }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button class="btn btn-outline text-sm" type="button" @click="() => store.loadSession(session.session_id)">
                Naloži sejo
              </button>
              <button class="btn btn-muted text-sm" type="button" @click="() => store.deleteSession(session.session_id)">
                Izbriši
              </button>
            </div>
          </div>
        </div>
        <footer class="flex items-center justify-between gap-3 border-t border-slate-200 px-6 py-4">
          <div>
            <p v-if="store.highlightedSession" class="text-sm text-slate-600">
              <span class="font-semibold text-slate-800">Poudarjena seja:</span>
              {{ store.highlightedSession.project_name }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button class="btn btn-outline text-sm" type="button" @click="store.restoreHighlighted" :disabled="!store.highlightedSession">
              Obnovi označeno
            </button>
            <button class="btn btn-muted text-sm" type="button" @click="store.discardHighlighted" :disabled="!store.highlightedSession">
              Odstrani označeno
            </button>
          </div>
        </footer>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/sessionStore';

const store = useSessionStore();
</script>
