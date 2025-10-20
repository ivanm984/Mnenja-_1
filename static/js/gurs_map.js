// GURS Zemljevid JavaScript - POSODOBLJENA VERZIJA

let map;
let baseLayerMap = new Map();
let overlayLayerMap = new Map();
let dynamicLayerMap = new Map();
let vectorLayer;
let katastrLayer;
let currentParcels = [];
let selectedParcel = null;
let sessionId = null;
let mapConfig = {
    defaultCenter: [14.8267, 46.0569],
    defaultZoom: 14,
    wmsUrl: 'https://prostor.gov.si/wms',
    rasterWmsUrl: 'https://prostor3.gov.si/egp/services/javni/OGC_EPSG3857_RASTER/MapServer/WMSServer',
    baseLayers: [],
    overlayLayers: []
};
let savedMapState = null;
let mapStateTimer = null;

const LAYER_ICONS = {
    ortofoto: '📷',
    namenska_raba: '🏘️',
    katastr: '📐',
    stavbe: '🏢',
    dtm: '⛰️',
    poplavna: '🌊'
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
    initMap();
    registerMapInteractions();
    buildLayerSelectors();
    await loadSessionParcels();
    await loadWmsCapabilities();
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
        const data = await response.json();
        if (data.success && data.config) {
            mapConfig = {
                defaultCenter: data.config.default_center || mapConfig.defaultCenter,
                defaultZoom: data.config.default_zoom || mapConfig.defaultZoom,
                wmsUrl: data.config.wms_url || mapConfig.wmsUrl,
                rasterWmsUrl: data.config.raster_wms_url || mapConfig.rasterWmsUrl,
                baseLayers: data.config.base_layers || [],
                overlayLayers: data.config.overlay_layers || []
            };
            savedMapState = data.config.saved_state || null;
            console.log('🧭 Map config:', mapConfig, 'saved state:', savedMapState);
        }
    } catch (error) {
        console.warn('⚠️ Map config ni bilo mogoče naložiti, uporabljam privzete vrednosti.', error);
    }
}

function initMap() {
    console.log('🗺️ Kreiram zemljevid...');

    const viewCenter = savedMapState?.center || mapConfig.defaultCenter;
    const viewZoom = savedMapState?.zoom || mapConfig.defaultZoom;

    baseLayerMap = new Map();
    overlayLayerMap = new Map();
    dynamicLayerMap = new Map();
    katastrLayer = null;

    const osmLayer = new ol.layer.Tile({
        source: new ol.source.OSM(),
        visible: false
    });

    const baseLayers = mapConfig.baseLayers.map(createTileLayerFromConfig);
    if (baseLayers.length === 0) {
        baseLayers.push(createTileLayerFromConfig({
            id: 'ortofoto',
            name: 'DOF',
            title: 'Digitalni ortofoto',
            url: mapConfig.rasterWmsUrl,
            format: 'image/jpeg',
            transparent: false,
            default_visible: true
        }));
        baseLayers.push(createTileLayerFromConfig({
            id: 'namenska_raba',
            name: 'OPN_RABA',
            title: 'Namenska raba',
            url: mapConfig.wmsUrl,
            format: 'image/png',
            transparent: true,
            default_visible: false
        }));
        mapConfig.baseLayers = [
            { id: 'ortofoto', name: 'DOF', title: 'Digitalni ortofoto', url: mapConfig.rasterWmsUrl, format: 'image/jpeg', transparent: false, default_visible: true },
            { id: 'namenska_raba', name: 'OPN_RABA', title: 'Namenska raba', url: mapConfig.wmsUrl, format: 'image/png', transparent: true, default_visible: false }
        ];
    }

    let overlayConfigs = mapConfig.overlayLayers.slice();
    if (!overlayConfigs.some(cfg => cfg.id === 'katastr')) {
        overlayConfigs.push({
            id: 'katastr',
            name: 'KN_ZK',
            title: 'Parcelne meje',
            url: mapConfig.wmsUrl,
            format: 'image/png',
            transparent: true,
            default_visible: true,
            always_on: true
        });
        mapConfig.overlayLayers = overlayConfigs;
    }

    const overlayLayers = overlayConfigs.map(cfg => {
        const layer = createTileLayerFromConfig(cfg, true);
        if (cfg.id === 'katastr') {
            katastrLayer = layer;
        }
        return layer;
    });

    const layers = [osmLayer, ...baseLayers, ...overlayLayers];

    map = new ol.Map({
        target: 'map',
        layers,
        view: new ol.View({
            center: ol.proj.fromLonLat(viewCenter),
            zoom: viewZoom
        })
    });

    console.log('✅ Zemljevid inicializiran');
    console.log('📍 Začetni center:', viewCenter, 'zoom:', viewZoom);

    map.on('singleclick', handleMapClick);
}

