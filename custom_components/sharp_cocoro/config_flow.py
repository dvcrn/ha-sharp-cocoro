"""Config flow for Sharp Cocoro Air integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from sharp_cocoro import Cocoro

from .const import DOMAIN

from homeassistant.config_entries import ConfigFlow
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

CONF_KEY = "app_key"
CONF_SECRET = "app_secret"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_KEY): str,
        vol.Required(CONF_SECRET): str,
    }
)


class PlaceholderHub:
    """Placeholder class to make tests pass."""

    def __init__(self, host: str) -> None:
        """Initialize."""
        self.host = host

    async def authenticate(self, username: str, password: str) -> bool:
        """Test if we can authenticate with the host."""
        async with Cocoro(app_secret=password, app_key=username) as cocoro:
            await cocoro.login()
            return cocoro.is_authenticated


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    hub = PlaceholderHub("host")

    if not await hub.authenticate(data[CONF_KEY], data[CONF_SECRET]):
        raise InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": "Sharp Cocoro Air"}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sharp Cocoro Air."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
