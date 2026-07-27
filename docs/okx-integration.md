# OKX.AI integration map

This document maps Norn to the current official OKX.AI A2MCP, Agent Payments Protocol, A2A, and seller SDK guides.

## A2MCP: Norn Opportunity Brief

Norn Opportunity Brief is the deterministic service:

- public HTTPS endpoint: `POST /api/v1/opportunity-brief`;
- structured request and response schemas;
- bounded to one ranking and readiness brief;
- fixed price: `$0.01`;
- payment network: X Layer `eip155:196`;
- settlement asset: official X Layer USDT0 `0x779ded0c9e1022225f8e0630b35a9b54be713736`;
- atomic amount: `10000` for a six-decimal token;
- recipient: supplied through `PAY_TO_ADDRESS` and never committed;
- payment middleware: `okxweb3-app-x402` with the official facilitator client and exact EVM scheme.

In `PAYMENT_MODE=okx`, the middleware must return HTTP 402 and `PAYMENT-REQUIRED` for an unpaid request, verify the replayed payment, and allow the business handler to execute once. `PAYMENT_MODE=free` is only for exploration and deployment checks. `PAYMENT_MODE=demo` is a local conformance harness and is forbidden in production.

## Agent Payments Protocol

Norn uses the protocol in two different deployment shapes:

- A2MCP uses a priced HTTP service and an HTTP 402 challenge.
- A2A uses negotiated commercial terms carried through the agent conversation and whichever supported payment method is selected for the engagement.

Norn does not implement its own broker or claim persistent commercial payment state. Facilitator or broker responsibilities remain with the selected OKX payment infrastructure.

Escrow must not be advertised as live unless the official payment surface used for the engagement supports it. The A2A contract therefore records cancellation and dispute procedures without promising unavailable escrow behaviour.

## A2A: Norn Opportunity Strategy

Norn Opportunity Strategy handles custom, multi-round work:

- opportunity portfolio and campaign strategy;
- funding and partnership pipeline design;
- evidence remediation planning;
- multi-opportunity application packages;
- negotiated scope, milestones, project price, delivery format, revision allowance, cancellation, and dispute terms.

The runnable skill is `skills/norn-opportunity-strategy/SKILL.md`. The registration draft is `evidence/norn-opportunity-strategy/service-spec.draft.json`.

A2A is deliberately separate from the A2MCP endpoint. It has no advertised HTTP payment endpoint and must not be invoked for a deterministic single-call brief.

## Production variables

```text
ENVIRONMENT=production
PUBLIC_BASE_URL=https://<public-host>
NORN_DATA_DIR=/data
PAYMENT_MODE=okx
PAYMENT_NETWORK=eip155:196
PAYMENT_PRICE=$0.01
PAYMENT_ASSET=0x779ded0c9e1022225f8e0630b35a9b54be713736
PAYMENT_ATOMIC_AMOUNT=10000
PAY_TO_ADDRESS=<real X Layer recipient>
OKX_API_KEY=<secret>
OKX_SECRET_KEY=<secret>
OKX_PASSPHRASE=<secret>
OKX_BASE_URL=https://web3.okx.com
```

## Registration truth gates

Before registering A2MCP:

1. switch the public deployment to `PAYMENT_MODE=okx`;
2. verify an unpaid request returns HTTP 402 with `PAYMENT-REQUIRED`;
3. verify a separately controlled OKX User agent pays and receives HTTP 200;
4. record settlement proof and replay behaviour without saving payment signatures;
5. replace the temporary hostname when a durable production domain is available.

Before registering A2A:

1. simulate representative scopes, budgets, urgency, low offers, scope expansion, revisions, and refusal cases;
2. manually review delivery quality;
3. verify all tools and data sources declared by the skill are callable;
4. set the real provider identity, listing details, and negotiated price policy in OKX.AI;
5. never claim escrow support until it is active for the chosen payment method.
