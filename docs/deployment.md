# Deployment and public proof

## Fastest supported path

Use the included Dockerfile on Render or Railway with a persistent volume.

Required production variables:

```text
ENVIRONMENT=production
PUBLIC_BASE_URL=https://<real-host>
NORN_DATA_DIR=/data
PAYMENT_MODE=okx
PAYMENT_NETWORK=eip155:196
PAYMENT_PRICE=$0.01
PAY_TO_ADDRESS=<real X Layer recipient>
OKX_API_KEY=<secret>
OKX_SECRET_KEY=<secret>
OKX_PASSPHRASE=<secret>
```

Install the current OKX payment SDK in the image before switching to `PAYMENT_MODE=okx`. The repository leaves it commented in `requirements.txt` because the build environment used to create this package had no package-registry access; verify the current package version from OKX documentation rather than pinning an unverified release.

## Preflight

```bash
python -m compileall app
pytest
curl -sS http://localhost:8000/health | python -m json.tool
```

## Public conformance

Replace `$BASE` with the real HTTPS origin.

```bash
curl -i "$BASE/health"
curl -i "$BASE/ready"
curl -i -X POST "$BASE/api/v1/opportunity-brief"   -H 'content-type: application/json'   --data @evidence/norn-opportunity-brief/sample-request.json
```

Expected unpaid result:

- HTTP 402;
- `PAYMENT-REQUIRED` response header;
- network `eip155:196`;
- exact intended price and recipient;
- no opportunity scoring execution in the audit log.

After explicit payment approval, replay the exact request through an OKX User agent. Expected paid result:

- HTTP 200;
- ranked opportunities and a schema-valid provenance object;
- `PAYMENT-RESPONSE` settlement proof;
- exactly one business execution;
- a duplicate replay is rejected or idempotent according to the settled SDK behaviour.

## Public truth gate

Do not call Norn operational until a separately registered OKX User agent can discover the service and complete the paid call. Save sanitised request/result digests, service ID, agent ID, transaction hash and timestamps in the lifecycle record. Never save the payment signature or API credentials.

## Rollback

1. Disable the marketplace service or set it inactive.
2. Restore the previous deployment image/version.
3. Confirm `/health` and `/ready` on the restored version.
4. Preserve the failed deployment logs after redaction.
5. Re-run public conformance before reactivation.
