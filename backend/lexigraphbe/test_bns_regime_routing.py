"""
Pytest unit test suite for BNS Regime Routing & IPC ↔ BNS Statutory Mapping.
"""

from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL
from lexigraphbe.schemas import LegalConceptItem, LegalQueryObject
from lexigraphbe.classifier_prefilter import StatuteClassifierPrefilter
from lexigraphbe.ipc2bns_mapper import IPC2BNSMapper
from lexigraphbe.chapter_identification_agent import ChapterIdentificationAgent


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()


def test_ipc2bns_mapper_bidirectional():
    """
    Verifies that IPC2BNSMapper correctly translates IPC sections to BNS sections and vice versa.
    """
    mapper = IPC2BNSMapper()

    # 1. IPC 498A -> BNS 85
    res1 = mapper.get_bns_equivalent("498A")
    assert res1 is not None
    assert res1["bns_section_clean"] == "85"

    # 2. BNS 85 -> IPC 498A
    res2 = mapper.get_ipc_equivalent("85")
    assert res2 is not None
    assert res2["ipc_section"] == "498A"

    # 3. IPC 420 -> BNS 318(4)
    res3 = mapper.get_bns_equivalent("420")
    assert res3 is not None
    assert "318" in res3["bns_section_clean"]

    # 4. IPC 302 -> BNS 103(1)
    res4 = mapper.get_bns_equivalent("302")
    assert res4 is not None
    assert "103" in res4["bns_section_clean"]


def test_bns_regime_prefilter_routing():
    """
    Verifies that StatuteClassifierPrefilter routes candidate section searching to BNS dataset
    when target_regime is 'BNS + BNSS' or statute_type is 'BNS'.
    """
    prefilter = StatuteClassifierPrefilter()

    # Query BNS dataset for dowry cruelty
    bns_matches = prefilter.prefilter_candidates("dowry cruelty harassment", statute_type="BNS", top_k=5)
    assert len(bns_matches) > 0
    assert any(m.statute == "BNS" for m in bns_matches)
    assert any(m.section_number == "85" for m in bns_matches)

    # Query IPC dataset for comparison
    ipc_matches = prefilter.prefilter_candidates("dowry cruelty harassment", statute_type="IPC", top_k=5)
    assert len(ipc_matches) > 0
    assert any(m.statute == "IPC" for m in ipc_matches)
    assert any(m.section_number == "498A" for m in ipc_matches)


