import os
import json
import random
import sqlite3
import time
import csv
import tempfile
from io import StringIO
from datetime import datetime
from functools import wraps
from math import sqrt

import joblib
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, send_file, url_for
from twilio.rest import Client
from werkzeug.security import check_password_hash, generate_password_hash

from train import (
    DEFAULT_THRESHOLD,
    build_inference_features,
    clean_wide_meter_dataset,
    train_and_save_model,
    load_trained_artifacts,
)

# Load environment variables
load_dotenv()

# --- PRECISE PATH CONFIGURATION ---
# BASE_DIR = .../smartTheft/backend
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
# ROOT_DIR = .../smartTheft
ROOT_DIR = os.path.dirname(BASE_DIR)
# FRONTEND_DIR = .../smartTheft/frontend
FRONTEND_DIR = os.path.join(ROOT_DIR, 'frontend')

app = Flask(
    __name__,
    template_folder=FRONTEND_DIR,
    static_folder=os.path.join(FRONTEND_DIR, 'assets'),
    static_url_path='/assets'
)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.getenv("SECRET_KEY", "smart-theft-dev-secret"))

BATCH_FEATURE_COLUMNS = {
    "avg_daily_consumption",
    "max_daily_consumption",
    "consumption_variance",
}
BATCH_RAW_EXCLUDED_COLUMNS = {"CONS_NO", "FLAG", "THEFT_LABEL", "LABEL", "ID"}

# -------------------------
# AI MODEL LOADING
# -------------------------
# Based on your screenshot, these files are in the 'backend' folder
MODEL_PATH = os.path.join(BASE_DIR, 'smart_theft_model.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'scaler.pkl')

model = None
scaler = None


def load_model_artifacts():
    global model, scaler
    if model is not None and scaler is not None:
        return model, scaler

    try:
        loaded_model, loaded_scaler = load_trained_artifacts(BASE_DIR)
        model, scaler = loaded_model, loaded_scaler
        print("Reusable model helpers loaded successfully.")
    except Exception as helper_error:
        print(f"Reusable model loader unavailable: {helper_error}")
        try:
            loaded_model = joblib.load(MODEL_PATH)
            loaded_scaler = joblib.load(SCALER_PATH)
            model, scaler = loaded_model, loaded_scaler
            print("AI Model & Scaler loaded successfully.")
        except Exception as e:
            print(f"AI Model Load Failed: {e}. Check if files are in 'backend' folder.")
            model = None
            scaler = None

    return model, scaler


def get_model():
    return load_model_artifacts()[0]


def get_scaler():
    return load_model_artifacts()[1]


def model_artifacts_present():
    return os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH)

# -------------------------
# TWILIO & DATABASE
# -------------------------
TWILIO_SID = os.getenv('TWILIO_SID', 'YOUR_SID')
TWILIO_AUTH = os.getenv('TWILIO_AUTH_TOKEN', 'YOUR_AUTH')
TWILIO_FROM = os.getenv('TWILIO_PHONE_FROM', '+1234567890')
TWILIO_TO = os.getenv('TWILIO_PHONE_TO', '+91XXXXXXXXXX')
SMS_ALERTS_ENABLED = os.getenv('SMS_ALERTS_ENABLED', 'false').strip().lower() == 'true'
CESIUM_ION_TOKEN = os.getenv('CESIUM_ION_TOKEN', '')
LIVE_CACHE_SECONDS = max(1, int(os.getenv('LIVE_CACHE_SECONDS', '10')))

