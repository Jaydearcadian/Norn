#!/usr/bin/env python3
from __future__ import annotations
import hashlib, hmac, json, os, sys
import httpx

base = os.getenv("NORN_URL", "http://localhost:8000")
secret = os.getenv("DEMO_PAYMENT_SECRET", "local-test-only").encode()
payload = json.loads(open(sys.argv[1]).read()) if len(sys.argv) > 1 else {
    "profile": httpx.get(f"{base}/api/profile").json(),
    "opportunities": httpx.post(f"{base}/api/feed", json={}).json()["items"],
    "includePackForTopOpportunity": True,
    "maximumResults": 5,
}
body = json.dumps(payload, separators=(",", ":")).encode()
first = httpx.post(f"{base}/api/v1/opportunity-brief", content=body, headers={"content-type":"application/json"})
print("unpaid", first.status_code, first.headers.get("PAYMENT-REQUIRED", "")[:48])
signature = "demo:" + hmac.new(secret, body, hashlib.sha256).hexdigest()
paid = httpx.post(f"{base}/api/v1/opportunity-brief", content=body, headers={"content-type":"application/json", "PAYMENT-SIGNATURE": signature})
print("paid", paid.status_code)
print(json.dumps(paid.json(), indent=2)[:5000])
