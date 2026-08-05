"""
Pytest unit test suite for LexiGraph Stage 0: Case Intake & Context Initialization.
"""

import json
from unittest.mock import MagicMock
import pytest

from lexigraphbe.config import GLOBAL_CALL_GUARDRAIL, extract_json_from_text


@pytest.fixture(autouse=True)
def reset_call_guardrail():
    GLOBAL_CALL_GUARDRAIL.reset()
    yield
    GLOBAL_CALL_GUARDRAIL.reset()
from lexigraphbe.schemas import (
    AccusedParty,
    CaseContextObject,
    CaseMetadata,
    CaseProfile,
    IntakeInput,
    LowConfidenceField,
    Parties,
    PrimaryParticipants,
    VerificationResult,
)
from lexigraphbe.intake_agent import CaseIntakeAgent
from lexigraphbe.verifier_agent import CaseIntakeVerifierAgent
from lexigraphbe.pipeline import Stage0Pipeline


def test_schemas_defaults_and_validation():
    profile = CaseProfile()
    assert profile.procedural_stage == "UNKNOWN"
    assert profile.requested_relief == "UNKNOWN"
    assert profile.legal_regime == "UNKNOWN"
    assert profile.flag_for_confirmation is False
    assert profile.min_confidence_threshold == 0.70
    assert profile.low_confidence_fields == []
    assert profile.documents == []
    assert profile.missing_information == []

    # Test serialization and dict export
    d = profile.model_dump()
    assert "case_metadata" in d
    assert "parties" in d
    assert "confidence" in d
    assert "low_confidence_fields" in d
    assert "min_confidence_threshold" in d
    assert "contract_status" in d
    assert "contract_violations" in d

    # Test re-hydration
    restored = CaseProfile.model_validate(d)
    assert restored.procedural_stage == "UNKNOWN"


def test_extract_json_from_text():
    # Plain JSON
    raw_plain = '{"key": "value"}'
    assert extract_json_from_text(raw_plain) == {"key": "value"}

    # Markdown fenced JSON
    raw_fenced = """Here is the result:
```json
{
  "procedural_stage": "Anticipatory Bail",
  "legal_regime": "BNS + BNSS"
}
```
"""
    extracted = extract_json_from_text(raw_fenced)
    assert extracted["procedural_stage"] == "Anticipatory Bail"
    assert extracted["legal_regime"] == "BNS + BNSS"


def test_intake_agent_with_mock_llm():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "case_metadata": {
            "case_id": "FIR-2025-99",
            "fir_number": "123/2025",
            "fir_date": "15/01/2025",
            "offence_date": "10/06/2024",
            "police_station": "Nashik Road",
            "court": "Sessions Court",
            "state": "Maharashtra"
        },
        "parties": {
            "complainant": "Wife",
            "accused": "Husband",
            "relationship": "Married"
        },
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "IPC + CrPC",
        "flag_for_confirmation": False,
        "regime_notes": "Offence date 10/06/2024 (pre-July 1 2024) controls per Art 20(1)",
        "documents": ["FIR", "Bail Application"],
        "case_facts": "The applicant seeks anticipatory bail regarding FIR 123/2025.",
        "primary_participants": {
            "accused": ["Husband"],
            "victim": ["Wife"]
        },
        "missing_information": ["Medical Report"],
        "confidence": {
            "procedural_stage": 0.99,
            "legal_regime": 0.95
        }
    })
    mock_llm.invoke.return_value = mock_response

    agent = CaseIntakeAgent(llm=mock_llm)
    inp = IntakeInput(documents_text="FIR No 123/2025. Incident took place June 10, 2024.")
    profile = agent.run(inp)

    assert profile.case_metadata.fir_number == "123/2025"
    assert profile.case_metadata.offence_date == "10/06/2024"
    assert profile.legal_regime == "IPC + CrPC"
    assert profile.flag_for_confirmation is False
    assert "Medical Report" in profile.missing_information
    assert profile.overall_confidence == 0.97


def test_procedural_missing_documents_check():
    # Test checking universal baseline document checklist without premature offence inferencing
    profile = CaseProfile(documents=["Written Submissions"])
    missing = profile.check_procedural_missing_documents()
    assert len(missing) == 2
    assert any("FIR / Complaint Copy" in item for item in profile.missing_information)
    assert any("Bail Application Copy" in item for item in profile.missing_information)