client = Client(TWILIO_SID, TWILIO_AUTH)
# Data folder is inside the backend folder according to your setup
DB_PATH_SETTING = os.getenv("DATABASE_PATH", os.path.join('data', 'theft.db'))
DB_PATH = DB_PATH_SETTING if os.path.isabs(DB_PATH_SETTING) else os.path.join(BASE_DIR, DB_PATH_SETTING)

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS thefts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            voltage REAL,
            current REAL,
            power REAL,
            status TEXT,
            lat REAL,
            lon REAL,
            zone_id TEXT,
            zone_name TEXT,
            meter_id TEXT,
            consumer_name TEXT,
            consumer_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("PRAGMA table_info(thefts)")
    existing_columns = {row[1] for row in cur.fetchall()}
    if "zone_id" not in existing_columns:
        cur.execute("ALTER TABLE thefts ADD COLUMN zone_id TEXT")
    if "zone_name" not in existing_columns:
        cur.execute("ALTER TABLE thefts ADD COLUMN zone_name TEXT")
    if "meter_id" not in existing_columns:
        cur.execute("ALTER TABLE thefts ADD COLUMN meter_id TEXT")
    if "consumer_name" not in existing_columns:
        cur.execute("ALTER TABLE thefts ADD COLUMN consumer_name TEXT")
    if "consumer_type" not in existing_columns:
        cur.execute("ALTER TABLE thefts ADD COLUMN consumer_type TEXT")
    if "timestamp" not in existing_columns:
        cur.execute("ALTER TABLE thefts ADD COLUMN timestamp TEXT")
    cur.execute("UPDATE thefts SET timestamp = COALESCE(timestamp, CURRENT_TIMESTAMP)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            zone_id TEXT,
            zone_name TEXT,
            location_label TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            recommended_action TEXT,
            assignee TEXT,
            notes TEXT,
            latest_risk_score REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS case_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor_username TEXT,
            actor_role TEXT,
            summary TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(case_id) REFERENCES cases(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            related_case_id INTEGER,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(related_case_id) REFERENCES cases(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            actor_username TEXT,
            actor_role TEXT,
            summary TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_acknowledgements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            zone_id TEXT,
            reading_timestamp TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'acknowledged',
            case_id INTEGER,
            acknowledged_by TEXT,
            acknowledged_role TEXT,
            note TEXT,
            acknowledged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(city, zone_id, reading_timestamp)
        )
        """
    )
    cur.execute("PRAGMA table_info(alert_acknowledgements)")
    alert_columns = {row[1] for row in cur.fetchall()}
    if "action" not in alert_columns:
        cur.execute("ALTER TABLE alert_acknowledgements ADD COLUMN action TEXT NOT NULL DEFAULT 'acknowledged'")
    if "case_id" not in alert_columns:
        cur.execute("ALTER TABLE alert_acknowledgements ADD COLUMN case_id INTEGER")
    if "acknowledged_by" not in alert_columns:
        cur.execute("ALTER TABLE alert_acknowledgements ADD COLUMN acknowledged_by TEXT")
    if "acknowledged_role" not in alert_columns:
        cur.execute("ALTER TABLE alert_acknowledgements ADD COLUMN acknowledged_role TEXT")
    if "note" not in alert_columns:
        cur.execute("ALTER TABLE alert_acknowledgements ADD COLUMN note TEXT")
    if "acknowledged_at" not in alert_columns:
        cur.execute("ALTER TABLE alert_acknowledgements ADD COLUMN acknowledged_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    cur.execute(
        """
        UPDATE alert_acknowledgements
        SET action = COALESCE(action, 'acknowledged'),
            acknowledged_at = COALESCE(acknowledged_at, CURRENT_TIMESTAMP)
        """
    )
    con.commit()
    con.close()

init_db()

LIVE_DATA_CACHE = {
    "timestamp": 0.0,
    "data": [],
}


DEFAULT_USERS = [
    {
        "username": os.getenv("SMART_THEFT_ADMIN_USER", "admin"),
        "full_name": "System Administrator",
        "password": os.getenv("SMART_THEFT_ADMIN_PASSWORD", "admin123"),
        "role": "admin",
    },
    {
        "username": os.getenv("SMART_THEFT_ANALYST_USER", "analyst"),
        "full_name": "Grid Risk Analyst",
        "password": os.getenv("SMART_THEFT_ANALYST_PASSWORD", "analyst123"),
        "role": "analyst",
    },
    {
        "username": os.getenv("SMART_THEFT_OPERATOR_USER", "operator"),
        "full_name": "Field Operations Officer",
        "password": os.getenv("SMART_THEFT_OPERATOR_PASSWORD", "operator123"),
        "role": "operator",
    },
]


def seed_default_users():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    for user in DEFAULT_USERS:
        cur.execute("SELECT id FROM users WHERE username = ?", (user["username"],))
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO users (username, full_name, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (
                user["username"],
                user["full_name"],
                generate_password_hash(user["password"]),
                user["role"],
            ),
        )
    con.commit()
    con.close()


seed_default_users()

# -------------------------
# CITY PROFILES
# -------------------------
CITY_PROFILES = {
    "Delhi": {"base_power": 2800, "peak_power": 4200, "variance": 400, "lat": 28.6139, "lon": 77.2090},
    "Mumbai": {"base_power": 2400, "peak_power": 3800, "variance": 350, "lat": 19.0760, "lon": 72.8777},
    "Bangalore": {"base_power": 2600, "peak_power": 4100, "variance": 380, "lat": 12.9716, "lon": 77.5946},
    "Chennai": {"base_power": 2200, "peak_power": 3600, "variance": 320, "lat": 13.0827, "lon": 80.2707},
    "Kolkata": {"base_power": 2500, "peak_power": 3900, "variance": 370, "lat": 22.5726, "lon": 88.3639},
    "Hyderabad": {"base_power": 2550, "peak_power": 3980, "variance": 365, "lat": 17.3850, "lon": 78.4867},
    "Pune": {"base_power": 2480, "peak_power": 3890, "variance": 350, "lat": 18.5204, "lon": 73.8567},
    "Ahmedabad": {"base_power": 2450, "peak_power": 3840, "variance": 340, "lat": 23.0225, "lon": 72.5714},
    "Jaipur": {"base_power": 2380, "peak_power": 3750, "variance": 330, "lat": 26.9124, "lon": 75.7873},
    "Lucknow": {"base_power": 2360, "peak_power": 3700, "variance": 325, "lat": 26.8467, "lon": 80.9462},
    "Kanpur": {"base_power": 2340, "peak_power": 3660, "variance": 320, "lat": 26.4499, "lon": 80.3319},
    "Nagpur": {"base_power": 2320, "peak_power": 3620, "variance": 315, "lat": 21.1458, "lon": 79.0882},
    "Indore": {"base_power": 2300, "peak_power": 3600, "variance": 310, "lat": 22.7196, "lon": 75.8577},
    "Bhopal": {"base_power": 2280, "peak_power": 3560, "variance": 305, "lat": 23.2599, "lon": 77.4126},
    "Patna": {"base_power": 2260, "peak_power": 3520, "variance": 300, "lat": 25.5941, "lon": 85.1376},
    "Surat": {"base_power": 2420, "peak_power": 3800, "variance": 335, "lat": 21.1702, "lon": 72.8311},
    "Vadodara": {"base_power": 2240, "peak_power": 3500, "variance": 295, "lat": 22.3072, "lon": 73.1812},
    "Rajkot": {"base_power": 2200, "peak_power": 3440, "variance": 285, "lat": 22.3039, "lon": 70.8022},
    "Nashik": {"base_power": 2190, "peak_power": 3420, "variance": 285, "lat": 19.9975, "lon": 73.7898},
    "Aurangabad": {"base_power": 2170, "peak_power": 3380, "variance": 280, "lat": 19.8762, "lon": 75.3433},
    "Visakhapatnam": {"base_power": 2350, "peak_power": 3700, "variance": 325, "lat": 17.6868, "lon": 83.2185},
    "Vijayawada": {"base_power": 2210, "peak_power": 3460, "variance": 290, "lat": 16.5062, "lon": 80.6480},
    "Coimbatore": {"base_power": 2230, "peak_power": 3490, "variance": 295, "lat": 11.0168, "lon": 76.9558},
    "Madurai": {"base_power": 2140, "peak_power": 3340, "variance": 275, "lat": 9.9252, "lon": 78.1198},
    "Salem": {"base_power": 2100, "peak_power": 3280, "variance": 270, "lat": 11.6643, "lon": 78.1460},
    "Tiruchirappalli": {"base_power": 2120, "peak_power": 3310, "variance": 272, "lat": 10.7905, "lon": 78.7047},
    "Kochi": {"base_power": 2180, "peak_power": 3400, "variance": 285, "lat": 9.9312, "lon": 76.2673},
    "Thiruvananthapuram": {"base_power": 2160, "peak_power": 3370, "variance": 280, "lat": 8.5241, "lon": 76.9366},
    "Mysore": {"base_power": 2080, "peak_power": 3250, "variance": 265, "lat": 12.2958, "lon": 76.6394},
    "Mangalore": {"base_power": 2090, "peak_power": 3270, "variance": 268, "lat": 12.9141, "lon": 74.8560},
    "Bhubaneswar": {"base_power": 2200, "peak_power": 3450, "variance": 290, "lat": 20.2961, "lon": 85.8245},
    "Cuttack": {"base_power": 2140, "peak_power": 3350, "variance": 278, "lat": 20.4625, "lon": 85.8828},
    "Ranchi": {"base_power": 2110, "peak_power": 3300, "variance": 272, "lat": 23.3441, "lon": 85.3096},
    "Jamshedpur": {"base_power": 2170, "peak_power": 3390, "variance": 282, "lat": 22.8046, "lon": 86.2029},
    "Guwahati": {"base_power": 2130, "peak_power": 3330, "variance": 276, "lat": 26.1445, "lon": 91.7362},
    "Noida": {"base_power": 2400, "peak_power": 3760, "variance": 330, "lat": 28.5355, "lon": 77.3910},
    "Gurgaon": {"base_power": 2460, "peak_power": 3850, "variance": 340, "lat": 28.4595, "lon": 77.0266},
    "Faridabad": {"base_power": 2310, "peak_power": 3620, "variance": 312, "lat": 28.4089, "lon": 77.3178},
    "Amritsar": {"base_power": 2180, "peak_power": 3410, "variance": 286, "lat": 31.6340, "lon": 74.8723},
    "Ludhiana": {"base_power": 2270, "peak_power": 3540, "variance": 300, "lat": 30.9010, "lon": 75.8573},
    "Chandigarh": {"base_power": 2220, "peak_power": 3480, "variance": 292, "lat": 30.7333, "lon": 76.7794}
}

ZONE_BLUEPRINTS = [
    {"slug": "central", "name": "Central Grid", "lat_offset": 0.00, "lon_offset": 0.00, "load_bias": 0.10},
    {"slug": "north", "name": "North Residential", "lat_offset": 0.16, "lon_offset": -0.08, "load_bias": -0.04},
    {"slug": "industrial", "name": "Industrial Belt", "lat_offset": -0.12, "lon_offset": 0.14, "load_bias": 0.18},
]

METER_BLUEPRINTS = [
    {"suffix": "M001", "consumer_type": "Residential", "name_template": "Household Cluster A", "load_bias": -0.06},
    {"suffix": "M002", "consumer_type": "Commercial", "name_template": "Retail Feed", "load_bias": 0.05},
    {"suffix": "M003", "consumer_type": "Industrial", "name_template": "Industrial Consumer", "load_bias": 0.14},
    {"suffix": "M004", "consumer_type": "Public Utility", "name_template": "Utility Services", "load_bias": 0.02},
]


def normalize_city_name(city_name):
    return " ".join(part.capitalize() for part in city_name.strip().split())


def build_zone_id(city_name, zone_slug):
    normalized = city_name.lower().replace(" ", "-")
    return f"{normalized}-{zone_slug}"


def generate_city_profile(city_name, lat=None, lon=None):
    if city_name in CITY_PROFILES:
        return CITY_PROFILES[city_name]

    lat = float(lat) if lat is not None else 20.5
    lon = float(lon) if lon is not None else 78.9
    latitude_factor = min(abs(lat) / 35.0, 1.0)
    coastal_factor = min(abs(lon - 80.0) / 25.0, 1.0)

    base_power = round(2100 + (latitude_factor * 550) + (coastal_factor * 250))
    variance = round(260 + (latitude_factor * 120) + (coastal_factor * 60))
    peak_power = round(base_power * 1.45)

    profile = {
        "base_power": base_power,
        "peak_power": peak_power,
        "variance": variance,
        "lat": lat,
        "lon": lon,
    }
    CITY_PROFILES[city_name] = profile
    return profile


def ensure_city_profile(city_name, lat=None, lon=None):
    profile = CITY_PROFILES.get(city_name)
    if profile:
        if lat is not None and lon is not None:
            profile["lat"] = float(lat)
            profile["lon"] = float(lon)
        return profile
    return generate_city_profile(city_name, lat=lat, lon=lon)


def get_city_zones(city_name, lat=None, lon=None):
    profile = ensure_city_profile(city_name, lat=lat, lon=lon)
    zones = []
    for blueprint in ZONE_BLUEPRINTS:
        zones.append({
            "zone_id": build_zone_id(city_name, blueprint["slug"]),
            "zone_name": blueprint["name"],
            "lat": round(float(profile["lat"]) + blueprint["lat_offset"], 6),
            "lon": round(float(profile["lon"]) + blueprint["lon_offset"], 6),
            "load_bias": blueprint["load_bias"],
        })
    return zones


def get_zone_meters(city_name, zone):
    meters = []
    zone_slug = zone["zone_id"].split("-")[-1]
    for blueprint in METER_BLUEPRINTS:
        meters.append({
            "meter_id": f"{zone['zone_id']}-{blueprint['suffix']}",
            "consumer_name": f"{blueprint['name_template']} {zone_slug.title()}",
            "consumer_type": blueprint["consumer_type"],
            "meter_bias": blueprint["load_bias"],
        })
    return meters


def seed_default_cities():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT meter_id FROM thefts WHERE meter_id IS NOT NULL")
    existing_meter_ids = {row[0] for row in cur.fetchall()}

    for city, profile in CITY_PROFILES.items():
        for zone in get_city_zones(city, lat=profile["lat"], lon=profile["lon"]):
            for meter in get_zone_meters(city, zone):
                if meter["meter_id"] in existing_meter_ids:
                    continue
                voltage = 220.0
                power = round(profile["base_power"] * (1 + zone["load_bias"] + meter["meter_bias"]))
                current = round(power / voltage, 2)
                cur.execute(
                    """
                    INSERT INTO thefts (city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        city,
                        voltage,
                        current,
                        power,
                        "NORMAL",
                        zone["lat"],
                        zone["lon"],
                        zone["zone_id"],
                        zone["zone_name"],
                        meter["meter_id"],
                        meter["consumer_name"],
                        meter["consumer_type"],
                    ),
                )
    con.commit()

    con.close()


seed_default_cities()


def get_realistic_power(city_name, zone=None):
    profile = ensure_city_profile(city_name)
    hour = datetime.now().hour
    if (8 <= hour <= 11) or (18 <= hour <= 22):
        power = profile["peak_power"] + random.randint(-profile["variance"], profile["variance"])
    elif 2 <= hour <= 5:
        power = profile["base_power"] * 0.6 + random.randint(-profile["variance"]//2, profile["variance"]//2)
    else:
        power = profile["base_power"] + random.randint(-profile["variance"], profile["variance"])
    if zone:
        power += profile["variance"] * float(zone.get("load_bias", 0))
    return round(max(500, min(5000, power)), 2)


def get_live_data_payload():
    now = time.time()
    cached_data = LIVE_DATA_CACHE["data"]
    if cached_data and (now - LIVE_DATA_CACHE["timestamp"]) < LIVE_CACHE_SECONDS:
        return cached_data

    data = compute_live_data()
    LIVE_DATA_CACHE["timestamp"] = now
    LIVE_DATA_CACHE["data"] = data
    return data


def fetch_user_by_username(username):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, username, full_name, password_hash, role
        FROM users
        WHERE username = ?
        """,
        (username,),
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "full_name": row[2],
        "password_hash": row[3],
        "role": row[4],
    }


def fetch_users(role=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    if role:
        cur.execute(
            """
            SELECT id, username, full_name, role, created_at
            FROM users
            WHERE role = ?
            ORDER BY full_name
            """,
            (role,),
        )
    else:
        cur.execute(
            """
            SELECT id, username, full_name, role, created_at
            FROM users
            ORDER BY role, full_name
            """
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": row[0],
            "username": row[1],
            "full_name": row[2],
            "role": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]


def create_user_record(username, full_name, password, role):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO users (username, full_name, password_hash, role)
        VALUES (?, ?, ?, ?)
        """,
        (username, full_name, generate_password_hash(password), role),
    )
    user_id = cur.lastrowid
    con.commit()
    con.close()
    return user_id


def create_notification(title, message, category, severity="info", related_case_id=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO notifications (title, message, category, severity, related_case_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, message, category, severity, related_case_id),
    )
    notification_id = cur.lastrowid
    con.commit()
    con.close()
    return notification_id


def log_audit_event(action, entity_type, summary, entity_id=None, details=None, actor=None):
    actor_username = None
    actor_role = None
    if actor:
        actor_username = actor.get("username")
        actor_role = actor.get("role")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO audit_events (action, entity_type, entity_id, actor_username, actor_role, summary, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            entity_type,
            str(entity_id) if entity_id is not None else None,
            actor_username,
            actor_role,
            summary,
            details,
        ),
    )
    audit_id = cur.lastrowid
    con.commit()
    con.close()
    return audit_id


def fetch_notifications(limit=30, unread_only=False):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    if unread_only:
        cur.execute(
            """
            SELECT id, title, message, category, severity, related_case_id, is_read, created_at
            FROM notifications
            WHERE is_read = 0
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT id, title, message, category, severity, related_case_id, is_read, created_at
            FROM notifications
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "message": row[2],
            "category": row[3],
            "severity": row[4],
            "related_case_id": row[5],
            "is_read": bool(row[6]),
            "created_at": row[7],
        }
        for row in rows
    ]


def mark_notification_read(notification_id):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        """,
        (notification_id,),
    )
    changed = cur.rowcount > 0
    con.commit()
    con.close()
    return changed


def mark_all_notifications_read():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE is_read = 0
        """
    )
    changed = cur.rowcount
    con.commit()
    con.close()
    return changed


def get_notification_summary():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications")
    total_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
    unread_count = cur.fetchone()[0]
    cur.execute(
        """
        SELECT id, title, severity, created_at
        FROM notifications
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 1
        """
    )
    latest = cur.fetchone()
    con.close()
    return {
        "total_count": total_count,
        "unread_count": unread_count,
        "latest": {
            "id": latest[0],
            "title": latest[1],
            "severity": latest[2],
            "created_at": latest[3],
        } if latest else None,
    }


def fetch_audit_events(limit=25):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, action, entity_type, entity_id, actor_username, actor_role, summary, details, created_at
        FROM audit_events
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": row[0],
            "action": row[1],
            "entity_type": row[2],
            "entity_id": row[3],
            "actor_username": row[4],
            "actor_role": row[5],
            "summary": row[6],
            "details": row[7],
            "created_at": row[8],
        }
        for row in rows
    ]


def is_alert_acknowledged(city, zone_id, reading_timestamp):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT 1
        FROM alert_acknowledgements
        WHERE city = ?
          AND COALESCE(zone_id, '') = COALESCE(?, '')
          AND reading_timestamp = ?
        LIMIT 1
        """,
        (city, zone_id, reading_timestamp),
    )
    row = cur.fetchone()
    con.close()
    return bool(row)


