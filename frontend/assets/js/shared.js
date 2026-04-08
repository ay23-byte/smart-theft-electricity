const NOTIFICATION_BADGE_REFRESH_MS = 30000;

function updateNotificationBadges(unreadCount) {
    const count = Number(unreadCount) || 0;
    const alertLinks = document.querySelectorAll('.portal-header a[href="/alerts"]');

    alertLinks.forEach((link) => {
        let badge = link.querySelector(".portal-nav-badge");

        if (count <= 0) {
            if (badge) {
                badge.remove();
            }
            link.removeAttribute("aria-label");
            return;
        }

        if (!badge) {
            badge = document.createElement("span");
            badge.className = "portal-nav-badge";
            link.appendChild(badge);
        }

        badge.textContent = String(count);
        link.setAttribute("aria-label", `Alerts, ${count} unread notification${count === 1 ? "" : "s"}`);
    });
}

function updateNotificationCounters(unreadCount) {
    document.querySelectorAll("[data-notification-count]").forEach((node) => {
        node.textContent = String(Number(unreadCount) || 0);
    });
}

async function refreshNotificationSummary() {
    try {
        const response = await fetch("/api/notifications/summary");
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Failed to load notification summary.");
        }

        updateNotificationBadges(payload.unread_count || 0);
        updateNotificationCounters(payload.unread_count || 0);
    } catch (error) {
        console.warn("Notification summary unavailable:", error);
    }
}

window.refreshNotificationSummary = refreshNotificationSummary;

document.addEventListener("DOMContentLoaded", () => {
    refreshNotificationSummary();
    setInterval(refreshNotificationSummary, NOTIFICATION_BADGE_REFRESH_MS);
});
