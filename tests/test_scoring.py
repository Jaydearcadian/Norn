from __future__ import annotations

from app.models import CapabilityProfile, Evidence, Opportunity, ProjectClaim, SkillClaim
from app.scoring import assess_fit


def test_verified_evidence_increases_readiness():
    profile = CapabilityProfile(
        displayName="Builder",
        skills=[SkillClaim(name="Solidity", status="verified", evidenceIds=["repo"])],
        projects=[ProjectClaim(name="Protocol", summary="EVM smart-contract project", status="verified", capabilities=["EVM", "Solidity"], evidenceIds=["repo"])],
        preferredOpportunities=["hackathon"],
        supportedEcosystems=["EVM"],
        evidence=[Evidence(id="repo", label="Public Solidity repository", kind="repository", status="verified", tags=["Solidity", "EVM", "public repository"])],
    )
    opportunity = Opportunity(
        id="o1", title="EVM Build", type="hackathon", issuer="Issuer",
        requirements=["Public Solidity repository"], preferredCapabilities=["Solidity", "EVM"], ecosystems=["EVM"],
        sourceUrl="https://example.com/opportunity", sourceType="manual", applicationEffort="low", competitiveIntensity="medium", longTermValue=70,
    )
    result = assess_fit(profile, opportunity)
    assert result.score >= 65
    assert result.gaps[0].status == "verified"
    assert "Public Solidity repository" in result.strongEvidence


def test_claimed_capability_is_not_treated_as_verified():
    profile = CapabilityProfile(skills=[SkillClaim(name="ZK proofs", status="claimed")])
    opportunity = Opportunity(
        id="o2", title="ZK Grant", type="grant", issuer="Issuer",
        requirements=["Public zero-knowledge deployment proof"], preferredCapabilities=["ZK proofs"],
        sourceUrl="https://example.com/zk", sourceType="manual",
    )
    result = assess_fit(profile, opportunity)
    assert result.gaps[0].status in {"partial", "missing"}
    assert result.gaps[0].status != "verified"
