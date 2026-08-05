import json
import os
import re
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

# Updated path to point to your new directory
JSON_DIR = BASE_DIR.parent.parent / "backend" / "bail_cases"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


def clear_existing_cases():
    """Delete ALL existing Case nodes and related nodes before ingesting new ones.
    This must run before any file is processed so we start from a clean graph
    that matches the corrected schema below."""
    with driver.session() as session:
        print("\n🗑️  Clearing existing Case nodes and related data...")

        # Delete Case nodes and their relationships
        result = session.run("""
            MATCH (c:Case)
            OPTIONAL MATCH (c)-[r]-()
            DELETE r, c
            RETURN count(c) AS deleted_cases
        """)
        deleted = result.single()["deleted_cases"]
        print(f"   ✓ Deleted {deleted} Case nodes")

        # Delete orphaned Headnote nodes
        result = session.run("""
            MATCH (h:Headnote)
            WHERE NOT (h)<-[:HAS_HEADNOTE]-()
            DELETE h
            RETURN count(h) AS deleted
        """)
        deleted = result.single()["deleted"]
        print(f"   ✓ Deleted {deleted} orphaned Headnote nodes")

        # Delete orphaned Paragraph nodes
        result = session.run("""
            MATCH (p:Paragraph)
            WHERE NOT (p)<-[:HAS_PARAGRAPH]-()
            DELETE p
            RETURN count(p) AS deleted
        """)
        deleted = result.single()["deleted"]
        print(f"   ✓ Deleted {deleted} orphaned Paragraph nodes")

        # Delete orphaned BailCondition nodes
        result = session.run("""
            MATCH (bc:BailCondition)
            WHERE NOT (bc)<-[:HAS_BAIL_CONDITION]-()
            DELETE bc
            RETURN count(bc) AS deleted
        """)
        deleted = result.single()["deleted"]
        print(f"   ✓ Deleted {deleted} orphaned BailCondition nodes")

        # Delete orphaned StatutorySection nodes
        result = session.run("""
            MATCH (s:StatutorySection)
            WHERE NOT (s)<-[:APPLIES_SECTION]-()
            DELETE s
            RETURN count(s) AS deleted
        """)
        deleted = result.single()["deleted"]
        print(f"   ✓ Deleted {deleted} orphaned StatutorySection nodes")

        print("   ✅ Cleanup complete!\n")


def _derive_facts(case):
    """Best-effort derivation of a 'facts' narrative field, since the source
    JSON has no dedicated facts field. Falls back through numbered_paragraphs
    -> headnote_raw -> empty string."""
    if case.get("facts"):
        return case.get("facts")

    numbered_paragraphs = case.get("numbered_paragraphs", [])
    if numbered_paragraphs:
        first_few = numbered_paragraphs[:3]
        texts = [p.get("text", "") for p in first_few if p.get("text")]
        if texts:
            return "\n\n".join(texts)

    return case.get("headnote_raw", "")


def _derive_summary(case):
    """Best-effort derivation of a short 'summary' field: prefer dispute_nature,
    else the first headnote point's text."""
    if case.get("dispute_nature"):
        return case.get("dispute_nature")

    headnote_points = case.get("headnote_points", [])
    if headnote_points:
        return headnote_points[0].get("text", "")

    return ""


def _derive_holding(case):
    """No distinct 'holding' field exists in the source JSON; ratio_decidendi
    is the closest equivalent."""
    return case.get("ratio_decidendi", "")


