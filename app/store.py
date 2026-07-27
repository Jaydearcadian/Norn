from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

from .config import Settings
from .digests import sha256_digest
from .models import CapabilityProfile, Opportunity, PackArtifact, SourceSnapshot, WatchItem


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, canonical_url TEXT NOT NULL, issuer TEXT, source_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_snapshots (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), url TEXT NOT NULL,
  source_type TEXT NOT NULL, page_type TEXT NOT NULL, retrieved_at TEXT NOT NULL,
  published_at TEXT, content_digest TEXT NOT NULL, content_type TEXT NOT NULL,
  http_status INTEGER NOT NULL, issuer TEXT, title TEXT, raw_body BLOB,
  UNIQUE(source_id, content_digest)
);
CREATE TABLE IF NOT EXISTS programmes (
  id TEXT PRIMARY KEY, issuer TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(issuer, name)
);
CREATE TABLE IF NOT EXISTS opportunities (
  canonical_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, current_version INTEGER NOT NULL,
  title TEXT NOT NULL, issuer TEXT NOT NULL, programme_id TEXT, lifecycle_status TEXT NOT NULL,
  review_status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunity_versions (
  canonical_id TEXT NOT NULL REFERENCES opportunities(canonical_id), version INTEGER NOT NULL,
  payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL, changed_fields_json TEXT NOT NULL,
  normalization_run_id TEXT, created_at TEXT NOT NULL,
  PRIMARY KEY(canonical_id, version), UNIQUE(canonical_id, payload_digest)
);
CREATE TABLE IF NOT EXISTS requirements (
  canonical_id TEXT NOT NULL, opportunity_version INTEGER NOT NULL, requirement_id TEXT NOT NULL,
  category TEXT NOT NULL, statement TEXT NOT NULL, mandatory INTEGER NOT NULL,
  source_snapshot_id TEXT, confidence REAL NOT NULL, interpretation TEXT NOT NULL,
  payload_json TEXT NOT NULL, PRIMARY KEY(canonical_id, opportunity_version, requirement_id)
);
CREATE TABLE IF NOT EXISTS opportunity_sources (
  canonical_id TEXT NOT NULL, opportunity_version INTEGER NOT NULL, source_snapshot_id TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'supporting', PRIMARY KEY(canonical_id, opportunity_version, source_snapshot_id)
);
CREATE TABLE IF NOT EXISTS normalization_runs (
  id TEXT PRIMARY KEY, adapter TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
  status TEXT NOT NULL, input_count INTEGER NOT NULL DEFAULT 0, output_count INTEGER NOT NULL DEFAULT 0,
  review_count INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS profile_versions (
  profile_id TEXT NOT NULL, version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  payload_digest TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(profile_id, version)
);
CREATE TABLE IF NOT EXISTS assessments (
  profile_id TEXT NOT NULL, profile_version INTEGER NOT NULL, canonical_id TEXT NOT NULL,
  opportunity_version INTEGER NOT NULL, engine_version TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(profile_id, profile_version, canonical_id, opportunity_version, engine_version)
);
CREATE TABLE IF NOT EXISTS review_queue (
  id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, opportunity_version INTEGER NOT NULL,
  reason TEXT NOT NULL, fields_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS watch_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL, event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


class JsonStore:
    """Compatibility facade: JSON for user artefacts, SQLite for compiled opportunity truth."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.db_path = self.root / "norn.sqlite3"
        self._init_db()
        self._seed_if_missing()
        self._migrate_seed_opportunities()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

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
        for source_name, dest_name in [("seed_profile.json", "profile"), ("seed_watch.json", "watch")]:
            destination = self._path(dest_name)
            if not destination.exists():
                destination.write_text((seed_dir / source_name).read_text())
        for empty in ["packs", "audit", "replays"]:
            if not self._path(empty).exists():
                self._write(empty, [])

    def _migrate_seed_opportunities(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        if count:
            return
        seed = Path(__file__).parent / "data" / "seed_opportunities.json"
        if seed.exists():
            self.save_opportunities([Opportunity.model_validate(item) for item in json.loads(seed.read_text())])

    def get_profile(self) -> CapabilityProfile:
        return CapabilityProfile.model_validate(self._read("profile", {}))

    def save_profile(self, profile: CapabilityProfile) -> CapabilityProfile:
        previous = self.get_profile() if self._path("profile").exists() else None
        profile.version = (previous.version + 1) if previous else 1
        self._write("profile", profile.model_dump(mode="json"))
        payload = profile.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO profile_versions VALUES (?, ?, ?, ?, ?)",
                (profile.id, profile.version, json.dumps(payload), sha256_digest(payload), datetime.now(timezone.utc).isoformat()),
            )
        return profile

    @staticmethod
    def opportunity_fingerprint(item: Opportunity) -> str:
        identity = {
            "issuer": item.issuer.strip().lower(), "programme": (item.programme or item.title).strip().lower(),
            "cycle": (item.cycle or "").strip().lower(), "track": (item.track or "").strip().lower(),
            "deadline": str(item.deadline or ""), "applicationUrl": str(item.applicationUrl or item.sourceUrl),
        }
        return sha256_digest(identity)

    @staticmethod
    def _changed_fields(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
        ignored = {"version", "changedFields", "sourceTimestamp", "lastVerifiedAt"}
        return sorted(key for key in set(previous) | set(current) if key not in ignored and previous.get(key) != current.get(key))

    def list_opportunities(self) -> list[Opportunity]:
        query = """
        SELECT v.payload_json FROM opportunities o
        JOIN opportunity_versions v ON v.canonical_id=o.canonical_id AND v.version=o.current_version
        ORDER BY json_extract(v.payload_json, '$.deadline') IS NULL,
                 json_extract(v.payload_json, '$.deadline')
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [Opportunity.model_validate_json(row[0]) for row in rows]

    def get_opportunity_history(self, canonical_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT version, payload_digest, changed_fields_json, created_at FROM opportunity_versions WHERE canonical_id=? ORDER BY version DESC",
                (canonical_id,),
            ).fetchall()
        return [dict(version=row[0], payloadDigest=row[1], changedFields=json.loads(row[2]), createdAt=row[3]) for row in rows]

    def save_opportunities(self, opportunities: list[Opportunity], normalization_run_id: str | None = None) -> list[Opportunity]:
        stamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            for item in opportunities:
                fingerprint = item.canonicalFingerprint or self.opportunity_fingerprint(item)
                item.canonicalFingerprint = fingerprint
                existing = connection.execute(
                    "SELECT canonical_id, current_version FROM opportunities WHERE fingerprint=? OR canonical_id=?",
                    (fingerprint, item.canonicalId or item.id),
                ).fetchone()
                canonical_id = existing[0] if existing else (item.canonicalId or item.id)
                previous_payload: dict[str, Any] = {}
                current_version = 0
                if existing:
                    current_version = existing[1]
                    previous_row = connection.execute(
                        "SELECT payload_json FROM opportunity_versions WHERE canonical_id=? AND version=?",
                        (canonical_id, current_version),
                    ).fetchone()
                    previous_payload = json.loads(previous_row[0]) if previous_row else {}
                item.canonicalId = canonical_id
                candidate = item.model_dump(mode="json")
                candidate["version"] = current_version + 1
                candidate["changedFields"] = self._changed_fields(previous_payload, candidate) if existing else []
                payload_digest = sha256_digest({k: v for k, v in candidate.items() if k not in {"version", "changedFields", "sourceTimestamp", "lastVerifiedAt"}})
                duplicate = connection.execute(
                    "SELECT version FROM opportunity_versions WHERE canonical_id=? AND payload_digest=?",
                    (canonical_id, payload_digest),
                ).fetchone()
                if duplicate:
                    continue
                item.version = current_version + 1
                item.changedFields = candidate["changedFields"]
                candidate = item.model_dump(mode="json")
                programme_id = None
                if item.programme:
                    programme_id = "programme_" + sha256_digest({"issuer": item.issuer.lower(), "name": item.programme.lower()})[:20]
                    connection.execute(
                        "INSERT OR IGNORE INTO programmes VALUES (?, ?, ?, ?)",
                        (programme_id, item.issuer, item.programme, stamp),
                    )
                connection.execute(
                    "INSERT INTO opportunities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(canonical_id) DO UPDATE SET current_version=excluded.current_version, title=excluded.title, issuer=excluded.issuer, programme_id=excluded.programme_id, lifecycle_status=excluded.lifecycle_status, review_status=excluded.review_status, updated_at=excluded.updated_at",
                    (canonical_id, fingerprint, item.version, item.title, item.issuer, programme_id, item.lifecycleStatus, item.reviewStatus, stamp, stamp),
                )
                connection.execute(
                    "INSERT INTO opportunity_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (canonical_id, item.version, json.dumps(candidate, default=str), payload_digest, json.dumps(item.changedFields), normalization_run_id, stamp),
                )
                for requirement in [*item.eligibility, *item.requirements, *item.deliverables]:
                    connection.execute(
                        "INSERT OR REPLACE INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (canonical_id, item.version, requirement.id, requirement.category, requirement.statement, int(requirement.mandatory), requirement.sourceSnapshotId, requirement.confidence, requirement.interpretation.value, requirement.model_dump_json()),
                    )
                for snapshot_id in item.sourceSnapshotIds:
                    connection.execute(
                        "INSERT OR IGNORE INTO opportunity_sources VALUES (?, ?, ?, 'supporting')",
                        (canonical_id, item.version, snapshot_id),
                    )
                if item.reviewStatus == "pending":
                    review_id = "review_" + sha256_digest({"id": canonical_id, "version": item.version})[:20]
                    connection.execute(
                        "INSERT OR IGNORE INTO review_queue VALUES (?, ?, ?, ?, ?, 'pending', '', ?, NULL)",
                        (review_id, canonical_id, item.version, "Low-confidence or incomplete normalization", json.dumps(self.review_fields(item)), stamp),
                    )
        return self.list_opportunities()

    @staticmethod
    def review_fields(item: Opportunity) -> list[str]:
        fields = []
        if item.normalizationConfidence < 0.75: fields.append("normalizationConfidence")
        if not item.deadline: fields.append("deadline")
        if not item.requirements: fields.append("requirements")
        if item.sourceType != "official": fields.append("sourceType")
        return fields

    def save_source_snapshot(self, snapshot: SourceSnapshot, raw_body: bytes | None = None) -> SourceSnapshot:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO sources VALUES (?, ?, ?, ?, ?)",
                (snapshot.sourceId, str(snapshot.url), snapshot.issuer, snapshot.sourceType, snapshot.retrievedAt.isoformat()),
            )
            connection.execute(
                "INSERT OR IGNORE INTO source_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot.id, snapshot.sourceId, str(snapshot.url), snapshot.sourceType, snapshot.pageType, snapshot.retrievedAt.isoformat(), snapshot.publishedAt.isoformat() if snapshot.publishedAt else None, snapshot.contentDigest, snapshot.contentType, snapshot.httpStatus, snapshot.issuer, snapshot.title, raw_body),
            )
        return snapshot

    def start_normalization_run(self, adapter: str, input_count: int = 0) -> str:
        run_id = "run_" + sha256_digest({"adapter": adapter, "at": datetime.now(timezone.utc).isoformat()})[:20]
        with self._connect() as connection:
            connection.execute("INSERT INTO normalization_runs VALUES (?, ?, ?, NULL, 'running', ?, 0, 0, '')", (run_id, adapter, datetime.now(timezone.utc).isoformat(), input_count))
        return run_id

    def finish_normalization_run(self, run_id: str, output_count: int, review_count: int, notes: str = "") -> None:
        with self._connect() as connection:
            connection.execute("UPDATE normalization_runs SET completed_at=?, status='completed', output_count=?, review_count=?, notes=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), output_count, review_count, notes, run_id))

    def list_review_queue(self, status: str = "pending") -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM review_queue WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        return [{**dict(row), "fields": json.loads(row["fields_json"])} for row in rows]

    def resolve_review(self, review_id: str, status: str, notes: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("UPDATE review_queue SET status=?, notes=?, resolved_at=? WHERE id=?", (status, notes, datetime.now(timezone.utc).isoformat(), review_id))
        return cursor.rowcount > 0

    def list_packs(self) -> list[PackArtifact]:
        return [PackArtifact.model_validate(item) for item in self._read("packs", [])]

    def save_pack(self, pack: PackArtifact) -> PackArtifact:
        items = [item for item in self.list_packs() if item.id != pack.id] + [pack]
        self._write("packs", [item.model_dump(mode="json") for item in items])
        return pack

    def get_pack(self, pack_id: str) -> PackArtifact | None:
        return next((item for item in self.list_packs() if item.id == pack_id), None)

    def list_watch(self) -> list[WatchItem]:
        return [WatchItem.model_validate(item) for item in self._read("watch", [])]

    def save_watch(self, item: WatchItem) -> WatchItem:
        items = [existing for existing in self.list_watch() if existing.id != item.id] + [item]
        self._write("watch", [existing.model_dump(mode="json") for existing in items])
        with self._connect() as connection:
            connection.execute("INSERT INTO watch_events(opportunity_id,event_type,payload_json,created_at) VALUES (?, 'watch.updated', ?, ?)", (item.opportunityId, item.model_dump_json(), datetime.now(timezone.utc).isoformat()))
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
