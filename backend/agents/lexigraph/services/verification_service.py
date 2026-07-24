from typing import Dict, Any, List
from .neo4j_service import Neo4jService


class VerificationService:
    """
    VerificationService
    
    Verifies candidate sections against the Neo4j Graph Database.
    Validates Act (IPC ↔ BNS) mappings and extracts connected offences.
    """

    def __init__(self):
        self.neo4j_service = Neo4jService()

    def get_node_info(self, act: str, section: str) -> Dict[str, Any]:
        """Queries node properties in Neo4j."""
        query = """
            MATCH (n:LawSection {act: $act, section: $section})
            RETURN n.section AS section, n.title AS title, n.description AS description, 
                   n.punishment AS punishment, n.chapter AS chapter, n.category AS category,
                   n.keywords AS keywords, n.act AS act
            LIMIT 1
        """
        rows = self.neo4j_service.run_query(query, {"act": act, "section": section})
        if rows:
            return rows[0]
        return {}

    def get_mappings(self, act: str, section: str) -> List[Dict[str, Any]]:
        """Retrieves replacement links (IPC ↔ BNS)."""
        mappings = []
        rows = self.neo4j_service.run_query(
            """
            MATCH (n:LawSection {act: $act, section: $section})-[r:REPLACED_BY|REPLACES]-(other:LawSection)
            WHERE other.act <> $act
            RETURN other.section AS section, other.act AS act, r.status AS status, other.title AS title
            """,
            {"act": act, "section": section}
        )
        seen = set()
        for r in rows:
            eq_sec = f"{r['act']} {r['section']}"
            if eq_sec not in seen:
                seen.add(eq_sec)
                mappings.append({
                    "equivalent_section": eq_sec,
                    "status": r.get("status") or "Replaced",
                    "title": r.get("title") or ""
                })
        return mappings

    def get_connected_nodes(self, act: str, section: str) -> List[Dict[str, Any]]:
        """Retrieves rule-linked sections, crimes, and IPC/BNS crosswalk neighbours."""
        connected: List[Dict[str, Any]] = []
        seen: set = set()
        params = {"act": act, "section": section}

        rule_rows = self.neo4j_service.run_query(
            """
            MATCH (n:LawSection {act: $act, section: $section})-[rule:MORE_SPECIFIC_THAN|OVERRIDES|ENHANCES]-(other:LawSection)
            RETURN type(rule) AS relation, other.act AS act, other.section AS section, other.title AS title
            """,
            params,
        )
        for r in rule_rows:
            sec_name = f"{r['act']} {r['section']}"
            key = (r["relation"], sec_name)
            if key not in seen:
                seen.add(key)
                connected.append({
                    "relation": r["relation"],
                    "section": sec_name,
                    "title": r.get("title") or "",
                    "kind": "rule_expansion",
                })

        map_rows = self.neo4j_service.run_query(
            """
            MATCH (n:LawSection {act: $act, section: $section})-[map:REPLACED_BY|REPLACES]-(other:LawSection)
            RETURN DISTINCT other.act AS act, other.section AS section, other.title AS title
            """,
            params,
        )
        for r in map_rows:
            sec_name = f"{r['act']} {r['section']}"
            key = ("act_mapping", sec_name)
            if key not in seen:
                seen.add(key)
                connected.append({
                    "relation": "IPC_BNS_MAPPING",
                    "section": sec_name,
                    "title": r.get("title") or "",
                    "kind": "act_mapping",
                })

        crime_rows = self.neo4j_service.run_query(
            """
            MATCH (n:LawSection {act: $act, section: $section})<-[:DEFINED_BY]-(crime:Crime)
            RETURN crime.name AS name
            """,
            params,
        )
        for r in crime_rows:
            name = r.get("name") or ""
            if not name:
                continue
            key = ("DEFINED_BY", name)
            if key not in seen:
                seen.add(key)
                connected.append({
                    "relation": "DEFINED_BY",
                    "section": name,
                    "title": name,
                    "kind": "crime",
                })

        return connected

    def get_graph_relationships(self, act: str, section: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns structured graph enrichment for a verified section.
        Retrieves connected constitutional articles, supreme court cases, high court cases,
        legal principles, evidence types, punishments, exceptions, and illustrations.
        First checks label existence to prevent Neo4j warnings.
        """
        # Retrieve existing labels to prevent query warnings
        existing_labels = set()
        try:
            label_rows = self.neo4j_service.run_query("CALL db.labels()", {})
            for r in label_rows:
                existing_labels.add(r.get("label"))
        except Exception as e:
            print(f"[VerificationService] Error fetching labels: {e}")

        params = {"act": act, "section": section}

        related_offences = self.get_connected_nodes(act, section)

        constitutional_articles = []
        if "ConstitutionalArticle" in existing_labels:
            const_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:PROTECTED_BY]->(a:ConstitutionalArticle)
                RETURN a.article AS article, a.title AS title, a.description AS description, a.source AS source, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in const_rows:
                constitutional_articles.append({
                    "article": r.get("article") or "",
                    "title": r.get("title") or "",
                    "description": r.get("description") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        supreme_court_cases = []
        if "SupremeCourtCase" in existing_labels:
            sc_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:INTERPRETED_BY]->(c:SupremeCourtCase)
                RETURN c.case_name AS case_name, c.citation AS citation, c.year AS year, 
                       c.summary AS summary, c.ratio_decidendi AS ratio_decidendi, 
                       c.court AS court, c.source AS source, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in sc_rows:
                supreme_court_cases.append({
                    "case_name": r.get("case_name") or "",
                    "citation": r.get("citation") or "",
                    "year": r.get("year") or 0,
                    "summary": r.get("summary") or "",
                    "ratio_decidendi": r.get("ratio_decidendi") or "",
                    "court": r.get("court") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        high_court_cases = []
        if "HighCourtCase" in existing_labels:
            hc_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:FOLLOWED_BY]->(c:HighCourtCase)
                RETURN c.case_name AS case_name, c.citation AS citation, c.year AS year, 
                       c.summary AS summary, c.court AS court, c.source AS source, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in hc_rows:
                high_court_cases.append({
                    "case_name": r.get("case_name") or "",
                    "citation": r.get("citation") or "",
                    "year": r.get("year") or 0,
                    "summary": r.get("summary") or "",
                    "court": r.get("court") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        legal_principles = []
        if "LegalPrinciple" in existing_labels:
            lp_rows = self.neo4j_service.run_query(
                """
                MATCH (lp:LegalPrinciple)-[r:APPLIES_TO]->(n:LawSection {act: $act, section: $section})
                RETURN lp.name AS name, lp.description AS description, lp.source AS source, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in lp_rows:
                legal_principles.append({
                    "name": r.get("name") or "",
                    "description": r.get("description") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        evidence_types = []
        if "EvidenceType" in existing_labels:
            et_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:SUPPORTED_BY]->(et:EvidenceType)
                RETURN et.name AS name, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in et_rows:
                evidence_types.append({
                    "name": r.get("name") or "",
                    "relation": r.get("relation") or "",
                })

        punishments = []
        if "Punishment" in existing_labels:
            p_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:HAS_PUNISHMENT]->(p:Punishment)
                RETURN p.minimum AS minimum, p.maximum AS maximum, p.fine AS fine, 
                       p.life_imprisonment AS life_imprisonment, p.death_penalty AS death_penalty, type(r) AS relation
                LIMIT 5
                """,
                params,
            )
            for r in p_rows:
                punishments.append({
                    "minimum": r.get("minimum") or "None",
                    "maximum": r.get("maximum") or "None",
                    "fine": r.get("fine") or "Yes",
                    "life_imprisonment": bool(r.get("life_imprisonment")),
                    "death_penalty": bool(r.get("death_penalty")),
                    "relation": r.get("relation") or "",
                })

        exceptions = []
        if "Exception" in existing_labels:
            ex_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:HAS_EXCEPTION]->(e:Exception)
                RETURN e.description AS description, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in ex_rows:
                exceptions.append({
                    "description": r.get("description") or "",
                    "relation": r.get("relation") or "",
                })

        illustrations = []
        if "Illustration" in existing_labels:
            ill_rows = self.neo4j_service.run_query(
                """
                MATCH (n:LawSection {act: $act, section: $section})-[r:HAS_ILLUSTRATION]->(i:Illustration)
                RETURN i.description AS description, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in ill_rows:
                illustrations.append({
                    "description": r.get("description") or "",
                    "relation": r.get("relation") or "",
                })

        # Landmark cases mapping to preserve backwards compatibility / scoring
        landmark_cases = []
        for sc in supreme_court_cases:
            landmark_cases.append({
                "name": sc["case_name"],
                "citation": sc["citation"],
                "relation": sc["relation"]
            })
        for hc in high_court_cases:
            landmark_cases.append({
                "name": hc["case_name"],
                "citation": hc["citation"],
                "relation": hc["relation"]
            })

        # Print graph enrichment summary
        print("\nGraph Enrichment")
        print(f"Related Offences : {len(related_offences)}")
        print(f"Constitution Articles : {len(constitutional_articles)}")
        print(f"Supreme Court Cases : {len(supreme_court_cases)}")
        print(f"Evidence Types : {len(evidence_types)}")
        print(f"Legal Principles : {len(legal_principles)}")

        return {
            "related_offences": related_offences,
            "constitutional_articles": constitutional_articles,
            "supreme_court_cases": supreme_court_cases,
            "high_court_cases": high_court_cases,
            "legal_principles": legal_principles,
            "evidence_types": evidence_types,
            "punishments": punishments,
            "exceptions": exceptions,
            "illustrations": illustrations,
            "landmark_cases": landmark_cases, # Backwards compatibility
        }
