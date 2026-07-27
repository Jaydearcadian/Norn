from __future__ import annotations

import json
from pathlib import Path

from app.config import (
    DEFAULT_ATOMIC_AMOUNT,
    DEFAULT_PRICE_USD,
    Settings,
    X_LAYER_NETWORK,
    X_LAYER_USDT0,
)


def test_official_x_layer_payment_defaults():
    settings = Settings()
    assert settings.payment_network == X_LAYER_NETWORK == "eip155:196"
    assert settings.payment_price == DEFAULT_PRICE_USD == "$0.01"
    assert settings.payment_asset == X_LAYER_USDT0 == "0x779ded0c9e1022225f8e0630b35a9b54be713736"
    assert settings.payment_atomic_amount == DEFAULT_ATOMIC_AMOUNT == "10000"


def test_okx_mode_rejects_wrong_asset_or_amount(tmp_path: Path):
    settings = Settings(
        environment="production",
        data_dir=tmp_path,
        public_base_url="https://norn.example",
        payment_mode="okx",
        payment_network=X_LAYER_NETWORK,
        payment_price="$0.02",
        payment_asset="0x0000000000000000000000000000000000000000",
        payment_atomic_amount="20000",
        pay_to_address="0x1111111111111111111111111111111111111111",
        okx_api_key="key",
        okx_secret_key="secret",
        okx_passphrase="passphrase",
    )
    blockers = settings.validate_production()
    assert any("official X Layer USDT0" in blocker for blocker in blockers)
    assert any("PAYMENT_PRICE=$0.01" in blocker for blocker in blockers)


def test_a2mcp_and_a2a_specs_remain_separate():
    root = Path(__file__).resolve().parents[1]
    a2mcp = json.loads((root / "evidence/norn-opportunity-brief/service-spec.draft.json").read_text())
    a2a = json.loads((root / "evidence/norn-opportunity-strategy/service-spec.draft.json").read_text())

    assert a2mcp["serviceType"] == "A2MCP"
    assert a2mcp["a2mcp"]["endpoint"].startswith("https://")
    assert a2mcp["pricing"]["paymentAsset"] == X_LAYER_USDT0
    assert a2mcp["pricing"]["atomicAmount"] == DEFAULT_ATOMIC_AMOUNT

    assert a2a["serviceType"] == "A2A"
    assert a2a["a2mcp"]["endpoint"] == ""
    assert a2a["a2a"]["negotiatedPricing"] is True
    assert a2a["a2a"]["taskCategories"]
    assert "Representing unavailable escrow functionality as active" in a2a["safety"]["excludedActions"]
