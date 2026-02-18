"""Sensor platform for Sharp Cocoro Air."""

from typing import TYPE_CHECKING

from sharp_cocoro import Cocoro
from sharp_cocoro.properties import RangePropertyStatus, SinglePropertyStatus

from . import SharpCocoroData
from .const import DOMAIN

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.const import PRECISION_TENTHS
from homeassistant.const import UnitOfEnergy
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

if TYPE_CHECKING:
    from sharp_cocoro import Aircon

# Status codes from the Sharp Cocoro API
STATUS_CODE_ROOM_TEMPERATURE = "BB"
STATUS_CODE_HUMIDITY = "BA"
STATUS_CODE_POWER = "84"
STATUS_CODE_ENERGY = "85"
STATUS_CODE_ERROR_STATUS = "88"
STATUS_CODE_SPECIAL_STATUS = "AA"

# Special status values (AA)
SPECIAL_STATUS_MAP = {
    "40": "Normal",
    "41": "Defrosting",
    "42": "Preheating",
    "43": "Exhaust",
}

# Error status values (88)
ERROR_STATUS_MAP = {
    "41": "Error",
    "42": "No Error",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Sharp Cocoro Air sensor platform."""
    cocoro_data = entry.runtime_data
    assert isinstance(cocoro_data, SharpCocoroData)

    entities = []
    for device_index in range(len(cocoro_data.devices)):
        # Temperature sensor (always available)
        entities.append(SharpCocoroTemperatureSensor(cocoro_data, device_index))
        # Humidity sensor
        entities.append(SharpCocoroHumiditySensor(cocoro_data, device_index))
        # Power sensor
        entities.append(SharpCocoroPowerSensor(cocoro_data, device_index))
        # Energy sensor
        entities.append(SharpCocoroEnergySensor(cocoro_data, device_index))
        # Special status sensor (defrost, preheat, etc.)
        entities.append(SharpCocoroSpecialStatusSensor(cocoro_data, device_index))
        # Error status sensor
        entities.append(SharpCocoroErrorStatusSensor(cocoro_data, device_index))

    async_add_entities(entities)


class SharpCocoroBaseSensor(SensorEntity):
    """Base class for Sharp Cocoro sensors."""

    _attr_has_entity_name = True

    @property
    def _device(self) -> "Aircon":
        return self._cocoro_data.devices[self._device_index]  # type: ignore[return-value]

    @property
    def _cocoro(self) -> Cocoro:
        return self._cocoro_data.cocoro

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int, sensor_type: str):
        """Initialize the sensor."""
        self._cocoro_data = cocoro_data
        self._device_index = device_index
        self._sensor_type = sensor_type

        self._attr_unique_id = f"{self._device.device_id}_{sensor_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self._device.device_id))},
            name=self._device.name,
            manufacturer=self._device.maker,
            model=self._device.model,
            serial_number=self._device.serial_number,
        )

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

    def _get_range_value(self, status_code: str) -> int | float | None:
        """Get a range value from the device properties."""
        prop_status = self._device.get_property_status(status_code)
        if prop_status is None:
            return None
        if isinstance(prop_status, RangePropertyStatus):
            code = prop_status.valueRange.get("code")
            if code is not None:
                try:
                    return int(code)
                except ValueError:
                    try:
                        return float(code)
                    except ValueError:
                        return None
        return None


class SharpCocoroTemperatureSensor(SharpCocoroBaseSensor):
    """Temperature sensor for Sharp Cocoro Air."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = int(PRECISION_TENTHS)
    _attr_translation_key = "temperature"

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int):
        """Initialize the temperature sensor."""
        super().__init__(cocoro_data, device_index, "temperature")
        self._attr_name = f"{self._device.name} Temperature"

    @property
    def native_value(self) -> float | None:  # type: ignore[override]
        """Return the current temperature."""
        temp = self._device.get_room_temperature()
        # Filter out invalid values (device returns garbage when off)
        if temp is None or temp < -40 or temp > 60:
            return None
        return temp


class SharpCocoroHumiditySensor(SharpCocoroBaseSensor):
    """Humidity sensor for Sharp Cocoro Air."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "humidity"

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int):
        """Initialize the humidity sensor."""
        super().__init__(cocoro_data, device_index, "humidity")
        self._attr_name = f"{self._device.name} Humidity"

    @property
    def native_value(self) -> int | float | None:  # type: ignore[override]
        """Return the current humidity."""
        humidity = self._get_range_value(STATUS_CODE_HUMIDITY)
        # Filter out invalid values (device returns garbage when off)
        if humidity is None or humidity < 0 or humidity > 100:
            return None
        return humidity


class SharpCocoroPowerSensor(SharpCocoroBaseSensor):
    """Power consumption sensor for Sharp Cocoro Air."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "power"

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int):
        """Initialize the power sensor."""
        super().__init__(cocoro_data, device_index, "power")
        self._attr_name = f"{self._device.name} Power"

    @property
    def native_value(self) -> int | float | None:  # type: ignore[override]
        """Return the current power consumption."""
        return self._get_range_value(STATUS_CODE_POWER)


class SharpCocoroEnergySensor(SharpCocoroBaseSensor):
    """Energy consumption sensor for Sharp Cocoro Air."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "energy"

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int):
        """Initialize the energy sensor."""
        super().__init__(cocoro_data, device_index, "energy")
        self._attr_name = f"{self._device.name} Energy"

    @property
    def native_value(self) -> float | None:  # type: ignore[override]
        """Return the cumulative energy consumption."""
        value = self._get_range_value(STATUS_CODE_ENERGY)
        if value is not None:
            # Convert from Wh to kWh (the API returns in 0.001 kWh increments)
            return float(value) * 0.001
        return None


class SharpCocoroSpecialStatusSensor(SharpCocoroBaseSensor):
    """Special status sensor for Sharp Cocoro Air (defrost, preheat, etc.)."""

    _attr_translation_key = "special_status"
    _attr_icon = "mdi:information-outline"

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int):
        """Initialize the special status sensor."""
        super().__init__(cocoro_data, device_index, "special_status")
        self._attr_name = f"{self._device.name} Status"

    @property
    def native_value(self) -> str | None:  # type: ignore[override]
        """Return the special status."""
        prop_status = self._device.get_property_status(STATUS_CODE_SPECIAL_STATUS)
        if prop_status is None:
            return None
        if isinstance(prop_status, SinglePropertyStatus):
            code = prop_status.valueSingle.get("code")
            if code is None:
                # null means normal operation (not in any special state)
                return SPECIAL_STATUS_MAP.get("40", "Normal")
            return SPECIAL_STATUS_MAP.get(code, f"Unknown ({code})")
        return None


class SharpCocoroErrorStatusSensor(SharpCocoroBaseSensor):
    """Error status sensor for Sharp Cocoro Air."""

    _attr_translation_key = "error_status"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, cocoro_data: SharpCocoroData, device_index: int):
        """Initialize the error status sensor."""
        super().__init__(cocoro_data, device_index, "error_status")
        self._attr_name = f"{self._device.name} Error Status"

    @property
    def native_value(self) -> str | None:  # type: ignore[override]
        """Return the error status."""
        prop_status = self._device.get_property_status(STATUS_CODE_ERROR_STATUS)
        if prop_status is None:
            return None
        if isinstance(prop_status, SinglePropertyStatus):
            code = prop_status.valueSingle.get("code")
            if code is not None:
                return ERROR_STATUS_MAP.get(code, f"Unknown ({code})")
        return None