def record_alert_acknowledgement(city, zone_id, reading_timestamp, actor=None, note=None):
    return record_alert_workflow_action(
        action="acknowledged",
        city=city,
        zone_id=zone_id,
        reading_timestamp=reading_timestamp,
        actor=actor,
        note=note,
    )


def fetch_alert_workflow_action(city, zone_id, reading_timestamp):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT action, case_id, acknowledged_by, acknowledged_role, note, acknowledged_at
        FROM alert_acknowledgements
        WHERE city = ?
          AND COALESCE(zone_id, '') = COALESCE(?, '')
          AND reading_timestamp = ?
        LIMIT 1
        """,
        (normalize_city_name(city), (zone_id or "").strip(), str(reading_timestamp)),
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "action": row[0],
        "case_id": row[1],
        "acknowledged_by": row[2],
        "acknowledged_role": row[3],
        "note": row[4],
        "acknowledged_at": row[5],
    }


def record_alert_workflow_action(action, city, zone_id, reading_timestamp, actor=None, note=None, case_id=None):
    actor_username = actor.get("username") if actor else None
    actor_role = actor.get("role") if actor else None
    zone_key = (zone_id or "").strip()
    city_key = normalize_city_name(city)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO alert_acknowledgements
            (city, zone_id, reading_timestamp, action, case_id, acknowledged_by, acknowledged_role, note, acknowledged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(city, zone_id, reading_timestamp) DO UPDATE SET
            action = excluded.action,
            case_id = excluded.case_id,
            acknowledged_by = excluded.acknowledged_by,
            acknowledged_role = excluded.acknowledged_role,
            note = excluded.note,
            acknowledged_at = CURRENT_TIMESTAMP
        """,
        (
            city_key,
            zone_key,
            str(reading_timestamp),
            action,
            case_id,
            actor_username,
            actor_role,
            note,
        ),
    )
    changed = cur.rowcount > 0
    con.commit()
    con.close()
    return changed


def is_alert_hidden(city, zone_id, reading_timestamp):
    workflow = fetch_alert_workflow_action(city, zone_id, reading_timestamp)
    return bool(workflow and workflow.get("action") in {"acknowledged", "escalated", "resolved"})


def create_database_backup_file():
    if not os.path.exists(DB_PATH):
        init_db()

    fd, backup_path = tempfile.mkstemp(prefix="smarttheft_backup_", suffix=".sqlite")
    os.close(fd)

    source = sqlite3.connect(DB_PATH)
    destination = None
    try:
        try:
            destination = sqlite3.connect(backup_path)
            source.backup(destination)
        except sqlite3.OperationalError:
            if destination is not None:
                destination.close()
                destination = None
            with open(backup_path, "w", encoding="utf-8") as handle:
                for line in source.iterdump():
                    handle.write(f"{line}\n")
    finally:
        if destination is not None:
            destination.close()
        source.close()

    return backup_path


def is_sqlite_database_file(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def apply_database_restore(source_path, destination_path):
    source_is_sqlite = is_sqlite_database_file(source_path)
    source = sqlite3.connect(source_path) if source_is_sqlite else None
    destination = sqlite3.connect(destination_path)
    try:
        if source_is_sqlite:
            source.backup(destination)
        else:
            destination.execute("PRAGMA foreign_keys = OFF")
            objects = destination.execute(
                """
                SELECT type, name FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY CASE type
                    WHEN 'table' THEN 0
                    WHEN 'view' THEN 1
                    WHEN 'index' THEN 2
                    WHEN 'trigger' THEN 3
                    ELSE 4
                END, name
                """
            ).fetchall()
            for object_type, object_name in objects:
                try:
                    if object_type == "table":
                        destination.execute(f'DROP TABLE IF EXISTS "{object_name}"')
                    elif object_type == "view":
                        destination.execute(f'DROP VIEW IF EXISTS "{object_name}"')
                    elif object_type == "trigger":
                        destination.execute(f'DROP TRIGGER IF EXISTS "{object_name}"')
                    elif object_type == "index":
                        destination.execute(f'DROP INDEX IF EXISTS "{object_name}"')
                except sqlite3.OperationalError:
                    continue
            with open(source_path, "r", encoding="utf-8", errors="ignore") as handle:
                sql_text = handle.read()
            destination.executescript(sql_text)
        destination.commit()
        init_db()
    finally:
        if source is not None:
            source.close()
        destination.close()


def restore_database_from_file(source_path):
    if not os.path.exists(source_path):
        raise FileNotFoundError("Backup file not found.")

    current_backup_path = create_database_backup_file()
    try:
        apply_database_restore(source_path, DB_PATH)
    except Exception:
        try:
            apply_database_restore(current_backup_path, DB_PATH)
        finally:
            pass
        raise
    finally:
        try:
            os.remove(current_backup_path)
        except OSError:
            pass


def get_current_user():
    username = session.get("username")
    if not username:
        return None
    return fetch_user_by_username(username)


def login_required(route_handler):
    @wraps(route_handler)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login_page", next=request.path))
        return route_handler(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    def decorator(route_handler):
        @wraps(route_handler)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required."}), 401
                return redirect(url_for("login_page", next=request.path))
            if user["role"] not in allowed_roles:
                if request.path.startswith("/api/"):
                    return jsonify({
                        "error": "You do not have permission to perform this action.",
                        "required_roles": list(allowed_roles),
                    }), 403
                return redirect(url_for("home"))
            return route_handler(*args, **kwargs)

        return wrapper

    return decorator


@app.context_processor
def inject_auth_context():
    user = get_current_user()
    return {
        "current_user": user,
        "current_role": user["role"] if user else None,
    }

# -------------------------
# ROUTES
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if session.get("username"):
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = fetch_user_by_username(username)

        if user and check_password_hash(user["password_hash"], password):
            session["username"] = user["username"]
            session["role"] = user["role"]
            log_audit_event(
                action="login",
                entity_type="auth",
                summary=f"{user['username']} signed in.",
                entity_id=user["username"],
                actor=user,
            )
            next_url = request.args.get("next") or url_for("home")
            return redirect(next_url)

        error = "Invalid username or password."

    return render_template("login.html", error=error, demo_users=DEFAULT_USERS)


@app.route("/logout")
def logout():
    actor = get_current_user()
    if actor:
        log_audit_event(
            action="logout",
            entity_type="auth",
            summary=f"{actor['username']} signed out.",
            entity_id=actor["username"],
            actor=actor,
        )
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/api/session")
@login_required
def session_details():
    user = get_current_user()
    return jsonify({
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
    })


@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/map")
@login_required
def map_page():
    return render_template("map.html")

@app.route("/earth")
@login_required
def earth_page():
    return render_template("earth.html")


@app.route("/alerts")
@login_required
def alerts_page():
    return render_template("alerts.html")


@app.route("/cases")
@login_required
def cases_page():
    return render_template("cases.html")


@app.route("/monitoring")
@login_required
def monitoring_page():
    return render_template("monitoring.html")


@app.route("/admin")
@role_required("admin")
def admin_page():
    return render_template("admin.html")

@app.route("/api/cesium-token")
@login_required
def get_cesium_token():
    return jsonify({"token": CESIUM_ION_TOKEN})

# -------------------------
# AI PREDICTION ENGINE
# -------------------------
def fetch_city_history(city_name, limit=12):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT power FROM thefts
        WHERE city = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (city_name, limit),
    )
    rows = cur.fetchall()
    con.close()
    return [float(row[0]) for row in rows]


def build_city_features(power_val, city_name):
    history = fetch_city_history(city_name)
    samples = history + [float(power_val)]

    if not samples:
        samples = [float(power_val)]

    avg_usage = float(np.mean(samples))
    max_usage = float(np.max(samples))
    variance = float(np.var(samples))
    return build_inference_features(avg_usage, max_usage, variance)


def run_ai_prediction(power_val, city_name):
    loaded_model = get_model()
    loaded_scaler = get_scaler()
    if loaded_model is None or loaded_scaler is None:
        return "THEFT" if power_val > 3500 else "NORMAL", 0.0

    features = build_city_features(power_val, city_name)
    scaled_feat = loaded_scaler.transform(features)
    prob = loaded_model.predict_proba(scaled_feat)[0][1]

    status = "THEFT" if prob > DEFAULT_THRESHOLD else "NORMAL"
    return status, round(prob * 100, 2)


def build_prediction_explanations(avg_usage, max_usage, variance, city_name=None):
    avg_usage = float(avg_usage)
    max_usage = float(max_usage)
    variance = float(variance)
    intensity = max_usage / max(avg_usage, 0.1)
    explanations = []

    if city_name:
        profile = ensure_city_profile(city_name)
        base_power = float(profile["base_power"])
        peak_power = float(profile["peak_power"])
        expected_variance = float(profile["variance"])

        if avg_usage >= base_power * 1.15:
            explanations.append({
                "label": "Above baseline",
                "value": f"{avg_usage:.0f} W vs {base_power:.0f} W",
                "tone": "theft" if avg_usage >= base_power * 1.3 else "watch",
                "note": "Average usage is higher than the city baseline.",
            })
        if max_usage >= peak_power * 1.1:
            explanations.append({
                "label": "Peak spike",
                "value": f"{max_usage:.0f} W peak",
                "tone": "theft",
                "note": "Maximum usage is well above the expected peak.",
            })
        if variance >= expected_variance * 1.35:
            explanations.append({
                "label": "High volatility",
                "value": f"{variance:.2f}",
                "tone": "watch" if variance < expected_variance * 1.7 else "theft",
                "note": "The meter is fluctuating more than normal.",
            })

    if intensity >= 1.35:
        explanations.append({
            "label": "Usage intensity",
            "value": f"{intensity:.2f}x",
            "tone": "theft" if intensity >= 1.6 else "watch",
            "note": "Peak demand is far above average demand.",
        })
    elif intensity <= 0.8:
        explanations.append({
            "label": "Stable profile",
            "value": f"{intensity:.2f}x",
            "tone": "normal",
            "note": "Peak and average usage are staying close together.",
        })

    if not explanations:
        explanations.append({
            "label": "Model match",
            "value": "Balanced pattern",
            "tone": "normal",
            "note": "Nothing strongly abnormal was detected in the feature mix.",
        })

    return explanations[:4]


def build_prediction_reading_profile(avg_usage, max_usage, variance, status, city_name=None):
    avg_usage = float(avg_usage)
    max_usage = float(max_usage)
    variance = float(variance)
    intensity = max_usage / max(avg_usage, 0.1)

    if city_name:
        profile = ensure_city_profile(city_name)
        base_power = float(profile["base_power"])
        peak_power = float(profile["peak_power"])
        expected_variance = float(profile["variance"])
    else:
        base_power = max(avg_usage, 1.0)
        peak_power = max(max_usage, base_power)
        expected_variance = max(variance, 1.0)

    if status == "THEFT":
        if avg_usage >= base_power * 1.3 and max_usage >= peak_power * 1.1:
            return {
                "type": "baseline overload",
                "label": "Baseline overload",
                "summary": "The reading is far above the city baseline and peak expectation, so the model reads it as a likely theft-style overload.",
                "tone": "theft",
            }
        if intensity >= 1.6:
            return {
                "type": "spike-heavy pattern",
                "label": "Spike-heavy pattern",
                "summary": "The peak usage is much higher than the average, which makes the pattern look like a sudden theft-style spike.",
                "tone": "theft",
            }
        if variance >= expected_variance * 1.7:
            return {
                "type": "volatile pattern",
                "label": "Volatile pattern",
                "summary": "The reading is swinging more than the city usually does, and that volatility pushed the model toward theft.",
                "tone": "watch",
            }
        return {
            "type": "mixed risk pattern",
            "label": "Mixed risk pattern",
            "summary": "Several signals are elevated at once, so the model reads this as suspicious even without one single extreme spike.",
            "tone": "watch",
        }

    if avg_usage <= base_power * 0.85 and intensity <= 0.9 and variance <= expected_variance * 1.1:
        return {
            "type": "stable consumption",
            "label": "Stable consumption",
            "summary": "The reading stays close to the expected city baseline, so the model reads it as normal behavior.",
            "tone": "normal",
        }

    if variance >= expected_variance * 1.3:
        return {
            "type": "watch pattern",
            "label": "Watch pattern",
            "summary": "The usage is still below theft threshold, but the fluctuations are noticeable enough to keep an eye on it.",
            "tone": "watch",
        }

    if intensity >= 1.2:
        return {
            "type": "elevated normal pattern",
            "label": "Elevated normal pattern",
            "summary": "The reading is a little high compared with the baseline, but it still looks more like normal heavy use than theft.",
            "tone": "watch",
        }

    return {
        "type": "balanced pattern",
        "label": "Balanced pattern",
        "summary": "Nothing in the reading strongly breaks the city pattern, so the model treats it as normal.",
        "tone": "normal",
    }


def is_wide_meter_csv(frame):
    if frame is None or frame.empty:
        return False

    available_columns = [column for column in frame.columns if str(column).upper() not in BATCH_FEATURE_COLUMNS]
    if {"CONS_NO", "FLAG"}.intersection({str(column).upper() for column in frame.columns}):
        reading_columns = [column for column in frame.columns if str(column).upper() not in BATCH_RAW_EXCLUDED_COLUMNS]
        return len(reading_columns) > 0

    date_like_columns = [column for column in frame.columns if any(char.isdigit() for char in str(column))]
    return len(date_like_columns) >= 10 and len(available_columns) > 0


def convert_wide_meter_csv_to_features(frame):
    cleaned = clean_wide_meter_dataset(frame)
    reading_columns = [column for column in cleaned.columns if str(column).upper() not in BATCH_RAW_EXCLUDED_COLUMNS]

    if not reading_columns:
        raise ValueError("No meter reading columns were found in the uploaded CSV.")

    numeric_readings = cleaned[reading_columns].apply(pd.to_numeric, errors="coerce")
    avg_series = numeric_readings.mean(axis=1)
    max_series = numeric_readings.max(axis=1)
    var_series = numeric_readings.var(axis=1)

    feature_frame = pd.DataFrame({
        "avg_daily_consumption": avg_series,
        "max_daily_consumption": max_series,
        "consumption_variance": var_series,
    })

    if "CONS_NO" in cleaned.columns:
        meter_ids = cleaned["CONS_NO"].astype(str).str.strip()
        feature_frame["source_id"] = meter_ids
        feature_frame["city"] = meter_ids.map(lambda value: f"Meter {value}" if value else "Batch Sample")
    else:
        feature_frame["city"] = "Batch Sample"
        feature_frame["source_id"] = "Batch Sample"

    feature_frame = feature_frame.dropna(subset=["avg_daily_consumption", "max_daily_consumption", "consumption_variance"], how="any")
    feature_frame = feature_frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["avg_daily_consumption", "max_daily_consumption", "consumption_variance"], how="any")

    return feature_frame, len(frame), len(cleaned)


