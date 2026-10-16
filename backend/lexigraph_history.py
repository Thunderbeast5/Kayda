"""
LexiGraph Query & Precedent History Service
Persists queries, retrieved precedent cases, and verified sections to Firebase Firestore
with automatic local JSON fallback in temp_uploads/lexigraph_history.json.
"""

import sys
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

TEMP_DIR = Path(__file__).resolve().parent / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)
HISTORY_FILE = TEMP_DIR / "lexigraph_history.json"


def _get_firestore_db():
    try:
        from backend.agents.evidence.evidence_analyzer import _get_firestore_client
        return _get_firestore_client()
    except Exception as e:
        try:
            from agents.evidence.evidence_analyzer import _get_firestore_client
            return _get_firestore_client()
        except Exception:
            print(f"[Firebase] Firestore client unavailable for LexiGraph history: {e}", file=sys.stderr)
            return None


def build_lexigraph_summary(result: dict) -> dict:
    """Builds a rich, normalized summary object with verified sections and retrieved precedent case law."""
    supporting = result.get("supporting_cases") or []
    similar = result.get("similar_cases") or []
    s5_prec = result.get("stage5_precedent_retrieval") or {}

    pros_precedents = s5_prec.get("prosecution_precedents") or []
    def_precedents = s5_prec.get("defense_precedents") or []

    # Merge and standardize precedent cases
    precedents = []
    seen_titles = set()

    for p in pros_precedents:
        title = p.get("case_name") or p.get("title") or "Supreme Court Precedent"
        key = title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            matched = p.get("matched_statutes") or []
            interprets = [
                f"{m.get('statute', '')} {m.get('section_number', '')}".strip()
                for m in matched if isinstance(m, dict)
            ]
            comp = p.get("compact_summary") if isinstance(p.get("compact_summary"), dict) else {}
            rel = p.get("relevance_evaluation") if isinstance(p.get("relevance_evaluation"), dict) else {}

            ratio = (
                comp.get("core_proposition")
                or "; ".join([pr.get("text") or pr.get("proposition") for pr in p.get("propositions", []) if isinstance(pr, dict)])
                or rel.get("usage_recommendation")
                or p.get("abstract_facts")
                or "Article 141 Binding Precedent."
            )

            precedents.append({
                "case_id": p.get("case_id", ""),
                "case_name": title,
                "case_title": title,
                "title": title,
                "citation": p.get("citation") or "",
                "court": p.get("court") or "Supreme Court of India",
                "decided_on": p.get("decided_on") or "",
                "year": str(p.get("decided_on") or "")[:4] if p.get("decided_on") else "",
                "binding_under": "Article 141 Binding Precedent",
                "procedural_stage": p.get("procedural_stage") or "Pre-arrest / Anticipatory Bail",
                "role_stance": "Prosecution",
                "match_score": p.get("match_score", 0.0),
                "final_relevance_score": p.get("final_relevance_score", 8.8),
                "similarity": round(float(p.get("final_relevance_score") or 8.8) / 10.0, 2),
                "ratio_decidendi": ratio,
                "facts": p.get("abstract_facts") or "",
                "interprets": interprets or [f"Section {m}" for m in (p.get("all_statutes") or []) if isinstance(m, (str, int))],
                "usage_recommendation": comp.get("usage_recommendation") or rel.get("usage_recommendation") or "",
                "key_quotes": [comp.get("key_quote")] if comp.get("key_quote") else rel.get("key_quotes", []),
                "distinguishing_factors": rel.get("distinguishing_factors", []),
                "type": "binding_authority"
            })

    for p in def_precedents:
        title = p.get("case_name") or p.get("title") or "Supreme Court Precedent"
        key = title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            matched = p.get("matched_statutes") or []
            interprets = [
                f"{m.get('statute', '')} {m.get('section_number', '')}".strip()
                for m in matched if isinstance(m, dict)
            ]
            comp = p.get("compact_summary") if isinstance(p.get("compact_summary"), dict) else {}
            rel = p.get("relevance_evaluation") if isinstance(p.get("relevance_evaluation"), dict) else {}

            ratio = (
                comp.get("core_proposition")
                or "; ".join([pr.get("text") or pr.get("proposition") for pr in p.get("propositions", []) if isinstance(pr, dict)])
                or rel.get("usage_recommendation")
                or p.get("abstract_facts")
                or "Article 141 Binding Precedent."
            )

            precedents.append({
                "case_id": p.get("case_id", ""),
                "case_name": title,
                "case_title": title,
                "title": title,
                "citation": p.get("citation") or "",
                "court": p.get("court") or "Supreme Court of India",
                "decided_on": p.get("decided_on") or "",
                "year": str(p.get("decided_on") or "")[:4] if p.get("decided_on") else "",
                "binding_under": "Article 141 Binding Precedent",
                "procedural_stage": p.get("procedural_stage") or "Pre-arrest / Anticipatory Bail",
                "role_stance": "Defense",
                "match_score": p.get("match_score", 0.0),
                "final_relevance_score": p.get("final_relevance_score", 8.8),
                "similarity": round(float(p.get("final_relevance_score") or 8.8) / 10.0, 2),
                "ratio_decidendi": ratio,
                "facts": p.get("abstract_facts") or "",
                "interprets": interprets or [f"Section {m}" for m in (p.get("all_statutes") or []) if isinstance(m, (str, int))],
                "usage_recommendation": comp.get("usage_recommendation") or rel.get("usage_recommendation") or "",
                "key_quotes": [comp.get("key_quote")] if comp.get("key_quote") else rel.get("key_quotes", []),
                "distinguishing_factors": rel.get("distinguishing_factors", []),
                "type": "binding_authority"
            })

    for c in supporting:
        title = c.get("case_name") or c.get("title") or c.get("citation") or "Supreme Court Landmark Precedent"
        key = title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            precedents.append({
                "title": title,
                "case_title": title,
                "case_name": title,
                "citation": c.get("citation") or "",
                "court": c.get("court") or "Supreme Court of India",
                "year": c.get("year") or "",
                "binding_under": c.get("binding_under") or "Article 141 Binding Precedent",
                "ratio_decidendi": c.get("ratio_decidendi") or c.get("summary") or "Constitutional parameters governing discretionary pre-arrest bail.",
                "facts": c.get("facts_summary") or c.get("facts") or "",
                "interprets": c.get("interprets") or [],
                "similarity": 0.95,
                "type": "binding_authority",
                "role_stance": "Binding SC Precedent",
                "reason": c.get("reason") or "Directly interprets statutory sections attracted by case facts."
            })

    for c in similar:
        title = c.get("case_name") or c.get("title") or c.get("case_id") or "Precedent Case"
        key = title.lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
            precedents.append({
                "title": title,
                "case_title": title,
                "case_name": title,
                "citation": c.get("citation") or meta.get("citation") or "",
                "court": c.get("court") or meta.get("court") or "Supreme Court of India",
                "year": c.get("year") or meta.get("year") or "",
                "binding_under": "Factually Similar Precedent",
                "ratio_decidendi": c.get("reasoning") or c.get("judgment_summary") or c.get("ratio_decidendi") or meta.get("reasoning") or "",
                "facts": c.get("facts") or meta.get("facts") or "",
                "interprets": c.get("sections") or meta.get("sections") or [],
                "similarity": float(c.get("ranking_score") or c.get("similarity") or 0.8),
                "type": "similar_case",
                "role_stance": "Factual Precedent",
                "reason": "High factual and legal similarity to FIR narrative."
            })

    # Normalized verified sections from Stage 4 or recommended_sections
    verified_sections = []
    s4 = result.get("stage4_statutory_verification") or {}
    s4_sections = s4.get("verified_sections") or []

    if s4_sections:
        for sec in s4_sections:
            verified_sections.append({
                "section_number": str(sec.get("section_number", "")),
                "section": str(sec.get("section_number", "")),
                "statute": sec.get("statute", "IPC"),
                "act": sec.get("statute", "IPC"),
                "title": sec.get("title", f"Section {sec.get('section_number', '')}"),
                "ipc_equivalent": sec.get("ipc_equivalent") or sec.get("section_number", ""),
                "bns_equivalent": sec.get("bns_equivalent", ""),
                "overall_status": sec.get("overall_status", "Prima Facie Attracted"),
                "overall_prima_facie_strength": sec.get("overall_prima_facie_strength", "Moderate"),
                "punishment_text": sec.get("punishment_text", "As per Schedule"),
                "cognizable": sec.get("cognizable", True),
                "bailable": sec.get("bailable", False),
                "ingredient_evaluation": sec.get("ingredient_evaluation", []),
                "legal_reasoning": sec.get("legal_reasoning", ""),
                "missing_supporting_facts": sec.get("missing_supporting_facts", []),
            })
    else:
        for s in (result.get("recommended_sections") or []):
            act = s.get("act", "")
            sec_num = str(s.get("section") or s.get("section_number") or "")
            eq = s.get("equivalent_section")

            bns_eq = ""
            ipc_eq = ""
            if isinstance(eq, dict):
                if eq.get("act") == "BNS":
                    bns_eq = str(eq.get("section") or "")
                elif eq.get("act") == "IPC":
                    ipc_eq = str(eq.get("section") or "")
            elif isinstance(eq, str):
                bns_eq = eq

            ingredients = []
            for ing in (s.get("ingredient_summary") or []):
                if isinstance(ing, dict):
                    ingredients.append({
                        "ingredient": ing.get("name", "Statutory Ingredient"),
                        "status": ing.get("state", "Satisfied"),
                        "reason": ing.get("element_type", "Statutory Element"),
                        "matched_fact": s.get("applicability", "")
                    })
                else:
                    ingredients.append({
                        "ingredient": str(ing),
                        "status": "Satisfied",
                        "reason": "Statutory Element",
                        "matched_fact": s.get("applicability", "")
                    })

            if not ingredients:
                ingredients = [{
                    "ingredient": "Statutory Offence Elements",
                    "status": "Satisfied",
                    "reason": s.get("applicability", "Statutory ingredients prima facie attracted."),
                    "matched_fact": s.get("reason", "")
                }]

            verified_sections.append({
                "statute": act,
                "act": act,
                "section_number": sec_num,
                "section": sec_num,
                "title": s.get("title", f"{act} Section {sec_num}"),
                "bns_equivalent": bns_eq or (sec_num if act == "BNS" else ""),
                "ipc_equivalent": ipc_eq or (sec_num if act == "IPC" else ""),
                "bailable": False,
                "cognizable": True,
                "punishment_text": s.get("punishment") or "As prescribed by schedule",
                "ingredient_evaluation": ingredients,
                "legal_reasoning": s.get("applicability") or s.get("reason") or "Statutory ingredients substantiated on facts."
            })

    s0 = result.get("stage0_case_context") or {}
    s5_bail = result.get("stage5_bail_reasoning") or {}
    bail_rec = (
        s5_bail.get("bail_recommendation")
        or s5_bail.get("recommendation")
        or ("Custodial Interrogation Recommended (Oppose Bail)" if any(not sec.get("bailable") for sec in verified_sections) else "Anticipatory Bail Recommended")
    )
    risk_level = s5_bail.get("flight_risk_level") or s5_bail.get("overall_risk") or "Moderate"

    return {
        "legal_regime": s0.get("legal_regime") or result.get("legal_regime") or "BNS + BNSS",
        "bail_recommendation": bail_rec,
        "risk_level": risk_level,
        "total_sections_count": len(verified_sections),
        "verified_sections": verified_sections,
        "precedents": precedents,
        "pipeline_confidence": result.get("pipeline_confidence", 0.85),
    }


