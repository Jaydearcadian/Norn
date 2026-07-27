#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.store import JsonStore
from app.vision import VisionEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Norn against the truthful 9.5 launch gate")
    parser.add_argument("--data-dir", default="runtime-data")
    parser.add_argument("--payment-ready", action="store_true")
    parser.add_argument("--output", default="evidence/vision-9-5-scorecard.json")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    store = JsonStore(Settings(environment="test", data_dir=data_dir, public_base_url="http://testserver", payment_mode="free"))
    engine = VisionEngine(store.db_path)
    result = engine.launch_scorecard(store.list_opportunities(), store.get_profile(), args.payment_ready)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
