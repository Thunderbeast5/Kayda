from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
from pathlib import Path
from typing import Any

# =========================
# Paths and env
# =========================
BASE_DIR = Path(__file__).resolve().parent

env_candidates = [
    BASE_DIR.parent / ".env",
    BASE_DIR.parent.parent / ".env",
    BASE_DIR / ".env",
    Path(".env"),
]
ENV_PATH = None
for c in env_candidates:
    if c.exists():
        ENV_PATH = c
        break

try:
    from dotenv import load_dotenv

    if ENV_PATH:
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()
except ImportError:
    pass

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

BATCH_SIZE = 500

csv_dir_candidates = [
    BASE_DIR.parent.parent.parent / "data" / "cleaned",
    BASE_DIR.parent.parent / "data" / "cleaned",
    BASE_DIR.parent / "data" / "cleaned",
    BASE_DIR / "data" / "cleaned",
    Path("data/cleaned"),
    Path("."),
]
DEFAULT_CSV_DIR = next((p for p in csv_dir_candidates if p.exists() and p.is_dir()), Path("."))

IPC_CSV = "ipc.csv"
BNS_CSV = "bns_sections_clean.csv"
MAP_CSV = "ipc2bns.csv"

# canonical mapping statuses used by text2cypher schema/prompt
STATUS_DELETED_NO_BNS = "deleted_no_bns_successor"
STATUS_NEW_NO_IPC = "new_no_ipc_predecessor"
STATUS_ACTIVE = "active_mapping"

# punishment boilerplate that causes hub pollution
PUNISHMENT_STOP_TEXTS = {
    "",
    "see description",
    "refer description",
    "as per description",
    "same as above",
    "as above",
    "refer above",
    "see above",
    "as described above",
    "same punishment",
}


# =========================
# Utilities
# =========================
def clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().strip('"').strip()
    if s.lower() in {"", "nan", "none", "n/a", "null"}:
        return ""
    return re.sub(r"\s+", " ", s)


