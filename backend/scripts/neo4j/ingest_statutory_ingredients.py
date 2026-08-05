import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / "backend" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


# ── STATUTORY INGREDIENTS MAPPING DATA ──────────────────────────────────────────
STATUTORY_DATA = [
    {
        "sections": [
            {"act": "BNS", "section": "80"},
            {"act": "IPC", "section": "304B"}
        ],
        "title": "Dowry Death",
        "ingredients": [
            {"name": "Woman Victim", "description": "The deceased must be a female who died an unnatural death."},
            {"name": "Unnatural Death", "description": "Death caused by burns, bodily injury, or under abnormal circumstances."},
            {"name": "Within Seven Years of Marriage", "description": "Death occurred within seven years of the marriage."},
            {"name": "Dowry Demand", "description": "Demand for property or valuable security in connection with marriage."},
            {"name": "Cruelty or Harassment Soon Before Death", "description": "Deceased subjected to cruelty or harassment by husband or relatives soon before death."}
        ],
        "punishment": {"term": "Rigorous imprisonment for not less than 7 years, extending to life imprisonment.", "bailable": False, "cognizable": True},
        "exceptions": [
            {"title": "Accidental Death without Dowry Demand", "description": "Natural or purely accidental death unrelated to dowry coercion."}
        ],
        "evidence_links": [
            {"ingredient": "Woman Victim", "evidence": "Birth Certificate"},
            {"ingredient": "Unnatural Death", "evidence": "Postmortem Report"},
            {"ingredient": "Unnatural Death", "evidence": "Medical Report"},
            {"ingredient": "Unnatural Death", "evidence": "Inquest Report"},
            {"ingredient": "Within Seven Years of Marriage", "evidence": "Marriage Certificate"},
            {"ingredient": "Dowry Demand", "evidence": "Witness Statement"},
            {"ingredient": "Dowry Demand", "evidence": "Bank Transaction"},
            {"ingredient": "Dowry Demand", "evidence": "WhatsApp Chats"},
            {"ingredient": "Dowry Demand", "evidence": "Audio Recording"},
            {"ingredient": "Cruelty or Harassment Soon Before Death", "evidence": "Dying Declaration"},
            {"ingredient": "Cruelty or Harassment Soon Before Death", "evidence": "Witness Statement"},
            {"ingredient": "Cruelty or Harassment Soon Before Death", "evidence": "Call Detail Records (CDR)"}
        ]
    },
    {
        "sections": [
            {"act": "BNS", "section": "85"},
            {"act": "IPC", "section": "498A"}
        ],
        "title": "Cruelty by Husband or Relative of Husband",
        "ingredients": [
            {"name": "Married Woman", "description": "The victim is a woman lawfully married."},
            {"name": "Husband or Relative", "description": "Accused is the husband or relative of the husband."},
            {"name": "Cruelty or Harassment", "description": "Conduct driving woman to suicide or causing grave injury/danger to life or health."},
            {"name": "Coercion for Property", "description": "Harassment to coerce woman or her relatives to satisfy unlawful demand for property."}
        ],
        "punishment": {"term": "Imprisonment up to 3 years and fine.", "bailable": False, "cognizable": True},
        "exceptions": [
            {"title": "Ordinary Marital Discord", "description": "Petty domestic squabbles not amounting to wilful conduct driving woman to suicide or injury."}
        ],
        "evidence_links": [
            {"ingredient": "Married Woman", "evidence": "Marriage Certificate"},
            {"ingredient": "Husband or Relative", "evidence": "Witness Statement"},
            {"ingredient": "Cruelty or Harassment", "evidence": "WhatsApp Chats"},
            {"ingredient": "Cruelty or Harassment", "evidence": "Medical Report"},
            {"ingredient": "Cruelty or Harassment", "evidence": "Witness Statement"},
            {"ingredient": "Coercion for Property", "evidence": "Bank Transaction"},
            {"ingredient": "Coercion for Property", "evidence": "Audio Recording"}
        ]
    },
    {
        "sections": [
            {"act": "BNS", "section": "63"},
            {"act": "IPC", "section": "375"}
        ],
        "title": "Rape Definition & Offence",
        "ingredients": [
            {"name": "Female Victim", "description": "Victim is a woman or female person."},
            {"name": "Penetration or Sexual Act", "description": "Penetration of penis, object, or body part into vagina, urethra, anus, or mouth."},
            {"name": "Absence of Free Consent", "description": "Act done against will, without consent, or consent obtained under fear of death/hurt."}
        ],
        "punishment": {"term": "Rigorous imprisonment for not less than 10 years extending to life imprisonment.", "bailable": False, "cognizable": True},
        "exceptions": [
            {"title": "Medical Examination Exception", "description": "Medical procedure or examination conducted in good faith by qualified medical practitioner."}
        ],
        "evidence_links": [
            {"ingredient": "Female Victim", "evidence": "Witness Statement"},
            {"ingredient": "Penetration or Sexual Act", "evidence": "FSL Report"},
            {"ingredient": "Penetration or Sexual Act", "evidence": "DNA Report"},
            {"ingredient": "Penetration or Sexual Act", "evidence": "Medical Report"},
            {"ingredient": "Absence of Free Consent", "evidence": "Statement under Section 164"},
            {"ingredient": "Absence of Free Consent", "evidence": "Dying Declaration"}
        ]
    },
    {
        "sections": [
            {"act": "BNS", "section": "101"},
            {"act": "IPC", "section": "302"}
        ],
        "title": "Punishment for Murder",
        "ingredients": [
            {"name": "Human Victim", "description": "Death caused to a human being."},
            {"name": "Act Causing Death", "description": "Act done by accused causing death."},
            {"name": "Intention to Cause Death", "description": "Intention of causing death or intention of causing bodily injury sufficient in ordinary course of nature to cause death."},
            {"name": "Knowledge of Imminent Danger", "description": "Knowledge that the act is so imminently dangerous that it must in all probability cause death."}
        ],
        "punishment": {"term": "Death or imprisonment for life, and fine.", "bailable": False, "cognizable": True},
        "exceptions": [
            {"title": "Grave and Sudden Provocation", "description": "Culpable homicide not amounting to murder if offender deprived of self-control by provocation."},
            {"title": "Private Defence", "description": "Act done in good faith of right of private defence of person or property."},
            {"title": "Sudden Fight", "description": "Homicide committed without premeditation in a sudden fight in heat of passion."}
        ],
        "evidence_links": [
            {"ingredient": "Human Victim", "evidence": "Postmortem Report"},
            {"ingredient": "Act Causing Death", "evidence": "Forensic Report"},
            {"ingredient": "Act Causing Death", "evidence": "Weapon Recovery Memo"},
            {"ingredient": "Intention to Cause Death", "evidence": "Witness Statement"},
            {"ingredient": "Intention to Cause Death", "evidence": "CCTV Footage"}
        ]
    },
    {
        "sections": [
            {"act": "BNS", "section": "74"},
            {"act": "IPC", "section": "354"}
        ],
        "title": "Assault on Woman to Outrage Modesty",
        "ingredients": [
            {"name": "Woman Victim", "description": "Victim is a female person."},
            {"name": "Assault or Criminal Force", "description": "Accused used assault or criminal force against the woman."},
            {"name": "Intent to Outrage Modesty", "description": "Act done with intention or knowledge that it will outrage her modesty."}
        ],
        "punishment": {"term": "Imprisonment for 1 to 5 years and fine.", "bailable": False, "cognizable": True},
        "exceptions": [],
        "evidence_links": [
            {"ingredient": "Woman Victim", "evidence": "Witness Statement"},
            {"ingredient": "Assault or Criminal Force", "evidence": "CCTV Footage"},
            {"ingredient": "Assault or Criminal Force", "evidence": "Medical Report"},
            {"ingredient": "Intent to Outrage Modesty", "evidence": "Witness Statement"},
            {"ingredient": "Intent to Outrage Modesty", "evidence": "Statement under Section 164"}
        ]
    },
    {
        "sections": [
            {"act": "BNS", "section": "124"},
            {"act": "IPC", "section": "326A"}
        ],
        "title": "Voluntarily Causing Grievous Hurt by Use of Acid",
        "ingredients": [
            {"name": "Acid or Corrosive Substance", "description": "Use of acid or acidic/corrosive substance."},
            {"name": "Grievous Hurt or Disfigurement", "description": "Permanent or partial damage, deformity, or disfigurement to any part of body."},
            {"name": "Voluntary Act with Intention/Knowledge", "description": "Act done voluntarily with intention or knowledge of causing injury."}
        ],
        "punishment": {"term": "Imprisonment for not less than 10 years extending to life imprisonment.", "bailable": False, "cognizable": True},
        "exceptions": [],
        "evidence_links": [
            {"ingredient": "Acid or Corrosive Substance", "evidence": "Chemical Analysis Report"},
            {"ingredient": "Grievous Hurt or Disfigurement", "evidence": "Medical Report"},
            {"ingredient": "Voluntary Act with Intention/Knowledge", "evidence": "CCTV Footage"},
            {"ingredient": "Voluntary Act with Intention/Knowledge", "evidence": "Witness Statement"}
        ]
    }
]

