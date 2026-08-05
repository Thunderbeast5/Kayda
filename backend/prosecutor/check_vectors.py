"""
check_vectors.py
Fetches specific vectors from Pinecone and prints their metadata
so we can see what text was actually indexed.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

for candidate in [
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parents[2] / "backend" / ".env",
    Path(".env"),
]:
    if candidate.exists():
        load_dotenv(candidate)
        break

from pinecone import Pinecone

pc    = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "ipc"))

# Fetch specific IDs to inspect what was indexed
print(f"Index: {os.getenv('PINECONE_INDEX_NAME')}")
stats = index.describe_index_stats()
print(f"Total vectors: {stats.get('total_vector_count')}, Namespaces: {list(stats.get('namespaces', {}).keys())}\n")

# Fetch key sections to inspect metadata
result = index.fetch(ids=["IPC_420", "IPC_405", "IPC_25", "IPC_424"])
vectors = result.get("vectors") or {}
print(f"Fetched {len(vectors)} vectors:")
for vid, data in vectors.items():
    meta = data.get("metadata") or {}
    dim = len(data.get("values") or [])
    print(f"\nID: {vid} (dim={dim})")
    print(f"  metadata keys: {list(meta.keys())}")
    print(f"  title:         {meta.get('title','(empty)')[:80]}")
    print(f"  section_title: {meta.get('section_title','(empty)')[:80]}")
    print(f"  text:          {str(meta.get('text','(empty)'))[:150]}")
    print(f"  description:   {str(meta.get('description','(empty)'))[:150]}")

for vid, data in vectors.items():
    meta = data.get("metadata") or {}
    dim  = len(data.get("values") or [])
    print(f"{'='*60}")
    print(f"ID:          {vid}")
    print(f"Vector dim:  {dim}")
    print(f"act:         {meta.get('act')}")
    print(f"section:     {meta.get('section')}")
    print(f"title:       {meta.get('title')}")
    print(f"description: {str(meta.get('description',''))[:200]}")
    print(f"context_block: {str(meta.get('context_block',''))[:300]}")
    print()
