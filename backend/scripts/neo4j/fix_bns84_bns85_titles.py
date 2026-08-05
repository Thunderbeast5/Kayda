"""
fix_bns84_bns85_titles.py
========================
Fixes data-entry copy-paste error where BNS 84 in Neo4j had BNS 85's title and description.

Correct Statutory Provisions (BNS 2023):
- BNS 84: Enticing or taking away or detaining with criminal intent a married woman (replaces IPC 498).
- BNS 85: Husband or relative of husband of a woman subjecting her to cruelty (replaces IPC 498A).
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


def fix_titles():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[fix_titles] Error: Missing Neo4j credentials.")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("=" * 80)
    print("FIXING BNS 84 AND BNS 85 TITLES AND DESCRIPTIONS IN NEO4J")
    print("=" * 80)

    with driver.session(database=NEO4J_DATABASE) as session:
        # Update BNS 84
        session.run("""
            MATCH (n:LawSection {act: 'BNS', section: '84'})
            SET n.title = 'Enticing or taking away or detaining with criminal intent a married woman',
                n.description = 'Whoever takes or entices away any woman who is and whom he knows or has reason to believe to be the wife of any other man, from that man, or from any person having the care of her on behalf of that man, with intent that she may have illicit intercourse with any person, or conceals or detains with that intent any such woman, shall be punished with imprisonment of either description for a term which may extend to two years, or with fine, or with both.'
        """)
        print("  [OK] Corrected BNS 84 -> 'Enticing or taking away or detaining with criminal intent a married woman'")

        # Update BNS 85
        session.run("""
            MATCH (n:LawSection {act: 'BNS', section: '85'})
            SET n.title = 'Husband or relative of husband of a woman subjecting her to cruelty',
                n.description = 'Whoever, being the husband or the relative of the husband of a woman, subjects such woman to cruelty shall be punished with imprisonment for a term which may extend to three years and shall also be liable to fine.'
        """)
        print("  [OK] Corrected BNS 85 -> 'Husband or relative of husband of a woman subjecting her to cruelty'")

        # Verify
        rows = session.run("""
            MATCH (n:LawSection)
            WHERE n.act = 'BNS' AND n.section IN ['84', '85']
            RETURN n.act AS act, n.section AS sec, n.title AS title
        """).data()
        for r in rows:
            print(f"  Verified DB Node: {r['act']} {r['sec']} -> '{r['title']}'")

    driver.close()
    print("=" * 80)


if __name__ == "__main__":
    fix_titles()
