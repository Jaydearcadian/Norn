#!/usr/bin/env bash
set -euo pipefail
SKILL=skills/okx-ai-agent-service-lifecycle/scripts/lifecycle_record.py
python3 "$SKILL" validate evidence/norn-opportunity-brief/lifecycle-record.json
python3 "$SKILL" validate-spec evidence/norn-opportunity-brief/service-spec.draft.json
