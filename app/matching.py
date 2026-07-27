from __future__ import annotations

import math
import re
from datetime import date
from typing import Iterable

from .models import CapabilityProfile, Evidence, GapItem, Opportunity, OpportunityRequirement

STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "with", "your", "you",
    "must", "should", "required", "experience", "working", "project", "team",
}
ALIASES = {
    "evm": {"ethereum", "solidity", "smart contract", "x layer", "xlayer"},
    "zk": {"zero knowledge", "zkp", "proof", "prover", "privacy"},
    "agent payments": {"x402", "agent payment", "machine payment", "payable agent"},
    "cross chain": {"layerzero", "interop", "interoperability", "bridge"},
    "ai agents": {"agent", "agentic", "mcp", "a2a"},
}


def tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9][a-z0-9+.#-]*", text.lower())) - STOP
    phrases = {key for key in ALIASES if key in text.lower()}
    for canonical, aliases in ALIASES.items():
        if any(alias in text.lower() for alias in aliases):
            phrases.add(canonical)
    return words | phrases


def profile_terms(profile: CapabilityProfile, verified_only: bool = False) -> set[str]:
    values: list[str] = []
    verified_evidence_ids = {item.id for item in profile.evidence if item.status.value == "verified"}
    for skill in profile.skills:
        is_proven = skill.status.value == "verified" and bool(verified_evidence_ids & set(skill.evidenceIds))
        if not verified_only or is_proven:
            values.append(skill.name)
    for project in profile.projects:
        is_proven = project.status.value == "verified" and bool(verified_evidence_ids & set(project.evidenceIds))
        if not verified_only or is_proven:
            values.extend([project.name, project.summary, *project.ecosystems, *project.capabilities])
    if not verified_only:
        values.extend(profile.supportedEcosystems)
    return tokens(" ".join(values))


def evidence_terms(evidence: Evidence) -> set[str]:
    return tokens(" ".join([evidence.label, evidence.note, *evidence.tags]))


def similarity(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


def match_requirement(profile: CapabilityProfile, requirement: OpportunityRequirement | str) -> GapItem:
    requirement = requirement if isinstance(requirement, OpportunityRequirement) else OpportunityRequirement.from_text(requirement)
    statement = requirement.statement
    req = tokens(" ".join([statement, requirement.category, *requirement.acceptedEvidence]))
    verified_matches: list[str] = []
    claimed_matches: list[str] = []
    for evidence in profile.evidence:
        overlap = similarity(req, evidence_terms(evidence))
        if overlap >= 0.16 or req & evidence_terms(evidence):
            if evidence.status.value == "verified":
                verified_matches.append(evidence.id)
            elif evidence.status.value == "claimed":
                claimed_matches.append(evidence.id)

    verified_capability_overlap = similarity(req, profile_terms(profile, verified_only=True))
    all_capability_overlap = similarity(req, profile_terms(profile, verified_only=False))
    base = dict(requirement=statement, requirementId=requirement.id, category=requirement.category, mandatory=requirement.mandatory)

    if not requirement.mandatory:
        return GapItem(**base, status="not_applicable", eligibilityResult="not_applicable", reason="The issuer describes this requirement as optional.")
    if verified_matches or verified_capability_overlap >= 0.24:
        return GapItem(**base, status="verified", eligibilityResult="met" if requirement.category in {"eligibility", "geography", "team", "legal"} else None, matchedEvidenceIds=verified_matches, reason="Verified capability or evidence satisfies this structured requirement.")
    if claimed_matches or all_capability_overlap >= 0.16:
        return GapItem(**base, status="partial", eligibilityResult="unknown" if requirement.category in {"eligibility", "geography", "team", "legal"} else None, matchedEvidenceIds=claimed_matches, reason="Relevant capability exists, but independently verifiable proof is incomplete.", recommendedAction=f"Attach accepted evidence proving: {statement}")
    return GapItem(**base, status="missing", eligibilityResult="unknown" if requirement.category in {"eligibility", "geography", "team", "legal"} else None, reason="No matching verified or claimed evidence was found.", recommendedAction=f"Create or obtain evidence for: {statement}")


def deadline_days(opportunity: Opportunity) -> int | None:
    if opportunity.deadline is None:
        return None
    return (opportunity.deadline - date.today()).days
