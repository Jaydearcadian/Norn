from __future__ import annotations

import base64
import hmac
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from fastapi import HTTPException, Request, Response

from .config import Settings
from .digests import canonical_json, sha256_digest
from .store import JsonStore


@dataclass
class PaymentResult:
    payer: str | None
    replay_key: str
    mode: str


class DemoPaymentGateway:
    """Local conformance harness. It is deliberately forbidden in production."""

    def __init__(self, settings: Settings, store: JsonStore):
        self.settings = settings
        self.store = store

    def challenge(self, url: str) -> dict[str, Any]:
        accepts = [{
            "scheme": "exact",
            "network": self.settings.payment_network,
            "asset": self.settings.payment_asset or "TEST_ASSET_NOT_FOR_PRODUCTION",
            "amount": self.settings.payment_atomic_amount or "10000",
            "payTo": self.settings.pay_to_address or "0x1111111111111111111111111111111111111111",
            "maxTimeoutSeconds": self.settings.payment_max_timeout_seconds,
            "extra": {"name": "TEST USD", "version": "1", "demo": True},
        }]
        return {
            "x402Version": 2,
            "resource": {
                "url": url,
                "description": "Norn Opportunity Brief — local demo payment harness",
                "mimeType": "application/json",
            },
            "accepts": accepts,
            "extensions": {"norn": {"environment": "demo", "productionValid": False}},
        }

    def required_header(self, challenge: dict[str, Any]) -> str:
        return base64.b64encode(canonical_json(challenge).encode()).decode()

    def expected_signature(self, body: bytes) -> str:
        digest = hmac.new(self.settings.demo_payment_secret.encode(), body, sha256).hexdigest()
        return f"demo:{digest}"

    async def require(self, request: Request, body: bytes) -> PaymentResult:
        signature = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")
        challenge = self.challenge(str(request.url))
        if not signature:
            raise PaymentRequired(challenge, self.required_header(challenge))
        if not hmac.compare_digest(signature, self.expected_signature(body)):
            raise HTTPException(status_code=402, detail={"error": "invalid_demo_payment", "challenge": challenge})
        replay_key = sha256_digest({"signature": signature, "body": body.decode("utf-8")})
        if self.store.has_replay(replay_key):
            raise HTTPException(status_code=409, detail={"error": "payment_replay", "message": "This paid invocation has already executed."})
        self.store.record_replay(replay_key)
        return PaymentResult(payer="demo-payer", replay_key=replay_key, mode="demo")


class PaymentRequired(Exception):
    def __init__(self, challenge: dict[str, Any], header: str):
        self.challenge = challenge
        self.header = header


def configure_okx_payment_middleware(app, settings: Settings) -> None:
    """Mount the official OKX middleware when dependencies and credentials exist.

    The import paths follow the current OKX Python SDK documentation. This function
    raises rather than silently falling back, preserving the fail-closed boundary.
    """
    if settings.payment_mode != "okx":
        return
    try:
        from x402.http import (
            OKXAuthConfig,
            OKXFacilitatorClient,
            OKXFacilitatorConfig,
            PaymentOption,
            RouteConfig,
        )
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.mechanisms.evm.exact.server import ExactEvmScheme
        from x402.server import x402ResourceServer
    except ImportError as exc:
        raise RuntimeError(
            "Install okxweb3-app-x402 with its EVM dependencies before PAYMENT_MODE=okx"
        ) from exc

    facilitator = OKXFacilitatorClient(
        OKXFacilitatorConfig(
            auth=OKXAuthConfig(
                api_key=settings.okx_api_key,
                secret_key=settings.okx_secret_key,
                passphrase=settings.okx_passphrase,
            ),
            base_url=settings.okx_base_url,
            sync_settle=True,
        )
    )
    server = x402ResourceServer(facilitator)
    server.register(settings.payment_network, ExactEvmScheme())
    endpoint = f"{settings.public_base_url.rstrip('/')}/api/v1/opportunity-brief"
    routes = {
        "POST /api/v1/opportunity-brief": RouteConfig(
            accepts=[PaymentOption(
                scheme="exact",
                price={
                    "amount": settings.payment_atomic_amount,
                    "asset": settings.payment_asset,
                    "extra": {"name": "USD₮0", "version": "1"},
                },
                network=settings.payment_network,
                pay_to=settings.pay_to_address,
                max_timeout_seconds=settings.payment_max_timeout_seconds,
            )],
            resource=endpoint,
            description="Norn evidence-backed opportunity ranking and readiness brief",
            mime_type="application/json",
        )
    }
    app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
