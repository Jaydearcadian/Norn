from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, settings as default_settings
from .digests import sha256_digest
from .discovery import DiscoveryEngine
from .gaps import identify_gaps
from .models import (
    CapabilityProfile, DiscoverRequest, FitAssessment, GapRequest, HealthResponse,
    ImportOpportunityRequest, OpportunityBriefRequest, OpportunityBriefResponse,
    PackArtifact, PackRequest, ReviewDecision, ScoreRequest, WatchItem,
)
from .normalization import compile_opportunity, snapshot_from_response
from .pack import prepare_pack
from .payment import DemoPaymentGateway, PaymentRequired, configure_okx_payment_middleware
from .redaction import redact
from .scoring import assess_fit
from .service import build_opportunity_brief
from .store import JsonStore


def create_app(settings: Settings = default_settings) -> FastAPI:
    configuration_errors = settings.configuration_errors()
    if configuration_errors and settings.environment == "production":
        raise RuntimeError("; ".join(configuration_errors))

    app = FastAPI(title="Norn", version=__version__, description="Opportunity compiler and verified capability intelligence.")
    app.state.settings = settings
    app.state.store = JsonStore(settings)
    app.state.discovery = DiscoveryEngine(settings, app.state.store)
    app.state.demo_payment = DemoPaymentGateway(settings, app.state.store)

    configure_okx_payment_middleware(app, settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment != "production" else [settings.public_base_url],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type", "PAYMENT-SIGNATURE", "X-PAYMENT"],
        expose_headers=["PAYMENT-REQUIRED", "PAYMENT-RESPONSE", "X-PAYMENT-RESPONSE"],
    )

    @app.exception_handler(PaymentRequired)
    async def payment_required_handler(_request: Request, exc: PaymentRequired):
        return JSONResponse(status_code=402, content=exc.challenge, headers={"PAYMENT-REQUIRED": exc.header, "Cache-Control": "no-store"})

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        blockers = settings.readiness_blockers()
        return HealthResponse(status="degraded" if blockers else "ok", service="norn", version=__version__, paymentMode=settings.payment_mode, blockers=blockers)

    @app.get("/ready")
    async def ready():
        blockers = settings.readiness_blockers()
        return {"ready": not blockers, "blockers": blockers}

    @app.get("/api/profile", response_model=CapabilityProfile)
    async def get_profile():
        return app.state.store.get_profile()

    @app.put("/api/profile", response_model=CapabilityProfile)
    async def put_profile(profile: CapabilityProfile):
        profile.updatedAt = datetime.now(timezone.utc)
        saved = app.state.store.save_profile(profile)
        app.state.store.append_audit({"at": datetime.now(timezone.utc).isoformat(), "event": "profile.updated", "digest": sha256_digest(saved.model_dump(mode="json"))})
        return saved

    @app.post("/api/feed")
    async def discover(request: DiscoverRequest):
        items = await app.state.discovery.discover(request)
        return {"items": items, "count": len(items), "liveDiscovery": settings.enable_live_discovery, "compilerVersion": "normalization-v2"}

    @app.post("/api/feed/import")
    async def import_opportunities(request: ImportOpportunityRequest):
        compiled = [compile_opportunity(item, []) for item in request.opportunities]
        saved = app.state.store.save_opportunities(compiled)
        return {"count": len(saved)}

    @app.post("/api/sources/ingest")
    async def ingest_source(payload: dict):
        url = str(payload.get("url", ""))
        if not url:
            raise HTTPException(422, "url is required")
        items = await app.state.discovery.ingest_url(url, str(payload.get("sourceType", "official")))
        return {"items": items, "count": len(items)}

    @app.get("/api/opportunities/{opportunity_id}/history")
    async def opportunity_history(opportunity_id: str):
        items = app.state.store.opportunity_history(opportunity_id)
        if not items:
            raise HTTPException(404, "Opportunity not found")
        return {"items": items, "count": len(items)}

    @app.get("/api/review-queue")
    async def review_queue():
        items = app.state.store.list_review_queue()
        return {"items": items, "count": len(items)}

    @app.post("/api/review-queue/{opportunity_id}/{version}")
    async def review_opportunity(opportunity_id: str, version: int, decision: ReviewDecision):
        app.state.store.review(opportunity_id, version, decision.status, decision.note)
        return {"ok": True, "opportunityId": opportunity_id, "version": version, "status": decision.status}

    @app.post("/api/score", response_model=FitAssessment)
    async def score(request: ScoreRequest):
        return assess_fit(request.profile, request.opportunity)

    @app.post("/api/gaps")
    async def gaps(request: GapRequest):
        return {"items": identify_gaps(request.profile, request.opportunity)}

    @app.post("/api/packs", response_model=PackArtifact)
    async def packs(request: PackRequest):
        artifact = prepare_pack(request.profile, request.opportunity, request.assessment)
        app.state.store.save_pack(artifact)
        return artifact

    @app.get("/api/packs")
    async def list_packs():
        return {"items": app.state.store.list_packs()}

    @app.get("/api/packs/{pack_id}", response_model=PackArtifact)
    async def get_pack(pack_id: str):
        pack = app.state.store.get_pack(pack_id)
        if pack is None:
            raise HTTPException(404, "Pack not found")
        return pack

    @app.get("/api/watch")
    async def list_watch():
        return {"items": app.state.store.list_watch()}

    @app.post("/api/watch", response_model=WatchItem)
    async def save_watch(item: WatchItem):
        item.updatedAt = datetime.now(timezone.utc)
        return app.state.store.save_watch(item)

    @app.post("/api/watch/digest")
    async def watch_digest():
        items = app.state.store.list_watch()
        now = datetime.now(timezone.utc)
        urgent, followups = [], []
        for item in items:
            if item.deadline:
                days = (item.deadline - now.date()).days
                if 0 <= days <= 7 and item.status not in {"submitted", "won", "lost", "archived"}:
                    urgent.append({"id": item.id, "title": item.title, "daysRemaining": days, "nextAction": item.nextAction})
            if item.followUpAt and item.followUpAt <= now and item.status not in {"won", "lost", "archived"}:
                followups.append({"id": item.id, "title": item.title, "followUpAt": item.followUpAt, "nextAction": item.nextAction})
        return {"urgentDeadlines": urgent, "dueFollowUps": followups, "generatedAt": now}

    @app.post("/api/v1/opportunity-brief", response_model=OpportunityBriefResponse)
    async def opportunity_brief(request: Request):
        body = await request.body()
        if len(body) > settings.maximum_input_bytes:
            raise HTTPException(413, "Request exceeds MAXIMUM_INPUT_BYTES")
        try:
            payload = OpportunityBriefRequest.model_validate_json(body)
        except Exception as exc:
            raise HTTPException(422, detail={"error": "invalid_input", "message": str(exc)}) from exc
        payment = await app.state.demo_payment.require(request, body) if settings.payment_mode == "demo" else None
        result = build_opportunity_brief(payload)
        app.state.store.append_audit(redact({"at": datetime.now(timezone.utc).isoformat(), "event": "opportunity_brief.executed", "requestDigest": result.provenance.requestDigest, "resultDigest": result.provenance.resultDigest, "paymentMode": settings.payment_mode, "replayKey": payment.replay_key if payment else None}))
        return result

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
