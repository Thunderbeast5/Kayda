from typing import Dict, Any, List

# Lower threshold to avoid dropping all candidates when metadata is sparse.
# The user explicitly wants to remove the floor that was killing results.
MERGE_SIMILARITY_THRESHOLD = 0.0   # effectively disabled

MAX_CANDIDATES_POST_MERGE = 12


class MergeService:
    """
    MergeService

    A specialized retrieval component of Kayda AI.
    Merges candidate sections retrieved from multiple Pinecone searches into a unified candidate list.
    Applies a similarity floor and a hard candidate cap before returning results
    so that downstream Neo4j verification only processes high-quality hits.
    """

    def merge_results(self, input_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merges duplicate sections across multiple retrieval results.
        Identifies duplicates using section number, act, and unique section ID.
        """
        retrieval_results = input_json.get("retrieval_results") or []
        merged_map: Dict[str, Dict[str, Any]] = {}

        for res in retrieval_results:
            query_str = res.get("query") or ""
            matches = res.get("matches") or []
            
            for m in matches:
                mid = m.get("id") or ""
                score = float(m.get("score") if m.get("score") is not None else 0.0)
                meta = m.get("metadata") or {}
                
                # Derive act from ID prefix (e.g., "IPC_120B" → "IPC")
                act = ""
                if mid.startswith("BNS_"):
                    act = "BNS"
                elif mid.startswith("IPC_"):
                    act = "IPC"
                elif mid.startswith("BNSS_"):
                    act = "BNSS"
                elif mid.startswith("CRPC_"):
                    act = "CRPC"
                elif mid.startswith("BSA_"):
                    act = "BSA"
                elif mid.startswith("IEA_"):
                    act = "IEA"
                elif mid.startswith("POCSO_"):
                    act = "POCSO"
                elif mid.startswith("DPA_") or mid.startswith("DOWRY_"):
                    act = "DPA"
                else:
                    # fallback: try to get from metadata
                    act = meta.get("act", "")

                # Section number from metadata field "section_number"
                section_num = meta.get("section_number") or ""
                if not section_num:
                    # fallback: remove act prefix from id
                    section_num = mid.replace(f"{act}_", "") if act else mid
                
                if not section_num or not act:
                    continue
                    
                # Identify duplicates using unique section ID (section_key)
                section_key = f"{act}_{section_num}".strip().upper()
                section_name = f"{act} {section_num}"
                
                if section_key not in merged_map:
                    merged_map[section_key] = {
                        "section": section_name,
                        "sources": {query_str} if query_str else set(),
                        "best_similarity": score,
                        "metadata": meta,
                        "act": act,
                        "section_num": section_num
                    }
                else:
                    existing = merged_map[section_key]
                    if score > existing["best_similarity"]:
                        existing["best_similarity"] = score
                    if query_str:
                        existing["sources"].add(query_str)
                        
        # Format sources as a list and convert map to sorted list
        merged_list = []
        for key, item in merged_map.items():
            merged_list.append({
                "section": item["section"],
                "sources": sorted(list(item["sources"])),
                "best_similarity": item["best_similarity"],
                "metadata": item["metadata"],
                "act": item["act"],
                "section_num": item["section_num"]
            })
            
        # Sort by highest best_similarity in descending order
        merged_list = sorted(merged_list, key=lambda x: x["best_similarity"], reverse=True)

        # --- Similarity floor (now disabled) ---
        above_threshold = [c for c in merged_list if c["best_similarity"] >= MERGE_SIMILARITY_THRESHOLD]
        if above_threshold:
            merged_list = above_threshold
        else:
            # If threshold is 0, this won't trigger; but keep fallback just in case.
            merged_list = merged_list[:5]
            print(
                f"[MergeService] WARNING: no candidates cleared similarity floor "
                f"({MERGE_SIMILARITY_THRESHOLD}); falling back to top {len(merged_list)}."
            )

        # --- Hard cap ---
        if len(merged_list) > MAX_CANDIDATES_POST_MERGE:
            print(
                f"[MergeService] Capping {len(merged_list)} candidates → {MAX_CANDIDATES_POST_MERGE} "
                f"(similarity floor already applied)."
            )
            merged_list = merged_list[:MAX_CANDIDATES_POST_MERGE]

        return {
            "merged_candidates": merged_list
        }