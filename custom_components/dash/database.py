import json
import logging
import sqlite3
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


def _path(hass):
    return hass.config.path("dash.db")


def init_db(hass):
    conn = sqlite3.connect(_path(hass))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trips (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time  TEXT NOT NULL,
            end_time    TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            duration_s  INTEGER,
            avg_coolant REAL,
            avg_voltage REAL,
            min_fuel    REAL,
            max_rpm     REAL
        );

        CREATE TABLE IF NOT EXISTS readings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id      INTEGER NOT NULL REFERENCES trips(id),
            timestamp    TEXT NOT NULL,
            rpm          REAL,
            coolant_temp REAL,
            speed        REAL,
            throttle_pos REAL,
            engine_load  REAL,
            voltage      REAL,
            fuel_level   REAL,
            intake_temp  REAL,
            stft1        REAL,
            health_score INTEGER,
            breakdown    TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_readings_trip ON readings(trip_id);
        CREATE INDEX IF NOT EXISTS idx_readings_ts   ON readings(timestamp);

        CREATE TABLE IF NOT EXISTS maintenance_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT NOT NULL,
            service_type TEXT NOT NULL,
            mileage      INTEGER,
            notes        TEXT,
            created_at   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance_log(date);
    """)

    # Columns added after v1 — ALTER existing databases in place
    _add_columns(conn, "readings", {
        "odometer": "REAL",  # Toyota PID 21 28; units (km vs mi) still to confirm
        "fuel_l":   "REAL",
        "oil_temp": "REAL",
    })
    _add_columns(conn, "trips", {
        "start_odometer": "REAL",
        "end_odometer":   "REAL",
        "max_oil_temp":   "REAL",
    })
    conn.commit()
    conn.close()


def _add_columns(conn, table: str, columns: dict):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, col_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def start_trip(hass) -> int:
    conn = sqlite3.connect(_path(hass))
    c = conn.cursor()
    c.execute("INSERT INTO trips (start_time) VALUES (?)", (datetime.utcnow().isoformat(),))
    trip_id = c.lastrowid
    conn.commit()
    conn.close()
    return trip_id


def end_trip(hass, trip_id: int):
    conn = sqlite3.connect(_path(hass))
    c = conn.cursor()

    c.execute("""
        SELECT AVG(coolant_temp), AVG(voltage), MIN(fuel_level), MAX(rpm),
               MIN(odometer), MAX(odometer), MAX(oil_temp)
        FROM readings WHERE trip_id = ?
    """, (trip_id,))
    (avg_coolant, avg_voltage, min_fuel, max_rpm,
     start_odometer, end_odometer, max_oil_temp) = c.fetchone()

    c.execute("SELECT start_time FROM trips WHERE id = ?", (trip_id,))
    row = c.fetchone()
    duration = None
    if row:
        start = datetime.fromisoformat(row[0])
        duration = int((datetime.utcnow() - start).total_seconds())

    c.execute("""
        UPDATE trips SET
            end_time    = ?,
            status      = 'completed',
            duration_s  = ?,
            avg_coolant = ?,
            avg_voltage = ?,
            min_fuel    = ?,
            max_rpm     = ?,
            start_odometer = ?,
            end_odometer   = ?,
            max_oil_temp   = ?
        WHERE id = ?
    """, (
        datetime.utcnow().isoformat(),
        duration, avg_coolant, avg_voltage, min_fuel, max_rpm,
        start_odometer, end_odometer, max_oil_temp,
        trip_id,
    ))
    conn.commit()
    conn.close()


def save_reading(hass, reading: dict, trip_id: int, health_score: int, breakdown: dict):
    conn = sqlite3.connect(_path(hass))
    conn.execute("""
        INSERT INTO readings (
            trip_id, timestamp, rpm, coolant_temp, speed, throttle_pos,
            engine_load, voltage, fuel_level, intake_temp, stft1,
            odometer, fuel_l, oil_temp,
            health_score, breakdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trip_id,
        datetime.utcnow().isoformat(),
        reading.get("rpm"),
        reading.get("coolant_temp"),
        reading.get("speed"),
        reading.get("throttle_pos"),
        reading.get("engine_load"),
        reading.get("voltage"),
        reading.get("fuel_level"),
        reading.get("intake_temp"),
        reading.get("stft1"),
        reading.get("odometer"),
        reading.get("fuel_l"),
        reading.get("oil_temp"),
        health_score,
        json.dumps(breakdown),
    ))
    conn.commit()
    conn.close()


def get_recent_trips(hass, limit: int = 20) -> list:
    conn = sqlite3.connect(_path(hass))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT t.*, COUNT(r.id) AS reading_count
        FROM trips t
        LEFT JOIN readings r ON r.trip_id = t.id
        GROUP BY t.id
        ORDER BY t.start_time DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def add_maintenance(hass, date: str, service_type: str, mileage, notes: str) -> int:
    conn = sqlite3.connect(_path(hass))
    c = conn.cursor()
    c.execute("""
        INSERT INTO maintenance_log (date, service_type, mileage, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (date, service_type, mileage, notes, datetime.utcnow().isoformat()))
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def get_maintenance_log(hass, limit: int = 100) -> list:
    conn = sqlite3.connect(_path(hass))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM maintenance_log
        ORDER BY date DESC, id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