# ── COURT CASE INTERPRETATIONS & PRINCIPLES ────────────────────────────────────
CASE_INTERPRETATIONS = [
    {
        "case_name": "SWAJIT HALDER@BABU HALDER v. STATEOFWEST BENGAL",
        "interprets_sections": [
            {"act": "BNS", "section": "80"},
            {"act": "IPC", "section": "304B"}
        ],
        "establishes_principles": [
            "Presumption of Dowry Death",
            "Burden of Proof"
        ]
    },
    {
        "case_name": "SUKHWINDER SINGH v. STATE OF PUNJAB (C",
        "interprets_sections": [
            {"act": "BNS", "section": "80"},
            {"act": "IPC", "section": "304B"}
        ],
        "establishes_principles": [
            "Presumption of Dowry Death",
            "Cruelty Soon Before Death"
        ]
    },
    {
        "case_name": "Bachchan Singh v. State of Punjab",
        "interprets_sections": [
            {"act": "BNS", "section": "101"},
            {"act": "IPC", "section": "302"}
        ],
        "establishes_principles": [
            "Rarest of Rare Cases",
            "Presumption of Innocence"
        ]
    },
    {
        "case_name": "Lalita Kumari v. Govt of UP",
        "interprets_sections": [
            {"act": "BNS", "section": "173"},
            {"act": "IPC", "section": "154"}
        ],
        "establishes_principles": [
            "Mandatory FIR Registration",
            "Natural Justice"
        ]
    }
]


