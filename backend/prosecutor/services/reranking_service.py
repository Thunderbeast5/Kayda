"""
reranking_service.py
====================
Reranks verified legal candidates using a multi‑signal formula that now incorporates:
- Graph connectivity (Supreme Court cases, High Court cases, legal principles, evidence types)
- Ingredient validation confidence
- Vector similarity
- Community match
- Case similarity
- Metadata completeness
"""

from typing import Dict, Any, List


class RerankingService:
    """
    RerankingService

    Compute a final ranking score for every verified legal candidate.
    Only responsible for scoring and ranking.
    """

    def compute_retrieval_score(self, candidate: Dict[str, Any], query_keywords: List[str], user_query: str = "") -> Dict[str, Any]:
        """
        Computes the keyword match score between query keywords and candidate text,
        applying a penalty for critical crime categories (e.g. economic offences, POCSO)
        present in the title but completely unsupported by the user query.
        """
        title = str(candidate.get("title") or "").lower()
        punishment = str(candidate.get("punishment") or "").lower()
        full_text = f"{title} {punishment}".lower()

        matched_keywords = []
        keyword_match_count = 0
        for kw in query_keywords:
            kw_clean = kw.lower().strip()
            if not kw_clean:
                continue
            if kw_clean in full_text:
                keyword_match_count += 1
                matched_keywords.append(kw)

        keyword_score = keyword_match_count / len(query_keywords) if query_keywords else 0.0

        # Critical term mismatch penalty – updated for anticipatory bail
        penalty = 0.0
        if user_query:
            query_lower = user_query.lower()
            critical_terms = {
                # 1. Economic Offences
                "economic_offence": [
                    "economic", "fraud", "scam", "embezzlement", "money laundering",
                    "company", "bank", "loan", "investment", "public funds",
                    "PMLA", "Companies Act", "SFIO"
                ],
                # 2. POCSO Offences
                "pocso": [
                    "POCSO", "child", "minor", "sexual assault", "rape", "abuse",
                    "digital blackmail", "exploitation"
                ],
                # 3. NDPS Offences
                "ndps": [
                    "NDPS", "narcotic", "drug", "psychotropic", "commercial quantity",
                    "codeine", "cough syrup", "substance"
                ],
                # 4. Fraud & Forgery
                "fraud_forgery": [
                    "fraud", "forgery", "cheating", "counterfeit", "fake document",
                    "impersonation", "420", "467", "471", "468"
                ],
                # 5. Grave Violent Offences
                "grave_violence": [
                    "murder", "culpable homicide", "rape", "dacoity", "terrorism",
                    "national security", "UAPA"
                ]
            }

            title_words = re.findall(r"\b\w+\b", title)
            for category, triggers in critical_terms.items():
                # If the title contains the category name (e.g., "economic_offence")
                if category in title_words:
                    has_trigger = any(trig in query_lower for trig in triggers)
                    if not has_trigger:
                        penalty += 0.30

        keyword_score = max(0.0, keyword_score - penalty)
        vector_sim = candidate.get("vector_similarity") or candidate.get("similarity") or 0.0

        final_score = (0.70 * vector_sim) + (0.30 * keyword_score)

        return {
            "score": round(final_score, 4),
            "keyword_overlap": round(keyword_score, 4),
            "matched_keywords": matched_keywords
        }

    def compute_reranked_confidence(
        self,
        semantic_similarity: float,
        keyword_overlap: float,
        graph_verified: bool,
        has_mappings: bool,
        metadata: Dict[str, Any]
    ) -> float:
        """Legacy helper; kept for compatibility."""
        graph_relation = 1.0 if graph_verified else 0.5
        missing_count = 0
        if not metadata.get("chapter"):
            missing_count += 1
        if not metadata.get("status"):
            missing_count += 1
        metadata_completeness = max(1.0 - (0.2 * missing_count), 0.0)

        confidence = (0.40 * semantic_similarity) + \
                     (0.30 * keyword_overlap) + \
                     (0.20 * graph_relation) + \
                     (0.10 * metadata_completeness)
        return round(min(max(confidence, 0.0), 1.0), 4)

    def rerank_candidates(self, input_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Computes final multi‑signal confidence scores for candidates and ranks them.

        New scoring components:
        - vector_similarity (35%)
        - ingredient_confidence (20%)
        - graph_score (15%) – now derived from:
            * number of Supreme Court cases
            * number of High Court cases
            * number of legal principles
            * number of evidence types
        - community_match (10%)
        - case_similarity (10%)
        - metadata_completeness (10%)

        The graph_score is normalised so that a section with at least 3 SC cases,
        2 principles, and 2 evidence types gets a score near 1.0.
        """
        verified_candidates = input_json.get("verified_candidates") or []
        primary_intent = input_json.get("primary_intent_community") or ""
        avg_top_case_sim = float(input_json.get("top_case_similarity", 0.70))
        ranked_list = []

        for candidate in verified_candidates:
            # 1. Semantic Similarity (35% weight)
            similarity = float(candidate.get("similarity") if candidate.get("similarity") is not None else candidate.get("vector_similarity", 0.0))

            # 2. Ingredient Score (20% weight)
            ing_score = float(
                candidate.get("ingredient_confidence")
                if candidate.get("ingredient_confidence") is not None
                else candidate.get("ingredient_score", 0.75)
            )

            # 3. Graph Score (15% weight) – NEW: uses explicit counts
            # If candidate already has `precedent_count`, `principle_count`, `evidence_count`, use them.
            # Otherwise fallback to the old logic (which may look for relationships dict).
            precedent_count = candidate.get("precedent_count", 0)
            principle_count = candidate.get("principle_count", 0)
            evidence_count = candidate.get("evidence_count", 0)

            if precedent_count > 0 or principle_count > 0 or evidence_count > 0:
                # Normalise: target max values for near‑full score
                sc_cap = min(precedent_count, 4)   # SC+HC cases
                princ_cap = min(principle_count, 4)
                ev_cap = min(evidence_count, 4)
                # Weighted: SC/HC cases are most valuable, then principles, then evidence
                graph_score = 0.5 + 0.08 * sc_cap + 0.05 * princ_cap + 0.03 * ev_cap
                graph_score = min(1.0, graph_score)
            else:
                # Old fallback logic (backward compatibility)
                relationships = candidate.get("relationships") or {}
                if relationships:
                    # Try to compute from relationship dict if present
                    sc_cases = relationships.get("supreme_court_cases") or []
                    hc_cases = relationships.get("high_court_cases") or []
                    principles = relationships.get("legal_principles") or []
                    evidence = relationships.get("evidence_types") or []
                    precedent_count = len(sc_cases) + len(hc_cases)
                    principle_count = len(principles)
                    evidence_count = len(evidence)

                    sc_cap = min(precedent_count, 4)
                    princ_cap = min(principle_count, 4)
                    ev_cap = min(evidence_count, 4)
                    graph_score = 0.5 + 0.08 * sc_cap + 0.05 * princ_cap + 0.03 * ev_cap
                    graph_score = min(1.0, graph_score)
                else:
                    # Fallback to simple graph_verified flag
                    graph_score = 1.0 if candidate.get("graph_verified") else 0.5

            # 4. Community Match (10% weight)
            cand_comm = candidate.get("community_id") or candidate.get("community", {}).get("candidate_community_id") or ""
            target_comm = primary_intent or candidate.get("community", {}).get("community_id") or ""

            if cand_comm and target_comm and cand_comm == target_comm:
                community_match = 1.0
            elif (target_comm == "women_offences" and cand_comm == "human_body_offences") or \
                 (target_comm == "children_offences" and cand_comm in ["women_offences", "human_body_offences"]) or \
                 (target_comm == "human_body_offences" and cand_comm in ["women_offences", "children_offences"]):
                community_match = 0.8
            elif cand_comm == "general_offences" or not cand_comm:
                community_match = 0.5
            elif target_comm and cand_comm and cand_comm != target_comm:
                community_match = 0.3
            else:
                community_match = 0.5

            # 5. Case Similarity (10% weight)
            cand_case_sim = candidate.get("case_similarity")
            if cand_case_sim is not None:
                case_similarity = float(cand_case_sim)
            else:
                case_similarity = avg_top_case_sim

            # 6. Metadata Score (10% weight)
            if "metadata_completeness" in candidate and candidate["metadata_completeness"] is not None:
                metadata_score = float(candidate["metadata_completeness"])
            else:
                metadata_score = 1.0 if candidate.get("metadata_verified") else 0.5

            # Combine all signals
            confidence = (0.35 * similarity) + \
                         (0.20 * ing_score) + \
                         (0.15 * graph_score) + \
                         (0.10 * community_match) + \
                         (0.10 * case_similarity) + \
                         (0.10 * metadata_score)

            confidence = round(min(max(confidence, 0.0), 1.0), 4)

            updated_candidate = dict(candidate)
            updated_candidate["confidence"] = confidence
            updated_candidate["similarity"] = round(similarity, 4)
            updated_candidate["ingredient_score"] = round(ing_score, 4)
            updated_candidate["graph_score"] = round(graph_score, 4)
            updated_candidate["community_match"] = round(community_match, 4)
            updated_candidate["case_similarity"] = round(case_similarity, 4)
            updated_candidate["score_breakdown"] = {
                "vector_similarity_35": round(similarity, 4),
                "ingredient_validation_20": round(ing_score, 4),
                "graph_enrichment_15": round(graph_score, 4),
                "community_match_10": round(community_match, 4),
                "case_precedents_10": round(case_similarity, 4),
                "metadata_completeness_10": round(metadata_score, 4),
                "confidence": confidence,
            }

            if "graph_verified" not in updated_candidate:
                updated_candidate["graph_verified"] = bool(graph_score >= 0.5 and candidate.get("graph_verified"))
            if "metadata_verified" not in updated_candidate:
                updated_candidate["metadata_verified"] = bool(metadata_score >= 1.0)

            ranked_list.append(updated_candidate)

        ranked_list = sorted(ranked_list, key=lambda x: x["confidence"], reverse=True)

        return {"ranked_candidates": ranked_list}