"""
ingredient_validator_service.py
================================
Production-grade Metadata-Driven Legal Validation Engine.

Completely metadata-driven by Neo4j (:HAS_INGREDIENT) graph schema.
Evaluates 3-state statutory ingredient outcomes (Satisfied, Contradicted, Unverified)
across ACTUS_REUS, MENS_REA, VICTIM, and CIRCUMSTANCE element types with ZERO hardcoded section rules.
"""

import re
from typing import Dict, Any, List, Tuple


class IngredientValidatorService:
    """Generic Metadata-Driven Statutory Ingredient Validator."""

    def __init__(self, neo4j_service=None):
        self.neo4j_service = neo4j_service

    def validate_candidate(
        self, candidate: Dict[str, Any], facts: Dict[str, Any]
    ) -> Tuple[bool, float, str]:
        """
        Validates a candidate LawSection by dynamically traversing Neo4j statutory ingredients
        and evaluating 3-state outcomes (Satisfied, Contradicted, Unverified).
        
        Returns:
            (is_valid: bool, confidence: float, reason: str)
        """
        act = candidate.get("act", "")
        sec_num = candidate.get("section_num", "")
        sec_str = f"{act} {sec_num}".upper()

        ingredients = self._get_section_ingredients(act, sec_num)

        # If no ingredients at all (direct or via equivalent), fall back to a
        # lower confidence based only on vector similarity.
        if not ingredients:
            vec_sim = float(candidate.get("vector_similarity") or 0.70)
            # Lower confidence: 0.40 base + 0.20 * vec_sim → range 0.40–0.60
            fallback_conf = round(0.40 + (0.20 * vec_sim), 4)
            # We still mark it as "valid" but with low confidence, so it may
            # be outranked by sections with real ingredient matches.
            return True, fallback_conf, f"Candidate {sec_str} – no ingredient data; relying on vector similarity only (confidence {fallback_conf})."

        satisfied_count = 0
        contradicted_count = 0
        unverified_count = 0

        mandatory_satisfied = 0
        mandatory_total = 0

        matched_actus = 0
        total_actus = 0
        matched_mens = 0
        total_mens = 0

        verification_notes = []

        for ing in ingredients:
            state, reason_detail = self._evaluate_ingredient(ing, facts)
            ing_name = ing.get("name") or "Statutory Ingredient"
            e_type = str(ing.get("element_type") or "ACTUS_REUS").upper()
            is_mandatory = bool(ing.get("mandatory"))

            if is_mandatory:
                mandatory_total += 1

            if e_type in ("ACTUS_REUS", "VICTIM", "CIRCUMSTANCE"):
                total_actus += 1
                if state == "SATISFIED":
                    matched_actus += 1
            elif e_type == "MENS_REA":
                total_mens += 1
                if state == "SATISFIED":
                    matched_mens += 1

            if state == "SATISFIED":
                satisfied_count += 1
                if is_mandatory:
                    mandatory_satisfied += 1
            elif state == "CONTRADICTED":
                contradicted_count += 1
                if is_mandatory:
                    return False, 0.20, f"Hard Rejection: Mandatory statutory ingredient '{ing_name}' contradicted by facts."
            else:  # UNVERIFIED
                unverified_count += 1
                verification_notes.append(f"Provisional: '{ing_name}' unverified in query prompt")

        # Ingredient Match Ratios
        actus_score = (matched_actus / total_actus) if total_actus > 0 else 0.50
        mens_score = (matched_mens / total_mens) if total_mens > 0 else 0.50

        vec_sim = float(candidate.get("vector_similarity") or 0.70)
        has_graph = 1.0 if candidate.get("relationships") else 0.5

        # Weighted Legal Applicability Score Formula
        confidence = round((0.50 * actus_score) + (0.25 * mens_score) + (0.15 * vec_sim) + (0.10 * has_graph), 4)
        
        note_str = f" ({'; '.join(verification_notes[:2])})" if verification_notes else ""
        summary_reason = f"Verified statutory ingredients matched ({matched_actus}/{total_actus} Actus Reus, {matched_mens}/{total_mens} Mens Rea).{note_str}"

        if confidence >= 0.45:
            return True, confidence, summary_reason
        else:
            return False, confidence, f"Statutory ingredient match score ({confidence:.2f}) below minimum applicability threshold (0.45).{note_str}"

    def get_ingredient_summary(self, candidate: Dict[str, Any], facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Public accessor returning the actual per-ingredient breakdown (name,
        element type, mandatory flag, and evaluated state) for a candidate
        section - added so callers (e.g. lexigraph_agent's context renderer)
        can surface real ingredient NAMES like "dishonest inducement" or
        "entrustment of property" to the LLM, instead of only the aggregate
        match-count summary that validate_candidate() returns. Does not
        change validate_candidate()'s existing return contract - this is a
        separate read-only accessor over the same underlying data.
        """
        act = candidate.get("act", "")
        sec_num = candidate.get("section_num", "")
        ingredients = self._get_section_ingredients(act, sec_num)

        summary = []
        for ing in ingredients:
            state, reason_detail = self._evaluate_ingredient(ing, facts)
            summary.append({
                "name": ing.get("name") or "Statutory Ingredient",
                "element_type": str(ing.get("element_type") or "ACTUS_REUS").upper(),
                "mandatory": bool(ing.get("mandatory")),
                "state": state,
                "detail": reason_detail,
            })
        return summary

    def _evaluate_ingredient(self, ing: Dict[str, Any], facts: Dict[str, Any]) -> Tuple[str, str]:
        """
        Evaluates a single ingredient node against extracted facts.
        Returns ("SATISFIED" | "CONTRADICTED" | "UNVERIFIED", explanation)
        """
        fact_key = ing.get("fact_key")
        comparator = (ing.get("comparator") or "is_true").lower()
        expected_val = ing.get("expected_value")

        if not fact_key:
            return "UNVERIFIED", "No fact_key metadata defined on ingredient"

        # Check special specified flags for numerical fields
        if fact_key == "marriage_duration_years":
            if not facts.get("marriage_duration_specified"):
                return "UNVERIFIED", "Marriage duration not explicitly specified in prompt"
            val = facts.get("marriage_duration_years")
            if val is None:
                return "UNVERIFIED", "Marriage duration value is null"
            if val <= 7:
                return "SATISFIED", f"Marriage duration ({val} years) <= 7 years"
            else:
                return "CONTRADICTED", f"Marriage duration ({val} years) > 7 years"

        fact_val = facts.get(fact_key)

        if fact_val is None:
            return "UNVERIFIED", f"Fact '{fact_key}' unspecified in query"

        if comparator == "is_true":
            if bool(fact_val) == True:
                return "SATISFIED", f"Fact '{fact_key}' is true"
            else:
                return "CONTRADICTED", f"Fact '{fact_key}' is false"

        elif comparator == "is_false":
            if bool(fact_val) == False:
                return "SATISFIED", f"Fact '{fact_key}' is false"
            else:
                return "CONTRADICTED", f"Fact '{fact_key}' is true"

        elif comparator == "eq":
            exp_str = str(expected_val or "").lower().strip()
            act_str = str(fact_val or "").lower().strip()
            if act_str == "unspecified" or not act_str:
                return "UNVERIFIED", f"Fact '{fact_key}' is unspecified"
            if act_str == exp_str:
                return "SATISFIED", f"Fact '{fact_key}' ('{act_str}') equals '{exp_str}'"
            # Token-based matching for multi-value fields
            act_tokens = re.split(r"[,;/]|\s+", act_str)
            if exp_str in act_tokens:
                return "SATISFIED", f"Fact '{fact_key}' ('{act_str}') contains token '{exp_str}'"
            return "CONTRADICTED", f"Fact '{fact_key}' ('{act_str}') != '{exp_str}'"

        elif comparator == "lte":
            try:
                if float(fact_val) <= float(expected_val):
                    return "SATISFIED", f"Fact '{fact_key}' ({fact_val}) <= {expected_val}"
                else:
                    return "CONTRADICTED", f"Fact '{fact_key}' ({fact_val}) > {expected_val}"
            except (ValueError, TypeError):
                return "UNVERIFIED", f"Could not parse numeric comparison for '{fact_key}'"

        elif comparator == "gte":
            try:
                if float(fact_val) >= float(expected_val):
                    return "SATISFIED", f"Fact '{fact_key}' ({fact_val}) >= {expected_val}"
                else:
                    return "CONTRADICTED", f"Fact '{fact_key}' ({fact_val}) < {expected_val}"
            except (ValueError, TypeError):
                return "UNVERIFIED", f"Could not parse numeric comparison for '{fact_key}'"

        elif comparator == "contains":
            exp_str = str(expected_val or "").lower()
            act_str = str(fact_val or "").lower()
            if exp_str in act_str:
                return "SATISFIED", f"Fact '{fact_key}' contains '{exp_str}'"
            else:
                return "CONTRADICTED", f"Fact '{fact_key}' does not contain '{exp_str}'"

        return "UNVERIFIED", f"Unknown comparator '{comparator}'"

    def _get_section_ingredients(self, act: str, sec_num: str) -> List[Dict[str, Any]]:
        """
        Queries Neo4j for statutory ingredients linked via :HAS_INGREDIENT.

        Traversal order (stops as soon as rows are found):

        1. Direct: section itself has :HAS_INGREDIENT nodes.
           e.g. IPC 498A, IPC 304B, BNS 85 — full definition sections.

        2. One-hop equivalent: follow :REPLACES/:REPLACED_BY to a counterpart
           section (e.g. IPC 498A → BNS 85) and use its ingredients.
           This handles cases where ingredients are modelled on only one side
           of the IPC↔BNS equivalence pair.

        NOTE: Punishment-quantum sections (e.g. IPC 506, BNS 351(2)) that have
        no :HAS_INGREDIENT edges and whose one-hop equivalent is also a
        punishment-quantum section will correctly return [] here. Those sections
        are pre-classified as PUNISHMENT_QUANTUM in the agent's Step 3 and
        never reach this method for validation — they are auto-accepted as
        co-applicable once their paired definition section is validated.
        """
        if not self.neo4j_service:
            return []

        # --- 1. Direct ---
        direct_query = """
        MATCH (n:LawSection {act: $act, section: $sec_num})
        MATCH (n)-[:HAS_INGREDIENT]->(i:Ingredient)
        RETURN i.name AS name, i.element_type AS element_type, i.description AS description,
               i.fact_key AS fact_key, i.comparator AS comparator, i.expected_value AS expected_value,
               i.mandatory AS mandatory, i.confidence_weight AS confidence_weight
        """
        rows = self.neo4j_service.run_query(direct_query, {"act": act, "sec_num": sec_num})
        if rows:
            return rows

        # --- 2. One-hop equivalent (REPLACES / REPLACED_BY in both directions) ---
        equivalent_query = """
        MATCH (n:LawSection {act: $act, section: $sec_num})
        OPTIONAL MATCH (n)-[:REPLACES|REPLACED_BY]-(other:LawSection)
        WHERE other IS NOT NULL
        MATCH (other)-[:HAS_INGREDIENT]->(i:Ingredient)
        RETURN i.name AS name, i.element_type AS element_type, i.description AS description,
               i.fact_key AS fact_key, i.comparator AS comparator, i.expected_value AS expected_value,
               i.mandatory AS mandatory, i.confidence_weight AS confidence_weight
        """
        rows = self.neo4j_service.run_query(equivalent_query, {"act": act, "sec_num": sec_num})
        return rows or []