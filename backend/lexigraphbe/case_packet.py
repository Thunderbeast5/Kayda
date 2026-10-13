"""
Compact, LLM-ready description of ONE precedent for the batch screening call (~250-300 tokens).

What is sent, and why (everything else in the tagged JSON is left out):
    case_id, name, court, year      identify the case and its binding weight
    procedural_stage, outcome       was bail granted / refused / cancelled / FIR quashed: decides which side it helps
    offence_types, dispute_nature   what kind of case it is (the field the reasoner needs to reject wrong-domain cases)
    statutes                        '*' marks the ones that matched the input (the evidence behind the shortlist)
    abstract_facts                  trimmed
    lower_court_outcome             trimmed
    issues                          question -> short_answer (max 2)
    holdings                        proposition id, who it favours, text (max 3; the ids are what the LLM may cite)

Left out: paragraphs, headnote, quotes, anchors, contentions, authority table, coram, parser flags, review notes,
non-holding propositions. Propositions the tagger's own verifier marked 'unsupported' are only used if nothing else exists.
"""
import re
from typing import Any, Dict, List, Set, Tuple


def _trim(text: Any, words: int) -> str:
    toks = re.sub(r"\s+", " ", str(text or "")).strip().split(" ")
    return " ".join(toks[:words]) + (" ..." if len(toks) > words else "") if toks != [""] else ""


def _year(decided_on: str) -> str:
    m = re.match(r"(\d{4})", str(decided_on or ""))
    return m.group(1) if m else ""


def _court(court: str) -> str:
    c = (court or "").lower()
    return "SC" if "supreme" in c else ("HC" if "high" in c else (court or "?")[:20])


def select_holdings(cand: Any, max_n: int = 3, words: int = 38) -> List[Dict[str, str]]:
    props = list(getattr(cand, "propositions", None) or [])
    verdicts = getattr(cand, "verdicts", None) or {}

    def rank(p: Dict[str, Any]) -> Tuple[int, int]:
        holding = 0 if (p.get("is_holding") or p.get("kind") == "ratio") else 1
        unsupported = 1 if (verdicts.get(p.get("id"), {}) or {}).get("verdict") == "unsupported" else 0
        return (holding, unsupported)

    props.sort(key=rank)
    chosen = [p for p in props if rank(p)[0] == 0 and rank(p)[1] == 0][:max_n]
    if not chosen:
        chosen = [p for p in props if rank(p)[0] == 0][:max_n] or props[:max_n]
    return [{"id": str(p.get("id", "")), "favors": str(p.get("favors", "neutral")), "text": _trim(p.get("text"), words)}
            for p in chosen if p.get("id")]


def build_packet(cand: Any, max_issues: int = 2) -> Dict[str, Any]:
    matched = {str(m.get("statute") or m.get("section") or "") for m in (cand.matched_statutes or [])}
    matched_secs = {re.sub(r"\s+", "", str(m.get("section", ""))).upper() for m in (cand.matched_statutes or [])}
    stat_bits: List[str] = []
    for s in (cand.statutes or [])[:40]:
        sec = str(s.get("section", "")).strip()
        label = f"{_short_act(str(s.get('act', '')))} {sec}"
        star = "*" if re.sub(r"\s+", "", sec).upper() in matched_secs else ""
        if label not in stat_bits and f"{label}*" not in stat_bits:
            stat_bits.append(label + star)
    stat_bits.sort(key=lambda x: (not x.endswith("*"), x))
    holdings = select_holdings(cand)
    issues = [{"q": _trim(i.get("question"), 30), "a": _trim(i.get("short_answer"), 28)}
              for i in (cand.issues or [])[:max_issues] if i.get("question")]
    return {
        "case_id": cand.case_id,
        "name": _trim(cand.case_name, 14),
        "court_year": f"{_court(cand.court)} {_year(cand.decided_on)}".strip(),
        "stage": cand.procedural_stage or cand.inferred_stage,
        "outcome": _trim(cand.disposition, 18),
        "offence_types": ", ".join(cand.offence_types[:5]) if getattr(cand, "offence_types", None) else "",
        "dispute": getattr(cand, "dispute_nature", "") or "",
        "statutes": ", ".join(stat_bits[:12]),
        "facts": _trim(cand.abstract_facts, 60),
        "lower_court": _trim(getattr(cand, "lower_court_outcome", ""), 22),
        "issues": issues,
        "holdings": holdings,
    }


_ACT_SHORT = [("indian penal", "IPC"), ("bharatiya nyaya", "BNS"), ("bharatiya nagarik", "BNSS"), ("criminal procedure", "CrPC"),
              ("crpc", "CrPC"), ("evidence", "IEA"), ("bharatiya sakshya", "BSA"), ("narcotic", "NDPS"), ("corruption", "PCA"),
              ("negotiable", "NI Act"), ("money laundering", "PMLA"), ("pocso", "POCSO"), ("protection of children", "POCSO"),
              ("dowry", "Dowry Act"), ("information technology", "IT Act"), ("unlawful activities", "UAPA")]


def _short_act(act: str) -> str:
    a = act.lower()
    for k, v in _ACT_SHORT:
        if k in a:
            return v
    return act.strip()[:14] or "?"


def packet_text(p: Dict[str, Any]) -> str:
    lines = [f"[{p['case_id']}] {p['name']} ({p['court_year']}) | stage: {p['stage']} | outcome: {p['outcome']}"]
    meta = " | ".join(x for x in (f"offence: {p['offence_types']}" if p["offence_types"] else "",
                                   f"dispute: {p['dispute']}" if p["dispute"] else "") if x)
    if meta:
        lines.append(meta)
    lines.append(f"statutes: {p['statutes']}")
    lines.append(f"facts: {p['facts']}")
    if p["lower_court"]:
        lines.append(f"lower court: {p['lower_court']}")
    for i in p["issues"]:
        lines.append(f"issue: {i['q']} -> {i['a']}")
    for h in p["holdings"]:
        lines.append(f"{h['id']} [{h['favors']}]: {h['text']}")
    return "\n".join(lines)


def packet_ids(p: Dict[str, Any]) -> Set[str]:
    return {h["id"] for h in p["holdings"]}
