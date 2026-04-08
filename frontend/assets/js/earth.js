// SIMPLE 3D EARTH VIEWER
console.log("Earth.js loaded");
console.log("Cesium available:", typeof Cesium !== 'undefined');

let viewer = null;
let allDataEarth = [];
let lastTheftCountEarth = 0;
let audioContextEarth = null;
let audioContextEarthResumed = false;
let searchMarkerEarth = null;
let earthRefreshTimer = null;
let fallbackImageryProviderEarth = null;

function setImageryStatus(message, isActive = false) {
    const badge = document.getElementById('imageryStatus');
    if (!badge) return;
    badge.textContent = message;
    badge.className = `imagery-status ${isActive ? 'imagery-status--active' : 'imagery-status--fallback'}`;
}

async function fetchCesiumToken() {
    try {
        const response = await fetch('/api/cesium-token');
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'Cesium token unavailable.');
        }
        return (result.token || '').trim();
    } catch (error) {
        console.warn('Cesium token request failed:', error);
        return '';
    }
}

function focusEarthLocation(latNum, lonNum, label, locationData = null) {
    if (!viewer) {
        alert('Viewer not ready yet.');
        return;
    }

    smoothFlyToEarth(latNum, lonNum, 50000, 2.8);

    if (searchMarkerEarth) {
        viewer.entities.remove(searchMarkerEarth);
        searchMarkerEarth = null;
    }

    searchMarkerEarth = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lonNum, latNum),
        point: {
            pixelSize: 16,
            color: Cesium.Color.ORANGE,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2
        },
        label: {
            text: label,
            font: 'bold 14px Arial',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -18)
        }
    });

    if (locationData) {
        searchMarkerEarth.smartTheftData = locationData;
        openLocationDrawerEarth(locationData);
    }
}

function smoothFlyToEarth(latNum, lonNum, height = 2000000, duration = 2.4) {
    if (!viewer) return;

    viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lonNum, latNum, height),
        orientation: {
            heading: Cesium.Math.toRadians(0),
            pitch: Cesium.Math.toRadians(-45),
            roll: 0
        },
        duration,
        easingFunction: Cesium.EasingFunction.CUBIC_OUT
    });
}

function findLiveLocationMatch(name) {
    const query = name.trim().toLowerCase();
    if (!query) return null;

    return allDataEarth.find((item) =>
        item.city?.toLowerCase() === query ||
        item.zone_name?.toLowerCase() === query ||
        item.location_label?.toLowerCase() === query
    ) || allDataEarth.find((item) =>
        item.city?.toLowerCase().includes(query) ||
        item.zone_name?.toLowerCase().includes(query) ||
        item.location_label?.toLowerCase().includes(query)
    ) || null;
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
        return `${data.city} is currently marked as a likely theft hotspot. Use this view to understand where the alert sits spatially before dispatching a response.`;
    }
    return `${data.city} is currently classified as normal, and the 3D Earth view helps confirm its geographic context against the wider network.`;
}

function openLocationDrawerEarth(data) {
    const drawer = document.getElementById("locationDrawerEarth");
    const city = document.getElementById("drawerCityEarth");
    const status = document.getElementById("drawerStatusEarth");
    const risk = document.getElementById("drawerRiskEarth");
    const summary = document.getElementById("drawerSummaryEarth");
    const grid = document.getElementById("drawerGridEarth");
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
    loadCityHistory(data.city, "Earth", data.zone_id || "");
    loadZoneConsumers(data.zone_id || "", "Earth", data.suspicious_consumers || []);
}

function closeLocationDrawerEarth() {
    const drawer = document.getElementById("locationDrawerEarth");
    if (drawer) drawer.classList.remove("is-open");
}

function setPanelOpen(panel, button, open) {
    if (!panel || !button) return;
    panel.classList.toggle("is-open", open);
    panel.setAttribute("aria-hidden", String(!open));
    button.setAttribute("aria-expanded", String(open));
}

function setEarthModeActive(mode) {
    const modeIds = {
        featured: ["earthTabFeatured", "earthModeFeatured"],
        trending: ["earthTabTrending", "earthModeTrending"],
        latest: ["earthTabLatest", "earthModeLatest"]
    };

    Object.values(modeIds).flat().forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.classList.remove("is-active");
    });

    (modeIds[mode] || []).forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.classList.add("is-active");
    });
}