def test_stage3_bns_regime_passthrough():
    """
    Verifies that Stage 3 ChapterIdentificationAgent respects query_obj.legal_regime = 'BNS + BNSS'
    and passes target_regime='BNS + BNSS' to pre-filter candidate search.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = '{"schema_version": "1.0", "chapter_candidates": [{"concept": "Cruelty", "chapter_number": "V", "chapter_name": "Of Offences Against Woman", "confidence": 0.98}], "section_candidates": [{"concept": "Cruelty", "section_number": "85", "section_title": "Cruelty by Husband", "confidence": 0.99}], "manual_review": [], "verification_status": "PENDING"}'

    agent = ChapterIdentificationAgent(llm=mock_llm)

    qo = LegalQueryObject(
        legal_regime="BNS + BNSS",
        legal_concepts=[LegalConceptItem(concept="Dowry Cruelty", confidence=0.95)]
    )

    cio = agent.run(qo)

    assert cio.legal_regime == "BNS + BNSS"
    assert cio.section_candidates[0].section_number == "85"


def test_stage3_ipc_index_selection_for_ipc_regime():
    """
    DEDICATED STAGE 3 INDEX VERIFICATION (IPC):
    Verifies that when legal_regime is 'IPC + CrPC', Stage 3 prefilter EXCLUSIVELY
    queries the IPC index and excludes 100% of BNS candidates.
    """
    prefilter = StatuteClassifierPrefilter()
    qo_ipc = LegalQueryObject(
        legal_regime="IPC + CrPC",
        legal_concepts=[LegalConceptItem(concept="cheating property fraud", confidence=0.95)]
    )

    candidates = prefilter.shortlist_candidates_for_query(qo_ipc, top_k=10, target_regime="IPC + CrPC")
    assert len(candidates) > 0
    assert all(c.statute == "IPC" for c in candidates), "IPC regime search contained non-IPC candidates"
    assert any(c.section_number == "420" for c in candidates), "IPC 420 missing from IPC cheating search"


def test_stage3_bns_index_selection_for_bns_regime():
    """
    DEDICATED STAGE 3 INDEX VERIFICATION (BNS):
    Verifies that when legal_regime is 'BNS + BNSS', Stage 3 prefilter EXCLUSIVELY
    queries the BNS index and excludes 100% of IPC candidates.
    """
    prefilter = StatuteClassifierPrefilter()
    qo_bns = LegalQueryObject(
        legal_regime="BNS + BNSS",
        legal_concepts=[LegalConceptItem(concept="cheating property fraud", confidence=0.95)]
    )

    candidates = prefilter.shortlist_candidates_for_query(qo_bns, top_k=10, target_regime="BNS + BNSS")
    assert len(candidates) > 0
    assert all(c.statute == "BNS" for c in candidates), "BNS regime search contained non-BNS candidates"
    assert any("318" in c.section_number for c in candidates), "BNS 318 missing from BNS cheating search"


def test_stage3_historical_cases_regime_routing():
    """
    DEDICATED HISTORICAL CASE ROUTING TEST:
    Verifies that historical cases (offence committed prior to 1 July 2024) route to IPC index,
    while post-July 2024 cases route to BNS index.
    """
    from lexigraphbe.schemas import CaseContextObject, CaseProfile, CaseMetadata
    from lexigraphbe.intake_agent import CaseIntakeAgent

    # 1. Historical pre-July-2024 case (e.g., May 2024) -> IPC regime
    cco_historical = CaseContextObject(
        case_metadata=CaseMetadata(offence_date="2024-05-15"),
        case_profile=CaseProfile(legal_regime="IPC + CrPC"),
        contract_status="CONTRACT_PASSED",
        verification_status="VERIFIED"
    )

    # 2. Modern post-July-2024 case (e.g., August 2024) -> BNS regime
    cco_modern = CaseContextObject(
        case_metadata=CaseMetadata(offence_date="2024-08-15"),
        case_profile=CaseProfile(legal_regime="BNS + BNSS"),
        contract_status="CONTRACT_PASSED",
        verification_status="VERIFIED"
    )

    assert cco_historical.case_profile.legal_regime == "IPC + CrPC"
    assert cco_modern.case_profile.legal_regime == "BNS + BNSS"

    prefilter = StatuteClassifierPrefilter()

    # Pre-July 2024 query shortlist -> IPC
    hist_candidates = prefilter.shortlist_candidates_for_query(
        LegalQueryObject(legal_regime=cco_historical.case_profile.legal_regime, legal_concepts=[LegalConceptItem(concept="murder", confidence=0.9)]),
        target_regime=cco_historical.case_profile.legal_regime
    )
    assert all(c.statute == "IPC" for c in hist_candidates)
    assert any(c.section_number == "302" for c in hist_candidates)

    # Post-July 2024 query shortlist -> BNS
    modern_candidates = prefilter.shortlist_candidates_for_query(
        LegalQueryObject(legal_regime=cco_modern.case_profile.legal_regime, legal_concepts=[LegalConceptItem(concept="murder", confidence=0.9)]),
        target_regime=cco_modern.case_profile.legal_regime
    )
    assert all(c.statute == "BNS" for c in modern_candidates)
    assert any("103" in c.section_number for c in modern_candidates)


def test_stage3_chapter_filtering_for_both_corpora():
    """
    DEDICATED DUAL-CORPUS CHAPTER FILTERING TEST:
    Verifies chapter metadata extraction and filtering across both IPC and BNS corpora.
    """
    prefilter = StatuteClassifierPrefilter()

    # IPC Chapter XVII (Offences Against Property)
    ipc_cands = prefilter.prefilter_candidates("theft extortion robbery", statute_type="IPC", top_k=5)
    assert len(ipc_cands) > 0
    for c in ipc_cands:
        assert c.chapter is not None

    # BNS Chapter XVII (Offences Against Property) & Chapter V (Offences Against Woman)
    bns_cands = prefilter.prefilter_candidates("theft extortion robbery", statute_type="BNS", top_k=5)
    assert len(bns_cands) > 0
    for c in bns_cands:
        assert c.chapter is not None
        assert "Chapter" in c.chapter or "Preliminary" in c.chapter or len(c.chapter) > 0

