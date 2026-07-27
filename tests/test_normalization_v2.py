from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.compiler import compile_candidate
from app.config import Settings
from app.main import create_app
from app.models import Opportunity, SourceSnapshot
from app.store import JsonStore


def snapshot(digest: str = "sha256:" + "a" * 64) -> SourceSnapshot:
    return SourceSnapshot(
        id="snapshot_rules_v1" if digest.endswith("a" * 64) else "snapshot_rules_v2",
        sourceId="source_programme",
        url="https://example.com/rules",
        sourceType="official",
        pageType="rules",
        retrievedAt=datetime.now(timezone.utc),
        contentDigest=digest,
        contentType="application/json",
        httpStatus=200,
        issuer="Example Foundation",
        title="Example Builder Programme rules",
    )


def test_compiler_segments_tracks_and_attributes_requirements():
    raw = {
        "id": "example-2026",
        "title": "Example Builder Programme",
        "issuer": "Example Foundation",
        "type": "hackathon",
        "cycle": "2026",
        "deadline": "2026-09-30",
        "value": {"minimum": 1000, "maximum": 5000, "currency": "USD"},
        "requirements": ["Applicants must submit a public repository", "A two-minute demo video is required"],
        "tracks": [
            {"title": "Agent Infrastructure", "track": "Agents", "preferredCapabilities": ["AI agents"]},
            {"title": "ZK Infrastructure", "track": "ZK", "preferredCapabilities": ["zero knowledge"]},
        ],
        "applicationUrl": "https://example.com/apply",
    }
    compiled = compile_candidate(raw, snapshot(), "structured_json")
    assert len(compiled) == 2
    assert {item.track for item in compiled} == {"Agents", "ZK"}
    assert all(item.independentlyActionable for item in compiled)
    assert all(item.sourceSnapshotIds == ["snapshot_rules_v1"] for item in compiled)
    assert all(item.deliverables for item in compiled)
    assert all(item.fieldProvenance["timing"].basis.value == "explicit" for item in compiled)


def test_sqlite_store_deduplicates_by_fingerprint_and_appends_versions(tmp_path: Path):
    settings = Settings(environment="test", data_dir=tmp_path / "data", public_base_url="http://testserver")
    store = JsonStore(settings)
    source = snapshot()
    store.save_source_snapshot(source, b"first")
    first = compile_candidate({
        "id": "external-id-one", "title": "Agent Track", "issuer": "Example Foundation",
        "programme": "Builder Programme", "cycle": "2026", "track": "Agents",
        "type": "hackathon", "deadline": "2026-09-30", "applicationUrl": "https://example.com/apply/agents",
        "requirements": ["Submit a public repository"],
    }, source, "structured_json")[0]
    store.save_opportunities([first])

    second_source = snapshot("sha256:" + "b" * 64)
    store.save_source_snapshot(second_source, b"second")
    second = compile_candidate({
        "id": "different-upstream-id", "title": "Agent Track", "issuer": "Example Foundation",
        "programme": "Builder Programme", "cycle": "2026", "track": "Agents",
        "type": "hackathon", "deadline": "2026-09-30", "applicationUrl": "https://example.com/apply/agents",
        "requirements": ["Submit a public repository", "Deploy a working public demo"],
    }, second_source, "structured_json")[0]
    store.save_opportunities([second])

    opportunities = [item for item in store.list_opportunities() if item.programme == "Builder Programme"]
    assert len(opportunities) == 1
    assert opportunities[0].version == 2
    assert "requirements" in opportunities[0].changedFields or "deliverables" in opportunities[0].changedFields
    history = store.get_opportunity_history(opportunities[0].canonicalId)
    assert [item["version"] for item in history] == [2, 1]


def test_feed_exposes_compiler_intelligence_and_review_queue(tmp_path: Path):
    settings = Settings(environment="test", data_dir=tmp_path / "data", public_base_url="http://testserver", enable_live_discovery=False)
    client = TestClient(create_app(settings))
    feed = client.post("/api/feed", json={})
    assert feed.status_code == 200
    assert feed.json()["compilerVersion"] == "normalization-v2"
    item = feed.json()["items"][0]
    assert "intelligence" in item
    assert "completeness" in item["intelligence"]
    assert "hardEligibility" in item["intelligence"]
    assert item["version"] >= 1

    review = client.get("/api/feed/review")
    assert review.status_code == 200
    assert "items" in review.json()


def test_legacy_string_requirements_are_structured():
    opportunity = Opportunity.model_validate({
        "id": "legacy", "title": "Legacy feed", "type": "grant", "issuer": "Issuer",
        "requirements": ["Applicants must provide a repository"],
        "sourceUrl": "https://example.com/grant",
    })
    assert opportunity.requirements[0].statement == "Applicants must provide a repository"
    assert opportunity.requirements[0].mandatory is True