def save_lexigraph_query_session(query_id: str, query: str, result: dict, summary: dict = None) -> dict:
    if summary is None:
        summary = build_lexigraph_summary(result)
    created_at = datetime.now(timezone.utc).isoformat()
    session_data = {
        "query_id": query_id,
        "query": query,
        "created_at": created_at,
        "pipeline_confidence": result.get("pipeline_confidence", 0.85),
        "primary_intent": result.get("community", {}).get("primary_intent") if isinstance(result.get("community"), dict) else "general_offences",
        "recommended_count": len(summary.get("verified_sections") or result.get("recommended_sections") or []),
        "precedents_count": len(summary.get("precedents") or []),
        "result": result,
        "summary": summary,
    }

    firestore_saved = False
    try:
        db = _get_firestore_db()
        if db:
            db.collection("lexigraph_queries").document(query_id).set(session_data)
            firestore_saved = True
            print(f"[Firebase] Saved LexiGraph query '{query_id}' to Firestore collection 'lexigraph_queries'")
    except Exception as e:
        print(f"[Firebase] Firestore set error: {e}", file=sys.stderr)

    try:
        history = []
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                except Exception:
                    history = []
        history.insert(0, session_data)
        history = history[:100]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as local_err:
        print(f"[Firebase] Local history file write error: {local_err}", file=sys.stderr)

    session_data["saved_to_firestore"] = firestore_saved
    return session_data


