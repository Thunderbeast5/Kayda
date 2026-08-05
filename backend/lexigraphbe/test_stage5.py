"""
Pytest unit test suite for LexiGraph Stage 5: Anticipatory Bail Reasoning Engine.
"""

import json
from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL
from lexigraphbe.schemas import (
    BailEvaluationMap,
    BailFactorEvaluationItem,
    BailReasoningObject,
    BailVerificationIssue,
    BailVerificationResult,
    CaseContextObject,
    CaseProfile,
    ChapterCandidateItem,
    ChapterIdentificationObject,
    LegalConceptItem,
    LegalQueryObject,
    OverallBailRecommendation,
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


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()


def test_bail_reasoning_object_schema():
    eval_map = BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High", reason="Cruelty and dowry harassment."),
        prima_facie_case=BailFactorEvaluationItem(value="Strong", reason="Ingredients satisfied."),
        custodial_interrogation=BailFactorEvaluationItem(value="Required", reason="Recovery pending."),
        witness_tampering=BailFactorEvaluationItem(value="High", reason="Family relationship."),
        evidence_tampering=BailFactorEvaluationItem(value="Medium", reason="Electronic records."),
        flight_risk=BailFactorEvaluationItem(value="Low", reason="Permanent residence."),
        criminal_antecedents=BailFactorEvaluationItem(value="None", reason="No prior record."),
        cooperation=BailFactorEvaluationItem(value="Cooperative", reason="Attended questioning.")
    )
    rec = OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92, summary_reasoning="Pending recovery.")

    bro = BailReasoningObject(
        bail_provision_applied="Section 438 CrPC",
        legal_regime="IPC + CrPC",
        bail_evaluation=eval_map,
        overall_recommendation=rec
    )

    d = bro.model_dump()
    assert d["schema_version"] == "5.0"
    assert d["bail_provision_applied"] == "Section 438 CrPC"
    assert d["bail_evaluation"]["gravity_of_offence"]["value"] == "High"
    assert d["overall_recommendation"]["decision"] == "Recommend Reject Anticipatory Bail"

    restored = BailReasoningObject.model_validate(d)
    assert restored.overall_recommendation.confidence == 0.92


def test_bail_reasoning_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "bail_provision_applied": "Section 438 CrPC",
        "legal_regime": "IPC + CrPC",
        "bail_evaluation": {
            "gravity_of_offence": {"value": "High", "reason": "Severe cruelty alleged."},
            "prima_facie_case": {"value": "Strong", "reason": "Stage 4 ingredients satisfied."},
            "custodial_interrogation": {"value": "Required", "reason": "Stridhan recovery pending."},
            "witness_tampering": {"value": "High", "reason": "Close family ties."},
            "evidence_tampering": {"value": "Medium", "reason": "Digital messages accessible."},
            "flight_risk": {"value": "Low", "reason": "Local roots."},
            "criminal_antecedents": {"value": "None", "reason": "No priors."},
            "cooperation": {"value": "Cooperative", "reason": "Joined investigation."}
        },
        "overall_recommendation": {
            "decision": "Recommend Reject Anticipatory Bail",
            "confidence": 0.92,
            "summary_reasoning": "Custodial interrogation required for pending recovery."
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = BailReasoningAgent(llm=mock_llm)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])

    bro = agent.run(cco, qo, svo)

    assert bro.bail_provision_applied == "Section 438 CrPC"
    assert bro.bail_evaluation.gravity_of_offence.value == "High"
    assert bro.overall_recommendation.decision == "Recommend Reject Anticipatory Bail"


def test_bail_verifier_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Bail reasoning audit cleanly passed."
    })

    verifier = BailReasoningVerifierAgent(llm=mock_llm)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    eval_map = BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    )
    rec = OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.92)
    bro = BailReasoningObject(bail_evaluation=eval_map, overall_recommendation=rec)

    res = verifier.verify(cco, svo, bro)

    assert res.status == "VERIFIED"
    assert res.verified_bail_object is not None
    assert res.verified_bail_object.verification_status == "VERIFIED"


def test_stage5_pipeline_flow():
    mock_agent_llm = MagicMock()
    mock_agent_llm.invoke.return_value.content = json.dumps({
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

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 5 Clean."})

    agent = BailReasoningAgent(llm=mock_agent_llm)
    verifier = BailReasoningVerifierAgent(llm=mock_verifier_llm)

    pipeline = Stage5Pipeline(reasoning_agent=agent, verifier_agent=verifier)

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])

    res = pipeline.run(cco, qo, svo)

    assert res.status == "VERIFIED"
    assert res.verified_bail_object is not None
    assert res.verified_bail_object.overall_recommendation.decision == "Recommend Reject Anticipatory Bail"


