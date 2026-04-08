// ============================================================
// GLOBAL STATE
// ============================================================
let mapInstance = null;
let allMarkers = [];
let allData = [];
let zoneOverlayLayer = null;
let lastTheftCountMap = 0;
let audioContextMap = null;
let audioContextMapResumed = false;
let localIndiaCities = null;

async function loadLocalIndiaCities() {
    if (localIndiaCities) return localIndiaCities;

    const response = await fetch('/assets/data/india_cities.json');
    if (!response.ok) {
        throw new Error('Could not load local India city data.');
    }

    localIndiaCities = await response.json();
    console.log(`Loaded ${localIndiaCities.length} local India cities`);
    return localIndiaCities;
}

function formatHistoryTimestamp(timestamp) {
    if (!timestamp) return "live";
    const date = new Date(timestamp);
    if (!Number.isNaN(date.getTime())) {
        return `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
    }
    return "live";
}

async function loadCityHistory(cityName, target, zoneId = "") {
    const meta = document.getElementById(`drawerHistoryMeta${target}`);
    const bars = document.getElementById(`drawerHistoryBars${target}`);
    if (!meta || !bars) return;

    meta.textContent = "Loading history...";
    bars.innerHTML = "";

    try {
        const query = zoneId ? `?limit=8&zone_id=${encodeURIComponent(zoneId)}` : `?limit=8`;
        const response = await fetch(`/api/city/${encodeURIComponent(cityName)}/history${query}`);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "History unavailable.");
        }

        const history = [...result.history].reverse();
        const maxPower = Math.max(...history.map(item => Number(item.power) || 0), 1);
        const theftCount = result.summary?.theft_count || 0;
        meta.textContent = `${result.summary.samples} samples · ${theftCount} theft flags`;
        bars.innerHTML = history.map((item) => {
            const power = Number(item.power) || 0;
            const height = Math.max(14, (power / maxPower) * 100);
            const statusClass = item.status === "THEFT" ? "is-theft" : "is-normal";
            return `
                <div class="location-history__bar-group">
                    <div class="location-history__bar ${statusClass}" style="height:${height}%;" title="${power.toFixed(0)} W"></div>
                    <span>${formatHistoryTimestamp(item.timestamp)}</span>
                </div>
            `;
        }).join("");
    } catch (error) {
        meta.textContent = error.message;
        bars.innerHTML = "";
    }
}

async function loadZoneConsumers(zoneId, target, fallbackConsumers = []) {
    const meta = document.getElementById(`drawerConsumersMeta${target}`);
    const list = document.getElementById(`drawerConsumersList${target}`);
    if (!meta || !list) return;

    if (!zoneId) {
        meta.textContent = "No zone selected";
        list.innerHTML = "";
        return;
    }

    meta.textContent = "Loading consumers...";
    list.innerHTML = "";

    try {
        const response = await fetch(`/api/zone/${encodeURIComponent(zoneId)}/consumers?limit=6`);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Consumers unavailable.");
        }

        meta.textContent = `${result.consumers.length} consumers`;
        list.innerHTML = result.consumers.map((item) => `
            <div class="location-consumer-card">
                <strong>${item.consumer_name}</strong>
                <span>${item.consumer_type}</span>
                <small>${item.meter_id}</small>
                <p>Avg ${Number(item.avg_power).toFixed(0)}W · Peak ${Number(item.max_power).toFixed(0)}W</p>
            </div>
        `).join("");
    } catch (error) {
        meta.textContent = error.message;
        list.innerHTML = fallbackConsumers.map((item) => `
            <div class="location-consumer-card">
                <strong>${item.consumer_name}</strong>
                <span>${item.consumer_type}</span>
                <small>${item.meter_id}</small>
                <p>${Number(item.power).toFixed(0)}W · ${item.status}</p>
            </div>
        `).join("");
    }
}

function formatDrawerTimestamp(timestamp) {
    if (!timestamp) return "Live feed";
    const date = new Date(Number(timestamp) * 1000);
    if (Number.isNaN(date.getTime())) return "Live feed";
    return date.toLocaleString();
}

function buildDrawerSummary(data) {
    if (data.action_reason) {
        return data.action_reason;
    }
    if (data.status === "THEFT") {
        return `${data.city} is currently flagged as suspicious. Review the risk score, power load, and coordinates before dispatching a field check.`;
    }
    return `${data.city} is currently behaving within normal range, but the live telemetry remains available for verification.`;
}

function openLocationDrawerMap(data) {
    const drawer = document.getElementById("locationDrawerMap");
    const city = document.getElementById("drawerCityMap");
    const status = document.getElementById("drawerStatusMap");
    const risk = document.getElementById("drawerRiskMap");
    const summary = document.getElementById("drawerSummaryMap");
    const grid = document.getElementById("drawerGridMap");
    if (!drawer || !city || !status || !risk || !summary || !grid) return;

    city.textContent = data.location_label || data.city;
    status.textContent = data.status;
    status.className = `location-drawer__badge ${data.status === "THEFT" ? "location-drawer__badge--theft" : "location-drawer__badge--normal"}`;
    risk.textContent = `Risk Score: ${Number(data.risk_score || 0).toFixed(2)}%`;
    summary.textContent = buildDrawerSummary(data);
    grid.innerHTML = `
        <div class="location-drawer__item"><span>City</span><strong>${data.city}</strong></div>
        <div class="location-drawer__item"><span>Zone</span><strong>${data.zone_name || "City-wide"}</strong></div>
        <div class="location-drawer__item"><span>Power</span><strong>${Number(data.power || 0).toFixed(0)} W</strong></div>
        <div class="location-drawer__item"><span>Voltage</span><strong>${Number(data.voltage || 0).toFixed(0)} V</strong></div>
        <div class="location-drawer__item"><span>Current</span><strong>${Number(data.current || 0).toFixed(2)} A</strong></div>
        <div class="location-drawer__item"><span>Severity</span><strong>${data.severity || "normal"}</strong></div>
        <div class="location-drawer__item"><span>Action</span><strong>${data.recommended_action || "No Action"}</strong></div>
        <div class="location-drawer__item"><span>Latitude</span><strong>${Number(data.lat || 0).toFixed(4)}°</strong></div>
        <div class="location-drawer__item"><span>Longitude</span><strong>${Number(data.lon || 0).toFixed(4)}°</strong></div>
        <div class="location-drawer__item"><span>Updated</span><strong>${formatDrawerTimestamp(data.timestamp)}</strong></div>
    `;
    drawer.classList.add("is-open");
    loadCityHistory(data.city, "Map", data.zone_id || "");
    loadZoneConsumers(data.zone_id || "", "Map", data.suspicious_consumers || []);
}

function closeLocationDrawerMap() {
    const drawer = document.getElementById("locationDrawerMap");
    if (drawer) drawer.classList.remove("is-open");
}

// Resume audio context on user interaction
document.addEventListener('click', () => {
    if (audioContextMap && audioContextMap.state === 'suspended') {
        audioContextMap.resume().then(() => {
            audioContextMapResumed = true;
            console.log("✅ Audio context resumed (map)");
        });
    }
});

document.addEventListener('touchstart', () => {
    if (audioContextMap && audioContextMap.state === 'suspended') {
        audioContextMap.resume().then(() => {
            audioContextMapResumed = true;
            console.log("✅ Audio context resumed (map)");
        });
    }
});

// ============================================================
// ALARM FUNCTIONS
// ============================================================

/**
 * Initialize Web Audio API context for alarm sound
 */
function initializeAudioContextMap() {
    try {
        if (!audioContextMap) {
            audioContextMap = new (window.AudioContext || window.webkitAudioContext)();
            console.log("✅ Audio context initialized (map)");
        }
    } catch (err) {
        console.warn("Audio context unavailable (map):", err);
    }
}

/**
 * Play alarm sound using Web Audio API
 */
function playAlarmSoundMap() {
    if (!audioContextMap) {
        console.warn("Audio context not available (map)");
        return;
    }
    
    try {
        if (audioContextMap.state === 'suspended') {
            audioContextMap.resume().then(() => {
                console.log("Audio context resumed, playing sound (map)");
                playAlarmToneMap();
            });
        } else {
            playAlarmToneMap();
        }
    } catch (err) {
        console.error("Error playing alarm sound (map):", err);
    }
}

/**
 * Play the actual alarm tone for map
 */
function playAlarmToneMap() {
    if (!audioContextMap) return;
    
    try {
        const now = audioContextMap.currentTime;
        const duration = 0.3;
        
        const osc1 = audioContextMap.createOscillator();
        const osc2 = audioContextMap.createOscillator();
        const gain = audioContextMap.createGain();
        
        osc1.frequency.value = 1000;
        osc2.frequency.value = 1200;
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioContextMap.destination);
        
        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + duration);
        osc2.stop(now + duration);
        
        console.log("🔊 Alarm sound played (map)");
    } catch (err) {
        console.error("Error in playAlarmToneMap:", err);
    }
}

/**
 * Trigger alarm for theft detection
 */
function triggerAlarmMap(city) {
    const alarmPanel = document.getElementById('alarmPanel');
    const alarmMessage = document.getElementById('alarmMessage');
    
    if (alarmPanel && alarmMessage) {
        alarmMessage.textContent = `🚨 Theft detected in ${city}! Power consumption exceeded threshold.`;
        alarmPanel.classList.remove('hidden');
        
        playAlarmSoundMap();
        
        setTimeout(() => {
            dismissAlarm();
        }, 5000);
    }
}

/**
 * Dismiss alarm
 */
function dismissAlarm() {
    const alarmPanel = document.getElementById('alarmPanel');
    if (alarmPanel) {
        alarmPanel.classList.add('hidden');
    }
}
const diagnostics = {
    leafletLoaded: typeof L !== 'undefined',
    cdnUrls: [
        { name: 'jsDelivr (Primary)', url: 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.js' },
        { name: 'unpkg (Fallback)', url: 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' },
        { name: 'OpenStreetMap Tiles', url: 'https://tile.openstreetmap.org/0/0/0.png' }
    ]
};

async function runDiagnostics() {
    const testsDiv = document.getElementById('tests');
    testsDiv.innerHTML = '';
    
    // Test each CDN
    for (const cdn of diagnostics.cdnUrls) {
        const testItem = document.createElement('div');
        testItem.className = 'test-item';
        const status = document.createElement('div');
        status.className = 'test-status loading';
        const text = document.createElement('span');
        
        testItem.appendChild(status);
        testItem.appendChild(text);
        testsDiv.appendChild(testItem);
        
        try {
            const response = await fetch(cdn.url, { method: 'HEAD', timeout: 5000 });
            status.className = 'test-status pass';
            text.textContent = `✅ ${cdn.name} - Reachable`;
            console.log(`✅ ${cdn.name} reachable`);
        } catch (err) {
            status.className = 'test-status fail';
            text.textContent = `❌ ${cdn.name} - Unreachable`;
            console.log(`❌ ${cdn.name} failed:`, err.message);
        }
    }
}

// ============================================================
// LEAFLET MAP INITIALIZATION
// ============================================================
function initializeLeafletMap() {
    console.log("Initializing Leaflet map...");
    
    try {
        const mapContainer = document.getElementById('map');
        mapContainer.style.display = 'block';
        
        mapInstance = L.map('map').setView([20.5, 78.9], 5);
        console.log("Map initialized successfully");
        fetch("/api/zones/geojson")
            .then((res) => res.json())
            .then((geojson) => {
                zoneOverlayLayer = L.geoJSON(geojson, {
                    style: () => ({
                        color: "#82cfff",
                        weight: 1,
                        opacity: 0.7,
                        fillOpacity: 0.05,
                    }),
                    onEachFeature: (feature, layer) => {
                        const props = feature.properties || {};
                        layer.bindTooltip(`${props.zone_name}, ${props.city}`);
                    },
                }).addTo(mapInstance);
            })
            .catch((error) => console.warn("Zone overlay unavailable:", error));
        
        // Add OpenStreetMap tiles with fallback
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '© OpenStreetMap contributors'
        }).addTo(mapInstance);
        
        // Initialize audio for alarms
        initializeAudioContextMap();
        
        // Load local cities dataset and add search/filter event listeners
        loadLocalIndiaCities().then(() => {
            setupFilterListeners();
        }).catch(() => {
            setupFilterListeners();
        });
        
        function loadData() {
            console.log("Fetching theft data...");
            fetch("/api/live")
                .then(res => res.json())
                .then(data => {
                    console.log(`Loaded ${data.length} locations`);
                    allData = data;
                    
                    // Clear existing markers
                    allMarkers.forEach(marker => mapInstance.removeLayer(marker));
                    allMarkers = [];
                    
                    // Apply filters and add markers
                    applyFilters();
                })
                .catch(err => console.error("Error loading data:", err));
        }
        
        console.log("Starting auto-refresh (3s interval)");
        setInterval(loadData, 3000);
        loadData();
        
    } catch (err) {
        console.error("Leaflet initialization error:", err);
        showFallback();
    }
}

/**
 * Apply current filter selections to map markers
 */
function applyFilters() {
    const searchInput = document.getElementById('citySearch');
    const statusFilter = document.getElementById('statusFilter');
    
    const searchTerm = (searchInput?.value || '').toLowerCase();
    const statusValue = statusFilter?.value || '';
    
    // Clear existing markers
    allMarkers.forEach(marker => mapInstance.removeLayer(marker));
    allMarkers = [];
    
    // Check for new thefts and trigger alarms
    const currentTheftCount = allData.filter(c => c.status === "THEFT").length;
    if (currentTheftCount > lastTheftCountMap) {
        const theftCities = allData.filter(c => c.status === "THEFT");
        if (theftCities.length > 0) {
            triggerAlarmMap(theftCities[0].city);
        }
    }
    lastTheftCountMap = currentTheftCount;
    
    // Filter and add markers
    allData.forEach(d => {
        if (!d.lat || !d.lon) return;
        
        // Apply search filter
        if (searchTerm && !d.city.toLowerCase().includes(searchTerm)) {
            return;
        }
        
        // Apply status filter
        if (statusValue && d.status !== statusValue) {
            return;
        }
        
        // Add marker
        const isTheft = d.status === "THEFT";
        const marker = L.circleMarker([d.lat, d.lon], {
            radius: 8,
            color: isTheft ? "#ef4444" : "#16c784",
            weight: 2,
            opacity: 0.8,
            fillOpacity: 0.6
        }).addTo(mapInstance).bindPopup(
            `<strong>${d.location_label || d.city}</strong><br/>
            Status: ${d.status}<br/>
            Power: ${d.power.toFixed(0)}W`
        );
        marker.on('click', () => openLocationDrawerMap(d));
        
        allMarkers.push(marker);
    });
}

/**
 * Setup filter event listeners
 */
function setupFilterListeners() {
    const searchInput = document.getElementById('citySearch');
    const statusFilter = document.getElementById('statusFilter');
    
    if (searchInput) {
        searchInput.addEventListener('input', applyFilters);
    }
    
    if (statusFilter) {
        statusFilter.addEventListener('change', applyFilters);
    }
}

/**
 * Reset all filters
 */
function resetFilters() {
    const searchInput = document.getElementById('citySearch');
    const statusFilter = document.getElementById('statusFilter');
    
    if (searchInput) searchInput.value = '';
    if (statusFilter) statusFilter.value = '';
    
    applyFilters();
}

// ============================================================
// FALLBACK VIEW (Table-based without Leaflet)
// ============================================================
function showFallback() {
    console.log("Showing fallback view...");
    
    const diagnosticsDiv = document.getElementById('diagnostics');
    const mapDiv = document.getElementById('map');
    
    mapDiv.style.display = 'none';
    diagnosticsDiv.style.display = 'block';
    
    runDiagnostics();
    
    // Show theft locations in list form
    async function updateFallback() {
        try {
            const response = await fetch('/api/live');
            const data = await response.json();
            
            const listDiv = document.getElementById('fallback-list');
            listDiv.innerHTML = '';
            
            data.forEach(d => {
                const item = document.createElement('div');
                item.className = `location-item ${d.status === 'THEFT' ? 'theft' : 'normal'}`;
                item.innerHTML = `
                    <strong>${d.location_label || d.city}</strong> - ${d.status}
                    <br/><small>Coordinates: ${d.lat.toFixed(2)}, ${d.lon.toFixed(2)}</small>
                    <br/><small>Power: ${d.power.toFixed(0)}W</small>
                `;
                item.addEventListener('click', () => openLocationDrawerMap(d));
                listDiv.appendChild(item);
            });
        } catch (err) {
            console.error("Error loading fallback data:", err);
        }
    }
    
    updateFallback();
    setInterval(updateFallback, 3000);
}

// ============================================================
// MAIN INITIALIZATION
// ============================================================
if (typeof L !== 'undefined') {
    console.log("✅ Leaflet loaded, initializing map...");
    initializeLeafletMap();
} else {
    console.error("❌ Leaflet not loaded, showing fallback...");
    // Wait a moment for CDN scripts to load
    setTimeout(() => {
        if (typeof L !== 'undefined') {
            initializeLeafletMap();
        } else {
            showFallback();
        }
    }, 2000);
}

/**
 * Search for a city using the Nominatim API and pan the map to its location.
 */
async function searchCity() {
    const searchInput = document.getElementById('citySearch');
    const cityName = searchInput?.value.trim();

    if (!cityName) {
        alert('Please enter a city name.');
        return;
    }

    // First try local dataset
    try {
        await loadLocalIndiaCities();
        if (localIndiaCities) {
            const found = localIndiaCities.find(c => c.city.toLowerCase() === cityName.toLowerCase()) || localIndiaCities.find(c => c.city.toLowerCase().startsWith(cityName.toLowerCase()));
            if (found) {
                mapInstance.setView([found.lat, found.lon], 12);
                const marker = L.marker([found.lat, found.lon]).addTo(mapInstance).bindPopup(`<strong>${found.city}</strong><br/><small>${found.state}</small>`).openPopup();
                allMarkers.push(marker);
                return;
            }
        }
    } catch (err) {
        console.warn('Local lookup failed, falling back to Nominatim');
    }

    // Fallback to Nominatim
    try {
        const response = await fetch(`https://nominatim.openstreetmap.org/search?city=${encodeURIComponent(cityName)}&country=India&format=json`);
        const results = await response.json();

        if (results.length === 0) {
            alert('City not found. Please try another name.');
            return;
        }

        const { lat, lon, display_name } = results[0];
        mapInstance.setView([parseFloat(lat), parseFloat(lon)], 12);

        // Optionally, add a marker for the searched city
        const marker = L.marker([lat, lon]).addTo(mapInstance).bindPopup(`<strong>${display_name.split(',')[0]}</strong>`).openPopup();
        allMarkers.push(marker);
    } catch (error) {
        console.error('Error searching for city:', error);
        alert('An error occurred while searching for the city.');
    }
}

// Add event listener for the search button
const searchButton = document.getElementById('searchButton');
if (searchButton) {
    searchButton.addEventListener('click', searchCity);
}
