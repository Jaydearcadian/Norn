from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re


X_LAYER_NETWORK = "eip155:196"
X_LAYER_USDT0 = "0x779ded0c9e1022225f8e0630b35a9b54be713736"
DEFAULT_PRICE_USD = "$0.01"
DEFAULT_ATOMIC_AMOUNT = "10000"
EVM_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Norn")
    environment: str = os.getenv("ENVIRONMENT", "development")
    data_dir: Path = Path(os.getenv("NORN_DATA_DIR", "./runtime-data"))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    maximum_input_bytes: int = int(os.getenv("MAXIMUM_INPUT_BYTES", "262144"))
    payment_mode: str = os.getenv("PAYMENT_MODE", "free").lower()
    payment_network: str = os.getenv("PAYMENT_NETWORK", X_LAYER_NETWORK)
    payment_price: str = os.getenv("PAYMENT_PRICE", DEFAULT_PRICE_USD)
    payment_asset: str = os.getenv("PAYMENT_ASSET", X_LAYER_USDT0)
    payment_atomic_amount: str = os.getenv("PAYMENT_ATOMIC_AMOUNT", DEFAULT_ATOMIC_AMOUNT)
    pay_to_address: str = os.getenv("PAY_TO_ADDRESS", "")
    payment_max_timeout_seconds: int = int(os.getenv("PAYMENT_MAX_TIMEOUT_SECONDS", "300"))
    okx_api_key: str = os.getenv("OKX_API_KEY", "")
    okx_secret_key: str = os.getenv("OKX_SECRET_KEY", "")
    okx_passphrase: str = os.getenv("OKX_PASSPHRASE", "")
    okx_base_url: str = os.getenv("OKX_BASE_URL", "https://web3.okx.com")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_queries: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv("NORN_GITHUB_QUERIES", "").split(";;") if item.strip()
    )
    source_feed_urls: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv("NORN_SOURCE_FEED_URLS", "").split(",") if item.strip()
    )
    enable_live_discovery: bool = _bool("ENABLE_LIVE_DISCOVERY", False)
    demo_payment_secret: str = os.getenv("DEMO_PAYMENT_SECRET", "local-test-only")

    def configuration_errors(self) -> list[str]:
        errors: list[str] = []
        if self.environment == "production" and not self.public_base_url.startswith("https://"):
            errors.append("PUBLIC_BASE_URL must use HTTPS in production")
        if self.payment_mode == "okx":
            required = {
                "PAY_TO_ADDRESS": self.pay_to_address,
                "OKX_API_KEY": self.okx_api_key,
                "OKX_SECRET_KEY": self.okx_secret_key,
                "OKX_PASSPHRASE": self.okx_passphrase,
                "PAYMENT_ASSET": self.payment_asset,
                "PAYMENT_ATOMIC_AMOUNT": self.payment_atomic_amount,
            }
            errors.extend(f"{name} is required for PAYMENT_MODE=okx" for name, value in required.items() if not value)
            if self.pay_to_address and not EVM_ADDRESS_PATTERN.fullmatch(self.pay_to_address):
                errors.append("PAY_TO_ADDRESS must be a 20-byte 0x-prefixed EVM address")
            if self.payment_network != X_LAYER_NETWORK:
                errors.append(f"PAYMENT_NETWORK must be {X_LAYER_NETWORK} for the OKX.AI X Layer listing")
            if self.payment_asset.lower() != X_LAYER_USDT0:
                errors.append("PAYMENT_ASSET must be the official X Layer USDT0 contract")
            if self.payment_atomic_amount != DEFAULT_ATOMIC_AMOUNT or self.payment_price != DEFAULT_PRICE_USD:
                errors.append("PAYMENT_PRICE=$0.01 must correspond to PAYMENT_ATOMIC_AMOUNT=10000 for 6-decimal USDT0")
        if self.payment_mode == "demo" and self.environment == "production":
            errors.append("PAYMENT_MODE=demo is forbidden in production")
        if self.payment_mode not in {"free", "demo", "okx"}:
            errors.append("PAYMENT_MODE must be free, demo, or okx")
        return errors

    def readiness_blockers(self) -> list[str]:
        blockers = self.configuration_errors()
        if self.environment == "production" and self.payment_mode != "okx":
            blockers.append("PAYMENT_MODE=okx is required for paid production readiness")
        return blockers

    def validate_production(self) -> list[str]:
        """Backward-compatible readiness check used by health and lifecycle tooling."""
        return self.readiness_blockers()


settings = Settings()
