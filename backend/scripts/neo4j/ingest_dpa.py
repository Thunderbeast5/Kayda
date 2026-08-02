"""
ingest_dpa.py - Dowry Prohibition Act (DPA) Ingestion Script
=============================================================
Ingests Dowry Prohibition Act sections from CSV into Neo4j with high accuracy.
Automatically wipes previously ingested nodes before re-ingestion.

Usage:
    python scripts/neo4j/ingest_dpa.py
    python scripts/neo4j/ingest_dpa.py --wipe     # explicit wipe flag (also default behavior)
"""

import csv
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
_env_candidates = [
    BASE_DIR.parent / ".env",          # scripts/.env
    BASE_DIR.parent.parent / ".env",   # backend/.env
    Path(".env"),
]
ENV_PATH = next((p for p in _env_candidates if p.exists()), None)

# DPA CSV location
DPA_CSV = BASE_DIR.parent / "pinecone" / "data" / "Dowry_sections.csv"

load_dotenv(ENV_PATH) if ENV_PATH else load_dotenv()
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise EnvironmentError("Missing NEO4J credentials in .env")

print(f"[INFO] Neo4j URI: {NEO4J_URI}")
print(f"[INFO] Neo4j Database: {NEO4J_DATABASE}")
print(f"[INFO] DPA CSV: {DPA_CSV}")
print(f"[INFO] DPA CSV exists: {DPA_CSV.exists()}")

# ── Utility Functions ─────────────────────────────────────────────────────────

def clean(value):
    """Clean CSV cell values thoroughly."""
    if value is None:
        return ""
    val_str = str(value).strip()
    if val_str.lower() in ("nan", "n/a", "none", ""):
        return ""
    return val_str


def extract_section_number(section_str):
    """Extract precise section number/alphanumeric identifier from string."""
    if not section_str:
        return ""
    # Remove prefix text like "Section", "Sec.", "DPA"
    cleaned = re.sub(r"^(section|sec\.?|dpa)\s*", "", str(section_str), flags=re.IGNORECASE).strip()
    # Match standard alphanumeric section formats (e.g., 3, 4A, 8B)
    match = re.search(r"(\d+[A-Za-z]*)", cleaned)
    return match.group(1) if match else cleaned


# ── Neo4j Operations ──────────────────────────────────────────────────────────

