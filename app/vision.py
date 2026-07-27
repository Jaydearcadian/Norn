from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import CapabilityProfile, FitAssessment, Opportunity
from .scoring import assess_fit


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EvidenceLink(BaseModel):
    requirementId: str
    requirement: str
    capability: str | None = None
    acceptedEvidence: list[str] = Field(default_factory=list)
    matchedEvidenceIds: list[str] = Field(default_factory=list)
    state: Literal["met", "partial", "missing", "unknown"]
    confidence: float = Field(ge=0, le=1)
    explanation: str


class DecisionReport(BaseModel):
    assessment: FitAssessment
    decisionConfidence: float = Field(ge=0, le=1)
    dossierConfidence: float = Field(ge=0, le=1)
    evidenceConfidence: float = Field(ge=0, le=1)
    completionProbability: float = Field(ge=0, le=1)
    evidenceGraph: list[EvidenceLink]
    uncertaintyReasons: list[str]
    nextBestAction: str


class WorkflowCreate(BaseModel):
    opportunityId: str
    title: str
    nextAction: str
    owner: str = "unassigned"
    deadline: str | None = None


class WorkflowTransition(BaseModel):
    state: Literal[
        "discovered", "normalized", "reviewed", "qualified", "gap_closing",
        "ready", "approved", "submitted", "awaiting_decision", "won", "lost", "archived"
    ]
    note: str = ""
    receiptUrl: str | None = None
    outcomeValue: float | None = None


