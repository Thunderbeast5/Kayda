"""
Pytest unit test suite for LexiGraph Stage 6: Judicial Precedent Retrieval Engine.
"""

import json
from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL
from lexigraphbe.schemas import (
    BailEvaluationMap,
    BailFactorEvaluationItem,
    BailReasoningObject,
    CaseContextObject,
    CaseProfile,
    ChapterCandidateItem,
    ChapterIdentificationObject,
    LegalConceptItem,
    LegalQueryObject,
    OverallBailRecommendation,
    PrecedentItem,
    PrecedentRetrievalObject,
    PrecedentVerificationIssue,
    PrecedentVerificationResult,
    SectionCandidateItem,
    StatutoryIngredientItem,
    StatutoryVerificationObject,
    SubQueryItem,
    VerifiedSectionItem,
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
from lexigraphbe.statutory_verification_agent import StatutoryVerificationAgent
from lexigraphbe.statutory_verifier_agent import StatutoryVerificationAuditor
from lexigraphbe.stage4_pipeline import Stage4Pipeline
from lexigraphbe.bail_reasoning_agent import BailReasoningAgent
from lexigraphbe.bail_verifier_agent import BailReasoningVerifierAgent
from lexigraphbe.stage5_pipeline import Stage5Pipeline
from lexigraphbe.precedent_retrieval_agent import PrecedentRetrievalAgent
from lexigraphbe.precedent_verifier_agent import PrecedentVerificationAuditor
from lexigraphbe.stage6_pipeline import Stage6Pipeline


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()


def test_precedent_retrieval_object_schema():
    item1 = PrecedentItem(
        case_name="Arnesh Kumar v. State of Bihar",
        court="Supreme Court",
        citation="(2014) 8 SCC 273",
        facts="Dowry harassment allegations under Section 498A.",
        verified_offences=["498A IPC"],
        bail_outcome="Anticipatory Bail Principles Applied",
        ratio_decidendi="Arrest should not be automatic in offences punishable up to seven years.",
        similarity_score=0.94
    )
    item2 = PrecedentItem(
        case_name="Dilip Singh v. State of Madhya Pradesh",
        court="Supreme Court",
        citation="LAWS(SC)-2021-1-41",
        facts="Property transaction, cheating allegations.",
        verified_offences=["420 IPC", "406 IPC"],
        bail_outcome="Conditional bail modified",
        ratio_decidendi="Bail proceedings cannot become recovery proceedings.",
        similarity_score=0.89
    )

    pro = PrecedentRetrievalObject(precedents=[item1, item2])

    d = pro.model_dump()
    assert d["schema_version"] == "1.0"
    assert len(d["precedents"]) == 2
    assert d["precedents"][0]["case_name"] == "Arnesh Kumar v. State of Bihar"
    assert d["precedents"][0]["similarity_score"] == 0.94

    restored = PrecedentRetrievalObject.model_validate(d)
    assert restored.precedents[1].citation == "LAWS(SC)-2021-1-41"


def test_precedent_retrieval_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "precedents": [
            {
                "case_name": "Arnesh Kumar v. State of Bihar",
                "court": "Supreme Court",
                "citation": "(2014) 8 SCC 273",
                "facts": "Dowry harassment allegations.",
                "verified_offences": ["498A IPC"],
                "bail_outcome": "Anticipatory Bail Principles Applied",
                "ratio_decidendi": "No automatic arrest under 7 years punishment.",
                "similarity_score": 0.95
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = PrecedentRetrievalAgent(llm=mock_llm)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92))

    pro = agent.run(cco, qo, svo, bro)

    assert len(pro.precedents) == 1
    assert pro.precedents[0].case_name == "Arnesh Kumar v. State of Bihar"
    assert pro.precedents[0].similarity_score == 0.95


def test_precedent_verifier_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Precedent retrieval audit cleanly passed."
    })

    verifier = PrecedentVerificationAuditor(llm=mock_llm)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92))

    pro = PrecedentRetrievalObject(precedents=[
        PrecedentItem(
            case_name="Arnesh Kumar v. State of Bihar",
            court="Supreme Court",
            citation="(2014) 8 SCC 273",
            facts="Facts",
            verified_offences=["498A IPC"],
            bail_outcome="Applied",
            ratio_decidendi="Ratio text.",
            similarity_score=0.94
        )
    ])

    res = verifier.verify(cco, svo, bro, pro)

    assert res.status == "VERIFIED"
    assert res.verified_precedent_object is not None
    assert res.verified_precedent_object.verification_status == "VERIFIED"


