import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / "backend" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def find_judgment_jsons(base_dir: Path) -> List[Path]:
    """Locates all extracted judgment JSON files across json - Copy and data/legal_cases."""
    paths = []
    json_copy_dir = base_dir / "json - Copy"
    if json_copy_dir.exists():
        for p in json_copy_dir.rglob("*.json"):
            if p.name.startswith("20") and "_INSC_" in p.name:
                paths.append(p)
                
    cases_dir = base_dir / "data" / "legal_cases"
    if cases_dir.exists():
        for p in cases_dir.rglob("*.json"):
            if p.name.startswith("20") and "_INSC_" in p.name:
                paths.append(p)
                
    return sorted(list(set(paths)))


def find_taxonomy_mappings(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Loads taxonomy mappings from segregation - Copy directories."""
    mappings = {}
    seg_dir = base_dir / "segregation - Copy"
    if not seg_dir.exists():
        return mappings

    for p in seg_dir.rglob("classified_taxonomy_*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        cid = item.get("case_id")
                        if cid:
                            mappings[cid] = item
        except Exception as e:
            print(f"[ingest_case_graph] Warning reading taxonomy file {p.name}: {e}", flush=True)
            
    return mappings


def extract_cited_cases(text: str) -> List[str]:
    """Extracts authentic legal citations (Party A v. Party B AIR/SCC/SCR/relied on) from judgment text."""
    if not text:
        return []
    pattern = r'([A-Z][A-Za-z\s\.\&\@]{2,40}\s+(?:v\.|vs\.|VERSUS)\s+[A-Z][A-Za-z\s\.\&\@]{2,40}(?:,?\s+(?:AIR|\(\d{4}\)|\d{4}\s+SCC|\d{4}\s+SCR|SCC|SCR|\d+\s+Supreme)[^\n\.\;]{0,40})?(?:\s*,?\s*(?:referred to|relied on|cited|followed))?)'
    matches = re.findall(pattern, text)
    citations = []
    for m in matches:
        m_clean = re.sub(r'\s+', ' ', m).strip()
        if (" v. " in m_clean or " vs. " in m_clean or " VERSUS " in m_clean) and \
           any(k in m_clean for k in ["AIR", "SCC", "SCR", "Supreme", "Scale", "CrLJ", "referred to", "relied on", "19", "20"]):
            citations.append(m_clean)
    return list(set(citations))[:5]


def parse_case_metadata(json_path: Path, taxonomy_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Extracts clean metadata and relationship entities for Neo4j case graph ingestion."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"[ingest_case_graph] Error reading {json_path}: {e}", flush=True)
        return {}

    cid = raw.get("case_id") or json_path.stem
    tax = taxonomy_map.get(cid) or {}

    title = raw.get("case_title") or tax.get("case_title") or cid
    if not title or title == cid:
        full_text = raw.get("full_text") or ""
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        if len(lines) >= 3:
            title = f"{lines[0]} {lines[1]} {lines[2]}"[:120]
        else:
            title = cid

    year = raw.get("year") or tax.get("decision_date", "")[-4:]
    if not str(year).isdigit():
        parts = cid.split("_")
        year = parts[0] if parts and parts[0].isdigit() else "2006"

    court = raw.get("court") or "Supreme Court of India"
    
    categories = tax.get("primary_categories") or []
    community = categories[0] if categories else "general_offences"

    ipc_sections = raw.get("ipc_sections_referred") or tax.get("ipc_sections") or []
    bns_sections = raw.get("bns_sections_referred") or tax.get("bns_sections") or []
    keywords = raw.get("list_of_keywords") or tax.get("crime_keywords") or []
    
    articles = raw.get("cites_articles") or tax.get("cites_articles") or []
    evidence_types = raw.get("evidence_types") or tax.get("evidence_types") or []
    
    # Precedent citation extraction
    full_text = raw.get("full_text") or raw.get("judgment_text") or ""
    cited_cases = extract_cited_cases(full_text)

    return {
        "case_id": cid,
        "title": title,
        "court": court,
        "year": int(year) if str(year).isdigit() else 2006,
        "community": community,
        "ipc_sections": [str(s).replace("IPC", "").strip() for s in ipc_sections if s],
        "bns_sections": [str(s).replace("BNS", "").strip() for s in bns_sections if s],
        "articles": [str(a) for a in articles if a],
        "evidence_types": [str(e) for e in evidence_types if e],
        "keywords": [str(k) for k in keywords if k],
        "cited_cases": cited_cases
    }


def ingest_case_graph():
    """Builds individual Case nodes and relationships in Neo4j using bulk UNWIND transactions."""
    print("=" * 80, flush=True)
    print("INGESTING CASE GRAPH INTO NEO4J (NODES & RELATIONSHIPS)", flush=True)
    print("=" * 80, flush=True)

    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[Error] Neo4j credentials missing in environment.", flush=True)
        sys.exit(1)

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[Error] neo4j python package missing.", flush=True)
        sys.exit(1)

    json_paths = find_judgment_jsons(BASE_DIR)
    taxonomy_map = find_taxonomy_mappings(BASE_DIR)
    print(f"Found {len(json_paths)} judgment JSONs for graph ingestion.", flush=True)

    cases_data = []
    for jpath in json_paths:
        parsed = parse_case_metadata(jpath, taxonomy_map)
        if parsed and parsed.get("case_id"):
            cases_data.append(parsed)

    print(f"Parsed {len(cases_data)} cases ready for Neo4j ingestion.", flush=True)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session(database=NEO4J_DATABASE) as session:
        # 1. Ensure Constraints & Indexes
        try:
            session.run("CREATE CONSTRAINT case_id_unique IF NOT EXISTS FOR (c:Case) REQUIRE c.case_id IS UNIQUE")
            session.run("CREATE CONSTRAINT court_name_unique IF NOT EXISTS FOR (crt:Court) REQUIRE crt.name IS UNIQUE")
            session.run("CREATE CONSTRAINT keyword_name_unique IF NOT EXISTS FOR (kw:Keyword) REQUIRE kw.name IS UNIQUE")
        except Exception as e:
            print(f"  [Constraint Info] {e}", flush=True)

        # 2. Bulk MERGE Case nodes
        print("[1/7] Bulk upserting Case nodes...", flush=True)
        session.run("""
            UNWIND $batch AS item
            MERGE (c:Case {case_id: item.case_id})
            SET c.title = item.title,
                c.court = item.court,
                c.year = item.year
        """, batch=cases_data)

        # 3. DECIDED_BY Court
        print("[2/7] Linking DECIDED_BY Court relationships...", flush=True)
        session.run("""
            UNWIND $batch AS item
            MATCH (c:Case {case_id: item.case_id})
            MERGE (crt:Court {name: item.court})
            MERGE (c)-[:DECIDED_BY]->(crt)
        """, batch=cases_data)

        # 4. BELONGS_TO Community
        print("[3/7] Linking BELONGS_TO Community relationships...", flush=True)
        session.run("""
            UNWIND $batch AS item
            MATCH (c:Case {case_id: item.case_id})
            MERGE (comm:Community {community_id: item.community})
            MERGE (c)-[:BELONGS_TO]->(comm)
        """, batch=cases_data)

        # 5. APPLIES_SECTION (IPC & BNS)
        print("[4/7] Linking APPLIES_SECTION LawSection relationships...", flush=True)
        session.run("""
            UNWIND $batch AS item
            MATCH (c:Case {case_id: item.case_id})
            FOREACH (sec IN item.ipc_sections |
                MERGE (l1:LawSection {act: 'IPC', section: sec})
                MERGE (c)-[:APPLIES_SECTION]->(l1)
            )
            FOREACH (sec IN item.bns_sections |
                MERGE (l2:LawSection {act: 'BNS', section: sec})
                MERGE (c)-[:APPLIES_SECTION]->(l2)
            )
        """, batch=cases_data)

        # 6. CITES_ARTICLE & USES_EVIDENCE & HAS_KEYWORD
        print("[5/7] Linking Articles, Evidence, and Keyword relationships...", flush=True)
        session.run("""
            UNWIND $batch AS item
            MATCH (c:Case {case_id: item.case_id})
            FOREACH (art IN item.articles |
                MERGE (a:ConstitutionalArticle {article: art})
                MERGE (c)-[:CITES_ARTICLE]->(a)
            )
            FOREACH (ev IN item.evidence_types |
                MERGE (e:EvidenceType {name: ev})
                MERGE (c)-[:USES_EVIDENCE]->(e)
            )
            FOREACH (kw IN item.keywords |
                MERGE (k:Keyword {name: kw})
                MERGE (c)-[:HAS_KEYWORD]->(k)
            )
        """, batch=cases_data)

        # 7. CITES_CASE Precedent Chain Relationships
        print("[6/7] Linking CITES_CASE Precedent Chain relationships...", flush=True)
        session.run("""
            UNWIND $batch AS item
            MATCH (c:Case {case_id: item.case_id})
            FOREACH (cited IN item.cited_cases |
                MERGE (ref:Case {title: cited})
                MERGE (c)-[:CITES_CASE]->(ref)
            )
        """, batch=cases_data)

        # 8. Stats Summary
        case_count = session.run("MATCH (c:Case) RETURN count(c) AS count").single()["count"]
        rels_summary = session.run("""
            MATCH (c:Case)-[r]->()
            RETURN type(r) AS type, count(r) AS count
        """)
        
        print("\n" + "=" * 80, flush=True)
        print("NEO4J CASE GRAPH INGESTION COMPLETE", flush=True)
        print("=" * 80, flush=True)
        print(f"Total Case Nodes: {case_count}", flush=True)
        print("Relationships Breakdown:", flush=True)
        for r in rels_summary:
            print(f"  - {r['type']}: {r['count']}", flush=True)
        print("=" * 80 + "\n", flush=True)

    driver.close()


if __name__ == "__main__":
    ingest_case_graph()