def stable_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARNING: Missing file: {path}")
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def batched(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def parse_chapter(raw: str) -> tuple[str, str]:
    raw = clean(raw)
    m = re.match(r"Chapter\s+([IVXLCDM]+)\s*:\s*(.+)", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper(), clean(m.group(2))
    return "", raw


def extract_ipc_section(url: str, section_cell: str = "") -> str | None:
    m = re.search(r"section-(\d+[A-Za-z]*)", str(url), flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.match(r"\s*(\d+[A-Za-z]*)\s*$", str(section_cell))
    return m2.group(1) if m2 else None


def extract_leading_int(s: str) -> int | None:
    m = re.match(r"\s*(\d+)", str(s))
    return int(m.group(1)) if m else None


def parse_bns_targets(raw_target: str) -> list[str]:
    """
    Parse mapping targets robustly.

    Examples:
      "103(1)" -> ["103"]
      "2(19) & 2(35)" -> ["2"]
      "309(2), 310(1)" -> ["309", "310"]
      "5 (EXPL.)" -> ["5"]
      "REMOVED"/"DELETED"/"REPEALED"/"N/A" -> []
    """
    t = clean(raw_target)
    u = t.upper()
    if u in {"", "REMOVED", "DELETED", "REPEALED", "N/A", "NA"}:
        return []

    parts = re.split(r"\s*(?:&|,|;|\band\b)\s*", t, flags=re.IGNORECASE)

    out = []
    seen = set()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^\s*(\d+)", part)
        if not m:
            continue
        sec = m.group(1)
        if sec not in seen:
            seen.add(sec)
            out.append(sec)
    return out


def split_keywords(s: str) -> list[str]:
    if not s:
        return []
    parts = re.split(r"[,\|;/]+", s)
    out = []
    seen = set()
    for p in parts:
        k = clean(p).lower()
        if not k:
            continue
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def normalize_punishment_text(txt: str) -> str:
    t = clean(txt).lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_low_signal_punishment(txt: str) -> bool:
    t = normalize_punishment_text(txt)
    if not t:
        return True
    if t in PUNISHMENT_STOP_TEXTS:
        return True
    # extra guard against common "see/ref description ..." variants
    if re.fullmatch(r"(see|refer)\s+(the\s+)?description", t):
        return True
    return False


# =========================
# Loaders
# =========================
def load_ipc(csv_dir: Path) -> dict[str, dict]:
    rows = read_csv(csv_dir / IPC_CSV)
    ipc: dict[str, dict] = {}
    dupes = 0

    for r in rows:
        sec = extract_ipc_section(r.get("URL", ""), r.get("Section", ""))
        if not sec:
            continue

        title = clean(r.get("Offense"))
        desc = clean(r.get("Legal_Description")) or clean(r.get("Simple_Words"))
        punishment = clean(r.get("Punishment"))

        payload = {
            "act": "IPC",
            "section": sec,
            "title": title,
            "description": desc,
            "punishment": punishment,
            "cognizable": clean(r.get("Cognizable")),
            "bailable": clean(r.get("Bailable")),
            "court": clean(r.get("Court")),
            "source_url": clean(r.get("URL")),
            "data_complete": bool(title or desc or punishment),
        }

        if sec in ipc:
            dupes += 1
            old = ipc[sec]
            for k in ["title", "description", "punishment", "cognizable", "bailable", "court", "source_url"]:
                if not old.get(k) and payload.get(k):
                    old[k] = payload[k]
            old["data_complete"] = old["data_complete"] or payload["data_complete"]
        else:
            ipc[sec] = payload

    for _, row in ipc.items():
        if not row["title"] and row["description"]:
            row["title"] = row["description"][:100]

    print(f"IPC loaded: {len(rows)} rows -> {len(ipc)} unique sections ({dupes} merged duplicates)")
    return ipc


def load_bns(csv_dir: Path) -> dict[str, dict]:
    rows = read_csv(csv_dir / BNS_CSV)
    bns: dict[str, dict] = {}

    for r in rows:
        sec_raw = clean(r.get("Section"))
        if not sec_raw:
            continue

        sec_i = extract_leading_int(sec_raw)
        if sec_i is None:
            continue
        sec = str(sec_i)

        ch_raw = clean(r.get("Chapter"))
        ch_num, ch_title = parse_chapter(ch_raw) if ch_raw else ("", "")

        bns[sec] = {
            "act": "BNS",
            "section": sec,
            "title": clean(r.get("Title")),
            "description": clean(r.get("Description")),
            "punishment": clean(r.get("Punishment")),
            "category": clean(r.get("Category")),
            "keywords": clean(r.get("Keywords")),
            "chapter_raw": ch_raw,
            "chapter_number": ch_num,
            "chapter_title": ch_title,
            "data_complete": True,
        }

    print(f"BNS loaded: {len(rows)} rows -> {len(bns)} unique sections")
    return bns


def load_mapping(csv_dir: Path, ipc: dict[str, dict], bns: dict[str, dict]) -> list[dict]:
    rows = read_csv(csv_dir / MAP_CSV)
    mappings: list[dict] = []
    stub_ipc = 0

    for r in rows:
        ipc_sec_raw = clean(r.get("IPC_Section"))
        ipc_sec = re.match(r"^\d+[A-Za-z]*$", ipc_sec_raw).group(0) if re.match(r"^\d+[A-Za-z]*$", ipc_sec_raw) else None
        ipc_title = clean(r.get("IPC_Title"))
        bns_target_raw = clean(r.get("BNS_Section"))
        bns_title = clean(r.get("BNS_Title"))
        note = clean(r.get("Notes"))

        if ipc_sec and ipc_sec not in ipc:
            ipc[ipc_sec] = {
                "act": "IPC",
                "section": ipc_sec,
                "title": ipc_title,
                "description": "",
                "punishment": "",
                "cognizable": "",
                "bailable": "",
                "court": "",
                "source_url": "",
                "data_complete": False,
            }
            stub_ipc += 1

        bns_targets = parse_bns_targets(bns_target_raw)
        bns_targets = [s for s in bns_targets if s in bns]

        mappings.append(
            {
                "ipc_section": ipc_sec,
                "ipc_title_hint": ipc_title,
                "bns_targets": bns_targets,
                "bns_raw": bns_target_raw,
                "bns_title_hint": bns_title,
                "note": note,
            }
        )

    print(f"Mapping loaded: {len(rows)} rows -> {len(mappings)} entries ({stub_ipc} IPC stubs added)")
    return mappings


# =========================
# Neo4j
# =========================
def get_driver():
    from neo4j import GraphDatabase

    if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
        raise ValueError(
            "Missing Neo4j credentials. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD "
            f"(looked via {ENV_PATH})."
        )
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def wipe_graph(driver):
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    print("Graph wiped.")


def create_constraints(driver):
    stmts = [
        "CREATE CONSTRAINT act_code IF NOT EXISTS FOR (a:Act) REQUIRE a.code IS UNIQUE",
        "CREATE CONSTRAINT lawsection_id IF NOT EXISTS FOR (l:LawSection) REQUIRE l.id IS UNIQUE",
        "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT crime_id IF NOT EXISTS FOR (c:Crime) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT punish_id IF NOT EXISTS FOR (p:Punishment) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT keyword_id IF NOT EXISTS FOR (k:Keyword) REQUIRE k.id IS UNIQUE",
        "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:LegalRule) REQUIRE r.id IS UNIQUE",
    ]
    with driver.session() as s:
        for q in stmts:
            s.run(q)
    print("Constraints ensured.")


def create_fulltext_indexes(driver):
    stmts = [
        """
        CREATE FULLTEXT INDEX lawSectionText IF NOT EXISTS
        FOR (l:LawSection) ON EACH [l.title, l.description, l.punishment, l.keywords]
        """,
        """
        CREATE FULLTEXT INDEX crimeName IF NOT EXISTS
        FOR (c:Crime) ON EACH [c.name]
        """,
    ]
    with driver.session() as s:
        for q in stmts:
            s.run(q)
    print("Full-text indexes ensured: lawSectionText, crimeName")


def ingest_acts(driver):
    rows = [
        {"code": "IPC", "name": "Indian Penal Code"},
        {"code": "BNS", "name": "Bharatiya Nyaya Sanhita, 2023"},
    ]
    with driver.session() as s:
        s.run(
            """
        UNWIND $rows AS row
        MERGE (a:Act {code: row.code})
        SET a.name = row.name
        """,
            rows=rows,
        )
    print("Act nodes ensured.")


def ingest_chapters(driver, bns: dict[str, dict]) -> int:
    chapters = {}
    for r in bns.values():
        if not r["chapter_raw"]:
            continue
        cid = stable_id("BNS", r["chapter_raw"])
        chapters[cid] = {
            "id": cid,
            "act": "BNS",
            "raw": r["chapter_raw"],
            "number": r["chapter_number"],
            "title": r["chapter_title"],
        }

    payload = list(chapters.values())
    with driver.session() as s:
        for batch in batched(payload, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (c:Chapter {id: row.id})
            SET c.act = row.act, c.raw = row.raw, c.number = row.number, c.title = row.title
            WITH c, row
            MATCH (a:Act {code: row.act})
            MERGE (a)-[:HAS_CHAPTER]->(c)
            """,
                rows=batch,
            )

    print(f"Chapter nodes ensured: {len(payload)}")
    return len(payload)


def ingest_sections(driver, ipc: dict[str, dict], bns: dict[str, dict]):
    ipc_rows = [{"id": f"IPC_{r['section']}", **r} for r in ipc.values()]
    bns_rows = [
        {
            "id": f"BNS_{r['section']}",
            **r,
            "chapter_id": stable_id("BNS", r["chapter_raw"]) if r["chapter_raw"] else None,
        }
        for r in bns.values()
    ]

    with driver.session() as s:
        for batch in batched(ipc_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (l:LawSection {id: row.id})
            SET l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.punishment = row.punishment,
                l.cognizable = row.cognizable,
                l.bailable = row.bailable,
                l.court = row.court,
                l.source_url = row.source_url,
                l.data_complete = row.data_complete
            WITH l, row
            MATCH (a:Act {code: 'IPC'})
            MERGE (a)-[:HAS_SECTION]->(l)
            """,
                rows=batch,
            )

        for batch in batched(bns_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (l:LawSection {id: row.id})
            SET l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.punishment = row.punishment,
                l.category = row.category,
                l.keywords = row.keywords,
                l.data_complete = row.data_complete
            WITH l, row
            MATCH (a:Act {code: 'BNS'})
            MERGE (a)-[:HAS_SECTION]->(l)
            WITH l, row
            CALL {
              WITH l, row
              WITH l, row WHERE row.chapter_id IS NOT NULL
              MATCH (c:Chapter {id: row.chapter_id})
              MERGE (c)-[:HAS_SECTION]->(l)
              RETURN count(*) AS n
            }
            RETURN count(*) AS done
            """,
                rows=batch,
            )

    print(f"LawSection nodes ensured: IPC={len(ipc_rows)}, BNS={len(bns_rows)}")


def ingest_keywords(driver, bns: dict[str, dict], ipc: dict[str, dict]) -> int:
    rows = []

    for r in bns.values():
        for kw in split_keywords(r.get("keywords", "")):
            rows.append({"law_id": f"BNS_{r['section']}", "kw_id": stable_id("KW", kw), "name": kw})

    for r in ipc.values():
        title = clean(r.get("title", "")).lower()
        if title:
            rows.append({"law_id": f"IPC_{r['section']}", "kw_id": stable_id("KW", title), "name": title})

    with driver.session() as s:
        for batch in batched(rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (k:Keyword {id: row.kw_id})
            SET k.name = row.name
            WITH k, row
            MATCH (l:LawSection {id: row.law_id})
            MERGE (l)-[:HAS_KEYWORD]->(k)
            """,
                rows=batch,
            )

    distinct = len({r["kw_id"] for r in rows})
    print(f"Keyword nodes ensured: {distinct} distinct; edges={len(rows)}")
    return distinct


def ingest_crimes(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> int:
    rows = []
    for r in list(ipc.values()) + list(bns.values()):
        name = clean(r.get("title"))
        if not name:
            continue
        rows.append(
            {
                "crime_id": stable_id("CRIME", name.lower()),
                "name": name,
                "law_id": f"{r['act']}_{r['section']}",
            }
        )

    with driver.session() as s:
        for batch in batched(rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (c:Crime {id: row.crime_id})
            SET c.name = row.name
            WITH c, row
            MATCH (l:LawSection {id: row.law_id})
            MERGE (c)-[:DEFINED_BY]->(l)
            """,
                rows=batch,
            )

    distinct = len({r["crime_id"] for r in rows})
    print(f"Crime nodes ensured: {distinct} distinct; edges={len(rows)}")
    return distinct


def ingest_punishments(driver, ipc: dict[str, dict], bns: dict[str, dict]) -> int:
    rows = []
    skipped_low_signal = 0

    for r in list(ipc.values()) + list(bns.values()):
        txt_raw = clean(r.get("punishment"))
        if is_low_signal_punishment(txt_raw):
            skipped_low_signal += 1
            continue

        # keep dedupe mostly global, but avoid a single mega-hub for generic strings
        norm = normalize_punishment_text(txt_raw)
        section = str(r.get("section", ""))
        punish_id = stable_id("PUNISH", norm if len(norm) > 20 else f"{norm}|{r['act']}|{section}")

        rows.append(
            {
                "punish_id": punish_id,
                "text": txt_raw,
                "law_id": f"{r['act']}_{r['section']}",
            }
        )

    with driver.session() as s:
        for batch in batched(rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (p:Punishment {id: row.punish_id})
            SET p.text = row.text
            WITH p, row
            MATCH (l:LawSection {id: row.law_id})
            MERGE (l)-[:HAS_PUNISHMENT]->(p)
            """,
                rows=batch,
            )

    distinct = len({r["punish_id"] for r in rows})
    print(
        f"Punishment nodes ensured: {distinct} distinct; edges={len(rows)}; "
        f"skipped low-signal punishments={skipped_low_signal}"
    )
    return distinct


def ingest_mappings(driver, mappings: list[dict]):
    pair_rows = []
    ipc_no_successor = set()

    for m in mappings:
        ipc_sec = m["ipc_section"]
        if not ipc_sec:
            continue
        ipc_id = f"IPC_{ipc_sec}"
        targets = m["bns_targets"]

        if not targets:
            ipc_no_successor.add(ipc_id)
            continue

        for b in targets:
            pair_rows.append(
                {
                    "ipc_id": ipc_id,
                    "bns_id": f"BNS_{b}",
                    "note": m["note"],
                    "bns_raw": m["bns_raw"],
                    "status": STATUS_ACTIVE,
                }
            )

    with driver.session() as s:
        for batch in batched(pair_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MATCH (i:LawSection {id: row.ipc_id})
            MATCH (b:LawSection {id: row.bns_id})
            MERGE (i)-[r1:REPLACED_BY]->(b)
            SET r1.note = row.note,
                r1.raw_mapping = row.bns_raw,
                r1.status = row.status
            MERGE (b)-[r2:REPLACES]->(i)
            SET r2.note = row.note,
                r2.raw_mapping = row.bns_raw,
                r2.status = row.status
            """,
                rows=batch,
            )

        if ipc_no_successor:
            s.run(
                f"""
            UNWIND $ids AS id
            MATCH (l:LawSection {{id: id}})
            SET l.mapping_status = '{STATUS_DELETED_NO_BNS}'
            """,
                ids=list(ipc_no_successor),
            )

    print(f"Mapping edges ensured: {len(pair_rows)}")
    print(f"IPC sections tagged {STATUS_DELETED_NO_BNS}: {len(ipc_no_successor)}")


def tag_bns_without_ipc_predecessor(driver) -> int:
    with driver.session() as s:
        result = s.run(
            f"""
            MATCH (b:LawSection {{act:'BNS'}})
            WHERE NOT (b)-[:REPLACES]->(:LawSection {{act:'IPC'}})
            SET b.mapping_status = '{STATUS_NEW_NO_IPC}'
            RETURN count(b) AS c
            """
        ).single()
    count = int(result["c"]) if result else 0
    print(f"BNS sections tagged {STATUS_NEW_NO_IPC}: {count}")
    return count


def ingest_reasoning_rules(driver):
    """
    Keep this layer aligned with expand_with_rules() in text2cypher.py:
    OVERRIDES|MORE_SPECIFIC_THAN|ENHANCES|INCLUDES_ELEMENTS_OF|CANNOT_COEXIST_WITH
    """
    rules = [
        {
            "id": "ipc_302_more_specific_than_299",
            "source": "IPC_302",
            "target": "IPC_299",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "Murder is treated as a specific aggravated form in relation to culpable homicide.",
            "confidence": 0.85,
        },
        {
            "id": "bns_103_more_specific_than_102",
            "source": "BNS_103",
            "target": "BNS_102",
            "relationship": "MORE_SPECIFIC_THAN",
            "condition": "BNS 103 is treated as a more specific aggravated form relative to BNS 102.",
            "confidence": 0.85,
        },
    ]

    allowed = {"OVERRIDES", "MORE_SPECIFIC_THAN", "ENHANCES", "INCLUDES_ELEMENTS_OF", "CANNOT_COEXIST_WITH"}

    with driver.session() as s:
        for rel_type in allowed:
            rel_rows = [r for r in rules if r["relationship"] == rel_type]
            if not rel_rows:
                continue
            s.run(
                f"""
            UNWIND $rows AS row
            MATCH (source:LawSection {{id: row.source}})
            MATCH (target:LawSection {{id: row.target}})
            MERGE (source)-[rel:{rel_type}]->(target)
            SET rel.rule_id = row.id, rel.condition = row.condition, rel.confidence = row.confidence

            MERGE (rule:LegalRule {{id: row.id}})
            SET rule.relationship = row.relationship, rule.condition = row.condition, rule.confidence = row.confidence
            MERGE (rule)-[:APPLIES_FROM]->(source)
            MERGE (rule)-[:APPLIES_TO]->(target)
            """,
                rows=rel_rows,
            )

    print(f"LegalRule nodes ensured: {len(rules)}")


def print_summary(driver):
    q = {
        "Act": "MATCH (n:Act) RETURN count(n) AS c",
        "Chapter": "MATCH (n:Chapter) RETURN count(n) AS c",
        "LawSection IPC": "MATCH (n:LawSection {act:'IPC'}) RETURN count(n) AS c",
        "LawSection BNS": "MATCH (n:LawSection {act:'BNS'}) RETURN count(n) AS c",
        "Crime": "MATCH (n:Crime) RETURN count(n) AS c",
        "Punishment": "MATCH (n:Punishment) RETURN count(n) AS c",
        "Keyword": "MATCH (n:Keyword) RETURN count(n) AS c",
        "LegalRule": "MATCH (n:LegalRule) RETURN count(n) AS c",
        "HAS_CHAPTER": "MATCH ()-[r:HAS_CHAPTER]->() RETURN count(r) AS c",
        "HAS_SECTION": "MATCH ()-[r:HAS_SECTION]->() RETURN count(r) AS c",
        "DEFINED_BY": "MATCH ()-[r:DEFINED_BY]->() RETURN count(r) AS c",
        "HAS_PUNISHMENT": "MATCH ()-[r:HAS_PUNISHMENT]->() RETURN count(r) AS c",
        "HAS_KEYWORD": "MATCH ()-[r:HAS_KEYWORD]->() RETURN count(r) AS c",
        "REPLACED_BY": "MATCH ()-[r:REPLACED_BY]->() RETURN count(r) AS c",
        "REPLACED_BY with status": "MATCH ()-[r:REPLACED_BY]->() WHERE r.status IS NOT NULL RETURN count(r) AS c",
        "REPLACES": "MATCH ()-[r:REPLACES]->() RETURN count(r) AS c",
        "REPLACES with status": "MATCH ()-[r:REPLACES]->() WHERE r.status IS NOT NULL RETURN count(r) AS c",
        f"{STATUS_DELETED_NO_BNS} tags": f"MATCH (n:LawSection {{mapping_status:'{STATUS_DELETED_NO_BNS}'}}) RETURN count(n) AS c",
        f"{STATUS_NEW_NO_IPC} tags": f"MATCH (n:LawSection {{mapping_status:'{STATUS_NEW_NO_IPC}'}}) RETURN count(n) AS c",
    }
    print("\n--- Graph Summary ---")
    with driver.session() as s:
        for k, cy in q.items():
            c = s.run(cy).single()["c"]
            print(f"{k}: {c}")


# =========================
# Main
# =========================
def main():
    parser = argparse.ArgumentParser(description="Ingest IPC-BNS legal graph from ipc.csv, bns_sections_clean.csv, ipc2bns.csv")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="Directory containing CSV files")
    parser.add_argument("--wipe", action="store_true", help="Wipe graph before ingest")
    parser.add_argument("--dry-run", action="store_true", help="Parse/validate only, no DB writes")
    args = parser.parse_args()

    print(f"CSV directory: {args.csv_dir.resolve()}")

    print("\n--- Loading data ---")
    ipc = load_ipc(args.csv_dir)
    bns = load_bns(args.csv_dir)
    mappings = load_mapping(args.csv_dir, ipc, bns)

    if args.dry_run:
        print("\nDRY RUN complete.")
        print(f"IPC sections: {len(ipc)}")
        print(f"BNS sections: {len(bns)}")
        print(f"Mapping rows: {len(mappings)}")
        return

    driver = get_driver()
    try:
        if args.wipe:
            wipe_graph(driver)

        print("\n--- Neo4j ingest ---")
        create_constraints(driver)
        ingest_acts(driver)
        ingest_chapters(driver, bns)
        ingest_sections(driver, ipc, bns)
        ingest_keywords(driver, bns, ipc)
        ingest_crimes(driver, ipc, bns)
        ingest_punishments(driver, ipc, bns)
        ingest_mappings(driver, mappings)
        tag_bns_without_ipc_predecessor(driver)
        ingest_reasoning_rules(driver)
        create_fulltext_indexes(driver)  # required by text2cypher.py
        print_summary(driver)
    finally:
        driver.close()

    print("\nDone.")


if __name__ == "__main__":
    main()