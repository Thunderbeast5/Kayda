
from __future__ import annotations

import argparse
import csv
import hashlib
import json
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

# Procedural and Evidence Acts paths
ALL_ACTS_DIR = BASE_DIR.parent.parent / "all_acts"
BNSS_JSON = ALL_ACTS_DIR / "bnss" / "bnss_all_sections.json"
CRPC_JSON = ALL_ACTS_DIR / "bnss" / "crpc.json"
CRPC_BNSS_MAP_CSV = ALL_ACTS_DIR / "bnss" / "crpc2bnss.csv"
BSA_CSV = ALL_ACTS_DIR / "bsa" / "bsa_sections.csv"
IEA_JSON = ALL_ACTS_DIR / "bsa" / "iea.json"
IEA_BSA_MAP_CSV = ALL_ACTS_DIR / "bsa" / "iea2bsa.csv"

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
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARNING: Missing file: {path}")
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> list[dict]:
    """Read JSON file and return data as list of dicts."""
    if not path.exists():
        print(f"WARNING: Missing file: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"ERROR reading JSON {path}: {e}")
        return []


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
    Parse mapping targets robustly, PRESERVING subsection numbers like (1), (2), etc.

    Examples:
      "103(1)" -> ["103(1)"]
      "2(19) & 2(35)" -> ["2(19)", "2(35)"]
      "309(2), 310(1)" -> ["309(2)", "310(1)"]
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
        # Match section number with optional subsection: e.g., "8(1)", "309(2)", "2(19)", or "5"
        m = re.match(r"^\s*(\d+(?:\([0-9A-Za-z]+\))?)", part)
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
        # FIXED: Only keep BNS targets that exist (by base section number or full subsection)
        bns_targets = [s for s in bns_targets if extract_leading_int(s) and str(extract_leading_int(s)) in bns]

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


def load_bnss() -> dict[str, dict]:
    """Load BNSS (Bharatiya Nagarik Suraksha Sanhita) sections from JSON."""
    rows = read_json(BNSS_JSON)
    bnss: dict[str, dict] = {}
    
    for r in rows:
        sec = clean(r.get("section_no"))
        if not sec:
            continue
            
        bnss[sec] = {
            "act": "BNSS",
            "section": sec,
            "title": clean(r.get("title")),
            "description": clean(r.get("body")),
            "chapter": clean(r.get("chapter")),
            "year": r.get("year", 2023),
            "legal_topic": clean(r.get("legal_topic")),
            "procedural_stage": clean(r.get("procedural_stage")),
            "bail_related": r.get("bail_related", False),
            "investigation_related": r.get("investigation_related", False),
            "court_related": r.get("court_related", False),
            "rights_related": r.get("rights_related", False),
            "data_complete": True,
        }
    
    print(f"BNSS loaded: {len(rows)} rows -> {len(bnss)} unique sections")
    return bnss


def load_crpc() -> dict[str, dict]:
    """Load CrPC (Code of Criminal Procedure) sections from JSON."""
    rows = read_json(CRPC_JSON)
    crpc: dict[str, dict] = {}
    
    for r in rows:
        sec = normalize_section_number(r.get("section"))
        if not sec:
            continue
            
        crpc[sec] = {
            "act": "CrPC",
            "section": sec,
            "title": clean(r.get("section_title")),
            "description": clean(r.get("section_desc")),
            "chapter": clean(r.get("chapter")),
            "year": 1973,
            "data_complete": True,
        }
    
    print(f"CrPC loaded: {len(rows)} rows -> {len(crpc)} unique sections")
    return crpc


def load_crpc_bnss_mapping(crpc: dict[str, dict], bnss: dict[str, dict]) -> list[dict]:
    """Load CrPC to BNSS mapping from CSV."""
    rows = read_csv(CRPC_BNSS_MAP_CSV)
    mappings: list[dict] = []
    stub_crpc = 0
    
    for r in rows:
        crpc_sec = clean(r.get("CrPC Section"))
        bnss_sec = clean(r.get("BNSS Section"))
        notes = clean(r.get("Key Changes / Notes"))
        
        if not crpc_sec:
            continue
            
        # Add stub for CrPC if not exists
        if crpc_sec and crpc_sec not in crpc:
            crpc[crpc_sec] = {
                "act": "CrPC",
                "section": crpc_sec,
                "title": clean(r.get("CrPC Subject")),
                "description": "",
                "chapter": "",
                "year": 1973,
                "data_complete": False,
            }
            stub_crpc += 1
        
        # Only map if BNSS section exists and is not "Removed" or "-"
        if bnss_sec and bnss_sec != "-" and bnss_sec.upper() not in {"REMOVED", "N/A", "NA"}:
            mappings.append({
                "crpc_section": crpc_sec,
                "bnss_section": bnss_sec,
                "note": notes,
            })
    
    print(f"CrPC-BNSS Mapping loaded: {len(rows)} rows -> {len(mappings)} mappings ({stub_crpc} CrPC stubs)")
    return mappings


def load_bsa() -> dict[str, dict]:
    """Load BSA (Bharatiya Sakshya Adhiniyam) sections from CSV."""
    rows = read_csv(BSA_CSV)
    bsa: dict[str, dict] = {}
    
    for r in rows:
        sec = clean(r.get("Section") or r.get("section"))
        if not sec:
            continue
        
        # Try different possible column names for title
        title = (clean(r.get("Section _name")) or  # Note: space in column name
                clean(r.get("Section_name")) or
                clean(r.get("Title")) or 
                clean(r.get("title")))
            
        bsa[sec] = {
            "act": "BSA",
            "section": sec,
            "title": title,
            "description": clean(r.get("Description") or r.get("description")),
            "year": 2023,
            "data_complete": True,
        }
    
    print(f"BSA loaded: {len(rows)} rows -> {len(bsa)} unique sections")
    return bsa


def load_iea() -> dict[str, dict]:
    """Load IEA (Indian Evidence Act) sections from JSON."""
    rows = read_json(IEA_JSON)
    iea: dict[str, dict] = {}
    
    for r in rows:
        sec = normalize_section_number(r.get("section"))
        if not sec:
            continue
            
        iea[sec] = {
            "act": "IEA",
            "section": sec,
            "title": clean(r.get("section_title") or r.get("title")),
            "description": clean(r.get("section_desc") or r.get("description")),
            "chapter": clean(r.get("chapter")),
            "year": 1872,
            "data_complete": True,
        }
    
    print(f"IEA loaded: {len(rows)} rows -> {len(iea)} unique sections")
    return iea


def load_iea_bsa_mapping(iea: dict[str, dict], bsa: dict[str, dict]) -> list[dict]:
    """Load IEA to BSA mapping from CSV."""
    rows = read_csv(IEA_BSA_MAP_CSV)
    mappings: list[dict] = []
    stub_iea = 0
    
    for r in rows:
        iea_sec = clean(r.get("IEA Section"))
        bsa_sec = clean(r.get("BSA Section"))
        notes = clean(r.get("Key Changes / Notes"))
        
        if not iea_sec:
            continue
            
        # Add stub for IEA if not exists
        if iea_sec and iea_sec not in iea:
            iea[iea_sec] = {
                "act": "IEA",
                "section": iea_sec,
                "title": clean(r.get("IEA Subject")),
                "description": "",
                "chapter": "",
                "year": 1872,
                "data_complete": False,
            }
            stub_iea += 1
        
        # Only map if BSA section exists and is not "Removed" or "-"
        if bsa_sec and bsa_sec != "-" and bsa_sec.upper() not in {"REMOVED", "N/A", "NA"}:
            mappings.append({
                "iea_section": iea_sec,
                "bsa_section": bsa_sec,
                "note": notes,
            })
    
    print(f"IEA-BSA Mapping loaded: {len(rows)} rows -> {len(mappings)} mappings ({stub_iea} IEA stubs)")
    return mappings


def normalize_section_number(section: Any) -> str:
    """Normalize section number to string format."""
    if section is None:
        return ""
    return str(section).strip()


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
        {"code": "CrPC", "name": "Code of Criminal Procedure, 1973"},
        {"code": "BNSS", "name": "Bharatiya Nagarik Suraksha Sanhita, 2023"},
        {"code": "IEA", "name": "Indian Evidence Act, 1872"},
        {"code": "BSA", "name": "Bharatiya Sakshya Adhiniyam, 2023"},
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
    print("Act nodes ensured (IPC, BNS, CrPC, BNSS, IEA, BSA).")


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


def ingest_procedural_sections(driver, bnss: dict[str, dict], crpc: dict[str, dict]):
    """Ingest BNSS and CrPC procedural law sections."""
    bnss_rows = [{"id": f"BNSS_{r['section']}", **r} for r in bnss.values()]
    crpc_rows = [{"id": f"CrPC_{r['section']}", **r} for r in crpc.values()]
    
    with driver.session() as s:
        # Ingest BNSS
        for batch in batched(bnss_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (l:LawSection:ProceduralLaw {id: row.id})
            SET l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.chapter = row.chapter,
                l.year = row.year,
                l.legal_topic = row.legal_topic,
                l.procedural_stage = row.procedural_stage,
                l.bail_related = row.bail_related,
                l.investigation_related = row.investigation_related,
                l.court_related = row.court_related,
                l.rights_related = row.rights_related,
                l.data_complete = row.data_complete,
                l.status = 'active'
            WITH l, row
            MATCH (a:Act {code: 'BNSS'})
            MERGE (a)-[:HAS_SECTION]->(l)
            """,
                rows=batch,
            )
        
        # Ingest CrPC
        for batch in batched(crpc_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (l:LawSection:ProceduralLaw {id: row.id})
            SET l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.chapter = row.chapter,
                l.year = row.year,
                l.data_complete = row.data_complete,
                l.status = 'replaced'
            WITH l, row
            MATCH (a:Act {code: 'CrPC'})
            MERGE (a)-[:HAS_SECTION]->(l)
            """,
                rows=batch,
            )
    
    print(f"Procedural LawSection nodes ensured: BNSS={len(bnss_rows)}, CrPC={len(crpc_rows)}")


def ingest_evidence_sections(driver, bsa: dict[str, dict], iea: dict[str, dict]):
    """Ingest BSA and IEA evidence law sections."""
    bsa_rows = [{"id": f"BSA_{r['section']}", **r} for r in bsa.values()]
    iea_rows = [{"id": f"IEA_{r['section']}", **r} for r in iea.values()]
    
    with driver.session() as s:
        # Ingest BSA
        for batch in batched(bsa_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (l:LawSection:EvidenceLaw {id: row.id})
            SET l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.year = row.year,
                l.data_complete = row.data_complete,
                l.status = 'active'
            WITH l, row
            MATCH (a:Act {code: 'BSA'})
            MERGE (a)-[:HAS_SECTION]->(l)
            """,
                rows=batch,
            )
        
        # Ingest IEA
        for batch in batched(iea_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MERGE (l:LawSection:EvidenceLaw {id: row.id})
            SET l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.chapter = row.chapter,
                l.year = row.year,
                l.data_complete = row.data_complete,
                l.status = 'replaced'
            WITH l, row
            MATCH (a:Act {code: 'IEA'})
            MERGE (a)-[:HAS_SECTION]->(l)
            """,
                rows=batch,
            )
    
    print(f"Evidence LawSection nodes ensured: BSA={len(bsa_rows)}, IEA={len(iea_rows)}")


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
            b_base = str(extract_leading_int(b))
            pair_rows.append(
                {
                    "ipc_id": ipc_id,
                    "bns_id": f"BNS_{b}",  # Distinct node ID e.g. BNS_8(1)
                    "bns_base_id": f"BNS_{b_base}",
                    "bns_section": b,
                    "bns_title_hint": m["bns_title_hint"],
                    "bns_subsection": b,
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
            OPTIONAL MATCH (baseBns:LawSection {id: row.bns_base_id})
            MERGE (b:LawSection {id: row.bns_id})
            ON CREATE SET b.act = 'BNS',
                          b.section = row.bns_section,
                          b.title = COALESCE(baseBns.title, row.bns_title_hint),
                          b.description = COALESCE(baseBns.description, ''),
                          b.punishment = COALESCE(baseBns.punishment, ''),
                          b.category = COALESCE(baseBns.category, 'General Provisions'),
                          b.keywords = COALESCE(baseBns.keywords, ''),
                          b.data_complete = True
            MERGE (i)-[r1:REPLACED_BY]->(b)
            SET r1.note = row.note,
                r1.raw_mapping = row.bns_raw,
                r1.bns_subsection = row.bns_subsection,
                r1.target_section = row.bns_subsection,
                r1.status = row.status
            MERGE (b)-[r2:REPLACES]->(i)
            SET r2.note = row.note,
                r2.raw_mapping = row.bns_raw,
                r2.ipc_subsection = row.ipc_section,
                r2.status = row.status
            """,
                rows=batch,
            )

        if ipc_no_successor:
            s.run(
                """
            UNWIND $ids AS id
            MATCH (l:LawSection {id: id})
            SET l.mapping_status = $status
            """,
                ids=list(ipc_no_successor),
                status=STATUS_DELETED_NO_BNS,
            )

    print(f"Mapping edges ensured: {len(pair_rows)}")
    print(f"IPC sections tagged {STATUS_DELETED_NO_BNS}: {len(ipc_no_successor)}")


def ingest_crpc_bnss_mappings(driver, mappings: list[dict]):
    """Ingest CrPC to BNSS replacement mappings."""
    pair_rows = []
    crpc_no_successor = set()
    
    for m in mappings:
        crpc_sec = m["crpc_section"]
        bnss_sec = m["bnss_section"]
        
        if not crpc_sec:
            continue
            
        if not bnss_sec:
            crpc_no_successor.add(f"CrPC_{crpc_sec}")
            continue
        
        bnss_base = str(extract_leading_int(bnss_sec)) if extract_leading_int(bnss_sec) else bnss_sec
        pair_rows.append({
            "crpc_id": f"CrPC_{crpc_sec}",
            "bnss_id": f"BNSS_{bnss_sec}",
            "bnss_base_id": f"BNSS_{bnss_base}",
            "bnss_section": bnss_sec,
            "note": m["note"],
            "status": STATUS_ACTIVE,
        })
    
    with driver.session() as s:
        for batch in batched(pair_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MATCH (c:LawSection {id: row.crpc_id})
            OPTIONAL MATCH (baseBnss:LawSection {id: row.bnss_base_id})
            MERGE (b:LawSection {id: row.bnss_id})
            ON CREATE SET b.act = 'BNSS',
                          b.section = row.bnss_section,
                          b.title = COALESCE(baseBnss.title, ''),
                          b.description = COALESCE(baseBnss.description, ''),
                          b.chapter = COALESCE(baseBnss.chapter, ''),
                          b.year = 2023,
                          b.data_complete = True,
                          b.status = 'active'
            MERGE (c)-[r1:REPLACED_BY]->(b)
            SET r1.note = row.note, r1.target_section = row.bnss_section, r1.status = row.status
            MERGE (b)-[r2:REPLACES]->(c)
            SET r2.note = row.note, r2.status = row.status
            """,
                rows=batch,
            )
        
        if crpc_no_successor:
            s.run(
                """
            UNWIND $ids AS id
            MATCH (l:LawSection {id: id})
            SET l.mapping_status = $status
            """,
                ids=list(crpc_no_successor),
                status=STATUS_DELETED_NO_BNS,
            )
    
    print(f"CrPC-BNSS mapping edges ensured: {len(pair_rows)}")
    print(f"CrPC sections without BNSS successor: {len(crpc_no_successor)}")


def ingest_iea_bsa_mappings(driver, mappings: list[dict]):
    """Ingest IEA to BSA replacement mappings."""
    pair_rows = []
    iea_no_successor = set()
    
    for m in mappings:
        iea_sec = m["iea_section"]
        bsa_sec = m["bsa_section"]
        
        if not iea_sec:
            continue
            
        if not bsa_sec:
            iea_no_successor.add(f"IEA_{iea_sec}")
            continue
        
        bsa_base = str(extract_leading_int(bsa_sec)) if extract_leading_int(bsa_sec) else bsa_sec
        pair_rows.append({
            "iea_id": f"IEA_{iea_sec}",
            "bsa_id": f"BSA_{bsa_sec}",
            "bsa_base_id": f"BSA_{bsa_base}",
            "bsa_section": bsa_sec,
            "note": m["note"],
            "status": STATUS_ACTIVE,
        })
    
    with driver.session() as s:
        for batch in batched(pair_rows, BATCH_SIZE):
            s.run(
                """
            UNWIND $rows AS row
            MATCH (i:LawSection {id: row.iea_id})
            OPTIONAL MATCH (baseBsa:LawSection {id: row.bsa_base_id})
            MERGE (b:LawSection {id: row.bsa_id})
            ON CREATE SET b.act = 'BSA',
                          b.section = row.bsa_section,
                          b.title = COALESCE(baseBsa.title, ''),
                          b.description = COALESCE(baseBsa.description, ''),
                          b.year = 2023,
                          b.data_complete = True,
                          b.status = 'active'
            MERGE (i)-[r1:REPLACED_BY]->(b)
            SET r1.note = row.note, r1.target_section = row.bsa_section, r1.status = row.status
            MERGE (b)-[r2:REPLACES]->(i)
            SET r2.note = row.note, r2.status = row.status
            """,
                rows=batch,
            )
        
        if iea_no_successor:
            s.run(
                """
            UNWIND $ids AS id
            MATCH (l:LawSection {id: id})
            SET l.mapping_status = $status
            """,
                ids=list(iea_no_successor),
                status=STATUS_DELETED_NO_BNS,
            )
    
    print(f"IEA-BSA mapping edges ensured: {len(pair_rows)}")
    print(f"IEA sections without BSA successor: {len(iea_no_successor)}")


def tag_bns_without_ipc_predecessor(driver) -> int:
    with driver.session() as s:
        result = s.run(
            """
            MATCH (b:LawSection {act:'BNS'})
            WHERE NOT (b)-[:REPLACES]->(:LawSection {act:'IPC'})
            SET b.mapping_status = $status
            RETURN count(b) AS c
            """,
            status=STATUS_NEW_NO_IPC,
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
        "LawSection CrPC": "MATCH (n:LawSection {act:'CrPC'}) RETURN count(n) AS c",
        "LawSection BNSS": "MATCH (n:LawSection {act:'BNSS'}) RETURN count(n) AS c",
        "LawSection IEA": "MATCH (n:LawSection {act:'IEA'}) RETURN count(n) AS c",
        "LawSection BSA": "MATCH (n:LawSection {act:'BSA'}) RETURN count(n) AS c",
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
    parser = argparse.ArgumentParser(description="Ingest IPC-BNS-CrPC-BNSS-IEA-BSA legal graph from CSV and JSON files")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="Directory containing CSV files")
    parser.add_argument("--wipe", action="store_true", help="Wipe graph before ingest")
    parser.add_argument("--dry-run", action="store_true", help="Parse/validate only, no DB writes")
    args = parser.parse_args()

    print(f"CSV directory: {args.csv_dir.resolve()}")
    print(f"All Acts directory: {ALL_ACTS_DIR.resolve()}")

    print("\n--- Loading data ---")
    # Criminal Laws
    ipc = load_ipc(args.csv_dir)
    bns = load_bns(args.csv_dir)
    mappings = load_mapping(args.csv_dir, ipc, bns)
    
    # Procedural Laws
    bnss = load_bnss()
    crpc = load_crpc()
    crpc_bnss_mappings = load_crpc_bnss_mapping(crpc, bnss)
    
    # Evidence Laws
    bsa = load_bsa()
    iea = load_iea()
    iea_bsa_mappings = load_iea_bsa_mapping(iea, bsa)

    if args.dry_run:
        print("\nDRY RUN complete.")
        print(f"IPC sections: {len(ipc)}")
        print(f"BNS sections: {len(bns)}")
        print(f"IPC-BNS mappings: {len(mappings)}")
        print(f"CrPC sections: {len(crpc)}")
        print(f"BNSS sections: {len(bnss)}")
        print(f"CrPC-BNSS mappings: {len(crpc_bnss_mappings)}")
        print(f"IEA sections: {len(iea)}")
        print(f"BSA sections: {len(bsa)}")
        print(f"IEA-BSA mappings: {len(iea_bsa_mappings)}")
        return

    driver = get_driver()
    try:
        if args.wipe:
            wipe_graph(driver)

        print("\n--- Neo4j ingest ---")
        create_constraints(driver)
        ingest_acts(driver)
        ingest_chapters(driver, bns)
        
        # Ingest criminal law sections
        ingest_sections(driver, ipc, bns)
        
        # Ingest procedural law sections
        ingest_procedural_sections(driver, bnss, crpc)
        
        # Ingest evidence law sections
        ingest_evidence_sections(driver, bsa, iea)
        
        # Ingest keywords, crimes, punishments
        ingest_keywords(driver, bns, ipc)
        ingest_crimes(driver, ipc, bns)
        ingest_punishments(driver, ipc, bns)
        
        # Ingest all mappings
        ingest_mappings(driver, mappings)
        ingest_crpc_bnss_mappings(driver, crpc_bnss_mappings)
        ingest_iea_bsa_mappings(driver, iea_bsa_mappings)
        
        tag_bns_without_ipc_predecessor(driver)
        ingest_reasoning_rules(driver)
        create_fulltext_indexes(driver)
        print_summary(driver)
    finally:
        driver.close()

    print("\nDone.")


if __name__ == "__main__":
    main()