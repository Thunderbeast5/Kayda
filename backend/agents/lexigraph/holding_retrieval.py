"""
holding_retrieval.py
====================
Dynamic Precedent & Holding Retrieval Engine.

Retrieves operative legal rules (Holdings) from:
1. Pinecone index ('precedents' [1024-dim] or 'ipc-index' [namespace: holdings, 384-dim])
2. Neo4j Aura graph: (Case)-[:HAS_HOLDING]->(Holding)-[:APPLIES_SECTION]->(LawSection)
3. Local persistent precedent datasets (data/precedents/holdings_*.json)

Each holding supplies the legal rule as data:
  - id: str
  - case: str
  - para: str
  - principle: str
  - conditions: str
  - effect: str ("favours_denial" / "favours_grant" / "procedural")
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Base directories
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_PRECEDENTS_DIRS = [
    _BACKEND_DIR / "data" / "precedents",
    _BACKEND_DIR.parent / "data" / "precedents",
]


class Holding(BaseModel):
    id: str
    case: str
    para: str
    principle: str
    conditions: str
    effect: str = "procedural"  # favours_denial / favours_grant / procedural
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "case": self.case,
            "para": self.para,
            "principle": self.principle,
            "conditions": self.conditions,
            "effect": self.effect,
            "score": round(self.score, 4),
        }


# Cache loaded holdings in memory
_CACHED_HOLDINGS: Optional[List[Holding]] = None


def load_all_local_holdings() -> List[Holding]:
    """
    Loads all offline holdings from data/precedents/holdings_*.json.
    """
    global _CACHED_HOLDINGS
    if _CACHED_HOLDINGS is not None:
        return _CACHED_HOLDINGS

    holdings_list: List[Holding] = []
    seen_ids = set()

    for pdir in _DATA_PRECEDENTS_DIRS:
        if not pdir.exists():
            continue
        for fpath in pdir.glob("holdings_*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        hid = item.get("id") or item.get("holding_id") or ""
                        # deduplicate on combination of id, case, principle
                        key = (hid, item.get("case", ""), item.get("principle", "")[:40])
                        if key in seen_ids:
                            continue
                        seen_ids.add(key)
                        holdings_list.append(Holding(
                            id=hid or f"holding_{len(holdings_list)+1}",
                            case=item.get("case", "Precedent"),
                            para=item.get("para", ""),
                            principle=item.get("principle", ""),
                            conditions=item.get("conditions", ""),
                            effect=item.get("effect", "procedural"),
                            score=0.0
                        ))
            except Exception as exc:
                print(f"[HoldingRetrieval] Error reading {fpath}: {exc}")

    _CACHED_HOLDINGS = holdings_list
    return holdings_list


def _query_pinecone_holdings(query_text: str, top_k: int = 5) -> Dict[str, float]:
    """
    Queries Pinecone index for holdings if available.
    Returns mapping of holding_id -> similarity_score.
    """
    scores: Dict[str, float] = {}
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        return scores

    # Try 1: Query 'precedents' index (1024-dim, e5-large)
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=api_key)
        existing = [idx.name for idx in pc.list_indexes()]
        if "precedents" in existing:
            emb_res = pc.inference.embed(
                model="multilingual-e5-large",
                inputs=[query_text],
                parameters={"input_type": "query"}
            )
            query_vec = emb_res[0].values
            idx = pc.Index("precedents")
            res = idx.query(vector=query_vec, top_k=top_k, include_metadata=True)
            for match in res.get("matches", []):
                mid = match.get("id") or ""
                score = float(match.get("score", 0.0))
                if mid:
                    scores[mid] = max(scores.get(mid, 0.0), score)
            if scores:
                return scores
    except Exception:
        pass

    # Try 2: Query 'ipc-index' (namespace: holdings, 384-dim)
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=api_key)
        index_name = os.getenv("PINECONE_INDEX_NAME", "ipc-index")
        idx = pc.Index(index_name)
        global _ST_HOLDING_MODEL
        if "_ST_HOLDING_MODEL" not in globals() or _ST_HOLDING_MODEL is None:
            from sentence_transformers import SentenceTransformer
            _ST_HOLDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        model = _ST_HOLDING_MODEL
        vec = model.encode(query_text).tolist()
        res = idx.query(vector=vec, top_k=top_k, namespace="holdings", include_metadata=True)
        for match in res.get("matches", []):
            mid = match.get("id") or ""
            score = float(match.get("score", 0.0))
            if mid:
                scores[mid] = max(scores.get(mid, 0.0), score)
    except Exception:
        pass

    return scores


def _compute_keyword_relevance(query_tokens: set[str], holding: Holding) -> float:
    """
    Compute token and legal concept overlap between query and holding.
    """
    holding_text = f"{holding.case} {holding.principle} {holding.conditions} {holding.effect}".lower()
    
    score = 0.0
    for tok in query_tokens:
        if len(tok) < 3:
            continue
        if tok in holding_text:
            score += 1.0

    # High-value legal rule trigger keywords
    triggers = {
        "proclamation": 4.0,
        "section 82": 4.0,
        "sec 82": 4.0,
        "82 crpc": 4.0,
        "abscond": 3.5,
        "evad": 3.0,
        "non-bailable": 2.5,
        "warrant": 2.5,
        "nbw": 2.5,
        "438": 2.0,
        "anticipatory": 2.0,
        "custodial": 2.0,
        "recovery": 1.5,
        "tampering": 1.5,
        "cooperation": 1.5,
    }
    for kw, weight in triggers.items():
        if kw in " ".join(query_tokens):
            if kw in holding_text:
                score += weight

    return score


def retrieve_holdings(
    query_text: str,
    case_facts: Optional[List[Any]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Retrieves the most relevant precedent holdings for the current case.
    The returned holdings provide the data-driven legal rules for the agents.
    """
    holdings = load_all_local_holdings()
    if not holdings:
        return []

    # Build comprehensive search query from query_text and case_facts
    fact_snippets = []
    if case_facts:
        for f in case_facts:
            txt = getattr(f, "text", f.get("text", "") if isinstance(f, dict) else str(f))
            if txt:
                fact_snippets.append(txt)
    
    combined_query = f"{query_text} {' '.join(fact_snippets)}".lower()
    query_tokens = set(re.findall(r"\b[a-z0-9_-]+\b", combined_query))

    # Get Pinecone vector scores if available
    vector_scores = _query_pinecone_holdings(combined_query[:500], top_k=top_k * 2)

    scored_holdings: List[Holding] = []
    for h in holdings:
        kw_score = _compute_keyword_relevance(query_tokens, h)
        vec_score = vector_scores.get(h.id, 0.0)

        # Normalize keyword score to ~0-1 range
        norm_kw = min(kw_score / 15.0, 1.0)
        
        if vec_score > 0:
            final_score = (vec_score * 0.5) + (norm_kw * 0.5)
        else:
            final_score = norm_kw

        h_copy = Holding(**h.model_dump())
        h_copy.score = final_score
        scored_holdings.append(h_copy)

    # Sort descending by score
    scored_holdings.sort(key=lambda x: x.score, reverse=True)
    top_holdings = scored_holdings[:top_k]

    return [h.to_dict() for h in top_holdings]


