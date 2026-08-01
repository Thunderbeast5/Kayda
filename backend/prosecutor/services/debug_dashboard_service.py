"""
debug_dashboard_service.py

Comprehensive debug dashboard that integrates all debug services to provide
complete visibility into the GraphRAG pipeline from query to final output.
"""

from typing import Dict, Any, List, Optional
from .pipeline_debug_service import PipelineDebugService
from .candidate_explainer_service import CandidateExplainerService
from .graph_visualizer_service import GraphVisualizerService
from .precedent_ranking_service import PrecedentRankingService
import json


class DebugDashboardService:
    """
    Integrated debug dashboard providing comprehensive pipeline visualization.
    Combines pipeline flow, candidate explanations, graph traversal, and case rankings.
    """

    def __init__(self):
        self.pipeline_debug = PipelineDebugService()
        self.candidate_explainer = CandidateExplainerService()
        self.graph_visualizer = GraphVisualizerService()
        self.precedent_ranker = PrecedentRankingService()

    def generate_full_dashboard(
        self,
        query: str,
        production_output: Dict[str, Any],
        prosecutor_result: Optional[Dict[str, Any]] = None,
        include_graph_viz: bool = True,
        include_candidate_explanations: bool = True,
        include_case_rankings: bool = True
    ) -> str:
        """
        Generate complete debug dashboard with all pipeline information.

        Args:
            query: Original user query
            production_output: LexiGraphAgent production output
            prosecutor_result: Optional prosecutor turn result
            include_graph_viz: Whether to include graph visualizations
            include_candidate_explanations: Whether to include candidate explanations
            include_case_rankings: Whether to include case ranking details

        Returns:
            Formatted dashboard string
        """
        lines = []
        
        # HEADER
        lines.append("\n" + "=" * 120)
        lines.append(" " * 40 + "KAYDA AI - DEBUG DASHBOARD")
        lines.append("=" * 120)
        
        # SECTION 1: QUERY INFORMATION
        lines.append(self._format_query_section(query, production_output))
        
        # SECTION 2: PIPELINE FLOW
        lines.append(self._format_pipeline_flow(production_output))
        
        # SECTION 3: QUERY EXPANSION
        lines.append(self._format_query_expansion(production_output))
        
        # SECTION 4: RETRIEVAL RESULTS
        lines.append(self._format_retrieval_results(production_output))
        
        # SECTION 5: CANDIDATE EXPLANATIONS
        if include_candidate_explanations:
            lines.append(self._format_candidate_explanations(query, production_output))
        
        # SECTION 6: GRAPH TRAVERSAL VISUALIZATION
        if include_graph_viz:
            lines.append(self._format_graph_visualization(production_output))
        
        # SECTION 7: CASE RANKINGS
        if include_case_rankings:
            lines.append(self._format_case_rankings(query, production_output))
        
        # SECTION 8: VERIFICATION RESULTS
        if prosecutor_result:
            lines.append(self._format_verification_results(prosecutor_result))
        
        # SECTION 9: FINAL OUTPUT
        lines.append(self._format_final_output(production_output, prosecutor_result))
        
        # SECTION 10: RECOMMENDATIONS
        lines.append(self._format_recommendations(production_output, prosecutor_result))
        
        # FOOTER
        lines.append("\n" + "=" * 120)
        lines.append(" " * 45 + "END OF DASHBOARD")
        lines.append("=" * 120 + "\n")
        
        return "\n".join(lines)

    def _format_query_section(self, query: str, output: Dict[str, Any]) -> str:
        """Format query information section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 45 + "SECTION 1: QUERY INFORMATION" + " " * 45 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        lines.append(f"\nOriginal Query:")
        lines.append(f"  {query}")
        
        role = output.get("role", "neutral")
        lines.append(f"\nRole: {role.upper()}")
        
        pipeline_conf = output.get("pipeline_confidence", 0.0)
        lines.append(f"Pipeline Confidence: {pipeline_conf:.4f}")
        
        # Confidence interpretation
        if pipeline_conf >= 0.80:
            conf_level = "HIGH - Strong retrieval and validation"
        elif pipeline_conf >= 0.60:
            conf_level = "MODERATE - Reasonable retrieval quality"
        elif pipeline_conf >= 0.45:
            conf_level = "LOW - Limited retrieval support"
        else:
            conf_level = "VERY LOW - Insufficient evidence retrieved"
        
        lines.append(f"Confidence Level: {conf_level}")
        
        community = output.get("community")
        if community:
            lines.append(f"\nDetected Community: {community.get('community_name', 'Unknown')}")
            lines.append(f"Community Score: {community.get('community_score', 0.0):.4f}")
        
        return "\n".join(lines)

    def _format_pipeline_flow(self, output: Dict[str, Any]) -> str:
        """Format pipeline flow section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 47 + "SECTION 2: PIPELINE FLOW" + " " * 47 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        debug_data = output.get("debug", {})
        
        if debug_data:
            decision = debug_data.get("decision", {})
            lines.append(f"\nLLM Reasoning Invoked: {decision.get('invoke_reasoning', 'Unknown')}")
            lines.append(f"Reason: {decision.get('reason', 'N/A')}")
        
        # Section counts through pipeline
        recommended = output.get("recommended_sections", [])
        rejected = output.get("rejected_sections", [])
        
        lines.append(f"\n[PIPELINE PROGRESSION]")
        lines.append(f"  Pinecone Retrieval       → (check logs above)")
        lines.append(f"  Candidate Filtering      → (check logs above)")
        lines.append(f"  Metadata Verification    → (check logs above)")
        lines.append(f"  Graph Enrichment         → (check logs above)")
        lines.append(f"  Community Retrieval      → (check logs above)")
        lines.append(f"  Multi-Signal Scoring     → (check logs above)")
        lines.append(f"  Ingredient Validation    → Passed: {len(recommended)}, Rejected: {len(rejected)}")
        lines.append(f"  Final Output             → {len(recommended)} sections")
        
        return "\n".join(lines)

    def _format_query_expansion(self, output: Dict[str, Any]) -> str:
        """Format query expansion section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 45 + "SECTION 3: QUERY EXPANSION" + " " * 47 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        # This would come from debug data if we stored it
        lines.append("\n(Query expansion details logged during pipeline execution)")
        
        return "\n".join(lines)

    def _format_retrieval_results(self, output: Dict[str, Any]) -> str:
        """Format retrieval results section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 44 + "SECTION 4: RETRIEVAL RESULTS" + " " * 46 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        recommended = output.get("recommended_sections", [])
        rejected = output.get("rejected_sections", [])
        supporting_cases = output.get("supporting_cases", [])
        similar_cases = output.get("similar_cases", [])
        articles = output.get("supporting_articles", [])
        evidence = output.get("supporting_evidence", [])
        principles = output.get("supporting_principles", [])
        
        lines.append(f"\n[STATUTORY SECTIONS]")
        lines.append(f"  Recommended: {len(recommended)}")
        lines.append(f"  Rejected: {len(rejected)}")
        
        lines.append(f"\n[CASE LAW]")
        lines.append(f"  Graph-Linked Cases: {len(supporting_cases)}")
        sc_count = sum(1 for c in supporting_cases if "Supreme" in c.get("court", ""))
        hc_count = len(supporting_cases) - sc_count
        lines.append(f"    - Supreme Court: {sc_count}")
        lines.append(f"    - High Court: {hc_count}")
        lines.append(f"  Semantically Similar Cases: {len(similar_cases)}")
        
        lines.append(f"\n[SUPPORTING CONTEXT]")
        lines.append(f"  Constitutional Articles: {len(articles)}")
        lines.append(f"  Evidence Types: {len(evidence)}")
        lines.append(f"  Legal Principles: {len(principles)}")
        
        # Show top recommended sections
        if recommended:
            lines.append(f"\n[TOP RECOMMENDED SECTIONS]")
            for i, sec in enumerate(recommended[:3], 1):
                act = sec.get("act", "")
                section = sec.get("section", "")
                title = sec.get("title", "")
                conf = sec.get("confidence", 0.0)
                lines.append(f"  {i}. {act} {section}: {title}")
                lines.append(f"     Confidence: {conf:.4f}")
        
        # Show rejected sections
        if rejected:
            lines.append(f"\n[REJECTED SECTIONS]")
            for i, rej in enumerate(rejected[:3], 1):
                section = rej.get("section", "")
                reason = rej.get("reason", "")
                lines.append(f"  {i}. {section}: {reason[:80]}...")
        
        return "\n".join(lines)

    def _format_candidate_explanations(self, query: str, output: Dict[str, Any]) -> str:
        """Format candidate explanations section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 42 + "SECTION 5: CANDIDATE EXPLANATIONS" + " " * 43 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        debug_data = output.get("debug", {})
        ranked_candidates = debug_data.get("ranked_candidates", [])
        
        if not ranked_candidates:
            lines.append("\n(No candidate explanations available - enable debug mode)")
            return "\n".join(lines)
        
        # Generate explanations for top 3 candidates
        community = output.get("community", {})
        community_name = community.get("community_name") if community else None
        
        lines.append(f"\n[TOP 3 CANDIDATE EXPLANATIONS]")
        
        for i, candidate in enumerate(ranked_candidates[:3], 1):
            section = candidate.get("section", "Unknown")
            title = candidate.get("title", "")
            conf = candidate.get("confidence", 0.0)
            
            lines.append(f"\n{i}. {section}: {title}")
            lines.append(f"   Overall Confidence: {conf:.4f}")
            
            # Scoring breakdown
            semantic = candidate.get("similarity", 0.0)
            keyword = candidate.get("keyword_match", 0.0)
            case_sim = candidate.get("case_similarity", 0.0)
            
            lines.append(f"   Scores:")
            lines.append(f"     - Semantic Similarity: {semantic:.3f} (weight: 0.40)")
            lines.append(f"     - Keyword Match: {keyword:.3f} (weight: 0.20)")
            lines.append(f"     - Case Support: {case_sim:.3f} (weight: 0.10)")
            
            # Graph connections
            rel = candidate.get("relationships", {})
            sc_cases = len(rel.get("supreme_court_cases", []))
            hc_cases = len(rel.get("high_court_cases", []))
            
            if sc_cases + hc_cases > 0:
                lines.append(f"   Precedents: {sc_cases} SC, {hc_cases} HC")
        
        return "\n".join(lines)

    def _format_graph_visualization(self, output: Dict[str, Any]) -> str:
        """Format graph visualization section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 42 + "SECTION 6: GRAPH TRAVERSAL PATHS" + " " * 44 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        debug_data = output.get("debug", {})
        ranked_candidates = debug_data.get("ranked_candidates", [])
        
        if not ranked_candidates:
            lines.append("\n(No graph data available - enable debug mode)")
            return "\n".join(lines)
        
        # Visualize top 2 sections
        sections_to_viz = []
        for candidate in ranked_candidates[:2]:
            sections_to_viz.append({
                "act": candidate.get("act", ""),
                "section_num": candidate.get("section_num", ""),
                "title": candidate.get("title", ""),
                "relationships": candidate.get("relationships", {})
            })
        
        if sections_to_viz:
            viz = self.graph_visualizer.visualize_multiple_sections(sections_to_viz, max_sections=2)
            lines.append(viz)
        
        # Summary statistics
        stats = self.graph_visualizer.generate_summary_statistics(ranked_candidates)
        lines.append(f"\n[GRAPH STATISTICS ACROSS ALL CANDIDATES]")
        lines.append(f"  Total Sections: {stats['total_sections']}")
        lines.append(f"  Supreme Court Cases: {stats['total_sc_cases']}")
        lines.append(f"  High Court Cases: {stats['total_hc_cases']}")
        lines.append(f"  Constitutional Articles: {stats['total_articles']}")
        lines.append(f"  Legal Principles: {stats['total_principles']}")
        lines.append(f"  Avg Connections/Section: {stats['avg_connections_per_section']:.2f}")
        
        return "\n".join(lines)

    def _format_case_rankings(self, query: str, output: Dict[str, Any]) -> str:
        """Format case rankings section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 46 + "SECTION 7: CASE RANKINGS" + " " * 48 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        supporting_cases = output.get("supporting_cases", [])
        similar_cases = output.get("similar_cases", [])
        
        if not supporting_cases and not similar_cases:
            lines.append("\n(No cases retrieved)")
            return "\n".join(lines)
        
        # Show top 5 graph-linked cases
        if supporting_cases:
            lines.append(f"\n[GRAPH-LINKED CASES (Top 5)]")
            for i, case in enumerate(supporting_cases[:5], 1):
                case_name = case.get("case_name", "Unknown")
                citation = case.get("citation", "N/A")
                court = case.get("court", "Unknown")
                year = case.get("year", "")
                ranking_score = case.get("ranking_score")
                
                lines.append(f"\n  {i}. {case_name}")
                lines.append(f"     Citation: {citation}")
                lines.append(f"     Court: {court} ({year})")
                if ranking_score is not None:
                    lines.append(f"     Ranking Score: {ranking_score:.4f}")
        
        # Show top 3 similar cases
        if similar_cases:
            lines.append(f"\n[SEMANTICALLY SIMILAR CASES (Top 3)]")
            for i, case in enumerate(similar_cases[:3], 1):
                case_name = case.get("case_name", "Unknown")
                court = case.get("court", "Unknown")
                similarity = case.get("similarity", 0.0)
                ranking_score = case.get("ranking_score")
                
                lines.append(f"\n  {i}. {case_name}")
                lines.append(f"     Court: {court}")
                lines.append(f"     Semantic Similarity: {similarity:.4f}")
                if ranking_score is not None:
                    lines.append(f"     Ranking Score: {ranking_score:.4f}")
        
        return "\n".join(lines)

    def _format_verification_results(self, prosecutor_result: Dict[str, Any]) -> str:
        """Format verification results section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 43 + "SECTION 8: VERIFICATION RESULTS" + " " * 44 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        verification = prosecutor_result.get("verification", {})
        
        is_clean = verification.get("is_clean", True)
        lines.append(f"\nVerification Status: {'✓ CLEAN' if is_clean else '✗ ISSUES FOUND'}")
        
        # Verified citations
        verified_sections = verification.get("verified_sections", [])
        verified_cases = verification.get("verified_cases", [])
        
        lines.append(f"\n[VERIFIED CITATIONS]")
        lines.append(f"  Sections: {len(verified_sections)}")
        lines.append(f"  Cases: {len(verified_cases)}")
        
        # Issues
        hallucinated = verification.get("hallucinated_sections", [])
        ungrounded = verification.get("real_but_ungrounded_sections", [])
        unverified_cases = verification.get("unverified_cases", [])
        
        if hallucinated:
            lines.append(f"\n[⚠️  HALLUCINATED SECTIONS]")
            for sec in hallucinated:
                lines.append(f"  - {sec} (NOT IN NEO4J DATABASE)")
        
        if ungrounded:
            lines.append(f"\n[⚠️  REAL BUT UNGROUNDED SECTIONS]")
            for sec in ungrounded:
                lines.append(f"  - {sec} (exists but not retrieved this turn)")
        
        if unverified_cases:
            lines.append(f"\n[⚠️  UNVERIFIED CASES]")
            for case in unverified_cases:
                lines.append(f"  - {case}")
        
        if is_clean:
            lines.append(f"\n✓ All citations verified against Neo4j knowledge graph")
        
        return "\n".join(lines)

    def _format_final_output(self, output: Dict[str, Any], prosecutor_result: Optional[Dict[str, Any]]) -> str:
        """Format final output section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 47 + "SECTION 9: FINAL OUTPUT" + " " * 49 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        if prosecutor_result:
            theory = prosecutor_result.get("theory_of_case", "")
            if theory:
                lines.append(f"\n[THEORY OF THE CASE]")
                lines.append(f"{theory}")
            
            spoken = prosecutor_result.get("spoken_argument", "")
            if spoken:
                lines.append(f"\n[SPOKEN ARGUMENT]")
                # Truncate for dashboard
                lines.append(f"{spoken[:500]}...")
                lines.append(f"\n(Full argument: {len(spoken)} characters)")
        else:
            recommended = output.get("recommended_sections", [])
            lines.append(f"\n{len(recommended)} sections recommended")
            lines.append(f"{len(output.get('supporting_cases', []))} precedent cases retrieved")
        
        return "\n".join(lines)

    def _format_recommendations(self, output: Dict[str, Any], prosecutor_result: Optional[Dict[str, Any]]) -> str:
        """Format recommendations section."""
        lines = ["\n" + "╔" + "=" * 118 + "╗"]
        lines.append("║" + " " * 46 + "SECTION 10: RECOMMENDATIONS" + " " * 45 + "║")
        lines.append("╚" + "=" * 118 + "╝")
        
        recommendations = []
        
        # Check pipeline confidence
        conf = output.get("pipeline_confidence", 0.0)
        if conf < 0.60:
            recommendations.append("⚠️  Low pipeline confidence - consider refining query or checking data quality")
        
        # Check case support
        supporting_cases = output.get("supporting_cases", [])
        if len(supporting_cases) == 0:
            recommendations.append("⚠️  No precedent cases retrieved - consider ingesting more case law")
        
        sc_count = sum(1 for c in supporting_cases if "Supreme" in c.get("court", ""))
        if sc_count == 0 and len(supporting_cases) > 0:
            recommendations.append("💡 No Supreme Court cases found - High Court precedents available")
        
        # Check verification
        if prosecutor_result:
            verification = prosecutor_result.get("verification", {})
            if not verification.get("is_clean"):
                recommendations.append("❌ Verification issues detected - review unverified citations")
        
        # Check rejected sections
        rejected = output.get("rejected_sections", [])
        if len(rejected) > len(output.get("recommended_sections", [])):
            recommendations.append("💡 More sections rejected than recommended - ingredient validation is strict")
        
        if not recommendations:
            recommendations.append("✓ Pipeline execution successful - no issues detected")
        
        lines.append("")
        for rec in recommendations:
            lines.append(f"  {rec}")
        
        return "\n".join(lines)

    def export_dashboard_json(
        self,
        query: str,
        production_output: Dict[str, Any],
        prosecutor_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export dashboard data as JSON for programmatic access."""
        return {
            "query": query,
            "role": production_output.get("role", "neutral"),
            "pipeline_confidence": production_output.get("pipeline_confidence", 0.0),
            "retrieval_counts": {
                "recommended_sections": len(production_output.get("recommended_sections", [])),
                "rejected_sections": len(production_output.get("rejected_sections", [])),
                "supporting_cases": len(production_output.get("supporting_cases", [])),
                "similar_cases": len(production_output.get("similar_cases", [])),
                "articles": len(production_output.get("supporting_articles", [])),
                "evidence": len(production_output.get("supporting_evidence", [])),
                "principles": len(production_output.get("supporting_principles", []))
            },
            "verification": prosecutor_result.get("verification", {}) if prosecutor_result else None,
            "debug_data": production_output.get("debug", {})
        }