function openEarthSearchPanel() {
    const panel = document.getElementById("earthControlsPanel");
    const panelToggle = document.getElementById("earthPanelToggle");
    setPanelOpen(panel, panelToggle, true);
    setEarthModeActive("featured");
    const input = document.getElementById("citySearchEarth");
    if (input) {
        input.focus();
        input.select?.();
    }
}

function resetEarthView() {
    const panel = document.getElementById("earthControlsPanel");
    const panelToggle = document.getElementById("earthPanelToggle");
    setPanelOpen(panel, panelToggle, false);
    resetFiltersEarth();
    flyHomeEarth();
    setEarthModeActive("featured");
}

function flyHomeEarth() {
    smoothFlyToEarth(20.5, 78.9, 2000000, 2.2);
}

function getPriorityHotspotEarth() {
    const candidates = allDataEarth.filter((item) => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon)));
    if (!candidates.length) return null;

    return [...candidates].sort((a, b) => {
        const aTheft = a.status === "THEFT" ? 1 : 0;
        const bTheft = b.status === "THEFT" ? 1 : 0;
        if (aTheft !== bTheft) return bTheft - aTheft;

        const aTime = Number.isFinite(Date.parse(a.timestamp)) ? Date.parse(a.timestamp) : 0;
        const bTime = Number.isFinite(Date.parse(b.timestamp)) ? Date.parse(b.timestamp) : 0;
        if (aTime !== bTime) return bTime - aTime;

        return Number(b.risk_score || 0) - Number(a.risk_score || 0);
    })[0];
}

function focusLatestHotspotEarth() {
    const spot = getPriorityHotspotEarth();
    if (!spot) return;
    const panel = document.getElementById("earthControlsPanel");
    const panelToggle = document.getElementById("earthPanelToggle");
    setPanelOpen(panel, panelToggle, false);
    setEarthModeActive("latest");
    focusEarthLocation(
        Number(spot.lat),
        Number(spot.lon),
        spot.location_label || spot.city,
        spot
    );
}

function bindEarthButton(buttonId, handler) {
    const button = document.getElementById(buttonId);
    if (button && !button.dataset.bound) {
        button.dataset.bound = "true";
        button.addEventListener("click", handler);
    }
}

function bindEarthChromeControls() {
    const panel = document.getElementById("earthControlsPanel");
    const panelToggle = document.getElementById("earthPanelToggle");
    const panelClose = document.getElementById("earthPanelClose");
    const diagnostics = document.getElementById("diagnostics");
    const fallbackToggle = document.getElementById("fallbackToggle");
    const diagnosticsClose = document.getElementById("diagnosticsClose");

    if (panelToggle && !panelToggle.dataset.bound) {
        panelToggle.dataset.bound = "true";
        panelToggle.addEventListener("click", () => {
            const isOpen = panel?.classList.contains("is-open");
            setPanelOpen(panel, panelToggle, !isOpen);
        });
    }

    if (panelClose && !panelClose.dataset.bound) {
        panelClose.dataset.bound = "true";
        panelClose.addEventListener("click", () => {
            setPanelOpen(panel, panelToggle, false);
        });
    }

    bindEarthButton("earthActionExplore", openEarthSearchPanel);
    bindEarthButton("earthActionSearch", openEarthSearchPanel);
    bindEarthButton("earthActionLatest", focusLatestHotspotEarth);
    bindEarthButton("earthActionReset", resetEarthView);
    bindEarthButton("earthTabFeatured", openEarthSearchPanel);
    bindEarthButton("earthModeFeatured", openEarthSearchPanel);
    bindEarthButton("earthTabTrending", () => {
        focusLatestHotspotEarth();
        setEarthModeActive("trending");
    });
    bindEarthButton("earthModeTrending", () => {
        focusLatestHotspotEarth();
        setEarthModeActive("trending");
    });
    bindEarthButton("earthTabLatest", () => {
        focusLatestHotspotEarth();
        setEarthModeActive("latest");
    });
    bindEarthButton("earthModeLatest", () => {
        focusLatestHotspotEarth();
        setEarthModeActive("latest");
    });

    if (fallbackToggle && !fallbackToggle.dataset.bound) {
        fallbackToggle.dataset.bound = "true";
        fallbackToggle.addEventListener("click", () => {
            const isVisible = diagnostics?.style.display === "block";
            if (diagnostics) diagnostics.style.display = isVisible ? "none" : "block";
            fallbackToggle.textContent = isVisible ? "Show Hotspot List" : "Hide Hotspot List";
        });
    }

    if (diagnosticsClose && !diagnosticsClose.dataset.bound) {
        diagnosticsClose.dataset.bound = "true";
        diagnosticsClose.addEventListener("click", () => {
            if (diagnostics) diagnostics.style.display = "none";
            if (fallbackToggle) fallbackToggle.textContent = "Show Hotspot List";
        });
    }

    setEarthModeActive("featured");
}

