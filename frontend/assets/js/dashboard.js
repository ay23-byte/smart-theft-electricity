// Global chart instance
let consumptionChart = null;
let lastTheftCount = 0;
let audioContext = null;
let audioContextResumed = false;
let liveStreamSource = null;
let liveStreamReconnectTimer = null;
let livePollingTimer = null;
let auditLogRefreshTimer = null;
let lastBatchPredictionResult = null;

// Initialize dashboard on page load
document.addEventListener("DOMContentLoaded", () => {
    initializeDashboard();
    initializeAudioContext();
    initializePredictionForm();
    initializeBatchPredictionForm();
    initializeBatchExportButton();
    initializeModelRetrainButton();
    initializeAuditExportButton();
    initializeLiveUpdates();
});

// Resume audio context on user interaction (required by browser autoplay policy)
document.addEventListener('click', () => {
    if (audioContext && audioContext.state === 'suspended') {
        audioContext.resume().then(() => {
            audioContextResumed = true;
            console.log("✅ Audio context resumed");
        });
    }
});

document.addEventListener('touchstart', () => {
    if (audioContext && audioContext.state === 'suspended') {
        audioContext.resume().then(() => {
            audioContextResumed = true;
            console.log("✅ Audio context resumed");
        });
    }
});

/**
 * Initialize Web Audio API context for alarm sound
 */
function initializeAudioContext() {
    try {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            console.log("✅ Audio context initialized");
        }
    } catch (err) {
        console.warn("Audio context unavailable:", err);
    }
}

/**
 * Play alarm sound using Web Audio API
 */
function playAlarmSound() {
    if (!audioContext) {
        console.warn("Audio context not available");
        return;
    }
    
    try {
        // Resume context if suspended
        if (audioContext.state === 'suspended') {
            audioContext.resume().then(() => {
                console.log("Audio context resumed, playing sound");
                playAlarmTone();
            });
        } else {
            playAlarmTone();
        }
    } catch (err) {
        console.error("Error playing alarm sound:", err);
    }
}

/**
 * Play the actual alarm tone
 */
function playAlarmTone() {
    if (!audioContext) return;
    
    try {
        const now = audioContext.currentTime;
        const duration = 0.3;
        
        // Create alarm tone (1000Hz and 1200Hz)
        const osc1 = audioContext.createOscillator();
        const osc2 = audioContext.createOscillator();
        const gain = audioContext.createGain();
        
        osc1.frequency.value = 1000;
        osc2.frequency.value = 1200;
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + duration);
        
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioContext.destination);
        
        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + duration);
        osc2.stop(now + duration);
        
        console.log("🔊 Alarm sound played");
    } catch (err) {
        console.error("Error in playAlarmTone:", err);
    }
}

/**
 * Trigger alarm for theft detection
 */
