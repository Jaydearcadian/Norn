from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import (
    AttributionBasis,
    FieldAttribution,
    Opportunity,
    OpportunityIntelligence,
    OpportunityRequirement,
    SourceSnapshot,
)


def digest_bytes(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def snapshot_from_response(
    *, url: str, content: bytes, content_type: str, http_status: int,
    source_type: str, document_role: str, issuer: str | None = None,
    title: str | None = None, published_at: datetime | None = None,
) -> SourceSnapshot:
    content_digest = digest_bytes(content)
    source_id = f"source_{sha256(canonical_url(url).encode()).hexdigest()[:16]}"
    return SourceSnapshot(
        id=f"snapshot_{sha256((source_id + content_digest).encode()).hexdigest()[:20]}",
        sourceId=source_id,
        url=canonical_url(url),
        sourceType=source_type,
        documentRole=document_role,
        retrievedAt=datetime.now(timezone.utc),
        publishedAt=published_at,
        contentDigest=content_digest,
        contentType=content_type.split(";", 1)[0],
        httpStatus=http_status,
        issuer=issuer,
        title=title,
    )


def requirement_from_text(
    statement: str, index: int, snapshot_id: str | None, *,
    category: str = "other", basis: AttributionBasis = AttributionBasis.explicit,
    confidence: float = 0.9,
) -> OpportunityRequirement:
    optional = any(marker in statement.lower() for marker in (
        "optional", "nice to have", "preferred but not required",
    ))
    return OpportunityRequirement(
        id=f"req_{slug(statement)[:42] or index}",
        category=category,
        statement=statement.strip(),
        mandatory=not optional,
        sourceSnapshotId=snapshot_id,
        sourceExcerptDigest=digest_bytes(statement.strip().encode()),
        confidence=confidence,
        interpretation=basis,
    )


def canonical_fingerprint(opportunity: Opportunity) -> str:
    identity = {
        "issuer": slug(opportunity.issuer),
        "programme": slug(opportunity.intelligence.programme or opportunity.title),
        "cycle": slug(opportunity.intelligence.cycle or ""),
        "track": slug(opportunity.intelligence.track or opportunity.title),
        "deadline": opportunity.deadline.isoformat() if opportunity.deadline else None,
        "applicationUrl": canonical_url(str(opportunity.applicationUrl or opportunity.sourceUrl)),
    }
    return sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def dossier_digest(opportunity: Opportunity) -> str:
    payload = opportunity.model_dump(mode="json")
    intelligence = payload.get("intelligence", {})
    intelligence.pop("version", None)
    intelligence.pop("changeSummary", None)
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def completeness(opportunity: Opportunity) -> float:
    checks = [
        bool(opportunity.title), bool(opportunity.issuer), bool(opportunity.summary),
        bool(opportunity.sourceUrl), opportunity.deadline is not None,
        bool(opportunity.requirements), bool(opportunity.applicationUrl),
        bool(opportunity.preferredCapabilities or opportunity.ecosystems),
        opportunity.value.minimum is not None or opportunity.value.maximum is not None,
        bool(opportunity.intelligence.sourceSnapshotIds),
    ]
    return round(sum(checks) / len(checks), 2)


def compile_opportunity(
    opportunity: Opportunity,
    snapshots: list[SourceSnapshot],
    *, programme: str | None = None, cycle: str | None = None,
    track: str | None = None,
) -> Opportunity:
    snapshot_ids = [snapshot.id for snapshot in snapshots]
    primary = snapshots[0].id if snapshots else None
    requirements = []
    for index, requirement in enumerate(opportunity.requirements):
        if isinstance(requirement, OpportunityRequirement):
            item = requirement.model_copy(deep=True)
            if not item.sourceSnapshotId:
                item.sourceSnapshotId = primary
            requirements.append(item)
        else:
            requirements.append(requirement_from_text(requirement, index, primary))
    opportunity.requirements = requirements

    official = sum(snapshot.sourceType == "official" for snapshot in snapshots)
    source_quality = round(official / len(snapshots), 2) if snapshots else 0
    attributions = [
        FieldAttribution(field="title", basis=AttributionBasis.explicit, confidence=1, sourceSnapshotIds=[primary] if primary else []),
        FieldAttribution(field="issuer", basis=AttributionBasis.explicit, confidence=1, sourceSnapshotIds=[primary] if primary else []),
        FieldAttribution(field="deadline", basis=AttributionBasis.explicit if opportunity.deadline else AttributionBasis.unknown, confidence=1 if opportunity.deadline else 0, sourceSnapshotIds=[primary] if primary and opportunity.deadline else []),
        FieldAttribution(field="applicationEffort", basis=AttributionBasis.inferred, confidence=0.7, reasons=["Derived from mandatory requirements and deliverables"]),
    ]
    intelligence = opportunity.intelligence.model_copy(deep=True)
    intelligence.programme = programme or intelligence.programme or opportunity.title
    intelligence.cycle = cycle or intelligence.cycle
    intelligence.track = track or intelligence.track
    intelligence.sourceSnapshotIds = sorted(set([*intelligence.sourceSnapshotIds, *snapshot_ids]))
    intelligence.fieldAttributions = attributions
    intelligence.sourceQuality = source_quality
    intelligence.completeness = completeness(opportunity)
    intelligence.freshness = "fresh"
    intelligence.dossierStatus = "verified" if source_quality == 1 and intelligence.completeness >= 0.7 else "normalized"
    intelligence.reviewReasons = []
    if not opportunity.deadline:
        intelligence.reviewReasons.append("Deadline not found")
    if not opportunity.applicationUrl:
        intelligence.reviewReasons.append("Application URL not found")
    if any(req.confidence < 0.7 or req.interpretation in {AttributionBasis.inferred, AttributionBasis.conflicting} for req in requirements):
        intelligence.reviewReasons.append("One or more requirements need human review")
    if intelligence.reviewReasons:
        intelligence.dossierStatus = "review_required"
    opportunity.intelligence = intelligence
    opportunity.intelligence.canonicalFingerprint = canonical_fingerprint(opportunity)
    opportunity.intelligence.completeness = completeness(opportunity)
    return opportunity


def change_summary(previous: Opportunity, current: Opportunity) -> list[str]:
    changes: list[str] = []
    fields: list[tuple[str, Any, Any]] = [
        ("deadline", previous.deadline, current.deadline),
        ("status", previous.status, current.status),
        ("value", previous.value.model_dump(), current.value.model_dump()),
        ("application URL", str(previous.applicationUrl or ""), str(current.applicationUrl or "")),
        ("requirements", [r.statement for r in previous.requirements], [r.statement for r in current.requirements]),
    ]
    for label, before, after in fields:
        if before != after:
            changes.append(f"{label} changed")
    return changes