def test_procedural_bail_provision_statutory_text_injection():
    """
    Verifies that BailReasoningAgent injects the exact statutory text of Section 438 CrPC
    or Section 482 BNSS based on the legal regime into the LLM prompt.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "bail_provision_applied": "Section 482 BNSS",
        "legal_regime": "BNS + BNSS",
        "bail_evaluation": {
            "gravity_of_offence": {"value": "High", "reason": "Severe cruelty under BNS 85."},
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
            "summary_reasoning": "Rejection recommended under Sec 482 BNSS statutory factors."
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = BailReasoningAgent(llm=mock_llm)

    cp = CaseProfile(legal_regime="BNS + BNSS")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Cruelty", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="85", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])

    bro = agent.run(cco, qo, svo)

    # 1. Assert Section 482 BNSS was applied
    assert bro.bail_provision_applied == "Section 482 BNSS"

    # 2. Assert statutory text of Section 482 BNSS was injected into LLM prompt
    messages_sent = mock_llm.invoke.call_args[0][0]
    prompt_text = messages_sent[1].content
    assert "Section 482 BNSS" in prompt_text
    assert "Bharatiya Nagarik Suraksha Sanhita" in prompt_text
    assert "Direction for grant of bail to person apprehending arrest" in prompt_text


def test_full_stage0_to_stage5_end_to_end_chain():
    # 1. Stage 0 Mock
    mock_s0_intake = MagicMock()
    mock_s0_intake.invoke.return_value.content = json.dumps({
        "case_metadata": {"fir_number": "1001/2025", "offence_date": "10/08/2024"},
        "parties": {"accused": ["Husband"]},
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "BNS + BNSS",
        "documents": ["FIR Copy"],
        "case_facts": "The husband repeatedly harassed the victim.",
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
        "sub_queries": [{"id": "SQ1", "query": "Cruelty harassment.", "concept": "Matrimonial Cruelty", "target_parties": ["Husband"]}],
        "legal_concepts": [{"concept": "Matrimonial Cruelty", "confidence": 0.95}],
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
        "chapter_candidates": [{"concept": "Matrimonial Cruelty", "chapter_number": "V", "chapter_name": "Of Offences Against Woman", "confidence": 0.98}],
        "section_candidates": [{"concept": "Matrimonial Cruelty", "section_number": "85", "section_title": "Cruelty by Husband", "confidence": 0.99}],
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
                "section_number": "85",
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
        "bail_provision_applied": "Section 482 BNSS",
        "legal_regime": "BNS + BNSS",
        "bail_evaluation": {
            "gravity_of_offence": {"value": "Medium", "reason": "BNS 85 offence."},
            "prima_facie_case": {"value": "Strong", "reason": "Ingredients satisfied."},
            "custodial_interrogation": {"value": "Not Required", "reason": "No recovery pending."},
            "witness_tampering": {"value": "Low", "reason": "No threats alleged."},
            "evidence_tampering": {"value": "Low", "reason": "Documents in police custody."},
            "flight_risk": {"value": "Low", "reason": "Local residence."},
            "criminal_antecedents": {"value": "None", "reason": "No priors."},
            "cooperation": {"value": "Cooperative", "reason": "Joined investigation."}
        },
        "overall_recommendation": {
            "decision": "Recommend Grant Anticipatory Bail",
            "confidence": 0.94,
            "summary_reasoning": "Custodial interrogation not required and no flight risk."
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })
    mock_s5_verifier = MagicMock()
    mock_s5_verifier.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Stage 5 Clean."})

    s5_pipeline = Stage5Pipeline(reasoning_agent=BailReasoningAgent(llm=mock_s5_agent), verifier_agent=BailReasoningVerifierAgent(llm=mock_s5_verifier))
    s5_res = s5_pipeline.run(cco, qo, svo)

    assert s5_res.status == "VERIFIED"
    assert s5_res.verified_bail_object is not None
    assert s5_res.verified_bail_object.prosecution_arguments is not None
    assert s5_res.verified_bail_object.defense_arguments is not None


def test_stage5_dual_perspective_argument_packages():
    """
    Verifies that Stage 5 generates structured argument packages for both Prosecution (bail denial)
    and Defense (bail grant) to feed Virtual Moot Court role agents.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "5.0",
        "bail_provision_applied": "Section 438 CrPC",
        "legal_regime": "IPC + CrPC",
        "bail_evaluation": {
            "gravity_of_offence": {"value": "High", "reason": "Continuous dowry harassment and cruelty."},
            "prima_facie_case": {"value": "Strong", "reason": "Ingredients of S.498A satisfied."},
            "custodial_interrogation": {"value": "Required", "reason": "Recovery of dowry articles and Stridhan is pending."},
            "witness_tampering": {"value": "High", "reason": "Witnesses are family members."},
            "evidence_tampering": {"value": "Medium", "reason": "Electronic records."},
            "flight_risk": {"value": "Low", "reason": "Local residence."},
            "criminal_antecedents": {"value": "None", "reason": "No priors."},
            "cooperation": {"value": "Cooperative", "reason": "Joined investigation."}
        },
        "overall_recommendation": {
            "decision": "Recommend Reject Anticipatory Bail",
            "confidence": 0.92,
            "summary_reasoning": "High gravity and pending recovery of Stridhan."
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = BailReasoningAgent(llm=mock_llm)
    cco = CaseContextObject(
        case_profile=CaseProfile(procedural_stage="Anticipatory Bail", legal_regime="IPC + CrPC"),
        contract_status="VALID",
        verification_status="VERIFIED"
    )
    qo = LegalQueryObject(legal_regime="IPC + CrPC", legal_concepts=[LegalConceptItem(concept="Cruelty", confidence=0.95)])
    svo = StatutoryVerificationObject(legal_regime="IPC + CrPC")

    bro_pros = agent.run(cco, qo, svo, side="PROSECUTION")
    assert bro_pros.target_side == "PROSECUTION"
    assert bro_pros.prosecution_arguments is not None
    assert bro_pros.prosecution_arguments.primary_objective == "REJECT_BAIL"

    bro_def = agent.run(cco, qo, svo, side="DEFENSE")
    assert bro_def.target_side == "DEFENSE"
    assert bro_def.defense_arguments is not None
    assert bro_def.defense_arguments.primary_objective == "GRANT_BAIL"
