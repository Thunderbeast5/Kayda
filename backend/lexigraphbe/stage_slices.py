"""
Typed input slices for LexiGraph backend pipeline stages.
Ensures each stage gets ONLY the extracted fields it needs rather than
the full redundant JSON and 2,500-token raw document text.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def _to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except Exception:
            return {}
    return {}


def compact_json(data: Any) -> str:
    """Serialize data to compact JSON with no unnecessary whitespace."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Stage 1 Slice: Query Understanding
# Needs extracted facts, parties, and regime/procedural stage from Stage 0.
# ---------------------------------------------------------------------------
class Stage1InputSlice(BaseModel):
    case_facts: str = Field(default="", description="Extracted factual narrative")
    parties: Dict[str, Any] = Field(default_factory=dict, description="Identified parties and accused list")
    procedural_stage: str = Field(default="UNKNOWN")
    requested_relief: str = Field(default="UNKNOWN")
    legal_regime: str = Field(default="IPC + CrPC")
    case_metadata: Dict[str, Any] = Field(default_factory=dict)


def get_stage1_slice(case_context: Any) -> Stage1InputSlice:
    d = _to_dict(case_context)
    profile = d.get("case_profile") or d
    return Stage1InputSlice(
        case_facts=str(profile.get("case_facts") or ""),
        parties=profile.get("parties") or {},
        procedural_stage=str(profile.get("procedural_stage") or "UNKNOWN"),
        requested_relief=str(profile.get("requested_relief") or "UNKNOWN"),
        legal_regime=str(profile.get("legal_regime") or "IPC + CrPC"),
        case_metadata=profile.get("case_metadata") or {},
    )


# ---------------------------------------------------------------------------
# Stage 3 Slice: Chapter Verification
# Needs only the legal concepts, sub-queries, and regime from Stage 1.
# ---------------------------------------------------------------------------
class Stage3QuerySlice(BaseModel):
    legal_regime: str = Field(default="IPC + CrPC")
    legal_concepts: List[str] = Field(default_factory=list)
    sub_queries: List[Dict[str, Any]] = Field(default_factory=list)


def get_stage3_slice(legal_query: Any) -> Stage3QuerySlice:
    d = _to_dict(legal_query)
    concepts = [
        c.get("concept") if isinstance(c, dict) else str(c)
        for c in d.get("legal_concepts", [])
    ]
    sub_queries = []
    for sq in d.get("sub_queries", []):
        if isinstance(sq, dict):
            sub_queries.append({
                "id": sq.get("id"),
                "concept": sq.get("legal_concept"),
                "query": sq.get("query"),
                "parties": sq.get("target_parties"),
            })
    return Stage3QuerySlice(
        legal_regime=str(d.get("legal_regime") or "IPC + CrPC"),
        legal_concepts=concepts,
        sub_queries=sub_queries,
    )


# ---------------------------------------------------------------------------
# Stage 5 Slice: Bail Reasoning
# Needs extracted facts & parties (Stage 0), sub-queries (Stage 1),
# and verified offences with titles & punishments (Stage 4).
# ---------------------------------------------------------------------------
class Stage5ContextSlice(BaseModel):
    case_facts: str = Field(default="")
    parties: Dict[str, Any] = Field(default_factory=dict)
    procedural_stage: str = Field(default="Anticipatory Bail")
    requested_relief: str = Field(default="Anticipatory Bail")
    legal_regime: str = Field(default="IPC + CrPC")


class Stage5StatutorySlice(BaseModel):
    verified_offences: List[Dict[str, Any]] = Field(default_factory=list)


def get_stage5_slices(case_context: Any, legal_query: Any, statutory_object: Any) -> tuple[dict, dict, dict]:
    c_dict = _to_dict(case_context)
    c_prof = c_dict.get("case_profile") or c_dict
    s0_slice = {
        "case_facts": c_prof.get("case_facts") or "",
        "parties": c_prof.get("parties") or {},
        "procedural_stage": c_prof.get("procedural_stage") or "Anticipatory Bail",
        "requested_relief": c_prof.get("requested_relief") or "Anticipatory Bail",
        "legal_regime": c_prof.get("legal_regime") or "IPC + CrPC",
    }

    q_dict = _to_dict(legal_query)
    s1_slice = {
        "legal_concepts": [c.get("concept") if isinstance(c, dict) else str(c) for c in q_dict.get("legal_concepts", [])],
        "sub_queries": [sq.get("query") if isinstance(sq, dict) else str(sq) for sq in q_dict.get("sub_queries", [])],
    }

    st_dict = _to_dict(statutory_object)
    raw_offences = st_dict.get("verified_offences") or st_dict.get("verified_sections") or []
    offences = []
    for o in raw_offences:
        if isinstance(o, dict):
            offences.append({
                "section": o.get("section_number") or o.get("section"),
                "statute": o.get("statute", "IPC"),
                "title": o.get("title") or o.get("description"),
                "punishment": o.get("punishment_text") or o.get("punishment"),
                "classification": o.get("classification", "PRIMARY"),
            })
    s4_slice = {"verified_offences": offences}

    return s0_slice, s1_slice, s4_slice


# ---------------------------------------------------------------------------
# Stage 6 Slice: Precedent Retrieval
# Needs concise facts (Stage 0), concepts (Stage 1), verified sections (Stage 4),
# bail factors (Stage 5), and compact corpus.
# ---------------------------------------------------------------------------
def get_stage6_slices(
    case_context: Any,
    legal_query: Any,
    statutory_object: Any,
    bail_object: Any,
    corpus: List[Any],
) -> tuple[dict, dict, dict, dict, list]:
    c_dict = _to_dict(case_context)
    c_prof = c_dict.get("case_profile") or c_dict
    s0_slice = {
        "case_facts": c_prof.get("case_facts") or "",
        "procedural_stage": c_prof.get("procedural_stage") or "Anticipatory Bail",
    }

    q_dict = _to_dict(legal_query)
    s1_slice = {
        "legal_concepts": [c.get("concept") if isinstance(c, dict) else str(c) for c in q_dict.get("legal_concepts", [])],
    }

    st_dict = _to_dict(statutory_object)
    raw_offences = st_dict.get("verified_offences") or st_dict.get("verified_sections") or []
    s4_slice = {
        "verified_sections": [
            str(o.get("section_number") or o.get("section") or "") for o in raw_offences if isinstance(o, dict)
        ]
    }

    b_dict = _to_dict(bail_object)
    s5_slice = {
        "bail_factors": b_dict.get("bail_factors") or {},
        "overall_recommendation": b_dict.get("overall_recommendation") or "",
    }

    compact_corpus = []
    for item in corpus:
        if isinstance(item, dict):
            compact_corpus.append({
                "id": item.get("judgment_id") or item.get("id"),
                "case_name": item.get("case_name") or item.get("case"),
                "citation": item.get("citation"),
                "court": item.get("court"),
                "sections": item.get("relevant_sections") or item.get("sections"),
                "ratio": item.get("ratio_decidendi") or item.get("ratio"),
                "bail_decision": item.get("bail_decision") or item.get("decision"),
            })
        else:
            compact_corpus.append(item)

    return s0_slice, s1_slice, s4_slice, s5_slice, compact_corpus