def test_confidence_cutoff_behavior():
    mock_llm = MagicMock()
    # Mock LLM returning confidence score 0.45 for procedural_stage (below 0.70 threshold)
    mock_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {
            "fir_number": "789/2025",
            "fir_date": "10/08/2024",
            "offence_date": "05/08/2024"
        },
        "procedural_stage": "Investigation",
        "legal_regime": "BNS + BNSS",
        "documents": ["FIR Copy", "Bail Application Copy"],
        "confidence": {
            "procedural_stage": 0.45,
            "legal_regime": 0.90
        }
    })

    agent = CaseIntakeAgent(llm=mock_llm)
    profile = agent.run(IntakeInput(documents_text="Vague document text", min_confidence_threshold=0.70))

    # Assert cutoff action was triggered
    assert profile.flag_for_confirmation is True
    assert len(profile.low_confidence_fields) == 1
    low_conf = profile.low_confidence_fields[0]
    assert low_conf.field_name == "procedural_stage"
    assert low_conf.confidence_score == 0.45
    assert low_conf.cutoff_threshold == 0.70
    assert any("procedural_stage" in msg and "low confidence" in msg for msg in profile.missing_information)


def test_stage1_hard_contract_validation():
    # 1. Valid Profile Passing Contract
    valid_profile = CaseProfile(
        parties=Parties(accused="John Doe"),
        case_facts="Detailed narrative of alleged offence.",
        requested_relief="Anticipatory Bail",
        procedural_stage="Anticipatory Bail",
        legal_regime="BNS + BNSS",
    )
    status, violations = valid_profile.validate_stage1_contract()
    assert status == "CONTRACT_PASSED"
    assert len(violations) == 0

    # 2. Incomplete Profile Blocked by Contract
    invalid_profile = CaseProfile(
        parties=Parties(accused=None), # Missing accused identity
        case_facts="",                 # Missing narrative
        requested_relief="UNKNOWN",    # Missing relief
        procedural_stage="Anticipatory Bail",
        legal_regime="BNS + BNSS",
    )
    status2, violations2 = invalid_profile.validate_stage1_contract()
    assert status2 == "CONTRACT_BLOCKED"
    assert len(violations2) >= 3
    assert any("accused_identity" in v for v in violations2)
    assert any("offence_narrative" in v for v in violations2)
    assert any("requested_relief" in v for v in violations2)


def test_multi_party_accused_handling():
    # Test array of accused objects (e.g. dowry case with husband + in-laws)
    multi_accused = [
        AccusedParty(name="Ramesh (Husband)", relationship="Husband", role_alleged="Main Accused"),
        AccusedParty(name="Suresh (Father-in-law)", relationship="Father-in-law", role_alleged="Co-Accused"),
        AccusedParty(name="Kamla (Mother-in-law)", relationship="Mother-in-law", role_alleged="Co-Accused"),
    ]
    profile = CaseProfile(
        parties=Parties(accused=multi_accused),
        case_facts="Allegations of dowry demand and harassment under section 498A/304B.",
        requested_relief="Anticipatory Bail",
        procedural_stage="Anticipatory Bail",
        legal_regime="IPC + CrPC",
    )

    accused_list = profile.get_accused_list()
    assert len(accused_list) == 3
    assert "Ramesh (Husband)" in accused_list
    assert "Suresh (Father-in-law)" in accused_list
    assert "Kamla (Mother-in-law)" in accused_list

    status, violations = profile.validate_stage1_contract()
    assert status == "CONTRACT_PASSED"
    assert len(violations) == 0


def test_case_context_object_export():
    profile = CaseProfile(
        parties=Parties(accused=["Husband", "Father-in-law"]),
        case_facts="Detailed narrative of dowry harassment and cruelty.",
        requested_relief="Anticipatory Bail",
        procedural_stage="Anticipatory Bail",
        legal_regime="BNS + BNSS",
    )
    vr = VerificationResult(
        status="VERIFIED",
        verified_case_profile=profile
    )

    cco = vr.export_case_context_object()
    assert cco.schema_version == "1.0"
    assert cco.contract_status == "CONTRACT_PASSED"
    assert cco.verification_status == "VERIFIED"
    assert len(cco.active_parties) == 2
    assert "Husband" in cco.active_parties
    assert "intake_timestamp" in cco.system_metadata

    json_str = cco.to_downstream_json()
    assert "schema_version" in json_str
    assert "case_profile" in json_str


