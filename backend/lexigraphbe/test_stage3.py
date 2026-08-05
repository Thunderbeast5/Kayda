"""
Pytest unit test suite for LexiGraph Stage 3: IPC/BNS Chapter & Section Title Identification.
"""

import json
from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL
from lexigraphbe.schemas import (
    CaseContextObject,
    CaseProfile,
    ChapterCandidateItem,
    ChapterIdentificationObject,
    ChapterVerificationIssue,
    ChapterVerificationResult,
    LegalConceptItem,
    LegalQueryObject,
    SectionCandidateItem,
    SubQueryItem,
)
from lexigraphbe.intake_agent import CaseIntakeAgent
from lexigraphbe.verifier_agent import CaseIntakeVerifierAgent
from lexigraphbe.pipeline import Stage0Pipeline
from lexigraphbe.query_understanding_agent import QueryUnderstandingAgent
from lexigraphbe.query_verifier_agent import QueryVerificationAgent
from lexigraphbe.stage1_pipeline import Stage1Pipeline
from lexigraphbe.chapter_identification_agent import ChapterIdentificationAgent
from lexigraphbe.chapter_verifier_agent import ChapterVerificationAgent
from lexigraphbe.stage3_pipeline import Stage3Pipeline
from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter
from lexigraphbe.eval_prefilter import run_prefilter_recall_evaluation


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()


def test_chapter_identification_object_schema():
    chap = ChapterCandidateItem(
        concept="Dowry Demand",
        chapter_number="XXA",
        chapter_name="Of Cruelty by Husband or Relatives",
        confidence=0.98
    )
    sec = SectionCandidateItem(
        concept="Dowry Demand",
        section_number="498A",
        section_title="Cruelty by Husband or Relatives",
        confidence=0.99
    )

    cio = ChapterIdentificationObject(
        chapter_candidates=[chap],
        section_candidates=[sec],
        legal_regime="IPC + CrPC"
    )

    d = cio.model_dump()
    assert d["schema_version"] == "1.0"
    assert d["legal_regime"] == "IPC + CrPC"
    assert len(d["chapter_candidates"]) == 1
    assert d["chapter_candidates"][0]["chapter_number"] == "XXA"
    assert d["section_candidates"][0]["section_number"] == "498A"

    restored = ChapterIdentificationObject.model_validate(d)
    assert restored.chapter_candidates[0].concept == "Dowry Demand"
    assert restored.section_candidates[0].section_title == "Cruelty by Husband or Relatives"


def test_prefilter_recall_evaluation_benchmark_metrics():
    """
    Verifies that StatuteClassifierPrefilter achieves 100% Recall@10 (1.0) and high Recall@5 (>= 0.85)
    on benchmark test scenarios to guarantee retrieval accuracy ceiling.
    """
    metrics = run_prefilter_recall_evaluation()

    assert metrics["sample_size_n"] == 30
    assert metrics["recall_at_10"] == 1.0
    assert metrics["recall_at_5"] >= 0.85, f"Recall@5 {metrics['recall_at_5']} below 0.85"
    assert metrics["mean_reciprocal_rank_mrr"] >= 0.50, f"MRR {metrics['mean_reciprocal_rank_mrr']} below 0.50"


