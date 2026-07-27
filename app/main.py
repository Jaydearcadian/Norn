from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
from .pack import prepare_pack
from .payment import DemoPaymentGateway, PaymentRequired, configure_okx_payment_middleware
from .redaction import redact
from .scoring import assess_fit
from .service import build_opportunity_brief
from .store import JsonStore
from .vision import VisionEngine, WorkflowCreate, WorkflowTransition


def _feed_intelligence(opportunity, assessment) -> dict:
    mandatory = [gap for gap in assessment.gaps if gap.mandatory and gap.status != "not_applicable"]
    evidenced = sum(gap.status == "verified" for gap in mandatory)
    critical = next((gap for gap in mandatory if gap.status in {"missing", "partial"}), None)
    return {
        "whyFound": "Matched configured source discovery and normalized technical opportunity domains.",
        "officialSource": opportunity.sourceType == "official",
        "sourceQuality": "official" if opportunity.sourceType == "official" else opportunity.sourceType,
        "completeness": opportunity.completeness,
        "freshness": opportunity.sourceTimestamp,
        "changedFields": opportunity.changedFields,
        "deadlineVerified": bool(opportunity.deadline and opportunity.fieldProvenance.get("timing") and opportunity.fieldProvenance["timing"].basis.value == "explicit"),
        "independentlyActionable": opportunity.independentlyActionable,
        "eligibility": assessment.eligibility,
        "hardEligibility": assessment.hardEligibility,
        "requirementsEvidenced": evidenced,
        "requirementsTotal": len(mandatory),
        "strongestMatch": assessment.strongEvidence[0] if assessment.strongEvidence else None,
        "criticalGap": critical.requirement if critical else None,
        "recommendedAction": critical.recommendedAction if critical else "Review the dossier and prepare the approval-gated Pack.",
        "reviewStatus": opportunity.reviewStatus,
        "lifecycleStatus": opportunity.lifecycleStatus,
        "version": opportunity.version,
    }


def create_app(settings: Settings = default_settings) -> FastAPI:
    configuration_errors = settings.configuration_errors()
    if configuration_errors and settings.environment == "production":
        raise RuntimeError("; ".join(configuration_errors))

    app = FastAPI(title="Norn", version=__version__, description="Opportunity compiler and verified capability intelligence.")
    app.state.settings = settings
    app.state.store = JsonStore(settings)
    app.state.discovery = DiscoveryEngine(settings, app.state.store)
    app.state.demo_payment = DemoPaymentGateway(settings, app.state.store)
    app.state.vision = VisionEngine(app.state.store.db_path)

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
        current_blockers = settings.readiness_blockers()
        return HealthResponse(status="degraded" if current_blockers else "ok", service="norn", version=__version__, paymentMode=settings.payment_mode, blockers=current_blockers)

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
        app.state.store.append_audit({"at": datetime.now(timezone.utc).isoformat(), "event": "profile.updated", "digest": sha256_digest(saved.model_dump(mode="json")), "version": saved.version})
        return saved

    @app.post("/api/feed")
    async def discover(request: DiscoverRequest):
        items = await app.state.discovery.discover(request)
        profile = request.profile or app.state.store.get_profile()
        payload = []
        for item in items:
            assessment = assess_fit(profile, item)
            record = item.model_dump(mode="json")
            record["intelligence"] = _feed_intelligence(item, assessment)
            payload.append(record)
        return {"items": payload, "count": len(payload), "liveDiscovery": settings.enable_live_discovery, "compilerVersion": "normalization-v2"}

    @app.post("/api/feed/import")
    async def import_opportunities(request: ImportOpportunityRequest):
        saved = app.state.store.save_opportunities(request.opportunities)
        return {"count": len(saved)}

    @app.get("/api/opportunities/{opportunity_id}/history")
    async def opportunity_history(opportunity_id: str):
        history = app.state.store.get_opportunity_history(opportunity_id)
        if not history:
            raise HTTPException(404, "Opportunity dossier not found")
        return {"opportunityId": opportunity_id, "versions": history}

    @app.get("/api/feed/review")
    async def review_queue():
        items = app.state.store.list_review_queue()
        return {"items": items, "count": len(items)}

    @app.post("/api/feed/review/{review_id}")
    async def resolve_review(review_id: str, decision: ReviewDecision):
        if not app.state.store.resolve_review(review_id, decision.status, decision.notes):
            raise HTTPException(404, "Review item not found")
        return {"id": review_id, "status": decision.status}

    @app.post("/api/score", response_model=FitAssessment)
    async def score(request: ScoreRequest):
        return assess_fit(request.profile, request.opportunity)

    @app.post("/api/decision")
    async def decision(request: ScoreRequest):
        return app.state.vision.decision_report(request.profile, request.opportunity)

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

    @app.get("/api/workflows")
    async def list_workflows():
        items = app.state.vision.list_workflows()
        return {"items": items, "count": len(items)}

    @app.post("/api/workflows")
    async def create_workflow(request: WorkflowCreate):
        return app.state.vision.create_workflow(request)

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        workflow = app.state.vision.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(404, "Workflow not found")
        return workflow

    @app.post("/api/workflows/{workflow_id}/transition")
    async def transition_workflow(workflow_id: str, transition: WorkflowTransition):
        try:
            workflow = app.state.vision.transition(workflow_id, transition)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if workflow is None:
            raise HTTPException(404, "Workflow not found")
        return workflow

    @app.get("/api/launch-readiness")
    async def launch_readiness():
        return app.state.vision.launch_scorecard(
            app.state.store.list_opportunities(),
            app.state.store.get_profile(),
            payment_ready=not settings.readiness_blockers(),
        )

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
        app.state.store.append_audit(redact({
            "at": datetime.now(timezone.utc).isoformat(), "event": "opportunity_brief.executed",
            "requestDigest": result.provenance.requestDigest, "resultDigest": result.provenance.resultDigest,
            "paymentMode": settings.payment_mode, "replayKey": payment.replay_key if payment else None,
            "opportunityVersions": result.provenance.opportunityVersions,
        }))
        return result

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
