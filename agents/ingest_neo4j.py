"""
Sprint 1 – Legal Data Ingestion
Reads data/ipc_sections.csv and loads it into Neo4j AuraDB.

CSV columns expected:
    Description, Offense, Punishment, Section

Each row becomes:
    (:Crime {name}) -[:DEFINED_BY]-> (:IPC {section, description, punishment, offense})

Run from the project root:
    python agents/ingest_neo4j.py
"""

import csv
import re
from pathlib import Path
from neo4j_connection import get_driver, DATABASE, verify_connection

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH     = PROJECT_ROOT / "data" / "ipc_sections.csv"

# ── Cypher ────────────────────────────────────────────────────────────────────
MERGE_QUERY = """
MERGE (c:Crime {name: $crime_type})
MERGE (l:IPC {section: $section})
  ON CREATE SET l.description = $description,
                l.punishment  = $punishment,
                l.offense     = $offense
  ON MATCH  SET l.description = $description,
                l.punishment  = $punishment,
                l.offense     = $offense
MERGE (c)-[:DEFINED_BY]->(l)
"""


def _derive_crime_type(offense: str, section: str) -> str:
    """
    Derives a broad crime-type label from the offense description.
    Falls back to the raw section string if the offense is empty.
    """
    if not offense:
        return section or "Unknown"

    offense_lower = offense.lower()

    # Simple keyword → category mapping (extend as needed)
    mappings = [
        (["murder", "culpable homicide", "death"],              "Homicide"),
        (["theft", "stolen", "steal"],                          "Theft"),
        (["rape", "sexual assault", "outraging modesty"],       "Sexual Offence"),
        (["fraud", "cheating", "forgery", "deceiv"],            "Fraud"),
        (["assault", "hurt", "grievous"],                       "Assault"),
        (["kidnap", "abduct"],                                   "Kidnapping"),
        (["robbery", "dacoity"],                                 "Robbery"),
        (["bribe", "corruption", "public servant"],             "Corruption"),
        (["trespass", "house-breaking", "house breaking"],      "Trespass"),
        (["defamation", "slander", "libel"],                    "Defamation"),
        (["sedition", "rebellion", "war against"],              "Sedition"),
        (["drug", "narcotic", "intoxicant"],                    "Drug Offence"),
        (["arson", "fire"],                                      "Arson"),
        (["extortion", "blackmail"],                            "Extortion"),
        (["counterfeit", "currency", "coin"],                   "Counterfeiting"),
    ]

    for keywords, category in mappings:
        if any(kw in offense_lower for kw in keywords):
            return category

    # Last resort: use the first 4 words of the offense as a label
    words = re.sub(r"[^a-zA-Z ]", " ", offense).split()
    return " ".join(words[:4]).title() if words else (section or "Unknown")


def ingest(csv_path: Path = CSV_PATH) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    if not verify_connection():
        raise RuntimeError("Cannot connect to Neo4j — check your .env credentials.")

    rows_ok      = 0
    rows_skipped = 0

    with get_driver() as driver:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                section     = (row.get("Section")     or "").strip()
                description = (row.get("Description") or "").strip()
                punishment  = (row.get("Punishment")  or "").strip()
                offense     = (row.get("Offense")     or "").strip()

                if not section:
                    rows_skipped += 1
                    continue

                crime_type = _derive_crime_type(offense, section)

                _, summary, _ = driver.execute_query(
                    MERGE_QUERY,
                    crime_type=crime_type,
                    section=section,
                    description=description,
                    punishment=punishment,
                    offense=offense,
                    database_=DATABASE,
                )
                rows_ok += 1

                if rows_ok % 50 == 0:
                    print(f"  … {rows_ok} sections ingested so far")

    print(
        f"\n[Ingest] Done — {rows_ok} IPC sections loaded, "
        f"{rows_skipped} rows skipped (missing section number)."
    )


# ── Verify ingestion ──────────────────────────────────────────────────────────
def verify_ingestion(limit: int = 10) -> None:
    """Runs a quick MATCH to confirm data is present in Neo4j."""
    from neo4j_connection import execute_query

    records, summary, _ = execute_query(
        "MATCH (n:IPC) RETURN n.section AS section, n.offense AS offense LIMIT $limit",
        {"limit": limit},
    )

    print(f"\n[Verify] First {limit} IPC nodes in the database:")
    for r in records:
        print(f"  {r['section']:12s}  {r['offense'][:70]}")

    print(
        f"\nQuery returned {len(records)} record(s) "
        f"in {summary.result_available_after} ms."
    )


if __name__ == "__main__":
    ingest()
    verify_ingestion()