function registerMapInteractions() {
    map.on('moveend', scheduleMapStateSave);
}

function createTileLayerFromConfig(cfg, isOverlay = false) {
    const url = cfg.url || mapConfig.wmsUrl;
    const format = cfg.format || 'image/png';
    const transparent = cfg.transparent !== undefined ? cfg.transparent : true;
    const visible = cfg.default_visible ?? true;

    const layerName = cfg.name || cfg.id;
    const layer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url,
            params: {
                LAYERS: layerName,
                TILED: true,
                FORMAT: format,
                TRANSPARENT: transparent
            },
            crossOrigin: 'anonymous'
        }),
        visible,
        opacity: transparent ? (cfg.opacity ?? 0.75) : 1,
        name: cfg.id || layerName
    });

    if (isOverlay) {
        overlayLayerMap.set(cfg.id, layer);
        layer.setZIndex(50 + overlayLayerMap.size);
        if (cfg.always_on) {
            layer.setVisible(true);
        }
    } else {
        baseLayerMap.set(cfg.id, layer);
        layer.setZIndex(baseLayerMap.size);
    }

    return layer;
}

function buildLayerSelectors() {
    const baseContainer = document.getElementById('baseLayerOptions');
    const overlayContainer = document.getElementById('overlayLayerOptions');

    if (!baseContainer || !overlayContainer) {
        return;
    }

    baseContainer.innerHTML = '';
    overlayContainer.innerHTML = '';

    let activeBase = null;
    baseLayerMap.forEach((layer, id) => {
        if (layer.getVisible()) {
            activeBase = id;
        }
    });
    if (!activeBase && baseLayerMap.size > 0) {
        activeBase = baseLayerMap.keys().next().value;
        switchBaseLayer(activeBase);
    }

    baseLayerMap.forEach((layer, id) => {
        const cfg = mapConfig.baseLayers.find(l => l.id === id) || { id, title: id };
        const label = document.createElement('label');
        label.className = 'layer-option' + (id === activeBase ? ' active' : '');

        const input = document.createElement('input');
        input.type = 'radio';
        input.name = 'base-layer';
        input.value = id;
        input.checked = id === activeBase;
        input.addEventListener('change', () => switchBaseLayer(id));

        const icon = LAYER_ICONS[id] || '🗺️';
        const span = document.createElement('span');
        span.textContent = `${icon} ${cfg.title || id}`;

        label.appendChild(input);
        label.appendChild(span);
        baseContainer.appendChild(label);
    });

    overlayLayerMap.forEach((layer, id) => {
        const cfg = mapConfig.overlayLayers.find(l => l.id === id) || { id, title: id };
        const label = document.createElement('label');
        const isActive = layer.getVisible();
        label.className = 'layer-option' + (isActive ? ' active' : '');

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = id;
        input.checked = isActive;
        input.disabled = cfg.always_on || false;
        input.addEventListener('change', () => toggleOverlayLayer(id, input.checked));

        const icon = LAYER_ICONS[id] || '🗂️';
        const span = document.createElement('span');
        span.textContent = `${icon} ${cfg.title || id}`;

        label.appendChild(input);
        label.appendChild(span);
        overlayContainer.appendChild(label);
    });
}

