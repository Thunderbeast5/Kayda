"""
Case bank service — loads pre-prepared judgment JSON files from data/cases/
and normalizes them into the shapes the frontend already expects
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
    for path in sorted(glob.glob(os.path.join(CASES_DIR, "*.json"))):
        try:
            data = _load_case_file(path)
        except (json.JSONDecodeError, OSError):
            continue  # skip malformed files rather than crash the list endpoint

        meta = data.get("case_metadata", {})
        laws = meta.get("laws_referred", [])
        issues = data.get("key_legal_issues", [])

        cases.append({
            "id": _case_id_from_path(path),
            "title": f"{meta.get('appellant', 'Unknown')} vs. {meta.get('respondent', 'Unknown')}",
            "court": meta.get("court", ""),
            "citation": meta.get("citation", ""),
            "decided_on": meta.get("decided_on", ""),
            "primary_charge": laws[0] if laws else "",
            "summary": issues[0]["issue"] if issues else "",
            "turn_count": len(data.get("simulation_conversation", [])),
        })
    return cases


def get_case(case_id: str) -> dict | None:
    path = os.path.join(CASES_DIR, f"{case_id}.json")
    if not os.path.exists(path):
        return None
    return _load_case_file(path)


def normalize_case_data(case: dict, case_id: str) -> dict:
    """Matches the `caseData` shape CourtroomSidebar already renders."""
    meta = case.get("case_metadata", {})
    laws = meta.get("laws_referred", [])
    return {
        "fileId": case_id,
        "title": f"{meta.get('appellant', 'Unknown')} vs. {meta.get('respondent', 'Unknown')}",
        "firNo": meta.get("citation", ""),
        "charge": laws[0] if laws else "",
        "evidenceLinked": True,
    }


def _infer_agent_id(speaker: str) -> str:
    """
    Role-heuristic mapping instead of a hardcoded name table, so this works
    across any case file in the bank without per-case configuration —
    judges/counsel are named differently in every judgment.
    """
    s = speaker.lower()
    if "judge" in s or "justice" in s:
        return "judge"
    if "defen" in s:  # defense / defence
        return "defense"
    if "prosecut" in s:
        return "prosecutor"
    if "appellant" in s or "accused" in s:
        return "accused"
    return "witness"  # advocates, IOs, complainants, etc.


_CITATION_RE = re.compile(
    r"\bSection\s+\d+[A-Za-z()]*|\bIPC\s+\d+[A-Za-z()]*|\bS\.\s?\d+[A-Za-z()]*",
    re.IGNORECASE,
)


def _extract_citations(text: str) -> list[str]:
    found = _CITATION_RE.findall(text)
    # de-dupe while preserving order — a dialogue line rarely needs the same
    # section badge shown twice
    seen = set()
    out = []
    for f in found:
        key = f.lower().strip()
        if key not in seen:
            seen.add(key)
            out.append(f.strip())
    return out


def build_events(case_id: str) -> list[dict] | None:
    """Turn stored simulation_conversation into the event shape handleEvent() expects."""
    case = get_case(case_id)
    if case is None:
        return None

    events = []
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