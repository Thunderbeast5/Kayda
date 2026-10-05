"""
ingest_precedent.py
===================
Offline Precedent & Holding Ingestion Pipeline
Turns Supreme Court judgments (e.g. Srikant Upadhyay, 2024 INSC 202)
into retrievable holdings:
1. LLM extraction of Holding(id, case, para, principle, conditions, effect) per paragraph group.
2. Embedding of (principle + conditions) into Pinecone (indexes: 'precedents' [1024-dim] & 'ipc-index' [384-dim]).
3. Neo4j graph edge creation: (Case) -> [:HAS_HOLDING] -> (Holding) -> [:APPLIES_SECTION] -> (CrPC Section 438 / 82).
4. Local persistence into data/precedents/holdings.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
if str(BASE_DIR / "agents") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "agents"))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")


# ── Holding Schema ────────────────────────────────────────────────────────────

class Holding(BaseModel):
    id: str            # e.g., "srikant_para23"
    case: str          # e.g., "Srikant Upadhyay v. State of Bihar, 2024 INSC 202"
    para: str          # e.g., "23" or "24-25"
    principle: str     # one-sentence legal rule
    conditions: str    # when it applies
    effect: str        # favours_denial / favours_grant / procedural


# ── Text Extraction from Judgment PDF ─────────────────────────────────────────

def extract_judgment_text(pdf_path: Path) -> str:
    """Extract raw text from PDF judgment using pypdf."""
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    pages_text = []
    for page in reader.pages:
        t = page.extract_text() or ""
        pages_text.append(t)
    return "\n\n".join(pages_text).strip()


def parse_paragraph_groups(full_text: str, group_size: int = 2) -> List[Dict[str, Any]]:
    """
    Split judgment text into numbered paragraph groups for focused LLM extraction.
    """
    # Regex split on paragraph numbers like "\n1. ", "\n2. ", "\n24. "
    raw_paras = re.split(r"\n(?=\d{1,2}\.\s)", full_text)
    
    parsed = []
    for p in raw_paras:
        p_clean = p.strip()
        if not p_clean:
            continue
        # Extract paragraph number
        m = re.match(r"^(\d{1,2})\.\s*", p_clean)
        num = m.group(1) if m else "intro"
        parsed.append({"num": num, "text": p_clean})

    # Group adjacent paragraphs into logical batches
    groups = []
    i = 0
    while i < len(parsed):
        batch = parsed[i : i + group_size]
        para_label = "-".join([b["num"] for b in batch])
        combined_text = "\n\n".join([b["text"] for b in batch])
        groups.append({"para_range": para_label, "text": combined_text})
        i += group_size

    return groups


# ── LLM Extraction Pass ───────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are an expert Supreme Court researcher analyzing an Indian criminal appeal judgment.

CASE CITATION:
{case_citation}

PARAGRAPH GROUP:
Paragraphs: {para_range}
------------------------
{text}
------------------------

TASK:
Extract operative legal holdings from this paragraph group.
Do NOT extract mere factual background, procedural histories of parties, or formal appearances.
Extract ONLY substantive legal rules, ratios, interpretations of statutes (e.g. Section 438 CrPC, Section 82 CrPC),
or binding principles established by the Court.

If this paragraph group contains NO binding legal holding or statutory interpretation, return an EMPTY list: [].

For each operative legal rule, return JSON matching this schema:
[
  {{
    "id": "{case_slug}_para{para_range}",
    "case": "{case_citation}",
    "para": "{para_range}",
    "principle": "One-sentence authoritative legal rule formulated or affirmed by the court",
    "conditions": "Specific factual or procedural conditions under which this principle applies",
    "effect": "favours_denial" | "favours_grant" | "procedural"
  }}
]

Return ONLY valid JSON (no markdown fences, no explanation).
"""


