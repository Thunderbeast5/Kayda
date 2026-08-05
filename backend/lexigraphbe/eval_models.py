"""
Model Tier Accuracy & Schema Compliance Evaluator for LexiGraph Backend.
Benchmarks gpt-4o-mini vs. llama-3.1-8b-instant vs. llama-3.3-70b-versatile on
categorization accuracy, schema compliance, and structured JSON output validity.
"""

import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from .config import get_llm, MODEL_TIER_CHEAP, MODEL_TIER_REASONING
from .schemas import ChapterIdentificationObject, LegalConceptItem, LegalQueryObject, SubQueryItem
from .chapter_identification_agent import ChapterIdentificationAgent


class ModelBenchmarkReport(BaseModel):
    model_name: str
    tier: str
    total_eval_runs: int
    successful_schema_parses: int
    schema_compliance_rate: float
    avg_latency_seconds: float
    accuracy_score: float
    recommendation: str


BENCHMARK_PROMPTS_DATA = [
    {
        "query": LegalQueryObject(
            legal_regime="IPC + CrPC",
            legal_concepts=[
                LegalConceptItem(concept="Dowry Demand", confidence=0.98),
                LegalConceptItem(concept="Criminal Intimidation", confidence=0.95),
            ],
            sub_queries=[
                SubQueryItem(id="SQ1", query="Husband and in-laws demanded dowry.", concept="Dowry Demand", target_parties=["Husband"])
            ]
        ),
        "expected_chapter": "XXA",
        "expected_section": "498A"
    },
    {
        "query": LegalQueryObject(
            legal_regime="IPC + CrPC",
            legal_concepts=[
                LegalConceptItem(concept="Criminal Breach of Trust", confidence=0.95),
            ],
            sub_queries=[
                SubQueryItem(id="SQ1", query="Entrusted stridhan property dishonestly misappropriated.", concept="Criminal Breach of Trust", target_parties=["Husband"])
            ]
        ),
        "expected_chapter": "XVII",
        "expected_section": "406"
    },
    {
        "query": LegalQueryObject(
            legal_regime="BNS + BNSS",
            legal_concepts=[
                LegalConceptItem(concept="Dowry Demand", confidence=0.98),
            ],
            sub_queries=[
                SubQueryItem(id="SQ1", query="Cruelty by husband for dowry under new code.", concept="Dowry Demand", target_parties=["Husband"])
            ]
        ),
        "expected_chapter": "V",
        "expected_section": "85"
    }
]


def evaluate_model_performance(model_name: str, tier: str = MODEL_TIER_CHEAP) -> ModelBenchmarkReport:
    """
    Evaluates a specific LLM model on categorization accuracy, latency, and schema compliance.
    """
    total_runs = len(BENCHMARK_PROMPTS_DATA)
    successful_parses = 0
    correct_categorizations = 0
    total_latency = 0.0

    try:
        llm = get_llm(model_name=model_name)
    except Exception as e:
        return ModelBenchmarkReport(
            model_name=model_name,
            tier=tier,
            total_eval_runs=total_runs,
            successful_schema_parses=0,
            schema_compliance_rate=0.0,
            avg_latency_seconds=0.0,
            accuracy_score=0.0,
            recommendation=f"Failed to initialize model ({e})"
        )

    agent = ChapterIdentificationAgent(llm=llm)

    for item in BENCHMARK_PROMPTS_DATA:
        t0 = time.time()
        try:
            res: ChapterIdentificationObject = agent.run(item["query"])
            latency = time.time() - t0
            total_latency += latency
            successful_parses += 1

            # Check chapter and section title identification accuracy
            matched_sec = any(
                item["expected_section"] in sec.section_number
                for sec in res.section_candidates
            )
            if matched_sec:
                correct_categorizations += 1

        except Exception as err:
            latency = time.time() - t0
            total_latency += latency

    compliance_rate = round(successful_parses / total_runs, 4)
    accuracy_score = round(correct_categorizations / total_runs, 4)
    avg_latency = round(total_latency / total_runs, 4)

    recommendation = "RECOMMENDED FOR PRODUCTION" if accuracy_score >= 0.80 and compliance_rate == 1.0 else "SUB-OPTIMAL FOR CHEAP TIER (RECOMMEND GPT-4O-MINI OR LLAMA-3.3-70B)"

    return ModelBenchmarkReport(
        model_name=model_name,
        tier=tier,
        total_eval_runs=total_runs,
        successful_schema_parses=successful_parses,
        schema_compliance_rate=compliance_rate,
        avg_latency_seconds=avg_latency,
        accuracy_score=accuracy_score,
        recommendation=recommendation
    )


if __name__ == "__main__":
    print("=== MODEL TIER ACCURACY & COMPLIANCE BENCHMARK ===")
    test_models = ["gpt-4o-mini", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    for m in test_models:
        rep = evaluate_model_performance(m)
        print(f"\nModel: {m}")
        print(json.dumps(rep.model_dump(), indent=2))
