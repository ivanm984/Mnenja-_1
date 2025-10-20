// GURS Zemljevid JavaScript - CELOTNA VERZIJA

let map;
let ortofotoLayer;
let katastrLayer;
let stavbeLayer;
let namenskaRabaLayer;
let dtmLayer;
let poplavnaLayer;
let vectorLayer;
let currentParcels = [];
let selectedParcel = null;

// Litija koordinate - PRAVILNE!
const LITIJA_CENTER = [14.8267, 46.0569];
const DEFAULT_ZOOM = 14;

// Inicializacija ob nalaganju
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Inicializacija GURS zemljevida...');
    
    if (typeof ol === 'undefined') {
        console.error('❌ OpenLayers ni naložen!');
        alert('Napaka: OpenLayers knjižnica ni naložena.');
        return;
    }
    
    console.log('✅ OpenLayers naložen, verzija:', ol.VERSION || 'unknown');
    
    initMap();
    loadSessionParcels();
});

function initMap() {
    console.log('🗺️ Kreiram zemljevid...');
    
    // OpenStreetMap backup
    const osmLayer = new ol.layer.Tile({
        source: new ol.source.OSM(),
        visible: false
    });
    
    // GURS SLOJI
    
    // 1. Ortofoto - Glavna podlaga
    ortofotoLayer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: 'https://e-prostor.gov.si/egp/services/javni/OGC_EPSG3857_RASTER/MapServer/WMSServer',
            params: {
                'LAYERS': 'DOF',
                'TILED': true,
                'FORMAT': 'image/jpeg'
            },
            serverType: 'geoserver'
        }),
        visible: true,
        name: 'ortofoto'
    });
    
    // 2. Katastrske meje - Vedno vidne
    katastrLayer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: 'https://prostor.gov.si/wms',
            params: {
                'LAYERS': 'KN_ZK',
                'TILED': true,
                'TRANSPARENT': true,
                'FORMAT': 'image/png'
            },
            serverType: 'geoserver'
        }),
        visible: true,
        opacity: 0.7,
        name: 'katastr'
    });
    
    // 3. Stavbe
    stavbeLayer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: 'https://prostor.gov.si/wms',
            params: {
                'LAYERS': 'KN_SN',
                'TILED': true,
                'TRANSPARENT': true,
                'FORMAT': 'image/png'
            },
            serverType: 'geoserver'
        }),
        visible: false,
        opacity: 0.6,
        name: 'stavbe'
    });
    
    // 4. Namenska raba
    namenskaRabaLayer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: 'https://prostor.gov.si/wms',
            params: {
                'LAYERS': 'OPN_RABA',
                'TILED': true,
                'TRANSPARENT': true,
                'FORMAT': 'image/png'
            },
            serverType: 'geoserver'
        }),
        visible: false,
        opacity: 0.6,
        name: 'namenska_raba'
    });
    
    // 5. DTM - Digitalni model terena
    dtmLayer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: 'https://prostor.gov.si/wms',
            params: {
                'LAYERS': 'DTM',
                'TILED': true,
                'TRANSPARENT': true,
                'FORMAT': 'image/png'
            },
            serverType: 'geoserver'
        }),
        visible: false,
        opacity: 0.5,
        name: 'dtm'
    });
    
    // 6. Poplavna območja
    poplavnaLayer = new ol.layer.Tile({
        source: new ol.source.TileWMS({
            url: 'https://prostor.gov.si/wms',
            params: {
                'LAYERS': 'POP',
                'TILED': true,
                'TRANSPARENT': true,
                'FORMAT': 'image/png'
            },
            serverType: 'geoserver'
        }),
        visible: false,
        opacity: 0.5,
        name: 'poplave'
    });
    
    // Kreiraj zemljevid
    map = new ol.Map({
        target: 'map',
        layers: [
            osmLayer,
            ortofotoLayer,
            dtmLayer,
            poplavnaLayer,
            namenskaRabaLayer,
            stavbeLayer,
            katastrLayer
        ],
        view: new ol.View({
            center: ol.proj.fromLonLat(LITIJA_CENTER),
            zoom: DEFAULT_ZOOM
        })
    });
    
    console.log('✅ Zemljevid inicializiran');
    console.log('📍 Center:', LITIJA_CENTER);
    
    // Klik event
    map.on('singleclick', handleMapClick);
}

async function handleMapClick(evt) {
    console.log('🖱️ Klik na:', evt.coordinate);
    
    const viewResolution = map.getView().getResolution();
    const url = katastrLayer.getSource().getFeatureInfoUrl(
        evt.coordinate,
        viewResolution,
        'EPSG:3857',
        { 'INFO_FORMAT': 'application/json' }
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
        stevilka: props.ST_PARCELE || props.PARCELA || 'Neznano',
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
    
    map.addLayer(vectorLayer);
    
    // Centriraj na parcele
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
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');
    
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
        center: ol.proj.fromLonLat(LITIJA_CENTER),
        zoom: DEFAULT_ZOOM,
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

// Preklapljanje slojev
function changeLayer(layerType) {
    console.log('🔄 Preklapljam na:', layerType);
    
    // Izklopi vse razen izbrane
    ortofotoLayer.setVisible(layerType === 'ortofoto');
    namenskaRabaLayer.setVisible(layerType === 'namenska_raba');
    stavbeLayer.setVisible(layerType === 'stavbe');
    dtmLayer.setVisible(layerType === 'dtm');
    poplavnaLayer.setVisible(layerType === 'poplave');
    
    // Katastrske meje vedno vidne
    katastrLayer.setVisible(true);
    
    // Posodobi UI
    document.querySelectorAll('.layer-option').forEach(option => {
        const radio = option.querySelector('input[type="radio"]');
        if (radio.checked) {
            option.classList.add('active');
        } else {
            option.classList.remove('active');
        }
    });
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