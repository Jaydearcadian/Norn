from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def brief_payload(client: TestClient) -> dict:
    profile = client.get("/api/profile").json()
    opportunities = client.post("/api/feed", json={}).json()["items"]
    return {"profile": profile, "opportunities": opportunities, "includePackForTopOpportunity": True, "maximumResults": 5}


def test_core_surfaces(client: TestClient):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "norn"
    feed = client.post("/api/feed", json={})
    assert feed.status_code == 200
    assert feed.json()["count"] >= 1
    payload = brief_payload(client)
    scored = client.post("/api/score", json={"profile": payload["profile"], "opportunity": payload["opportunities"][0]})
    assert scored.status_code == 200
    assert 0 <= scored.json()["score"] <= 100
    pack = client.post("/api/packs", json={"profile": payload["profile"], "opportunity": payload["opportunities"][0]})
    assert pack.status_code == 200
    assert pack.json()["approvalStatus"] == "draft"


def test_demo_payment_challenge_paid_call_and_replay(tmp_path: Path):
    settings = Settings(
        environment="test", data_dir=tmp_path / "data", public_base_url="http://testserver",
        payment_mode="demo", demo_payment_secret="test-secret", enable_live_discovery=False,
    )
    client = TestClient(create_app(settings))
    payload = brief_payload(client)
    body = json.dumps(payload, separators=(",", ":")).encode()

    unpaid = client.post("/api/v1/opportunity-brief", content=body, headers={"content-type":"application/json"})
    assert unpaid.status_code == 402
    assert unpaid.headers.get("PAYMENT-REQUIRED")
    assert unpaid.json()["x402Version"] == 2

    wrong = client.post("/api/v1/opportunity-brief", content=body, headers={"content-type":"application/json", "PAYMENT-SIGNATURE":"demo:wrong"})
    assert wrong.status_code == 402

    signature = "demo:" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    paid = client.post("/api/v1/opportunity-brief", content=body, headers={"content-type":"application/json", "PAYMENT-SIGNATURE":signature})
    assert paid.status_code == 200
    result = paid.json()
    assert result["ranked"]
    assert result["provenance"]["requestDigest"]
    assert result["topPack"]["approvalStatus"] == "draft"

    replay = client.post("/api/v1/opportunity-brief", content=body, headers={"content-type":"application/json", "PAYMENT-SIGNATURE":signature})
    assert replay.status_code == 409


def test_invalid_input_does_not_execute_business(tmp_path: Path):
    settings = Settings(environment="test", data_dir=tmp_path / "data", public_base_url="http://testserver", payment_mode="demo", demo_payment_secret="x")
    client = TestClient(create_app(settings))
    response = client.post("/api/v1/opportunity-brief", content=b'{}', headers={"content-type":"application/json"})
    assert response.status_code == 422


def test_production_okx_mode_fails_closed_without_credentials(tmp_path: Path):
    import pytest
    settings = Settings(
        environment="production",
        data_dir=tmp_path / "data",
        public_base_url="https://norn.example",
        payment_mode="okx",
        pay_to_address="",
        okx_api_key="",
        okx_secret_key="",
        okx_passphrase="",
    )
    with pytest.raises(RuntimeError):
        create_app(settings)


def test_free_production_deployment_is_not_payment_ready(tmp_path: Path):
    settings = Settings(
        environment="production",
        data_dir=tmp_path / "data",
        public_base_url="https://norn.example",
        payment_mode="free",
    )
    client = TestClient(create_app(settings))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "degraded"
    assert "PAYMENT_MODE=okx" in " ".join(health.json()["blockers"])
    assert client.get("/ready").json()["ready"] is False
