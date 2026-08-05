import os
from pathlib import Path
from typing import Dict, Any, List, Optional
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

PINECONE_API_KEY    = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "ipc-2")
PINECONE_HOST       = os.getenv("PINECONE_HOST", "")

_pinecone_index = None


class PineconeService:
    """
    PineconeService

    Handles vector-database querying against the IPC-only Pinecone index.
    Responsibilities: vector retrieval only.
    No deduplication, verification, scoring, or type-routing logic here.

    Key design notes
    ----------------
    * act_filter is applied by ID prefix AFTER retrieval so we don't need a
      metadata "act" field in the index.  With the IPC-only index the prefix
      is always "IPC_", but the parameter is kept for forward compatibility.

    * The `query` key in every result dict is the STRIPPED form of the input
      query string (matching EmbeddingService's contract) so that callers can
      build sq_type_by_query lookups that always hit.

    * Namespace strategy: the service queries both the named namespace and the
      default ("") namespace and takes the best score per vector ID, then
      re-caps at top_k.  This handles indices where some vectors live in the
      named namespace and others were inserted without one.
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

    def query_index(
        self,
        input_json: Dict[str, Any],
        top_k: int = 10,
        namespace: str = "legal_sections",
        act_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queries the Pinecone index for every embedding independently.

        Parameters
        ----------
        input_json : dict
            Must contain an "embeddings" list where each item has:
              - "query"     : str  (stripped, matches EmbeddingService output)
              - "embedding" : list[float]
            Any item also containing a "sub_query_type" key will have that
            field forwarded into the result so the agent can use it for
            dominant-type resolution without re-doing the lookup.

        act_filter : str | None
            If provided (e.g. "IPC"), only vector IDs whose uppercased form
            starts with "<ACT>_" are kept.  Applied after namespace merging
            and before the final top_k cap.

        Returns
        -------
        dict with key "retrieval_results": list of
            {
              "query"        : str,
              "sub_query_type": str,   # forwarded from input if present
              "matches"      : [{"id", "score", "metadata"}]
            }
        """
        embeddings_list: List[Dict[str, Any]] = input_json.get("embeddings") or []
        index = self._get_index()
        retrieval_results: List[Dict[str, Any]] = []

        # Build the namespace list to query for this index.
        # Always include both the named namespace and the default ("") namespace
        # so that vectors inserted either way are found.
        if namespace:
            namespaces_to_query = [namespace, ""]
        else:
            namespaces_to_query = [""]

        prefix = (act_filter.upper() + "_") if act_filter else None

        for item in embeddings_list:
            # Use the stripped query string — guaranteed to match sq_type_by_query keys
            query_str: str = str(item.get("query") or "").strip()
            vector: List[float] = item.get("embedding") or []
            forwarded_type: str = item.get("sub_query_type", "OFFENCE")

            if not vector:
                print(f"[PineconeService] Skipping item with empty embedding: '{query_str}'")
                retrieval_results.append({
                    "query": query_str,
                    "sub_query_type": forwarded_type,
                    "matches": []
                })
                continue

            # Merge results across namespaces: best score per vector ID wins
            combined: Dict[str, Dict[str, Any]] = {}
            for ns in namespaces_to_query:
                query_kwargs: Dict[str, Any] = {
                    "vector": vector,
                    "top_k": top_k,
                    "include_metadata": True,
                }
                if ns:
                    query_kwargs["namespace"] = ns

                try:
                    response = index.query(**query_kwargs)
                    raw_matches: List[Dict] = response.get("matches") or []
                except Exception as e:
                    print(
                        f"[PineconeService] Pinecone query failed "
                        f"(ns='{ns}', query='{query_str}'): {e}"
                    )
                    continue

                for match in raw_matches:
                    m_id: str = match.get("id") or ""
                    score: float = float(
                        match.get("score") if match.get("score") is not None else 0.0
                    )
                    if m_id not in combined or score > combined[m_id]["score"]:
                        combined[m_id] = {
                            "id": m_id,
                            "score": score,
                            "metadata": match.get("metadata") or {},
                        }

            sorted_matches = sorted(
                combined.values(), key=lambda x: x["score"], reverse=True
            )

            # Apply ID-prefix filter (e.g. keep only "IPC_*")
            if prefix:
                before = len(sorted_matches)
                sorted_matches = [m for m in sorted_matches if m["id"].upper().startswith(prefix)]
                after = len(sorted_matches)
                if before != after:
                    print(
                        f"[PineconeService] act_filter='{act_filter}' removed "
                        f"{before - after} non-{act_filter} matches for query '{query_str}'"
                    )

            # Final top_k cap after filtering
            sorted_matches = sorted_matches[:top_k]

            if not sorted_matches:
                print(f"[PineconeService] No matches for query '{query_str}' after filtering.")

            retrieval_results.append({
                "query": query_str,
                "sub_query_type": forwarded_type,
                "matches": sorted_matches,
            })

        return {"retrieval_results": retrieval_results}