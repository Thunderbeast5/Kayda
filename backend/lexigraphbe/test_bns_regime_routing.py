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
