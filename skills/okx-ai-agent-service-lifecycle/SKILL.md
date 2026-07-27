---
name: okx-ai-agent-service-lifecycle
description: Build, deploy, register, activate, self-test, monitor, update, and decommission a functioning OKX AI ASP service offered as A2MCP (public HTTPS API/pay-per-call) or A2A (agent-to-agent negotiated work). Use for end-to-end OKX AI provider delivery, service listing readiness, lifecycle evidence, or proving an agent is genuinely callable—not merely registered.
version: 1.0.0
---

# OKX AI Agent Service Lifecycle

## Purpose

Use this as the umbrella workflow for delivering a real OKX AI Agent Service Provider (ASP) from product definition through public proof and ongoing operations.

This skill coordinates, but does not duplicate, the authoritative skills:

- Load `okx-ai` before every identity, service listing, activation/deactivation, task-marketplace, or OKX A2A communication action. Its preflight, consent, collection, QA, confirmation, and one-call gates are mandatory.
- Load `okx-agent-payments-protocol` before probing, quoting, paying, replaying, or decoding any HTTP 402/A2MCP payment. Its payment confirmation gate is mandatory.
- Load `wrangler` before Cloudflare commands; retrieve current Cloudflare docs rather than guessing flags.
- Load the implementation skill matching the chosen stack. Do not force OpenRails into an otherwise independent service.

Installed `onchainos`/`okx-a2a` skills and current upstream docs outrank examples here when they differ.

## Non-negotiable truth boundary

A service is not “live” because code exists, tests pass, an ASP identity exists, or activation succeeded. Claim completion only after a separately registered OKX User agent can discover and successfully exercise the service through its advertised protocol.

Never:

- fabricate an agent ID, service ID, endpoint, listing, task, payment, transaction, receipt, review, or rating;
- expose private keys, wallet/session credentials, API tokens, bearer tokens, payment signatures, or Cloudflare secrets in chat, logs, source, evidence, or responses;
- let the provider runtime silently sign or broadcast for a user unless that custody model is explicitly designed, disclosed, and approved;
- treat discovery, quote, negotiation, or registration as payment authorization;
- auto-pay an A2MCP challenge or auto-submit an A2A task without the applicable user approval;
- use localhost, private IPs, placeholders, redirects, or undeployed endpoints in an A2MCP listing;
- claim native OpenRails settlement for OKX/x402 compatibility evidence.

## Lifecycle state machine

```text
CONCEPT
→ CONTRACT_FROZEN
→ IMPLEMENTED
→ LOCAL_VERIFIED
→ PUBLIC_DEPLOYED
→ PUBLIC_VERIFIED
→ ASP_REGISTERED
→ ACTIVE
→ INDEPENDENT_SELF_TEST_PASSED
→ MONITORED
→ UPDATED | DEACTIVATED | DECOMMISSIONED
```

Create a durable lifecycle record at the beginning. Advance a phase only with evidence. Use `scripts/lifecycle_record.py init|validate|advance` and the contract in `references/records-and-evidence.md`.

## Phase 0 — Define the service

Capture before coding:

- customer and concrete outcome;
- inputs, outputs, errors, limits, timeout, and completion semantics;
- data sources and provenance;
- pricing and refund/failure policy;
- provider identity and settlement recipient boundary;
- deployment target and operational owner;
- fulfillment mode: machine, human, physical, or hybrid;
- excluded and regulated actions;
- chosen service type: `A2MCP` or `A2A`.

Reject vague “does anything” listings. One service should express one coherent purchasable outcome. Multiple distinct outcomes can be multiple services on one ASP.

## Phase 1 — Choose A2MCP or A2A

### A2MCP — API service

Choose when one public HTTPS request can produce a bounded result.

OKX listing contract:

- `serviceType: "A2MCP"`
- fixed `fee` required as a quoted numeric string; USDT is implicit in the identity flow;
- public `https://` endpoint required;
- endpoint must be stable, reachable, and no longer than the official limit;
- request inputs must be declared and machine-validatable.

Implementation may be MCP JSON-RPC or documented HTTP JSON. For MCP, keep `initialize` and `tools/list` free, expose explicit JSON schemas, and charge only the actual business tool call. For HTTP JSON, declare exact method and input placement. See `references/protocol-contracts.md`.

### A2A — agent-to-agent service

Choose when the job needs negotiation, asynchronous work, human judgment, attachments, milestones, or variable terms.

OKX listing contract:

- `serviceType: "A2A"`
- omit `endpoint` from the service record;
- fee is optional; omitted fee means negotiated pricing, while explicit `"0"` means free;
- communication and task execution use the OKX A2A/task runtime, not a fake API URL.

Run the official communication readiness flow and require `okx-a2a doctor --fix --json` to report `ready:true` before task testing.

## Phase 2 — Freeze the protocol contract

