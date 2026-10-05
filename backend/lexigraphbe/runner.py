"""
CLI and Python runner for Stage 0 (Intake), Stage 1 (Query Understanding), Stage 2 (Batched Sub-Query Mapping), Stage 3 (Chapter Identification), Stage 4 (Statutory Verification), Stage 5 (Bail Reasoning), and Stage 6 (Precedent Retrieval).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

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
from .stage5_pipeline import Stage5Pipeline
from .stage6_pipeline import Stage6Pipeline
from .bsa_retrieval_agent import BSARetrievalAgent
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
            print(f"    [OK] Section {sec:>6}  [{types}]  (from {sqs})", flush=True)
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
            print(f"  STAGE 4 -> STAGE 5 PIPELINE HANDOFF", flush=True)
            print(sep, flush=True)
            print(f"  Sections confirmed for bail analysis: {accepted}", flush=True)
            print(sep, flush=True)
            return
        received = pt.get("stage3_input_sections", [])
        accepted = pt.get("stage4_accepted_sections", [])
        rejected = pt.get("stage4_rejected_sections", [])
        print(f"\n{sep}", flush=True)
        print(f"  STAGE 4 -> STAGE 5 PIPELINE HANDOFF", flush=True)
        print(sep, flush=True)
        print(f"  Received from Stage 3 ({len(received)}): {received}", flush=True)
        print(f"  Confirmed by Stage 4  ({len(accepted)}): {accepted}", flush=True)
        if rejected:
            print(f"  Dropped by Stage 4    ({len(rejected)}):", flush=True)
            for r in rejected:
                print(f"    [!!] Section {r.get('section_number'):>6}  -- {r.get('reason', '')}", flush=True)
        else:
            print(f"  Dropped by Stage 4    (0): None", flush=True)
        print(f"  Passing to Stage 5: {pt.get('passing_to_stage5', accepted)}", flush=True)
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
                if len(doc_text) > 35000:
                    doc_text = "\n".join(pages_text[:12])
            except Exception:
                import pypdf
                reader = pypdf.PdfReader(str(p))
                pages_text = [page.extract_text() or "" for page in reader.pages]
                doc_text = "\n".join(pages_text[:12]) if len(pages_text) > 12 else "\n".join(pages_text)
        else:
            doc_text = p.read_text(encoding="utf-8")
    elif text:
        doc_text = text
    else:
        doc_text = "Sample FIR text: FIR No. 123/2025 registered at Nashik Road Police Station, Maharashtra."

    inp = IntakeInput(
        documents_text=doc_text,
        user_query=user_query or "",
        court_type=court_type,
        legal_regime_override=legal_regime_override,
    )

    pipeline = Stage0Pipeline()
    result = pipeline.run(inp)
    cco = result.export_case_context_object()
    return cco.model_dump()


def run_stage1(case_context_input: dict) -> dict:
    """
    Executes Stage 1 pipeline on CaseContextObject dict and returns LegalQueryObject dict.
    """
    pipeline = Stage1Pipeline()
    res = pipeline.run(case_context_input)
    if res.verified_query_object:
        return res.verified_query_object.model_dump()
    return {"status": res.status, "feedback": res.feedback}


def run_stage2(legal_query_input: dict) -> dict:
    """
    Executes Stage 2 pipeline on LegalQueryObject dict and returns Stage2BatchedMappingResponse dict.
    """
    pipeline = Stage2Pipeline()
    res = pipeline.run(legal_query_input)
    if res.batched_mapping_response:
        return res.batched_mapping_response.model_dump()
    return {"status": res.status, "feedback": res.feedback}


def run_stage3(legal_query_input: dict, stage2_input: Optional[dict] = None) -> dict:
    """
    Executes Stage 3 pipeline on LegalQueryObject and Stage 2 verified mapping dicts.
    """
    pipeline = Stage3Pipeline()
    res = pipeline.run(legal_query_input, stage2_mapping=stage2_input)
    if res.verified_chapter_object:
        return res.verified_chapter_object.model_dump()
    return {"status": res.status, "feedback": res.feedback}


def run_stage3b(
    legal_query_input: dict,
    stage3_input: Optional[dict] = None,
) -> dict:
    """
    Executes Stage 3b: BSA Evidence Law Section Retrieval.

    Runs deterministically (0 LLM calls) and returns a BSARetrievalObject dict
    containing relevant Bharatiya Sakshya Adhiniyam sections with IEA equivalents
    and IPC → BNS equivalents for offences identified in Stage 3.

    Args:
        legal_query_input: LegalQueryObject dict from Stage 1.
        stage3_input: Optional ChapterIdentificationObject dict from Stage 3
                      (used to resolve IPC → BNS equivalents for identified offences).

    Returns:
        BSARetrievalObject as dict.
    """
    agent = BSARetrievalAgent()
    verified_offences = None
    if stage3_input:
        verified_offences = stage3_input.get("verified_offences", [])

    print("\n" + "=" * 60, flush=True)
    print("  STAGE 3b: BSA EVIDENCE LAW SECTION RETRIEVAL & VERIFICATION", flush=True)
    print("=" * 60, flush=True)

    result = agent.run(
        legal_query=legal_query_input,
        verified_offences=verified_offences,
    )

    result_dict = result.model_dump()
    sections = result_dict.get("relevant_sections", [])
    rejected = result_dict.get("rejected_sections", [])
    ipc_bns_map = result_dict.get("ipc_to_bns_map", {})

    print(f"\n  [VERIFIED / ACCEPTED BSA SECTIONS ({len(sections)})]:", flush=True)
    for sec in sections:
        iea = sec.get("replaces_IEA") or "—"
        cat = sec.get("relevance_category") or "DOCUMENTS"
        v_reason = sec.get("verification_reason") or sec.get("relevance_reason") or ""
        print(
            f"    ✓ [BSA {sec['section_number']:>3}] "
            f"{sec['heading'][:50]:<50} "
            f"| IEA: {iea:<10} "
            f"| [{cat}]",
            flush=True,
        )
        if v_reason:
            print(f"      Grounding: {v_reason}", flush=True)

    if rejected:
        print(f"\n  [AUDITED & REJECTED CANDIDATES ({len(rejected)})]:", flush=True)
        for sec in rejected[:5]:
            rej_reason = sec.get("verification_reason") or "Tangential / generic noise"
            print(f"    ✗ [BSA {sec['section_number']:>3}] {sec['heading'][:45]:<45} -> {rej_reason}", flush=True)

    if ipc_bns_map:
        print(f"\n  [IPC → BNS EQUIVALENTS (via Neo4j REPLACED_BY) ({len(ipc_bns_map)})]:", flush=True)
        for ipc_sec, bns_sec in sorted(ipc_bns_map.items()):
            print(f"    IPC {ipc_sec:>3} → BNS {bns_sec}", flush=True)

    for note in result_dict.get("retrieval_notes", []):
        print(f"  NOTE: {note}", flush=True)

    print("=" * 60, flush=True)
    return result_dict


def run_stage4(
    legal_query_input: dict,
    chapter_input: dict,
    bsa_input: Optional[dict] = None,
) -> dict:
    """
    Executes Stage 4 pipeline on LegalQueryObject and ChapterIdentificationObject dicts.
    At the conclusion of Stage 4, displays both:
      1. Verified IPC sections mapped to BNS equivalents (via Neo4j REPLACED_BY)
      2. Verified BSA evidence sections mapped to IEA equivalents (via Neo4j REPLACES)
    """
    pipeline = Stage4Pipeline()
    res = pipeline.run(legal_query_input, chapter_input)
    
    stage4_dict = (
        res.verified_statutory_object.model_dump()
        if res.verified_statutory_object
        else {"status": res.status, "feedback": res.feedback}
    )

    # If BSA input was not passed from Stage 3b, run it now to guarantee both mappings are present
    if not bsa_input:
        try:
            bsa_input = run_stage3b(legal_query_input, chapter_input)
        except Exception:
            bsa_input = {}

    # Extract IPC -> BNS mappings
    repo = StatuteRepository.get_instance()
    ipc_bns_mappings = []
    verified_offences = stage4_dict.get("verified_offences", [])
    if not verified_offences and chapter_input:
        verified_offences = chapter_input.get("verified_offences", [])

    for off in verified_offences:
        raw_sec = str(off.get("ipc_equivalent") or off.get("section_number") or "").strip()
        clean_sec = raw_sec.upper().replace("IPC_", "").replace("SECTION ", "").strip()
        title = off.get("section_title") or off.get("offence_title") or ""
        bns_eq = repo.get_ipc_bns_equivalent(clean_sec) or off.get("bns_equivalent") or "N/A"
        ipc_bns_mappings.append({
            "ipc_section": clean_sec,
            "title": title,
            "bns_equivalent": bns_eq,
        })

    # Extract BSA -> IEA mappings
    bsa_iea_mappings = []
    if bsa_input and "relevant_sections" in bsa_input:
        for b_sec in bsa_input["relevant_sections"]:
            bsa_num = str(b_sec.get("section_number", "")).strip()
            heading = b_sec.get("heading", "")
            cat = b_sec.get("relevance_category", "DOCUMENTS")
            iea_eq = b_sec.get("replaces_IEA") or "None"
            bsa_iea_mappings.append({
                "bsa_section": bsa_num,
                "heading": heading,
                "category": cat,
                "iea_equivalent": iea_eq,
            })

    # Terminal summary of both mappings at the end of Stage 4
    print("\n" + "=" * 80, flush=True)
    print("  STAGE 4 COMPREHENSIVE STATUTE EQUIVALENCE SUMMARY", flush=True)
    print("=" * 80, flush=True)
    print("  [1] VERIFIED SUBSTANTIVE OFFENCES (IPC → BNS via Neo4j REPLACED_BY):", flush=True)
    if ipc_bns_mappings:
        for m in ipc_bns_mappings:
            title_snippet = f"({m['title'][:40]})" if m['title'] else ""
            print(f"      • IPC {m['ipc_section']:<5} {title_snippet:<42} ──► BNS {m['bns_equivalent']}", flush=True)
    else:
        print("      • (No substantive offences to map)", flush=True)

    print("\n  [2] VERIFIED EVIDENCE LAW PROVISIONS (BSA → IEA via Neo4j REPLACES):", flush=True)
    if bsa_iea_mappings:
        for b in bsa_iea_mappings:
            head_snippet = f"({b['heading'][:40]})" if b['heading'] else ""
            print(f"      • BSA {b['bsa_section']:<5} {head_snippet:<42} ──► IEA {b['iea_equivalent']:<10} [{b['category']}]", flush=True)
    else:
        print("      • (No evidentiary provisions mapped)", flush=True)
    print("=" * 80 + "\n", flush=True)

    stage4_dict["ipc_to_bns_equivalents"] = ipc_bns_mappings
    stage4_dict["bsa_to_iea_equivalents"] = bsa_iea_mappings
    return stage4_dict



def run_stage5(case_context_input: dict, legal_query_input: dict, statutory_input: dict) -> dict:
    """
    Executes Stage 5 pipeline on CaseContextObject, LegalQueryObject, and StatutoryVerificationObject dicts.
    """
    pipeline = Stage5Pipeline()
    res = pipeline.run(case_context_input, legal_query_input, statutory_input)
    if res.verified_bail_object:
        return res.verified_bail_object.model_dump()
    return {"status": res.status, "feedback": res.feedback}


def run_stage6(case_context_input: dict, legal_query_input: dict, statutory_input: dict, bail_input: dict) -> dict:
    """
    Executes Stage 6 pipeline on CaseContextObject, LegalQueryObject, StatutoryVerificationObject, and BailReasoningObject dicts.
    """
    pipeline = Stage6Pipeline()
    res = pipeline.run(case_context_input, legal_query_input, statutory_input, bail_input)
    if res.verified_precedent_object:
        return res.verified_precedent_object.model_dump()
    return {"status": res.status, "feedback": res.feedback}


def run_full_pipeline(
    text: Optional[str] = None,
    file_path: Optional[str] = None,
    user_query: Optional[str] = None,
    court_type: Optional[str] = None,
    legal_regime_override: Optional[str] = None,
) -> dict:
    """
    Chains Stage 0 -> Stage 1 -> Stage 2 -> Stage 3 -> Stage 3b -> Stage 4 -> Stage 5 -> Stage 6
    and returns combined outputs.
    Stage 3b is BSA Evidence Law Section Retrieval (parallel to Stage 3, 0 LLM calls).
    """
    stage0_out = run_stage0(
        text=text,
        file_path=file_path,
        user_query=user_query,
        court_type=court_type,
        legal_regime_override=legal_regime_override,
    )

    stage1_out = run_stage1(stage0_out)
    stage2_out = run_stage2(stage1_out)
    stage3_out = run_stage3(stage1_out, stage2_out)
    stage3b_out = run_stage3b(stage1_out, stage3_out)  # BSA retrieval & verification
    stage4_out = run_stage4(stage1_out, stage3_out, bsa_input=stage3b_out)
    stage5_out = run_stage5(stage0_out, stage1_out, stage4_out)
    stage6_out = run_stage6(stage0_out, stage1_out, stage4_out, stage5_out)


    return {
        "stage0_case_context": stage0_out,
        "stage1_legal_query": stage1_out,
        "stage2_subquery_mapping": stage2_out,
        "stage3_chapter_identification": stage3_out,
        "stage3b_bsa_retrieval": stage3b_out,
        "stage4_statutory_verification": stage4_out,
        "stage5_bail_reasoning": stage5_out,
        "stage6_precedent_retrieval": stage6_out,
    }


def main():
    parser = argparse.ArgumentParser(description="Run Stage 0, Stage 1, Stage 2, Stage 3, Stage 3b (BSA), Stage 4, Stage 5, Stage 6 & Full LexiGraph Backend Pipelines")
    parser.add_argument("--file", "-f", type=str, help="Path to input raw document text file")
    parser.add_argument("--text", "-t", type=str, help="Raw document text input string")
    parser.add_argument("--query", "-q", type=str, help="User instructions / query")
    parser.add_argument("--court", type=str, help="Court type (Sessions Court / High Court)")
    parser.add_argument("--regime", type=str, default="IPC + CrPC", help="Legal regime (default: IPC + CrPC)")
    parser.add_argument(
        "--stage",
        type=str,
        choices=["0", "1", "2", "3", "3b", "4", "5", "6", "7"],
        default="7",
        help="Target stage to run (0=Intake, 1=Query Understanding, 2=SubQuery Mapping, 3=Chapter Identification, 3b=BSA Retrieval, 4=Statutory Verification, 5=Bail Reasoning, 6=Precedent Retrieval, 7=Full Chain)",
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
        elif args.stage == "4":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            res = run_stage4(stage1_res, stage3_res)
            print("\n=== STAGE 4 STATUTORY VERIFICATION RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(4, res)
        elif args.stage == "5":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            stage4_res = run_stage4(stage1_res, stage3_res)
            res = run_stage5(stage0_res, stage1_res, stage4_res)
            print("\n=== STAGE 5 BAIL REASONING RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == "6":
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            stage4_res = run_stage4(stage1_res, stage3_res)
            stage5_res = run_stage5(stage0_res, stage1_res, stage4_res)
            res = run_stage6(stage0_res, stage1_res, stage4_res, stage5_res)
            print("\n=== STAGE 6 PRECEDENT RETRIEVAL RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        else:
            res = run_full_pipeline(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            print("\n=== FULL END-TO-END STAGE 0+1+2+3+3b+4+5+6 PIPELINE CHAIN RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
    except Exception as e:
        print(f"Error running pipeline: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
