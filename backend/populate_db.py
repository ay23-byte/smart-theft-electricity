"""
Real-time Electricity Theft Detection - Realistic Dataset Generator
This script populates the database with realistic Indian city power consumption data
"""

import sqlite3
import os
from datetime import datetime
import math

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'theft.db')

# Realistic power consumption data for Indian cities
CITY_DATA = {
    "Delhi": {
        "lat": 28.6139,
        "lon": 77.2090,
        "base_power": 2800,  # Base consumption in Watts
        "peak_power": 4200,  # Peak hours consumption
        "theft_threshold": 3500,  # When power > this, it's theft
        "variance": 400  # ±400W variation
    },
    "Mumbai": {
        "lat": 19.0760,
        "lon": 72.8777,
        "base_power": 2400,
        "peak_power": 3800,
        "theft_threshold": 3500,
        "variance": 350
    },
    "Bangalore": {
        "lat": 12.9716,
        "lon": 77.5946,
        "base_power": 2600,
        "peak_power": 4100,
        "theft_threshold": 3500,
        "variance": 380
    },
    "Chennai": {
        "lat": 13.0827,
        "lon": 80.2707,
        "base_power": 2200,
        "peak_power": 3600,
        "theft_threshold": 3500,
        "variance": 320
    },
    "Kolkata": {
        "lat": 22.5726,
        "lon": 88.3639,
        "base_power": 2500,
        "peak_power": 3900,
        "theft_threshold": 3500,
        "variance": 370
    },
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867, "base_power": 2550, "peak_power": 3980, "theft_threshold": 3500, "variance": 365},
    "Pune": {"lat": 18.5204, "lon": 73.8567, "base_power": 2480, "peak_power": 3890, "theft_threshold": 3500, "variance": 350},
    "Ahmedabad": {"lat": 23.0225, "lon": 72.5714, "base_power": 2450, "peak_power": 3840, "theft_threshold": 3500, "variance": 340},
    "Jaipur": {"lat": 26.9124, "lon": 75.7873, "base_power": 2380, "peak_power": 3750, "theft_threshold": 3500, "variance": 330},
    "Lucknow": {"lat": 26.8467, "lon": 80.9462, "base_power": 2360, "peak_power": 3700, "theft_threshold": 3500, "variance": 325},
    "Kanpur": {"lat": 26.4499, "lon": 80.3319, "base_power": 2340, "peak_power": 3660, "theft_threshold": 3500, "variance": 320},
    "Nagpur": {"lat": 21.1458, "lon": 79.0882, "base_power": 2320, "peak_power": 3620, "theft_threshold": 3500, "variance": 315},
    "Indore": {"lat": 22.7196, "lon": 75.8577, "base_power": 2300, "peak_power": 3600, "theft_threshold": 3500, "variance": 310},
    "Bhopal": {"lat": 23.2599, "lon": 77.4126, "base_power": 2280, "peak_power": 3560, "theft_threshold": 3500, "variance": 305},
    "Patna": {"lat": 25.5941, "lon": 85.1376, "base_power": 2260, "peak_power": 3520, "theft_threshold": 3500, "variance": 300},
    "Surat": {"lat": 21.1702, "lon": 72.8311, "base_power": 2420, "peak_power": 3800, "theft_threshold": 3500, "variance": 335},
    "Vadodara": {"lat": 22.3072, "lon": 73.1812, "base_power": 2240, "peak_power": 3500, "theft_threshold": 3500, "variance": 295},
    "Rajkot": {"lat": 22.3039, "lon": 70.8022, "base_power": 2200, "peak_power": 3440, "theft_threshold": 3400, "variance": 285},
    "Nashik": {"lat": 19.9975, "lon": 73.7898, "base_power": 2190, "peak_power": 3420, "theft_threshold": 3400, "variance": 285},
    "Aurangabad": {"lat": 19.8762, "lon": 75.3433, "base_power": 2170, "peak_power": 3380, "theft_threshold": 3400, "variance": 280},
    "Visakhapatnam": {"lat": 17.6868, "lon": 83.2185, "base_power": 2350, "peak_power": 3700, "theft_threshold": 3500, "variance": 325},
    "Vijayawada": {"lat": 16.5062, "lon": 80.6480, "base_power": 2210, "peak_power": 3460, "theft_threshold": 3400, "variance": 290},
    "Coimbatore": {"lat": 11.0168, "lon": 76.9558, "base_power": 2230, "peak_power": 3490, "theft_threshold": 3400, "variance": 295},
    "Madurai": {"lat": 9.9252, "lon": 78.1198, "base_power": 2140, "peak_power": 3340, "theft_threshold": 3350, "variance": 275},
    "Salem": {"lat": 11.6643, "lon": 78.1460, "base_power": 2100, "peak_power": 3280, "theft_threshold": 3300, "variance": 270},
    "Tiruchirappalli": {"lat": 10.7905, "lon": 78.7047, "base_power": 2120, "peak_power": 3310, "theft_threshold": 3325, "variance": 272},
    "Kochi": {"lat": 9.9312, "lon": 76.2673, "base_power": 2180, "peak_power": 3400, "theft_threshold": 3400, "variance": 285},
    "Thiruvananthapuram": {"lat": 8.5241, "lon": 76.9366, "base_power": 2160, "peak_power": 3370, "theft_threshold": 3375, "variance": 280},
    "Mysore": {"lat": 12.2958, "lon": 76.6394, "base_power": 2080, "peak_power": 3250, "theft_threshold": 3300, "variance": 265},
    "Mangalore": {"lat": 12.9141, "lon": 74.8560, "base_power": 2090, "peak_power": 3270, "theft_threshold": 3300, "variance": 268},
    "Bhubaneswar": {"lat": 20.2961, "lon": 85.8245, "base_power": 2200, "peak_power": 3450, "theft_threshold": 3400, "variance": 290},
    "Cuttack": {"lat": 20.4625, "lon": 85.8828, "base_power": 2140, "peak_power": 3350, "theft_threshold": 3350, "variance": 278},
    "Ranchi": {"lat": 23.3441, "lon": 85.3096, "base_power": 2110, "peak_power": 3300, "theft_threshold": 3325, "variance": 272},
    "Jamshedpur": {"lat": 22.8046, "lon": 86.2029, "base_power": 2170, "peak_power": 3390, "theft_threshold": 3380, "variance": 282},
    "Guwahati": {"lat": 26.1445, "lon": 91.7362, "base_power": 2130, "peak_power": 3330, "theft_threshold": 3340, "variance": 276},
    "Noida": {"lat": 28.5355, "lon": 77.3910, "base_power": 2400, "peak_power": 3760, "theft_threshold": 3500, "variance": 330},
    "Gurgaon": {"lat": 28.4595, "lon": 77.0266, "base_power": 2460, "peak_power": 3850, "theft_threshold": 3500, "variance": 340},
    "Faridabad": {"lat": 28.4089, "lon": 77.3178, "base_power": 2310, "peak_power": 3620, "theft_threshold": 3500, "variance": 312},
    "Amritsar": {"lat": 31.6340, "lon": 74.8723, "base_power": 2180, "peak_power": 3410, "theft_threshold": 3400, "variance": 286},
    "Ludhiana": {"lat": 30.9010, "lon": 75.8573, "base_power": 2270, "peak_power": 3540, "theft_threshold": 3500, "variance": 300},
    "Chandigarh": {"lat": 30.7333, "lon": 76.7794, "base_power": 2220, "peak_power": 3480, "theft_threshold": 3400, "variance": 292}
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


