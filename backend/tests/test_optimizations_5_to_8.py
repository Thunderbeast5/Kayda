import pytest
import json
from agents.orchestrator.formatting import summarize_transcript_history
from agents.orchestrator.state import Turn
from prosecutor.prosecutor_agent import ProsecutorAgent, MAX_CORRECTION_ATTEMPTS
from agents.orchestrator.orchestrator_graph import MAX_CITATION_RETRIES
from agents.evidence.evidence_analyzer import extract_facts_and_inventory
from lexigraphbe.stage_slices import (
    get_stage1_slice,
    get_stage3_slice,
    get_stage5_slices,
    get_stage6_slices,
    compact_json,
)


def test_optimization_5_collapsed_retries():
    """Item 5: Collapsed nested retries and targeted repair prompt."""
    assert MAX_CORRECTION_ATTEMPTS == 1, "Prosecutor correction attempts must be capped at 1"
    assert MAX_CITATION_RETRIES == 1, "Orchestrator citation retries must be capped at 1"

    # Test targeted repair prompt in ProsecutorAgent
    agent = ProsecutorAgent.__new__(ProsecutorAgent)
    prompt = agent._correction_prompt({
        "hallucinated_sections": ["IPC 999"],
        "unverified_cases": ["Fake v. State"],
    })
    assert "TARGETED REPAIR REQUIRED" in prompt
    assert "Do NOT regenerate the response from scratch" in prompt
    assert "IPC 999" in prompt
    assert "Fake v. State" in prompt


def test_optimization_6_typed_stage_slices():
    """Item 6: Slices give each stage only the extracted fields it needs."""
    # Test Stage 1 slice drops bulky debug data & raw documents
    mock_stage0 = {
        "case_profile": {
            "case_facts": "Accused attacked victim with a stick causing hurt.",
            "parties": {"accused": [{"name": "A1"}], "victim": "V1"},
            "procedural_stage": "Anticipatory Bail",
            "requested_relief": "Anticipatory Bail",
            "legal_regime": "IPC + CrPC",
            "low_confidence_fields": [{"field": "test", "score": 0.5}],  # Should be dropped
            "documents_text": "A" * 5000,  # Should be dropped
        },
        "system_metadata": {"intake_time": "2026-10-13"},  # Should be dropped
    }
    s1 = get_stage1_slice(mock_stage0)
    assert s1.case_facts == "Accused attacked victim with a stick causing hurt."
    assert s1.legal_regime == "IPC + CrPC"
    dumped1 = s1.model_dump()
    assert "documents_text" not in dumped1
    assert "low_confidence_fields" not in dumped1
    assert "system_metadata" not in dumped1

    # Compact JSON format check
    compacted = compact_json(dumped1)
    assert ": " not in compacted and ", " not in compacted

    # Test Stage 3 slice
    mock_stage1 = {
        "legal_regime": "IPC + CrPC",
        "legal_concepts": [{"concept": "Voluntarily Causing Hurt"}],
        "sub_queries": [{"id": "sq_1", "legal_concept": "Hurt", "query": "Did A cause hurt?", "target_parties": ["A1"]}],
        "important_facts": {"fact1": "details"},  # Dropped from Stage 3 verifier slice
    }
    s3 = get_stage3_slice(mock_stage1)
    assert s3.legal_concepts == ["Voluntarily Causing Hurt"]
    assert len(s3.sub_queries) == 1

    # Test Stage 5 slice
    mock_stage4 = {
        "verified_offences": [{"section_number": "323", "title": "Hurt", "punishment_text": "1 year"}],
        "verification_audit": "detailed audit logs",  # Should be dropped
    }
    s0_s5, s1_s5, s4_s5 = get_stage5_slices(mock_stage0, mock_stage1, mock_stage4)
    assert s0_s5["procedural_stage"] == "Anticipatory Bail"
    assert s4_s5["verified_offences"][0]["section"] == "323"
    assert "verification_audit" not in s4_s5

    # Test Stage 6 slice
    mock_stage5 = {
        "bail_factors": {"gravity": "Low"},
        "overall_recommendation": "Grant Bail",
    }
    mock_corpus = [
        {"judgment_id": "j_1", "case_name": "State v. X", "citation": "2024 SC 1", "full_text": "B" * 5000}
    ]
    s0_s6, s1_s6, s4_s6, s5_s6, comp_corpus = get_stage6_slices(
        mock_stage0, mock_stage1, mock_stage4, mock_stage5, mock_corpus
    )
    assert comp_corpus[0]["case_name"] == "State v. X"
    assert "full_text" not in comp_corpus[0]


