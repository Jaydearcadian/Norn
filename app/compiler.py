from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .digests import sha256_digest
from .models import (
    AttributionBasis, EvaluationCriterion, FieldAttribution, Opportunity,
    OpportunityRequirement, OpportunityTiming, OpportunityValue, SourceSnapshot,
)

TYPE_MARKERS = {
    "hackathon": ("hackathon", "buildathon"), "grant": ("grant", "funding call"),
    "bounty": ("bounty", "rewarded issue", "reward"), "accelerator": ("accelerator", "cohort"),
    "rfp": ("request for proposal", "rfp", "procurement"), "job": ("job", "role", "hiring"),
    "research": ("research funding", "research call"), "partnership": ("partnership", "integration programme"),
}

PAGE_MARKERS = {
    "rules": ("rules", "eligibility", "terms and conditions"), "faq": ("faq", "frequently asked"),
    "prizes": ("prize", "rewards", "funding breakdown"), "application": ("apply", "application form", "submit"),
    "documentation": ("documentation", "developer docs", "api reference"), "track": ("track", "category prize"),
    "programme": ("programme", "program", "hackathon", "grant"),
}

CURRENCY_RE = re.compile(r"(?P<symbol>[$£€])\s?(?P<amount>\d[\d,]*(?:\.\d+)?)|(?P<amount2>\d[\d,]*(?:\.\d+)?)\s?(?P<currency>USD|USDT|USDC|GBP|EUR)", re.I)
DATE_RE = re.compile(r"(?P<date>20\d{2}[-/]\d{1,2}[-/]\d{1,2})")
REQUIREMENT_LINE_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s*(?P<statement>.{8,})$")


def snapshot_id(url: str, digest: str) -> str:
    return "snapshot_" + sha256_digest({"url": url, "digest": digest})[:24]


def source_id(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return "source_" + sha256_digest({"host": parsed.netloc.lower(), "path": path.lower()})[:24]


def classify_page(title: str, text: str, content_type: str, url: str) -> str:
    combined = f"{title} {text[:3000]} {url}".lower()
    if "github.com" in url and "/issues/" in url:
        return "github_issue"
    for page_type, markers in PAGE_MARKERS.items():
        if any(marker in combined for marker in markers):
            return page_type
    if "json" in content_type or "rss" in content_type or "xml" in content_type:
        return "programme"
    return "unknown"


def classify_type(title: str, summary: str, labels: list[str] | None = None) -> str:
    combined = " ".join([title, summary, *(labels or [])]).lower()
    for opportunity_type, markers in TYPE_MARKERS.items():
        if any(marker in combined for marker in markers):
            return opportunity_type
    return "other"


def normalize_issuer(value: str | None, url: str) -> str:
    if value and value.strip():
        cleaned = re.sub(r"\s+", " ", value).strip()
        aliases = {"okx ai": "OKX.AI", "okx.ai": "OKX.AI", "github": "GitHub"}
        return aliases.get(cleaned.lower(), cleaned)
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title() or "Unknown issuer"


def extract_value(text: str, raw: dict[str, Any] | None = None) -> tuple[OpportunityValue, FieldAttribution]:
    raw = raw or {}
    supplied = raw.get("value")
    if isinstance(supplied, dict):
        value = OpportunityValue.model_validate(supplied)
        return value, FieldAttribution(basis=AttributionBasis.explicit, confidence=0.95, originalValue=supplied)
    matches = list(CURRENCY_RE.finditer(text[:20000]))
    if not matches:
        return OpportunityValue(), FieldAttribution(basis=AttributionBasis.unknown, confidence=0.0)
    amounts: list[float] = []
    currency = "USD"
    symbols = {"$": "USD", "£": "GBP", "€": "EUR"}
    for match in matches[:20]:
        raw_amount = match.group("amount") or match.group("amount2")
        try:
            amounts.append(float(raw_amount.replace(",", "")))
        except (TypeError, ValueError):
            continue
        currency = (match.group("currency") or symbols.get(match.group("symbol"), currency)).upper()
    if not amounts:
        return OpportunityValue(), FieldAttribution(basis=AttributionBasis.unknown, confidence=0.0)
    return OpportunityValue(minimum=min(amounts), maximum=max(amounts), currency=currency, components=["cash"]), FieldAttribution(basis=AttributionBasis.explicit, confidence=0.72, originalValue=[m.group(0) for m in matches[:5]])


def parse_date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.max.time(), tzinfo=timezone.utc)
    text = str(value).strip().replace("/", "-")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        match = DATE_RE.search(text)
        if not match:
            return None
        try:
            return datetime.fromisoformat(match.group("date").replace("/", "-")).replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def extract_timing(text: str, raw: dict[str, Any] | None = None) -> tuple[OpportunityTiming, FieldAttribution]:
    raw = raw or {}
    timing_raw = raw.get("timing") if isinstance(raw.get("timing"), dict) else {}
    deadline_raw = timing_raw.get("submissionDeadline") or raw.get("deadline") or raw.get("submission_deadline")
    deadline = parse_date(deadline_raw)
    basis = AttributionBasis.explicit if deadline else AttributionBasis.unknown
    confidence = 0.98 if deadline else 0.0
    if not deadline:
        candidates = DATE_RE.findall(text[:20000])
        if candidates:
            deadline = parse_date(candidates[-1])
            basis, confidence = AttributionBasis.inferred, 0.45
    return OpportunityTiming(
        opensAt=parse_date(timing_raw.get("opensAt") or raw.get("opens_at")),
        registrationDeadline=parse_date(timing_raw.get("registrationDeadline") or raw.get("registration_deadline")),
        submissionDeadline=deadline,
        decisionDate=parse_date(timing_raw.get("decisionDate") or raw.get("decision_date")),
        timezone=timing_raw.get("timezone") or raw.get("timezone"),
        rolling=bool(timing_raw.get("rolling") or raw.get("rolling", False)),
    ), FieldAttribution(basis=basis, confidence=confidence, originalValue=deadline_raw)


