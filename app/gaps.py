from __future__ import annotations

from .matching import match_requirement
from .models import CapabilityProfile, GapItem, Opportunity


def identify_gaps(profile: CapabilityProfile, opportunity: Opportunity) -> list[GapItem]:
    return [match_requirement(profile, requirement) for requirement in opportunity.requirements]
