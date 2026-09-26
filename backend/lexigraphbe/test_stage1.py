"""
Pytest unit test suite for LexiGraph Stage 1: Query Understanding & Legal Decomposition.
"""

import json
from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL, MODEL_TIER_CHEAP, MODEL_TIER_REASONING, get_llm_for_tier


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()
from lexigraphbe.schemas import (
    CaseContextObject,
    CaseProfile,
    ImportantFacts,
    LegalConceptItem,
    LegalQueryObject,
    Parties,
    SubQueryItem,
)
from lexigraphbe.batch_utils import (
    SubQueryChapterMapping,
    Stage2BatchedMappingResponse,
    SectionIngredientEvaluation,
    Stage5BatchedIngredientResponse,
)
from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter, CandidateSectionMatch
from lexigraphbe.intake_agent import CaseIntakeAgent
from lexigraphbe.verifier_agent import CaseIntakeVerifierAgent
from lexigraphbe.query_understanding_agent import QueryUnderstandingAgent
from lexigraphbe.query_verifier_agent import QueryVerificationAgent
from lexigraphbe.stage1_pipeline import Stage1Pipeline
from lexigraphbe.section_matcher import ClosedSetSectionAuditor


def test_legal_query_object_schema():
    qo = LegalQueryObject(
        case_type="Anticipatory Bail",
        entities={"victim": ["Wife"], "accused": ["Husband"]},
        relationship=["Husband-Wife"],
        legal_concepts=[
            LegalConceptItem(concept="Dowry Demand", confidence=0.98),
            LegalConceptItem(concept="Mental Cruelty", confidence=0.92),
        ],
        sub_queries=[
            SubQueryItem(
                id="SQ1",
                query="Continuous demand for dowry by husband.",
                concept="Dowry Demand",
                target_parties=["Husband"],
                role_alleged="Main Accused / Direct Demand"
            ),
            SubQueryItem(
                id="SQ2",
                query="Threats and harassment after marriage.",
                concept="Mental Cruelty",
                target_parties=["Husband"],
                role_alleged="Main Accused"
            ),
        ],
        procedural_events=["Marriage", "FIR Registered"],
        important_facts=ImportantFacts(money="₹5,00,000", location="Nashik"),
        legal_regime="IPC + CrPC",
        flag_for_confirmation=False,
    )

    d = qo.model_dump()
    assert d["schema_version"] == "1.0"
    assert d["case_type"] == "Anticipatory Bail"
    assert d["legal_regime"] == "IPC + CrPC"
    assert len(d["sub_queries"]) == 2
    assert d["sub_queries"][0]["id"] == "SQ1"
    assert d["sub_queries"][0]["target_parties"] == ["Husband"]

    restored = LegalQueryObject.model_validate(d)
    assert restored.legal_concepts[0].concept == "Dowry Demand"
    assert restored.sub_queries[0].target_parties == ["Husband"]
    assert restored.legal_regime == "IPC + CrPC"


def test_task_based_model_tiering_routing():
    """
    Verifies that task-based model tiering routes simple extraction/verification tasks
    to MODEL_TIER_CHEAP and complex legal reasoning tasks to MODEL_TIER_REASONING.
    """
    # Test agent default tier bindings
    intake = CaseIntakeAgent(llm=MagicMock())
    intake_verifier = CaseIntakeVerifierAgent(llm=MagicMock())
    query_agent = QueryUnderstandingAgent(llm=MagicMock())
    query_verifier = QueryVerificationAgent(llm=MagicMock())

    assert intake.llm is not None
    assert query_agent.llm is not None

    assert MODEL_TIER_CHEAP == "cheap"
    assert MODEL_TIER_REASONING == "reasoning"


def test_statute_classifier_prefilter_local_execution():
    """
    Verifies that StatuteClassifierPrefilter executes 100% locally in Python
    with 0 LLM API calls, shortlisting candidate sections (top 5-10) for downstream LLM reasoning.
    """
    prefilter = StatuteClassifierPrefilter()

    qo = LegalQueryObject(
        legal_regime="IPC + CrPC",
        legal_concepts=[
            LegalConceptItem(concept="Dowry Demand", confidence=0.98),
            LegalConceptItem(concept="Mental Cruelty", confidence=0.95),
        ],
        sub_queries=[
            SubQueryItem(
                id="SQ1",
                query="Continuous demand for dowry and physical assault.",
                concept="Dowry Demand",
                target_parties=["Husband"]
            )
        ]
    )

    candidates = prefilter.shortlist_candidates_for_query(qo, top_k=5)

    # Assert local pre-filtering returned candidate matches with 0 API calls
    assert isinstance(candidates, list)
    assert len(candidates) > 0
    assert any("498" in c.section_number or "304" in c.section_number or "323" in c.section_number or "IPC" in c.statute for c in candidates)
    assert candidates[0].score > 0.0


