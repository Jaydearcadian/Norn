from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from app.models import CapabilityProfile, Evidence, Opportunity, OpportunityRequirement, SkillClaim
from app.vision import VisionEngine, WorkflowCreate, WorkflowTransition


def opportunity() -> Opportunity:
    return Opportunity(
        id="opp_vision",
        canonicalId="opp_vision",
        title="Verified Agent Programme",
        type="hackathon",
        issuer="Issuer",
        programme="Agent Programme",
        track="ASP",
        requirements=[OpportunityRequirement(
            id="req_deploy",
            category="deployment",
            statement="Provide a public deployment",
            mandatory=True,
            acceptedEvidence=["deployment URL"],
            confidence=1.0,
            interpretation="explicit",
        )],
        sourceUrl="https://example.com/rules",
        sourceType="official",
        completeness=1.0,
        normalizationConfidence=1.0,
        lifecycleStatus="verified",
        reviewStatus="approved",
    )


def profile() -> CapabilityProfile:
    return CapabilityProfile(
        version=2,
        skills=[SkillClaim(name="deployment", status="verified", evidenceIds=["deploy"])],
        evidence=[Evidence(
            id="deploy",
            label="Public deployment",
            kind="deployment",
            url="https://norn.example",
            tags=["deployment", "public"],
            status="verified",
        )],
    )


def test_decision_report_exposes_confidence_and_evidence_graph(tmp_path: Path):
    engine = VisionEngine(tmp_path / "norn.sqlite3")
    report = engine.decision_report(profile(), opportunity())
    assert report.dossierConfidence == 1.0
    assert report.decisionConfidence > 0.7
    assert report.evidenceGraph[0].requirementId == "req_deploy"
    assert report.evidenceGraph[0].state == "met"
    assert report.completionProbability > 0


def test_workflow_enforces_approval_before_submission(tmp_path: Path):
    engine = VisionEngine(tmp_path / "norn.sqlite3")
    workflow = engine.create_workflow(WorkflowCreate(
        opportunityId="opp_vision", title="Verified Agent Programme", nextAction="Review dossier"
    ))
    assert workflow["state"] == "discovered"
    with pytest.raises(ValueError):
        engine.transition(workflow["id"], WorkflowTransition(state="submitted"))
    for state in ["normalized", "reviewed", "qualified", "ready", "approved", "submitted", "awaiting_decision", "won"]:
        workflow = engine.transition(workflow["id"], WorkflowTransition(state=state, note=f"Moved to {state}"))
    assert workflow["state"] == "won"
    assert len(workflow["events"]) == 9


def test_launch_scorecard_never_rounds_missing_truth_to_ready(tmp_path: Path):
    engine = VisionEngine(tmp_path / "norn.sqlite3")
    score = engine.launch_scorecard([opportunity()], profile(), payment_ready=False)
    assert score["ready"] is False
    assert score["score"] < 9.5
    assert "compilerCorpus" in score["blockers"]
    assert "paymentReadiness" in score["blockers"]


def test_vision_endpoints(tmp_path: Path):
    settings = Settings(environment="test", data_dir=tmp_path, public_base_url="http://testserver", payment_mode="free")
    from fastapi.testclient import TestClient
    client = TestClient(create_app(settings))
    decision = client.post("/api/decision", json={"profile": profile().model_dump(mode="json"), "opportunity": opportunity().model_dump(mode="json")})
    assert decision.status_code == 200
    assert "decisionConfidence" in decision.json()
    workflow = client.post("/api/workflows", json={
        "opportunityId": "opp_vision", "title": "Verified Agent Programme", "nextAction": "Review dossier"
    })
    assert workflow.status_code == 200
    readiness = client.get("/api/launch-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is False
