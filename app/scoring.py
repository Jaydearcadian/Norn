from __future__ import annotations

import json
from hashlib import sha256

from .gaps import identify_gaps
from .matching import deadline_days, profile_terms, similarity, tokens
from .models import CapabilityProfile, CriterionScore, FitAssessment, Opportunity

WEIGHTS = {"eligibility": 22, "technicalFit": 18, "strategicAlignment": 14, "evidenceStrength": 16, "rewardValue": 10, "preparationCost": 7, "deadlinePressure": 5, "competitiveIntensity": 3, "longTermValue": 5}


def _criterion(key: str, label: str, ratio: float, reason: str) -> CriterionScore:
    maximum = WEIGHTS[key]
    return CriterionScore(key=key, label=label, score=round(max(0.0, min(maximum, ratio * maximum)), 2), maximum=maximum, reason=reason)


def _value_ratio(opportunity: Opportunity, minimum_value: float) -> float:
    value = opportunity.value.maximum or opportunity.value.minimum or 0
    if value <= 0:
        return 0.35
    return min(1.0, value / max(max(minimum_value, 5000), 1))


def assess_fit(profile: CapabilityProfile, opportunity: Opportunity) -> FitAssessment:
    gaps = identify_gaps(profile, opportunity)
    mandatory = [gap for gap, req in zip(gaps, opportunity.requirements) if req.mandatory]
    total_requirements = max(len(mandatory), 1)
    verified = sum(item.status == "verified" for item in mandatory)
    partial = sum(item.status == "partial" for item in mandatory)
    missing = sum(item.status == "missing" for item in mandatory)
    unknown = sum(item.status == "unknown" for item in mandatory)
    failed = sum(item.status == "failed" for item in mandatory)

    excluded = opportunity.type in profile.constraints.excludedCategories
    max_value = opportunity.value.maximum or opportunity.value.minimum or 0
    value_block = max_value > 0 and max_value < profile.constraints.minimumValue
    hard_eligibility = "failed" if excluded or value_block or failed else "unknown" if unknown else "met"
    eligibility_ratio = 0 if hard_eligibility == "failed" else verified / total_requirements if hard_eligibility == "unknown" else (verified + 0.55 * partial) / total_requirements

    desired = tokens(" ".join([*opportunity.preferredCapabilities, *opportunity.ecosystems, opportunity.summary]))
    technical_ratio = min(1.0, similarity(profile_terms(profile), desired) * 2.6)
    preferred = tokens(" ".join(profile.preferredOpportunities + profile.supportedEcosystems))
    strategic_ratio = min(1.0, similarity(preferred, tokens(f"{opportunity.type} {' '.join(opportunity.ecosystems)}")) * 3.0)
    evidence_ratio = min(1.0, (verified + 0.45 * partial) / total_requirements)
    effort_ratio = {"low": 1.0, "medium": 0.62, "high": 0.28}[opportunity.applicationEffort]
    days = deadline_days(opportunity)
    if days is None:
        deadline_ratio, deadline_reason = 0.55, "No verified deadline is available; feasibility remains unknown."
    elif days < 0:
        deadline_ratio, deadline_reason = 0.0, "The verified deadline has passed."
    elif days <= 2:
        deadline_ratio, deadline_reason = 0.3, f"Only {days} day(s) remain, creating execution risk."
    elif days <= 7:
        deadline_ratio, deadline_reason = 0.75, f"{days} days remain; immediate preparation is required."
    else:
        deadline_ratio, deadline_reason = 1.0, f"{days} days remain, leaving a workable preparation window."

    criteria = [
        _criterion("eligibility", "Eligibility", eligibility_ratio, f"Hard eligibility is {hard_eligibility}: {verified} met, {missing} missing, {unknown} unknown."),
        _criterion("technicalFit", "Technical fit", technical_ratio, "Compared verified and claimed capabilities with structured technical fields."),
        _criterion("strategicAlignment", "Strategic alignment", strategic_ratio, "Compared opportunity classification with profile preferences."),
        _criterion("evidenceStrength", "Evidence strength", evidence_ratio, "Only verified evidence receives full credit."),
        _criterion("rewardValue", "Reward value", _value_ratio(opportunity, profile.constraints.minimumValue), "Compared normalized commercial value with profile constraints."),
        _criterion("preparationCost", "Preparation cost", effort_ratio, f"Application effort is {opportunity.applicationEffort} and is explicitly marked inferred."),
        _criterion("deadlinePressure", "Deadline pressure", deadline_ratio, deadline_reason),
        _criterion("competitiveIntensity", "Competitive intensity", {"low": 1, "medium": .6, "high": .3, "unknown": .5}[opportunity.competitiveIntensity], f"Competition is {opportunity.competitiveIntensity}."),
        _criterion("longTermValue", "Long-term value", opportunity.longTermValue / 100, "Uses Norn's separately attributed long-term estimate."),
    ]
    score = round(sum(item.score for item in criteria))
    if hard_eligibility == "failed" or (days is not None and days < 0):
        eligibility = "ineligible"
    elif hard_eligibility == "unknown":
        eligibility = "uncertain"
    elif missing == 0 and verified >= max(1, total_requirements // 2):
        eligibility = "eligible"
    else:
        eligibility = "likely" if missing <= max(1, total_requirements // 3) else "uncertain"
    recommendation = "skip" if eligibility == "ineligible" or score < 40 else "close_gaps_first" if missing or unknown else "pursue_now" if score >= 70 else "watch"
    probability = max(.05, min(.95, score / 100))
    monetary = max_value or opportunity.value.minimum or 1000
    expected_value_index = round((monetary * probability * (.5 + opportunity.longTermValue / 100)) / {"low": 1, "medium": 1.8, "high": 3}[opportunity.applicationEffort], 2)
    evidence_by_id = {item.id: item for item in profile.evidence}
    strong = []
    for gap in gaps:
        for evidence_id in gap.matchedEvidenceIds:
            evidence = evidence_by_id.get(evidence_id)
            if evidence and evidence.status.value == "verified" and evidence.label not in strong:
                strong.append(evidence.label)
    profile_version = sha256(json.dumps(profile.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    return FitAssessment(
        opportunityId=opportunity.id, opportunityVersion=opportunity.intelligence.version,
        profileVersion=profile_version, scoringEngineVersion="norn-score-v2",
        score=score, expectedValueIndex=expected_value_index, eligibility=eligibility,
        hardEligibility=hard_eligibility, recommendation=recommendation, criteria=criteria,
        strongEvidence=strong, missingEvidence=[item.requirement for item in gaps if item.status in {"missing", "partial", "unknown"}],
        rationale=[f"Norn Score is {score}/100.", f"Hard eligibility is {hard_eligibility}; unknown rules receive no partial eligibility credit.", deadline_reason],
        gaps=gaps,
    )
