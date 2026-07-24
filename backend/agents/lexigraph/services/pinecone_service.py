import os
from typing import Dict, Any, List

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = "legal-embeddings"

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

    def query_index(self, input_json: Dict[str, Any], top_k: int = 10) -> Dict[str, Any]:
        """
        Queries Pinecone index for every embedding independently.
        Returns Top 10 most relevant matches, preserving the query association.
        """
        embeddings_list = input_json.get("embeddings") or []
        index = self._get_index()
        retrieval_results = []

        for item in embeddings_list:
            query_str = item.get("query") or ""
            vector = item.get("embedding") or []
            
            if not vector:
                continue
                
            try:
                response = index.query(
                    vector=vector,
                    top_k=top_k,
                    include_metadata=True
                )
                
                raw_matches = response.get("matches") or []
                matches = []
                for match in raw_matches:
                    matches.append({
                        "id": match.get("id") or "",
                        "score": float(match.get("score") if match.get("score") is not None else 0.0),
                        "metadata": match.get("metadata") or {}
                    })
                    
                retrieval_results.append({
                    "query": query_str,
                    "matches": matches
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
