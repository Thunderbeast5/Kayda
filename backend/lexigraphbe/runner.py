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


def run_stage4(legal_query_input: dict, chapter_input: dict) -> dict:
    """
    Executes Stage 4 pipeline on LegalQueryObject and ChapterIdentificationObject dicts.
    """
    pipeline = Stage4Pipeline()
    res = pipeline.run(legal_query_input, chapter_input)
    if res.verified_statutory_object:
        return res.verified_statutory_object.model_dump()
    return {"status": res.status, "feedback": res.feedback}


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
    Chains Stage 0 -> Stage 1 -> Stage 2 -> Stage 3 -> Stage 4 -> Stage 5 -> Stage 6 and returns combined outputs.
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
    stage4_out = run_stage4(stage1_out, stage3_out)
    stage5_out = run_stage5(stage0_out, stage1_out, stage4_out)
    stage6_out = run_stage6(stage0_out, stage1_out, stage4_out, stage5_out)

    return {
        "stage0_case_context": stage0_out,
        "stage1_legal_query": stage1_out,
        "stage2_subquery_mapping": stage2_out,
        "stage3_chapter_identification": stage3_out,
        "stage4_statutory_verification": stage4_out,
        "stage5_bail_reasoning": stage5_out,
        "stage6_precedent_retrieval": stage6_out,
    }


def main():
    parser = argparse.ArgumentParser(description="Run Stage 0, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6 & Full LexiGraph Backend Pipelines")
    parser.add_argument("--file", "-f", type=str, help="Path to input raw document text file")
    parser.add_argument("--text", "-t", type=str, help="Raw document text input string")
    parser.add_argument("--query", "-q", type=str, help="User instructions / query")
    parser.add_argument("--court", type=str, help="Court type (Sessions Court / High Court)")
    parser.add_argument("--regime", type=str, help="Legal regime override (IPC + CrPC)")
    parser.add_argument("--stage", type=int, choices=[0, 1, 2, 3, 4, 5, 6, 7], default=7, help="Target stage to run (0=Intake, 1=Query Understanding, 2=SubQuery Mapping, 3=Chapter Identification, 4=Statutory Verification, 5=Bail Reasoning, 6=Precedent Retrieval, 7=Full Chain)")

    args = parser.parse_args()

    try:
        if args.stage == 0:
            res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            print("\n=== STAGE 0 CASE CONTEXT RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == 1:
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            res = run_stage1(stage0_res)
            print("\n=== STAGE 1 LEGAL QUERY RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == 2:
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            res = run_stage2(stage1_res)
            print("\n=== STAGE 2 BATCHED SUB-QUERY MAPPING RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(2, res)
        elif args.stage == 3:
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            res = run_stage3(stage1_res, stage2_res)
            print("\n=== STAGE 3 CHAPTER IDENTIFICATION RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(3, res)
        elif args.stage == 4:
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            res = run_stage4(stage1_res, stage3_res)
            print("\n=== STAGE 4 STATUTORY VERIFICATION RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
            _print_pipeline_transition(4, res)
        elif args.stage == 5:
            stage0_res = run_stage0(text=args.text, file_path=args.file, user_query=args.query, court_type=args.court, legal_regime_override=args.regime)
            stage1_res = run_stage1(stage0_res)
            stage2_res = run_stage2(stage1_res)
            stage3_res = run_stage3(stage1_res, stage2_res)
            stage4_res = run_stage4(stage1_res, stage3_res)
            res = run_stage5(stage0_res, stage1_res, stage4_res)
            print("\n=== STAGE 5 BAIL REASONING RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
        elif args.stage == 6:
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
            print("\n=== FULL END-TO-END STAGE 0+1+2+3+4+5+6 PIPELINE CHAIN RESULT ===", flush=True)
            print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
    except Exception as e:
        print(f"Error running pipeline: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