def wipe_dpa_data(driver):
    """Wipe all existing DPA sections and Act nodes from Neo4j to ensure clean state."""
    print("\n[WIPE] Deleting all existing DPA LawSection and Act nodes...")
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (s:LawSection {act: 'DPA'})
            DETACH DELETE s
            RETURN count(s) as deleted_sections
        """)
        sec_deleted = result.single()["deleted_sections"]
        
        result_act = session.run("""
            MATCH (a:Act {name: 'DPA'})
            DETACH DELETE a
            RETURN count(a) as deleted_acts
        """)
        act_deleted = result_act.single()["deleted_acts"]
        
        print(f"[WIPE] Successfully deleted {sec_deleted} DPA section nodes and {act_deleted} Act nodes.")


def create_constraints_and_indexes(driver):
    """Create necessary constraints and indexes for high-performance lookups."""
    print("\n[SCHEMA] Verifying/Creating constraints and indexes...")
    
    with driver.session(database=NEO4J_DATABASE) as session:
        try:
            session.run("""
                CREATE CONSTRAINT law_section_act_section IF NOT EXISTS
                FOR (s:LawSection) REQUIRE (s.act, s.section) IS UNIQUE
            """)
            print("  ✓ Ensured unique constraint on (act, section)")
        except Exception as e:
            print(f"  ⚠ Constraint notice: {e}")
        
        try:
            session.run("""
                CREATE INDEX law_section_act IF NOT EXISTS
                FOR (s:LawSection) ON (s.act)
            """)
            print("  ✓ Ensured index on act")
        except Exception as e:
            print(f"  ⚠ Index notice: {e}")


def create_dpa_act_node(driver):
    """Create or merge the parent DPA Act node."""
    print("\n[ACT] Creating/Updating DPA Act node...")
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run("""
            MERGE (a:Act {name: 'DPA'})
            SET a.full_name = 'Dowry Prohibition Act, 1961',
                a.year = 1961,
                a.status = 'Active',
                a.description = 'An Act to prohibit the giving or taking of dowry'
        """)
    print("[ACT] DPA Act node configured successfully.")


def ingest_dpa_sections(driver, csv_path):
    """Ingest sanitized DPA sections from CSV with high accuracy filters."""
    if not csv_path.exists():
        print(f"[ERROR] CSV file not found: {csv_path}")
        return
    
    print(f"\n[INGEST] Reading and validating DPA sections from {csv_path}...")
    all_rows = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_sec = clean(row.get("Section", ""))
            extracted_sec = extract_section_number(raw_sec)
            
            if extracted_sec:
                all_rows.append({
                    'section': extracted_sec,
                    'title': clean(row.get("Title", "")),
                    'description': clean(row.get("Description", "")),
                    'punishment': clean(row.get("Punishment", "")),
                    'chapter': clean(row.get("Chapter", "")),
                    'chapter_title': clean(row.get("Chapter_Title", "")),
                    'sub_sections': clean(row.get("Sub_Sections", ""))
                })
    
    # Deduplicate/Filter: choose row with the richest description for each section number
    sections_dict = {}
    for row in all_rows:
        sec_num = row['section']
        desc_len = len(row['description'])
        
        if sec_num not in sections_dict or desc_len > len(sections_dict[sec_num]['description']):
            sections_dict[sec_num] = row
    
    sections = list(sections_dict.values())
    
    # Sort section numbers cleanly (handles numeric and alphanumeric sorts like 3, 4, 4A, etc.)
    def sort_key(x):
        num_part = int(''.join(filter(str.isdigit, x['section'])) or 0)
        alpha_part = ''.join(filter(str.isalpha, x['section']))
        return (num_part, alpha_part)

    sections.sort(key=sort_key)
    
    print(f"[INGEST] Processed {len(sections)} unique, high-accuracy DPA sections for ingestion.")
    
    # Perform transaction batch execution
    with driver.session(database=NEO4J_DATABASE) as session:
        for sec in sections:
            session.run("""
                MERGE (s:LawSection {act: 'DPA', section: $section})
                SET s.title = $title,
                    s.description = $description,
                    s.punishment = $punishment,
                    s.chapter = $chapter,
                    s.chapter_title = $chapter_title,
                    s.sub_sections = $sub_sections,
                    s.status = 'Active',
                    s.type = 'substantive'
                
                WITH s
                MATCH (a:Act {name: 'DPA'})
                MERGE (s)-[:PART_OF]->(a)
                MERGE (a)-[:HAS_SECTION]->(s)
            """, **sec)
            
            print(f"  ✓ Ingested DPA Section {sec['section']}: {sec['title'][:55]}...")
    
    print(f"\n[SUCCESS] Successfully committed {len(sections)} DPA sections into Neo4j.")


def verify_ingestion(driver):
    """Run diagnostics to verify accurate ingestion results."""
    print("\n[VERIFY] Running post-ingestion verification...")
    
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (s:LawSection {act: 'DPA'})
            RETURN count(s) as total
        """)
        total = result.single()["total"]
        print(f"  • Total verified DPA sections in graph: {total}")
        
        result = session.run("""
            MATCH (s:LawSection {act: 'DPA'})
            RETURN s.section as section, s.title as title
            ORDER BY s.section
            LIMIT 5
        """)
        print("  • Sample ingested records:")
        for record in result:
            print(f"    - DPA Section {record['section']}: {record['title'][:55]}...")
        
        result = session.run("""
            MATCH (s:LawSection {act: 'DPA'})-[:PART_OF]->(a:Act {name: 'DPA'})
            RETURN count(s) as connected
        """)
        connected = result.single()["connected"]
        print(f"  • Sections correctly linked to Act node: {connected}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Force wipe existing nodes by default to guarantee high accuracy/no stale duplicates, 
    # while retaining support for explicit command-line flags.
    wipe = True if "--no-wipe" not in sys.argv else False
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        print("=" * 80)
        print("DPA (DOWRY PROHIBITION ACT) HIGH-ACCURACY INGESTION PIPELINE")
        print("=" * 80)
        
        if wipe:
            wipe_dpa_data(driver)
        
        create_constraints_and_indexes(driver)
        create_dpa_act_node(driver)
        ingest_dpa_sections(driver, DPA_CSV)
        verify_ingestion(driver)
        
        print("\n" + "=" * 80)
        print("✓ DPA INGESTION PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
    finally:
        driver.close()


if __name__ == "__main__":
    main()