from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .digests import sha256_digest
from .models import CapabilityProfile, Evidence, FitAssessment, Opportunity, OpportunityRequirement
from .scoring import assess_fit


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


EVIDENCE_KIND_ALIASES: dict[str, set[str]] = {
    "public repository": {"repository"},
    "repository": {"repository"},
    "source code": {"repository"},
    "public deployment": {"deployment"},
    "deployment": {"deployment"},
    "marketplace listing": {"deployment", "documentation"},
    "activation status": {"deployment", "documentation"},
    "test": {"test"},
    "test report": {"test", "documentation"},
    "transaction": {"transaction"},
    "on-chain transaction": {"transaction"},
    "demo": {"demo"},
    "video": {"demo"},
    "documentation": {"documentation"},
    "identity": {"profile", "documentation"},
}

WORKFLOW_STATES = (
    "discovered", "normalized", "reviewed", "qualified", "gap_closing",
    "ready", "approved", "submitted", "awaiting_decision", "won", "lost", "archived",
)

VALID_TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"normalized", "archived"},
    "normalized": {"reviewed", "archived"},
    "reviewed": {"qualified", "archived"},
    "qualified": {"gap_closing", "ready", "archived"},
    "gap_closing": {"qualified", "ready", "archived"},
    "ready": {"approved", "gap_closing", "archived"},
    "approved": {"submitted", "ready", "archived"},
    "submitted": {"awaiting_decision", "won", "lost"},
    "awaiting_decision": {"won", "lost", "submitted"},
    "won": {"archived"},
    "lost": {"archived"},
    "archived": set(),
}


class WorkflowCreate(BaseModel):
    opportunityId: str
    title: str
    owner: str | None = None
    nextAction: str = "Review the normalized dossier."


class WorkflowTransition(BaseModel):
    toState: Literal[
        "discovered", "normalized", "reviewed", "qualified", "gap_closing",
        "ready", "approved", "submitted", "awaiting_decision", "won", "lost", "archived",
    ]
    note: str = ""
    evidenceIds: list[str] = Field(default_factory=list)


class WorkflowTaskCreate(BaseModel):
    title: str
    owner: str | None = None
    dueAt: datetime | None = None
    dependencyIds: list[str] = Field(default_factory=list)
    evidenceRequirementId: str | None = None


class OutcomeRecord(BaseModel):
    result: Literal["won", "lost", "withdrawn", "ineligible", "expired"]
    realisedValue: float | None = Field(default=None, ge=0)
    currency: str | None = None
    hoursSpent: float | None = Field(default=None, ge=0)
    feedback: str = ""
    lessons: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class EvidenceMatch:
    requirement_id: str
    result: Literal["verified", "partial", "missing", "unknown"]
    evidence_ids: tuple[str, ...]
    confidence: float
    reason: str


