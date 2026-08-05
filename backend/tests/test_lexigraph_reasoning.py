import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agents.lexigraph.legal_reasoning.lg1 import (
    SectionCandidate,
    build_case_analysis_payload,
    evaluate_benchmark,
    score_graph_context,
)


def test_llm_config_import_is_safe_when_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    sys.modules.pop("backend.agents.config.llm_config", None)
    sys.modules.pop("agents.config.llm_config", None)

    from backend.agents.config import llm_config

    reloaded = importlib.reload(llm_config)
    assert reloaded.GROQ_API_KEY is None


def test_case_analysis_payload_has_flat_shape():
    candidate = SectionCandidate(
        law_id="IPC_380",
        act="IPC",
        section="380",
        title="Theft in a dwelling house",
        description="Theft committed in a dwelling house.",
    )
    payload = build_case_analysis_payload("House theft", [candidate])

    assert payload["user_query"] == "House theft"
    assert payload["sections"][0]["section"] == "380"
    assert "case_analysis" not in payload


def test_graph_context_scoring_prefers_rich_relationships():
    poor_candidate = SectionCandidate(law_id="IPC_379", act="IPC", section="379", title="Theft")
    rich_candidate = SectionCandidate(law_id="IPC_380", act="IPC", section="380", title="Theft in dwelling house")

    poor_candidate.graph_relationships = [{"type": "IPC_BNS_MAPPING", "targets": [{"id": "BNS_305"}]}]
    rich_candidate.graph_relationships = [
        {"type": "IPC_BNS_MAPPING", "targets": [{"id": "BNS_305"}]},
        {"type": "DEFINED_BY", "targets": [{"id": "Crime_theft"}]},
        {"type": "CO_CHARGED_WITH", "targets": [{"id": "IPC_392"}]},
        {"type": "LANDMARK_CASE", "targets": [{"id": "Case_abc"}]},
    ]

    poor_score = score_graph_context(poor_candidate)
    rich_score = score_graph_context(rich_candidate)

    assert rich_score > poor_score
    assert rich_score >= 0.2


def test_evaluate_benchmark_reports_precision_and_graph_coverage():
    cases = [
        {
            "id": "theft_001",
            "query": "house theft",
            "category": "Theft",
            "expected_sections": ["BNS 305", "BNS 331"],
            "expected_priority": ["BNS 305"],
            "retrieved": ["BNS 305", "BNS 331", "BNS 304", "IPC 380"],
            "graph_enriched": [True, True, False, False],
            "reasoning_confidence": [0.91, 0.86, 0.56, 0.41],
        }
    ]

    metrics = evaluate_benchmark(cases)

    assert metrics["precision_at_5"] == 0.4
    assert metrics["recall_at_5"] == 1.0
    assert metrics["graph_coverage"] == 0.5
    assert metrics["average_reasoning_confidence"] == 0.685


def test_evaluate_benchmark_supports_graded_relevance_and_reasoning_checks():
    cases = [
        {
            "id": "theft_002",
            "query": "my neighbour broke into my house and stole my TV",
            "category": "House Trespass",
            "expected_sections": [
                {"section": "BNS 305", "relevance": 3},
                {"section": "BNS 331", "relevance": 2},
                {"section": "BNS 303", "relevance": 1},
            ],
            "retrieved": ["BNS 305", "BNS 331", "BNS 303"],
            "vector_only_retrieved": ["BNS 303", "BNS 331"],
            "graph_rag_retrieved": ["BNS 305", "BNS 331", "BNS 303"],
            "graph_enriched": [True, True, True],
            "reasoning": [
                {
                    "section": "BNS 305",
                    "reason": "This fits the house-breaking facts.",
                    "supporting_facts": ["The accused entered the house"],
                    "missing_evidence": [],
                    "ambiguities": [],
                    "unsupported_facts": [],
                }
            ],
        }
    ]

    metrics = evaluate_benchmark(cases)

    assert metrics["ndcg"] > 0.0
    assert metrics["graph_improvement"]["ndcg"] > 0.0
    assert metrics["by_category"]["House Trespass"]["total_cases"] == 1
    assert metrics["reasoning_quality"]["structure_score"] == 1.0
    assert metrics["reasoning_quality"]["grounding_score"] == 1.0
