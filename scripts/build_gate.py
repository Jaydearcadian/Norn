#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.readiness import build_readiness
from app.store import JsonStore
from app.vision import VisionEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Norn pre-deploy build readiness")
    parser.add_argument("--data-dir", default="/tmp/norn-build-gate")
    parser.add_argument("--output", default="evidence/norn-build-readiness.json")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    store = JsonStore(Settings(environment="test", data_dir=data_dir, public_base_url="http://testserver", payment_mode="free"))
    report = build_readiness(store, VisionEngine(store.db_path))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["buildReady"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
