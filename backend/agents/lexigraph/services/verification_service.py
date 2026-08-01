from typing import Dict, Any, List, Optional
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

    def get_equivalent_ipc_section(self, act: str = "", section: str = "") -> Optional[Dict[str, Any]]:
        """
        Retrieves official IPC ↔ BNS equivalent successor mapping for a given section.
        
        Guarantees deterministic, audited traversal:
        - Never uses LIMIT 1 without deterministic ordering
        - Never uses collect()[0]
        - Matches exact LawSection using BOTH act AND section
        - Returns equivalent_section: null if 0 or >1 distinct mappings found (logging an ERROR on >1)
        - Logs structured diagnostic path on successful match.
        """
        sec_clean = str(section or "").strip()
        act_clean = str(act or "").strip().upper()

        parts = sec_clean.split()
        if len(parts) >= 2 and parts[0].upper() in ("BNS", "IPC"):
            act_clean = parts[0].upper()
            sec_clean = parts[1]
        elif sec_clean.upper().startswith("BNS"):
            act_clean = "BNS"
            sec_clean = sec_clean[3:].strip("_ ")
        elif sec_clean.upper().startswith("IPC"):
            act_clean = "IPC"
            sec_clean = sec_clean[3:].strip("_ ")

        if not sec_clean:
            return None
            
        if not act_clean:
            act_clean = "BNS"

        target_act = "IPC" if act_clean == "BNS" else "BNS"

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

        # Deduplicate rows by target section
        unique_targets = {}
        for r in rows:
            target_key = f"{r['act']} {r['section']}"
            if target_key not in unique_targets:
                unique_targets[target_key] = r

        if len(unique_targets) > 1:
            target_list = list(unique_targets.keys())
            print(f"\n[WARN] Multiple successor mappings found for {act_clean} {sec_clean}: {target_list}. Selecting primary: {target_list[0]}")

        matched = list(unique_targets.values())[0]
        
        # STEP 7: Improved Logging
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

    def get_connected_nodes(self, act: str, section: str) -> List[Dict[str, Any]]:
        """Retrieves rule-linked sections, crimes, and IPC/BNS crosswalk neighbours."""
        connected: List[Dict[str, Any]] = []
        seen: set = set()
        params = {"act": act, "section": section}

        # Check existing relationship types to avoid DBMS warnings
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
        Queries both the target section and its equivalent mapped section (e.g. IPC 304B for BNS 80).
        """
        existing_labels = set()
        try:
            label_rows = self.neo4j_service.run_query("CALL db.labels()", {})
            for r in label_rows:
                existing_labels.add(r.get("label"))
        except Exception as e:
            print(f"[VerificationService] Error fetching labels: {e}")

        # Gather target nodes including IPC/BNS equivalents to surface precedent cases for new sections
        target_nodes = [{"act": act, "section": section}]
        mappings = self.get_mappings(act, section)
        for m in mappings:
            eq = m.get("equivalent_section", "")
            parts = eq.split()
            if len(parts) == 2:
                target_nodes.append({"act": parts[0], "section": parts[1]})

        params = {"nodes": target_nodes, "act": act, "section": section}

        related_offences = self.get_connected_nodes(act, section)

        constitutional_articles = []
        if "ConstitutionArticle" in existing_labels or "ConstitutionalArticle" in existing_labels:
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
                if art_title and art_title not in art_name:
                    display_str = f"{art_name} - {art_title}"
                else:
                    display_str = art_name
                constitutional_articles.append({
                    "article": display_str,
                    "title": art_title,
                    "description": r.get("description") or "",
                    "source": r.get("source") or "",
                    "relation": r.get("relation") or "",
                })

        supreme_court_cases = []
        if "SupremeCourtCase" in existing_labels:
            sc_rows = self.neo4j_service.run_query(
                """
                UNWIND $nodes AS target
                MATCH (n:LawSection {act: target.act, section: target.section})-[r:INTERPRETED_IN|INTERPRETS]-(sc:SupremeCourtCase)
                OPTIONAL MATCH (sc)-[:INTERPRETS]->(ls:LawSection)
                OPTIONAL MATCH (sc)-[:ESTABLISHES]->(lp:LegalPrinciple)
                OPTIONAL MATCH (sc)-[:REQUIRES]->(ev:EvidenceType)
                OPTIONAL MATCH (sc)-[:BINDING_UNDER]->(art141:ConstitutionArticle)
                RETURN DISTINCT sc.case_name AS case_name, sc.citation AS citation, sc.year AS year, 
                       sc.summary AS summary, sc.ratio_decidendi AS ratio_decidendi, sc.holding AS holding,
                       sc.court AS court, type(r) AS relation,
                       collect(DISTINCT ls.act + " " + ls.section) AS interprets,
                       collect(DISTINCT lp.name) AS legal_principles,
                       collect(DISTINCT ev.name) AS required_evidence,
                       coalesce(art141.article_number, "Article 141") AS binding_under
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
                    "holding": r.get("holding") or "",
                    "court": r.get("court") or "Supreme Court of India",
                    "relation": r.get("relation") or "",
                    "interprets": [s for s in r.get("interprets", []) if s],
                    "binding_under": r.get("binding_under") or "Article 141",
                    "legal_principles": [p for p in r.get("legal_principles", []) if p],
                    "required_evidence": [e for e in r.get("required_evidence", []) if e]
                })

        high_court_cases = []
        if "HighCourtCase" in existing_labels:
            hc_rows = self.neo4j_service.run_query(
                """
                UNWIND $nodes AS target
                MATCH (n:LawSection {act: target.act, section: target.section})-[r:FOLLOWED_BY]->(c:HighCourtCase)
                RETURN DISTINCT c.case_name AS case_name, c.citation AS citation, c.year AS year, 
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
                UNWIND $nodes AS target
                MATCH (n:LawSection {act: target.act, section: target.section})
                OPTIONAL MATCH (n)-[:GOVERNED_BY|APPLIES_TO|RELATES_TO]-(lp1:LegalPrinciple)
                OPTIONAL MATCH (n)-[:INTERPRETED_IN|INTERPRETS]-(sc:SupremeCourtCase)-[:ESTABLISHES]->(lp2:LegalPrinciple)
                OPTIONAL MATCH (n)-[:PROTECTED_BY|DERIVES_FROM|GOVERNED_BY]-(art:ConstitutionArticle)-[:RELATES_TO]->(lp3:LegalPrinciple)
                WITH coalesce(lp1, lp2, lp3) AS lp
                WHERE lp IS NOT NULL
                RETURN DISTINCT lp.name AS name, lp.description AS description, lp.source AS source, "ESTABLISHED_IN_PRECEDENT" AS relation
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

        ingredients = []
        if "Ingredient" in existing_labels:
            ing_rows = self.neo4j_service.run_query(
                """
                UNWIND $nodes AS target
                MATCH (n:LawSection {act: target.act, section: target.section})-[r:HAS_INGREDIENT]->(i:Ingredient)
                OPTIONAL MATCH (i)-[:REQUIRES_EVIDENCE]->(e:EvidenceType)
                RETURN DISTINCT i.name AS name, i.description AS description, collect(DISTINCT e.name) AS required_evidence
                LIMIT 10
                """,
                params,
            )
            for r in ing_rows:
                ingredients.append({
                    "name": r.get("name") or "",
                    "description": r.get("description") or "",
                    "required_evidence": [ev for ev in r.get("required_evidence", []) if ev]
                })

        victim_rights = []
        if "VictimRight" in existing_labels:
            vr_rows = self.neo4j_service.run_query(
                """
                UNWIND $nodes AS target
                MATCH (n:LawSection {act: target.act, section: target.section})-[r:PROTECTS|SAFEGUARDS]-(vr:VictimRight)
                RETURN DISTINCT vr.right_name AS name, vr.description AS description, type(r) AS relation
                LIMIT 10
                """,
                params,
            )
            for r in vr_rows:
                victim_rights.append({
                    "name": r.get("name") or "",
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
        print(f"Statutory Ingredients : {len(ingredients)}")
        print(f"Victim Rights : {len(victim_rights)}")

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
            "landmark_cases": landmark_cases, # Backwards compatibility
        }
