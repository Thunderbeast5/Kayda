import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
# Ensure backend is in sys.path so we can import lexigraphbe
sys.path.insert(0, str(BASE_DIR / "backend"))

from neo4j import GraphDatabase
from lexigraphbe.ipc2bns_mapper import IPC2BNSMapper

load_dotenv(BASE_DIR / "backend" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

def add_ingredients_relations():
    json_path = BASE_DIR / "data" / "ingredients.json"
    if not json_path.exists():
        print(f"Data file not found at {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    mapper = IPC2BNSMapper()
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        for item in data:
            ipc_sec = str(item.get("section", "")).strip()
            if not ipc_sec:
                continue
                
            ingredients = item.get("ingredients", [])
            if not ingredients:
                continue
                
            # Get BNS equivalents
            bns_info = mapper.get_bns_equivalent(ipc_sec)
            bns_secs = []
            if bns_info:
                clean = bns_info.get("bns_section_clean")
                parent = bns_info.get("parent_bns_section")
                if clean and clean != "REMOVED":
                    bns_secs.append(clean)
                if parent and parent not in bns_secs and parent != "REMOVED":
                    bns_secs.append(parent)
                    
            for ing_str in ingredients:
                # Name is a truncated version for display, description holds the full text
                ing_name = (ing_str[:97] + "...") if len(ing_str) > 100 else ing_str
                ing_desc = ing_str
                
                # MERGE Ingredient node
                session.run("""
                    MERGE (i:Ingredient {name: $name})
                    ON CREATE SET i.description = $desc
                    ON MATCH SET i.description = $desc
                """, name=ing_name, desc=ing_desc)
                
                # Link to IPC
                session.run("""
                    MATCH (l:LawSection {act: "IPC", section: $section})
                    MATCH (i:Ingredient {name: $name})
                    MERGE (l)-[:HAS_INGREDIENT]->(i)
                """, section=ipc_sec, name=ing_name)
                
                # Link to BNS equivalent(s)
                for bns_sec in bns_secs:
                    session.run("""
                        MATCH (l:LawSection {act: "BNS", section: $section})
                        MATCH (i:Ingredient {name: $name})
                        MERGE (l)-[:HAS_INGREDIENT]->(i)
                    """, section=bns_sec, name=ing_name)
                    
    driver.close()
    print("Ingredient relations added successfully to IPC and BNS nodes.")

if __name__ == "__main__":
    add_ingredients_relations()