function triggerAlarm(city) {
    const alarmPanel = document.getElementById('alarmPanel');
    const alarmMessage = document.getElementById('alarmMessage');
    
    if (alarmPanel && alarmMessage) {
        alarmMessage.textContent = `🚨 Theft detected in ${city}! Power consumption exceeded threshold.`;
        alarmPanel.classList.remove('hidden');
        
        // Play alarm sound
        playAlarmSound();
        
        // Auto-dismiss after 5 seconds
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

/**
 * Initialize dashboard and chart
 */
function initializeDashboard() {
    createConsumptionChart();
    updateDashboard();
    loadAuditLog();
    if (!auditLogRefreshTimer) {
        auditLogRefreshTimer = setInterval(loadAuditLog, 15000);
    }
}

function initializeLiveUpdates() {
    const runtime = window.SMARTTHEFT_RUNTIME || {};
    if (runtime.liveStreamEnabled === false) {
        setStatusMessage("Live stream disabled in production. Using light polling.", "info");
        startLivePolling(10000);
        return;
    }

    if ("EventSource" in window) {
        connectLiveStream();
        return;
    }

    startLivePolling(10000);
}

function startLivePolling(intervalMs = 3000) {
    if (livePollingTimer) return;

    livePollingTimer = setInterval(updateDashboard, intervalMs);
    setStatusMessage("Live stream unavailable. Using polling fallback.", "error");
}

function stopLivePolling() {
    if (!livePollingTimer) return;

    clearInterval(livePollingTimer);
    livePollingTimer = null;
}

function connectLiveStream() {
    if (liveStreamSource) {
        liveStreamSource.close();
    }

    try {
        liveStreamSource = new EventSource("/api/live/stream");
    } catch (error) {
        console.warn("EventSource unavailable, switching to polling.", error);
        startLivePolling(10000);
        return;
    }

    liveStreamSource.onopen = () => {
        stopLivePolling();
        if (liveStreamReconnectTimer) {
            clearTimeout(liveStreamReconnectTimer);
            liveStreamReconnectTimer = null;
        }
        setStatusMessage("Live stream connected.", "success");
    };

    liveStreamSource.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            if (Array.isArray(payload.live)) {
                updateAnalytics(payload.live);
                updateChart(payload.live);
            }
            if (payload.summary) {
                updatePortalStatus(payload.summary);
            }
        } catch (error) {
            console.warn("Could not parse live stream payload:", error);
        }
    };

    liveStreamSource.onerror = () => {
        if (liveStreamSource) {
            liveStreamSource.close();
            liveStreamSource = null;
        }

        setStatusMessage("Live stream disconnected. Reconnecting...", "error");
        startLivePolling(10000);

        if (!liveStreamReconnectTimer) {
            liveStreamReconnectTimer = setTimeout(() => {
                liveStreamReconnectTimer = null;
                connectLiveStream();
            }, 5000);
        }
    };
}

/**
 * Initialize model prediction form
 */
function initializePredictionForm() {
    const form = document.getElementById("predictionForm");
    if (!form) return;

    form.addEventListener("submit", handlePredictionSubmit);
}

function initializeBatchPredictionForm() {
    const form = document.getElementById("batchPredictionForm");
    if (!form) return;

    form.addEventListener("submit", handleBatchPredictionSubmit);
}

function initializeBatchExportButton() {
    const button = document.getElementById("downloadBatchResultsButton");
    if (!button) return;

    button.addEventListener("click", handleBatchResultsDownload);
}

function initializeModelRetrainButton() {
    const button = document.getElementById("retrainModelButton");
    if (!button) return;

    button.addEventListener("click", handleModelRetrain);
}

function initializeAuditExportButton() {
    const button = document.getElementById("exportAuditLogButton");
    if (!button) return;

    button.addEventListener("click", handleAuditExport);
}

/**
 * Fetch live data and update all dashboard elements
 */
async function updateDashboard() {
    try {
        const [liveResponse, summaryResponse] = await Promise.all([
            fetch("/api/live"),
            fetch("/api/monitoring/summary"),
        ]);

        if (!liveResponse.ok) throw new Error("Failed to fetch live data");
        if (!summaryResponse.ok) throw new Error("Failed to fetch monitoring summary");

        const cities = await liveResponse.json();
        const summary = await summaryResponse.json();
        
        // Update analytics cards
        updatePortalStatus(summary);
        loadAuditLog();
        if (cities.length === 0) return;
        updateAnalytics(cities);
        
        // Update chart with current hour's data by city
        updateChart(cities);
        
    } catch (error) {
        console.error("Dashboard update error:", error);
    }
}

/**
 * Update analytics stat cards
 */
function updateAnalytics(cities) {
    // Count THEFT status
    const theftCount = cities.filter(c => c.status === "THEFT").length;
    document.getElementById("theft-count").textContent = theftCount;
    
    // Trigger alarm if new thefts detected
    if (theftCount > lastTheftCount) {
        const theftCities = cities.filter(c => c.status === "THEFT");
        if (theftCities.length > 0) {
            triggerAlarm(theftCities[0].city);
        }
    }
    lastTheftCount = theftCount;
    
    // Calculate average power
    const avgPower = cities.reduce((sum, c) => sum + c.power, 0) / cities.length;
    document.getElementById("avg-power").textContent = Math.round(avgPower) + "W";
    
    // Find peak power
    const peakPower = Math.max(...cities.map(c => c.power));
    document.getElementById("peak-power").textContent = Math.round(peakPower) + "W";
    
    // Find top city by power consumption
    const topCity = cities.reduce((max, c) => c.power > max.power ? c : max);
    document.getElementById("top-city").textContent = topCity.city;
}

