# Norn

**Find where your proof has value.**

Norn is an opportunity compiler. It turns fragmented, inconsistent source material into versioned, evidence-backed opportunity dossiers, then compares each dossier with a versioned capability profile.

It is built as an OKX.AI Agent Service Provider candidate with six connected product surfaces:

- **Norn Profile** — verified capabilities, projects, constraints and evidence.
- **Norn Feed** — source-backed dossiers with freshness, completeness, changes and fit intelligence.
- **Norn Score** — explainable fit and expected-value ranking keyed to profile, dossier and engine versions.
- **Norn Gaps** — structured mandatory, optional and eligibility requirement analysis.
- **Norn Pack** — approval-gated application drafts using verified facts only.
- **Norn Watch** — deadlines, source changes, next actions and submission follow-through.

## Current status

`PUBLIC_DEPLOYED · NORMALIZATION_V2_IMPLEMENTED_ON_FEATURE_BRANCH`

The deployed service remains the verified public free-mode build. The `agent/opportunity-compiler-v2` branch adds SQLite-backed source snapshots, canonical dossiers, structured requirements, field attribution, versioned deduplication, official HTML/JSON/RSS/GitHub adapters, a review queue and dossier-aware Feed intelligence. Production x402 settlement, OKX registration, marketplace activation, independent consumer proof and a curated 30-opportunity benchmark remain external gates.

## Opportunity Compiler

```text
Discover source bundle
  → capture immutable snapshots
  → classify and extract attributed facts
  → segment independently actionable units
  → compile canonical dossier
  → validate, fingerprint, deduplicate and version
  → human review when uncertain
  → compare with Norn Profile
  → Score, Gaps, Pack and Watch
```

See [`docs/normalization-v2.md`](docs/normalization-v2.md) for the schema, deterministic passes, migration strategy and truth boundaries.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
./scripts/run.sh
```

Open `http://localhost:8000`.

To compile live sources, set:

```env
ENABLE_LIVE_DISCOVERY=true
NORN_SOURCE_BUNDLE_URLS=https://issuer.example/announcement,https://issuer.example/rules,https://issuer.example/faq
```

Only HTTPS sources are accepted. Each response is snapshotted before extraction.

## Test

```bash
./scripts/test.sh
```

The suite covers:

- source snapshot and raw-content capture;
- track segmentation and structured requirement attribution;
- fingerprint-based deduplication and append-only versions;
- legacy string-requirement migration;
- Feed intelligence and review-queue APIs;
- Norn Score and hard-eligibility boundaries;
- verified versus claimed capability handling;
- Norn Pack claim exclusion;
- unpaid HTTP 402 challenge, local paid replay and duplicate rejection;
- invalid-input rejection before business execution;
- credential redaction and OKX integration contracts.

## Compiler storage

Opportunity truth is stored in `NORN_DATA_DIR/norn.sqlite3` with tables for sources, snapshots, programmes, opportunities, versions, requirements, source links, normalization runs, profile versions, assessments, review items and watch events. Existing profile, Pack, Watch, audit and replay JSON files remain behind a compatibility facade during migration.

Useful endpoints:

```text
POST /api/feed
GET  /api/feed/review
POST /api/feed/review/{review_id}
GET  /api/opportunities/{canonical_id}/history
POST /api/score
POST /api/gaps
POST /api/packs
POST /api/v1/opportunity-brief
```

## Production payment

The default `PAYMENT_MODE=free` makes local exploration easy. `PAYMENT_MODE=demo` enables a local-only 402 conformance harness and is forbidden in production.

For production:

1. Install the pinned dependencies from `requirements.txt`, including the official OKX seller SDK.
2. Set `PAYMENT_MODE=okx`.
3. Store `PAY_TO_ADDRESS`, `OKX_API_KEY`, `OKX_SECRET_KEY` and `OKX_PASSPHRASE` in the hosting secret manager.
4. Use X Layer `eip155:196`, official USDT0 and the real HTTPS origin.
5. Run the public conformance and independent consumer tests in `docs/deployment.md`.

A production deployment left in `PAYMENT_MODE=free` remains inspectable but reports degraded health and `ready: false`; it is not payment-ready.

## Safety boundary

Norn does not submit applications automatically. It does not invent experience, deployments, customers, revenue, partnerships, audits, source facts or on-chain proof. Inferred fields remain labelled as inferred, unknown eligibility remains unknown, and generated Packs remain drafts until explicit approval.
