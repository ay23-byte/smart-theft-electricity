let allCasesCache = [];
const canManageCases = ["admin", "operator"].includes(String(window.smartTheftCurrentRole || "").toLowerCase());

function formatCaseStatus(status) {
    return String(status || "open").replaceAll("_", " ");
}

function getCaseStatusTone(status) {
    switch (String(status || "open")) {
        case "open":
            return "case-card__status--open";
        case "in_progress":
            return "case-card__status--progress";
        case "resolved":
            return "case-card__status--resolved";
        case "closed":
            return "case-card__status--closed";
        default:
            return "";
    }
}

function setCaseFeedback(message, tone = "info") {
    const feedback = document.getElementById("caseFeedback");
    if (!feedback) return;

    feedback.className = `cases-feedback cases-feedback--${tone}`;
    feedback.textContent = message;
}

function updateCaseSummary(summary = {}) {
    document.getElementById("case-total-count").textContent = summary.total ?? 0;
    document.getElementById("case-open-count").textContent = summary.open ?? 0;
    document.getElementById("case-progress-count").textContent = summary.in_progress ?? 0;
    document.getElementById("case-resolved-count").textContent = summary.resolved ?? 0;
    const closedCount = document.getElementById("case-closed-count");
    if (closedCount) {
        closedCount.textContent = summary.closed ?? 0;
    }
}

function updateCaseExportLink() {
    const filter = document.getElementById("caseStatusFilter");
    const exportLink = document.getElementById("caseExportLink");
    const reportLink = document.getElementById("caseReportLink");
    if (!exportLink) return;

    const query = filter && filter.value ? `?status=${encodeURIComponent(filter.value)}` : "";
    exportLink.href = `/api/cases/export.csv${query}`;
    if (reportLink) {
        reportLink.href = `/api/cases/report.pdf${query}`;
    }
}

function getVisibleCaseIds() {
    return applyLocalCaseFilters(allCasesCache).map((item) => item.id);
}

