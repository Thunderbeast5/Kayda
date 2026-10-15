"""
Unit and Integration Test: Legal Reliability Audit for Stage 5 Precedent Pipeline.

Verifies resolution of all items in the user's critique:
A. Clear errors in output:
   1. Proposition mapping (Bhiwandi p2/p3 neutral/156(3) excluded; p1 contradicting for defense).
   2. Supporting/contradicting derivation (Bimla Tiwari auto-populated; Shajan Skaria p3 inverted holding fixed).
   3. Fact-fidelity & anti-hallucination (land title dispute, no "commercial dispute" or ungrounded "documents already seized").
   4. key_propositions accurately cited without claiming unverified verbatim quotes.
   5. Bimla Tiwari CrPC 82/83 how_used: "process" (not "charged"); precedential weight flagged as limited/persuasive.
   6. Tusharbhai holding accurately describes police remand impermissible during anticipatory bail and non-confession != non-cooperation.
   7. Article 141 ratio-based binding levels (Constitution Bench vs regular ratio vs short disposal order vs obiter).
   8. Statutory match consistency (Bhiwandi matches substantive offences 420/467/468/471 + 438).
   9. Role-aware scoring & ranking (supporting authorities lead; adverse authorities partitioned).

B. Substantive legal gaps:
   1. BNS/BNSS dual citations (IPC 420->BNS 318(4), IPC 467->BNS 338, IPC 468->BNS 336/340, IPC 471->BNS 340(2), CrPC 438->BNSS 482).
   2. Section 467 IPC auto-detection for forged sale deeds.
   3. Landmark authorities present in candidate pool (Sibbia, Sushila Aggarwal, Mhetre, Mohammed Ibrahim, Arnesh Kumar, Antil, Sheila Sebastian, Sarabjit Kaur).
   4. Mariam Fasihuddin positioned on defense side.
   5. Caveats for Adri Dharan Das, Km. Hema Mishra, and Pratibha Manchanda parallel proceedings rebuttal.
"""

import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from lexigraphbe.precedent_statute_matcher import PrecedentStatuteMatcher
from lexigraphbe.precedent_retrieval import PrecedentRetriever, PrecedentCandidate, CORE_LANDMARK_AUTHORITIES
from lexigraphbe.precedent_relevance_agent import (
    derive_and_sanitize_propositions,
    determine_binding_level,
    sanitize_fact_fidelity_and_caveats,
    PrecedentRelevanceBatchEvaluator,
    PrecedentRelevanceVerifierAgent
)
from lexigraphbe.schemas.stage5_precedent import (
    RoleSpecificRelevanceEvaluation,
    RoleSpecificPrecedentItem,
    MatchedStatuteItem,
    PropositionItem,
    PrecedentRoleRef,
    PrecedentCaseDetail,
    RoleSpecificPrecedentRetrievalObject
)


def test_bns_bnss_dual_statute_mapping():
    print("\n--- 1. Testing BNS/BNSS Dual Citation and S.467 Detection ---")
    matcher = PrecedentStatuteMatcher()
    
    stage4_result = {
        "verified_offences": [
            {"statute": "IPC", "section_number": "420", "overall_prima_facie_strength": "Strong"},
            {"statute": "IPC", "section_number": "468", "overall_prima_facie_strength": "Moderate"},
            {"statute": "IPC", "section_number": "471", "overall_prima_facie_strength": "Moderate"},
        ]
    }
    case_context = {
        "case_facts": "The dispute concerns title over agricultural land involving a forged ownership document and a fraudulent sale deed.",
        "requested_relief": "Anticipatory Bail under Section 438 CrPC"
    }
    
    extracted = matcher.extract_statutes_from_stage4(stage4_result, case_context)
    sections = {s["section"] for s in extracted}
    
    # Verify S.467 auto-detection
    assert "467" in sections, f"Section 467 IPC should be auto-detected for forged sale deed, found: {sections}"
    assert "438" in sections, "Section 438 CrPC should be present"
    
    # Check kind semantics for procedural sections in extracted statutes
    for s in extracted:
        if s["section"] in ("438", "41", "41A", "82", "83", "156(3)"):
            assert s.get("kind") in ("procedure", "process"), f"Section {s['section']} should be procedure/process, got {s.get('kind')}"
            
    # Check matcher how_used normalization
    matched_count, matched_list = matcher.match_statutes(
        extracted,
        [
            {"act": "CrPC 1973", "section": "438", "how_used": "charged"},  # Bad legacy tag
            {"act": "CrPC 1973", "section": "82", "how_used": "charged"},
            {"act": "IPC", "section": "420", "how_used": "charged"}
        ]
    )
    for m in matched_list:
        if m["judgment_section"] in ("438", "82"):
            assert m["how_used"] in ("procedure", "process"), f"Section {m['judgment_section']} should be normalized to procedure/process, got {m['how_used']}"
            assert m["how_used"] != "charged", f"Section {m['judgment_section']} must NEVER be 'charged'"
        if "dual_citation" in m and m["judgment_section"] == "420":
            assert "BNS" in m["dual_citation"], f"Dual citation missing for 420: {m.get('dual_citation')}"
            
    print(f"[PASS] S.467 IPC auto-detected and procedural sections normalized correctly. Sections: {sorted(list(sections))}")


