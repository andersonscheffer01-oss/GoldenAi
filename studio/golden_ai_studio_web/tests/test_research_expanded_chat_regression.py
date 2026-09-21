"""Focused regressions for research evidence selection and expanded chat wiring."""

import json
from pathlib import Path
from types import SimpleNamespace

from jarvis_core.memory.v2.research import (
    EvidenceRecord,
    KnowledgeCandidate,
    ResearchReport,
    SourceTrustLevel,
)
from jarvis_core.service import JarvisService


ROOT = Path(__file__).parents[1]
UI = ROOT / "jarvis_ui"


def _evidence(url, trust, timestamp, quote):
    return EvidenceRecord(
        url=url,
        title=url,
        source_type="web",
        timestamp=timestamp,
        domain=url.split("/")[2],
        trust=trust,
        confidence={"A": 0.9, "E": 0.42}[trust.value],
        basis="official_primary_source" if trust == SourceTrustLevel.A else "isolated_hypothesis",
        quote=quote,
    )


def _service_for_report(report):
    provider = SimpleNamespace(status=lambda: {"providers": {}, "fallback_count": 0})
    learning = SimpleNamespace(research_candidates=lambda *args, **kwargs: report)
    return SimpleNamespace(
        learning_engine=learning,
        research_provider=provider,
    )


def test_official_source_wins_over_repeated_secondary_chunks():
    official = _evidence("https://official.example.com/versions", SourceTrustLevel.A, 200, "current stable 9.0")
    secondary = [_evidence("https://blog.example.com/python", SourceTrustLevel.E, 300, f"historical chunk {i}") for i in range(8)]
    candidates = [KnowledgeCandidate(claim=e.quote, evidences=[e], trust=e.trust, confidence=e.confidence) for e in [*secondary, official]]
    report = ResearchReport(query="versao atual", candidates=candidates, evidences=[official, *secondary], pages_fetched=2, results_count=2)
    result = JarvisService._run_web_research(_service_for_report(report), "versao atual", limit=5)
    records = result["evidence_records"]
    assert records[0]["source"]["trust"] == "A"
    assert sum(item["source"]["url"] == official.url for item in records) <= 2


def test_same_url_is_one_logical_source_with_best_chunks():
    records = [_evidence("https://official.example.com/versions", SourceTrustLevel.A, 100 + i, f"chunk {i}") for i in range(5)]
    candidates = [KnowledgeCandidate(claim=e.quote, evidences=[e], trust=e.trust, confidence=e.confidence) for e in records]
    report = ResearchReport(query="latest version", candidates=candidates, evidences=records, pages_fetched=1, results_count=1)
    result = JarvisService._run_web_research(_service_for_report(report), "latest version", limit=5)
    selected = [item for item in result["evidence_records"] if item["source"]["url"] == records[0].url]
    assert len(selected) == 2
    assert {item["quote"] for item in selected} == {"chunk 3", "chunk 4"}


def test_current_query_prefers_newer_evidence_when_trust_is_equal():
    old = _evidence("https://official.example.com/versions", SourceTrustLevel.A, 100, "stable 8.0")
    new = _evidence("https://official.example.com/versions", SourceTrustLevel.A, 200, "stable 9.0")
    candidates = [KnowledgeCandidate(claim=e.quote, evidences=[e], trust=e.trust, confidence=e.confidence) for e in [old, new]]
    report = ResearchReport(query="current latest version", candidates=candidates, evidences=[old, new], pages_fetched=1, results_count=1)
    result = JarvisService._run_web_research(_service_for_report(report), "current latest version", limit=5)
    assert result["evidence_records"][0]["quote"] == "stable 9.0"


def test_expanded_chat_reuses_existing_dom_and_transport():
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    golden = (UI / "src" / "golden.js").read_text(encoding="utf-8")
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert 'id="chatExpandedHistory"' in html
    assert 'id="chatExpandedInput"' in html
    assert 'el.expandedHistory.appendChild(el.chatSlot.querySelector("#conversation"))' in golden
    assert 'el.expandedInput.appendChild(input)' in golden
    assert golden.count("new WebSocket") == 0
    assert 'new CustomEvent("jarvis:message-added"' in app


def test_cache_bust_covers_modified_ui_assets():
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    for asset in ("styles.css?v=", "markdown-sanitizer.js?v=", "app.js?v="):
        assert asset in html
    for asset in ("brain.js?v=", "golden.js?v=", "search.js?v="):
        assert asset in app
