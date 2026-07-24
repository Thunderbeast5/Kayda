import os
import sys
from typing import Dict, Any, List, Set
from .neo4j_service import Neo4jService

class CommunityRetrievalService:
    """
    CommunityRetrievalService
    
    Responsible for retrieving related graph communities, performing depth-2 graph expansion,
    calculating community confidence scores, and enriching candidate sections with community contexts.
    """

    def __init__(self):
        self.neo4j_service = Neo4jService()

    def retrieve_community_context(self, verified_candidates: List[Dict[str, Any]], query: str, primary_intent_community: str = "") -> List[Dict[str, Any]]:
        """
        Retrieves community context for the list of verified candidates.
        Determines the best community prioritizing primary_intent_community, performs depth-2 graph traversal,
        calculates scores, and enriches candidates with a 'community' field.
        """
        if not verified_candidates:
            return []

        # 1. Map candidates to their communities via Neo4j
        cand_params = [{"act": c["act"], "section": c["section_num"]} for c in verified_candidates]
        
        community_mapping = {} # (act, section) -> community_info
        community_counts = {}  # community_id -> count of candidates
        
        try:
            rows = self.neo4j_service.run_query(
                """
                UNWIND $candidates AS item
                MATCH (n:LawSection {act: item.act, section: item.section})-[:BELONGS_TO]->(c:Community)
                RETURN n.act as act, n.section as section, c.community_id as community_id, 
                       c.name as name, c.summary as summary, c.keywords as keywords
                """,
                {"candidates": cand_params}
            )
            for r in rows:
                key = (r["act"], r["section"])
                community_mapping[key] = {
                    "community_id": r["community_id"],
                    "name": r["name"],
                    "summary": r["summary"],
                    "keywords": r["keywords"] or []
                }
                cid = r["community_id"]
                community_counts[cid] = community_counts.get(cid, 0) + 1
        except Exception as e:
            print(f"[CommunityRetrievalService] Error querying community mappings: {e}")

        # Choose primary_intent_community if provided, else most frequent community
        best_community_id = primary_intent_community
        if not best_community_id and community_counts:
            best_community_id = max(community_counts, key=community_counts.get)

        if not best_community_id:
            # Fallback to general offences if no communities were mapped
            best_community_id = "general_offences"


        # 2. Retrieve details and perform Graph Traversal/Expansion (Depth = 2) from sections in best community
        community_name = ""
        community_summary = ""
        community_keywords = []
        
        # Initialize sets to aggregate unique connected elements
        related_sections = set()
        related_cases = set()
        related_articles = set()
        related_principles = set()
        related_evidence = set()

        try:
            # Get community info
            comm_rows = self.neo4j_service.run_query(
                """
                MATCH (c:Community {community_id: $community_id})
                RETURN c.name as name, c.summary as summary, c.keywords as keywords
                """,
                {"community_id": best_community_id}
            )
            if comm_rows:
                community_name = comm_rows[0]["name"] or ""
                community_summary = comm_rows[0]["summary"] or ""
                community_keywords = comm_rows[0]["keywords"] or []

            # Perform depth-2 graph traversal along the requested relationship types
            # Starting from sections in the community
            graph_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                MATCH path = (n)-[r:BELONGS_TO|PROTECTED_BY|SUPPORTED_BY|INTERPRETED_BY|APPLIES_TO*1..2]-(m)
                RETURN labels(m) as labels, properties(m) as props
                """,
                {"community_id": best_community_id}
            )


            for row in graph_rows:
                lbls = row["labels"]
                props = row["props"]
                if "LawSection" in lbls:
                    related_sections.add(f"{props.get('act')} {props.get('section')}")
                elif "SupremeCourtCase" in lbls or "HighCourtCase" in lbls:
                    related_cases.add(props.get("case_name"))
                elif "ConstitutionalArticle" in lbls:
                    related_articles.add(props.get("article"))
                elif "LegalPrinciple" in lbls:
                    related_principles.add(props.get("name"))
                elif "EvidenceType" in lbls:
                    related_evidence.add(props.get("name"))

        except Exception as e:
            print(f"[CommunityRetrievalService] Error during graph expansion query: {e}")

        # 3. Calculate Community Score
        candidates_in_comm = []
        for c in verified_candidates:
            key = (c["act"], c["section_num"])
            if key in community_mapping and community_mapping[key]["community_id"] == best_community_id:
                candidates_in_comm.append(c)

        query_lower = query.lower()
        keyword_overlap = 0
        for kw in community_keywords:
            if kw.lower() in query_lower:
                keyword_overlap += 1
        kw_score = min(1.0, keyword_overlap / max(1, len(community_keywords)))

        ret_ratio = len(candidates_in_comm) / max(1, len(verified_candidates))
        avg_sim = sum(c.get("vector_similarity", 0.0) for c in candidates_in_comm) / max(1, len(candidates_in_comm)) if candidates_in_comm else 0.0

        community_score = 0.4 * ret_ratio + 0.4 * avg_sim + 0.2 * kw_score

        # 4. Logging Step
        print("\nCommunity Retrieval")
        print(f"Community Name : {community_name}")
        print(f"Community Score : {community_score:.4f}")
        print(f"Community Sections : {len(related_sections)}")
        print(f"Community Cases : {len(related_cases)}")
        print(f"Community Articles : {len(related_articles)}")

        # 5. Enrich candidate schema
        enriched_candidates = []
        for c in verified_candidates:
            c_copy = dict(c)
            key = (c["act"], c["section_num"])
            cand_comm_id = community_mapping.get(key, {}).get("community_id", best_community_id)
            c_copy["community_id"] = cand_comm_id
            c_copy["community"] = {
                "community_id": best_community_id,
                "candidate_community_id": cand_comm_id,
                "community_name": community_name,
                "community_summary": community_summary,
                "community_score": round(community_score, 4),
                "related_sections": sorted(list(related_sections)),
                "related_cases": sorted(list(related_cases)),
                "related_articles": sorted(list(related_articles)),
                "related_principles": sorted(list(related_principles)),
                "related_evidence": sorted(list(related_evidence))
            }
            enriched_candidates.append(c_copy)

        return enriched_candidates

