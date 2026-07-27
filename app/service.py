from __future__ import annotations

from .digests import sha256_digest
from .models import OpportunityBriefRequest, OpportunityBriefResponse, Provenance, RankedOpportunity
from .pack import prepare_pack
from .scoring import assess_fit


def build_opportunity_brief(request: OpportunityBriefRequest) -> OpportunityBriefResponse:
    ranked = [RankedOpportunity(opportunity=item, assessment=assess_fit(request.profile, item)) for item in request.opportunities]
    ranked.sort(key=lambda item: (item.assessment.score, item.assessment.expectedValueIndex), reverse=True)
    ranked = ranked[: request.maximumResults]
    top_pack = prepare_pack(request.profile, ranked[0].opportunity, ranked[0].assessment) if request.includePackForTopOpportunity and ranked else None
    request_dump = request.model_dump(mode="json")
    provisional = {"ranked": [item.model_dump(mode="json") for item in ranked], "topPack": top_pack.model_dump(mode="json") if top_pack else None}
    snapshot_ids = sorted({snapshot_id for item in ranked for snapshot_id in item.opportunity.intelligence.sourceSnapshotIds})
    provenance = Provenance(
        requestDigest=sha256_digest(request_dump), resultDigest=sha256_digest(provisional),
        sourceUrls=[str(item.opportunity.sourceUrl) for item in ranked],
        sourceTimestamps=[item.opportunity.sourceTimestamp for item in ranked],
        sourceSnapshotIds=snapshot_ids, engineVersion="norn-score-v2",
    )
    summary = f"Evaluated {len(request.opportunities)} versioned dossier(s). " + (f"Top match: {ranked[0].opportunity.title} at {ranked[0].assessment.score}/100." if ranked else "No candidates remained.")
    return OpportunityBriefResponse(ranked=ranked, topPack=top_pack, summary=summary, provenance=provenance)
