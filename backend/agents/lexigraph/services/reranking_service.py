import re
from typing import Dict, Any, List


class RerankingService:
    """
    RerankingService
    
    A specialized retrieval component of Kayda AI.
    Compute a final ranking score for every verified legal candidate.
    Only responsible for scoring and ranking.
    """

    def compute_retrieval_score(self, candidate: Dict[str, Any], query_keywords: List[str], user_query: str = "") -> Dict[str, Any]:
        """
        Computes the keyword match score between query keywords and candidate text,
        applying a penalty for critical crime categories (e.g. assault) present in the title
        but completely unsupported by the user query.
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

        # Critical term mismatch penalty
        penalty = 0.0
        if user_query:
            query_lower = user_query.lower()
            critical_terms = {
                "assault": ["assault", "force", "attack", "threaten", "beat", "hit", "struck", "strike"],
                "murder": ["murder", "kill", "death", "dead", "homicide", "slay", "body"],
                "rape": ["rape", "sexual", "molest", "assault"],
                "kidnapping": ["kidnap", "abduct", "take away", "hostage"],
                "forgery": ["forge", "forger", "fake", "falsify", "counterfeit"],
                "counterfeit": ["counterfeit", "fake", "forge", "coin", "currency", "notes"],
                "extortion": ["extortion", "extort", "blackmail", "threaten"],
                "dacoity": ["dacoity", "dacoit", "gang robbery"],
                "robbery": ["robbery", "rob", "heist"],
                "suicide": ["suicide", "kill self"],
                "dowry": ["dowry", "marriage gift"],
                "cruelty": ["cruelty", "harass", "abuse"],
                "defamation": ["defamation", "defame", "slander", "libel"]
            }
            
            title_words = re.findall(r"\b\w+\b", title)
            for term, triggers in critical_terms.items():
                if term in title_words:
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
        """
        Helper method computing confidence score using multi-signal formula:
        confidence = 0.40 * similarity + 0.30 * keyword_match + 0.20 * graph_relation + 0.10 * metadata_completeness
        """
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
        Computes final multi-signal confidence scores for candidates and ranks them using Step 5 formula:
        
        Final Score = 0.45 * Semantic Similarity 
                    + 0.20 * Keyword Match 
                    + 0.15 * Graph Score 
                    + 0.15 * Community Match
                    + 0.05 * Metadata Score
        """
        verified_candidates = input_json.get("verified_candidates") or []
        primary_intent = input_json.get("primary_intent_community") or ""
        ranked_list = []

        for candidate in verified_candidates:
            # 1. Semantic Similarity (0.45 weight)
            similarity = float(candidate.get("similarity") if candidate.get("similarity") is not None else candidate.get("vector_similarity", 0.0))
            
            # 2. Keyword Match (0.20 weight)
            keyword_match = float(
                candidate.get("keyword_match") if candidate.get("keyword_match") is not None
                else candidate.get("keyword_overlap", 0.0)
            )

            # 3. Graph Score (0.15 weight)
            if "graph_relation" in candidate and candidate["graph_relation"] is not None:
                graph_score = float(candidate["graph_relation"])
            else:
                relationships = candidate.get("relationships") or {}
                if relationships:
                    num_cases = len(relationships.get("landmark_cases") or [])
                    num_articles = len(relationships.get("constitutional_articles") or [])
                    num_offences = len(relationships.get("related_offences") or [])
                    
                    graph_score = 0.5
                    if candidate.get("graph_verified"):
                        graph_score += min(0.2, num_cases * 0.1)
                        graph_score += min(0.1, num_articles * 0.05)
                        graph_score += min(0.2, num_offences * 0.05)
                else:
                    graph_score = 1.0 if candidate.get("graph_verified") else 0.5

            # 4. Community Match (0.15 weight)
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
                community_match = 0.0
            else:
                community_match = 0.5

            # 5. Metadata Score (0.05 weight)
            if "metadata_completeness" in candidate and candidate["metadata_completeness"] is not None:
                metadata_score = float(candidate["metadata_completeness"])
            else:
                metadata_score = 1.0 if candidate.get("metadata_verified") else 0.5

            # Calculate Step 5 Final Score
            confidence = (0.45 * similarity) + \
                         (0.20 * keyword_match) + \
                         (0.15 * graph_score) + \
                         (0.15 * community_match) + \
                         (0.05 * metadata_score)
            
            confidence = round(min(max(confidence, 0.0), 1.0), 4)

            # Construct copy of candidate with confidence and breakdown populated
            updated_candidate = dict(candidate)
            updated_candidate["confidence"] = confidence
            updated_candidate["similarity"] = round(similarity, 4)
            updated_candidate["keyword_match"] = round(keyword_match, 4)
            updated_candidate["community_match"] = round(community_match, 4)
            updated_candidate["score_breakdown"] = {
                "semantic_similarity": round(similarity, 4),
                "keyword_match": round(keyword_match, 4),
                "graph_score": round(graph_score, 4),
                "community_match": round(community_match, 4),
                "metadata_score": round(metadata_score, 4),
                "confidence": confidence,
            }
            
            if "graph_verified" not in updated_candidate:
                updated_candidate["graph_verified"] = bool(graph_score >= 0.5 and candidate.get("graph_verified"))
            if "metadata_verified" not in updated_candidate:
                updated_candidate["metadata_verified"] = bool(metadata_score >= 1.0)

            ranked_list.append(updated_candidate)

        # Sort all candidates by confidence in descending order
        ranked_list = sorted(ranked_list, key=lambda x: x["confidence"], reverse=True)

        return {
            "ranked_candidates": ranked_list
        }