Copy `templates/service-spec.json` into the project/evidence directory and fill it from user-approved facts. Before implementation, run:

```bash
python3 <skill-dir>/scripts/lifecycle_record.py validate-spec evidence/<service-slug>/service-spec.json
```

Do not advance `contract` until it passes.

For both types define:

- stable service name and two-part listing description;
- input and output schema;
- error taxonomy;
- idempotency/replay behavior;
- timeout and retry policy;
- provenance and receipt fields;
- sensitive-data handling;
- authoritative completion condition.

Additional A2MCP contract:

- public endpoint and method;
- free discovery/handshake behavior;
- unpaid challenge behavior;
- chain/network, token, amount, recipient, expiry, and payment scheme;
- exact paid replay behavior;
- response/receipt binding.

Additional A2A contract:

- accepted task categories and required brief fields;
- quote/negotiation rules;
- acceptance criteria and artifacts;
- progress/status events;
- delivery, revision, rejection, dispute, and cancellation behavior.

Do not start implementation while price, recipient, authority, required inputs, or completion conditions remain ambiguous.

## Phase 3 — Implement

Use the project’s real package manager and architecture. Read its `AGENTS.md`, `package.json`, CI, tests, and deployment config before edits.

Required common surfaces:

- health/readiness;
- structured validation;
- bounded execution timeout;
- explicit error responses;
- idempotency or replay protection for mutations;
- request, result, and provenance digests;
- logs with credential redaction;
- no sensitive authorization material echoed in output.

A2MCP must fail closed before business execution when payment is absent or invalid. A2A must preserve task/job identity and counterpart role across every event.

## Phase 4 — Verify locally

Follow RED → GREEN → REFACTOR for changed behavior. Minimum tests:

### Common

- valid and invalid input;
- timeout/upstream failure;
- replay/idempotency;
- credential redaction;
- output schema;
- truthful failure and partial-result behavior.

### A2MCP

- free `initialize` and `tools/list` when MCP is used;
- unpaid business call returns a valid challenge and performs no business work;
- malformed/wrong-chain/wrong-token/wrong-amount/wrong-recipient proof rejected;
- approved paid replay runs exactly once;
- response includes canonical payment/receipt evidence;
- credential never persists or appears in output.

### A2A

- communication readiness;
- task received with correct counterpart identity;
- quote/negotiation path;
- accept/reject path;
- progress and delivery artifact;
- revision/dispute/cancellation behavior;
- duplicate event safety.

Record exact commands and outputs. “Tests passed” without command, count, and artifact is insufficient.

## Phase 5 — Deploy safely

- Use a stable public HTTPS origin.
- Keep credentials outside source control and project `.env` when production policy requires external secret injection.
- Run the repository’s guarded dry-run/preflight.
- Capture platform deployment/version ID, timestamp, config digest, and rollback target.
- Verify the deployed version before behavioral testing; account for propagation lag.
- Never replace a protected deployment, route, database, queue, bucket, or signer boundary without explicit approval.

## Phase 6 — Public conformance

Probe the original public source, not a local substitute.

### A2MCP gate

1. Health returns success.
2. MCP `initialize` and `tools/list` work freely, or HTTP service metadata is publicly inspectable.
3. Unpaid business invocation returns the expected payment challenge.
4. Challenge advertises the intended network (for X Layer, `eip155:196`), asset, exact amount, and intended recipient.
5. Required business inputs are explicit.
6. Endpoint does not redirect to an unrelated page.
7. After explicit payment approval, paid replay returns the promised result and a decodable receipt.
8. Settlement and result provenance are read back independently.

### A2A gate

1. `okx-a2a` runtime reports ready.
2. ASP can receive a real marketplace task/chat event.
3. Counterparty identity and job ID remain stable.
4. ASP can quote/negotiate and accept or reject.
5. ASP emits progress where applicable.
6. ASP delivers the promised artifact.
7. User can accept, request revision, cancel, or dispute according to the contract.

Store sanitized request/response metadata, hashes, and IDs—not secrets.

## Phase 7 — Register the OKX ASP

Load `okx-ai` and follow its official ASP registration flow end to end. Do not bypass its mandatory steps.

Required sequence:

1. Official wallet/onchainos preflight.
2. Resolve role `asp` and run the official role pre-check.
3. Handle first-wallet consent and uniqueness exactly as instructed.
4. Collect ASP identity name, description, and required uploaded avatar.
5. Collect every service, asking “add another / done” after each one.
6. For each service use exact camelCase listing keys:
   - `serviceName`
   - `serviceDescription`
   - `serviceType`
   - `fee` when required
   - `endpoint` only for A2MCP
7. Run the official batch listing QA exactly once after the user says Done.
8. Show the identity and service confirmation cards.
9. Wait for the official explicit confirmation token.
10. Execute one create call and record the returned agent/service identifiers.
11. Run official A2A communication initialization after registration.

