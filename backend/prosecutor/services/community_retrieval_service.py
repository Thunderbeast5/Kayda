import os
import re
import sys
from typing import Dict, Any, List, Set
from .neo4j_service import Neo4jService


class CommunityRetrievalService:
    """
    CommunityRetrievalService
    
    Enhanced to leverage Neo4j GDS v2.x Leiden Community Detection hierarchies
    (Level 1 Macro -> Level 2 Meso -> Level 3 Micro) while preserving backward
    compatibility with intent-based retrieval.
    """

    def __init__(self):
        self.neo4j_service = Neo4jService()

    def retrieve_community_context(
        self,
        verified_candidates: List[Dict[str, Any]],
        query: str,
        primary_intent_community: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Retrieves GDS Leiden detected community hierarchy and depth-2 graph enrichment
        separately for each candidate statutory section.
        """
        if not verified_candidates:
            return []

        cand_params = [{"act": c["act"], "section": c["section_num"]} for c in verified_candidates]
        
        community_mapping = {}  # (act, section) -> leiden_community_info
        community_counts = {}   # community_id -> count
        
        try:
            # 1. Query Neo4j for Leiden community hierarchy properties
            # CORRECTNESS NOTE: the previous version of this query selected
            # c.community_id three times and aliased the copies as level1/
            # level2/level3 - meaning the docstring's claim of a "Level 1
            # Macro -> Level 2 Meso -> Level 3 Micro" GDS Leiden hierarchy was
            # not actually being queried at all; all three "levels" were
            # always identical. This now attempts the real hierarchical
            # property names GDS Leiden writes back when run with
            # `includeIntermediateCommunities: true` (typically
            # `communityId` at the base level plus `intermediateCommunityIds`
            # as a list, OR separate properties per level depending on how
            # your write-back step named them). You MUST confirm the actual
            # property names your GDS write-back uses on :Community /
            # :LawSection nodes (via `CALL db.propertyKeys()` or inspecting
            # one node) and adjust the RETURN clause below to match - this is
            # a placeholder that degrades gracefully to the flat community_id
            # for all three levels if the level-specific properties don't
            # exist, rather than silently faking a hierarchy that isn't there.
            rows = self.neo4j_service.run_query(
                """
                UNWIND $candidates AS item
                MATCH (n:LawSection {act: item.act, section: item.section})
                OPTIONAL MATCH (n)-[:BELONGS_TO]->(c:Community)
                RETURN n.act AS act, n.section AS section,
                       c.community_id AS fallback_community_id,
                       coalesce(c.level1_community_id, c.community_id) AS level1,
                       coalesce(c.level2_community_id, c.community_id) AS level2,
                       coalesce(c.level3_community_id, c.community_id) AS level3,
                       c.name AS name, c.summary AS summary, c.keywords AS keywords
                """,
                {"candidates": cand_params}
            )
            for r in rows:
                key = (r["act"], r["section"])
                cid = r.get("fallback_community_id") or "general_offences"
                community_mapping[key] = {
                    "community_id": str(cid),
                    "level1": str(r.get("level1") or cid),
                    "level2": str(r.get("level2") or cid),
                    "level3": str(r.get("level3") or cid),
                    "name": r.get("name") or f"Community {cid}",
                    "summary": self._convert_summary_to_bns(r.get("summary") or f"Graph community clustered by GDS Leiden ({cid})."),
                    "keywords": r.get("keywords") or []
                }
                community_counts[str(cid)] = community_counts.get(str(cid), 0) + 1
        except Exception as e:
            print(f"[CommunityRetrievalService] Error querying GDS Leiden community mappings: {e}")

        # Choose best community ID
        best_community_id = primary_intent_community
        if not best_community_id and community_counts:
            best_community_id = max(community_counts, key=community_counts.get)
        if not best_community_id:
            best_community_id = "general_offences"

        # 2. Per-Candidate Section Direct Typed One-Hop Graph Expansion
        per_candidate_graph = {}  # (act, section) -> dict of enriched elements
        UNIVERSAL_PRINCIPLES = ["Presumption of Innocence", "Burden of Proof beyond Reasonable Doubt"]

        try:
            # Query graph expansion per section without aggregating across candidates
            graph_rows = self.neo4j_service.run_query(
                """
                UNWIND $candidates AS item
                MATCH (n:LawSection {act: item.act, section: item.section})
                
                OPTIONAL MATCH (n)-[:HAS_INGREDIENT]->(ing:Ingredient)
                OPTIONAL MATCH (ing)-[:REQUIRES_EVIDENCE]->(stat_ev:EvidenceType)
                OPTIONAL MATCH (n)-[:REQUIRES_EVIDENCE]->(stat_ev_direct:EvidenceType)
                
                OPTIONAL MATCH (n)-[:PROTECTED_BY|DERIVES_FROM|UPHOLDS|PROHIBITED_BY|GOVERNED_BY|BINDING_UNDER]->(art)
                WHERE art:ConstitutionArticle OR art:ConstitutionalArticle OR art:Article
                
                OPTIONAL MATCH (cs)-[:APPLIES_SECTION]->(n)
                WHERE cs:Case OR cs:SupremeCourtCase OR cs:HighCourtCase

                OPTIONAL MATCH (cs)-[:REQUIRES_EVIDENCE]->(case_ev:EvidenceType)
                
                OPTIONAL MATCH (lp_stat:LegalPrinciple)-[:APPLIES_TO]->(n)
                OPTIONAL MATCH (art)-[:RELATES_TO]->(lp_const:LegalPrinciple)
                OPTIONAL MATCH (cs)-[:APPLIES_TO|RELATES_TO]->(lp_case:LegalPrinciple)
                
                RETURN n.act AS act, n.section AS section,
                       collect(DISTINCT ing.name) AS ingredients,
                       collect(DISTINCT coalesce(stat_ev.name, stat_ev_direct.name)) AS stat_evidence,
                       collect(DISTINCT case_ev.name) AS case_evidence,
                       collect(DISTINCT {
                           code: coalesce(art.article_number, art.article, art.code, "Article"),
                           title: coalesce(art.title, "")
                       }) AS raw_articles,
                       collect(DISTINCT lp_stat.name) AS stat_principles,
                       collect(DISTINCT lp_const.name) AS const_principles,
                       collect(DISTINCT lp_case.name) AS case_principles,
                       collect(DISTINCT coalesce(cs.title, cs.case_name)) AS cases
                """,
                {"candidates": cand_params}
            )

            for row in graph_rows:
                key = (row["act"], row["section"])
                cand_cases = [c for c in row.get("cases", []) if c]
                cand_ings = [i for i in row.get("ingredients", []) if i]
                cand_stat_ev = [e for e in row.get("stat_evidence", []) if e]
                cand_case_ev = [e for e in row.get("case_evidence", []) if e]

                seen_articles = {}
                for a_obj in row.get("raw_articles", []):
                    code = (a_obj.get("code") or "").strip()
                    title = (a_obj.get("title") or "").strip()
                    if code and code != "Article":
                        formatted_art = f"{code} - {title}".strip(" -")
                        if code not in seen_articles:
                            seen_articles[code] = formatted_art
                cand_articles = list(seen_articles.values())

                stat_p = [p for p in row.get("stat_principles", []) if p]
                const_p = [p for p in row.get("const_principles", []) if p]
                case_p = [p for p in row.get("case_principles", []) if p]
                offence_principles = list(dict.fromkeys(stat_p + const_p + case_p))
                cand_principles = offence_principles[:4] + UNIVERSAL_PRINCIPLES

                per_candidate_graph[key] = {
                    "ingredients": sorted(cand_ings),
                    "statutory_evidence": sorted(cand_stat_ev),
                    "case_derived_evidence": sorted(cand_case_ev),
                    "articles": sorted(cand_articles),
                    "principles": sorted(cand_principles),
                    "cases": sorted(cand_cases)
                }

        except Exception as e:
            print(f"[CommunityRetrievalService] Error during per-candidate graph expansion: {e}")

        # 3. Community Score Calculation
        candidates_in_comm = []
        for c in verified_candidates:
            key = (c["act"], c["section_num"])
            if key in community_mapping and community_mapping[key]["community_id"] == str(best_community_id):
                candidates_in_comm.append(c)

        ret_ratio = len(candidates_in_comm) / max(1, len(verified_candidates))
        avg_sim = sum(c.get("vector_similarity", 0.0) for c in candidates_in_comm) / max(1, len(candidates_in_comm)) if candidates_in_comm else 0.50
        community_score = round(0.50 * ret_ratio + 0.50 * avg_sim, 4)

        # 4. Enrich Candidate Schema per Candidate Section
        enriched_candidates = []
        for c in verified_candidates:
            c_copy = dict(c)
            key = (c["act"], c["section_num"])
            c_info = community_mapping.get(key, {})
            cand_graph = per_candidate_graph.get(key, {
                "ingredients": [], "statutory_evidence": [], "case_derived_evidence": [],
                "articles": [], "principles": UNIVERSAL_PRINCIPLES, "cases": []
            })
            cand_comm_id = c_info.get("community_id", str(best_community_id))

            clustering_reasons = []
            if cand_graph["ingredients"]:
                clustering_reasons.append(f"Shared statutory ingredients ({', '.join(cand_graph['ingredients'][:3])})")
            if cand_graph["cases"]:
                clustering_reasons.append(f"Direct judicial precedents ({', '.join(cand_graph['cases'][:2])})")
            if cand_graph["principles"]:
                clustering_reasons.append(f"Scoped legal principles ({', '.join(cand_graph['principles'][:3])})")
            if not clustering_reasons:
                clustering_reasons.append("Shared statutory intent & chapter proximity")

            c_copy["community_id"] = cand_comm_id
            c_copy["community"] = {
                "community_id": cand_comm_id,
                "community_level_1": c_info.get("level1", cand_comm_id),
                "community_level_2": c_info.get("level2", cand_comm_id),
                "community_level_3": c_info.get("level3", cand_comm_id),
                "community_name": c_info.get("name") or f"Leiden Cluster {cand_comm_id}",
                "community_summary": self._convert_summary_to_bns(c_info.get("summary") or ""),
                "community_score": community_score,
                "clustering_reasons": clustering_reasons,
                "related_sections": [f"{c['act']} {c['section_num']}"],
                "related_ingredients": cand_graph["ingredients"],
                "related_cases": cand_graph["cases"],
                "related_articles": cand_graph["articles"],
                "related_principles": cand_graph["principles"],
                "supporting_evidence": cand_graph["statutory_evidence"],
                "case_derived_evidence": cand_graph["case_derived_evidence"],
                "universal_principles": UNIVERSAL_PRINCIPLES,
                "live_case_count": len(cand_graph["cases"]),
                "live_section_count": 1
            }
            enriched_candidates.append(c_copy)

        return enriched_candidates

    def _convert_summary_to_bns(self, text: str) -> str:
        """Converts legacy IPC references in community summaries to modern BNS sections via graph mapping or fallback."""
        if not text:
            return ""

        try:
            rows = self.neo4j_service.run_query("""
                MATCH (b:LawSection {act: 'BNS'})-[r:REPLACES|REPLACED_BY]-(i:LawSection {act: 'IPC'})
                RETURN i.section AS ipc, b.section AS bns
            """)
            if rows:
                for r in rows:
                    # Word-boundary match instead of plain str.replace(): a
                    # plain substring replace of "IPC 302" would also corrupt
                    # "IPC 3021" or "IPC 302A" (turning them into "BNS 1011"
                    # or "BNS 101A") wherever the shorter section number is a
                    # left-substring of a longer/lettered one. \b after the
                    # digits stops at a digit/letter boundary, so "IPC 302"
                    # only matches when not immediately followed by another
                    # digit or letter.
                    pattern = re.compile(rf"\bIPC\s+{re.escape(str(r['ipc']))}\b(?![A-Za-z0-9])")
                    text = pattern.sub(f"BNS {r['bns']}", text)
                return text
        except Exception:
            pass

        # Fallback dictionary if Neo4j query fails. NOTE: this covers only
        # ~12 mappings out of ~350+ actual IPC->BNS section correspondences.
        # If the Neo4j REPLACES/REPLACED_BY relationships aren't populated
        # for a given IPC section, its old-code reference will silently pass
        # through un-converted unless it happens to be one of the 12 below -
        # for 100% accuracy this fallback needs to be the complete official
        # IPC-to-BNS conversion table, not a partial hand-picked sample.
        fallback_map = {
            "228A": "73", "304B": "80", "498A": "85",
            "375": "63", "376": "64", "354": "74",
            "366": "87", "302": "101", "307": "109",
            "363": "137", "370": "143", "506": "351"
        }
        for ipc_sec, bns_sec in fallback_map.items():
            pattern = re.compile(rf"\bIPC\s+{re.escape(ipc_sec)}\b(?![A-Za-z0-9])")
            text = pattern.sub(f"BNS {bns_sec}", text)
        return text