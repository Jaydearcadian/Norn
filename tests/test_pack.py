from __future__ import annotations

from app.models import CapabilityProfile, Evidence, Opportunity, ProjectClaim, SkillClaim
from app.pack import prepare_pack


def test_pack_excludes_unverified_claims():
    profile = CapabilityProfile(
        displayName="Builder",
        skills=[
            SkillClaim(name="Solidity", status="verified", evidenceIds=["repo"]),
            SkillClaim(name="Ten enterprise customers", status="claimed", evidenceIds=[]),
        ],
        projects=[ProjectClaim(name="Norn", summary="Opportunity intelligence", status="verified", evidenceIds=["repo"])],
        evidence=[Evidence(id="repo", label="Public repository", kind="repository", status="verified", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", tags=["Solidity"])],
    )
    opportunity = Opportunity(
        id="o", title="Grant", type="grant", issuer="Issuer",
        requirements=["Public repository"], sourceUrl="https://example.com/grant",
    )
    pack = prepare_pack(profile, opportunity)
    assert "Public repository" in pack.content
    assert "Ten enterprise customers" not in pack.content.split("## Verified capability evidence")[1].split("## Requirement")[0]
    assert any("Ten enterprise customers" in item for item in pack.excludedClaims)
    assert pack.approvalStatus == "draft"


def test_verified_evidence_requires_url_or_digest():
    import pytest
    with pytest.raises(ValueError):
        Evidence(id="bad", label="Unsupported verification", kind="other", status="verified")
