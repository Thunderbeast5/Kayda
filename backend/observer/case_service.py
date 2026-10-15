"""
Case bank service — loads pre-prepared judgment JSON files from data/observer/
and completed simulation transcripts from backend/transcripts/
and normalizes them into the shapes the frontend expects
(caseData for CourtroomSidebar, event objects for handleEvent()).

No LLM calls here on purpose: this is the "replay a real case" path for
observer mode, not the live orchestrator path.
"""

import json
import os
import re
import glob

# Resolves to root MootCourt/data/observer
CASES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "observer")
)
# Resolves to backend/transcripts
TRANSCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "transcripts")
)


def _load_case_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _case_id_from_path(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _turn_delay(text: str) -> float:
    """
    Rough pacing so replay doesn't dump the whole transcript instantly.
    Scales with dialogue length, capped so long speeches don't stall the demo.
    """
    return min(0.5 + len(text) / 200, 2.5)


def list_cases() -> list[dict]:
    """Lightweight metadata for the case picker screen — no dialogue payload."""
    cases = []
    seen_ids = set()

    for path in sorted(glob.glob(os.path.join(CASES_DIR, "*.json"))):
        try:
            data = _load_case_file(path)
            cid = _case_id_from_path(path)
            seen_ids.add(cid)
            meta = data.get("case_metadata", {})
            laws = meta.get("laws_referred", [])
            issues = data.get("key_legal_issues", [])

            cases.append({
                "id": cid,
                "title": f"{meta.get('appellant', 'Unknown')} vs. {meta.get('respondent', 'Unknown')}",
                "court": meta.get("court", ""),
                "citation": meta.get("citation", ""),
                "decided_on": meta.get("decided_on", ""),
                "primary_charge": laws[0] if laws else "",
                "summary": issues[0]["issue"] if issues else "",
                "turn_count": len(data.get("simulation_conversation", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue

    # Also list available transcripts from backend/transcripts/
    for path in sorted(glob.glob(os.path.join(TRANSCRIPTS_DIR, "transcript_*.json"))):
        try:
            filename = os.path.splitext(os.path.basename(path))[0]
            cid = filename.replace("transcript_", "")
            if cid in seen_ids:
                continue
            data = _load_case_file(path)
            turns = data.get("transcript", [])
            if not turns:
                continue
            seen_ids.add(cid)
            facts = data.get("case_facts", [])
            title = "Srikant Upadhyay v. State of Bihar"
            if facts and isinstance(facts[0], dict) and "text" in facts[0]:
                txt = facts[0]["text"]
                if "The case is " in txt:
                    try:
                        title = txt.split("The case is ")[1].split(",")[0]
                    except Exception:
                        pass
            cases.append({
                "id": cid,
                "title": title,
                "court": "Supreme Court of India",
                "citation": f"SESSION-{cid.upper()}",
                "decided_on": "2024",
                "primary_charge": "Sections 341, 323, 354, 354B IPC",
                "summary": "Anticipatory bail vs proclamation proceedings under Section 82 CrPC",
                "turn_count": len(turns) + (1 if "verdict" in data else 0),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return cases


def get_case(case_id: str) -> dict | None:
    # 1. Check data/observer/{case_id}.json
    path = os.path.join(CASES_DIR, f"{case_id}.json")
    if os.path.exists(path):
        return _load_case_file(path)

    # 2. Check backend/transcripts/transcript_{case_id}.json
    t_path = os.path.join(TRANSCRIPTS_DIR, f"transcript_{case_id}.json")
    if os.path.exists(t_path):
        return _load_case_file(t_path)

    # 3. Direct filename match
    t_path_direct = os.path.join(TRANSCRIPTS_DIR, f"{case_id}.json")
    if os.path.exists(t_path_direct):
        return _load_case_file(t_path_direct)

    return None


def normalize_case_data(case: dict, case_id: str) -> dict:
    """Matches the `caseData` shape CourtroomSidebar already renders."""
    if "case_metadata" in case:
        meta = case.get("case_metadata", {})
        laws = meta.get("laws_referred", [])
        return {
            "fileId": case_id,
            "title": f"{meta.get('appellant', 'Unknown')} vs. {meta.get('respondent', 'Unknown')}",
            "firNo": meta.get("citation", ""),
            "charge": laws[0] if laws else "",
            "evidenceLinked": True,
        }

    # Handling for orchestrator transcript files (e.g. transcript_8efffec1.json)
    facts = case.get("case_facts", [])
    title = "Srikant Upadhyay v. State of Bihar"
    charge = "Sections 341, 323, 354, 354B, 379, 504, 506 IPC & Daain Act"
    fir_no = "FIR-79/2020"

    if facts and isinstance(facts[0], dict) and "text" in facts[0]:
        first_fact = facts[0]["text"]
        if "The case is " in first_fact:
            try:
                title = first_fact.split("The case is ")[1].split(",")[0]
            except Exception:
                pass

    return {
        "fileId": case_id,
        "title": title,
        "firNo": fir_no,
        "charge": charge,
        "evidenceLinked": True,
    }


def _infer_agent_id(speaker: str) -> str:
    """
    Role-heuristic mapping instead of a hardcoded name table, so this works
    across any case file in the bank without per-case configuration —
    judges/counsel are named differently in every judgment.
    """
    s = str(speaker).lower()
    if "judge" in s or "justice" in s or "bench" in s:
        return "judge"
    if "defen" in s:  # defense / defence
        return "defense"
    if "prosecut" in s or "state" in s:
        return "prosecutor"
    if "appellant" in s or "accused" in s:
        return "accused"
    return "witness"  # advocates, IOs, complainants, etc.


_CITATION_RE = re.compile(
    r"\bSection\s+\d+[A-Za-z()]*|\bIPC\s+\d+[A-Za-z()]*|\bCrPC\s+\d+[A-Za-z()]*|\bS\.\s?\d+[A-Za-z()]*",
    re.IGNORECASE,
)


def _extract_citations(text: str) -> list[str]:
    found = _CITATION_RE.findall(text)
    seen = set()
    out = []
    for f in found:
        key = f.lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(f.strip())
    return out


def build_events(case_id: str) -> list[dict] | None:
    """Turn stored simulation_conversation or transcript into the event shape handleEvent() expects."""
    case = get_case(case_id)
    if case is None:
        return None

    events = []

    # Format 1: Pre-prepared case with simulation_conversation
    if "simulation_conversation" in case:
        for turn in case.get("simulation_conversation", []):
            speaker = turn.get("speaker", "Unknown")
            text = turn.get("dialogue", "")
            events.append({
                "agent_id": _infer_agent_id(speaker),
                "display_name": speaker,
                "full_text": text,
                "verified_citations": _extract_citations(text),
            })
        return events

    # Format 2: Orchestrator transcript (e.g. transcript_8efffec1.json)
    if "transcript" in case:
        for turn in case.get("transcript", []):
            speaker = turn.get("speaker", "Unknown")
            text = turn.get("content", "")
            citations = turn.get("citations") or _extract_citations(text)
            events.append({
                "agent_id": _infer_agent_id(speaker),
                "display_name": str(speaker).replace("_", " ").title(),
                "full_text": text,
                "verified_citations": citations if isinstance(citations, list) else [],
            })

        if "verdict" in case and case["verdict"]:
            v = case["verdict"]
            decision = v.get("decision", "Court Adjourned")
            findings = v.get("key_findings", [])
            finding_text = "\n".join(f"• {f.get('finding')}" for f in findings if isinstance(f, dict) and f.get('finding'))
            full_text = f"FINAL VERDICT: {decision}\n\nKey Findings:\n{finding_text}" if finding_text else f"FINAL VERDICT: {decision}"
            events.append({
                "agent_id": "judge",
                "display_name": "Chief Justice / Presiding Bench",
                "full_text": full_text,
                "verified_citations": ["CrPC 438"],
            })
        return events

    return events