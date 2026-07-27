from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClaimStatus(str, Enum):
    verified = "verified"
    claimed = "claimed"
    aspirational = "aspirational"


class AttributionBasis(str, Enum):
    explicit = "explicit"
    derived = "derived"
    inferred = "inferred"
    unknown = "unknown"
    conflicting = "conflicting"


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
    version: int = 1
    displayName: str = "Norn Builder"
    biography: str = ""
    skills: list[SkillClaim] = Field(default_factory=list)
    projects: list[ProjectClaim] = Field(default_factory=list)
    preferredOpportunities: list[str] = Field(default_factory=list)
    supportedEcosystems: list[str] = Field(default_factory=list)
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)
    evidence: list[Evidence] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=utcnow)


class SourceSnapshot(BaseModel):
    id: str
    sourceId: str
    url: HttpUrl
    sourceType: Literal["official", "aggregator", "manual", "fixture"] = "manual"
    pageType: Literal["programme", "cycle", "track", "rules", "faq", "prizes", "application", "documentation", "github_issue", "repository", "role", "update", "issuer", "unknown"] = "unknown"
    retrievedAt: datetime = Field(default_factory=utcnow)
    publishedAt: datetime | None = None
    contentDigest: str
    contentType: str
    httpStatus: int
    issuer: str | None = None
    title: str | None = None


class FieldAttribution(BaseModel):
    basis: AttributionBasis = AttributionBasis.unknown
    confidence: float = Field(default=0.0, ge=0, le=1)
    sourceSnapshotIds: list[str] = Field(default_factory=list)
    sourceExcerptDigest: str | None = None
    originalValue: Any | None = None
    reasons: list[str] = Field(default_factory=list)


class OpportunityRequirement(BaseModel):
    id: str
    category: Literal["eligibility", "technical", "deployment", "deliverable", "application", "legal", "team", "geography", "evidence", "other"] = "other"
    statement: str
    mandatory: bool = True
    appliesTo: list[str] = Field(default_factory=lambda: ["all"])
    acceptedEvidence: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    sourceSnapshotId: str | None = None
    sourceExcerptDigest: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    interpretation: AttributionBasis = AttributionBasis.unknown

    @classmethod
    def from_text(cls, value: str, index: int = 0) -> "OpportunityRequirement":
        import hashlib
        lowered = value.lower()
        category = "other"
        for marker, mapped in {
            "eligible": "eligibility", "resident": "geography", "country": "geography",
            "deploy": "deployment", "live": "deployment", "demo": "deliverable",
            "video": "deliverable", "repository": "deliverable", "github": "technical",
            "experience": "technical", "submit": "application", "form": "application",
            "team": "team", "entity": "legal", "evidence": "evidence",
        }.items():
            if marker in lowered:
                category = mapped
                break
        optional = any(marker in lowered for marker in ("optional", "nice to have", "preferred but not required"))
        digest = hashlib.sha256(value.strip().encode()).hexdigest()[:16]
        return cls(
            id=f"req_{digest}_{index}", statement=value.strip(), category=category,
            mandatory=not optional, confidence=0.5, interpretation=AttributionBasis.inferred,
        )


class OpportunityValue(BaseModel):
    minimum: float | None = None
    maximum: float | None = None
    currency: str = "USD"
    components: list[Literal["cash", "in_kind", "equity", "credits", "tokens", "unknown"]] = Field(default_factory=list)
    paymentSchedule: str | None = None
    note: str = ""


class OpportunityTiming(BaseModel):
    opensAt: datetime | None = None
    registrationDeadline: datetime | None = None
    submissionDeadline: datetime | None = None
    decisionDate: datetime | None = None
    timezone: str | None = None
    rolling: bool = False


class EvaluationCriterion(BaseModel):
    name: str
    weight: float | None = None
    description: str = ""
    sourceSnapshotId: str | None = None


