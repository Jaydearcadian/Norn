# API contract

## Health

- `GET /health`
- `GET /ready`

## Norn Profile

- `GET /api/profile`
- `PUT /api/profile`

## Norn Feed

- `POST /api/feed`
- `POST /api/feed/import`

Configured live feeds must use HTTPS and return either an array of normalised opportunities or `{ "opportunities": [...] }`.

## Norn Score

`POST /api/score`

```json
{
  "profile": { "...": "CapabilityProfile" },
  "opportunity": { "...": "Opportunity" }
}
```

## Norn Gaps

`POST /api/gaps`

## Norn Pack

- `POST /api/packs`
- `GET /api/packs`
- `GET /api/packs/{pack_id}`

## Norn Watch

- `GET /api/watch`
- `POST /api/watch`

## OKX.AI A2MCP service

`POST /api/v1/opportunity-brief`

Input:

```json
{
  "profile": { "...": "CapabilityProfile" },
  "opportunities": [{ "...": "Opportunity" }],
  "includePackForTopOpportunity": true,
  "maximumResults": 5
}
```

Output:

```json
{
  "ranked": [
    {
      "opportunity": {},
      "assessment": {
        "score": 87,
        "eligibility": "likely",
        "recommendation": "close_gaps_first",
        "criteria": [],
        "gaps": []
      }
    }
  ],
  "topPack": {},
  "summary": "Evaluated 3 opportunity candidates...",
  "provenance": {
    "requestDigest": "sha256",
    "resultDigest": "sha256",
    "sourceUrls": [],
    "sourceTimestamps": [],
    "engineVersion": "norn-score-v1"
  }
}
```

In production paid mode, an unpaid request must return HTTP 402 with the `PAYMENT-REQUIRED` header. A valid paid replay reaches the handler once and returns a `PAYMENT-RESPONSE` settlement proof through the official middleware.
