# Norn build status

## Achieved

- Product and service architecture frozen except the recipient and OKX identity values.
- Norn Profile, Feed, Score, Gaps, Pack and Watch implemented.
- Bounded `POST /api/v1/opportunity-brief` ASP outcome implemented.
- Deterministic scoring, evidence rules, provenance digests and approval boundary implemented.
- Verified evidence requires a public URL or SHA-256 digest and a link from the capability claim.
- Configured HTTPS feeds and optional GitHub issue discovery implemented.
- Local HTTP 402 challenge, valid paid replay and duplicate replay rejection implemented for conformance testing.
- Official OKX Python x402 middleware `0.1.1` plus EVM dependencies pinned and integrated with explicit X Layer USDT0 terms.
- Dashboard, Dockerfile, Render and Railway definitions implemented.
- Public HTTPS deployment verified in free mode at `https://norn.161.97.81.1.nip.io`.
- Sixteen tests passing locally, including a real import/construction check against the installed OKX SDK.
- GitHub Actions CI added for Python compilation, JavaScript syntax, tests, and lifecycle validation.
- Lifecycle record status: `public_deployed`; paid public conformance remains in progress.

## External blockers

1. Real X Layer recipient wallet.
2. OKX facilitator API key, secret and passphrase.
3. Production redeploy with `PAYMENT_MODE=okx`.
4. Live unpaid HTTP 402 challenge and independently paid replay/settlement proof.
5. OKX ASP identity and service registration.
6. Marketplace review, activation, and discovery.
7. Independent call from a separately registered OKX User agent.
8. A2A scenario training and live task-runtime readiness if the Strategy service is listed.
9. Final demo post and campaign form.

None of the external states above are claimed as complete.