def test_batched_schemas_and_single_call_response_validation():
    """
    Verifies that Stage 2 and Stage 5 single-call batched response models
    (Stage2BatchedMappingResponse and Stage5BatchedIngredientResponse)
    validate correctly without multiplicative O(N x M) LLM call loops.
    """
    # 1. Test Stage 2 Batched Single-Call Response Schema
    s2_batch = Stage2BatchedMappingResponse(
        mappings=[
            SubQueryChapterMapping(
                sub_query_id="SQ1",
                sub_query_text="Continuous demand for cash dowry.",
                target_parties=["Husband"],
                candidate_chapters=["Chapter XXA: Of Cruelty by Husband or Relatives of Husband"],
                candidate_sections=["IPC 498A", "BNS 85"],
                relevance_reasoning="Direct dowry demand cruelty alignment."
            ),
            SubQueryChapterMapping(
                sub_query_id="SQ2",
                sub_query_text="Incitement for car dowry by father-in-law.",
                target_parties=["Father-in-law"],
                candidate_chapters=["Chapter XXA: Of Cruelty"],
                candidate_sections=["IPC 498A", "IPC 109", "BNS 85", "BNS 45"],
                relevance_reasoning="Abetment of dowry demand."
            )
        ]
    )

    s2_dict = s2_batch.model_dump()
    assert len(s2_dict["mappings"]) == 2
    assert s2_dict["mappings"][0]["sub_query_id"] == "SQ1"
    assert s2_dict["mappings"][1]["target_parties"] == ["Father-in-law"]

    # 2. Test Stage 5 Batched Single-Call Response Schema
    s5_batch = Stage5BatchedIngredientResponse(
        evaluations=[
            SectionIngredientEvaluation(
                section_identifier="IPC 498A",
                section_title="Husband or relative of husband subjecting woman to cruelty",
                ingredients_present=["Subjected woman to cruelty", "Demand for dowry"],
                ingredients_missing=[],
                target_parties=["Husband", "Father-in-law"],
                applicability_score=0.98,
                bail_relevance_summary="High relevance for dowry demand allegation."
            )
        ]
    )

    s5_dict = s5_batch.model_dump()
    assert len(s5_dict["evaluations"]) == 1
    assert s5_dict["evaluations"][0]["applicability_score"] == 0.98


