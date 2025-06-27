"""Climate platform for Sharp Cocoro Air."""

import asyncio
import logging
from functools import wraps
from typing import Any
from typing import ClassVar

from sharp_cocoro import Aircon
from sharp_cocoro import Cocoro
from sharp_cocoro.devices.aircon.aircon_properties import FanDirection
from sharp_cocoro.devices.aircon.aircon_properties import StatusCode
from sharp_cocoro.devices.aircon.aircon_properties import ValueSingle

from . import SharpCocoroData
from .const import DOMAIN

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import FAN_AUTO
from homeassistant.components.climate.const import FAN_HIGH
from homeassistant.components.climate.const import FAN_LOW
from homeassistant.components.climate.const import FAN_MEDIUM
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.components.climate.const import HVACAction
from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Sharp Cocoro Air fan platform."""
    cocoro_device = entry.runtime_data
    assert isinstance(cocoro_device, SharpCocoroData)
    async_add_entities([SharpCocoroAircon(cocoro_device)])


FANDIRECTION_SWING_MAPPING = {
    FanDirection.FAN_DIRECTION_AUTO: "Auto",
    FanDirection.FAN_DIRECTION_1: "Top",
    FanDirection.FAN_DIRECTION_2: "High",
    FanDirection.FAN_DIRECTION_3: "Middle",
    FanDirection.FAN_DIRECTION_4: "Low",
    FanDirection.FAN_DIRECTION_5: "Bottom",
    FanDirection.FAN_DIRECTION_SWING: "Swing",
}

WINDSPEED_FANMODE_MAPPING = {
    ValueSingle.WINDSPEED_LEVEL_AUTO: FAN_AUTO,
    ValueSingle.WINDSPEED_LEVEL_1: FAN_LOW,
    ValueSingle.WINDSPEED_LEVEL_2: FAN_LOW,
    ValueSingle.WINDSPEED_LEVEL_3: FAN_MEDIUM,
    ValueSingle.WINDSPEED_LEVEL_4: FAN_MEDIUM,
    ValueSingle.WINDSPEED_LEVEL_5: FAN_MEDIUM,
    ValueSingle.WINDSPEED_LEVEL_6: FAN_HIGH,
    ValueSingle.WINDSPEED_LEVEL_7: FAN_HIGH,
    ValueSingle.WINDSPEED_LEVEL_8: FAN_HIGH,
}

FANMODE_WINDSPEED_MAPPING = {
    FAN_AUTO: ValueSingle.WINDSPEED_LEVEL_AUTO,
    FAN_LOW: ValueSingle.WINDSPEED_LEVEL_1,
    FAN_MEDIUM: ValueSingle.WINDSPEED_LEVEL_4,
    FAN_HIGH: ValueSingle.WINDSPEED_LEVEL_8,
}

HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.AUTO,
    HVACMode.FAN_ONLY,
]

SUPPORTED_FEATURES = (
    ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.SWING_MODE
)

SUPPORTED_FEATURES_NO_TEMPERATURE = (
    ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.SWING_MODE
)


class SharpCocoroAircon(ClimateEntity):
    """Representation of a Sharp Cocoro Air air conditioner."""

    _attr_fan_modes: ClassVar[list[str]] = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_hvac_modes = HVAC_MODES

    @property
    def _device(self) -> Aircon:
        return self._cocoro_data.device

    @property
    def _cocoro(self) -> Cocoro:
        return self._cocoro_data.cocoro

    def __init__(self, cocoro_data: SharpCocoroData):
        """Initialize the fan."""
        self._cocoro_data = cocoro_data

        self._attr_name = self._device.name
        self._attr_unique_id = str(self._device.device_id)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.maker,
            model=self._device.model,
            serial_number=self._device.serial_number,
        )

        self._attr_swing_modes = list(FANDIRECTION_SWING_MAPPING.values())

        # Create debounced refresh function
        self._debounced_refresh = debounce(5)(self._cocoro_data.async_refresh_data)

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._remove_listener = self.hass.bus.async_listen(
            "sharp_cocoro.device_updated", self._handle_device_update
        )

    async def _handle_device_update(self, event):
        device_id = event.data.get("device_id")
        if device_id == self._device.device_id:
            self.async_write_ha_state()

    async def async_set_temperature(self, temperature: float, **kwargs: Any) -> None:
        """Set new target temperature."""
        _LOGGER.info("Setting temperature to %s", temperature)
        temperature = float(temperature)
        self._device.queue_temperature_update(temperature)
        self._device.queue_power_on()
        opmode = self._device.get_property_status(StatusCode.OPERATION_MODE)
        if opmode:
            self._device.queue_property_status_update(opmode)
        await self.execute_and_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing mode."""
        _LOGGER.info("Setting swing mode to %s", swing_mode)
        target_mode = next(
            (k for k, v in FANDIRECTION_SWING_MAPPING.items() if v == swing_mode), None
        )
        if target_mode is not None:
            self._device.queue_fan_direction_update(target_mode.value)
            await self.execute_and_refresh()
        else:
            _LOGGER.error("Invalid swing mode: %s", swing_mode)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        _LOGGER.info("Turning on the device")
        temp = self._device.get_temperature()
        self._device.queue_power_on()
        self._device.queue_temperature_update(temp)
        opmode = self._device.get_property_status(StatusCode.OPERATION_MODE)
        if opmode:
            self._device.queue_property_status_update(opmode)
        await self.execute_and_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        _LOGGER.info("Turning off the device")
        self._device.queue_power_off()
        await self.execute_and_refresh()

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        operation_mode = self._device.get_operation_mode()
        if operation_mode in [
            ValueSingle.OPERATION_AUTO,
            ValueSingle.OPERATION_DEHUMIDIFY,
            ValueSingle.OPERATION_VENTILATION,
        ]:
            return SUPPORTED_FEATURES_NO_TEMPERATURE
        return SUPPORTED_FEATURES

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac operation ie. heat, cool mode."""
        if self._device.get_power_status() == ValueSingle.POWER_OFF:
            return HVACMode.OFF

        operation_mode = self._device.get_operation_mode()
        mode_mapping = {
            ValueSingle.OPERATION_HEAT: HVACMode.HEAT,
            ValueSingle.OPERATION_COOL: HVACMode.COOL,
            ValueSingle.OPERATION_AUTO: HVACMode.AUTO,
            ValueSingle.OPERATION_DEHUMIDIFY: HVACMode.DRY,
            ValueSingle.OPERATION_VENTILATION: HVACMode.FAN_ONLY,
        }
        return mode_mapping.get(operation_mode, HVACMode.AUTO)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        _LOGGER.info("Setting HVAC mode to %s", hvac_mode)
        self._device.queue_power_on()
        self._device.queue_temperature_update(self._device.get_temperature())

        mode_mapping = {
            HVACMode.HEAT: ValueSingle.OPERATION_HEAT,
            HVACMode.COOL: ValueSingle.OPERATION_COOL,
            HVACMode.AUTO: ValueSingle.OPERATION_AUTO,
            HVACMode.DRY: ValueSingle.OPERATION_DEHUMIDIFY,
            HVACMode.FAN_ONLY: ValueSingle.OPERATION_VENTILATION,
        }

        if hvac_mode in mode_mapping:
            self._device.queue_operation_mode_update(mode_mapping[hvac_mode])
        elif hvac_mode == HVACMode.OFF:
            self._device.queue_power_off()

        await self.execute_and_refresh()

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation if supported."""
        if self._device.get_power_status() == ValueSingle.POWER_OFF:
            return HVACAction.OFF

        operation_mode = self._device.get_operation_mode()
        action_mapping = {
            ValueSingle.OPERATION_HEAT: HVACAction.HEATING,
            ValueSingle.OPERATION_COOL: HVACAction.COOLING,
            ValueSingle.OPERATION_DEHUMIDIFY: HVACAction.DRYING,
            ValueSingle.OPERATION_VENTILATION: HVACAction.FAN,
            ValueSingle.OPERATION_AUTO: HVACAction.IDLE,
            ValueSingle.OPERATION_OTHER: HVACAction.FAN,
        }
        return action_mapping.get(operation_mode, HVACAction.OFF)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.get_room_temperature()

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        state = self._device.get_state8()
        return state.temperature if state else None

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        windspeed = self._device.get_windspeed()
        if windspeed and hasattr(windspeed, "value"):
            return WINDSPEED_FANMODE_MAPPING.get(windspeed.value, FAN_AUTO)
        return FAN_AUTO

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        _LOGGER.info("Setting fan mode to %s", fan_mode)
        self._device.queue_windspeed_update(FANMODE_WINDSPEED_MAPPING[fan_mode])
        await self.execute_and_refresh()

    @property
    def swing_mode(self) -> str | None:
        """Return the fan setting."""
        swing_status = self._device.get_fan_direction()
        if swing_status and hasattr(swing_status, "value"):
            return FANDIRECTION_SWING_MAPPING.get(swing_status.value, "Auto")
        return "Auto"

    async def execute_and_refresh(self) -> None:
        """Execute queued updates and schedule a debounced refresh."""
        _LOGGER.info(
            "Executing updates for Sharp Cocoro Aircon: %s",
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
