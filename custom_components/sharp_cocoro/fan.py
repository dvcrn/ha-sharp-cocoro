from typing import Any

from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature, HVACAction, FAN_HIGH, FAN_AUTO, FAN_MEDIUM, FAN_LOW, PRECISION_WHOLE, PRECISION_TENTHS
from homeassistant.components.fan import FanEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from sharp_cocoro import Cocoro, Aircon
from sharp_cocoro.devices.aircon.aircon_properties import ValueSingle
from .const import DOMAIN
from . import SharpCocoroData

import logging

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    cocoro_device = entry.runtime_data
    assert isinstance(cocoro_device, SharpCocoroData)

    async_add_entities([SharpCocoroAirFan(cocoro_device)])



class SharpCocoroAirFan(FanEntity):
    """Representation of a Sharp Cocoro Air fan."""
    _attr_speed_count = 8

    @property
    def _device(self) -> Aircon:
        return self._cocoro_data.device

    @property
    def _cocoro(self) -> Cocoro:
        return self._cocoro_data.cocoro

    def __init__(self, cocoro_device: SharpCocoroData):
        """Initialize the fan."""
        print("fan init called ... ? ")

        self._cocoro_data = cocoro_device


        self.name = self._device.name + " Fan"
        # Initialize other necessary attributes
        # concat device_id and "fan"
        self.unique_id = "%s_%s" % (self._device.device_id, "fan")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.maker,
            model=self._device.model,
            serial_number=self._device.serial_number
        )

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._remove_listener = self.hass.bus.async_listen(
            "sharp_cocoro.device_updated",
            self._handle_device_update
        )

    async def _handle_device_update(self, event):
        print("handle device update called", event)
        device_id = event.data.get("device_id")
        if device_id == self._device.device_id:
            # await self.async_update_ha_state()
            self.async_write_ha_state()


    # Implement properties and methods here
    # For example:
    @property
    def is_on(self):
        """Return true if the fan is on."""
        # Logic to determine if the fan is on
        return self._device.get_power_status() == ValueSingle.POWER_ON

    @property
    def percentage(self) -> int | None:
        windspeed = self._device.get_windspeed()
        speed_mapping = {
            ValueSingle.WINDSPEED_LEVEL_1: 1,
            ValueSingle.WINDSPEED_LEVEL_2: 2,
            ValueSingle.WINDSPEED_LEVEL_3: 3,
            ValueSingle.WINDSPEED_LEVEL_4: 4,
            ValueSingle.WINDSPEED_LEVEL_5: 5,
            ValueSingle.WINDSPEED_LEVEL_6: 6,
            ValueSingle.WINDSPEED_LEVEL_7: 7,
            ValueSingle.WINDSPEED_LEVEL_8: 8,
        }

        if windspeed not in speed_mapping:
            return None  # or some default value

        speed_level = speed_mapping[windspeed]
        percentage = int((speed_level / 8) * 100)

        return percentage

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._device.queue_power_off()
        logging.getLogger('aiohttp').setLevel(logging.DEBUG)
        print(await self._cocoro.execute_queued_updates(self._device))
        return

    def set_percentage(self, percentage: int) -> None:
        pass

    def set_preset_mode(self, preset_mode: str) -> None:
        pass

    def set_direction(self, direction: str) -> None:
        pass

    def turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        pass

    def oscillate(self, oscillating: bool) -> None:
        pass

    def turn_off(self, **kwargs: Any) -> None:
        pass

    # Implement other methods like set_percentage, set_preset_mode, etc.
