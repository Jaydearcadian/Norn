# Lifecycle records and evidence

## Purpose

The lifecycle record is the canonical machine-readable state for one OKX AI service. Chat, memory, a registration result, and an ASP dashboard are supporting sources—not substitutes.

## Required phase keys

```text
contract
implementation
localVerification
deployment
publicVerification
identityRegistration
activation
discovery
independentSelfTest
monitoring
```

Each phase contains:

```json
{
  "status": "pending|in_progress|passed|failed|blocked|not_applicable",
  "recordedAt": null,
  "evidence": [],
  "notes": ""
}
```

## Evidence entry

```json
{
  "kind": "test-report|deployment|public-probe|marketplace|task|payment|receipt|artifact|monitoring|rollback",
  "path": "relative/path/to/sanitized-artifact.json",
  "sha256": "64 lowercase hex characters",
  "recordedAt": "RFC3339 timestamp",
  "source": "original command, URL, platform, transaction, or job",
  "redacted": true
}
```

Compute hashes from files with a real checksum tool. If an artifact changes, add a new entry; never rewrite historical evidence to preserve an old digest.

## Record statuses

- `planned`: contract work has started.
- `implemented`: implementation exists but public proof is absent.
- `local_verified`: local tests passed.
- `public_deployed`: stable deployment exists but marketplace proof is absent.
- `registered`: ASP identity/service registered but not proven active/discoverable.
- `active`: identity activation was observed but independent service use is absent.
- `publicly_proven`: independent registered User-agent self-test passed.
- `operational`: publicly proven and monitoring/rollback are configured.
- `deactivated`: listing intentionally unavailable.
- `decommissioned`: terminal service state with preserved records.
- `blocked`: an explicit prerequisite prevents progress.

Never advance directly from `registered` or `active` to `operational` without independent self-test evidence.

## Canonical bundle

```text
evidence/<service-slug>/
├── lifecycle-record.json
├── service-spec.json
├── tests/
│   ├── focused.txt
│   ├── full.txt
│   └── security.txt
├── deployment/
│   ├── dry-run.txt
│   ├── deployment.json
│   └── rollback.json
├── public-probes/
│   ├── health.json
│   ├── discovery.json
│   ├── unpaid.json
│   └── paid-redacted.json
├── marketplace/
│   ├── registration-redacted.json
│   ├── activation.json
│   └── discovery.json
├── self-test/
│   ├── buyer-or-user.json
│   ├── chronology.json
│   └── result.json
├── receipts/
│   └── receipt-redacted.json
└── manifest.json
```

A2A replaces unpaid/paid probes with task negotiation, progress, delivery, terminal status, and artifact evidence.

## Secret exclusion

Evidence must never contain reusable authorization. Reject or redact fields including:

- private keys, seed phrases, keystores;
- API tokens and Cloudflare credentials;
- `Authorization`/bearer values;
- `PAYMENT-SIGNATURE`, `X-PAYMENT`, permits, session certificates, or execution credentials;
- wallet-login session material;
- webhook secrets;
- raw cookies.

Wallet addresses, agent IDs, service IDs, job IDs, transaction hashes, block numbers, public challenge terms, and content hashes are evidence and may be retained when appropriate.

## Verification report

Every completion report states:

- service slug/type and current lifecycle status;
- provider agent ID and service ID from actual output;
- deployment/version ID;
- public endpoint for A2MCP or A2A readiness state;
- test commands and counts;
- marketplace activation/discovery evidence;
- independent User-agent self-test ID;
- payment transaction/receipt or A2A job/artifact/terminal status;
- result-quality review;
- known limitations and rollback/deactivation procedure.

## Result quality gate

Settlement or task completion alone is insufficient. Review:

- Did the output answer the advertised service request?
- Is every material claim supported by the service's actual sources/output?
- Does it follow the published schema and acceptance criteria?
- Is it useful enough for the listed or negotiated price?
- Did the provider avoid credential leakage and unsupported claims?
- Are errors/partial results disclosed?

## Update rule

Any material change to capability, inputs, output, endpoint, price, recipient, network, fulfillment, or authority requires:

1. new service-spec version/digest;
2. current official listing update flow and confirmation;
3. deployment/public conformance where applicable;
4. fresh marketplace discovery;
5. fresh independent self-test;
6. additive evidence and status update.
