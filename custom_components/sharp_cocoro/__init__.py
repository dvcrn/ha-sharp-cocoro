"""The Sharp Cocoro Air integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sharp_cocoro import Cocoro, Device

from homeassistant.components.fan import FanEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.event import async_track_time_interval

from .config_flow import CONF_KEY, CONF_SECRET

PLATFORMS: list[Platform] = [Platform.FAN, Platform.CLIMATE, Platform.SENSOR]

type CocoroConfigEntry = ConfigEntry[Cocoro]

_LOGGER = logging.getLogger(__name__)

@dataclass
class SharpCocoroData:
    """State container for Sharp Cocoro integration."""
    cocoro: Cocoro
    device: Device
    hass: HomeAssistant

    async def async_refresh_data(self, _=None):
        """Refresh device data."""
        _LOGGER.info("Refreshing device data")
        devices = await self.cocoro.query_devices()
        for device in devices:
            if device.device_id == self.device.device_id:
                self.device = device
                break

        self.hass.bus.async_fire("sharp_cocoro.device_updated", {"device_id": self.device.device_id})

async def async_setup_entry(hass: HomeAssistant, entry: CocoroConfigEntry) -> bool:
    """Set up Sharp Cocoro Air from a config entry."""
    app_secret = entry.data[CONF_SECRET]
    app_key = entry.data[CONF_KEY]
    _LOGGER.info("Initializing Sharp Cocoro Air with app key: %s", app_key)

    async with Cocoro(app_secret=app_secret, app_key=app_key) as cocoro:
        await cocoro.login()
        devices = await cocoro.query_devices()
        device = devices[0]

        _LOGGER.info("Discovered device: %s (ID: %s)", device.name, device.device_id)

        scd = SharpCocoroData(cocoro, device, hass)
        async_track_time_interval(hass, scd.async_refresh_data, timedelta(seconds=15))        

        entry.runtime_data = scd

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: CocoroConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Sharp Cocoro Air integration")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
