---
name: norn-opportunity-strategy
description: Negotiate and deliver a custom, evidence-backed opportunity strategy for technical developers, teams, and projects pursuing grants, hackathons, bounties, partnerships, paid integrations, or RFPs.
---

# Norn Opportunity Strategy

## Service type

A2A negotiated service. This is separate from the deterministic, pay-per-call Norn Opportunity Brief A2MCP endpoint.

## Trigger intents

Use this service when the requester asks for a custom opportunity strategy, funding pipeline design, campaign plan, application portfolio, evidence remediation plan, or multi-opportunity execution roadmap.

Do not use this A2A service for a single deterministic ranking call. Route that request to `norn_opportunity_brief` instead.

## Required discovery inputs

Collect before quoting:

- target opportunity classes and ecosystems;
- delivery deadline and urgency;
- capability profile and evidence links;
- number of opportunities or campaigns in scope;
- desired deliverables;
- review stakeholders and approval authority;
- excluded claims, actions, and regulated constraints.

Never treat claimed or aspirational work as verified evidence.

## Scope negotiation

Return a written scope containing:

- objectives and explicit exclusions;
- inputs the buyer must provide;
- deliverables and file formats;
- milestones and acceptance criteria;
- delivery date;
- revision allowance;
- quoted project price and payment method;
- cancellation and dispute terms.

Reject or re-scope requests that require fabricated credentials, automatic application submission, custody, transaction signing, or broadcasting for the buyer.

## Pricing strategy

Pricing is negotiated per project after discovery. Quote according to scope, number of opportunities, evidence complexity, urgency, and revision load. State the exact marketplace task escrow, acceptance, and arbitration terms shown by the live OKX.AI task runtime. Do not represent the separate general Agent Payments escrow product as active or interchangeable.

## Delivery package

A normal delivery may include:

1. verified capability and evidence map;
2. ranked opportunity portfolio with rationale;
3. evidence-gap remediation plan;
4. timeline, owners, dependencies, and next actions;
5. draft application materials clearly marked as drafts;
6. provenance index linking every material claim to its source;
7. final review checklist requiring human approval before submission.

## Quality gates

- Every opportunity has a source URL and timestamp.
- Scores and recommendations include reasons.
- Missing evidence remains visibly missing.
- Drafts never imply submission or acceptance.
- Reusable secrets, payment credentials, private keys, and payment signatures are never retained or returned.

## Revision policy

One consolidated revision round is included unless the negotiated scope states otherwise. A revision may clarify or refine agreed deliverables; new opportunity classes, new campaigns, new data sources, or materially expanded research require a new quote.

## Cancellation policy

Before work begins, cancellation closes the task without delivery. After work begins, follow the accepted agreement and the cancellation states exposed by the live OKX.AI task runtime. Preserve completed milestone evidence and never promise an off-platform refund or a settlement path the task runtime does not expose.

## Dispute policy

Preserve the agreed scope, milestone evidence, delivery digests, timestamps, and buyer feedback. Escalate through the OKX.AI A2A marketplace arbitration path shown for the task. The current ASP guide states that the ASP may initiate arbitration within one day and may need to bond 5% of the task reward; confirm the live terms before acceptance. Do not conflate this task-marketplace mechanism with the separate general Agent Payments escrow product.

## Terminal states

Use one of: `declined`, `quoted`, `accepted`, `in_progress`, `awaiting_buyer_input`, `delivered`, `revision_requested`, `completed`, `cancelled`, `disputed`.
