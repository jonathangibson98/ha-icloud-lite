from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_COLLECTIONS, EVENT_PHOTO, MANIFEST_FILE, PHOTO_DIR


def _read_manifest() -> list[dict]:
    try:
        return json.loads((Path(PHOTO_DIR) / MANIFEST_FILE).read_text())
    except (FileNotFoundError, ValueError):
        return []


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    known: set[str] = set()

    async def _sync(event=None) -> None:
        """Add entities for any collection the add-on knows about that we don't."""
        collections = await hass.async_add_executor_job(_read_manifest)
        new = []
        for c in collections:
            key = f"{c['slug']}_{c['orientation']}"
            if key in known:
                continue
            known.add(key)
            new.append(PhotoPullerImage(hass, entry, c["slug"], c["name"], c["orientation"]))
        if new:
            async_add_entities(new)

    await _sync()
    entry.async_on_unload(hass.bus.async_listen(EVENT_COLLECTIONS, _sync))
    entry.async_on_unload(hass.bus.async_listen(EVENT_PHOTO, _sync))


class PhotoPullerImage(ImageEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_content_type = "image/jpeg"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, slug: str, name: str, orientation: str
    ) -> None:
        super().__init__(hass)
        self._slug = slug
        self._orientation = orientation
        base = f"{slug}_{orientation}"
        self._path = Path(PHOTO_DIR) / f"{base}.jpg"
        self._meta_path = Path(PHOTO_DIR) / f"{base}.json"
        self._attr_unique_id = f"{entry.entry_id}_{base}"
        self._attr_name = orientation.capitalize()
        self._attr_extra_state_attributes = {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{slug}")},
            name=f"{name} Photos",
            manufacturer="Unsplash",
        )

    def _load_initial(self):
        mtime = None
        meta = {}
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            pass
        try:
            meta = json.loads(self._meta_path.read_text())
        except (FileNotFoundError, ValueError):
            pass
        return mtime, meta

    def _read(self):
        try:
            return self._path.read_bytes()
        except FileNotFoundError:
            return None

    def _apply_meta(self, meta: dict) -> None:
        self._attr_extra_state_attributes = {
            "photographer": meta.get("photographer"),
            "photo_url": meta.get("photo_url"),
            "search_term": meta.get("search_term"),
        }

    async def async_added_to_hass(self) -> None:
        mtime, meta = await self.hass.async_add_executor_job(self._load_initial)
        if mtime:
            self._attr_image_last_updated = dt_util.utc_from_timestamp(mtime)
        self._apply_meta(meta)
        self.async_on_remove(self.hass.bus.async_listen(EVENT_PHOTO, self._handle_event))

    @callback
    def _handle_event(self, event) -> None:
        if (
            event.data.get("slug") != self._slug
            or event.data.get("orientation") != self._orientation
        ):
            return
        self._apply_meta(event.data)
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return await self.hass.async_add_executor_job(self._read)