async function updateCaseStatus(caseId, status) {
    const response = await fetch(`/api/cases/${caseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || "Failed to update the case.");
    }

    return result;
}

async function bulkUpdateVisibleCases(status) {
    const visibleIds = getVisibleCaseIds();
    if (!visibleIds.length) {
        setCaseFeedback("No visible cases available for bulk update.", "error");
        return;
    }

    const response = await fetch("/api/cases/bulk-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            status,
            case_ids: visibleIds,
        }),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || "Bulk case update failed.");
    }

    return result;
}

async function loadCaseTimeline(caseId, target) {
    if (!target) return;

    target.innerHTML = `<div class="case-timeline__empty">Loading timeline...</div>`;

    try {
        const response = await fetch(`/api/cases/${caseId}/timeline`);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Failed to load case timeline.");
        }

        const events = payload.events || [];
        if (!events.length) {
            target.innerHTML = `<div class="case-timeline__empty">No audit events yet.</div>`;
            return;
        }

        target.innerHTML = events.map((event) => `
            <div class="case-timeline__item">
                <div class="case-timeline__dot"></div>
                <div class="case-timeline__content">
                    <strong>${event.summary}</strong>
                    <p>${event.details || "No additional details provided."}</p>
                    <span>${event.actor_username || "system"} ${event.actor_role ? `(${event.actor_role})` : ""} • ${event.created_at}</span>
                </div>
            </div>
        `).join("");
    } catch (error) {
        target.innerHTML = `<div class="case-timeline__empty">${error.message}</div>`;
    }
}

function getCaseFilters() {
    return {
        query: (document.getElementById("caseSearchInput")?.value || "").trim().toLowerCase(),
        severity: document.getElementById("caseSeverityFilter")?.value || "",
    };
}

function applyLocalCaseFilters(cases) {
    const filters = getCaseFilters();
    return cases.filter((item) => {
        if (filters.severity && item.severity !== filters.severity) {
            return false;
        }
        if (filters.query) {
            const haystack = [
                item.location_label,
                item.city,
                item.zone_name,
                item.assignee,
                item.recommended_action,
            ].join(" ").toLowerCase();
            return haystack.includes(filters.query);
        }
        return true;
    });
}

function renderCases(cases) {
    const list = document.getElementById("casesList");
    if (!list) return;

    if (!cases.length) {
        list.innerHTML = `
            <article class="case-card">
                <strong>No cases found.</strong>
                <p>Create a case from Alert Center to begin tracking investigations here.</p>
            </article>
        `;
        return;
    }

    list.innerHTML = cases.map((item) => `
        <article class="case-card case-card--${item.severity} case-card--${String(item.status || "open")}">
            <div class="case-card__header">
                <div>
                    <span class="alert-card__severity">${item.severity}</span>
                    <h3>${item.location_label}</h3>
                </div>
                <div class="case-card__status ${getCaseStatusTone(item.status)}">${formatCaseStatus(item.status)}</div>
            </div>

            <div class="alert-card__meta case-card__meta">
                <span>City: ${item.city}</span>
                <span>Zone: ${item.zone_name || "City-wide"}</span>
                <span>Action: ${item.recommended_action || "Pending"}</span>
                <span>Risk: ${item.latest_risk_score ? Number(item.latest_risk_score).toFixed(2) : "0.00"}%</span>
            </div>

            <form class="case-form" data-case-id="${item.id}">
                <label class="case-field">
                    <span>Status</span>
                    <select name="status">
                        <option value="open" ${item.status === "open" ? "selected" : ""}>Open</option>
                        <option value="in_progress" ${item.status === "in_progress" ? "selected" : ""}>In Progress</option>
                        <option value="resolved" ${item.status === "resolved" ? "selected" : ""}>Resolved</option>
                        <option value="closed" ${item.status === "closed" ? "selected" : ""}>Closed</option>
                    </select>
                </label>

                <label class="case-field">
                    <span>Assignee</span>
                    <input type="text" name="assignee" value="${item.assignee || ""}" placeholder="Field officer or analyst">
                </label>

                <label class="case-field case-field--full">
                    <span>Notes</span>
                    <textarea name="notes" rows="3" placeholder="Investigation notes, site observations, or follow-up plan">${item.notes || ""}</textarea>
                </label>

            <div class="case-card__footer">
                <div class="case-card__timestamps">
                    <span>Created: ${item.created_at || "-"}</span>
                    <span>Updated: ${item.updated_at || "-"}</span>
                </div>
                <div class="case-card__actions">
                    <button type="button" class="portal-pill case-timeline-toggle">View Timeline</button>
                    ${canManageCases ? `
                        ${item.status !== "in_progress" ? `<button type="button" class="portal-pill case-quick-action" data-case-id="${item.id}" data-status="in_progress">Start Work</button>` : ""}
                        ${item.status !== "resolved" ? `<button type="button" class="portal-pill case-quick-action" data-case-id="${item.id}" data-status="resolved">Resolve</button>` : ""}
                        ${item.status !== "closed" ? `<button type="button" class="portal-pill case-quick-action" data-case-id="${item.id}" data-status="closed">Close</button>` : ""}
                        ${item.status === "closed" ? `<button type="button" class="portal-pill case-quick-action" data-case-id="${item.id}" data-status="open">Reopen</button>` : ""}
                    ` : ""}
                    <button type="submit" class="btn">Save Case</button>
                </div>
            </div>
        </form>

            <div class="case-timeline" hidden>
                <div class="case-timeline__header">
                    <span class="eyebrow">Audit trail</span>
                    <strong>Investigation timeline</strong>
                </div>
                <div class="case-timeline__body"></div>
            </div>
        </article>
    `).join("");

    list.querySelectorAll(".case-timeline-toggle").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest(".case-card");
            const form = card?.querySelector(".case-form");
            const timeline = card?.querySelector(".case-timeline");
            const timelineBody = card?.querySelector(".case-timeline__body");
            if (!card || !form || !timeline || !timelineBody) return;

            const shouldOpen = timeline.hidden;
            timeline.hidden = !shouldOpen;
            button.textContent = shouldOpen ? "Hide Timeline" : "View Timeline";

            if (shouldOpen) {
                await loadCaseTimeline(form.dataset.caseId, timelineBody);
            }
        });
    });

    list.querySelectorAll(".case-form").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const caseId = form.dataset.caseId;
            const payload = {
                status: form.elements.status.value,
                assignee: form.elements.assignee.value.trim(),
                notes: form.elements.notes.value.trim(),
            };

            try {
                const response = await fetch(`/api/cases/${caseId}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || "Failed to update the case.");
                }

                setCaseFeedback(`Case #${caseId} updated successfully.`, "success");
                loadCases();
            } catch (error) {
                setCaseFeedback(error.message, "error");
            }
        });
    });

    list.querySelectorAll(".case-quick-action").forEach((button) => {
        button.addEventListener("click", async () => {
            const caseId = button.dataset.caseId;
            const nextStatus = button.dataset.status;
            if (!caseId || !nextStatus) return;

            const originalText = button.textContent;
            button.disabled = true;
            button.textContent = "Updating...";

            try {
                await updateCaseStatus(caseId, nextStatus);
                setCaseFeedback(`Case #${caseId} updated to ${formatCaseStatus(nextStatus)}.`, "success");
                loadCases();
            } catch (error) {
                button.disabled = false;
                button.textContent = originalText;
                setCaseFeedback(error.message, "error");
            }
        });
    });
}

