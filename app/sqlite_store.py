from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from .config import Settings
from .models import CapabilityProfile, Opportunity, PackArtifact, SourceSnapshot, WatchItem
from .normalization import change_summary, dossier_digest


class SQLiteStore:
    """SQLite source of truth for dossiers; preserves the old store interface."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "norn.sqlite3"
        self._lock = RLock()
        self._init_schema()
        self._seed_if_empty()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    def _init_schema(self) -> None:
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL,
                issuer TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_snapshots (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                content_digest TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                UNIQUE(source_id, content_digest), FOREIGN KEY(source_id) REFERENCES sources(id)
            );
            CREATE TABLE IF NOT EXISTS programmes (
                id TEXT PRIMARY KEY, issuer TEXT NOT NULL, name TEXT NOT NULL,
                cycle TEXT, parent_id TEXT, UNIQUE(issuer, name, cycle)
            );
            CREATE TABLE IF NOT EXISTS opportunities (
                id TEXT PRIMARY KEY, canonical_fingerprint TEXT NOT NULL UNIQUE,
                current_version INTEGER NOT NULL, lifecycle_status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS opportunity_versions (
                opportunity_id TEXT NOT NULL, version INTEGER NOT NULL,
                dossier_digest TEXT NOT NULL, payload_json TEXT NOT NULL,
                change_summary_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(opportunity_id, version),
                FOREIGN KEY(opportunity_id) REFERENCES opportunities(id)
            );
            CREATE TABLE IF NOT EXISTS requirements (
                opportunity_id TEXT NOT NULL, opportunity_version INTEGER NOT NULL,
                requirement_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                PRIMARY KEY(opportunity_id, opportunity_version, requirement_id)
            );
            CREATE TABLE IF NOT EXISTS opportunity_sources (
                opportunity_id TEXT NOT NULL, opportunity_version INTEGER NOT NULL,
                snapshot_id TEXT NOT NULL,
                PRIMARY KEY(opportunity_id, opportunity_version, snapshot_id)
            );
            CREATE TABLE IF NOT EXISTS normalization_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, adapter TEXT NOT NULL,
                started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL,
                stats_json TEXT NOT NULL, errors_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profile_versions (
                profile_id TEXT NOT NULL, version_digest TEXT NOT NULL,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(profile_id, version_digest)
            );
            CREATE TABLE IF NOT EXISTS assessments (
                profile_version TEXT NOT NULL, opportunity_id TEXT NOT NULL,
                opportunity_version INTEGER NOT NULL, scoring_engine_version TEXT NOT NULL,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(profile_version, opportunity_id, opportunity_version, scoring_engine_version)
            );
            CREATE TABLE IF NOT EXISTS review_queue (
                opportunity_id TEXT NOT NULL, opportunity_version INTEGER NOT NULL,
                reasons_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, reviewed_at TEXT,
                PRIMARY KEY(opportunity_id, opportunity_version)
            );
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS replays (replay_key TEXT PRIMARY KEY, created_at TEXT NOT NULL);
            """)

    def _seed_if_empty(self) -> None:
        seed_dir = Path(__file__).parent / "data"
        with self._db() as db:
            if db.execute("SELECT 1 FROM kv_store WHERE key='profile'").fetchone() is None:
                db.execute("INSERT INTO kv_store(key,payload_json) VALUES('profile',?)", ((seed_dir / "seed_profile.json").read_text(),))
            for key, filename in (("packs", "[]"), ("watch", (seed_dir / "seed_watch.json").read_text())):
                if db.execute("SELECT 1 FROM kv_store WHERE key=?", (key,)).fetchone() is None:
                    db.execute("INSERT INTO kv_store(key,payload_json) VALUES(?,?)", (key, filename))
        if not self.list_opportunities():
            seeds = [Opportunity.model_validate(item) for item in json.loads((seed_dir / "seed_opportunities.json").read_text())]
            self.save_opportunities(seeds)

    def _get_kv(self, key: str, default: Any) -> Any:
        with self._db() as db:
            row = db.execute("SELECT payload_json FROM kv_store WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set_kv(self, key: str, value: Any) -> None:
        payload = json.dumps(value, default=str)
        with self._db() as db:
            db.execute("INSERT INTO kv_store(key,payload_json) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET payload_json=excluded.payload_json", (key, payload))

    def save_snapshot(self, snapshot: SourceSnapshot, raw_text: str = "") -> SourceSnapshot:
        payload = snapshot.model_dump(mode="json")
        payload["rawText"] = raw_text
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO sources(id,url,source_type,issuer,created_at) VALUES(?,?,?,?,?)", (snapshot.sourceId, str(snapshot.url), snapshot.sourceType, snapshot.issuer, snapshot.retrievedAt.isoformat()))
            db.execute("INSERT OR IGNORE INTO source_snapshots(id,source_id,payload_json,content_digest,retrieved_at) VALUES(?,?,?,?,?)", (snapshot.id, snapshot.sourceId, json.dumps(payload), snapshot.contentDigest, snapshot.retrievedAt.isoformat()))
        return snapshot

    def list_snapshots(self, source_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT payload_json FROM source_snapshots"
        params: tuple[Any, ...] = ()
        if source_id:
            query += " WHERE source_id=?"
            params = (source_id,)
        query += " ORDER BY retrieved_at DESC"
        with self._db() as db:
            return [json.loads(row[0]) for row in db.execute(query, params).fetchall()]

    def get_profile(self) -> CapabilityProfile:
        return CapabilityProfile.model_validate(self._get_kv("profile", {}))

    def save_profile(self, profile: CapabilityProfile) -> CapabilityProfile:
        payload = profile.model_dump(mode="json")
        digest = __import__("hashlib").sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self._set_kv("profile", payload)
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO profile_versions(profile_id,version_digest,payload_json,created_at) VALUES(?,?,?,?)", (profile.id, digest, json.dumps(payload), datetime.now(timezone.utc).isoformat()))
        return profile

    def list_opportunities(self) -> list[Opportunity]:
        with self._db() as db:
            rows = db.execute("""
                SELECT v.payload_json FROM opportunities o
                JOIN opportunity_versions v ON v.opportunity_id=o.id AND v.version=o.current_version
                ORDER BY json_extract(v.payload_json,'$.deadline') IS NULL, json_extract(v.payload_json,'$.deadline')
            """).fetchall()
        return [Opportunity.model_validate(json.loads(row[0])) for row in rows]

    def save_opportunities(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            for item in opportunities:
                fingerprint = item.intelligence.canonicalFingerprint or item.id
                existing = db.execute("SELECT id,current_version FROM opportunities WHERE canonical_fingerprint=?", (fingerprint,)).fetchone()
                opportunity_id = existing["id"] if existing else item.id
                current_version = int(existing["current_version"]) if existing else 0
                previous = None
                if existing:
                    row = db.execute("SELECT payload_json,dossier_digest FROM opportunity_versions WHERE opportunity_id=? AND version=?", (opportunity_id, current_version)).fetchone()
                    previous = Opportunity.model_validate(json.loads(row["payload_json"]))
                    if row["dossier_digest"] == dossier_digest(item):
                        continue
                version = current_version + 1
                item.id = opportunity_id
                item.intelligence.version = version
                item.intelligence.changeSummary = change_summary(previous, item) if previous else ["initial dossier compiled"]
                payload = item.model_dump(mode="json")
                digest = dossier_digest(item)
                db.execute("INSERT INTO opportunities(id,canonical_fingerprint,current_version,lifecycle_status,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET current_version=excluded.current_version,lifecycle_status=excluded.lifecycle_status,updated_at=excluded.updated_at", (opportunity_id, fingerprint, version, item.intelligence.dossierStatus, now, now))
                db.execute("INSERT INTO opportunity_versions(opportunity_id,version,dossier_digest,payload_json,change_summary_json,created_at) VALUES(?,?,?,?,?,?)", (opportunity_id, version, digest, json.dumps(payload), json.dumps(item.intelligence.changeSummary), now))
                for requirement in item.requirements:
                    db.execute("INSERT INTO requirements(opportunity_id,opportunity_version,requirement_id,payload_json) VALUES(?,?,?,?)", (opportunity_id, version, requirement.id, json.dumps(requirement.model_dump(mode='json'))))
                for snapshot_id in item.intelligence.sourceSnapshotIds:
                    db.execute("INSERT OR IGNORE INTO opportunity_sources(opportunity_id,opportunity_version,snapshot_id) VALUES(?,?,?)", (opportunity_id, version, snapshot_id))
                if item.intelligence.reviewReasons:
                    db.execute("INSERT INTO review_queue(opportunity_id,opportunity_version,reasons_json,status,created_at) VALUES(?,?,?,?,?) ON CONFLICT(opportunity_id,opportunity_version) DO UPDATE SET reasons_json=excluded.reasons_json", (opportunity_id, version, json.dumps(item.intelligence.reviewReasons), "pending", now))
        return self.list_opportunities()

    def opportunity_history(self, opportunity_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT version,payload_json,change_summary_json,created_at FROM opportunity_versions WHERE opportunity_id=? ORDER BY version DESC", (opportunity_id,)).fetchall()
        return [{"version": row["version"], "opportunity": json.loads(row["payload_json"]), "changes": json.loads(row["change_summary_json"]), "createdAt": row["created_at"]} for row in rows]

    def list_review_queue(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM review_queue WHERE status='pending' ORDER BY created_at").fetchall()
        return [{"opportunityId": r["opportunity_id"], "opportunityVersion": r["opportunity_version"], "reasons": json.loads(r["reasons_json"]), "status": r["status"], "createdAt": r["created_at"]} for r in rows]

    def review(self, opportunity_id: str, version: int, status: str, note: str) -> None:
        with self._db() as db:
            db.execute("UPDATE review_queue SET status=?,note=?,reviewed_at=? WHERE opportunity_id=? AND opportunity_version=?", (status, note, datetime.now(timezone.utc).isoformat(), opportunity_id, version))

    def list_packs(self) -> list[PackArtifact]:
        return [PackArtifact.model_validate(item) for item in self._get_kv("packs", [])]

    def save_pack(self, pack: PackArtifact) -> PackArtifact:
        items = [item for item in self.list_packs() if item.id != pack.id] + [pack]
        self._set_kv("packs", [item.model_dump(mode="json") for item in items])
        return pack

    def get_pack(self, pack_id: str) -> PackArtifact | None:
        return next((item for item in self.list_packs() if item.id == pack_id), None)

    def list_watch(self) -> list[WatchItem]:
        return [WatchItem.model_validate(item) for item in self._get_kv("watch", [])]

    def save_watch(self, item: WatchItem) -> WatchItem:
        items = [existing for existing in self.list_watch() if existing.id != item.id] + [item]
        self._set_kv("watch", [existing.model_dump(mode="json") for existing in items])
        return item

    def append_audit(self, event: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute("INSERT INTO audit(payload_json,created_at) VALUES(?,?)", (json.dumps(event, default=str), datetime.now(timezone.utc).isoformat()))

    def has_replay(self, replay_key: str) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM replays WHERE replay_key=?", (replay_key,)).fetchone() is not None

    def record_replay(self, replay_key: str) -> None:
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO replays(replay_key,created_at) VALUES(?,?)", (replay_key, datetime.now(timezone.utc).isoformat()))


JsonStore = SQLiteStore
