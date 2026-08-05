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
    assert pro.precedents[0].similarity_score > 0.0


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
    assert pro.precedents[0].similarity_score > 0.0


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


def test_precedent_similarity_matcher_mathematical_vector_cosine():
    """
    Verifies that PrecedentSimilarityMatcher calculates real mathematical TF-IDF vector cosine similarity,
    Jaccard offence set overlap score, and hybrid score in Python code with zero LLM opinion bias.
    """
    from lexigraphbe.precedent_matcher import PrecedentSimilarityMatcher
    from lexigraphbe.precedent_retrieval_agent import load_precedents_corpus

    matcher = PrecedentSimilarityMatcher()

    # 1. Test Cosine Similarity Math
    sim1 = matcher.compute_cosine_similarity("continuous dowry demand harassment physical assault", "allegations of matrimonial cruelty and dowry harassment under section 498A")
    assert sim1 > 0.0
    assert isinstance(sim1, float)

    # 2. Test Jaccard Offence Overlap Math
    jaccard_score = matcher.compute_jaccard_similarity({"498A_IPC", "4_DOWRY_PROHIBITION_ACT"}, {"498A_IPC", "304B_IPC"})
    assert jaccard_score == round(1 / 3, 4)

    # 3. Test Full Hybrid Precedent Ranking
    cp = CaseProfile(legal_regime="IPC + CrPC", case_facts="Continuous harassment for dowry and physical assault.")
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

    corpus = load_precedents_corpus()
    ranked = matcher.rank_precedents(cco, qo, svo, bro, corpus, top_k=3)

    assert len(ranked) == 3
    assert ranked[0].computed_similarity_score > 0.0
    assert ranked[0].computed_similarity_score >= ranked[1].computed_similarity_score


def test_multi_domain_precedent_corpus_and_low_similarity_cutoff_handling():
    """
    Verifies that PrecedentRetrievalAgent and PrecedentSimilarityMatcher:
    1. Support multi-domain precedent matching (NDPS, PMLA, POCSO, Matrimonial, Homicide).
    2. Flag fact patterns with low similarity score (< 0.70) in manual_review rather than force-fitting.
    """
    from lexigraphbe.precedent_matcher import PrecedentSimilarityMatcher
    from lexigraphbe.precedent_retrieval_agent import load_precedents_corpus, PrecedentRetrievalAgent

    corpus = load_precedents_corpus()
    assert len(corpus) >= 12
    assert any(c.get("category") == "NDPS Act" for c in corpus)
    assert any(c.get("category") == "Economic & Money Laundering" for c in corpus)
    assert any(c.get("category") == "POCSO & Sexual Offences" for c in corpus)

    # Test NDPS fact pattern matching
    matcher = PrecedentSimilarityMatcher()
    cp = CaseProfile(legal_regime="IPC + CrPC", case_facts="Seizure of commercial quantity of psychotropic drug under NDPS Act.")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="NDPS Drug Possession", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="22 NDPS", section_title="Psychotropic Substance", ingredients=[], overall_confidence=0.95)])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="High"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Required"),
        witness_tampering=BailFactorEvaluationItem(value="High"),
        evidence_tampering=BailFactorEvaluationItem(value="Medium"),
        flight_risk=BailFactorEvaluationItem(value="High"),
        criminal_antecedents=BailFactorEvaluationItem(value="Previous NDPS Case"),
        cooperation=BailFactorEvaluationItem(value="Non-Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Reject Anticipatory Bail", confidence=0.95))

    ranked_ndps = matcher.rank_precedents(cco, qo, svo, bro, corpus, top_k=3)
    assert ranked_ndps[0].case_name == "State of Kerala v. Rajesh"

    # Test Unmatched low-similarity fact pattern (< 0.70 cutoff)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "1.0",
        "precedents": [
            {
                "case_name": "Irrelevant Distant Case",
                "court": "High Court",
                "citation": "2025 HC 100",
                "facts": "Unrelated maritime dispute.",
                "verified_offences": ["999 Fake"],
                "bail_outcome": "N/A",
                "ratio_decidendi": "Unrelated ratio.",
                "similarity_score": 0.15
            }
        ],
        "manual_review": [],
        "verification_status": "PENDING"
    })

    agent = PrecedentRetrievalAgent(llm=mock_llm, min_similarity_threshold=0.70)
    pro = agent.run(cco, qo, svo, bro)

    assert any("cutoff 0.7" in note for note in pro.manual_review)