// Resume audio context on user interaction
document.addEventListener('click', () => {
    if (audioContextEarth && audioContextEarth.state === 'suspended') {
        audioContextEarth.resume().then(() => {
            audioContextEarthResumed = true;
            console.log("✅ Audio context resumed (earth)");
        });
    }
});

document.addEventListener('touchstart', () => {
    if (audioContextEarth && audioContextEarth.state === 'suspended') {
        audioContextEarth.resume().then(() => {
            audioContextEarthResumed = true;
            console.log("✅ Audio context resumed (earth)");
        });
    }
});

// ============================================================
// ALARM FUNCTIONS
// ============================================================

/**
 * Initialize Web Audio API context for alarm sound
 */
function initializeAudioContextEarth() {
    try {
        if (!audioContextEarth) {
            audioContextEarth = new (window.AudioContext || window.webkitAudioContext)();
            console.log("✅ Audio context initialized (earth)");
        }
    } catch (err) {
        console.warn("Audio context unavailable (earth):", err);
    }
}

/**
 * Play alarm sound using Web Audio API
 */
function playAlarmSoundEarth() {
    if (!audioContextEarth) {
        console.warn("Audio context not available (earth)");
        return;
    }
    
    try {
        if (audioContextEarth.state === 'suspended') {
            audioContextEarth.resume().then(() => {
                console.log("Audio context resumed, playing sound (earth)");
                playAlarmToneEarth();
            });
        } else {
            playAlarmToneEarth();
        }
    } catch (err) {
        console.error("Error playing alarm sound (earth):", err);
    }
}

/**
 * Play the actual alarm tone for earth
 */
function playAlarmToneEarth() {
    if (!audioContextEarth) return;
    
    try {
        const now = audioContextEarth.currentTime;
        const duration = 0.3;
        
        const osc1 = audioContextEarth.createOscillator();
        const osc2 = audioContextEarth.createOscillator();
        const gain = audioContextEarth.createGain();
        
        osc1.frequency.value = 1000;
        osc2.frequency.value = 1200;
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioContextEarth.destination);
        
        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + duration);
        osc2.stop(now + duration);
        
        console.log("🔊 Alarm sound played (earth)");
    } catch (err) {
        console.error("Error in playAlarmToneEarth:", err);
    }
}

/**
 * Trigger alarm for theft detection
 */
