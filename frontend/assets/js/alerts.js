const canManageAlerts = ["admin", "operator"].includes(String(window.smartTheftCurrentRole || "").toLowerCase());

async function openCaseFromAlert(alert) {
    const payload = {
        city: alert.city,
        zone_id: alert.zone_id,
        zone_name: alert.zone_name,
        location_label: alert.location_label || alert.city,
        severity: alert.severity,
        recommended_action: alert.recommended_action,
        latest_risk_score: alert.risk_score,
        notes: alert.action_reason || "",
    };

    const response = await fetch("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || "Failed to create case.");
    }

    return result;
}

async function acknowledgeAlert(alert, note = "") {
    const response = await fetch("/api/alerts/acknowledge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            city: alert.city,
            zone_id: alert.zone_id,
            timestamp: alert.timestamp,
            note,
        }),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || "Failed to acknowledge the alert.");
    }

    return result;
}

async function escalateAlert(alert, note = "") {
    const response = await fetch("/api/alerts/escalate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            city: alert.city,
            zone_id: alert.zone_id,
            timestamp: alert.timestamp,
            note,
        }),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || "Failed to escalate the alert.");
    }

    return result;
}

async function resolveAlert(alert, note = "") {
    const response = await fetch("/api/alerts/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            city: alert.city,
            zone_id: alert.zone_id,
            timestamp: alert.timestamp,
            note,
        }),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || "Failed to resolve the alert.");
    }

    return result;
}

async function loadAlerts() {
    const list = document.getElementById("alertsList");
    if (!list) return;

    try {
        const response = await fetch("/api/alerts");
        const alerts = await response.json();
        if (!response.ok) {
            throw new Error("Failed to load alerts.");
        }

        document.getElementById("alert-count").textContent = alerts.length;
        document.getElementById("critical-count").textContent = alerts.filter(item => item.severity === "critical").length;
        document.getElementById("high-count").textContent = alerts.filter(item => item.severity === "high").length;
        document.getElementById("watch-count").textContent = alerts.filter(item => item.severity === "watch" || item.severity === "medium").length;

        if (!alerts.length) {
            list.innerHTML = `<div class="alert-card"><strong>No active alerts.</strong><p>Everything is currently within normal operating range.</p></div>`;
            return;
        }

        list.innerHTML = alerts.map((item) => `
            <article class="alert-card alert-card--${item.severity}" data-alert="${encodeURIComponent(JSON.stringify(item))}">
                <div class="alert-card__top">
                    <div>
                        <span class="alert-card__severity">${item.severity}</span>
                        <h3>${item.location_label || item.city}</h3>
                    </div>
                    <div class="alert-card__score">${Number(item.risk_score).toFixed(2)}%</div>
                </div>
                <p class="alert-card__reason">${item.action_reason}</p>
                <div class="alert-card__meta">
                    <span>Status: ${item.status}</span>
                    <span>Action: ${item.recommended_action}</span>
                    <span>Power: ${Number(item.power).toFixed(0)}W</span>
                    <span>Overload: ${Number(item.overload_ratio).toFixed(2)}x</span>
                </div>
                ${canManageAlerts ? `
                    <div class="alert-card__actions">
                        <button type="button" class="btn alert-card__button js-escalate-alert">Escalate</button>
                        <button type="button" class="btn alert-card__button js-resolve-alert">Resolve</button>
                        <button type="button" class="btn alert-card__button js-ack-alert">Acknowledge</button>
                        <a href="/cases" class="portal-link-action">View Cases</a>
                    </div>
                ` : `
                    <div class="alert-card__actions">
                        <a href="/cases" class="portal-link-action">View Cases</a>
                    </div>
                `}
            </article>
        `).join("");

        list.querySelectorAll(".js-escalate-alert").forEach((button) => {
            button.addEventListener("click", async () => {
                const card = button.closest(".alert-card");
                if (!card) return;

                try {
                    button.disabled = true;
                    button.textContent = "Escalating...";
                    const alertData = JSON.parse(decodeURIComponent(card.dataset.alert));
                    const note = window.prompt("Optional escalation note:", alertData.action_reason || "");
                    if (note === null) {
                        button.disabled = false;
                        button.textContent = "Escalate";
                        return;
                    }
                    const result = await escalateAlert(alertData, note.trim());
                    button.textContent = result.case_created ? "Escalated" : "Case Exists";
                    loadAlerts();
                } catch (error) {
                    button.disabled = false;
                    button.textContent = "Escalate";
                    window.alert(error.message);
                }
            });
        });

        list.querySelectorAll(".js-resolve-alert").forEach((button) => {
            button.addEventListener("click", async () => {
                const card = button.closest(".alert-card");
                if (!card) return;

                try {
                    button.disabled = true;
                    button.textContent = "Resolving...";
                    const alertData = JSON.parse(decodeURIComponent(card.dataset.alert));
                    const note = window.prompt("Optional resolution note:", "");
                    if (note === null) {
                        button.disabled = false;
                        button.textContent = "Resolve";
                        return;
                    }
                    await resolveAlert(alertData, note.trim());
                    button.textContent = "Resolved";
                    loadAlerts();
                } catch (error) {
                    button.disabled = false;
                    button.textContent = "Resolve";
                    window.alert(error.message);
                }
            });
        });

        list.querySelectorAll(".js-ack-alert").forEach((button) => {
            button.addEventListener("click", async () => {
                const card = button.closest(".alert-card");
                if (!card) return;

                try {
                    button.disabled = true;
                    button.textContent = "Acknowledging...";
                    const alertData = JSON.parse(decodeURIComponent(card.dataset.alert));
                    const result = await acknowledgeAlert(alertData);
                    button.textContent = result.acknowledged ? "Acknowledged" : "Already Saved";
                    loadAlerts();
                } catch (error) {
                    button.disabled = false;
                    button.textContent = "Acknowledge";
                    window.alert(error.message);
                }
            });
        });
    } catch (error) {
        list.innerHTML = `<div class="alert-card"><strong>Error loading alerts.</strong><p>${error.message}</p></div>`;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    loadAlerts();
    setInterval(loadAlerts, 5000);
});
