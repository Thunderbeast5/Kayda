from typing import Dict, Any, List


class MergeService:
    """
    MergeService
    
    A specialized retrieval component of Kayda AI.
    Merges candidate sections retrieved from multiple Pinecone searches into a unified candidate list.
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
                
                act = meta.get("act") or ""
                if not act:
                    act = "BNS" if mid.startswith("BNS_") else "IPC"
                    
                section_num = meta.get("section") or ""
                if not section_num:
                    section_num = mid.replace("IPC_", "").replace("BNS_", "")
                    
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
                    # Accumulate unique sources
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
                # Preserve act and section_num internally for downstream agents
                "act": item["act"],
                "section_num": item["section_num"]
            })
            
        # Sort by highest best_similarity in descending order
        merged_list = sorted(merged_list, key=lambda x: x["best_similarity"], reverse=True)
        
        return {
            "merged_candidates": merged_list
        }
