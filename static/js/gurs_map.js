// GURS Zemljevid JavaScript - POPOLNA VERZIJA 2.5 (Debug koordinate markerjev, preverjanje gumbov)

let map;
let baseLayerMap = new Map();
let overlayLayerMap = new Map();
let dynamicLayerMap = new Map();
let vectorLayer;
let katastrLayer;
let katastrStevilkeLayer;
let currentParcels = [];
let selectedParcel = null;
let sessionId = null;
let mapConfig = {
    defaultCenter: [14.8267, 46.0569],
    defaultZoom: 14,
    wmsUrl: 'https://ipi.eprostor.gov.si/wms-si-gurs-kn/wms',
    rasterWmsUrl: 'https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms',
    rpeWmsUrl: 'https://ipi.eprostor.gov.si/wms-si-gurs-rpe/wms',
    base_layers: [], // Uporabljamo podčrtaj
    overlay_layers: [] // Uporabljamo podčrtaj
};
let savedMapState = null;
let mapStateTimer = null;

const LAYER_ICONS = { ortofoto: '📷', namenska_raba: '🏘️', katastr: '📐', katastr_stevilke: '#️⃣', stavbe: '🏢' };

DocumentReady(async () => {
    console.log('🚀 Inicializacija GURS zemljevida v2.5...');
    if (typeof ol === 'undefined') { console.error('❌ OpenLayers ni naložen!'); alert('Napaka: OpenLayers knjižnica ni naložena.'); return; }
    console.log('✅ OpenLayers naložen, verzija:', ol.VERSION || 'unknown');
    const urlParams = new URLSearchParams(window.location.search); sessionId = urlParams.get('session_id');
    await loadMapConfig();
    initMap();
    if (map) {
        registerMapInteractions();
        buildLayerSelectors();
        await loadSessionParcels();
        setupWmsCatalogToggle();
        setupSearchInputEnter();
        console.log("✅ Vsi elementi zemljevida inicializirani v2.5.");
    } else {
        console.error("❌❌❌ Inicializacija zemljevida ni uspela v2.5.");
    }
});

