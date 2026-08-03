
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
MAP_CLEAN_CSV = "ipc2bns_clean.csv"
MAP_CSV = "ipc2bns_clean.csv" if (DEFAULT_CSV_DIR / "ipc2bns_clean.csv").exists() else "ipc2bns.csv"


def make_bns_node_id(target_clean: str, node_type: str, parent_sec: str = "") -> str:
    """Computes stable Neo4j node ID for BNS sections, subsections, clauses, and explanations."""
    t = clean(target_clean).upper()
    if node_type == "EXPLANATION" or "EXPL" in t:
        sec = parent_sec or (re.match(r"^(\d+[A-Z]*)", t).group(1) if re.match(r"^(\d+[A-Z]*)", t) else t)
        return f"BNS_{sec}_EXPL"
    return f"BNS_{t}"


# Procedural and Evidence Acts paths
ALL_ACTS_DIR = BASE_DIR.parent.parent / "all_acts"
BNSS_JSON = ALL_ACTS_DIR / "bnss" / "bnss_all_sections.json"
CRPC_CSV_PATH = DEFAULT_CSV_DIR / "crpc.csv" if (DEFAULT_CSV_DIR / "crpc.csv").exists() else (BASE_DIR / "data" / "cleaned" / "crpc.csv")
CRPC_JSON = ALL_ACTS_DIR / "bnss" / "crpc.json"
CRPC_BNSS_MAP_CSV = DEFAULT_CSV_DIR / "crpc2bnss_clean.csv" if (DEFAULT_CSV_DIR / "crpc2bnss_clean.csv").exists() else (DEFAULT_CSV_DIR / "crpc2bnss_clean_temp.csv" if (DEFAULT_CSV_DIR / "crpc2bnss_clean_temp.csv").exists() else ALL_ACTS_DIR / "bnss" / "crpc2bnss.csv")
BSA_CSV = ALL_ACTS_DIR / "bsa" / "bsa_sections.csv"
IEA_JSON = ALL_ACTS_DIR / "bsa" / "iea.json"
IEA_BSA_MAP_CSV = ALL_ACTS_DIR / "bsa" / "iea2bsa.csv"

# canonical mapping statuses used by text2cypher schema/prompt
STATUS_DELETED_NO_BNS = "deleted_no_bns_successor"
STATUS_DELETED_NO_BNSS = "deleted_no_bnss_successor"
STATUS_NEW_NO_IPC = "new_no_ipc_predecessor"
STATUS_NEW_NO_CRPC = "new_no_crpc_predecessor"
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
            "content_source": "source_dataset",
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
    clean_csv_path = csv_dir / MAP_CLEAN_CSV
    map_csv_path = clean_csv_path if clean_csv_path.exists() else csv_dir / MAP_CSV
    rows = read_csv(map_csv_path)
    mappings: list[dict] = []
    stub_ipc = 0

    is_clean = len(rows) > 0 and "BNS_Section_Clean" in rows[0]

    for r in rows:
        ipc_sec_raw = clean(r.get("IPC_Section"))
        ipc_sec = re.match(r"^\d+[A-Za-z]*$", ipc_sec_raw).group(0) if re.match(r"^\d+[A-Za-z]*$", ipc_sec_raw) else None
        ipc_title = clean(r.get("IPC_Title"))
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
                "content_source": "mapping_title_only",
            }
            stub_ipc += 1

        if is_clean:
            bns_target_raw = clean(r.get("BNS_Section_Raw") or r.get("BNS_Section"))
            bns_clean_target = clean(r.get("BNS_Section_Clean") or r.get("BNS_Section"))
            bns_title = clean(r.get("BNS_Title"))
            node_type = clean(r.get("NodeType")) or "SECTION"
            parent_section = clean(r.get("ParentSection"))
            parent_subsection = clean(r.get("ParentSubsection"))
            subsection_number = clean(r.get("SubsectionNumber"))
            clause = clean(r.get("Clause"))
            validation_status = clean(r.get("ValidationStatus"))
            duplicate_group = clean(r.get("DuplicateGroup"))
            requires_manual_review = clean(r.get("RequiresManualReview"))

            if node_type == "SPECIAL_STATUS" or bns_clean_target.upper() in {"REMOVED", "DELETED", "REPEALED", "N/A", "NA"}:
                continue

            mappings.append(
                {
                    "ipc_section": ipc_sec,
                    "ipc_title_hint": ipc_title,
                    "bns_clean": bns_clean_target,
                    "bns_raw": bns_target_raw,
                    "bns_title_hint": bns_title,
                    "note": note,
                    "node_type": node_type,
                    "parent_section": parent_section,
                    "parent_subsection": parent_subsection,
                    "subsection_number": subsection_number,
                    "clause": clause,
                    "validation_status": validation_status,
                    "duplicate_group": duplicate_group,
                    "requires_manual_review": requires_manual_review,
                }
            )
        else:
            bns_target_raw = clean(r.get("BNS_Section"))
            bns_title = clean(r.get("BNS_Title"))
            bns_targets = parse_bns_targets(bns_target_raw)
            bns_targets = [s for s in bns_targets if extract_leading_int(s) and str(extract_leading_int(s)) in bns]

            for b in bns_targets:
                parent_sec = str(extract_leading_int(b))
                node_type = "SUBSECTION" if "(" in b else "SECTION"
                mappings.append(
                    {
                        "ipc_section": ipc_sec,
                        "ipc_title_hint": ipc_title,
                        "bns_clean": b,
                        "bns_raw": bns_target_raw,
                        "bns_title_hint": bns_title,
                        "note": note,
                        "node_type": node_type,
                        "parent_section": parent_sec,
                        "parent_subsection": b if node_type == "SUBSECTION" else parent_sec,
                        "subsection_number": "",
                        "clause": "",
                        "validation_status": "VALID",
                        "duplicate_group": "NONE",
                        "requires_manual_review": "NO",
                    }
                )

    print(f"Mapping loaded from {map_csv_path.name}: {len(rows)} rows -> {len(mappings)} valid mapping entries ({stub_ipc} IPC stubs added)")
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
    """Load CrPC (Code of Criminal Procedure) sections from CSV or JSON."""
    crpc: dict[str, dict] = {}
    
    if CRPC_CSV_PATH.exists():
        rows = read_csv(CRPC_CSV_PATH)
        for r in rows:
            sec = clean(r.get("Section") or r.get("section")).upper()
            if not sec:
                continue
            title = clean(r.get("Title") or r.get("title"))
            desc = clean(r.get("Description") or r.get("description"))
            chap = clean(r.get("Chapter") or r.get("chapter"))
            crpc[sec] = {
                "act": "CrPC",
                "section": sec,
                "title": title,
                "description": desc,
                "chapter": chap,
                "year": 1973,
                "data_complete": str(r.get("data_complete", "true")).lower() == "true",
                "content_source": clean(r.get("content_source")) or "source_dataset",
            }
        print(f"CrPC loaded from CSV ({CRPC_CSV_PATH.name}): {len(rows)} rows -> {len(crpc)} unique sections")
    else:
        rows = read_json(CRPC_JSON)
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
                "content_source": "source_dataset",
            }
        print(f"CrPC loaded from JSON ({CRPC_JSON.name}): {len(rows)} rows -> {len(crpc)} unique sections")
    return crpc


