"""One device_tracker per device you picked. Home Assistant's own zones do the rest."""
from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ICloudLiteCoordinator
from .const import CONF_DEVICES, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ICloudLiteCoordinator = entry.runtime_data
    selected: list[str] = entry.options.get(CONF_DEVICES, [])

    # Remove trackers for devices you un-picked
    registry = er.async_get(hass)
    keep = {f"{DOMAIN}_{dev_id}" for dev_id in selected}
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if ent.unique_id not in keep:
            registry.async_remove(ent.entity_id)

    async_add_entities(
        ICloudLiteTracker(coordinator, dev_id)
        for dev_id in selected
        if dev_id in coordinator.data
    )


class ICloudLiteTracker(CoordinatorEntity[ICloudLiteCoordinator], TrackerEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:cellphone"

    def __init__(self, coordinator: ICloudLiteCoordinator, dev_id: str) -> None:
        super().__init__(coordinator)
        self._dev_id = dev_id
        info = coordinator.data[dev_id]
        self._attr_unique_id = f"{DOMAIN}_{dev_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id)},
            name=info["name"],
            model=info["model"],
            manufacturer="Apple",
        )

    @property
    def _info(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._dev_id, {})

    @property
    def _loc(self) -> dict[str, Any] | None:
        return self._info.get("location")

    @property
    def available(self) -> bool:
        return super().available and self._loc is not None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self._loc.get("latitude") if self._loc else None

    @property
    def longitude(self) -> float | None:
        return self._loc.get("longitude") if self._loc else None

    @property
    def location_accuracy(self) -> int:
        return int(self._loc.get("horizontalAccuracy") or 0) if self._loc else 0

    @property
    def battery_level(self) -> int | None:
        level = self._info.get("battery")
        return int(level * 100) if level is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "battery_status": self._info.get("battery_status"),
            "location_timestamp": self._loc.get("timeStamp") if self._loc else None,
        }
