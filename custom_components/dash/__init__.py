import logging

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .database import init_db
from .panel import async_register_panel

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data[DOMAIN] = {
        "current_trip_id": None,
        "last_reading_time": None,
        "latest_reading": {},
    }

    await hass.async_add_executor_job(init_db, hass)

    from .api import DashIngestView, DashStatusView, DashTripsView
    hass.http.register_view(DashIngestView)
    hass.http.register_view(DashStatusView)
    hass.http.register_view(DashTripsView)

    await async_register_panel(hass)

    _LOGGER.info("Dash integration loaded")
    return True