def load_crpc_bnss_mapping(crpc: dict[str, dict], bnss: dict[str, dict]) -> list[dict]:
    """Load CrPC to BNSS mapping from cleaned CSV."""
    rows = read_csv(CRPC_BNSS_MAP_CSV)
    mappings: list[dict] = []
    stub_crpc = 0
    
    for r in rows:
        crpc_sec = clean(r.get("CrPC_Section") or r.get("CrPC Section"))
        bnss_sec = clean(r.get("BNSS_Section_Clean") or r.get("BNSS Section"))
        notes = clean(r.get("Notes") or r.get("Key Changes / Notes"))
        category = clean(r.get("Category"))
        node_type = clean(r.get("NodeType")) or "SECTION"
        amendment_type = clean(r.get("AmendmentType"))
        
        if not crpc_sec:
            continue
            
        # Add stub for CrPC if not exists in source dataset
        if crpc_sec and crpc_sec.upper() not in {"NOT APPLICABLE", "N/A", "NA"} and crpc_sec not in crpc:
            crpc[crpc_sec] = {
                "act": "CrPC",
                "section": crpc_sec,
                "title": clean(r.get("CrPC_Subject") or r.get("CrPC Subject")),
                "description": "",
                "chapter": "",
                "year": 1973,
                "data_complete": False,
                "content_source": "mapping_title_only",
            }
            stub_crpc += 1
        
        # Only map if BNSS section exists and is not "Removed" or "-"
        if bnss_sec and bnss_sec != "-" and bnss_sec.upper() not in {"REMOVED", "N/A", "NA"} and category != "REMOVED":
            mappings.append({
                "crpc_section": crpc_sec,
                "bnss_section": bnss_sec,
                "note": notes,
                "node_type": node_type,
                "amendment_type": amendment_type,
            })
    
    print(f"CrPC-BNSS Mapping loaded from {CRPC_BNSS_MAP_CSV.name}: {len(rows)} rows -> {len(mappings)} mappings ({stub_crpc} CrPC stubs)")
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
                "content_source": "mapping_title_only",
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
        "CREATE CONSTRAINT generated_node_id IF NOT EXISTS FOR (g:GeneratedNode) REQUIRE g.id IS UNIQUE",
    ]
    with driver.session() as s:
        for q in stmts:
            s.run(q)
    print("Constraints ensured.")