def predict_batch_rows(frame):
    results = []
    invalid_rows = []
    loaded_model = get_model()
    loaded_scaler = get_scaler()

    if {"avg_daily_consumption", "max_daily_consumption", "consumption_variance"}.issubset(frame.columns):
        source_frame = frame.copy()
    elif is_wide_meter_csv(frame):
        source_frame, raw_rows, cleaned_rows = convert_wide_meter_csv_to_features(frame)
    else:
        missing_columns = [column for column in BATCH_FEATURE_COLUMNS if column not in frame.columns]
        raise KeyError({
            "missing_columns": missing_columns,
            "required_columns": sorted(BATCH_FEATURE_COLUMNS),
        })

    if source_frame.empty:
        return results, invalid_rows, "wide" if is_wide_meter_csv(frame) else "engineered"

    for index, row in source_frame.iterrows():
        try:
            avg_usage = float(row["avg_daily_consumption"])
            max_usage = float(row["max_daily_consumption"])
            variance = float(row["consumption_variance"])
        except (TypeError, ValueError):
            invalid_rows.append({
                "row": int(index) + 2,
                "error": "Feature columns must contain numeric values.",
            })
            continue

        city_name = normalize_city_name(str(row.get("city", "Batch Sample")).strip() or "Batch Sample")
        features = build_inference_features(avg_usage, max_usage, variance)
        if loaded_model is None or loaded_scaler is None:
            probability = 1.0 if avg_usage > 3500 or max_usage > 3500 else 0.0
        else:
            scaled_features = loaded_scaler.transform(features)
            probability = float(loaded_model.predict_proba(scaled_features)[0][1])
        status = "THEFT" if probability > DEFAULT_THRESHOLD else "NORMAL"
        usage_intensity = float(features.iloc[0]["usage_intensity"])
        reading_profile = build_prediction_reading_profile(avg_usage, max_usage, variance, status, city_name=city_name)

        results.append({
            "row": int(index) + 2,
            "city": city_name,
            "source_id": str(row.get("source_id", city_name)),
            "status": status,
            "risk_score": round(probability * 100, 2),
            "avg_daily_consumption": round(avg_usage, 2),
            "max_daily_consumption": round(max_usage, 2),
            "consumption_variance": round(variance, 2),
            "usage_intensity": round(usage_intensity, 2),
            "reading_profile": reading_profile,
        })

    return results, invalid_rows, "wide" if is_wide_meter_csv(frame) else "engineered"


def derive_incident_metadata(status, risk_score, power_val, city_name):
    profile = ensure_city_profile(city_name)
    peak_power = float(profile["peak_power"])
    risk_val = float(risk_score)
    overload_ratio = power_val / max(peak_power, 1.0)

    if status == "NORMAL":
        if risk_val >= 30:
            severity = "watch"
            recommended_action = "Monitor"
            action_reason = "Risk remains below theft threshold but is elevated enough to watch closely."
        else:
            severity = "normal"
            recommended_action = "No Action"
            action_reason = "Usage is within the expected operating range for this city profile."
    else:
        if risk_val >= 75 or overload_ratio >= 1.18:
            severity = "critical"
            recommended_action = "Urgent Dispatch"
            action_reason = "Very high theft probability or extreme overload requires immediate field verification."
        elif risk_val >= 55 or overload_ratio >= 1.08:
            severity = "high"
            recommended_action = "Inspect"
            action_reason = "The pattern is suspicious enough to justify meter inspection and local verification."
        else:
            severity = "medium"
            recommended_action = "Monitor"
            action_reason = "The model flagged this location, but another observation cycle is recommended."

    return {
        "severity": severity,
        "recommended_action": recommended_action,
        "action_reason": action_reason,
        "peak_reference_power": round(peak_power, 2),
        "overload_ratio": round(overload_ratio, 3),
    }


def notify_theft(city_name, risk_score, power_val):
    if not SMS_ALERTS_ENABLED:
        return
    if TWILIO_SID == 'YOUR_SID' or TWILIO_AUTH == 'YOUR_AUTH':
        return

    try:
        client.messages.create(
            body=f"AI ALERT: {city_name}\nRisk Score: {risk_score}%\nPower: {power_val}W",
            from_=TWILIO_FROM,
            to=TWILIO_TO
        )
    except Exception:
        pass


def get_city_coordinates(city_name):
    profile = CITY_PROFILES.get(city_name)
    if profile:
        return profile["lat"], profile["lon"]

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"city": city_name, "country": "India", "format": "json", "limit": 1},
            headers={"User-Agent": "smart-theft-app"},
            timeout=5,
        )
        response.raise_for_status()
        results = response.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        return None, None

    return None, None


def upsert_city_reading(
    city_name,
    lat,
    lon,
    voltage,
    current,
    power,
    status,
    zone_id=None,
    zone_name=None,
    meter_id=None,
    consumer_name=None,
    consumer_type=None,
):
    ensure_city_profile(city_name, lat=lat, lon=lon)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO thefts (city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            city_name,
            float(voltage),
            float(current),
            float(power),
            status,
            float(lat),
            float(lon),
            zone_id,
            zone_name,
            meter_id,
            consumer_name,
            consumer_type,
        ),
    )
    con.commit()
    con.close()


def get_monitored_locations():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT city, lat, lon, zone_id, zone_name
        FROM thefts
        WHERE id IN (
            SELECT MAX(id)
            FROM thefts
            GROUP BY COALESCE(zone_id, LOWER(city))
        )
        ORDER BY city, zone_name
        """
    )
    locations = cur.fetchall()
    con.close()
    return locations


def get_latest_monitored_readings():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT city, voltage, current, power, status, lat, lon, zone_id, zone_name, timestamp
        FROM thefts
        WHERE id IN (
            SELECT MAX(id)
            FROM thefts
            GROUP BY COALESCE(zone_id, LOWER(city))
        )
        ORDER BY city, zone_name
        """
    )
    rows = cur.fetchall()
    con.close()
    return rows


def fetch_city_inventory():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT city, zone_name, COUNT(*) as readings, MAX(timestamp) as last_seen
        FROM thefts
        GROUP BY city, COALESCE(zone_id, LOWER(city))
        ORDER BY city, zone_name
        """
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "city": row[0],
            "zone_name": row[1],
            "readings": int(row[2]),
            "last_seen": row[3],
        }
        for row in rows
    ]


def fetch_city_history_rows(city_name, limit=12, zone_id=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    if zone_id:
        cur.execute(
            """
            SELECT city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type, timestamp
            FROM thefts
            WHERE zone_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (zone_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type, timestamp
            FROM thefts
            WHERE LOWER(city) = LOWER(?)
            ORDER BY id DESC
            LIMIT ?
            """,
            (city_name, limit),
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "city": row[0],
            "voltage": float(row[1]),
            "current": float(row[2]),
            "power": float(row[3]),
            "status": row[4],
            "lat": float(row[5]),
            "lon": float(row[6]),
            "zone_id": row[7],
            "zone_name": row[8],
            "meter_id": row[9],
            "consumer_name": row[10],
            "consumer_type": row[11],
            "timestamp": row[12],
        }
        for row in rows
    ]


def fetch_zone_consumers(zone_id, limit=12):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT meter_id, consumer_name, consumer_type, AVG(power) as avg_power, MAX(power) as max_power, MAX(timestamp) as last_seen
        FROM thefts
        WHERE zone_id = ?
        GROUP BY meter_id, consumer_name, consumer_type
        ORDER BY max_power DESC
        LIMIT ?
        """,
        (zone_id, limit),
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "meter_id": row[0],
            "consumer_name": row[1],
            "consumer_type": row[2],
            "avg_power": round(float(row[3]), 2),
            "max_power": round(float(row[4]), 2),
            "last_seen": row[5],
        }
        for row in rows
    ]


