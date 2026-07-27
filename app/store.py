from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

from .config import Settings
from .models import CapabilityProfile, Opportunity, PackArtifact, WatchItem


class JsonStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._seed_if_missing()

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def _read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        with self._lock:
            return json.loads(path.read_text())

    def _write(self, name: str, value: Any) -> None:
        path = self._path(name)
        payload = json.dumps(value, indent=2, default=str) + "\n"
        with self._lock:
            with NamedTemporaryFile("w", dir=self.root, delete=False) as handle:
                handle.write(payload)
                tmp = Path(handle.name)
            os.replace(tmp, path)

    def _seed_if_missing(self) -> None:
        seed_dir = Path(__file__).parent / "data"
        for source_name, dest_name in [
            ("seed_profile.json", "profile"),
            ("seed_opportunities.json", "opportunities"),
            ("seed_watch.json", "watch"),
        ]:
            destination = self._path(dest_name)
            if not destination.exists():
                destination.write_text((seed_dir / source_name).read_text())
        for empty in ["packs", "audit", "replays"]:
            if not self._path(empty).exists():
                self._write(empty, [])

    def get_profile(self) -> CapabilityProfile:
        return CapabilityProfile.model_validate(self._read("profile", {}))

    def save_profile(self, profile: CapabilityProfile) -> CapabilityProfile:
        self._write("profile", profile.model_dump(mode="json"))
        return profile

    def list_opportunities(self) -> list[Opportunity]:
        return [Opportunity.model_validate(item) for item in self._read("opportunities", [])]

    def save_opportunities(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        deduped = {item.id: item for item in self.list_opportunities()}
        deduped.update({item.id: item for item in opportunities})
        ordered = sorted(deduped.values(), key=lambda item: (item.deadline is None, item.deadline or date.max))
        self._write("opportunities", [item.model_dump(mode="json") for item in ordered])
        return ordered

    def list_packs(self) -> list[PackArtifact]:
        return [PackArtifact.model_validate(item) for item in self._read("packs", [])]

    def save_pack(self, pack: PackArtifact) -> PackArtifact:
        items = self.list_packs()
        items = [item for item in items if item.id != pack.id] + [pack]
        self._write("packs", [item.model_dump(mode="json") for item in items])
        return pack

    def get_pack(self, pack_id: str) -> PackArtifact | None:
        return next((item for item in self.list_packs() if item.id == pack_id), None)

    def list_watch(self) -> list[WatchItem]:
        return [WatchItem.model_validate(item) for item in self._read("watch", [])]

    def save_watch(self, item: WatchItem) -> WatchItem:
        items = [existing for existing in self.list_watch() if existing.id != item.id] + [item]
        self._write("watch", [existing.model_dump(mode="json") for existing in items])
        return item

    def append_audit(self, event: dict[str, Any]) -> None:
        events = self._read("audit", [])
        events.append(event)
        self._write("audit", events[-1000:])

    def has_replay(self, replay_key: str) -> bool:
        return replay_key in self._read("replays", [])

    def record_replay(self, replay_key: str) -> None:
        keys = self._read("replays", [])
        if replay_key not in keys:
            keys.append(replay_key)
            self._write("replays", keys[-10000:])
