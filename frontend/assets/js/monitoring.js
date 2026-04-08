function renderMonitoringStats(data) {
    const container = document.getElementById("monitoringStats");
    if (!container) return;

    const cards = [
        ["Model Ready", data.model_loaded ? "Yes" : "No"],
        ["Theft Rate", `${Number(data.theft_rate || 0).toFixed(2)}%`],
        ["Average Drift", `${Number(data.average_drift || 0).toFixed(2)}%`],
        ["Active Alerts", data.active_alerts || 0],
        ["Open Cases", data.open_cases || 0],
        ["Unread Notices", data.unread_notifications || 0],
    ];

    container.innerHTML = cards.map(([label, value], index) => `
        <article class="stat-card ${index === 0 ? "stat-card--accent" : ""}">
            <div class="stat-label">${label}</div>
            <div class="stat-value">${value}</div>
        </article>
    `).join("");
}

function renderStackList(targetId, items, emptyMessage, renderItem) {
    const container = document.getElementById(targetId);
    if (!container) return;

    if (!items.length) {
        container.innerHTML = `<div class="stack-item"><p>${emptyMessage}</p></div>`;
        return;
    }

    container.innerHTML = items.map(renderItem).join("");
}

function renderModelMonitoring(data) {
    const summary = document.getElementById("modelDriftSummary");
    const chart = document.getElementById("modelDriftChart");
    const caption = document.getElementById("modelDriftCaption");
    if (!summary || !chart || !caption) return;

    const cards = [
        ["Avg Drift", `${Number(data.average_drift || 0).toFixed(2)}%`],
        ["Alert Count", Number(data.drift_alerts || 0)],
        ["Peak Positive", `${Number(data.max_positive_drift || 0).toFixed(2)}%`],
        ["Peak Negative", `${Number(data.max_negative_drift || 0).toFixed(2)}%`],
        ["Theft Label Rate", `${Number(data.theft_label_rate || 0).toFixed(2)}%`],
        ["Window", Number(data.sample_window || 0)],
    ];

    summary.innerHTML = cards.map(([label, value], index) => `
        <article class="stat-card ${index === 0 ? "stat-card--accent" : ""}">
            <div class="stat-label">${label}</div>
            <div class="stat-value">${value}</div>
        </article>
    `).join("");

    const series = Array.isArray(data.drift_series) ? data.drift_series : [];
    if (!series.length) {
        chart.innerHTML = `<div class="stack-item"><strong>No drift data available.</strong><p>There are not enough recent samples to render the trend line yet.</p></div>`;
        caption.textContent = "Drift values are computed from the latest theft samples compared with the city baseline. This is a monitoring proxy, not a full retraining score.";
        return;
    }

    const maxMagnitude = Math.max(...series.map((item) => Math.abs(Number(item.drift) || 0)), 1);
    chart.innerHTML = series.map((item, index) => {
        const drift = Number(item.drift) || 0;
        const height = Math.max(10, (Math.abs(drift) / maxMagnitude) * 100);
        const tone = item.risk_band || (Math.abs(drift) >= 30 ? "high" : Math.abs(drift) >= 15 ? "watch" : "normal");
        return `
            <div class="drift-bar ${tone}">
                <div class="drift-bar__track">
                    <div class="drift-bar__fill" style="height:${height}%;"></div>
                </div>
                <strong>${drift.toFixed(1)}%</strong>
                <span>${item.city}</span>
                <small>${item.status}</small>
            </div>
        `;
    }).join("");

    caption.textContent = `Drift is measured against each city's baseline load. ${Number(data.drift_alerts || 0)} sample${Number(data.drift_alerts || 0) === 1 ? "" : "s"} exceeded the monitoring threshold of 30%.`;
}

async function markAllNotificationsRead() {
    const button = document.getElementById("markAllNotificationsRead");
    if (!button) return;

    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Clearing...";

    try {
        const response = await fetch("/api/notifications/read-all", { method: "PATCH" });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Failed to clear notifications.");
        }

        loadMonitoringHub();
        if (typeof window.refreshNotificationSummary === "function") {
            window.refreshNotificationSummary();
        }
    } catch (error) {
        console.error("Failed to clear notifications:", error);
        button.disabled = false;
    } finally {
        button.textContent = originalText;
    }
}

async function loadMonitoringHub() {
    try {
        const [summaryResponse, notificationsResponse, modelMonitoringResponse] = await Promise.all([
            fetch("/api/monitoring/summary"),
            fetch("/api/notifications?limit=8&unread_only=1"),
            fetch("/api/model/monitoring"),
        ]);

        const summary = await summaryResponse.json();
        const notificationsPayload = await notificationsResponse.json();
        const modelMonitoringPayload = await modelMonitoringResponse.json();

        if (!summaryResponse.ok) {
            throw new Error(summary.error || "Failed to load monitoring summary.");
        }
        if (!modelMonitoringResponse.ok) {
            throw new Error(modelMonitoringPayload.error || "Failed to load model monitoring.");
        }

        renderMonitoringStats(summary);
        renderModelMonitoring(modelMonitoringPayload || {});
        renderStackList(
            "monitoringHotspots",
            summary.top_hotspots || [],
            "No active hotspots right now.",
            (item) => `
                <div class="stack-item">
                    <strong>${item.location_label}</strong>
                    <span>${item.recommended_action} • ${item.severity}</span>
                    <p>${Number(item.risk_score).toFixed(2)}% risk • ${Number(item.power).toFixed(0)}W</p>
                </div>
            `,
        );

        renderStackList(
            "dispatchPlanList",
            summary.dispatch_plan || [],
            "No open dispatch stops right now.",
            (item, index) => `
                <div class="stack-item">
                    <strong>Stop ${index + 1}: ${item.location_label}</strong>
                    <span>${item.assignee || "Unassigned"} • ETA ${item.dispatch_eta_minutes} min</span>
                    <p>${item.severity} priority • ${item.status.replaceAll("_", " ")} • ${Number(item.latest_risk_score || 0).toFixed(2)}% risk</p>
                </div>
            `,
        );

        renderStackList(
            "monitoringNotifications",
            notificationsPayload.notifications || [],
            "No unread notifications.",
            (item) => `
                <div class="stack-item">
                    <strong>${item.title}</strong>
                    <span>${item.category} • ${item.severity}</span>
                    <p>${item.message}</p>
                </div>
            `,
        );

        const bulkButton = document.getElementById("markAllNotificationsRead");
        if (bulkButton) {
            bulkButton.disabled = !(notificationsPayload.notifications || []).length;
        }

        if (typeof window.refreshNotificationSummary === "function") {
            window.refreshNotificationSummary();
        }
    } catch (error) {
        renderStackList("monitoringHotspots", [], error.message, () => "");
        const chart = document.getElementById("modelDriftChart");
        const summary = document.getElementById("modelDriftSummary");
        const caption = document.getElementById("modelDriftCaption");
        if (chart) {
            chart.innerHTML = `<div class="stack-item"><strong>Model monitoring unavailable.</strong><p>${error.message}</p></div>`;
        }
        if (summary) {
            summary.innerHTML = "";
        }
        if (caption) {
            caption.textContent = "Model drift data could not be loaded right now.";
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("markAllNotificationsRead")?.addEventListener("click", markAllNotificationsRead);
    loadMonitoringHub();
    setInterval(loadMonitoringHub, 10000);
});
