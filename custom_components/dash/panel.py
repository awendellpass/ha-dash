import logging
import os

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass: HomeAssistant):
    hass.http.register_static_path(
        f"/{DOMAIN}/frontend",
        os.path.join(os.path.dirname(__file__), "frontend"),
        cache_headers=False,
    )

    from homeassistant.components.frontend import async_register_built_in_panel
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Dash",
        sidebar_icon="mdi:car",
        frontend_url_path=DOMAIN,
        config={
            "_panel_custom": {
                "name": "dash-panel",
                "module_url": f"/{DOMAIN}/frontend/dash-panel.js",
            }
        },
        require_admin=False,
    )
