from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClaimStatus(str, Enum):
    verified = "verified"
    claimed = "claimed"
    aspirational = "aspirational"


class Evidence(BaseModel):
    id: str
    label: str
    kind: Literal["repository", "deployment", "test", "transaction", "demo", "documentation", "profile", "other"]
    url: HttpUrl | None = None
    digest: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.claimed
    note: str = ""

    @model_validator(mode="after")
    def verified_requires_proof(self):
        if self.digest is not None:
            value = self.digest.removeprefix("sha256:")
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
                raise ValueError("Evidence digest must be a 64-character SHA-256 hex string")
        if self.status == ClaimStatus.verified and not (self.url or self.digest):
            raise ValueError("Verified evidence requires a public URL or SHA-256 digest")
        return self


class SkillClaim(BaseModel):
    name: str
    status: ClaimStatus = ClaimStatus.claimed
    evidenceIds: list[str] = Field(default_factory=list)


class ProjectClaim(BaseModel):
    name: str
    summary: str = ""
    status: ClaimStatus = ClaimStatus.claimed
    ecosystems: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    evidenceIds: list[str] = Field(default_factory=list)


class ProfileConstraints(BaseModel):
    remote: bool = True
    minimumValue: float = 0
    currencies: list[str] = Field(default_factory=lambda: ["USD", "USDT"])
    excludedCategories: list[str] = Field(default_factory=list)
    deadlineBufferDays: int = 1


class CapabilityProfile(BaseModel):
    id: str = "primary"
    displayName: str = "Norn Builder"
    biography: str = ""
    skills: list[SkillClaim] = Field(default_factory=list)
    projects: list[ProjectClaim] = Field(default_factory=list)
    preferredOpportunities: list[str] = Field(default_factory=list)
    supportedEcosystems: list[str] = Field(default_factory=list)
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)
    evidence: list[Evidence] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utcnow)


class OpportunityValue(BaseModel):
    minimum: float | None = None
    maximum: float | None = None
    currency: str = "USD"
    note: str = ""


class Opportunity(BaseModel):
    id: str
    title: str
    type: Literal["job", "contract", "grant", "hackathon", "bounty", "accelerator", "investment", "research", "partnership", "rfp", "speaking", "publishing", "competition", "incentive", "other"]
    issuer: str
    summary: str = ""
    value: OpportunityValue = Field(default_factory=OpportunityValue)
    deadline: date | None = None
    requirements: list[str] = Field(default_factory=list)
    preferredCapabilities: list[str] = Field(default_factory=list)
    ecosystems: list[str] = Field(default_factory=list)
    sourceUrl: HttpUrl
    sourceTimestamp: datetime = Field(default_factory=utcnow)
    sourceType: Literal["official", "aggregator", "manual", "fixture"] = "manual"
    applicationEffort: Literal["low", "medium", "high"] = "medium"
    competitiveIntensity: Literal["low", "medium", "high", "unknown"] = "unknown"
    longTermValue: int = Field(default=50, ge=0, le=100)
    status: Literal["open", "closing", "closed", "unknown"] = "unknown"


class CriterionScore(BaseModel):
    key: str
    label: str
    score: float
    maximum: float
    reason: str


class GapItem(BaseModel):
    requirement: str
    status: Literal["verified", "partial", "missing", "not_applicable"]
    matchedEvidenceIds: list[str] = Field(default_factory=list)
    reason: str
    recommendedAction: str | None = None


class FitAssessment(BaseModel):
    opportunityId: str
    score: int = Field(ge=0, le=100)
    expectedValueIndex: float = Field(ge=0)
    eligibility: Literal["eligible", "likely", "uncertain", "ineligible"]
    recommendation: Literal["pursue_now", "close_gaps_first", "watch", "skip"]
    criteria: list[CriterionScore]
    strongEvidence: list[str]
    missingEvidence: list[str]
    rationale: list[str]
    gaps: list[GapItem]
    generatedAt: datetime = Field(default_factory=utcnow)


class ScoreRequest(BaseModel):
    profile: CapabilityProfile
    opportunity: Opportunity


class GapRequest(BaseModel):
    profile: CapabilityProfile
    opportunity: Opportunity


class PackRequest(BaseModel):
    profile: CapabilityProfile
    opportunity: Opportunity
    assessment: FitAssessment | None = None
    format: Literal["markdown", "json"] = "markdown"


class PackArtifact(BaseModel):
    id: str
    opportunityId: str
    title: str
    content: str
    includedEvidenceIds: list[str]
    excludedClaims: list[str]
    approvalStatus: Literal["draft", "approved", "submitted"] = "draft"
    createdAt: datetime = Field(default_factory=utcnow)
    digest: str


class WatchItem(BaseModel):
    id: str
    opportunityId: str
    title: str
    deadline: date | None = None
    nextAction: str
    followUpAt: datetime | None = None
    status: Literal["watching", "preparing", "ready", "submitted", "won", "lost", "archived"] = "watching"
    notes: str = ""
    updatedAt: datetime = Field(default_factory=utcnow)


class OpportunityBriefRequest(BaseModel):
    profile: CapabilityProfile
    opportunities: list[Opportunity] = Field(min_length=1, max_length=25)
    includePackForTopOpportunity: bool = True
    maximumResults: int = Field(default=5, ge=1, le=10)


class RankedOpportunity(BaseModel):
    opportunity: Opportunity
    assessment: FitAssessment


class Provenance(BaseModel):
    requestDigest: str
    resultDigest: str
    sourceUrls: list[str]
    sourceTimestamps: list[datetime]
    engineVersion: str = "norn-score-v1"
    generatedAt: datetime = Field(default_factory=utcnow)


class OpportunityBriefResponse(BaseModel):
    ranked: list[RankedOpportunity]
    topPack: PackArtifact | None = None
    summary: str
    provenance: Provenance


class DiscoverRequest(BaseModel):
    profile: CapabilityProfile | None = None
    query: str = ""
    types: list[str] = Field(default_factory=list)
    maximumResults: int = Field(default=25, ge=1, le=100)


class ImportOpportunityRequest(BaseModel):
    opportunities: list[Opportunity] = Field(min_length=1, max_length=500)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    paymentMode: str
    blockers: list[str] = Field(default_factory=list)
