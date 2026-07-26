from __future__ import annotations

import math
import re
from datetime import date
from typing import Iterable

from .models import CapabilityProfile, Evidence, GapItem, Opportunity

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
    for skill in profile.skills:
        if not verified_only or skill.status.value == "verified":
            values.append(skill.name)
    for project in profile.projects:
        if not verified_only or project.status.value == "verified":
            values.extend([project.name, project.summary, *project.ecosystems, *project.capabilities])
    values.extend(profile.supportedEcosystems)
    return tokens(" ".join(values))


def evidence_terms(evidence: Evidence) -> set[str]:
    return tokens(" ".join([evidence.label, evidence.note, *evidence.tags]))


def similarity(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    return intersection / math.sqrt(len(a) * len(b))


def match_requirement(profile: CapabilityProfile, requirement: str) -> GapItem:
    req = tokens(requirement)
    verified_matches: list[str] = []
    claimed_matches: list[str] = []
    for ev in profile.evidence:
        if similarity(req, evidence_terms(ev)) >= 0.16 or req & evidence_terms(ev):
            if ev.status.value == "verified":
                verified_matches.append(ev.id)
            elif ev.status.value == "claimed":
                claimed_matches.append(ev.id)

    verified_capability_overlap = similarity(req, profile_terms(profile, verified_only=True))
    all_capability_overlap = similarity(req, profile_terms(profile, verified_only=False))

    lowered = requirement.lower()
    if any(marker in lowered for marker in ["optional", "nice to have", "preferred but not required"]):
        return GapItem(
            requirement=requirement, status="not_applicable", reason="The source describes this as optional.",
        )
    if verified_matches or verified_capability_overlap >= 0.24:
        return GapItem(
            requirement=requirement,
            status="verified",
            matchedEvidenceIds=verified_matches,
            reason="Verified capability or evidence overlaps this requirement.",
        )
    if claimed_matches or all_capability_overlap >= 0.16:
        return GapItem(
            requirement=requirement,
            status="partial",
            matchedEvidenceIds=claimed_matches,
            reason="A relevant capability is claimed, but independently verifiable proof is incomplete.",
            recommendedAction=f"Attach a public repository, deployment, test, transaction, demo, or document proving: {requirement}",
        )
    return GapItem(
        requirement=requirement,
        status="missing",
        reason="No matching verified or claimed evidence was found.",
        recommendedAction=f"Create or obtain evidence for: {requirement}",
    )


def deadline_days(opportunity: Opportunity) -> int | None:
    if opportunity.deadline is None:
        return None
    return (opportunity.deadline - date.today()).days
