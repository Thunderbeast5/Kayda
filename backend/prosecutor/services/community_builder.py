import os
import sys
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))

from agents.config.llm_config import get_llm

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# ---------------------------------------------------------------------------
# COMMUNITY DEFINITIONS
# Expanded for anticipatory bail scope:
#   - Added  "anticipatory_bail"  community (BNSS 482, CrPC 438, related
#     procedural relief provisions)
#   - Added  "bail_and_bonds"     community (general bail, surety, bonds)
#   - Added  "dowry_offences"     community (distinct from generic women
#     offences so dowry-specific sections rank correctly)
#   - Added  "sexual_offences"    community (POCSO, rape, trafficking —
#     separated from the broader women_offences bucket)
#   - Kept all original communities; updated descriptions to BNS language
# ---------------------------------------------------------------------------
COMMUNITY_DEFS = {
    "anticipatory_bail": {
        "name": "Anticipatory Bail",
        "description": (
            "Provisions governing pre-arrest bail, personal liberty, and "
            "custodial rights under BNSS 482/483 and CrPC 438/439. Includes "
            "conditions for grant or rejection of anticipatory bail, "
            "prosecutorial opposition, court discretion, and related "
            "procedural safeguards under Article 21."
        ),
        "keywords": [
            "anticipatory bail", "pre-arrest bail", "bail", "bnss 482",
            "crpc 438", "personal liberty", "article 21", "custodial",
            "pre-arrest", "apprehension of arrest", "anticipatory",
        ],
        "category": "Procedure",
    },
    "bail_and_bonds": {
        "name": "Bail and Bonds",
        "description": (
            "General bail provisions, bailable offences, surety, bonds, "
            "and release conditions under BNSS/CrPC."
        ),
        "keywords": [
            "bail", "surety", "bond", "bailable", "non-bailable",
            "release", "custody", "remand",
        ],
        "category": "Procedure",
    },
    "women_offences": {
        "name": "Women Offences",
        "description": (
            "Offences relating to cruelty by husband or relatives, "
            "domestic violence, harassment, and offences against the "
            "dignity of women (BNS 85/86, formerly IPC 498A)."
        ),
        "keywords": [
            "cruelty", "harassment", "married women", "husband",
            "wife", "domestic violence", "women", "modesty",
        ],
        "category": "Offences against Human Body",
    },
    "dowry_offences": {
        "name": "Dowry Offences",
        "description": (
            "Offences relating to dowry demand, dowry death, and "
            "prohibition of dowry under BNS 80/84/85 and the "
            "Dowry Prohibition Act."
        ),
        "keywords": [
            "dowry", "dowry death", "dowry demand", "dowry prohibition",
            "dpa", "stridhan",
        ],
        "category": "Offences against Human Body",
    },
    "sexual_offences": {
        "name": "Sexual Offences",
        "description": (
            "Offences relating to rape, sexual assault, trafficking, "
            "POCSO, and outraging the modesty of women "
            "(BNS 63-73, POCSO)."
        ),
        "keywords": [
            "rape", "sexual assault", "pocso", "trafficking",
            "modesty", "outraging", "sexual", "molestation",
        ],
        "category": "Offences against Human Body",
    },
    "children_offences": {
        "name": "Children Offences",
        "description": (
            "Offences relating to kidnapping, abduction, and assault "
            "of minors or children."
        ),
        "keywords": ["child", "minor", "children", "kidnapping", "infant"],
        "category": "Offences against Human Body",
    },
    "property_offences": {
        "name": "Property Offences",
        "description": (
            "Offences relating to theft, robbery, burglary, mischief, "
            "extortion, and trespass."
        ),
        "keywords": [
            "theft", "robbery", "burglary", "extortion",
            "trespass", "mischief",
        ],
        "category": "Offences against Property",
    },
    "cyber_crime": {
        "name": "Cyber Crime",
        "description": (
            "Offences committed using computer systems, networks, "
            "and electronic devices."
        ),
        "keywords": [
            "cyber", "computer", "hacking", "electronic",
            "internet", "information technology",
        ],
        "category": "Cyber Crime",
    },
    "financial_crime": {
        "name": "Financial Crime",
        "description": (
            "Offences relating to forgery, counterfeiting, cheating, "
            "tax fraud, and currency manipulation."
        ),
        "keywords": [
            "forgery", "counterfeit", "cheating", "fraud",
            "coin", "currency",
        ],
        "category": "Financial Crime",
    },
    "human_body_offences": {
        "name": "Offences Against Human Body",
        "description": (
            "Offences relating to homicide, murder, hurt, wrongful "
            "restraint, and causing death by negligence."
        ),
        "keywords": [
            "murder", "homicide", "negligence", "hurt",
            "assault", "kidnap", "injury", "death",
        ],
        "category": "Offences against Human Body",
    },
    "evidence_law": {
        "name": "Evidence Law",
        "description": (
            "Provisions governing the relevancy, proof, and admissibility "
            "of facts and witness statements under BSA/IEA."
        ),
        "keywords": [
            "evidence", "witness", "confession", "dying declaration",
            "admissibility", "presumption",
        ],
        "category": "Evidence",
    },
    "criminal_procedure": {
        "name": "Criminal Procedure",
        "description": (
            "Provisions governing police processes, arrests, summonses, "
            "justice administration, and public order under BNSS/CrPC."
        ),
        "keywords": [
            "court", "judge", "police", "arrest", "summons",
            "procedure", "justice", "fir", "charge",
        ],
        "category": "Procedure",
    },
    "constitutional_rights": {
        "name": "Constitutional Rights",
        "description": (
            "Fundamental constitutional protections, personal liberty, "
            "equality, and state directives."
        ),
        "keywords": [
            "constitution", "fundamental rights", "article",
            "liberty", "equality",
        ],
        "category": "Constitutional",
    },
    "general_offences": {
        "name": "General Offences",
        "description": (
            "General provisions, fallbacks, miscellaneous public order "
            "offences, and exceptions."
        ),
        "keywords": ["general", "provisions", "offences", "fallback", "public order"],
        "category": "General",
    },
}


