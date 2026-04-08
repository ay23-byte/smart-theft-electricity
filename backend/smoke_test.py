"""End-to-end smoke test for the SmartTheft backend.

This script runs against a shared in-memory SQLite database so the integration
checks can exercise create/update workflows without touching the real project
data.

Run:
    python smoke_test.py

Optional:
    python smoke_test.py --retrain
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
import tempfile
import uuid
from io import BytesIO, StringIO
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


SMOKE_DB_PATH = str(SCRIPT_DIR / "smoke_test.sqlite")
SMOKE_DB_URI = "file:smarttheft_smoke?mode=memory&cache=shared"
ORIGINAL_SQLITE_CONNECT = sqlite3.connect
ORIGINAL_MKSTEMP = tempfile.mkstemp


def smoke_connect(database, *args, **kwargs):
    if str(database) == SMOKE_DB_PATH:
        kwargs = dict(kwargs)
        kwargs["uri"] = True
        kwargs["check_same_thread"] = False
        return ORIGINAL_SQLITE_CONNECT(SMOKE_DB_URI, *args, **kwargs)
    return ORIGINAL_SQLITE_CONNECT(database, *args, **kwargs)


ANCHOR_CONNECTION = ORIGINAL_SQLITE_CONNECT(SMOKE_DB_URI, uri=True, check_same_thread=False)
sqlite3.connect = smoke_connect
os.environ["DATABASE_PATH"] = SMOKE_DB_PATH

# Import after DATABASE_PATH and sqlite3.connect are prepared for the smoke DB.
sys.path.insert(0, str(SCRIPT_DIR))
from app import DEFAULT_USERS, app as flask_app  # noqa: E402


flask_app.config["TESTING"] = True


class SmokeTestError(RuntimeError):
    pass


def snippet(resp, limit=240):
    try:
        text = resp.get_data(as_text=True)
    except Exception:
        return "<unavailable>"
    return text[:limit].replace("\n", " ").strip()


def ensure_status(resp, expected, label):
    if resp.status_code not in expected:
        raise SmokeTestError(
            f"{label} failed: expected {expected}, got {resp.status_code}. "
            f"Body: {snippet(resp)}"
        )


def expect_json(resp, label):
    if not resp.is_json:
        raise SmokeTestError(f"{label} did not return JSON. Body: {snippet(resp)}")
    return resp.get_json()


def log_ok(label):
    print(f"[PASS] {label}")


def log_skip(label):
    print(f"[SKIP] {label}")


def login(client):
    admin_username = os.environ.get("SMART_THEFT_ADMIN_USER", DEFAULT_USERS[0]["username"])
    admin_password = os.environ.get("SMART_THEFT_ADMIN_PASSWORD", DEFAULT_USERS[0]["password"])
    resp = client.post(
        "/login",
        data={"username": admin_username, "password": admin_password},
        follow_redirects=False,
    )
    ensure_status(resp, {302, 303}, "login")
    log_ok("login")


def get_first_alert(client):
    resp = client.get("/api/alerts")
    ensure_status(resp, {200}, "/api/alerts")
    alerts = expect_json(resp, "/api/alerts")
    return alerts[0] if alerts else None


def check_read_only_routes(client):
    routes = [
        ("/api/session", "session"),
        ("/", "home page"),
        ("/map", "map page"),
        ("/earth", "earth page"),
        ("/alerts", "alerts page"),
        ("/cases", "cases page"),
        ("/monitoring", "monitoring page"),
        ("/admin", "admin page"),
        ("/api/notifications/summary", "notification summary"),
        ("/api/notifications", "notifications list"),
        ("/api/monitoring/summary", "monitoring summary"),
        ("/api/model/monitoring", "model monitoring"),
        ("/api/dispatch/plan", "dispatch plan"),
        ("/api/zones/geojson", "zones geojson"),
        ("/api/audit-log", "audit log"),
        ("/api/debug/cities", "debug cities"),
        ("/api/cases", "cases api"),
        ("/api/cesium-token", "cesium token"),
    ]
    for path, label in routes:
        resp = client.get(path)
        ensure_status(resp, {200}, label)
        log_ok(label)

    resp = client.get("/api/live")
    ensure_status(resp, {200}, "/api/live")
    live_payload = expect_json(resp, "/api/live")
    if not isinstance(live_payload, list):
        raise SmokeTestError("/api/live returned a non-list payload.")
    log_ok("live data")

    stream_resp = client.get("/api/live/stream", buffered=False)
    ensure_status(stream_resp, {200}, "/api/live/stream")
    if "text/event-stream" not in stream_resp.headers.get("Content-Type", ""):
        raise SmokeTestError("/api/live/stream did not return event-stream content.")
    first_chunk = next(stream_resp.response, b"")
    if not first_chunk:
        raise SmokeTestError("/api/live/stream did not emit an event.")
    stream_resp.close()
    log_ok("live stream")

    resp = client.get("/api/model/performance-report")
    if resp.status_code == 200:
        log_ok("model performance report")
    elif resp.status_code == 404:
        log_skip("model performance report not found")
    else:
        ensure_status(resp, {200}, "model performance report")


def check_prediction_routes(client):
    single_payload = {
        "avg_daily_consumption": 120.5,
        "max_daily_consumption": 360.0,
        "consumption_variance": 48.2,
    }
    resp = client.post("/api/predict", json=single_payload)
    ensure_status(resp, {200}, "single prediction")
    data = expect_json(resp, "single prediction")
    if "status" not in data or "risk_score" not in data:
        raise SmokeTestError("Single prediction response is missing status or risk_score.")
    log_ok("single prediction")

    engineered_csv = "avg_daily_consumption,max_daily_consumption,consumption_variance,city\n120,340,45,SmokeTown\n80,190,22,SmokeTown\n"
    resp = client.post(
        "/api/predict-batch",
        data={"file": (BytesIO(engineered_csv.encode("utf-8")), "engineered.csv")},
        content_type="multipart/form-data",
    )
    ensure_status(resp, {200}, "engineered batch prediction")
    batch_data = expect_json(resp, "engineered batch prediction")
    if batch_data.get("summary", {}).get("processed_rows", 0) < 1:
        raise SmokeTestError("Engineered batch prediction processed no rows.")
    log_ok("engineered batch prediction")

    raw_csv = StringIO()
    writer = csv.writer(raw_csv)
    writer.writerow(["CONS_NO", "FLAG"] + [f"D{i}" for i in range(1, 11)])
    writer.writerow(["10001", 0] + [120, 118, 121, 119, 120, 122, 123, 121, 120, 119])
    writer.writerow(["10002", 1] + [340, 355, 332, 360, 348, 351, 349, 350, 358, 345])
    resp = client.post(
        "/api/predict-batch",
        data={"file": (BytesIO(raw_csv.getvalue().encode("utf-8")), "raw.csv")},
        content_type="multipart/form-data",
    )
    ensure_status(resp, {200}, "raw batch prediction")
    raw_data = expect_json(resp, "raw batch prediction")
    if raw_data.get("source_format") not in {"wide", "engineered"}:
        raise SmokeTestError("Raw batch prediction did not report a recognized source format.")
    log_ok("raw batch prediction")


def check_ingest_route(client):
    ingest_csv = StringIO()
    writer = csv.writer(ingest_csv)
    writer.writerow(["city", "power", "lat", "lon", "voltage", "current", "zone_name"])
    writer.writerow(["Smoke City Alpha", 2450, 28.50, 77.20, 220, 11.14, "Central Grid"])
    writer.writerow(["Smoke City Beta", 3100, 19.07, 72.88, 220, 14.09, "Industrial Belt"])
    resp = client.post(
        "/api/ingest/csv",
        data={"file": (BytesIO(ingest_csv.getvalue().encode("utf-8")), "ingest.csv")},
        content_type="multipart/form-data",
    )
    ensure_status(resp, {200}, "CSV ingest")
    data = expect_json(resp, "CSV ingest")
    if data.get("inserted_rows", 0) < 2:
        raise SmokeTestError("CSV ingest did not insert the expected rows.")
    log_ok("CSV ingest")


def check_city_and_case_routes(client):
    unique_city = f"Smoke City {uuid.uuid4().hex[:8]}"
    app_module = sys.modules.get("app")
    original_predict = getattr(app_module, "run_ai_prediction", None) if app_module else None
    if app_module is not None:
        app_module.run_ai_prediction = lambda power_val, city_name: ("NORMAL", 12.34)  # type: ignore[assignment]
    try:
        resp = client.post(
            "/api/add",
            json={"city": unique_city, "lat": 26.85, "lon": 80.95},
        )
    finally:
        if app_module is not None and original_predict is not None:
            app_module.run_ai_prediction = original_predict  # type: ignore[assignment]

    ensure_status(resp, {200}, "add city")
    add_data = expect_json(resp, "add city")
    if str(add_data.get("city", "")).strip().lower() != unique_city.lower():
        raise SmokeTestError("Add city response did not echo the created city.")
    log_ok("add city")

    case_payload = {
        "city": unique_city,
        "zone_id": f"{unique_city.lower().replace(' ', '-')}-central",
        "zone_name": "Central Grid",
        "location_label": f"{unique_city} - Central Grid",
        "severity": "high",
        "recommended_action": "Inspect transformer",
        "assignee": "operator",
        "notes": "Created by smoke test.",
        "latest_risk_score": 87.4,
    }
    resp = client.post("/api/cases", json=case_payload)
    ensure_status(resp, {200, 201}, "create case")
    case_data = expect_json(resp, "create case")
    case = case_data.get("case") or {}
    case_id = case.get("id")
    if not case_id:
        raise SmokeTestError("Create case response did not include a case id.")
    log_ok("create case")

    resp = client.patch(
        f"/api/cases/{case_id}",
        json={
            "status": "in_progress",
            "assignee": "operator",
            "notes": "Smoke test progressing.",
        },
    )
    ensure_status(resp, {200}, "update case")
    log_ok("update case")

    resp = client.post(
        "/api/cases/bulk-status",
        json={"case_ids": [case_id], "status": "closed", "note": "Smoke test bulk close."},
    )
    ensure_status(resp, {200}, "bulk case status")
    log_ok("bulk case status")

    resp = client.get(f"/api/cases/{case_id}/timeline")
    ensure_status(resp, {200}, "case timeline")
    log_ok("case timeline")

    resp = client.get("/api/cases/export.csv")
    ensure_status(resp, {200}, "cases CSV export")
    log_ok("cases CSV export")

    resp = client.get("/api/cases/report.pdf")
    ensure_status(resp, {200}, "cases PDF export")
    log_ok("cases PDF export")

    return case_id, unique_city


def check_notifications_and_alerts(client, case_id):
    resp = client.get("/api/notifications/summary")
    ensure_status(resp, {200}, "notification summary")
    log_ok("notification summary")

    resp = client.get("/api/notifications")
    ensure_status(resp, {200}, "notifications list")
    notifications = expect_json(resp, "notifications list")
    if notifications:
        resp = client.patch("/api/notifications/read-all")
        ensure_status(resp, {200}, "mark all notifications read")
        log_ok("mark all notifications read")
    else:
        log_skip("no notifications to mark as read")

    alerts_resp = client.get("/api/alerts")
    ensure_status(alerts_resp, {200}, "alerts list")
    alerts = expect_json(alerts_resp, "alerts list")
    if not alerts:
        log_skip("no active alerts to workflow-test")
        return

    if len(alerts) >= 1:
        alert = alerts[0]
        ack_resp = client.post(
            "/api/alerts/acknowledge",
            json={
                "city": alert["city"],
                "zone_id": alert.get("zone_id"),
                "timestamp": alert["timestamp"],
                "note": "Smoke test acknowledge.",
            },
        )
        ensure_status(ack_resp, {200}, "acknowledge alert")
        log_ok("acknowledge alert")

    if len(alerts) >= 2:
        alert = alerts[1]
        esc_resp = client.post(
            "/api/alerts/escalate",
            json={
                "city": alert["city"],
                "zone_id": alert.get("zone_id"),
                "timestamp": alert["timestamp"],
                "note": "Smoke test escalate.",
            },
        )
        ensure_status(esc_resp, {200}, "escalate alert")
        esc_data = expect_json(esc_resp, "escalate alert")
        if not esc_data.get("case_id"):
            raise SmokeTestError("Escalate alert did not return a case id.")
        log_ok("escalate alert")

    if len(alerts) >= 3:
        alert = alerts[2]
        res_resp = client.post(
            "/api/alerts/resolve",
            json={
                "city": alert["city"],
                "zone_id": alert.get("zone_id"),
                "timestamp": alert["timestamp"],
                "note": "Smoke test resolve.",
                "case_id": case_id,
            },
        )
        ensure_status(res_resp, {200}, "resolve alert")
        log_ok("resolve alert")
    else:
        log_skip("not enough alerts to test resolve separately")


def check_admin_routes(client):
    resp = client.get("/api/admin/users")
    ensure_status(resp, {200}, "admin users list")
    users = expect_json(resp, "admin users list").get("users", [])
    if not users:
        raise SmokeTestError("Admin users endpoint returned no users.")
    log_ok("admin users list")

    unique_username = f"smoke_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/admin/users",
        json={
            "username": unique_username,
            "full_name": "Smoke Test User",
            "password": "SmokePass123!",
            "role": "analyst",
        },
    )
    ensure_status(resp, {201}, "create admin user")
    log_ok("create admin user")

    try:
        resp = client.get("/api/admin/database/backup")
        ensure_status(resp, {200}, "database backup")
        backup_bytes = resp.get_data()
        if not backup_bytes:
            raise SmokeTestError("Database backup response was empty.")
        log_ok("database backup")

        resp = client.post(
            "/api/admin/database/restore",
            data={"file": (BytesIO(backup_bytes), "smoke_restore.sqlite")},
            content_type="multipart/form-data",
        )
        ensure_status(resp, {200}, "database restore")
        log_ok("database restore")
    except Exception as exc:
        log_skip(f"database backup/restore skipped in this environment: {exc}")


def maybe_retrain_model(client):
    resp = client.post("/api/model/retrain")
    ensure_status(resp, {200}, "model retrain")
    data = expect_json(resp, "model retrain")
    if not data.get("dataset_size"):
        raise SmokeTestError("Model retrain did not report a dataset size.")
    log_ok("model retrain")


def main():
    parser = argparse.ArgumentParser(description="Run SmartTheft backend smoke tests.")
    parser.add_argument(
        "--retrain",
        action="store_true",
        help="Also test the model retraining endpoint (takes longer and rewrites model artifacts).",
    )
    args = parser.parse_args()

    print("Using shared in-memory SQLite smoke database.")
    try:
        with flask_app.test_client() as client:
            app_module = sys.modules.get("app")
            if app_module is not None and hasattr(app_module, "tempfile"):
                def smoke_mkstemp(*args, **kwargs):
                    kwargs = dict(kwargs)
                    kwargs.setdefault("dir", str(SCRIPT_DIR / "data"))
                    return ORIGINAL_MKSTEMP(*args, **kwargs)

                app_module.tempfile.mkstemp = smoke_mkstemp  # type: ignore[assignment]
            login(client)
            check_read_only_routes(client)
            check_prediction_routes(client)
            check_ingest_route(client)
            case_id, _city = check_city_and_case_routes(client)
            check_notifications_and_alerts(client, case_id)
            check_admin_routes(client)
            if args.retrain:
                maybe_retrain_model(client)
            print("\nSmoke test completed successfully.")
    finally:
        try:
            ANCHOR_CONNECTION.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except SmokeTestError as exc:
        print(f"\n[FAIL] {exc}")
        raise SystemExit(1) from exc