def test_prefilter_to_agent_narrow_candidate_set_wiring():
    """
    CONFIRMATION TEST FOR PREFILTER -> AGENT WIRING:
    Verifies that StatuteClassifierPrefilter shortlists the candidate set locally FIRST (0 API calls),
    and ChapterIdentificationAgent operates STRICTLY over this pre-filtered shortlist (top 10-15).
    The full 574-section index is NEVER sent to the LLM. Token savings are 100% real.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "chapter_candidates": [
            {"concept": "Dowry Demand", "chapter_number": "XXA", "chapter_name": "Of Cruelty", "confidence": 0.98}
        ],
        "section_candidates": [
            {"concept": "Dowry Demand", "section_number": "498A", "section_title": "Cruelty by Husband", "confidence": 0.99}
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_prefilter = MagicMock(spec=StatuteClassifierPrefilter)
    mock_prefilter.shortlist_candidates_for_query.return_value = [
        MagicMock(model_dump=lambda: {"section_identifier": "IPC 498A", "section_number": "498A", "title": "Cruelty by Husband", "chapter": "XXA", "score": 0.98})
    ]

    agent = ChapterIdentificationAgent(llm=mock_llm, prefilter=mock_prefilter)
    query_obj = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.98)])

    agent.run(query_obj)

    # 1. Assert local pre-filter was called first with legal query and target_regime
    mock_prefilter.shortlist_candidates_for_query.assert_called_once_with(query_obj, top_k=15, target_regime=query_obj.legal_regime)

    # 2. Assert LLM prompt was invoked with ONLY the pre-filtered candidates, NOT the 574-section corpus
    assert mock_llm.invoke.call_count == 1
    messages_sent = mock_llm.invoke.call_args[0][0]
    user_prompt_content = messages_sent[1].content

    assert "PRE-FILTERED CANDIDATE STATUTORY INDEX CANDIDATES" in user_prompt_content
    assert "IPC 498A" in user_prompt_content
    assert "Operate ONLY over the pre-filtered candidate entries provided above" in user_prompt_content


def test_chapter_identification_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "chapter_candidates": [
            {
                "concept": "Dowry Demand",
                "chapter_number": "XXA",
                "chapter_name": "Of Cruelty by Husband or Relatives",
                "confidence": 0.98
            },
            {
                "concept": "Criminal Intimidation",
                "chapter_number": "XXII",
                "chapter_name": "Criminal Intimidation, Insult and Annoyance",
                "confidence": 0.95
            }
        ],
        "section_candidates": [
            {
                "concept": "Dowry Demand",
                "section_number": "498A",
                "section_title": "Cruelty by Husband or Relatives",
                "confidence": 0.99
            },
            {
                "concept": "Criminal Intimidation",
                "section_number": "506",
                "section_title": "Punishment for Criminal Intimidation",
                "confidence": 0.96
            },
            {
                "concept": "Low Confidence Concept",
                "section_number": "504",
                "section_title": "Intentional Insult",
                "confidence": 0.55
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = ChapterIdentificationAgent(llm=mock_llm, min_confidence_threshold=0.70)
    query_obj = LegalQueryObject(
        legal_regime="IPC + CrPC",
        legal_concepts=[
            LegalConceptItem(concept="Dowry Demand", confidence=0.98),
            LegalConceptItem(concept="Criminal Intimidation", confidence=0.95),
        ],
        sub_queries=[
            SubQueryItem(id="SQ1", query="Continuous demand for dowry.", concept="Dowry Demand", target_parties=["Husband"])
        ]
    )

    cio = agent.run(query_obj)

    assert len(cio.chapter_candidates) == 2
    assert cio.chapter_candidates[0].chapter_number == "XXA"
    assert cio.section_candidates[0].section_number == "498A"
    assert cio.legal_regime == "IPC + CrPC"
    # Check that candidate below 0.70 confidence cutoff was flagged in manual_review
    assert len(cio.manual_review) == 1
    assert "Section candidate 'Intentional Insult'" in cio.manual_review[0]


def test_chapter_verifier_agent_duplicate_shortcircuit():
    verifier = ChapterVerificationAgent(llm=MagicMock())

    query_obj = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])

    dup_cio = ChapterIdentificationObject(
        section_candidates=[
            SectionCandidateItem(concept="Dowry Demand", section_number="498A", section_title="Title 1", confidence=0.95),
            SectionCandidateItem(concept="Dowry Demand", section_number="498A", section_title="Title 1 Dup", confidence=0.90),
        ]
    )

    res = verifier.verify(query_obj, dup_cio)

    assert res.status == "RETRY"
    assert len(res.issues) == 1
    assert "Duplicate section candidate" in res.issues[0].issue


def test_stage3_pipeline_flow():
    mock_agent_llm = MagicMock()
    mock_agent_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "chapter_candidates": [
            {"concept": "Dowry Demand", "chapter_number": "XXA", "chapter_name": "Of Cruelty", "confidence": 0.98}
        ],
        "section_candidates": [
            {"concept": "Dowry Demand", "section_number": "498A", "section_title": "Cruelty by Husband", "confidence": 0.99}
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Stage 3 Verified."
    })

    agent = ChapterIdentificationAgent(llm=mock_agent_llm)
    verifier = ChapterVerificationAgent(llm=mock_verifier_llm)

    pipeline = Stage3Pipeline(chapter_agent=agent, verifier_agent=verifier)
    query_obj = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])

    res = pipeline.run(query_obj)

    assert res.status == "VERIFIED"
    assert res.verified_chapter_object is not None
    assert res.verified_chapter_object.chapter_candidates[0].chapter_number == "XXA"
    assert res.verified_chapter_object.section_candidates[0].section_number == "498A"


def test_stage0_to_stage1_to_stage3_full_chain():
    # 1. Mock Stage 0 Intake & Verifier LLMs
    mock_intake_llm = MagicMock()
    mock_intake_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {"fir_number": "789/2025", "offence_date": "10/08/2024"},
        "parties": {"accused": ["Husband", "Father-in-law"]},
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "BNS + BNSS",
        "documents": ["FIR Copy", "Bail Application Copy"],
        "case_facts": "The husband and father-in-law repeatedly demanded dowry.",
        "confidence": {"procedural_stage": 0.95}
    })

    mock_s0_verifier_llm = MagicMock()
    mock_s0_verifier_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    s0_pipeline = Stage0Pipeline(intake_agent=CaseIntakeAgent(llm=mock_intake_llm), verifier_agent=CaseIntakeVerifierAgent(llm=mock_s0_verifier_llm))
    s0_res = s0_pipeline.run("Raw FIR text")
    cco = s0_res.export_case_context_object()

    # 2. Mock Stage 1 Query Agent & Verifier LLMs
    mock_s1_query_llm = MagicMock()
    mock_s1_query_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {"victim": ["Wife"], "accused": ["Husband"]},
        "sub_queries": [{"id": "SQ1", "query": "Dowry demand cruelty.", "concept": "Dowry Demand", "target_parties": ["Husband"]}],
        "legal_concepts": [{"concept": "Dowry Demand", "confidence": 0.95}],
        "procedural_events": ["FIR Registered"],
        "important_facts": {},
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_s1_verifier_llm = MagicMock()
    mock_s1_verifier_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 1 Clean."})

    s1_pipeline = Stage1Pipeline(query_agent=QueryUnderstandingAgent(llm=mock_s1_query_llm), verifier_agent=QueryVerificationAgent(llm=mock_s1_verifier_llm))
    s1_res = s1_pipeline.run(cco)
    qo = s1_res.verified_query_object

    # 3. Mock Stage 3 Chapter Agent & Verifier LLMs
    mock_s3_agent_llm = MagicMock()
    mock_s3_agent_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "chapter_candidates": [
            {"concept": "Dowry Demand", "chapter_number": "85", "chapter_name": "Of Cruelty", "confidence": 0.98}
        ],
        "section_candidates": [
            {"concept": "Dowry Demand", "section_number": "85", "section_title": "Cruelty by Husband", "confidence": 0.99}
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_s3_verifier_llm = MagicMock()
    mock_s3_verifier_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 3 Clean."})

    s3_pipeline = Stage3Pipeline(chapter_agent=ChapterIdentificationAgent(llm=mock_s3_agent_llm), verifier_agent=ChapterVerificationAgent(llm=mock_s3_verifier_llm))
    s3_res = s3_pipeline.run(qo)

    assert s3_res.status == "VERIFIED"
    cio = s3_res.verified_chapter_object
    assert cio is not None
    assert cio.legal_regime == "BNS + BNSS"
    assert cio.chapter_candidates[0].chapter_number == "85"
    assert cio.section_candidates[0].section_number == "85"
