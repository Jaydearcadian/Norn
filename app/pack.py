from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .digests import sha256_digest
from .models import CapabilityProfile, FitAssessment, Opportunity, PackArtifact
from .scoring import assess_fit


def _verified_profile_lines(profile: CapabilityProfile) -> tuple[list[str], list[str], list[str]]:
    evidence_by_id = {item.id: item for item in profile.evidence}
    verified_lines: list[str] = []
    included_ids: list[str] = []
    excluded: list[str] = []

    for skill in profile.skills:
        linked = [evidence_by_id.get(item) for item in skill.evidenceIds]
        proven = [item for item in linked if item and item.status.value == "verified"]
        if skill.status.value == "verified" and proven:
            verified_lines.append(f"- {skill.name}: supported by {', '.join(item.label for item in proven)}")
            included_ids.extend(item.id for item in proven)
        else:
            excluded.append(f"Skill claim not used as verified fact: {skill.name}")

    for project in profile.projects:
        linked = [evidence_by_id.get(item) for item in project.evidenceIds]
        proven = [item for item in linked if item and item.status.value == "verified"]
        if project.status.value == "verified" and proven:
            verified_lines.append(f"- {project.name}: {project.summary} Evidence: {', '.join(item.label for item in proven)}")
            included_ids.extend(item.id for item in proven)
        else:
            excluded.append(f"Project claim not used as verified fact: {project.name}")

    return verified_lines, sorted(set(included_ids)), excluded


def prepare_pack(
    profile: CapabilityProfile,
    opportunity: Opportunity,
    assessment: FitAssessment | None = None,
) -> PackArtifact:
    assessment = assessment or assess_fit(profile, opportunity)
    verified_lines, included_ids, excluded = _verified_profile_lines(profile)
    verified_section = "\n".join(verified_lines) if verified_lines else (
        "- No capability claim currently meets Norn's verified-evidence threshold."
    )
    gap_lines = "\n".join(
        f"- [{item.status.upper()}] {item.requirement}"
        + (f" — {item.recommendedAction}" if item.recommendedAction else "")
        for item in assessment.gaps
    ) or "- No explicit requirements were supplied."

    content = f"""# Norn Pack — {opportunity.title}

## Submission status

**Draft only. Human approval is required before submission.**

## Opportunity

- Issuer: {opportunity.issuer}
- Type: {opportunity.type}
- Deadline: {opportunity.deadline or 'Not supplied'}
- Source: {opportunity.sourceUrl}
- Norn Score: {assessment.score}/100
- Recommendation: {assessment.recommendation}

## Tailored project summary

{profile.displayName} is preparing an application for {opportunity.title}. The application should lead with capabilities that are backed by the evidence index below and should avoid treating claimed or aspirational work as completed proof.

## Verified capability evidence

{verified_section}

## Requirement and evidence matrix

{gap_lines}

## Proposed completion plan

1. Close every missing or partial evidence item before making the corresponding claim.
2. Capture public, independently readable evidence where the opportunity requests deployment or execution proof.
3. Re-run Norn Score after evidence is added.
4. Review the exact answers and attachments.
5. Submit only after explicit approval, then save the confirmation receipt.

## Evidence index

"""
    evidence_by_id = {item.id: item for item in profile.evidence}
    for evidence_id in included_ids:
        item = evidence_by_id[evidence_id]
        content += f"- {item.label} ({item.kind}) — {item.url or item.digest or 'stored evidence'}\n"
    if not included_ids:
        content += "- No verified evidence included.\n"

    content += "\n## Claims deliberately excluded\n\n"
    content += "\n".join(f"- {line}" for line in excluded) if excluded else "- None."
    content += "\n"

    digest = sha256_digest(content)
    return PackArtifact(
        id=f"pack_{uuid4().hex[:12]}",
        opportunityId=opportunity.id,
        title=f"Norn Pack — {opportunity.title}",
        content=content,
        includedEvidenceIds=included_ids,
        excludedClaims=excluded,
        createdAt=datetime.now(timezone.utc),
        digest=digest,
    )
