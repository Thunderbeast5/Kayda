"""
graph_visualizer_service.py

Visualizes GraphRAG traversal paths for debugging.
Shows complete retrieval chain: Section → Cases → Principles → Ingredients → Evidence → Articles
"""

from typing import Dict, Any, List, Optional


class GraphVisualizerService:
    """
    Visualizes Neo4j graph traversal paths to help debug retrieval decisions.
    Shows how each section connects to supporting evidence through the knowledge graph.
    """

    def __init__(self):
        self.visualization_mode = "tree"  # "tree" or "linear"

    def visualize_section_graph(
        self,
        section: str,
        act: str,
        relationships: Dict[str, List[Dict[str, Any]]],
        include_metadata: bool = True
    ) -> str:
        """
        Generate ASCII tree visualization of graph connections for a section.

        Args:
            section: Section number
            act: Act name (IPC, BNS, etc.)
            relationships: Graph relationships dict from verification_service
            include_metadata: Whether to include detailed metadata

        Returns:
            Formatted ASCII tree string
        """
        lines = []
        
        # Root node
        section_display = f"{act} {section}"
        lines.append("┌" + "─" * (len(section_display) + 2) + "┐")
        lines.append(f"│ {section_display} │")
        lines.append("└" + "─" * (len(section_display) + 2) + "┘")
        lines.append("│")

        # Supreme Court Cases
        sc_cases = relationships.get("supreme_court_cases", [])
        if sc_cases:
            lines.append("├─── Supreme Court Cases")
            for i, case in enumerate(sc_cases):
                is_last_sc = (i == len(sc_cases) - 1) and not any([
                    relationships.get("high_court_cases"),
                    relationships.get("constitutional_articles"),
                    relationships.get("legal_principles"),
                    relationships.get("ingredients"),
                    relationships.get("evidence_types")
                ])
                prefix = "│    └── " if is_last_sc else "│    ├── "
                
                case_name = case.get("case_name", "Unknown Case")
                citation = case.get("citation", "")
                year = case.get("year", "")
                
                lines.append(f"{prefix}[CASE] {case_name}")
                if include_metadata and citation:
                    lines.append(f"│         Citation: {citation}")
                if include_metadata and year:
                    lines.append(f"│         Year: {year}")
                
                # Show legal principles from this case
                case_principles = case.get("legal_principles", [])
                if case_principles and include_metadata:
                    for j, principle in enumerate(case_principles[:2]):  # Limit to 2
                        lines.append(f"│         └── [PRINCIPLE] {principle}")

        # High Court Cases
        hc_cases = relationships.get("high_court_cases", [])
        if hc_cases:
            has_more_below = any([
                relationships.get("constitutional_articles"),
                relationships.get("legal_principles"),
                relationships.get("ingredients"),
                relationships.get("evidence_types")
            ])
            lines.append("│")
            lines.append("├─── High Court Cases" if has_more_below else "└─── High Court Cases")
            
            for i, case in enumerate(hc_cases[:5]):  # Limit display to 5
                is_last = (i == len(hc_cases) - 1 or i == 4) and not has_more_below
                prefix = "│    └── " if is_last else "│    ├── "
                if not has_more_below and is_last:
                    prefix = "     └── "
                
                case_name = case.get("case_name", "Unknown Case")
                citation = case.get("citation", "")
                
                lines.append(f"{prefix}[CASE] {case_name}")
                if include_metadata and citation:
                    connector = "     " if (not has_more_below and is_last) else "│    "
                    lines.append(f"{connector}     Citation: {citation}")
            
            if len(hc_cases) > 5:
                connector = "│    " if has_more_below else "     "
                lines.append(f"{connector}└── ... and {len(hc_cases) - 5} more")

        # Constitutional Articles
        articles = relationships.get("constitutional_articles", [])
        if articles:
            has_more_below = any([
                relationships.get("legal_principles"),
                relationships.get("ingredients"),
                relationships.get("evidence_types")
            ])
            lines.append("│")
            lines.append("├─── Constitutional Articles" if has_more_below else "└─── Constitutional Articles")
            
            for i, article in enumerate(articles):
                is_last = (i == len(articles) - 1) and not has_more_below
                prefix = "     └── " if is_last else "│    ├── " if has_more_below else "     ├── "
                
                article_num = article.get("article", "Unknown")
                title = article.get("title", "")
                
                lines.append(f"{prefix}[ARTICLE] {article_num}")
                if include_metadata and title:
                    connector = "          " if is_last else "│         "
                    lines.append(f"{connector}{title}")

        # Legal Principles
        principles = relationships.get("legal_principles", [])
        if principles:
            has_more_below = any([
                relationships.get("ingredients"),
                relationships.get("evidence_types")
            ])
            lines.append("│")
            lines.append("├─── Legal Principles" if has_more_below else "└─── Legal Principles")
            
            for i, principle in enumerate(principles[:5]):  # Limit to 5
                is_last = (i == len(principles) - 1 or i == 4) and not has_more_below
                prefix = "     └── " if is_last else "│    ├── " if has_more_below else "     ├── "
                
                name = principle.get("name", "Unknown")
                lines.append(f"{prefix}[PRINCIPLE] {name}")
            
            if len(principles) > 5:
                connector = "│    " if has_more_below else "     "
                lines.append(f"{connector}└── ... and {len(principles) - 5} more")

        # Statutory Ingredients
        ingredients = relationships.get("ingredients", [])
        if ingredients:
            has_more_below = bool(relationships.get("evidence_types"))
            lines.append("│")
            lines.append("├─── Statutory Ingredients" if has_more_below else "└─── Statutory Ingredients")
            
            for i, ingredient in enumerate(ingredients):
                is_last = (i == len(ingredients) - 1) and not has_more_below
                prefix = "     └── " if is_last else "│    ├── " if has_more_below else "     ├── "
                
                name = ingredient.get("name", "Unknown")
                lines.append(f"{prefix}[INGREDIENT] {name}")
                
                # Show required evidence for this ingredient
                req_evidence = ingredient.get("required_evidence", [])
                if req_evidence and include_metadata:
                    for j, evidence in enumerate(req_evidence[:2]):  # Limit to 2
                        is_last_ev = j == len(req_evidence) - 1 or j == 1
                        ev_connector = "          └── " if is_last_ev else "          ├── "
                        if is_last and is_last_ev:
                            ev_connector = "          └── "
                        elif is_last:
                            ev_connector = "          ├── "
                        else:
                            ev_connector = "│         └── " if is_last_ev else "│         ├── "
                        
                        lines.append(f"{ev_connector}[EVIDENCE] {evidence}")

        # Evidence Types
        evidence_types = relationships.get("evidence_types", [])
        if evidence_types:
            lines.append("│")
            lines.append("└─── Evidence Types")
            
            for i, evidence in enumerate(evidence_types):
                is_last = i == len(evidence_types) - 1
                prefix = "     └── " if is_last else "     ├── "
                
                name = evidence.get("name", "Unknown")
                lines.append(f"{prefix}[EVIDENCE] {name}")

        return "\n".join(lines)

    def visualize_multiple_sections(
        self,
        sections_data: List[Dict[str, Any]],
        max_sections: int = 5
    ) -> str:
        """
        Visualize graph traversal for multiple sections.

        Args:
            sections_data: List of section dicts with relationships
            max_sections: Maximum number of sections to visualize

        Returns:
            Combined visualization string
        """
        lines = []
        lines.append("\n" + "=" * 100)
        lines.append("GRAPH TRAVERSAL VISUALIZATION")
        lines.append("=" * 100)
        lines.append("")

        for i, section_data in enumerate(sections_data[:max_sections], 1):
            act = section_data.get("act", "")
            section = section_data.get("section_num", "")
            title = section_data.get("title", "")
            relationships = section_data.get("relationships", {})
            
            lines.append(f"\n[{i}] {act} {section}: {title}")
            lines.append("")
            
            viz = self.visualize_section_graph(section, act, relationships, include_metadata=False)
            lines.append(viz)
            
            if i < min(len(sections_data), max_sections):
                lines.append("\n" + "-" * 100)

        if len(sections_data) > max_sections:
            lines.append(f"\n... and {len(sections_data) - max_sections} more sections")

        lines.append("\n" + "=" * 100 + "\n")
        return "\n".join(lines)

    def visualize_linear_path(
        self,
        section: str,
        act: str,
        relationships: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Generate linear (arrow-based) visualization of graph path.

        Args:
            section: Section number
            act: Act name
            relationships: Graph relationships dict

        Returns:
            Linear path visualization
        """
        lines = []
        lines.append(f"\n{act} {section}")
        
        # Count connections
        sc_count = len(relationships.get("supreme_court_cases", []))
        hc_count = len(relationships.get("high_court_cases", []))
        article_count = len(relationships.get("constitutional_articles", []))
        principle_count = len(relationships.get("legal_principles", []))
        ingredient_count = len(relationships.get("ingredients", []))
        evidence_count = len(relationships.get("evidence_types", []))

        if sc_count > 0:
            lines.append(f"  ↓")
            lines.append(f"  SC Cases ({sc_count})")
        
        if hc_count > 0:
            lines.append(f"  ↓")
            lines.append(f"  HC Cases ({hc_count})")
        
        if article_count > 0:
            lines.append(f"  ↓")
            lines.append(f"  Constitutional Articles ({article_count})")
        
        if principle_count > 0:
            lines.append(f"  ↓")
            lines.append(f"  Legal Principles ({principle_count})")
        
        if ingredient_count > 0:
            lines.append(f"  ↓")
            lines.append(f"  Statutory Ingredients ({ingredient_count})")
        
        if evidence_count > 0:
            lines.append(f"  ↓")
            lines.append(f"  Evidence Types ({evidence_count})")

        return "\n".join(lines)

    def generate_summary_statistics(
        self,
        sections_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate summary statistics for graph traversal across all sections.

        Args:
            sections_data: List of section dicts with relationships

        Returns:
            Summary statistics dict
        """
        stats = {
            "total_sections": len(sections_data),
            "total_sc_cases": 0,
            "total_hc_cases": 0,
            "total_articles": 0,
            "total_principles": 0,
            "total_ingredients": 0,
            "total_evidence": 0,
            "sections_with_sc_cases": 0,
            "sections_with_hc_cases": 0,
            "sections_with_no_cases": 0,
            "avg_connections_per_section": 0.0
        }

        total_connections = 0

        for section in sections_data:
            relationships = section.get("relationships", {})
            
            sc_cases = relationships.get("supreme_court_cases", [])
            hc_cases = relationships.get("high_court_cases", [])
            articles = relationships.get("constitutional_articles", [])
            principles = relationships.get("legal_principles", [])
            ingredients = relationships.get("ingredients", [])
            evidence = relationships.get("evidence_types", [])

            sc_count = len(sc_cases)
            hc_count = len(hc_cases)
            
            stats["total_sc_cases"] += sc_count
            stats["total_hc_cases"] += hc_count
            stats["total_articles"] += len(articles)
            stats["total_principles"] += len(principles)
            stats["total_ingredients"] += len(ingredients)
            stats["total_evidence"] += len(evidence)

            if sc_count > 0:
                stats["sections_with_sc_cases"] += 1
            if hc_count > 0:
                stats["sections_with_hc_cases"] += 1
            if sc_count == 0 and hc_count == 0:
                stats["sections_with_no_cases"] += 1

            total_connections += sc_count + hc_count + len(articles) + len(principles) + len(ingredients) + len(evidence)

        if stats["total_sections"] > 0:
            stats["avg_connections_per_section"] = total_connections / stats["total_sections"]

        return stats

    def print_summary_statistics(self, stats: Dict[str, Any]):
        """Print formatted summary statistics."""
        print("\n" + "=" * 100)
        print("GRAPH TRAVERSAL SUMMARY STATISTICS")
        print("=" * 100)
        print(f"\nTotal Sections Analyzed        : {stats['total_sections']}")
        print(f"\nCase Law Support:")
        print(f"  Supreme Court Cases          : {stats['total_sc_cases']}")
        print(f"  High Court Cases             : {stats['total_hc_cases']}")
        print(f"  Sections with SC Cases       : {stats['sections_with_sc_cases']}")
        print(f"  Sections with HC Cases       : {stats['sections_with_hc_cases']}")
        print(f"  Sections with No Cases       : {stats['sections_with_no_cases']}")
        print(f"\nGraph Connections:")
        print(f"  Constitutional Articles      : {stats['total_articles']}")
        print(f"  Legal Principles             : {stats['total_principles']}")
        print(f"  Statutory Ingredients        : {stats['total_ingredients']}")
        print(f"  Evidence Types               : {stats['total_evidence']}")
        print(f"\nAverage Connections per Section: {stats['avg_connections_per_section']:.2f}")
        print("=" * 100 + "\n")