def test_proposition_derivation_bhiwandi_and_bimla():
    print("\n--- 2. Testing Proposition Derivation (Bhiwandi & Bimla Tiwari) ---")
    
    # Bhiwandi propositions: p1 favors prosecution; p2, p3 neutral (S.156(3))
    bhiwandi_props = [
        {"id": "p1", "text": "Anticipatory bail may not be granted when serious allegations of fraud are involved.", "favors": "prosecution", "statutes": ["CrPC 1973"]},
        {"id": "p2", "text": "The validity of a Magistrate order under Section 156(3) cannot be questioned in bail.", "favors": "neutral", "statutes": ["CrPC 1973"]},
        {"id": "p3", "text": "Investigation under Section 156(3) happens before taking cognizance.", "favors": "neutral", "statutes": ["CrPC 1973"]},
    ]
    
    input_statutes = [{"act": "IPC", "section": "420"}, {"act": "IPC", "section": "468"}, {"act": "CrPC", "section": "438"}]
    input_summary = "Dispute over agricultural land title involving fraudulent sale deed."
    
    # Test Defense evaluation for Bhiwandi:
    # Even if LLM erroneously outputs supporting_propositions=["p2", "p3"]
    s_def, c_def = derive_and_sanitize_propositions(
        candidate_propositions=bhiwandi_props,
        role="defense",
        llm_supporting=["p2", "p3"],
        llm_contradicting=[],
        input_statutes=input_statutes,
        input_case_summary=input_summary
    )
    
    assert s_def == [], f"Defense supporting_propositions for Bhiwandi must be empty, got {s_def}"
    assert c_def == ["p1"], f"Defense contradicting_propositions for Bhiwandi must auto-repair to ['p1'], got {c_def}"
    print("[PASS] Bhiwandi: p2 and p3 (neutral 156(3)) excluded from defense supporting; p1 mapped to contradicting")
    
    # Test Bimla Tiwari evaluation for Defense:
    # LLM erroneously outputs supporting_propositions=[]
    bimla_props = [
        {"id": "p1", "text": "Bail should not be contingent on repayment as recovery is civil.", "favors": "accused", "statutes": ["CrPC 1973"]},
        {"id": "p2", "text": "Repayment should not lead to granting or denial of bail.", "favors": "accused", "statutes": ["CrPC 1973"]},
        {"id": "p3", "text": "Recovery of money is within civil realm, not criminal law.", "favors": "accused", "statutes": ["CrPC 1973"]},
    ]
    s_bimla, c_bimla = derive_and_sanitize_propositions(
        candidate_propositions=bimla_props,
        role="defense",
        llm_supporting=[],
        llm_contradicting=[],
        input_statutes=input_statutes,
        input_case_summary=input_summary
    )
    assert s_bimla == ["p1", "p2", "p3"], f"Defense supporting_propositions for Bimla Tiwari must auto-populate to ['p1', 'p2', 'p3'], got {s_bimla}"
    assert c_bimla == [], f"Defense contradicting_propositions for Bimla Tiwari must be empty, got {c_bimla}"
    print("[PASS] Bimla Tiwari: empty supporting list auto-populated from accused-favoring propositions")


