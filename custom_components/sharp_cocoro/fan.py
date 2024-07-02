from typing import Any, List, Optional

from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature, HVACAction, FAN_HIGH, FAN_AUTO, FAN_MEDIUM, FAN_LOW, PRECISION_WHOLE, PRECISION_TENTHS
from homeassistant.components.fan import FanEntity, FanEntityFeature, ATTR_PRESET_MODE
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    int_states_in_range,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)
from sharp_cocoro import Cocoro, Aircon
from sharp_cocoro.devices.aircon.aircon_properties import ValueSingle
from .const import DOMAIN
from . import SharpCocoroData
import math

import logging

PRESET_MODE_AUTO = "Auto"
PRESET_MODE_NORMAL = "Normal"

FEATURES = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE 
SUPPORTED_PRESET_MODES = [PRESET_MODE_AUTO, PRESET_MODE_NORMAL]
SPEED_RANGE = (1, 8)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    cocoro_device = entry.runtime_data
    assert isinstance(cocoro_device, SharpCocoroData)

    async_add_entities([SharpCocoroAirFan(cocoro_device)])



class SharpCocoroAirFan(FanEntity):
    """Representation of a Sharp Cocoro Air fan."""
    _attr_speed_count = 8
    _attr_supported_features = FEATURES

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
        self.unique_id = str(self._device.device_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.maker,
            model=self._device.model,
            serial_number=self._device.serial_number
        )

        self._speed_mapping = {
            ValueSingle.WINDSPEED_LEVEL_1: 1,
            ValueSingle.WINDSPEED_LEVEL_2: 2,
            ValueSingle.WINDSPEED_LEVEL_3: 3,
            ValueSingle.WINDSPEED_LEVEL_4: 4,
            ValueSingle.WINDSPEED_LEVEL_5: 5,
            ValueSingle.WINDSPEED_LEVEL_6: 6,
            ValueSingle.WINDSPEED_LEVEL_7: 7,
            ValueSingle.WINDSPEED_LEVEL_8: 8,
        }

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

        if windspeed == ValueSingle.WINDSPEED_LEVEL_AUTO:
            return 100

        if windspeed not in self._speed_mapping:
            return None  # or some default value

        speed_level = self._speed_mapping[windspeed]
        percentage = int((speed_level / 8) * 100)

        return percentage

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._device.queue_power_off()
        await self.execute_and_refresh()
        return

    # async def async_turn_on(self, **kwargs: Any) -> None:
    #     self._device.queue_power_on()
    #     opmode = self._device.get_operation_mode()
    #     if opmode:
    #         self._device.queue_property_status_update(opmode)

    #     await self.execute_and_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        print("set percentage called", percentage)
        """Set the speed percentage of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return

        target_speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        print(target_speed)
        target_speed_setting = next(
            (v for v, k in self._speed_mapping.items() if k == target_speed), None
        )

        print(target_speed_setting)
        self._device.queue_windspeed_update(target_speed_setting)
        self._device.queue_power_on()
        await self.execute_and_refresh()


    @property
    def preset_modes(self) -> List[str]:
        """Return the preset modes supported."""
        return SUPPORTED_PRESET_MODES

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current selected preset mode."""
        windspeed = self._device.get_windspeed()
        if windspeed == ValueSingle.WINDSPEED_LEVEL_AUTO:
            return PRESET_MODE_AUTO

        return PRESET_MODE_NORMAL

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        print("set preset mode called", preset_mode)
        if preset_mode == PRESET_MODE_AUTO:
            self._device.queue_windspeed_update(ValueSingle.WINDSPEED_LEVEL_AUTO)
        else:
            self._device.queue_windspeed_update(ValueSingle.WINDSPEED_LEVEL_4)

        await self.execute_and_refresh()

    def set_direction(self, direction: str) -> None:
        pass

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        print("turn on called", percentage, preset_mode)
        pass

    def oscillate(self, oscillating: bool) -> None:
        pass

    # Implement other methods like set_percentage, set_preset_mode, etc.
    async def execute_and_refresh(self) -> None:
        """Execute queued updates and refresh state."""
        print("execute and refresh", self._device.property_updates)
        await self._cocoro.execute_queued_updates(self._device)
        await self._cocoro_data.async_refresh_data()