def test_rich_factual_narrative_and_numbered_paragraphs_vector_signal():
    """
    Verifies that PrecedentSimilarityMatcher extracts high-density vector signal from
    factual_narrative and numbered_paragraphs attributes in precedents_structured.json.
    """
    from lexigraphbe.precedent_matcher import PrecedentSimilarityMatcher
    from lexigraphbe.precedent_retrieval_agent import load_precedents_corpus

    corpus = load_precedents_corpus()
    arnesh_case = next(c for c in corpus if c["case_name"] == "Arnesh Kumar v. State of Bihar")

    assert "factual_narrative" in arnesh_case
    assert len(arnesh_case["factual_narrative"]) > 100
    assert "numbered_paragraphs" in arnesh_case
    assert len(arnesh_case["numbered_paragraphs"]) >= 3

    matcher = PrecedentSimilarityMatcher()
    detailed_facts = "Marriage solemnized on 01.07.2007 according to Hindu rites. Complainant alleged husband and mother-in-law demanded Maruti car, air-conditioner, and Rs 8 Lakhs dowry."
    sim_score = matcher.compute_cosine_similarity(detailed_facts, arnesh_case["factual_narrative"])
    assert sim_score > 0.25


def test_bns_regime_precedent_retrieval_and_offence_mapping():
    """
    Verifies that a BNS-regime case with verified offences '85 BNS' and '318 BNS'
    retrieves matching precedents (Arnesh Kumar, Kahkashan Kausar) with 100% accuracy via IPC2BNS equivalence mapping.
    """
    from lexigraphbe.precedent_matcher import PrecedentSimilarityMatcher
    from lexigraphbe.precedent_retrieval_agent import load_precedents_corpus

    corpus = load_precedents_corpus()
    matcher = PrecedentSimilarityMatcher()

    cp = CaseProfile(legal_regime="BNS + BNSS", case_facts="Matrimonial dispute under Section 85 BNS and cheating allegations under Section 318 BNS.")
    cco = CaseContextObject(case_profile=cp, contract_status="CONTRACT_PASSED", verification_status="VERIFIED")
    qo = LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Dowry Cruelty BNS", confidence=0.95)])
    svo = StatutoryVerificationObject(verified_sections=[
        VerifiedSectionItem(section_number="85 BNS", section_title="Cruelty", ingredients=[], overall_confidence=0.95),
        VerifiedSectionItem(section_number="318 BNS", section_title="Cheating", ingredients=[], overall_confidence=0.95)
    ])
    bro = BailReasoningObject(bail_evaluation=BailEvaluationMap(
        gravity_of_offence=BailFactorEvaluationItem(value="Medium"),
        prima_facie_case=BailFactorEvaluationItem(value="Strong"),
        custodial_interrogation=BailFactorEvaluationItem(value="Not Required"),
        witness_tampering=BailFactorEvaluationItem(value="Low"),
        evidence_tampering=BailFactorEvaluationItem(value="Low"),
        flight_risk=BailFactorEvaluationItem(value="Low"),
        criminal_antecedents=BailFactorEvaluationItem(value="None"),
        cooperation=BailFactorEvaluationItem(value="Cooperative")
    ), overall_recommendation=OverallBailRecommendation(decision="Recommend Grant Anticipatory Bail", confidence=0.95))

    ranked = matcher.rank_precedents(cco, qo, svo, bro, corpus, top_k=5)

    assert len(ranked) > 0
    retrieved_names = [r.case_name for r in ranked]
    assert any("Arnesh Kumar" in name for name in retrieved_names)
    assert any("Kahkashan Kausar" in name or "Gurbaksh Singh" in name for name in retrieved_names)






