from typing import Dict, Any, List

_embedder = None


class EmbeddingService:
    """
    EmbeddingService

    Uses jinaai/jina-embeddings-v3 (1024-dim) to match the Pinecone index dimension.
    Falls back gracefully if model loading fails.

    Key contract upheld by this class:
      - The `query` key in every output embedding dict is the STRIPPED version of the
        input query (str(q).strip()).  Callers that build lookup maps from sub-query
        strings MUST also strip their keys before lookup — see sq_type_by_query in
        lexigraph_agent.py.
      - Deduplication is applied across the input list so the same string is only
        embedded once, saving model calls.
    """

    def __init__(self, model_name: str = "jinaai/jina-embeddings-v3"):
        self.model_name = model_name

    def _get_embedder(self):
        global _embedder
        if _embedder is None:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(
                self.model_name,
                trust_remote_code=True,
                local_files_only=True   # use local cache; no HF download
            )
        return _embedder

    def generate_embeddings(self, input_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates vector embeddings for every search query in the input.

        Normalisation: every query is stripped via str(q).strip() before
        deduplication and embedding.  The same normalised form is used as the
        `query` key in the output, so callers can safely do:

            lookup = {str(sq["query"]).strip(): sq["type"] for sq in sub_queries}
            emb_type = lookup.get(emb_item["query"], "OFFENCE")

        and the key will always match.
        """
        search_queries = input_json.get("search_queries") or []

        # Normalise + deduplicate while preserving original insertion order
        unique_queries: List[str] = []
        seen: set = set()
        for q in search_queries:
            q_clean = str(q).strip()
            if q_clean and q_clean not in seen:
                seen.add(q_clean)
                unique_queries.append(q_clean)

        output_embeddings: List[Dict[str, Any]] = []

        if not unique_queries:
            return {"embeddings": output_embeddings}

        # ---- Batch encode (fast path) ----------------------------------------
        try:
            embedder = self._get_embedder()
            vectors = embedder.encode(unique_queries, convert_to_numpy=True).tolist()
            for q, vec in zip(unique_queries, vectors):
                output_embeddings.append({"query": q, "embedding": vec})
            return {"embeddings": output_embeddings}

        except Exception as e:
            print(
                f"[EmbeddingService] Batch embedding error: {e}. "
                f"Falling back to single-query encoding..."
            )

        # ---- Single-query fallback -------------------------------------------
        embedder = self._get_embedder()
        for q in unique_queries:
            try:
                vec = embedder.encode([q], convert_to_numpy=True).tolist()[0]
                output_embeddings.append({"query": q, "embedding": vec})
            except Exception as ex:
                print(f"[EmbeddingService] Failed to embed query '{q}': {ex}")
                # Skip — caller must handle missing entries gracefully

        return {"embeddings": output_embeddings}