def build_zone_id(city_name, zone_slug):
    normalized = city_name.lower().replace(" ", "-")
    return f"{normalized}-{zone_slug}"


def get_city_zones(city_name):
    info = CITY_DATA[city_name]
    zones = []
    for blueprint in ZONE_BLUEPRINTS:
        zones.append({
            "zone_id": build_zone_id(city_name, blueprint["slug"]),
            "zone_name": blueprint["name"],
            "lat": round(info["lat"] + blueprint["lat_offset"], 6),
            "lon": round(info["lon"] + blueprint["lon_offset"], 6),
            "load_bias": blueprint["load_bias"],
        })
    return zones


def get_zone_meters(city_name, zone):
    zone_slug = zone["zone_id"].split("-")[-1]
    return [
        {
            "meter_id": f"{zone['zone_id']}-{blueprint['suffix']}",
            "consumer_name": f"{blueprint['name_template']} {zone_slug.title()}",
            "consumer_type": blueprint["consumer_type"],
            "meter_bias": blueprint["load_bias"],
        }
        for blueprint in METER_BLUEPRINTS
    ]

def get_realistic_power(city_name, hour=None):
    """
    Generate realistic power consumption based on time of day
    Peak hours: 8-11 AM, 6-10 PM (higher consumption)
    Off-peak: 2-5 AM (lower consumption)
    """
    import time
    import random
    
    if hour is None:
        hour = datetime.now().hour
    
    data = CITY_DATA[city_name]
    base = data["base_power"]
    peak = data["peak_power"]
    variance = data["variance"]
    
    # Peak hours: 8-11 AM, 6-10 PM
    if (8 <= hour <= 11) or (18 <= hour <= 22):
        power = peak + random.randint(-variance, variance)
    # Off-peak: 2-5 AM
    elif 2 <= hour <= 5:
        power = base * 0.6 + random.randint(-variance//2, variance//2)
    # Normal hours
    else:
        power = base + random.randint(-variance, variance)
    
    return max(500, min(5000, power))  # Keep between 500-5000W

def populate_database():
    """
    Populate database with realistic power data for testing
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    # Create table if doesn't exist
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
    
    # Clear existing data
    cur.execute("DELETE FROM thefts")
    
    print("🔄 Populating database with realistic power consumption data...")
    
    # Add realistic data for each city and zone
    for city, info in CITY_DATA.items():
        print(f"  📍 {city}...")
        for zone in get_city_zones(city):
            for meter in get_zone_meters(city, zone):
                for i in range(4):
                    voltage = 220 + (i % 3) * 5  # 220 to 230V
                    power = get_realistic_power(city) * (1 + zone["load_bias"] + meter["meter_bias"])
                    power = max(500, min(7000, power))
                    current = power / voltage
                    status = "THEFT" if power > info["theft_threshold"] else "NORMAL"
                    
                    cur.execute("""
                        INSERT INTO thefts (city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        city,
                        voltage,
                        round(current, 2),
                        round(power, 2),
                        status,
                        zone["lat"],
                        zone["lon"],
                        zone["zone_id"],
                        zone["zone_name"],
                        meter["meter_id"],
                        meter["consumer_name"],
                        meter["consumer_type"],
                    ))
    
    con.commit()
    con.close()
    
    print("\n✅ Database populated with realistic Indian city power data!")
    print("\nSample Data Generated:")
    print("  • Delhi: 2800W base, 4200W peak, 3500W theft threshold")
    print("  • Mumbai: 2400W base, 3800W peak, 3500W theft threshold")
    print("  • Bangalore: 2600W base, 4100W peak, 3500W theft threshold")
    print("  • Chennai: 2200W base, 3600W peak, 3500W theft threshold")
    print("  • Kolkata: 2500W base, 3900W peak, 3500W theft threshold")
    print("\nPower varies by hour of day for realistic simulation!")

if __name__ == "__main__":
    populate_database()