function DocumentReady(callback) { if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', callback); } else { callback(); } }

async function loadMapConfig() {
    try {
        const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
        const response = await fetch(`/api/gurs/map-config${query}`);
        if (!response.ok) { throw new Error(`HTTP error! status: ${response.status}`); }
        const data = await response.json();
        if (data.success && data.config) {
            data.config.base_layers = Array.isArray(data.config.base_layers) ? data.config.base_layers : [];
            data.config.overlay_layers = Array.isArray(data.config.overlay_layers) ? data.config.overlay_layers : [];
            mapConfig = { ...mapConfig, ...data.config };
            savedMapState = data.config.saved_state || null;
            console.log('🧭 Map config uspešno naložen:', mapConfig, 'Shranjeno stanje:', savedMapState);
        } else { console.warn('⚠️ Map config API:', data); }
    } catch (error) {
        console.error('❌ Kritična napaka nalaganja Map config:', error);
        console.warn('Uporabljam privzete vrednosti.');
    }
    mapConfig.base_layers = mapConfig.base_layers || [];
    mapConfig.overlay_layers = mapConfig.overlay_layers || [];
    console.log(`Končni mapConfig PRED initMap (po loadMapConfig): Base=${mapConfig.base_layers.length}, Overlay=${mapConfig.overlay_layers.length}`);
}

function initMap() {
    console.log('🗺️ Kreiram zemljevid...');
    const viewCenter = savedMapState?.center || mapConfig.defaultCenter;
    const viewZoom = savedMapState?.zoom || mapConfig.defaultZoom;

    baseLayerMap = new Map(); overlayLayerMap = new Map(); dynamicLayerMap = new Map();
    katastrLayer = null; katastrStevilkeLayer = null;

    const osmLayer = new ol.layer.Tile({ source: new ol.source.OSM(), visible: false });

    const baseLayersOL = [];
    (mapConfig.base_layers || []).forEach(cfg => {
        const layer = createTileLayerFromConfig(cfg);
        if (layer) baseLayersOL.push(layer);
    });

    if (baseLayersOL.length === 0) {
        console.warn("Ni osnovnih slojev, dodajam privzeto ortofoto.");
        const defaultOrto = createTileLayerFromConfig({ id: 'ortofoto', name: 'SI.GURS.ZPDZ:DOF025', title: 'Digitalni ortofoto', url: mapConfig.rasterWmsUrl, format: 'image/jpeg', transparent: false, category: 'base', default_visible: true });
        if (defaultOrto) baseLayersOL.push(defaultOrto);
    }

    const overlayLayersOL = [];
    (mapConfig.overlay_layers || []).forEach(cfg => {
        const layer = createTileLayerFromConfig(cfg);
        if (layer) overlayLayersOL.push(layer);
    });

    if (!overlayLayerMap.has('katastr')) {
        console.warn("Dodajam privzeti sloj za meje (katastr).");
        const l = createTileLayerFromConfig({ id: 'katastr', name: 'SI.GURS.KN:PARCELE', title: 'Parcelne meje', url: mapConfig.wmsUrl, format: 'image/png', transparent: true, category: 'overlay', default_visible: true, always_on: true });
        if (l) overlayLayersOL.push(l);
    }

    katastrLayer = overlayLayerMap.get('katastr');
    katastrStevilkeLayer = overlayLayerMap.get('katastr_stevilke');

    const layers = [osmLayer, ...baseLayersOL, ...overlayLayersOL];

    try {
        map = new ol.Map({
            target: 'map', layers: layers,
            view: new ol.View({ center: ol.proj.fromLonLat(viewCenter), zoom: viewZoom })
        });
        console.log('✅ Zemljevid inicializiran s sloji:', layers.map(l => l.get('name')));
        console.log('📍 Začetni center:', viewCenter, 'zoom:', viewZoom);
        map.on('singleclick', handleMapClick);
    } catch (e) {
        console.error("❌❌❌ Kritična napaka inicializacije Map:", e);
        document.getElementById('map').innerHTML = `<div style="padding: 20px; color: var(--danger);">Napaka zagonu zemljevida: ${e.message}.</div>`;
        map = null;
    }
}

function registerMapInteractions() { if (!map) return; map.on('moveend', scheduleMapStateSave); }

function createTileLayerFromConfig(cfg) {
    if (!cfg || typeof cfg !== 'object' || !cfg.id || !cfg.name || !cfg.url) { console.error("!!! Napačna konfiguracija sloja:", cfg); return null; }
    const { id, name, url, format = 'image/png', transparent = true, default_visible = false, opacity = 1.0, always_on = false, category = 'overlay' } = cfg;
    const visible = default_visible === true;

    try {
        const layer = new ol.layer.Tile({
            source: new ol.source.TileWMS({ url: url, params: { LAYERS: name, TILED: true, FORMAT: format, TRANSPARENT: transparent, VERSION: '1.3.0' }, crossOrigin: 'anonymous', serverType: 'geoserver' }),
            visible: visible, opacity: opacity, name: id
        });
        layer.getSource().on('tileloaderror', (event) => { console.warn(`⚠️ Napaka tile za ${id} (${name}):`, event?.tile?.src_ || 'neznan vir'); });

        if (category === 'base') {
            baseLayerMap.set(id, layer); layer.setZIndex(baseLayerMap.size);
            console.log(` -> Base sloj ustvarjen: ${id} (${name}) - Viden: ${visible}`);
        } else {
            overlayLayerMap.set(id, layer);
            let zIndex = (id === 'namenska_raba') ? 49 : (id === 'katastr') ? 50 : (id === 'katastr_stevilke') ? 51 : (52 + overlayLayerMap.size);
            layer.setZIndex(zIndex);
            if (always_on) { layer.setVisible(true); }
            console.log(` -> Overlay sloj ustvarjen: ${id} (${name}) - Viden: ${layer.getVisible()}, Z-Index: ${zIndex}`);
        }
        return layer;
    } catch (e) { console.error(`!!! Kritična napaka ustvarjanja sloja ${id} (${name}):`, e); return null; }
}

function buildLayerSelectors() {
    console.log("--- Začenjam buildLayerSelectors ---");
    const baseContainer = document.getElementById('baseLayerOptions');
    const overlayContainer = document.getElementById('overlayLayerOptions');
    if (!baseContainer || !overlayContainer) { console.error("!!! Napaka: Kontejnerji za gumbe niso najdeni!"); return; }
    console.log(" -> Kontejnerji OK.");

    const baseLayersConfig = mapConfig.base_layers || [];
    const overlayLayersConfig = mapConfig.overlay_layers || [];
    console.log(` -> Podatki: Base=${baseLayersConfig.length}, Overlay=${overlayLayersConfig.length}`);

    baseContainer.innerHTML = ''; overlayContainer.innerHTML = '';

    console.log(` -> Obdelujem ${baseLayersConfig.length} osnovnih slojev...`);
    let activeBase = baseLayersConfig.find(cfg => cfg.default_visible)?.id || baseLayersConfig[0]?.id;
    if (activeBase) {
        console.log(` -> Aktiven osnovni sloj: ${activeBase}`);
        if (baseLayerMap.has(activeBase)) { switchBaseLayer(activeBase); }
        else { console.warn(` -> Sloj ${activeBase} ni v baseLayerMap!`); }
    } else { console.log(" -> Ni aktivnega osnovnega sloja."); }

    baseLayersConfig.forEach((cfg, index) => {
        console.log(`  --> Base layer #${index}: ${cfg.id}`);
        const layer = baseLayerMap.get(cfg.id);
        if (!layer) { console.warn(`  !!! Sloj ${cfg.id} ni v baseLayerMap!`); return; }
        console.log(`  --> Sloj ${cfg.id} najden.`);
        try {
            const label = document.createElement('label'); label.className = 'layer-option' + (cfg.id === activeBase ? ' active' : ''); label.setAttribute('data-layer-id', cfg.id); label.title = cfg.description || cfg.title || cfg.id;
            const input = document.createElement('input'); input.type = 'radio'; input.name = 'base-layer'; input.value = cfg.id; input.checked = (cfg.id === activeBase);
            label.addEventListener('click', () => switchBaseLayer(cfg.id)); // Event listener dodan TUKAJ
            const span = document.createElement('span'); span.textContent = `${LAYER_ICONS[cfg.id] || '🗺️'} ${cfg.title || cfg.id}`;
            label.appendChild(input); label.appendChild(span); baseContainer.appendChild(label);
            console.log(`  --> Gumb za ${cfg.id} dodan.`);
        } catch (e) { console.error(`  !!! Napaka gumba za ${cfg.id}:`, e); }
    });

    console.log(` -> Obdelujem ${overlayLayersConfig.length} dodatnih slojev...`);
    overlayLayersConfig.forEach((cfg, index) => {
        console.log(`  --> Overlay layer #${index}: ${cfg.id}`);
        const layer = overlayLayerMap.get(cfg.id);
        if (!layer) { console.warn(`  !!! Sloj ${cfg.id} ni v overlayLayerMap!`); return; }
        console.log(`  --> Sloj ${cfg.id} najden.`);
        const isActive = layer.getVisible();
        try {
            const label = document.createElement('label'); label.className = 'layer-option' + (isActive ? ' active' : ''); label.setAttribute('data-layer-id', cfg.id); label.title = cfg.description || cfg.title || cfg.id;
            const input = document.createElement('input'); input.type = 'checkbox'; input.value = cfg.id; input.checked = isActive; input.disabled = cfg.always_on || false;
            // PREJŠNJA NAPAKA: Event listener je bil vezan na label, ampak je moral biti vezan na input za checkbox pravilno delovanje
            // label.addEventListener('click', ...); // Stara, napačna koda
            input.addEventListener('change', (e) => { // ✅ POPRAVLJENO: Listener na 'change' dogodek input elementa
                 if (input.disabled) { e.preventDefault(); return; }
                 toggleOverlayLayer(cfg.id, e.target.checked); // Posredujemo novo stanje (true/false)
            });
            const span = document.createElement('span'); span.textContent = `${LAYER_ICONS[cfg.id] || '🗂️'} ${cfg.title || cfg.id}`;
            if (input.disabled) { span.style.opacity = '0.7'; span.title = "Vedno vklopljen"; }
            label.appendChild(input); label.appendChild(span); overlayContainer.appendChild(label);
            console.log(`  --> Gumb za ${cfg.id} dodan (Viden: ${isActive}).`);
        } catch (e) { console.error(`  !!! Napaka gumba za ${cfg.id}:`, e); }
    });
    console.log("--- Končujem buildLayerSelectors ---");
}

function switchBaseLayer(layerId) {
    console.log(`>>> switchBaseLayer CALLED with ID: ${layerId}`);
    if (!layerId || !baseLayerMap.has(layerId)) { console.warn(`switchBaseLayer: Neobstoječ sloj ${layerId}`); return; }
    const layerToActivate = baseLayerMap.get(layerId);
    if (!layerToActivate) { console.warn(`switchBaseLayer: Sloj ${layerId} ni bil najden v mapi!`); return; }
    console.log(`   -> Poskušam aktivirati sloj:`, layerToActivate.get('name'));
    let changed = false;
    baseLayerMap.forEach((layer, id) => {
        const shouldBeVisible = (id === layerId);
        if (layer.getVisible() !== shouldBeVisible) {
            console.log(`   -> Spreminjam vidnost za ${id} na ${shouldBeVisible}`);
            try { layer.setVisible(shouldBeVisible); changed = true; }
            catch (e) { console.error(`   !!! Napaka pri setVisible za ${id}:`, e); }
            console.log(`   -> Vidnost za ${id} JE ZDAJ ${layer.getVisible()}`);
        }
    });
    if (changed) {
        document.querySelectorAll('#baseLayerOptions .layer-option').forEach(option => {
            const id = option.getAttribute('data-layer-id'); option.classList.toggle('active', id === layerId);
            const input = option.querySelector('input'); if (input) input.checked = (id === layerId);
        });
        console.log(`   -> UI posodobljen za ${layerId}`);
    } else {
        console.log(`   -> Vidnost za ${layerId} je že bila pravilna.`);
    }
}

function toggleOverlayLayer(layerId, visible) {
    console.log(`>>> toggleOverlayLayer CALLED for ID: ${layerId}, visible: ${visible}`);
    const layer = overlayLayerMap.get(layerId); if (!layer) { console.warn(`toggleOverlayLayer: Sloj ${layerId} ni najden!`); return; }
    const cfg = (mapConfig.overlay_layers || []).find(l => l.id === layerId);
    if (cfg?.always_on && !visible) { console.log(`   -> Sloj ${layerId} je always_on.`); return; }

    console.log(`   -> Poskušam nastaviti vidnost za ${layerId} na ${visible}`);
    try { layer.setVisible(visible); }
    catch (e) { console.error(`   !!! Napaka pri setVisible za ${layerId}:`, e); return; }
    console.log(`   -> Vidnost za ${layerId} JE ZDAJ ${layer.getVisible()}`);

    document.querySelectorAll('#overlayLayerOptions .layer-option[data-layer-id="' + layerId + '"]').forEach(option => {
        option.classList.toggle('active', visible);
        const input = option.querySelector('input');
        if (input && input.checked !== visible) {
             console.warn(`   -> Desinhronizacija UI za ${layerId}, popravljam input.`);
             input.checked = visible;
        }
    });
    console.log(`   -> UI posodobljen za ${layerId}`);
}

function setupWmsCatalogToggle() {
    const toggleBtn = document.getElementById('toggleWmsCatalog'); const toggleBtnText = document.getElementById('toggleWmsBtn'); const catalogContainer = document.getElementById('wmsCatalogContainer');
    let capabilitiesLoaded = false;
    if (toggleBtn && catalogContainer && toggleBtnText) {
        toggleBtn.addEventListener('click', async () => {
            const isHidden = catalogContainer.style.display === 'none'; catalogContainer.style.display = isHidden ? 'block' : 'none'; toggleBtnText.textContent = isHidden ? 'Skrij' : 'Pokaži';
            if (isHidden && !capabilitiesLoaded) { await loadWmsCapabilities(); capabilitiesLoaded = true; }
        });
    } else { console.warn("Elementi za WMS katalog niso najdeni."); }
}

async function loadWmsCapabilities() {
    const status = document.getElementById('capabilityStatus'); const list = document.getElementById('capabilityLayers');
    if (!status || !list) return; status.textContent = 'Nalagam seznam...'; list.innerHTML = '';
    try {
        const response = await fetch('/api/gurs/wms-capabilities'); if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        if (data.success && Array.isArray(data.layers) && data.layers.length > 0) {
            status.textContent = 'Izberite sloj za dodajanje:';
            // ✅ POPRAVLJENO: Uporabimo mapConfig.overlay_layers za preverjanje znanih
            const knownNames = new Set([...(mapConfig.base_layers || []), ...(mapConfig.overlay_layers || [])].map(l => l.name));
            renderCapabilityLayers(data.layers, data.wms_url, list, knownNames);
        } else { status.textContent = 'Seznam ni na voljo.'; console.warn("WMS Caps API:", data); }
    } catch (error) { console.error('❌ Napaka WMS capabilities:', error); status.textContent = 'Napaka nalaganja.'; }
}

function renderCapabilityLayers(layers, wmsUrl, container, knownLayerNames) { // Dodan parameter knownLayerNames
    container.innerHTML = ''; let addedCount = 0;
    layers.forEach(layer => {
        if (addedCount >= 50 || !layer.name || knownLayerNames.has(layer.name.trim())) return;
        const w = document.createElement('div'); w.className = 'layer-chip';
        const i = document.createElement('span'); i.textContent = layer.title || layer.name; i.title = layer.description || `Ime: ${layer.name}`;
        const b = document.createElement('button'); b.type = 'button'; b.textContent = dynamicLayerMap.has(layer.name) ? 'Odstrani' : 'Dodaj';
        b.className = 'btn-toggle-dynamic-layer'; b.setAttribute('data-layer-name', layer.name);
        b.addEventListener('click', () => { const n = b.getAttribute('data-layer-name'); if (dynamicLayerMap.has(n)) { removeDynamicLayer(n); b.textContent = 'Dodaj'; } else { addDynamicLayer(layer, wmsUrl); b.textContent = 'Odstrani'; } });
        w.appendChild(i); w.appendChild(b); container.appendChild(w); addedCount++;
    });
    if (addedCount === 0) { container.textContent = 'Ni dodatnih slojev.'; }
}

function addDynamicLayer(layerInfo, wmsUrl) {
    if (!layerInfo?.name) { console.error("Brez imena sloja:", layerInfo); return; } const n = layerInfo.name; if (dynamicLayerMap.has(n)) { console.warn(`Sloj ${n} že dodan.`); return; }
    console.log(`Dodajam dinamični sloj ${n} iz ${wmsUrl}`);
    try {
        const l = new ol.layer.Tile({ source: new ol.source.TileWMS({ url: wmsUrl, params: { LAYERS: n, TILED: true, FORMAT: 'image/png', TRANSPARENT: true }, crossOrigin: 'anonymous' }), opacity: 0.7, visible: true, name: `dynamic-${n}` });
        l.setZIndex(60 + dynamicLayerMap.size); dynamicLayerMap.set(n, l); map.addLayer(l); console.log(`➕ Dinamični sloj ${n} dodan.`);
    } catch (e) { console.error(`!!! Napaka pri dodajanju dinamičnega sloja ${n}:`, e); }
}

function removeDynamicLayer(layerName) {
    const l = dynamicLayerMap.get(layerName); if (!l) { console.warn(`Sloj ${layerName} ni dodan.`); return; }
    map.removeLayer(l); dynamicLayerMap.delete(layerName); console.log(`➖ Dinamični sloj ${layerName} odstranjen.`);
}

async function handleMapClick(evt) {
    if (!map) return; console.log('🖱️ Klik na koordinatah:', evt.coordinate);
    const viewResolution = map.getView().getResolution(); let parcelData = null; let rabaData = null;

    if (katastrLayer && katastrLayer.getVisible() && katastrLayer.getSource()) {
        const url = katastrLayer.getSource().getFeatureInfoUrl(evt.coordinate, viewResolution, 'EPSG:3857', { INFO_FORMAT: 'application/json', FEATURE_COUNT: 1 });
        if (url) { try { console.debug("Zahtevam GFI (Kataster):", url.substring(0, 150) + "..."); const r = await fetch(url); if (r.ok) { const t = await r.text(); try { parcelData = JSON.parse(t); } catch(e) { console.warn("Kataster GFI ni JSON.", t.substring(0, 100)); }} else { console.warn(`Kataster GFI HTTP ${r.status}`); } } catch (e) { console.error('❌ Kataster GFI napaka:', e); }}
    } else { console.debug('Kataster sloj ni viden/na voljo.'); }

    const namenskaRabaLayer = overlayLayerMap.get('namenska_raba');
    if (namenskaRabaLayer && namenskaRabaLayer.getVisible() && namenskaRabaLayer.getSource()) {
        const url = namenskaRabaLayer.getSource().getFeatureInfoUrl(evt.coordinate, viewResolution, 'EPSG:3857', { INFO_FORMAT: 'application/json', FEATURE_COUNT: 1 });
        if (url) { try { console.debug("Zahtevam GFI (Raba):", url.substring(0, 150) + "..."); const r = await fetch(url); if (r.ok) { const t = await r.text(); try { rabaData = JSON.parse(t); console.debug("Namenska raba GFI odgovor:", rabaData);} catch(e) { console.warn("Namenska raba GFI ni JSON.", t.substring(0, 100)); }} else { console.warn(`Namenska raba GFI HTTP ${r.status}`); } } catch (e) { console.error('❌ Namenska raba GFI napaka:', e); }}
    } else { console.debug('Sloj namenske rabe ni viden/na voljo.'); }

    if (parcelData && Array.isArray(parcelData.features) && parcelData.features.length > 0) {
        console.log("Prejeti GFI podatki iz katastra:", parcelData.features[0].properties);
        if (rabaData && Array.isArray(rabaData.features) && rabaData.features.length > 0) { console.log("Prejeti GFI podatki iz namenske rabe:", rabaData.features[0].properties); } else { console.log("GFI Podatki o namenski rabi niso bili najdeni."); }
        processAndDisplayClickedParcel(parcelData.features[0], rabaData);
    } else {
        console.log("Na kliknjeni lokaciji ni bilo najdenih GFI podatkov o parceli.");
        document.getElementById('parcelInfo').style.display = 'none'; document.getElementById('emptyState').style.display = 'block';
    }
}

function processAndDisplayClickedParcel(parcelFeature, rabaFeatureInfo = null) {
    const props = parcelFeature.properties || {}; let namenskaRabaOpis = 'Ni podatka';
    const stevilka = props.ST_PARCELE || props.PARCELNA_STEVILKA || props.st_parce || props.EID_PARCELA || 'Neznano';
    const ko_id = props.KO_ID || props.ko_id; const ko_naziv = props.NAZIV || props.ime_ko || '';
    const ko_display = ko_id ? `${ko_naziv.replace(ko_id.toString(), '').trim()} (${ko_id})` : ko_naziv || 'Neznano';
    const povrsina_raw = props.POVRSINA || props.RAC_POVRSINA || props.povrsina || 0; const povrsina = parseInt(povrsina_raw, 10) || 0;
    console.log(`Izluščeno iz katastra GFI: Št=${stevilka}, KO=${ko_display}, Pov=${povrsina}`);

    if (rabaFeatureInfo && Array.isArray(rabaFeatureInfo.features) && rabaFeatureInfo.features.length > 0) {
        const rabaProps = rabaFeatureInfo.features[0].properties || {};
        namenskaRabaOpis = rabaProps.OPIS || rabaProps.NAM_RABA_OPIS || rabaProps.EUP_OPIS || rabaProps.RABA || `ID: ${rabaProps.NAMENSKA_RABA_ID || rabaProps.VRSTA_NAMENSKE_RABE_ID || '?'}` || namenskaRabaOpis;
        console.log(`Najdena namenska raba GFI: '${namenskaRabaOpis}' iz polj:`, rabaProps);
    } else {
         console.debug("GFI Podatki o namenski rabi niso bili najdeni.");
         if (props.NAM_RABA_OPIS || props.EUP_OPIS) { namenskaRabaOpis = props.NAM_RABA_OPIS || props.EUP_OPIS; console.log(`Namenska raba GFI najdena v katastru: '${namenskaRabaOpis}'`); }
         else if (props.VRSTA_NAMENSKE_RABE_ID) { namenskaRabaOpis = `ID: ${props.VRSTA_NAMENSKE_RABE_ID}`; console.log(`Namenska raba GFI ID najden v katastru: '${namenskaRabaOpis}'`); }
    }
    selectedParcel = { stevilka: stevilka.startsWith('1001') ? 'Neznano (EID)' : stevilka, katastrska_obcina: ko_display, povrsina: povrsina, namenska_raba: namenskaRabaOpis };
    console.log("Končni podatki GFI za prikaz:", selectedParcel);
    displayParcelInfo(selectedParcel);
}

function displayParcelInfo(parcel) {
    const infoDiv = document.getElementById('parcelInfo'); const emptyState = document.getElementById('emptyState'); const contentDiv = document.getElementById('parcelInfoContent');
    if (!infoDiv || !contentDiv || !emptyState) return;
    infoDiv.style.display = 'block'; emptyState.style.display = 'none';
    const povrsinaFormatted = (parcel.povrsina > 0) ? `${parcel.povrsina} m²` : 'Ni podatka';
    contentDiv.innerHTML = `
        <div class="info-row"><div class="info-label">Parcela</div><div class="info-value">${parcel.stevilka || 'N/A'}</div></div>
        <div class="info-row"><div class="info-label">Katastrska občina</div><div class="info-value">${parcel.katastrska_obcina || 'N/A'}</div></div>
        <div class="info-row"><div class="info-label">Površina</div><div class="info-value">${povrsinaFormatted}</div></div>
        <div class="info-row"><div class="info-label">Namenska raba</div><div class="info-value">${parcel.namenska_raba || 'Ni podatka'}</div></div>`;
}

function addParcelMarkers(parcels) {
    console.log(`📍 Poskušam dodati ${parcels?.length || 0} markerjev...`);
    if (vectorLayer) { if (map) map.removeLayer(vectorLayer); vectorLayer = null; }
    if (!map || !Array.isArray(parcels) || parcels.length === 0) { console.warn("Ni zemljevida ali parcel za markerje."); return; }

    const features = parcels.map((p, index) => {
        console.log(`  -> Obdelujem parcelo #${index}:`, p); // LOG KOORD 1
        if (!p || !Array.isArray(p.coordinates) || p.coordinates.length < 2) { console.warn(`  !!! Neveljavne koordinate #${index}:`, p?.stevilka, p?.coordinates); return null; } // LOG KOORD 2
        if (!p.coordinates.every(c => typeof c === 'number' && isFinite(c))) { console.warn(`  !!! Koordinate niso števila #${index}:`, p.coordinates); return null; } // LOG KOORD 3
        console.log(`  --> Koordinate za ${p.stevilka || `parcela #${index}`}: [${p.coordinates[0]}, ${p.coordinates[1]}] (Pred transformacijo)`); // LOG KOORD 4
        const lon = p.coordinates[0]; const lat = p.coordinates[1];
        if (lon < 13 || lon > 17 || lat < 45 || lat > 47) { console.warn(`  !!! Koordinate [${lon}, ${lat}] izven SLO obsega. Napačen CRS?`); } // LOG KOORD 5
        try {
            const transformedCoords = ol.proj.fromLonLat(p.coordinates);
            console.log(`  --> Transformirane koordinate: [${transformedCoords[0]}, ${transformedCoords[1]}]`); // LOG KOORD 6
            const f = new ol.Feature({ geometry: new ol.geom.Point(transformedCoords), parcel: p });
            // Začasno poenostavljen stil
            f.setStyle(new ol.style.Style({ image: new ol.style.Circle({ radius: 7, fill: new ol.style.Fill({ color: 'rgba(255, 0, 0, 0.8)' }), stroke: new ol.style.Stroke({ color: '#ffffff', width: 2 }) }) }));
            console.log(`  --> Feature za ${p.stevilka || `parcela #${index}`} ustvarjen.`); // LOG KOORD 7
            return f;
        } catch (e) { console.error(`  !!! Napaka feature/transformaciji za ${p.stevilka}:`, e); console.error(`      Originalne koordinate:`, p.coordinates); return null; } // LOG KOORD 8
    }).filter(f => f !== null);

    if (features.length === 0) { console.log("Noben feature ni bil ustvarjen za markerje."); return; }
    const s = new ol.source.Vector({ features }); vectorLayer = new ol.layer.Vector({ source: s, zIndex: 100 });
    map.addLayer(vectorLayer); console.log(`✅ Uspešno dodanih ${features.length} feature-jev v vectorLayer.`);
    setTimeout(() => { if (!map) return; try { const e = s.getExtent(); if (e && e.every(isFinite) && e[0] !== Infinity) { map.getView().fit(e, { padding: [100, 100, 100, 100], duration: 1200, maxZoom: 17 }); console.log('✅ Pogled centriran.'); } else { console.warn("Neveljaven extent:", e); resetView(); } } catch (err) { console.error("Napaka centriranja:", err); resetView(); } }, 300);
}

async function loadSessionParcels() {
    if (!sessionId) { console.log('⚠️ Ni session_id.'); displayParcelList([]); return; }
    console.log(`🔍 Nalagam parcele za session: ${sessionId}`);
    try {
        const r = await fetch(`/api/gurs/session-parcels/${sessionId}`); if (!r.ok) throw new Error(`HTTP ${r.status}`); const d = await r.json(); console.log('📦 Podatki iz seje:', d);
        if (d.success && Array.isArray(d.parcels) && d.parcels.length > 0) {
            console.log(`✅ Najdenih ${d.parcels.length} parcel.`); currentParcels = d.parcels;
            addParcelMarkers(currentParcels); // KLIC MARKERJEV
            displayParcelList(currentParcels);
            const first = currentParcels.find(p => Array.isArray(p.coordinates) && p.coordinates.length === 2 && p.coordinates.every(isFinite));
            if (first) { if (document.getElementById('parcelInfoContent')) { displayParcelInfo(first); console.log("Prikazujem info za prvo parcelo:", first); } else { console.warn("Element #parcelInfoContent ni najden."); } }
            else { console.log("Ni parcel z veljavnimi koordinatami."); document.getElementById('parcelInfo').style.display = 'none'; document.getElementById('emptyState').style.display = 'block'; }
            if (d.message) { console.warn("Sporočilo:", d.message); }
        } else { console.log('⚠️ Ni parcel v seji.'); currentParcels = []; displayParcelList([]); document.getElementById('parcelInfo').style.display = 'none'; document.getElementById('emptyState').style.display = 'block'; }
    } catch (e) { console.error('❌ Napaka nalaganja parcel iz seje:', e); currentParcels = []; displayParcelList([]); document.getElementById('parcelInfo').style.display = 'none'; document.getElementById('emptyState').style.display = 'block'; }
}

function displayParcelList(parcels) {
    const listDiv = document.getElementById('parcelList'); const countSpan = document.getElementById('parcelCount'); const contentDiv = document.getElementById('parcelListContent');
    if (!listDiv || !countSpan || !contentDiv) return; if (!Array.isArray(parcels) || parcels.length === 0) { listDiv.style.display = 'none'; return; }
    listDiv.style.display = 'block'; countSpan.textContent = `(${parcels.length})`; const formatPovrsina = (p) => (p?.povrsina > 0) ? `${p.povrsina} m²` : 'N/A';
    contentDiv.innerHTML = parcels.map((p, idx) => (!p || !p.stevilka) ? '' : `<div class="parcel-item" onclick="selectParcel(${idx})" title="Prikaži na zemljevidu"><div class="parcel-number">${p.stevilka}</div><div class="parcel-details">${p.katastrska_obcina || 'Neznana KO'} • ${formatPovrsina(p)}</div></div>`).join('');
}

function selectParcel(index) {
    console.log(`Izbira parcele z indeksom: ${index}`);
    if (typeof index !== 'number' || index < 0 || index >= currentParcels.length) { console.warn(`Neveljaven indeks: ${index}`); return; } if (!map) { console.warn("selectParcel: Map not ready."); return; } const p = currentParcels[index];
    if (p) { displayParcelInfo(p); if (Array.isArray(p.coordinates) && p.coordinates.length === 2 && p.coordinates.every(isFinite)) { console.log(`Centriram na ${p.stevilka} na ${p.coordinates}`); map.getView().animate({ center: ol.proj.fromLonLat(p.coordinates), zoom: 17, duration: 800 }); } else { console.warn(`${p.stevilka} nima koordinat.`); } }
    else { console.error(`Parcela ${index} ni najdena.`); }
}

function zoomIn() { console.log("Klik na Zoom In"); if (!map) { console.warn("zoomIn: Map not ready."); return; } const view = map.getView(); if (!view) { console.warn("zoomIn: View not ready."); return; } view.animate({ zoom: view.getZoom() + 1, duration: 250 }); }
function zoomOut() { console.log("Klik na Zoom Out"); if (!map) { console.warn("zoomOut: Map not ready."); return; } const view = map.getView(); if (!view) { console.warn("zoomOut: View not ready."); return; } view.animate({ zoom: view.getZoom() - 1, duration: 250 }); }
function resetView() {
    console.log("Klik na Reset View"); if (!map) { console.warn("resetView: Map not ready."); return; } const view = map.getView(); if (!view) { console.warn("resetView: View not ready."); return; }
    if (vectorLayer && vectorLayer.getSource()?.getFeatures().length > 0) { try { const e = vectorLayer.getSource().getExtent(); if (e && e.every(isFinite) && e[0] !== Infinity) { console.log("Resetiram na markerje:", e); view.fit(e, { padding: [80, 80, 80, 80], duration: 800, maxZoom: 17 }); return; } else { console.warn("Neveljaven extent markerjev:", e); } } catch(err) { console.error("Napaka resetiranja na markerje:", err); } }
    console.log("Resetiram na privzeto lokacijo."); view.animate({ center: ol.proj.fromLonLat(mapConfig.defaultCenter), zoom: mapConfig.defaultZoom, duration: 800 });
}

async function searchParcel() {
    console.log("Klik na Search Parcel"); const searchInput = document.getElementById('searchInput'); const searchBtn = document.getElementById('searchBtn');
    if (!searchInput || !searchBtn) { console.warn("searchParcel: Elementi niso najdeni."); return; } if (!map) { console.warn("searchParcel: Map not ready."); alert("Zemljevid se še nalaga."); return; } const query = searchInput.value.trim(); if (!query) { alert('Vnesite iskalni niz.'); return; }
    searchBtn.disabled = true; searchBtn.textContent = 'Iščem...';
    try {
        console.log(`Iščem: "${query}"`); const r = await fetch(`/api/gurs/search-parcel?query=${encodeURIComponent(query)}`); if (!r.ok) { throw new Error(`HTTP ${r.status}`); } const d = await r.json(); console.log("Odgovor iskanja:", d);
        if (d.success && Array.isArray(d.parcels) && d.parcels.length > 0) { console.log(`Najdenih ${d.parcels.length}.`); currentParcels = d.parcels; addParcelMarkers(currentParcels); displayParcelList(currentParcels); if (d.parcels[0]) { displayParcelInfo(d.parcels[0]); } }
        else { console.warn("Iskanje ni vrnilo rezultatov."); let msg = 'Parcela ni najdena.'; if (query.includes('/') && !query.match(/\s\D/)) { msg += ' Poskusite dodati ime katastrske občine.'; } alert(msg); }
    } catch (e) { console.error('❌ Napaka iskanja:', e); alert('Napaka pri iskanju.'); }
    finally { searchBtn.disabled = false; searchBtn.textContent = 'Išči'; }
}

function scheduleMapStateSave() { if (!sessionId) return; if (mapStateTimer) clearTimeout(mapStateTimer); mapStateTimer = setTimeout(saveMapState, 1500); }
async function saveMapState() {
    if (!sessionId || !map) return; const v = map.getView(); const c3857 = v.getCenter(); if (!c3857) { console.warn("Ni centra."); return; }
    try {
        const cLL = ol.proj.toLonLat(c3857); const z = v.getZoom(); if (!cLL || cLL.length < 2 || !cLL.every(isFinite) || !isFinite(z)) { console.warn('Neveljaven pogled:', cLL, z); return; } const p = { center_lon: Number(cLL[0].toFixed(6)), center_lat: Number(cLL[1].toFixed(6)), zoom: Math.round(z) };
        const r = await fetch(`/api/gurs/map-state/${encodeURIComponent(sessionId)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) });
        if (r.ok) { console.log('💾 Stanje shranjeno:', p); } else { console.warn(`⚠️ Napaka shranjevanja: ${r.status}`); }
    } catch (e) { console.error('❌ Napaka shranjevanja:', e); }
}
function setupSearchInputEnter() { const si = document.getElementById('searchInput'); if (si) { si.addEventListener('keypress', (e) => { if (e.key === 'Enter') { e.preventDefault(); searchParcel(); } }); } }

console.log('✅ GURS zemljevid modul v2.5 naložen.');