def test_stage0_legal_regime_passthrough_unchanged():
    """
    Verifies that legal_regime ('IPC + CrPC' or 'BNS + BNSS'), flag_for_confirmation,
    and regime_notes pass through from Stage 0 CaseContextObject into LegalQueryObject
    completely unchanged and are never re-derived.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {"victim": ["Wife"], "accused": ["Husband"]},
        "sub_queries": [
            {
                "id": "SQ1",
                "query": "Demand for cash dowry.",
                "concept": "Dowry Demand",
                "target_parties": ["Husband"]
            }
        ]
    })

    agent = QueryUnderstandingAgent(llm=mock_llm)

    profile_ipc = CaseProfile(
        legal_regime="IPC + CrPC",
        flag_for_confirmation=True,
        regime_notes="Offence committed pre-July 1, 2024 controls."
    )

    qo = agent.run(profile_ipc)

    # Assert exact passthrough without re-derivation
    assert qo.legal_regime == "IPC + CrPC"
    assert qo.flag_for_confirmation is True
    assert qo.regime_notes == "Offence committed pre-July 1, 2024 controls."


def test_multi_party_accused_subquery_attribution_mapping():
    """
    Verifies that multi-party accused cases (Husband + Father-in-law + Mother-in-law)
    correctly map distinct sub-queries per target party (target_parties & role_alleged)
    so individual bail arguments can be generated without flattening.
    """
    sq_husband = SubQueryItem(
        id="SQ1",
        query="Continuous direct demand for cash dowry and physical assault by husband.",
        concept="Dowry Demand",
        target_parties=["Husband"],
        role_alleged="Main Accused / Direct Physical Assault"
    )

    sq_father_in_law = SubQueryItem(
        id="SQ2",
        query="Incitement and demand for car dowry by father-in-law.",
        concept="Abetment of Cruelty",
        target_parties=["Father-in-law"],
        role_alleged="Co-Accused / Abetment & Financial Demand"
    )

    sq_mother_in_law = SubQueryItem(
        id="SQ3",
        query="Verbal abuse and taunting by mother-in-law.",
        concept="Mental Cruelty",
        target_parties=["Mother-in-law"],
        role_alleged="Co-Accused / Verbal Harassment"
    )

    qo = LegalQueryObject(
        case_type="Anticipatory Bail",
        entities={"victim": ["Wife"], "accused": ["Husband", "Father-in-law", "Mother-in-law"]},
        sub_queries=[sq_husband, sq_father_in_law, sq_mother_in_law]
    )

    # Assert distinct target_parties preserved per sub-query
    assert qo.sub_queries[0].target_parties == ["Husband"]
    assert qo.sub_queries[1].target_parties == ["Father-in-law"]
    assert qo.sub_queries[2].target_parties == ["Mother-in-law"]

    assert "Direct Physical Assault" in qo.sub_queries[0].role_alleged
    assert "Abetment" in qo.sub_queries[1].role_alleged
    assert "Verbal Harassment" in qo.sub_queries[2].role_alleged


def test_closed_set_section_auditor_variations_and_non_leaks():
    """
    Tests ClosedSetSectionAuditor against section format variations (Section 498A, 498-A, u/s 420, Sec. 34, IPC 406)
    and verifies zero false positives on FIR numbers, dates, monetary amounts, and paragraph references.
    """
    auditor = ClosedSetSectionAuditor()

    # 1. Format variations of section leaks -> MUST BE DETECTED
    leak_examples = [
        "Allegation of cruelty under Section 498A IPC.",
        "Cruelty alleged under 498-A IPC by in-laws.",
        "Cheating committed u/s 420 of IPC.",
        "Acts committed with common intention Sec. 34.",
        "Criminal breach of trust under IPC 406.",
        "Offence punishable under Section 304B.",
        "Offence of murder under Section 302 IPC.",
    ]

    for text in leak_examples:
        leaks = auditor.audit_text_for_leaks(text)
        assert len(leaks) >= 1, f"Failed to detect leak in: '{text}'"

    # 2. Non-leak text (FIR numbers, dates, money, affidavit paragraph) -> MUST NOT BE DETECTED
    non_leak_examples = [
        "FIR No. 123/2025 registered at Nashik Police Station.",
        "Incident took place on 10/06/2024 at 5:00 PM.",
        "Continuous demand for dowry amount of ₹5,00,000.",
        "Statement recorded in paragraph 5 of affidavit dated 15th.",
        "Physical assault upon spouse resulting in bodily harm.",
        "Misappropriation of Stridhan amounting to Criminal Breach of Trust.",
    ]

    for text in non_leak_examples:
        leaks = auditor.audit_text_for_leaks(text)
        assert len(leaks) == 0, f"False positive leak detected in: '{text}' -> {leaks}"


def test_pipeline_max_retries_hard_ceiling_cap():
    """
    Verifies that Stage1Pipeline strictly caps reflection retries to max_retries (default 1)
    and falls back cleanly to flag_for_confirmation and manual_review on judgment failures.
    """
    mock_query_llm = MagicMock()
    # LLM keeps generating section 498A
    mock_query_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {"victim": ["Wife"], "accused": ["Husband"]},
        "sub_queries": [
            {
                "id": "SQ1",
                "query": "Offence under Section 498A IPC for dowry cruelty.",
                "concept": "Dowry Demand",
                "target_parties": ["Husband"]
            }
        ]
    })

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "RETRY",
        "issues": [{"target": "SQ1", "issue": "Section 498A leak", "feedback": "Remove section number"}],
        "feedback": "Section leak."
    })

    agent = QueryUnderstandingAgent(llm=mock_query_llm)
    verifier = QueryVerificationAgent(llm=mock_verifier_llm)

    # Instantiate pipeline with hard cap max_retries = 1
    pipeline = Stage1Pipeline(query_agent=agent, verifier_agent=verifier, max_retries=1)

    res = pipeline.run("Case context string")

    # Verify total query agent calls == 2 (1 initial + 1 retry max)
    assert mock_query_llm.invoke.call_count == 2
    assert res.status == "RETRY"
    # Assert fallback to confirmation flag and manual review
    assert res.verified_query_object.flag_for_confirmation is True
    assert len(res.verified_query_object.manual_review) >= 1
    assert "Unresolved verification issue" in res.verified_query_object.manual_review[0]


def test_query_understanding_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {
            "victim": ["Wife"],
            "accused": ["Husband", "Father-in-law"]
        },
        "relationship": ["Husband-Wife", "In-laws"],
        "legal_concepts": [
            {"concept": "Dowry Demand", "confidence": 0.98},
            {"concept": "Criminal Intimidation", "confidence": 0.95},
            {"concept": "Low Confidence Concept", "confidence": 0.50}
        ],
        "sub_queries": [
            {
                "id": "SQ1",
                "query": "Repeated demands for dowry by husband and in-laws.",
                "concept": "Dowry Demand",
                "target_parties": ["Husband"],
                "role_alleged": "Main Accused"
            },
            {
                "id": "SQ2",
                "query": "Threats to cause physical harm.",
                "concept": "Criminal Intimidation",
                "target_parties": ["Father-in-law"],
                "role_alleged": "Co-Accused"
            }
        ],
        "procedural_events": ["Marriage", "FIR Registered", "Anticipatory Bail Application"],
        "important_facts": {
            "money": "₹5,00,000",
            "location": "Nashik Road",
            "documents": ["FIR"]
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = QueryUnderstandingAgent(llm=mock_llm, min_confidence_threshold=0.70)
    profile = CaseProfile(
        parties=Parties(accused=["Husband", "Father-in-law"]),
        case_facts="The husband and father-in-law repeatedly demanded dowry and issued threats.",
        requested_relief="Anticipatory Bail",
        procedural_stage="Anticipatory Bail",
        legal_regime="IPC + CrPC"
    )

    query_obj = agent.run(profile)

    assert len(query_obj.sub_queries) == 2
    assert query_obj.sub_queries[0].id == "SQ1"
    assert query_obj.sub_queries[0].target_parties == ["Husband"]
    assert "Husband" in query_obj.entities["accused"]
    # Check that concept below 0.70 cutoff was flagged in manual_review
    assert len(query_obj.manual_review) == 1
    assert "Low Confidence Concept" in query_obj.manual_review[0]


def test_statute_section_leak_verification_check():
    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Clean."
    })

    verifier = QueryVerificationAgent(llm=mock_verifier_llm)

    # Query containing forbidden section number "Section 498A"
    leaked_query_obj = LegalQueryObject(
        sub_queries=[
            SubQueryItem(id="SQ1", query="Offence under Section 498A IPC for dowry cruelty.", concept="Dowry Demand")
        ]
    )

    result = verifier.verify("Case context string", leaked_query_obj)

    # Must fail verification due to section leak
    assert result.status == "RETRY"
    assert len(result.issues) == 1
    assert "Statutory section leak" in result.issues[0].issue
    assert "498A" in result.issues[0].issue


def test_named_legal_concepts_permitted_vs_bare_section_numbers_blocked():
    """
    Verifies that statutory-flavored named legal concepts (HyDE-style pre-retrieval framing)
    e.g. 'Criminal Breach of Trust', 'Dishonest Inducement to Deliver Property', 'Matrimonial Cruelty'
    are PERMITTED and pass verification cleanly, while explicit section numbers like 'Section 406 IPC' are BLOCKED.
    """
    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "HyDE-style named legal concepts verified."
    })

    verifier = QueryVerificationAgent(llm=mock_verifier_llm)

    # 1. PERMITTED: Rich statutory-flavored named legal concepts without bare section numbers
    permitted_query_obj = LegalQueryObject(
        legal_concepts=[
            LegalConceptItem(concept="Criminal Breach of Trust", confidence=0.96),
            LegalConceptItem(concept="Dishonest Inducement to Deliver Property", confidence=0.94),
            LegalConceptItem(concept="Matrimonial Cruelty", confidence=0.95),
        ],
        sub_queries=[
            SubQueryItem(id="SQ1", query="Misappropriation of Stridhan amounting to Criminal Breach of Trust.", concept="Criminal Breach of Trust", target_parties=["Husband"]),
            SubQueryItem(id="SQ2", query="Dishonest Inducement to Deliver Property by false promises.", concept="Dishonest Inducement to Deliver Property", target_parties=["Father-in-law"]),
        ]
    )

    res_permitted = verifier.verify("Case context text", permitted_query_obj)
    assert res_permitted.status == "VERIFIED"
    assert res_permitted.verified_query_object is not None

    # 2. BLOCKED: Bare statutory section number leak (e.g. "u/s 406 IPC")
    blocked_query_obj = LegalQueryObject(
        sub_queries=[
            SubQueryItem(id="SQ1", query="Allegation of offence u/s 406 IPC for breach of trust.", concept="Criminal Breach of Trust", target_parties=["Husband"])
        ]
    )

    res_blocked = verifier.verify("Case context text", blocked_query_obj)
    assert res_blocked.status == "RETRY"
    assert len(res_blocked.issues) == 1
    assert "Statutory section leak" in res_blocked.issues[0].issue


def test_query_verifier_agent_verified_mock():
    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "All 8 criteria verified cleanly."
    })

    verifier = QueryVerificationAgent(llm=mock_verifier_llm)
    clean_query_obj = LegalQueryObject(
        sub_queries=[
            SubQueryItem(id="SQ1", query="Continuous demand for dowry by husband.", concept="Dowry Demand", target_parties=["Husband"])
        ]
    )

    result = verifier.verify("Case context string", clean_query_obj)
    assert result.status == "VERIFIED"
    assert result.verified_query_object is not None


def test_stage1_pipeline_flow():
    mock_query_llm = MagicMock()
    mock_query_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {"victim": ["Wife"], "accused": ["Husband"]},
        "relationship": ["Husband-Wife"],
        "legal_concepts": [{"concept": "Dowry Demand", "confidence": 0.95}],
        "sub_queries": [{"id": "SQ1", "query": "Continuous demand for dowry.", "concept": "Dowry Demand", "target_parties": ["Husband"]}],
        "procedural_events": ["FIR Registered"],
        "important_facts": {"money": "₹2,00,000"},
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Verified."
    })

    agent = QueryUnderstandingAgent(llm=mock_query_llm)
    verifier = QueryVerificationAgent(llm=mock_verifier_llm)

    pipeline = Stage1Pipeline(query_agent=agent, verifier_agent=verifier)
    res = pipeline.run("Case context string")

    assert res.status == "VERIFIED"
    assert res.verified_query_object.sub_queries[0].id == "SQ1"


def test_stage0_to_stage1_end_to_end_chain():
    # Test Stage 0 CaseContextObject exporting directly into Stage 1 Pipeline
    mock_intake_llm = MagicMock()
    mock_intake_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {"fir_number": "123/2025", "offence_date": "10/08/2024"},
        "parties": {"accused": "Husband"},
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "BNS + BNSS",
        "documents": ["FIR Copy", "Bail Application Copy"],
        "case_facts": "The husband demanded cash dowry and assaulted the victim.",
        "confidence": {"procedural_stage": 0.95}
    })

    mock_stage0_verifier_llm = MagicMock()
    mock_stage0_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Clean."
    })

    from lexigraphbe.pipeline import Stage0Pipeline
    s0_pipeline = Stage0Pipeline(
        intake_agent=CaseIntakeAgent(llm=mock_intake_llm),
        verifier_agent=CaseIntakeVerifierAgent(llm=mock_stage0_verifier_llm)
    )
    s0_res = s0_pipeline.run("Raw FIR document text")
    cco = s0_res.export_case_context_object()

    assert cco.contract_status == "CONTRACT_PASSED"

    mock_stage1_query_llm = MagicMock()
    mock_stage1_query_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "case_type": "Anticipatory Bail",
        "entities": {"victim": ["Wife"], "accused": ["Husband"]},
        "relationship": ["Husband-Wife"],
        "legal_concepts": [
            {"concept": "Dowry Demand", "confidence": 0.95},
            {"concept": "Physical Assault", "confidence": 0.92}
        ],
        "sub_queries": [
            {"id": "SQ1", "query": "Demand for cash dowry by husband.", "concept": "Dowry Demand", "target_parties": ["Husband"]},
            {"id": "SQ2", "query": "Physical assault upon victim by husband.", "concept": "Physical Assault", "target_parties": ["Husband"]}
        ],
        "procedural_events": ["FIR Registered", "Bail Application"],
        "important_facts": {"documents": ["FIR Copy"]},
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_stage1_verifier_llm = MagicMock()
    mock_stage1_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Stage 1 Verified."
    })

    s1_pipeline = Stage1Pipeline(
        query_agent=QueryUnderstandingAgent(llm=mock_stage1_query_llm),
        verifier_agent=QueryVerificationAgent(llm=mock_stage1_verifier_llm)
    )

    s1_res = s1_pipeline.run(cco)
    assert s1_res.status == "VERIFIED"
    assert len(s1_res.verified_query_object.sub_queries) == 2
    assert s1_res.verified_query_object.legal_regime == cco.case_profile.legal_regime