def format_holdings_for_prompt(holdings: List[Dict[str, Any]]) -> str:
    """
    Formats the retrieved precedent holdings into a clear, authoritative block
    for inclusion in Prosecutor, Defense, and Judge agent prompts.
    """
    if not holdings:
        return "No specific judicial precedent holdings retrieved."

    lines = [
        "RETRIEVED PRECEDENT HOLDINGS & BINDING RATIO DECIDENDI",
        "=================================================================",
        "NOTE: Legal rules governing this bail application originate from these retrieved",
        "precedent holdings as data. The Court and Counsel must apply these rules to the facts.",
        "-----------------------------------------------------------------",
    ]

    for i, h in enumerate(holdings, 1):
        cid = h.get("id", f"holding_{i}")
        case = h.get("case", "Supreme Court Precedent")
        para = h.get("para", "")
        principle = h.get("principle", "").strip()
        conditions = h.get("conditions", "").strip()
        effect = str(h.get("effect", "procedural")).upper()
        score = h.get("score", 0.0)

        para_str = f" (Para {para})" if para else ""
        lines.append(
            f"\n{i}. [{cid}] {case}{para_str}  [Relevance: {score:.2f} | Effect: {effect}]\n"
            f"   - Principle : {principle}\n"
            f"   - Conditions: {conditions}\n"
            f"   - Effect    : {effect}"
        )

    return "\n".join(lines)