def test_optimization_7_reuse_stage0_in_evidence_analyzer():
    """Item 7: Reuse Stage 0 output directly in Evidence Analyzer (0 LLM calls)."""
    stage0_input = {
        "case_profile": {
            "case_facts": "FIR was registered against accused. A search was conducted and weapon recovered.",
            "documents": [
                {"document_name": "FIR Copy", "is_available": True, "description": "FIR 123/2025"},
                {"document_name": "Medical Report", "is_available": False, "description": "MLC absent"}
            ],
            "case_metadata": {"fir_number": "123/2025"}
        }
    }
    res = extract_facts_and_inventory("dummy raw text", stage0_data=stage0_input)
    assert "facts" in res and len(res["facts"]) >= 1
    assert "evidence_inventory" in res and len(res["evidence_inventory"]) >= 2
    inv_items = {item["item"]: item["status"] for item in res["evidence_inventory"]}
    assert inv_items.get("fir_copy") == "present"
    assert inv_items.get("medical_report") == "not_on_record"


def test_optimization_8_summarize_transcript_history():
    """Item 8: Keep last 1-2 turns verbatim and summarize earlier turns with argument IDs."""
    # 1. Test <= 2 turns: verbatim
    turns_short = [
        Turn(turn_no=1, speaker="prosecutor", round_no=1, content="Opening prosecution argument.", citations=["IPC 324"], evidence_refs=["fact_1"]),
        Turn(turn_no=2, speaker="defense", round_no=1, content="Opening defense argument.", citations=["CrPC 438"], evidence_refs=["fact_2"]),
    ]
    formatted_short = summarize_transcript_history(turns_short, keep_last=2)
    assert "### [PROSECUTOR — Round 1]" in formatted_short
    assert "### [DEFENSE — Round 1]" in formatted_short
    assert "SUMMARY OF EARLIER PROCEEDINGS" not in formatted_short

    # 2. Test > 2 turns: earlier summarized, last 2 verbatim
    turns_long = [
        Turn(
            turn_no=1,
            speaker="prosecutor",
            round_no=1,
            content="Full long turn 1 content with detailed prosecution speech.",
            citations=["IPC 324"],
            evidence_refs=["fact_1"],
            structured_argument={"theory": "Premeditated assault", "arguments": ["Accused attacked victim with stick [fact_1]"]}
        ),
        Turn(
            turn_no=2,
            speaker="defense",
            round_no=1,
            content="Full long turn 2 content with detailed defense speech.",
            citations=["CrPC 438"],
            evidence_refs=["fact_2"],
            structured_argument={"theory": "Absence of premeditation", "arguments": ["Concedes mutual quarrel occurred", "Contests presence of dangerous weapon"]}
        ),
        Turn(
            turn_no=3,
            speaker="prosecutor",
            round_no=2,
            content="Verbatim prosecutor turn 3 rebuttal.",
            citations=["IPC 324"],
            evidence_refs=["fact_1"]
        ),
        Turn(
            turn_no=4,
            speaker="defense",
            round_no=2,
            content="Verbatim defense turn 4 rejoinder.",
            citations=["CrPC 438"],
            evidence_refs=["fact_2"]
        ),
    ]

    formatted_long = summarize_transcript_history(turns_long, keep_last=2)
    assert "--- SUMMARY OF EARLIER PROCEEDINGS ---" in formatted_long
    assert "Turn 1 (Prosecutor, Round 1)" in formatted_long
    assert "Theory: Premeditated assault" in formatted_long
    assert "[Citations: IPC 324]" in formatted_long
    assert "[Evidence: fact_1]" in formatted_long
    assert "Turn 2 (Defense, Round 1)" in formatted_long
    assert "Conceded: Concedes mutual quarrel occurred" in formatted_long
    assert "Contested: Contests presence of dangerous weapon" in formatted_long

    # Check that recent turns are verbatim
    assert "--- RECENT PROCEEDINGS (VERBATIM) ---" in formatted_long
    assert "### [PROSECUTOR — Round 2]" in formatted_long
    assert "Verbatim prosecutor turn 3 rebuttal." in formatted_long
    assert "### [DEFENSE — Round 2]" in formatted_long
    assert "Verbatim defense turn 4 rejoinder." in formatted_long
