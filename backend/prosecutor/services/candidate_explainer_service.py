"""
candidate_explainer_service.py

Provides detailed explanations for candidate section selection with multi-signal
scoring breakdown (semantic similarity, keyword match, graph connections, 
community relevance, case support).
"""

from typing import Dict, Any, List, Optional
import re


class CandidateExplainerService:
    """
    Generates human-readable explanations for why legal sections were selected or rejected.
    Breaks down multi-signal scoring and provides reasoning for each decision.
    """

    def __init__(self):
        pass

    def explain_candidate(
        self,
        candidate: Dict[str, Any],
        query: str,
        keywords: List[str],
        community_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive explanation for a single candidate.

        Args:
            candidate: Candidate section dict with scores and metadata
            query: Original user query
            keywords: Extracted keywords from query
            community_name: Primary intent community

        Returns:
            Dict with detailed explanation breakdown
        """
        section = candidate.get("section", "Unknown Section")
        title = candidate.get("title", "")
        
        # Extract scores
        semantic_score = float(candidate.get("similarity", 0.0))
        keyword_score = float(candidate.get("keyword_match", 0.0))
        graph_score = self._compute_graph_score(candidate)
        community_score = self._compute_community_score(candidate, community_name)
        case_score = float(candidate.get("case_similarity", 0.0))
        confidence = float(candidate.get("confidence", 0.0))

        # Generate explanations for each signal
        semantic_explanation = self._explain_semantic_score(semantic_score, query, title)
        keyword_explanation = self._explain_keyword_match(keyword_score, keywords, title, candidate)
        graph_explanation = self._explain_graph_connections(candidate)
        community_explanation = self._explain_community_match(candidate, community_name)
        case_explanation = self._explain_case_support(candidate, case_score)

        # Overall decision reasoning
        decision_reasoning = self._generate_decision_reasoning(
            confidence, semantic_score, keyword_score, graph_score, 
            community_score, case_score
        )

        # Matched keywords
        matched_keywords = self._find_matched_keywords(keywords, title, candidate)

        return {
            "section": section,
            "title": title,
            "confidence": confidence,
            "scores": {
                "semantic_similarity": {
                    "value": semantic_score,
                    "weight": 0.40,
                    "explanation": semantic_explanation
                },
                "keyword_match": {
                    "value": keyword_score,
                    "weight": 0.20,
                    "explanation": keyword_explanation
                },
                "graph_connections": {
                    "value": graph_score,
                    "weight": 0.15,
                    "explanation": graph_explanation
                },
                "community_relevance": {
                    "value": community_score,
                    "weight": 0.10,
                    "explanation": community_explanation
                },
                "case_support": {
                    "value": case_score,
                    "weight": 0.10,
                    "explanation": case_explanation
                }
            },
            "matched_keywords": matched_keywords,
            "decision_reasoning": decision_reasoning,
            "strengths": self._identify_strengths(candidate, semantic_score, keyword_score, graph_score),
            "weaknesses": self._identify_weaknesses(candidate, semantic_score, keyword_score, graph_score)
        }

    def explain_candidate_batch(
        self,
        candidates: List[Dict[str, Any]],
        query: str,
        keywords: List[str],
        community_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate explanations for multiple candidates."""
        return [
            self.explain_candidate(c, query, keywords, community_name)
            for c in candidates
        ]

    def print_candidate_explanation(self, explanation: Dict[str, Any]):
        """Print formatted explanation for a candidate."""
        print("\n" + "=" * 80)
        print(f"CANDIDATE EXPLANATION: {explanation['section']}")
        print("=" * 80)
        print(f"Title: {explanation['title']}")
        print(f"Overall Confidence: {explanation['confidence']:.4f}")
        
        print("\n[SCORING BREAKDOWN]")
        for signal_name, signal_data in explanation['scores'].items():
            print(f"\n{signal_name.upper().replace('_', ' ')}:")
            print(f"  Score: {signal_data['value']:.4f} (weight: {signal_data['weight']})")
            print(f"  Contribution: {signal_data['value'] * signal_data['weight']:.4f}")
            print(f"  Explanation: {signal_data['explanation']}")

        if explanation['matched_keywords']:
            print(f"\n[MATCHED KEYWORDS]")
            print(f"  {', '.join(explanation['matched_keywords'])}")

        if explanation['strengths']:
            print(f"\n[STRENGTHS]")
            for strength in explanation['strengths']:
                print(f"  • {strength}")

        if explanation['weaknesses']:
            print(f"\n[WEAKNESSES]")
            for weakness in explanation['weaknesses']:
                print(f"  • {weakness}")

        print(f"\n[DECISION REASONING]")
        print(f"  {explanation['decision_reasoning']}")
        print("=" * 80)

    def _explain_semantic_score(self, score: float, query: str, title: str) -> str:
        """Explain semantic similarity score."""
        if score >= 0.85:
            return f"Very high semantic similarity ({score:.3f}). The section title '{title}' is conceptually very close to the query intent."
        elif score >= 0.70:
            return f"High semantic similarity ({score:.3f}). Strong conceptual match between query and section content."
        elif score >= 0.55:
            return f"Moderate semantic similarity ({score:.3f}). Partial conceptual alignment with query."
        elif score >= 0.40:
            return f"Low semantic similarity ({score:.3f}). Weak conceptual match with query."
        else:
            return f"Very low semantic similarity ({score:.3f}). Minimal conceptual alignment with query."

    def _explain_keyword_match(self, score: float, keywords: List[str], title: str, candidate: Dict[str, Any]) -> str:
        """Explain keyword matching score."""
        if score >= 0.70:
            return f"Strong keyword overlap ({score:.3f}). Multiple query keywords appear in section title/description."
        elif score >= 0.40:
            return f"Moderate keyword overlap ({score:.3f}). Some query keywords match section content."
        elif score >= 0.20:
            return f"Weak keyword overlap ({score:.3f}). Few query keywords found in section."
        else:
            return f"No significant keyword overlap ({score:.3f}). Query keywords not prominent in section."

    def _explain_graph_connections(self, candidate: Dict[str, Any]) -> str:
        """Explain graph connectivity score."""
        relationships = candidate.get("relationships", {})
        
        connection_counts = {
            "cases": len(relationships.get("supreme_court_cases", [])) + len(relationships.get("high_court_cases", [])),
            "articles": len(relationships.get("constitutional_articles", [])),
            "principles": len(relationships.get("legal_principles", [])),
            "evidence": len(relationships.get("evidence_types", [])),
            "ingredients": len(relationships.get("ingredients", []))
        }

        total_connections = sum(connection_counts.values())

        if total_connections >= 10:
            return f"Rich graph connectivity ({total_connections} connections): {connection_counts['cases']} cases, {connection_counts['articles']} articles, {connection_counts['principles']} principles, {connection_counts['evidence']} evidence types, {connection_counts['ingredients']} ingredients. Well-established in legal knowledge graph."
        elif total_connections >= 5:
            return f"Moderate graph connectivity ({total_connections} connections): {connection_counts['cases']} cases, {connection_counts['articles']} articles, {connection_counts['principles']} principles. Adequately supported in knowledge graph."
        elif total_connections >= 2:
            return f"Limited graph connectivity ({total_connections} connections). Basic presence in knowledge graph but fewer supporting relationships."
        else:
            return f"Minimal graph connectivity ({total_connections} connections). Isolated section with few graph relationships."

    def _explain_community_match(self, candidate: Dict[str, Any], community_name: Optional[str]) -> str:
        """Explain community relevance score."""
        candidate_community = candidate.get("community_id", "")
        
        if not community_name:
            return "Community relevance not evaluated (no primary intent detected)."
        
        if candidate_community and community_name.lower() in candidate_community.lower():
            return f"Strong community match. Section belongs to '{candidate_community}' community, aligning with query intent '{community_name}'."
        elif candidate_community:
            return f"Different community. Section belongs to '{candidate_community}' community, which differs from query intent '{community_name}'."
        else:
            return "No community classification available for this section."

    def _explain_case_support(self, candidate: Dict[str, Any], score: float) -> str:
        """Explain case law support score."""
        relationships = candidate.get("relationships", {})
        sc_cases = len(relationships.get("supreme_court_cases", []))
        hc_cases = len(relationships.get("high_court_cases", []))

        if sc_cases > 0 and hc_cases > 0:
            return f"Strong precedent support ({score:.3f}). {sc_cases} Supreme Court and {hc_cases} High Court cases interpreting this section."
        elif sc_cases > 0:
            return f"Supreme Court precedents available ({score:.3f}). {sc_cases} SC cases provide binding interpretation."
        elif hc_cases > 0:
            return f"High Court precedents available ({score:.3f}). {hc_cases} HC cases provide persuasive interpretation."
        else:
            return f"No precedent cases retrieved ({score:.3f}). Section lacks case law support in knowledge graph."

    def _generate_decision_reasoning(
        self, confidence: float, semantic: float, keyword: float,
        graph: float, community: float, case: float
    ) -> str:
        """Generate overall decision reasoning."""
        if confidence >= 0.80:
            strong_signals = []
            if semantic >= 0.75: strong_signals.append("high semantic similarity")
            if keyword >= 0.60: strong_signals.append("strong keyword match")
            if graph >= 0.70: strong_signals.append("rich graph connectivity")
            if case >= 0.70: strong_signals.append("solid case law support")
            
            if strong_signals:
                return f"Selected with high confidence due to: {', '.join(strong_signals)}."
            else:
                return "Selected with high confidence based on overall multi-signal alignment."
        elif confidence >= 0.60:
            return "Selected with moderate confidence. Multiple signals indicate relevance despite some weaknesses."
        elif confidence >= 0.45:
            return "Included despite lower confidence. May be relevant but lacks strong signal support."
        else:
            return "Filtered out due to low confidence. Insufficient signal strength across multiple factors."

    def _find_matched_keywords(self, keywords: List[str], title: str, candidate: Dict[str, Any]) -> List[str]:
        """Find which keywords matched in the candidate."""
        matched = []
        title_lower = title.lower()
        description = str(candidate.get("description", "")).lower()
        punishment = str(candidate.get("punishment", "")).lower()
        
        combined_text = f"{title_lower} {description} {punishment}"
        
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in combined_text or any(kw_lower in word for word in combined_text.split()):
                matched.append(kw)
        
        return matched

    def _identify_strengths(self, candidate: Dict[str, Any], semantic: float, keyword: float, graph: float) -> List[str]:
        """Identify candidate strengths."""
        strengths = []
        
        if semantic >= 0.75:
            strengths.append("Very high semantic similarity to query")
        if keyword >= 0.60:
            strengths.append("Strong keyword match with query terms")
        if graph >= 0.70:
            strengths.append("Well-connected in legal knowledge graph")
        
        relationships = candidate.get("relationships", {})
        sc_cases = len(relationships.get("supreme_court_cases", []))
        if sc_cases > 0:
            strengths.append(f"Supported by {sc_cases} Supreme Court precedent(s)")
        
        if candidate.get("metadata_verified"):
            strengths.append("Verified against Neo4j graph database")
        
        if candidate.get("is_valid"):
            strengths.append("Passed ingredient validation test")
        
        return strengths

    def _identify_weaknesses(self, candidate: Dict[str, Any], semantic: float, keyword: float, graph: float) -> List[str]:
        """Identify candidate weaknesses."""
        weaknesses = []
        
        if semantic < 0.50:
            weaknesses.append("Low semantic similarity to query")
        if keyword < 0.30:
            weaknesses.append("Weak keyword match")
        if graph < 0.40:
            weaknesses.append("Limited graph connectivity")
        
        relationships = candidate.get("relationships", {})
        total_cases = len(relationships.get("supreme_court_cases", [])) + len(relationships.get("high_court_cases", []))
        if total_cases == 0:
            weaknesses.append("No precedent cases retrieved")
        
        if not candidate.get("is_valid"):
            weaknesses.append(f"Failed ingredient validation: {candidate.get('validation_reason', 'Unknown')}")
        
        return weaknesses

    def _compute_graph_score(self, candidate: Dict[str, Any]) -> float:
        """Compute normalized graph connectivity score."""
        relationships = candidate.get("relationships", {})
        
        # Count different types of connections
        sc_cases = len(relationships.get("supreme_court_cases", []))
        hc_cases = len(relationships.get("high_court_cases", []))
        articles = len(relationships.get("constitutional_articles", []))
        principles = len(relationships.get("legal_principles", []))
        evidence = len(relationships.get("evidence_types", []))
        
        # Weighted scoring (SC cases more valuable)
        score = (
            sc_cases * 0.3 +
            hc_cases * 0.2 +
            articles * 0.2 +
            principles * 0.15 +
            evidence * 0.15
        )
        
        # Normalize to 0-1 range (assume max 10 connections of each type)
        normalized = min(score / 5.0, 1.0)
        
        return normalized

    def _compute_community_score(self, candidate: Dict[str, Any], community_name: Optional[str]) -> float:
        """Compute community match score."""
        if not community_name:
            return 0.5  # Neutral
        
        candidate_community = candidate.get("community_id", "")
        
        if candidate_community and community_name.lower() in candidate_community.lower():
            return 1.0  # Perfect match
        elif candidate_community:
            return 0.3  # Different community
        else:
            return 0.5  # Unknown
