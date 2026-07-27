# Norn 9.5 vision contract

Norn reaches the envisioned product when it can truthfully perform this loop:

```text
fragmented source bundle
  -> immutable source snapshots
  -> attributed, versioned opportunity dossier
  -> deterministic validation and human review
  -> versioned capability and evidence comparison
  -> confidence-aware decision
  -> approval-controlled execution workflow
  -> receipt and outcome capture
  -> measured learning
```

## Implemented product surfaces

### Opportunity truth

- HTML, JSON, RSS/Atom and GitHub issue adapters.
- Immutable source snapshots before extraction.
- Programme, cycle, track and parent relationships.
- Structured eligibility, requirements and deliverables.
- Explicit, derived, inferred, unknown and conflicting attribution.
- Canonical fingerprints, deduplication, versions and changed fields.
- Human review queue.

### Decision intelligence

`POST /api/decision` returns:

- the reproducible FitAssessment;
- dossier confidence;
- evidence confidence;
- overall decision confidence;
- bounded completion probability;
- a requirement-to-capability-to-evidence graph;
- uncertainty reasons;
- the next best action.

Unknown eligibility and missing evidence reduce confidence. They are never hidden by the numeric score.

### Execution loop

The workflow state machine is:

```text
discovered -> normalized -> reviewed -> qualified
-> gap_closing -> ready -> approved -> submitted
-> awaiting_decision -> won | lost -> archived
```

Invalid jumps are rejected. Submission cannot occur before approval. Receipts and realised outcome values can be recorded without allowing automatic application submission.

### Truthful launch gate

`GET /api/launch-readiness` and `scripts/vision_gate.py` score only evidenced readiness:

- a 30-dossier compiler corpus;
- structured dossier coverage;
- human-review coverage;
- verified dossier coverage;
- official-source coverage;
- verified profile evidence;
- production payment readiness.

The gate passes only at 9.5 or higher with no incomplete category. It never rounds missing external proof upward.

## Required final evidence before submission

The repository can implement the product and test contracts. These final facts must be created by a real deployment and marketplace interaction:

1. Run the complete test suite and compiler migration checks.
2. Compile and review at least 30 real technical opportunities.
3. Attach at least five verified profile evidence records.
4. Deploy with the real HTTPS origin and persistent SQLite volume.
5. Configure the real X Layer recipient and OKX facilitator credentials.
6. Verify an unpaid HTTP 402 challenge.
7. Complete one independently paid and settled call.
8. Register and activate the ASP and retain the agent/service identifiers.
9. Verify discovery from a separately registered consumer agent.
10. Capture the demo video, X post and submission receipt.

## Commands

```bash
python3 -m compileall -q app
node --check app/static/app.js
./scripts/test.sh
python3 scripts/vision_gate.py --data-dir runtime-data
```

The final command exits with status 2 until the real 9.5 evidence exists. After paid production verification, run it with `--payment-ready`.
