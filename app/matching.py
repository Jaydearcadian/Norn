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
    if isinstance(requirement, str):
        requirement = OpportunityRequirement(id="legacy", statement=requirement)
    statement = requirement.statement
    req = tokens(" ".join([statement, *requirement.acceptedEvidence]))
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
    if not requirement.mandatory:
        return GapItem(requirementId=requirement.id, requirement=statement, status="not_applicable", reason="The dossier marks this requirement optional.")
    if requirement.confidence < 0.5 or requirement.interpretation.value in {"unknown", "conflicting"}:
        return GapItem(requirementId=requirement.id, requirement=statement, status="unknown", reason="The opportunity requirement is not verified strongly enough for a hard eligibility decision.", recommendedAction="Review the attributed source and resolve the requirement interpretation.")
    if verified_matches or verified_capability_overlap >= 0.24:
        return GapItem(requirementId=requirement.id, requirement=statement, status="verified", matchedEvidenceIds=verified_matches, reason="Verified capability or evidence satisfies the structured requirement.")
    if claimed_matches or all_capability_overlap >= 0.16:
        return GapItem(requirementId=requirement.id, requirement=statement, status="partial", matchedEvidenceIds=claimed_matches, reason="Relevant capability exists, but accepted evidence is incomplete.", recommendedAction=f"Attach accepted evidence for: {statement}")
    return GapItem(requirementId=requirement.id, requirement=statement, status="missing", reason="No matching verified or claimed evidence was found.", recommendedAction=f"Create or obtain accepted evidence for: {statement}")


def deadline_days(opportunity: Opportunity) -> int | None:
    return None if opportunity.deadline is None else (opportunity.deadline - date.today()).days
