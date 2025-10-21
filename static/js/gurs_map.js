// GURS Zemljevid JavaScript - POSODOBLJENA VERZIJA

let map;
let baseLayerMap = new Map();
let overlayLayerMap = new Map();
let dynamicLayerMap = new Map();
let vectorLayer;
let katastrLayer; // Zdaj predstavlja samo meje
let katastrStevilkeLayer; // Ločen sloj za številke
let currentParcels = [];
let selectedParcel = null;
let sessionId = null;
let mapConfig = {
    defaultCenter: [14.8267, 46.0569],
    defaultZoom: 14,
    wmsUrl: 'https://ipi.eprostor.gov.si/wms-si-gurs-kn/wms', // Kataster URL
    rasterWmsUrl: 'https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms', // Ortofoto URL
    rpeWmsUrl: 'https://ipi.eprostor.gov.si/wms-si-gurs-rpe/wms', // Namenska raba URL (čeprav jo zdaj kličemo iz KN)
    baseLayers: [],
    overlayLayers: []
};
let savedMapState = null;
let mapStateTimer = null;

const LAYER_ICONS = {
    ortofoto: '📷',
    namenska_raba: '🏘️',
    katastr: '📐',
    katastr_stevilke: '#️⃣', // Ikona za številke
    stavbe: '🏢',
    dtm: '⛰️',
    poplavna: '🌊'
    // Dodajte ikone za morebitne nove sloje
};

// Inicializacija ob nalaganju
DocumentReady(async () => {
    console.log('🚀 Inicializacija GURS zemljevida...');

    if (typeof ol === 'undefined') {
        console.error('❌ OpenLayers ni naložen!');
        alert('Napaka: OpenLayers knjižnica ni naložena.');
        return;
    }

    console.log('✅ OpenLayers naložen, verzija:', ol.VERSION || 'unknown');

    const urlParams = new URLSearchParams(window.location.search);
    sessionId = urlParams.get('session_id');

    await loadMapConfig();
    initMap(); // Ustvari zemljevid s sloji iz configa
    registerMapInteractions(); // Shrani stanje ob premikanju
    buildLayerSelectors(); // Ustvari gumbe za preklop slojev
    await loadSessionParcels(); // Naloži in prikaži parcele iz seje
    
    // Skrij WMS katalog ob nalaganju in dodaj event listener
    const toggleBtn = document.getElementById('toggleWmsCatalog');
    const toggleBtnText = document.getElementById('toggleWmsBtn');
    const catalogContainer = document.getElementById('wmsCatalogContainer');
    let capabilitiesLoaded = false; 

    if (toggleBtn && catalogContainer && toggleBtnText) {
        toggleBtn.addEventListener('click', async () => {
            const isHidden = catalogContainer.style.display === 'none';
            if (isHidden) {
                catalogContainer.style.display = 'block';
                toggleBtnText.textContent = 'Skrij';
                if (!capabilitiesLoaded) {
                    await loadWmsCapabilities(); // Naloži seznam samo ob prvem kliku
                    capabilitiesLoaded = true;
                }
            } else {
                catalogContainer.style.display = 'none';
                toggleBtnText.textContent = 'Pokaži';
            }
        });
    } else {
        console.warn("Elementi za WMS katalog niso najdeni v HTML-ju.");
    }
});


function DocumentReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}