function switchBaseLayer(layerId) {
    baseLayerMap.forEach((layer, id) => {
        layer.setVisible(id === layerId);
    });

    document.querySelectorAll('#baseLayerOptions .layer-option').forEach(option => {
        const input = option.querySelector('input');
        if (input) {
            option.classList.toggle('active', input.value === layerId);
        }
    });
}

function toggleOverlayLayer(layerId, visible) {
    const layer = overlayLayerMap.get(layerId);
    if (!layer) return;

    const cfg = mapConfig.overlayLayers.find(l => l.id === layerId);
    if (cfg?.always_on) {
        layer.setVisible(true);
        return;
    }

    layer.setVisible(visible);
    document.querySelectorAll('#overlayLayerOptions .layer-option').forEach(option => {
        const input = option.querySelector('input');
        if (input && input.value === layerId) {
            option.classList.toggle('active', input.checked);
        }
    });
}

async function loadWmsCapabilities() {
    const status = document.getElementById('capabilityStatus');
    const list = document.getElementById('capabilityLayers');
    if (!status || !list) return;

    try {
        const response = await fetch('/api/gurs/wms-capabilities');
        const data = await response.json();
        if (data.success && Array.isArray(data.layers)) {
            status.textContent = data.source === 'remote'
                ? 'Klikni na sloj za dodajanje na zemljevid'
                : 'Uporabljam privzete sloje (ni povezave do WMS)';
            renderCapabilityLayers(data.layers, data.wms_url, list);
        } else {
            status.textContent = 'Sloji niso na voljo.';
        }
    } catch (error) {
        console.error('❌ Napaka pri nalaganju WMS capabilities:', error);
        status.textContent = 'Slojev ni bilo mogoče naložiti.';
    }
}

function renderCapabilityLayers(layers, wmsUrl, container) {
    container.innerHTML = '';
    const knownNames = new Set();
    mapConfig.baseLayers.forEach(l => knownNames.add(l.name));
    mapConfig.overlayLayers.forEach(l => knownNames.add(l.name));

    const limitedLayers = layers.slice(0, 40);

    limitedLayers.forEach(layer => {
        if (!layer.name || knownNames.has(layer.name)) {
            return;
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'layer-chip';

        const info = document.createElement('span');
        info.textContent = layer.title || layer.name;

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.textContent = dynamicLayerMap.has(layer.name) ? 'Odstrani' : 'Dodaj';

        toggleBtn.addEventListener('click', () => {
            if (dynamicLayerMap.has(layer.name)) {
                removeDynamicLayer(layer.name);
                toggleBtn.textContent = 'Dodaj';
            } else {
                addDynamicLayer(layer, wmsUrl);
                toggleBtn.textContent = 'Odstrani';
            }
        });

        wrapper.appendChild(info);
        wrapper.appendChild(toggleBtn);
        container.appendChild(wrapper);
    });
}

function addDynamicLayer(layerInfo, wmsUrl) {
    if (!layerInfo?.name) return;

    const layer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: wmsUrl || mapConfig.wmsUrl,
            params: {
                LAYERS: layerInfo.name,
                TILED: true,
                FORMAT: 'image/png',
                TRANSPARENT: true
            },
            crossOrigin: 'anonymous'
        }),
        opacity: 0.7,
        visible: true
    });

    layer.setZIndex(60 + dynamicLayerMap.size);
    dynamicLayerMap.set(layerInfo.name, layer);
    map.addLayer(layer);
    console.log('➕ Dodan WMS sloj:', layerInfo.name);
}

function removeDynamicLayer(layerName) {
    const layer = dynamicLayerMap.get(layerName);
    if (!layer) return;
    map.removeLayer(layer);
    dynamicLayerMap.delete(layerName);
    console.log('➖ Odstranjen WMS sloj:', layerName);
}

