"""
Auditor Benchmark Evaluator for LexiGraph Backend Stage 4.
Evaluates StatutoryVerificationAuditor across a representative n=20 benchmark suite:
- Detection Rate of Known Incorrect/Faulty Outputs (10 Invalid Cases)
- False Positive Rate on Valid/Clean Outputs (10 Clean Cases)
"""

import json
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

from .schemas import (
    ChapterCandidateItem,
    ChapterIdentificationObject,
    LegalConceptItem,
    LegalQueryObject,
    SectionCandidateItem,
    StatutoryIngredientItem,
    StatutoryVerificationObject,
    StatutoryVerificationResult,
    SubQueryItem,
    VerifiedSectionItem,
)
from .statutory_verifier_agent import StatutoryVerificationAuditor


BENCHMARK_AUDIT_CASES: List[Dict[str, Any]] = [
    # --- INVALID / FAULTY CASES (10 Incorrect Cases) ---
    {
        "id": "AUDIT_FAIL_01",
        "description": "Unapproved Section 302 included when Stage 3 candidate shortlist contained only 498A.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Dowry Demand", section_number="498A", section_title="Cruelty", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="302", section_title="Murder", ingredients=[], overall_confidence=0.95)])
    },
    {
        "id": "AUDIT_FAIL_02",
        "description": "Ingredient lacks factual reasoning text.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Dowry Demand", section_number="498A", section_title="Cruelty", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="498A",
                section_title="Cruelty by Husband",
                ingredients=[StatutoryIngredientItem(ingredient="Marriage", status="Satisfied", reason="")],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_03",
        "description": "Disjunctive OR cruelty assessed as Not Satisfied overall when Clause (a) willful conduct was satisfied.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Matrimonial Cruelty", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Matrimonial Cruelty", section_number="498A", section_title="Cruelty", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="498A",
                section_title="Cruelty by Husband",
                ingredients=[
                    StatutoryIngredientItem(ingredient="Marriage", logical_operator="MANDATORY", status="Satisfied", reason="Married."),
                    StatutoryIngredientItem(ingredient="Clause (a) Willful Conduct", logical_operator="OR", condition_group="Cruelty_Branch", status="Satisfied", reason="Severe physical injury."),
                    StatutoryIngredientItem(ingredient="Clause (b) Dowry Harassment", logical_operator="OR", condition_group="Cruelty_Branch", status="Not Satisfied", reason="No dowry demand.")
                ],
                overall_confidence=0.40  # Faulty low confidence despite Clause (a) satisfied
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_04",
        "description": "Unverified BNS 103 Section included when legal regime is IPC + CrPC.",
        "is_valid": False,
        "query": LegalQueryObject(legal_regime="IPC + CrPC", legal_concepts=[LegalConceptItem(concept="Murder", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Murder", section_number="302", section_title="Murder", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[VerifiedSectionItem(section_number="103", section_title="Murder", ingredients=[], overall_confidence=0.95)])
    },
    {
        "id": "AUDIT_FAIL_05",
        "description": "Unsupported factual assumption made regarding weapon recovery.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Assault", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Assault", section_number="323", section_title="Voluntarily Causing Hurt", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="323",
                section_title="Voluntarily Causing Hurt",
                ingredients=[StatutoryIngredientItem(ingredient="Weapon", status="Satisfied", reason="Assumed gun was recovered though not in FIR.")],
                overall_confidence=0.90
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_06",
        "description": "IPC 420 Cheating verified without fraudulent inducement ingredient.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Cheating", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Cheating", section_number="420", section_title="Cheating", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="420",
                section_title="Cheating",
                ingredients=[],  # Empty ingredients
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_07",
        "description": "Verification status set to VERIFIED despite confidence < 0.50.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Extortion", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Extortion", section_number="384", section_title="Extortion", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="384",
                section_title="Extortion",
                ingredients=[StatutoryIngredientItem(ingredient="Fear of Injury", status="Insufficient Evidence", reason="Unsubstantiated claim.")],
                overall_confidence=0.30
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_08",
        "description": "BNS 85 Cruelty missing parent section attribution.",
        "is_valid": False,
        "query": LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Cruelty", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Cruelty", section_number="85", section_title="Cruelty", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="498A",  # Wrong section number for BNS regime
                section_title="Cruelty by Husband",
                ingredients=[StatutoryIngredientItem(ingredient="Marriage", status="Satisfied", reason="Married.")],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_09",
        "description": "Fabricated punishment severity string.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Theft", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Theft", section_number="379", section_title="Theft", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="379",
                section_title="Theft",
                punishment_text="Imprisonment for 20 years",  # Wrong punishment for theft (max 3 years)
                max_imprisonment_years=20.0,
                arnesh_kumar_threshold_exceeded=True,
                ingredients=[StatutoryIngredientItem(ingredient="Theft", status="Satisfied", reason="Stolen.")],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_FAIL_10",
        "description": "Unsatisfied mandatory ingredient ignored.",
        "is_valid": False,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Death", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Dowry Death", section_number="304B", section_title="Dowry Death", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="304B",
                section_title="Dowry Death",
                ingredients=[
                    StatutoryIngredientItem(ingredient="Marriage within 7 Years", status="Not Satisfied", reason="Married 15 years ago."),  # Fails mandatory condition
                ],
                overall_confidence=0.95  # Incorrect high confidence
            )
        ])
    },

    # --- VALID / CLEAN CASES (10 Correct Cases) ---
    {
        "id": "AUDIT_CLEAN_01",
        "description": "Valid Section 498A verification with grounded reasoning and disjunctive OR clause (a) satisfied.",
        "is_valid": True,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Demand", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Dowry Demand", section_number="498A", section_title="Cruelty", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="498A",
                section_title="Cruelty by Husband",
                disjunctive_clause_applied="Satisfied via Clause (a) Willful Conduct",
                ingredients=[
                    StatutoryIngredientItem(ingredient="Marriage", logical_operator="MANDATORY", status="Satisfied", reason="Married in 2020."),
                    StatutoryIngredientItem(ingredient="Clause (a) Willful Conduct", logical_operator="OR", condition_group="Cruelty_Disjunctive_Branches", status="Satisfied", reason="Assault resulting in injury stated in complaint.")
                ],
                overall_confidence=0.96
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_02",
        "description": "Valid Section 304B Dowry Death verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Dowry Death", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Dowry Death", section_number="304B", section_title="Dowry Death", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="304B",
                section_title="Dowry Death",
                punishment_text="Imprisonment for not less than 7 years but which may extend to life",
                max_imprisonment_years=99.0,
                arnesh_kumar_threshold_exceeded=True,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Death within 7 years", logical_operator="MANDATORY", status="Satisfied", reason="Died within 3 years of marriage."),
                    StatutoryIngredientItem(ingredient="Dowry harassment soon before death", logical_operator="MANDATORY", status="Satisfied", reason="Harassment documented 2 weeks prior.")
                ],
                overall_confidence=0.97
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_03",
        "description": "Valid IPC Section 406 Criminal Breach of Trust verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Breach of Trust", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Breach of Trust", section_number="406", section_title="Criminal Breach of Trust", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="406",
                section_title="Criminal Breach of Trust",
                punishment_text="Imprisonment up to 3 years or fine",
                max_imprisonment_years=3.0,
                arnesh_kumar_threshold_exceeded=False,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Entrustment of Property", status="Satisfied", reason="Stridhan jewelry entrusted."),
                    StatutoryIngredientItem(ingredient="Dishonest Misappropriation", status="Satisfied", reason="Refused return.")
                ],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_04",
        "description": "Valid IPC Section 420 Cheating verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Cheating", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Cheating", section_number="420", section_title="Cheating", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="420",
                section_title="Cheating and Dishonestly Inducing Delivery of Property",
                punishment_text="Imprisonment up to 7 years and fine",
                max_imprisonment_years=7.0,
                arnesh_kumar_threshold_exceeded=False,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Cheating", status="Satisfied", reason="False representation made."),
                    StatutoryIngredientItem(ingredient="Dishonest Inducement", status="Satisfied", reason="Induced cash delivery.")
                ],
                overall_confidence=0.96
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_05",
        "description": "Valid BNS Section 85 Cruelty verification for BNS regime.",
        "is_valid": True,
        "query": LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Cruelty", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Cruelty", section_number="85", section_title="Cruelty by Husband", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="85",
                section_title="Husband or relative of husband of a woman subjecting her to cruelty",
                punishment_text="Imprisonment up to 3 years and fine",
                max_imprisonment_years=3.0,
                arnesh_kumar_threshold_exceeded=False,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Marriage", logical_operator="MANDATORY", status="Satisfied", reason="Married in 2024."),
                    StatutoryIngredientItem(ingredient="Cruelty Harassment", logical_operator="OR", status="Satisfied", reason="Harassment for dowry.")
                ],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_06",
        "description": "Valid BNS Section 80 Dowry Death verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Dowry Death", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Dowry Death", section_number="80", section_title="Dowry Death", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="80",
                section_title="Dowry Death",
                punishment_text="Imprisonment not less than 7 years but which may extend to life",
                max_imprisonment_years=99.0,
                arnesh_kumar_threshold_exceeded=True,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Death within 7 years", status="Satisfied", reason="Death occurred 2 years after marriage.")
                ],
                overall_confidence=0.96
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_07",
        "description": "Valid BNS Section 318 Cheating verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Cheating", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Cheating", section_number="318", section_title="Cheating", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="318",
                section_title="Cheating and dishonestly inducing delivery of property",
                punishment_text="Imprisonment up to 7 years and fine",
                max_imprisonment_years=7.0,
                arnesh_kumar_threshold_exceeded=False,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Cheating", status="Satisfied", reason="Deceitful representation.")
                ],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_08",
        "description": "Valid Section 506 Criminal Intimidation verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Criminal Intimidation", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Criminal Intimidation", section_number="506", section_title="Criminal Intimidation", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="506",
                section_title="Punishment for criminal intimidation",
                punishment_text="Imprisonment up to 7 years or fine",
                max_imprisonment_years=7.0,
                arnesh_kumar_threshold_exceeded=False,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Threat to Cause Death", status="Satisfied", reason="Threatened to shoot victim.")
                ],
                overall_confidence=0.95
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_09",
        "description": "Valid IPC Section 302 Murder verification.",
        "is_valid": True,
        "query": LegalQueryObject(legal_concepts=[LegalConceptItem(concept="Murder", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Murder", section_number="302", section_title="Murder", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="302",
                section_title="Punishment for murder",
                punishment_text="Death or imprisonment for life, and fine",
                max_imprisonment_years=99.0,
                arnesh_kumar_threshold_exceeded=True,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Intention to cause death", status="Satisfied", reason="Inflicted fatal gunshot wound.")
                ],
                overall_confidence=0.98
            )
        ])
    },
    {
        "id": "AUDIT_CLEAN_10",
        "description": "Valid BNS Section 103 Murder verification for BNS regime.",
        "is_valid": True,
        "query": LegalQueryObject(legal_regime="BNS + BNSS", legal_concepts=[LegalConceptItem(concept="Murder", confidence=0.95)]),
        "chapter_obj": ChapterIdentificationObject(section_candidates=[SectionCandidateItem(concept="Murder", section_number="103", section_title="Murder", confidence=0.95)]),
        "stat_obj": StatutoryVerificationObject(verified_sections=[
            VerifiedSectionItem(
                section_number="103",
                section_title="Punishment for murder",
                punishment_text="Death or imprisonment for life, and fine",
                max_imprisonment_years=99.0,
                arnesh_kumar_threshold_exceeded=True,
                ingredients=[
                    StatutoryIngredientItem(ingredient="Intention to cause death", status="Satisfied", reason="Shooting with premeditated intent.")
                ],
                overall_confidence=0.98
            )
        ])
    },
]


