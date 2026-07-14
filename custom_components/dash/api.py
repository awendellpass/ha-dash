import logging
from datetime import datetime

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN, TRIP_GAP_SECONDS
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

# Maps Torque Pro URL parameter names → internal field names.
# Torque derives param names from each PID's "log name"; multiple aliases
# cover common variations across app versions.
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
}


def _parse(params: dict) -> dict:
    reading = {}
    for key, raw in params.items():
        mapped = _PARAM_MAP.get(key.lower().replace(" ", "_"))
        if mapped and raw not in ("", None):
            try:
                reading[mapped] = float(raw)
            except ValueError:
                pass
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

        reading = _parse(params)
        if not reading:
            return web.Response(text="ok")

        state = hass.data[DOMAIN]
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
        return web.Response(text="ok")


class DashStatusView(HomeAssistantView):
    url = "/api/dash/status"
    name = "api:dash:status"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        return self.json(hass.data[DOMAIN].get("latest_reading", {}))


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
