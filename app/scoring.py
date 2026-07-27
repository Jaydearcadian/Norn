from __future__ import annotations

from .gaps import identify_gaps
from .matching import deadline_days, profile_terms, similarity, tokens
from .models import CapabilityProfile, CriterionScore, FitAssessment, Opportunity

SCORING_ENGINE_VERSION = "norn-score-v2"
WEIGHTS = {
    "eligibility": 22, "technicalFit": 18, "strategicAlignment": 14,
    "evidenceStrength": 16, "rewardValue": 10, "preparationCost": 7,
    "deadlinePressure": 5, "competitiveIntensity": 3, "longTermValue": 5,
}


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
    total_requirements = max(len(gaps), 1)
    verified = sum(item.status == "verified" for item in gaps)
    partial = sum(item.status == "partial" for item in gaps)
    missing = sum(item.status == "missing" for item in gaps)

    eligibility_gaps = [item for item in gaps if item.category in {"eligibility", "geography", "team", "legal"} and item.mandatory]
    explicit_failures = [item for item in eligibility_gaps if item.eligibilityResult == "failed"]
    unknown_eligibility = [item for item in eligibility_gaps if item.eligibilityResult == "unknown"]
    if explicit_failures:
        hard_eligibility = "failed"
    elif unknown_eligibility:
        hard_eligibility = "unknown"
    else:
        hard_eligibility = "met"

    excluded = opportunity.type in profile.constraints.excludedCategories
    min_value = profile.constraints.minimumValue
    max_value = opportunity.value.maximum or opportunity.value.minimum or 0
    value_block = max_value > 0 and max_value < min_value
    if excluded or value_block or hard_eligibility == "failed":
        eligibility_ratio = 0.0
    elif hard_eligibility == "unknown":
        eligibility_ratio = 0.35
    else:
        eligibility_ratio = (verified + 0.55 * partial) / total_requirements

    profile_capabilities = profile_terms(profile)
    desired = tokens(" ".join([*opportunity.preferredCapabilities, *opportunity.ecosystems, *opportunity.technicalDomains, opportunity.summary]))
    technical_ratio = min(1.0, similarity(profile_capabilities, desired) * 2.6)
    preferred = tokens(" ".join(profile.preferredOpportunities + profile.supportedEcosystems))
    strategic_ratio = min(1.0, similarity(preferred, tokens(f"{opportunity.type} {' '.join(opportunity.ecosystems)} {' '.join(opportunity.themes)}")) * 3.0)
    evidence_ratio = min(1.0, (verified + 0.45 * partial) / total_requirements)
    value_ratio = _value_ratio(opportunity, min_value)
    effort_ratio = {"low": 1.0, "medium": 0.62, "high": 0.28}[opportunity.applicationEffort]

    days = deadline_days(opportunity)
    if days is None:
        deadline_ratio, deadline_reason = 0.45, "No verified deadline is available; feasibility remains unknown."
    elif days < 0:
        deadline_ratio, deadline_reason = 0.0, "The recorded deadline has passed."
    elif days <= 2:
        deadline_ratio, deadline_reason = 0.3, f"Only {days} day(s) remain, creating execution risk."
    elif days <= 7:
        deadline_ratio, deadline_reason = 0.75, f"{days} days remain; immediate preparation is required."
    else:
        deadline_ratio, deadline_reason = 1.0, f"{days} days remain, leaving a workable preparation window."

    competition_ratio = {"low": 1.0, "medium": 0.6, "high": 0.3, "unknown": 0.5}[opportunity.competitiveIntensity]
    long_term_ratio = opportunity.longTermValue / 100
    criteria = [
        _criterion("eligibility", "Eligibility", eligibility_ratio, f"Hard eligibility is {hard_eligibility}; {len(unknown_eligibility)} mandatory condition(s) remain unknown."),
        _criterion("technicalFit", "Technical fit", technical_ratio, "Compared verified and claimed profile capabilities with structured technical domains."),
        _criterion("strategicAlignment", "Strategic alignment", strategic_ratio, "Compared preferred opportunity classes, themes and ecosystems."),
        _criterion("evidenceStrength", "Evidence strength", evidence_ratio, "Only verified evidence receives full credit; claimed evidence receives partial credit."),
        _criterion("rewardValue", "Reward value", value_ratio, "Compared attributed commercial value with the profile minimum."),
        _criterion("preparationCost", "Preparation cost", effort_ratio, f"Application effort is {opportunity.applicationEffort} and is marked as inferred when not issuer-stated."),
        _criterion("deadlinePressure", "Deadline pressure", deadline_ratio, deadline_reason),
        _criterion("competitiveIntensity", "Competitive intensity", competition_ratio, f"Competitive intensity is {opportunity.competitiveIntensity}."),
        _criterion("longTermValue", "Long-term value", long_term_ratio, "Uses the dossier's relationship-value estimate."),
    ]
    score = round(sum(item.score for item in criteria))

    if excluded or value_block or hard_eligibility == "failed" or (days is not None and days < 0):
        eligibility = "ineligible"
    elif hard_eligibility == "unknown":
        eligibility = "uncertain"
    elif missing == 0 and verified >= max(1, total_requirements // 2):
        eligibility = "eligible"
    elif missing <= max(1, total_requirements // 3):
        eligibility = "likely"
    else:
        eligibility = "uncertain"

    if eligibility == "ineligible" or score < 40:
        recommendation = "skip"
    elif missing > 0 and score >= 55:
        recommendation = "close_gaps_first"
    elif score >= 70 and hard_eligibility == "met":
        recommendation = "pursue_now"
    else:
        recommendation = "watch"

    probability = max(0.05, min(0.95, score / 100))
    monetary = max_value or opportunity.value.minimum or 1000
    effort_cost = {"low": 1.0, "medium": 1.8, "high": 3.0}[opportunity.applicationEffort]
    expected_value_index = round((monetary * probability * (0.5 + long_term_ratio)) / effort_cost, 2)
    evidence_by_id = {item.id: item for item in profile.evidence}
    strong = []
    for gap in gaps:
        for evidence_id in gap.matchedEvidenceIds:
            evidence = evidence_by_id.get(evidence_id)
            if evidence and evidence.status.value == "verified" and evidence.label not in strong:
                strong.append(evidence.label)
    missing_evidence = [item.requirement for item in gaps if item.status in {"missing", "partial"}]
    rationale = [
        f"Norn Score is {score}/100 with recommendation '{recommendation}'.",
        f"Assessment key: profile v{profile.version}, opportunity v{opportunity.version}, engine {SCORING_ENGINE_VERSION}.",
        f"Hard eligibility is {hard_eligibility}; {verified} requirements are verified and {missing} are missing.",
        deadline_reason,
    ]
    return FitAssessment(
        opportunityId=opportunity.canonicalId or opportunity.id, opportunityVersion=opportunity.version,
        profileVersion=profile.version, scoringEngineVersion=SCORING_ENGINE_VERSION,
        score=score, expectedValueIndex=expected_value_index, eligibility=eligibility,
        hardEligibility=hard_eligibility, recommendation=recommendation, criteria=criteria,
        strongEvidence=strong, missingEvidence=missing_evidence, rationale=rationale, gaps=gaps,
    )
