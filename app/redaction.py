from __future__ import annotations

import re
from typing import Any

SENSITIVE = {
    "authorization", "bearer", "token", "secret", "password", "privatekey",
    "private_key", "mnemonic", "seedphrase", "payment-signature", "x-payment",
    "okx_api_key", "okx_secret_key", "okx_passphrase",
}


def _normalise(key: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", key.lower())


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _normalise(str(key)) in SENSITIVE else redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)bearer\s+[a-z0-9._~+\-/]+=*", "Bearer [REDACTED]", value)
        value = re.sub(r"0x[a-fA-F0-9]{64}", "0x[REDACTED]", value)
    return value