def extract_holdings_from_judgment(
    pdf_path: Path,
    case_citation: str = "Srikant Upadhyay v. State of Bihar, 2024 INSC 202",
    case_slug: str = "srikant",
) -> List[Holding]:
    """Run an LLM extraction pass over paragraph groups of the judgment."""
    from config.llm_config import get_llm
    llm = get_llm(temperature=0)

    print(f"[PrecedentIngest] Extracting text from {pdf_path.name}...")
    full_text = extract_judgment_text(pdf_path)
    groups = parse_paragraph_groups(full_text, group_size=2)
    print(f"[PrecedentIngest] Split judgment into {len(groups)} paragraph groups. Extracting holdings...")

    all_holdings: List[Holding] = []
    seen_principles = set()

    for idx, grp in enumerate(groups, 1):
        # Skip introductory headers with no paragraphs
        if grp["para_range"] == "intro" and len(grp["text"]) < 500:
            continue

        prompt = EXTRACTION_PROMPT.format(
            case_citation=case_citation,
            para_range=grp["para_range"],
            case_slug=case_slug,
            text=grp["text"][:4000],
        )

        try:
            resp = llm.invoke(prompt)
            cleaned = re.sub(r"^```(?:json)?|```$", "", resp.content.strip(), flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
            if isinstance(data, list):
                for item in data:
                    principle = item.get("principle", "").strip()
                    if principle and principle.lower() not in seen_principles:
                        seen_principles.add(principle.lower())
                        holding = Holding(
                            id=item.get("id") or f"{case_slug}_para{grp['para_range']}",
                            case=case_citation,
                            para=str(item.get("para") or grp["para_range"]),
                            principle=principle,
                            conditions=item.get("conditions", "").strip(),
                            effect=item.get("effect", "procedural").strip().lower(),
                        )
                        all_holdings.append(holding)
                        print(f"  [OK] [{holding.id}] ({holding.effect}): {holding.principle[:90]}...")
        except Exception as exc:
            print(f"  [Warn] Para group {grp['para_range']} extraction error: {exc}")

    print(f"[PrecedentIngest] Total extracted holdings: {len(all_holdings)}")
    return all_holdings


# ── Pinecone Embedding & Upsert ───────────────────────────────────────────────

def embed_holdings_to_pinecone(holdings: List[Holding]):
    """
    Embed principle + conditions into Pinecone.
    Upserts to 'precedents' index (1024-dim) and 'ipc-index' (384-dim, namespace: 'holdings').
    """
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        print("[PrecedentIngest] PINECONE_API_KEY not found in environment. Skipping Pinecone.")
        return

    from pinecone import Pinecone
    pc = Pinecone(api_key=api_key)

    texts_to_embed = [f"{h.principle} Conditions: {h.conditions}" for h in holdings]
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    # 1. Upsert into 'precedents' index (dimension 1024)
    if "precedents" in existing_indexes:
        print("[PrecedentIngest] Generating 1024-dim embeddings via Pinecone inference (multilingual-e5-large)...")
        try:
            emb_res = pc.inference.embed(
                model="multilingual-e5-large",
                inputs=texts_to_embed,
                parameters={"input_type": "passage", "truncate": "END"},
            )
            vectors_1024 = []
            for h, vec_item in zip(holdings, emb_res):
                vectors_1024.append({
                    "id": h.id,
                    "values": vec_item["values"],
                    "metadata": {
                        "id": h.id,
                        "case": h.case,
                        "para": h.para,
                        "principle": h.principle,
                        "conditions": h.conditions,
                        "effect": h.effect,
                        "text": f"{h.principle} (Conditions: {h.conditions})",
                        "type": "holding",
                    },
                })
            idx_prec = pc.Index("precedents")
            # Upsert into both default namespace and units namespace
            idx_prec.upsert(vectors=vectors_1024)
            idx_prec.upsert(vectors=vectors_1024, namespace="units")
            print(f"[PrecedentIngest] Successfully upserted {len(vectors_1024)} holdings into 'precedents' index.")
        except Exception as e:
            print(f"[PrecedentIngest] Upsert to 'precedents' error: {e}")

    # 2. Upsert into 'ipc-index' (dimension 384, namespace: 'holdings')
    if "ipc-index" in existing_indexes:
        print("[PrecedentIngest] Generating 384-dim embeddings via SentenceTransformers (all-MiniLM-L6-v2)...")
        try:
            from sentence_transformers import SentenceTransformer
            embedder = SentenceTransformer("all-MiniLM-L6-v2")
            vectors_384 = embedder.encode(texts_to_embed).tolist()
            records_384 = []
            for h, vec in zip(holdings, vectors_384):
                records_384.append({
                    "id": h.id,
                    "values": vec,
                    "metadata": {
                        "id": h.id,
                        "case": h.case,
                        "para": h.para,
                        "principle": h.principle,
                        "conditions": h.conditions,
                        "effect": h.effect,
                        "text": f"{h.principle} (Conditions: {h.conditions})",
                        "type": "holding",
                    },
                })
            idx_ipc = pc.Index("ipc-index")
            idx_ipc.upsert(vectors=records_384, namespace="holdings")
            idx_ipc.upsert(vectors=records_384, namespace="legal_cases")
            print(f"[PrecedentIngest] Successfully upserted {len(records_384)} holdings into 'ipc-index' (namespaces: holdings, legal_cases).")
        except Exception as e:
            print(f"[PrecedentIngest] Upsert to 'ipc-index' error: {e}")


# ── Neo4j Graph Ingestion ─────────────────────────────────────────────────────

def ingest_holdings_to_neo4j(
    holdings: List[Holding],
    case_id: str = "srikant_upadhyay_2024",
    case_title: str = "Srikant Upadhyay v. State of Bihar",
    citation: str = "2024 INSC 202",
    year: int = 2024,
):
    """
    Add graph edges:
    (c:Case) -> [:HAS_HOLDING] -> (h:Holding) -> [:APPLIES_SECTION] -> (s:CrPCSection / LawSection)
    """
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    pwd = os.getenv("NEO4J_PASSWORD")
    db = os.getenv("NEO4J_DATABASE", "neo4j")

    if not uri or not user or not pwd:
        print("[PrecedentIngest] Neo4j credentials not configured. Skipping Neo4j ingestion.")
        return

    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    with driver.session(database=db) as session:
        print("[PrecedentIngest] Upserting Case and Holding nodes into Neo4j...")
        
        # 1. Create/Merge Case node
        session.run("""
            MERGE (c:Case {case_id: $case_id})
            SET c.title = $title,
                c.citation = $citation,
                c.year = $year,
                c.court = 'Supreme Court of India'
        """, case_id=case_id, title=case_title, citation=citation, year=year)

        # 2. Create Holding nodes and connect to Case
        for h in holdings:
            session.run("""
                MATCH (c:Case {case_id: $case_id})
                MERGE (hold:Holding {id: $hid})
                SET hold.case = $case,
                    hold.para = $para,
                    hold.principle = $principle,
                    hold.conditions = $conditions,
                    hold.effect = $effect
                MERGE (c)-[:HAS_HOLDING]->(hold)
            """, case_id=case_id, hid=h.id, case=h.case, para=h.para,
                 principle=h.principle, conditions=h.conditions, effect=h.effect)

        # 3. Connect Holdings to relevant CrPC / BNSS / IPC Sections
        # Srikant Upadhyay directly interprets CrPC 438, CrPC 82, BNSS 482, BNSS 84
        session.run("""
            MATCH (c:Case {case_id: $case_id})-[:HAS_HOLDING]->(h:Holding)
            
            // Link to CrPC 438 / BNSS 482
            MERGE (s438:LawSection {act: 'CrPC', section: '438'})
            MERGE (h)-[:APPLIES_SECTION]->(s438)
            
            // Link to CrPC 82 / BNSS 84 (Proclamation)
            MERGE (s82:LawSection {act: 'CrPC', section: '82'})
            MERGE (h)-[:APPLIES_SECTION]->(s82)
            
            // Link to StatutoryProvision nodes if they exist
            WITH h
            OPTIONAL MATCH (sp438:StatutoryProvision {section: '438'})
            FOREACH (_ IN CASE WHEN sp438 IS NOT NULL THEN [1] ELSE [] END |
                MERGE (h)-[:INTERPRETS_PROVISION]->(sp438)
            )
            OPTIONAL MATCH (sp82:StatutoryProvision {section: '82'})
            FOREACH (_ IN CASE WHEN sp82 IS NOT NULL THEN [1] ELSE [] END |
                MERGE (h)-[:INTERPRETS_PROVISION]->(sp82)
            )
        """, case_id=case_id)

        print("[PrecedentIngest] Successfully linked (Case) -> [:HAS_HOLDING] -> (Holding) -> [:APPLIES_SECTION] -> (Sections) in Neo4j.")

    driver.close()


# ── Local File Persistence ────────────────────────────────────────────────────

def save_holdings_to_disk(holdings: List[Holding], out_path: Path):
    """Save extracted holdings to JSON file for offline inspection and pipeline access."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = [h.model_dump() for h in holdings]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"[PrecedentIngest] Saved {len(holdings)} holdings to {out_path}")


# ── Main CLI Runner ───────────────────────────────────────────────────────────

def run_ingest(
    pdf_path: str = "c:/proj/MootCourt/data/fir/2024 INSC 202.pdf",
    case_citation: str = "Srikant Upadhyay v. State of Bihar, 2024 INSC 202",
    case_slug: str = "srikant",
):
    p = Path(pdf_path)
    if not p.exists():
        # Check fallback
        alt_path = BASE_DIR.parent / "data" / "fir" / p.name
        if alt_path.exists():
            p = alt_path
        else:
            raise FileNotFoundError(f"Judgment file not found at: {pdf_path}")

    print("=" * 70)
    print(f"[PrecedentIngest] STARTING INGESTION FOR: {case_citation}")
    print(f"[PrecedentIngest] File: {p}")
    print("=" * 70)

    # 1. LLM extraction
    holdings = extract_holdings_from_judgment(
        pdf_path=p,
        case_citation=case_citation,
        case_slug=case_slug,
    )

    if not holdings:
        print("[PrecedentIngest] No holdings extracted. Exiting.")
        return

    # 2. Local disk persistence
    out_file = BASE_DIR / "data" / "precedents" / f"holdings_{case_slug}.json"
    save_holdings_to_disk(holdings, out_file)

    # 3. Pinecone vector embedding
    embed_holdings_to_pinecone(holdings)

    # 4. Neo4j graph relationships
    ingest_holdings_to_neo4j(
        holdings=holdings,
        case_id=f"{case_slug}_2024",
        case_title=case_citation.split(",")[0].strip(),
        citation="2024 INSC 202",
        year=2024,
    )

    print("=" * 70)
    print(f"[PrecedentIngest] INGESTION COMPLETE FOR {case_citation}")
    print(f"Total Holdings: {len(holdings)}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest judicial precedents into retrievable holdings")
    parser.add_argument("pdf", nargs="?", default="c:/proj/MootCourt/data/fir/2024 INSC 202.pdf", help="Path to judgment PDF")
    parser.add_argument("--citation", default="Srikant Upadhyay v. State of Bihar, 2024 INSC 202", help="Case Citation")
    parser.add_argument("--slug", default="srikant", help="Case slug for holding IDs")
    args = parser.parse_args()

    run_ingest(pdf_path=args.pdf, case_citation=args.citation, case_slug=args.slug)
