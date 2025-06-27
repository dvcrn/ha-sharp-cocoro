"""Fan platform for Sharp Cocoro Air."""

import asyncio
import logging
import math
from functools import wraps
from typing import Any

from sharp_cocoro import Aircon
from sharp_cocoro import Cocoro
from sharp_cocoro.devices.aircon.aircon_properties import StatusCode
from sharp_cocoro.devices.aircon.aircon_properties import ValueSingle

from . import SharpCocoroData
from .const import DOMAIN

from homeassistant.components.fan import FanEntity
from homeassistant.components.fan import FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import percentage_to_ranged_value

_LOGGER = logging.getLogger(__name__)


def debounce(wait_time):
    """Debounce a function for a specified amount of time."""

    def decorator(fn):
        pending_task = None

        @wraps(fn)
        async def debounced(*args, **kwargs):
            nonlocal pending_task

            # Cancel any existing task
            if pending_task is not None and not pending_task.done():
                pending_task.cancel()

            # Create a new task with delay
            async def delayed_call():
                await asyncio.sleep(wait_time)
                await fn(*args, **kwargs)

            pending_task = asyncio.create_task(delayed_call())

        return debounced

    return decorator


PRESET_MODE_AUTO = "Auto"
PRESET_MODE_NORMAL = "Normal"

FEATURES = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
SUPPORTED_PRESET_MODES = [PRESET_MODE_AUTO, PRESET_MODE_NORMAL]
SPEED_RANGE = (1, 8)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Sharp Cocoro Air fan platform."""
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
        _LOGGER.info("Initializing Sharp Cocoro Air Fan")
        self._cocoro_data = cocoro_device

        self._attr_name = f"{self._device.name} Fan"
        self._attr_unique_id = str(self._device.device_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.maker,
            model=self._device.model,
            serial_number=self._device.serial_number,
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

        # Create debounced refresh function
        self._debounced_refresh = debounce(5)(self._cocoro_data.async_refresh_data)

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._remove_listener = self.hass.bus.async_listen(
            "sharp_cocoro.device_updated", self._handle_device_update
        )

    async def _handle_device_update(self, event):
        _LOGGER.info("Handling device update for Sharp Cocoro Air Fan")
        device_id = event.data.get("device_id")
        if device_id == self._device.device_id:
            self.async_write_ha_state()

    @property
    def is_on(self):
        """Return true if the fan is on."""
        return self._device.get_power_status() == ValueSingle.POWER_ON

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        windspeed = self._device.get_windspeed()

        if windspeed == ValueSingle.WINDSPEED_LEVEL_AUTO:
            return 100

        if windspeed not in self._speed_mapping:
            return None

        speed_level = self._speed_mapping[windspeed]
        return int((speed_level / 8) * 100)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        _LOGGER.info("Turning off Sharp Cocoro Air Fan")
        self._device.queue_power_off()
        await self.execute_and_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan."""
        _LOGGER.info("Setting Sharp Cocoro Air Fan speed to %s%%", percentage)
        if percentage == 0:
            await self.async_turn_off()
            return

        target_speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        target_speed_setting = next(
            (v for v, k in self._speed_mapping.items() if k == target_speed), None
        )

        self._device.queue_windspeed_update(target_speed_setting)
        self._device.queue_power_on()
        await self.execute_and_refresh()

    @property
    def preset_modes(self) -> list[str]:
        """Return the preset modes supported."""
        return SUPPORTED_PRESET_MODES

    @property
    def preset_mode(self) -> str | None:
        """Return the current selected preset mode."""
        windspeed = self._device.get_windspeed()
        return (
            PRESET_MODE_AUTO
            if windspeed == ValueSingle.WINDSPEED_LEVEL_AUTO
            else PRESET_MODE_NORMAL
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        _LOGGER.info("Setting Sharp Cocoro Air Fan preset mode to %s", preset_mode)
        windspeed = (
            ValueSingle.WINDSPEED_LEVEL_AUTO
            if preset_mode == PRESET_MODE_AUTO
            else ValueSingle.WINDSPEED_LEVEL_4
        )
        self._device.queue_windspeed_update(windspeed)
        await self.execute_and_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        _LOGGER.info("Turning on Sharp Cocoro Air Fan")
        self._device.queue_power_on()
        opmode = self._device.get_property_status(StatusCode.OPERATION_MODE)
        if opmode:
            self._device.queue_property_status_update(opmode)
        await self.execute_and_refresh()

    async def execute_and_refresh(self) -> None:
        """Execute queued updates and schedule a debounced refresh."""
        _LOGGER.info(
            "Executing updates for Sharp Cocoro Air Fan: %s",
            self._device.property_updates,
        )

        try:
            await self._cocoro.execute_queued_updates(self._device)
            # Schedule debounced refresh
            await self._debounced_refresh()

        except Exception as e:
            _LOGGER.error("Failed to execute updates: %s", e)

            # Try to re-authenticate on authentication errors
            if (
                "401" in str(e)
                or "unauthorized" in str(e).lower()
                or "authentication" in str(e).lower()
            ):
                _LOGGER.info(
                    "Authentication error during execute, attempting to re-login"
                )
                try:
                    await self._cocoro_data.async_login()
                    # Retry the operation after re-authentication
                    await self._cocoro.execute_queued_updates(self._device)
                    await self._debounced_refresh()
                    _LOGGER.info(
                        "Successfully executed updates after re-authentication"
                    )

                except Exception as retry_error:
                    _LOGGER.error(
                        "Failed to execute updates after re-authentication: %s",
                        retry_error,
                    )
                    # Clear the queued updates to prevent them from piling up
                    self._device.property_updates.clear()
            else:
                # For non-authentication errors, clear the queue to prevent issues
                _LOGGER.error(
                    "Non-authentication error during execute, clearing update queue"
                )
                self._device.property_updates.clear()
