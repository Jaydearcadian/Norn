from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.models import (
    AttributionBasis, CapabilityProfile, Evidence, FieldAttribution, Opportunity,
    OpportunityRequirement, SkillClaim,
)
from app.store import JsonStore
from app.vision import OutcomeRecord, VisionStore, WorkflowCreate, WorkflowTaskCreate, WorkflowTransition


def build_store(tmp_path: Path) -> tuple[JsonStore, VisionStore]:
    settings = Settings(environment="test", data_dir=tmp_path / "data", public_base_url="http://testserver", payment_mode="free")
    store = JsonStore(settings)
    return store, VisionStore(store.db_path)


def high_quality_opportunity(index: int = 1) -> Opportunity:
    snapshot = f"snapshot_{index}"
    requirement = OpportunityRequirement(
        id=f"req_{index}",
        category="deployment",
        statement="A public deployment must be available",
        mandatory=True,
        acceptedEvidence=["public deployment"],
        sourceSnapshotId=snapshot,
        confidence=1.0,
        interpretation=AttributionBasis.explicit,
    )
    return Opportunity(
        id=f"opp_{index}",
        canonicalId=f"issuer-programme-2026-track-{index}",
        canonicalFingerprint=("a" * 48) + str(index).zfill(4),
        version=1,
        title=f"Opportunity {index}",
        type="hackathon",
        issuer="Issuer",
        programme="Programme",
        cycle="2026",
        track=f"Track {index}",
        independentlyActionable=True,
        requirements=[requirement],
        sourceUrl=f"https://example.com/{index}",
        sourceType="official",
        sourceSnapshotIds=[snapshot],
        fieldProvenance={
            "requirements": FieldAttribution(
                basis=AttributionBasis.explicit,
                confidence=1.0,
                sourceSnapshotIds=[snapshot],
            )
        },
        normalizationConfidence=0.95,
        completeness=0.92,
        lifecycleStatus="verified",
        reviewStatus="approved",
    )


def test_typed_evidence_requires_accepted_proof_kind(tmp_path: Path):
    _, vision = build_store(tmp_path)
    requirement = high_quality_opportunity().requirements[0]
    profile = CapabilityProfile(
        skills=[SkillClaim(name="Deployment", status="verified", evidenceIds=["repo", "deploy"])],
        evidence=[
            Evidence(id="repo", label="Public repository", kind="repository", status="verified", digest="a" * 64),
            Evidence(id="deploy", label="Live public deployment", kind="deployment", status="verified", digest="b" * 64),
        ],
    )
    match = vision.match_requirement(profile, requirement)
    assert match.result == "verified"
    assert match.evidence_ids == ("deploy",)
    assert "repo" not in match.evidence_ids


def test_confidence_assessment_is_version_keyed_and_conservative(tmp_path: Path):
    _, vision = build_store(tmp_path)
    opportunity = high_quality_opportunity()
    profile = CapabilityProfile(
        version=3,
        evidence=[Evidence(id="deploy", label="Live public deployment", kind="deployment", status="verified", digest="b" * 64)],
    )
    result = vision.assess(profile, opportunity)
    assert result["profileVersion"] == 3
    assert result["opportunityVersion"] == 1
    assert 0 < result["assessmentConfidence"] <= 1
    assert 0 < result["completionProbability"] <= 1
    assert result["typedEvidenceMatches"][0]["result"] == "verified"


def test_workflow_rejects_skips_and_requires_approval_evidence(tmp_path: Path):
    _, vision = build_store(tmp_path)
    workflow = vision.create_workflow(WorkflowCreate(opportunityId="opp", title="Opportunity"))
    with pytest.raises(ValueError):
        vision.transition(workflow["id"], WorkflowTransition(toState="submitted"))

    current = workflow
    for state in ["normalized", "reviewed", "qualified", "ready"]:
        current = vision.transition(current["id"], WorkflowTransition(toState=state))
    with pytest.raises(ValueError):
        vision.transition(current["id"], WorkflowTransition(toState="approved"))
    approved = vision.transition(current["id"], WorkflowTransition(toState="approved", evidenceIds=["human_approval_receipt"]))
    submitted = vision.transition(approved["id"], WorkflowTransition(toState="submitted", evidenceIds=["submission_receipt"]))
    assert submitted["state"] == "submitted"


def test_task_dependencies_and_outcome_feedback(tmp_path: Path):
    _, vision = build_store(tmp_path)
    workflow = vision.create_workflow(WorkflowCreate(opportunityId="opp", title="Opportunity"))
    first = vision.add_task(workflow["id"], WorkflowTaskCreate(title="Capture deployment proof"))
    first_id = first["tasks"][0]["id"]
    second = vision.add_task(workflow["id"], WorkflowTaskCreate(title="Submit", dependencyIds=[first_id]))
    second_id = second["tasks"][1]["id"]
    with pytest.raises(ValueError):
        vision.complete_task(workflow["id"], second_id)
    vision.complete_task(workflow["id"], first_id)
    completed = vision.complete_task(workflow["id"], second_id)
    assert all(task["status"] == "completed" for task in completed["tasks"])

    current = workflow
    for state in ["normalized", "reviewed", "qualified", "ready"]:
        current = vision.transition(current["id"], WorkflowTransition(toState=state))
    current = vision.transition(current["id"], WorkflowTransition(toState="approved", evidenceIds=["approval"]))
    current = vision.transition(current["id"], WorkflowTransition(toState="submitted", evidenceIds=["receipt"]))
    recorded = vision.record_outcome(current["id"], OutcomeRecord(result="won", realisedValue=1000, currency="USDT", hoursSpent=12, lessons=["Activation proof was decisive."]))
    assert recorded["outcome"]["result"] == "won"
    assert recorded["outcome"]["lessons"]


def test_benchmark_enforces_thirty_real_dossiers(tmp_path: Path):
    _, vision = build_store(tmp_path)
    twenty_nine = [high_quality_opportunity(index) for index in range(1, 30)]
    failed = vision.benchmark(twenty_nine)
    assert failed["passed"] is False
    assert failed["thresholds"]["opportunityCount"] is False

    thirty = [high_quality_opportunity(index) for index in range(1, 31)]
    passed = vision.benchmark(thirty)
    assert passed["passed"] is True
    assert all(passed["thresholds"].values())


def test_readiness_never_claims_95_without_external_truth(tmp_path: Path):
    _, vision = build_store(tmp_path)
    dossiers = [high_quality_opportunity(index) for index in range(1, 31)]
    readiness = vision.readiness(dossiers, payment_ready=False, deployment_ready=False)
    assert readiness["targetReached"] is False
    assert readiness["overall"] < 9.5
    assert readiness["blockers"]
