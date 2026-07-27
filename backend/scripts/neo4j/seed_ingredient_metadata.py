"""
seed_ingredient_metadata.py
===========================
Seeds generic evaluation metadata on Neo4j :Ingredient nodes:
- fact_key
- comparator
- expected_value
- mandatory
- confidence_weight
- element_type
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


INGREDIENT_METADATA_MAP = [
    {
        "name": "Woman Victim",
        "fact_key": "victim_gender",
        "comparator": "eq",
        "expected_value": "female",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "VICTIM"
    },
    {
        "name": "Female Victim",
        "fact_key": "victim_gender",
        "comparator": "eq",
        "expected_value": "female",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "VICTIM"
    },
    {
        "name": "Married Woman",
        "fact_key": "marital_status",
        "comparator": "eq",
        "expected_value": "married",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "VICTIM"
    },
    {
        "name": "Husband or Relative",
        "fact_key": "marital_status",
        "comparator": "eq",
        "expected_value": "married",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "CIRCUMSTANCE"
    },
    {
        "name": "Unnatural Death",
        "fact_key": "death",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.30,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Within Seven Years of Marriage",
        "fact_key": "marriage_duration_years",
        "comparator": "lte",
        "expected_value": "7",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "CIRCUMSTANCE"
    },
    {
        "name": "Dowry Demand",
        "fact_key": "dowry_demand",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.25,
        "element_type": "CIRCUMSTANCE"
    },
    {
        "name": "Cruelty or Harassment Soon Before Death",
        "fact_key": "cruelty_or_harassment",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.25,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Cruelty or Harassment",
        "fact_key": "cruelty_or_harassment",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.25,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Assault or Criminal Force",
        "fact_key": "physical_force_or_assault",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.30,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Intent to Outrage Modesty",
        "fact_key": "inappropriate_touch_or_modesty",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.35,
        "element_type": "MENS_REA"
    },
    {
        "name": "Intent to Disrobe",
        "fact_key": "disrobing_attempt",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.35,
        "element_type": "MENS_REA"
    },
    {
        "name": "Penetration or Sexual Act",
        "fact_key": "sexual_penetration",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.40,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Absence of Free Consent",
        "fact_key": "absence_of_consent",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.30,
        "element_type": "MENS_REA"
    },
    {
        "name": "Acid or Corrosive Substance",
        "fact_key": "acid_or_corrosive",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.40,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Grievous Hurt or Disfigurement",
        "fact_key": "grievous_hurt_or_disfigurement",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": False,
        "weight": 0.20,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Coercion for Property",
        "fact_key": "dowry_demand",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.25,
        "element_type": "MENS_REA"
    },
    {
        "name": "Voluntary Act",
        "fact_key": "physical_force_or_assault",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Voluntary Act with Intention/Knowledge",
        "fact_key": "physical_force_or_assault",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Threat of Injury",
        "fact_key": "cruelty_or_harassment",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "ACTUS_REUS"
    },
    {
        "name": "Intent to Cause Alarm",
        "fact_key": "cruelty_or_harassment",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "MENS_REA"
    },
    {
        "name": "Intent to Cause Hurt",
        "fact_key": "physical_force_or_assault",
        "comparator": "is_true",
        "expected_value": "true",
        "mandatory": True,
        "weight": 0.20,
        "element_type": "MENS_REA"
    }
]


def seed_metadata():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[seed_metadata] Error: Missing Neo4j credentials.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("SEEDING EVALUATION METADATA ON NEO4J INGREDIENT NODES")
    print("=" * 80)

    with driver.session(database=NEO4J_DATABASE) as session:
        for m in INGREDIENT_METADATA_MAP:
            session.run("""
                MATCH (i:Ingredient {name: $name})
                SET i.fact_key = $fact_key,
                    i.comparator = $comparator,
                    i.expected_value = $expected_value,
                    i.mandatory = $mandatory,
                    i.confidence_weight = $weight,
                    i.element_type = $element_type
            """, name=m["name"], fact_key=m["fact_key"], comparator=m["comparator"],
                 expected_value=m["expected_value"], mandatory=m["mandatory"],
                 weight=m["weight"], element_type=m["element_type"])
            print(f"  [OK] Seeded metadata -> Ingredient '{m['name']}' (key: {m['fact_key']}, comp: {m['comparator']}, type: {m['element_type']})")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    seed_metadata()
