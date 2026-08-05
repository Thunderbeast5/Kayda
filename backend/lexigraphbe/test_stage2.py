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


def test_stage2_factual_trigger_detection_and_multi_offence_mapping():
    """
    Verifies that StatuteClassifierPrefilter detects factual triggers (dowry cruelty, DP Act, stridhan, threats, hurt)
    and proposes multi-offence Primary and Secondary candidates.
    """
    from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter

    facts = "Husband and family continuously demanded dowry, retained stridhan gold, threatened wife, and slapped her."
    triggers = StatuteClassifierPrefilter.detect_factual_triggers(facts, statute_type="IPC")

    sec_nums = [t["section_number"] for t in triggers]
    assert "498A" in sec_nums
    assert "Section 4" in sec_nums
    assert "406" in sec_nums
    assert "506" in sec_nums
    assert "323" in sec_nums


def test_stage2_knowledge_base_rules_and_not_triggered_screening():
    """
    Verifies that StatuteClassifierPrefilter.evaluate_fatal_disqualification leverages STATUTE_KNOWLEDGE_BASE
    to screen non-triggered sections like Section 304B (Dowry Death) when death is absent.
    """
    from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter, STATUTE_KNOWLEDGE_BASE

    assert len(STATUTE_KNOWLEDGE_BASE) >= 8

    facts_no_death = "Continuous dowry demand and mental cruelty by husband and in-laws."
    not_triggered, reason, missing_mands = StatuteClassifierPrefilter.evaluate_fatal_disqualification("304B", "IPC", facts_no_death)
    assert not_triggered is True
    assert "Screening non-trigger" in reason
    assert "death_of_woman" in missing_mands

    facts_with_death = "Wife found dead under suspicious circumstances following dowry harassment."
    not_triggered2, reason2, missing2 = StatuteClassifierPrefilter.evaluate_fatal_disqualification("304B", "IPC", facts_with_death)
    assert not_triggered2 is False
    assert reason2 is None
    assert missing2 == []


def test_stage2_missing_facts_and_not_triggered_sections():
    """
    Verifies that SectionMappingCandidate supports missing_facts array and
    SubQueryChapterMapping supports not_triggered_sections array with backward compatibility.
    """
    from lexigraphbe.batch_utils import NotTriggeredSectionItem, SectionMappingCandidate, SubQueryChapterMapping

    primary_item = SectionMappingCandidate(
        section_number="498A",
        section_title="Cruelty by Husband",
        candidate_type="PRIMARY",
        score=0.94,
        ingredients_matched=["Marriage", "Dowry demand", "Harassment"],
        missing_facts=[],
        relevance_reasoning="Direct legal nexus: Marriage + Dowry demand + Cruelty"
    )

    secondary_item = SectionMappingCandidate(
        section_number="406",
        section_title="Criminal Breach of Trust",
        candidate_type="SECONDARY",
        score=0.76,
        ingredients_matched=["Entrustment of stridhan property"],
        missing_facts=["Entrustment of specific stridhan articles", "Refusal to return stridhan on demand"],
        relevance_reasoning="Secondary legal nexus: Ancillary offence regarding stridhan retention"
    )

    not_triggered_item = NotTriggeredSectionItem(
        section_number="304B",
        section_title="Dowry Death",
        not_triggered_reason="Screening non-trigger: Section 304B requires death of woman. No death reported in case facts.",
        missing_mandatory_ingredients=["death_of_woman", "within_7_years_of_marriage"]
    )

    mapping = SubQueryChapterMapping(
        sub_query_id="SQ1",
        sub_query_text="Dowry demand and threats",
        primary_candidate_sections=[primary_item],
        secondary_candidate_sections=[secondary_item],
        not_triggered_sections=[not_triggered_item],
    )

    assert len(mapping.primary_candidate_sections) == 1
    assert mapping.primary_candidate_sections[0].missing_facts == []
    assert len(mapping.secondary_candidate_sections) == 1
    assert "Entrustment of specific stridhan articles" in mapping.secondary_candidate_sections[0].missing_facts
    assert len(mapping.not_triggered_sections) == 1
    assert mapping.not_triggered_sections[0].section_number == "304B"

    # Backward compatibility properties
    assert mapping.rejected_sections[0].section_number == "304B"
    assert mapping.rejected_sections[0].rejection_reason == "Screening non-trigger: Section 304B requires death of woman. No death reported in case facts."
    assert mapping.candidate_sections == ["498A", "406"]

