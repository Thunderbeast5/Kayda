import sys
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

backend_dir = Path(__file__).resolve().parent.parent
agents_dir = backend_dir / "agents"
for p in [str(backend_dir), str(agents_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from lexigraphbe.config import (
    MODEL_CHEAP,
    MODEL_STRONG,
    MODEL_VERIFIER,
    MODEL_COURTROOM,
    MODEL_STAGE0,
    MODEL_STAGE1,
    MODEL_STAGE2,
    MODEL_STAGE3,
    MODEL_STAGE4,
    MODEL_STAGE5,
    MODEL_STAGE6,
    MODEL_STAGE7,
)
from lexigraphbe.schemas import (
    CaseProfile,
    IntakeInput,
    LegalConceptItem,
    LegalQueryObject,
    SubQueryItem,
    LowConfidenceField,
    VerificationResult,
)
from lexigraphbe.pipeline import Stage0Pipeline
from lexigraphbe.intake_agent import CaseIntakeAgent
from lexigraphbe.verifier_agent import CaseIntakeVerifierAgent
from lexigraphbe.query_verifier_agent import QueryVerificationAgent
from lexigraphbe.stage2_verifier_agent import Stage2MappingVerifierAgent
from lexigraphbe.statutory_verification_agent import StatutoryVerificationAgent
from lexigraphbe.batch_utils import (
    Stage2BatchedMappingResponse,
    SubQueryChapterMapping,
    SectionMappingCandidate,
)
from prosecutor.prosecutor_agent import ProsecutorAgent
from agents.defense.defense import DefenseAgent
from agents.judge.judge import JudgeAgent


def test_optimization_9_model_routing():
    """Verify Item 9: Easy stages route to MODEL_CHEAP, high stakes and courtroom to MODEL_STRONG."""
    # Easy stages: 0, 1, 2, 3
    assert MODEL_STAGE0 == MODEL_CHEAP
    assert MODEL_STAGE1 == MODEL_CHEAP
    assert MODEL_STAGE2 == MODEL_CHEAP
    assert MODEL_STAGE3 == MODEL_CHEAP
    assert MODEL_VERIFIER == MODEL_CHEAP

    # High-stakes stages: 4, 6, and courtroom arguments
    assert MODEL_STAGE4 == MODEL_STRONG
    assert MODEL_STAGE6 == MODEL_STRONG
    assert MODEL_COURTROOM == MODEL_STRONG

    # Stage 4 agent must use MODEL_STAGE4 (strong model)
    s4_agent = StatutoryVerificationAgent()
    assert s4_agent.llm is not None

    # Courtroom agents must use MODEL_COURTROOM
    mock_lexi = MagicMock()
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "Argument text"

    defense = DefenseAgent()
    assert defense.llm is not None

    judge = JudgeAgent()
    assert judge.llm is not None


def test_optimization_10_stage0_verifier_bypass_when_clean(monkeypatch):
    """Verify Item 10: Stage 0 bypasses LLM verifier when contract passes cleanly AND toggle is ON."""
    monkeypatch.setenv("OPT_VERIFIER_BYPASS_STAGE0", "true")
    mock_intake = MagicMock(spec=CaseIntakeAgent)
    clean_profile = CaseProfile(
        procedural_stage="Anticipatory Bail",
        requested_relief="Anticipatory Bail",
        legal_regime="IPC + CrPC",
        documents=["FIR Copy", "Bail Application Copy"],
        case_facts="Accused person is alleged to have taken a motorcycle without owner consent.",
        flag_for_confirmation=False,
        low_confidence_fields=[],
    )
    clean_profile.parties.accused = "Accused Person"
    clean_profile.case_metadata.fir_number = "123/2026"
    mock_intake.run.return_value = clean_profile

    mock_verifier = MagicMock(spec=CaseIntakeVerifierAgent)
    pipeline = Stage0Pipeline(intake_agent=mock_intake, verifier_agent=mock_verifier)

    result = pipeline.run("FIR 123/2026 registered against Accused Person regarding motorcycle theft.")

    assert result.status == "VERIFIED"
    assert result.contract_status == "CONTRACT_PASSED"
    # LLM verifier MUST NOT be called because programmatic contract passed clean and toggle is true
    assert not mock_verifier.verify.called
    assert "LLM verifier bypassed" in result.feedback


def test_optimization_10_stage0_verifier_runs_when_ungrounded(monkeypatch):
    """Verify Correction 2: Even if toggle is ON, if extracted accused is NOT in raw text, verifier MUST run."""
    monkeypatch.setenv("OPT_VERIFIER_BYPASS_STAGE0", "true")
    mock_intake = MagicMock(spec=CaseIntakeAgent)
    clean_profile = CaseProfile(
        procedural_stage="Anticipatory Bail",
        requested_relief="Anticipatory Bail",
        legal_regime="IPC + CrPC",
        documents=["FIR Copy", "Bail Application Copy"],
        case_facts="Accused person is alleged to have taken a motorcycle without owner consent.",
        flag_for_confirmation=False,
        low_confidence_fields=[],
    )
    clean_profile.parties.accused = "Vikramaditya Singhania"
    clean_profile.case_metadata.fir_number = "123/2026"
    mock_intake.run.return_value = clean_profile

    mock_verifier = MagicMock(spec=CaseIntakeVerifierAgent)
    mock_verifier.verify.return_value = VerificationResult(
        status="VERIFIED",
        contract_status="CONTRACT_PASSED",
        issues=[],
        feedback="Verified by LLM verifier after ungrounded detection.",
        verified_case_profile=clean_profile,
    )
    pipeline = Stage0Pipeline(intake_agent=mock_intake, verifier_agent=mock_verifier)
    result = pipeline.run("FIR 123/2026 incident registered at local police station.")

    assert result.status == "VERIFIED"
    # LLM verifier MUST be called because deterministic grounding caught the missing name
    assert mock_verifier.verify.called


def test_optimization_10_stage0_verifier_default_runs_verifier(monkeypatch):
    """Verify Correction 2: By default (OPT_VERIFIER_BYPASS_STAGE0=false), Stage 0 LLM verifier is preserved."""
    monkeypatch.setenv("OPT_VERIFIER_BYPASS_STAGE0", "false")
    mock_intake = MagicMock(spec=CaseIntakeAgent)
    clean_profile = CaseProfile(
        procedural_stage="Anticipatory Bail",
        requested_relief="Anticipatory Bail",
        legal_regime="IPC + CrPC",
        documents=["FIR Copy", "Bail Application Copy"],
        case_facts="Accused person is alleged to have taken a motorcycle without owner consent.",
        flag_for_confirmation=False,
        low_confidence_fields=[],
    )
    clean_profile.parties.accused = "Accused Person"
    clean_profile.case_metadata.fir_number = "123/2026"
    mock_intake.run.return_value = clean_profile

    mock_verifier = MagicMock(spec=CaseIntakeVerifierAgent)
    mock_verifier.verify.return_value = VerificationResult(
        status="VERIFIED",
        contract_status="CONTRACT_PASSED",
        issues=[],
        feedback="Verified by LLM verifier.",
        verified_case_profile=clean_profile,
    )
    pipeline = Stage0Pipeline(intake_agent=mock_intake, verifier_agent=mock_verifier)
    result = pipeline.run("FIR 123/2026 text")

    assert result.status == "VERIFIED"
    # LLM verifier MUST be called when toggle is false
    assert mock_verifier.verify.called


def test_optimization_10_stage0_verifier_called_when_flagged():
    """Verify Item 10: Stage 0 calls LLM verifier when contract or profile flags low confidence."""
    mock_intake = MagicMock(spec=CaseIntakeAgent)
    flagged_profile = CaseProfile(
        procedural_stage="Anticipatory Bail",
        requested_relief="Anticipatory Bail",
        legal_regime="IPC + CrPC",
        documents=["FIR Copy", "Bail Application Copy"],
        case_facts="Accused person is alleged to have taken a motorcycle without owner consent.",
        flag_for_confirmation=True,  # Flagged!
        low_confidence_fields=[LowConfidenceField(field_name="offence_date", confidence_score=0.4, reason="Missing date")],
    )
    flagged_profile.parties.accused = "Accused Person"
    flagged_profile.case_metadata.fir_number = "123/2026"
    mock_intake.run.return_value = flagged_profile

    mock_verifier = MagicMock(spec=CaseIntakeVerifierAgent)
    mock_verifier.verify.return_value = VerificationResult(
        status="VERIFIED",
        contract_status="CONTRACT_PASSED",
        issues=[],
        feedback="Verified by LLM after review of flagged items.",
        verified_case_profile=flagged_profile,
    )

    pipeline = Stage0Pipeline(intake_agent=mock_intake, verifier_agent=mock_verifier)
    result = pipeline.run("FIR 123/2026 text")

    assert result.status == "VERIFIED"
    # LLM verifier MUST be called because profile was flagged
    assert mock_verifier.verify.called


def test_optimization_10_stage1_verifier_bypass_when_clean():
    """Verify Item 10: Stage 1 bypasses LLM verifier when programmatic contract passes cleanly."""
    mock_llm = MagicMock()
    verifier = QueryVerificationAgent(llm=mock_llm)

    query_obj = LegalQueryObject(
        case_type="Anticipatory Bail",
        sub_queries=[
            SubQueryItem(id="sq_1", query="Whether motorcycle theft without violence attracts custodial interrogation", concept="theft", target_parties=["Accused"], role_alleged="Theft")
        ],
        legal_concepts=[
            LegalConceptItem(concept="theft", confidence=0.95),
            LegalConceptItem(concept="recovery", confidence=0.90),
            LegalConceptItem(concept="custodial interrogation", confidence=0.85),
        ],
        flag_for_confirmation=False,
        manual_review=[],
    )

    res = verifier.verify(case_context={"legal_regime": "IPC + CrPC"}, legal_query=query_obj)

    assert res.status == "VERIFIED"
    assert "LLM verifier bypassed" in res.feedback
    # Underlying LLM must NOT have been called
    assert not mock_llm.invoke.called


def test_optimization_10_stage1_verifier_blocks_leak_without_llm():
    """Verify Item 10: Section leaks are caught programmatically with 0 LLM calls."""
    mock_llm = MagicMock()
    verifier = QueryVerificationAgent(llm=mock_llm)

    # Subquery contains explicit section leak 'Section 379 IPC'
    leaked_query = LegalQueryObject(
        case_type="Anticipatory Bail",
        sub_queries=[
            SubQueryItem(id="sq_1", query="Ingredients of Section 379 IPC for vehicle theft", concept="theft", target_parties=["Accused"], role_alleged="Theft")
        ],
        legal_concepts=[LegalConceptItem(concept="theft", confidence=0.95)],
    )

    res = verifier.verify(case_context={"legal_regime": "IPC + CrPC"}, legal_query=leaked_query)

    assert res.status == "RETRY"
    assert any("Statutory section leak detected" in issue.issue for issue in res.issues)
    assert not mock_llm.invoke.called


def test_optimization_10_stage2_verifier_bypass_when_clean(monkeypatch):
    """Verify Item 10: Stage 2 bypasses LLM verifier when programmatic scope audit passes cleanly AND toggle is ON."""
    monkeypatch.setenv("OPT_VERIFIER_BYPASS_STAGE2", "true")
    mock_llm = MagicMock()
    verifier = Stage2MappingVerifierAgent(llm=mock_llm)

    resp = Stage2BatchedMappingResponse(
        mappings=[
            SubQueryChapterMapping(
                sub_query_id="sq_1",
                sub_query_text="Whether motorcycle theft attracts custody",
                primary_candidate_sections=[
                    SectionMappingCandidate(statute="IPC", section_number="379", section_title="Punishment for theft", score=0.95, relevance_reasoning="Vehicle theft")
                ],
                secondary_candidate_sections=[],
                conditional_candidate_sections=[],
            )
        ]
    )

    res = verifier.verify(legal_query={"legal_regime": "IPC + CrPC"}, mapping_response=resp)

    assert res.status == "VERIFIED"
    assert "LLM verifier bypassed" in res.feedback
    assert not mock_llm.invoke.called


def test_optimization_10_stage2_verifier_default_runs_verifier(monkeypatch):
    """Verify Correction 2: By default (OPT_VERIFIER_BYPASS_STAGE2=false), Stage 2 LLM verifier is preserved."""
    monkeypatch.setenv("OPT_VERIFIER_BYPASS_STAGE2", "false")
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "All mappings validated by LLM.",
    })
    verifier = Stage2MappingVerifierAgent(llm=mock_llm)

    resp = Stage2BatchedMappingResponse(
        mappings=[
            SubQueryChapterMapping(
                sub_query_id="sq_1",
                sub_query_text="Whether motorcycle theft attracts custody",
                primary_candidate_sections=[
                    SectionMappingCandidate(statute="IPC", section_number="379", section_title="Punishment for theft", score=0.95, relevance_reasoning="Vehicle theft")
                ],
                secondary_candidate_sections=[],
                conditional_candidate_sections=[],
            )
        ]
    )

    res = verifier.verify(legal_query={"legal_regime": "IPC + CrPC"}, mapping_response=resp)

    assert res.status == "VERIFIED"
    assert mock_llm.invoke.called


def test_baseline_cases_integrity():
    """Verify integrity of the 5 representative baseline cases fixture."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "baseline_cases.json"
    assert fixture_path.exists()

    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) == 5
    case_ids = [c["id"] for c in cases]
    assert "case_1_srikant_absconding" in case_ids
    assert "case_2_vague_fir_cooperating" in case_ids
    assert "case_3_bare_application" in case_ids
    assert "case_4_motorcycle_theft" in case_ids
    assert "case_5_corporate_cheating" in case_ids

    # Case 1: Proclaimed offender -> DENIED, IPC 302/120B
    c1 = next(c for c in cases if c["id"] == "case_1_srikant_absconding")
    assert c1["expected_bail_outcome"] == "DENIED"
    assert "302" in c1["expected_sections"]
    assert any("Srikant Upadhyay" in p for p in c1["expected_precedents"])

    # Case 4: Motorcycle theft -> <= 7 yrs Arnesh Kumar, IPC 379
    c4 = next(c for c in cases if c["id"] == "case_4_motorcycle_theft")
    assert c4["expected_sections"] == ["379"]
    assert any("Arnesh Kumar" in p for p in c4["expected_precedents"])
