# Norn threat model

| Threat | Boundary | Mitigation |
|---|---|---|
| Fabricated capability claim | Profile and Pack | Claim status is explicit; only verified evidence receives full credit or appears as verified fact. |
| Malicious source instructions | Feed | Source text is treated as data, schemas are validated, and source content cannot change policy. |
| Duplicate paid execution | Paid endpoint | Replay key storage and official x402 verification/settlement path. |
| Payment bypass | Paid endpoint | Production mode fails startup when SDK or credentials are missing; demo mode is forbidden in production. |
| Secret leakage | Logs and responses | Structured redaction, no payment signatures or API credentials in output, evidence stores digests rather than reusable authorisation. |
| Weak application submitted automatically | Pack and connector | Every pack is `draft`; submission is outside the ASP and requires explicit approval. |
| Stale opportunity | Feed | Source URL and source timestamp are mandatory; Watch is responsible for refresh and deadline changes. |
| SSRF through feeds | Discovery | Only operator-configured HTTPS feed URLs are fetched; redirects are disabled. |
| Prompt injection through opportunity text | Scoring/Pack | Core scoring and pack generation are deterministic, not instruction-following model calls. |
| Oversized or expensive request | API | Input byte ceiling, opportunity count maximum and bounded timeout. |
