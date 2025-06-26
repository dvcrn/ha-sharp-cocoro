"""The Sharp Cocoro Air integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta

from sharp_cocoro import Cocoro
from sharp_cocoro import Device

from .config_flow import CONF_KEY
from .config_flow import CONF_SECRET

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

PLATFORMS: list[Platform] = [Platform.FAN, Platform.CLIMATE, Platform.SENSOR]

CocoroConfigEntry = ConfigEntry[Cocoro]

_LOGGER = logging.getLogger(__name__)

# Token refresh interval (30 minutes)
TOKEN_REFRESH_INTERVAL = timedelta(minutes=30)


@dataclass
class SharpCocoroData:
    """State container for Sharp Cocoro integration."""

    cocoro: Cocoro
    device: Device
    hass: HomeAssistant
    app_key: str = field(default="")
    app_secret: str = field(default="")
    last_login_time: datetime | None = field(default=None)

    async def async_ensure_authenticated(self) -> bool:
        """Ensure the client is authenticated, re-login if necessary."""
        try:
            # Check if we need to refresh the token proactively
            if (
                self.last_login_time
                and (datetime.now() - self.last_login_time) > TOKEN_REFRESH_INTERVAL
            ):
                _LOGGER.info("Token refresh interval exceeded, re-authenticating")
                await self.async_login()
            return True
        except Exception as e:
            _LOGGER.error("Failed to ensure authentication: %s", e)
            return False

    async def async_login(self) -> None:
        """Perform login to the Cocoro API."""
        _LOGGER.info("Logging in to Sharp Cocoro API")
        await self.cocoro.login()
        self.last_login_time = datetime.now()
        _LOGGER.info("Successfully logged in to Sharp Cocoro API")

    async def async_refresh_data(self, _=None):
        """Refresh device data with error handling."""
        _LOGGER.info("Refreshing device data")

        try:
            devices = await self.cocoro.query_devices()
            for device in devices:
                if device.device_id == self.device.device_id:
                    self.device = device
                    break

            self.hass.bus.async_fire(
                "sharp_cocoro.device_updated", {"device_id": self.device.device_id}
            )

        except Exception as e:
            _LOGGER.error("Failed to refresh device data: %s", e)

            # Try to re-authenticate on any error (including 401)
            if (
                "401" in str(e)
                or "unauthorized" in str(e).lower()
                or "authentication" in str(e).lower()
            ):
                _LOGGER.info("Authentication error detected, attempting to re-login")
                try:
                    await self.async_login()
                    # Retry the refresh after re-authentication
                    devices = await self.cocoro.query_devices()
                    for device in devices:
                        if device.device_id == self.device.device_id:
                            self.device = device
                            break

                    self.hass.bus.async_fire(
                        "sharp_cocoro.device_updated",
                        {"device_id": self.device.device_id},
                    )
                    _LOGGER.info("Successfully refreshed data after re-authentication")

                except Exception as retry_error:
                    _LOGGER.error(
                        "Failed to refresh data after re-authentication: %s",
                        retry_error,
                    )
            else:
                # For non-authentication errors, just log them
                _LOGGER.error("Non-authentication error during refresh: %s", e)


async def async_setup_entry(hass: HomeAssistant, entry: CocoroConfigEntry) -> bool:
    """Set up Sharp Cocoro Air from a config entry."""
    app_secret = entry.data[CONF_SECRET]
    app_key = entry.data[CONF_KEY]
    _LOGGER.info("Initializing Sharp Cocoro Air with app key: %s", app_key)

    # Create Cocoro client without context manager to maintain connection
    cocoro = Cocoro(app_secret=app_secret, app_key=app_key)

    try:
        # Initial login
        await cocoro.login()
        devices = await cocoro.query_devices()

        if not devices:
            _LOGGER.error("No devices found")
            return False

        device = devices[0]
        _LOGGER.info("Discovered device: %s (ID: %s)", device.name, device.device_id)

        # Create data container with credentials for re-authentication
        scd = SharpCocoroData(
            cocoro=cocoro,
            device=device,
            hass=hass,
            app_key=app_key,
            app_secret=app_secret,
            last_login_time=datetime.now(),
        )

        # Set up periodic device refresh (every 15 seconds)
        async_track_time_interval(hass, scd.async_refresh_data, timedelta(seconds=15))

        # Set up periodic token refresh (every 30 minutes)
        async def async_refresh_token(_):
            """Periodically refresh the authentication token."""
            _LOGGER.info("Performing periodic token refresh")
            await scd.async_ensure_authenticated()

        async_track_time_interval(hass, async_refresh_token, TOKEN_REFRESH_INTERVAL)

        entry.runtime_data = scd
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except Exception as e:
        _LOGGER.error("Failed to set up Sharp Cocoro Air: %s", e)
        # Clean up on failure
        if hasattr(cocoro, "close"):
            await cocoro.close()
        return False


async def async_unload_entry(hass: HomeAssistant, entry: CocoroConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Sharp Cocoro Air integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up the Cocoro client
    if unload_ok and entry.runtime_data:
        scd = entry.runtime_data
        if hasattr(scd.cocoro, "close"):
            try:
                await scd.cocoro.close()
                _LOGGER.info("Cocoro client closed successfully")
            except Exception as e:
                _LOGGER.error("Error closing Cocoro client: %s", e)

    return unload_ok
