"""
Prefilter Recall Evaluation Suite for LexiGraph Backend.
Evaluates StatuteClassifierPrefilter Recall@5, Recall@10, Recall@15, and MRR (Mean Reciprocal Rank)
against ground-truth statutory section labels across a 30-case representative benchmark corpus.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from .classifier_prefilter import StatuteClassifierPrefilter
from .schemas import LegalConceptItem, LegalQueryObject, SubQueryItem


class EvaluationBenchmarkCase(BaseModel):
    case_id: str
    scenario_description: str
    legal_concepts: List[str]
    sub_queries: List[str]
    target_regime: str
    ground_truth_sections: List[str]


BENCHMARK_CORPUS: List[EvaluationBenchmarkCase] = [
    # --- IPC REGIME (15 Cases) ---
    EvaluationBenchmarkCase(
        case_id="BENCH_01",
        scenario_description="Continuous demand for cash dowry, harassment for motor vehicle, and physical assault upon spouse.",
        legal_concepts=["Dowry Demand", "Matrimonial Cruelty", "Physical Assault"],
        sub_queries=["Continuous demand for cash dowry by husband and in-laws.", "Physical assault resulting in bodily harm."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 498A", "IPC 323"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_02",
        scenario_description="Unnatural death of married woman within 7 years of marriage under suspicious circumstances following dowry harassment.",
        legal_concepts=["Dowry Death", "Dowry Demand", "Matrimonial Cruelty"],
        sub_queries=["Death of victim within 7 years of marriage following dowry demands.", "Continuous harassment for dowry."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 304B", "IPC 498A"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_03",
        scenario_description="Entrustment of Stridhan ornaments and cash to in-laws, dishonestly misappropriated and refused to return.",
        legal_concepts=["Criminal Breach of Trust", "Misappropriation of Stridhan"],
        sub_queries=["Dishonest misappropriation of Stridhan jewelry entrusted at marriage."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 406"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_04",
        scenario_description="Cheating and dishonest inducement to deliver property by false promises of marriage and business partnership.",
        legal_concepts=["Cheating", "Dishonest Inducement to Deliver Property"],
        sub_queries=["Dishonest inducement to transfer cash funds based on fraudulent representations."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 420"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_05",
        scenario_description="Threats to kill victim and family members with deadly weapons if police complaint is lodged.",
        legal_concepts=["Criminal Intimidation", "Threat to Life"],
        sub_queries=["Threatening victim with dire consequences and death."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 506"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_06",
        scenario_description="Pre-planned murder with sharp firearm weapon during group feud.",
        legal_concepts=["Murder", "Common Intention"],
        sub_queries=["Shooting victim causing immediate death with premeditation."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 302", "IPC 34"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_07",
        scenario_description="Attempt to commit murder by inflicting deep knife wounds on neck.",
        legal_concepts=["Attempt to Murder", "Grievous Hurt"],
        sub_queries=["Stabbing victim in vital area with intent to kill."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 307", "IPC 326"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_08",
        scenario_description="Culpable homicide not amounting to murder caused by sudden fight without premeditation.",
        legal_concepts=["Culpable Homicide"],
        sub_queries=["Fatal blow inflicted during sudden provocation and fight."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 304"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_09",
        scenario_description="Extortion of money by threatening to publish defamatory photographs.",
        legal_concepts=["Extortion", "Defamation"],
        sub_queries=["Demanding money by putting victim in fear of injury."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 384", "IPC 500"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_10",
        scenario_description="Night housebreaking and theft of valuable gold assets.",
        legal_concepts=["Housebreaking", "Theft"],
        sub_queries=["Breaking into house at night to commit theft."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 457", "IPC 380"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_11",
        scenario_description="Dacoity with deadly weapons committed by group of five masked men.",
        legal_concepts=["Dacoity", "Armed Robbery"],
        sub_queries=["Five persons looting house while armed with dangerous weapons."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 395", "IPC 397"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_12",
        scenario_description="Forgery of land deed documents and valuable security for illegal property transfer.",
        legal_concepts=["Forgery", "Forged Document"],
        sub_queries=["Fabricating forged signature on land sale deed."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 467", "IPC 471"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_13",
        scenario_description="Kidnapping of minor child for ransom demand.",
        legal_concepts=["Kidnapping for Ransom"],
        sub_queries=["Abducting child and demanding cash ransom for release."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 364A"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_14",
        scenario_description="Outraging modesty of woman by physical assault and sexual harassment.",
        legal_concepts=["Outraging Modesty", "Sexual Harassment"],
        sub_queries=["Assaulting woman with intent to outrage her modesty."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 354", "IPC 354A"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_15",
        scenario_description="Causing death by rash and negligent driving of motor vehicle.",
        legal_concepts=["Rash and Negligent Driving", "Causing Death by Negligence"],
        sub_queries=["Driving heavy vehicle recklessly causing fatal road collision."],
        target_regime="IPC + CrPC",
        ground_truth_sections=["IPC 304A", "IPC 279"],
    ),

    # --- BNS REGIME (15 Cases) ---
    EvaluationBenchmarkCase(
        case_id="BENCH_16",
        scenario_description="Post-July 1 2024 dowry cruelty and physical harassment by husband.",
        legal_concepts=["Dowry Demand", "Matrimonial Cruelty"],
        sub_queries=["Continuous demand for dowry under new penal code."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 85"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_17",
        scenario_description="Post-July 1 2024 dowry death of woman within 7 years of marriage.",
        legal_concepts=["Dowry Death", "Matrimonial Cruelty"],
        sub_queries=["Unnatural death of victim following dowry harassment."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 80"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_18",
        scenario_description="Post-July 1 2024 dishonest misappropriation of property and breach of trust.",
        legal_concepts=["Criminal Breach of Trust"],
        sub_queries=["Misappropriation of entrusted funds."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 316"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_19",
        scenario_description="Post-July 1 2024 cheating and dishonest inducement to deliver property.",
        legal_concepts=["Cheating", "Dishonest Inducement"],
        sub_queries=["Fraudulent inducement to deliver cash property."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 318"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_20",
        scenario_description="Post-July 1 2024 criminal intimidation and death threats.",
        legal_concepts=["Criminal Intimidation"],
        sub_queries=["Threatening victim with physical harm and death."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 351"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_21",
        scenario_description="Post-July 1 2024 murder committed with common intention.",
        legal_concepts=["Murder", "Common Intention"],
        sub_queries=["Intentional killing of victim during assault."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 103", "BNS 3"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_22",
        scenario_description="Post-July 1 2024 attempt to commit murder with dangerous weapon.",
        legal_concepts=["Attempt to Murder"],
        sub_queries=["Inflicting knife injury with intent to cause death."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 109"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_23",
        scenario_description="Post-July 1 2024 culpable homicide not amounting to murder.",
        legal_concepts=["Culpable Homicide"],
        sub_queries=["Causing death without premeditated murder intent."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 105"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_24",
        scenario_description="Post-July 1 2024 extortion of money under fear of injury.",
        legal_concepts=["Extortion"],
        sub_queries=["Extorting money by threatening victim."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 308"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_25",
        scenario_description="Post-July 1 2024 theft of property from dwelling house.",
        legal_concepts=["Theft"],
        sub_queries=["Stealing property from residence."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 303", "BNS 305"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_26",
        scenario_description="Post-July 1 2024 robbery and armed assault.",
        legal_concepts=["Robbery"],
        sub_queries=["Committing robbery with force."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 309"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_27",
        scenario_description="Post-July 1 2024 dacoity committed by group of five persons.",
        legal_concepts=["Dacoity"],
        sub_queries=["Looting dwelling house in group of five."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 310"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_28",
        scenario_description="Post-July 1 2024 forgery of valuable legal security.",
        legal_concepts=["Forgery"],
        sub_queries=["Forging signature on valuable security."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 336"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_29",
        scenario_description="Post-July 1 2024 assault or criminal force to woman with intent to outrage modesty.",
        legal_concepts=["Outraging Modesty"],
        sub_queries=["Sexual assault and outraging modesty."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 74"],
    ),
    EvaluationBenchmarkCase(
        case_id="BENCH_30",
        scenario_description="Post-July 1 2024 causing death by rash or negligent act.",
        legal_concepts=["Causing Death by Negligence"],
        sub_queries=["Negligent driving causing fatal accident."],
        target_regime="BNS + BNSS",
        ground_truth_sections=["BNS 106"],
    ),
]


def run_prefilter_recall_evaluation(prefilter: Optional[StatuteClassifierPrefilter] = None) -> Dict[str, Any]:
    """
    Evaluates StatuteClassifierPrefilter Recall@5, Recall@10, Recall@15, and MRR across 30-case benchmark corpus.

    Returns:
        Dict containing benchmark evaluation metrics.
    """
    eval_prefilter = prefilter or StatuteClassifierPrefilter()

    total_cases = len(BENCHMARK_CORPUS)
    hits_at_5 = 0
    hits_at_10 = 0
    hits_at_15 = 0
    reciprocal_ranks = []

    for test_case in BENCHMARK_CORPUS:
        qo = LegalQueryObject(
            legal_regime=test_case.target_regime,
            legal_concepts=[LegalConceptItem(concept=c, confidence=0.95) for c in test_case.legal_concepts],
            sub_queries=[SubQueryItem(id=f"SQ{i+1}", query=sq, concept=test_case.legal_concepts[0] if test_case.legal_concepts else "") for i, sq in enumerate(test_case.sub_queries)],
        )

        candidates = eval_prefilter.shortlist_candidates_for_query(qo, top_k=15, target_regime=test_case.target_regime)
        retrieved_ids = [c.section_identifier.upper() for c in candidates]

        targets = [gt.upper() for gt in test_case.ground_truth_sections]

        # Check hit @ 5
        top_5_ids = retrieved_ids[:5]
        if any(target in top_5_ids or any(target in r for r in top_5_ids) for target in targets):
            hits_at_5 += 1

        # Check hit @ 10
        top_10_ids = retrieved_ids[:10]
        if any(target in top_10_ids or any(target in r for r in top_10_ids) for target in targets):
            hits_at_10 += 1

        # Check hit @ 15
        if any(target in retrieved_ids or any(target in r for r in retrieved_ids) for target in targets):
            hits_at_15 += 1

        # Compute Reciprocal Rank
        rank = 0
        for idx, r_id in enumerate(retrieved_ids, start=1):
            if any(t == r_id or t.replace(" ", "_") in r_id or t.split()[-1] in r_id for t in targets):
                rank = idx
                break

        reciprocal_ranks.append(1.0 / rank if rank > 0 else 0.0)

    recall_5 = round(hits_at_5 / total_cases, 4)
    recall_10 = round(hits_at_10 / total_cases, 4)
    recall_15 = round(hits_at_15 / total_cases, 4)
    mrr = round(sum(reciprocal_ranks) / total_cases, 4)

    return {
        "sample_size_n": total_cases,
        "ipc_cases_count": 15,
        "bns_cases_count": 15,
        "recall_at_5": recall_5,
        "recall_at_10": recall_10,
        "recall_at_15": recall_15,
        "mean_reciprocal_rank_mrr": mrr,
    }


if __name__ == "__main__":
    print("=== LEXIGRAPH PREFILTER RECALL BENCHMARK EVALUATION (n=30) ===")
    results = run_prefilter_recall_evaluation()
    print(json.dumps(results, indent=2))