@dataclass
class VisionEngine:
    db_path: Path

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_workflows (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    deadline TEXT,
                    receipt_url TEXT,
                    outcome_value REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_events (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES execution_workflows(id)
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_opportunity ON execution_workflows(opportunity_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_events ON workflow_events(workflow_id, created_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def decision_report(self, profile: CapabilityProfile, opportunity: Opportunity) -> DecisionReport:
        assessment = assess_fit(profile, opportunity)
        evidence_by_id = {item.id: item for item in profile.evidence}
        graph: list[EvidenceLink] = []
        confidence_values: list[float] = []
        for gap in assessment.gaps:
            matched = [evidence_by_id[item] for item in gap.matchedEvidenceIds if item in evidence_by_id]
            verified = [item for item in matched if item.status.value == "verified"]
            requirement = next(
                (item for item in [*opportunity.eligibility, *opportunity.requirements, *opportunity.deliverables]
                 if item.id == gap.requirementId),
                None,
            )
            source_confidence = requirement.confidence if requirement else 0.5
            if gap.status == "verified":
                state, confidence = "met", min(1.0, 0.75 + 0.25 * source_confidence)
            elif gap.status == "partial":
                state, confidence = "partial", 0.45 * source_confidence
            elif gap.eligibilityResult == "unknown":
                state, confidence = "unknown", 0.2 * source_confidence
            else:
                state, confidence = "missing", 0.15 * source_confidence
            confidence_values.append(confidence)
            graph.append(EvidenceLink(
                requirementId=gap.requirementId or "legacy",
                requirement=gap.requirement,
                capability=(requirement.category if requirement else gap.category),
                acceptedEvidence=(requirement.acceptedEvidence if requirement else []),
                matchedEvidenceIds=[item.id for item in matched],
                state=state,
                confidence=round(confidence, 3),
                explanation=gap.reason,
            ))

        dossier_confidence = round(
            max(0.0, min(1.0, 0.55 * opportunity.completeness + 0.45 * opportunity.normalizationConfidence)), 3
        )
        evidence_confidence = round(sum(confidence_values) / max(len(confidence_values), 1), 3)
        uncertainty: list[str] = []
        if dossier_confidence < 0.8:
            uncertainty.append("The dossier is incomplete or contains low-confidence normalisation.")
        if assessment.hardEligibility == "unknown":
            uncertainty.append("At least one mandatory eligibility condition is unknown.")
        if opportunity.reviewStatus == "pending":
            uncertainty.append("The compiled dossier is awaiting human review.")
        if not assessment.strongEvidence:
            uncertainty.append("No strong verified profile evidence matches the opportunity yet.")
        decision_confidence = round(max(0.05, min(0.99, 0.45 * dossier_confidence + 0.45 * evidence_confidence + 0.10 * (1 if opportunity.sourceType == "official" else 0.5))), 3)
        probability = round(max(0.02, min(0.95, (assessment.score / 100) * decision_confidence * (0.35 if assessment.hardEligibility == "unknown" else 1.0))), 3)
        critical = next((item for item in assessment.gaps if item.mandatory and item.status in {"missing", "partial"}), None)
        next_action = critical.recommendedAction if critical and critical.recommendedAction else (
            "Resolve unknown eligibility before committing effort." if assessment.hardEligibility == "unknown"
            else "Review and approve the Norn Pack before submission."
        )
        return DecisionReport(
            assessment=assessment,
            decisionConfidence=decision_confidence,
            dossierConfidence=dossier_confidence,
            evidenceConfidence=evidence_confidence,
            completionProbability=probability,
            evidenceGraph=graph,
            uncertaintyReasons=uncertainty,
            nextBestAction=next_action,
        )

    def create_workflow(self, request: WorkflowCreate) -> dict:
        now = utcnow()
        workflow_id = f"workflow_{uuid4().hex[:12]}"
        with self._connect() as db:
            db.execute(
                "INSERT INTO execution_workflows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (workflow_id, request.opportunityId, request.title, "discovered", request.owner,
                 request.nextAction, request.deadline, None, None, now, now),
            )
            db.execute(
                "INSERT INTO workflow_events VALUES (?, ?, ?, ?, ?, ?)",
                (f"event_{uuid4().hex[:12]}", workflow_id, None, "discovered", "Workflow created", now),
            )
        return self.get_workflow(workflow_id)

    def transition(self, workflow_id: str, transition: WorkflowTransition) -> dict | None:
        current = self.get_workflow(workflow_id)
        if current is None:
            return None
        allowed = {
            "discovered": {"normalized", "archived"}, "normalized": {"reviewed", "archived"},
            "reviewed": {"qualified", "archived"}, "qualified": {"gap_closing", "ready", "archived"},
            "gap_closing": {"ready", "archived"}, "ready": {"approved", "gap_closing", "archived"},
            "approved": {"submitted", "ready", "archived"}, "submitted": {"awaiting_decision"},
            "awaiting_decision": {"won", "lost"}, "won": {"archived"}, "lost": {"archived"},
            "archived": set(),
        }
        if transition.state not in allowed.get(current["state"], set()):
            raise ValueError(f"Invalid transition {current['state']} -> {transition.state}")
        now = utcnow()
        with self._connect() as db:
            db.execute(
                "UPDATE execution_workflows SET state=?, receipt_url=COALESCE(?, receipt_url), outcome_value=COALESCE(?, outcome_value), updated_at=? WHERE id=?",
                (transition.state, transition.receiptUrl, transition.outcomeValue, now, workflow_id),
            )
            db.execute(
                "INSERT INTO workflow_events VALUES (?, ?, ?, ?, ?, ?)",
                (f"event_{uuid4().hex[:12]}", workflow_id, current["state"], transition.state, transition.note, now),
            )
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM execution_workflows WHERE id=?", (workflow_id,)).fetchone()
            if row is None:
                return None
            events = db.execute("SELECT * FROM workflow_events WHERE workflow_id=? ORDER BY created_at", (workflow_id,)).fetchall()
        result = dict(row)
        result["events"] = [dict(item) for item in events]
        return result

    def list_workflows(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT id FROM execution_workflows ORDER BY updated_at DESC").fetchall()
        return [item for row in rows if (item := self.get_workflow(row["id"]))]

    def launch_scorecard(self, opportunities: list[Opportunity], profile: CapabilityProfile, payment_ready: bool) -> dict:
        reviewed = sum(item.reviewStatus in {"approved", "not_required"} for item in opportunities)
        verified = sum(item.lifecycleStatus == "verified" for item in opportunities)
        structured = sum(bool(item.requirements or item.eligibility or item.deliverables) for item in opportunities)
        official = sum(item.sourceType == "official" for item in opportunities)
        profile_verified = sum(item.status.value == "verified" for item in profile.evidence)
        checks = {
            "compilerCorpus": min(1.0, len(opportunities) / 30),
            "structuredDossiers": structured / max(len(opportunities), 1),
            "reviewCoverage": reviewed / max(len(opportunities), 1),
            "verifiedDossiers": verified / max(len(opportunities), 1),
            "officialSourceCoverage": official / max(len(opportunities), 1),
            "verifiedProfileEvidence": min(1.0, profile_verified / 5),
            "paymentReadiness": 1.0 if payment_ready else 0.0,
        }
        score = round(sum(checks.values()) / len(checks) * 10, 2)
        blockers = [name for name, value in checks.items() if value < 0.95]
        return {
            "score": score,
            "target": 9.5,
            "ready": score >= 9.5 and not blockers,
            "checks": {key: round(value * 10, 2) for key, value in checks.items()},
            "blockers": blockers,
            "truth": "A score below 9.5 identifies real missing proof; it is never rounded up for presentation.",
        }
