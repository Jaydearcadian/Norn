# Norn Normalization v2

Norn is an opportunity compiler. It captures raw source material, extracts attributed facts, compiles a canonical dossier, versions changes, and only then compares the dossier with a versioned capability profile.

```text
source bundle -> immutable snapshots -> attributed facts -> canonical dossier
              -> deterministic validation -> fingerprint/version -> assessment
```

## Storage

SQLite is the local source of truth and can migrate cleanly to PostgreSQL. The schema includes:

- `sources`
- `source_snapshots`
- `programmes`
- `opportunities`
- `opportunity_versions`
- `requirements`
- `opportunity_sources`
- `normalization_runs`
- `profile_versions`
- `assessments`
- `review_queue`
- `audit`
- `replays`

The previous profile, pack, watch, audit, and replay interfaces remain compatible.

## Canonical unit

The scoreable item is the smallest independently actionable unit:

- programme -> round;
- event -> track or prize;
- repository -> issue;
- accelerator -> cohort;
- procurement notice -> lot;
- organisation -> role.

Canonical fingerprints use issuer, programme, cycle, track, deadline, and application URL. A changed dossier creates an immutable new version with a human-readable change summary.

## Source adapters

Three deterministic adapters are included:

1. `OfficialHtmlAdapter` captures HTML and extracts conservative title, deadline, and requirement candidates.
2. `StructuredFeedAdapter` accepts JSON plus RSS/Atom and compiles each independently actionable item.
3. `GitHubIssueAdapter` resolves repository/issue identity, labels, scope, and official issue provenance.

AI extraction can be added behind these adapters, but only deterministic validation may promote a dossier to `normalized` or `verified`.

## Attribution

Every structured requirement has an attribution basis:

- `explicit`
- `derived`
- `inferred`
- `unknown`
- `conflicting`

Unknown or conflicting mandatory eligibility rules receive no partial eligibility credit. They enter the human review queue.

## API additions

```text
POST /api/sources/ingest
GET  /api/opportunities/{id}/history
GET  /api/review-queue
POST /api/review-queue/{id}/{version}
```

`POST /api/feed` now returns dossier intelligence including completeness, source quality, freshness, changes, current version, and review status.

## Deliberate milestone boundary

Normalization v2 establishes the storage, provenance, versioning, adapter, review, and feed contracts. It does not claim that generic HTML extraction is semantically complete. Real-source expansion to 30 opportunities should be performed as a separate evidence-backed corpus task, with each uncertain extraction reviewed before use.