def fetch_cases(status=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    if status:
        cur.execute(
            """
            SELECT id, city, zone_id, zone_name, location_label, severity, status, recommended_action, assignee, notes, latest_risk_score, created_at, updated_at
            FROM cases
            WHERE status = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (status,),
        )
    else:
        cur.execute(
            """
            SELECT id, city, zone_id, zone_name, location_label, severity, status, recommended_action, assignee, notes, latest_risk_score, created_at, updated_at
            FROM cases
            ORDER BY updated_at DESC, id DESC
            """
        )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": row[0],
            "city": row[1],
            "zone_id": row[2],
            "zone_name": row[3],
            "location_label": row[4],
            "severity": row[5],
            "status": row[6],
            "recommended_action": row[7],
            "assignee": row[8],
            "notes": row[9],
            "latest_risk_score": row[10],
            "created_at": row[11],
            "updated_at": row[12],
        }
        for row in rows
    ]


def auto_assign_case(severity):
    operators = fetch_users(role="operator")
    if not operators:
        return None

    active_cases = [case for case in fetch_cases() if case["status"] in {"open", "in_progress"}]
    load_by_username = {item["username"]: 0 for item in operators}
    for case in active_cases:
        if case["assignee"] in load_by_username:
            load_by_username[case["assignee"]] += 1

    ranked = sorted(
        operators,
        key=lambda item: (
            load_by_username.get(item["username"], 0),
            item["full_name"].lower(),
        ),
    )
    return ranked[0]["username"] if ranked else None


def append_case_event(case_id, event_type, summary, details=None, actor=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO case_events (case_id, event_type, actor_username, actor_role, summary, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            event_type,
            actor["username"] if actor else None,
            actor["role"] if actor else None,
            summary,
            details,
        ),
    )
    con.commit()
    con.close()


def fetch_case_timeline(case_id):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT id, event_type, actor_username, actor_role, summary, details, created_at
        FROM case_events
        WHERE case_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (case_id,),
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": row[0],
            "event_type": row[1],
            "actor_username": row[2],
            "actor_role": row[3],
            "summary": row[4],
            "details": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def create_zone_polygon(zone):
    lat = float(zone["lat"])
    lon = float(zone["lon"])
    lat_delta = 0.09
    lon_delta = 0.11
    coordinates = [[
        [lon - lon_delta, lat - lat_delta],
        [lon + lon_delta, lat - lat_delta],
        [lon + lon_delta, lat + lat_delta],
        [lon - lon_delta, lat + lat_delta],
        [lon - lon_delta, lat - lat_delta],
    ]]
    return {
        "type": "Feature",
        "properties": {
            "zone_id": zone["zone_id"],
            "zone_name": zone["zone_name"],
            "city": zone["city"],
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": coordinates,
        },
    }


def build_zone_geojson():
    features = []
    for city, profile in CITY_PROFILES.items():
        for zone in get_city_zones(city, lat=profile["lat"], lon=profile["lon"]):
            zone_with_city = {**zone, "city": city}
            features.append(create_zone_polygon(zone_with_city))
    return {"type": "FeatureCollection", "features": features}


def compute_distance(point_a, point_b):
    return sqrt(((point_a[0] - point_b[0]) ** 2) + ((point_a[1] - point_b[1]) ** 2))


def build_dispatch_plan():
    open_cases = [case for case in fetch_cases() if case["status"] in {"open", "in_progress"}]
    if not open_cases:
        return []

    latest_locations = {item["location_label"]: item for item in get_live_data_payload()}
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "watch": 1, "normal": 0}
    enriched = []
    for case in open_cases:
        location = latest_locations.get(case["location_label"], {})
        enriched.append({
            **case,
            "lat": float(location.get("lat", CITY_PROFILES.get(case["city"], {}).get("lat", 20.5))),
            "lon": float(location.get("lon", CITY_PROFILES.get(case["city"], {}).get("lon", 78.9))),
            "priority_rank": severity_rank.get(case["severity"], 0),
        })

    enriched.sort(key=lambda item: (item["priority_rank"], item.get("latest_risk_score") or 0), reverse=True)
    current = (28.6139, 77.2090)
    ordered = []
    pending = enriched[:]
    while pending:
        pending.sort(
            key=lambda item: (
                -item["priority_rank"],
                -float(item.get("latest_risk_score") or 0),
                compute_distance(current, (item["lat"], item["lon"])),
            )
        )
        next_stop = pending.pop(0)
        ordered.append({
            **next_stop,
            "dispatch_eta_minutes": max(20, int(compute_distance(current, (next_stop["lat"], next_stop["lon"])) * 90)),
        })
        current = (next_stop["lat"], next_stop["lon"])
    return ordered


def build_monitoring_snapshot():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT city, power, status, zone_id, zone_name, timestamp
        FROM thefts
        ORDER BY id DESC
        LIMIT 200
        """
    )
    recent_rows = cur.fetchall()
    con.close()

    recent_samples = [
        {
            "city": row[0],
            "power": float(row[1]),
            "status": row[2],
            "zone_id": row[3],
            "zone_name": row[4],
            "timestamp": row[5],
        }
        for row in recent_rows
    ]
    active_locations = get_live_data_payload()
    open_cases = [case for case in fetch_cases() if case["status"] in {"open", "in_progress"}]
    resolved_cases = [case for case in fetch_cases() if case["status"] == "resolved"]
    theft_samples = [item for item in recent_samples if item["status"] == "THEFT"]
    avg_power = round(float(np.mean([item["power"] for item in recent_samples])) if recent_samples else 0.0, 2)
    peak_power = round(float(np.max([item["power"] for item in recent_samples])) if recent_samples else 0.0, 2)
    theft_rate = round((len(theft_samples) / len(recent_samples)) * 100, 2) if recent_samples else 0.0

    drift_records = []
    for item in recent_samples[:60]:
        profile = ensure_city_profile(item["city"])
        baseline = float(profile["base_power"])
        drift = ((item["power"] - baseline) / max(baseline, 1.0)) * 100
        drift_records.append(drift)
    average_drift = round(float(np.mean(drift_records)) if drift_records else 0.0, 2)

    return {
        "model_loaded": model_artifacts_present(),
        "threshold": DEFAULT_THRESHOLD,
        "sample_window": len(recent_samples),
        "average_power": avg_power,
        "peak_power": peak_power,
        "theft_rate": theft_rate,
        "average_drift": average_drift,
        "active_alerts": sum(1 for item in active_locations if item["status"] == "THEFT"),
        "open_cases": len(open_cases),
        "resolved_cases": len(resolved_cases),
        "unread_notifications": sum(1 for item in fetch_notifications(limit=100, unread_only=True)),
        "top_hotspots": sorted(
            [item for item in active_locations if item["status"] == "THEFT"],
            key=lambda item: item["risk_score"],
            reverse=True,
        )[:5],
        "dispatch_plan": build_dispatch_plan()[:5],
    }


def build_model_monitoring_snapshot(limit=12):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT city, power, status, zone_id, zone_name, timestamp
        FROM thefts
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(limit, 50)),),
    )
    recent_rows = cur.fetchall()
    con.close()

    drift_series = []
    theft_labels = 0
    for row in reversed(recent_rows):
        city = row[0]
        power = float(row[1])
        status = row[2]
        zone_id = row[3]
        zone_name = row[4]
        timestamp = row[5]
        profile = ensure_city_profile(city)
        baseline = float(profile["base_power"])
        drift = round(((power - baseline) / max(baseline, 1.0)) * 100, 2)
        theft_labels += 1 if status == "THEFT" else 0
        drift_series.append({
            "city": city,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "timestamp": timestamp,
            "status": status,
            "power": round(power, 2),
            "baseline": round(baseline, 2),
            "drift": drift,
            "risk_band": "high" if abs(drift) >= 30 else "watch" if abs(drift) >= 15 else "normal",
        })

    drift_values = [item["drift"] for item in drift_series]
    average_drift = round(float(np.mean(drift_values)) if drift_values else 0.0, 2)
    max_positive_drift = round(float(max(drift_values)) if drift_values else 0.0, 2)
    max_negative_drift = round(float(min(drift_values)) if drift_values else 0.0, 2)
    drift_alerts = sum(1 for item in drift_series if abs(item["drift"]) >= 30)

    return {
        "model_loaded": model_artifacts_present(),
        "threshold": DEFAULT_THRESHOLD,
        "sample_window": len(drift_series),
        "average_drift": average_drift,
        "max_positive_drift": max_positive_drift,
        "max_negative_drift": max_negative_drift,
        "drift_alerts": drift_alerts,
        "theft_label_rate": round((theft_labels / len(drift_series)) * 100, 2) if drift_series else 0.0,
        "drift_series": drift_series,
    }


def create_case_record(payload):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO cases (city, zone_id, zone_name, location_label, severity, status, recommended_action, assignee, notes, latest_risk_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["city"],
            payload.get("zone_id"),
            payload.get("zone_name"),
            payload["location_label"],
            payload["severity"],
            payload.get("status", "open"),
            payload.get("recommended_action"),
            payload.get("assignee"),
            payload.get("notes"),
            payload.get("latest_risk_score"),
        ),
    )
    case_id = cur.lastrowid
    con.commit()
    con.close()
    return case_id


