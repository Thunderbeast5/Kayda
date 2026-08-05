"""
Pytest unit test suite for LexiGraph Stage 7: Role-Specific Legal Argument Generation Engine.
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
    DefenceArguments,
    JudgeOrder,
    LegalConceptItem,
    LegalQueryObject,
    OverallBailRecommendation,
    PrecedentItem,
    PrecedentRetrievalObject,
    ProsecutorArguments,
    RoleArgumentObject,
    RoleArgumentVerificationResult,
    SectionCandidateItem,
    StatutoryIngredientItem,
    StatutoryVerificationObject,
    VerifiedSectionItem,
)
from lexigraphbe.role_argument_agent import RoleArgumentAgent
from lexigraphbe.role_argument_verifier_agent import RoleArgumentVerifierAgent
from lexigraphbe.stage7_pipeline import Stage7Pipeline


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()


def test_role_argument_object_schema():
    prosecution = ProsecutorArguments(
        verified_sections=["498A IPC"],
        arguments=["Cruelty ingredients satisfied.", "Custodial interrogation needed."],
        precedents=["Arnesh Kumar v. State of Bihar"],
        prayer="Reject anticipatory bail."
    )
    defence = DefenceArguments(
        arguments=["No criminal antecedents.", "Full cooperation."],
        precedents=["Dilip Singh v. State of Madhya Pradesh"],
        prayer="Grant anticipatory bail."
    )
    judge = JudgeOrder(
        issues=["Whether anticipatory bail should be granted?"],
        facts_considered=["Factual summary"],
        applicable_law=["Section 498A IPC", "Section 438 CrPC"],
        statutory_analysis="Ingredients verified.",
        bail_factor_analysis="Low flight risk.",
        precedents=["Arnesh Kumar v. State of Bihar"],
        reasoning="Impartial reasoning.",
        decision="Grant",
        conditions=["Appear before IO."]
    )

    rao = RoleArgumentObject(
        prosecutor_arguments=prosecution,
        defence_arguments=defence,
        judge_order=judge
    )

    d = rao.model_dump()
    assert d["schema_version"] == "1.0"
    assert d["prosecutor_arguments"]["prayer"] == "Reject anticipatory bail."
    assert d["defence_arguments"]["prayer"] == "Grant anticipatory bail."
    assert d["judge_order"]["decision"] == "Grant"

    restored = RoleArgumentObject.model_validate(d)
    assert restored.prosecutor_arguments.verified_sections == ["498A IPC"]


def test_role_argument_agent_mock():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "prosecutor_arguments": {
            "verified_sections": ["498A IPC"],
            "arguments": ["Statutory ingredients satisfied.", "Custodial interrogation required."],
            "precedents": ["Arnesh Kumar v. State of Bihar"],
            "prayer": "Reject anticipatory bail."
        },
        "defence_arguments": {
            "arguments": ["No criminal antecedents.", "Cooperated with investigation."],
            "precedents": ["Dilip Singh v. State of Madhya Pradesh"],
            "prayer": "Grant anticipatory bail."
        },
        "judge_order": {
            "issues": ["Whether to grant anticipatory bail?"],
            "facts_considered": ["Case facts."],
            "applicable_law": ["Section 498A IPC"],
            "statutory_analysis": "Statutory analysis.",
            "bail_factor_analysis": "Bail factor analysis.",
            "precedents": ["Arnesh Kumar v. State of Bihar"],
            "reasoning": "Reasoning text.",
            "decision": "Grant",
            "conditions": ["Appear before IO."]
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = RoleArgumentAgent(llm=mock_llm)

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

    prec_item1 = PrecedentItem(case_name="Arnesh Kumar v. State of Bihar", court="Supreme Court", citation="(2014) 8 SCC 273", facts="Facts", verified_offences=["498A IPC"], bail_outcome="Outcome", ratio_decidendi="Ratio", similarity_score=0.95)
    prec_item2 = PrecedentItem(case_name="Dilip Singh v. State of Madhya Pradesh", court="Supreme Court", citation="LAWS(SC)-2021-1-41", facts="Facts", verified_offences=["420 IPC"], bail_outcome="Outcome", ratio_decidendi="Ratio", similarity_score=0.90)
    pro = PrecedentRetrievalObject(precedents=[prec_item1, prec_item2])

    rao = agent.run(cco, svo, bro, pro)

    assert rao.prosecutor_arguments.prayer == "Reject anticipatory bail."
    assert rao.defence_arguments.prayer == "Grant anticipatory bail."
    assert rao.judge_order.decision == "Grant"


def test_role_argument_verifier_agent_unretrieved_precedent_leak():
    """
    Verifies that zero-cost auditor pre-check catches unretrieved precedent citation leaks.
    """
    verifier = RoleArgumentVerifierAgent()

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

    prec_item = PrecedentItem(case_name="Arnesh Kumar v. State of Bihar", court="Supreme Court", citation="(2014) 8 SCC 273", facts="Facts", verified_offences=["498A IPC"], bail_outcome="Outcome", ratio_decidendi="Ratio", similarity_score=0.95)
    pro = PrecedentRetrievalObject(precedents=[prec_item])

    prosecution = ProsecutorArguments(verified_sections=["498A IPC"], arguments=["Cruelty satisfied."], precedents=["Unretrieved Fake Case v. State"], prayer="Reject anticipatory bail.")
    defence = DefenceArguments(arguments=["No antecedents."], precedents=["Arnesh Kumar v. State of Bihar"], prayer="Grant anticipatory bail.")
    judge = JudgeOrder(issues=["Issue"], facts_considered=["Facts"], applicable_law=["498A"], statutory_analysis="Analysis", bail_factor_analysis="Analysis", precedents=["Arnesh Kumar v. State of Bihar"], reasoning="Reasoning", decision="Grant", conditions=["Appear before IO."])

    rao = RoleArgumentObject(prosecutor_arguments=prosecution, defence_arguments=defence, judge_order=judge)

    v_res = verifier.verify(cco, svo, bro, pro, rao)

    assert v_res.status == "RETRY"
    assert any("Unretrieved Fake Case" in i.target for i in v_res.issues)


def test_role_argument_verifier_agent_low_confidence_precedent_rejection():
    """
    Verifies that RoleArgumentVerifierAgent rejects arguments relying on low-confidence precedents (< 0.70)
    without manual review clearance.
    """
    verifier = RoleArgumentVerifierAgent()

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

    low_prec_item = PrecedentItem(case_name="Weak Distant Case v. State", court="High Court", citation="2025 HC 11", facts="Facts", verified_offences=["498A IPC"], bail_outcome="Outcome", ratio_decidendi="Ratio", similarity_score=0.35)
    pro = PrecedentRetrievalObject(precedents=[low_prec_item], manual_review=[])

    prosecution = ProsecutorArguments(verified_sections=["498A IPC"], arguments=["Cruelty satisfied."], precedents=["Weak Distant Case v. State"], prayer="Reject anticipatory bail.")
    defence = DefenceArguments(arguments=["No antecedents."], precedents=[], prayer="Grant anticipatory bail.")
    judge = JudgeOrder(issues=["Issue"], facts_considered=["Facts"], applicable_law=["498A"], statutory_analysis="Analysis", bail_factor_analysis="Analysis", precedents=[], reasoning="Reasoning", decision="Grant", conditions=["Appear before IO."])

    rao = RoleArgumentObject(prosecutor_arguments=prosecution, defence_arguments=defence, judge_order=judge)

    v_res = verifier.verify(cco, svo, bro, pro, rao)

    assert v_res.status == "RETRY"
    assert any("low retrieval confidence" in i.issue.lower() for i in v_res.issues)


def test_stage7_upstream_stage4_failure_deferral():
    """
    Verifies that Stage 7 RoleArgumentAgent defers argument generation when upstream Stage 4 returns
    no verified sections or verification_status='UNVERIFIED'.
    """
    agent = RoleArgumentAgent()

    cp = CaseProfile(legal_regime="BNS + BNSS")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    svo = StatutoryVerificationObject(verified_sections=[], verification_status="FAILED_RETRY_EXHAUSTED")
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
    pro = PrecedentRetrievalObject(precedents=[])

    rao = agent.run(cco, svo, bro, pro)

    assert rao.verification_status == "DEFERRED_UPSTREAM_FAILURE"
    assert any("deferred due to upstream Stage 4" in note for note in rao.manual_review)




def test_stage7_pipeline_execution():
    mock_agent_llm = MagicMock()
    mock_agent_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "prosecutor_arguments": {
            "verified_sections": ["498A IPC"],
            "arguments": ["Statutory ingredients satisfied."],
            "precedents": ["Arnesh Kumar v. State of Bihar"],
            "prayer": "Reject anticipatory bail."
        },
        "defence_arguments": {
            "arguments": ["No criminal antecedents."],
            "precedents": ["Arnesh Kumar v. State of Bihar"],
            "prayer": "Grant anticipatory bail."
        },
        "judge_order": {
            "issues": ["Issue"],
            "facts_considered": ["Facts"],
            "applicable_law": ["Section 498A IPC"],
            "statutory_analysis": "Analysis",
            "bail_factor_analysis": "Analysis",
            "precedents": ["Arnesh Kumar v. State of Bihar"],
            "reasoning": "Reasoning",
            "decision": "Grant",
            "conditions": ["Appear before IO."]
        },
        "manual_review": [],
        "verification_status": "PENDING"
    })

    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Stage 7 arguments verified cleanly."
    })

    agent = RoleArgumentAgent(llm=mock_agent_llm)
    verifier = RoleArgumentVerifierAgent(llm=mock_verifier_llm)
    pipeline = Stage7Pipeline(argument_agent=agent, verifier_agent=verifier)

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

    prec_item = PrecedentItem(case_name="Arnesh Kumar v. State of Bihar", court="Supreme Court", citation="(2014) 8 SCC 273", facts="Facts", verified_offences=["498A IPC"], bail_outcome="Outcome", ratio_decidendi="Ratio", similarity_score=0.95)
    pro = PrecedentRetrievalObject(precedents=[prec_item])

    res = pipeline.run(cco, svo, bro, pro)

    assert res.status == "VERIFIED"
    assert res.verified_role_argument_object is not None
    assert res.verified_role_argument_object.prosecutor_arguments.prayer == "Reject anticipatory bail."


# ==============================================================================
# BAIL CONDITION CLOSED-SET VALIDATOR TESTS
# ==============================================================================

def test_bail_condition_validator_permissible_categories():
    """
    Verifies that all 8 canonical permissible bail condition categories pass validation.
    """
    from lexigraphbe.bail_condition_validator import BailConditionValidator, PERMISSIBLE_BAIL_CONDITION_CATEGORIES

    validator = BailConditionValidator()
    assert len(PERMISSIBLE_BAIL_CONDITION_CATEGORIES) == 8

    permissible_examples = [
        "Accused shall appear before the investigating officer whenever required.",
        "Accused shall surrender his passport to the court within 3 days.",
        "Accused shall not tamper with witnesses or evidence.",
        "Accused shall intimate the investigating officer of any change of address.",
        "Accused shall furnish a personal bond of Rs. 50,000 with two sureties.",
        "Accused shall cooperate with the investigating officer.",
        "Accused shall not commit any similar offence while on bail.",
        "Accused shall appear before the Sessions Court on the date fixed.",
    ]

    for cond in permissible_examples:
        result = validator.validate_single(cond)
        assert result.is_permissible, f"Expected permissible, but got rejection for: {cond!r} — {result.rejection_reason}"


def test_bail_condition_validator_impermissible_patterns():
    """
    Verifies that impermissible bail conditions (monetary deposit, civil recovery, etc.)
    are correctly rejected by the closed-set validator.
    """
    from lexigraphbe.bail_condition_validator import BailConditionValidator

    validator = BailConditionValidator()
    impermissible_examples = [
        "Accused shall deposit Rs. 41 Lakhs in the trial court.",
        "Accused shall pay compensation to the complainant.",
        "Accused shall settle the civil dispute with the complainant.",
        "Accused shall deposit cash of Rs. 10 Lakhs.",
    ]

    for cond in impermissible_examples:
        result = validator.validate_single(cond)
        assert not result.is_permissible, f"Expected rejection, but got permissible for: {cond!r}"


def test_stage7_judge_order_impermissible_condition_rejected():
    """
    Verifies that RoleArgumentVerifierAgent rejects JudgeOrder with impermissible bail conditions
    (e.g., monetary deposit) — closed-set validation must trigger RETRY.
    """
    verifier = RoleArgumentVerifierAgent()

    cp = CaseProfile(legal_regime="IPC + CrPC")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="498A", section_title="Cruelty", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="Medium"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Not Required"),
        witness_tampering=BailFactorEvaluationItem(value="Low"),
        evidence_tampering=BailFactorEvaluationItem(value="Low"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Grant Anticipatory Bail", confidence=0.92))

    prec_item = PrecedentItem(case_name="Arnesh Kumar v. State of Bihar", court="Supreme Court", citation="(2014) 8 SCC 273", facts="Facts", verified_offences=["498A IPC"], bail_outcome="Guidelines", ratio_decidendi="Ratio", similarity_score=0.95)
    pro = PrecedentRetrievalObject(precedents=[prec_item])

    prosecution = ProsecutorArguments(verified_sections=["498A IPC"], arguments=["Cruelty established."], precedents=["Arnesh Kumar v. State of Bihar"], prayer="Reject anticipatory bail.")
    defence = DefenceArguments(arguments=["No antecedents."], precedents=["Arnesh Kumar v. State of Bihar"], prayer="Grant anticipatory bail.")
    judge = JudgeOrder(
        issues=["Whether bail should be granted?"],
        facts_considered=["Dowry demand alleged."],
        applicable_law=["498A IPC", "438 CrPC"],
        statutory_analysis="Ingredients satisfied.",
        bail_factor_analysis="Gravity moderate.",
        precedents=["Arnesh Kumar v. State of Bihar"],
        reasoning="Reasonable.",
        decision="Grant",
        conditions=["Accused shall appear before IO.", "Accused shall deposit Rs. 50 Lakhs in the trial court."]
    )

    rao = RoleArgumentObject(prosecutor_arguments=prosecution, defence_arguments=defence, judge_order=judge)
    v_res = verifier.verify(cco, svo, bro, pro, rao)

    assert v_res.status == "RETRY"
    assert any("IMPERMISSIBLE_BAIL_CONDITION" in i.issue for i in v_res.issues)

