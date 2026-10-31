import logging
from datetime import datetime

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN, FUEL_TANK_L, TRIP_GAP_SECONDS
from .database import (
    add_maintenance,
    end_trip,
    get_maintenance_log,
    get_recent_trips,
    save_reading,
    start_trip,
)
from .health import calculate_health_score

_LOGGER = logging.getLogger(__name__)

# Torque Pro uploads standard PIDs as hex keys ("k" + PID, no leading zero).
_KEY_MAP = {
    "kc":  "rpm",
    "k5":  "coolant_temp",
    "kd":  "speed",
    "k11": "throttle_pos",
    "k4":  "engine_load",
    "k42": "voltage",
    "k2f": "fuel_level",
    "kf":  "intake_temp",
    "k6":  "stft1",
}

# Keys Torque always sends that Dash deliberately doesn't store (yet).
_IGNORED_KEYS = {"kff1005", "kff1006"}  # GPS longitude / latitude

# Maps PID names → internal field names. Used for keys Torque has named via
# its userFullName<key> params (how custom PIDs get identified), plus direct
# name-style params from older app versions.
_PARAM_MAP = {
    "rpm":                          "rpm",
    "coolant_temp":                 "coolant_temp",
    "engine_coolant_temperature":   "coolant_temp",
    "speed":                        "speed",
    "gps_speed":                    "speed",
    "throttle_pos":                 "throttle_pos",
    "throttle_position":            "throttle_pos",
    "engine_load":                  "engine_load",
    "calculated_engine_load":       "engine_load",
    "voltage":                      "voltage",
    "bat_voltage":                  "voltage",
    "control_module_voltage":       "voltage",
    "fuel_level":                   "fuel_level",
    "fuel_level_(from_engine_ecu)": "fuel_level",
    "iat":                          "intake_temp",
    "intake_temp":                  "intake_temp",
    "intake_air_temperature":       "intake_temp",
    "stft_1b":                      "stft1",
    "stft_bank_1":                  "stft1",
    "short_term_fuel_trim_bank_1":  "stft1",
    # Toyota custom PIDs (from WiCAN's Corolla 2014-2019 profile), named in Torque
    "odometer":                     "odometer",
    "fuel_level_(l)":               "fuel_l",
    "fuel_liters":                  "fuel_l",
    "oil_temp":                     "oil_temp",
    "engine_oil_temp":              "oil_temp",
    "engine_oil_temperature":       "oil_temp",
}


def _norm_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _norm_key(key: str) -> str:
    """'k0c' and 'kc' are the same PID; Torque isn't consistent about padding."""
    key = key.lower()
    if key.startswith("k") and len(key) > 1:
        return "k" + (key[1:].lstrip("0") or "0")
    return key


def _learn_names(params: dict, key_names: dict):
    """Torque sends userFullName<hex>=<PID name> at session start."""
    for key, raw in params.items():
        if key.startswith("userFullName") and raw:
            key_names[_norm_key("k" + key[len("userFullName"):])] = raw


def _parse(params: dict, key_names: dict, unknown: dict) -> dict:
    reading = {}
    for key, raw in params.items():
        if raw in ("", None):
            continue
        k = _norm_key(key)
        mapped = _KEY_MAP.get(k)
        if not mapped and k in key_names:
            mapped = _PARAM_MAP.get(_norm_name(key_names[k]))
        if not mapped:
            mapped = _PARAM_MAP.get(_norm_name(key))
        if not mapped:
            # Remember unmapped PID keys so new/custom ones are discoverable
            # via /api/dash/status instead of silently dropped.
            if k.startswith("k") and k not in _IGNORED_KEYS:
                unknown[k] = {"name": key_names.get(k), "value": raw}
            continue
        try:
            reading[mapped] = float(raw)
        except ValueError:
            pass

    # Toyota reports fuel in liters; derive % when the standard PID is missing
    if "fuel_level" not in reading and "fuel_l" in reading:
        reading["fuel_level"] = round(reading["fuel_l"] / FUEL_TANK_L * 100, 1)
    return reading


class DashIngestView(HomeAssistantView):
    """Receives vehicle telemetry pushed by Torque Pro on a timed interval."""
    url = "/api/dash/ingest"
    name = "api:dash:ingest"
    requires_auth = False  # Torque Pro cannot attach HA auth tokens to uploads

    async def get(self, request):
        hass = request.app["hass"]
        params = dict(request.query)
        _LOGGER.debug("Dash ingest: %s", params)

        state = hass.data[DOMAIN]
        _learn_names(params, state["key_names"])
        reading = _parse(params, state["key_names"], state["unknown_keys"])
        if not reading:
            return web.Response(text="OK!")  # Torque requires this exact reply

        now = datetime.utcnow()
        last_time = state["last_reading_time"]
        trip_id = state["current_trip_id"]

        gap = (now - last_time).total_seconds() if last_time else None
        if gap is None or gap > TRIP_GAP_SECONDS:
            if trip_id is not None:
                await hass.async_add_executor_job(end_trip, hass, trip_id)
            trip_id = await hass.async_add_executor_job(start_trip, hass)
            state["current_trip_id"] = trip_id
            _LOGGER.info("Dash: trip %s started", trip_id)

        state["last_reading_time"] = now

        health_score, breakdown = calculate_health_score(reading)

        await hass.async_add_executor_job(
            save_reading, hass, reading, trip_id, health_score, breakdown
        )

        state["latest_reading"] = {
            **reading,
            "health_score": health_score,
            "breakdown": breakdown,
            "trip_id": trip_id,
            "timestamp": now.isoformat(),
        }

        hass.bus.fire(f"{DOMAIN}_reading", {"health_score": health_score})
        return web.Response(text="OK!")


class DashStatusView(HomeAssistantView):
    url = "/api/dash/status"
    name = "api:dash:status"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        state = hass.data[DOMAIN]
        return self.json({
            **state.get("latest_reading", {}),
            "unknown_keys": state.get("unknown_keys", {}),
        })


class DashTripsView(HomeAssistantView):
    url = "/api/dash/trips"
    name = "api:dash:trips"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        trips = await hass.async_add_executor_job(get_recent_trips, hass)
        return self.json(trips)


class DashMaintenanceView(HomeAssistantView):
    url = "/api/dash/maintenance"
    name = "api:dash:maintenance"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        entries = await hass.async_add_executor_job(get_maintenance_log, hass)
        return self.json(entries)

    async def post(self, request):
        hass = request.app["hass"]
        data = await request.json()

        service_type = (data.get("service_type") or "").strip()
        date = (data.get("date") or "").strip()
        if not service_type or not date:
            return web.Response(status=400, text="service_type and date are required")

        mileage = data.get("mileage")
        try:
            mileage = int(mileage) if mileage not in (None, "") else None
        except (TypeError, ValueError):
            mileage = None

        notes = (data.get("notes") or "").strip() or None

        entry_id = await hass.async_add_executor_job(
            add_maintenance, hass, date, service_type, mileage, notes
        )
        return self.json({"id": entry_id})