def test_stage6_pipeline_flow():
    mock_agent_llm = MagicMock()
    mock_agent_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "precedents": [
            {
                "case_name": "Arnesh Kumar v. State of Bihar",
                "court": "Supreme Court",
                "citation": "(2014) 8 SCC 273",
                "facts": "Dowry harassment allegations.",
                "verified_offences": ["498A IPC"],
                "bail_outcome": "Anticipatory Bail Principles Applied",
                "ratio_decidendi": "No automatic arrest under 7 years punishment.",
                "similarity_score": 0.95
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 6 Clean."})

    agent = PrecedentRetrievalAgent(llm=mock_agent_llm)
    verifier = PrecedentVerificationAuditor(llm=mock_verifier_llm)

    pipeline = Stage6Pipeline(retrieval_agent=agent, verifier_agent=verifier)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92))

    res = pipeline.run(cco, qo, svo, bro)

    assert res.status == "VERIFIED"
    assert res.verified_precedent_object is not None
    assert res.verified_precedent_object.precedents[0].case_name == "Arnesh Kumar v. State of Bihar"


def test_full_stage0_to_stage6_end_to_end_chain():
    # 1. Stage 0 Mock
    mock_s0_intake = MagicMock()
    mock_s0_intake.invoke.return_value.content = json.dumps({
        "case_metadata": {"fir_number": "2002/2025", "offence_date": "10/08/2024"},
        "parties": {"accused": ["Husband"]},
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "IPC + CrPC",
        "documents": ["FIR Copy"],
        "case_facts": "Dowry harassment and cruelty alleged under 498A.",
        "confidence": {"procedural_stage": 0.95}
    })
    mock_s0_verifier = MagicMock()
    mock_s0_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    s0_pipeline = Stage0Pipeline(intake_agent=CaseIntakeAgent(llm=mock_s0_intake), verifier_agent=CaseIntakeVerifierAgent(llm=mock_s0_verifier))
    s0_res = s0_pipeline.run("Raw FIR text")
    cco = s0_res.export_case_context_object()

    # 2. Stage 1 Mock
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

    # 3. Stage 3 Mock
    mock_s3_agent = MagicMock()
    mock_s3_agent.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "chapter_candidates": [{"concept": "Dowry Cruelty", "chapter_number": "XXA", "chapter_name": "Of Cruelty", "confidence": 0.98}],
        "section_candidates": [{"concept": "Dowry Cruelty", "section_number": "498A", "section_title": "Cruelty by Husband", "confidence": 0.99}],
        "manual_review": [],
        "verification_status": "PENDING"
    })
    mock_s3_verifier = MagicMock()
    mock_s3_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    s3_pipeline = Stage3Pipeline(chapter_agent=ChapterIdentificationAgent(llm=mock_s3_agent), verifier_agent=ChapterVerificationAgent(llm=mock_s3_verifier))
    s3_res = s3_pipeline.run(qo)
    cio = s3_res.verified_chapter_object

    # 4. Stage 4 Mock
    mock_s4_agent = MagicMock()
    mock_s4_agent.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "verified_sections": [
            {
                "section_number": "498A",
                "section_title": "Cruelty by Husband",
                "ingredients": [{"ingredient": "Marriage", "status": "Satisfied", "reason": "Married."}],
                "overall_confidence": 0.97
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })
    mock_s4_auditor = MagicMock()
    mock_s4_auditor.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Clean."})

    s4_pipeline = Stage4Pipeline(statutory_agent=StatutoryVerificationAgent(llm=mock_s4_agent), verifier_agent=StatutoryVerificationAuditor(llm=mock_s4_auditor))
    s4_res = s4_pipeline.run(qo, cio)
    svo = s4_res.verified_statutory_object

    # 5. Stage 5 Mock
    mock_s5_agent = MagicMock()
    mock_s5_agent.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "bail_provision_applied": "Section 438 CrPC",
        "legal_regime": "IPC + CrPC",
        "bail_evaluation": {
            "gravity_of_offence": {"value": "High", "reason": "Severe cruelty."},
            "prima_facie_case": {"value": "Strong", "reason": "Ingredients satisfied."},
            "custodial_interrogation": {"value": "Required", "reason": "Recovery pending."},
            "witness_tampering": {"value": "High", "reason": "Family relationship."},
            "evidence_tampering": {"value": "Medium", "reason": "Electronic evidence."},
            "flight_risk": {"value": "Low", "reason": "Local residence."},
            "criminal_antecedents": {"value": "None", "reason": "Clean record."},
            "cooperation": {"value": "Cooperative", "reason": "Joined investigation."}
        },
        "overall_recommendation": {
            "decision": "Recommend Reject Anticipatory Bail",
            "confidence": 0.92,
            "summary_reasoning": "Rejection recommended."
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })
    mock_s5_verifier = MagicMock()
    mock_s5_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 5 Clean."})

    s5_pipeline = Stage5Pipeline(reasoning_agent=BailReasoningAgent(llm=mock_s5_agent), verifier_agent=BailReasoningVerifierAgent(llm=mock_s5_verifier))
    s5_res = s5_pipeline.run(cco, qo, svo)
    bro = s5_res.verified_bail_object

    # 6. Stage 6 Mock
    mock_s6_agent = MagicMock()
    mock_s6_agent.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "precedents": [
            {
                "case_name": "Arnesh Kumar v. State of Bihar",
                "court": "Supreme Court",
                "citation": "(2014) 8 SCC 273",
                "facts": "Dowry harassment allegations under 498A.",
                "verified_offences": ["498A IPC"],
                "bail_outcome": "Anticipatory Bail Principles Applied",
                "ratio_decidendi": "Arrest should not be automatic in offences punishable up to 7 years.",
                "similarity_score": 0.96
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })
    mock_s6_verifier = MagicMock()
    mock_s6_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 6 Clean."})

    s6_pipeline = Stage6Pipeline(retrieval_agent=PrecedentRetrievalAgent(llm=mock_s6_agent), verifier_agent=PrecedentVerificationAuditor(llm=mock_s6_verifier))
    s6_res = s6_pipeline.run(cco, qo, svo, bro)

    assert s6_res.status == "VERIFIED"
    pro = s6_res.verified_precedent_object
    assert pro is not None
    assert len(pro.precedents) == 1
    assert pro.precedents[0].case_name == "Arnesh Kumar v. State of Bihar"
    assert pro.precedents[0].similarity_score == 0.96


