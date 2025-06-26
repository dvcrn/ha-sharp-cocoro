
from sharp_cocoro import Aircon
from sharp_cocoro import Cocoro

from . import SharpCocoroData
from .const import DOMAIN

from homeassistant.components.climate import PRECISION_TENTHS
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Sharp Cocoro Air fan platform."""
    cocoro_device = entry.runtime_data
    assert isinstance(cocoro_device, SharpCocoroData)

    async_add_entities([SharpCocoroSensor(cocoro_device)])


class SharpCocoroSensor(SensorEntity):
    """Representation of a Sharp Cocoro Air fan."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = PRECISION_TENTHS

    @property
    def _device(self) -> Aircon:
        return self._cocoro_data.device

    @property
    def _cocoro(self) -> Cocoro:
        return self._cocoro_data.cocoro

    def __init__(self, cocoro_device: SharpCocoroData):
        """Initialize the fan."""
        self._cocoro_data = cocoro_device

        # Initialize other necessary attributes
        # concat device_id and "fan"
        self.name = self._device.name + " Temperature"
        self.unique_id = str(self._device.device_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
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
        print("handle device update called", event)
        device_id = event.data.get("device_id")
        if device_id == self._device.device_id:
            # await self.async_update_ha_state()
            self.async_write_ha_state()

    @property
    def native_value(self):
        return self._device.get_room_temperature()
