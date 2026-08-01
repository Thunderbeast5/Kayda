import os
import sys
import json
import glob
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / "backend" / ".env")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "cases")


def find_judgment_jsons(base_dir: Path) -> List[Path]:
    """Locates all extracted judgment JSON files across json - Copy and data/legal_cases."""
    paths = []
    
    # 1. Look in json - Copy
    json_copy_dir = base_dir / "json - Copy"
    if json_copy_dir.exists():
        for p in json_copy_dir.rglob("*.json"):
            if p.name.startswith("20") and "_INSC_" in p.name:
                paths.append(p)
                
    # 2. Look in data/legal_cases
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
            print(f"[ingest_cases] Warning reading taxonomy file {p.name}: {e}")
            
    return mappings


def extract_case_fields(json_path: Path, taxonomy_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Parses judgment JSON and taxonomy data into structured format for embedding."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"[ingest_cases] Error reading {json_path}: {e}")
        return {}

    case_id = raw_data.get("case_id") or json_path.stem
    tax = taxonomy_map.get(case_id) or {}

    title = raw_data.get("case_title") or tax.get("case_title") or case_id
    if not title or title == case_id:
        # Extract title from full_text head if available
        full_text = raw_data.get("full_text") or ""
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        if len(lines) >= 3:
            title = f"{lines[0]} {lines[1]} {lines[2]}"[:120]
        else:
            title = case_id

    year = raw_data.get("year") or tax.get("decision_date", "")[-4:]
    if not year or not year.isdigit():
        parts = case_id.split("_")
        year = parts[0] if parts and parts[0].isdigit() else "2006"

    court = raw_data.get("court") or "Supreme Court of India"
    judges = raw_data.get("judges") or tax.get("judges") or []
    
    # Text fields for embedding
    facts = raw_data.get("facts") or raw_data.get("case_arising_from") or raw_data.get("issue_for_consideration") or ""
    issues = raw_data.get("issues") or raw_data.get("issue_for_consideration") or ""
    headnotes = raw_data.get("headnotes") or ""
    reasoning = raw_data.get("reasoning") or headnotes
    summary = raw_data.get("judgment_summary") or raw_data.get("summary") or headnotes or issues
    
    keywords = raw_data.get("list_of_keywords") or tax.get("crime_keywords") or []
    ipc_sections = raw_data.get("ipc_sections_referred") or tax.get("ipc_sections") or []
    bns_sections = raw_data.get("bns_sections_referred") or tax.get("bns_sections") or []

    categories = tax.get("primary_categories") or []
    community = categories[0] if categories else "general_offences"
    crime_type = ", ".join(categories) if categories else "criminal_offence"

    # Construct rich embedding text (NOT entire PDF text)
    embed_text_parts = [
        f"Case Title: {title}",
        f"Court: {court} ({year})",
        f"Crime Community: {community}",
        f"Applicable IPC Sections: {', '.join(ipc_sections)}",
        f"Applicable BNS Sections: {', '.join(bns_sections)}",
        f"Keywords: {', '.join(keywords)}",
        f"Facts: {facts[:500]}",
        f"Issues: {issues[:500]}",
        f"Reasoning: {reasoning[:800]}",
        f"Summary: {summary[:500]}"
    ]
    embedding_text = "\n".join([p for p in embed_text_parts if p.strip()])

    return {
        "case_id": case_id,
        "case_name": title,
        "court": court,
        "year": int(year) if str(year).isdigit() else 2006,
        "community": community,
        "crime_type": crime_type,
        "ipc_sections": ipc_sections,
        "bns_sections": bns_sections,
        "keywords": keywords,
        "facts": facts[:1000],
        "reasoning": reasoning[:1000],
        "judgment_summary": summary[:1000],
        "embedding_text": embedding_text
    }


def ingest_cases(batch_size: int = 50):
    """Main execution for generating case embeddings and uploading to Pinecone namespace `legal_cases`."""
    print("=" * 80)
    print("INGESTING CASE EMBEDDINGS INTO PINECONE (NAMESPACE: legal_cases)")
    print("=" * 80)

    if not PINECONE_API_KEY:
        print("[Error] PINECONE_API_KEY not found in environment.")
        sys.exit(1)

    try:
        from sentence_transformers import SentenceTransformer
        from pinecone import Pinecone
    except ImportError as e:
        print(f"[Error] Required dependency missing: {e}")
        sys.exit(1)

    print("[1/4] Scanning judgment JSONs and taxonomy classifications...")
    json_paths = find_judgment_jsons(BASE_DIR)
    taxonomy_map = find_taxonomy_mappings(BASE_DIR)
    print(f"Found {len(json_paths)} judgment JSONs and {len(taxonomy_map)} taxonomy records.")

    if not json_paths:
        print("No judgment JSONs found. Check directory paths.")
        return

    print("[2/4] Initializing SentenceTransformer model 'all-MiniLM-L6-v2'...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"[3/4] Connecting to Pinecone Index '{PINECONE_INDEX_NAME}'...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    print(f"[4/4] Processing and upserting in batches of {batch_size}...")
    
    vectors_to_upsert = []
    total_upserted = 0

    for idx, jpath in enumerate(json_paths, 1):
        case_info = extract_case_fields(jpath, taxonomy_map)
        if not case_info or not case_info.get("embedding_text"):
            continue

        embed_text = case_info.pop("embedding_text")
        vector = model.encode(embed_text, convert_to_numpy=True).tolist()

        # Metadata dictionary clean-up for Pinecone storage
        meta = {
            "case_id": str(case_info["case_id"]),
            "case_name": str(case_info["case_name"]),
            "court": str(case_info["court"]),
            "year": int(case_info["year"]),
            "community": str(case_info["community"]),
            "crime_type": str(case_info["crime_type"]),
            "ipc_sections": [str(s) for s in case_info["ipc_sections"]],
            "bns_sections": [str(s) for s in case_info["bns_sections"]],
            "keywords": [str(k) for k in case_info["keywords"]],
            "facts": str(case_info["facts"]),
            "reasoning": str(case_info["reasoning"]),
            "judgment_summary": str(case_info["judgment_summary"])
        }

        vectors_to_upsert.append({
            "id": case_info["case_id"],
            "values": vector,
            "metadata": meta
        })

        if len(vectors_to_upsert) >= batch_size:
            index.upsert(vectors=vectors_to_upsert, namespace="legal_cases")
            total_upserted += len(vectors_to_upsert)
            print(f"  Upserted {total_upserted} / {len(json_paths)} case embeddings...", flush=True)
            vectors_to_upsert = []

    if vectors_to_upsert:
        index.upsert(vectors=vectors_to_upsert, namespace="legal_cases")
        total_upserted += len(vectors_to_upsert)

    print("=" * 80, flush=True)
    print(f"SUCCESS: Ingested {total_upserted} judgment embeddings into namespace 'legal_cases'.", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    ingest_cases()
