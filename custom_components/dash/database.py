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
    """)
    conn.commit()
    conn.close()


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
        SELECT AVG(coolant_temp), AVG(voltage), MIN(fuel_level), MAX(rpm)
        FROM readings WHERE trip_id = ?
    """, (trip_id,))
    avg_coolant, avg_voltage, min_fuel, max_rpm = c.fetchone()

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
            max_rpm     = ?
        WHERE id = ?
    """, (
        datetime.utcnow().isoformat(),
        duration, avg_coolant, avg_voltage, min_fuel, max_rpm,
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
            health_score, breakdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