def ingest_statutory_ingredients():
    """Ingests Ingredient, Punishment, Exception nodes and dual Evidence links in Neo4j."""
    print("=" * 80, flush=True)
    print("INGESTING STATUTORY INGREDIENTS, PUNISHMENTS, EXCEPTIONS & DUAL EVIDENCE LINKS", flush=True)
    print("=" * 80, flush=True)

    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[Error] Neo4j credentials missing in environment.", flush=True)
        sys.exit(1)

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[Error] neo4j python package missing.", flush=True)
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:
        # 1. Constraints & Indexes
        try:
            session.run("CREATE CONSTRAINT ingredient_name_unique IF NOT EXISTS FOR (ing:Ingredient) REQUIRE ing.name IS UNIQUE")
            session.run("CREATE CONSTRAINT punishment_term_unique IF NOT EXISTS FOR (p:Punishment) REQUIRE p.term IS UNIQUE")
            session.run("CREATE CONSTRAINT exception_title_unique IF NOT EXISTS FOR (ex:Exception) REQUIRE ex.title IS UNIQUE")
            session.run("CREATE CONSTRAINT principle_name_unique IF NOT EXISTS FOR (pr:LegalPrinciple) REQUIRE pr.name IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] {e}", flush=True)

        # 2. Ingest Statutory Elements
        print("[1/5] Ingesting Ingredients, Punishments, and Exceptions...", flush=True)
        for group in STATUTORY_DATA:
            p_data = group["punishment"]
            # MERGE Punishment node
            session.run("""
                MERGE (p:Punishment {term: $term})
                SET p.bailable = $bailable, p.cognizable = $cognizable
            """, term=p_data["term"], bailable=p_data["bailable"], cognizable=p_data["cognizable"])

            for sec in group["sections"]:
                act = sec["act"]
                snum = sec["section"]
                
                # MERGE LawSection and PRESCRIBES Punishment
                session.run("""
                    MERGE (l:LawSection {act: $act, section: $section})
                    WITH l
                    MATCH (p:Punishment {term: $term})
                    MERGE (l)-[:PRESCRIBES]->(p)
                """, act=act, section=snum, term=p_data["term"])

                # MERGE Ingredients & HAS_INGREDIENT
                for ing in group["ingredients"]:
                    session.run("""
                        MERGE (i:Ingredient {name: $name})
                        SET i.description = $desc
                        WITH i
                        MATCH (l:LawSection {act: $act, section: $section})
                        MERGE (l)-[:HAS_INGREDIENT]->(i)
                    """, name=ing["name"], desc=ing["description"], act=act, section=snum)

                # MERGE Exceptions & HAS_EXCEPTION
                for ex in group["exceptions"]:
                    session.run("""
                        MERGE (ex:Exception {title: $title})
                        SET ex.description = $desc
                        WITH ex
                        MATCH (l:LawSection {act: $act, section: $section})
                        MERGE (l)-[:HAS_EXCEPTION]->(ex)
                    """, title=ex["title"], desc=ex["description"], act=act, section=snum)

                # MERGE Evidence Links (DUAL PATH: Ingredient -> REQUIRES_EVIDENCE -> EvidenceType AND LawSection -> SUPPORTED_BY -> EvidenceType)
                for elink in group["evidence_links"]:
                    ing_name = elink["ingredient"]
                    ev_name = elink["evidence"]

                    session.run("""
                        MERGE (e:EvidenceType {name: $ev_name})
                        WITH e
                        MATCH (i:Ingredient {name: $ing_name})
                        MERGE (i)-[:REQUIRES_EVIDENCE]->(e)
                    """, ing_name=ing_name, ev_name=ev_name)

                    session.run("""
                        MATCH (l:LawSection {act: $act, section: $section})
                        MATCH (e:EvidenceType {name: $ev_name})
                        MERGE (l)-[:SUPPORTED_BY]->(e)
                    """, act=act, section=snum, ev_name=ev_name)

        # 3. Ingest Court Case INTERPRETS and ESTABLISHES Relationships
        print("[2/5] Ingesting CourtCase INTERPRETS LawSection & ESTABLISHES LegalPrinciple...", flush=True)
        for citem in CASE_INTERPRETATIONS:
            cname = citem["case_name"]
            session.run("MERGE (c:Case {title: $cname}) SET c.case_id = coalesce(c.case_id, $cname)", cname=cname)

            for sec in citem["interprets_sections"]:
                session.run("""
                    MATCH (c:Case {title: $cname})
                    MATCH (l:LawSection {act: $act, section: $section})
                    MERGE (c)-[:INTERPRETS]->(l)
                """, cname=cname, act=sec["act"], section=sec["section"])

            for pr in citem["establishes_principles"]:
                session.run("""
                    MERGE (p:LegalPrinciple {name: $pname})
                    WITH p
                    MATCH (c:Case {title: $cname})
                    MERGE (c)-[:ESTABLISHES]->(p)
                """, cname=cname, pname=pr)

        # 4. Summary Stats
        ing_count = session.run("MATCH (i:Ingredient) RETURN count(i) AS count").single()["count"]
        pun_count = session.run("MATCH (p:Punishment) RETURN count(p) AS count").single()["count"]
        exc_count = session.run("MATCH (ex:Exception) RETURN count(ex) AS count").single()["count"]
        has_ing_count = session.run("MATCH ()-[r:HAS_INGREDIENT]->() RETURN count(r) AS count").single()["count"]
        req_ev_count = session.run("MATCH ()-[r:REQUIRES_EVIDENCE]->() RETURN count(r) AS count").single()["count"]
        sup_by_count = session.run("MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS count").single()["count"]
        interprets_count = session.run("MATCH ()-[r:INTERPRETS]->() RETURN count(r) AS count").single()["count"]
        establishes_count = session.run("MATCH ()-[r:ESTABLISHES]->() RETURN count(r) AS count").single()["count"]

        print("\n" + "=" * 80, flush=True)
        print("STATUTORY INGREDIENTS & DUAL EVIDENCE GRAPH INGESTION COMPLETE", flush=True)
        print("=" * 80, flush=True)
        print(f"  - Ingredient Nodes        : {ing_count}", flush=True)
        print(f"  - Punishment Nodes        : {pun_count}", flush=True)
        print(f"  - Exception Nodes         : {exc_count}", flush=True)
        print(f"  - HAS_INGREDIENT Edges    : {has_ing_count}", flush=True)
        print(f"  - REQUIRES_EVIDENCE Edges : {req_ev_count}", flush=True)
        print(f"  - SUPPORTED_BY Edges      : {sup_by_count}", flush=True)
        print(f"  - INTERPRETS Edges        : {interprets_count}", flush=True)
        print(f"  - ESTABLISHES Edges       : {establishes_count}", flush=True)
        print("=" * 80 + "\n", flush=True)

    driver.close()


if __name__ == "__main__":
    ingest_statutory_ingredients()
