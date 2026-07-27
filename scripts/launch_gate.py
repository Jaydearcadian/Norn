#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.config import Settings
from app.store import JsonStore
from app.vision import VisionStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Norn demo and production launch readiness.")
    parser.add_argument("--data-dir", default=os.getenv("NORN_DATA_DIR", "./runtime-data"))
    parser.add_argument("--public-base-url", default=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--environment", default=os.getenv("ENVIRONMENT", "development"))
    parser.add_argument("--payment-mode", default=os.getenv("PAYMENT_MODE", "free"))
    parser.add_argument("--require-target", action="store_true", help="Exit non-zero unless the truthful 9.5 target is reached.")
    args = parser.parse_args()

    settings = Settings(
        environment=args.environment,
        data_dir=Path(args.data_dir),
        public_base_url=args.public_base_url,
        payment_mode=args.payment_mode,
    )
    store = JsonStore(settings)
    vision = VisionStore(store.db_path)
    deployment_ready = settings.environment == "production" and settings.public_base_url.startswith("https://")
    payment_ready = deployment_ready and settings.payment_mode == "okx" and not settings.configuration_errors()
    result = vision.readiness(store.list_opportunities(), payment_ready, deployment_ready)
    print(json.dumps(result, indent=2))

    if args.require_target and not result["targetReached"]:
        print("Norn has not truthfully reached the 9.5 launch target.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