def test_grounded_precedents_structured_json_dataset_loading():
    """
    Verifies that PrecedentRetrievalAgent loads precedents_structured.json from disk,
    verifies that the corpus has >= 8 grounded landmark precedent records, and passes
    grounded dataset entries into the LLM prompt.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "precedents": [
            {
                "case_name": "Gurbaksh Singh Sibbia v. State of Punjab",
                "court": "Supreme Court of India",
                "citation": "(1980) 2 SCC 565",
                "facts": "Landmark Constitution Bench decision.",
                "verified_offences": ["438 CrPC"],
                "bail_outcome": "Anticipatory Bail Scope Defined",
                "ratio_decidendi": "Section 438 CrPC is a device to secure individual liberty.",
                "similarity_score": 0.95
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = PrecedentRetrievalAgent(llm=mock_llm)

    # 1. Assert corpus loaded from precedents_structured.json has at least 8 records
    assert len(agent.corpus) >= 8
    assert any("Gurbaksh Singh Sibbia" in c["case_name"] for c in agent.corpus)
    assert any("Satender Kumar Antil" in c["case_name"] for c in agent.corpus)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92))

    agent.run(cco, qo, svo, bro)

    # 2. Assert grounded dataset json was injected into LLM prompt
    messages_sent = mock_llm.invoke.call_args[0][0]
    prompt_text = messages_sent[1].content
    assert "PREC_SC_001" in prompt_text
    assert "Gurbaksh Singh Sibbia" in prompt_text
    assert "Satender Kumar Antil" in prompt_text


def test_stage6_precedent_similarity_calibration():
    """
    Verifies that PrecedentRetrievalAgent calibrates similarity scores based on factual and offence overlap:
    - Arnesh Kumar / direct offence matches score high (>= 0.90).
    - Satender Kumar Antil (generic Category A guidelines) scores <= 0.55 and triggers manual_review warning.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "precedents": [
            {
                "case_name": "Arnesh Kumar v. State of Bihar",
                "court": "Supreme Court of India",
                "citation": "(2014) 8 SCC 273",
                "facts": "Allegations under 498A IPC and Section 4 DP Act.",
                "verified_offences": ["498A IPC", "4 Dowry Prohibition Act"],
                "bail_outcome": "Guidelines Formulated",
                "ratio_decidendi": "Mandatory 41A notice required.",
                "similarity_score": 0.85
            },
            {
                "case_name": "Satender Kumar Antil v. CBI",
                "court": "Supreme Court of India",
                "citation": "(2022) 10 SCC 51",
                "facts": "General arrest guidelines across Category A, B, C, D offences.",
                "verified_offences": ["Category A Offences"],
                "bail_outcome": "Bail Policy Formulated",
                "ratio_decidendi": "Category A offences up to 7 years get bail without custody.",
                "similarity_score": 0.85
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = PrecedentRetrievalAgent(llm=mock_llm)

    cco = CaseContextObject(case_profile=CaseProfile(legal_regime="IPC + CrPC"), contract_status="VALID", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92))

    res = agent.run(cco, qo, svo, bro)

    # Arnesh Kumar should be calibrated >= 0.90
    arnesh = next((p for p in res.precedents if "Arnesh" in p.case_name), None)
    assert arnesh is not None
    assert arnesh.similarity_score >= 0.90

    # Satender Kumar Antil should be calibrated <= 0.55 & trigger manual_review
    satender = next((p for p in res.precedents if "Satender" in p.case_name), None)
    assert satender is not None
    assert satender.similarity_score <= 0.55
    assert any("Satender" in note and "cutoff 0.70" in note for note in res.manual_review)

