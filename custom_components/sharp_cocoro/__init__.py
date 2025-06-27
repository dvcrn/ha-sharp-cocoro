"""The Sharp Cocoro Air integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
import traceback

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

try:
    _LOGGER.info("Importing Cocoro from sharp_cocoro")
    from sharp_cocoro import Cocoro
    _LOGGER.info("Successfully imported Cocoro")
except Exception as e:
    _LOGGER.error("Failed to import Cocoro: %s", e)
    _LOGGER.error("Traceback: %s", traceback.format_exc())
    raise

try:
    _LOGGER.info("Importing Device from sharp_cocoro")
    from sharp_cocoro import Device
    _LOGGER.info("Successfully imported Device")
except Exception as e:
    _LOGGER.error("Failed to import Device: %s", e)
    _LOGGER.error("Traceback: %s", traceback.format_exc())
    raise

from .config_flow import CONF_KEY
from .config_flow import CONF_SECRET

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

PLATFORMS: list[Platform] = [Platform.FAN, Platform.CLIMATE, Platform.SENSOR]

CocoroConfigEntry = ConfigEntry[Cocoro]

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
                    _LOGGER.debug("Device refreshed from API")
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

    # Get Home Assistant's managed aiohttp session
    session = async_get_clientsession(hass)
    _LOGGER.info("Got aiohttp session from Home Assistant")

    try:
        _LOGGER.info("Creating Cocoro client with session")
        # Create Cocoro client with HA's session to avoid SSL blocking
        cocoro = Cocoro(app_secret=app_secret, app_key=app_key, session=session)
        _LOGGER.info("Successfully created Cocoro client")
    except Exception as e:
        _LOGGER.error("Failed to create Cocoro client: %s", e)
        _LOGGER.error("Traceback: %s", traceback.format_exc())
        raise

    try:
        _LOGGER.info("Attempting login")
        # Initial login
        await cocoro.login()
        _LOGGER.info("Login successful")
        
        _LOGGER.info("Querying devices")
        devices = await cocoro.query_devices()
        _LOGGER.info("Query devices successful, found %d devices", len(devices) if devices else 0)

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
        _LOGGER.error("Error type: %s", type(e))
        _LOGGER.error("Full traceback: %s", traceback.format_exc())
        # Clean up on failure
        if 'cocoro' in locals() and hasattr(cocoro, "close"):
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