class Opportunity(BaseModel):
    id: str
    canonicalId: str | None = None
    version: int = 1
    canonicalFingerprint: str | None = None
    title: str
    type: Literal["job", "contract", "grant", "hackathon", "bounty", "accelerator", "investment", "research", "partnership", "rfp", "speaking", "publishing", "competition", "incentive", "other"]
    subtypes: list[str] = Field(default_factory=list)
    issuer: str
    programme: str | None = None
    cycle: str | None = None
    track: str | None = None
    parentOpportunityId: str | None = None
    independentlyActionable: bool = True
    summary: str = ""
    themes: list[str] = Field(default_factory=list)
    technicalDomains: list[str] = Field(default_factory=list)
    value: OpportunityValue = Field(default_factory=OpportunityValue)
    timing: OpportunityTiming = Field(default_factory=OpportunityTiming)
    deadline: date | None = None
    eligibility: list[OpportunityRequirement] = Field(default_factory=list)
    requirements: list[OpportunityRequirement] = Field(default_factory=list)
    deliverables: list[OpportunityRequirement] = Field(default_factory=list)
    evaluation: list[EvaluationCriterion] = Field(default_factory=list)
    applicationUrl: HttpUrl | None = None
    applicationSteps: list[str] = Field(default_factory=list)
    preferredCapabilities: list[str] = Field(default_factory=list)
    ecosystems: list[str] = Field(default_factory=list)
    sourceUrl: HttpUrl
    sourceTimestamp: datetime = Field(default_factory=utcnow)
    sourceType: Literal["official", "aggregator", "manual", "fixture"] = "manual"
    sourceSnapshotIds: list[str] = Field(default_factory=list)
    fieldProvenance: dict[str, FieldAttribution] = Field(default_factory=dict)
    applicationEffort: Literal["low", "medium", "high"] = "medium"
    competitiveIntensity: Literal["low", "medium", "high", "unknown"] = "unknown"
    longTermValue: int = Field(default=50, ge=0, le=100)
    status: Literal["open", "closing", "closed", "unknown", "withdrawn"] = "unknown"
    lifecycleStatus: Literal["draft", "normalized", "verified", "stale", "closed", "withdrawn"] = "draft"
    normalizationConfidence: float = Field(default=0.0, ge=0, le=1)
    completeness: float = Field(default=0.0, ge=0, le=1)
    lastVerifiedAt: datetime | None = None
    changedFields: list[str] = Field(default_factory=list)
    reviewStatus: Literal["not_required", "pending", "approved", "rejected"] = "not_required"

    @field_validator("requirements", "eligibility", "deliverables", mode="before")
    @classmethod
    def coerce_requirements(cls, value):
        if value is None:
            return []
        return [OpportunityRequirement.from_text(item, index) if isinstance(item, str) else item for index, item in enumerate(value)]

    @model_validator(mode="after")
    def synchronize_legacy_fields(self):
        if self.canonicalId is None:
            self.canonicalId = self.id
        if self.timing.submissionDeadline and self.deadline is None:
            self.deadline = self.timing.submissionDeadline.date()
        if self.deadline and self.timing.submissionDeadline is None:
            self.timing.submissionDeadline = datetime.combine(self.deadline, datetime.max.time(), tzinfo=timezone.utc)
        return self


class CriterionScore(BaseModel):
    key: str
    label: str
    score: float
    maximum: float
    reason: str


class GapItem(BaseModel):
    requirement: str
    requirementId: str | None = None
    category: str | None = None
    mandatory: bool = True
    status: Literal["verified", "partial", "missing", "not_applicable"]
    eligibilityResult: Literal["met", "failed", "unknown", "not_applicable"] | None = None
    matchedEvidenceIds: list[str] = Field(default_factory=list)
    reason: str
    recommendedAction: str | None = None


class FitAssessment(BaseModel):
    opportunityId: str
    opportunityVersion: int = 1
    profileVersion: int = 1
    scoringEngineVersion: str = "norn-score-v1"
    score: int = Field(ge=0, le=100)
    expectedValueIndex: float = Field(ge=0)
    eligibility: Literal["eligible", "likely", "uncertain", "ineligible"]
    hardEligibility: Literal["met", "failed", "unknown"] = "unknown"
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
    sourceSnapshotIds: list[str] = Field(default_factory=list)
    opportunityVersions: dict[str, int] = Field(default_factory=dict)
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


class ReviewDecision(BaseModel):
    status: Literal["approved", "rejected"]
    notes: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    paymentMode: str
    blockers: list[str] = Field(default_factory=list)
