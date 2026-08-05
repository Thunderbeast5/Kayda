"""
Neo4j Independent Retrieval Service

Makes Neo4j a first-class retrieval source instead of only a verification layer.

Retrieval Strategy:
-------------------
1. Takes decomposed legal facts (from query expansion)
2. Uses graph traversal to find candidate LawSection nodes through:
   - Keyword matching on node properties
   - Crime → LawSection relationships
   - Legal principle connections
   - Evidence type associations
   - Related offence patterns

3. Computes graph evidence score for each section using:
   - Ingredient overlap (from Crime nodes)
   - Related offences count
   - Evidence types available
   - Legal principles connected
   - Victim rights associations
   - Constitutional connections

4. Returns scored candidates independently (NOT dependent on LLM results)

This transforms Neo4j from a verification component into an independent
retrieval engine that can surface sections the LLM missed.
"""

from typing import Dict, Any, List, Set, Tuple
from .neo4j_service import Neo4jService


class Neo4jRetrievalService:
    """
    Graph-based section retrieval using Neo4j traversal.
    
    Retrieves candidate LawSection nodes by:
    1. Matching decomposed facts against Keywords, Crime nodes
    2. Traversing relationships to find connected sections
    3. Computing graph evidence scores based on relationship strength
    """
    
    def __init__(self):
        self.neo4j_service = Neo4jService()
        # Cache relationship types to avoid repeated queries
        self._relationship_types_cache: Set[str] = set()
        self._load_relationship_types()
    
    def _load_relationship_types(self):
        """Load available relationship types from graph once."""
        try:
            rows = self.neo4j_service.run_query(
                "CALL db.relationshipTypes()", {}
            )
            self._relationship_types_cache = {
                row.get("relationshipType", "") for row in rows
            }
            print(
                f"[Neo4jRetrievalService] Loaded {len(self._relationship_types_cache)} "
                f"relationship types from graph"
            )
        except Exception as e:
            print(f"[Neo4jRetrievalService] Error loading relationship types: {e}")
    
    def retrieve_sections(
        self,
        sub_queries: List[Dict[str, Any]],
        case_facts: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Main retrieval method using graph traversal.
        
        Parameters
        ----------
        sub_queries : list of dict
            Decomposed legal facts with "query" and "type" keys
        case_facts : str
            Original case facts for context
        top_k : int
            Maximum number of sections to return
        
        Returns
        -------
        List of dict with:
            - section: str (e.g., "IPC 498A")
            - act: str
            - section_num: str
            - graph_score: float (0.0-1.0)
            - evidence: dict (breakdown of graph signals)
            - title: str
            - description: str
        """
        # Extract search terms from sub-queries
        offence_queries = [
            sq for sq in sub_queries if sq.get("type") == "OFFENCE"
        ]
        
        if not offence_queries:
            return []
        
        # Build search terms from queries (keywords, concepts)
        search_terms = self._extract_search_terms(offence_queries, case_facts)
        
        print(
            f"[Neo4jRetrievalService] Retrieving sections for "
            f"{len(search_terms)} search terms..."
        )
        
        # Multi-path retrieval
        candidates: Dict[str, Dict[str, Any]] = {}
        
        # Path 1: Keyword → LawSection direct matching
        keyword_sections = self._retrieve_via_keywords(search_terms)
        self._merge_candidates(candidates, keyword_sections, "keyword_match")
        
        # Path 2: Crime → LawSection ingredient matching
        crime_sections = self._retrieve_via_crimes(search_terms)
        self._merge_candidates(candidates, crime_sections, "crime_ingredient")
        
        # Path 3: Legal principle connections
        principle_sections = self._retrieve_via_principles(search_terms)
        self._merge_candidates(candidates, principle_sections, "legal_principle")
        
        # Path 4: Evidence type associations
        evidence_sections = self._retrieve_via_evidence(search_terms)
        self._merge_candidates(candidates, evidence_sections, "evidence_type")
        
        # Compute graph evidence scores
        scored_candidates = self._compute_graph_scores(
            list(candidates.values()), search_terms
        )
        
        # Sort by graph_score descending
        scored_candidates.sort(key=lambda x: x["graph_score"], reverse=True)
        
        print(
            f"[Neo4jRetrievalService] Retrieved {len(scored_candidates)} candidates; "
            f"returning top {min(top_k, len(scored_candidates))}"
        )
        
        return scored_candidates[:top_k]
    
    def _extract_search_terms(
        self,
        offence_queries: List[Dict[str, Any]],
        case_facts: str
    ) -> List[str]:
        """
        Extract meaningful search terms from queries and case facts.
        
        Returns list of keywords/concepts for graph matching.
        Includes synonym expansion for better graph retrieval.
        """
        terms: Set[str] = set()
        
        # Extract from queries
        for query in offence_queries:
            query_text = query.get("query", "").lower()
            # Split and filter meaningful terms (>3 chars, not stopwords)
            words = query_text.split()
            for word in words:
                cleaned = word.strip(".,;:!?()[]{}\"'")
                if len(cleaned) > 3 and cleaned not in self._get_stopwords():
                    terms.add(cleaned)
        
        # Synonym expansion for common patterns
        case_lower = case_facts.lower()
        
        # Financial fraud synonyms
        if any(word in case_lower for word in ["invest", "investor", "diverted", "divert", "scheme"]):
            terms.update(["trust", "breach", "misappropriation", "entrusted", "criminal", "dishonest"])
        
        if "fictitious" in case_lower or "false" in case_lower:
            terms.update(["fraudulent", "deception", "deceiving", "inducing"])
        
        if "deposit" in case_lower or "money" in case_lower or "funds" in case_lower:
            terms.update(["property", "delivery", "dishonestly"])
        
        # Extract key terms from case facts (limited to avoid noise)
        important_keywords = {
            "dowry", "cruelty", "harassment", "threat", "intimidation",
            "assault", "rape", "sexual", "murder", "death", "hurt",
            "cheat", "fraud", "property", "theft", "robbery",
            "kidnapping", "abduction", "minor", "child",
            "husband", "wife", "woman", "married",
            # Financial fraud keywords
            "investment", "investor", "money", "funds", "deposit",
            "diverted", "divert", "misappropriation", "breach", "trust",
            "entrust", "entrusted", "dishonest", "fictitious", "scheme",
            "return", "returns", "repay", "failed", "deliver"
        }
        
        for keyword in important_keywords:
            if keyword in case_lower:
                terms.add(keyword)
        
        result_list = list(terms)
        print(f"[Neo4jRetrievalService] Extracted {len(result_list)} search terms (with synonyms)")
        return result_list
    
    def _get_stopwords(self) -> Set[str]:
        """Common legal stopwords to exclude from search."""
        return {
            "the", "and", "for", "with", "from", "that", "this",
            "shall", "any", "such", "under", "section", "act",
            "offense", "offence", "person", "said", "being"
        }
    
    def _retrieve_via_keywords(
        self, search_terms: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Path 1: Keyword → LawSection matching.
        
        Finds sections whose title/description contain search terms,
        or are connected to Keyword nodes that match.
        """
        if not search_terms:
            return []
        
        # Query for direct title/description matching + Keyword node matching
        query = """
        UNWIND $terms AS term
        MATCH (n:LawSection)
        WHERE toLower(n.title) CONTAINS term
           OR toLower(n.description) CONTAINS term
           OR toLower(coalesce(n.keywords, '')) CONTAINS term
        OPTIONAL MATCH (n)-[:HAS_KEYWORD]->(k:Keyword)
        WHERE toLower(k.name) CONTAINS term
        RETURN DISTINCT
            n.act AS act,
            n.section AS section,
            n.title AS title,
            n.description AS description,
            count(DISTINCT term) AS term_matches
        ORDER BY term_matches DESC
        LIMIT 30
        """
        
        try:
            rows = self.neo4j_service.run_query(
                query, {"terms": search_terms}
            )
            
            results = []
            for row in rows:
                if row.get("act") and row.get("section"):
                    results.append({
                        "act": row["act"],
                        "section": row["section"],
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                        "signal_strength": float(row.get("term_matches", 1)) / len(search_terms),
                        "retrieval_path": "keyword",
                    })
            
            print(
                f"[Neo4jRetrievalService] Keyword path: {len(results)} sections"
            )
            return results
        
        except Exception as e:
            print(f"[Neo4jRetrievalService] Error in keyword retrieval: {e}")
            return []
    
    def _retrieve_via_crimes(
        self, search_terms: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Path 2: Crime ingredient matching.
        
        Finds Crime nodes matching search terms, then retrieves
        LawSections that define those crimes.
        """
        if not search_terms:
            return []
        
        query = """
        UNWIND $terms AS term
        MATCH (c:Crime)
        WHERE toLower(c.name) CONTAINS term
           OR toLower(coalesce(c.description, '')) CONTAINS term
        MATCH (c)-[:DEFINED_BY]->(n:LawSection)
        RETURN DISTINCT
            n.act AS act,
            n.section AS section,
            n.title AS title,
            n.description AS description,
            count(DISTINCT term) AS term_matches,
            collect(DISTINCT c.name) AS matched_crimes
        ORDER BY term_matches DESC
        LIMIT 30
        """
        
        try:
            rows = self.neo4j_service.run_query(
                query, {"terms": search_terms}
            )
            
            results = []
            for row in rows:
                if row.get("act") and row.get("section"):
                    results.append({
                        "act": row["act"],
                        "section": row["section"],
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                        "signal_strength": float(row.get("term_matches", 1)) / len(search_terms),
                        "retrieval_path": "crime_ingredient",
                        "matched_crimes": row.get("matched_crimes", []),
                    })
            
            print(
                f"[Neo4jRetrievalService] Crime ingredient path: {len(results)} sections"
            )
            return results
        
        except Exception as e:
            print(f"[Neo4jRetrievalService] Error in crime retrieval: {e}")
            return []
    
    def _retrieve_via_principles(
        self, search_terms: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Path 3: Legal principle connections.
        
        Finds LawSections connected to legal principles/rules
        that match search terms.
        """
        if not search_terms:
            return []
        
        # Check if LegalRule nodes exist
        if "LegalRule" not in {"LegalRule"}:  # Placeholder - assumes they might exist
            return []
        
        query = """
        UNWIND $terms AS term
        MATCH (r:LegalRule)
        WHERE toLower(coalesce(r.id, '')) CONTAINS term
           OR toLower(coalesce(r.condition, '')) CONTAINS term
        MATCH (r)-[:APPLIES_FROM|APPLIES_TO]-(n:LawSection)
        RETURN DISTINCT
            n.act AS act,
            n.section AS section,
            n.title AS title,
            n.description AS description,
            count(DISTINCT term) AS term_matches
        ORDER BY term_matches DESC
        LIMIT 20
        """
        
        try:
            rows = self.neo4j_service.run_query(
                query, {"terms": search_terms}
            )
            
            results = []
            for row in rows:
                if row.get("act") and row.get("section"):
                    results.append({
                        "act": row["act"],
                        "section": row["section"],
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                        "signal_strength": float(row.get("term_matches", 1)) / len(search_terms),
                        "retrieval_path": "legal_principle",
                    })
            
            print(
                f"[Neo4jRetrievalService] Legal principle path: {len(results)} sections"
            )
            return results
        
        except Exception as e:
            # LegalRule nodes might not exist - silent fail
            return []
    
    def _retrieve_via_evidence(
        self, search_terms: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Path 4: Evidence type associations.
        
        Finds sections connected to evidence types/keywords
        relevant to search terms.
        """
        if not search_terms:
            return []
        
        query = """
        UNWIND $terms AS term
        MATCH (k:Keyword)
        WHERE toLower(k.name) CONTAINS term
        MATCH (k)<-[:HAS_KEYWORD]-(n:LawSection)
        RETURN DISTINCT
            n.act AS act,
            n.section AS section,
            n.title AS title,
            n.description AS description,
            count(DISTINCT term) AS term_matches
        ORDER BY term_matches DESC
        LIMIT 20
        """
        
        try:
            rows = self.neo4j_service.run_query(
                query, {"terms": search_terms}
            )
            
            results = []
            for row in rows:
                if row.get("act") and row.get("section"):
                    results.append({
                        "act": row["act"],
                        "section": row["section"],
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                        "signal_strength": float(row.get("term_matches", 1)) / len(search_terms),
                        "retrieval_path": "evidence_type",
                    })
            
            print(
                f"[Neo4jRetrievalService] Evidence type path: {len(results)} sections"
            )
            return results
        
        except Exception as e:
            print(f"[Neo4jRetrievalService] Error in evidence retrieval: {e}")
            return []
    
    def _merge_candidates(
        self,
        candidates: Dict[str, Dict[str, Any]],
        new_results: List[Dict[str, Any]],
        path_name: str
    ):
        """
        Merge new results into candidate dictionary.
        
        Accumulates retrieval paths and signal strengths.
        """
        for result in new_results:
            key = f"{result['act']} {result['section']}"
            
            if key not in candidates:
                candidates[key] = result
                candidates[key]["retrieval_paths"] = [path_name]
                candidates[key]["path_signals"] = {path_name: result.get("signal_strength", 0.5)}
            else:
                # Accumulate paths
                if path_name not in candidates[key]["retrieval_paths"]:
                    candidates[key]["retrieval_paths"].append(path_name)
                    candidates[key]["path_signals"][path_name] = result.get("signal_strength", 0.5)
                    # Update signal strength (max across paths)
                    if result.get("signal_strength", 0) > candidates[key].get("signal_strength", 0):
                        candidates[key]["signal_strength"] = result["signal_strength"]
    
    def _compute_graph_scores(
        self,
        candidates: List[Dict[str, Any]],
        search_terms: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Compute comprehensive graph evidence score for each candidate.
        
        Uses graph signals:
        - Retrieval path count (more paths = stronger signal)
        - Signal strength from matching
        - Related offences count
        - Evidence types available
        - Legal principles connected
        - Victim rights associations
        - Ingredient coverage
        """
        if not candidates:
            return []
        
        # Batch query for graph enrichment - use only relationships that exist
        sections = [
            {"act": c["act"], "section": c["section"]}
            for c in candidates
        ]
        
        # Build relationship pattern from only available relationships
        related_rels = []
        for rel in ["RELATED_TO", "MORE_SPECIFIC_THAN", "OVERRIDES", "ENHANCES"]:
            if rel in self._relationship_types_cache:
                related_rels.append(rel)
        
        # Query for relationship counts (all in one batch)
        if related_rels:
            rel_pattern = "|".join(f"`{r}`" for r in related_rels)
            enrichment_query = f"""
            UNWIND $sections AS sec
            MATCH (n:LawSection {{act: sec.act, section: sec.section}})
            OPTIONAL MATCH (n)-[:{rel_pattern}]-(related:LawSection)
            OPTIONAL MATCH (n)-[:HAS_KEYWORD]->(k:Keyword)
            OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(n)
            OPTIONAL MATCH (n)-[:PROTECTED_BY|DERIVES_FROM|UPHOLDS]-(a:ConstitutionalArticle)
            OPTIONAL MATCH (r:LegalRule)-[:APPLIES_FROM|APPLIES_TO]-(n)
            RETURN
                sec.act AS act,
                sec.section AS section,
                count(DISTINCT related) AS related_count,
                count(DISTINCT k) AS evidence_count,
                count(DISTINCT c) AS ingredient_count,
                count(DISTINCT a) AS constitutional_count,
                count(DISTINCT r) AS principle_count
            """
        else:
            # No related relationships exist - skip that part
            enrichment_query = """
            UNWIND $sections AS sec
            MATCH (n:LawSection {act: sec.act, section: sec.section})
            OPTIONAL MATCH (n)-[:HAS_KEYWORD]->(k:Keyword)
            OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(n)
            OPTIONAL MATCH (n)-[:PROTECTED_BY|DERIVES_FROM|UPHOLDS]-(a:ConstitutionalArticle)
            OPTIONAL MATCH (r:LegalRule)-[:APPLIES_FROM|APPLIES_TO]-(n)
            RETURN
                sec.act AS act,
                sec.section AS section,
                0 AS related_count,
                count(DISTINCT k) AS evidence_count,
                count(DISTINCT c) AS ingredient_count,
                count(DISTINCT a) AS constitutional_count,
                count(DISTINCT r) AS principle_count
            """
        
        try:
            enrichment = self.neo4j_service.run_query(
                enrichment_query, {"sections": sections}
            )
            
            # Build enrichment map
            enrichment_map = {}
            for row in enrichment:
                key = f"{row['act']} {row['section']}"
                enrichment_map[key] = row
        
        except Exception as e:
            print(f"[Neo4jRetrievalService] Error in enrichment query: {e}")
            enrichment_map = {}
        
        # Compute scores
        for candidate in candidates:
            key = f"{candidate['act']} {candidate['section']}"
            enrich = enrichment_map.get(key, {})
            
            # Score components (normalized 0-1)
            path_count = len(candidate.get("retrieval_paths", []))
            path_score = min(1.0, path_count / 4.0)  # 4 paths = max
            
            signal_strength = candidate.get("signal_strength", 0.5)
            
            related_count = enrich.get("related_count", 0)
            related_score = min(1.0, related_count / 5.0)  # 5+ related = max
            
            evidence_count = enrich.get("evidence_count", 0)
            evidence_score = min(1.0, evidence_count / 3.0)  # 3+ evidence = max
            
            ingredient_count = enrich.get("ingredient_count", 0)
            ingredient_score = min(1.0, ingredient_count / 2.0)  # 2+ ingredients = max
            
            constitutional_count = enrich.get("constitutional_count", 0)
            constitutional_score = min(1.0, constitutional_count / 1.0)
            
            principle_count = enrich.get("principle_count", 0)
            principle_score = min(1.0, principle_count / 2.0)
            
            # Weighted combination (tuned for sparse graphs - less penalty for missing relationships)
            graph_score = (
                0.25 * path_score +           # Multiple paths = strong signal
                0.35 * signal_strength +       # Direct match quality (increased from 0.25)
                0.20 * ingredient_score +      # Has crime definitions (increased from 0.15)
                0.05 * related_score +         # Connected to other sections (decreased - sparse)
                0.10 * evidence_score +        # Evidence types available
                0.03 * principle_score +       # Legal rules apply (decreased - sparse)
                0.02 * constitutional_score    # Constitutional connections (decreased - sparse)
            )
            
            # Boost score if multiple retrieval paths agree (high confidence signal)
            if path_count >= 2:
                graph_score = min(1.0, graph_score * 1.15)  # 15% boost
            
            if path_count >= 3:
                graph_score = min(1.0, graph_score * 1.25)  # Additional 10% boost
            
            candidate["graph_score"] = graph_score
            candidate["evidence"] = {
                "path_count": path_count,
                "retrieval_paths": candidate.get("retrieval_paths", []),
                "signal_strength": signal_strength,
                "related_offences": related_count,
                "evidence_types": evidence_count,
                "ingredients": ingredient_count,
                "constitutional_links": constitutional_count,
                "legal_principles": principle_count,
            }
        
        return candidates
