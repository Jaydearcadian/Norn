# Norn

**Agentic opportunity intelligence for turning verified capability into action.**

Norn is an AI system that finds grants, hackathons, bounties, accelerators, partnerships, technical work, and RFPs, then evaluates them against a verified capability profile.

The important constraint is that the system distinguishes **evidence from claims**. Norn can rank opportunities and prepare an application pack, but it must not invent experience or submit on the user's behalf without explicit approval.

```text
verified profile
      ↓
opportunity ingestion + provenance
      ↓
fit / expected-value scoring
      ↓
evidence-gap analysis
      ↓
approval-gated application pack
      ↓
watch + follow-through
```

## Product surfaces

- **Profile**: verified capabilities, projects, constraints, and evidence.
- **Feed**: normalized opportunities with source provenance.
- **Score**: explainable fit and expected-value ranking.
- **Gaps**: verified, partial, and missing requirement analysis.
- **Pack**: application drafts generated from verified facts.
- **Watch**: deadlines, next actions, and submission follow-through.

## Current status

`PUBLIC_DEPLOYED`

The application, scoring engine, evidence-gap engine, pack generator, dashboard, local HTTP 402 harness, replay protection, redaction, and deployment definitions are implemented and tested. A public HTTPS free-mode deployment is verified.

Production x402 settlement, external marketplace activation, and independent consumer proof require external credentials and infrastructure. They are not represented as complete here.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
./scripts/run.sh
```

Open `http://localhost:8000`.

## Test

```bash
./scripts/test.sh
```

The suite covers scoring and evidence weighting, verified versus claimed capabilities, claim exclusion from generated packs, core APIs, HTTP 402 challenges, paid replay protection, invalid-input rejection, and credential redaction.

## Payment boundary

The default `PAYMENT_MODE=free` supports local exploration. `PAYMENT_MODE=demo` provides a local-only 402 conformance harness. Production payment requires the appropriate provider credentials and must not rely on the demo mode.

The protected endpoint is:

```text
POST /api/v1/opportunity-brief
```

It accepts a capability profile and normalized opportunities and returns ranked scores, evidence gaps, provenance digests, and an optional pack for the strongest result.

## Safety boundary

Norn does not submit applications by default. It does not invent experience, deployments, customers, revenue, partnerships, audits, or onchain proof. Generated packs remain drafts until a person explicitly approves them.

## Why this project matters

Norn explores a useful agent pattern: **the agent can operate over opportunities without being allowed to manufacture the evidence required to pursue them.**

That makes provenance, evidence, authorization, and human approval first-class parts of the agent loop rather than afterthoughts.
