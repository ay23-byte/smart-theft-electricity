function setAdminFeedback(message, tone = "info") {
    const feedback = document.getElementById("adminFeedback");
    if (!feedback) return;
    feedback.className = `cases-feedback cases-feedback--${tone}`;
    feedback.textContent = message;
}

function renderAdminUsers(users) {
    const list = document.getElementById("adminUsersList");
    if (!list) return;

    if (!users.length) {
        list.innerHTML = `<div class="stack-item"><p>No users found.</p></div>`;
        return;
    }

    list.innerHTML = users.map((user) => `
        <div class="stack-item">
            <strong>${user.full_name}</strong>
            <span>${user.role} • ${user.username}</span>
            <p>Created ${user.created_at}</p>
        </div>
    `).join("");
}

function renderAdminNotifications(notifications) {
    const list = document.getElementById("adminNotifications");
    const bulkButton = document.getElementById("markAllNotificationsRead");
    if (!list) return;

    if (!notifications.length) {
        list.innerHTML = `<div class="stack-item"><p>No notifications available.</p></div>`;
        if (bulkButton) {
            bulkButton.disabled = true;
        }
        return;
    }

    list.innerHTML = notifications.map((item) => `
        <div class="stack-item">
            <strong>${item.title}</strong>
            <span>${item.category} • ${item.severity} • ${item.created_at}</span>
            <p>${item.message}</p>
            ${item.is_read ? "" : `<button type="button" class="portal-pill admin-read-notice" data-id="${item.id}">Mark Read</button>`}
        </div>
    `).join("");

    list.querySelectorAll(".admin-read-notice").forEach((button) => {
        button.addEventListener("click", async () => {
            const notificationId = button.dataset.id;
            await fetch(`/api/notifications/${notificationId}/read`, { method: "PATCH" });
            loadAdminConsole();
            if (typeof window.refreshNotificationSummary === "function") {
                window.refreshNotificationSummary();
            }
        });
    });

    if (bulkButton) {
        bulkButton.disabled = false;
    }
}

function initializeDatabaseControls() {
    const backupButton = document.getElementById("downloadDatabaseBackup");
    if (backupButton) {
        backupButton.addEventListener("click", handleDatabaseBackupDownload);
    }

    const restoreForm = document.getElementById("databaseRestoreForm");
    if (restoreForm) {
        restoreForm.addEventListener("submit", handleDatabaseRestore);
    }
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

        setAdminFeedback(`Marked ${result.updated_count || 0} notifications as read.`, "success");
        loadAdminConsole();
        if (typeof window.refreshNotificationSummary === "function") {
            window.refreshNotificationSummary();
        }
    } catch (error) {
        setAdminFeedback(error.message, "error");
        button.disabled = false;
    } finally {
        button.textContent = originalText;
    }
}

async function loadAdminConsole() {
    try {
        const [usersResponse, notificationsResponse] = await Promise.all([
            fetch("/api/admin/users"),
            fetch("/api/notifications?limit=12"),
        ]);

        const usersPayload = await usersResponse.json();
        const notificationsPayload = await notificationsResponse.json();
        if (!usersResponse.ok) {
            throw new Error(usersPayload.error || "Failed to load admin users.");
        }

        renderAdminUsers(usersPayload.users || []);
        renderAdminNotifications(notificationsPayload.notifications || []);
    } catch (error) {
        setAdminFeedback(error.message, "error");
    }
}

async function handleUserCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
        full_name: form.full_name.value.trim(),
        username: form.username.value.trim(),
        password: form.password.value.trim(),
        role: form.role.value,
    };

    try {
        const response = await fetch("/api/admin/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Failed to create user.");
        }

        form.reset();
        setAdminFeedback(`User ${result.user.username} created successfully.`, "success");
        loadAdminConsole();
    } catch (error) {
        setAdminFeedback(error.message, "error");
    }
}

async function handleIngestion(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const resultBox = document.getElementById("ingestionResult");
    const file = document.getElementById("ingestionFile")?.files?.[0];
    if (!file) {
        resultBox.innerHTML = `<div class="stack-item"><p>Please choose a CSV file.</p></div>`;
        return;
    }

    const payload = new FormData();
    payload.append("file", file);

    try {
        const response = await fetch("/api/ingest/csv", {
            method: "POST",
            body: payload,
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Ingestion failed.");
        }

        resultBox.innerHTML = `
            <div class="stack-item">
                <strong>${result.filename}</strong>
                <span>${result.inserted_rows} rows ingested • ${result.theft_count} theft flags</span>
                <p>New cities: ${(result.new_cities || []).join(", ") || "none"}</p>
                <p>Invalid rows: ${(result.invalid_rows || []).length}</p>
            </div>
        `;
    } catch (error) {
        resultBox.innerHTML = `<div class="stack-item"><p>${error.message}</p></div>`;
    }
}

function handleDatabaseBackupDownload() {
    window.location.href = "/api/admin/database/backup";
}

async function handleDatabaseRestore(event) {
    event.preventDefault();

    const form = event.currentTarget;
    const button = form.querySelector("button[type='submit']");
    const fileInput = document.getElementById("databaseRestoreFile");
    const selectedFile = fileInput?.files?.[0];

    if (!selectedFile) {
        setAdminFeedback("Please choose a SQLite backup file to restore.", "error");
        return;
    }

    const payload = new FormData();
    payload.append("file", selectedFile);

    if (button) {
        button.disabled = true;
        button.textContent = "Restoring...";
    }

    try {
        const response = await fetch("/api/admin/database/restore", {
            method: "POST",
            body: payload,
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "Database restore failed.");
        }

        setAdminFeedback("Database restored successfully. Refreshing portal data...", "success");
        form.reset();
        loadAdminConsole();
        if (typeof window.refreshNotificationSummary === "function") {
            window.refreshNotificationSummary();
        }
    } catch (error) {
        setAdminFeedback(error.message, "error");
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = "Restore Database";
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("adminUserForm")?.addEventListener("submit", handleUserCreate);
    document.getElementById("ingestionForm")?.addEventListener("submit", handleIngestion);
    document.getElementById("markAllNotificationsRead")?.addEventListener("click", markAllNotificationsRead);
    initializeDatabaseControls();
    loadAdminConsole();
    setInterval(loadAdminConsole, 15000);
});