def _link_sections(session, citation, case):
    """Link this Case to the REAL, pre-existing LawSection corpus (the
    BNSSection/CrPCSection/IPCSection/etc. nodes that already carry
    act + section properties, e.g. {act:"BNS", section:"74"}).

    Uses act_sections[] from the source JSON, which -- unlike referred_acts --
    actually tells us which act each section belongs to (act_short_name) and
    whether it was charged/applied/interpreted in this case. We MATCH onto
    existing nodes only; we never MERGE-create new section nodes here, since
    doing so previously produced orphan StatutorySection nodes disconnected
    from the real corpus.

    Per-case facts (is_charged, is_applied, how_used, context) are stored as
    relationship properties on APPLIES_SECTION, since the LawSection node
    itself is shared across many cases and shouldn't carry case-specific state.
    """
    act_sections = case.get("act_sections", [])
    matched = 0
    unmatched = []

    for entry in act_sections:
        act_short = (entry.get("act_short_name") or "").strip()
        section_raw = (entry.get("section") or "").strip()
        if not act_short or not section_raw:
            continue

        # Strip a trailing subsection parenthetical, e.g. "438(2)" -> "438",
        # since the corpus generally stores base section numbers.
        section_base = re.sub(r"\(.*\)$", "", section_raw).strip()

        rel_props = dict(
            how_used=entry.get("how_used", ""),
            is_charged=bool(entry.get("is_charged", False)),
            is_convicted=bool(entry.get("is_convicted", False)),
            is_applied=bool(entry.get("is_applied", False)),
            is_interpreted=bool(entry.get("is_interpreted", False)),
            context=entry.get("context", "") or "",
        )

        # Try base section first (covers the common case), then fall back
        # to the raw section string (in case the corpus does store "438(2)"
        # as its own node).
        linked = False
        for candidate_section in dict.fromkeys([section_base, section_raw]):
            result = session.run(
                """
                MATCH (s:LawSection {act: $act, section: $section})
                WITH s LIMIT 1
                MATCH (c:Case {citation: $citation})
                MERGE (c)-[r:APPLIES_SECTION]->(s)
                SET r += $rel_props
                RETURN s
                """,
                act=act_short,
                section=candidate_section,
                citation=citation,
                rel_props=rel_props,
            )
            if result.single():
                linked = True
                break

        if linked:
            matched += 1
        else:
            unmatched.append(f"{act_short} {section_raw}")

    if unmatched:
        print(f"   ⚠️  No matching LawSection found for: {', '.join(unmatched)}")

    return matched


