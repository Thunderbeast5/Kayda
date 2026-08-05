"""
Pytest unit test suite for LexiGraph Stage 2: Sub-Query to Chapter Candidate Batched Mapping.
"""

import json
from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL
from lexigraphbe.schemas import (
    CaseContextObject,
    CaseProfile,
    LegalConceptItem,
    LegalQueryObject,
    Stage2VerificationIssue,
    Stage2VerificationResult,
    SubQueryItem,
)
from lexigraphbe.batch_utils import Stage2BatchedMappingResponse, SubQueryChapterMapping
from lexigraphbe.stage2_mapping_agent import Stage2SubQueryMappingAgent
from lexigraphbe.stage2_verifier_agent import Stage2MappingVerifierAgent
from lexigraphbe.stage2_pipeline import Stage2Pipeline
from lexigraphbe.intake_agent import CaseIntakeAgent
from lexigraphbe.verifier_agent import CaseIntakeVerifierAgent
from lexigraphbe.pipeline import Stage0Pipeline
from lexigraphbe.query_understanding_agent import QueryUnderstandingAgent
from lexigraphbe.query_verifier_agent import QueryVerificationAgent
from lexigraphbe.stage1_pipeline import Stage1Pipeline


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()


def test_stage2_batched_mapping_schema():
    m1 = SubQueryChapterMapping(
        sub_query_id="SQ1",
        sub_query_text="Harassment for dowry demand.",
        target_parties=["Husband"],
        candidate_chapters=["Of Cruelty by Husband or Relatives of Husband"],
        candidate_sections=["Section 498A - Cruelty by Husband or Relatives of Husband"],
        relevance_reasoning="Matrimonial cruelty mapped."
    )

    resp = Stage2BatchedMappingResponse(mappings=[m1])
    d = resp.model_dump()
    assert d["schema_version"] == "1.0"
    assert len(d["mappings"]) == 1
    assert d["mappings"][0]["sub_query_id"] == "SQ1"
    assert d["mappings"][0]["candidate_sections"][0] == "Section 498A - Cruelty by Husband or Relatives of Husband"

    restored = Stage2BatchedMappingResponse.model_validate(d)
    assert restored.mappings[0].target_parties == ["Husband"]


def test_stage2_mapping_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "mappings": [
            {
                "sub_query_id": "SQ1",
                "sub_query_text": "Dowry harassment",
                "target_parties": ["Husband"],
                "candidate_chapters": ["Of Cruelty"],
                "candidate_sections": ["498A"],
                "relevance_reasoning": "Matrimonial cruelty mapped."
            }
        ]
    })

    mock_prefilter = MagicMock()
    mock_prefilter.prefilter_candidates.return_value = []

    agent = Stage2SubQueryMappingAgent(llm=mock_llm, prefilter=mock_prefilter)
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])

    res = agent.run(qo)

    assert len(res.mappings) == 1
    assert res.mappings[0].sub_query_id == "SQ1"
    assert res.mappings[0].candidate_sections == ["498A"]


def test_stage2_verifier_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Stage 2 mapping audit cleanly passed."
    })

    verifier = Stage2MappingVerifierAgent(llm=mock_llm)
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    resp = Stage2BatchedMappingResponse(mappings=[
        SubQueryChapterMapping(
            sub_query_id="SQ1",
            sub_query_text="Text",
            target_parties=["Husband"],
            candidate_chapters=["Chap"],
            candidate_sections=["498A"],
            relevance_reasoning="Reason"
        )
    ])

    res = verifier.verify(qo, resp)

    assert res.status == "VERIFIED"
    assert res.batched_mapping_response is not None


def test_stage2_pipeline_flow():
    mock_agent_llm = MagicMock()
    mock_agent_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "mappings": [
            {
                "sub_query_id": "SQ1",
                "sub_query_text": "Text",
                "target_parties": ["Husband"],
                "candidate_chapters": ["Chap"],
                "candidate_sections": ["498A"],
                "relevance_reasoning": "Reason"
            }
        ]
    })

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    mock_prefilter = MagicMock()
    mock_prefilter.prefilter_candidates.return_value = []

    agent = Stage2SubQueryMappingAgent(llm=mock_agent_llm, prefilter=mock_prefilter)
    verifier = Stage2MappingVerifierAgent(llm=mock_verifier_llm)

    pipeline = Stage2Pipeline(mapping_agent=agent, verifier_agent=verifier)
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])

    res = pipeline.run(qo)

    assert res.status == "VERIFIED"
    assert res.batched_mapping_response is not None
    assert res.batched_mapping_response.mappings[0].sub_query_id == "SQ1"