def requirement_category(statement: str) -> str:
    lowered = statement.lower()
    markers = {
        "eligibility": ("eligible", "must be", "applicant", "resident", "citizen"),
        "deployment": ("deploy", "live", "marketplace", "production"),
        "deliverable": ("demo", "video", "deck", "repository", "report"),
        "application": ("form", "submit", "word limit", "attachment"),
        "technical": ("build", "integrate", "api", "sdk", "contract", "code"),
        "team": ("team", "member"), "legal": ("entity", "incorporated", "terms"),
        "geography": ("country", "region", "resident", "geography"), "evidence": ("proof", "evidence", "receipt"),
    }
    for category, values in markers.items():
        if any(marker in lowered for marker in values):
            return category
    return "other"


def compile_requirements(raw_requirements: Any, text: str, snapshot: SourceSnapshot) -> list[OpportunityRequirement]:
    statements: list[str] = []
    if isinstance(raw_requirements, list):
        for item in raw_requirements:
            if isinstance(item, str): statements.append(item)
            elif isinstance(item, dict) and item.get("statement"): statements.append(str(item["statement"]))
    elif isinstance(raw_requirements, str):
        statements.extend(line.strip() for line in raw_requirements.splitlines() if line.strip())
    if not statements:
        for line in text.splitlines():
            match = REQUIREMENT_LINE_RE.match(line.strip())
            if match and any(marker in match.group("statement").lower() for marker in ("must", "required", "submit", "eligible", "build", "provide")):
                statements.append(match.group("statement").strip())
    unique: list[str] = []
    seen = set()
    for statement in statements:
        normalized = re.sub(r"\s+", " ", statement).strip(" .")
        if len(normalized) < 8 or normalized.lower() in seen:
            continue
        seen.add(normalized.lower()); unique.append(normalized)
    requirements = []
    for index, statement in enumerate(unique[:50]):
        optional = any(marker in statement.lower() for marker in ("optional", "nice to have", "preferred but not required"))
        digest = hashlib.sha256(statement.encode()).hexdigest()
        requirements.append(OpportunityRequirement(
            id=f"req_{digest[:16]}_{index}", category=requirement_category(statement), statement=statement,
            mandatory=not optional, acceptedEvidence=[], sourceSnapshotId=snapshot.id,
            sourceExcerptDigest="sha256:" + digest, confidence=0.92 if raw_requirements else 0.62,
            interpretation=AttributionBasis.explicit if raw_requirements else AttributionBasis.inferred,
        ))
    return requirements


def canonical_fingerprint(issuer: str, programme: str, cycle: str | None, track: str | None, deadline: date | None, application_url: str) -> str:
    return sha256_digest({
        "issuer": issuer.lower().strip(), "programme": programme.lower().strip(),
        "cycle": (cycle or "").lower().strip(), "track": (track or "").lower().strip(),
        "deadline": str(deadline or ""), "applicationUrl": application_url.rstrip("/").lower(),
    })


