"""
CLI and Python runner for Stage 0 (Intake), Stage 1 (Query Understanding), Stage 2 (Batched Sub-Query Mapping), Stage 3 (Chapter Identification), Stage 3b (BSA Retrieval), Stage 3c (BNSS Retrieval), Stage 4 (Statutory Verification), and Special Act Routing.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .pipeline import Stage0Pipeline
from .stage1_pipeline import Stage1Pipeline
from .stage2_pipeline import Stage2Pipeline
from .stage3_pipeline import Stage3Pipeline
from .stage4_pipeline import Stage4Pipeline
from .bsa_retrieval_agent import BSARetrievalAgent
from .bnss_retrieval_agent import BNSSRetrievalAgent
from .act_router import SpecialActRetrievalAgent
from .statute_repository import StatuteRepository
from .schemas import IntakeInput


def _print_pipeline_transition(stage_num: int, res: dict) -> None:
    """Prints a concise pipeline transition summary after each stage output."""
    sep = "=" * 60
    if stage_num == 2:
        mappings = res.get("mappings", [])
        all_sections: dict = {}
        for m in mappings:
            sq_id = m.get("sub_query_id", "?")
            for bucket in ("primary_candidate_sections", "secondary_candidate_sections", "conditional_candidate_sections"):
                for c_item in m.get(bucket, []):
                    all_sections.setdefault(c_item.get("section_number", "?"), {"classifications": [], "sub_queries": []})                         .setdefault("sources", set()).update(c_item.get("retrieval_sources") or [])
            for p in m.get("primary_candidate_sections", []):
                s = p.get("section_number", "?")
                all_sections.setdefault(s, {"classifications": [], "sub_queries": []})
                all_sections[s]["classifications"].append("PRIMARY")
                all_sections[s]["sub_queries"].append(sq_id)
            for s_item in m.get("secondary_candidate_sections", []):
                s = s_item.get("section_number", "?")
                all_sections.setdefault(s, {"classifications": [], "sub_queries": []})
                all_sections[s]["classifications"].append("SECONDARY")
                all_sections[s]["sub_queries"].append(sq_id)
            for c in m.get("conditional_candidate_sections", []):
                s = c.get("section_number", "?")
                all_sections.setdefault(s, {"classifications": [], "sub_queries": []})
                all_sections[s]["classifications"].append("CONDITIONAL")
                all_sections[s]["sub_queries"].append(sq_id)
            for s in m.get("candidate_sections", []):
                if isinstance(s, str):
                    all_sections.setdefault(s, {"classifications": [], "sub_queries": []})
                    all_sections[s]["classifications"].append("CANDIDATE")
                    all_sections[s]["sub_queries"].append(sq_id)
        print(f"\n{sep}", flush=True)
        print(f"  STAGE 2 -> STAGE 3 PIPELINE HANDOFF", flush=True)
        print(sep, flush=True)
        print(f"  Sections being passed to Stage 3 ({len(all_sections)} total):", flush=True)
        for sec, info in sorted(all_sections.items()):
            types = "/".join(sorted(set(info["classifications"])))
            sqs = ", ".join(sorted(set(info["sub_queries"])))
            srcs = ", ".join(sorted(info.get("sources") or [])) or "n/a"
            print(f"    [OK] Section {sec:>6}  [{types}]  (from {sqs}; found by: {srcs})", flush=True)
        excluded = [(n.get("section_number"), n.get("not_triggered_reason", "")) for m in mappings for n in m.get("not_triggered_sections", [])]
        if excluded:
            print(f"  Screened and excluded ({len(excluded)}): " + ", ".join(x for x, _ in excluded), flush=True)
        print(sep, flush=True)
    elif stage_num == 3:
        pt = res.get("pipeline_transition")
        if not pt:
            accepted = [vo.get("section_number") for vo in res.get("verified_offences", [])]
            print(f"\n{sep}", flush=True)
            print(f"  STAGE 3 -> STAGE 4 PIPELINE HANDOFF", flush=True)
            print(sep, flush=True)
            print(f"  Sections passing to Stage 4: {accepted}", flush=True)
            print(sep, flush=True)
            return
        received = pt.get("stage2_input_sections", [])
        accepted = pt.get("stage3_accepted_sections", [])
        rejected = pt.get("stage3_rejected_sections", [])
        print(f"\n{sep}", flush=True)
        print(f"  STAGE 3 -> STAGE 4 PIPELINE HANDOFF", flush=True)
        print(sep, flush=True)
        print(f"  Received from Stage 2 ({len(received)}): {received}", flush=True)
        print(f"  Accepted by Stage 3   ({len(accepted)}): {accepted}", flush=True)
        if rejected:
            print(f"  Rejected by Stage 3   ({len(rejected)}):", flush=True)
            for r in rejected:
                print(f"    [!!] Section {r.get('section_number'):>6}  [{r.get('rejection_type', 'UNKNOWN')}]  -- {r.get('reason', '')}", flush=True)
        else:
            print(f"  Rejected by Stage 3   (0): None", flush=True)
        print(f"  Passing to Stage 4: {pt.get('passing_to_stage4', accepted)}", flush=True)
        print(sep, flush=True)
    elif stage_num == 4:
        pt = res.get("pipeline_transition")
        if not pt:
            accepted = [vs.get("section_number") for vs in res.get("verified_sections", [])]
            print(f"\n{sep}", flush=True)
            print(f"  STAGE 4 STATUTORY VERIFICATION COMPLETE", flush=True)
            print(sep, flush=True)
            print(f"  Sections confirmed: {accepted}", flush=True)
            print(sep, flush=True)
            return
        received = pt.get("stage3_input_sections", [])
        accepted = pt.get("stage4_accepted_sections", [])
        rejected = pt.get("stage4_rejected_sections", [])
        print(f"\n{sep}", flush=True)
        print(f"  STAGE 4 STATUTORY VERIFICATION COMPLETE", flush=True)
        print(sep, flush=True)
        print(f"  Received from Stage 3 ({len(received)}): {received}", flush=True)
        print(f"  Confirmed by Stage 4  ({len(accepted)}): {accepted}", flush=True)
        if rejected:
            print(f"  Dropped by Stage 4    ({len(rejected)}):", flush=True)
            for r in rejected:
                print(f"    [!!] Section {r.get('section_number'):>6}  -- {r.get('reason', '')}", flush=True)
        else:
            print(f"  Dropped by Stage 4    (0): None", flush=True)
        print(f"  Verified Stage 4 sections: {pt.get('passing_to_stage5', accepted)}", flush=True)
        print(sep, flush=True)


def run_stage0(
    text: Optional[str] = None,
    file_path: Optional[str] = None,
    user_query: Optional[str] = None,
    court_type: Optional[str] = None,
    legal_regime_override: Optional[str] = None,
) -> dict:
    """
    Executes Stage 0 pipeline and returns dict representation of CaseContextObject.
    """
    print("\n" + "=" * 60, flush=True)
    print("  STAGE 0: CASE INTAKE & CONTEXT INITIALIZATION", flush=True)
    print("=" * 60, flush=True)
    if file_path:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if p.suffix.lower() == ".pdf":
            try:
                import fitz
                doc = fitz.open(str(p))
                pages_text = [page.get_text() for page in doc]
                doc_text = "\n".join(pages_text)
            except Exception:
                import pypdf
                reader = pypdf.PdfReader(str(p))
                pages_text = [page.extract_text() or "" for page in reader.pages]
                doc_text = "\n".join(pages_text)
        else:
            doc_text = p.read_text(encoding="utf-8")
    elif text:
        doc_text = text
    else:
        raise ValueError("No input text or file path provided to Stage 0 intake.")

    inp = IntakeInput(
        documents_text=doc_text,
        user_query=user_query or "",
        court_type=court_type,
        legal_regime_override=legal_regime_override,
    )

    pipeline = Stage0Pipeline()
    result = pipeline.run(inp)
    cco = result.export_case_context_object()
    cco_dict = cco.model_dump()
    _cp = cco_dict.get("case_profile") or {}
    regime = _cp.get("legal_regime") or "Unknown"
    jurisdiction = (_cp.get("case_metadata") or {}).get("state") or "Unknown"
    contract = cco_dict.get("contract_status") or "Unknown"
    parties = cco_dict.get("active_parties") or []
    print(f"  [OK] Legal Regime     : {regime}", flush=True)
    print(f"  [OK] Jurisdiction     : {jurisdiction}", flush=True)
    print(f"  [OK] Contract Status  : {contract}", flush=True)
    print(f"  [OK] Active Parties   : {', '.join(parties) if parties else 'None identified'}", flush=True)
    print("=" * 60, flush=True)
    return cco_dict


def run_stage1(case_context_input: dict) -> dict:
    """
    Executes Stage 1 pipeline on CaseContextObject dict and returns LegalQueryObject dict.
    """
    print("\n" + "=" * 60, flush=True)
    print("  STAGE 1: LEGAL QUERY DECONSTRUCTION", flush=True)
    print("=" * 60, flush=True)
    pipeline = Stage1Pipeline()
    res = pipeline.run(case_context_input)
    if res.verified_query_object:
        result = res.verified_query_object.model_dump()
        result["status"] = "OK"
        result["verification_status"] = "VERIFIED"
        result["verification_feedback"] = res.feedback
        sub_queries = result.get("sub_queries") or []
        concepts = result.get("legal_concepts") or []
        print(f"  [OK] Sub-queries identified : {len(sub_queries)}", flush=True)
        print(f"  [OK] Legal concepts          : {len(concepts)}", flush=True)
        print("=" * 60, flush=True)
        return result
    cand_obj = res.candidate_query_object
    if cand_obj is not None and cand_obj.factual_allegations:
        # The LLM verifier's objections are review notes, not proof the decomposition is unusable. Continue
        # (DEGRADED) when the deterministic checks pass: quotes occur in the narrative, families are valid.
        from .family_retrieval import validate_decomposition
        check = validate_decomposition(cand_obj.case_facts or "", cand_obj.factual_allegations, cand_obj.offence_families)
        if check.ok:
            result = cand_obj.model_dump()
            result["status"] = "DEGRADED"
            result["verification_status"] = res.status
            result["verification_feedback"] = res.feedback
            print(f"  [DEGRADED] Stage 1 verifier raised issues ({res.status}); structural checks passed, continuing.", flush=True)
            print(f"  [DEGRADED] Facts: {len(cand_obj.factual_allegations)} | Families: {len(cand_obj.offence_families)}", flush=True)
            print("=" * 60, flush=True)
            return result
    print(f"  [{res.status}] Stage 1 verification failed structural checks. Dependent stages blocked.", flush=True)
    print("=" * 60, flush=True)
    return {
        "status": "BLOCKED",
        "verification_status": res.status,
        "feedback": res.feedback,
        "candidate_query_object": cand_obj.model_dump() if cand_obj else None,
    }


def _blocked(stage_input: Optional[dict], stage_name: str) -> Optional[dict]:
    """A BLOCKED upstream result must not be parsed as an (empty) query object downstream."""
    if isinstance(stage_input, dict) and stage_input.get("status") == "BLOCKED":
        print(f"  [BLOCKED] {stage_name} skipped: upstream Stage 1 is blocked.", flush=True)
        return {"status": "BLOCKED", "feedback": f"{stage_name} skipped because Stage 1 is blocked."}
    return None


def run_stage2(legal_query_input: dict) -> dict:
    """
    Executes Stage 2 pipeline on LegalQueryObject dict and returns Stage2BatchedMappingResponse dict.
    """
    blocked = _blocked(legal_query_input, "Stage 2")
    if blocked:
        return blocked
    verification_status = str(legal_query_input.get("verification_status", "")).upper()
    if verification_status and verification_status != "VERIFIED":
        print(f"  [NOTICE] Proceeding with Stage 1 status: {verification_status}", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("  STAGE 2: BATCHED SUB-QUERY PRE-FILTER MAPPING", flush=True)
    print("=" * 60, flush=True)
    pipeline = Stage2Pipeline()
    res = pipeline.run(legal_query_input)
    if res.batched_mapping_response:
        result = res.batched_mapping_response.model_dump()
        mappings = result.get("mappings") or []
        total_candidates = sum(
            len(m.get("primary_candidate_sections", []))
            + len(m.get("secondary_candidate_sections", []))
            + len(m.get("conditional_candidate_sections", []))
            for m in mappings
        )
        print(f"  [OK] Sub-query mappings : {len(mappings)}", flush=True)
        print(f"  [OK] Candidate sections : {total_candidates}", flush=True)
        print("=" * 60, flush=True)
        return result
    print("=" * 60, flush=True)
    return {"status": res.status, "feedback": res.feedback}


def run_stage3(legal_query_input: dict, stage2_input: Optional[dict] = None) -> dict:
    """
    Executes Stage 3 pipeline on LegalQueryObject and Stage 2 verified mapping dicts.
    """
    print("\n" + "=" * 60, flush=True)
    print("  STAGE 3: CHAPTER IDENTIFICATION & IPC ⇄ BNS NORMALIZATION", flush=True)
    print("=" * 60, flush=True)
    blocked = _blocked(legal_query_input, "Stage 3")
    if blocked:
        return blocked
    pipeline = Stage3Pipeline()
    res = pipeline.run(legal_query_input, stage2_mapping=stage2_input)
    if res.verified_chapter_object:
        result = res.verified_chapter_object.model_dump()
        verified = result.get("verified_offences") or []
        print(f"  [OK] Verified offences : {len(verified)}", flush=True)
        for vo in verified:
            sec = vo.get("section_number", "?")
            title = (vo.get("section_title") or vo.get("offence_title") or "")[:50]
            print(f"    ✓ Section {sec:<6} {title:<50} [{vo.get('classification') or ''}]", flush=True)
        print("=" * 60, flush=True)
        return result
    print("=" * 60, flush=True)
    return {"status": res.status, "feedback": res.feedback}


def _print_act_sections(act: str, result_dict: dict) -> None:
    sections = result_dict.get("relevant_sections", [])
    rejected = result_dict.get("rejected_sections", [])
    print(f"\n  [{act} SECTIONS ({len(sections)})]:", flush=True)
    for sec in sections:
        print(
            f"    ✓ [{act} {sec['section_number']:>3}] {sec['heading'][:55]:<55} "
            f"| {sec.get('applicability', ''):<10} | {sec.get('relevance_category') or ''}",
            flush=True,
        )
        reason = sec.get("relevance_reason") or sec.get("verification_reason") or ""
        if reason:
            print(f"      {reason}", flush=True)
    if rejected:
        print(f"\n  [REJECTED {act} CANDIDATES ({len(rejected)})]:", flush=True)
        for sec in rejected[:5]:
            print(f"    ✗ [{act} {sec['section_number']:>3}] {sec['heading'][:45]:<45} -> {sec.get('verification_reason') or ''}", flush=True)
    for note in result_dict.get("retrieval_notes", []):
        if not note.startswith(("Verifier ACCEPTED", "Verifier REJECTED")):
            print(f"  NOTE: {note}", flush=True)


def run_stage3b(
    legal_query_input: dict,
    stage3_input: Optional[dict] = None,
) -> dict:
    """
    Stage 3b: BSA evidence-law section retrieval. The complete Adhiniyam is shown to one nomination call
    (act_nominator); evidence-cluster retrieval is the fallback. IEA equivalents are resolved after Stage 4.
    """
    blocked = _blocked(legal_query_input, "Stage 3b")
    if blocked:
        return blocked
    print("\n" + "=" * 60, flush=True)
    print("  STAGE 3b: BSA EVIDENCE LAW SECTION RETRIEVAL", flush=True)
    print("=" * 60, flush=True)
    verified_offences = (stage3_input or {}).get("verified_offences", []) if stage3_input else None
    result_dict = BSARetrievalAgent().run(legal_query=legal_query_input, verified_offences=verified_offences).model_dump()
    _print_act_sections("BSA", result_dict)
    print("=" * 60, flush=True)
    return result_dict


def run_stage3c(
    legal_query_input: dict,
    case_context: Optional[dict] = None,
    stage3_input: Optional[dict] = None,
) -> dict:
    """
    Stage 3c: BNSS procedural-law section retrieval. The complete Sanhita is shown to one nomination call with
    the procedural stage, relief and the Stage 3 offences (punishment, bailability); the prefilter is the
    fallback. CrPC equivalents are resolved after Stage 4.
    """
    print("\n" + "=" * 60, flush=True)
    print("  STAGE 3c: BNSS PROCEDURAL LAW SECTION RETRIEVAL", flush=True)
    print("=" * 60, flush=True)
    query = legal_query_input
    if isinstance(query, dict) and query.get("status") == "BLOCKED":
        query = query.get("candidate_query_object") or {}
    verified_offences = (stage3_input or {}).get("verified_offences", []) if stage3_input else None
    result_dict = BNSSRetrievalAgent().run(
        legal_query=query, case_context=case_context, verified_offences=verified_offences,
    ).model_dump()
    _print_act_sections("BNSS", result_dict)
    print("=" * 60, flush=True)
    return result_dict


def run_stage4(
    legal_query_input: dict,
    chapter_input: dict,
    bsa_input: Optional[dict] = None,
    bnss_input: Optional[dict] = None,
    print_summary: bool = True,
) -> dict:
    """
    Stage 4: ingredient-level verification of the Stage 3 offences, then the Act Router, then one statute
    equivalence step (IPC->BNS, BNSS->CrPC, BSA->IEA) over everything the pipeline retrieved.
    """
    blocked = _blocked(legal_query_input, "Stage 4")
    if blocked:
        return blocked
    pipeline = Stage4Pipeline()
    res = pipeline.run(legal_query_input, chapter_input)

    stage4_dict = (
        res.verified_statutory_object.model_dump()
        if res.verified_statutory_object
        else {"status": res.status, "feedback": res.feedback}
    )
    if print_summary:
        _print_stage4_outcome(stage4_dict)

    try:
        stage4_dict["act_router_output"] = run_act_router(
            legal_query_input=legal_query_input,
            stage4_input=stage4_dict,
            bsa_input=bsa_input or {},
            bnss_input=bnss_input or {},
        )
    except Exception as e:
        print(f"  [Act Router] Note: {e}", flush=True)
        stage4_dict["act_router_output"] = {}

    run_equivalence_mapping(stage4_dict, bsa_input or {}, bnss_input or {}, print_table=print_summary)
    return stage4_dict


def _print_stage4_outcome(stage4_dict: dict) -> None:
    sep = "=" * 80
    print(f"\n{sep}\n  STAGE 4 OUTCOME (ingredient verification)\n{sep}", flush=True)
    groups = [
        ("ATTRACTED", stage4_dict.get("attracted_offences") or []),
        ("CONDITIONAL (depends on a fact not yet alleged)", stage4_dict.get("conditional_offences") or []),
        ("NOT ATTRACTED", stage4_dict.get("rejected_offences") or []),
    ]
    for label, items in groups:
        print(f"  {label} ({len(items)}):", flush=True)
        if not items:
            print("      • none", flush=True)
        for o in items:
            gaps = [e.get("ingredient") for e in (o.get("ingredient_evaluation") or [])
                    if str(e.get("status", "")).upper() in ("MISSING", "NOT SATISFIED", "CONTRADICTED", "UNKNOWN")]
            line = f"      • IPC {o.get('section_number'):<5} {(o.get('title') or '')[:55]:<55} {o.get('overall_status') or ''}"
            print(line, flush=True)
            if gaps and label != "ATTRACTED":
                print(f"          missing: {'; '.join(str(g)[:70] for g in gaps[:3])}", flush=True)
    print(f"  Status: {stage4_dict.get('verification_status')}", flush=True)
    print(sep, flush=True)


def run_equivalence_mapping(stage4_dict: dict, bsa_input: dict, bnss_input: dict, print_table: bool = True) -> dict:
    """
    Resolves new-code / old-code equivalents once, for everything retrieved: attracted and conditional IPC
    offences -> BNS, BNSS -> CrPC, BSA -> IEA, all from the Neo4j crosswalk (CrosswalkService). Stores the
    lists on stage4_dict (keys read by precedent retrieval) and prints one table.
    """
    from .crosswalk_service import CrosswalkService
    cw = CrosswalkService.get_instance()

    ipc_rows = []
    for status, key in (("ATTRACTED", "attracted_offences"), ("CONDITIONAL", "conditional_offences")):
        for o in stage4_dict.get(key) or []:
            sec = str(o.get("section_number") or "").strip().upper()
            targets = list(cw.ipc_to_bns.get(sec, []))
            ipc_rows.append({
                "ipc_section": sec, "title": o.get("title") or "", "status": status,
                "bns_equivalent": cw.get_bns_for_ipc(sec) or "N/A", "bns_all_targets": targets,
            })
    bnss_rows = [{
        "bnss_section": s.get("section_number"), "heading": s.get("heading", ""),
        "category": s.get("relevance_category", ""), "applicability": s.get("applicability", ""),
        "crpc_equivalent": cw.get_crpc_for_bnss(str(s.get("section_number"))) or s.get("replaces_CrPC") or "None",
    } for s in (bnss_input.get("relevant_sections") or [])]
    bsa_rows = [{
        "bsa_section": s.get("section_number"), "heading": s.get("heading", ""),
        "category": s.get("relevance_category", ""), "applicability": s.get("applicability", ""),
        "iea_equivalent": cw.get_iea_for_bsa(str(s.get("section_number"))) or s.get("replaces_IEA") or "None",
    } for s in (bsa_input.get("relevant_sections") or [])]

    stage4_dict["ipc_to_bns_equivalents"] = ipc_rows
    stage4_dict["bnss_to_crpc_equivalents"] = bnss_rows
    stage4_dict["bsa_to_iea_equivalents"] = bsa_rows
    if print_table:
        _print_equivalence_table(stage4_dict)
    return {"ipc_to_bns": ipc_rows, "bnss_to_crpc": bnss_rows, "bsa_to_iea": bsa_rows}


def _print_equivalence_table(stage4_dict: dict) -> None:
    ipc_rows = stage4_dict.get("ipc_to_bns_equivalents") or []
    bnss_rows = stage4_dict.get("bnss_to_crpc_equivalents") or []
    bsa_rows = stage4_dict.get("bsa_to_iea_equivalents") or []
    sep = "=" * 80
    print(f"\n{sep}\n  STATUTE EQUIVALENCE MAPPING (Neo4j crosswalk)\n{sep}", flush=True)
    regime = str(stage4_dict.get("legal_regime") or "").upper()
    if "IPC" in regime or "CRPC" in regime:
        print(f"  Selected regime (Stage 0): {stage4_dict.get('legal_regime')} - the IPC / CrPC / IEA sections apply;", flush=True)
        print("  BNS / BNSS / BSA are their equivalents under the 2023 codes (BNSS / BSA retrieval runs on the new text).", flush=True)
    elif regime:
        print(f"  Selected regime (Stage 0): {stage4_dict.get('legal_regime')} - the BNS / BNSS / BSA sections apply;", flush=True)
        print("  IPC / CrPC / IEA are the repealed-code equivalents.", flush=True)
    print("  [1] IPC → BNS (substantive offences):", flush=True)
    for r in ipc_rows or [{}]:
        if not r:
            print("      • none", flush=True)
            break
        extra = f"  (all targets: {', '.join(r['bns_all_targets'])})" if len(r["bns_all_targets"]) > 1 else ""
        print(f"      • IPC {r['ipc_section']:<5} ──► BNS {r['bns_equivalent']:<8} [{r['status']}] {r['title'][:45]}{extra}", flush=True)
    print("  [2] BNSS → CrPC (procedure):", flush=True)
    for r in bnss_rows or [{}]:
        if not r:
            print("      • none", flush=True)
            break
        print(f"      • BNSS {r['bnss_section']:<5} ──► CrPC {r['crpc_equivalent']:<10} [{r['applicability']}] {r['heading'][:45]}", flush=True)
    print("  [3] BSA → IEA (evidence):", flush=True)
    for r in bsa_rows or [{}]:
        if not r:
            print("      • none", flush=True)
            break
        print(f"      • BSA {r['bsa_section']:<5} ──► IEA {r['iea_equivalent']:<10} [{r['applicability']}] {r['heading'][:45]}", flush=True)
    print(sep, flush=True)


def run_act_router(
    case_context_input: Optional[dict] = None,
    legal_query_input: Optional[dict] = None,
    stage4_input: Optional[dict] = None,
    bsa_input: Optional[dict] = None,
    bnss_input: Optional[dict] = None,
) -> dict:
    """
    Executes the Special Act Router Sub-Pipeline.
    Runs after Stage 4:
      1. Evaluates applicability of the 8 Special Acts using special_act_routing_prompt.txt.
      2. Runs a 0-API-call candidate prefilter on the selected Special Act JSON(s).
      3. Performs definition-grounded LLM retrieval and verifier auditing on candidate sections.
      No statutory ingredients and no Neo4j mappings are performed for Special Acts.
    """
    agent = SpecialActRetrievalAgent()

    # Extract case facts
    case_facts_parts = []
    if case_context_input:
        cf = case_context_input.get("case_facts") or case_context_input.get("raw_text")
        if isinstance(cf, str) and cf:
            case_facts_parts.append(cf)
    if legal_query_input:
        for k in ["case_facts", "raw_text", "text", "raw_case_text", "user_query"]:
            v = legal_query_input.get(k)
            if isinstance(v, str) and v:
                case_facts_parts.append(v)
        imp = legal_query_input.get("important_facts")
        if isinstance(imp, dict):
            for val in imp.values():
                if isinstance(val, str) and val:
                    case_facts_parts.append(val)
                elif isinstance(val, list):
                    case_facts_parts.extend(str(x) for x in val if x)
        cs = legal_query_input.get("case_summary")
        if isinstance(cs, str) and cs:
            case_facts_parts.append(cs)

    case_facts = " ".join(case_facts_parts).strip()

    # Extract concepts
    concepts = []
    if legal_query_input:
        for c in legal_query_input.get("legal_concepts", []):
            ct = c.get("concept") if isinstance(c, dict) else getattr(c, "concept", "")
            if ct:
                concepts.append(ct)

    # Extract IPC / BNS sections from Stage 4
    ipc_bns = (stage4_input or {}).get("ipc_to_bns_equivalents", [])
    if not ipc_bns and stage4_input:
        for off in stage4_input.get("verified_offences", []):
            ipc_bns.append({
                "ipc_section": off.get("section_number"),
                "title": off.get("section_title") or off.get("offence_title"),
                "bns_equivalent": off.get("bns_equivalent"),
            })

    # Extract BSA sections
    bsa_sections = (stage4_input or {}).get("bsa_to_iea_equivalents") or (bsa_input or {}).get("relevant_sections", [])

    # Extract BNSS sections
    bnss_sections = (stage4_input or {}).get("bnss_to_crpc_equivalents") or (bnss_input or {}).get("relevant_sections", [])

    print("\n" + "=" * 60, flush=True)
    print("  ACT ROUTER SUB-PIPELINE: SPECIAL ACT APPLICABILITY & RETRIEVAL", flush=True)
    print("=" * 60, flush=True)

    result = agent.run(
        case_facts=case_facts,
        legal_concepts=concepts,
        ipc_bns_sections=ipc_bns,
        bsa_sections=bsa_sections,
        bnss_sections=bnss_sections,
    )

    result_dict = result.model_dump()
    routings = result_dict.get("act_routing", [])
    relevant_secs = result_dict.get("relevant_sections", [])
    rejected_secs = result_dict.get("rejected_sections", [])

    print(f"\n  [SPECIAL ACT ROUTING DECISIONS (8 ACTS)]:", flush=True)
    for r in routings:
        dec = r.get("decision", "SKIP")
        doc = r.get("document", "")
        title = r.get("act_title") or doc
        reason = r.get("reason", "")
        marker = "✓" if dec == "PROCESS" else ("?" if dec == "CANDIDATE" else "✗")
        print(f"    {marker} [{dec:<9}] {title[:48]:<48} -> {reason[:75]}", flush=True)

    if relevant_secs:
        print(f"\n  [VERIFIED SPECIAL ACT SECTIONS ({len(relevant_secs)})]:", flush=True)
        for s in relevant_secs:
            doc = s.get("act_document", "")
            s_num = s.get("section_number", "")
            heading = s.get("heading", "")
            cat = s.get("relevance_category", "SPECIAL_OFFENCE")
            v_reason = s.get("verification_reason") or s.get("relevance_reason") or ""
            print(f"    ✓ [{doc}] Sec {s_num:>4}: {heading[:45]:<45} | [{cat}]", flush=True)
            if v_reason:
                print(f"      Grounding: {v_reason}", flush=True)
    else:
        print("\n  [VERIFIED SPECIAL ACT SECTIONS]: None (No Special Act provisions applicable to facts)", flush=True)

    if rejected_secs:
        print(f"\n  [AUDITED & REJECTED SPECIAL ACT CANDIDATES ({len(rejected_secs)})]:", flush=True)
        for s in rejected_secs[:5]:
            doc = s.get("act_document", "")
            s_num = s.get("section_number", "")
            rej_reason = s.get("verification_reason") or "Factual prerequisite not established"
            print(f"    ✗ [{doc}] Sec {s_num:>4} -> {rej_reason[:70]}", flush=True)

    print("=" * 60, flush=True)
    return result_dict




def _precedent_legal_issues(stage1: dict, stage0: dict) -> list:
    """
    Legal questions for precedent screening: the requested relief, the parties' procedural submissions
    (Stage 1 STATEMENT facts such as custodial interrogation or witness influence), and the offence
    sub-queries. Without the procedural questions the screen can only judge factual similarity.
    """
    issues = []
    prof = (stage0 or {}).get("case_profile") or {}
    relief = prof.get("requested_relief") or prof.get("procedural_stage")
    if relief:
        issues.append(f"Requested relief: {relief}")
    for f in (stage1 or {}).get("factual_allegations", []) or []:
        if str(f.get("conduct_type", "")).upper() == "STATEMENT":
            issues.append(f.get("description") or f.get("verbatim_quote") or "")
    for sq in (stage1 or {}).get("sub_queries", []) or []:
        if sq.get("query"):
            issues.append(sq["query"])
    return [i for i in issues if i]

def run_full_pipeline(
    text: Optional[str] = None,
    file_path: Optional[str] = None,
    user_query: Optional[str] = None,
    court_type: Optional[str] = None,
    legal_regime_override: Optional[str] = None,
    run_precedent_retrieval: bool = True,
    max_precedent_candidates: int = 12,
) -> dict:
    """
    Chains Stage 0 -> Stage 1 -> Stage 2 -> Stage 3 -> Stage 3b -> Stage 3c -> Stage 4 -> Stage 5 (Precedent Retrieval)
    and returns combined outputs.
    Stage 3b: BSA Evidence Law Section Retrieval.
    Stage 3c: BNSS Procedural Law Section Retrieval.
    Stage 4: Offence verification + Act Router (special statutes).
    Stage 5: Precedent Retrieval (optional, enabled by default).
    
    Args:
        text: Raw case text input
        file_path: Path to input file
        user_query: User instructions/query
        court_type: Court type (Sessions Court / High Court)
        legal_regime_override: Legal regime override (default: IPC + CrPC)
        run_precedent_retrieval: Whether to run Stage 5 precedent retrieval (default: True)
        max_precedent_candidates: Maximum precedent candidates to retrieve (default: 20)
    
    Returns:
        Combined dictionary with all stage outputs including precedent retrieval
    """
    from .config import reset_request_budget
    reset_request_budget()

    stage0_out = run_stage0(
        text=text,
        file_path=file_path,
        user_query=user_query,
        court_type=court_type,
        legal_regime_override=legal_regime_override,
    )

    stage1_out = run_stage1(stage0_out)
    if stage1_out.get("status") == "BLOCKED":
        return {
            "status": "BLOCKED",
            "blocking_stage": "STAGE_1",
            "stage0_result": stage0_out,
            "stage1_result": stage1_out,
            "feedback": stage1_out.get("feedback", "Stage 1 verification failed. Dependent stages blocked.")
        }

    import concurrent.futures
    import time

    stage_timings: Dict[str, int] = {}

    t_s2 = time.perf_counter()
    stage2_out = run_stage2(stage1_out)
    stage_timings["stage2_ms"] = int((time.perf_counter() - t_s2) * 1000)

    t_s3 = time.perf_counter()
    stage3_out = run_stage3(stage1_out, stage2_out)
    stage_timings["stage3_ms"] = int((time.perf_counter() - t_s3) * 1000)

    # Execute Stage 3b (BSA Evidence Law) and Stage 3c (BNSS Procedural Law) concurrently
    t_parallel = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_3b = executor.submit(run_stage3b, stage1_out, stage3_out)
        f_3c = executor.submit(run_stage3c, stage1_out, stage0_out, stage3_out)
        stage3b_out = f_3b.result()
        stage3c_out = f_3c.result()
    stage_timings["stage3b_3c_concurrent_ms"] = int((time.perf_counter() - t_parallel) * 1000)

    t_s4 = time.perf_counter()
    stage4_out = run_stage4(stage1_out, stage3_out, bsa_input=stage3b_out, bnss_input=stage3c_out)
    stage_timings["stage4_ms"] = int((time.perf_counter() - t_s4) * 1000)

    result = {
        "status": "DEGRADED" if stage1_out.get("status") == "DEGRADED" else "VERIFIED",
        "stage0_result": stage0_out,
        "stage0_case_context": stage0_out,
        "stage1_result": stage1_out,
        "stage1_legal_query": stage1_out,
        "stage2_result": stage2_out,
        "stage2_subquery_mapping": stage2_out,
        "stage3_result": stage3_out,
        "stage3_chapter_identification": stage3_out,
        "stage3b_result": stage3b_out,
        "stage3b_bsa_retrieval": stage3b_out,
        "stage3c_result": stage3c_out,
        "stage3c_bnss_retrieval": stage3c_out,
        "stage4_result": stage4_out,
        "stage4_statutory_verification": stage4_out,
        "stage4b_act_router": stage4_out.get("act_router_output", {}),
        "stage_durations_ms": stage_timings,
    }

    # Stage 5: Precedent Retrieval (optional)
    if run_precedent_retrieval:
        try:
            from precedent_retrieval.pipeline import PrecedentPipeline
            
            print("\n" + "="*80)
            print("STAGE 5: PRECEDENT RETRIEVAL")
            print("="*80)
            
            # Extract legal issues from Stage 1
            legal_issues = []
            if stage1_out and isinstance(stage1_out, dict):
                sub_queries = stage1_out.get('sub_queries', [])
                legal_issues = _precedent_legal_issues(stage1_out, stage0_out)
            
            print(f"\n[Stage 5] Extracted {len(legal_issues)} legal issues from Stage 1")
            print(f"[Stage 5] Running precedent retrieval with max {max_precedent_candidates} candidates...")
            
            # Run precedent retrieval
            prec_pipeline = PrecedentPipeline(max_candidates=max_precedent_candidates)
            prec_result = prec_pipeline.run(
                case_context=stage0_out,
                statutory_object=stage4_out,
                legal_issues=legal_issues
            )
            
            # Add to result
            result["stage5_result"] = prec_result.model_dump() if hasattr(prec_result, 'model_dump') else prec_result
            result["stage5_precedent_retrieval"] = result["stage5_result"]
            
            prec_obj = prec_result.verified_precedent_object
            print(f"\n[Stage 5] ✅ Precedent Retrieval Complete")
            print(f"  - Judgments Scanned: {prec_obj.total_judgments_scanned}")
            print(f"  - Candidates Matched: {prec_obj.candidates_after_statutory_match}")
            print(f"  - Prosecution Precedents: {len(prec_obj.prosecution_precedents)}")
            print(f"  - Defense Precedents: {len(prec_obj.defense_precedents)}")
            
        except Exception as e:
            print(f"\n[Stage 5] ⚠️  Precedent Retrieval Failed: {e}")
            import traceback
            traceback.print_exc()
            result["stage5_result"] = {
                "status": "FAILED",
                "error": str(e),
                "error_type": type(e).__name__
            }
            result["stage5_precedent_retrieval"] = result["stage5_result"]

    return result


def main():
    parser = argparse.ArgumentParser(description="Run Stage 0-5 LexiGraph Backend Pipeline (with optional Precedent Retrieval)")
    parser.add_argument("--file", "-f", type=str, help="Path to input raw document text file")
    parser.add_argument("--text", "-t", type=str, help="Raw document text input string")
    parser.add_argument("--query", "-q", type=str, help="User instructions / query")
    parser.add_argument("--court", type=str, help="Court type (Sessions Court / High Court)")
    parser.add_argument("--regime", type=str, default="IPC + CrPC", help="Legal regime (default: IPC + CrPC)")
    parser.add_argument(
        "--stage",
        type=str,
        choices=["0", "1", "2", "3", "3b", "3c", "4", "act_router", "all"],
        default="all",
        help="Target stage to run (0=Intake, 1=Query Understanding, 2=SubQuery Mapping, 3=Chapter Identification, 3b=BSA Retrieval, 3c=BNSS Retrieval, 4=Statutory Verification + Act Router, all=Full Stages 0-5 Pipeline with Precedent Retrieval)",
    )
    parser.add_argument(
        "--precedents",
        action="store_true",
        default=True,
        help="Run Stage 5 precedent retrieval after Stage 4 (default: True when stage=all)"
    )
    parser.add_argument(
        "--no-precedents",
        dest="precedents",
        action="store_false",
        help="Skip Stage 5 precedent retrieval"
    )
    parser.add_argument(
        "--max-precedents",
        type=int,
        default=12,
        help="Maximum precedent candidates to retrieve (default: 20)"
    )

    args = parser.parse_args()

    try:
        if args.stage == "0":
            res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            print("\n=== STAGE 0 CASE CONTEXT RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == "1":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            res = run_stage1(stage0_res)
            print("\n=== STAGE 1 LEGAL QUERY RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == "2":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            res = run_stage2(stage1_res)
            print("\n=== STAGE 2 BATCHED SUB-QUERY MAPPING RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(2, res)
        elif args.stage == "3":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            res = run_stage3(stage1_res, stage2_res)
            print("\n=== STAGE 3 CHAPTER IDENTIFICATION RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(3, res)
        elif args.stage == "3b":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            res = run_stage3b(stage1_res, stage3_res)
            print("\n=== STAGE 3b BSA RETRIEVAL RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == "3c":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            res = run_stage3c(stage1_res, stage0_res)
            print("\n=== STAGE 3c BNSS RETRIEVAL RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == "4":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            stage3b_res = run_stage3b(stage1_res, stage3_res)
            stage3c_res = run_stage3c(stage1_res, stage0_res, stage3_res)
            res = run_stage4(stage1_res, stage3_res, bsa_input=stage3b_res, bnss_input=stage3c_res)
            print("\n=== STAGE 4 STATUTORY VERIFICATION RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == "act_router":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            stage3b_res = run_stage3b(stage1_res, stage3_res)
            stage3c_res = run_stage3c(stage1_res, stage0_res, stage3_res)
            stage4_res = run_stage4(stage1_res, stage3_res, bsa_input=stage3b_res, bnss_input=stage3c_res)
            res = stage4_res.get("act_router_output") or run_act_router(
                case_context_input=stage0_res,
                legal_query_input=stage1_res,
                stage4_input=stage4_res,
                bsa_input=stage3b_res,
                bnss_input=stage3c_res,
            )
            print("\n=== ACT ROUTER SUB-PIPELINE RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        else:
            # Full Stages 0-4 pipeline — each stage printed immediately as it completes
            stage0_res = run_stage0(
                text=args.text, file_path=args.file,
                user_query=args.query, court_type=args.court,
                legal_regime_override=args.regime,
            )
            print("\n=== STAGE 0 CASE CONTEXT RESULT ===", flush=True)
            print(json.dumps(stage0_res, indent=2, ensure_ascii=False), flush=True)

            stage1_res = run_stage1(stage0_res)
            print("\n=== STAGE 1 LEGAL QUERY RESULT ===", flush=True)
            print(json.dumps(stage1_res, indent=2, ensure_ascii=False), flush=True)

            stage2_res = run_stage2(stage1_res)
            print("\n=== STAGE 2 BATCHED SUB-QUERY MAPPING RESULT ===", flush=True)
            print(json.dumps(stage2_res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(2, stage2_res)

            stage3_res = run_stage3(stage1_res, stage2_res)
            print("\n=== STAGE 3 CHAPTER IDENTIFICATION RESULT ===", flush=True)
            print(json.dumps(stage3_res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(3, stage3_res)

            stage3b_res = run_stage3b(stage1_res, stage3_res)
            print("\n=== STAGE 3b BSA RETRIEVAL RESULT ===", flush=True)
            print(json.dumps(stage3b_res, indent=2, ensure_ascii=False), flush=True)

            stage3c_res = run_stage3c(stage1_res, stage0_res)
            print("\n=== STAGE 3c BNSS RETRIEVAL RESULT ===", flush=True)
            print(json.dumps(stage3c_res, indent=2, ensure_ascii=False), flush=True)

            stage4_res = run_stage4(stage1_res, stage3_res, bsa_input=stage3b_res, bnss_input=stage3c_res)
            print("\n=== STAGE 4 STATUTORY VERIFICATION RESULT ===", flush=True)
            print(json.dumps(stage4_res, indent=2, ensure_ascii=False), flush=True)

            res = {
                "status": "VERIFIED",
                "stage0_result": stage0_res,
                "stage0_case_context": stage0_res,
                "stage1_result": stage1_res,
                "stage1_legal_query": stage1_res,
                "stage2_result": stage2_res,
                "stage2_subquery_mapping": stage2_res,
                "stage3_result": stage3_res,
                "stage3_chapter_identification": stage3_res,
                "stage3b_result": stage3b_res,
                "stage3b_bsa_retrieval": stage3b_res,
                "stage3c_result": stage3c_res,
                "stage3c_bnss_retrieval": stage3c_res,
                "stage4_result": stage4_res,
                "stage4_statutory_verification": stage4_res,
                "stage4b_act_router": stage4_res.get("act_router_output", {}),
            }
            
            # Stage 5: Precedent Retrieval (if enabled)
            if args.precedents:
                try:
                    from precedent_retrieval.pipeline import PrecedentPipeline
                    
                    print("\n" + "="*80)
                    print("STAGE 5: PRECEDENT RETRIEVAL")
                    print("="*80)
                    
                    # Extract legal issues from Stage 1
                    legal_issues = []
                    if stage1_res and isinstance(stage1_res, dict):
                        sub_queries = stage1_res.get('sub_queries', [])
                        legal_issues = _precedent_legal_issues(stage1_res, stage0_res)
                    
                    print(f"\n[Stage 5] Extracted {len(legal_issues)} legal issues from Stage 1")
                    print(f"[Stage 5] Running precedent retrieval with max {args.max_precedents} candidates...")
                    
                    # Run precedent retrieval
                    prec_pipeline = PrecedentPipeline(max_candidates=args.max_precedents)
                    prec_result = prec_pipeline.run(
                        case_context=stage0_res,
                        statutory_object=stage4_res,
                        legal_issues=legal_issues
                    )
                    
                    # Add to result
                    prec_result_dict = prec_result.model_dump() if hasattr(prec_result, 'model_dump') else prec_result
                    res["stage5_result"] = prec_result_dict
                    res["stage5_precedent_retrieval"] = prec_result_dict
                    
                    print("\n=== STAGE 5 PRECEDENT RETRIEVAL RESULT ===", flush=True)
                    print(json.dumps(prec_result_dict, indent=2, ensure_ascii=False, default=str), flush=True)
                    
                    prec_obj = prec_result.verified_precedent_object
                    print(f"\n[Stage 5] ✅ Precedent Retrieval Complete")
                    print(f"  - Judgments Scanned: {prec_obj.total_judgments_scanned}")
                    print(f"  - Candidates Matched: {prec_obj.candidates_after_statutory_match}")
                    print(f"  - Prosecution Precedents: {len(prec_obj.prosecution_precedents)}")
                    print(f"  - Defense Precedents: {len(prec_obj.defense_precedents)}")
                    
                except Exception as e:
                    print(f"\n[Stage 5] ⚠️  Precedent Retrieval Failed: {e}", file=sys.stderr)
                    import traceback
                    traceback.print_exc()
                    res["stage5_result"] = {
                        "status": "FAILED",
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                    res["stage5_precedent_retrieval"] = res["stage5_result"]
            
            print("\n=== LEXIGRAPH STAGES 0-5 PIPELINE CHAIN COMPLETE ===", flush=True)
    except Exception as e:
        print(f"Error running pipeline: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