def update_case_record(case_id, payload):
    allowed_fields = {
        "status": payload.get("status"),
        "assignee": payload.get("assignee"),
        "notes": payload.get("notes"),
        "recommended_action": payload.get("recommended_action"),
        "latest_risk_score": payload.get("latest_risk_score"),
    }
    updates = {key: value for key, value in allowed_fields.items() if value is not None}
    if not updates:
        return False

    assignments = ", ".join(f"{field} = ?" for field in updates.keys())
    values = list(updates.values())
    values.append(case_id)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        f"""
        UPDATE cases
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        values,
    )
    changed = cur.rowcount > 0
    con.commit()
    con.close()
    return changed


def update_cases_bulk_status(case_ids, status, actor=None, note=None):
    valid_statuses = {"open", "in_progress", "resolved", "closed"}
    if status not in valid_statuses:
        raise ValueError("status must be one of: open, in_progress, resolved, closed.")

    normalized_ids = []
    for case_id in case_ids:
        try:
            normalized_ids.append(int(case_id))
        except (TypeError, ValueError):
            continue

    if not normalized_ids:
        return {"updated": [], "missing": []}

    updated_cases = []
    missing_cases = []
    for case_id in normalized_ids:
        case_record = next((item for item in fetch_cases() if item["id"] == case_id), None)
        if not case_record:
            missing_cases.append(case_id)
            continue

        if update_case_record(case_id, {"status": status}):
            updated_cases.append(case_id)
            append_case_event(
                case_id,
                "updated",
                f"Case #{case_id} updated via bulk action.",
                details=f"status changed to {status}. {note or 'Bulk workflow action executed.'}",
                actor=actor,
            )

    if updated_cases:
        log_audit_event(
            action="bulk_case_status_update",
            entity_type="case",
            summary=f"Bulk case status update applied to {len(updated_cases)} case(s).",
            details=f"status={status}; case_ids={updated_cases}; missing={missing_cases}",
            actor=actor,
        )

    return {"updated": updated_cases, "missing": missing_cases}


def create_or_get_case_from_payload(payload, actor=None):
    city = normalize_city_name((payload.get("city") or "").strip())
    location_label = (payload.get("location_label") or "").strip()
    severity = (payload.get("severity") or "").strip().lower()

    if not city or not location_label or not severity:
        raise ValueError("city, location_label, and severity are required to create a case.")

    active_statuses = {"open", "in_progress"}
    existing_case = next(
        (
            item for item in fetch_cases()
            if item["location_label"] == location_label and item["status"] in active_statuses
        ),
        None,
    )
    if existing_case:
        return existing_case, False, existing_case["id"]

    assignee = (payload.get("assignee") or "").strip() or auto_assign_case(severity)
    case_payload = {
        "city": city,
        "zone_id": payload.get("zone_id"),
        "zone_name": payload.get("zone_name"),
        "location_label": location_label,
        "severity": severity,
        "status": payload.get("status", "open"),
        "recommended_action": payload.get("recommended_action"),
        "assignee": assignee,
        "notes": payload.get("notes"),
        "latest_risk_score": payload.get("latest_risk_score"),
    }
    case_id = create_case_record(case_payload)
    append_case_event(
        case_id,
        "created",
        f"Case opened for {location_label}.",
        details=f"Severity set to {severity}. Recommended action: {payload.get('recommended_action') or 'Pending'}. Assignee: {assignee or 'unassigned'}.",
        actor=actor,
    )
    create_notification(
        title="New investigation case opened",
        message=f"{location_label} was escalated as a {severity} case and assigned to {assignee or 'the operations queue'}.",
        category="case",
        severity=severity,
        related_case_id=case_id,
    )
    log_audit_event(
        action="create_case",
        entity_type="case",
        entity_id=case_id,
        summary=f"Case #{case_id} opened for {location_label}.",
        details=f"severity={severity}; assignee={assignee or 'unassigned'}; recommended_action={payload.get('recommended_action') or 'pending'}",
        actor=actor,
    )
    created_case = next((item for item in fetch_cases() if item["id"] == case_id), None)
    return created_case, True, case_id


@app.route("/api/cases")
@login_required
def cases_data():
    status = request.args.get("status")
    cases = fetch_cases(status=status)
    summary = {
        "total": len(cases),
        "open": sum(1 for item in cases if item["status"] == "open"),
        "in_progress": sum(1 for item in cases if item["status"] == "in_progress"),
        "resolved": sum(1 for item in cases if item["status"] == "resolved"),
        "closed": sum(1 for item in cases if item["status"] == "closed"),
    }
    return jsonify({
        "summary": summary,
        "cases": cases,
    })


@app.route("/api/cases", methods=["POST"])
@role_required("admin", "operator")
def create_case():
    payload = request.get_json(silent=True) or {}
    actor = get_current_user()

    try:
        created_case, is_new, _ = create_or_get_case_from_payload(payload, actor=actor)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "message": "Case created successfully." if is_new else "An active case already exists for this location.",
        "case": created_case,
    }), 201 if is_new else 200


@app.route("/api/cases/<int:case_id>", methods=["PATCH"])
@role_required("admin", "operator")
def update_case(case_id):
    payload = request.get_json(silent=True) or {}
    actor = get_current_user()
    valid_statuses = {"open", "in_progress", "resolved", "closed"}
    status = payload.get("status")

    if status is not None and status not in valid_statuses:
        return jsonify({
            "error": "status must be one of: open, in_progress, resolved, closed."
        }), 400

    updated = update_case_record(case_id, payload)
    if not updated:
        return jsonify({
            "error": "Case not found or no valid fields were provided."
        }), 404

    updated_case = next((item for item in fetch_cases() if item["id"] == case_id), None)
    event_fragments = []
    if "status" in payload and payload.get("status"):
        event_fragments.append(f"status changed to {payload['status']}")
    if "assignee" in payload:
        event_fragments.append(f"assignee set to {payload.get('assignee') or 'unassigned'}")
    if "notes" in payload:
        event_fragments.append("notes updated")
    if "recommended_action" in payload and payload.get("recommended_action"):
        event_fragments.append(f"action updated to {payload['recommended_action']}")
    if "latest_risk_score" in payload and payload.get("latest_risk_score") is not None:
        event_fragments.append(f"risk score refreshed to {payload['latest_risk_score']}")

    append_case_event(
        case_id,
        "updated",
        f"Case #{case_id} updated.",
        details=", ".join(event_fragments) if event_fragments else "Case fields were updated.",
        actor=actor,
    )
    create_notification(
        title="Case updated",
        message=f"Case #{case_id} for {updated_case['location_label']} was updated to {updated_case['status']}.",
        category="case",
        severity=updated_case["severity"],
        related_case_id=case_id,
    )
    log_audit_event(
        action="update_case",
        entity_type="case",
        entity_id=case_id,
        summary=f"Case #{case_id} updated.",
        details=", ".join(event_fragments) if event_fragments else "Case fields were updated.",
        actor=actor,
    )
    return jsonify({
        "message": "Case updated successfully.",
        "case": updated_case,
    })


@app.route("/api/cases/bulk-status", methods=["POST"])
@role_required("admin", "operator")
def bulk_update_cases():
    payload = request.get_json(silent=True) or {}
    actor = get_current_user()
    status = (payload.get("status") or "").strip()
    case_ids = payload.get("case_ids") or []
    note = (payload.get("note") or "").strip() or None

    try:
        result = update_cases_bulk_status(case_ids, status, actor=actor, note=note)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not result["updated"]:
        return jsonify({
            "error": "No valid cases were updated.",
            "missing_case_ids": result["missing"],
        }), 400

    return jsonify({
        "message": "Cases updated successfully.",
        "updated_case_ids": result["updated"],
        "missing_case_ids": result["missing"],
        "status": status,
    })


@app.route("/api/cases/<int:case_id>/timeline")
@login_required
def case_timeline(case_id):
    case_record = next((item for item in fetch_cases() if item["id"] == case_id), None)
    if not case_record:
        return jsonify({"error": "Case not found."}), 404
    return jsonify({
        "case": case_record,
        "events": fetch_case_timeline(case_id),
    })


@app.route("/api/cases/export.csv")
@login_required
def export_cases_csv():
    status = request.args.get("status")
    cases = fetch_cases(status=status)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "city",
        "zone_name",
        "location_label",
        "severity",
        "status",
        "recommended_action",
        "assignee",
        "latest_risk_score",
        "notes",
        "created_at",
        "updated_at",
    ])
    for item in cases:
        writer.writerow([
            item["id"],
            item["city"],
            item["zone_name"] or "",
            item["location_label"],
            item["severity"],
            item["status"],
            item["recommended_action"] or "",
            item["assignee"] or "",
            item["latest_risk_score"] if item["latest_risk_score"] is not None else "",
            item["notes"] or "",
            item["created_at"],
            item["updated_at"],
        ])

    filename = f"smart_theft_cases_{status or 'all'}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/cases/report.pdf")
@login_required
def export_cases_pdf():
    from io import BytesIO
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt

    cases = fetch_cases(status=request.args.get("status"))
    buffer = BytesIO()
    with PdfPages(buffer) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("white")
        y = 0.95
        fig.text(0.08, y, "SmartTheft Investigation Report", fontsize=18, weight="bold")
        y -= 0.04
        fig.text(0.08, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", fontsize=10)
        y -= 0.05
        summary = [
            f"Total cases: {len(cases)}",
            f"Open: {sum(1 for item in cases if item['status'] == 'open')}",
            f"In Progress: {sum(1 for item in cases if item['status'] == 'in_progress')}",
            f"Resolved: {sum(1 for item in cases if item['status'] == 'resolved')}",
        ]
        for line in summary:
            fig.text(0.08, y, line, fontsize=11)
            y -= 0.03
        y -= 0.02
        for item in cases[:18]:
            fig.text(
                0.08,
                y,
                f"#{item['id']} | {item['location_label']} | {item['severity']} | {item['status']} | {item['assignee'] or 'unassigned'}",
                fontsize=9,
            )
            y -= 0.028
            if y < 0.08:
                pdf.savefig(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69))
                y = 0.95
        pdf.savefig(fig)
        plt.close(fig)

    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=smart_theft_cases_report.pdf"},
    )


@app.route("/api/monitoring/summary")
@login_required
def monitoring_summary():
    return jsonify(build_monitoring_snapshot())


@app.route("/api/model/monitoring")
@login_required
def model_monitoring():
    return jsonify(build_model_monitoring_snapshot())


@app.route("/api/model/performance-report")
@login_required
def model_performance_report():
    actor = get_current_user()
    report_path = os.path.join(BASE_DIR, "model_performance.png")
    if not os.path.exists(report_path):
        return jsonify({"error": "Model performance report not found. Retrain the model first."}), 404

    response = send_file(
        report_path,
        as_attachment=True,
        download_name="smarttheft_model_performance.png",
        mimetype="image/png",
    )
    log_audit_event(
        action="download_model_report",
        entity_type="model",
        summary="Model performance report downloaded.",
        details="report=model_performance.png",
        actor=actor,
    )
    return response


@app.route("/api/dispatch/plan")
@login_required
def dispatch_plan():
    return jsonify({
        "stops": build_dispatch_plan(),
    })


@app.route("/api/zones/geojson")
@login_required
def zones_geojson():
    return jsonify(build_zone_geojson())


@app.route("/api/notifications")
@login_required
def notifications_data():
    limit = max(1, min(request.args.get("limit", default=30, type=int), 100))
    unread_only = request.args.get("unread_only", default=0, type=int) == 1
    return jsonify({
        "notifications": fetch_notifications(limit=limit, unread_only=unread_only),
    })


@app.route("/api/notifications/<int:notification_id>/read", methods=["PATCH"])
@login_required
def read_notification(notification_id):
    changed = mark_notification_read(notification_id)
    if not changed:
        return jsonify({"error": "Notification not found."}), 404
    return jsonify({"message": "Notification marked as read."})


@app.route("/api/notifications/read-all", methods=["PATCH"])
@login_required
def read_all_notifications():
    changed = mark_all_notifications_read()
    return jsonify({
        "message": "Notifications marked as read.",
        "updated_count": changed,
    })


@app.route("/api/notifications/summary")
@login_required
def notifications_summary():
    return jsonify(get_notification_summary())


@app.route("/api/admin/users")
@role_required("admin")
def admin_users():
    return jsonify({"users": fetch_users()})


@app.route("/api/admin/users", methods=["POST"])
@role_required("admin")
def admin_create_user():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    full_name = (payload.get("full_name") or "").strip()
    password = payload.get("password") or ""
    role = (payload.get("role") or "").strip()
    valid_roles = {"admin", "analyst", "operator"}

    if not username or not full_name or not password or role not in valid_roles:
        return jsonify({"error": "username, full_name, password, and a valid role are required."}), 400
    if fetch_user_by_username(username):
        return jsonify({"error": "That username already exists."}), 409

    user_id = create_user_record(username, full_name, password, role)
    create_notification(
        title="New portal user created",
        message=f"{full_name} was added as {role}.",
        category="admin",
        severity="info",
    )
    log_audit_event(
        action="create_user",
        entity_type="user",
        entity_id=username,
        summary=f"Created user {username} ({role}).",
        details=f"Full name={full_name}",
        actor=get_current_user(),
    )
    return jsonify({
        "message": "User created successfully.",
        "user": next((item for item in fetch_users() if item["id"] == user_id), None),
    }), 201


@app.route("/api/admin/database/backup")
@role_required("admin")
def admin_database_backup():
    actor = get_current_user()
    backup_path = create_database_backup_file()
    filename = f"smarttheft_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sqlite"
    response = send_file(
        backup_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/x-sqlite3",
    )
    response.call_on_close(lambda: os.path.exists(backup_path) and os.remove(backup_path))
    log_audit_event(
        action="database_backup",
        entity_type="database",
        summary="Database backup downloaded.",
        details=f"filename={filename}",
        actor=actor,
    )
    return response


@app.route("/api/admin/database/restore", methods=["POST"])
@role_required("admin")
def admin_database_restore():
    actor = get_current_user()
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Upload a SQLite backup file in the 'file' field."}), 400

    if not upload.filename.lower().endswith((".sqlite", ".db", ".sqlite3")):
        return jsonify({"error": "Only SQLite backup files are supported."}), 400

    temp_upload = tempfile.NamedTemporaryFile(prefix="smarttheft_restore_", suffix=".sqlite", delete=False)
    temp_upload_path = temp_upload.name
    try:
        temp_upload.close()
        upload.save(temp_upload_path)
        restore_database_from_file(temp_upload_path)
        log_audit_event(
            action="database_restore",
            entity_type="database",
            summary="Database restored from backup.",
            details=f"filename={upload.filename}",
            actor=actor,
        )
        create_notification(
            title="Database restored",
            message=f"SQLite database restored from {upload.filename}.",
            category="admin",
            severity="info",
        )
        return jsonify({
            "message": "Database restored successfully.",
            "filename": upload.filename,
        })
    except Exception as exc:
        log_audit_event(
            action="database_restore_failed",
            entity_type="database",
            summary="Database restore failed.",
            details=str(exc),
            actor=actor,
        )
        return jsonify({"error": f"Database restore failed: {exc}"}), 500
    finally:
        try:
            os.remove(temp_upload_path)
        except OSError:
            pass


@app.route("/api/ingest/csv", methods=["POST"])
@role_required("admin", "analyst", "operator")
def ingest_csv():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Upload a CSV file in the 'file' field."}), 400

    try:
        csv_text = upload.stream.read().decode("utf-8-sig")
        frame = pd.read_csv(StringIO(csv_text))
    except Exception as exc:
        return jsonify({"error": f"Could not read CSV file: {exc}"}), 400

    if "city" not in frame.columns or "power" not in frame.columns:
        return jsonify({"error": "CSV must contain at least 'city' and 'power' columns."}), 400

    inserted = 0
    theft_count = 0
    new_cities = set()
    invalid_rows = []
    for index, row in frame.iterrows():
        try:
            city_name = normalize_city_name(str(row.get("city", "")).strip())
            power = float(row["power"])
            if not city_name:
                raise ValueError("city is empty")
            voltage = float(row.get("voltage", 220.0))
            current = float(row.get("current", power / max(voltage, 1.0)))
            lat = row.get("lat")
            lon = row.get("lon")
            zone_value = row.get("zone_name", "")
            zone_name = None if pd.isna(zone_value) else str(zone_value).strip() or None
            lat = float(lat) if pd.notna(lat) else None
            lon = float(lon) if pd.notna(lon) else None
        except Exception as exc:
            invalid_rows.append({"row": int(index) + 2, "error": str(exc)})
            continue

        city_preexisting = city_name in CITY_PROFILES
        if lat is None or lon is None:
            lat, lon = get_city_coordinates(city_name)
        profile = ensure_city_profile(city_name, lat=lat, lon=lon)
        if not city_preexisting:
            new_cities.add(city_name)
        lat = profile["lat"] if lat is None else lat
        lon = profile["lon"] if lon is None else lon
        zone_id = None
        if zone_name:
            matching_zone = next((zone for zone in get_city_zones(city_name, lat=profile["lat"], lon=profile["lon"]) if zone["zone_name"] == zone_name), None)
            if matching_zone:
                zone_id = matching_zone["zone_id"]
                lat = matching_zone["lat"]
                lon = matching_zone["lon"]

        status, risk_score = run_ai_prediction(power, city_name)
        upsert_city_reading(city_name, lat, lon, voltage, current, power, status, zone_id=zone_id, zone_name=zone_name)
        inserted += 1
        if status == "THEFT":
            theft_count += 1

    create_notification(
        title="CSV ingestion completed",
        message=f"{upload.filename} processed with {inserted} valid rows and {theft_count} theft flags.",
        category="ingestion",
        severity="high" if theft_count else "info",
    )
    log_audit_event(
        action="ingest_csv",
        entity_type="ingestion",
        summary=f"CSV ingestion processed {upload.filename}.",
        details=f"inserted={inserted}; theft_count={theft_count}; invalid_rows={len(invalid_rows)}; new_cities={len(new_cities)}",
        actor=get_current_user(),
    )
    return jsonify({
        "filename": upload.filename,
        "inserted_rows": inserted,
        "invalid_rows": invalid_rows,
        "theft_count": theft_count,
        "new_cities": sorted(new_cities),
    })


@app.route("/api/add", methods=["POST"])
@role_required("admin", "operator")
def add_city():
    payload = request.get_json(silent=True) or {}
    city_name = normalize_city_name((payload.get("city") or "").strip())

    if not city_name:
        return jsonify({"error": "City name is required."}), 400

    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        lat, lon = get_city_coordinates(city_name)

    if lat is None or lon is None:
        return jsonify({"error": f"Coordinates not found for '{city_name}'."}), 404

    ensure_city_profile(city_name, lat=lat, lon=lon)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT id FROM thefts
        WHERE LOWER(city) = LOWER(?)
        LIMIT 1
        """,
        (city_name,),
    )
    existing = cur.fetchone()

    if existing is None:
        for zone in get_city_zones(city_name, lat=lat, lon=lon):
            for meter in get_zone_meters(city_name, zone):
                voltage = 220.0
                power = round(get_realistic_power(city_name, zone=zone) * (1 + meter["meter_bias"]), 2)
                current = round(power / voltage, 2)
                status, _ = run_ai_prediction(power, city_name)
                cur.execute(
                    """
                    INSERT INTO thefts (city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        city_name,
                        voltage,
                        current,
                        power,
                        status,
                        float(zone["lat"]),
                        float(zone["lon"]),
                        zone["zone_id"],
                        zone["zone_name"],
                        meter["meter_id"],
                        meter["consumer_name"],
                        meter["consumer_type"],
                    ),
                )
        con.commit()

    con.close()
    log_audit_event(
        action="add_city",
        entity_type="city",
        entity_id=city_name,
        summary=f"City {city_name} added to the monitoring network.",
        details=f"lat={lat}; lon={lon}; already_present={existing is not None}",
        actor=get_current_user(),
    )
    return jsonify({"message": f"{city_name} added successfully.", "city": city_name, "lat": lat, "lon": lon})


@app.route("/api/audit-log")
@login_required
def audit_log():
    limit = request.args.get("limit", default=25, type=int)
    limit = max(1, min(limit, 100))
    return jsonify({
        "events": fetch_audit_events(limit=limit),
    })


@app.route("/api/audit-log/export")
@role_required("admin")
def export_audit_log():
    limit = request.args.get("limit", default=250, type=int)
    limit = max(1, min(limit, 1000))
    events = fetch_audit_events(limit=limit)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "action",
        "entity_type",
        "entity_id",
        "actor_username",
        "actor_role",
        "summary",
        "details",
        "created_at",
    ])
    for event in events:
        writer.writerow([
            event["id"],
            event["action"],
            event["entity_type"],
            event["entity_id"],
            event["actor_username"],
            event["actor_role"],
            event["summary"],
            event["details"],
            event["created_at"],
        ])

    filename = f"smarttheft_audit_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    log_audit_event(
        action="export_audit_log",
        entity_type="audit_log",
        summary=f"Audit log export generated with {len(events)} rows.",
        details=f"limit={limit}; filename={filename}",
        actor=get_current_user(),
    )

    response = Response(
        output.getvalue(),
        mimetype="text/csv",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/api/predict", methods=["POST"])
@role_required("admin", "analyst")
def predict_theft():
    payload = request.get_json(silent=True) or {}

    try:
        avg_usage = float(payload["avg_daily_consumption"])
        max_usage = float(payload["max_daily_consumption"])
        variance = float(payload["consumption_variance"])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": "Provide avg_daily_consumption, max_daily_consumption, and consumption_variance."
        }), 400

    loaded_model = get_model()
    loaded_scaler = get_scaler()
    if loaded_model is None or loaded_scaler is None:
        return jsonify({"error": "Model is not loaded. Run train.py first."}), 503

    features = build_inference_features(avg_usage, max_usage, variance)
    scaled_features = loaded_scaler.transform(features)
    probability = float(loaded_model.predict_proba(scaled_features)[0][1])
    status = "THEFT" if probability > DEFAULT_THRESHOLD else "NORMAL"
    explanations = build_prediction_explanations(avg_usage, max_usage, variance)
    reading_profile = build_prediction_reading_profile(avg_usage, max_usage, variance, status)
    log_audit_event(
        action="predict_single",
        entity_type="prediction",
        summary=f"Single prediction scored as {status}.",
        details=f"risk={round(probability * 100, 2)}%; avg={avg_usage:.2f}; max={max_usage:.2f}; variance={variance:.2f}",
        actor=get_current_user(),
    )

    return jsonify({
        "status": status,
        "risk_score": round(probability * 100, 2),
        "threshold": DEFAULT_THRESHOLD,
        "features": features.iloc[0].to_dict(),
        "explanations": explanations,
        "reading_profile": reading_profile,
    })


@app.route("/api/predict-batch", methods=["POST"])
@role_required("admin", "analyst")
def predict_batch_theft():
    loaded_model = get_model()
    loaded_scaler = get_scaler()
    if loaded_model is None or loaded_scaler is None:
        return jsonify({"error": "Model is not loaded. Run train.py first."}), 503

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Upload a CSV file in the 'file' field."}), 400

    if not upload.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV uploads are supported."}), 400

    try:
        csv_text = upload.stream.read().decode("utf-8-sig")
        frame = pd.read_csv(StringIO(csv_text))
    except Exception as exc:
        return jsonify({"error": f"Could not read CSV file: {exc}"}), 400

    if frame.empty:
        return jsonify({"error": "The uploaded CSV file is empty."}), 400

    try:
        results, invalid_rows, source_format = predict_batch_rows(frame)
    except KeyError as exc:
        payload = exc.args[0] if exc.args else {}
        return jsonify({
            "error": "CSV is missing required columns.",
            "missing_columns": payload.get("missing_columns", []),
            "required_columns": payload.get("required_columns", sorted(BATCH_FEATURE_COLUMNS)),
        }), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not results:
        return jsonify({
            "error": "No valid rows were found in the uploaded CSV.",
            "invalid_rows": invalid_rows,
        }), 400

    theft_count = sum(1 for item in results if item["status"] == "THEFT")
    normal_count = len(results) - theft_count
    average_risk = round(float(np.mean([item["risk_score"] for item in results])), 2)
    highest_risk = max(results, key=lambda item: item["risk_score"])
    reading_type_counts = {}
    for item in results:
        profile = item.get("reading_profile") or {}
        label = profile.get("label") or item["status"]
        reading_type_counts[label] = reading_type_counts.get(label, 0) + 1
    log_audit_event(
        action="predict_batch",
        entity_type="prediction",
        summary=f"Batch prediction completed for {len(results)} rows.",
        details=f"source_format={source_format}; theft_count={theft_count}; invalid_rows={len(invalid_rows)}; file={upload.filename}",
        actor=get_current_user(),
    )

    return jsonify({
        "filename": upload.filename,
        "source_format": source_format,
        "threshold": DEFAULT_THRESHOLD,
        "summary": {
            "processed_rows": len(results),
            "invalid_rows": len(invalid_rows),
            "theft_count": theft_count,
            "normal_count": normal_count,
            "average_risk_score": average_risk,
            "highest_risk_location": highest_risk["city"],
            "highest_risk_score": highest_risk["risk_score"],
            "reading_type_counts": reading_type_counts,
        },
        "invalid_rows": invalid_rows,
        "results": results,
    })


@app.route("/api/model/retrain", methods=["POST"])
@role_required("admin")
def retrain_model():
    global model, scaler
    actor = get_current_user()
    try:
        result = train_and_save_model(BASE_DIR)
        model = result["model"]
        scaler = result["scaler"]
        log_audit_event(
            action="retrain_model",
            entity_type="model",
            summary="Model retrained successfully.",
            details=f"dataset_size={result['dataset_size']}; report={os.path.basename(result['report_image_path'])}",
            actor=actor,
        )
        create_notification(
            title="Model retrained",
            message=f"SmartTheft model was retrained using {result['dataset_size']} samples.",
            category="model",
            severity="info",
        )
        return jsonify({
            "message": "Model retrained successfully.",
            "dataset_size": result["dataset_size"],
            "model_path": result["model_path"],
            "scaler_path": result["scaler_path"],
            "report_image_path": result["report_image_path"],
            "suspects_path": result["suspects_path"],
        })
    except Exception as exc:
        log_audit_event(
            action="retrain_model_failed",
            entity_type="model",
            summary="Model retrain failed.",
            details=str(exc),
            actor=actor,
        )
        return jsonify({"error": f"Model retraining failed: {exc}"}), 500


@app.route("/api/city/<city_name>/history")
@login_required
def city_history(city_name):
    normalized_city = normalize_city_name(city_name)
    limit = request.args.get("limit", default=12, type=int)
    limit = max(1, min(limit, 50))
    zone_id = request.args.get("zone_id")

    history = fetch_city_history_rows(normalized_city, limit=limit, zone_id=zone_id)
    if not history:
        return jsonify({"error": f"No history found for '{normalized_city}'."}), 404

    powers = [row["power"] for row in history]
    theft_count = sum(1 for row in history if row["status"] == "THEFT")
    avg_power = round(float(np.mean(powers)), 2)
    max_power = round(float(np.max(powers)), 2)

    return jsonify({
        "city": normalized_city,
        "zone_id": zone_id,
        "zone_name": history[0].get("zone_name"),
        "history": history,
        "summary": {
            "samples": len(history),
            "theft_count": theft_count,
            "avg_power": avg_power,
            "max_power": max_power,
        },
    })


@app.route("/api/zone/<zone_id>/consumers")
@login_required
def zone_consumers(zone_id):
    limit = request.args.get("limit", default=8, type=int)
    limit = max(1, min(limit, 25))
    consumers = fetch_zone_consumers(zone_id, limit=limit)
    if not consumers:
        return jsonify({"error": f"No consumers found for zone '{zone_id}'."}), 404
    return jsonify({
        "zone_id": zone_id,
        "consumers": consumers,
    })


@app.route("/api/debug/cities")
@role_required("admin")
def debug_cities():
    inventory = fetch_city_inventory()
    return jsonify({
        "count": len(inventory),
        "cities": inventory,
    })


@app.route("/api/alerts")
@login_required
def alerts_data():
    alerts = [
        item
        for item in live_data().get_json()
        if item["severity"] != "normal"
        and not is_alert_hidden(item["city"], item.get("zone_id"), item.get("timestamp"))
    ]
    alerts.sort(
        key=lambda item: (
            ["watch", "medium", "high", "critical"].index(item["severity"]),
            item["risk_score"],
        ),
        reverse=True,
    )
    return jsonify(alerts)


@app.route("/api/alerts/acknowledge", methods=["POST"])
@role_required("admin", "operator")
def acknowledge_alert():
    payload = request.get_json(silent=True) or {}
    city = normalize_city_name((payload.get("city") or "").strip())
    zone_id = (payload.get("zone_id") or "").strip() or None
    reading_timestamp = (payload.get("timestamp") or "").strip()
    note = (payload.get("note") or "").strip() or None

    if not city or not reading_timestamp:
        return jsonify({
            "error": "city and timestamp are required to acknowledge an alert."
        }), 400

    inserted = record_alert_acknowledgement(city, zone_id, reading_timestamp, actor=get_current_user(), note=note)
    if not inserted:
        return jsonify({
            "message": "Alert was already acknowledged.",
            "acknowledged": False,
        }), 200

    log_audit_event(
        action="acknowledge_alert",
        entity_type="alert",
        summary=f"Alert acknowledged for {city}.",
        details=f"zone_id={zone_id or 'n/a'}; timestamp={reading_timestamp}; note={note or 'none'}",
        actor=get_current_user(),
    )
    return jsonify({
        "message": "Alert acknowledged successfully.",
        "acknowledged": True,
    })


@app.route("/api/alerts/escalate", methods=["POST"])
@role_required("admin", "operator")
def escalate_alert():
    payload = request.get_json(silent=True) or {}
    actor = get_current_user()
    city = normalize_city_name((payload.get("city") or "").strip())
    zone_id = (payload.get("zone_id") or "").strip() or None
    reading_timestamp = (payload.get("timestamp") or "").strip()
    note = (payload.get("note") or "").strip() or None

    if not city or not reading_timestamp:
        return jsonify({
            "error": "city and timestamp are required to escalate an alert."
        }), 400

    alert_item = next(
        (
            item for item in get_live_data_payload()
            if item["city"] == city
            and str(item.get("zone_id") or "").strip() == str(zone_id or "").strip()
            and str(item.get("timestamp") or "") == reading_timestamp
        ),
        None,
    )
    if not alert_item:
        return jsonify({"error": "Alert snapshot not found in the live queue."}), 404

    case_payload = {
        "city": city,
        "zone_id": zone_id,
        "zone_name": alert_item.get("zone_name"),
        "location_label": alert_item.get("location_label") or city,
        "severity": alert_item.get("severity") or "high",
        "recommended_action": alert_item.get("recommended_action") or "Inspect",
        "latest_risk_score": alert_item.get("risk_score"),
        "notes": note or alert_item.get("action_reason") or "",
    }
    created_case, is_new, case_id = create_or_get_case_from_payload(case_payload, actor=actor)
    record_alert_workflow_action(
        action="escalated",
        city=city,
        zone_id=zone_id,
        reading_timestamp=reading_timestamp,
        actor=actor,
        note=note or alert_item.get("action_reason"),
        case_id=case_id,
    )
    log_audit_event(
        action="escalate_alert",
        entity_type="alert",
        summary=f"Alert escalated for {alert_item.get('location_label') or city}.",
        details=f"case_id={case_id}; zone_id={zone_id or 'n/a'}; timestamp={reading_timestamp}; note={note or 'none'}",
        actor=actor,
    )
    create_notification(
        title="Alert escalated",
        message=f"{alert_item.get('location_label') or city} was escalated into case #{case_id}.",
        category="case",
        severity=alert_item.get("severity") or "high",
        related_case_id=case_id,
    )
    return jsonify({
        "message": "Alert escalated successfully.",
        "escalated": True,
        "case_created": is_new,
        "case": created_case,
        "case_id": case_id,
    })


@app.route("/api/alerts/resolve", methods=["POST"])
@role_required("admin", "operator")
def resolve_alert():
    payload = request.get_json(silent=True) or {}
    actor = get_current_user()
    city = normalize_city_name((payload.get("city") or "").strip())
    zone_id = (payload.get("zone_id") or "").strip() or None
    reading_timestamp = (payload.get("timestamp") or "").strip()
    note = (payload.get("note") or "").strip() or None

    if not city or not reading_timestamp:
        return jsonify({
            "error": "city and timestamp are required to resolve an alert."
        }), 400

    alert_item = next(
        (
            item for item in get_live_data_payload()
            if item["city"] == city
            and str(item.get("zone_id") or "").strip() == str(zone_id or "").strip()
            and str(item.get("timestamp") or "") == reading_timestamp
        ),
        None,
    )
    if not alert_item:
        return jsonify({"error": "Alert snapshot not found in the live queue."}), 404

    record_alert_workflow_action(
        action="resolved",
        city=city,
        zone_id=zone_id,
        reading_timestamp=reading_timestamp,
        actor=actor,
        note=note or alert_item.get("action_reason"),
        case_id=payload.get("case_id"),
    )
    log_audit_event(
        action="resolve_alert",
        entity_type="alert",
        summary=f"Alert resolved for {alert_item.get('location_label') or city}.",
        details=f"zone_id={zone_id or 'n/a'}; timestamp={reading_timestamp}; note={note or 'none'}",
        actor=actor,
    )
    create_notification(
        title="Alert resolved",
        message=f"{alert_item.get('location_label') or city} was marked resolved by the operations team.",
        category="case",
        severity="info",
        related_case_id=payload.get("case_id"),
    )
    return jsonify({
        "message": "Alert resolved successfully.",
        "resolved": True,
    })

def compute_live_data():
    data = []
    readings = get_latest_monitored_readings()
    for city, voltage, current, power, status, lat, lon, zone_id, zone_name, timestamp in readings:
        ensure_city_profile(city, lat=lat, lon=lon)
        _, risk_score = run_ai_prediction(power, city)
        metadata = derive_incident_metadata(status, risk_score, power, city)
        data.append({
            "city": city,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "location_label": f"{zone_name}, {city}" if zone_name else city,
            "voltage": float(voltage),
            "current": float(current),
            "power": float(power),
            "status": status,
            "risk_score": round(risk_score, 2),
            "lat": float(lat),
            "lon": float(lon),
            "timestamp": timestamp,
            "suspicious_consumers": [],
            **metadata,
        })
    return data


@app.route("/api/live")
@login_required
def live_data():
    return jsonify(get_live_data_payload())


@app.route("/api/live/stream")
@login_required
def live_data_stream():
    def event_stream():
        while True:
            payload = {
                "live": get_live_data_payload(),
                "summary": build_monitoring_snapshot(),
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(max(3, LIVE_CACHE_SECONDS))

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=debug, host="0.0.0.0", port=port, threaded=True)