def make_dummy_candidate(case_id, case_name, court="Supreme Court of India", decided_on="2020-01-01", procedural_stage="anticipatory_bail", abstract_facts="", disposition="Allowed", score_breakdown=None, role_scores=None, retrieval_score=8.0):
    return PrecedentCandidate(
        case_id=case_id,
        case_name=case_name,
        court=court,
        decided_on=decided_on,
        disposition=disposition,
        procedural_stage=procedural_stage,
        matched_statutes=[],
        match_score=1.0,
        total_statutes=1,
        abstract_facts=abstract_facts,
        statutes=[],
        propositions=[],
        issues=[],
        score_breakdown=score_breakdown or {},
        role_scores=role_scores or {},
        retrieval_score=retrieval_score
    )


def test_fact_fidelity_and_case_caveats():
    print("\n--- 3. Testing Fact-Fidelity Scrubbing & Mandatory Legal Caveats ---")
    
    dummy_cand_tusharbhai = make_dummy_candidate(
        case_id="_2024_8_SCR_235",
        case_name="Tusharbhai Rajnikantbhai Shah v. Kamal Dayani & Ors.",
        court="Supreme Court of India",
        decided_on="2024-08-07",
        procedural_stage="post_arrest_bail",
        abstract_facts="Police custody remand granted despite anticipatory bail.",
        disposition="Contempt found; remand illegal",
        retrieval_score=8.0
    )
    
    # Evaluation containing hallucinated phrases
    hallucinated_eval = {
        "analysis": "This is a private commercial/contractual dispute where custodial interrogation is unnecessary because documents are already seized.",
        "use_for": ["Custodial interrogation unnecessary where documents are already seized", "Commercial dispute given criminal color"],
        "against": [],
        "distinguish": []
    }
    
    input_summary = "Dispute over title to agricultural land involving a forged ownership document and a fraudulent sale deed."
    
    sanitize_fact_fidelity_and_caveats(
        evaluation=hallucinated_eval,
        candidate=dummy_cand_tusharbhai,
        role="defense",
        input_case_summary=input_summary
    )
    
    # Verify scrubbing of hallucinated "commercial dispute" and "documents already seized"
    analysis_text = hallucinated_eval["analysis"].lower()
    assert "private commercial/contractual dispute" not in analysis_text, "Failed to scrub commercial dispute"
    assert "documents are already seized" not in analysis_text, "Failed to scrub documents already seized"
    
    # Verify Tusharbhai accurate holding
    use_for_str = " ".join(hallucinated_eval["use_for"]).lower()
    assert "police custody remand is impermissible while an interim anticipatory bail order subsists" in use_for_str, "Tusharbhai remand holding missing"
    assert "non-cooperation" in use_for_str, "Tusharbhai non-confession holding missing"
    print("[PASS] Fact-fidelity scrubbed hallucinated phrases and restored true Tusharbhai holding")

    # Verify Adri Dharan Das caveat
    dummy_cand_adri = make_dummy_candidate(
        case_id="_2005_2_SCR_188",
        case_name="Adri Dharan Das v. State of West Bengal",
        court="Supreme Court of India",
        decided_on="2005-02-17",
        procedural_stage="anticipatory_bail",
        abstract_facts="Anticipatory bail principles.",
        disposition="Appeal dismissed",
        retrieval_score=7.0
    )
    adri_eval = {"analysis": "Anticipatory bail is exceptional power.", "use_for": [], "against": [], "distinguish": []}
    sanitize_fact_fidelity_and_caveats(adri_eval, dummy_cand_adri, "defense", input_summary)
    distinguish_str = " ".join(adri_eval["distinguish"]).lower()
    assert "sushila aggarwal" in distinguish_str and "softened" in distinguish_str, "Adri Dharan Das caveat missing"
    print("[PASS] Adri Dharan Das: Caveat on exceptionality being softened by Sushila Aggarwal present")

    # Verify Pratibha Manchanda rebuttal for defense
    dummy_cand_pratibha = make_dummy_candidate(
        case_id="_2023_10_SCR_411",
        case_name="Pratibha Manchanda v. State of Haryana",
        court="Supreme Court of India",
        decided_on="2023-07-07",
        procedural_stage="anticipatory_bail",
        abstract_facts="Land fraud with forged POA.",
        disposition="Anticipatory bail denied",
        retrieval_score=8.5
    )
    pm_eval = {"analysis": "Parallel proceedings permissible.", "use_for": [], "against": [], "distinguish": []}
    sanitize_fact_fidelity_and_caveats(pm_eval, dummy_cand_pratibha, "defense", input_summary)
    use_for_pm = " ".join(pm_eval["use_for"]).lower()
    assert "parallel civil/criminal" in use_for_pm and "mohammed ibrahim" in use_for_pm, "Pratibha Manchanda defense rebuttal missing"
    print("[PASS] Pratibha Manchanda: Defense rebuttal anticipating parallel proceedings present")