function triggerAlarmEarth(city) {
    const alarmPanel = document.getElementById('alarmPanel');
    const alarmMessage = document.getElementById('alarmMessage');
    
    if (alarmPanel && alarmMessage) {
        alarmMessage.textContent = `🚨 Theft detected in ${city}! Power consumption exceeded threshold.`;
        alarmPanel.classList.remove('hidden');
        
        playAlarmSoundEarth();
        
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

// Initialize the Cesium Viewer
async function initViewer() {
    let cesiumToken = '';
    try {
        console.log("Creating Cesium.Viewer...");

        cesiumToken = await fetchCesiumToken();
        const viewerOptions = {
            animation: false,
            baseLayerPicker: false,
            fullscreenButton: true,
            geocoder: false,
            homeButton: true,
            infoBox: false,
            sceneModePicker: true,
            timeline: false
        };

        const canUsePhotorealisticTiles = Boolean(
            cesiumToken && typeof Cesium.createGooglePhotorealistic3DTileset === "function"
        );

        if (canUsePhotorealisticTiles) {
            Cesium.Ion.defaultAccessToken = cesiumToken;
            viewer = new Cesium.Viewer('earth', viewerOptions);

            try {
                const tileset = await Cesium.createGooglePhotorealistic3DTileset({
                    onlyUsingWithGoogleGeocoder: false
                });
                viewer.scene.primitives.add(tileset);
                viewer.scene.skyAtmosphere.show = false;
                viewer.scene.backgroundColor = Cesium.Color.BLACK;
                viewer.scene.postProcessStages.fxaa.enabled = true;
                viewer.scene.globe.show = false;
                viewer.scene.globe.baseColor = Cesium.Color.BLACK;
                viewer.scene.globe.enableLighting = false;
                setImageryStatus("Google photorealistic 3D active.", true);
            } catch (tilesetError) {
                console.warn("Google photorealistic 3D tiles failed, falling back to Cesium World Imagery:", tilesetError);
                if (viewer && !viewer.isDestroyed()) {
                    viewer.destroy();
                }
                viewer = null;
            }
        }

        if (!viewer) {
            const fallbackViewerOptions = {
                ...viewerOptions,
                scene3DOnly: false
            };

            if (cesiumToken) {
                Cesium.Ion.defaultAccessToken = cesiumToken;
                try {
                    fallbackViewerOptions.imageryProvider = Cesium.createWorldImagery({
                        style: Cesium.IonWorldImageryStyle.AERIAL_WITH_LABELS
                    });
                    fallbackViewerOptions.terrainProvider = await Cesium.createWorldTerrainAsync();
                } catch (terrainError) {
                    console.warn("Cesium world terrain failed, using ellipsoid terrain instead:", terrainError);
                    fallbackViewerOptions.terrainProvider = new Cesium.EllipsoidTerrainProvider();
                }
            } else {
                fallbackImageryProviderEarth = new Cesium.OpenStreetMapImageryProvider({
                    url: 'https://tile.openstreetmap.org/'
                });
                fallbackViewerOptions.imageryProvider = fallbackImageryProviderEarth;
                fallbackViewerOptions.terrainProvider = new Cesium.EllipsoidTerrainProvider();
            }

            viewer = new Cesium.Viewer('earth', fallbackViewerOptions);
            setImageryStatus(
                cesiumToken ? "Cesium World Imagery active." : "Cesium token missing. Using fallback imagery.",
                Boolean(cesiumToken)
            );
        }

        console.log("Viewer created successfully.");
        completeEarthViewerSetup();
    } catch (err) {
        console.error("Viewer error:", err);
        if (!viewer) {
            try {
                const safeViewerOptions = {
                    animation: false,
                    baseLayerPicker: false,
                    fullscreenButton: true,
                    geocoder: false,
                    homeButton: true,
                    infoBox: false,
                    sceneModePicker: true,
                    timeline: false
                };

                if (cesiumToken) {
                    Cesium.Ion.defaultAccessToken = cesiumToken;
                    try {
                        safeViewerOptions.imageryProvider = Cesium.createWorldImagery({
                            style: Cesium.IonWorldImageryStyle.AERIAL_WITH_LABELS
                        });
                        safeViewerOptions.terrainProvider = await Cesium.createWorldTerrainAsync();
                    } catch (terrainError) {
                        console.warn("Cesium world terrain failed in safety fallback, using ellipsoid terrain instead:", terrainError);
                        safeViewerOptions.terrainProvider = new Cesium.EllipsoidTerrainProvider();
                    }
                } else {
                    fallbackImageryProviderEarth = new Cesium.OpenStreetMapImageryProvider({
                        url: 'https://tile.openstreetmap.org/'
                    });
                    safeViewerOptions.imageryProvider = fallbackImageryProviderEarth;
                    safeViewerOptions.terrainProvider = new Cesium.EllipsoidTerrainProvider();
                }

                viewer = new Cesium.Viewer('earth', safeViewerOptions);
                setImageryStatus(
                    cesiumToken ? "Cesium World Imagery active." : "Cesium token missing. Using fallback imagery.",
                    Boolean(cesiumToken)
                );
                completeEarthViewerSetup();
                return;
            } catch (safeError) {
                console.error("Safe viewer fallback failed:", safeError);
            }
        }
        showFallback();
    }
}

function completeEarthViewerSetup() {
    if (!viewer) return;
    bindEarthChromeControls();

    // Set view
    smoothFlyToEarth(20.5, 78.9, 2000000, 2.2);
    console.log("Earth camera positioned.");

    // Initialize audio for alarms
    initializeAudioContextEarth();

    // Setup filters
    setupFilterListenersEarth();

    // Load locations
    loadLocations();
    if (earthRefreshTimer) {
        clearInterval(earthRefreshTimer);
    }
    earthRefreshTimer = setInterval(loadLocations, 3000);

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((movement) => {
        const pickedObject = viewer.scene.pick(movement.position);
        if (Cesium.defined(pickedObject) && pickedObject.id && pickedObject.id.smartTheftData) {
            openLocationDrawerEarth(pickedObject.id.smartTheftData);
        }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

// Load theft locations on map
function loadLocations() {
    if (!viewer) return;

    fetch('/api/live').then(async (response) => {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Could not load live map data.');
        }
        return data;
    }).then(data => {
        allDataEarth = data;
        applyFiltersEarth();
    }).catch(err => console.error("Load error:", err));
}

/**
 * Apply current filter selections to Earth markers
 */
function applyFiltersEarth() {
    if (!viewer) return;
    
    const searchInput = document.getElementById('citySearchEarth');
    const statusFilter = document.getElementById('statusFilterEarth');
    
    const searchTerm = (searchInput?.value || '').toLowerCase();
    const statusValue = statusFilter?.value || '';
    
    // Check for new thefts and trigger alarms
    const currentTheftCount = allDataEarth.filter(c => c.status === "THEFT").length;
    if (currentTheftCount > lastTheftCountEarth) {
        const theftCities = allDataEarth.filter(c => c.status === "THEFT");
        if (theftCities.length > 0) {
            triggerAlarmEarth(theftCities[0].city);
        }
    }
    lastTheftCountEarth = currentTheftCount;
    
    viewer.entities.removeAll();
    
    allDataEarth.forEach(d => {
        if (!Number.isFinite(Number(d.lat)) || !Number.isFinite(Number(d.lon))) return;
        
        // Apply search filter
        if (searchTerm && !d.city.toLowerCase().includes(searchTerm)) {
            return;
        }
        
        // Apply status filter
        if (statusValue && d.status !== statusValue) {
            return;
        }
        
        const entity = viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(d.lon, d.lat),
            point: {
                pixelSize: 12,
                color: d.status === 'THEFT' ? Cesium.Color.RED : Cesium.Color.GREEN,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2
            },
            label: {
                text: d.zone_name || d.city,
                font: 'bold 12px Arial',
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 1,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -12)
            }
        });
        entity.smartTheftData = d;
    });
}

/**
 * Setup filter event listeners for Earth
 */
function setupFilterListenersEarth() {
    const searchInput = document.getElementById('citySearchEarth');
    const statusFilter = document.getElementById('statusFilterEarth');
    
    if (searchInput) {
        searchInput.addEventListener('input', applyFiltersEarth);
    }
    
    if (statusFilter) {
        statusFilter.addEventListener('change', applyFiltersEarth);
    }
}

/**
 * Reset all filters on Earth view
 */
function resetFiltersEarth() {
    const searchInput = document.getElementById('citySearchEarth');
    const statusFilter = document.getElementById('statusFilterEarth');
    
    if (searchInput) searchInput.value = '';
    if (statusFilter) statusFilter.value = '';
    
    applyFiltersEarth();
}

// Fallback for when Cesium doesn't load
function showFallback() {
    console.log("Showing fallback");
    document.getElementById('earth').style.display = 'none';
    const controlsPanel = document.getElementById('earthControlsPanel');
    const controlsToggle = document.getElementById('earthPanelToggle');
    const actionStrip = document.querySelector('.earth-showcase-strip');
    const toolbar = document.querySelector('.earth-toolbar');
    const diagnostics = document.getElementById('diagnostics');
    const fallbackToggle = document.getElementById('fallbackToggle');
    setImageryStatus("Cesium unavailable. Hotspot list active.", false);
    if (controlsPanel) {
        controlsPanel.classList.remove('is-open');
        controlsPanel.setAttribute('aria-hidden', 'true');
    }
    if (controlsToggle) controlsToggle.setAttribute('aria-expanded', 'false');
    if (actionStrip) actionStrip.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';
    if (diagnostics) diagnostics.style.display = 'none';
    if (fallbackToggle) {
        fallbackToggle.style.display = 'inline-flex';
        fallbackToggle.textContent = 'Show Hotspot List';
    }
    bindEarthChromeControls();

    const list = document.getElementById('fallback-list');
    function update() {
        fetch('/api/live').then(async (response) => {
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Could not load fallback map data.');
            }
            return data;
        }).then(data => {
            list.innerHTML = '';
            data.forEach(d => {
                const card = document.createElement('div');
                card.className = `location-card ${d.status === 'THEFT' ? 'theft' : 'normal'}`;
                card.innerHTML = `<strong>${d.location_label || d.city}</strong><small>Status: ${d.status}</small><small>Lat: ${Number(d.lat).toFixed(4)} deg</small><small>Lon: ${Number(d.lon).toFixed(4)} deg</small><small>Power: ${Number(d.power).toFixed(0)}W</small>`;
                card.addEventListener('click', () => openLocationDrawerEarth(d));
                list.appendChild(card);
            });
            if (diagnostics && diagnostics.style.display === 'block') {
                const tests = document.getElementById('tests');
                if (tests && tests.children.length > 0) {
                    tests.innerHTML = `<div class="test-item"><div class="test-status pass"></div><span>Hotspot list loaded successfully.</span></div>`;
                }
            }
        }).catch((error) => {
            console.error('Fallback data load error:', error);
        });
    }
    update();
    setInterval(update, 3000);
}

