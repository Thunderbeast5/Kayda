"""
LexiGraph / MootCourt — Case Judgments Pinecone Ingest v2
=========================================================
Standalone embedding & upsert script for case judgments (pinecone_documents.json).
Cleans null/None metadata values before sending to Pinecone.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------
# Paths / Env Setup
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

env_candidates = [
    BASE_DIR.parent / ".env",
    BASE_DIR.parent.parent / ".env",
    BASE_DIR / ".env",
    Path(".env"),
]
ENV_PATH = next((c for c in env_candidates if c.exists()), None)

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH) if ENV_PATH else load_dotenv()
except ImportError:
    pass

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_HOST_2 = "https://cases-9zoq3sm.svc.aped-4627-b74a.pinecone.io"
DEFAULT_INDEX_NAME = "cases"
DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 384-dim embedding model
DEFAULT_JSON_FILE = BASE_DIR / "pinecone_documents.json"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def clean_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Pinecone rejects null/None values.
    Recursively converts None values to empty strings or lists of strings.
    """
    cleaned = {}
    for k, v in meta.items():
        if v is None:
            cleaned[k] = ""
        elif isinstance(v, list):
            # Pinecone expects lists to contain only strings
            cleaned[k] = [str(item) for item in v if item is not None]
        else:
            cleaned[k] = v
    return cleaned


def load_documents(json_path: Path) -> list[dict]:
    if not json_path.exists():
        print(f"Error: Document file not found at {json_path}")
        print("Please run your case generation script (case.py) first.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"Loaded {len(docs)} case documents from {json_path.name}")
    return docs


# ----------------------------------------------------------------------
# Pinecone Setup
# ----------------------------------------------------------------------
def get_pinecone_client():
    from pinecone import Pinecone
    if not PINECONE_API_KEY:
        raise ValueError(f"PINECONE_API_KEY not found in environment (checked {ENV_PATH})")
    return Pinecone(api_key=PINECONE_API_KEY)


def ensure_index(pc, index_name: str, host: str | None, dimension: int, wipe: bool):
    from pinecone import ServerlessSpec

    if host:
        print(f"Connecting directly to index '{index_name}' via host: {host}")
        return pc.Index(name=index_name, host=host)

    existing = [idx.name for idx in pc.list_indexes()]

    if wipe and index_name in existing:
        print(f"--wipe flag active: Deleting index '{index_name}'...")
        pc.delete_index(index_name)
        existing.remove(index_name)

    if index_name not in existing:
        print(f"Creating Pinecone index '{index_name}' (dim={dimension})...")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    return pc.Index(index_name)


# ----------------------------------------------------------------------
# Embedding & Upload Execution
# ----------------------------------------------------------------------
def run_embedding(
    documents: list[dict],
    model_name: str,
    index_name: str,
    host: str | None,
    wipe: bool,
    batch_size: int,
) -> int:
    from sentence_transformers import SentenceTransformer

    print(f"\nLoading embedding model: {model_name}...")
    model = SentenceTransformer(model_name)
    dimension = model.get_sentence_embedding_dimension()
    print(f"Model loaded successfully. Vector dimension: {dimension}")

    pc = get_pinecone_client()
    index = ensure_index(pc, index_name, host, dimension, wipe)

    vectors = []
    uploaded = 0
    total = len(documents)

    print(f"\nStarting embedding generation for {total} documents...")

    for doc in documents:
        doc_id = str(doc["id"])
        text = doc["text"]
        
        # Extract and sanitize metadata to remove None/null values
        raw_metadata = doc.get("metadata", {})
        raw_metadata["text"] = text
        metadata = clean_metadata(raw_metadata)

        # Generate actual vector representation (384-dim)
        embedding = model.encode(text).tolist()

        vectors.append({
            "id": doc_id,
            "values": embedding,
            "metadata": metadata
        })

        # Batch upload
        if len(vectors) >= batch_size:
            index.upsert(vectors=vectors)
            uploaded += len(vectors)
            print(f"  Upserted {uploaded}/{total} vectors...")
            vectors.clear()

    # Flush remaining vectors
    if vectors:
        index.upsert(vectors=vectors)
        uploaded += len(vectors)

    print(f"\nDone: Successfully upserted {uploaded} vectors into index '{index_name}'.")
    return uploaded


# ----------------------------------------------------------------------
# Main CLI Interface
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="LexiGraph Judgment/Case Pinecone Ingestion Script")
    parser.add_argument(
        "--json-file",
        type=Path,
        default=DEFAULT_JSON_FILE,
        help=f"Path to JSON documents file (default: {DEFAULT_JSON_FILE})",
    )
    parser.add_argument(
        "--index-name",
        default=DEFAULT_INDEX_NAME,
        help=f"Pinecone index name (default: {DEFAULT_INDEX_NAME})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Direct Pinecone host URL (e.g. PINECONE_HOST_2)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"SentenceTransformer model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete and recreate index before embedding (ignored if --host is specified)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for vector upserts (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect documents and payload structure without generating vectors or calling API",
    )
    args = parser.parse_args()

    print(f"JSON File Path: {args.json_file}")
    documents = load_documents(args.json_file)

    if args.dry_run:
        print(f"\n--dry-run set: Loaded {len(documents)} total case documents.")
        if documents:
            sample = documents[0]
            print("\nSample Document ID:", sample.get("id"))
            print("\nSample Metadata (before clean):", sample.get("metadata"))
            print("Sample Metadata (after clean):", clean_metadata(sample.get("metadata", {})))
        return

    run_embedding(
        documents=documents,
        model_name=args.model,
        index_name=args.index_name,
        host=args.host,
        wipe=args.wipe,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()