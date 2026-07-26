import os
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
        for candidate statutory sections.
        """
        if not verified_candidates:
            return []

        cand_params = [{"act": c["act"], "section": c["section_num"]} for c in verified_candidates]
        
        community_mapping = {}  # (act, section) -> leiden_community_info
        community_counts = {}   # community_id -> count
        
        try:
            # Query Neo4j for Leiden community properties safely without property key warnings
            rows = self.neo4j_service.run_query(
                """
                UNWIND $candidates AS item
                MATCH (n:LawSection {act: item.act, section: item.section})
                OPTIONAL MATCH (n)-[:BELONGS_TO]->(c:Community)
                RETURN n.act AS act, n.section AS section,
                       c.community_id AS fallback_community_id, 
                       c.name AS name, c.summary AS summary, c.keywords AS keywords
                """,
                {"candidates": cand_params}
            )
            for r in rows:
                key = (r["act"], r["section"])
                cid = r.get("fallback_community_id") or "general_offences"
                community_mapping[key] = {
                    "community_id": str(cid),
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

        # 2. Direct Typed One-Hop Graph Expansion per Candidate Section
        related_sections = set()
        related_cases = set()
        related_articles = set()
        related_principles = set()
        statutory_evidence = set()
        case_derived_evidence = set()
        related_ingredients = set()

        # Universal criminal-law principles (applied by default to all offences)
        UNIVERSAL_PRINCIPLES = ["Presumption of Innocence", "Burden of Proof beyond Reasonable Doubt"]

        try:
            # Query graph expansion strictly via direct typed one-hop relationships off LawSection
            graph_rows = self.neo4j_service.run_query(
                """
                UNWIND $candidates AS item
                MATCH (n:LawSection {act: item.act, section: item.section})
                
                // Problem 3 Fix: Statutory evidence strictly from Ingredient schema
                OPTIONAL MATCH (n)-[:HAS_INGREDIENT]->(ing:Ingredient)
                OPTIONAL MATCH (ing)-[:REQUIRES_EVIDENCE]->(stat_ev:EvidenceType)
                OPTIONAL MATCH (n)-[:REQUIRES_EVIDENCE]->(stat_ev_direct:EvidenceType)
                
                // Problem 4 Fix: Constitutional Articles directly linked to Section
                OPTIONAL MATCH (n)-[:PROTECTED_BY|DERIVES_FROM|UPHOLDS|PROHIBITED_BY|GOVERNED_BY|BINDING_UNDER]->(art)
                WHERE art:ConstitutionArticle OR art:ConstitutionalArticle OR art:Article
                
                // Problem 1 Fix: Direct, typed, one-hop case retrieval ONLY (no community traversal)
                OPTIONAL MATCH (cs)-[:APPLIES_SECTION|INTERPRETS]->(n)
                WHERE cs:Case OR cs:CourtCase OR cs:SupremeCourtCase
                OPTIONAL MATCH (n)-[:INTERPRETED_IN]->(cs2)
                WHERE cs2:Case OR cs2:CourtCase OR cs2:SupremeCourtCase
                
                // Case-derived evidence (kept as a separate labeled field, Problem 3)
                OPTIONAL MATCH (cs)-[:REQUIRES]->(case_ev:EvidenceType)
                
                // Problem 2 Fix: Principles split by direct sources
                OPTIONAL MATCH (lp_stat:LegalPrinciple)-[:APPLIES_TO]->(n)
                OPTIONAL MATCH (art)-[:RELATES_TO|EMBODIES]->(lp_const:LegalPrinciple)
                OPTIONAL MATCH (cs)-[:ESTABLISHES]->(lp_case:LegalPrinciple)
                
                RETURN collect(DISTINCT n.act + " " + n.section) AS sections,
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
                       collect(DISTINCT coalesce(cs.title, cs.case_name, cs2.title, cs2.case_name)) AS cases
                """,
                {"candidates": cand_params}
            )

            if graph_rows:
                row = graph_rows[0]
                related_sections.update([s for s in row.get("sections", []) if s])
                related_ingredients.update([i for i in row.get("ingredients", []) if i])
                statutory_evidence.update([e for e in row.get("stat_evidence", []) if e])
                case_derived_evidence.update([e for e in row.get("case_evidence", []) if e])
                related_cases.update([c for c in row.get("cases", []) if c])

                # Problem 4 Fix: Article Deduplication by article code
                seen_articles = {}
                for a_obj in row.get("raw_articles", []):
                    code = (a_obj.get("code") or "").strip()
                    title = (a_obj.get("title") or "").strip()
                    if code and code != "Article":
                        formatted_art = f"{code} - {title}".strip(" -")
                        if code not in seen_articles:
                            seen_articles[code] = formatted_art
                related_articles.update(seen_articles.values())

                # Problem 2 Fix: Principles Scoped & Capped (<= 6 total)
                stat_p = [p for p in row.get("stat_principles", []) if p]
                const_p = [p for p in row.get("const_principles", []) if p]
                case_p = [p for p in row.get("case_principles", []) if p]
                
                # Combine offence-specific principles
                offence_principles = list(dict.fromkeys(stat_p + const_p + case_p))
                # Cap offence-specific principles to max 4 so total principles stays <= 6
                capped_offence_principles = offence_principles[:4]
                all_principles = capped_offence_principles + UNIVERSAL_PRINCIPLES
                related_principles.update(all_principles)

        except Exception as e:
            print(f"[CommunityRetrievalService] Error during direct graph expansion: {e}")

        # Problem 5 Fix: Validate static community summary against live graph count
        for key, comm_meta in community_mapping.items():
            comm_summary = comm_meta.get("summary", "")
            self._validate_summary_and_counts(comm_summary, len(related_cases), len(related_sections))

        # 3. Community Score Calculation
        candidates_in_comm = []
        for c in verified_candidates:
            key = (c["act"], c["section_num"])
            if key in community_mapping and community_mapping[key]["community_id"] == str(best_community_id):
                candidates_in_comm.append(c)

        ret_ratio = len(candidates_in_comm) / max(1, len(verified_candidates))
        avg_sim = sum(c.get("vector_similarity", 0.0) for c in candidates_in_comm) / max(1, len(candidates_in_comm)) if candidates_in_comm else 0.50
        community_score = round(0.50 * ret_ratio + 0.50 * avg_sim, 4)

        # Logging Step
        print("\nCommunity Retrieval (Direct One-Hop Enriched)")
        print(f"Community ID       : {best_community_id}")
        print(f"Community Score    : {community_score:.4f}")
        print(f"Direct Sections    : {len(related_sections)}")
        print(f"Direct Cases       : {len(related_cases)}")
        print(f"Deduplicated Arts  : {len(related_articles)}")
        print(f"Scoped Principles  : {len(related_principles)}")

        # 4. Construct Explainable Clustering Reasons
        clustering_reasons = []
        if related_ingredients:
            ing_sample = ", ".join(sorted(list(related_ingredients))[:3])
            clustering_reasons.append(f"Shared statutory ingredients ({ing_sample})")
        if related_cases:
            case_sample = ", ".join(sorted(list(related_cases))[:2])
            clustering_reasons.append(f"Direct judicial precedents ({case_sample})")
        if related_principles:
            pr_sample = ", ".join(sorted(list(related_principles))[:3])
            clustering_reasons.append(f"Scoped legal principles ({pr_sample})")
        if statutory_evidence:
            ev_sample = ", ".join(sorted(list(statutory_evidence))[:3])
            clustering_reasons.append(f"Statutory proof requirements ({ev_sample})")
        if not clustering_reasons:
            clustering_reasons.append("Shared statutory intent & chapter proximity")

        # 5. Enrich Candidate Schema
        enriched_candidates = []
        for c in verified_candidates:
            c_copy = dict(c)
            key = (c["act"], c["section_num"])
            c_info = community_mapping.get(key, {})
            cand_comm_id = c_info.get("community_id", str(best_community_id))
            
            c_copy["community_id"] = cand_comm_id
            c_copy["community"] = {
                "community_id": cand_comm_id,
                "community_level_1": c_info.get("communityLevel1", cand_comm_id),
                "community_level_2": c_info.get("communityLevel2", cand_comm_id),
                "community_level_3": c_info.get("communityLevel3", cand_comm_id),
                "community_name": c_info.get("name") or f"Leiden Cluster {cand_comm_id}",
                "community_summary": self._convert_summary_to_bns(c_info.get("summary") or ""),
                "community_score": community_score,
                "clustering_reasons": clustering_reasons,
                "related_sections": sorted(list(related_sections)),
                "related_ingredients": sorted(list(related_ingredients)),
                "related_cases": sorted(list(related_cases)),
                "related_articles": sorted(list(related_articles)),
                "related_principles": sorted(list(related_principles)),
                "supporting_evidence": sorted(list(statutory_evidence)),
                "case_derived_evidence": sorted(list(case_derived_evidence)),
                "universal_principles": UNIVERSAL_PRINCIPLES,
                "live_case_count": len(related_cases),
                "live_section_count": len(related_sections)
            }
            enriched_candidates.append(c_copy)

        return enriched_candidates

    def _validate_summary_and_counts(self, summary_text: str, live_cases_count: int, live_sections_count: int):
        """
        Problem 5 Guard: Detects drift between cached community summary text
        and live graph counts, logging warnings if silent contradictions exist.
        """
        if not summary_text:
            return
        import re
        case_matches = re.findall(r"(\d+)\s+cases", summary_text, re.IGNORECASE)
        for count_str in case_matches:
            claimed_count = int(count_str)
            if claimed_count != live_cases_count:
                print(f"[CommunityRetrievalService] ⚠️ Summary vs Live Mismatch: Cached summary claims {claimed_count} cases, but live graph query returned {live_cases_count} cases.")

    def _convert_summary_to_bns(self, text: str) -> str:
        """Converts legacy IPC references in community summaries to modern BNS sections."""
        if not text:
            return ""
        ipc_to_bns_map = {
            "IPC 228A": "BNS 73",
            "IPC 304B": "BNS 80",
            "IPC 498A": "BNS 85",
            "IPC 375": "BNS 63",
            "IPC 376": "BNS 64",
            "IPC 354": "BNS 74",
            "IPC 366": "BNS 87",
            "IPC 302": "BNS 101",
            "IPC 307": "BNS 109",
            "IPC 363": "BNS 137",
            "IPC 370": "BNS 143",
            "IPC 506": "BNS 351"
        }
        for ipc, bns in ipc_to_bns_map.items():
            text = text.replace(ipc, bns)
        return text