def ingest_case(case):
    """
    Ingests a bail case from TheLawsSuperOnline JSON format into Neo4j.
    Handles the actual structure: case_citation, court, coram, decided_on, etc.

    NOTE: In addition to the original field names, this now also sets
    year / outcome / summary / facts / holding aliases so that retrieval
    queries expecting those generic names return real data instead of null.
    """

    citation = case.get("case_citation", "")
    if not citation:
        raise ValueError("Missing 'case_citation' field in case data.")

    decided_on_year = case.get("decided_on_year", None)
    bail_outcome = case.get("bail_outcome", "")
    summary = _derive_summary(case)
    facts = _derive_facts(case)
    holding = _derive_holding(case)

    with driver.session() as session:

        # ============================================================
        # CASE NODE
        # ============================================================
        case_name = f"{case.get('appellant', '')} vs {case.get('respondent', '')}"

        session.run(
            """
            MERGE (c:Case {citation:$citation})

            SET
                c.case_name = $case_name,
                c.court = $court,
                c.date = $date,
                c.decided_on_year = $year,
                c.coram = $coram,
                c.judges = $judges,
                c.appeal_type = $appeal_type,
                c.final_verdict = $final_verdict,
                c.appellant = $appellant,
                c.respondent = $respondent,
                c.advocates = $advocates,
                c.equivalent_citations = $equivalent_citations,
                c.headnote_raw = $headnote,
                c.ratio_decidendi = $ratio,
                c.ratio_para_number = $ratio_para,
                c.dispute_nature = $dispute_nature,
                c.bail_outcome = $bail_outcome,
                c.bail_amount_original = $bail_original,
                c.bail_amount_modified = $bail_modified,
                c.source_file = $source_file,

                // --- aliases for retrieval-query compatibility ---
                c.year = $year,
                c.outcome = $bail_outcome,
                c.summary = $summary,
                c.facts = $facts,
                c.holding = $holding
            """,
            citation=citation,
            case_name=case_name,
            court=case.get("court", ""),
            date=case.get("decided_on", ""),
            year=decided_on_year,
            coram=case.get("coram", ""),
            judges=case.get("judgment_author", ""),
            appeal_type=case.get("appeal_type", ""),
            final_verdict=case.get("final_verdict", ""),
            appellant=case.get("appellant", ""),
            respondent=case.get("respondent", ""),
            advocates=case.get("advocates", ""),
            equivalent_citations=case.get("equivalent_citations", []),
            headnote=case.get("headnote_raw", ""),
            ratio=case.get("ratio_decidendi", ""),
            ratio_para=case.get("ratio_para_number", ""),
            dispute_nature=case.get("dispute_nature", ""),
            bail_outcome=bail_outcome,
            bail_original=case.get("bail_amount_original_normalized", ""),
            bail_modified=case.get("bail_amount_modified_normalized", ""),
            source_file=case.get("source_file", ""),
            summary=summary,
            facts=facts,
            holding=holding
        )

        # ============================================================
        # SECTIONS (BNS/IPC/CrPC/BNSS/BSA etc.)
        # ============================================================
        # Uses act_sections[] (has act_short_name + section + charge status),
        # matched against the REAL pre-existing LawSection corpus. This
        # replaces the old referred_acts-based approach, which had no act
        # name to work with and hardcoded "CrPC", producing orphan nodes
        # that never matched the actual retrieval-query corpus.
        matched_count = _link_sections(session, citation, case)
        if matched_count == 0 and case.get("act_sections"):
            print(f"   ⚠️  {citation}: 0 of {len(case['act_sections'])} act_sections matched to existing LawSection nodes")

        # ============================================================
        # CITED JUDGMENTS (Precedents)
        # ============================================================
        cited_judgments = case.get("cited_judgments", [])
        for cited in cited_judgments[:10]:  # Limit to top 10 to avoid overwhelming
            try:
                parts = cited.split(",", 1)
                if len(parts) >= 2:
                    cited_case_name = parts[0].strip()
                    citation_part = parts[1].strip()

                    citation_match = re.search(r'\[(LAWS\([^\]]+\))\]', citation_part)
                    cited_citation = citation_match.group(1) if citation_match else citation_part

                    session.run(
                        """
                        MATCH (c:Case {citation:$citation})

                        MERGE (cited:Case {citation:$cited_citation})
                        SET cited.case_name = $cited_case_name

                        MERGE (c)-[:CITES]->(cited)
                        """,
                        citation=citation,
                        cited_citation=cited_citation,
                        cited_case_name=cited_case_name
                    )
            except Exception:
                # Skip malformed citations
                continue

        # ============================================================
        # HEADNOTE POINTS (Key Holdings)
        # ============================================================
        headnote_points = case.get("headnote_points", [])
        for idx, point in enumerate(headnote_points):
            label = point.get("label", "")
            text = point.get("text", "")

            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (h:Headnote {id:$id})
                SET h.label = $label,
                    h.text = $text,
                    h.order = $order

                MERGE (c)-[:HAS_HEADNOTE]->(h)
                """,
                citation=citation,
                id=f"{citation}_headnote_{idx}",
                label=label,
                text=text,
                order=idx
            )

        # ============================================================
        # NUMBERED PARAGRAPHS (Judgment Text)
        # ============================================================
        numbered_paragraphs = case.get("numbered_paragraphs", [])
        for para in numbered_paragraphs:
            para_num = para.get("number", "")
            para_text = para.get("text", "")

            if para_num and para_text:
                session.run(
                    """
                    MATCH (c:Case {citation:$citation})

                    MERGE (p:Paragraph {id:$id})
                    SET p.number = $number,
                        p.text = $text

                    MERGE (c)-[:HAS_PARAGRAPH]->(p)
                    """,
                    citation=citation,
                    id=f"{citation}_para_{para_num}",
                    number=para_num,
                    text=para_text
                )

        # ============================================================
        # BAIL CONDITIONS
        # ============================================================
        bail_conditions = case.get("bail_conditions", [])
        for idx, condition in enumerate(bail_conditions):
            session.run(
                """
                MATCH (c:Case {citation:$citation})

                MERGE (bc:BailCondition {id:$id})
                SET bc.text = $text,
                    bc.order = $order

                MERGE (c)-[:HAS_BAIL_CONDITION]->(bc)
                """,
                citation=citation,
                id=f"{citation}_bail_cond_{idx}",
                text=condition,
                order=idx
            )


def main():
    if not JSON_DIR.exists():
        print(f"❌ Error: Directory does not exist -> {JSON_DIR}")
        return

    json_files = list(JSON_DIR.glob("*.json"))
    if not json_files:
        print(f"⚠️ No JSON files found in {JSON_DIR}")
        return

    print("=" * 60)
    print("REPLACING ALL CASE NODES WITH BAIL CASES (schema-aligned)")
    print("=" * 60)

    # Clear existing cases first, before any new file is processed
    clear_existing_cases()

    successful = 0
    failed = 0

    print(f"🔍 Found {len(json_files)} file(s) to process...\n")

    for json_file in json_files:
        print(f"Processing: {json_file.name}")

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                case = json.load(f)

            ingest_case(case)
            successful += 1
            print(f"  └─ ✅ Successfully ingested {json_file.name}")

        except json.JSONDecodeError:
            failed += 1
            print(f"  └─ ❌ Error: Skipping invalid JSON format in {json_file.name}")
        except Exception as e:
            failed += 1
            print(f"  └─ ❌ Error processing {json_file.name}: {e}")

    driver.close()

    print("\n" + "=" * 60)
    print(f"🎉 Batch run completed.")
    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()