import os
import json
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# ==========================
# Paths & Environment
# ==========================

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

JSON_DIR = BASE_DIR.parent.parent / "data" / "json"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


def ingest_case(case):

    citation = case["metadata"]["citation"]

    with driver.session() as session:

        # ============================================================
        # CASE
        # ============================================================

        session.run(
            """
            MERGE (c:Case {citation:$citation})

            SET
                c.case_name = $case_name,
                c.court = $court,
                c.date = $date,
                c.judge = $judge,
                c.outcome = $outcome,
                c.decision_summary = $summary
            """,
            citation=citation,
            case_name=case["metadata"]["case_name"],
            court=case["metadata"]["court"],
            date=case["metadata"]["date"],
            judge=case["metadata"]["judge"],
            outcome=case["decision"]["outcome"],
            summary=case["decision"]["summary"]
        )

        # ============================================================
        # IPC / BNS Sections
        # ============================================================

        for section in case["ipc_bns_sections"]:
            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MATCH (l:LawSection {
                    act:$act,
                    section:$section
                })

                MERGE (c)-[:APPLIES_SECTION]->(l)
                """,

                citation=citation,
                act=section["act"],
                section=section["section"]
            )

        # ============================================================
        # Facts
        # ============================================================

        for fact in case["facts"]:

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (f:Fact {id:$id})

                SET
                    f.text=$text

                MERGE (c)-[:HAS_FACT]->(f)
                """,
                citation=citation,
                id=f"{citation}_{fact['id']}",
                text=fact["text"]
            )

        # ============================================================
        # Issues
        # ============================================================

        for issue in case["issues"]:

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (i:Issue {id:$id})

                SET
                    i.text=$text

                MERGE (c)-[:HAS_ISSUE]->(i)
                """,
                citation=citation,
                id=f"{citation}_{issue['id']}",
                text=issue["text"]
            )

        # ============================================================
        # Prosecution Arguments
        # ============================================================

        for arg in case["prosecution_arguments"]:

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (a:Argument {id:$id})

                SET
                    a.side="Prosecution",
                    a.text=$text

                MERGE (c)-[:HAS_ARGUMENT]->(a)
                """,
                citation=citation,
                id=f"{citation}_{arg['id']}",
                text=arg["text"]
            )

        # ============================================================
        # Defense Arguments
        # ============================================================

        for arg in case["defense_arguments"]:

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (a:Argument {id:$id})

                SET
                    a.side="Defense",
                    a.text=$text

                MERGE (c)-[:HAS_ARGUMENT]->(a)
                """,
                citation=citation,
                id=f"{citation}_{arg['id']}",
                text=arg["text"]
            )

        # ============================================================
        # Judge Reasoning
        # ============================================================

        for reason in case["judge_reasoning"]:

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (r:Reasoning {id:$id})

                SET
                    r.text=$text

                MERGE (c)-[:HAS_REASONING]->(r)
                """,
                citation=citation,
                id=f"{citation}_{reason['id']}",
                text=reason["text"]
            )

        # ============================================================
        # Legal Principles
        # ============================================================

        for principle in case["legal_principles"]:

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (p:LegalPrinciple {id:$id})

                SET
                    p.text=$text

                MERGE (c)-[:ESTABLISHES]->(p)
                """,
                citation=citation,
                id=f"{citation}_{principle['id']}",
                text=principle["text"]
            )


def main():

    for json_file in JSON_DIR.glob("*.json"):

        print(f"Processing {json_file.name}")

        with open(json_file, "r", encoding="utf-8") as f:
            case = json.load(f)

        ingest_case(case)

    driver.close()
    print("✅ All cases ingested successfully.")


if __name__ == "__main__":
    main()