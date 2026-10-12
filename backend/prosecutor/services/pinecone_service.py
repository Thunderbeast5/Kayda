import os
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

env_candidates = [
    Path(__file__).resolve().parents[3] / ".env",
    Path(__file__).resolve().parents[4] / "backend" / ".env",
    Path("backend/.env"),
    Path(".env")
]
for candidate in env_candidates:
    if candidate.exists():
        load_dotenv(candidate)
        break

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "ipc")
PINECONE_HOST = os.getenv("PINECONE_HOST", "")

_pinecone_index = None


class PineconeService:
    """
    PineconeService
    
    Handles vector database querying for Pinecone.
    Only responsible for vector retrieval. No deduplication, verification, or scoring.
    """

    def __init__(self):
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY not set in backend/.env")

    def _get_index(self):
        global _pinecone_index
        if _pinecone_index is None:
            from pinecone import Pinecone
            pc = Pinecone(api_key=PINECONE_API_KEY)
            _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
        return _pinecone_index

    def query_index(self, input_json: Dict[str, Any], top_k: int = 10, namespace: str = "legal_sections") -> Dict[str, Any]:
        """
        Queries Pinecone index for every embedding independently.
        Returns Top 10 most relevant matches, preserving the query association.
        """
        embeddings_list = input_json.get("embeddings") or []
        index = self._get_index()
        retrieval_results = []

        namespaces_to_query = [namespace]
        if namespace != "legal_cases":
            if namespace and namespace != "":
                namespaces_to_query = [namespace, ""]
            else:
                namespaces_to_query = [""]

        for item in embeddings_list:
            query_str = item.get("query") or ""
            vector = item.get("embedding") or []
            
            if not vector:
                continue
                
            try:
                combined_matches_dict = {}
                for ns in namespaces_to_query:
                    query_kwargs = {
                        "vector": vector,
                        "top_k": top_k,
                        "include_metadata": True
                    }
                    if ns:
                        query_kwargs["namespace"] = ns

                    response = index.query(**query_kwargs)
                    raw_matches = response.get("matches") or []

                    for match in raw_matches:
                        m_id = match.get("id") or ""
                        score = float(match.get("score") if match.get("score") is not None else 0.0)
                        if m_id not in combined_matches_dict or score > combined_matches_dict[m_id]["score"]:
                            combined_matches_dict[m_id] = {
                                "id": m_id,
                                "score": score,
                                "metadata": match.get("metadata") or {}
                            }

                sorted_matches = sorted(combined_matches_dict.values(), key=lambda x: x["score"], reverse=True)[:top_k]

                retrieval_results.append({
                    "query": query_str,
                    "matches": sorted_matches
                })
            except Exception as e:
                print(f"[PineconeService] Failed to query Pinecone for query '{query_str}': {e}")
                retrieval_results.append({
                    "query": query_str,
                    "matches": []
                })
                
        return {
            "retrieval_results": retrieval_results
        }
