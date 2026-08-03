import os
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

target_ids = ["IPC_34", "IPC_120B", "IPC_100"]

print("=" * 80)
print(" VERIFYING COMPLETE BACKFILL FOR IPC 34, IPC 120B, AND IPC 100 IN NEO4J")
print("=" * 80 + "\n")

with driver.session() as s:
    for sid in target_ids:
        # Node properties
        node_res = s.run("""
            MATCH (n:LawSection {id: $id})
            RETURN properties(n) AS props
        """, id=sid).single()
        
        # Connected keywords
        kw_res = s.run("""
            MATCH (n:LawSection {id: $id})-[:HAS_KEYWORD]->(k:Keyword)
            RETURN k.name AS keyword
        """, id=sid).data()
        keywords = [r["keyword"] for r in kw_res]

        # Connected crimes
        crime_res = s.run("""
            MATCH (n:LawSection {id: $id})-[:DEFINED_BY]-(c:Crime)
            RETURN c.name AS crime
        """, id=sid).data()
        crimes = [r["crime"] for r in crime_res]

        # Connected punishments
        punish_res = s.run("""
            MATCH (n:LawSection {id: $id})-[:HAS_PUNISHMENT]->(p:Punishment)
            RETURN p.description AS punishment
        """, id=sid).data()
        punishments = [r["punishment"] for r in punish_res]

        print(f"--- SECTION: {sid} ---")
        props = node_res["props"] if node_res else {}
        for k in ["title", "description", "punishment", "cognizable", "bailable", "court", "node_type", "data_complete", "content_source"]:
            print(f"  * {k:15s}: {props.get(k, 'N/A')}")
        
        print(f"  * Connected Keywords   : {keywords if keywords else 'None (General Provision / No keyword link)'}")
        print(f"  * Connected Crimes     : {crimes if crimes else 'None'}")
        print(f"  * Connected Punishments: {punishments if punishments else props.get('punishment') or 'None'}")
        print()

# Check dataset provenance in source files
print("=" * 80)
print(" DATASET PROVENANCE ANALYSIS")
print("=" * 80)

ipc_clean_df = pd.read_csv(BASE_DIR / "data" / "cleaned" / "ipc.csv", dtype=str).fillna("")
new_ipc_df = pd.read_csv(BASE_DIR / "data" / "new" / "new_ipc_with_detail_description.csv", dtype=str).fillna("")
json_ipc_df = pd.read_json(BASE_DIR / "data" / "old" / "ipc.json", dtype=str).fillna("")

for sec in ["34", "120B", "100"]:
    print(f"\nTracing Section '{sec}':")
    row_new = new_ipc_df[new_ipc_df["Section"] == sec]
    row_json = json_ipc_df[json_ipc_df["Section"] == sec]
    
    if not row_new.empty:
        r = row_new.iloc[0]
        print(f"  [Primary Source]: data/new/new_ipc_with_detail_description.csv")
        print(f"    - Offense    : '{r['Offense']}'")
        print(f"    - Description: '{r['Description'][:80]}...'")
        print(f"    - Punishment : '{r['Punishment']}'")
        print(f"    - Cognizable : '{r['Cognizable']}'")
    elif not row_json.empty:
        r = row_json.iloc[0]
        print(f"  [Secondary Source]: data/old/ipc.json")
        print(f"    - Section Title: '{r['section_title']}'")
        print(f"    - Section Desc : '{r['section_desc'][:80]}...'")

driver.close()