# ---------------------------------------------------------------------------
# CLASSIFIER
# Priority order matters — more specific communities are checked first.
# Anticipatory bail and dowry are now checked before the generic buckets
# they used to fall into (criminal_procedure and women_offences).
# ---------------------------------------------------------------------------
def classify_section(act: str, section: str, title: str, description: str, category: str) -> str:
    act_upper  = act.upper()
    title_l    = title.lower()
    desc_l     = description.lower()
    cat_l      = (category or "").lower()
    section_l  = section.lower()

    # 1. Constitutional Rights
    if act_upper == "COI" or "constitution" in title_l or "fundamental right" in desc_l:
        return "constitutional_rights"

    # 2. Evidence Law  (BSA is the BNS-era replacement for IEA)
    if act_upper in ("IEA", "BSA") or "evidence" in desc_l or "admissib" in desc_l:
        return "evidence_law"

    # 3. Anticipatory Bail  — check BEFORE generic criminal_procedure
    #    BNSS 482 = anticipatory bail; BNSS 483 = direction for grant; CrPC 438/439
    _bail_sections = {"482", "483", "438", "439"}
    if (
        any(kw in title_l or kw in desc_l for kw in
            ["anticipatory bail", "pre-arrest bail", "apprehension of arrest",
             "direction for bail"])
        or (act_upper in ("BNSS", "CRPC") and section in _bail_sections)
    ):
        return "anticipatory_bail"

    # 4. General bail / bonds — check BEFORE generic criminal_procedure
    if any(kw in title_l or kw in desc_l for kw in
           ["bail in bailable", "bail in non-bailable", "surety", "bail bond",
            "release on bail"]):
        return "bail_and_bonds"

    # 5. Dowry Offences  — more specific than women_offences
    if (
        act_upper == "DPA"
        or any(kw in title_l or kw in desc_l for kw in
               ["dowry death", "dowry demand", "dowry prohibition", "stridhan",
                "dowry"])
    ):
        return "dowry_offences"

    # 6. Sexual Offences  — more specific than women_offences
    if any(kw in title_l or kw in desc_l for kw in
           ["rape", "sexual assault", "pocso", "trafficking", "outraging",
            "modesty", "molestation"]):
        return "sexual_offences"

    # 7. Women Offences  (cruelty, domestic violence, harassment — NOT dowry/sexual)
    if any(kw in title_l or kw in desc_l for kw in
           ["cruelty by husband", "cruelty by relative", "domestic violence",
            "harassment", "married women", "husband or relative"]) or "women" in cat_l:
        return "women_offences"

    # 8. Children Offences
    if any(kw in title_l or kw in desc_l for kw in
           ["child", "minor", "kidnapping a minor", "kidnaps minor", "infant"]) \
       or "children" in cat_l:
        return "children_offences"

    # 9. Cyber Crime
    if any(kw in title_l or kw in desc_l for kw in
           ["cyber", "computer", "hacking", "electronic record",
            "information technology"]):
        return "cyber_crime"

    # 10. Financial Crime
    if any(kw in title_l or kw in desc_l for kw in
           ["forgery", "counterfeit", "cheating", "fraud", "coin", "currency",
            "financial"]):
        return "financial_crime"

    # 11. Property Offences
    if "property" in cat_l or any(kw in title_l or kw in desc_l for kw in
                                   ["theft", "robbery", "burglary", "extortion",
                                    "trespass", "mischief"]):
        return "property_offences"

    # 12. Offences Against Human Body
    if "human body" in cat_l or any(kw in title_l or kw in desc_l for kw in
                                     ["murder", "homicide", "negligence", "hurt",
                                      "assault", "kidnap", "injury", "death"]):
        return "human_body_offences"

    # 13. Criminal Procedure  (everything procedural that isn't bail)
    if "justice" in cat_l or "order" in cat_l or \
       any(kw in title_l or kw in desc_l for kw in
           ["court", "judge", "police", "arrest", "summons", "public servant",
            "fir", "charge sheet", "cognizance"]):
        return "criminal_procedure"

    if "general" in cat_l:
        return "general_offences"

    return "general_offences"


