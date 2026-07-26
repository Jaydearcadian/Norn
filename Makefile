.PHONY: run test check lifecycle
run:
	PYTHONPATH=. ./scripts/run.sh

test:
	PYTHONPATH=. pytest

check:
	python3 -m compileall -q app
	node --check app/static/app.js
	PYTHONPATH=. pytest

lifecycle:
	python3 skills/okx-ai-agent-service-lifecycle/scripts/lifecycle_record.py validate evidence/norn-opportunity-brief/lifecycle-record.json
	-python3 skills/okx-ai-agent-service-lifecycle/scripts/lifecycle_record.py validate-spec evidence/norn-opportunity-brief/service-spec.draft.json