async function handleMapClick(evt) {
    console.log('🖱️ Klik na:', evt.coordinate);

    if (!katastrLayer) {
        console.warn('⚠️ Katastrska plast ni na voljo.');
        return;
    }

    const viewResolution = map.getView().getResolution();
    const url = katastrLayer.getSource().getFeatureInfoUrl(
        evt.coordinate,
        viewResolution,
        'EPSG:3857',
        { INFO_FORMAT: 'application/json' }
    );

    if (url) {
        try {
            const response = await fetch(url);
            const data = await response.json();

            if (data.features && data.features.length > 0) {
                handleParcelClick(data.features[0]);
            }
        } catch (error) {
            console.error('❌ GetFeatureInfo napaka:', error);
        }
    }
}

function handleParcelClick(feature) {
    const props = feature.properties || {};

    selectedParcel = {
        stevilka: props.ST_PARCE || props.PARCELA || 'Neznano',
        katastrska_obcina: props.IME_KO || props.KO || 'Neznano',
        povrsina: props.POVRSINA || props.SURFACE || 0,
        namenska_raba: props.RABA || 'Ni podatka'
    };

    displayParcelInfo(selectedParcel);
}

function displayParcelInfo(parcel) {
    const infoDiv = document.getElementById('parcelInfo');
    const emptyState = document.getElementById('emptyState');
    const contentDiv = document.getElementById('parcelInfoContent');

    if (!infoDiv || !contentDiv || !emptyState) return;

    infoDiv.style.display = 'block';
    emptyState.style.display = 'none';

    contentDiv.innerHTML = `
        <div class="info-row">
            <div class="info-label">Parcela</div>
            <div class="info-value">${parcel.stevilka}</div>
        </div>
        <div class="info-row">
            <div class="info-label">Katastrska občina</div>
            <div class="info-value">${parcel.katastrska_obcina}</div>
        </div>
        <div class="info-row">
            <div class="info-label">Površina</div>
            <div class="info-value">${parcel.povrsina} m²</div>
        </div>
        <div class="info-row">
            <div class="info-label">Namenska raba</div>
            <div class="info-value">${parcel.namenska_raba}</div>
        </div>
    `;
}

function addParcelMarkers(parcels) {
    console.log('📍 Dodajam', parcels.length, 'markerjev');

    if (vectorLayer) {
        map.removeLayer(vectorLayer);
    }

    const features = parcels.map(parcel => {
        const feature = new ol.Feature({
            geometry: new ol.geom.Point(ol.proj.fromLonLat(parcel.coordinates)),
            parcel: parcel
        });

        feature.setStyle(new ol.style.Style({
            image: new ol.style.Circle({
                radius: 10,
                fill: new ol.style.Fill({ color: 'rgba(99, 102, 241, 0.8)' }),
                stroke: new ol.style.Stroke({ color: '#fff', width: 3 })
            }),
            text: new ol.style.Text({
                text: parcel.stevilka,
                offsetY: -25,
                font: 'bold 14px Inter',
                fill: new ol.style.Fill({ color: '#fff' }),
                stroke: new ol.style.Stroke({ color: '#1e293b', width: 4 }),
                backgroundFill: new ol.style.Fill({ color: 'rgba(99, 102, 241, 0.95)' }),
                padding: [6, 10, 6, 10]
            })
        }));

        return feature;
    });

    const vectorSource = new ol.source.Vector({ features });
    vectorLayer = new ol.layer.Vector({ source: vectorSource });
    vectorLayer.setZIndex(100);

    map.addLayer(vectorLayer);

    if (features.length > 0) {
        const extent = vectorSource.getExtent();
        map.getView().fit(extent, {
            padding: [100, 100, 100, 100],
            duration: 1500,
            maxZoom: 17
        });
        console.log('✅ Centriran na parcele');
    }
}

