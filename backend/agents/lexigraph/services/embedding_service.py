from typing import Dict, Any, List

_embedder = None


class EmbeddingService:
    """
    EmbeddingService
    
    A specialized legal retrieval component of Kayda AI.
    Responsible for generating vector embeddings for search queries.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name

    def _get_embedder(self):
        global _embedder
        if _embedder is None:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(self.model_name)
        return _embedder

    def generate_embeddings(self, input_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates vector embeddings for every search query in the input.
        Skips empty/duplicate queries, preserves input order, and handles failures gracefully.
        """
        search_queries = input_json.get("search_queries") or []
        
        # Deduplicate and skip empty queries while preserving order
        unique_queries = []
        seen = set()
        for q in search_queries:
            q_clean = str(q).strip()
            if q_clean and q_clean not in seen:
                seen.add(q_clean)
                unique_queries.append(q_clean)
                
        output_embeddings = []
        
        if unique_queries:
            try:
                embedder = self._get_embedder()
                # Batch encode the queries
                vectors = embedder.encode(unique_queries, convert_to_numpy=True).tolist()
                
                for q, vec in zip(unique_queries, vectors):
                    output_embeddings.append({
                        "query": q,
                        "embedding": vec
                    })
            except Exception as e:
                # If batch generation fails, fallback to single query encoding to satisfy task 5
                print(f"[EmbeddingService] Batch embedding generation error: {e}. Falling back to individual query generation...")
                embedder = self._get_embedder()
                for q in unique_queries:
                    try:
                        vec = embedder.encode([q], convert_to_numpy=True).tolist()[0]
                        output_embeddings.append({
                            "query": q,
                            "embedding": vec
                        })
                    except Exception as ex:
                        print(f"[EmbeddingService] Failed to generate embedding for query '{q}': {ex}")
                        continue
                        
        return {
            "embeddings": output_embeddings
        }
