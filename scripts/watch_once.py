#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import httpx

base = os.getenv("NORN_URL", "http://localhost:8000")
response = httpx.post(f"{base}/api/watch/digest", timeout=30)
response.raise_for_status()
print(json.dumps(response.json(), indent=2, default=str))
