from pathlib import Path

from app.config import Settings
from app.readiness import benchmark_corpus, benchmark_report, build_readiness
from app.store import JsonStore
from app.vision import VisionEngine


def test_benchmark_corpus_covers_thirty_structured_actionable_dossiers():
    corpus = benchmark_corpus()
    assert len(corpus) == 30
    assert len({item.type for item in corpus}) == 10
    assert all(item.independentlyActionable for item in corpus)
    assert all(item.sourceSnapshotIds for item in corpus)
    assert all(item.eligibility and item.requirements and item.deliverables for item in corpus)
    assert all(item.fieldProvenance for item in corpus)
    assert all(item.sourceType == "fixture" for item in corpus)


def test_benchmark_report_is_truthfully_labelled():
    report = benchmark_report()
    assert report["passed"] is True
    assert report["score"] == 10.0
    assert report["caseCount"] == 30
    assert "not represented as issuer-verified" in report["truth"]


def test_build_gate_reaches_target_without_faking_operational_proof(tmp_path: Path):
    store = JsonStore(Settings(environment="test", data_dir=tmp_path, public_base_url="http://testserver", payment_mode="free"))
    report = build_readiness(store, VisionEngine(store.db_path))
    assert report["buildScore"] >= 9.5
    assert report["buildReady"] is True
    assert report["operationalReady"] is False
    assert report["operationalScore"] == 0.0
    assert report["externalGates"]["aspRegistration"] is False
    assert report["externalGates"]["paidSettlement"] is False