def test_regime_precedence_rules():
    # Case 1: Offence pre-July 2024, FIR post-July 2024 -> IPC + CrPC controlling
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {
            "fir_number": "123/2025",
            "fir_date": "10/01/2025",
            "offence_date": "15/05/2024"
        },
        "legal_regime": "IPC + CrPC",
        "flag_for_confirmation": False,
        "regime_notes": "Offence committed May 15, 2024 (pre-July 1 2024) -> IPC + CrPC controls under Art 20(1)."
    })
    agent = CaseIntakeAgent(llm=mock_llm)
    profile = agent.run("Incident on 15 May 2024, FIR registered 10 Jan 2025.")
    assert profile.legal_regime == "IPC + CrPC"
    assert profile.flag_for_confirmation is False

    # Case 2: Offence date missing, FIR date fallback -> flag_for_confirmation = True
    mock_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {
            "fir_number": "123/2025",
            "fir_date": "10/08/2024",
            "offence_date": None
        },
        "legal_regime": "BNS + BNSS",
        "flag_for_confirmation": True,
        "regime_notes": "Offence date unstated; FIR date fallback applied."
    })
    profile2 = agent.run("FIR date 10 August 2024.")
    assert profile2.legal_regime == "BNS + BNSS"
    assert profile2.flag_for_confirmation is True

    # Case 3: Both dates missing -> UNKNOWN, flag_for_confirmation = True, missing_information populated
    mock_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {
            "fir_number": None,
            "fir_date": None,
            "offence_date": None
        },
        "legal_regime": "UNKNOWN",
        "flag_for_confirmation": True,
        "missing_information": []
    })
    profile3 = agent.run("Complaint details without any dates.")
    assert profile3.legal_regime == "UNKNOWN"
    assert profile3.flag_for_confirmation is True
    assert any("Legal regime confirmation" in item for item in profile3.missing_information)


def test_verifier_agent_verified_with_mock_llm():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "All extracted fields supported by source documents."
    })
    mock_llm.invoke.return_value = mock_response

    verifier = CaseIntakeVerifierAgent(llm=mock_llm)
    profile = CaseProfile(
        procedural_stage="Anticipatory Bail",
        legal_regime="BNS + BNSS"
    )
    result = verifier.verify("Raw FIR document text", profile)

    assert result.status == "VERIFIED"
    assert len(result.issues) == 0
    assert result.verified_case_profile is not None


def test_verifier_agent_correction_needed_with_mock_llm():
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "status": "NEEDS_CORRECTION",
        "issues": [
            {
                "field": "legal_regime",
                "issue": "Offence date was May 2024, should be IPC + CrPC controlling under Art 20(1), not BNS + BNSS.",
                "feedback": "Change legal_regime to IPC + CrPC because offence date precedes July 1, 2024."
            }
        ],
        "feedback": "Legal regime precedence error."
    })
    mock_llm.invoke.return_value = mock_response

    verifier = CaseIntakeVerifierAgent(llm=mock_llm)
    profile = CaseProfile(legal_regime="BNS + BNSS")
    result = verifier.verify("Offence committed May 2024, FIR filed Aug 2024", profile)

    assert result.status == "NEEDS_CORRECTION"
    assert len(result.issues) == 1
    assert result.issues[0].field == "legal_regime"


def test_stage0_pipeline_flow():
    # Mock intake agent
    mock_intake_llm = MagicMock()
    mock_intake_llm.invoke.return_value.content = json.dumps({
        "case_metadata": {"fir_number": "456/2025", "offence_date": "10/08/2024"},
        "parties": {"accused": "Accused Person"},
        "procedural_stage": "Anticipatory Bail",
        "requested_relief": "Anticipatory Bail",
        "legal_regime": "BNS + BNSS",
        "documents": ["FIR Copy", "Bail Application Copy"],
        "case_facts": "Fact narrative.",
        "missing_information": [],
        "confidence": {"procedural_stage": 0.9}
    })

    # Mock verifier agent
    mock_verifier_llm = MagicMock()
    mock_verifier_llm.invoke.return_value.content = json.dumps({
        "status": "VERIFIED",
        "issues": [],
        "feedback": "Verified cleanly."
    })

    intake_agent = CaseIntakeAgent(llm=mock_intake_llm)
    verifier_agent = CaseIntakeVerifierAgent(llm=mock_verifier_llm)

    pipeline = Stage0Pipeline(intake_agent=intake_agent, verifier_agent=verifier_agent)
    res = pipeline.run("FIR 456/2025")

    assert res.status == "VERIFIED"
    assert res.contract_status == "CONTRACT_PASSED"
    assert res.verified_case_profile.case_metadata.fir_number == "456/2025"

    cco = res.export_case_context_object()
    assert cco.schema_version == "1.0"
    assert cco.contract_status == "CONTRACT_PASSED"
