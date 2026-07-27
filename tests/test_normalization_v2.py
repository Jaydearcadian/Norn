from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Opportunity, OpportunityRequirement
from app.normalization import compile_opportunity, snapshot_from_response
from app.sqlite_store import SQLiteStore


def opportunity(deadline: date | None = date(2026, 9, 1)) -> Opportunity:
    snapshot = snapshot_from_response(
        url="https://example.com/program/rules", content=b"official rules v1",
        content_type="text/html", http_status=200, source_type="official",
        document_role="rules", issuer="Example Foundation",
    )
    item = Opportunity(
        id="example-track", title="Example Programme / ZK Track", type="grant",
        issuer="Example Foundation", summary="Fund a working ZK integration.",
        deadline=deadline, sourceUrl="https://example.com/program/rules",
        applicationUrl="https://example.com/apply",
        requirements=["Deploy a working proof system"],
        preferredCapabilities=["ZK proofs"], ecosystems=["EVM"], status="open",
    )
    return compile_opportunity(item, [snapshot], programme="Example Programme", cycle="2026", track="ZK Track")


def test_structured_requirements_and_attribution():
    item = opportunity()
    assert isinstance(item.requirements[0], OpportunityRequirement)
    assert item.requirements[0].sourceSnapshotId
    assert item.intelligence.canonicalFingerprint
    assert item.intelligence.completeness >= 0.7
    assert any(field.field == "deadline" and field.basis.value == "explicit" for field in item.intelligence.fieldAttributions)


def test_sqlite_versions_changes_instead_of_overwrite(tmp_path):
    store = SQLiteStore(Settings(environment="test", data_dir=tmp_path, public_base_url="http://testserver"))
    first = opportunity(date(2026, 9, 1))
    store.save_opportunities([first])
    second = opportunity(date(2026, 9, 8))
    # Fingerprint normally includes deadline; preserve identity to simulate a changed source bundle.
    second.intelligence.canonicalFingerprint = first.intelligence.canonicalFingerprint
    store.save_opportunities([second])
    history = store.opportunity_history(first.id)
    assert len(history) == 2
    assert history[0]["changes"] == ["deadline changed"]


def test_unknown_eligibility_gets_no_partial_credit(tmp_path):
    client = TestClient(create_app(Settings(environment="test", data_dir=tmp_path, public_base_url="http://testserver")))
    profile = client.get("/api/profile").json()
    item = opportunity()
    item.requirements[0].confidence = 0.2
    item.requirements[0].interpretation = "unknown"
    response = client.post("/api/score", json={"profile": profile, "opportunity": item.model_dump(mode="json")})
    assert response.status_code == 200
    assert response.json()["hardEligibility"] == "unknown"
    eligibility = next(row for row in response.json()["criteria"] if row["key"] == "eligibility")
    assert eligibility["score"] == 0


def test_feed_exposes_intelligence_and_review_queue(tmp_path):
    client = TestClient(create_app(Settings(environment="test", data_dir=tmp_path, public_base_url="http://testserver")))
    payload = opportunity(deadline=None).model_dump(mode="json")
    response = client.post("/api/feed/import", json={"opportunities": [payload]})
    assert response.status_code == 200
    feed = client.post("/api/feed", json={}).json()
    dossier = next(item for item in feed["items"] if item["id"] == "example-track")
    assert dossier["intelligence"]["dossierStatus"] == "review_required"
    queue = client.get("/api/review-queue").json()
    assert queue["count"] >= 1
