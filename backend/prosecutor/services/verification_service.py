from typing import Dict, Any, List, Optional
from .neo4j_service import Neo4jService


class VerificationService:
    """
    VerificationService

    Verifies candidate sections against the Neo4j Graph Database.
    Validates Act crosswalk mappings:
      - IPC ↔ BNS (Indian Penal Code ↔ Bharatiya Nyaya Sanhita)
      - CrPC ↔ BNSS (Code of Criminal Procedure ↔ Bharatiya Nagarik Suraksha Sanhita)
      - IEA ↔ BSA (Indian Evidence Act ↔ Bharatiya Sakshya Adhiniyam)
    """

    # Pinecone Index Configurations
    PINECONE_STATUTE_INDEX = "ipc"   # Index for IPC/BNS, CrPC/BNSS, IEA/BSA embeddings
    PINECONE_CASES_INDEX = "cases"   # Index for Case Law embeddings

    # Mapping crosswalk pairs (Old Act <-> New Act)
    ACT_CROSSWALK_MAP = {
        "BNS": "IPC",
        "IPC": "BNS",
        "BNSS": "CRPC",
        "CRPC": "BNSS",
        "BSA": "IEA",
        "IEA": "BSA"
    }

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
        """
        Retrieves replacement links across all crosswalk pairs
        (IPC ↔ BNS, CrPC ↔ BNSS, IEA ↔ BSA).
        """
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

    def get_equivalent_ipc_section(self, act: str = "", section: str = "") -> Optional[Dict[str, Any]]:
        """
        Retrieves official equivalent successor/predecessor mapping for any section across:
          - IPC ↔ BNS
          - CrPC ↔ BNSS
          - IEA ↔ BSA
        """
        sec_clean = str(section or "").strip()
        act_clean = str(act or "").strip().upper()

        # Parse Act and Section dynamically
        parts = sec_clean.split()
        known_acts = ("BNS", "IPC", "BNSS", "CRPC", "BSA", "IEA")
        
        if len(parts) >= 2 and parts[0].upper() in known_acts:
            act_clean = parts[0].upper()
            sec_clean = parts[1]
        else:
            for known_act in known_acts:
                if sec_clean.upper().startswith(known_act):
                    act_clean = known_act
                    sec_clean = sec_clean[len(known_act):].strip("_ ")
                    break

        if not sec_clean:
            return None
            
        if not act_clean:
            act_clean = "BNS"

        # Determine target act using crosswalk mapping dictionary.
        # If the act isn't in the map it has no known counterpart — return None
        # rather than guessing "IPC", which would produce spurious crosswalk hits.
        target_act = self.ACT_CROSSWALK_MAP.get(act_clean)
        if not target_act:
            return None

        query = """
            MATCH (b:LawSection {act: $act, section: $section})
            MATCH (b)-[r:REPLACES|REPLACED_BY]-(target:LawSection)
            WHERE target.act <> $act AND target.act = $target_act
            RETURN target.act AS act, target.section AS section, target.title AS title, type(r) AS rel
            ORDER BY target.act, target.section, type(r)
        """

        try:
            rows = self.neo4j_service.run_query(query, {"act": act_clean, "section": sec_clean, "target_act": target_act})
        except Exception as e:
            print(f"[VerificationService] Error querying equivalent section for {act_clean} {sec_clean}: {e}")
            return None

        if not rows:
            return None

        unique_targets = {}
        for r in rows:
            target_key = f"{r['act']} {r['section']}"
            if target_key not in unique_targets:
                unique_targets[target_key] = r

        if len(unique_targets) > 1:
            target_list = list(unique_targets.keys())
            print(f"\n[WARN] Multiple successor mappings found for {act_clean} {sec_clean}: {target_list}. Selecting primary: {target_list[0]}")

        matched = list(unique_targets.values())[0]
        
        print("\n" + "=" * 50)
        print(f"Requested:\n{act_clean} {sec_clean}")
        print("  |")
        print(f"Matched Node:\nLawSection({act_clean} {sec_clean})")
        print("  |")
        print(f"Relationship:\n{matched.get('rel', 'REPLACES')}")
        print("  |")
        print(f"Returned:\n{matched['act']} {matched['section']}")
        print("=" * 50 + "\n")

        return {
            "act": matched["act"],
            "section": matched["section"],
            "mapping_verified": True
        }

    def batch_check_ingredients(self, sections: List[Dict[str, str]]) -> Dict[str, bool]:
        """
        Single-round-trip check: for each (act, section) pair, returns True if
        the Neo4j graph has at least one Crime node or HAS_INGREDIENT edge —
        i.e. the section has statutory ingredient data and can be validated.

        Use this BEFORE the per-candidate get_node_info loop so sections with
        no ingredient data are eliminated before they cause individual Neo4j
        calls.  Sections without ingredient data are still legitimate law, but
        the IngredientValidatorService cannot validate them and they will always
        be rejected at Step 4 — so we skip the Neo4j enrichment cost entirely.

        Returns a dict keyed by "ACT SECTION" → bool (True = has ingredients).
        """
        if not sections:
            return {}

        query = """
            UNWIND $sections AS s
            OPTIONAL MATCH (c:Crime)-[:DEFINED_BY]->(n:LawSection {act: s.act, section: s.section})
            WITH s, count(c) AS crime_count
            RETURN s.act AS act, s.section AS section, crime_count > 0 AS has_ingredients
        """
        try:
            rows = self.neo4j_service.run_query(query, {"sections": sections})
        except Exception as e:
            print(f"[VerificationService] batch_check_ingredients error: {e}")
            # On error, assume all sections may have ingredients (safe fallback —
            # per-section validation will still reject them if they don't).
            return {f"{s['act']} {s['section']}": True for s in sections}

        result: Dict[str, bool] = {}
        for row in rows:
            key = f"{row['act']} {row['section']}"
            result[key] = bool(row.get("has_ingredients"))

        # Fill any keys that came back missing from the query (shouldn't happen,
        # but guard against partial result sets from a LIMIT or timeout).
        for s in sections:
            key = f"{s['act']} {s['section']}"
            if key not in result:
                result[key] = False

        return result

    def batch_get_nodes(self, sections: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
        """
        Single-round-trip fetch of node properties for multiple sections.
        Replaces the per-candidate get_node_info() loop in Step 3 of LexiGraphAgent.

        Returns a dict keyed by "ACT SECTION" → node property dict (same shape
        as get_node_info(), empty dict if the node doesn't exist in the graph).
        """
        if not sections:
            return {}

        query = """
            UNWIND $sections AS s
            MATCH (n:LawSection {act: s.act, section: s.section})
            RETURN n.act AS act, n.section AS section, n.title AS title,
                   n.description AS description, n.punishment AS punishment,
                   n.chapter AS chapter, n.category AS category,
                   n.keywords AS keywords
        """
        try:
            rows = self.neo4j_service.run_query(query, {"sections": sections})
        except Exception as e:
            print(f"[VerificationService] batch_get_nodes error: {e}")
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = f"{row['act']} {row['section']}"
            result[key] = dict(row)
        return result

    def get_connected_nodes(self, act: str, section: str) -> List[Dict[str, Any]]:
        """Retrieves rule-linked sections, crimes, and act crosswalk neighbours (IPC/BNS, CrPC/BNSS, IEA/BSA)."""
        connected: List[Dict[str, Any]] = []
        seen: set = set()
        params = {"act": act, "section": section}

        existing_rel_types = set()
        try:
            rel_rows = self.neo4j_service.run_query("CALL db.relationshipTypes()", {})
            for r in rel_rows:
                existing_rel_types.add(r.get("relationshipType"))
        except Exception:
            pass

        target_rules = [r for r in ["MORE_SPECIFIC_THAN", "OVERRIDES", "ENHANCES"] if r in existing_rel_types]
        if target_rules:
            rel_pattern = "|".join(target_rules)
            rule_query = f"""
                MATCH (n:LawSection {{act: $act, section: $section}})-[rule:{rel_pattern}]-(other:LawSection)
                RETURN type(rule) AS relation, other.act AS act, other.section AS section, other.title AS title
            """
            rule_rows = self.neo4j_service.run_query(rule_query, params)
        else:
            rule_rows = []

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
                    "relation": "ACT_CROSSWALK_MAPPING",
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
        Returns robust graph enrichment for a verified section.
        Extracts details using schema-aligned relations for IPC, BNS, CrPC, BNSS, IEA, and BSA.
        """
        target_nodes = [{"act": act, "section": section}]
        mappings = self.get_mappings(act, section)
        for m in mappings:
            eq = m.get("equivalent_section", "")
            parts = eq.split()
            if len(parts) == 2:
                target_nodes.append({"act": parts[0], "section": parts[1]})

        params = {"nodes": target_nodes, "act": act, "section": section}
        related_offences = self.get_connected_nodes(act, section)

        # 1. Statutory Ingredients (Derived from connected Crime definitions and Keywords)
        ingredients = []
        ing_rows = self.neo4j_service.run_query(
            """
            UNWIND $nodes AS target
            MATCH (c:Crime)-[:DEFINED_BY]->(n:LawSection {act: target.act, section: target.section})
            OPTIONAL MATCH (n)-[:HAS_KEYWORD]->(k:Keyword)
            RETURN DISTINCT c.name AS name,
                   n.description AS description,
                   collect(DISTINCT k.name) AS required_evidence
            LIMIT 15
            """,
            params,
        )
        for r in ing_rows:
            if r.get("name"):
                ingredients.append({
                    "name": r.get("name"),
                    "description": r.get("description") or "",
                    "required_evidence": [ev for ev in r.get("required_evidence", []) if ev]
                })

        # 2. Direct Evidence / Keywords (Relevant for IPC/BNS and IEA/BSA)
        evidence_types = []
        et_rows = self.neo4j_service.run_query(
            """
            UNWIND $nodes AS target
            MATCH (n:LawSection {act: target.act, section: target.section})-[:HAS_KEYWORD]->(k:Keyword)
            RETURN DISTINCT k.name AS name, "HAS_KEYWORD" AS relation
            LIMIT 15
            """,
            params,
        )
        for r in et_rows:
            if r.get("name"):
                evidence_types.append({
                    "name": r.get("name"),
                    "relation": r.get("relation") or "HAS_KEYWORD",
                })

        # 3. Legal Principles / Rules (if LegalRule nodes exist)
        legal_principles = []
        lp_rows = self.neo4j_service.run_query(
            """
            UNWIND $nodes AS target
            MATCH (n:LawSection {act: target.act, section: target.section})
            OPTIONAL MATCH (r:LegalRule)-[:APPLIES_FROM|APPLIES_TO]-(n)
            RETURN DISTINCT r.id AS name,
                   coalesce(r.condition, "") AS description,
                   "LEGAL_RULE" AS source,
                   coalesce(r.relationship, "APPLIES") AS relation
            LIMIT 15
            """,
            params,
        )
        for r in lp_rows:
            if r.get("name"):
                legal_principles.append({
                    "name": r.get("name"),
                    "description": r.get("description") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        # 4. Precedent Cases – corrected query (removed non-existent 'facts_summary')
        supreme_court_cases = []
        high_court_cases = []
        case_rows = self.neo4j_service.run_query(
            """
            UNWIND $nodes AS target
            MATCH (n:LawSection {act: target.act, section: target.section})<-[r:APPLIES_SECTION|CITES|INTERPRETS]-(c)
            WHERE c:Case OR c:SupremeCourtCase OR c:HighCourtCase
            OPTIONAL MATCH (c)-[:APPLIES_TO|RELATES_TO]-(lp)
            RETURN DISTINCT coalesce(c.case_name, c.title, c.name) AS case_name,
                   coalesce(c.citation, "") AS citation,
                   coalesce(c.year, 0) AS year,
                   coalesce(c.facts, c.summary, "") AS facts,
                   coalesce(c.ratio_decidendi, c.holding, c.summary, "") AS ratio_decidendi,
                   coalesce(c.court, "Supreme Court of India") AS court,
                   type(r) AS relation,
                   collect(DISTINCT coalesce(lp.name, lp.title)) AS legal_principles
            LIMIT 25
            """,
            params,
        )
        for r in case_rows:
            court = (r.get("court") or "").strip()
            if not r.get("case_name"):
                continue
            entry = {
                "case_name": r.get("case_name"),
                "citation": r.get("citation") or "",
                "year": r.get("year") or 0,
                "facts": r.get("facts") or "",
                "ratio_decidendi": r.get("ratio_decidendi") or "",
                "court": court or "Supreme Court of India",
                "relation": r.get("relation") or "",
                "legal_principles": [p for p in r.get("legal_principles", []) if p],
            }
            if court and "high" in court.lower():
                high_court_cases.append(entry)
            else:
                supreme_court_cases.append(entry)

        # 5. Constitutional Articles
        constitutional_articles = []
        const_rows = self.neo4j_service.run_query(
            """
            UNWIND $nodes AS target
            MATCH (n:LawSection {act: target.act, section: target.section})-[r:PROTECTED_BY|DERIVES_FROM|UPHOLDS|PROHIBITED_BY|GOVERNED_BY]-(a)
            WHERE a:ConstitutionArticle OR a:ConstitutionalArticle
            RETURN DISTINCT coalesce(a.article_number, a.article) AS article, a.title AS title,
                   coalesce(a.summary, a.description) AS description, a.source AS source, type(r) AS relation
            LIMIT 10
            """,
            params,
        )
        for r in const_rows:
            art_name = r.get("article") or ""
            art_title = r.get("title") or ""
            display_str = f"{art_name} - {art_title}" if art_title and art_title not in art_name else art_name
            if display_str:
                constitutional_articles.append({
                    "article": display_str,
                    "title": art_title,
                    "description": r.get("description") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        # 6. Punishments, Exceptions, Illustrations, Victim Rights
        punishments, exceptions, illustrations, victim_rights = [], [], [], []

        p_rows = self.neo4j_service.run_query(
            "MATCH (n:LawSection {act: $act, section: $section})-[r:HAS_PUNISHMENT]-(p:Punishment) RETURN p", params
        )
        for r in p_rows:
            p = r.get("p", {})
            punishments.append({
                "minimum": p.get("minimum", "None"), "maximum": p.get("maximum", "None"),
                "fine": p.get("fine", "Yes"), "life_imprisonment": bool(p.get("life_imprisonment")),
                "death_penalty": bool(p.get("death_penalty"))
            })

        ex_rows = self.neo4j_service.run_query(
            "MATCH (n:LawSection {act: $act, section: $section})-[r:HAS_EXCEPTION]-(e) RETURN e.description AS description", params
        )
        for r in ex_rows:
            if r.get("description"):
                exceptions.append({"description": r.get("description")})

        ill_rows = self.neo4j_service.run_query(
            "MATCH (n:LawSection {act: $act, section: $section})-[r:HAS_ILLUSTRATION]-(i) RETURN i.description AS description", params
        )
        for r in ill_rows:
            if r.get("description"):
                illustrations.append({"description": r.get("description")})

        vr_rows = self.neo4j_service.run_query(
            """
            UNWIND $nodes AS target
            MATCH (n:LawSection {act: target.act, section: target.section})-[:HAS_KEYWORD]->(k:Keyword)
            RETURN k.name AS name, n.title AS description
            """,
            params
        )
        for r in vr_rows:
            if r.get("name"):
                victim_rights.append({"name": r.get("name"), "description": r.get("description") or ""})

        landmark_cases = [
            {"name": sc["case_name"], "citation": sc["citation"], "relation": sc["relation"]}
            for sc in (supreme_court_cases + high_court_cases)
        ]

        print("\nGraph Enrichment")
        print(f"Related Offences / Sections : {len(related_offences)}")
        print(f"Constitution Articles     : {len(constitutional_articles)}")
        print(f"Supreme Court Cases       : {len(supreme_court_cases)}")
        print(f"Evidence Types            : {len(evidence_types)}")
        print(f"Legal Principles          : {len(legal_principles)}")
        print(f"Statutory Ingredients     : {len(ingredients)}")
        print(f"Victim Rights             : {len(victim_rights)}")

        return {
            "related_offences": related_offences,
            "constitutional_articles": constitutional_articles,
            "supreme_court_cases": supreme_court_cases,
            "high_court_cases": high_court_cases,
            "legal_principles": legal_principles,
            "evidence_types": evidence_types,
            "ingredients": ingredients,
            "victim_rights": victim_rights,
            "punishments": punishments,
            "exceptions": exceptions,
            "illustrations": illustrations,
            "landmark_cases": landmark_cases,
            "pinecone_indexes": {
                "statutes": self.PINECONE_STATUTE_INDEX,
                "cases": self.PINECONE_CASES_INDEX
            }
        }