def compile_candidate(raw: dict[str, Any], snapshot: SourceSnapshot, adapter: str) -> list[Opportunity]:
    url = str(raw.get("applicationUrl") or raw.get("application_url") or raw.get("html_url") or raw.get("url") or snapshot.url)
    title = str(raw.get("title") or snapshot.title or "Untitled opportunity").strip()
    summary = str(raw.get("summary") or raw.get("description") or raw.get("body") or "").strip()[:4000]
    issuer = normalize_issuer(raw.get("issuer") or raw.get("organisation") or raw.get("organization"), url)
    programme = str(raw.get("programme") or raw.get("program") or title).strip()
    cycle = str(raw.get("cycle") or raw.get("edition") or "").strip() or None
    tracks = raw.get("tracks") if isinstance(raw.get("tracks"), list) else []
    if tracks:
        compiled: list[Opportunity] = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            child = {**raw, **track, "programme": programme, "parentOpportunityId": raw.get("id")}
            child.pop("tracks", None)
            compiled.extend(compile_candidate(child, snapshot, adapter))
        return compiled
    track = str(raw.get("track") or raw.get("lot") or raw.get("theme") or "").strip() or None
    opportunity_type = raw.get("type") or classify_type(title, summary, [str(v) for v in raw.get("labels", [])])
    if opportunity_type not in TYPE_MARKERS and opportunity_type not in {"contract", "investment", "speaking", "publishing", "competition", "incentive", "other"}:
        opportunity_type = "other"
    requirements = compile_requirements(raw.get("requirements"), summary, snapshot)
    timing, timing_attr = extract_timing(summary, raw)
    value, value_attr = extract_value(summary, raw)
    deadline = timing.submissionDeadline.date() if timing.submissionDeadline else None
    application_url = url
    fingerprint = canonical_fingerprint(issuer, programme, cycle, track, deadline, application_url)
    canonical_id = str(raw.get("canonicalId") or raw.get("id") or f"opp_{fingerprint[:24]}")
    completeness_checks = [bool(title), bool(issuer), bool(url), bool(requirements), bool(deadline), value.minimum is not None or value.maximum is not None]
    completeness = sum(completeness_checks) / len(completeness_checks)
    source_quality = 1.0 if snapshot.sourceType == "official" else 0.65 if snapshot.sourceType == "aggregator" else 0.5
    extraction_confidence = 0.9 if adapter in {"structured_json", "github"} else 0.62
    confidence = round(min(1.0, source_quality * 0.55 + extraction_confidence * 0.45), 2)
    review_status = "pending" if confidence < 0.75 or completeness < 0.6 or not requirements else "not_required"
    lifecycle = "verified" if snapshot.sourceType == "official" and confidence >= 0.85 and completeness >= 0.7 else "normalized"
    field_provenance = {
        "title": FieldAttribution(basis=AttributionBasis.explicit, confidence=0.95, sourceSnapshotIds=[snapshot.id], originalValue=title),
        "issuer": FieldAttribution(basis=AttributionBasis.explicit if raw.get("issuer") else AttributionBasis.inferred, confidence=0.9 if raw.get("issuer") else 0.58, sourceSnapshotIds=[snapshot.id]),
        "value": value_attr.model_copy(update={"sourceSnapshotIds": [snapshot.id]}),
        "timing": timing_attr.model_copy(update={"sourceSnapshotIds": [snapshot.id]}),
        "applicationEffort": FieldAttribution(basis=AttributionBasis.inferred, confidence=0.7, sourceSnapshotIds=[snapshot.id], reasons=[f"{len(requirements)} extracted requirements", f"adapter={adapter}"]),
    }
    effort = "high" if len(requirements) >= 5 else "medium" if len(requirements) >= 2 else "low"
    return [Opportunity(
        id=canonical_id, canonicalId=canonical_id, canonicalFingerprint=fingerprint, title=title,
        type=opportunity_type, issuer=issuer, programme=programme, cycle=cycle, track=track,
        parentOpportunityId=raw.get("parentOpportunityId"), independentlyActionable=bool(track or raw.get("independentlyActionable", True)),
        summary=summary, themes=[str(v) for v in raw.get("themes", [])], technicalDomains=[str(v) for v in raw.get("technicalDomains", raw.get("technical_domains", []))],
        value=value, timing=timing, deadline=deadline,
        eligibility=[r for r in requirements if r.category in {"eligibility", "geography", "team", "legal"}],
        requirements=[r for r in requirements if r.category not in {"eligibility", "geography", "team", "legal", "deliverable"}],
        deliverables=[r for r in requirements if r.category == "deliverable"],
        evaluation=[EvaluationCriterion.model_validate(v) for v in raw.get("evaluation", []) if isinstance(v, dict)],
        applicationUrl=application_url, applicationSteps=[str(v) for v in raw.get("applicationSteps", [])],
        preferredCapabilities=[str(v) for v in raw.get("preferredCapabilities", raw.get("skills", []))], ecosystems=[str(v) for v in raw.get("ecosystems", [])],
        sourceUrl=snapshot.url, sourceTimestamp=snapshot.retrievedAt, sourceType=snapshot.sourceType,
        sourceSnapshotIds=[snapshot.id], fieldProvenance=field_provenance,
        applicationEffort=effort, competitiveIntensity=str(raw.get("competitiveIntensity", "unknown")),
        longTermValue=int(raw.get("longTermValue", 50)), status=str(raw.get("status", "unknown")),
        lifecycleStatus=lifecycle, normalizationConfidence=confidence, completeness=round(completeness, 2),
        lastVerifiedAt=snapshot.retrievedAt if lifecycle == "verified" else None, reviewStatus=review_status,
    )]
