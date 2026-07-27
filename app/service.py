from __future__ import annotations

from .digests import sha256_digest
from .models import OpportunityBriefRequest, OpportunityBriefResponse, Provenance, RankedOpportunity
from .pack import prepare_pack
from .scoring import assess_fit


def build_opportunity_brief(request: OpportunityBriefRequest) -> OpportunityBriefResponse:
    ranked = [
        RankedOpportunity(opportunity=opportunity, assessment=assess_fit(request.profile, opportunity))
        for opportunity in request.opportunities
    ]
    ranked.sort(key=lambda item: (item.assessment.score, item.assessment.expectedValueIndex), reverse=True)
    ranked = ranked[: request.maximumResults]
    top_pack = None
    if request.includePackForTopOpportunity and ranked:
        top = ranked[0]
        top_pack = prepare_pack(request.profile, top.opportunity, top.assessment)

    request_dump = request.model_dump(mode="json")
    provisional = {
        "ranked": [item.model_dump(mode="json") for item in ranked],
        "topPack": top_pack.model_dump(mode="json") if top_pack else None,
    }
    provenance = Provenance(
        requestDigest=sha256_digest(request_dump),
        resultDigest=sha256_digest(provisional),
        sourceUrls=[str(item.opportunity.sourceUrl) for item in ranked],
        sourceTimestamps=[item.opportunity.sourceTimestamp for item in ranked],
    )
    summary = (
        f"Evaluated {len(request.opportunities)} opportunity candidate(s). "
        + (f"Top match: {ranked[0].opportunity.title} at {ranked[0].assessment.score}/100." if ranked else "No candidates remained.")
    )
    return OpportunityBriefResponse(ranked=ranked, topPack=top_pack, summary=summary, provenance=provenance)