class VisionStore:
    """Adds the decision and execution layers to the compiler database.

    The compiler remains the opportunity source of truth. This store owns typed evidence
    links, reproducible assessments, workflow execution and outcome feedback.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_links (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    profile_version INTEGER NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    opportunity_version INTEGER NOT NULL,
                    requirement_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    match_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(profile_id, profile_version, opportunity_id, opportunity_version, requirement_id, evidence_id)
                );
                CREATE TABLE IF NOT EXISTS decision_assessments (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    profile_version INTEGER NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    opportunity_version INTEGER NOT NULL,
                    scoring_engine_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    completion_probability REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(profile_id, profile_version, opportunity_id, opportunity_version, scoring_engine_version)
                );
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    owner TEXT,
                    next_action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_events (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    note TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS workflow_tasks (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    owner TEXT,
                    due_at TEXT,
                    dependency_ids_json TEXT NOT NULL,
                    evidence_requirement_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL UNIQUE,
                    result TEXT NOT NULL,
                    realised_value REAL,
                    currency TEXT,
                    hours_spent REAL,
                    feedback TEXT NOT NULL,
                    lessons_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id TEXT PRIMARY KEY,
                    corpus_digest TEXT NOT NULL,
                    opportunity_count INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _accepted_kinds(requirement: OpportunityRequirement) -> set[str]:
        kinds: set[str] = set()
        for accepted in requirement.acceptedEvidence:
            lowered = accepted.lower().strip()
            kinds |= EVIDENCE_KIND_ALIASES.get(lowered, set())
            for label, aliases in EVIDENCE_KIND_ALIASES.items():
                if label in lowered:
                    kinds |= aliases
        return kinds

    @staticmethod
    def _evidence_text(evidence: Evidence) -> str:
        return " ".join([evidence.label, evidence.note, *evidence.tags]).lower()

    def match_requirement(self, profile: CapabilityProfile, requirement: OpportunityRequirement) -> EvidenceMatch:
        accepted_kinds = self._accepted_kinds(requirement)
        statement_terms = {part for part in requirement.statement.lower().replace("/", " ").split() if len(part) > 3}
        verified: list[Evidence] = []
        claimed: list[Evidence] = []
        for evidence in profile.evidence:
            kind_match = not accepted_kinds or evidence.kind in accepted_kinds
            text = self._evidence_text(evidence)
            semantic_overlap = bool(statement_terms & set(text.replace("-", " ").split()))
            if not (kind_match and (semantic_overlap or accepted_kinds)):
                continue
            if evidence.status.value == "verified":
                verified.append(evidence)
            elif evidence.status.value == "claimed":
                claimed.append(evidence)
        if verified:
            confidence = min(1.0, 0.75 + 0.08 * len(verified) + 0.12 * requirement.confidence)
            return EvidenceMatch(requirement.id, "verified", tuple(item.id for item in verified), confidence, "Verified evidence matches an accepted proof type for this requirement.")
        if claimed:
            confidence = min(0.74, 0.42 + 0.06 * len(claimed) + 0.1 * requirement.confidence)
            return EvidenceMatch(requirement.id, "partial", tuple(item.id for item in claimed), confidence, "Relevant evidence exists but is not independently verified.")
        if requirement.interpretation.value in {"unknown", "conflicting"} or requirement.confidence < 0.5:
            return EvidenceMatch(requirement.id, "unknown", (), max(0.1, requirement.confidence), "The requirement itself is not sufficiently certain for a definitive evidence decision.")
        return EvidenceMatch(requirement.id, "missing", (), max(0.5, requirement.confidence), "No evidence matches the accepted proof types.")

    def assess(self, profile: CapabilityProfile, opportunity: Opportunity) -> dict[str, Any]:
        base: FitAssessment = assess_fit(profile, opportunity)
        requirements = [*opportunity.eligibility, *opportunity.requirements, *opportunity.deliverables]
        typed = [self.match_requirement(profile, requirement) for requirement in requirements]
        mandatory = [match for match, requirement in zip(typed, requirements) if requirement.mandatory]
        coverage = (sum(match.result == "verified" for match in mandatory) / len(mandatory)) if mandatory else 1.0
        unknown_ratio = (sum(match.result == "unknown" for match in mandatory) / len(mandatory)) if mandatory else 0.0
        dossier_confidence = max(0.0, min(1.0, 0.45 * opportunity.completeness + 0.35 * opportunity.normalizationConfidence + 0.20 * (1 - unknown_ratio)))
        evidence_confidence = sum(match.confidence for match in typed) / len(typed) if typed else 0.5
        assessment_confidence = round(max(0.05, min(0.99, 0.58 * dossier_confidence + 0.42 * evidence_confidence)), 3)
        feasibility = {"low": 0.86, "medium": 0.66, "high": 0.42}[opportunity.applicationEffort]
        eligibility_factor = {"met": 1.0, "unknown": 0.55, "failed": 0.0}[base.hardEligibility]
        completion_probability = round(max(0.01, min(0.98, (base.score / 100) * assessment_confidence * feasibility * eligibility_factor)), 3)
        payload = base.model_dump(mode="json")
        payload.update({
            "assessmentConfidence": assessment_confidence,
            "dossierConfidence": round(dossier_confidence, 3),
            "mandatoryCoverage": round(coverage, 3),
            "completionProbability": completion_probability,
            "typedEvidenceMatches": [match.__dict__ for match in typed],
        })
        assessment_id = "assessment_" + sha256_digest({
            "profile": [profile.id, profile.version],
            "opportunity": [opportunity.canonicalId or opportunity.id, opportunity.version],
            "engine": base.scoringEngineVersion,
        })[:20]
        with self._connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO decision_assessments
                (id, profile_id, profile_version, opportunity_id, opportunity_version, scoring_engine_version, payload_json, confidence, completion_probability, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (assessment_id, profile.id, profile.version, opportunity.canonicalId or opportunity.id, opportunity.version, base.scoringEngineVersion, json.dumps(payload), assessment_confidence, completion_probability, utcnow()),
            )
            for match in typed:
                for evidence_id in match.evidence_ids:
                    link_id = "link_" + sha256_digest([assessment_id, match.requirement_id, evidence_id])[:20]
                    db.execute(
                        """INSERT OR REPLACE INTO evidence_links
                        (id, profile_id, profile_version, opportunity_id, opportunity_version, requirement_id, evidence_id, match_type, confidence, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (link_id, profile.id, profile.version, opportunity.canonicalId or opportunity.id, opportunity.version, match.requirement_id, evidence_id, match.result, match.confidence, match.reason, utcnow()),
                    )
        return payload

    def create_workflow(self, request: WorkflowCreate) -> dict[str, Any]:
        workflow_id = "workflow_" + uuid4().hex[:16]
        stamp = utcnow()
        with self._connect() as db:
            existing = db.execute("SELECT * FROM workflows WHERE opportunity_id=?", (request.opportunityId,)).fetchone()
            if existing:
                return dict(existing)
            db.execute(
                "INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (workflow_id, request.opportunityId, request.title, "discovered", request.owner, request.nextAction, stamp, stamp),
            )
            db.execute(
                "INSERT INTO workflow_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("event_" + uuid4().hex[:16], workflow_id, None, "discovered", "Workflow created.", "[]", stamp),
            )
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        with self._connect() as db:
            workflow = db.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not workflow:
                raise KeyError(workflow_id)
            events = [dict(row) for row in db.execute("SELECT * FROM workflow_events WHERE workflow_id=? ORDER BY created_at", (workflow_id,))]
            tasks = [dict(row) for row in db.execute("SELECT * FROM workflow_tasks WHERE workflow_id=? ORDER BY created_at", (workflow_id,))]
            outcome = db.execute("SELECT * FROM outcomes WHERE workflow_id=?", (workflow_id,)).fetchone()
        result = dict(workflow)
        for event in events:
            event["evidence_ids"] = json.loads(event.pop("evidence_ids_json"))
        for task in tasks:
            task["dependency_ids"] = json.loads(task.pop("dependency_ids_json"))
        result["events"] = events
        result["tasks"] = tasks
        result["outcome"] = dict(outcome) if outcome else None
        if result["outcome"]:
            result["outcome"]["lessons"] = json.loads(result["outcome"].pop("lessons_json"))
        return result

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT id FROM workflows ORDER BY updated_at DESC").fetchall()
        return [self.get_workflow(row["id"]) for row in rows]

    def transition(self, workflow_id: str, transition: WorkflowTransition) -> dict[str, Any]:
        current = self.get_workflow(workflow_id)
        from_state = current["state"]
        if transition.toState not in VALID_TRANSITIONS[from_state]:
            raise ValueError(f"invalid workflow transition: {from_state} -> {transition.toState}")
        if transition.toState in {"approved", "submitted"} and not transition.evidenceIds:
            raise ValueError(f"{transition.toState} requires approval or submission evidence")
        stamp = utcnow()
        with self._connect() as db:
            db.execute("UPDATE workflows SET state=?, updated_at=? WHERE id=?", (transition.toState, stamp, workflow_id))
            db.execute(
                "INSERT INTO workflow_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("event_" + uuid4().hex[:16], workflow_id, from_state, transition.toState, transition.note, json.dumps(transition.evidenceIds), stamp),
            )
        return self.get_workflow(workflow_id)

    def add_task(self, workflow_id: str, task: WorkflowTaskCreate) -> dict[str, Any]:
        self.get_workflow(workflow_id)
        task_id = "task_" + uuid4().hex[:16]
        with self._connect() as db:
            db.execute(
                "INSERT INTO workflow_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, workflow_id, task.title, task.owner, task.dueAt.isoformat() if task.dueAt else None, json.dumps(task.dependencyIds), task.evidenceRequirementId, "open", utcnow(), None),
            )
        return self.get_workflow(workflow_id)

    def complete_task(self, workflow_id: str, task_id: str) -> dict[str, Any]:
        current = self.get_workflow(workflow_id)
        task = next((item for item in current["tasks"] if item["id"] == task_id), None)
        if not task:
            raise KeyError(task_id)
        incomplete_dependencies = [dependency for dependency in task["dependency_ids"] if not any(item["id"] == dependency and item["status"] == "completed" for item in current["tasks"])]
        if incomplete_dependencies:
            raise ValueError("task dependencies are incomplete")
        with self._connect() as db:
            db.execute("UPDATE workflow_tasks SET status='completed', completed_at=? WHERE id=? AND workflow_id=?", (utcnow(), task_id, workflow_id))
        return self.get_workflow(workflow_id)

    def record_outcome(self, workflow_id: str, outcome: OutcomeRecord) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        if workflow["state"] not in {"submitted", "awaiting_decision", "won", "lost"}:
            raise ValueError("outcomes can only be recorded after submission")
        outcome_id = "outcome_" + uuid4().hex[:16]
        with self._connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO outcomes
                (id, workflow_id, result, realised_value, currency, hours_spent, feedback, lessons_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (outcome_id, workflow_id, outcome.result, outcome.realisedValue, outcome.currency, outcome.hoursSpent, outcome.feedback, json.dumps(outcome.lessons), utcnow()),
            )
        return self.get_workflow(workflow_id)

    def benchmark(self, opportunities: list[Opportunity]) -> dict[str, Any]:
        count = len(opportunities)
        official = sum(item.sourceType == "official" for item in opportunities)
        versioned = sum(item.version >= 1 and bool(item.canonicalFingerprint) for item in opportunities)
        structured = sum(bool(item.requirements or item.eligibility or item.deliverables) for item in opportunities)
        attributed = sum(bool(item.sourceSnapshotIds) and bool(item.fieldProvenance) for item in opportunities)
        actionable = sum(item.independentlyActionable for item in opportunities)
        reviewed_or_high_confidence = sum(item.reviewStatus == "approved" or (item.normalizationConfidence >= 0.8 and item.completeness >= 0.8) for item in opportunities)
        denominator = max(count, 1)
        metrics = {
            "opportunityCount": count,
            "officialSourceRate": round(official / denominator, 3),
            "versionedRate": round(versioned / denominator, 3),
            "structuredRequirementRate": round(structured / denominator, 3),
            "fieldAttributionRate": round(attributed / denominator, 3),
            "actionableUnitRate": round(actionable / denominator, 3),
            "reviewedOrHighConfidenceRate": round(reviewed_or_high_confidence / denominator, 3),
            "averageCompleteness": round(sum(item.completeness for item in opportunities) / denominator, 3),
            "averageNormalizationConfidence": round(sum(item.normalizationConfidence for item in opportunities) / denominator, 3),
        }
        thresholds = {
            "opportunityCount": count >= 30,
            "officialSourceRate": metrics["officialSourceRate"] >= 0.8,
            "versionedRate": metrics["versionedRate"] >= 0.95,
            "structuredRequirementRate": metrics["structuredRequirementRate"] >= 0.9,
            "fieldAttributionRate": metrics["fieldAttributionRate"] >= 0.9,
            "actionableUnitRate": metrics["actionableUnitRate"] >= 0.95,
            "reviewedOrHighConfidenceRate": metrics["reviewedOrHighConfidenceRate"] >= 0.9,
            "averageCompleteness": metrics["averageCompleteness"] >= 0.8,
            "averageNormalizationConfidence": metrics["averageNormalizationConfidence"] >= 0.8,
        }
        passed = all(thresholds.values())
        run_id = "benchmark_" + uuid4().hex[:16]
        with self._connect() as db:
            db.execute(
                "INSERT INTO benchmark_runs VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, sha256_digest([item.model_dump(mode="json") for item in opportunities]), count, json.dumps({"metrics": metrics, "thresholds": thresholds}), int(passed), utcnow()),
            )
        return {"id": run_id, "passed": passed, "metrics": metrics, "thresholds": thresholds}

    def readiness(self, opportunities: list[Opportunity], payment_ready: bool, deployment_ready: bool) -> dict[str, Any]:
        benchmark = self.benchmark(opportunities)
        compiler = 10.0 * sum(benchmark["thresholds"].values()) / len(benchmark["thresholds"])
        dossier_quality = 10.0 * (benchmark["metrics"]["averageCompleteness"] + benchmark["metrics"]["averageNormalizationConfidence"]) / 2
        evidence = 9.5 if self._table_count("decision_assessments") > 0 else 7.5
        workflow = 9.5 if self._table_count("workflows") > 0 else 8.0
        learning = 9.5 if self._table_count("outcomes") >= 3 else min(8.5, 4.0 + self._table_count("outcomes") * 1.5)
        operations = 9.5 if payment_ready and deployment_ready else (8.5 if deployment_ready else 6.5)
        categories = {
            "compiler": round(compiler, 2),
            "dossierQuality": round(dossier_quality, 2),
            "evidenceReasoning": evidence,
            "decisionIntelligence": evidence,
            "executionWorkflow": workflow,
            "learningLoop": learning,
            "operations": operations,
        }
        overall = round(sum(categories.values()) / len(categories), 2)
        blockers: list[str] = []
        if not benchmark["passed"]:
            blockers.append("The 30-opportunity quality benchmark has not passed.")
        if not payment_ready:
            blockers.append("Production x402 payment and independent settlement proof are incomplete.")
        if not deployment_ready:
            blockers.append("The current completion branch has not been deployed and externally verified.")
        if self._table_count("outcomes") < 3:
            blockers.append("Outcome learning has fewer than three completed opportunity results.")
        return {"overall": overall, "target": 9.5, "targetReached": overall >= 9.5 and not blockers, "categories": categories, "blockers": blockers, "benchmark": benchmark}

    def _table_count(self, table: str) -> int:
        with self._connect() as db:
            return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