# ---------------------------------------------------------------------------
# BUILD
# ---------------------------------------------------------------------------
def build_communities():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[community_builder] Error: Missing Neo4j credentials.")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:

        # ── Constraint ──────────────────────────────────────────────────────
        print("[community_builder] Creating Community unique constraint...")
        session.run(
            "CREATE CONSTRAINT community_unique IF NOT EXISTS "
            "FOR (c:Community) REQUIRE c.community_id IS UNIQUE"
        )

        # ── Upsert Community nodes ───────────────────────────────────────────
        print("[community_builder] Ingesting Community nodes...")
        for cid, details in COMMUNITY_DEFS.items():
            session.run(
                """
                MERGE (c:Community {community_id: $community_id})
                SET c.name        = $name,
                    c.description = $description,
                    c.keywords    = $keywords,
                    c.category    = $category,
                    c.created_at  = $created_at
                """,
                community_id=cid,
                name=details["name"],
                description=details["description"],
                keywords=details["keywords"],
                category=details["category"],
                created_at=datetime.utcnow().isoformat(),
            )

        # ── Classify primary acts: BNS, IEA, BSA, BNSS, COI ────────────────
        # BNSS and BSA were previously missing from this pass.
        PRIMARY_ACTS = ["BNS", "BNSS", "BSA", "COI"]  # ground truths only; IEA/IPC/CrPC inherit below
        print(f"[community_builder] Classifying {PRIMARY_ACTS} sections...")
        res = session.run(
            """
            MATCH (n:LawSection)
            WHERE n.act IN $acts
            RETURN elementId(n) AS node_id,
                   n.act        AS act,
                   n.section    AS section,
                   n.title      AS title,
                   n.description AS description,
                   n.category   AS category
            """,
            acts=PRIMARY_ACTS,
        )

        primary_assignments = {}
        rows = list(res)
        print(f"[community_builder] Found {len(rows)} primary-act sections.")
        for r in rows:
            assigned = classify_section(
                r["act"], r["section"],
                r["title"] or "", r["description"] or "", r["category"] or "",
            )
            primary_assignments[f"{r['act']}_{r['section']}"] = assigned
            session.run(
                """
                MATCH (n) WHERE elementId(n) = $node_id
                MATCH (c:Community {community_id: $community_id})
                MERGE (n)-[:BELONGS_TO]->(c)
                """,
                node_id=r["node_id"],
                community_id=assigned,
            )

        print(f"[community_builder] Classified {len(primary_assignments)} primary sections.")

        # ── Classify IPC (inherit from BNS successor where possible) ────────
        print("[community_builder] Classifying IPC sections...")
        res_ipc = session.run(
            """
            MATCH (n:LawSection {act: 'IPC'})
            RETURN elementId(n) AS node_id,
                   n.section    AS section,
                   n.title      AS title,
                   n.description AS description
            """
        )

        ipc_count = 0
        for r in res_ipc:
            map_res = session.run(
                """
                MATCH (n:LawSection {act: 'IPC', section: $section})
                      -[r:REPLACED_BY|REPLACES]-
                      (other:LawSection {act: 'BNS'})
                RETURN other.section AS bns_section
                LIMIT 1
                """,
                section=r["section"],
            )
            bns_sec = None
            for row in map_res:
                bns_sec = row["bns_section"]

            if bns_sec and f"BNS_{bns_sec}" in primary_assignments:
                assigned = primary_assignments[f"BNS_{bns_sec}"]
            else:
                assigned = classify_section(
                    "IPC", r["section"],
                    r["title"] or "", r["description"] or "", "",
                )

            session.run(
                """
                MATCH (n) WHERE elementId(n) = $node_id
                MATCH (c:Community {community_id: $community_id})
                MERGE (n)-[:BELONGS_TO]->(c)
                """,
                node_id=r["node_id"],
                community_id=assigned,
            )
            ipc_count += 1

        print(f"[community_builder] Classified {ipc_count} IPC sections.")

        # ── Classify CRPC (inherit from BNSS successor where possible) ──────
        print("[community_builder] Classifying CrPC sections...")
        res_crpc = session.run(
            """
            MATCH (n:LawSection {act: 'CRPC'})
            RETURN elementId(n) AS node_id,
                   n.section    AS section,
                   n.title      AS title,
                   n.description AS description
            """
        )

        crpc_count = 0
        for r in res_crpc:
            map_res = session.run(
                """
                MATCH (n:LawSection {act: 'CRPC', section: $section})
                      -[r:REPLACED_BY|REPLACES]-
                      (other:LawSection {act: 'BNSS'})
                RETURN other.section AS bnss_section
                LIMIT 1
                """,
                section=r["section"],
            )
            bnss_sec = None
            for row in map_res:
                bnss_sec = row["bnss_section"]

            if bnss_sec and f"BNSS_{bnss_sec}" in primary_assignments:
                assigned = primary_assignments[f"BNSS_{bnss_sec}"]
            else:
                assigned = classify_section(
                    "CRPC", r["section"],
                    r["title"] or "", r["description"] or "", "",
                )

            session.run(
                """
                MATCH (n) WHERE elementId(n) = $node_id
                MATCH (c:Community {community_id: $community_id})
                MERGE (n)-[:BELONGS_TO]->(c)
                """,
                node_id=r["node_id"],
                community_id=assigned,
            )
            crpc_count += 1

        print(f"[community_builder] Classified {crpc_count} CrPC sections.")

        # ── Classify IEA (inherit from BSA successor where possible) ─────────
        print("[community_builder] Classifying IEA sections...")
        res_iea = session.run(
            """
            MATCH (n:LawSection {act: 'IEA'})
            RETURN elementId(n) AS node_id,
                   n.section    AS section,
                   n.title      AS title,
                   n.description AS description
            """
        )

        iea_count = 0
        for r in res_iea:
            map_res = session.run(
                """
                MATCH (n:LawSection {act: 'IEA', section: $section})
                      -[r:REPLACED_BY|REPLACES]-
                      (other:LawSection {act: 'BSA'})
                RETURN other.section AS bsa_section
                LIMIT 1
                """,
                section=r["section"],
            )
            bsa_sec = None
            for row in map_res:
                bsa_sec = row["bsa_section"]

            if bsa_sec and f"BSA_{bsa_sec}" in primary_assignments:
                assigned = primary_assignments[f"BSA_{bsa_sec}"]
            else:
                assigned = classify_section(
                    "IEA", r["section"],
                    r["title"] or "", r["description"] or "", "",
                )

            session.run(
                """
                MATCH (n) WHERE elementId(n) = $node_id
                MATCH (c:Community {community_id: $community_id})
                MERGE (n)-[:BELONGS_TO]->(c)
                """,
                node_id=r["node_id"],
                community_id=assigned,
            )
            iea_count += 1

        print(f"[community_builder] Classified {iea_count} IEA sections.")

        # ── Update node/edge counts ──────────────────────────────────────────
        print("[community_builder] Updating community metadata counts...")
        for cid in COMMUNITY_DEFS.keys():
            node_count = session.run(
                """
                MATCH (:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                RETURN count(*) AS c
                """,
                cid=cid,
            ).single()["c"]

            edge_count = session.run(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                MATCH (n)-[r]-()
                RETURN count(DISTINCT r) AS c
                """,
                cid=cid,
            ).single()["c"]

            session.run(
                """
                MATCH (c:Community {community_id: $cid})
                SET c.node_count = $node_count, c.edge_count = $edge_count
                """,
                cid=cid,
                node_count=node_count,
                edge_count=edge_count,
            )
            print(f"  {cid}: {node_count} sections, {edge_count} edges")

        # ── LLM Summaries ────────────────────────────────────────────────────
        print("[community_builder] Generating Community Summaries using LLM...")
        llm = get_llm(temperature=0.2)

        for cid, details in COMMUNITY_DEFS.items():
            print(f"  Summarizing community: {details['name']}...")

            sec_rows = session.run(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                RETURN n.act AS act, n.section AS section,
                       n.title AS title, n.description AS description
                LIMIT 15
                """,
                cid=cid,
            )
            sections_list = [
                f"{r['act']} {r['section']} - {r['title']}: {r['description']}"
                for r in sec_rows
            ]

            const_rows = session.run(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                MATCH (n)-[:PROTECTED_BY]->(a:ConstitutionalArticle)
                RETURN DISTINCT a.article AS article, a.title AS title
                """,
                cid=cid,
            )
            articles = [f"{r['article']} ({r['title']})" for r in const_rows]

            ev_rows = session.run(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                MATCH (n)-[:SUPPORTED_BY]->(et:EvidenceType)
                RETURN DISTINCT et.name AS name
                """,
                cid=cid,
            )
            evidence = [r["name"] for r in ev_rows]

            lp_rows = session.run(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                MATCH (lp:LegalPrinciple)-[:APPLIES_TO]->(n)
                RETURN DISTINCT lp.name AS name
                """,
                cid=cid,
            )
            principles = [r["name"] for r in lp_rows]

            sc_rows = session.run(
                """
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $cid})
                MATCH (n)<-[:APPLIES_SECTION]-(sc:Case)
                RETURN DISTINCT sc.case_name AS name
                """,
                cid=cid,
            )
            cases = [r["name"] for r in sc_rows]

            prompt = f"""You are an expert legal annotator summarizing legal knowledge graph communities for Kayda AI.