async function loadSessionParcels() {
    if (!sessionId) {
        console.log('⚠️ Ni session_id');
        return;
    }

    console.log('🔍 Nalagam parcele za session:', sessionId);

    try {
        const response = await fetch(`/api/gurs/session-parcels/${sessionId}`);
        const data = await response.json();

        console.log('📦 Parcele:', data);

        if (data.success && data.parcels && data.parcels.length > 0) {
            console.log(`✅ Najdenih ${data.parcels.length} parcel`);
            currentParcels = data.parcels;

            addParcelMarkers(currentParcels);
            displayParcelList(currentParcels);

            if (currentParcels.length > 0) {
                displayParcelInfo(currentParcels[0]);
            }
        } else {
            console.log('⚠️ Ni najdenih parcel');
        }
    } catch (error) {
        console.error('❌ Napaka:', error);
    }
}

function displayParcelList(parcels) {
    const listDiv = document.getElementById('parcelList');
    const countSpan = document.getElementById('parcelCount');
    const contentDiv = document.getElementById('parcelListContent');

    if (!listDiv || !countSpan || !contentDiv) return;

    if (parcels.length === 0) {
        listDiv.style.display = 'none';
        return;
    }

    listDiv.style.display = 'block';
    countSpan.textContent = `(${parcels.length})`;

    contentDiv.innerHTML = parcels.map((parcel, idx) => `
        <div class="parcel-item" onclick="selectParcel(${idx})">
            <div class="parcel-number">${parcel.stevilka}</div>
            <div class="parcel-details">
                ${parcel.katastrska_obcina} • ${parcel.povrsina} m²
            </div>
        </div>
    `).join('');
}

function selectParcel(index) {
    const parcel = currentParcels[index];
    if (parcel && parcel.coordinates) {
        displayParcelInfo(parcel);
        map.getView().animate({
            center: ol.proj.fromLonLat(parcel.coordinates),
            zoom: 17,
            duration: 1000
        });
    }
}

// Kontrole
function zoomIn() {
    const view = map.getView();
    view.animate({ zoom: view.getZoom() + 1, duration: 250 });
}

function zoomOut() {
    const view = map.getView();
    view.animate({ zoom: view.getZoom() - 1, duration: 250 });
}

function resetView() {
    map.getView().animate({
        center: ol.proj.fromLonLat(mapConfig.defaultCenter),
        zoom: mapConfig.defaultZoom,
        duration: 1000
    });
}

// Iskanje
async function searchParcel() {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const query = searchInput.value.trim();

    if (!query) {
        alert('Vnesite številko parcele');
        return;
    }

    searchBtn.disabled = true;
    searchBtn.textContent = 'Iščem...';

    try {
        const response = await fetch(`/api/gurs/search-parcel?query=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.success && data.parcels && data.parcels.length > 0) {
            currentParcels = data.parcels;
            addParcelMarkers(currentParcels);
            displayParcelList(currentParcels);

            if (data.parcels.length === 1) {
                displayParcelInfo(data.parcels[0]);
            }
        } else {
            alert('Parcela ni najdena');
        }
    } catch (error) {
        console.error('Napaka:', error);
        alert('Napaka pri iskanju');
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = 'Išči';
    }
}

function scheduleMapStateSave() {
    if (!sessionId) return;
    if (mapStateTimer) {
        clearTimeout(mapStateTimer);
    }
    mapStateTimer = setTimeout(saveMapState, 1200);
}

async function saveMapState() {
    if (!sessionId) return;
    const view = map.getView();
    const center3857 = view.getCenter();
    if (!center3857) return;

    const [lon, lat] = ol.proj.toLonLat(center3857);
    const payload = {
        center_lon: Number(lon.toFixed(6)),
        center_lat: Number(lat.toFixed(6)),
        zoom: Math.round(view.getZoom())
    };

    try {
        await fetch(`/api/gurs/map-state/${encodeURIComponent(sessionId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        console.log('💾 Shranjeno stanje zemljevida', payload);
    } catch (error) {
        console.warn('⚠️ Ni bilo mogoče shraniti stanja zemljevida:', error);
    }
}

// Enter za iskanje
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchParcel();
            }
        });
    }
});

console.log('✅ GURS zemljevid modul naložen');