def list_lexigraph_history(limit: int = 50) -> list:
    sessions = []
    try:
        db = _get_firestore_db()
        if db:
            docs = db.collection("lexigraph_queries").order_by("created_at", direction="DESCENDING").limit(limit).stream()
            for doc in docs:
                data = doc.to_dict()
                sessions.append({
                    "query_id": data.get("query_id") or doc.id,
                    "query": data.get("query", ""),
                    "created_at": data.get("created_at", ""),
                    "pipeline_confidence": data.get("pipeline_confidence", 0.85),
                    "primary_intent": data.get("primary_intent", "general_offences"),
                    "recommended_count": data.get("recommended_count", 0),
                    "precedents_count": data.get("precedents_count", 0),
                    "source": "firestore"
                })
            if sessions:
                return sessions
    except Exception as e:
        print(f"[Firebase] Could not fetch history from Firestore: {e}", file=sys.stderr)

    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                for item in history[:limit]:
                    sessions.append({
                        "query_id": item.get("query_id", ""),
                        "query": item.get("query", ""),
                        "created_at": item.get("created_at", ""),
                        "pipeline_confidence": item.get("pipeline_confidence", 0.85),
                        "primary_intent": item.get("primary_intent", "general_offences"),
                        "recommended_count": item.get("recommended_count", 0),
                        "precedents_count": item.get("precedents_count", 0),
                        "source": "local"
                    })
        except Exception as local_err:
            print(f"[Firebase] Error reading local history: {local_err}", file=sys.stderr)

    return sessions


def get_lexigraph_session_by_id(query_id: str) -> dict:
    try:
        db = _get_firestore_db()
        if db:
            doc = db.collection("lexigraph_queries").document(query_id).get()
            if doc.exists:
                data = doc.to_dict() or {}
                if "summary" not in data and "result" in data:
                    data["summary"] = build_lexigraph_summary(data["result"])
                return data
    except Exception as e:
        print(f"[Firebase] Could not fetch doc '{query_id}' from Firestore: {e}", file=sys.stderr)

    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                for item in history:
                    if item.get("query_id") == query_id:
                        if "summary" not in item and "result" in item:
                            item["summary"] = build_lexigraph_summary(item["result"])
                        return item
        except Exception as local_err:
            print(f"[Firebase] Local history lookup error: {local_err}", file=sys.stderr)

    return None
