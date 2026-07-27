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

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

with driver.session(database=NEO4J_DATABASE) as session:
    print("=" * 80)
    print("INSPECTING NEO4J INGREDIENT GRAPH")
    print("=" * 80)
    
    sections = ["80", "355", "74", "76", "63", "64", "351", "115", "124"]
    
    for sec in sections:
        rows = session.run("""
            MATCH (n:LawSection)
            WHERE n.section = $sec
            OPTIONAL MATCH (n)-[:HAS_INGREDIENT]->(i:Ingredient)
            OPTIONAL MATCH (i)-[:REQUIRES_EVIDENCE]->(ev:EvidenceType)
            RETURN n.act AS act, n.section AS section, n.title AS title, 
                   i.name AS ingredient_name, i.element_type AS element_type, i.description AS ingredient_desc,
                   ev.name AS evidence_name
        """, sec=sec).data()
        
        print(f"\n--- Section BNS/IPC {sec} ---")
        if not rows:
            print("  [NOT FOUND]")
            continue
            
        ing_dict = {}
        for r in rows:
            print(f"  Section: {r['act']} {r['section']} - '{r['title']}'")
            ing_name = r.get("ingredient_name")
            if ing_name:
                if ing_name not in ing_dict:
                    ing_dict[ing_name] = {"element_type": r.get("element_type"), "evidence": set()}
                if r.get("evidence_name"):
                    ing_dict[ing_name]["evidence"].add(r.get("evidence_name"))
        
        if ing_dict:
            print("  Ingredients:")
            for k, v in ing_dict.items():
                ev_str = f" -> Evidence: {list(v['evidence'])}" if v['evidence'] else ""
                print(f"    - [{v['element_type'] or 'INGREDIENT'}] {k}{ev_str}")
        else:
            print("  ⚠️ No ingredients linked via :HAS_INGREDIENT relationship.")

driver.close()