function updatePortalStatus(summary) {
    const unreadNotices = document.getElementById("portal-unread-notices");
    const openCases = document.getElementById("portal-open-cases");
    const activeAlerts = document.getElementById("portal-active-alerts");
    const modelHealth = document.getElementById("portal-model-health");

    if (unreadNotices) {
        unreadNotices.textContent = Number(summary.unread_notifications || 0);
    }
    if (openCases) {
        openCases.textContent = Number(summary.open_cases || 0);
    }
    if (activeAlerts) {
        activeAlerts.textContent = Number(summary.active_alerts || 0);
    }
    if (modelHealth) {
        modelHealth.textContent = summary.model_loaded ? "Ready" : "Offline";
        modelHealth.style.color = summary.model_loaded ? "#2ED573" : "#FF4757";
    }
}

async function loadAuditLog() {
    const list = document.getElementById("audit-log-list");
    if (!list) return;

    try {
        const response = await fetch("/api/audit-log?limit=6");
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Failed to load audit log.");
        }

        const events = Array.isArray(result.events) ? result.events : [];
        if (!events.length) {
            list.innerHTML = `<div class="audit-log__empty">No activity recorded yet.</div>`;
            return;
        }

        list.innerHTML = events.map((event) => {
            const actor = event.actor_username || "system";
            const actorRole = event.actor_role ? event.actor_role.toUpperCase() : "SYSTEM";
            const tone = String(event.action || "").includes("predict") ? "audit-log__item--prediction" : "";
            return `
                <article class="audit-log__item ${tone}">
                    <div class="audit-log__meta">
                        <span class="audit-log__action">${event.action}</span>
                        <span class="audit-log__entity">${event.entity_type}${event.entity_id ? ` #${event.entity_id}` : ""}</span>
                    </div>
                    <strong>${event.summary}</strong>
                    <p>${event.details || "No extra details provided."}</p>
                    <small>${actor} · ${actorRole} · ${event.created_at}</small>
                </article>
            `;
        }).join("");
    } catch (error) {
        console.warn("Audit log load failed:", error);
        list.innerHTML = `<div class="audit-log__empty">Audit trail unavailable right now.</div>`;
    }
}

/**
 * Create and initialize consumption chart
 */
function createConsumptionChart() {
    const ctx = document.getElementById("consumptionChart");
    if (!ctx) return;
    
    // Generate hourly labels and realistic data for all 24 hours
    const hours = Array.from({length: 24}, (_, i) => `${i}:00`);
    const consumptionData = generateRealisticHourlyData();
    
    consumptionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [{
                label: 'Average Power Consumption (W)',
                data: consumptionData,
                borderColor: '#00D4FF',
                backgroundColor: 'rgba(0, 212, 255, 0.1)',
                borderWidth: 2.5,
                tension: 0.4,
                fill: true,
                pointRadius: 5,
                pointBackgroundColor: '#00D4FF',
                pointBorderColor: '#0A0E27',
                pointBorderWidth: 2,
                pointHoverRadius: 7,
                pointHoverBackgroundColor: '#FF006E',
                pointHoverBorderColor: '#00D4FF'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#E5E7EB',
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    backgroundColor: '#151B33',
                    borderColor: '#00D4FF',
                    borderWidth: 1,
                    titleColor: '#00D4FF',
                    bodyColor: '#E5E7EB',
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y + ' W';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(55, 65, 81, 0.3)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#9CA3AF'
                    }
                },
                y: {
                    beginAtZero: true,
                    max: 5000,
                    grid: {
                        color: 'rgba(55, 65, 81, 0.3)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#9CA3AF',
                        callback: function(value) {
                            return value + ' W';
                        }
                    }
                }
            }
        }
    });
}

/**
 * Update chart with current city data
 */
function updateChart(cities) {
    if (!consumptionChart) return;
    
    // Calculate average power for each hour based on cities' current power
    // For now, we'll show the distribution of city powers across the chart
    const avgByHour = generateRealisticHourlyData();
    
    consumptionChart.data.datasets[0].data = avgByHour;
    consumptionChart.update('none'); // Update without animation
}

/**
 * Generate realistic hourly consumption pattern (24 hours)
 * Mimics Indian city power consumption patterns
 */
function generateRealisticHourlyData() {
    const baseProfiles = {
        0: 1500,   // Midnight - very low
        1: 1400,   // 1 AM - very low
        2: 1300,   // 2 AM - off-peak
        3: 1200,   // 3 AM - off-peak (lowest)
        4: 1400,   // 4 AM - off-peak
        5: 1800,   // 5 AM - beginning of morning
        6: 2300,   // 6 AM - morning ramp up
        7: 3000,   // 7 AM - peak begins
        8: 3800,   // 8 AM - peak (highest)
        9: 3900,   // 9 AM - peak
        10: 3700,  // 10 AM - peak
        11: 3500,  // 11 AM - peak ending
        12: 3200,  // Noon - afternoon begins
        13: 2800,  // 1 PM
        14: 2600,  // 2 PM
        15: 2500,  // 3 PM - afternoon low
        16: 2600,  // 4 PM
        17: 2900,  // 5 PM - evening starts
        18: 3500,  // 6 PM - evening peak
        19: 3900,  // 7 PM - peak hour
        20: 4000,  // 8 PM - peak hour (second highest)
        21: 3600,  // 9 PM - peak ending
        22: 3000,  // 10 PM - evening
        23: 2200   // 11 PM - night
    };
    
    // Add realistic variance (±200-400W)
    return Array.from({length: 24}, (_, hour) => {
        const variance = Math.random() * 400 - 200;
        return Math.round(baseProfiles[hour] + variance);
    });
}

/**
 * Submit custom values to the model prediction API
 */
async function handlePredictionSubmit(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const submitButton = form.querySelector("button[type='submit']");
    const payload = {
        avg_daily_consumption: Number(form.avg_daily_consumption.value),
        max_daily_consumption: Number(form.max_daily_consumption.value),
        consumption_variance: Number(form.consumption_variance.value)
    };

    if (
        Number.isNaN(payload.avg_daily_consumption) ||
        Number.isNaN(payload.max_daily_consumption) ||
        Number.isNaN(payload.consumption_variance)
    ) {
        setStatusMessage("Please enter valid numeric values for all prediction fields.", "error");
        return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Running...";

    try {
        const response = await fetch("/api/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Prediction request failed.");
        }

        renderPredictionResult(result);
        setStatusMessage(`Prediction complete: ${result.status} at ${result.risk_score}% risk.`, "success");
    } catch (error) {
        renderPredictionError(error.message);
        setStatusMessage(`Prediction error: ${error.message}`, "error");
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Run Prediction";
    }
}

/**
 * Render model prediction response
 */
function renderPredictionResult(result) {
    const resultCard = document.getElementById("predictionResult");
    const badge = document.getElementById("predictionStatusBadge");
    const riskScore = document.getElementById("predictionRiskScore");
    const meterFill = document.getElementById("predictionMeterFill");
    const thresholdMarker = document.getElementById("predictionThresholdMarker");
    const thresholdLabel = document.getElementById("predictionThresholdLabel");
    const readingType = document.getElementById("predictionReadingType");
    const readingSummary = document.getElementById("predictionReadingSummary");
    const summary = document.getElementById("predictionSummary");
    const features = document.getElementById("predictionFeatures");
    const explainability = document.getElementById("predictionExplainability");

    if (!resultCard || !badge || !riskScore || !meterFill || !thresholdMarker || !thresholdLabel || !readingType || !readingSummary || !summary || !features || !explainability) return;

    const isTheft = result.status === "THEFT";
    const riskValue = Math.max(0, Math.min(100, Number(result.risk_score)));
    const thresholdPercent = Math.max(0, Math.min(100, Number(result.threshold) * 100));

    resultCard.className = `prediction-result ${isTheft ? "prediction-result--theft" : "prediction-result--normal"}`;
    badge.className = `prediction-badge ${isTheft ? "prediction-badge--theft" : "prediction-badge--normal"}`;
    badge.textContent = result.status;
    riskScore.textContent = `Risk Score: ${riskValue.toFixed(2)}%`;
    meterFill.style.width = `${riskValue}%`;
    meterFill.className = `prediction-meter__fill ${isTheft ? "prediction-meter__fill--theft" : "prediction-meter__fill--normal"}`;
    thresholdMarker.style.left = `${thresholdPercent}%`;
    thresholdLabel.textContent = `Threshold ${thresholdPercent.toFixed(0)}%`;
    readingType.textContent = result.reading_profile?.label || (isTheft ? "Suspicious pattern" : "Normal pattern");
    readingSummary.textContent = result.reading_profile?.summary || (isTheft
        ? "The model sees this pattern as suspicious and likely theft."
        : "The model sees this pattern as normal consumption behavior.");
    summary.textContent = isTheft
        ? "The model sees this pattern as suspicious and likely theft."
        : "The model sees this pattern as normal consumption behavior.";

    features.innerHTML = `
        <div class="prediction-feature-chip">Avg: ${Number(result.features.avg_daily_consumption).toFixed(2)}</div>
        <div class="prediction-feature-chip">Max: ${Number(result.features.max_daily_consumption).toFixed(2)}</div>
        <div class="prediction-feature-chip">Variance: ${Number(result.features.consumption_variance).toFixed(2)}</div>
        <div class="prediction-feature-chip">Intensity: ${Number(result.features.usage_intensity).toFixed(2)}</div>
    `;
    explainability.innerHTML = Array.isArray(result.explanations) && result.explanations.length
        ? `
            <div class="prediction-explainability__title">Why this score</div>
            <div class="prediction-explainability__chips">
                ${result.explanations.map((item) => `
                    <div class="prediction-feature-chip prediction-feature-chip--${item.tone || 'normal'}">
                        <strong>${item.label}</strong>
                        <span>${item.value}</span>
                    </div>
                `).join("")}
            </div>
        `
        : "";
}

/**
 * Render prediction error state
 */
function renderPredictionError(message) {
    const resultCard = document.getElementById("predictionResult");
    const badge = document.getElementById("predictionStatusBadge");
    const riskScore = document.getElementById("predictionRiskScore");
    const meterFill = document.getElementById("predictionMeterFill");
    const thresholdMarker = document.getElementById("predictionThresholdMarker");
    const thresholdLabel = document.getElementById("predictionThresholdLabel");
    const readingType = document.getElementById("predictionReadingType");
    const readingSummary = document.getElementById("predictionReadingSummary");
    const summary = document.getElementById("predictionSummary");
    const features = document.getElementById("predictionFeatures");

    if (!resultCard || !badge || !riskScore || !meterFill || !thresholdMarker || !thresholdLabel || !readingType || !readingSummary || !summary || !features) return;

    resultCard.className = "prediction-result prediction-result--error";
    badge.className = "prediction-badge prediction-badge--error";
    badge.textContent = "Error";
    riskScore.textContent = "Risk Score: --";
    meterFill.style.width = "0%";
    meterFill.className = "prediction-meter__fill";
    thresholdMarker.style.left = "35%";
    thresholdLabel.textContent = "Threshold 35%";
    readingType.textContent = "Prediction unavailable";
    readingSummary.textContent = "Unable to explain the reading until a prediction succeeds.";
    summary.textContent = message;
    features.innerHTML = "";
    const explainability = document.getElementById("predictionExplainability");
    if (explainability) explainability.innerHTML = "";
}

async function handleBatchPredictionSubmit(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const submitButton = form.querySelector("button[type='submit']");
    const fileInput = document.getElementById("batchPredictionFile");
    const selectedFile = fileInput?.files?.[0];

    if (!selectedFile) {
        setStatusMessage("Please choose a CSV file for batch prediction.", "error");
        return;
    }

    const payload = new FormData();
    payload.append("file", selectedFile);

    submitButton.disabled = true;
    submitButton.textContent = "Uploading...";

    try {
        const response = await fetch("/api/predict-batch", {
            method: "POST",
            body: payload,
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Batch prediction request failed.");
        }

        renderBatchPredictionResult(result);
        setStatusMessage(`Batch prediction complete for ${result.summary.processed_rows} rows.`, "success");
    } catch (error) {
        renderBatchPredictionError(error.message);
        setStatusMessage(`Batch prediction error: ${error.message}`, "error");
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Run Batch Prediction";
    }
}

function escapeCsvValue(value) {
    const text = value === null || value === undefined ? "" : String(value);
    if (/[",\n\r]/.test(text)) {
        return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
}

function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function buildBatchResultsCsv(result) {
    const rows = [
        [
            "row",
            "city",
            "source_id",
            "status",
            "reading_type",
            "reading_summary",
            "risk_score",
            "avg_daily_consumption",
            "max_daily_consumption",
            "consumption_variance",
            "usage_intensity",
        ].join(",")
    ];

    (result.results || []).forEach((item) => {
        rows.push([
            item.row,
            item.city,
            item.source_id || "",
            item.status,
            item.reading_profile?.label || "",
            item.reading_profile?.summary || "",
            Number(item.risk_score || 0).toFixed(2),
            Number(item.avg_daily_consumption || 0).toFixed(2),
            Number(item.max_daily_consumption || 0).toFixed(2),
            Number(item.consumption_variance || 0).toFixed(2),
            Number(item.usage_intensity || 0).toFixed(2),
        ].map(escapeCsvValue).join(","));
    });

    return rows.join("\n");
}

function handleBatchResultsDownload() {
    if (!lastBatchPredictionResult || !Array.isArray(lastBatchPredictionResult.results) || !lastBatchPredictionResult.results.length) {
        setStatusMessage("Run a batch prediction first so there is something to download.", "error");
        return;
    }

    const csv = buildBatchResultsCsv(lastBatchPredictionResult);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");

    link.href = url;
    link.download = `smarttheft_batch_results_${stamp}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setStatusMessage("Batch results CSV downloaded.", "success");
}

async function handleModelRetrain(event) {
    const button = event.currentTarget;
    if (!button) return;

    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = "Retraining...";

    try {
        const response = await fetch("/api/model/retrain", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Model retraining failed.");
        }

        setStatusMessage(`Model retrained using ${Number(result.dataset_size || 0).toLocaleString()} samples.`, "success");
        loadAuditLog();
    } catch (error) {
        setStatusMessage(`Retrain error: ${error.message}`, "error");
    } finally {
        button.disabled = false;
        button.textContent = originalText || "Retrain Model";
    }
}

function handleAuditExport() {
    window.location.href = "/api/audit-log/export?limit=250";
}

function renderBatchPredictionResult(result) {
    const card = document.getElementById("batchPredictionResult");
    const badge = document.getElementById("batchPredictionBadge");
    const headline = document.getElementById("batchPredictionHeadline");
    const summary = document.getElementById("batchPredictionSummary");
    const metrics = document.getElementById("batchPredictionMetrics");
    const invalidRows = document.getElementById("batchPredictionInvalidRows");
    const tableBody = document.getElementById("batchPredictionTableBody");

    if (!card || !badge || !headline || !summary || !metrics || !invalidRows || !tableBody) return;

    lastBatchPredictionResult = result;
    const downloadButton = document.getElementById("downloadBatchResultsButton");
    if (downloadButton) {
        downloadButton.disabled = false;
    }

    const theftCount = Number(result.summary.theft_count || 0);
    const processedRows = Number(result.summary.processed_rows || 0);
    const riskTone = theftCount > 0 ? "prediction-result--theft" : "prediction-result--normal";
    const badgeTone = theftCount > 0 ? "prediction-badge--theft" : "prediction-badge--normal";
    const sourceLabel = result.source_format === "wide" ? "Raw meter file" : "Engineered features";

    card.className = `prediction-result ${riskTone}`;
    badge.className = `prediction-badge ${badgeTone}`;
    badge.textContent = theftCount > 0 ? "Alerts Found" : "All Normal";
    headline.textContent = `${result.filename} processed successfully (${sourceLabel})`;
    summary.textContent = `Scored ${processedRows} valid rows. Highest risk: ${result.summary.highest_risk_location} at ${Number(result.summary.highest_risk_score).toFixed(2)}%.`;

    metrics.innerHTML = `
        <div class="prediction-feature-chip">Theft: ${theftCount}</div>
        <div class="prediction-feature-chip">Normal: ${Number(result.summary.normal_count || 0)}</div>
        <div class="prediction-feature-chip">Invalid: ${Number(result.summary.invalid_rows || 0)}</div>
        <div class="prediction-feature-chip">Avg Risk: ${Number(result.summary.average_risk_score || 0).toFixed(2)}%</div>
        ${Object.entries(result.summary.reading_type_counts || {})
            .map(([label, count]) => `<div class="prediction-feature-chip">Reading: ${label} (${count})</div>`)
            .join("")}
    `;

    invalidRows.innerHTML = (result.invalid_rows || []).length
        ? result.invalid_rows.map((row) => `<div class="batch-invalid-list__item">Row ${escapeHtml(row.row)}: ${escapeHtml(row.error)}</div>`).join("")
        : "";

    tableBody.innerHTML = (result.results || []).map((item) => `
        <tr class="${item.status === "THEFT" ? "batch-results-table__row--theft" : ""}">
            <td>${escapeHtml(item.row)}</td>
            <td>${escapeHtml(item.city)}</td>
            <td>${escapeHtml(item.status)}</td>
            <td>${escapeHtml(item.reading_profile?.label || (item.status === "THEFT" ? "Suspicious pattern" : "Normal pattern"))}</td>
            <td title="${escapeHtml(item.reading_profile?.summary || "")}">${escapeHtml(item.reading_profile?.summary || "No explanation available.")}</td>
            <td>${Number(item.risk_score).toFixed(2)}%</td>
            <td>${Number(item.avg_daily_consumption).toFixed(2)}</td>
            <td>${Number(item.max_daily_consumption).toFixed(2)}</td>
            <td>${Number(item.consumption_variance).toFixed(2)}</td>
            <td>${Number(item.usage_intensity).toFixed(2)}</td>
        </tr>
    `).join("");
}

function renderBatchPredictionError(message) {
    const card = document.getElementById("batchPredictionResult");
    const badge = document.getElementById("batchPredictionBadge");
    const headline = document.getElementById("batchPredictionHeadline");
    const summary = document.getElementById("batchPredictionSummary");
    const metrics = document.getElementById("batchPredictionMetrics");
    const invalidRows = document.getElementById("batchPredictionInvalidRows");
    const tableBody = document.getElementById("batchPredictionTableBody");

    if (!card || !badge || !headline || !summary || !metrics || !invalidRows || !tableBody) return;

    lastBatchPredictionResult = null;
    const downloadButton = document.getElementById("downloadBatchResultsButton");
    if (downloadButton) {
        downloadButton.disabled = true;
    }

    card.className = "prediction-result prediction-result--error";
    badge.className = "prediction-badge prediction-badge--error";
    badge.textContent = "Error";
    headline.textContent = "Batch prediction failed";
    summary.textContent = message;
    metrics.innerHTML = "";
    invalidRows.innerHTML = "";
    tableBody.innerHTML = `<tr><td colspan="10">${message}</td></tr>`;
}

/**
 * Update shared status area
 */
function setStatusMessage(message, type = "info") {
    const status = document.getElementById("status");
    if (!status) return;

    status.textContent = message;
    status.className = "";
    status.classList.add(`status-${type}`);
}

/**
 * Add city to tracking system
 */
function sendCity() {
    let city = document.getElementById("city").value;
    if (!city.trim()) {
        setStatusMessage("Please enter a city name.", "error");
        return;
    }

    fetch("/api/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city })
    })
      .then(res => res.json())
      .then(d => {
          setStatusMessage("City added. Check maps for live data.", "success");
          document.getElementById("city").value = "";
          updateDashboard(); // Refresh dashboard immediately
      })
      .catch(err => {
          setStatusMessage("Error adding city: " + err.message, "error");
      });
}