def create_fulltext_indexes(driver):
    stmts = [
        """
        CREATE FULLTEXT INDEX lawSectionText IF NOT EXISTS
        FOR (l:LawSection) ON EACH [l.title, l.description, l.keywords, l.aliases, l.punishment]
        """,
        """
        CREATE FULLTEXT INDEX crimeName IF NOT EXISTS
        FOR (c:Crime) ON EACH [c.name]
        """,
    ]
    with driver.session() as s:
        for q in stmts:
            s.run(q)
    print("Full-text indexes ensured: lawSectionText (title, description, keywords, aliases, punishment), crimeName")


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
            SET l:IPCSection,
                l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.punishment = row.punishment,
                l.cognizable = row.cognizable,
                l.bailable = row.bailable,
                l.court = row.court,
                l.source_url = row.source_url,
                l.node_type = COALESCE(l.node_type, 'SECTION'),
                l.data_complete = row.data_complete,
                l.content_source = COALESCE(row.content_source, 'source_dataset')
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
            SET l:BNSSection,
                l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.punishment = row.punishment,
                l.category = row.category,
                l.keywords = row.keywords,
                l.node_type = COALESCE(l.node_type, 'SECTION'),
                l.data_complete = row.data_complete,
                l.content_source = COALESCE(row.content_source, 'source_dataset')
            WITH l, row
            MATCH (a:Act {code: 'BNS'})
            MERGE (a)-[:HAS_SECTION]->(l)
            WITH l, row
            CALL (l, row) {
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
            MERGE (l:LawSection {id: row.id})
            SET l:BNSSSection:ProceduralLaw,
                l.act = row.act,
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
                l.node_type = COALESCE(l.node_type, 'SECTION'),
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
            MERGE (l:LawSection {id: row.id})
            SET l:CrPCSection:ProceduralLaw,
                l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.chapter = row.chapter,
                l.year = row.year,
                l.node_type = COALESCE(l.node_type, 'SECTION'),
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
            MERGE (l:LawSection {id: row.id})
            SET l:BSASection:EvidenceLaw,
                l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.year = row.year,
                l.node_type = COALESCE(l.node_type, 'SECTION'),
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
            MERGE (l:LawSection {id: row.id})
            SET l:IEASection:EvidenceLaw,
                l.act = row.act,
                l.section = row.section,
                l.title = row.title,
                l.description = row.description,
                l.chapter = row.chapter,
                l.year = row.year,
                l.node_type = COALESCE(l.node_type, 'SECTION'),
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


def ingest_bns_hierarchy_nodes(driver, mappings: list[dict], bns: dict[str, dict]):
    """
    Step 2: Ingests complete BNS LawSection:BNSSection nodes for SUBSECTION, CLAUSE, and EXPLANATION types,
    and auto-creates missing intermediate hierarchy nodes tagged as :GeneratedNode.
    """
    node_rows = []
    generated_rows = []
    seen_node_ids = set()
    mapped_ids = set()

    for m in mappings:
        node_type = m.get("node_type", "SECTION")
        if node_type == "SPECIAL_STATUS":
            continue

        target = m["bns_clean"]
        parent_sec = m.get("parent_section", "")
        node_id = make_bns_node_id(target, node_type, parent_sec)
        mapped_ids.add(node_id)

        base_sec = str(extract_leading_int(target)) if extract_leading_int(target) else target
        base_info = bns.get(base_sec, {})
        canonical_title = m.get("bns_title_hint") or base_info.get("title", "")

        if node_id not in seen_node_ids:
            seen_node_ids.add(node_id)
            node_rows.append(
                {
                    "id": node_id,
                    "section": target,
                    "title": canonical_title,
                    "node_type": node_type,
                    "status": STATUS_ACTIVE,
                }
            )

    seen_gen_ids = set()
    for m in mappings:
        if m.get("node_type") == "CLAUSE":
            parent_sec = m.get("parent_section", "")
            parent_sub = m.get("parent_subsection", "")
            if parent_sub and parent_sub != parent_sec:
                gen_id = f"BNS_{parent_sub}"
                if gen_id not in mapped_ids and gen_id not in seen_gen_ids:
                    seen_gen_ids.add(gen_id)
                    sub_num = m.get("subsection_number", "")
                    gen_title = f"Subsection ({sub_num}) of Section {parent_sec}" if sub_num else f"Section {parent_sub}"
                    generated_rows.append(
                        {
                            "id": gen_id,
                            "section": parent_sub,
                            "title": gen_title,
                            "generated_reason": "Intermediate subsection",
                        }
                    )

    with driver.session() as s:
        for batch in batched(node_rows, BATCH_SIZE):
            s.run(
                """
                UNWIND $rows AS row
                MERGE (l:LawSection {id: row.id})
                ON CREATE SET l:BNSSection,
                              l.act = 'BNS',
                              l.section = row.section,
                              l.title = row.title,
                              l.year = 2023,
                              l.status = row.status,
                              l.node_type = row.node_type,
                              l.generated = false,
                              l.generated_reason = '',
                              l.data_complete = true
                ON MATCH SET l:BNSSection,
                             l.title = CASE WHEN row.title <> '' AND (l.title IS NULL OR l.title = '') THEN row.title ELSE l.title END,
                             l.node_type = row.node_type
                """,
                rows=batch,
            )

        if generated_rows:
            for batch in batched(generated_rows, BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MERGE (l:LawSection {id: row.id})
                    ON CREATE SET l:BNSSection:GeneratedNode,
                                  l.act = 'BNS',
                                  l.section = row.section,
                                  l.title = row.title,
                                  l.year = 2023,
                                  l.status = 'active',
                                  l.node_type = 'SUBSECTION',
                                  l.generated = true,
                                  l.generated_reason = row.generated_reason,
                                  l.data_complete = false
                    ON MATCH SET l:BNSSection:GeneratedNode
                    """,
                    rows=batch,
                )

    print(f"BNS Hierarchy nodes ingested: {len(node_rows)} explicit nodes, {len(generated_rows)} generated intermediate nodes.")


def ingest_bns_hierarchy_relationships(driver, mappings: list[dict]):
    """
    Step 2: Creates structural hierarchy edges in Neo4j:
      (BNS_ParentSection)-[:HAS_SUBSECTION]->(BNS_Subsection)
      (BNS_ParentSubsection)-[:HAS_CLAUSE]->(BNS_Clause)
      (BNS_ParentSection)-[:HAS_EXPLANATION]->(BNS_Explanation)
    """
    has_sub_pairs = []
    has_clause_pairs = []
    has_expl_pairs = []

    seen_sub = set()
    seen_clause = set()
    seen_expl = set()

    for m in mappings:
        nt = m.get("node_type", "SECTION")
        if nt == "SPECIAL_STATUS":
            continue

        target = m["bns_clean"]
        sec = m.get("parent_section", "")
        sub = m.get("parent_subsection", "")

        if not sec:
            continue

        parent_sec_id = f"BNS_{sec}"

        if nt == "EXPLANATION" or "EXPL" in target.upper():
            child_id = f"BNS_{sec}_EXPL"
            pair = (parent_sec_id, child_id)
            if pair not in seen_expl:
                seen_expl.add(pair)
                has_expl_pairs.append({"parent_id": parent_sec_id, "child_id": child_id})

        elif nt == "SUBSECTION":
            child_id = f"BNS_{target}"
            pair = (parent_sec_id, child_id)
            if pair not in seen_sub:
                seen_sub.add(pair)
                has_sub_pairs.append({"parent_id": parent_sec_id, "child_id": child_id})

        elif nt == "CLAUSE":
            child_id = f"BNS_{target}"
            if sub and sub != sec:
                parent_sub_id = f"BNS_{sub}"
                sub_pair = (parent_sec_id, parent_sub_id)
                if sub_pair not in seen_sub:
                    seen_sub.add(sub_pair)
                    has_sub_pairs.append({"parent_id": parent_sec_id, "child_id": parent_sub_id})
                clause_pair = (parent_sub_id, child_id)
                if clause_pair not in seen_clause:
                    seen_clause.add(clause_pair)
                    has_clause_pairs.append({"parent_id": parent_sub_id, "child_id": child_id})
            else:
                clause_pair = (parent_sec_id, child_id)
                if clause_pair not in seen_clause:
                    seen_clause.add(clause_pair)
                    has_clause_pairs.append({"parent_id": parent_sec_id, "child_id": child_id})

    with driver.session() as s:
        if has_sub_pairs:
            for batch in batched(has_sub_pairs, BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MATCH (parent:LawSection {id: row.parent_id})
                    MATCH (child:LawSection {id: row.child_id})
                    MERGE (parent)-[r:HAS_SUBSECTION]->(child)
                    SET r.level = 1
                    """,
                    rows=batch,
                )

        if has_clause_pairs:
            for batch in batched(has_clause_pairs, BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MATCH (parent:LawSection {id: row.parent_id})
                    MATCH (child:LawSection {id: row.child_id})
                    MERGE (parent)-[r:HAS_CLAUSE]->(child)
                    SET r.level = 2
                    """,
                    rows=batch,
                )

        if has_expl_pairs:
            for batch in batched(has_expl_pairs, BATCH_SIZE):
                s.run(
                    """
                    UNWIND $rows AS row
                    MATCH (parent:LawSection {id: row.parent_id})
                    MATCH (child:LawSection {id: row.child_id})
                    MERGE (parent)-[r:HAS_EXPLANATION]->(child)
                    SET r.type = 'EXPLANATION'
                    """,
                    rows=batch,
                )

    print(
        f"Hierarchy edges ingested: HAS_SUBSECTION={len(has_sub_pairs)}, "
        f"HAS_CLAUSE={len(has_clause_pairs)}, HAS_EXPLANATION={len(has_expl_pairs)}"
    )


def ingest_procedural_and_evidence_hierarchy(driver):
    """
    Constructs statutory hierarchy edges across all 6 relationship types:
      HAS_SUBSECTION, HAS_CLAUSE, HAS_EXPLANATION, HAS_ILLUSTRATION, HAS_EXCEPTION, HAS_PROVISO
    for BNS, BNSS, IEA, and BSA nodes using Cypher patterns and metadata files.
    """
    bsa_h_csv = DEFAULT_CSV_DIR / "bsa_hierarchy_metadata.csv"
    h_rows = read_csv(bsa_h_csv) if bsa_h_csv.exists() else []

    with driver.session() as s:
        # 1. Ingest BSA Metadata Hierarchy if available
        if h_rows:
            for batch in batched(h_rows, BATCH_SIZE):
                s.run("""
                    UNWIND $rows AS row
                    MATCH (parent:LawSection {act: 'BSA'})
                    WHERE parent.section = row.ParentSection OR parent.id = 'BSA_' + row.ParentSection
                    MERGE (child:LawSection {id: 'BSA_' + row.ChildIdentifier})
                    ON CREATE SET child.act = 'BSA',
                                  child.section = row.ChildIdentifier,
                                  child.node_type = row.NodeType,
                                  child.description = row.TextSlice,
                                  child.data_complete = true,
                                  child.status = 'active'
                    WITH parent, child, row
                    WHERE row.NodeType IN ['SUBSECTION', 'CLAUSE', 'EXPLANATION', 'ILLUSTRATION', 'EXCEPTION', 'PROVISO']
                    MATCH (p:LawSection {id: parent.id}), (c:LawSection {id: child.id})
                    FOREACH (_ IN CASE WHEN row.NodeType = 'SUBSECTION' THEN [1] ELSE [] END | MERGE (p)-[:HAS_SUBSECTION {level: 1}]->(c))
                    FOREACH (_ IN CASE WHEN row.NodeType = 'CLAUSE' THEN [1] ELSE [] END | MERGE (p)-[:HAS_CLAUSE {level: 2}]->(c))
                    FOREACH (_ IN CASE WHEN row.NodeType = 'EXPLANATION' THEN [1] ELSE [] END | MERGE (p)-[:HAS_EXPLANATION {type: 'EXPLANATION'}]->(c))
                    FOREACH (_ IN CASE WHEN row.NodeType = 'ILLUSTRATION' THEN [1] ELSE [] END | MERGE (p)-[:HAS_ILLUSTRATION {type: 'ILLUSTRATION'}]->(c))
                    FOREACH (_ IN CASE WHEN row.NodeType = 'EXCEPTION' THEN [1] ELSE [] END | MERGE (p)-[:HAS_EXCEPTION {type: 'EXCEPTION'}]->(c))
                    FOREACH (_ IN CASE WHEN row.NodeType = 'PROVISO' THEN [1] ELSE [] END | MERGE (p)-[:HAS_PROVISO {type: 'PROVISO'}]->(c))
                """, rows=batch)

        # 2. Connect Clauses (HAS_CLAUSE {level: 2})
        res_clause = s.run("""
            MATCH (c:LawSection)
            WHERE c.act IN ['BNS', 'BNSS', 'BSA'] AND c.id CONTAINS '(' AND c.node_type = 'CLAUSE'
            WITH c, split(c.section, '(')[0] AS base_sec
            MATCH (p:LawSection {act: c.act, section: base_sec})
            WHERE p.id <> c.id
            MERGE (p)-[r:HAS_CLAUSE]->(c)
            SET r.level = 2
            RETURN count(r) AS count
        """).single()
        clause_count = res_clause["count"] if res_clause else 0

        # 3. Connect Subsections (HAS_SUBSECTION {level: 1})
        res_sub = s.run("""
            MATCH (c:LawSection)
            WHERE c.act IN ['BNS', 'BNSS', 'BSA'] AND c.id CONTAINS '(' AND c.node_type <> 'CLAUSE'
            WITH c, split(c.section, '(')[0] AS base_sec
            MATCH (p:LawSection {act: c.act, section: base_sec})
            WHERE p.id <> c.id
            MERGE (p)-[r:HAS_SUBSECTION]->(c)
            SET r.level = 1
            RETURN count(r) AS count
        """).single()
        sub_count = res_sub["count"] if res_sub else 0

        # 4. Connect Explanations (HAS_EXPLANATION)
        res_expl = s.run("""
            MATCH (c:LawSection)
            WHERE c.act IN ['BNS', 'BNSS', 'BSA'] AND (c.id CONTAINS 'EXPL' OR c.node_type = 'EXPLANATION')
            WITH c, split(c.section, ' ')[0] AS base_sec
            MATCH (p:LawSection {act: c.act, section: base_sec})
            WHERE p.id <> c.id
            MERGE (p)-[r:HAS_EXPLANATION]->(c)
            SET r.type = 'EXPLANATION'
            RETURN count(r) AS count
        """).single()
        expl_count = res_expl["count"] if res_expl else 0

        # 5. Connect Illustrations (HAS_ILLUSTRATION)
        res_illus = s.run("""
            MATCH (c:LawSection)
            WHERE c.act IN ['BNS', 'BNSS', 'BSA'] AND (c.id CONTAINS 'Illus' OR c.node_type = 'ILLUSTRATION')
            WITH c, split(c.section, '(')[0] AS base_sec
            MATCH (p:LawSection {act: c.act, section: base_sec})
            WHERE p.id <> c.id
            MERGE (p)-[r:HAS_ILLUSTRATION]->(c)
            SET r.type = 'ILLUSTRATION'
            RETURN count(r) AS count
        """).single()
        illus_count = res_illus["count"] if res_illus else 0

        # 6. Connect Exceptions (HAS_EXCEPTION)
        res_exc = s.run("""
            MATCH (c:LawSection)
            WHERE c.act IN ['BNS', 'BNSS', 'BSA'] AND (c.id CONTAINS 'Exc' OR c.node_type = 'EXCEPTION')
            WITH c, split(c.section, '(')[0] AS base_sec
            MATCH (p:LawSection {act: c.act, section: base_sec})
            WHERE p.id <> c.id
            MERGE (p)-[r:HAS_EXCEPTION]->(c)
            SET r.type = 'EXCEPTION'
            RETURN count(r) AS count
        """).single()
        exc_count = res_exc["count"] if res_exc else 0

        # 7. Connect Provisos (HAS_PROVISO)
        res_prov = s.run("""
            MATCH (c:LawSection)
            WHERE c.act IN ['BNS', 'BNSS', 'BSA'] AND (c.id CONTAINS 'Prov' OR c.node_type = 'PROVISO')
            WITH c, split(c.section, '(')[0] AS base_sec
            MATCH (p:LawSection {act: c.act, section: base_sec})
            WHERE p.id <> c.id
            MERGE (p)-[r:HAS_PROVISO]->(c)
            SET r.type = 'PROVISO'
            RETURN count(r) AS count
        """).single()
        prov_count = res_prov["count"] if res_prov else 0

    print(
        f"Statutory Hierarchy edges ingested: HAS_SUBSECTION={sub_count}, HAS_CLAUSE={clause_count}, "
        f"HAS_EXPLANATION={expl_count}, HAS_ILLUSTRATION={illus_count}, HAS_EXCEPTION={exc_count}, HAS_PROVISO={prov_count}"
    )


def inherit_structural_context(driver):
    """
    Step 3: Propagates structural legal context (keywords, punishments, chapters, statutory ingredients,
    exceptions, illustrations, evidence types) from parent legal provisions down to child subsections,
    clauses, and explanations in Neo4j.

    Explicitly EXCLUDES judicial case relationships:
      INTERPRETS, APPLIES_SECTION, CITES_CASE, USES_EVIDENCE, DECIDED_BY.
    """
    structural_outgoing_rels = [
        "HAS_KEYWORD",
        "HAS_PUNISHMENT",
        "DEFINED_BY",
        "HAS_INGREDIENT",
        "HAS_EXCEPTION",
        "HAS_ILLUSTRATION",
        "SUPPORTED_BY",
    ]

    structural_incoming_rels = [
        "HAS_INGREDIENT",
        "SUPPORTED_BY",
        "HAS_EXCEPTION",
        "HAS_ILLUSTRATION",
    ]

    with driver.session() as s:
        # 0. Inherit node scalar properties (chapter, part, title, keywords, legal_domain)
        s.run(
            """
            MATCH (parent:LawSection)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION|HAS_ILLUSTRATION|HAS_EXCEPTION|HAS_PROVISO]->(child:LawSection)
            SET child.chapter = CASE WHEN child.chapter IS NULL OR child.chapter = '' THEN parent.chapter ELSE child.chapter END,
                child.part = CASE WHEN child.part IS NULL OR child.part = '' THEN COALESCE(parent.part, '') ELSE child.part END,
                child.title = CASE WHEN child.title IS NULL OR child.title = '' THEN COALESCE(parent.title, '') ELSE child.title END,
                child.keywords = CASE WHEN child.keywords IS NULL OR child.keywords = '' THEN COALESCE(parent.keywords, '') ELSE child.keywords END,
                child.legal_domain = CASE WHEN child.legal_domain IS NULL OR child.legal_domain = '' THEN COALESCE(parent.legal_domain, parent.act) ELSE child.legal_domain END
            """
        )

        # 1. Inherit Chapter HAS_SECTION relationships (Chapter -> Section -> Child)
        s.run(
            """
            MATCH (c:Chapter)-[:HAS_SECTION]->(parent:LawSection)
            MATCH (parent)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION|HAS_ILLUSTRATION|HAS_EXCEPTION|HAS_PROVISO]->(child:LawSection)
            MERGE (c)-[r:HAS_SECTION]->(child)
            ON CREATE SET r.inherited = true,
                          r.inherited_from = parent.id,
                          r.inheritance_level = CASE WHEN parent.node_type = 'SUBSECTION' THEN 2 ELSE 1 END
            """
        )

        # 2. Inherit outgoing structural relationships (parent -> target)
        for rel_type in structural_outgoing_rels:
            query = f"""
                MATCH (parent:LawSection)-[r:{rel_type}]->(target)
                MATCH (parent)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION|HAS_ILLUSTRATION|HAS_EXCEPTION|HAS_PROVISO]->(child:LawSection)
                MERGE (child)-[r_new:{rel_type}]->(target)
                ON CREATE SET r_new.inherited = true,
                              r_new.inherited_from = parent.id,
                              r_new.inheritance_level = CASE WHEN parent.node_type = 'SUBSECTION' THEN 2 ELSE 1 END
            """
            s.run(query)

        # 3. Inherit incoming structural relationships (source -> parent)
        for rel_type in structural_incoming_rels:
            query = f"""
                MATCH (source)-[r:{rel_type}]->(parent:LawSection)
                MATCH (parent)-[:HAS_SUBSECTION|HAS_CLAUSE|HAS_EXPLANATION|HAS_ILLUSTRATION|HAS_EXCEPTION|HAS_PROVISO]->(child:LawSection)
                MERGE (source)-[r_new:{rel_type}]->(child)
                ON CREATE SET r_new.inherited = true,
                              r_new.inherited_from = parent.id,
                              r_new.inheritance_level = CASE WHEN parent.node_type = 'SUBSECTION' THEN 2 ELSE 1 END
            """
            s.run(query)

        # 4. Level-2 Grandparent propagation for Clauses (grandparent -> sub -> clause)
        for rel_type in structural_outgoing_rels:
            query = f"""
                MATCH (grandparent:LawSection)-[r:{rel_type}]->(target)
                MATCH (grandparent)-[:HAS_SUBSECTION]->(sub:LawSection)-[:HAS_CLAUSE]->(clause:LawSection)
                MERGE (clause)-[r_new:{rel_type}]->(target)
                ON CREATE SET r_new.inherited = true,
                              r_new.inherited_from = grandparent.id,
                              r_new.inheritance_level = 2
            """
            s.run(query)

    print("Step 3: Structural context inheritance completed.")


def ingest_mappings(driver, mappings: list[dict]):
    pair_rows = []
    ipc_no_successor = set()

    for m in mappings:
        ipc_sec = m["ipc_section"]
        if not ipc_sec:
            continue
        ipc_id = f"IPC_{ipc_sec}"

        node_type = m.get("node_type", "SECTION")
        bns_target = m.get("bns_clean", "")

        if node_type == "SPECIAL_STATUS" or not bns_target:
            ipc_no_successor.add(ipc_id)
            continue

        parent_sec = m.get("parent_section", "")
        bns_node_id = make_bns_node_id(bns_target, node_type, parent_sec)

        pair_rows.append(
            {
                "ipc_id": ipc_id,
                "ipc_section": ipc_sec,
                "ipc_title": m.get("ipc_title_hint", ""),
                "bns_id": bns_node_id,
                "bns_section": bns_target,
                "bns_title_hint": m.get("bns_title_hint", ""),
                "bns_subsection": bns_target,
                "note": m.get("note", ""),
                "bns_raw": m.get("bns_raw", ""),
                "duplicate_group": m.get("duplicate_group", "NONE"),
                "requires_manual_review": m.get("requires_manual_review", "NO"),
                "status": m.get("validation_status", STATUS_ACTIVE),
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
                SET r1.ipc_section = row.ipc_section,
                    r1.ipc_title = row.ipc_title,
                    r1.bns_target = row.bns_section,
                    r1.note = row.note,
                    r1.raw_mapping = row.bns_raw,
                    r1.bns_subsection = row.bns_subsection,
                    r1.target_section = row.bns_subsection,
                    r1.duplicate_group = row.duplicate_group,
                    r1.requires_manual_review = row.requires_manual_review,
                    r1.status = row.status
                MERGE (b)-[r2:REPLACES]->(i)
                SET r2.ipc_section = row.ipc_section,
                    r2.ipc_title = row.ipc_title,
                    r2.note = row.note,
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


def segment_statutory_text(body: str, target_sub: str) -> str:
    """Parses statutory section body text and extracts the isolated slice for target subsection or clause."""
    if not body:
        return ""
    
    m_sub = re.search(r"\(([^)]+)\)$", target_sub)
    if not m_sub:
        return body.strip()
    
    marker = m_sub.group(1).strip()
    pattern_start = rf"\(\s*{re.escape(marker)}\s*\)"
    match_start = re.search(pattern_start, body)
    
    if not match_start:
        return body.strip()
    
    start_pos = match_start.start()
    
    if marker.isdigit():
        next_num = int(marker) + 1
        match_next = re.search(rf"\(\s*{next_num}\s*\)", body[match_start.end():])
        if match_next:
            end_pos = match_start.end() + match_next.start()
            return body[start_pos:end_pos].strip()
        else:
            return body[start_pos:].strip()
    else:
        next_char = chr(ord(marker) + 1)
        match_next = re.search(rf"\(\s*{re.escape(next_char)}\s*\)", body[match_start.end():])
        if match_next:
            end_pos = match_start.end() + match_next.start()
            return body[start_pos:end_pos].strip()
        else:
            return body[start_pos:].strip()


def ingest_crpc_bnss_mappings(driver, mappings: list[dict], bnss_dict: dict[str, dict] = None):
    """Ingest CrPC to BNSS replacement mappings with creation-time statutory text segmentation."""
    pair_rows = []
    crpc_no_successor = set()
    new_bnss_rows = []
    
    for m in mappings:
        crpc_sec = m["crpc_section"]
        bnss_sec = m["bnss_section"]
        
        if not crpc_sec:
            continue

        if crpc_sec.upper() in {"NOT APPLICABLE", "N/A", "NA"}:
            if bnss_sec and bnss_sec.upper() not in {"REMOVED", "N/A", "NA", "-"}:
                bnss_base = str(extract_leading_int(bnss_sec)) if extract_leading_int(bnss_sec) else bnss_sec
                body_text = bnss_dict.get(bnss_base, {}).get("description", "") if bnss_dict else ""
                segmented_desc = segment_statutory_text(body_text, bnss_sec) if "(" in bnss_sec else ""
                new_bnss_rows.append({
                    "bnss_id": f"BNSS_{bnss_sec}",
                    "bnss_base_id": f"BNSS_{bnss_base}",
                    "bnss_section": bnss_sec,
                    "description": segmented_desc,
                    "node_type": m.get("node_type", "SECTION"),
                })
            continue
            
        if not bnss_sec or bnss_sec.upper() in {"REMOVED", "DELETED", "N/A", "NA", "-"}:
            crpc_no_successor.add(f"CrPC_{crpc_sec}")
            continue
        
        bnss_base = str(extract_leading_int(bnss_sec)) if extract_leading_int(bnss_sec) else bnss_sec
        body_text = bnss_dict.get(bnss_base, {}).get("description", "") if bnss_dict else ""
        segmented_desc = segment_statutory_text(body_text, bnss_sec) if "(" in bnss_sec else ""
        pair_rows.append({
            "crpc_id": f"CrPC_{crpc_sec}",
            "bnss_id": f"BNSS_{bnss_sec}",
            "bnss_base_id": f"BNSS_{bnss_base}",
            "bnss_section": bnss_sec,
            "description": segmented_desc,
            "note": m["note"],
            "amendment_type": m.get("amendment_type", ""),
            "status": STATUS_ACTIVE,
        })
    
    with driver.session() as s:
        # 1. Merge New BNSS Sections (new_no_crpc_predecessor)
        if new_bnss_rows:
            s.run(
                """
            UNWIND $rows AS row
            OPTIONAL MATCH (baseBnss:LawSection {id: row.bnss_base_id})
            MERGE (b:LawSection {id: row.bnss_id})
            ON CREATE SET b.act = 'BNSS',
                          b.section = row.bnss_section,
                          b.title = COALESCE(baseBnss.title, ''),
                          b.description = CASE WHEN row.description <> '' THEN row.description ELSE COALESCE(baseBnss.description, '') END,
                          b.chapter = COALESCE(baseBnss.chapter, ''),
                          b.year = 2023,
                          b.data_complete = True,
                          b.status = 'active'
            SET b.node_type = row.node_type,
                b.description = CASE WHEN row.description <> '' THEN row.description ELSE b.description END,
                b.mapping_status = $status
            """,
                rows=new_bnss_rows,
                status=STATUS_NEW_NO_CRPC,
            )

        # 2. Ingest Mapping Edges
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
                          b.description = CASE WHEN row.description <> '' THEN row.description ELSE COALESCE(baseBnss.description, '') END,
                          b.chapter = COALESCE(baseBnss.chapter, ''),
                          b.year = 2023,
                          b.data_complete = True,
                          b.status = 'active'
            SET b.node_type = CASE
              WHEN b.section CONTAINS '(' AND b.section CONTAINS ')' THEN
                CASE WHEN b.section =~ '.*\\([A-Za-z]\\).*' THEN 'CLAUSE' ELSE 'SUBSECTION' END
              ELSE COALESCE(b.node_type, 'SECTION')
            END,
            b.description = CASE WHEN row.description <> '' THEN row.description ELSE b.description END
            MERGE (c)-[r1:REPLACED_BY]->(b)
            SET r1.note = row.note, r1.target_section = row.bnss_section, r1.status = row.status, r1.amendment_type = row.amendment_type
            MERGE (b)-[r2:REPLACES]->(c)
            SET r2.note = row.note, r2.status = row.status, r2.amendment_type = row.amendment_type
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
                status=STATUS_DELETED_NO_BNSS,
            )
    
    print(f"CrPC-BNSS mapping edges ensured: {len(pair_rows)}")
    print(f"New BNSS sections tagged: {len(new_bnss_rows)}")
    print(f"CrPC sections without BNSS successor: {len(crpc_no_successor)}")


def segment_bsa_statutory_text(parent_body: str, target_sub: str) -> str:
    """
    Slices parent BSA section body for a target sub-node (e.g. '63(1)', '2(1)(a)', '23(Prov)', '39(Illus)').
    """
    if not parent_body or not target_sub:
        return parent_body

    m_sub = re.search(r"\((\d+)\)", target_sub)
    sub_num = m_sub.group(1) if m_sub else ""

    m_clause = re.search(r"\(([a-z])\)", target_sub)
    clause_let = m_clause.group(1) if m_clause else ""

    # 1. Proviso Slicing
    if "Prov" in target_sub:
        m_prov = list(re.finditer(r"(Provided (?:that|further that|also that)[^\.\:\;]+[\.\:\;])", parent_body, re.IGNORECASE))
        if m_prov:
            idx = 0
            m_idx = re.search(r"Prov(\d+)", target_sub)
            if m_idx:
                idx = int(m_idx.group(1)) - 1
            if 0 <= idx < len(m_prov):
                return m_prov[idx].group(1).strip()
            return m_prov[0].group(1).strip()

    # 2. Explanation Slicing
    if "EXPL" in target_sub or "Explanation" in target_sub:
        m_expl = list(re.finditer(r"(Explanation[^\.\n]*[\.\n]+[^\n]+)", parent_body, re.IGNORECASE))
        if m_expl:
            return m_expl[0].group(1).strip()

    # 3. Illustration Slicing
    if "Illus" in target_sub or "Illustration" in target_sub:
        m_illus = list(re.finditer(r"(Illustrations?\.[^\n]+(?:\n\([a-z]\)[^\n]+)*)", parent_body, re.IGNORECASE))
        if m_illus:
            return m_illus[0].group(1).strip()
        m_inline = re.search(r"(Illustrations?\.\s*.+)", parent_body, re.DOTALL | re.IGNORECASE)
        if m_inline:
            return m_inline.group(1).strip()

    # 4. Clause Slicing inside Subsections or Base
    if clause_let:
        pattern = rf"(?:^|\n|\.\s+|;|\:\-\-|\,\s+)\({re.escape(clause_let)}\)\s+([^\n]+)"
        match = re.search(pattern, parent_body)
        if match:
            return f"({clause_let}) " + match.group(1).strip()

    # 5. Subsection Slicing
    if sub_num:
        pattern = rf"(?:^|\n|\.\s+)\({re.escape(sub_num)}\)\s+(.+?)(?=(?:\n|\.\s+)\(\d+\)|Illustrations?\.|Explanation|\Z)"
        match = re.search(pattern, parent_body, re.DOTALL)
        if match:
            return f"({sub_num}) " + match.group(1).strip()

    return parent_body


def segment_iea_statutory_text(parent_body: str, target_sub: str) -> str:
    """
    Slices parent IEA section body for a target sub-node (e.g. '27(Prov)', '9_EXPL', '105(Exc)', '50(Prov)').
    """
    if not parent_body or not target_sub:
        return parent_body

    m_sub = re.search(r"\((\d+)\)", target_sub)
    sub_num = m_sub.group(1) if m_sub else ""

    m_clause = re.search(r"\(([a-z])\)", target_sub)
    clause_let = m_clause.group(1) if m_clause else ""

    # 1. Proviso Slicing
    if "Prov" in target_sub:
        m_prov = list(re.finditer(r"(Provided (?:that|further that|also that)[^\.\:\;]+[\.\:\;])", parent_body, re.IGNORECASE))
        if m_prov:
            idx = 0
            m_idx = re.search(r"Prov(\d+)", target_sub)
            if m_idx:
                idx = int(m_idx.group(1)) - 1
            if 0 <= idx < len(m_prov):
                return m_prov[idx].group(1).strip()
            return m_prov[0].group(1).strip()

    # 2. Explanation Slicing
    if "EXPL" in target_sub or "Explanation" in target_sub:
        m_expl = list(re.finditer(r"(Explanation[^\.\n]*[\.\n]+[^\n]+)", parent_body, re.IGNORECASE))
        if m_expl:
            return m_expl[0].group(1).strip()

    # 3. Exception Slicing
    if "Exc" in target_sub or "Exception" in target_sub:
        m_exc = list(re.finditer(r"(Exception[^\.\n]*[\.\n]+[^\n]+)", parent_body, re.IGNORECASE))
        if m_exc:
            return m_exc[0].group(1).strip()

    # 4. Illustration Slicing
    if "Illus" in target_sub or "Illustration" in target_sub:
        m_illus = list(re.finditer(r"(Illustrations?\.[^\n]+(?:\n\([a-z]\)[^\n]+)*)", parent_body, re.IGNORECASE))
        if m_illus:
            return m_illus[0].group(1).strip()
        m_inline = re.search(r"(Illustrations?\.\s*.+)", parent_body, re.DOTALL | re.IGNORECASE)
        if m_inline:
            return m_inline.group(1).strip()

    # 5. Clause Slicing inside Subsections or Base
    if clause_let:
        pattern = rf"(?:^|\n|\.\s+|;|\:\-\-|\,\s+)\({re.escape(clause_let)}\)\s+([^\n]+)"
        match = re.search(pattern, parent_body)
        if match:
            return f"({clause_let}) " + match.group(1).strip()

    # 6. Subsection Slicing
    if sub_num:
        pattern = rf"(?:^|\n|\.\s+)\({re.escape(sub_num)}\)\s+(.+?)(?=(?:\n|\.\s+)\(\d+\)|Illustrations?\.|Explanation|\Z)"
        match = re.search(pattern, parent_body, re.DOTALL)
        if match:
            return f"({sub_num}) " + match.group(1).strip()

    return parent_body


def ingest_iea_bsa_mappings(driver, mappings: list[dict], bsa_dict: dict[str, dict] = None, iea_dict: dict[str, dict] = None):
    """Ingest IEA to BSA replacement mappings with creation-time statutory text segmentation."""
    pair_rows = []
    iea_no_successor = set()
    new_bsa_rows = []
    
    for m in mappings:
        iea_sec = m["iea_section"]
        bsa_sec = m["bsa_section"]
        
        if not iea_sec:
            continue
            
        if iea_sec.upper() in {"NOT APPLICABLE", "N/A", "NA", "NEW"}:
            if bsa_sec and bsa_sec.upper() not in {"REMOVED", "N/A", "NA", "-"}:
                bsa_base = str(extract_leading_int(bsa_sec)) if extract_leading_int(bsa_sec) else bsa_sec
                body_text = bsa_dict.get(bsa_base, {}).get("description", "") if bsa_dict else ""
                segmented_desc = segment_bsa_statutory_text(body_text, bsa_sec) if ("(" in bsa_sec or "EXPL" in bsa_sec or "Prov" in bsa_sec) else body_text
                new_bsa_rows.append({
                    "bsa_id": f"BSA_{bsa_sec}",
                    "bsa_base_id": f"BSA_{bsa_base}",
                    "bsa_section": bsa_sec,
                    "description": segmented_desc,
                    "node_type": m.get("node_type", "SECTION"),
                })
            continue

        if not bsa_sec or bsa_sec.upper() in {"REMOVED", "DELETED", "REPEALED"}:
            iea_no_successor.add(f"IEA_{iea_sec}")
            continue
        
        bsa_base = str(extract_leading_int(bsa_sec)) if extract_leading_int(bsa_sec) else bsa_sec
        bsa_body_text = bsa_dict.get(bsa_base, {}).get("description", "") if bsa_dict else ""
        segmented_bsa_desc = segment_bsa_statutory_text(bsa_body_text, bsa_sec) if ("(" in bsa_sec or "EXPL" in bsa_sec or "Prov" in bsa_sec) else ""

        iea_base = str(extract_leading_int(iea_sec)) if extract_leading_int(iea_sec) else iea_sec
        iea_body_text = iea_dict.get(iea_base, {}).get("description", "") if iea_dict else ""
        segmented_iea_desc = segment_iea_statutory_text(iea_body_text, iea_sec) if ("(" in iea_sec or "EXPL" in iea_sec or "Prov" in iea_sec) else ""

        mapping_t = m.get("mapping_type", "ONE_TO_ONE")
        category = m.get("Category", "PLAIN")
        amd_type = "repeal" if category == "REMOVED" else ("addition" if category == "NEW_SECTION" else "substitution")

        pair_rows.append({
            "iea_id": f"IEA_{iea_sec}",
            "iea_description": segmented_iea_desc,
            "bsa_id": f"BSA_{bsa_sec}",
            "bsa_base_id": f"BSA_{bsa_base}",
            "bsa_section": bsa_sec,
            "description": segmented_bsa_desc,
            "note": m["note"],
            "status": STATUS_ACTIVE,
            "mapping_type": mapping_t,
            "official_mapping": True,
            "effective_date": "2024-07-01",
            "mapping_status": STATUS_ACTIVE,
            "amendment_type": amd_type,
            "provenance": "Official BSA Schedule 2023 / Gazette Notification",
        })
    
    with driver.session() as s:
        if new_bsa_rows:
            s.run(
                """
            UNWIND $rows AS row
            OPTIONAL MATCH (baseBsa:LawSection {id: row.bsa_base_id})
            MERGE (b:LawSection {id: row.bsa_id})
            ON CREATE SET b.act = 'BSA',
                          b.section = row.bsa_section,
                          b.title = COALESCE(baseBsa.title, ''),
                          b.description = CASE WHEN row.description <> '' THEN row.description ELSE COALESCE(baseBsa.description, '') END,
                          b.chapter = COALESCE(baseBsa.chapter, ''),
                          b.year = 2023,
                          b.data_complete = True,
                          b.status = 'active'
            SET b.node_type = row.node_type,
                b.description = CASE WHEN row.description <> '' THEN row.description ELSE b.description END,
                b.mapping_status = $status
            """,
                rows=new_bsa_rows,
                status="new_no_iea_predecessor",
            )

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
                          b.description = CASE WHEN row.description <> '' THEN row.description ELSE COALESCE(baseBsa.description, '') END,
                          b.chapter = COALESCE(baseBsa.chapter, ''),
                          b.year = 2023,
                          b.data_complete = True,
                          b.status = 'active'
            SET b.node_type = CASE
              WHEN b.section CONTAINS '(' AND b.section CONTAINS ')' THEN
                CASE WHEN b.section =~ '.*\\([A-Za-z]\\).*' THEN 'CLAUSE' ELSE 'SUBSECTION' END
              ELSE COALESCE(b.node_type, 'SECTION')
            END,
            b.description = CASE WHEN row.description <> '' THEN row.description ELSE b.description END
            MERGE (i)-[r1:REPLACED_BY]->(b)
            SET r1.note = row.note,
                r1.target_section = row.bsa_section,
                r1.status = row.status,
                r1.mapping_type = row.mapping_type,
                r1.official_mapping = row.official_mapping,
                r1.effective_date = row.effective_date,
                r1.mapping_status = row.mapping_status,
                r1.amendment_type = row.amendment_type,
                r1.provenance = row.provenance
            MERGE (b)-[r2:REPLACES]->(i)
            SET r2.note = row.note,
                r2.status = row.status,
                r2.mapping_type = row.mapping_type,
                r2.official_mapping = row.official_mapping,
                r2.effective_date = row.effective_date,
                r2.mapping_status = row.mapping_status,
                r2.amendment_type = row.amendment_type,
                r2.provenance = row.provenance
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
                status="deleted_no_bsa_successor",
            )
    
    print(f"IEA-BSA mapping edges ensured: {len(pair_rows)}")
    print(f"IEA sections without BSA successor: {len(iea_no_successor)}")


def tag_unmapped_sections(driver):
    """
    Tags:
    1. IPC sections without BNS successors -> mapping_status = STATUS_DELETED_NO_BNS ('deleted_no_bns_successor')
    2. BNS sections without IPC predecessors -> mapping_status = STATUS_NEW_NO_IPC ('new_no_ipc_predecessor')
    """
    with driver.session() as s:
        # Fallback node_type harmonization for any remaining null node_types
        s.run("""
            MATCH (n:LawSection) WHERE n.node_type IS NULL
            SET n.node_type = CASE
              WHEN n.section CONTAINS '(' AND n.section CONTAINS ')' THEN
                CASE WHEN n.section =~ '.*\\([A-Za-z]\\).*' THEN 'CLAUSE' ELSE 'SUBSECTION' END
              ELSE 'SECTION'
            END
        """)

        # Tag unmapped IPC sections
        res_ipc = s.run(
            """
            MATCH (i:LawSection {act:'IPC'})
            WHERE NOT (i)-[:REPLACED_BY]->(:LawSection {act:'BNS'})
            SET i.mapping_status = $status
            RETURN count(i) AS c
            """,
            status=STATUS_DELETED_NO_BNS,
        ).single()
        ipc_count = int(res_ipc["c"]) if res_ipc else 0

        # Tag unmapped CrPC sections
        res_crpc = s.run(
            """
            MATCH (c:LawSection {act:'CrPC'})
            WHERE NOT (c)-[:REPLACED_BY]->(:LawSection {act:'BNSS'})
            SET c.mapping_status = $status
            RETURN count(c) AS c
            """,
            status="deleted_no_bnss_successor",
        ).single()
        crpc_count = int(res_crpc["c"]) if res_crpc else 0

        # Tag unmapped BNS sections
        res_bns = s.run(
            """
            MATCH (b:LawSection {act:'BNS'})
            WHERE NOT (b)-[:REPLACES]->(:LawSection {act:'IPC'})
            SET b.mapping_status = $status
            RETURN count(b) AS c
            """,
            status=STATUS_NEW_NO_IPC,
        ).single()
        bns_count = int(res_bns["c"]) if res_bns else 0

        # Count explicit unmapped BNSS sections
        res_bnss = s.run(
            """
            MATCH (b:LawSection {act:'BNSS', mapping_status:'new_no_crpc_predecessor'})
            RETURN count(b) AS c
            """
        ).single()
        bnss_count = int(res_bnss["c"]) if res_bnss else 0

    print(f"IPC sections tagged {STATUS_DELETED_NO_BNS}: {ipc_count}")
    print(f"CrPC sections tagged deleted_no_bnss_successor: {crpc_count}")
    print(f"BNS sections tagged {STATUS_NEW_NO_IPC}: {bns_count}")
    print(f"BNSS sections tagged new_no_crpc_predecessor: {bnss_count}")
    return ipc_count, crpc_count, bns_count, bnss_count


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
        "BNSSection Nodes (Total)": "MATCH (n:BNSSection) RETURN count(n) AS c",
        "  - BNS Base SECTION Nodes": "MATCH (n:BNSSection) WHERE n.node_type = 'SECTION' RETURN count(n) AS c",
        "  - BNS SUBSECTION Nodes": "MATCH (n:BNSSection) WHERE n.node_type = 'SUBSECTION' RETURN count(n) AS c",
        "  - BNS CLAUSE Nodes": "MATCH (n:BNSSection) WHERE n.node_type = 'CLAUSE' RETURN count(n) AS c",
        "  - BNS EXPLANATION Nodes": "MATCH (n:BNSSection) WHERE n.node_type = 'EXPLANATION' RETURN count(n) AS c",
        "GeneratedNode Intermediate Nodes": "MATCH (n:GeneratedNode) RETURN count(n) AS c",
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
        "HAS_SUBSECTION": "MATCH ()-[r:HAS_SUBSECTION]->() RETURN count(r) AS c",
        "HAS_CLAUSE": "MATCH ()-[r:HAS_CLAUSE]->() RETURN count(r) AS c",
        "HAS_EXPLANATION": "MATCH ()-[r:HAS_EXPLANATION]->() RETURN count(r) AS c",
        "DEFINED_BY": "MATCH ()-[r:DEFINED_BY]->() RETURN count(r) AS c",
        "HAS_PUNISHMENT": "MATCH ()-[r:HAS_PUNISHMENT]->() RETURN count(r) AS c",
        "HAS_KEYWORD": "MATCH ()-[r:HAS_KEYWORD]->() RETURN count(r) AS c",
        "Inherited HAS_KEYWORD": "MATCH ()-[r:HAS_KEYWORD]->() WHERE r.inherited = true RETURN count(r) AS c",
        "Inherited HAS_PUNISHMENT": "MATCH ()-[r:HAS_PUNISHMENT]->() WHERE r.inherited = true RETURN count(r) AS c",
        "Inherited DEFINED_BY": "MATCH ()-[r:DEFINED_BY]->() WHERE r.inherited = true RETURN count(r) AS c",
        "Inherited HAS_SECTION": "MATCH ()-[r:HAS_SECTION]->() WHERE r.inherited = true RETURN count(r) AS c",
        "REPLACED_BY": "MATCH ()-[r:REPLACED_BY]->() RETURN count(r) AS c",
        "REPLACED_BY with status": "MATCH ()-[r:REPLACED_BY]->() WHERE r.status IS NOT NULL RETURN count(r) AS c",
        "REPLACES": "MATCH ()-[r:REPLACES]->() RETURN count(r) AS c",
        "REPLACES with status": "MATCH ()-[r:REPLACES]->() WHERE r.status IS NOT NULL RETURN count(r) AS c",
        "Full Content Nodes (data_complete: true)": "MATCH (n:LawSection) WHERE n.data_complete = true RETURN count(n) AS c",
        "Stub Mapping-Only Nodes (data_complete: false)": "MATCH (n:LawSection) WHERE n.data_complete = false RETURN count(n) AS c",
        "  - IPC Stub Nodes": "MATCH (n:LawSection {act:'IPC'}) WHERE n.data_complete = false RETURN count(n) AS c",
        "  - CrPC Stub Nodes": "MATCH (n:LawSection {act:'CrPC'}) WHERE n.data_complete = false RETURN count(n) AS c",
        "  - IEA Stub Nodes": "MATCH (n:LawSection {act:'IEA'}) WHERE n.data_complete = false RETURN count(n) AS c",
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

    print("================================================================================")
    print(" STEP 4 END-TO-END UNIFIED NEO4J INGESTION PIPELINE")
    print("================================================================================")
    print(f"CSV directory: {args.csv_dir.resolve()}")
    print(f"All Acts directory: {ALL_ACTS_DIR.resolve()}")

    # ── STAGE 1: LOAD & PREPROCESS MAPPING FILES ──────────────────────────────
    print("\n--- STAGE 1: Load & Preprocess Mapping Files ---")
    try:
        from preprocess_ipc2bns import run_pipeline
        run_pipeline()
    except Exception as e:
        print(f"Preprocessing check: {e}")

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

        # ── STAGE 2: INGEST ACTS, CHAPTERS, & BASE LAWSECTION NODES ─────────
        print("\n--- STAGE 2: Ingest Acts, Chapters, & Base LawSections ---")
        create_constraints(driver)
        ingest_acts(driver)
        ingest_chapters(driver, bns)
        
        ingest_sections(driver, ipc, bns)
        ingest_procedural_sections(driver, bnss, crpc)
        ingest_evidence_sections(driver, bsa, iea)
        
        ingest_keywords(driver, bns, ipc)
        ingest_crimes(driver, ipc, bns)
        ingest_punishments(driver, ipc, bns)
        
        # ── STAGE 3: CREATE STATUTORY HIERARCHY & RELATIONSHIPS ─────────────
        print("\n--- STAGE 3: Statutory Hierarchy Construction ---")
        ingest_bns_hierarchy_nodes(driver, mappings, bns)
        ingest_bns_hierarchy_relationships(driver, mappings)

        # ── STAGE 5: CREATE IPC<->BNS, CrPC<->BNSS, & IEA<->BSA MAPPINGS ──────
        print("\n--- STAGE 5: Create Cross-Act Mapping Relationships ---")
        ingest_mappings(driver, mappings)
        ingest_crpc_bnss_mappings(driver, crpc_bnss_mappings, bnss)
        ingest_iea_bsa_mappings(driver, iea_bsa_mappings, bsa, iea)
        
        # Connect BNSS & BSA Hierarchy edges after mapping node creation
        ingest_procedural_and_evidence_hierarchy(driver)

        # ── STAGE 4: PROPAGATE STRUCTURAL GRAPH CONTEXT TO CHILD NODES ───────
        print("\n--- STAGE 4: Propagate Structural Context Enrichment ---")
        inherit_structural_context(driver)
        
        tag_unmapped_sections(driver)
        ingest_reasoning_rules(driver)

        # ── STAGE 6: BUILD FULL-TEXT INDEXES & GRAPHRAG RETRIEVAL READINESS ──
        print("\n--- STAGE 6: Build Full-Text Indexes & GraphRAG Readiness ---")
        create_fulltext_indexes(driver)
        print_summary(driver)
    finally:
        driver.close()

    print("\n================================================================================")
    print(" STEP 4 UNIFIED INGESTION PIPELINE COMPLETE")
    print("================================================================================")


if __name__ == "__main__":
    main()