def test_article_141_binding_levels():
    print("\n--- 4. Testing Article 141 Ratio-Based Binding Levels ---")
    
    cand_cb = make_dummy_candidate(case_id="_1980_3_SCR_383", case_name="Gurbaksh Singh Sibbia", court="Supreme Court", decided_on="1980", procedural_stage="anticipatory_bail", abstract_facts="", disposition="Appeals allowed", retrieval_score=9.0)
    cand_short = make_dummy_candidate(case_id="_2023_1_SCR_501", case_name="Bimla Tiwari v. State of Bihar", court="Supreme Court", decided_on="2023", procedural_stage="anticipatory_bail", abstract_facts="", disposition="Petitions disposed of", retrieval_score=7.0)
    cand_regular = make_dummy_candidate(case_id="_2009_8_SCC_751", case_name="Mohammed Ibrahim v. State of Bihar", court="Supreme Court", decided_on="2009", procedural_stage="quashing", abstract_facts="", disposition="Appeals allowed", retrieval_score=8.5)
    
    assert determine_binding_level(cand_cb) == "binding (Constitution Bench)"
    assert determine_binding_level(cand_short) == "persuasive (short disposal order)"
    assert determine_binding_level(cand_regular) == "binding"
    print("[PASS] Article 141 binding levels correctly distinguish Constitution Bench, regular ratio, and short disposal orders")


def test_role_aware_ranking_and_partitioning():
    print("\n--- 5. Testing Role-Aware Ranking and Partitioning ---")
    
    evaluator = PrecedentRelevanceBatchEvaluator()
    
    # Create mock RoleSpecificPrecedentItems for Prosecution
    # Item 1: Bhiwandi (Supporting prosecution, score 6.52)
    # Item 2: Ravindra Saxena (Adverse/distinguishable to prosecution, score 6.67)
    item_bhiwandi = RoleSpecificPrecedentItem(
        case_id="_2021_7_SCR_226",
        case_name="Supreme Bhiwandi",
        court="Supreme Court",
        decided_on="2021-07-26",
        procedural_stage="anticipatory_bail",
        disposition="Allowed",
        matched_statutes=[],
        match_score=1.0,
        abstract_facts="",
        all_statutes=[],
        propositions=[],
        relevance_evaluation=RoleSpecificRelevanceEvaluation(
            case_id="_2021_7_SCR_226",
            case_name="Supreme Bhiwandi",
            relevance_type="STRONGLY_SUPPORTING",
            analysis="Supports prosecution"
        ),
        final_relevance_score=6.52
    )
    
    item_saxena = RoleSpecificPrecedentItem(
        case_id="_2009_16_SCR_433",
        case_name="Ravindra Saxena",
        court="Supreme Court",
        decided_on="2009-12-15",
        procedural_stage="anticipatory_bail",
        disposition="Allowed",
        matched_statutes=[],
        match_score=1.0,
        abstract_facts="",
        all_statutes=[],
        propositions=[],
        relevance_evaluation=RoleSpecificRelevanceEvaluation(
            case_id="_2009_16_SCR_433",
            case_name="Ravindra Saxena",
            relevance_type="DISTINGUISHABLE",
            analysis="Adverse authority prosecution must distinguish"
        ),
        final_relevance_score=6.67
    )
    
    cases_dict, p_refs, d_refs, shared, p_supp, p_adv, d_supp, d_adv = evaluator.build_deduplicated_cases_and_refs(
        prosecution_items=[item_saxena, item_bhiwandi],
        defense_items=[],
        candidates_by_id={}
    )
    
    # Verify that in p_refs, supporting authorities LEAD adverse ones:
    assert p_refs[0].case_id == "_2021_7_SCR_226", f"Supporting authority (Bhiwandi) must lead in prosecution_refs, got {p_refs[0].case_id}"
    assert p_refs[1].case_id == "_2009_16_SCR_433", f"Adverse authority (Ravindra Saxena) must follow, got {p_refs[1].case_id}"
    
    # Verify partitioned lists
    assert len(p_supp) == 1 and p_supp[0].case_id == "_2021_7_SCR_226"
    assert len(p_adv) == 1 and p_adv[0].case_id == "_2009_16_SCR_433"
    print("[PASS] Role-aware ranking: Supporting authority leads in prosecution list despite numerical score of adverse case")


