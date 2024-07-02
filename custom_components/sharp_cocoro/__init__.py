"""The Sharp Cocoro Air integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, Event
from homeassistant.components.fan import FanEntity
from homeassistant.helpers.event import async_track_time_interval
from sharp_cocoro import Cocoro, Device
from dataclasses import dataclass
import asyncio
from datetime import timedelta
from .config_flow import CONF_KEY, CONF_SECRET

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
PLATFORMS: list[Platform] = [Platform.FAN, Platform.CLIMATE, Platform.SENSOR]

# TODO Create ConfigEntry type alias with API object
# TODO Rename type alias and update all entry annotations
type New_NameConfigEntry = ConfigEntry[Cocoro]  # noqa: F821


@dataclass
class SharpCocoroData:
    """State container for Sharp Cocoro integration."""
    cocoro: Cocoro
    device: Device
    hass: HomeAssistant

    async def async_refresh_data(self, _=None):
        """Refresh data."""
        print("refreshing device", _)
        devices = await self.cocoro.query_devices()
        for device in devices:
            if device.device_id == self.device.device_id:
                self.device = device
                break

        self.hass.bus.async_fire("sharp_cocoro.device_updated", {"device_id": device.device_id})


# TODO Update entry annotation
async def async_setup_entry(hass: HomeAssistant, entry: New_NameConfigEntry) -> bool:
    """Set up Sharp Cocoro Air from a config entry."""
    app_secret = entry.data[CONF_SECRET]
    app_key = entry.data[CONF_KEY]
    print("initializing cocoro air", app_key)
    async with Cocoro(app_secret=app_secret, app_key=app_key) as cocoro:
        await cocoro.login()
        devices = await cocoro.query_devices()
        device = devices[0]

        print("discovered device: ", device.name, device.device_id)

        # TODO 1. Create API instance
        # TODO 2. Validate the API connection (and authentication)
        # TODO 3. Store an API object for your platforms to access
        # entry.runtime_data = MyAPI(...)
        scd = SharpCocoroData(cocoro, device, hass)
        async_track_time_interval(hass, scd.async_refresh_data, timedelta(seconds=15))        

        entry.runtime_data = scd

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


# TODO Update entry annotation
async def async_unload_entry(hass: HomeAssistant, entry: New_NameConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


