"""
formatting.py
=============
Unified argument structuring, citation extraction, and evidence referencing
for MootCourt orchestrator agents (Prosecution and Defense).
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


def extract_citations_with_act(text: str) -> List[str]:
    """
    Extract citations with Act names (e.g. 'IPC 324', 'CrPC 438', 'BNS 118', 'BNSS 482', 'IEA 27').
    Defaults to 'IPC <sec>' for substantive criminal offense numbers if Act name is not prefixed.
    """
    found = []

    # 1. Pattern with explicit Act name prefix (e.g. IPC 324, CrPC 438, BNS 118(1))
    matches_explicit = re.findall(
        r"\b(IPC|BNS|CrPC|BNSS|IEA|BSA|POCSO|DP Act)\s*(?:Section|Sec\.?)?\s*(\d+[a-z]?(?:\(\d+\))?)\b",
        text,
        re.IGNORECASE,
    )
    for act, num in matches_explicit:
        act_norm = act.upper().replace("SECTION", "").strip()
        if "CRPC" in act_norm:
            act_norm = "CrPC"
        elif "BNSS" in act_norm:
            act_norm = "BNSS"
        elif "IPC" in act_norm:
            act_norm = "IPC"
        elif "BNS" in act_norm:
            act_norm = "BNS"
        elif "IEA" in act_norm:
            act_norm = "IEA"
        elif "BSA" in act_norm:
            act_norm = "BSA"
        found.append(f"{act_norm} {num.strip()}")

    # 2. Pattern with 'Section <num> IPC/CrPC' suffix
    matches_rev = re.findall(
        r"\b(?:Section|Sec\.?)\s*(\d+[a-z]?(?:\(\d+\))?)\s+(?:of\s+(?:the\s+)?)?(IPC|BNS|CrPC|BNSS|IEA|BSA)\b",
        text,
        re.IGNORECASE,
    )
    for num, act in matches_rev:
        act_norm = act.upper().strip()
        if "CRPC" in act_norm:
            act_norm = "CrPC"
        elif "BNSS" in act_norm:
            act_norm = "BNSS"
        found.append(f"{act_norm} {num.strip()}")

    # 3. Standalone sections with contextual Act resolution
    matches_standalone = re.findall(r"\b(?:Section|Sec\.?)\s*(\d+[a-z]?)\b", text, re.IGNORECASE)
    for num in matches_standalone:
        num_clean = num.strip()
        if not any(f" {num_clean}" in c for c in found):
            if num_clean in {"438", "482", "437", "439", "167", "187", "161", "164", "313"}:
                found.append(f"CrPC {num_clean}")
            elif num_clean in {"27", "23"}:
                found.append(f"IEA {num_clean}")
            else:
                found.append(f"IPC {num_clean}")

    # Deduplicate while preserving order
    dedup = []
    seen = set()
    for c in found:
        key = c.upper()
        if key not in seen:
            seen.add(key)
            dedup.append(c)
    return dedup


def extract_evidence_references(text: str) -> List[str]:
    """Pull fact references like 'fact_1', 'fact_3' from text."""
    matches = re.findall(r"\b(fact_\d+)\b", text.lower())
    seen = set()
    dedup = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            dedup.append(m)
    return dedup


def format_argument_markdown(
    theory: str,
    arguments: List[str],
    evidence_refs: List[str],
    sections: List[str],
    facts_lookup: Optional[Dict[str, str]] = None,
) -> str:
    """
    Renders the unified argument structure into a clean, professional,
    consistent Markdown format across both Prosecution and Defense.
    Schema: {theory, arguments[], evidence_refs[], sections[]}
    """
    lines = []
    lines.append("### Legal Theory")
    lines.append((theory or "Legal theory as submitted.").strip())
    lines.append("")
    lines.append("### Submissions")
    if arguments:
        for i, arg in enumerate(arguments, 1):
            clean_arg = arg.strip()
            # If line already starts with a number like "1.", trim it
            clean_arg = re.sub(r"^\d+\.\s*", "", clean_arg)
            lines.append(f"{i}. {clean_arg}")
    else:
        lines.append("1. Submissions on record before the court.")
    lines.append("")
    lines.append("### Evidence References")
    if evidence_refs:
        for ref in evidence_refs:
            ref_clean = ref.strip().lower()
            detail = facts_lookup.get(ref_clean, "") if facts_lookup else ""
            if detail:
                lines.append(f"- **[{ref_clean}]**: {detail}")
            else:
                lines.append(f"- **[{ref_clean}]**")
    else:
        lines.append("- *(No specific evidence references cited)*")
    lines.append("")
    lines.append("### Statutory Provisions")
    if sections:
        for sec in sections:
            lines.append(f"- {sec.strip()}")
    else:
        lines.append("- *(No statutory provisions cited)*")

    return "\n".join(lines)


def parse_argument_structure(text: str, fallback_theory: str = "") -> Dict[str, Any]:
    """
    Parses an argument text (whether raw JSON or Markdown with headings)
    into the standard dict schema:
    {
      "theory": str,
      "arguments": List[str],
      "evidence_refs": List[str],
      "sections": List[str]
    }
    """
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            theory = str(data.get("theory", "")).strip()
            args = data.get("arguments", [])
            arguments = [str(a) for a in args] if isinstance(args, list) else [str(args)]
            ev = data.get("evidence_refs", [])
            evidence_refs = [str(e) for e in ev] if isinstance(ev, list) else []
            sec = data.get("sections", [])
            sections = [str(s) for s in sec] if isinstance(sec, list) else []
            return {
                "theory": theory or fallback_theory,
                "arguments": arguments,
                "evidence_refs": evidence_refs,
                "sections": sections,
            }
    except Exception:
        pass

    # Markdown parsing
    theory = ""
    arguments = []
    evidence_refs = extract_evidence_references(text)
    sections = extract_citations_with_act(text)

    # Check for ### Legal Theory
    m_theory = re.search(r"###\s*(?:Legal\s+)?Theory\s*\n+([\s\S]*?)(?=\n###|\Z)", text, re.IGNORECASE)
    if m_theory:
        theory = m_theory.group(1).strip()

    # Check for ### Submissions or arguments
    m_subs = re.search(r"###\s*(?:Submissions|Arguments)\s*\n+([\s\S]*?)(?=\n###|\Z)", text, re.IGNORECASE)
    if m_subs:
        raw_subs = m_subs.group(1).strip()
        lines = [re.sub(r"^\d+\.\s*", "", l).strip() for l in raw_subs.split("\n") if l.strip()]
        arguments = [l for l in lines if l]

    if not theory:
        # Fallback: take first paragraph
        paras = [p.strip() for p in text.split("\n\n") if p.strip() and not p.startswith("#")]
        theory = paras[0] if paras else (fallback_theory or "Submissions on record.")
        if not arguments and len(paras) > 1:
            arguments = paras[1:]

    if not arguments:
        arguments = [text.strip()]

    return {
        "theory": theory,
        "arguments": arguments,
        "evidence_refs": evidence_refs,
        "sections": sections,
    }


def link_facts_to_text(text: str, facts: List[Any]) -> List[str]:
    """
    Extracts all evidence refs from text (e.g. 'fact_1', 'fact_2').
    If none or few were explicitly cited in text, matches facts against text
    by checking distinctive keywords in each fact's text.
    Returns deduplicated list of fact IDs (e.g. ['fact_1', 'fact_3']).
    """
    explicit = extract_evidence_references(text)
    seen = set(explicit)
    result = list(explicit)

    text_lower = text.lower()
    for i, f in enumerate(facts):
        fid = str(getattr(f, "id", f.get("id", f"fact_{i+1}") if isinstance(f, dict) else f"fact_{i+1}")).lower()
        if not fid or fid in seen:
            continue
        val = str(getattr(f, "text", f.get("text", f.get("value", "")) if isinstance(f, dict) else str(f))).strip().lower()
        words = [
            w for w in re.findall(r"\b[a-z]{4,}\b", val)
            if w not in {"with", "that", "this", "from", "were", "been", "have", "allegedly", "outside", "under"}
        ]
        if words:
            matches = sum(1 for w in words if w in text_lower)
            if matches >= 1:
                result.append(fid)
                seen.add(fid)

    return result


def structure_prosecution_turn(
    result_or_text: Any,
    case_facts: List[Any],
    lexigraph_output: Dict[str, Any],
) -> tuple[str, List[str], List[str], Dict[str, Any]]:
    """
    Normalizes a prosecution turn (whether a ProsecutorTurnResult object, JSON string,
    or prose string) into the standard schema:
    Returns (formatted_markdown, citations_with_act, evidence_refs, structured_dict).
    """
    facts_lookup = {
        str(getattr(f, "id", f.get("id", f"fact_{i+1}") if isinstance(f, dict) else f"fact_{i+1}")).lower():
            str(getattr(f, "text", f.get("text", f.get("value", "")) if isinstance(f, dict) else str(f)))
        for i, f in enumerate(case_facts)
    }

    if hasattr(result_or_text, "spoken_argument"):
        raw_spoken = result_or_text.spoken_argument or ""
        raw_theory = getattr(result_or_text, "theory_of_case", "") or ""
        raw_statutory = getattr(result_or_text, "statutory_basis", "") or ""
        raw_facts = getattr(result_or_text, "application_to_facts", "") or ""
        combined_text = f"{raw_spoken}\n{raw_statutory}\n{raw_facts}"
    else:
        combined_text = str(result_or_text)
        raw_theory = ""
        raw_spoken = combined_text

    # Parse structured components
    parsed = parse_argument_structure(combined_text, fallback_theory=raw_theory)
    theory = parsed.get("theory") or raw_theory or "Prosecution opposes relief based on established ingredients of offence."
    
    # Sections with Act prefix
    sections = parsed.get("sections", [])
    if not sections:
        sections = extract_citations_with_act(combined_text)
    if not sections and lexigraph_output:
        for s in lexigraph_output.get("ipc_sections", []):
            if isinstance(s, dict) and s.get("section"):
                sections.append(f"IPC {s['section']}")
    sections = list(dict.fromkeys(sections))

    # Evidence refs
    evidence_refs = link_facts_to_text(combined_text, case_facts)

    # Submissions / arguments
    arguments = parsed.get("arguments", [])
    # Clean arguments: remove prose openings if they are just formalities
    clean_args = []
    for a in arguments:
        a_clean = a.strip()
        # Clean salutations like "May it please the Court, ..."
        a_clean = re.sub(r"^May\s+it\s+please\s+the\s+Court[,\s]*", "", a_clean, flags=re.IGNORECASE).strip()
        if a_clean:
            clean_args.append(a_clean)
    if not clean_args:
        clean_args = [theory]

    structured_dict = {
        "theory": theory,
        "arguments": clean_args,
        "evidence_refs": evidence_refs,
        "sections": sections,
    }

    formatted_md = format_argument_markdown(
        theory=theory,
        arguments=clean_args,
        evidence_refs=evidence_refs,
        sections=sections,
        facts_lookup=facts_lookup,
    )

    return formatted_md, sections, evidence_refs, structured_dict


def export_transcript(state: Dict[str, Any], output_dir: Optional[str] = None) -> tuple[Path, Path]:
    """
    Exports the complete moot court hearing transcript to both Markdown (.md)
    and JSON (.json) formats.
    """
    sid = state.get("session_id", "session")
    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = Path(__file__).resolve().parent.parent.parent / "transcripts"
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / f"transcript_{sid}.json"
    md_file   = out_path / f"transcript_{sid}.md"

    # 1. JSON export (serializable subset)
    serializable_state = {
        "session_id": sid,
        "case_id": state.get("case_id", ""),
        "round_no": state.get("round_no", 1),
        "max_rounds": state.get("max_rounds", 2),
        "case_facts": [
            f.model_dump() if hasattr(f, "model_dump") else (dict(f) if isinstance(f, dict) else str(f))
            for f in state.get("case_facts", [])
        ],
        "evidence_inventory": state.get("evidence_inventory", []),
        "transcript": state.get("transcript", []),
        "judge_scores": state.get("judge_scores", {}),
        "verdict": state.get("verdict", {}),
        "errors": state.get("errors", []),
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(
            serializable_state,
            f,
            indent=2,
            ensure_ascii=False,
            default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o),
        )

    # 2. Markdown export
    verdict = state.get("verdict") or {}
    decision = str(verdict.get("decision", "NO_OPINION")).upper()
    conf_label = str(verdict.get("confidence_label") or verdict.get("confidence") or "medium").upper()
    statutes = verdict.get("statutes") or [l for l in verdict.get("laws_applied", []) if not any(c in l.lower() for c in (" v ", " vs ", "insc"))]
    precedents = verdict.get("precedents") or [l for l in verdict.get("laws_applied", []) if any(c in l.lower() for c in (" v ", " vs ", "insc"))]
    holdings_relied = verdict.get("holdings_relied") or []
    valid_votes = verdict.get("valid_votes")
    total_votes = verdict.get("total_votes")
    agree_count = verdict.get("agree_count")
    tally_info = f" ({valid_votes}/{total_votes} valid, {agree_count}/{valid_votes} agree)" if valid_votes and total_votes else ""

    md_lines = [
        "# Moot Court Simulation Transcript",
        f"**Session ID:** `{sid}`  ",
        f"**Court Order / Decision:** **{decision}** ({conf_label} Confidence{tally_info})  ",
        f"**Statutes Applied:** {', '.join(statutes) if statutes else 'None'}  ",
        f"**Precedents Relied On:** {', '.join(precedents) if precedents else 'None'}  ",
        f"**Holdings Applied:** {', '.join(holdings_relied) if holdings_relied else 'None'}  ",
        "",
        "---",

        "## 1. Case Record & Extracted Facts",
        "",
    ]
    for i, fact in enumerate(state.get("case_facts", [])):
        fid = getattr(fact, "id", fact.get("id", f"fact_{i+1}") if isinstance(fact, dict) else f"fact_{i+1}")
        txt = getattr(fact, "text", fact.get("text", fact.get("value", "")) if isinstance(fact, dict) else str(fact))
        src = getattr(fact, "source", fact.get("source", "record") if isinstance(fact, dict) else "record")
        ftype = getattr(fact, "type", fact.get("type", "allegation") if isinstance(fact, dict) else "allegation")
        md_lines.append(f"- **[{fid}]** `[{ftype}]` {txt} *(Source: {src})*")

    md_lines.extend([
        "",
        "## 2. Evidence Inventory (Record Status)",
        "",
        "| Evidence Item | Record Status | Details |",
        "|---|---|---|",
    ])
    for inv in state.get("evidence_inventory", []):
        md_lines.append(f"| {inv.get('item')} | `{inv.get('status')}` | {inv.get('details', '')} |")

    md_lines.extend([
        "",
        "---",
        "## 3. Courtroom Proceedings",
        "",
    ])

    for turn in state.get("transcript", []):
        spk = str(turn.get("speaker", "")).upper()
        rnd = turn.get("round_no", 1)
        cits = turn.get("citations", [])
        evs = turn.get("evidence_refs", [])
        cits_str = f" · Citations: {', '.join(cits)}" if cits else ""
        evs_str = f" · Evidence: {', '.join(evs)}" if evs else ""

        md_lines.append(f"### [{spk}] (Round {rnd}){cits_str}{evs_str}")
        md_lines.append("")
        md_lines.append(turn.get("content", ""))
        md_lines.append("")

    # Scores
    scores = state.get("judge_scores", {})
    if scores:
        p = scores.get("prosecution", {})
        d = scores.get("defense", {})
        md_lines.extend([
            "---",
            "## 4. Judicial Evaluation & Scores",
            "",
            "| Axis | Prosecution | Defense |",
            "|---|---|---|",
            f"| Legal Validity | {p.get('legal_validity', 0)}/10 | {d.get('legal_validity', 0)}/10 |",
            f"| Evidence Linkage | {p.get('evidence_linkage', 0)}/10 | {d.get('evidence_linkage', 0)}/10 |",
            f"| Logic Coherence | {p.get('logic_coherence', 0)}/10 | {d.get('logic_coherence', 0)}/10 |",
            f"| **Average Score** | **{p.get('average', 0)}/10** | **{d.get('average', 0)}/10** |",
            f"| **Total Score** | **{p.get('total', 0)}/30** | **{d.get('total', 0)}/30** |",
            "",
            f"**Overall Debate Quality:** {scores.get('overall', 0)}/10  ",
            "",
        ])

    # Final verdict
    md_lines.extend([
        "---",
        "## 5. Final Judicial Verdict & Reasoning",
        "",
        f"**Decision:** {decision}  ",
        f"**Confidence:** {conf_label}{tally_info}  ",
        f"**Statutes Applied:** {', '.join(statutes) if statutes else 'None'}  ",
        f"**Precedents Relied On:** {', '.join(precedents) if precedents else 'None'}  ",
        f"**Holdings Applied:** {', '.join(holdings_relied) if holdings_relied else 'None'}  ",
        "",
        "### Judicial Explanation",
        verdict.get("reasoning", "No detailed reasoning provided."),
        "",
    ])

    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return md_file, json_file


def summarize_transcript_history(transcript: List[Any], keep_last: int = 2) -> str:
    """
    Summarizes prior debate transcript turns to conserve prompt tokens across rounds.
    Keeps the last `keep_last` turns verbatim and replaces earlier ones with a concise
    running summary that preserves argument IDs, statutory citations, evidence references,
    and points conceded or contested.
    """
    if not transcript:
        return "(No prior hearing transcript recorded.)"

    if len(transcript) <= keep_last:
        parts = []
        for t in transcript:
            spk = (getattr(t, "speaker", None) or (t.get("speaker") if isinstance(t, dict) else "unknown")).upper()
            rnd = getattr(t, "round_no", None) or (t.get("round_no", 1) if isinstance(t, dict) else 1)
            content = getattr(t, "content", None) or (t.get("content", "") if isinstance(t, dict) else str(t))
            parts.append(f"### [{spk} — Round {rnd}]\n{content.strip()}")
        return "\n\n".join(parts)

    earlier = transcript[:-keep_last]
    recent = transcript[-keep_last:]

    summary_lines = [
        "--- SUMMARY OF EARLIER PROCEEDINGS ---",
        "Key points, argument IDs, citations, and points contested/conceded in earlier turns:",
    ]

    for t in earlier:
        spk = (getattr(t, "speaker", None) or (t.get("speaker") if isinstance(t, dict) else "unknown")).title()
        rnd = getattr(t, "round_no", None) or (t.get("round_no", 1) if isinstance(t, dict) else 1)
        t_no = getattr(t, "turn_no", None) or (t.get("turn_no", "?") if isinstance(t, dict) else "?")
        citations = getattr(t, "citations", None) or (t.get("citations", []) if isinstance(t, dict) else [])
        evidence_refs = getattr(t, "evidence_refs", None) or (t.get("evidence_refs", []) if isinstance(t, dict) else [])
        struct = getattr(t, "structured_argument", None) or (t.get("structured_argument", {}) if isinstance(t, dict) else {})
        content = getattr(t, "content", None) or (t.get("content", "") if isinstance(t, dict) else str(t))

        theory = struct.get("theory") if isinstance(struct, dict) else ""
        if not theory and content:
            first_line = content.strip().split("\n")[0]
            theory = first_line[:120]

        contested = []
        conceded = []
        args_list = struct.get("arguments", []) if isinstance(struct, dict) else []
        for arg in args_list:
            arg_str = str(arg).strip()
            low = arg_str.lower()
            if any(w in low for w in ("concede", "admit", "not dispute", "agree", "accepted")):
                conceded.append(arg_str[:90])
            else:
                contested.append(arg_str[:90])

        cits_str = f" [Citations: {', '.join(citations)}]" if citations else ""
        evs_str = f" [Evidence: {', '.join(evidence_refs)}]" if evidence_refs else ""

        bullet = f"• Turn {t_no} ({spk}, Round {rnd}): Theory: {theory}{cits_str}{evs_str}"
        if contested:
            bullet += f" | Contested: {'; '.join(contested[:2])}"
        if conceded:
            bullet += f" | Conceded: {'; '.join(conceded[:1])}"
        summary_lines.append(bullet)

    summary_lines.append("\n--- RECENT PROCEEDINGS (VERBATIM) ---")
    for t in recent:
        spk = (getattr(t, "speaker", None) or (t.get("speaker") if isinstance(t, dict) else "unknown")).upper()
        rnd = getattr(t, "round_no", None) or (t.get("round_no", 1) if isinstance(t, dict) else 1)
        content = getattr(t, "content", None) or (t.get("content", "") if isinstance(t, dict) else str(t))
        summary_lines.append(f"### [{spk} — Round {rnd}]\n{content.strip()}")

    return "\n\n".join(summary_lines)


