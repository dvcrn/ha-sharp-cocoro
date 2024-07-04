from typing import Any
import asyncio

from .const import DOMAIN
from . import SharpCocoroData
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
    HVACAction,
    PRECISION_WHOLE,
    PRECISION_TENTHS,
    SWING_ON,
    SWING_OFF,
    SWING_VERTICAL,
    FAN_ON, 
    FAN_OFF , 
    FAN_AUTO , 
    FAN_LOW , 
    FAN_MEDIUM , 
    FAN_HIGH , 
    FAN_TOP , 
    FAN_MIDDLE , 
    FAN_FOCUS ,  
    FAN_DIFFUSE 
)

from homeassistant.components.fan import FanEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from sharp_cocoro import Cocoro, Aircon, SinglePropertyStatus
from sharp_cocoro.properties import SingleProperty
from sharp_cocoro.devices.aircon.aircon_properties import ValueSingle, StatusCode, FanDirection


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
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
    FanDirection.FAN_DIRECTION_SWING: "Swing"
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
    HVACMode.FAN_ONLY
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
    _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = PRECISION_TENTHS
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_hvac_modes = HVAC_MODES
    # _attr_swing_modes = SWING_MODES

    @property
    def _device(self) -> Aircon:
        return self._cocoro_data.device

    @property
    def _cocoro(self) -> Cocoro:
        return self._cocoro_data.cocoro

    def __init__(self, cocoro_data: SharpCocoroData):
        """Initialize the fan."""
        self._cocoro_data = cocoro_data

        self.name = self._device.name
        self.unique_id = str(self._device.device_id)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.maker,
            model=self._device.model,
            serial_number=self._device.serial_number
        )

        # windspeed = self._device.get_property(StatusCode.WINDSPEED)
        # assert isinstance(windspeed, SingleProperty) 

        # turn into a map for easier access
        # self._windspeed = windspeed.code_map

        # self._attr_fan_modes = list(self._windspeed.values()) 
        self._attr_swing_modes = list(FANDIRECTION_SWING_MAPPING.values())  

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

    async def async_set_temperature(self, temperature, **kwargs: Any) -> None:
        print("set tmep mode")
        print(kwargs)
        print(temperature)

         # check type of temperature, convert to float if it isn't
        if not isinstance(temperature, float):
            temperature = float(temperature)

        self._device.queue_temperature_update(temperature)
        self._device.queue_power_on()
        opmode = self._device.get_property_status(StatusCode.OPERATION_MODE)
        if opmode:
            self._device.queue_property_status_update(opmode)

        print(await self._cocoro.execute_queued_updates(self._device))

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        print('async set swing mode', swing_mode)
        # reverse find swing mode from direction mapping
        target_mode = next(
            (k for k, v in FANDIRECTION_SWING_MAPPING.items() if v == swing_mode), None
        )
        print("swing target mode: ", target_mode)

        self._device.queue_fan_direction_update(target_mode.value)
        print(await self.execute_and_refresh())

    async def async_turn_on(self, **kwargs: Any) -> None:
        print("turn on")
        temp = self._device.get_temperature()

        self._device.queue_power_on()
        self._device.queue_temperature_update(temp)
        opmode = self._device.get_property_status(StatusCode.OPERATION_MODE)
        if opmode:
            self._device.queue_property_status_update(opmode)

        await self.execute_and_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._device.queue_power_off()
        await self.execute_and_refresh()

    def toggle(self) -> None:
        pass

    @property 
    def supported_features(self) -> int:
        """Return the list of supported features."""
        print("supported features...?")
        operation_mode = self._device.get_operation_mode()

        if operation_mode in [
            ValueSingle.OPERATION_AUTO,
            ValueSingle.OPERATION_DEHUMIDIFY,
            ValueSingle.OPERATION_VENTILATION,
        ]:
            return SUPPORTED_FEATURES_NO_TEMPERATURE
            
        return SUPPORTED_FEATURES

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> HVACMode | None:
        operation_mode = self._device.get_operation_mode()

        print("operation mode -- " + str(operation_mode))

        if self._device.get_power_status() == ValueSingle.POWER_OFF:
            return HVACMode.OFF

        # switch on operation_mode
        if operation_mode == ValueSingle.OPERATION_HEAT:
            return HVACMode.HEAT
        elif operation_mode == ValueSingle.OPERATION_COOL:
            return HVACMode.COOL
        elif operation_mode == ValueSingle.OPERATION_AUTO:
            return HVACMode.AUTO
        elif operation_mode == ValueSingle.OPERATION_DEHUMIDIFY:
            return HVACMode.DRY
        elif operation_mode == ValueSingle.OPERATION_VENTILATION:
            return HVACMode.FAN_ONLY

        return HVACMode.AUTO

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._device.queue_power_on()
        self._device.queue_temperature_update(self._device.get_temperature())

        if hvac_mode == HVACMode.HEAT:
            self._device.queue_operation_mode_update(ValueSingle.OPERATION_HEAT)
        elif hvac_mode == HVACMode.COOL:
            self._device.queue_operation_mode_update(ValueSingle.OPERATION_COOL)
        elif hvac_mode == HVACMode.AUTO:
            self._device.queue_operation_mode_update(ValueSingle.OPERATION_AUTO)
        elif hvac_mode == HVACMode.DRY:
            self._device.queue_operation_mode_update(ValueSingle.OPERATION_DEHUMIDIFY)
        elif hvac_mode == HVACMode.FAN_ONLY:
            self._device.queue_operation_mode_update(ValueSingle.OPERATION_VENTILATION)
        elif hvac_mode == HVACMode.OFF:
            self._device.queue_power_off()

        # self._device.queue_operation_mode_update(ValueSingle.OPERATION_OTHER)
        await self.execute_and_refresh()


    @property
    def hvac_action(self) -> HVACAction | None:
        if self._device.get_power_status() == ValueSingle.POWER_OFF:
            return HVACAction.OFF

        operation_mode = self._device.get_operation_mode()
        operation_mode_property = self._device.get_property(StatusCode.OPERATION_MODE)
        assert isinstance(operation_mode_property, SingleProperty)

        # return next(
        #     (
        #         v['name']
        #         for v in operation_mode_property.valueSingle
        #         if v["code"] == operation_mode.value
        #     )
        # )


        # switch on operation_mode
        if operation_mode == ValueSingle.OPERATION_HEAT:
            return HVACAction.HEATING
        elif operation_mode == ValueSingle.OPERATION_COOL:
            return HVACAction.COOLING
        elif operation_mode == ValueSingle.OPERATION_DEHUMIDIFY:
            return HVACAction.DRYING
        elif operation_mode == ValueSingle.OPERATION_VENTILATION:
            return HVACAction.FAN
        elif operation_mode == ValueSingle.OPERATION_AUTO:
            return HVACAction.IDLE
        elif operation_mode == ValueSingle.OPERATION_OTHER:
            return HVACAction.FAN

        return HVACAction.OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        print("current temp -- " + str(self._device.get_room_temperature()))
        return self._device.get_room_temperature()

    @property
    def target_temperature(self) -> float | None:
        print("target temp -- " + str(self._device.get_state8().temperature))
        """Return the temperature we try to reach."""
        return self._device.get_state8().temperature

    @property
    def target_temperature_step(self) -> float | None:
        """Return the supported step of target temperature."""
        return 0.5

    @property
    def fan_mode(self) -> str | None:
        windspeed = self._device.get_windspeed()
        print("windspeed -- ", windspeed.name)

        # find in windspeed values
        # return self._windspeed[windspeed.value]

        return WINDSPEED_FANMODE_MAPPING[windspeed.value]

        # if windspeed == ValueSingle.NANOE_ON:
        #     return FAN_AUTO
        if windspeed == ValueSingle.WINDSPEED_LEVEL_AUTO:
            return FAN_AUTO
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_1:
            return FAN_LOW
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_2:
            return FAN_LOW
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_3:
            return FAN_MEDIUM
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_4:
            return FAN_MEDIUM
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_5:
            return FAN_MEDIUM
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_6:
            return FAN_HIGH
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_7:
            return FAN_HIGH
        elif windspeed == ValueSingle.WINDSPEED_LEVEL_8:
            return FAN_HIGH

        return FAN_AUTO

    async def async_handle_set_fan_mode_service(self, fan_mode: str) -> None:
        self._device.queue_windspeed_update(FANMODE_WINDSPEED_MAPPING[fan_mode])
        await self.execute_and_refresh()

    @property
    def swing_mode(self) -> str | None:
        swing_status = self._device.get_fan_direction()
        print("swing status -- ", swing_status)
        return FANDIRECTION_SWING_MAPPING[swing_status.value]

    async def execute_and_refresh(self) -> None:
        """Execute queued updates and refresh state."""
        print("execute and refresh", self._device.property_updates)
        await self._cocoro.execute_queued_updates(self._device)
        await asyncio.sleep(5)
        await self._cocoro_data.async_refresh_data()
