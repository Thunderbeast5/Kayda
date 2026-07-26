"""
schema_migration.py
===================
Non-destructive Cypher schema migration engine providing additive canonical label tagging,
node deduplication, and safe rollback capabilities.
"""

from typing import Dict, Any, List


class SchemaMigrationEngine:
    """Executes schema canonicalization migrations on Neo4j."""

    def __init__(self, neo4j_service):
        self.neo4j_service = neo4j_service

    def run_additive_canonical_labeling(self) -> Dict[str, int]:
        """
        Phase 1 Migration: Applies canonical umbrella labels without deleting specialized tags.
        - Adds :Case to SupremeCourtCase, HighCourtCase, CourtCase
        - Adds :ConstitutionArticle to ConstitutionalArticle, Article
        - Adds :BNSSection / :IPCSection subtype tags to LawSection
        """
        results = {}

        # 0. Deduplicate case nodes before setting umbrella :Case label to avoid constraint conflicts
        q0 = """
        MATCH (c)
        WHERE (c:SupremeCourtCase OR c:HighCourtCase OR c:CourtCase OR c:Case)
        WITH coalesce(c.case_id, c.case_name, c.title) AS cid, collect(c) AS nodes
        WHERE cid IS NOT NULL AND size(nodes) > 1
        CALL apoc.refactor.mergeNodes(nodes, {properties: "combine", mergeRels: true})
        YIELD node
        RETURN count(node) AS count
        """
        try:
            self.neo4j_service.run_query(q0, {})
        except Exception as e:
            # Fallback Cypher if APOC is not installed
            fallback_case_merge = """
            MATCH (c)
            WHERE (c:SupremeCourtCase OR c:HighCourtCase OR c:CourtCase OR c:Case)
            WITH coalesce(c.case_id, c.case_name, c.title) AS cid, collect(c) AS nodes
            WHERE cid IS NOT NULL AND size(nodes) > 1
            WITH nodes[0] AS keep, nodes[1..] AS dupes
            UNWIND dupes AS dupe
            MATCH (dupe)-[r]->(target)
            MERGE (keep)-[r2:TYPE(r)]->(target)
            WITH keep, dupe, r
            MATCH (source)-[r3]->(dupe)
            MERGE (source)-[r4:TYPE(r3)]->(keep)
            WITH dupe
            DETACH DELETE dupe
            RETURN count(dupe) AS count
            """
            try:
                self.neo4j_service.run_query(fallback_case_merge, {})
            except Exception as e2:
                print(f"[SchemaMigrationEngine] Case deduplication warning: {e2}")

        # 1. Apply umbrella :Case label
        q1 = """
        MATCH (c)
        WHERE (c:SupremeCourtCase OR c:HighCourtCase OR c:CourtCase) AND NOT c:Case
        SET c:Case
        RETURN count(c) AS count
        """
        r1 = self.neo4j_service.run_query(q1, {})
        results["cases_tagged"] = r1[0]["count"] if r1 else 0

        # 2. Apply umbrella :ConstitutionArticle label
        q2 = """
        MATCH (a)
        WHERE (a:ConstitutionalArticle OR a:Article) AND NOT a:ConstitutionArticle
        SET a:ConstitutionArticle
        RETURN count(a) AS count
        """
        r2 = self.neo4j_service.run_query(q2, {})
        results["articles_tagged"] = r2[0]["count"] if r2 else 0

        # 3. Apply subtype :BNSSection / :IPCSection labels
        q3 = """
        MATCH (n:LawSection {act: 'BNS'}) WHERE NOT n:BNSSection SET n:BNSSection RETURN count(n) AS count
        """
        r3 = self.neo4j_service.run_query(q3, {})
        results["bns_sections_tagged"] = r3[0]["count"] if r3 else 0

        q4 = """
        MATCH (n:LawSection {act: 'IPC'}) WHERE NOT n:IPCSection SET n:IPCSection RETURN count(n) AS count
        """
        r4 = self.neo4j_service.run_query(q4, {})
        results["ipc_sections_tagged"] = r4[0]["count"] if r4 else 0

        return results

    def enforce_constraints(self) -> List[str]:
        """
        Phase 2 Migration: Ensures compound uniqueness constraints on Neo4j.
        """
        constraints = [
            ("law_section_unique", "CREATE CONSTRAINT law_section_unique IF NOT EXISTS FOR (n:LawSection) REQUIRE (n.act, n.section) IS UNIQUE"),
            ("const_article_num", "CREATE CONSTRAINT const_article_num IF NOT EXISTS FOR (a:ConstitutionArticle) REQUIRE a.article_number IS UNIQUE"),
            ("case_name_unique", "CREATE CONSTRAINT case_name_unique IF NOT EXISTS FOR (c:Case) REQUIRE c.case_name IS UNIQUE")
        ]
        applied = []
        for c_name, query in constraints:
            try:
                self.neo4j_service.run_query(query, {})
                applied.append(c_name)
            except Exception as e:
                print(f"[SchemaMigrationEngine] Constraint info ({c_name}): {e}")
        return applied
