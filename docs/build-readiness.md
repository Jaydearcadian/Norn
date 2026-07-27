# Norn 9.5 readiness contract

Norn uses two separate readiness scores so implementation quality cannot be confused with external marketplace events.

## Build readiness

Build readiness answers:

> Does the deployable repository express the complete demo vision coherently and testably?

The gate requires:

- source snapshot capture and field provenance;
- versioned canonical dossiers and fingerprint deduplication;
- structured eligibility, requirements and deliverables;
- human review for uncertain normalization;
- confidence-aware decision reports and evidence graphs;
- approval-controlled execution workflows;
- bounded paid Opportunity Brief service;
- a deterministic 30-dossier, ten-class compiler contract benchmark;
- explicit truth boundaries for every external event.

Run:

```bash
python3 scripts/build_gate.py \
  --data-dir /tmp/norn-build-gate \
  --output evidence/norn-build-readiness.json
```

The command exits `0` only when `buildScore >= 9.5` and every build check passes.

The bundled 30-dossier corpus is deliberately labelled `fixture`. It tests deterministic compiler contracts and never claims to be a live issuer-verified dataset.

## Operational readiness

Operational readiness begins only after deployment. It requires independently captured evidence for:

1. the real X Layer recipient wallet;
2. OKX facilitator credentials stored in the host secret manager;
3. a live unpaid HTTP 402 challenge;
4. paid settlement and duplicate-replay behaviour;
5. OKX ASP registration and agent ID;
6. marketplace activation;
7. independent consumer discovery and paid invocation;
8. a reviewed public-source opportunity corpus;
9. the demo video;
10. the final submission receipt.

No code path sets these events to true automatically.

## Final operator sequence

```text
merge compiler and vision branches
  → run full tests and build gate on VPS
  → deploy managed host
  → configure production payment secrets
  → verify health, ready and HTTP 402
  → register A2MCP and A2A services
  → record agent and service IDs
  → prove independent paid invocation
  → record 90-second demo
  → publish X post
  → submit and retain receipt
```

## Demo claim

After the build gate passes, the accurate claim is:

> Norn is demo-ready as a versioned, evidence-backed opportunity compiler with confidence-aware decisions, approval-controlled execution and OKX-compatible paid service contracts. Marketplace identity and settlement proof are completed after deployment and recorded separately.
