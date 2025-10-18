import { computed, reactive, ref, toRaw, watch } from 'vue';
import { defineStore } from 'pinia';

import type {
  AnalysisResultPayload,
  FileEntry,
  Requirement,
  RequirementResult,
  RequirementRevisionMap,
  SavedSessionRecord,
  StatusMessage
} from '@/types/session';
import type { MunicipalityProfile } from '@/types/global';
import { ensureText, formatFileSize, formatTimestamp, stringId } from '@/utils/format';

interface StatusOption {
  value: string;
  label: string;
}

interface ActionStateMap {
  extract: string;
  run: string;
  save: string;
  reset: string;
  rerunSelected: string;
  rerunNonCompliant: string;
  confirm: string;
  revision: string;
}

interface ActionTimersMap {
  [key: string]: ReturnType<typeof setTimeout> | undefined;
}

interface StoredState {
  sessionId: string;
  municipalitySlug: string;
  eupPairs: Array<{ id: number; eup: string; raba: string; originalEup: string; originalRaba: string }>;
  keyData: Record<string, string>;
  initialKeyData: Record<string, string>;
  metadata: Record<string, string>;
  requirements: Requirement[];
  resultsMap: Record<string, RequirementResult>;
  editableFindings: Record<string, string>;
  editableActions: Record<string, string>;
  initialEditableFindings: Record<string, string>;
  initialEditableActions: Record<string, string>;
  selectedRequirementIds: string[];
  excludedIds: string[];
  requirementRevisions: RequirementRevisionMap;
  latestNonCompliantIds: string[];
  analysisSummary: string;
  downloadReady: boolean;
  downloadHref: string;
  revisionPages: string;
  revisionInfo: string;
  sortOption: string;
}