def test_full_stage0_to_stage2_integration():
    mock_s0_intake = MagicMock()
    mock_s0_intake.invoke.return_value.content = json.dumps({
        "case_metadata": {"fir_number": "3003/2025", "offence_date": "10/08/2024"},
        "parties": {"accused": ["Husband"]},
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "IPC + CrPC",
        "documents": ["FIR Copy"],
        "case_facts": "Cruelty and dowry demand alleged.",
        "confidence": {"procedural_stage": 0.95}
    })
    mock_s0_verifier = MagicMock()
    mock_s0_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    s0_pipeline = Stage0Pipeline(intake_agent=CaseIntakeAgent(llm=mock_s0_intake), verifier_agent=CaseIntakeVerifierAgent(llm=mock_s0_verifier))
    s0_res = s0_pipeline.run("Raw FIR text")
    cco = s0_res.export_case_context_object()

    mock_s1_agent = MagicMock()
    mock_s1_agent.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {"victim": ["Wife"], "accused": ["Husband"]},
        "sub_queries": [{"id": "SQ1", "query": "Cruelty harassment.", "concept": "Dowry Cruelty", "target_parties": ["Husband"]}],
        "legal_concepts": [{"concept": "Dowry Cruelty", "confidence": 0.95}],
        "procedural_events": ["FIR Registered"],
        "important_facts": {},
        "manual_review": [],
        "verification_status": "PENDING"
    })
    mock_s1_verifier = MagicMock()
    mock_s1_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    s1_pipeline = Stage1Pipeline(query_agent=QueryUnderstandingAgent(llm=mock_s1_agent), verifier_agent=QueryVerificationAgent(llm=mock_s1_verifier))
    s1_res = s1_pipeline.run(cco)
    qo = s1_res.verified_query_object

    mock_s2_agent = MagicMock()
    mock_s2_agent.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "mappings": [
            {
                "sub_query_id": "SQ1",
                "sub_query_text": "Cruelty harassment.",
                "target_parties": ["Husband"],
                "candidate_chapters": ["Of Cruelty"],
                "candidate_sections": ["498A"],
                "relevance_reasoning": "Mapped to 498A."
            }
        ]
    })
    mock_s2_verifier = MagicMock()
    mock_s2_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 2 Verified."})

    mock_prefilter = MagicMock()
    mock_prefilter.prefilter_candidates.return_value = []

    s2_pipeline = Stage2Pipeline(mapping_agent=Stage2SubQueryMappingAgent(llm=mock_s2_agent, prefilter=mock_prefilter), verifier_agent=Stage2MappingVerifierAgent(llm=mock_s2_verifier))
    s2_res = s2_pipeline.run(qo)

    assert s2_res.status == "VERIFIED"
    resp = s2_res.batched_mapping_response
    assert resp is not None
    assert resp.mappings[0].candidate_sections == ["498A"]


def test_stage2_single_regime_sanitization():
    """
    CONFIRMATION TEST FOR FIX #4:
    Verifies that Stage 2 Agent post-processing cleans up accidental dual-regime slash citations
    (e.g., 'Section 498A IPC / Section 85 BNS') and returns ONLY the section belonging to the governing regime.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "mappings": [
            {
                "sub_query_id": "SQ1",
                "sub_query_text": "Dowry harassment",
                "target_parties": ["Husband"],
                "candidate_chapters": ["Of Cruelty"],
                "candidate_sections": ["Section 498A IPC / Section 85 BNS"],
                "relevance_reasoning": "Matrimonial cruelty mapped."
            }
        ]
    })

    mock_prefilter = MagicMock()
    mock_prefilter.prefilter_candidates.return_value = []

    # 1. Test IPC regime -> Returns 'Section 498A IPC'
    agent_ipc = Stage2SubQueryMappingAgent(llm=mock_llm, prefilter=mock_prefilter)
    qo_ipc = LegalQueryObject(legal_regime="IPC + CrPC", legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    res_ipc = agent_ipc.run(qo_ipc)

    assert len(res_ipc.mappings) == 1
    assert res_ipc.mappings[0].candidate_sections == ["Section 498A IPC"]

    # 2. Test BNS regime -> Returns 'Section 85 BNS'
    agent_bns = Stage2SubQueryMappingAgent(llm=mock_llm, prefilter=mock_prefilter)
    qo_bns = LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    res_bns = agent_bns.run(qo_bns)

    assert len(res_bns.mappings) == 1
    assert res_bns.mappings[0].candidate_sections == ["Section 85 BNS"]