Write a summary for the community: "{details['name']}".
Description: {details['description']}

Here are some example law sections in this community:
{chr(10).join(sections_list) if sections_list else "None found"}

Connected graph elements:
Relevant Constitutional Articles: {", ".join(articles) if articles else "None"}
Relevant Evidence Types: {", ".join(evidence) if evidence else "None"}
Relevant Legal Principles: {", ".join(principles) if principles else "None"}
Relevant Supreme Court Cases: {", ".join(cases) if cases else "None"}

Please produce the summary in this exact format:
This community contains offences relating to <list of core criminal topics>.

Important Sections: <comma-separated list of section numbers>
Relevant Constitution: <comma-separated list of constitutional articles>
Relevant Evidence: <comma-separated list of evidence types>
Relevant Legal Principles: <comma-separated list of principles>
Relevant Supreme Court Cases: <comma-separated list of SC case names>
"""
            try:
                response = llm.invoke(prompt)
                summary_text = response.content.strip()
                session.run(
                    "MATCH (c:Community {community_id: $cid}) SET c.summary = $summary",
                    cid=cid,
                    summary=summary_text,
                )
            except Exception as e:
                print(f"    Error generating summary for {details['name']}: {e}")

        print("[community_builder] Done. All communities built and summaries stored.")

    driver.close()


if __name__ == "__main__":
    build_communities()