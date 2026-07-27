# Norn

**Find where your proof has value.**

Norn converts a person or project's verified capabilities into a managed pipeline of grants, hackathons, bounties, accelerators, partnerships, technical work and RFPs.

It is built as an OKX.AI Agent Service Provider candidate with six connected product surfaces:

- **Norn Profile** — verified capabilities, projects, constraints and evidence.
- **Norn Feed** — normalised opportunities with source provenance.
- **Norn Score** — explainable fit and expected-value ranking.
- **Norn Gaps** — verified, partial and missing requirement analysis.
- **Norn Pack** — approval-gated application drafts using verified facts only.
- **Norn Watch** — deadlines, next actions and submission follow-through.

## Current status

`PUBLIC_DEPLOYED`

The application, scoring engine, evidence-gap engine, pack generator, dashboard, local 402 harness, replay protection, redaction and deployment definitions are implemented and tested. A public HTTPS free-mode deployment is verified. Production x402 settlement, OKX ASP registration, marketplace activation and independent consumer proof require external credentials and cannot truthfully be marked complete yet.

## Run

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

The suite covers:

- Norn Score and evidence weighting;
- verified versus claimed capability handling;
- Norn Pack claim exclusion;
- Profile, Feed, Score and Pack APIs;
- unpaid HTTP 402 challenge;
- valid local paid replay;
- duplicate replay rejection;
- invalid-input rejection before paid business execution;
- credential redaction.

## Production payment

The default `PAYMENT_MODE=free` makes local exploration easy. `PAYMENT_MODE=demo` enables a local-only 402 conformance harness. It is blocked in production.

For production:

1. Install the pinned dependencies from `requirements.txt`, including `okxweb3-app-x402[evm]==0.1.1`.
2. Set `PAYMENT_MODE=okx`.
3. Provide `PAY_TO_ADDRESS`, `OKX_API_KEY`, `OKX_SECRET_KEY` and `OKX_PASSPHRASE` through the hosting platform's secret manager.
4. Set `PAYMENT_NETWORK=eip155:196` and `PUBLIC_BASE_URL` to the real HTTPS origin.
5. Run the public conformance and independent consumer tests in `docs/deployment.md`.

A production deployment left in `PAYMENT_MODE=free` remains reachable for inspection but reports degraded health and `ready: false`; it is not payment-ready.

The protected endpoint is:

```text
POST /api/v1/opportunity-brief
```

It accepts a self-contained capability profile and one to twenty-five normalised opportunities, then returns ranked Norn Scores, evidence gaps, provenance digests and an optional Norn Pack for the top result.

## Safety boundary

Norn does not submit applications by default. It does not invent experience, deployments, customers, revenue, partnerships, audits or on-chain proof. Generated packs remain drafts until a person explicitly approves them.
