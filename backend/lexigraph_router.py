"""
LexiGraph API Router
Exposes the complete 7-stage LexiGraph pipeline (Stages 0 to 6)
via REST endpoints and real-time Server-Sent Events (SSE).
"""

import sys
import json
import asyncio
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# Ensure backend root is on path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from lexigraphbe.runner import (
    run_stage0,
    run_stage1,
    run_stage2,
    run_stage3,
    run_stage4,
    run_stage5,
    run_stage6,
    run_full_pipeline,
)
from lexigraphbe.statute_repository import StatuteRepository

router = APIRouter(prefix="/api/lexigraph", tags=["LexiGraph"])


class LexigraphRunRequest(BaseModel):
    text: Optional[str] = None
    query: Optional[str] = None
    court_type: Optional[str] = None
    legal_regime_override: Optional[str] = None
    stage: Optional[int] = 7


import uuid
from lexigraph_history import (
    save_lexigraph_query_session,
    list_lexigraph_history,
    get_lexigraph_session_by_id,
    build_lexigraph_summary,
)

def _extract_summary(full_result: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to extract unified summary across the 7 stages, including Stage 5 precedent retrieval."""
    s0 = full_result.get("stage0_case_context") or {}
    s1 = full_result.get("stage1_legal_query") or {}
    s3 = full_result.get("stage3_chapter_identification") or {}
    s4 = full_result.get("stage4_statutory_verification") or {}
    s5_prec = full_result.get("stage5_precedent_retrieval") or {}
    s5_bail = full_result.get("stage5_bail_reasoning") or {}
    s6 = full_result.get("stage6_precedent_retrieval") or {}

    # Extract verified offences / sections
    verified_sections = []
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
    elif s3.get("verified_offences"):
        for off in s3.get("verified_offences"):
            punish = off.get("punishment") or {}
            punish_str = punish.get("maximum") if isinstance(punish, dict) else str(punish)
            verified_sections.append({
                "section_number": str(off.get("section_number", "")),
                "section": str(off.get("section_number", "")),
                "statute": off.get("statute", "BNS"),
                "act": off.get("statute", "BNS"),
                "title": off.get("title", ""),
                "ipc_equivalent": off.get("ipc_equivalent", ""),
                "bns_equivalent": off.get("bns_equivalent", ""),
                "overall_status": "Prima Facie Attracted",
                "overall_prima_facie_strength": "Moderate",
                "punishment_text": punish_str or "As per schedule",
                "cognizable": off.get("cognizable", True),
                "bailable": off.get("bailable", False),
                "ingredient_evaluation": [],
                "legal_reasoning": f"Identified under Chapter {off.get('chapter_number', '')} {off.get('statute', '')}",
                "missing_supporting_facts": [],
            })

    # Precedents Extraction: From Stage 5 role-specific retrieval (prosecution + defense)
    precedents = []
    seen_ids = set()

    for p in (s5_prec.get("prosecution_precedents") or []):
        cid = p.get("case_id") or p.get("case_name") or p.get("title")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
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
                "case_name": p.get("case_name", "Supreme Court Precedent"),
                "case_title": p.get("case_name", "Supreme Court Precedent"),
                "title": p.get("case_name", "Supreme Court Precedent"),
                "citation": p.get("citation") or "",
                "court": p.get("court") or "Supreme Court of India",
                "decided_on": p.get("decided_on") or "",
                "year": str(p.get("decided_on") or "")[:4] if p.get("decided_on") else "",
                "binding_under": "Article 141 Binding Precedent",
                "procedural_stage": p.get("procedural_stage") or "Pre-arrest / Anticipatory Bail",
                "disposition": p.get("disposition") or "",
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

    for p in (s5_prec.get("defense_precedents") or []):
        cid = p.get("case_id") or p.get("case_name") or p.get("title")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
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
                "case_name": p.get("case_name", "Supreme Court Precedent"),
                "case_title": p.get("case_name", "Supreme Court Precedent"),
                "title": p.get("case_name", "Supreme Court Precedent"),
                "citation": p.get("citation") or "",
                "court": p.get("court") or "Supreme Court of India",
                "decided_on": p.get("decided_on") or "",
                "year": str(p.get("decided_on") or "")[:4] if p.get("decided_on") else "",
                "binding_under": "Article 141 Binding Precedent",
                "procedural_stage": p.get("procedural_stage") or "Pre-arrest / Anticipatory Bail",
                "disposition": p.get("disposition") or "",
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

    # Supporting / Similar cases fallback
    if not precedents:
        fallback_summary = build_lexigraph_summary(full_result)
        precedents = fallback_summary.get("precedents") or s6.get("relevant_precedents") or s6.get("precedents") or []

    # Bail recommendation
    bail_recommendation = s5_bail.get("bail_recommendation") or s5_bail.get("recommendation")
    if not bail_recommendation or bail_recommendation == "Pending Assessment":
        has_non_bailable = any(not sec.get("bailable") for sec in verified_sections)
        bail_recommendation = (
            "Custodial Interrogation Recommended (Oppose Anticipatory Bail)"
            if has_non_bailable
            else "Anticipatory Bail Recommended with Surety Conditions"
        )
    risk_level = s5_bail.get("flight_risk_level") or s5_bail.get("overall_risk") or "Moderate - Prima Facie Charges"

    # Legal concepts
    concepts = [
        c.get("concept") or c.get("concept_name")
        for c in (s1.get("legal_concepts") or [])
        if isinstance(c, dict)
    ]

    return {
        "legal_regime": s0.get("legal_regime") or "BNS + BNSS",
        "jurisdiction": s0.get("jurisdiction_state") or "Maharashtra",
        "legal_concepts": concepts,
        "verified_sections": verified_sections,
        "bail_recommendation": bail_recommendation,
        "risk_level": risk_level,
        "precedents": precedents,
        "total_sections_count": len(verified_sections),
    }


@router.post("/pipeline")
async def run_pipeline_endpoint(req: LexigraphRunRequest):
    """
    Executes the LexiGraph pipeline synchronously (in threadpool) and returns
    comprehensive multi-stage output + summary + persists session to Firebase.
    """
    text = req.text or req.query or ""
    if not text.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Text or query must not be empty."}
        )

    try:
        if req.stage == 0:
            stage_out = await asyncio.to_thread(
                run_stage0,
                text=text,
                user_query=req.query,
                court_type=req.court_type,
                legal_regime_override=req.legal_regime_override,
            )
            return {"success": True, "stage": 0, "data": {"stage0_case_context": stage_out}}

        # Full pipeline execution
        result = await asyncio.to_thread(
            run_full_pipeline,
            text=text,
            user_query=req.query,
            court_type=req.court_type,
            legal_regime_override=req.legal_regime_override,
        )

        summary = _extract_summary(result)

        # Save session to Firebase Firestore
        query_id = f"lexi_{uuid.uuid4().hex[:12]}"
        saved_session = await asyncio.to_thread(save_lexigraph_query_session, query_id, text.strip(), result, summary)

        return {
            "success": True,
            "query_id": query_id,
            "created_at": saved_session.get("created_at"),
            "saved_to_firestore": saved_session.get("saved_to_firestore", False),
            "stage": 7,
            "data": result,
            "summary": summary,
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"LexiGraph pipeline error: {str(e)}"}
        )


@router.get("/history")
async def get_lexigraph_history_endpoint(limit: int = 50):
    try:
        history = await asyncio.to_thread(list_lexigraph_history, limit)
        return {
            "success": True,
            "count": len(history),
            "data": history
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to fetch history: {str(e)}"}
        )


@router.get("/history/{query_id}")
async def get_lexigraph_session_endpoint(query_id: str):
    try:
        session = await asyncio.to_thread(get_lexigraph_session_by_id, query_id)
        if not session:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"Query record '{query_id}' not found."}
            )
        return {
            "success": True,
            "data": session
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to fetch query session: {str(e)}"}
        )


@router.get("/pipeline/stream")
async def stream_pipeline_endpoint(
    text: str = Query(...),
    query: Optional[str] = Query(None),
    court_type: Optional[str] = Query(None),
    legal_regime: Optional[str] = Query(None),
):
    """
    Server-Sent Events (SSE) streaming endpoint that runs each stage progressively
    and yields real-time progress events for the frontend.
    """
    if not text.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Text parameter cannot be empty."}
        )

    async def event_generator():
        try:
            # Stage 0: Intake
            yield f"data: {json.dumps({'stage': 0, 'status': 'running', 'title': 'Stage 0: Case Intake & Context'})}\n\n"
            stage0_out = await asyncio.to_thread(
                run_stage0,
                text=text,
                user_query=query,
                court_type=court_type,
                legal_regime_override=legal_regime,
            )
            yield f"data: {json.dumps({'stage': 0, 'status': 'complete', 'title': 'Stage 0 Complete', 'data': stage0_out})}\n\n"

            # Stage 1: Legal Query Decomposition
            yield f"data: {json.dumps({'stage': 1, 'status': 'running', 'title': 'Stage 1: Legal Query Deconstruction'})}\n\n"
            stage1_out = await asyncio.to_thread(run_stage1, stage0_out)
            yield f"data: {json.dumps({'stage': 1, 'status': 'complete', 'title': 'Stage 1 Complete', 'data': stage1_out})}\n\n"

            # Stage 2: Sub-Query Mapping
            yield f"data: {json.dumps({'stage': 2, 'status': 'running', 'title': 'Stage 2: Batched Statutory Pre-filter Mapping'})}\n\n"
            stage2_out = await asyncio.to_thread(run_stage2, stage1_out)
            yield f"data: {json.dumps({'stage': 2, 'status': 'complete', 'title': 'Stage 2 Complete', 'data': stage2_out})}\n\n"

            # Stage 3: Chapter Identification & IPC ⇄ BNS Normalization
            yield f"data: {json.dumps({'stage': 3, 'status': 'running', 'title': 'Stage 3: Chapter Identification & Normalization'})}\n\n"
            stage3_out = await asyncio.to_thread(run_stage3, stage1_out, stage2_out)
            yield f"data: {json.dumps({'stage': 3, 'status': 'complete', 'title': 'Stage 3 Complete', 'data': stage3_out})}\n\n"

            # Stage 4: Statutory Verification & Ingredient Matching
            yield f"data: {json.dumps({'stage': 4, 'status': 'running', 'title': 'Stage 4: Statutory Verification & Ingredient Matching'})}\n\n"
            stage4_out = await asyncio.to_thread(run_stage4, stage1_out, stage3_out)
            yield f"data: {json.dumps({'stage': 4, 'status': 'complete', 'title': 'Stage 4 Complete', 'data': stage4_out})}\n\n"

            # Stage 5: Anticipatory Bail Reasoning
            yield f"data: {json.dumps({'stage': 5, 'status': 'running', 'title': 'Stage 5: Anticipatory Bail Reasoning & Risk Assessment'})}\n\n"
            stage5_out = await asyncio.to_thread(run_stage5, stage0_out, stage1_out, stage4_out)
            yield f"data: {json.dumps({'stage': 5, 'status': 'complete', 'title': 'Stage 5 Complete', 'data': stage5_out})}\n\n"

            # Stage 6: Precedent Retrieval
            yield f"data: {json.dumps({'stage': 6, 'status': 'running', 'title': 'Stage 6: Supreme Court Precedent Grounding'})}\n\n"
            stage6_out = await asyncio.to_thread(run_stage6, stage0_out, stage1_out, stage4_out, stage5_out)
            yield f"data: {json.dumps({'stage': 6, 'status': 'complete', 'title': 'Stage 6 Complete', 'data': stage6_out})}\n\n"

            # Final combined payload
            full_out = {
                "stage0_case_context": stage0_out,
                "stage1_legal_query": stage1_out,
                "stage2_subquery_mapping": stage2_out,
                "stage3_chapter_identification": stage3_out,
                "stage4_statutory_verification": stage4_out,
                "stage5_bail_reasoning": stage5_out,
                "stage6_precedent_retrieval": stage6_out,
            }
            summary = _extract_summary(full_out)

            yield f"data: {json.dumps({'stage': 7, 'status': 'finished', 'data': full_out, 'summary': summary})}\n\n"

        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/statute/{section}")
async def get_statute_details(section: str):
    """
    Instant lookup of statutory section definition, ingredients, IPC ⇄ BNS equivalents,
    and schedule punishment info directly from StatuteRepository.
    """
    clean_sec = section.strip().upper().replace("SECTION", "").replace("SEC", "").replace("BNS", "").replace("IPC", "").strip()
    try:
        repo = StatuteRepository.get_instance()
        meta = repo.get_first_schedule_metadata(clean_sec)
        ipc_to_bns = repo.get_ipc_to_bns_map().get(clean_sec, {})
        bns_to_ipc = repo.get_bns_to_ipc_map().get(clean_sec, {})
        statute_db = repo.get_statute_db()
        sec_text = statute_db.get(f"IPC_{clean_sec}") or statute_db.get(f"BNS_{clean_sec}") or {}

        return {
            "success": True,
            "data": {
                "section": clean_sec,
                "metadata": meta or {},
                "ipc_to_bns": ipc_to_bns,
                "bns_to_ipc": bns_to_ipc,
                "statute_text": sec_text,
            },
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Error retrieving statute: {str(e)}"}
        )


@router.get("/sample-cases")
async def get_sample_cases():
    """
    Returns curated legal benchmark cases across Indian Criminal Law
    for instant 1-click execution in the UI.
    """
    return {
        "success": True,
        "cases": [
            {
                "id": "dowry_cruelty",
                "title": "Matrimonial Cruelty & Dowry Demand",
                "act": "IPC 498A ⇄ BNS 85",
                "regime": "IPC + CrPC",
                "court": "Sessions Court",
                "tag": "Anticipatory Bail",
                "summary": "Complainant married applicant in 2021. Alleges continuous dowry demands of ₹5 lakhs and car, emotional cruelty, and physical ejection from matrimonial home.",
                "text": "The applicant seeks anticipatory bail in connection with FIR No. 204/2024 registered at Pune Police Station. The complainant, Kavya, married the applicant Rohan in December 2021. The FIR alleges that shortly after marriage, the applicant and his parents commenced persistent demands for an additional ₹5,00,000 cash dowry and a vehicle. Complainant alleges verbal abuse, mental cruelty, financial restrictions, and that on 14th June 2024, she was physically assaulted and forced out of the house. The applicant submits that allegations are exaggerated arising from matrimonial discord, no MLC injury certificate exists, and he is a respected software professional willing to cooperate with investigation."
            },
            {
                "id": "property_assault",
                "title": "House Trespass & Simple Hurt with Threat",
                "act": "IPC 452, 323, 506 ⇄ BNS 332, 115, 351",
                "regime": "BNS + BNSS",
                "court": "Sessions Court",
                "tag": "Anticipatory Bail",
                "summary": "Boundary wall dispute between neighbors. Allegation of unlawful entry, assault with wooden stick causing simple injury, and threat to life.",
                "text": "The applicant seeks anticipatory bail after an FIR was registered at Nashik Road Police Station on 15-08-2024 alleging offences under Sections 332, 115, and 351(2) BNS. Complainant alleges applicant unlawfully entered his courtyard during an argument regarding a boundary fence, pushed him, and brandished a wooden stick causing simple contusions. Complainant also alleges applicant threatened dire consequences if civil suit was not withdrawn. The applicant submits this is a counterblast to an ongoing civil title injunction, cross-complaints were lodged, injuries are minor abrasions, and custodial interrogation is wholly unnecessary."
            },
            {
                "id": "extortion_threat",
                "title": "Extortion & Blackmail via Digital Communications",
                "act": "IPC 384, 506 ⇄ BNS 308, 351",
                "regime": "BNS + BNSS",
                "court": "High Court",
                "tag": "Anticipatory Bail",
                "summary": "Commercial partnership fallout. Demands for ₹10 lakhs accompanied by threats of leaking confidential contracts and defamation.",
                "text": "Anticipatory bail application under Section 482 BNSS before the High Court of Bombay. FIR lodged at Cyber Police Station Bandra alleging that former business consultant demanded ₹10,00,000 under threat of publishing confidential trade records and filing defamatory criminal petitions against the complainant company directors. Complainant transferred ₹2,00,000 into a bank account. Applicant contends that the sum requested was legitimate outstanding consultancy fee as per signed MoA, emails demonstrate contractual settlement negotiations, and no criminal extortion was ever intended."
            },
            {
                "id": "culpable_homicide_negligence",
                "title": "Rash & Negligent Driving Causing Fatal Injury",
                "act": "IPC 304A ⇄ BNS 106",
                "regime": "BNS + BNSS",
                "court": "Sessions Court",
                "tag": "Regular Bail / Relief",
                "summary": "Motor vehicle collision at late evening intersection resulting in pedestrian fatality. Allegation of speeding without headlights.",
                "text": "FIR No. 88/2024 registered under Section 106(1) BNS at Thane City Police Station. Accused driver of commercial truck was involved in a collision with a motorcyclist at a dimly lit junction. Motorcyclist succumbed to head injuries at Civil Hospital. Accused remained at the scene, called ambulance, and submitted to breathalyzer test indicating zero blood alcohol content. Applicant seeks anticipatory bail citing mechanical brake failure, absence of rash intention, complete cooperation with police, and availability of dashcam telemetry."
            }
        ]
    }