async function loadMapConfig() {
    try {
        const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
        const response = await fetch(`/api/gurs/map-config${query}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        if (data.success && data.config) {
            // Prepišemo celoten config objekt
            mapConfig = {
                defaultCenter: data.config.default_center || mapConfig.defaultCenter,
                defaultZoom: data.config.default_zoom || mapConfig.defaultZoom,
                wmsUrl: data.config.wms_url || mapConfig.wmsUrl,
                rasterWmsUrl: data.config.raster_wms_url || mapConfig.rasterWmsUrl,
                rpeWmsUrl: data.config.rpe_wms_url || mapConfig.rpeWmsUrl, 
                baseLayers: data.config.base_layers || [],
                overlayLayers: data.config.overlay_layers || []
            };
            
            savedMapState = data.config.saved_state || null;
            console.log('🧭 Map config uspešno naložen:', mapConfig, 'Shranjeno stanje:', savedMapState);
        } else {
             console.warn('⚠️ Map config API ni vrnil uspešnega odgovora ali config podatkov:', data);
             // Uporabimo privzete vrednosti, ki so že definirane v mapConfig zgoraj
        }
    } catch (error) {
        console.error('❌ Kritična napaka pri nalaganju Map config:', error);
        // V tem primeru uporabimo trdo kodirane privzete vrednosti
         mapConfig.baseLayers = mapConfig.baseLayers || [];
         mapConfig.overlayLayers = mapConfig.overlayLayers || [];
         console.warn('Uporabljam trdo kodirane privzete URL-je in sloje.');
    }
}

function initMap() {
    console.log('🗺️ Kreiram zemljevid...');

    const viewCenter = savedMapState?.center || mapConfig.defaultCenter;
    const viewZoom = savedMapState?.zoom || mapConfig.defaultZoom;

    // Resetiramo mape slojev
    baseLayerMap = new Map();
    overlayLayerMap = new Map();
    dynamicLayerMap = new Map();
    katastrLayer = null;
    katastrStevilkeLayer = null;

    // Osnovni OSM sloj (vedno prisoten, ampak skrit)
    const osmLayer = new ol.layer.Tile({ source: new ol.source.OSM(), visible: false });

    // Ustvarimo osnovne sloje iz konfiguracije
    const baseLayers = mapConfig.baseLayers
        .map(cfg => createTileLayerFromConfig(cfg, false))
        .filter(l => l); // Filtriramo morebitne napake

    // Če ni nobenega osnovnega sloja, dodamo vsaj ortofoto
    if (baseLayers.length === 0) {
        console.warn("Konfiguracija ni vsebovala osnovnih slojev, dodajam privzeto ortofoto.");
        const defaultOrto = createTileLayerFromConfig({
            id: 'ortofoto', name: 'SI.GURS.ZPDZ:DOF025', title: 'Digitalni ortofoto',
            url: mapConfig.rasterWmsUrl, format: 'image/jpeg', transparent: False,
            category: 'base', default_visible: True
        }, false);
        if (defaultOrto) baseLayers.push(defaultOrto);
    }

    // Ustvarimo dodatne sloje iz konfiguracije
    console.log(`🔧 Nalagam ${mapConfig.overlayLayers.length} overlay slojev...`);
    mapConfig.overlayLayers.forEach(cfg => {
        console.log(`   - ${cfg.id}: "${cfg.name}" (${cfg.default_visible ? 'Viden' : 'Skrit'})`);
    });

    const overlayLayers = mapConfig.overlayLayers
        .map(cfg => createTileLayerFromConfig(cfg, true))
        .filter(l => l); // Filtriramo morebitne napake

    // Preverimo, ali imamo vsaj osnovne katastrske sloje
    if (!overlayLayerMap.has('katastr')) {
         console.warn("Konfiguracija ni vsebovala sloja za meje (katastr), dodajam privzetega.");
         const defaultMeje = createTileLayerFromConfig({
             id: 'katastr', name: 'SI.GURS.KN:PARCELE', title: 'Parcelne meje',
             url: mapConfig.wmsUrl, format: 'image/png', transparent: True,
             category: 'overlay', default_visible: True, always_on: True
         }, true);
         if (defaultMeje) overlayLayers.push(defaultMeje);
    }
     if (!overlayLayerMap.has('katastr_stevilke')) {
         console.warn("Konfiguracija ni vsebovala sloja za številke (katastr_stevilke), dodajam privzetega.");
         const defaultStevilke = createTileLayerFromConfig({
             id: 'katastr_stevilke', name: 'NEP_OSNOVNI_PARCELE_CENTROID', title: 'Številke parcel',
             url: mapConfig.wmsUrl, format: 'image/png', transparent: True,
             category: 'overlay', default_visible: True, always_on: False
         }, true);
         if (defaultStevilke) overlayLayers.push(defaultStevilke);
    }

    // Shranimo reference na ključne sloje
    katastrLayer = overlayLayerMap.get('katastr');
    katastrStevilkeLayer = overlayLayerMap.get('katastr_stevilke');

    // Združimo vse sloje za inicializacijo zemljevida
    const layers = [osmLayer, ...baseLayers, ...overlayLayers];

    // Ustvarimo zemljevid
    map = new ol.Map({
        target: 'map',
        layers: layers,
        view: new ol.View({
            center: ol.proj.fromLonLat(viewCenter),
            zoom: viewZoom
        })
    });

    console.log('✅ Zemljevid inicializiran s sloji:', layers.map(l => l.get('name')));
    console.log('📍 Začetni center:', viewCenter, 'zoom:', viewZoom);

    // Dodamo interakcijo za klik
    map.on('singleclick', handleMapClick);
}

function registerMapInteractions() {
    if (!map) return;
    map.on('moveend', scheduleMapStateSave);
}

function createTileLayerFromConfig(cfg, isOverlay = false) {
    // Osnovno preverjanje konfiguracije
    if (!cfg || !cfg.id || !cfg.name || !cfg.url) {
        console.error("Napačna ali nepopolna konfiguracija sloja:", cfg);
        return null;
    }

    const url = cfg.url;
    const format = cfg.format || 'image/png';
    const transparent = cfg.transparent !== undefined ? cfg.transparent : true;
    const visible = cfg.default_visible === true; // Samo tisti z default_visible=true so vidni na začetku

    const layerName = cfg.name;
    const layer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: url,
            params: {
                LAYERS: layerName,
                TILED: true,
                FORMAT: format,
                TRANSPARENT: transparent,
                VERSION: '1.3.0' // Specificiramo verzijo za boljšo kompatibilnost
            },
            crossOrigin: 'anonymous', // Pomembno za GetFeatureInfo in deljenje
             serverType: 'geoserver' // Namig za OpenLayers, lahko pomaga pri nekaterih strežnikih
        }),
        visible: visible, // Nastavimo začetno vidnost
        opacity: cfg.opacity ?? (transparent ? 0.8 : 1), // Uporabimo opacity iz config ali privzeto
        name: cfg.id // Uporabimo ID za identifikacijo v kodi
    });

    // Shranimo v ustrezno mapo in nastavimo Z-index
    if (isOverlay) {
        overlayLayerMap.set(cfg.id, layer);
        let zIndex = 50; // Privzeti Z-index za overlaye
        if (cfg.id === 'katastr') zIndex = 50; // Meje spodaj
        else if (cfg.id === 'katastr_stevilke') zIndex = 51; // Številke čez meje
        else if (cfg.id === 'namenska_raba') zIndex = 49; // Raba pod mejami? Lahko testirate.
        else zIndex = 52 + overlayLayerMap.size; // Ostali čez vse
        layer.setZIndex(zIndex);

        // Always_on sloji MORAJO biti vidni ob zagonu
        if (cfg.always_on) {
            layer.setVisible(true);
             // Dodatno zagotovilo za always_on sloje
             if (!layer.getVisible()){
                  console.warn(`Always_on sloj ${cfg.id} ni bil nastavljen kot viden! Popravljam.`);
                  layer.setVisible(true);
             }
        }

        console.log(`✅ Overlay sloj ustvarjen: ${cfg.id} (${layerName}) - Viden: ${visible}, Z-Index: ${zIndex}, Opacity: ${layer.getOpacity()}`);
    } else {
        baseLayerMap.set(cfg.id, layer);
        layer.setZIndex(baseLayerMap.size); // Osnovni sloji so pod dodatnimi
        console.log(`✅ Base sloj ustvarjen: ${cfg.id} (${layerName}) - Viden: ${visible}`);
    }

    // Dodamo error handler za sloj
    layer.getSource().on('tileloaderror', function(event) {
        console.error(`❌ Napaka pri nalaganju tile za sloj ${cfg.id} (${layerName}):`, event);
        console.error(`   URL: ${url}`);
        console.error(`   Preverite, ali sloj "${layerName}" obstaja na strežniku.`);
    });

    // Success log
    layer.getSource().on('tileloadend', function(event) {
        console.debug(`✓ Tile naložen za sloj ${cfg.id}`);
    });

    return layer;
}

function buildLayerSelectors() {
    const baseContainer = document.getElementById('baseLayerOptions');
    const overlayContainer = document.getElementById('overlayLayerOptions');
    if (!baseContainer || !overlayContainer) return;

    baseContainer.innerHTML = '';
    overlayContainer.innerHTML = '';

    // Določimo aktivni osnovni sloj (tisti z default_visible=true)
    let activeBase = null;
    mapConfig.baseLayers.forEach(cfg => {
        if (cfg.default_visible) activeBase = cfg.id;
    });
    // Fallback na prvi osnovni sloj, če noben ni default_visible
    if (!activeBase && mapConfig.baseLayers.length > 0) {
        activeBase = mapConfig.baseLayers[0].id;
    }
    // Dejansko vklopi privzeti sloj na zemljevidu
    switchBaseLayer(activeBase);

    // Ustvarimo gumbe za osnovne sloje
    mapConfig.baseLayers.forEach(cfg => {
        const layer = baseLayerMap.get(cfg.id);
        if (!layer) return;

        const label = document.createElement('label');
        label.className = 'layer-option' + (cfg.id === activeBase ? ' active' : '');
        label.setAttribute('data-layer-id', cfg.id);
        label.title = cfg.description || cfg.title; // Tooltip

        const input = document.createElement('input'); // Skrit
        input.type = 'radio';
        input.name = 'base-layer';
        input.value = cfg.id;
        input.checked = (cfg.id === activeBase);
        
        label.addEventListener('click', () => switchBaseLayer(cfg.id));

        const icon = LAYER_ICONS[cfg.id] || '🗺️';
        const span = document.createElement('span');
        span.textContent = `${icon} ${cfg.title || cfg.id}`;

        label.appendChild(input);
        label.appendChild(span);
        baseContainer.appendChild(label);
    });

    // Ustvarimo gumbe za dodatne sloje
    mapConfig.overlayLayers.forEach(cfg => {
        const layer = overlayLayerMap.get(cfg.id);
        if (!layer) return;

        const label = document.createElement('label');
        const isActive = layer.getVisible(); // Preberemo dejansko stanje sloja
        label.className = 'layer-option' + (isActive ? ' active' : '');
        label.setAttribute('data-layer-id', cfg.id);
        label.title = cfg.description || cfg.title; // Tooltip

        const input = document.createElement('input'); // Skrit
        input.type = 'checkbox';
        input.value = cfg.id;
        input.checked = isActive;
        input.disabled = cfg.always_on || false; // Onemogočimo klik za always_on
        
        label.addEventListener('click', (e) => {
            if (input.disabled) { e.preventDefault(); return; }
            const isCheckedNow = !input.checked; // Preklopimo stanje
            input.checked = isCheckedNow; // Sinhroniziramo skriti input
            toggleOverlayLayer(cfg.id, isCheckedNow); // Vklopimo/izklopimo sloj
        });

        const icon = LAYER_ICONS[cfg.id] || '🗂️';
        const span = document.createElement('span');
        span.textContent = `${icon} ${cfg.title || cfg.id}`;
        if (input.disabled) {
             span.style.opacity = '0.7'; // Malo bolj sivo za onemogočene
             span.title = "Ta sloj je vedno vklopljen";
        }

        label.appendChild(input);
        label.appendChild(span);
        overlayContainer.appendChild(label);
    });
}


function switchBaseLayer(layerId) {
    if (!layerId || !baseLayerMap.has(layerId)) {
         console.warn(`Poskus preklopa na neobstoječ osnovni sloj: ${layerId}`);
         return;
    }
    
    // Izklopi vse osnovne sloje, vklopi izbranega
    baseLayerMap.forEach((layer, id) => {
        layer.setVisible(id === layerId);
    });

    // Posodobi UI gumbe
    document.querySelectorAll('#baseLayerOptions .layer-option').forEach(option => {
        const id = option.getAttribute('data-layer-id');
        option.classList.toggle('active', id === layerId);
        const input = option.querySelector('input');
        if (input) input.checked = (id === layerId);
    });
     console.log(`Preklopljeno na osnovni sloj: ${layerId}`);
}

function toggleOverlayLayer(layerId, visible) {
    const layer = overlayLayerMap.get(layerId);
    if (!layer) {
        console.warn(`Poskus preklopa neobstoječega dodatnega sloja: ${layerId}`);
        return;
    }

    const cfg = mapConfig.overlayLayers.find(l => l.id === layerId);
    // Always_on slojev ne dovolimo izklopiti
    if (cfg?.always_on && !visible) {
         console.log(`Sloj ${layerId} je always_on in ga ni mogoče izklopiti.`);
        // Zagotovimo, da ostane vklopljen tudi v UI
         document.querySelectorAll('#overlayLayerOptions .layer-option').forEach(option => {
            if (option.getAttribute('data-layer-id') === layerId) {
                option.classList.add('active');
                const input = option.querySelector('input');
                if (input) input.checked = true;
            }
         });
        return; 
    }

    // Nastavimo vidnost sloja
    layer.setVisible(visible);

    // Posodobimo UI gumb
    document.querySelectorAll('#overlayLayerOptions .layer-option').forEach(option => {
        if (option.getAttribute('data-layer-id') === layerId) {
            option.classList.toggle('active', visible);
            // Input je že posodobljen zgoraj v event listenerju
        }
    });
     console.log(`Vidnost dodatnega sloja ${layerId} nastavljena na: ${visible}`);
}


async function loadWmsCapabilities() {
    const status = document.getElementById('capabilityStatus');
    const list = document.getElementById('capabilityLayers');
    if (!status || !list) return;
    status.textContent = 'Nalagam seznam dodatnih slojev...';
    list.innerHTML = ''; // Počistimo prejšnje

    try {
        // Kličemo API, ki pridobi Capabilities iz GURS_WMS_URL (KN strežnik)
        const response = await fetch('/api/gurs/wms-capabilities');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        
        if (data.success && Array.isArray(data.layers) && data.layers.length > 0) {
            status.textContent = 'Izberite sloj za dodajanje na zemljevid:';
            renderCapabilityLayers(data.layers, data.wms_url, list); // data.wms_url je KN URL
        } else {
            status.textContent = 'Seznam dodatnih slojev trenutno ni na voljo.';
            console.warn("WMS Capabilities API odgovor ni bil uspešen ali je prazen:", data);
        }
    } catch (error) {
        console.error('❌ Napaka pri nalaganju WMS capabilities:', error);
        status.textContent = 'Napaka pri nalaganju seznama slojev.';
    }
}

function renderCapabilityLayers(layers, wmsUrl, container) {
    container.innerHTML = ''; // Počistimo prejšnjo vsebino
    let addedCount = 0;
    
    // Zgradimo seznam imen že uporabljenih slojev
    const knownLayerNames = new Set();
    mapConfig.baseLayers.forEach(l => l.name.split(',').forEach(n => knownLayerNames.add(n.trim())));
    mapConfig.overlayLayers.forEach(l => l.name.split(',').forEach(n => knownLayerNames.add(n.trim())));

    // Filtriramo in prikažemo do 50 slojev, ki še niso v osnovni konfiguraciji
    layers.forEach(layer => {
        if (addedCount >= 50) return; // Omejitev števila prikazanih
        
        // Preskočimo, če ime sloja že obstaja v osnovni konfiguraciji
        if (!layer.name || knownLayerNames.has(layer.name.trim())) {
            return; 
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'layer-chip';

        const info = document.createElement('span');
        info.textContent = layer.title || layer.name;
        info.title = layer.description || `Ime sloja: ${layer.name}`; // Tooltip

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.textContent = dynamicLayerMap.has(layer.name) ? 'Odstrani' : 'Dodaj';
        toggleBtn.className = 'btn-toggle-dynamic-layer';
        toggleBtn.setAttribute('data-layer-name', layer.name); // Shranimo ime za lažji dostop

        toggleBtn.addEventListener('click', () => {
            const layerName = toggleBtn.getAttribute('data-layer-name');
            if (dynamicLayerMap.has(layerName)) {
                removeDynamicLayer(layerName);
                toggleBtn.textContent = 'Dodaj';
            } else {
                // Posredujemo celoten layerInfo objekt
                addDynamicLayer(layer, wmsUrl); 
                toggleBtn.textContent = 'Odstrani';
            }
        });

        wrapper.appendChild(info);
        wrapper.appendChild(toggleBtn);
        container.appendChild(wrapper);
        addedCount++;
    });
    
    if (addedCount === 0) {
        container.textContent = 'Ni dodatnih slojev za prikaz iz tega vira.';
    }
}

function addDynamicLayer(layerInfo, wmsUrl) {
    if (!layerInfo?.name) {
        console.error("Ne morem dodati dinamičnega sloja brez imena:", layerInfo);
        return;
    }
    const layerName = layerInfo.name;

    // Preverimo, če sloj že obstaja
    if (dynamicLayerMap.has(layerName)) {
        console.warn(`Dinamični sloj ${layerName} je že dodan.`);
        return;
    }

    console.log(`Dodajam dinamični sloj ${layerName} iz ${wmsUrl}`);
    const layer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: wmsUrl, // Uporabimo URL vira
            params: {
                LAYERS: layerName,
                TILED: true,
                FORMAT: 'image/png',
                TRANSPARENT: true
            },
            crossOrigin: 'anonymous'
        }),
        opacity: 0.7,
        visible: true, // Dinamični sloji so takoj vidni
        name: `dynamic-${layerName}` // Dodamo predpono za lažje razlikovanje
    });

    layer.setZIndex(60 + dynamicLayerMap.size); // Nad vsemi ostalimi
    dynamicLayerMap.set(layerName, layer);
    map.addLayer(layer);
    console.log(`➕ Dinamični sloj ${layerName} dodan.`);
}

function removeDynamicLayer(layerName) {
    const layer = dynamicLayerMap.get(layerName);
    if (!layer) {
         console.warn(`Poskus odstranitve neobstoječega dinamičnega sloja: ${layerName}`);
         return;
    }
    map.removeLayer(layer);
    dynamicLayerMap.delete(layerName);
    console.log(`➖ Dinamični sloj ${layerName} odstranjen.`);
}

async function handleMapClick(evt) {
    console.log('🖱️ Klik na koordinatah:', evt.coordinate);
    const viewResolution = map.getView().getResolution();
    let parcelData = null; // Podatki iz KN:PARCELE
    let rabaData = null; // Podatki iz NEP_OST_NAMENSKE_RABE

    // 1. Pridobi podatke iz katastra (meje) za osnovne info (ID, Površina)
    if (katastrLayer && katastrLayer.getVisible() && katastrLayer.getSource()) {
        const katastrUrl = katastrLayer.getSource().getFeatureInfoUrl(
            evt.coordinate, viewResolution, 'EPSG:3857',
            { INFO_FORMAT: 'application/json', FEATURE_COUNT: 1 }
        );
        if (katastrUrl) {
            try {
                console.debug("Zahtevam GetFeatureInfo (Kataster):", katastrUrl);
                const response = await fetch(katastrUrl);
                if (response.ok) {
                    const textData = await response.text();
                    try { parcelData = JSON.parse(textData); } 
                    catch(e) { console.warn("Kataster GetFeatureInfo ni vrnil veljavnega JSON.", textData.substring(0, 200)); }
                } else { console.warn(`Kataster GetFeatureInfo HTTP napaka: ${response.status}`); }
            } catch (error) { console.error('❌ Kataster GetFeatureInfo napaka:', error); }
        }
    } else { console.debug('Sloj katastrskih mej ni viden ali ni na voljo za GetFeatureInfo.'); }

    // 2. Pridobi podatke o namenski rabi (če je sloj viden)
    const namenskaRabaLayer = overlayLayerMap.get('namenska_raba'); // Iščemo med OVERLAY sloji
    if (namenskaRabaLayer && namenskaRabaLayer.getVisible() && namenskaRabaLayer.getSource()) {
        const rabaUrl = namenskaRabaLayer.getSource().getFeatureInfoUrl(
            evt.coordinate, viewResolution, 'EPSG:3857',
            { INFO_FORMAT: 'application/json', FEATURE_COUNT: 1 }
        );
        if (rabaUrl) {
             try {
                console.debug("Zahtevam GetFeatureInfo (Raba):", rabaUrl);
                const response = await fetch(rabaUrl);
                 if (response.ok) {
                    const textData = await response.text();
                    try {
                        rabaData = JSON.parse(textData);
                        console.debug("Namenska raba odgovor:", rabaData);
                    }
                    catch(e) {
                        console.warn("Namenska raba GetFeatureInfo ni vrnila veljavnega JSON.", textData.substring(0, 200));
                        console.warn("💡 Preverite, ali sloj podpira GetFeatureInfo in ali je ime sloja pravilno.");
                    }
                } else {
                    console.warn(`Namenska raba GetFeatureInfo HTTP napaka: ${response.status}`);
                    console.warn("💡 Sloj morda ne obstaja ali ni dostopen. Preverite ime sloja v config.py");
                }
            } catch (error) {
                console.error('❌ Namenska raba GetFeatureInfo napaka:', error);
                console.error('💡 Mogoče sloj ne podpira GetFeatureInfo ali ima napačno ime.');
            }
        }
    } else {
        if (!namenskaRabaLayer) {
            console.debug('Sloj Namenska raba ni bil naložen. Preverite konfiguracijo.');
        } else if (!namenskaRabaLayer.getVisible()) {
            console.debug('Sloj Namenska raba ni viden. Vklopite ga v Layer Selector.');
        } else {
            console.debug('Sloj Namenska raba nima veljavnega vira.');
        }
    }

    // 3. Združi rezultate in prikaži
    // Prioriteta: Prikažemo podatke, če imamo vsaj zadetek iz katastra
    if (parcelData && Array.isArray(parcelData.features) && parcelData.features.length > 0) {
        console.log("Prejeti podatki iz katastra:", parcelData.features[0].properties);
        if (rabaData && Array.isArray(rabaData.features) && rabaData.features.length > 0) {
             console.log("Prejeti podatki iz namenske rabe:", rabaData.features[0].properties);
        } else {
             console.log("Podatki o namenski rabi niso bili najdeni za to lokacijo.");
        }
        handleParcelClick(parcelData.features[0], rabaData); // Posredujemo oba rezultata
    } else {
        console.log("Na kliknjeni lokaciji ni bilo najdenih podatkov o parceli.");
        // Počistimo info okno
        document.getElementById('parcelInfo').style.display = 'none';
        document.getElementById('emptyState').style.display = 'block';
    }
}

function handleParcelClick(parcelFeature, rabaFeatureInfo = null) {
    const props = parcelFeature.properties || {}; // Podatki iz KN:PARCELE
    let namenskaRabaOpis = 'Ni podatka'; // Privzeta vrednost

    // Poskusimo dobiti namensko rabo iz drugega klica (rabaFeatureInfo)
    if (rabaFeatureInfo && Array.isArray(rabaFeatureInfo.features) && rabaFeatureInfo.features.length > 0) {
        const rabaProps = rabaFeatureInfo.features[0].properties || {};
        // Poskusimo različna možna imena polj za opis namenske rabe
        namenskaRabaOpis = rabaProps.NAM_RABA_OPIS || rabaProps.EUP_OPIS || rabaProps.OPIS || rabaProps.RABA || namenskaRabaOpis;
        console.log(`Najdena namenska raba: '${namenskaRabaOpis}' iz polj:`, rabaProps);
    } else {
         console.debug("Podatki o namenski rabi niso bili najdeni v GetFeatureInfo odgovoru.");
         // Dodaten poskus: Ali je podatek morda že v parcelFeature? (malo verjetno)
         if (props.NAM_RABA_OPIS || props.EUP_OPIS) {
              namenskaRabaOpis = props.NAM_RABA_OPIS || props.EUP_OPIS;
              console.log(`Namenska raba najdena v osnovnih podatkih parcele: '${namenskaRabaOpis}'`);
         }
    }

    // Sestavimo objekt 'selectedParcel'
    selectedParcel = {
        stevilka: props.ST_PARCE || 'Neznano', // Glavno polje za številko
        katastrska_obcina: props.IME_KO || 'Neznano', // Glavno polje za ime KO
        povrsina: parseInt(props.POVRSINA || props.RAC_POVRSINA || 0, 10), // Uradna ali računska površina kot število
        namenska_raba: namenskaRabaOpis // Vrednost, ki smo jo pridobili
    };

    console.log("Končni podatki za prikaz:", selectedParcel);
    displayParcelInfo(selectedParcel); // Pokažemo podatke v UI
}


function displayParcelInfo(parcel) {
    const infoDiv = document.getElementById('parcelInfo');
    const emptyState = document.getElementById('emptyState');
    const contentDiv = document.getElementById('parcelInfoContent');
    if (!infoDiv || !contentDiv || !emptyState) return;

    infoDiv.style.display = 'block';
    emptyState.style.display = 'none';
    
    // Formatiramo površino le, če je večja od 0
    const povrsinaFormatted = (parcel.povrsina > 0) ? `${parcel.povrsina} m²` : 'Ni podatka';

    contentDiv.innerHTML = `
        <div class="info-row">
            <div class="info-label">Parcela</div>
            <div class="info-value">${parcel.stevilka || 'N/A'}</div>
        </div>
        <div class="info-row">
            <div class="info-label">Katastrska občina</div>
            <div class="info-value">${parcel.katastrska_obcina || 'N/A'}</div>
        </div>
        <div class="info-row">
            <div class="info-label">Površina</div>
            <div class="info-value">${povrsinaFormatted}</div>
        </div>
        <div class="info-row">
            <div class="info-label">Namenska raba (info)</div>
            <div class="info-value">${parcel.namenska_raba || 'Ni podatka'}</div>
        </div>
    `;
}

function addParcelMarkers(parcels) {
    console.log(`📍 Poskušam dodati ${parcels?.length || 0} markerjev...`);

    // Odstranimo prejšnji vektorski sloj, če obstaja
    if (vectorLayer) {
        map.removeLayer(vectorLayer);
        vectorLayer = null; // Resetiramo referenco
    }
    
    // Preverimo, ali imamo veljaven seznam parcel
    if (!Array.isArray(parcels) || parcels.length === 0) {
        console.warn("Ni parcel za dodajanje markerjev.");
        return;
    }

    // Ustvarimo feature za vsako parcelo z veljavnimi koordinatami
    const features = parcels.map(parcel => {
        if (!parcel || !Array.isArray(parcel.coordinates) || parcel.coordinates.length < 2 || !parcel.coordinates.every(c => typeof c === 'number' && isFinite(c))) {
            console.warn("Neveljavne ali manjkajoče koordinate za parcelo:", parcel?.stevilka || 'brez št.', parcel);
            return null; // Preskočimo neveljavno parcelo
        }
        
        try {
            const feature = new ol.Feature({
                geometry: new ol.geom.Point(ol.proj.fromLonLat(parcel.coordinates)),
                parcel: parcel // Shranimo celoten objekt parcele za kasnejši dostop
            });

            // Stil markerja in oznake
            feature.setStyle(new ol.style.Style({
                image: new ol.style.Circle({
                    radius: 8, // Malo manjši
                    fill: new ol.style.Fill({ color: 'rgba(99, 102, 241, 0.7)' }), // Malo bolj prosojno
                    stroke: new ol.style.Stroke({ color: '#ffffff', width: 2 }) // Bela obroba
                }),
                text: new ol.style.Text({
                    text: parcel.stevilka || '?', // Pokaži št. ali '?'
                    offsetY: -20, // Malo bližje markerju
                    font: 'bold 13px Inter, sans-serif',
                    fill: new ol.style.Fill({ color: '#ffffff' }), // Bela pisava
                    stroke: new ol.style.Stroke({ color: '#1e293b', width: 3 }), // Temna obroba pisave
                    backgroundFill: new ol.style.Fill({ color: 'rgba(79, 70, 229, 0.8)' }), // Temnejše ozadje
                    padding: [4, 8, 4, 8] // Malo manj paddinga
                })
            }));
            return feature;
        } catch (e) {
             console.error(`Napaka pri ustvarjanju feature za parcelo ${parcel.stevilka}:`, e);
             return null;
        }
    }).filter(f => f !== null); // Izločimo neuspešno ustvarjene feature

    // Če ni nobenega veljavnega feature-a, ne nadaljujemo
    if (features.length === 0) {
        console.log("Nobena parcela nima veljavnih podatkov za prikaz markerja.");
        return;
    }

    // Ustvarimo nov vektorski sloj
    const vectorSource = new ol.source.Vector({ features });
    vectorLayer = new ol.layer.Vector({ 
        source: vectorSource,
        zIndex: 100 // Zagotovimo, da so markerji na vrhu
     });

    map.addLayer(vectorLayer);
    console.log(`✅ Uspešno dodanih ${features.length} markerjev.`);

    // Centriramo pogled na dodane markerje (z zamikom za inicializacijo)
    setTimeout(() => {
        try {
            const extent = vectorSource.getExtent();
            if (extent && extent.every(isFinite) && extent[0] !== Infinity) {
                map.getView().fit(extent, {
                    padding: [100, 100, 100, 100], // Rob okoli markerjev
                    duration: 1200, // Malo počasnejša animacija
                    maxZoom: 17 // Največji zoom ob centriranju
                });
                console.log('✅ Pogled centriran na nove markerje.');
            } else {
                 console.warn("Neveljaven extent za centriranje markerjev:", extent);
                 resetView(); // Fallback na privzeti pogled
            }
        } catch (e) {
            console.error("Napaka pri centriranju na markerje:", e);
            resetView(); // Fallback
        }
    }, 300); // Kratek zamik
}


async function loadSessionParcels() {
    if (!sessionId) {
        console.log('⚠️ Ni session_id, parcele iz seje ne bodo naložene.');
        displayParcelList([]); 
        return;
    }

    console.log(`🔍 Nalagam parcele za session: ${sessionId}`);
    try {
        const response = await fetch(`/api/gurs/session-parcels/${sessionId}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();

        console.log('📦 Podatki o parcelah iz seje:', data);

        if (data.success && Array.isArray(data.parcels) && data.parcels.length > 0) {
            console.log(`✅ Najdenih ${data.parcels.length} parcel v seji.`);
            currentParcels = data.parcels; // Shranimo jih

            addParcelMarkers(currentParcels); // Doda markerje (uporabi prave koordinate)
            displayParcelList(currentParcels); // Posodobi seznam na desni

            // Prikaz info za prvo parcelo z veljavnimi koordinatami
            const firstValidParcel = currentParcels.find(p => Array.isArray(p.coordinates) && p.coordinates.length === 2 && p.coordinates.every(isFinite));
            if (firstValidParcel) {
                displayParcelInfo(firstValidParcel);
            } else {
                 console.log("Nobena parcela iz seje nima veljavnih koordinat za začetni prikaz info.");
                 document.getElementById('parcelInfo').style.display = 'none';
                 document.getElementById('emptyState').style.display = 'block';
            }
            // Izpis opozorila, če obstaja
            if (data.message) {
                 console.warn("Sporočilo s strežnika:", data.message);
                 // TODO: Morda prikazati to sporočilo uporabniku?
            }
        } else {
            console.log('⚠️ V seji ni bilo najdenih parcel ali pa API ni vrnil uspešnega odgovora.');
            currentParcels = []; // Počistimo seznam
            displayParcelList([]); 
            document.getElementById('parcelInfo').style.display = 'none';
            document.getElementById('emptyState').style.display = 'block';
        }
    } catch (error) {
        console.error('❌ Kritična napaka pri nalaganju parcel iz seje:', error);
        currentParcels = [];
        displayParcelList([]);
        document.getElementById('parcelInfo').style.display = 'none';
        document.getElementById('emptyState').style.display = 'block';
        // Morda obvestimo uporabnika?
        // alert("Napaka pri nalaganju parcel iz projekta. Poskusite osvežiti stran.");
    }
}


function displayParcelList(parcels) {
    const listDiv = document.getElementById('parcelList');
    const countSpan = document.getElementById('parcelCount');
    const contentDiv = document.getElementById('parcelListContent');
    if (!listDiv || !countSpan || !contentDiv) return;

    if (!Array.isArray(parcels) || parcels.length === 0) {
        listDiv.style.display = 'none'; // Skrij celoten blok, če ni parcel
        return;
    }

    listDiv.style.display = 'block'; // Pokaži blok
    countSpan.textContent = `(${parcels.length})`; // Pokaži število
    
    // Funkcija za varno formatiranje površine
    const formatPovrsina = (parcel) => {
        const pov = parcel?.povrsina;
        return (typeof pov === 'number' && pov > 0) ? `${pov} m²` : 'N/A';
    };

    // Generiramo HTML za vsako parcelo
    contentDiv.innerHTML = parcels.map((parcel, idx) => {
        if (!parcel || !parcel.stevilka) return ''; // Preskočimo neveljavne vnose
        return `
            <div class="parcel-item" onclick="selectParcel(${idx})" title="Klikni za prikaz na zemljevidu">
                <div class="parcel-number">${parcel.stevilka}</div>
                <div class="parcel-details">
                    ${parcel.katastrska_obcina || 'Neznana KO'} • ${formatPovrsina(parcel)}
                </div>
            </div>`;
    }).join('');
}


function selectParcel(index) {
     // Preverimo veljavnost indeksa
    if (typeof index !== 'number' || index < 0 || index >= currentParcels.length) {
         console.warn(`Neveljaven indeks parcele za izbiro: ${index}`);
         return;
    }
    
    const parcel = currentParcels[index];
    if (parcel) {
        displayParcelInfo(parcel); // Vedno posodobimo info okno
        
        // Centriramo zemljevid, če imamo veljavne koordinate
        if (Array.isArray(parcel.coordinates) && parcel.coordinates.length === 2 && parcel.coordinates.every(isFinite)) {
            console.log(`Centriram na parcelo ${parcel.stevilka} na ${parcel.coordinates}`);
            map.getView().animate({
                center: ol.proj.fromLonLat(parcel.coordinates),
                zoom: 17, // Fiksni zoom ob izbiri
                duration: 800 // Malo hitrejša animacija
            });
        } else {
            console.warn(`Izbrana parcela ${parcel.stevilka} nima veljavnih koordinat za centriranje.`);
            // Ne prikažemo alert-a, samo info ostane
        }
    } else {
        console.error(`Parcela z indeksom ${index} ni bila najdena v currentParcels.`);
    }
}

// Kontrole
function zoomIn() { map?.getView()?.animate({ zoom: map.getView().getZoom() + 1, duration: 250 }); }
function zoomOut() { map?.getView()?.animate({ zoom: map.getView().getZoom() - 1, duration: 250 }); }

function resetView() {
    if (!map) return;
    // Če imamo vektorski sloj z markerji, se osredotočimo nanj
    if (vectorLayer && vectorLayer.getSource()?.getFeatures().length > 0) {
         try {
            const extent = vectorLayer.getSource().getExtent();
             // Preverimo, ali je extent veljaven (ni neskončen ali NaN)
             if (extent && extent.every(isFinite) && extent[0] !== Infinity) {
                 console.log("Resetiram pogled na extent markerjev:", extent);
                 map.getView().fit(extent, {
                     padding: [80, 80, 80, 80], // Manj paddinga ob resetu
                     duration: 800,
                     maxZoom: 17
                 });
                 return; // Končamo tukaj
             } else {
                  console.warn("Neveljaven extent markerjev za reset:", extent);
             }
         } catch(e) { console.error("Napaka pri resetiranju pogleda na markerje:", e); }
    }
    
    // Fallback: Če ni markerjev ali je extent neveljaven, gremo na privzeto lokacijo
    console.log("Resetiram pogled na privzeto lokacijo.");
    map.getView().animate({
        center: ol.proj.fromLonLat(mapConfig.defaultCenter),
        zoom: mapConfig.defaultZoom,
        duration: 800
    });
}

// Iskanje parcel
async function searchParcel() {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    if (!searchInput || !searchBtn) return; // Preverimo, ali elementi obstajajo
    
    const query = searchInput.value.trim();
    if (!query) {
        alert('Vnesite iskalni niz (npr. "940/1 Hotič" ali samo "940/1").');
        return;
    }

    searchBtn.disabled = true;
    searchBtn.textContent = 'Iščem...';

    try {
        console.log(`Začenjam iskanje parcele: "${query}"`);
        const response = await fetch(`/api/gurs/search-parcel?query=${encodeURIComponent(query)}`);
        if (!response.ok) {
            throw new Error(`HTTP napaka! Status: ${response.status}`);
        }
        const data = await response.json();
        console.log("Odgovor iskanja:", data);

        if (data.success && Array.isArray(data.parcels) && data.parcels.length > 0) {
            console.log(`Iskanje uspešno, najdenih ${data.parcels.length} parcel.`);
            currentParcels = data.parcels; // Zamenjamo trenutne parcele z rezultati iskanja
            
            addParcelMarkers(currentParcels); // Doda markerje in centrira pogled
            displayParcelList(currentParcels); // Posodobi seznam na desni

            // Prikaz info za prvo najdeno parcelo
            if (data.parcels[0]) {
                displayParcelInfo(data.parcels[0]);
            }
            
        } else {
             console.warn("Iskanje parcele ni vrnilo rezultatov ali ni bilo uspešno.");
             // Sporočilo uporabniku - bolj specifično, če je mogoče
             let message = 'Parcela ni najdena.';
             if (query.includes('/') && !query.match(/\s\D/)) { // Če je verjetno samo št. brez KO
                 message += ' Poskusite dodati ime katastrske občine (npr. "940/1 Hotič").';
             }
             alert(message);
             // Ne spreminjamo seznama parcel ali markerjev, če iskanje ne uspe
        }
    } catch (error) {
        console.error('❌ Kritična napaka pri iskanju parcele:', error);
        alert('Napaka pri komunikaciji s strežnikom med iskanjem parcele.');
    } finally {
        // Ponastavimo gumb ne glede na rezultat
        searchBtn.disabled = false;
        searchBtn.textContent = 'Išči';
    }
}


function scheduleMapStateSave() {
    if (!sessionId) return; // Ne shranjujemo, če ni seje
    if (mapStateTimer) clearTimeout(mapStateTimer); // Počistimo prejšnji timer
    // Shranimo z zakasnitvijo po koncu premikanja
    mapStateTimer = setTimeout(saveMapState, 1500); // Malo daljša zakasnitev
}

async function saveMapState() {
    if (!sessionId || !map) return; // Preverimo pogoje
    
    const view = map.getView();
    const center3857 = view.getCenter(); // Center v EPSG:3857
    if (!center3857) {
        console.warn("Ne morem dobiti centra pogleda za shranjevanje.");
        return;
    }

    try {
        const centerLonLat = ol.proj.toLonLat(center3857); // Pretvorimo v Lon/Lat (EPSG:4326)
        const zoom = view.getZoom(); // Dobimo nivo zooma (lahko je decimalno)
        
        // Preverimo veljavnost vrednosti
        if (!centerLonLat || centerLonLat.length < 2 || !centerLonLat.every(isFinite) || !isFinite(zoom)) {
            console.warn('Neveljavne vrednosti pogleda za shranjevanje:', centerLonLat, zoom);
            return;
        }

        const payload = {
            center_lon: Number(centerLonLat[0].toFixed(6)), // Zaokrožimo lon
            center_lat: Number(centerLonLat[1].toFixed(6)), // Zaokrožimo lat
            zoom: Math.round(zoom) // Zaokrožimo zoom na celo število
        };

        // Pošljemo na strežnik
        const response = await fetch(`/api/gurs/map-state/${encodeURIComponent(sessionId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            console.log('💾 Stanje zemljevida uspešno shranjeno:', payload);
        } else {
             console.warn(`⚠️ Napaka pri shranjevanju stanja zemljevida: ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        // Ujamemo napake pri pretvorbi koordinat ali pri fetch klicu
        console.error('❌ Napaka pri shranjevanju stanja zemljevida:', error);
    }
}

// Enter za iskanje - dodano preprečevanje oddaje forme
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault(); // Pomembno: prepreči oddajo forme, če je input v formi
                searchParcel(); // Sproži iskanje
            }
        });
    }
});

console.log('✅ GURS zemljevid modul naložen in pripravljen.');