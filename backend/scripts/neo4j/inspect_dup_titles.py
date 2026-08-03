"""
inspect_dup_titles.py
=====================
Inspects the 4 duplicate target BNS nodes (8(6), 70(2), 189(2), 189(5)) in
ipc2bns_clean.csv, bns_sections_clean.csv, and current Neo4j DB.
"""

import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

DATA_CLEANED_DIR = BASE_DIR / "data" / "cleaned"
clean_df = pd.read_csv(DATA_CLEANED_DIR / "ipc2bns_clean.csv", dtype=str).fillna("")
bns_df = pd.read_csv(DATA_CLEANED_DIR / "bns_sections_clean.csv", dtype=str).fillna("")

targets = ["8(6)", "70(2)", "189(2)", "189(5)"]

print("Columns in bns_sections_clean.csv:", bns_df.columns.tolist())
sec_col = [c for c in bns_df.columns if "sec" in c.lower()][0]

print("=" * 80)
print(" DUPLICATE TARGET NODES CSV & TITLE INSPECTION")
print("=" * 80 + "\n")

for t in targets:
    rows = clean_df[clean_df["BNS_Section_Clean"] == t]
    print(f"Target BNS {t} (Count={len(rows)} mapping rows in ipc2bns_clean.csv):")
    for idx, r in rows.iterrows():
        print(f"  * IPC {r['IPC_Section']} ('{r['IPC_Title']}') -> BNS_Title in CSV: '{r['BNS_Title']}' [Group={r['DuplicateGroup']}]")
    
    base_sec = t.split("(")[0]
    base_info = bns_df[bns_df[sec_col] == base_sec]
    base_title = base_info["title"].values[0] if "title" in base_info.columns and not base_info.empty else "N/A"
    print(f"  -> Base BNS {base_sec} Title in bns_sections_clean.csv: '{base_title}'\n")

print("=" * 80)
print(" NEO4J CURRENT NODE & RELATIONSHIP TITLES")
print("=" * 80 + "\n")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

with driver.session() as s:
    for t in targets:
        node_id = f"BNS_{t}"
        node_data = s.run("MATCH (n:LawSection {id: $id}) RETURN n.title AS title, n.section AS sec", id=node_id).single()
        print(f"Node {node_id}: Title in Neo4j = '{node_data['title'] if node_data else 'NOT FOUND'}'")
        
        rels = s.run("""
            MATCH (i:LawSection)-[r:REPLACED_BY]->(b:LawSection {id: $id})
            RETURN i.id AS ipc_id, i.title AS ipc_node_title, r.ipc_title AS rel_ipc_title
        """, id=node_id).data()
        for r in rels:
            print(f"  * Inbound REPLACED_BY from {r['ipc_id']}: rel_ipc_title = '{r['rel_ipc_title']}'")
        print()

driver.close()
