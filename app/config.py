from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


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
    payment_network: str = os.getenv("PAYMENT_NETWORK", "eip155:196")
    payment_price: str = os.getenv("PAYMENT_PRICE", "$0.01")
    payment_asset: str = os.getenv("PAYMENT_ASSET", "")
    payment_atomic_amount: str = os.getenv("PAYMENT_ATOMIC_AMOUNT", "")
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

    def validate_production(self) -> list[str]:
        errors: list[str] = []
        if self.environment == "production" and not self.public_base_url.startswith("https://"):
            errors.append("PUBLIC_BASE_URL must use HTTPS in production")
        if self.payment_mode == "okx":
            required = {
                "PAY_TO_ADDRESS": self.pay_to_address,
                "OKX_API_KEY": self.okx_api_key,
                "OKX_SECRET_KEY": self.okx_secret_key,
                "OKX_PASSPHRASE": self.okx_passphrase,
            }
            errors.extend(f"{name} is required for PAYMENT_MODE=okx" for name, value in required.items() if not value)
        if self.payment_mode == "demo" and self.environment == "production":
            errors.append("PAYMENT_MODE=demo is forbidden in production")
        if self.payment_mode not in {"free", "demo", "okx"}:
            errors.append("PAYMENT_MODE must be free, demo, or okx")
        return errors


settings = Settings()
