"""
seed_missing_ingredients.py
============================
Seeds missing statutory Ingredient and EvidenceType nodes in Neo4j
for key BNS provisions (BNS 355, BNS 76, BNS 64, BNS 351, BNS 115).
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


INGREDIENT_SEED_DATA = [
    {
        "act": "BNS",
        "section": "355",
        "ingredients": [
            {"name": "Woman Victim", "element_type": "VICTIM", "desc": "Victim must be a female person."},
            {"name": "Assault or Criminal Force", "element_type": "ACTUS_REUS", "desc": "Accused used assault or criminal force against the woman."},
            {"name": "Intent to Outrage Modesty", "element_type": "MENS_REA", "desc": "Accused intended to outrage her modesty or knew it likely."}
        ]
    },
    {
        "act": "BNS",
        "section": "76",
        "ingredients": [
            {"name": "Woman Victim", "element_type": "VICTIM", "desc": "Victim must be a female person."},
            {"name": "Assault or Criminal Force", "element_type": "ACTUS_REUS", "desc": "Accused used assault or criminal force against the woman."},
            {"name": "Intent to Disrobe", "element_type": "MENS_REA", "desc": "Accused intended to disrobe or compel the woman to be naked."}
        ]
    },
    {
        "act": "BNS",
        "section": "64",
        "ingredients": [
            {"name": "Female Victim", "element_type": "VICTIM", "desc": "Victim must be a female person."},
            {"name": "Penetration or Sexual Act", "element_type": "ACTUS_REUS", "desc": "Accused engaged in non-consensual sexual penetration."},
            {"name": "Absence of Free Consent", "element_type": "MENS_REA", "desc": "Sexual act committed against victim's will or without free consent."}
        ]
    },
    {
        "act": "BNS",
        "section": "351",
        "ingredients": [
            {"name": "Threat of Injury", "element_type": "ACTUS_REUS", "desc": "Accused threatened person, reputation, or property with injury."},
            {"name": "Intent to Cause Alarm", "element_type": "MENS_REA", "desc": "Intended to cause alarm to that person or compel act."}
        ]
    },
    {
        "act": "BNS",
        "section": "115",
        "ingredients": [
            {"name": "Voluntary Act", "element_type": "ACTUS_REUS", "desc": "Accused committed an act causing bodily pain, disease, or infirmity."},
            {"name": "Intent to Cause Hurt", "element_type": "MENS_REA", "desc": "Intended or knew likely that hurt would be caused."}
        ]
    }
]


def seed_ingredients():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[seed_ingredients] Error: Missing Neo4j credentials in environment.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("SEEDING MISSING INGREDIENTS IN NEO4J")
    print("=" * 80)

    with driver.session(database=NEO4J_DATABASE) as session:
        for item in INGREDIENT_SEED_DATA:
            act = item["act"]
            sec = item["section"]
            
            for ing in item["ingredients"]:
                session.run("""
                    MATCH (n:LawSection {act: $act, section: $sec})
                    MERGE (i:Ingredient {name: $name})
                    SET i.description = $desc, i.element_type = $element_type
                    MERGE (n)-[:HAS_INGREDIENT]->(i)
                """, act=act, sec=sec, name=ing["name"], desc=ing["desc"], element_type=ing["element_type"])
                print(f"  [OK] Seeded ingredient '{ing['name']}' ({ing['element_type']}) -> {act} {sec}")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    seed_ingredients()