Registration is a record state, not public-live proof.

## Phase 8 — Activate and verify discovery

Load `okx-ai` and activate the exact ASP identity using its current procedure and language requirements.

After activation:

- search the marketplace as a consumer would;
- inspect the returned identity and service fields;
- verify name, description, type, fee, endpoint policy, and status;
- verify no test markers, placeholder URLs, or stale versions;
- record marketplace identifiers and retrieval evidence.

Do not infer activation from registration output. Do not infer discovery from activation output.

## Phase 9 — Independent self-test

This is the publication gate. Use a separately registered OKX User identity, not the ASP’s own provider context.

### A2MCP self-test

1. Discover the service through OKX AI.
2. Inspect its advertised endpoint and inputs.
3. Quote/probe through `okx-agent-payments-protocol`.
4. Present exact network, token, amount, recipient, and inputs.
5. Obtain explicit buyer approval.
6. Pay/replay through the official payment flow.
7. Validate result quality, schema, provider support, consistency, usefulness, and value for money—not settlement alone.
8. Record transaction/receipt, response digest, provider/service IDs, and redacted provenance.

### A2A self-test

1. Discover the ASP from the User identity.
2. Publish or direct a real task using the official task-marketplace flow.
3. Confirm ASP receives the task/chat event.
4. Exercise negotiation and acceptance.
5. Deliver a real artifact.
6. Have the User accept or exercise revision/dispute behavior.
7. Record job ID, counterpart IDs, terms, status chronology, artifact digest, and terminal outcome.

Only after this phase may the record use `operational` or `publicly_proven`.

## Phase 10 — Record and publish evidence

Use `references/records-and-evidence.md`. Minimum evidence bundle:

```text
evidence/<service-slug>/
├── lifecycle-record.json
├── service-spec.json
├── tests/
├── deployment/
├── public-probes/
├── marketplace/
├── self-test/
├── receipts/
└── manifest.json
```

Run:

```bash
python3 <skill-dir>/scripts/lifecycle_record.py validate evidence/<service-slug>/lifecycle-record.json
```

Generate hashes with a real tool. Do not hand-type digests. Redact credentials before hashing/publishing the bundle.

## Phase 11 — Operate

Monitor at least:

- public health and latency;
- endpoint/schema drift;
- challenge network/token/price/recipient drift;
- payment and task failure rate;
- A2A communication readiness;
- unhandled tasks and deadlines;
- result quality and user feedback;
- deployment version and upstream dependencies.

Alert on changes; do not silently auto-pay, auto-change price/recipient, or auto-reactivate.

## Phase 12 — Update, rollback, deactivate, decommission

For a listing update, load `okx-ai` and follow its ownership check, single QA pass, diff card, and explicit confirmation. Re-run public conformance and independent self-test after material changes.

For an incident:

1. stop accepting new work when fulfillment or payment integrity is uncertain;
2. preserve logs/evidence without secrets;
3. deactivate the listing if the public contract is no longer true;
4. roll back the deployment when safe;
5. verify recovery through the original public source;
6. reactivate only after approval and a fresh self-test.

For decommissioning, deactivate first, preserve immutable receipt/task records, remove secrets from the runtime, and document the terminal reason and replacement service if any.

## Definition of done

### A2MCP

- implementation and tests pass;
- stable public HTTPS endpoint;
- free discovery/handshake works;
- valid paid challenge and exact replay verified;
- ASP registered and active;
- consumer discovery works;
- independent registered User agent completed one approved paid call;
- result quality and receipt verified;
- evidence bundle validates;
- monitoring and rollback documented.

### A2A

- implementation and tests pass;
- communication runtime ready;
- ASP registered and active;
- consumer discovery works;
- independent registered User agent completed one real negotiated task lifecycle;
- artifact and terminal outcome verified;
- evidence bundle validates;
- monitoring and recovery documented.

## Pitfalls

- Registration ≠ activation ≠ discoverability ≠ callable proof.
- A2MCP endpoint registration before deployment creates permanent bad metadata and requires an update.
- A2A listings must not invent an API endpoint.
- Fixed fee strings are not token base units in the OKX identity listing; follow the official identity renderer. Payment challenges use their own exact atomic-unit contract.
- A 200 response can still contain an error envelope; validate semantic success.
- A valid transaction does not prove useful fulfillment.
- An external web search result is not OKX marketplace evidence.
- Never test a seller only from its own identity; use a distinct registered consumer.
- Save every version, ID, receipt, and digest, but never reusable authorization material.

## Linked files

- `references/protocol-contracts.md`
- `references/records-and-evidence.md`
- `templates/service-spec.json`
- `templates/lifecycle-record.json`
- `scripts/lifecycle_record.py`