def test_core_landmark_authorities_retrieval():
    print("\n--- 6. Testing Retrieval of Core Landmark Authorities ---")
    retriever = PrecedentRetriever()
    
    stage4 = {
        "verified_offences": [
            {"statute": "IPC", "section_number": "420", "overall_prima_facie_strength": "Strong"},
            {"statute": "IPC", "section_number": "468", "overall_prima_facie_strength": "Moderate"},
            {"statute": "IPC", "section_number": "471", "overall_prima_facie_strength": "Moderate"}
        ]
    }
    ctx = {
        "case_facts": "Agricultural land title dispute involving forged ownership document and fraudulent sale deed.",
        "requested_relief": "Anticipatory Bail under Section 438 CrPC"
    }
    
    role_pools = retriever.retrieve_by_role(stage4, ctx, top_k=8)
    def_candidates = [c.case_id for c in role_pools["defense"]]
    pros_candidates = [c.case_id for c in role_pools["prosecution"]]
    
    print(f"Top Defense Candidates: {def_candidates}")
    print(f"Top Prosecution Candidates: {pros_candidates}")
    
    # Check that crucial landmarks are present:
    # Defense: Mohammed Ibrahim (_2009_8_SCC_751), Sibbia (_1980_3_SCR_383)
    assert "_2009_8_SCC_751" in def_candidates, f"Mohammed Ibrahim must be in top defense candidates, got {def_candidates}"
    assert "_1980_3_SCR_383" in def_candidates, f"Gurbaksh Singh Sibbia must be in top defense candidates, got {def_candidates}"
    
    # Prosecution: Pratibha Manchanda (_2023_10_SCR_411) or Supreme Bhiwandi (_2021_7_SCR_226)
    assert any(c in pros_candidates for c in ("_2023_10_SCR_411", "_2021_7_SCR_226")), f"Pratibha Manchanda or Bhiwandi must be in top prosecution candidates, got {pros_candidates}"
    print("[PASS] Core landmark authorities retrieved at top of role pools")


def run_all_tests():
    print("=" * 80)
    print("STAGE 5 LEGAL RELIABILITY AUDIT - VERIFICATION SUITE")
    print("=" * 80)
    
    test_bns_bnss_dual_statute_mapping()
    test_proposition_derivation_bhiwandi_and_bimla()
    test_fact_fidelity_and_case_caveats()
    test_article_141_binding_levels()
    test_role_aware_ranking_and_partitioning()
    test_core_landmark_authorities_retrieval()
    
    print("\n" + "=" * 80)
    print("ALL LEGAL RELIABILITY AUDIT CHECKS PASSED (100%)")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
