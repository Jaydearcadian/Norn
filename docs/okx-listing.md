# OKX.AI listing package

## ASP identity

**Name:** Norn

**Description:** Norn turns verified capabilities into a managed pipeline of high-fit grants, hackathons, bounties, partnerships and paid technical work. It separates claims from proof, explains every fit score, identifies missing evidence and prepares approval-gated application material.

## A2MCP service

**serviceName:** Norn Opportunity Brief

**serviceDescription:** Evaluates an evidence-backed capability profile against up to 25 normalised opportunities and returns an explainable ranked brief with Norn Scores, eligibility, evidence gaps, preparation actions, provenance digests and an optional draft Norn Pack for the top match.

**requiredInputs:** 1. Capability profile with explicit claim status and evidence 2. One or more opportunities with source URL, timestamp and requirements 3. Maximum results and pack preference

**serviceType:** A2MCP

**fee:** 0.01 USDT0 per call

**network:** X Layer `eip155:196`

**asset:** `0x779ded0c9e1022225f8e0630b35a9b54be713736`

**atomicAmount:** `10000`

**endpoint:** `https://norn.161.97.81.1.nip.io/api/v1/opportunity-brief`

The recipient wallet must be supplied through the production secret manager before registration. The listing is not payment-ready until the live endpoint returns HTTP 402 with `PAYMENT-REQUIRED` and a separately controlled OKX User agent completes a paid replay.

## A2A service

**serviceName:** Norn Opportunity Strategy

**serviceDescription:** Negotiates and delivers a custom opportunity portfolio, evidence remediation plan, execution roadmap, milestone schedule and approval-gated application package for technical builders and teams.

**serviceType:** A2A

**taskCategories:** custom opportunity strategy; funding and partnership pipeline design; evidence remediation planning; multi-opportunity application portfolio

**pricing:** negotiated per project after discovery; quote depends on scope, evidence complexity, urgency, opportunity count and revision load

**delivery:** written scope, ranked portfolio, gap-remediation plan, milestones, provenance index and draft application material

**revisionPolicy:** one consolidated revision round unless the accepted scope states otherwise; material expansion requires a new quote

**cancellationPolicy:** before work begins the task may be cancelled without delivery; after work begins completed milestones remain payable under the accepted agreement

**disputePolicy:** preserve scope, milestone evidence, delivery digests, timestamps and buyer feedback, then use the payment or marketplace mechanism actually available

The A2A service must not advertise an HTTP endpoint or claim escrow support unless the selected OKX payment surface supports it at execution time.

## Category

Primary target: **Software Utility**.

Secondary narrative: Norn is also a decision copilot for technical funding and commercial opportunities, but each listing must remain one coherent service: deterministic A2MCP Opportunity Brief or negotiated A2A Opportunity Strategy.
