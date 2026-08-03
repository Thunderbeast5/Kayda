"""
debug_issue1_issue2.py
======================
Diagnostic script to investigate:
1. GeneratedNode count = 0 (137(1) existence & auto-generation logic check).
2. Count discrepancies in BNS sections in Neo4j.
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

print("=" * 80)
print(" DIAGNOSTIC 1: CSV INSPECTION FOR 137(1) & CLAUSES")
print("=" * 80 + "\n")

# Check 137(1)
rows_137_1 = clean_df[clean_df["BNS_Section_Clean"] == "137(1)"]
print(f"Rows with BNS_Section_Clean == '137(1)' in ipc2bns_clean.csv: {len(rows_137_1)}")
for idx, r in rows_137_1.iterrows():
    print(f"  - IPC {r['IPC_Section']} ({r['IPC_Title']}) -> BNS {r['BNS_Section_Clean']} [NodeType={r['NodeType']}]")

# Check all CLAUSE rows
clauses = clean_df[clean_df["NodeType"] == "CLAUSE"]
print(f"\nTotal CLAUSE rows in ipc2bns_clean.csv: {len(clauses)}")
all_bns_clean_targets = set(clean_df[clean_df["NodeType"] != "SPECIAL_STATUS"]["BNS_Section_Clean"])

for idx, r in clauses.iterrows():
    p_sub = r["ParentSubsection"]
    in_clean_csv = p_sub in all_bns_clean_targets
    print(
        f"  - Clause Target '{r['BNS_Section_Clean']}' (IPC {r['IPC_Section']}) -> "
        f"ParentSection='{r['ParentSection']}', ParentSubsection='{p_sub}' | Exists in ipc2bns_clean.csv? {in_clean_csv}"
    )

print("\n" + "=" * 80)
print(" DIAGNOSTIC 2: NEO4J BNS NODE COUNT BREAKDOWN")
print("=" * 80 + "\n")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

with driver.session() as s:
    total_bns_lawsection = s.run("MATCH (n:LawSection {act:'BNS'}) RETURN count(n) AS c").single()["c"]
    total_bns_section_label = s.run("MATCH (n:BNSSection) RETURN count(n) AS c").single()["c"]

    count_sections = s.run("MATCH (n:BNSSection) WHERE n.node_type = 'SECTION' RETURN count(n) AS c").single()["c"]
    count_subsections = s.run("MATCH (n:BNSSection) WHERE n.node_type = 'SUBSECTION' RETURN count(n) AS c").single()["c"]
    count_clauses = s.run("MATCH (n:BNSSection) WHERE n.node_type = 'CLAUSE' RETURN count(n) AS c").single()["c"]
    count_explanations = s.run("MATCH (n:BNSSection) WHERE n.node_type = 'EXPLANATION' RETURN count(n) AS c").single()["c"]
    count_null_type = s.run("MATCH (n:BNSSection) WHERE n.node_type IS NULL RETURN count(n) AS c").single()["c"]
    count_generated = s.run("MATCH (n:GeneratedNode) RETURN count(n) AS c").single()["c"]

    print(f"Total (:LawSection {{act:'BNS'}}): {total_bns_lawsection}")
    print(f"Total (:BNSSection):              {total_bns_section_label}")
    print("-" * 50)
    print(f"  - SECTION count:                 {count_sections}")
    print(f"  - SUBSECTION count:              {count_subsections}")
    print(f"  - CLAUSE count:                  {count_clauses}")
    print(f"  - EXPLANATION count:             {count_explanations}")
    print(f"  - NULL / UNSET node_type count:  {count_null_type}")
    print(f"  - GeneratedNode count:           {count_generated}")
    print(f"  - SUM (SECTION+SUBSECTION+CLAUSE+EXPLANATION+NULL) = {count_sections + count_subsections + count_clauses + count_explanations + count_null_type}")

    print("\nSample NULL node_type BNS nodes (unmapped base BNS sections):")
    null_nodes = s.run("MATCH (n:BNSSection) WHERE n.node_type IS NULL RETURN n.id AS id, n.section AS sec, n.mapping_status AS status LIMIT 5").data()
    for r in null_nodes:
        print(f"  - ID: {r['id']}, Section: {r['sec']}, Status: {r['status']}")

driver.close()
