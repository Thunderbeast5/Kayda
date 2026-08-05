import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR))

from agents.lexigraph.services.fact_extractor_service import FactExtractorService

extractor = FactExtractorService()

sample_queries = [
    "A married woman was repeatedly harassed for dowry and later burned alive.",
    "A woman reported that a man forcibly grabbed her, touched her inappropriately, and attempted to remove her clothes, but there was no allegation of sexual intercourse."
]

print("=" * 80)
print("TESTING HYBRID LLM FACT EXTRACTOR SERVICE")
print("=" * 80)

for q in sample_queries:
    print(f"\nQuery: '{q}'")
    facts = extractor.extract_facts(q)
    print(f"Extraction Mode: {facts.get('extraction_mode')}")
    print(f"Victim Gender  : {facts.get('victim_gender')}")
    print(f"Marital Status : {facts.get('marital_status')}")
    print(f"Death Occurred : {facts.get('death')} (Type: {facts.get('death_type')})")
    print(f"Dowry Demand   : {facts.get('dowry_demand')}")
    print(f"Cruelty        : {facts.get('cruelty_or_harassment')}")
    print(f"Modesty Touch  : {facts.get('inappropriate_touch_or_modesty')}")
    print(f"Disrobing      : {facts.get('disrobing_attempt')}")
    print(f"Penetration    : {facts.get('sexual_penetration')}")

print("=" * 80)