def run_auditor_benchmark_evaluation(auditor: Optional[StatutoryVerificationAuditor] = None) -> Dict[str, Any]:
    """
    Evaluates StatutoryVerificationAuditor detection rate of incorrect outputs and false positive rate across n=20 benchmark cases.

    Returns:
        Dict containing detection_rate, false_positive_rate, and evaluation summary.
    """
    if auditor is not None:
        eval_auditor = auditor
    else:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = json.dumps({"status": "VERIFIED", "issues": [], "feedback": "Audited cleanly."})
        eval_auditor = StatutoryVerificationAuditor(llm=mock_llm)

    true_positives = 0   # Correctly flagged incorrect output as RETRY
    false_positives = 0  # Incorrectly flagged clean output as RETRY
    total_incorrect_cases = 0
    total_clean_cases = 0

    for test_case in BENCHMARK_AUDIT_CASES:
        res: StatutoryVerificationResult = eval_auditor.verify(
            legal_query=test_case["query"],
            chapter_object=test_case["chapter_obj"],
            statutory_object=test_case["stat_obj"]
        )

        if not test_case["is_valid"]:
            total_incorrect_cases += 1
            if res.status == "RETRY":
                true_positives += 1
        else:
            total_clean_cases += 1
            if res.status == "RETRY":
                false_positives += 1

    detection_rate = round(true_positives / total_incorrect_cases, 4) if total_incorrect_cases > 0 else 1.0
    fp_rate = round(false_positives / total_clean_cases, 4) if total_clean_cases > 0 else 0.0

    return {
        "sample_size_n": len(BENCHMARK_AUDIT_CASES),
        "incorrect_cases_count": total_incorrect_cases,
        "clean_cases_count": total_clean_cases,
        "detection_rate_of_incorrect_outputs": detection_rate,
        "false_positive_rate": fp_rate,
    }


if __name__ == "__main__":
    print("=== STATUTORY VERIFICATION AUDITOR BENCHMARK EVALUATION (n=20) ===")
    results = run_auditor_benchmark_evaluation()
    print(json.dumps(results, indent=2))
