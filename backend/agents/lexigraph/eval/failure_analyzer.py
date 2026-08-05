"""
failure_analyzer.py
===================
Diagnostic failure analyzer for legal GraphRAG benchmark.

Categorizes scenario evaluation failures by pipeline stage:
- STAGE_1_PINECONE: Vector similarity drop / retrieval miss
- STAGE_2_COMMUNITY: Leiden community cluster mismatch
- STAGE_3_GRAPH: Missing 1-hop graph relationships (cases/evidence)
- STAGE_4_VALIDATOR: Hard-rejection or false positive by IngredientValidator
- STAGE_5_CONFIDENCE: Confidence miscalibration outside expected range
"""

import re
from typing import Dict, Any, List


class FailureAnalyzer:
    """Diagnoses root causes for benchmark scenario execution failures."""

    @staticmethod
    def analyze_scenario_failure(scenario: Dict[str, Any], pipeline_output: Dict[str, Any]) -> Dict[str, Any]:
        sid = scenario.get("id")
        is_neg = scenario.get("is_negative_example")
        exp_bns = scenario.get("expected_bns_sections") or []
        exp_top1 = scenario.get("expected_top1")
        
        recs = pipeline_output.get("recommended_sections") or []
        pred_sections = [f"{r.get('act')} {r.get('section')}".upper() for r in recs]
        rejected = pipeline_output.get("rejected_sections") or []
        
        failed_stages = []
        diagnosis = []
        actionable_fix = []

        # 1. Negative Scenario False Positive Check
        if is_neg and recs:
            failed_stages.append("STAGE_4_VALIDATOR")
            diagnosis.append(f"Negative scenario produced false positive recommendations: {pred_sections}")
            actionable_fix.append("Tighten ingredient validator hard-rejection thresholds for boundary facts.")

        # 2. Top-1 Prediction Mismatch
        if not is_neg and (exp_top1 or exp_bns):
            target_exp = exp_top1 or (exp_bns[0] if exp_bns else "")
            exp_clean = re.sub(r"^(BNS|IPC|SECTION)\s*", "", str(target_exp).upper()).strip()
            pred_cleans = [re.sub(r"^(BNS|IPC|SECTION)\s*", "", p.upper()).strip() for p in pred_sections[:1]]
            top1_hit = any(exp_clean == p or exp_clean in p or p in exp_clean for p in pred_cleans) if pred_cleans else False
            if not top1_hit:
                # Check if section was rejected by validator
                rej_hit = [r for r in rejected if exp_clean in str(r.get("section")).upper()]
                if rej_hit:
                    failed_stages.append("STAGE_4_VALIDATOR")
                    diagnosis.append(f"Expected Top-1 section '{target_exp}' was hard-rejected by validator: {rej_hit[0].get('reason')}")
                    actionable_fix.append("Update Neo4j ingredient comparator metadata for candidate section.")
                else:
                    failed_stages.append("STAGE_1_PINECONE")
                    diagnosis.append(f"Expected Top-1 section '{target_exp}' missed in vector search or reranking.")
                    actionable_fix.append("Expand query synonyms or boost Pinecone vector top_k retrieval window.")

        # 3. Community Cluster Alignment Check
        exp_comm = scenario.get("expected_community")
        actual_comm = pipeline_output.get("community", {}).get("community_id")
        if exp_comm and actual_comm and exp_comm != actual_comm:
            failed_stages.append("STAGE_2_COMMUNITY")
            diagnosis.append(f"Community cluster mismatch (Expected: '{exp_comm}', Actual: '{actual_comm}').")
            actionable_fix.append("Update GDS Leiden community membership or fallback candidate graph pooling.")

        # 4. Confidence Calibration Check
        pred_conf = pipeline_output.get("pipeline_confidence", 0.0)
        conf_range = scenario.get("expected_confidence_range") or [0.70, 1.00]
        if not (conf_range[0] <= pred_conf <= conf_range[1]):
            failed_stages.append("STAGE_5_CONFIDENCE")
            diagnosis.append(f"Confidence score {pred_conf:.4f} outside expected range {conf_range}.")
            actionable_fix.append("Adjust multi-signal weights in reranking_service.py.")

        return {
            "scenario_id": sid,
            "failed_stages": failed_stages or ["NONE"],
            "diagnosis": " | ".join(diagnosis) if diagnosis else "Passed successfully.",
            "actionable_fix": " | ".join(actionable_fix) if actionable_fix else "No fix required."
        }