async function loadCases() {
    const list = document.getElementById("casesList");
    const filter = document.getElementById("caseStatusFilter");
    if (!list) return;

    const query = filter && filter.value ? `?status=${encodeURIComponent(filter.value)}` : "";

    try {
        const response = await fetch(`/api/cases${query}`);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Failed to load cases.");
        }

        allCasesCache = payload.cases || [];
        updateCaseSummary(payload.summary || {});
        updateCaseExportLink();
        renderCases(applyLocalCaseFilters(allCasesCache));
    } catch (error) {
        list.innerHTML = `
            <article class="case-card">
                <strong>Error loading cases.</strong>
                <p>${error.message}</p>
            </article>
        `;
        setCaseFeedback(error.message, "error");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const filter = document.getElementById("caseStatusFilter");
    const severityFilter = document.getElementById("caseSeverityFilter");
    const searchInput = document.getElementById("caseSearchInput");
    if (filter) {
        filter.addEventListener("change", () => {
            updateCaseExportLink();
            loadCases();
        });
    }
    if (severityFilter) {
        severityFilter.addEventListener("change", () => renderCases(applyLocalCaseFilters(allCasesCache)));
    }
    if (searchInput) {
        searchInput.addEventListener("input", () => renderCases(applyLocalCaseFilters(allCasesCache)));
    }

    document.getElementById("bulkCloseVisibleCases")?.addEventListener("click", async () => {
        const button = document.getElementById("bulkCloseVisibleCases");
        if (!button) return;

        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "Closing...";

        try {
            const result = await bulkUpdateVisibleCases("closed");
            setCaseFeedback(`Closed ${result.updated_case_ids.length} visible case(s).`, "success");
            loadCases();
        } catch (error) {
            setCaseFeedback(error.message, "error");
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    });

    document.getElementById("bulkReopenVisibleCases")?.addEventListener("click", async () => {
        const button = document.getElementById("bulkReopenVisibleCases");
        if (!button) return;

        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "Reopening...";

        try {
            const result = await bulkUpdateVisibleCases("open");
            setCaseFeedback(`Reopened ${result.updated_case_ids.length} visible case(s).`, "success");
            loadCases();
        } catch (error) {
            setCaseFeedback(error.message, "error");
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    });

    updateCaseExportLink();
    loadCases();
    setInterval(loadCases, 10000);
});