export const useSessionStore = defineStore('session', () => {
  const appConfig = window.__APP_CONFIG__;
  const municipalities = ref<MunicipalityProfile[]>(appConfig?.municipalities ?? []);
  const municipalitiesIndex = computed<Record<string, MunicipalityProfile>>(() => {
    return municipalities.value.reduce((acc, item) => {
      acc[item.slug] = item;
      return acc;
    }, {} as Record<string, MunicipalityProfile>);
  });

  const defaultMunicipalitySlug = appConfig?.defaultMunicipalitySlug ?? municipalities.value[0]?.slug ?? '';
  const municipalitySlug = ref<string>(
    municipalitiesIndex.value[defaultMunicipalitySlug] ? defaultMunicipalitySlug : municipalities.value[0]?.slug ?? ''
  );

  const files = ref<FileEntry[]>([]);
  const pageOverrides = reactive<Record<string, string>>({});
  const revisionFiles = ref<FileEntry[]>([]);
  const status = ref<StatusMessage>({ type: 'info', message: '' });
  const isBusy = ref(false);
  const busyMessage = ref('');
  const sessionId = ref('');
  const eupPairs = ref<Array<{ id: number; eup: string; raba: string; originalEup: string; originalRaba: string }>>([]);
  const initialKeyData = ref<Record<string, string>>({});
  const keyData = ref<Record<string, string>>({});
  const metadata = ref<Record<string, string>>({ ...(municipalitiesIndex.value[municipalitySlug.value]?.default_metadata ?? {}) });
  const requirements = ref<Requirement[]>([]);
  const resultsMap = ref<Record<string, RequirementResult>>({});
  const editableFindings = ref<Record<string, string>>({});
  const editableActions = ref<Record<string, string>>({});
  const initialEditableFindings = ref<Record<string, string>>({});
  const initialEditableActions = ref<Record<string, string>>({});
  const activeEditorId = ref('');
  const selectedRequirementIds = ref<string[]>([]);
  const excludedIds = ref<string[]>([]);
  const requirementRevisions = ref<RequirementRevisionMap>({});
  const latestNonCompliantIds = ref<string[]>([]);
  const analysisSummary = ref('');
  const downloadReady = ref(false);
  const downloadHref = ref('');
  const revisionPages = ref('');
  const revisionInfo = ref('');
  const savedSessions = ref<SavedSessionRecord[]>([]);
  const savedSessionsLoading = ref(false);
  const showSavedModal = ref(false);
  const highlightedSession = ref<SavedSessionRecord | null>(null);
  const sortOption = ref('default');
  const storageKey = 'mnenja-vue-state';
  const isDragging = ref(false);

  const statusOptions = ref<StatusOption[]>([
    { value: '', label: 'NEZNANO' },
    { value: 'Skladno', label: 'SKLADNA' },
    { value: 'Neskladno', label: 'NESKLADNA' },
    { value: 'Ni relevantno', label: 'NI RELEVANTNO' }
  ]);

  const requirementSortOptions = ref<Array<{ value: string; label: string }>>([
    { value: 'default', label: 'Izvirni vrstni red' },
    { value: 'status-desc', label: 'Neskladne najprej' },
    { value: 'status-asc', label: 'Skladne najprej' }
  ]);

  const statusLabels = reactive<Record<string, string>>({
    '': 'NEZNANO',
    Neznano: 'NEZNANO',
    neznano: 'NEZNANO',
    Skladno: 'SKLADNA',
    skladno: 'SKLADNA',
    Neskladno: 'NESKLADNA',
    neskladno: 'NESKLADNA',
    'Ni relevantno': 'NI RELEVANTNO',
    'ni relevantno': 'NI RELEVANTNO'
  });

  const actionStates = reactive<ActionStateMap>({
    extract: '',
    run: '',
    save: '',
    reset: '',
    rerunSelected: '',
    rerunNonCompliant: '',
    confirm: '',
    revision: ''
  });

  const actionTimers = reactive<ActionTimersMap>({});

  const heroSteps = ref([
    { id: 1, title: 'Naloži dokumente', description: 'Dodajte PDF dokumentacijo.' },
    { id: 2, title: 'Preglej osnutek', description: 'AI pripravi osnutek podatkov.' },
    { id: 3, title: 'Potrdi in deli', description: 'Pripravite končno poročilo.' }
  ]);

  const keyLabels = reactive<Record<string, string>>({
    glavni_objekt: 'OBJEKT (OPIS FUNKCIJE)',
    vrsta_gradnje: 'VRSTA GRADNJE',
    klasifikacija_cc_si: 'CC-SI KLASIFIKACIJA',
    nezahtevni_objekti: 'NEZAHTEVNI OBJEKTI V PROJEKTU',
    enostavni_objekti: 'ENOSTAVNI OBJEKTI V PROJEKTU',
    vzdrzevalna_dela: 'VZDRŽEVALNA DELA / MANJŠA REKONSTRUKCIJA',
    parcela_objekta: 'GRADBENA PARCELA (ŠT.)',
    stevilke_parcel_ko: 'VSE PARCELE IN K.O.',
    velikost_parcel: 'SKUPNA VELIKOST PARCEL',
    velikost_obstojecega_objekta: 'VELIKOST OBSTOJEČEGA OBJEKTA',
    tlorisne_dimenzije: 'NOVE TLORISNE DIMENZIJE',
    gabariti_etaznost: 'NOVI GABARIT/ETAŽNOST',
    faktor_zazidanosti_fz: 'FAKTOR ZAZIDANOSTI (FZ)',
    faktor_izrabe_fi: 'FAKTOR IZRABE (FI)',
    zelene_povrsine: 'ZELENE POVRŠINE (FZP/m²)',
    naklon_strehe: 'NAKLON STREHE',
    kritina_barva: 'KRITINA/BARVA',
    materiali_gradnje: 'MATERIALI GRADNJE (npr. les)',
    smer_slemena: 'SMER SLEMENA',
    visinske_kote: 'VIŠINSKE KOTE (k.p., k.s.)',
    odmiki_parcel: 'ODMIKI OD PARCELNIH MEJ',
    komunalni_prikljucki: 'KOMUNALNI PRIKLJUČKI/OSKRBA'
  });

  const keyFieldList = computed(() => Object.entries(keyLabels).map(([key, label]) => ({ key, label })));

  const showReview = computed(() => Boolean(sessionId.value && eupPairs.value.length > 0));
  const heroActiveStep = computed(() => {
    if (requirements.value.length > 0) {
      return 3;
    }
    if (showReview.value) {
      return 2;
    }
    return 1;
  });

  const sortedRequirements = computed(() => {
    if (sortOption.value === 'default') {
      return requirements.value;
    }

    const items = requirements.value.map((req, index) => ({ req, index }));
    const comparator = (a: { req: Requirement; index: number }, b: { req: Requirement; index: number }) => {
      const weightA = statusWeight(currentStatus(a.req.id));
      const weightB = statusWeight(currentStatus(b.req.id));

      if (sortOption.value === 'status-desc') {
        if (weightA !== weightB) return weightB - weightA;
      } else if (sortOption.value === 'status-asc') {
        if (weightA !== weightB) return weightA - weightB;
      }

      return a.index - b.index;
    };

    return items.sort(comparator).map((item) => item.req);
  });

  const revisionTargetIds = computed(() => {
    if (selectedRequirementIds.value.length) {
      return [...selectedRequirementIds.value];
    }
    return [...latestNonCompliantIds.value];
  });

  function setStatus(type: StatusMessage['type'], message: string) {
    status.value = { type, message };
  }

  function startLoading(message: string) {
    isBusy.value = true;
    busyMessage.value = message;
    setStatus('info', message);
  }

  function stopLoading(type: StatusMessage['type'] = 'info', message = '') {
    isBusy.value = false;
    busyMessage.value = '';
    if (message) {
      setStatus(type, message);
    }
  }

  function setActionState(key: keyof ActionStateMap, state: string, options: { autoClear?: boolean; timeout?: number } = {}) {
    if (!Object.prototype.hasOwnProperty.call(actionStates, key)) {
      return;
    }

    const { autoClear = state === 'success' || state === 'error', timeout = 2200 } = options;
    const existingTimer = actionTimers[key];
    if (existingTimer) {
      clearTimeout(existingTimer);
      actionTimers[key] = undefined;
    }

    actionStates[key] = state;
    if (autoClear && state) {
      actionTimers[key] = setTimeout(() => {
        if (actionStates[key] === state) {
          actionStates[key] = '';
        }
        actionTimers[key] = undefined;
      }, timeout);
    }
  }

  function markActionWorking(key: keyof ActionStateMap) {
    setActionState(key, 'working', { autoClear: false });
  }

  function markActionResult(key: keyof ActionStateMap, state: 'success' | 'error') {
    const valid = state === 'success' ? 'success' : state === 'error' ? 'error' : '';
    if (valid) {
      setActionState(key, valid);
    }
  }

  function municipalityBySlug(slug: string) {
    return municipalitiesIndex.value[slug] ?? null;
  }

  function ensureValidMunicipalitySlug(): string {
    if (municipalityBySlug(municipalitySlug.value)) {
      return municipalitySlug.value;
    }
    const fallback = municipalities.value[0]?.slug ?? defaultMunicipalitySlug;
    municipalitySlug.value = fallback;
    return municipalitySlug.value;
  }

  function municipalityDefaults(slug?: string): Record<string, string> {
    const activeSlug = slug ?? ensureValidMunicipalitySlug();
    const profile = municipalityBySlug(activeSlug);
    return { ...(profile?.default_metadata ?? {}) };
  }

  function applyMunicipalityDefaults(mergeExisting = true) {
    const defaults = municipalityDefaults(municipalitySlug.value);
    metadata.value = mergeExisting ? { ...defaults, ...toRaw(metadata.value) } : { ...defaults };
  }

  function heroStepClass(stepId: number) {
    const active = heroActiveStep.value;
    return {
      active: stepId === active,
      completed: stepId < active
    };
  }

  function statusWeight(value: string): number {
    const normalized = (value || '').toLowerCase();
    if (normalized === 'neskladno') return 3;
    if (normalized === 'ni relevantno') return 2;
    if (normalized === 'skladno') return 1;
    return 0;
  }

  function displayStatus(id: string | number) {
    const key = stringId(id);
    const statusValue = resultsMap.value[key]?.status ?? '';
    return statusLabels[statusValue] ?? statusLabels[''];
  }

  function currentStatus(id: string | number): string {
    const key = stringId(id);
    return resultsMap.value[key]?.status ?? '';
  }

  function updateRequirementStatus(id: string | number, nextStatus: string) {
    const key = stringId(id);
    const entry = ensureResultEntry(key);
    entry.status = nextStatus;
    resultsMap.value = { ...resultsMap.value, [key]: entry };
    latestNonCompliantIds.value = computeNonCompliantIds();
    persistState(true);
  }

  function ensureResultEntry(id: string): RequirementResult {
    const entry = resultsMap.value[id] ?? { id };
    if (!resultsMap.value[id]) {
      resultsMap.value = { ...resultsMap.value, [id]: entry };
    }
    return entry;
  }

  function analysisFinding(id: string | number): string {
    return editableFindings.value[stringId(id)] ?? '';
  }

  function analysisAction(id: string | number): string {
    return editableActions.value[stringId(id)] ?? '';
  }

  function isResultModified(id: string | number) {
    const key = stringId(id);
    return (
      analysisFinding(key) !== (initialEditableFindings.value[key] ?? '') ||
      analysisAction(key) !== (initialEditableActions.value[key] ?? '')
    );
  }

  function applyEditableValuesToResult(id: string, finding: string, action: string) {
    const entry = ensureResultEntry(id);
    entry.obrazlozitev = ensureText(finding);
    entry.predlagani_ukrep = ensureText(action);
    resultsMap.value = { ...resultsMap.value, [id]: entry };
  }

  function prepareEditableResults() {
    const nextEditableFindings: Record<string, string> = {};
    const nextEditableActions: Record<string, string> = {};
    const nextInitialFindings: Record<string, string> = {};
    const nextInitialActions: Record<string, string> = {};
    const allKnownIds = new Set([
      ...Object.keys(resultsMap.value ?? {}),
      ...requirements.value.map((req) => stringId(req.id))
    ]);

    allKnownIds.forEach((key) => {
      if (!key) return;
      const result = resultsMap.value[key] ?? { id: key };
      const finding = ensureText(result.obrazlozitev ?? '');
      const action = ensureText(result.predlagani_ukrep ?? '');
      nextInitialFindings[key] = finding;
      nextInitialActions[key] = action;
      nextEditableFindings[key] = finding;
      nextEditableActions[key] = action;
    });

    initialEditableFindings.value = nextInitialFindings;
    initialEditableActions.value = nextInitialActions;
    editableFindings.value = nextEditableFindings;
    editableActions.value = nextEditableActions;
  }

  function onEditableChange(id: string | number) {
    const key = stringId(id);
    applyEditableValuesToResult(key, editableFindings.value[key], editableActions.value[key]);
    persistState(true);
  }

  function activateEditor(id: string | number) {
    activeEditorId.value = stringId(id);
  }

  function handleEditorBlur(id: string | number) {
    if (activeEditorId.value === stringId(id)) {
      activeEditorId.value = '';
    }
  }

  function toggleRequirementSelection(id: string | number) {
    const key = stringId(id);
    if (!key) return;
    if (selectedRequirementIds.value.includes(key)) {
      selectedRequirementIds.value = selectedRequirementIds.value.filter((item) => item !== key);
    } else {
      selectedRequirementIds.value = [...selectedRequirementIds.value, key];
    }
    persistState(true);
  }

  function toggleRequirementExclusion(id: string | number) {
    const key = stringId(id);
    if (!key) return;
    if (excludedIds.value.includes(key)) {
      excludedIds.value = excludedIds.value.filter((item) => item !== key);
    } else {
      excludedIds.value = [...excludedIds.value, key];
    }
    persistState(true);
  }

  function resetSelection() {
    selectedRequirementIds.value = [];
    persistState(true);
  }

  function resetAnalysis() {
    sessionId.value = '';
    requirements.value = [];
    resultsMap.value = {};
    editableFindings.value = {};
    editableActions.value = {};
    initialEditableFindings.value = {};
    initialEditableActions.value = {};
    selectedRequirementIds.value = [];
    excludedIds.value = [];
    requirementRevisions.value = {};
    latestNonCompliantIds.value = [];
    analysisSummary.value = '';
    downloadReady.value = false;
    downloadHref.value = '';
    revisionFiles.value = [];
    revisionPages.value = '';
    revisionInfo.value = '';
    persistState(true);
  }

  function appendFiles(list: File[]) {
    const pdfFiles = list.filter((file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
    pdfFiles.forEach((file) => {
      files.value.push({ id: `${Date.now()}-${file.name}`, file });
    });
    if (!pdfFiles.length) {
      setStatus('error', 'Dodani morajo biti PDF dokumenti.');
    }
    persistState(true);
  }

  function removeFile(id: string) {
    files.value = files.value.filter((item) => item.id !== id);
    delete pageOverrides[id];
    persistState(true);
  }

  function appendRevisionFiles(list: File[]) {
    const pdfFiles = list.filter((file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
    pdfFiles.forEach((file) => {
      revisionFiles.value.push({ id: `${Date.now()}-${file.name}`, file });
    });
    if (!pdfFiles.length) {
      setStatus('error', 'Dodani morajo biti PDF dokumenti.');
    }
    persistState(true);
  }

  function removeRevisionFile(id: string) {
    revisionFiles.value = revisionFiles.value.filter((item) => item.id !== id);
    persistState(true);
  }

  function formatFileEntrySize(entry: FileEntry) {
    return formatFileSize(entry.file.size);
  }

  function formatRevisionTimestamp(value?: string) {
    return formatTimestamp(value);
  }

  function preparePairs(eupList: string[] = [], rabaList: string[] = []) {
    eupPairs.value = [];
    const max = Math.max(eupList.length, rabaList.length);
    if (!max) {
      addPair();
      return;
    }

    for (let index = 0; index < max; index += 1) {
      const eup = eupList[index] ?? '';
      const raba = rabaList[index] ?? '';
      eupPairs.value.push({ id: Date.now() + index, eup, raba, originalEup: eup, originalRaba: raba });
    }
  }

  function addPair() {
    eupPairs.value.push({ id: Date.now(), eup: '', raba: '', originalEup: '', originalRaba: '' });
  }

  function removePair(index: number) {
    eupPairs.value.splice(index, 1);
    if (!eupPairs.value.length) {
      addPair();
    }
  }

  function keyFieldModified(key: string) {
    return (keyData.value[key] ?? '').trim() !== (initialKeyData.value[key] ?? '').trim();
  }

  function pairModified(pair: { eup: string; originalEup: string; raba: string; originalRaba: string }) {
    return (
      (pair.eup ?? '').trim() !== (pair.originalEup ?? '').trim() ||
      (pair.raba ?? '').trim() !== (pair.originalRaba ?? '').trim()
    );
  }

  function municipalityChanged(slug: string) {
    municipalitySlug.value = slug;
    applyMunicipalityDefaults(true);
    persistState(true);
  }

  function ensureTextareasResize(elements: NodeListOf<HTMLTextAreaElement>) {
    elements.forEach((textarea) => {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    });
  }

  function computeNonCompliantIds(): string[] {
    return requirements.value
      .filter((req) => currentStatus(req.id).toLowerCase() === 'neskladno')
      .map((req) => stringId(req.id));
  }

  function buildAnalysisSummary(): string {
    const total = requirements.value.length;
    const nonCompliant = latestNonCompliantIds.value.length;
    return `Analiziranih ${total} zahtev. Neskladnih: ${nonCompliant}.`;
  }

  function collectState(): StoredState | null {
    if (!sessionId.value) {
      return null;
    }

    return {
      sessionId: sessionId.value,
      municipalitySlug: municipalitySlug.value,
      eupPairs: eupPairs.value,
      keyData: keyData.value,
      initialKeyData: initialKeyData.value,
      metadata: metadata.value,
      requirements: requirements.value,
      resultsMap: resultsMap.value,
      editableFindings: editableFindings.value,
      editableActions: editableActions.value,
      initialEditableFindings: initialEditableFindings.value,
      initialEditableActions: initialEditableActions.value,
      selectedRequirementIds: selectedRequirementIds.value,
      excludedIds: excludedIds.value,
      requirementRevisions: requirementRevisions.value,
      latestNonCompliantIds: latestNonCompliantIds.value,
      analysisSummary: analysisSummary.value,
      downloadReady: downloadReady.value,
      downloadHref: downloadHref.value,
      revisionPages: revisionPages.value,
      revisionInfo: revisionInfo.value,
      sortOption: sortOption.value
    };
  }

  function persistState(auto = false) {
    const state = collectState();
    if (!state) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(state));
      if (!auto) {
        setStatus('success', 'Spremembe so shranjene lokalno.');
      }
    } catch (error) {
      console.warn('Shranjevanje ni uspelo', error);
    }
  }

  function restoreFromLocal() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const state = JSON.parse(raw) as StoredState;
      if (!state || !state.sessionId) return;

      sessionId.value = state.sessionId;
      municipalitySlug.value = state.municipalitySlug;
      eupPairs.value = state.eupPairs ?? [];
      keyData.value = state.keyData ?? {};
      initialKeyData.value = state.initialKeyData ?? {};
      metadata.value = state.metadata ?? {};
      requirements.value = state.requirements ?? [];
      resultsMap.value = state.resultsMap ?? {};
      editableFindings.value = state.editableFindings ?? {};
      editableActions.value = state.editableActions ?? {};
      initialEditableFindings.value = state.initialEditableFindings ?? {};
      initialEditableActions.value = state.initialEditableActions ?? {};
      selectedRequirementIds.value = state.selectedRequirementIds ?? [];
      excludedIds.value = state.excludedIds ?? [];
      requirementRevisions.value = state.requirementRevisions ?? {};
      latestNonCompliantIds.value = state.latestNonCompliantIds ?? [];
      analysisSummary.value = state.analysisSummary ?? '';
      downloadReady.value = state.downloadReady ?? false;
      downloadHref.value = state.downloadHref ?? '';
      revisionPages.value = state.revisionPages ?? '';
      revisionInfo.value = state.revisionInfo ?? '';
      sortOption.value = state.sortOption ?? 'default';

      ensureValidMunicipalitySlug();
      applyMunicipalityDefaults(true);
      if (!sortOption.value) {
        sortOption.value = 'default';
      }
      setStatus('success', 'Obnovljena je bila lokalno shranjena seja.');
      highlightedSession.value = {
        session_id: state.sessionId,
        project_name: state.metadata?.ime_projekta ?? 'Neimenovan projekt',
        summary: state.analysisSummary ?? '',
        updated_at: undefined,
        source: 'local'
      };
    } catch (error) {
      console.warn('Ni mogoče obnoviti seje', error);
    }
  }

  async function fetchSavedSessions(force = false) {
    if (savedSessionsLoading.value) return;
    savedSessionsLoading.value = true;
    try {
      const response = await fetch('/saved-sessions');
      const data = await response.json();
      savedSessions.value = (data.sessions ?? []).map((session: SavedSessionRecord) => ({ ...session, source: 'remote' }));
      if (savedSessions.value.length && (!highlightedSession.value || highlightedSession.value.source === 'local')) {
        highlightedSession.value = savedSessions.value[0];
      }
    } catch (error) {
      console.warn('Ne morem pridobiti shranjenih sej', error);
    } finally {
      savedSessionsLoading.value = false;
    }
  }

  function openSavedModal() {
    showSavedModal.value = true;
    fetchSavedSessions(true);
  }

  async function extractData() {
    if (!files.value.length) {
      setStatus('error', 'Prosim naložite vsaj eno PDF datoteko.');
      return;
    }

    markActionWorking('extract');
    const formData = new FormData();
    const manifest = files.value.map((item) => ({ name: item.file.name, pages: (pageOverrides[item.id] ?? '').trim() }));
    files.value.forEach((item) => formData.append('pdf_files', item.file));
    formData.append('files_meta_json', JSON.stringify(manifest));
    formData.append('municipality_slug', ensureValidMunicipalitySlug());

    startLoading('Analiziram dokumente in pripravljam podatke...');
    try {
      const response = await fetch('/extract-data', { method: 'POST', body: formData });
      if (!response.ok) {
        const errorPayload = await response.json();
        throw new Error(errorPayload.detail ?? 'Napaka pri ekstrakciji.');
      }

      const data = await response.json();
      sessionId.value = data.session_id;
      if (data.municipality_slug) {
        municipalitySlug.value = data.municipality_slug;
      }
      ensureValidMunicipalitySlug();
      preparePairs(data.eup, data.namenska_raba);
      prepareKeyData(data);
      requirements.value = [];
      resultsMap.value = {};
      prepareEditableResults();
      downloadReady.value = false;
      downloadHref.value = '';
      persistState(true);
      markActionResult('extract', 'success');
      stopLoading('success', 'Ekstrakcija uspešna. Preglejte predloge in nadaljujte.');
    } catch (error: any) {
      markActionResult('extract', 'error');
      stopLoading('error', error?.message ?? 'Napaka pri ekstrakciji.');
    }
  }

  function prepareKeyData(data: Record<string, any>) {
    initialKeyData.value = {};
    keyData.value = {};
    Object.keys(keyLabels).forEach((key) => {
      const val = data[key] ?? 'Ni podatka v dokumentaciji';
      initialKeyData.value[key] = val;
      keyData.value[key] = val;
    });

    const defaults = municipalityDefaults(data.municipality_slug ?? municipalitySlug.value);
    const metadataKeys = [
      'investitor',
      'investitor_naslov',
      'investitor1_ime',
      'investitor1_naslov',
      'ime_projekta',
      'stevilka_projekta',
      'datum_projekta',
      'projektant',
      'kratek_opis',
      'mnenjedajalec',
      'mnenjedajalec_naziv',
      'mnenjedajalec_naslov',
      'postopek_vodil',
      'odgovorna_oseba',
      'izdelovalec_porocila',
      'predpisi',
      'stevilka_porocila',
      'pvo_status'
    ];

    const nextMetadata: Record<string, string> = { ...defaults };
    metadataKeys.forEach((key) => {
      if (data[key] !== undefined && data[key] !== null) {
        nextMetadata[key] = data[key];
      }
    });

    if (!nextMetadata.investitor1_ime && nextMetadata.investitor) {
      nextMetadata.investitor1_ime = nextMetadata.investitor;
    }

    if (!nextMetadata.investitor1_naslov && nextMetadata.investitor_naslov) {
      nextMetadata.investitor1_naslov = nextMetadata.investitor_naslov;
    }

    metadata.value = nextMetadata;
  }

  async function runAnalysis(extra: { selectedIds?: string[]; actionKey?: keyof ActionStateMap; isRerun?: boolean } = {}) {
    if (!sessionId.value) {
      setStatus('error', 'Seja ni aktivna.');
      return;
    }

    const actionKey = extra.actionKey ?? (extra.isRerun ? (extra.selectedIds?.length === latestNonCompliantIds.value.length ? 'rerunNonCompliant' : 'rerunSelected') : 'run');
    markActionWorking(actionKey);

    const payload = {
      session_id: sessionId.value,
      final_eup_list: eupPairs.value.map((pair) => (pair.eup ?? '').trim()).filter(Boolean),
      final_raba_list: eupPairs.value.map((pair) => (pair.raba ?? '').trim()).filter(Boolean),
      key_data: { ...keyData.value },
      selected_ids: extra.selectedIds ?? [],
      existing_results_map: resultsMap.value ?? {}
    };
    downloadReady.value = false;
    downloadHref.value = '';
    startLoading(extra.isRerun ? 'Ponovno preverjam izbrane zahteve...' : 'Izvajam podrobno analizo...');
    try {
      const response = await fetch('/analyze-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail ?? 'Napaka pri analizi.');
      }

      const result: AnalysisResultPayload = await response.json();
      resultsMap.value = normalizeResultsMap(result.results_map ?? {});
      requirements.value = Array.isArray(result.zahteve) ? result.zahteve : [];
      prepareEditableResults();
      requirementRevisions.value = result.requirement_revisions ?? {};
      latestNonCompliantIds.value = computeNonCompliantIds();
      analysisSummary.value = buildAnalysisSummary();
      selectedRequirementIds.value = [...latestNonCompliantIds.value];
      persistState(true);
      markActionResult(actionKey, 'success');
      stopLoading('success', 'Analiza zaključena.');
    } catch (error: any) {
      markActionResult(actionKey, 'error');
      stopLoading('error', error?.message ?? 'Napaka pri analizi.');
    }
  }

  function normalizeResultsMap(data: Record<string, RequirementResult>): Record<string, RequirementResult> {
    const normalized: Record<string, RequirementResult> = {};
    if (data && typeof data === 'object') {
      Object.entries(data).forEach(([key, value]) => {
        const safeKey = stringId(value?.id ?? key);
        normalized[safeKey] = value && typeof value === 'object' ? { ...value, id: safeKey } : { id: safeKey };
      });
    }
    return normalized;
  }

  async function rerunNonCompliant() {
    const ids = [...latestNonCompliantIds.value];
    if (!ids.length) return;
    runAnalysis({ selectedIds: ids, actionKey: 'rerunNonCompliant', isRerun: true });
  }

  async function rerunSelected() {
    const ids = [...selectedRequirementIds.value];
    if (!ids.length) return;
    runAnalysis({ selectedIds: ids, actionKey: 'rerunSelected', isRerun: true });
  }

  async function saveProgress() {
    const state = collectState();
    if (!state) {
      markActionResult('save', 'error');
      setStatus('error', 'Seja ni aktivna.');
      return;
    }

    markActionWorking('save');
    persistState();
    startLoading('Shranjujem analizo...');

    try {
      const response = await fetch('/save-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: state.sessionId,
          data: state,
          project_name: state.metadata?.ime_projekta ?? undefined,
          summary: analysisSummary.value || undefined
        })
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = result?.detail ?? result?.message ?? 'Shranjevanje ni uspelo.';
        throw new Error(message);
      }

      if (result?.session_id) {
        highlightedSession.value = {
          session_id: result.session_id,
          project_name: result.project_name ?? 'Neimenovan projekt',
          summary: result.summary ?? '',
          source: 'remote'
        };
      }

      await fetchSavedSessions(true);
      markActionResult('save', 'success');
      stopLoading('success', 'Analiza je shranjena.');
    } catch (error: any) {
      markActionResult('save', 'error');
      stopLoading('error', error?.message ?? 'Shranjevanje ni uspelo.');
    }
  }

  async function loadSession(id: string) {
    startLoading('Nalagam shranjeno analizo...');
    try {
      const response = await fetch(`/saved-sessions/${id}`);
      const record = await response.json();
      if (!record || !record.data) {
        throw new Error('Shranjena analiza je prazna.');
      }
      localStorage.setItem(storageKey, JSON.stringify(record.data));
      showSavedModal.value = false;
      stopLoading('success', 'Naloženo.');
      restoreFromLocal();
    } catch (error: any) {
      stopLoading('error', error?.message ?? 'Nalaganje ni uspelo.');
    }
  }

  async function deleteSession(id: string) {
    try {
      await fetch(`/saved-sessions/${id}`, { method: 'DELETE' });
      await fetchSavedSessions(true);
      setStatus('success', 'Analiza izbrisana.');
    } catch (error) {
      setStatus('error', 'Brisanje ni uspelo.');
    }
  }

  function restoreHighlighted() {
    if (!highlightedSession.value) return;
    if (highlightedSession.value.source === 'remote') {
      loadSession(highlightedSession.value.session_id);
    } else {
      restoreFromLocal();
    }
  }

  function discardHighlighted() {
    localStorage.removeItem(storageKey);
    if (highlightedSession.value?.source === 'remote') {
      deleteSession(highlightedSession.value.session_id);
    } else {
      setStatus('success', 'Lokalna seja odstranjena.');
    }
    highlightedSession.value = savedSessions.value.length ? savedSessions.value[0] : null;
  }

  async function submitRevision() {
    if (!sessionId.value) {
      setStatus('error', 'Seja ni aktivna.');
      return;
    }
    if (!revisionFiles.value.length || !revisionTargetIds.value.length) {
      setStatus('error', 'Dodajte popravljene dokumente in izberite zahteve.');
      return;
    }

    markActionWorking('revision');
    startLoading('Nalagam popravljeno dokumentacijo...');
    try {
      const formData = new FormData();
      revisionFiles.value.forEach((item) => formData.append('revision_files', item.file));
      formData.append('session_id', sessionId.value);
      formData.append('revision_note', revisionInfo.value ?? '');
      formData.append('target_ids', JSON.stringify(revisionTargetIds.value));

      const response = await fetch('/upload-revision', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail ?? 'Pošiljanje popravkov ni uspelo.');
      }

      revisionFiles.value = [];
      revisionInfo.value = '';
      markActionResult('revision', 'success');
      stopLoading('success', 'Popravki naloženi.');
    } catch (error: any) {
      markActionResult('revision', 'error');
      stopLoading('error', error?.message ?? 'Pošiljanje popravkov ni uspelo.');
    }
  }

  async function confirmReport() {
    if (!sessionId.value) {
      setStatus('error', 'Seja ni aktivna.');
      return;
    }

    markActionWorking('confirm');
    startLoading('Pripravljam končno poročilo...');
    try {
      const payload = {
        session_id: sessionId.value,
        excluded_ids: excludedIds.value,
        metadata: metadata.value,
        key_data: keyData.value,
        results_map: resultsMap.value
      };

      const response = await fetch('/confirm-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail ?? 'Generiranje poročila ni uspelo.');
      }

      const result = await response.json();
      downloadReady.value = true;
      downloadHref.value = result?.download_url ?? '';
      markActionResult('confirm', 'success');
      stopLoading('success', 'Poročilo je pripravljeno.');
    } catch (error: any) {
      markActionResult('confirm', 'error');
      stopLoading('error', error?.message ?? 'Generiranje poročila ni uspelo.');
    }
  }

  watch(sortOption, () => persistState(true));

  ensureValidMunicipalitySlug();
  applyMunicipalityDefaults(true);
  restoreFromLocal();
  fetchSavedSessions();

  return {
    municipalities,
    municipalitySlug,
    files,
    pageOverrides,
    revisionFiles,
    status,
    isBusy,
    busyMessage,
    sessionId,
    eupPairs,
    initialKeyData,
    keyData,
    metadata,
    requirements,
    resultsMap,
    editableFindings,
    editableActions,
    initialEditableFindings,
    initialEditableActions,
    activeEditorId,
    selectedRequirementIds,
    excludedIds,
    requirementRevisions,
    latestNonCompliantIds,
    analysisSummary,
    downloadReady,
    downloadHref,
    revisionPages,
    revisionInfo,
    savedSessions,
    savedSessionsLoading,
    showSavedModal,
    highlightedSession,
    sortOption,
    statusOptions,
    requirementSortOptions,
    statusLabels,
    actionStates,
    heroSteps,
    keyLabels,
    keyFieldList,
    showReview,
    heroActiveStep,
    sortedRequirements,
    revisionTargetIds,
    isDragging,
    municipalitiesIndex,
    setStatus,
    startLoading,
    stopLoading,
    markActionWorking,
    markActionResult,
    ensureValidMunicipalitySlug,
    municipalityDefaults,
    applyMunicipalityDefaults,
    heroStepClass,
    statusWeight,
    displayStatus,
    currentStatus,
    updateRequirementStatus,
    ensureResultEntry,
    analysisFinding,
    analysisAction,
    isResultModified,
    prepareEditableResults,
    onEditableChange,
    activateEditor,
    handleEditorBlur,
    toggleRequirementSelection,
    toggleRequirementExclusion,
    resetSelection,
    resetAnalysis,
    appendFiles,
    removeFile,
    appendRevisionFiles,
    removeRevisionFile,
    formatFileEntrySize,
    formatRevisionTimestamp,
    preparePairs,
    addPair,
    removePair,
    keyFieldModified,
    pairModified,
    municipalityChanged,
    ensureTextareasResize,
    computeNonCompliantIds,
    buildAnalysisSummary,
    collectState,
    persistState,
    restoreFromLocal,
    fetchSavedSessions,
    openSavedModal,
    extractData,
    prepareKeyData,
    runAnalysis,
    normalizeResultsMap,
    rerunNonCompliant,
    rerunSelected,
    saveProgress,
    loadSession,
    deleteSession,
    restoreHighlighted,
    discardHighlighted,
    submitRevision,
    confirmReport
  };
});
