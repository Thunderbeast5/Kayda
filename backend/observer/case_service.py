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


def _load_transcript_case(path: str, case_id: str) -> dict:
    raw = _load_case_file(path)
    first_fact = ""
    case_facts = raw.get("case_facts", [])
    if case_facts and isinstance(case_facts, list) and len(case_facts) > 0:
        first_fact = case_facts[0].get("text", "") if isinstance(case_facts[0], dict) else str(case_facts[0])

    is_srikant = "Srikant" in first_fact or case_id.startswith("8eff")
    appellant = "Srikant Upadhyay and Others" if is_srikant else "Appellant"
    respondent = "State of Bihar and Another" if is_srikant else "State Respondent"
    citation = "Criminal Appeal No. 1552 of 2024 (FIR No. 79/2020)" if is_srikant else f"Session {case_id}"

    conv = []
    for t in raw.get("transcript", []):
        spk = t.get("speaker", "counsel")
        conv.append({
            "speaker": _format_speaker_name(spk),
            "dialogue": t.get("content", "")
        })

    return {
        "case_metadata": {
            "appellant": appellant,
            "respondent": respondent,
            "court": "Supreme Court of India",
            "citation": citation,
            "laws_referred": ["CrPC 438 / Anticipatory Bail", "IPC 354B", "IPC 379", "IPC 149"] if is_srikant else [],
            "decided_on": "14 March 2024" if is_srikant else "2024",
        },
        "simulation_conversation": conv,
        "key_legal_issues": [
            {"issue": f.get("text", "")} for f in case_facts[:5] if isinstance(f, dict)
        ],
        "case_facts": case_facts,
        "evidence_inventory": raw.get("evidence_inventory", []),
        "judge_scores": raw.get("judge_scores"),
        "verdict": raw.get("verdict"),
    }


def _format_speaker_name(role: str) -> str:
    r = role.lower()
    if "prosecut" in r:
        return "Public Prosecutor"
    if "defen" in r:
        return "Defense Counsel"
    if "judge" in r or "justice" in r:
        return "Hon’ble Judge"
    if "accused" in r:
        return "Accused"
    return role.title()


def list_cases() -> list[dict]:
    """Lightweight metadata for the case picker screen — no dialogue payload."""
    cases = []
    seen_ids = set()

    # 1. Primary cases from data/observer
    for path in sorted(glob.glob(os.path.join(CASES_DIR, "*.json"))):
        cid = _case_id_from_path(path)
        try:
            data = _load_case_file(path)
        except (json.JSONDecodeError, OSError):
            continue

        meta = data.get("case_metadata", {})
        laws = meta.get("laws_referred", [])
        issues = data.get("key_legal_issues", [])

        seen_ids.add(cid)
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

    # 2. Supplementary transcripts from backend/transcripts
    if os.path.exists(TRANSCRIPTS_DIR):
        for path in sorted(glob.glob(os.path.join(TRANSCRIPTS_DIR, "transcript_*.json"))):
            base = os.path.basename(path)
            cid = base.replace("transcript_", "").replace(".json", "")
            if cid in seen_ids:
                continue
            try:
                data = _load_transcript_case(path, cid)
            except Exception:
                continue
            meta = data.get("case_metadata", {})
            laws = meta.get("laws_referred", [])
            issues = data.get("key_legal_issues", [])
            seen_ids.add(cid)
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

    return cases


def get_case(case_id: str) -> dict | None:
    # 1. Check data/observer/<case_id>.json
    path = os.path.join(CASES_DIR, f"{case_id}.json")
    if os.path.exists(path):
        return _load_case_file(path)

    # 2. Check backend/transcripts/transcript_<case_id>.json or <case_id>.json
    if os.path.exists(TRANSCRIPTS_DIR):
        t_path = os.path.join(TRANSCRIPTS_DIR, f"transcript_{case_id}.json")
        if os.path.exists(t_path):
            return _load_transcript_case(t_path, case_id)
        raw_path = os.path.join(TRANSCRIPTS_DIR, f"{case_id}.json")
        if os.path.exists(raw_path):
            return _load_transcript_case(raw_path, case_id)

    return None


def normalize_case_data(case: dict, case_id: str) -> dict:
    """Matches the `caseData` shape CourtroomSidebar already renders."""
    meta = case.get("case_metadata", {})
    laws = meta.get("laws_referred", [])

    facts = case.get("case_facts", [])
    if not facts and "procedural_history" in case:
        facts = [
            {"id": f"fact_{idx+1}", "text": f"{item.get('date', '')}: {item.get('event', '')}", "type": "procedural_event"}
            for idx, item in enumerate(case.get("procedural_history", []))
        ]
    elif not facts and "key_legal_issues" in case:
        facts = [
            {"id": f"fact_{idx+1}", "text": f"{item.get('issue', '')} - {item.get('holding', '')}" if item.get('holding') else item.get('issue', ''), "type": "allegation"}
            for idx, item in enumerate(case.get("key_legal_issues", []))
        ]

    return {
        "fileId": case_id,
        "title": f"{meta.get('appellant', 'Unknown')} vs. {meta.get('respondent', 'Unknown')}",
        "firNo": meta.get("citation", ""),
        "charge": laws[0] if laws else "",
        "evidenceLinked": True,
        "case_facts": facts,
        "evidence_inventory": case.get("evidence_inventory", []),
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
    r"\bSection\s+\d+[A-Za-z()]*|\bIPC\s+\d+[A-Za-z()]*|\bS\.\s?\d+[A-Za-z()]*|\bCrPC\s+\d+[A-Za-z()]*",
    re.IGNORECASE,
)


def _extract_citations(text: str) -> list[str]:
    found = _CITATION_RE.findall(text)
    # de-dupe while preserving order
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
        agent_id = _infer_agent_id(speaker)
        citations = _extract_citations(text)
        events.append({
            "type": "agent_message",
            "agent_id": agent_id,
            "agent": agent_id,
            "display_name": speaker,
            "speaker": speaker,
            "full_text": text,
            "content": text,
            "text": text,
            "verified_citations": citations,
            "citations": citations,
        })

    # If this case has a final verdict decree, append it
    verdict = case.get("verdict")
    if verdict and isinstance(verdict, dict):
        events.append({
            "type": "verdict",
            "agent_id": "verdict",
            "agent": "judge",
            "result": verdict.get("result", "DENIED"),
            "confidence": verdict.get("confidence", "high"),
            "valid_votes": verdict.get("valid_votes", 3),
            "total_votes": verdict.get("total_votes", 5),
            "agree_count": verdict.get("agree_count", 3),
            "statutes": verdict.get("statutes", []),
            "precedents": verdict.get("precedents", []),
            "holdings_relied": verdict.get("holdings_relied", []),
            "vote_tally": verdict.get("vote_tally", {}),
            "explanation": verdict.get("explanation", ""),
        })

    return events