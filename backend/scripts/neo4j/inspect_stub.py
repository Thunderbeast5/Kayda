import os
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

with driver.session() as s:
    stub = s.run("MATCH (n:LawSection {id: 'IPC_269A'}) RETURN properties(n) AS p").single()
    print("=== IPC_269A NEO4J NODE PROPERTIES ===")
    if stub:
        for k, v in stub["p"].items():
            print(f"  {k}: {v}")
    else:
        print("IPC_269A not found")

ipc2bns_clean = pd.read_csv(BASE_DIR / "data" / "cleaned" / "ipc2bns_clean.csv", dtype=str).fillna("")
row_269a = ipc2bns_clean[ipc2bns_clean["IPC_Section"] == "269A"]
print("\n=== IPC_269A ROW IN ipc2bns_clean.csv ===")
print(row_269a[["IPC_Section", "IPC_Title", "BNS_Section_Clean", "BNS_Title", "Notes"]])

driver.close()