// START
console.log("Initializing...");
async function start() {
    if (typeof Cesium !== 'undefined' && Cesium.Viewer) {
        console.log("Cesium ready.");
        await initViewer();
    } else {
        console.log("Waiting for Cesium...");
        setTimeout(start, 500);
    }
}
start();

/**
 * Search for a city using Nominatim and fly the Cesium camera there.
 */
async function searchCityEarth() {
    const input = document.getElementById('citySearchEarth');
    const name = input?.value.trim();
    if (!name) {
        alert('Please enter a city name.');
        return;
    }

    const liveMatch = findLiveLocationMatch(name);
    if (liveMatch && Number.isFinite(Number(liveMatch.lat)) && Number.isFinite(Number(liveMatch.lon))) {
        focusEarthLocation(
            Number(liveMatch.lat),
            Number(liveMatch.lon),
            liveMatch.location_label || liveMatch.city,
            liveMatch
        );
        return;
    }

    // Try local dataset first
    try {
        const res = await fetch('/assets/data/india_cities.json');
        const local = await res.json();
        const query = name.toLowerCase();
        const found = local.find(c => c.city.toLowerCase() === query)
            || local.find(c => c.city.toLowerCase().startsWith(query))
            || local.find(c => c.city.toLowerCase().includes(query));
        if (found) {
            const latNum = parseFloat(found.lat);
            const lonNum = parseFloat(found.lon);
            focusEarthLocation(latNum, lonNum, found.city);
            return;
        }
    } catch (err) {
        console.warn('Local city lookup failed (earth), falling back to Nominatim', err);
    }

    // Fallback to Nominatim
    try {
        const resp = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(name + ', India')}&format=jsonv2&limit=1`);
        const results = await resp.json();
        if (!results || results.length === 0) { alert('City not found. Try a different name.'); return; }
        const { lat, lon, display_name } = results[0];
        const latNum = parseFloat(lat);
        const lonNum = parseFloat(lon);
        focusEarthLocation(latNum, lonNum, display_name.split(',')[0]);
    } catch (err) {
        console.error('Error searching city (earth):', err);
        alert('Search failed. Check console for details.');
    }
}

// Hook up search button when DOM available
const searchBtnEarth = document.getElementById('searchButtonEarth');
if (searchBtnEarth) searchBtnEarth.addEventListener('click', searchCityEarth);
const searchInputEarth = document.getElementById('citySearchEarth');
if (searchInputEarth) {
    searchInputEarth.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            searchCityEarth();
        }
    });
}


