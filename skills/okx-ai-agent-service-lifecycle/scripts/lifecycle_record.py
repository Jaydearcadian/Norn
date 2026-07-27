#!/usr/bin/env python3
"""Scaffold, advance, and validate OKX AI agent service lifecycle records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PHASES = [
    "contract", "implementation", "localVerification", "deployment",
    "publicVerification", "identityRegistration", "activation", "discovery",
    "independentSelfTest", "monitoring",
]
PHASE_STATUS = {"pending", "in_progress", "passed", "failed", "blocked", "not_applicable"}
RECORD_STATUS = {
    "planned", "implemented", "local_verified", "public_deployed", "registered",
    "active", "publicly_proven", "operational", "deactivated", "decommissioned", "blocked",
}
SERVICE_TYPES = {"A2MCP", "A2A"}
SENSITIVE_KEYS = {
    "privatekey", "seedphrase", "mnemonic", "keystore", "apitoken",
    "cloudflareapitoken", "authorization", "bearertoken", "paymentsignature",
    "xpayment", "executioncredential", "sessioncertificate", "password", "secret",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def phase() -> dict:
    return {"status": "pending", "recordedAt": None, "evidence": [], "notes": ""}


def make_record(slug: str, service_type: str) -> dict:
    stamp = now()
    return {
        "schemaVersion": "okx-ai-agent-service-lifecycle-v1",
        "serviceSlug": slug,
        "serviceType": service_type,
        "status": "planned",
        "provider": {"agentId": None, "serviceId": None, "walletAddress": None},
        "public": {"endpoint": None, "deploymentPlatform": None, "deploymentVersionId": None},
        "phases": {name: phase() for name in PHASES},
        "evidence": [],
        "limitations": [],
        "rollback": {"procedure": "", "lastVerifiedAt": None},
        "createdAt": stamp,
        "updatedAt": stamp,
    }


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def scan_sensitive(value, path: str = "$", errors: list[str] | None = None) -> list[str]:
    errors = errors if errors is not None else []
    if isinstance(value, dict):
        for key, child in value.items():
            if normalize_key(str(key)) in SENSITIVE_KEYS:
                errors.append(f"sensitive key forbidden at {path}.{key}")
            scan_sensitive(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_sensitive(child, f"{path}[{index}]", errors)
    return errors


def validate_record(record: dict) -> list[str]:
    errors: list[str] = []
    if record.get("schemaVersion") != "okx-ai-agent-service-lifecycle-v1":
        errors.append("unsupported schemaVersion")
    slug = record.get("serviceSlug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        errors.append("serviceSlug must be lowercase kebab-case")
    service_type = record.get("serviceType")
    if service_type not in SERVICE_TYPES:
        errors.append("serviceType must be A2MCP or A2A")
    status = record.get("status")
    if status not in RECORD_STATUS:
        errors.append("invalid record status")
    phases = record.get("phases")
    if not isinstance(phases, dict):
        errors.append("phases must be an object")
        phases = {}
    for name in PHASES:
        item = phases.get(name)
        if not isinstance(item, dict):
            errors.append(f"missing phase {name}")
            continue
        if item.get("status") not in PHASE_STATUS:
            errors.append(f"invalid status for phase {name}")
        if not isinstance(item.get("evidence"), list):
            errors.append(f"phase {name} evidence must be an array")
    public = record.get("public", {})
    endpoint = public.get("endpoint") if isinstance(public, dict) else None
    if service_type == "A2MCP" and endpoint is not None and not str(endpoint).startswith("https://"):
        errors.append("A2MCP public endpoint must use https://")
    if service_type == "A2A" and endpoint not in (None, ""):
        errors.append("A2A lifecycle record must not advertise a service endpoint")
    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be an array")
        evidence = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        digest = item.get("sha256")
        if digest not in (None, "") and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            errors.append(f"evidence[{index}].sha256 must be 64 lowercase hex characters")
        if not item.get("kind") or not item.get("path"):
            errors.append(f"evidence[{index}] requires kind and path")
    if status in {"publicly_proven", "operational"}:
        for required in ("publicVerification", "discovery", "independentSelfTest"):
            if phases.get(required, {}).get("status") != "passed":
                errors.append(f"{status} requires phase {required}=passed")
    if status == "operational" and phases.get("monitoring", {}).get("status") != "passed":
        errors.append("operational requires phase monitoring=passed")
    errors.extend(scan_sensitive(record))
    return errors


def validate_spec(spec: dict) -> list[str]:
    errors: list[str] = []
    if spec.get("schemaVersion") != "okx-ai-service-spec-v1":
        errors.append("unsupported service spec schemaVersion")
    slug = spec.get("serviceSlug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        errors.append("serviceSlug must be lowercase kebab-case")
    service_type = spec.get("serviceType")
    if service_type not in SERVICE_TYPES:
        errors.append("serviceType must be A2MCP or A2A")
    for key in ("name", "customer", "outcome"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            errors.append(f"{key} is required")
    description = spec.get("serviceDescription")
    if not isinstance(description, dict) or not str(description.get("capability", "")).strip():
        errors.append("serviceDescription.capability is required")
    elif not isinstance(description.get("requiredInputs"), list) or not description["requiredInputs"]:
        errors.append("serviceDescription.requiredInputs must be a non-empty array")
    inputs = spec.get("inputs")
    outputs = spec.get("outputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("schema"), dict) or not inputs["schema"]:
        errors.append("inputs.schema must be a non-empty object")
    if not isinstance(outputs, dict) or not isinstance(outputs.get("schema"), dict) or not outputs["schema"]:
        errors.append("outputs.schema must be a non-empty object")
    authority = spec.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority must be an object")
    else:
        if authority.get("runtimeSignsForUser") is not False:
            errors.append("authority.runtimeSignsForUser must be false unless a separately approved custody design replaces this template")
        if authority.get("runtimeBroadcastsForUser") is not False:
            errors.append("authority.runtimeBroadcastsForUser must be false unless a separately approved custody design replaces this template")
        if authority.get("humanApprovalRequired") is not True:
            errors.append("authority.humanApprovalRequired must be true")
    pricing = spec.get("pricing")
    if not isinstance(pricing, dict):
        errors.append("pricing must be an object")
        pricing = {}
    a2mcp = spec.get("a2mcp")
    a2a = spec.get("a2a")
    if service_type == "A2MCP":
        endpoint = a2mcp.get("endpoint") if isinstance(a2mcp, dict) else None
        if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
            errors.append("A2MCP a2mcp.endpoint must use https://")
        for key in ("listingFeeUsdt", "paymentNetwork", "paymentAsset", "atomicAmount", "recipient"):
            if not str(pricing.get(key, "")).strip():
                errors.append(f"A2MCP pricing.{key} is required")
        if str(pricing.get("listingFeeUsdt", "")) and not re.fullmatch(r"\d+(?:\.\d{1,6})?", str(pricing["listingFeeUsdt"])):
            errors.append("A2MCP pricing.listingFeeUsdt must be a plain numeric string with at most 6 decimals")
        if str(pricing.get("atomicAmount", "")) and not re.fullmatch(r"[1-9]\d*", str(pricing["atomicAmount"])):
            errors.append("A2MCP pricing.atomicAmount must be a positive integer string")
    if service_type == "A2A":
        endpoint = a2mcp.get("endpoint") if isinstance(a2mcp, dict) else None
        if endpoint not in (None, ""):
            errors.append("A2A spec must not advertise an A2MCP endpoint")
        categories = a2a.get("taskCategories") if isinstance(a2a, dict) else None
        if not isinstance(categories, list) or not categories:
            errors.append("A2A a2a.taskCategories must be a non-empty array")
        for key in ("revisionPolicy", "cancellationPolicy", "disputePolicy"):
            if not isinstance(a2a, dict) or not str(a2a.get(key, "")).strip():
                errors.append(f"A2A a2a.{key} is required")
    errors.extend(scan_sensitive(spec))
    return errors


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("record root must be an object")
    return value


def save(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=False) + "\n")


def cmd_init(args) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"refusing to overwrite existing record: {path}", file=sys.stderr)
        return 2
    record = make_record(args.slug, args.type)
    errors = validate_record(record)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    save(path, record)
    print(json.dumps({"ok": True, "path": str(path), "status": record["status"]}))
    return 0


def cmd_validate(args) -> int:
    try:
        record = load(Path(args.path))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        return 1
    errors = validate_record(record)
    print(json.dumps({"ok": not errors, "errors": errors, "status": record.get("status")}, indent=2))
    return 0 if not errors else 1


def cmd_validate_spec(args) -> int:
    try:
        spec = load(Path(args.path))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        return 1
    errors = validate_spec(spec)
    print(json.dumps({"ok": not errors, "errors": errors, "serviceType": spec.get("serviceType")}, indent=2))
    return 0 if not errors else 1


def cmd_advance(args) -> int:
    path = Path(args.path)
    record = load(path)
    if args.phase not in PHASES:
        print(f"unknown phase: {args.phase}", file=sys.stderr)
        return 2
    record["phases"][args.phase]["status"] = args.phase_status
    record["phases"][args.phase]["recordedAt"] = now()
    if args.notes is not None:
        record["phases"][args.phase]["notes"] = args.notes
    if args.record_status is not None:
        record["status"] = args.record_status
    record["updatedAt"] = now()
    errors = validate_record(record)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    save(path, record)
    print(json.dumps({"ok": True, "path": str(path), "phase": args.phase, "status": record["status"]}))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("path")
    init.add_argument("--slug", required=True)
    init.add_argument("--type", required=True, choices=sorted(SERVICE_TYPES))
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)
    validate = sub.add_parser("validate")
    validate.add_argument("path")
    validate.set_defaults(func=cmd_validate)
    validate_spec_parser = sub.add_parser("validate-spec")
    validate_spec_parser.add_argument("path")
    validate_spec_parser.set_defaults(func=cmd_validate_spec)
    advance = sub.add_parser("advance")
    advance.add_argument("path")
    advance.add_argument("--phase", required=True, choices=PHASES)
    advance.add_argument("--phase-status", required=True, choices=sorted(PHASE_STATUS))
    advance.add_argument("--record-status", choices=sorted(RECORD_STATUS))
    advance.add_argument("--notes")
    advance.set_defaults(func=cmd_advance)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    raise SystemExit(args.func(args))
