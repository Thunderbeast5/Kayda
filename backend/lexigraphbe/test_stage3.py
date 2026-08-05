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
    PunishmentSpec,
    SectionCandidateItem,
    SubQueryItem,
    VerifiedOffenceItem,
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


def test_chapter_identification_object_schema_v3():
    vo = VerifiedOffenceItem(
        section_number="498A",
        statute="IPC",
        ipc_equivalent="498A",
        bns_equivalent="85",
        title="Cruelty by Husband or Relatives of Husband",
        chapter_number="XXA",
        chapter_title="Of Cruelty by Husband or Relatives of Husband",
        punishment=PunishmentSpec(minimum=None, maximum="3 Years", fine=True),
        classification="PRIMARY",
        cognizable=True,
        bailable=False,
        verification_status="VERIFIED",
        verification_notes=["Title verified.", "Punishment verified."]
    )

    cio = ChapterIdentificationObject(
        schema_version="3.0",
        verified_offences=[vo],
        legal_regime="IPC + CrPC"
    )

    d = cio.model_dump()
    assert d["schema_version"] == "3.0"
    assert d["legal_regime"] == "IPC + CrPC"
    assert len(d["verified_offences"]) == 1
    assert d["verified_offences"][0]["bns_equivalent"] == "85"
    assert d["verified_offences"][0]["punishment"]["maximum"] == "3 Years"

    restored = ChapterIdentificationObject.model_validate(d)
    assert len(restored.verified_offences) == 1
    assert restored.verified_offences[0].ipc_equivalent == "498A"

    # Backward compatibility properties
    assert len(restored.section_candidates) == 1
    assert restored.section_candidates[0].section_number == "498A"


def test_stage3_ipc_bns_normalization_and_stage2_consumption():
    """
    Verifies that Stage 3 consumes Stage 2 candidate mapping, resolves IPC <-> BNS equivalents,
    and deduplicates equivalent sections into a single normalized offence item.
    """
    from lexigraphbe.batch_utils import SectionMappingCandidate, Stage2BatchedMappingResponse, SubQueryChapterMapping

    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "3.0",
        "verified_offences": [
            {
                "section_number": "498A",
                "statute": "IPC",
                "ipc_equivalent": "498A",
                "bns_equivalent": "85",
                "title": "Cruelty by Husband or Relatives of Husband",
                "chapter_number": "XXA",
                "chapter_title": "Of Cruelty by Husband or Relatives of Husband",
                "punishment": {"minimum": None, "maximum": "3 Years", "fine": True},
                "classification": "PRIMARY",
                "cognizable": True,
                "bailable": False,
                "verification_status": "VERIFIED",
                "verification_notes": ["Title verified."]
            },
            {
                "section_number": "85",
                "statute": "BNS",
                "ipc_equivalent": "498A",
                "bns_equivalent": "85",
                "title": "Cruelty by Husband or Relatives of Husband",
                "chapter_number": "V",
                "chapter_title": "Of Offences Against Woman",
                "punishment": {"minimum": None, "maximum": "3 Years", "fine": True},
                "classification": "PRIMARY",
                "cognizable": True,
                "bailable": False,
                "verification_status": "VERIFIED",
                "verification_notes": ["BNS mapped."]
            }
        ],
        "manual_review": [],
        "verification_status": "VERIFIED"
    })

    agent = ChapterIdentificationAgent(llm=mock_llm)
    query_obj = LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Cruelty", confidence=0.95)])
    stage2_resp = Stage2BatchedMappingResponse(mappings=[
        SubQueryChapterMapping(
            sub_query_id="SQ1",
            sub_query_text="Harassment for dowry",
            primary_candidate_sections=[
                SectionMappingCandidate(section_number="498A", section_title="Cruelty", candidate_type="PRIMARY")
            ]
        )
    ])

    res = agent.run(legal_query=query_obj, stage2_mapping=stage2_resp)

    # Assert IPC 498A and BNS 85 duplicate items were merged into a single normalized VerifiedOffenceItem
    assert len(res.verified_offences) == 1
    assert res.verified_offences[0].ipc_equivalent == "498A"
    assert res.verified_offences[0].bns_equivalent == "85"


def test_stage3_unknown_regime_manual_review_warning():
    """
    Verifies that if legal_regime is UNKNOWN, Stage 3 flags manual_review warning.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "schema_version": "3.0",
        "verified_offences": [
            {
                "section_number": "498A",
                "statute": "IPC",
                "ipc_equivalent": "498A",
                "bns_equivalent": "85",
                "title": "Cruelty by Husband",
                "chapter_number": "XXA",
                "chapter_title": "Of Cruelty",
                "punishment": {"minimum": None, "maximum": "3 Years", "fine": True},
                "classification": "PRIMARY",
                "cognizable": True,
                "bailable": False,
                "verification_status": "VERIFIED",
                "verification_notes": []
            }
        ],
        "manual_review": [],
        "verification_status": "VERIFIED"
    })

    agent = ChapterIdentificationAgent(llm=mock_llm)
    query_obj = LegalQueryObject(legal_regime="UNKNOWN", legal_concepts=[LegalConceptItem(concept="Cruelty", confidence=0.95)])

    res = agent.run(legal_query=query_obj)

    assert "UNKNOWN legal regime" in res.manual_review[0]
    assert res.verified_offences[0].statute == "IPC / BNS"


def test_stage3_score_inversion_fix_non_fatal_dowry_query():
    """
    Verifies that for a non-fatal dowry cruelty query (death absent):
    - 498A / 85 BNS gets top confidence (0.95+) and PRIMARY classification.
    - 304B (Dowry Death) is screened out via fatal disqualification and gets 0.0 confidence (NOT_TRIGGERED).
    """
    agent = ChapterIdentificationAgent()

    qo = LegalQueryObject(
        legal_regime="IPC + CrPC",
        legal_concepts=[
            LegalConceptItem(concept="Dowry Demand", confidence=0.95),
            LegalConceptItem(concept="Cruelty by Husband", confidence=0.95),
        ],
        sub_queries=[
            SubQueryItem(id="SQ1", query="The husband and his family continuously demanded dowry and subjected the wife to cruelty. She has filed an FIR and the accused is seeking anticipatory bail.", concept="Dowry Demand", target_parties=["Husband"])
        ]
    )

    cio = agent.run(qo)

    # 498A should be VERIFIED with PRIMARY status & 0.95 confidence
    offence_498a = next((vo for vo in cio.verified_offences if vo.section_number == "498A"), None)
    assert offence_498a is not None
    assert offence_498a.verification_status == "VERIFIED"
    assert offence_498a.classification == "PRIMARY"

    # Section candidate for 498A should have top score >= 0.95
    cand_498a = next((c for c in cio.section_candidates if c.section_number == "498A"), None)
    assert cand_498a is not None
    assert cand_498a.confidence >= 0.95

    # Special Act (Section 4 Dowry Prohibition Act) should be surfaced concurrently
    offence_dp4 = next((vo for vo in cio.verified_offences if "Section 4" in vo.section_number or "Dowry Prohibition" in vo.statute), None)
    assert offence_dp4 is not None
    assert offence_dp4.statute == "Dowry Prohibition Act"

    # 304B (Dowry death) should NOT be PRIMARY (disqualified due to missing death trigger)
    offence_304b = next((vo for vo in cio.verified_offences if vo.section_number == "304B"), None)
    if offence_304b:
        assert offence_304b.verification_status == "NOT_TRIGGERED"
        cand_304b = next((c for c in cio.section_candidates if c.section_number == "304B"), None)
        if cand_304b:
            assert cand_304b.confidence == 0.0

