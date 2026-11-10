"""Group members – a command to a group also counts for its members.

* Zigbee2MQTT groups: read from ``<base_topic>/bridge/groups`` and matched to HA
  entities by their MQTT unique ids (``0x<ieee>_<object>_<base>`` for devices,
  ``<group id>_<object>_<base>`` for groups), or by device identifiers
  (``zigbee2mqtt_0x…`` / ``zigbee2mqtt_<encoded base topic>_<group id>``).
* Home Assistant groups (light / switch / cover … groups, old-style groups):
  members from the ``entity_id`` attribute.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import re
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

_LOGGER = logging.getLogger(__name__)

_DEVICE_RE = re.compile(r"^zigbee2mqtt_(0x[0-9a-fA-F]+)$")
_GROUP_RE = re.compile(r"^zigbee2mqtt_(\d+)_(\d+)$")


class GroupResolver:
    """Knows which entities belong to which group entity."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._z2m: dict[str, list[dict[str, Any]]] = {}  # base topic → groups payload
        self.members: dict[str, set[str]] = {}  # group entity → member entities
        self._report: list[dict[str, Any]] = []
        self._unsubs: list[Callable[[], None]] = []

    async def async_start(self) -> None:
        bus = self.hass.bus
        self._unsubs.append(bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._on_registry))
        self._unsubs.append(bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._on_registry))
        if "mqtt" not in self.hass.config.components:
            return
        try:
            from homeassistant.components import mqtt  # noqa: PLC0415

            if not await mqtt.async_wait_for_mqtt_client(self.hass):
                return
            self._unsubs.append(
                await mqtt.async_subscribe(self.hass, "+/bridge/groups", self._on_groups)
            )
        except Exception as err:  # noqa: BLE001 - MQTT optional
            _LOGGER.debug("Pattern Pilot: Zigbee2MQTT groups not available (%s)", err)

    def stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def _on_registry(self, _event: Event) -> None:
        if self._z2m:
            self.rebuild()

    @callback
    def _on_groups(self, msg: Any) -> None:
        try:
            groups = json.loads(msg.payload)
        except (TypeError, ValueError):
            return
        if isinstance(groups, list):
            self.set_z2m_groups(msg.topic.split("/")[0], groups)

    @callback
    def set_z2m_groups(self, base: str, groups: list[dict[str, Any]]) -> None:
        self._z2m[base] = groups
        self.rebuild()

    @callback
    def rebuild(self) -> None:
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        mqtt_entities = [e for e in ent_reg.entities.values() if e.platform == "mqtt"]

        # 1) by device identifiers
        by_ieee_dev: dict[str, str] = {}
        by_group_dev: dict[str, str] = {}
        for device in dev_reg.devices.values():
            for domain, ident in device.identifiers:
                if domain != "mqtt":
                    continue
                if m := _DEVICE_RE.match(ident):
                    by_ieee_dev[m.group(1).lower()] = device.id
                elif m := _GROUP_RE.match(ident):
                    by_group_dev[m.group(2)] = device.id

        members: dict[str, set[str]] = {}
        report: list[dict[str, Any]] = []
        for base, groups in self._z2m.items():
            # 2) by unique ids: "<id>_<object>_<base>"
            suffix = f"_{base}"
            by_ieee_uid: dict[str, list[er.RegistryEntry]] = {}
            by_group_uid: dict[str, list[er.RegistryEntry]] = {}
            for e in mqtt_entities:
                uid = str(e.unique_id or "")
                if not uid.endswith(suffix):
                    continue
                head = uid[: -len(suffix)].split("_", 1)[0]
                if head.lower().startswith("0x"):
                    by_ieee_uid.setdefault(head.lower(), []).append(e)
                elif head.isdigit():
                    by_group_uid.setdefault(head, []).append(e)

            for group in groups:
                gid = str(group.get("id"))
                ieees = [str(m.get("ieee_address", "")).lower() for m in group.get("members") or []]
                group_entities = list(by_group_uid.get(gid, []))
                if gid in by_group_dev:
                    group_entities += er.async_entries_for_device(ent_reg, by_group_dev[gid])
                member_entities: list[er.RegistryEntry] = []
                for ieee in ieees:
                    member_entities += by_ieee_uid.get(ieee, [])
                    if ieee in by_ieee_dev:
                        member_entities += er.async_entries_for_device(ent_reg, by_ieee_dev[ieee])
                mapped = 0
                for ge in {e.entity_id: e for e in group_entities}.values():
                    found = {e.entity_id for e in member_entities if e.domain == ge.domain}
                    if found:
                        members[ge.entity_id] = found
                        mapped += 1
                report.append(
                    {
                        "name": group.get("friendly_name"),
                        "members": len(ieees),
                        "group_entities": sorted({e.entity_id for e in group_entities}),
                        "member_entities": len({e.entity_id for e in member_entities}),
                        "mapped": mapped,
                    }
                )
        self.members = members
        self._report = report

    def expand(self, entity_id: str) -> set[str]:
        """Members of a group entity (Zigbee2MQTT or Home Assistant group), recursively."""
        out: set[str] = set()
        todo = [entity_id]
        while todo:
            current = todo.pop()
            found = set(self.members.get(current, ()))
            state = self.hass.states.get(current)
            if state is not None:
                attr = state.attributes.get("entity_id")
                if isinstance(attr, (list, tuple)):
                    found.update(str(e) for e in attr)
            for member in found - out - {entity_id}:
                out.add(member)
                todo.append(member)
            if len(out) > 500:
                break
        return out

    def describe(self) -> dict[str, Any]:
        return {
            "z2m_bridges": sorted(self._z2m),
            "z2m_groups": sum(len(g) for g in self._z2m.values()),
            "z2m_group_list": self._report,
            "group_entities_mapped": {k: sorted(v) for k, v in self.members.items()},
        }
