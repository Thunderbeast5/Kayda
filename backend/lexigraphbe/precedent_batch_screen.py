"""
Steps 2 and 3 of Stage 5: ONE batch LLM call over the statute shortlist, then ONE verifier call.

    shortlist (<= ~20 PrecedentCandidates)  ->  screen LLM  ->  programmatic checks + verifier LLM  ->  role evaluations

Screen LLM input : structured input case, Stage 1 sub-queries, Stage 4 summary, and one compact packet per candidate
                   (see case_packet.py).
Screen LLM output: per case: keep/reject, reason, stance toward prosecution and defence, fact match, cited holdings.
Verifier         : (a) deterministic checks - unknown case ids, proposition ids not shown, statute numbers or case names in
                   a reason that appear nowhere in the supplied data, incoherent decisions; (b) one LLM call that re-reads
                   the same packets and flags unsupported or wrong decisions. Every flag lowers the decision's confidence
                   (hallucination: x0.5, other: x0.65); a flagged decision's claims are removed and a verifier fix is
                   applied when given.
Output is shaped like PrecedentRelevanceBatchEvaluator's, so the existing scoring/selection/output code is reused.
"""
import json
import re
from typing import Any, Dict, List, Optional, Set

from langchain_core.messages import HumanMessage, SystemMessage

from .case_packet import build_packet, packet_ids, packet_text

STANCES = {"SUPPORTS", "OPPOSES", "DISTINGUISHABLE", "NEUTRAL"}
LEVELS = {"HIGH", "MODERATE", "LOW"}
BASE_CONFIDENCE = 0.85
HALLUCINATION_FACTOR = 0.5
OTHER_FLAG_FACTOR = 0.65

SCREEN_SYSTEM = (
    "You are a senior Indian criminal-law researcher screening precedents for a bail matter. Use ONLY the information "
    "in the input case and the case packets. Never invent facts, sections, case names or holdings. Reply with JSON only."
)

SCREEN_PROMPT = """INPUT CASE
{case}

LEGAL QUESTIONS (from issue analysis)
{queries}

STATUTES / OFFENCES ESTABLISHED (stage 4)
{stage4}

CANDIDATE PRECEDENTS (statute shortlist; '*' marks a statute that matches the input; [pN] ids are citable holdings)
{packets}

TASK
Decide for EVERY candidate whether a lawyer arguing this matter would actually cite it, and for which side.
keep=true only if the precedent decides a point that matters here: same kind of offence or dispute, or a holding that
answers one of the legal questions. keep=false if it shares only generic sections (e.g. the bail provision), concerns a
different kind of offence or dispute, or cannot be used by either side. Check offence type, dispute, stage and outcome.
For each side give a stance: SUPPORTS (helps that side), OPPOSES (hurts that side, must be answered),
DISTINGUISHABLE (adverse on its face but the input differs in a way you can state), NEUTRAL.
fact: HIGH (same kind of facts) / MODERATE / LOW.
props: ids of holdings you relied on (only ids shown above). reason: <= 30 words, using only facts and sections that appear
in the input case or that candidate's packet; for a rejection say what mismatched.

Return {{"decisions":[{{"id":"<case_id>","keep":true,"reason":"...","pros":"SUPPORTS|OPPOSES|DISTINGUISHABLE|NEUTRAL",
"def":"SUPPORTS|OPPOSES|DISTINGUISHABLE|NEUTRAL","fact":"HIGH|MODERATE|LOW","props":["p1"],"use":"point it is cited for"}}]}}
One entry per candidate, in the order given."""

VERIFY_SYSTEM = (
    "You audit another model's precedent screening. You see the same input and packets. Flag only real problems. "
    "Reply with JSON only."
)

VERIFY_PROMPT = """INPUT CASE
{case}

LEGAL QUESTIONS
{queries}

STATUTES / OFFENCES (stage 4)
{stage4}

CANDIDATE PACKETS
{packets}

SCREENING DECISIONS TO AUDIT
{decisions}

Check each decision against its packet and the input:
 - UNSUPPORTED: the reason states a fact, section, holding or case not present in the packet/input (hallucination).
 - WRONG_KEEP: kept although offence type, dispute or stage clearly mismatches the input, or rejected although it plainly
   decides a point raised by the input.
 - WRONG_STANCE: stance contradicts the cited holding or the outcome (e.g. bail granted but marked as helping prosecution).
Return {{"flags":[{{"id":"<case_id>","problem":"UNSUPPORTED|WRONG_KEEP|WRONG_STANCE","note":"<=20 words",
"fix":{{"keep":true|false|null,"pros":"<stance or null>","def":"<stance or null>"}}}}]}}. Return {{"flags":[]}} if all are sound."""

_SEC_RE = re.compile(r"(?:\b(?:section|sections|sec\.?|ss?\.)\s*|\b(?:IPC|BNS|CrPC|BNSS|NDPS|PCA|IEA|BSA)\s*)(\d+[A-Za-z]?)", re.I)
_CASE_RE = re.compile(r"\b([A-Z][A-Za-z.'&]+(?: [A-Z][A-Za-z.'&]+){0,3}) v\.? ([A-Z][A-Za-z.'&]+)")


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    for fence in ("```json", "```"):
        if fence in t:
            a = t.find(fence) + len(fence)
            b = t.find("```", a)
            t = t[a:b if b > 0 else None].strip()
            break
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _content(resp: Any) -> str:
    return resp.content if hasattr(resp, "content") else str(resp)


class BatchPrecedentScreen:
    def __init__(self, llm: Any = None, verifier_llm: Any = None):
        self._llm = llm
        self._vllm = verifier_llm

    @property
    def llm(self):
        if self._llm is None:
            from .config import get_llm
            self._llm = get_llm(temperature=0.1)
        return self._llm

    @property
    def verifier_llm(self):
        if self._vllm is None:
            from .config import get_llm
            self._vllm = get_llm(temperature=0.0)
        return self._vllm

    # ------------------------------------------------------------------ main
    def screen(self, candidates: List[Any], input_case: str, legal_issues: List[str], stage4_summary: str) -> Dict[str, Any]:
        if not candidates:
            return {"prosecution": [], "defense": [], "rejected": [], "report": {"llm_calls": 0}}
        packets = {c.case_id: build_packet(c) for c in candidates}
        ptxt = "\n\n".join(packet_text(packets[c.case_id]) for c in candidates)
        queries = "\n".join(f"- {q}" for q in legal_issues) if legal_issues else "(none supplied)"
        fmt = dict(case=input_case, queries=queries, stage4=stage4_summary, packets=ptxt)

        raw = _parse_json(_content(self.llm.invoke([SystemMessage(content=SCREEN_SYSTEM),
                                                    HumanMessage(content=SCREEN_PROMPT.format(**fmt))])))
        calls = 1
        decisions, flags = self._normalise(raw, candidates, packets, input_case + " " + stage4_summary + " " + queries)

        # verifier: one call over the same data
        slim = [{k: d[k] for k in ("id", "keep", "reason", "pros", "def", "fact", "props")} for d in decisions.values()]
        vraw = _parse_json(_content(self.verifier_llm.invoke([
            SystemMessage(content=VERIFY_SYSTEM),
            HumanMessage(content=VERIFY_PROMPT.format(**fmt, decisions=json.dumps(slim, ensure_ascii=False)))])))
        calls += 1
        self._apply_verifier(vraw, decisions, flags)

        return self._to_evaluations(candidates, decisions, flags, calls)

    # ----------------------------------------------------- deterministic checks
    def _normalise(self, raw: Optional[Dict[str, Any]], candidates: List[Any], packets: Dict[str, Dict[str, Any]],
                   input_blob: str):
        by_id = {c.case_id: c for c in candidates}
        got: Dict[str, Dict[str, Any]] = {}
        flags: Dict[str, List[Dict[str, str]]] = {cid: [] for cid in by_id}
        for d in (raw or {}).get("decisions", []) if isinstance(raw, dict) else []:
            cid = str(d.get("id", ""))
            if cid not in by_id:
                continue                                    # unknown id: ignored, nothing to attach it to
            if cid in got:
                flags[cid].append({"kind": "DUPLICATE", "note": "duplicate decision ignored"})
                continue
            got[cid] = d
        out: Dict[str, Dict[str, Any]] = {}
        for cid, c in by_id.items():
            pk = packets[cid]
            blob = packet_text(pk) + " " + input_blob + " " + " ".join(str(s.get("section", "")) for s in c.statutes or [])
            blob_secs = {m.upper() for m in re.findall(r"\d+[A-Za-z]?", blob)}
            d = got.get(cid)
            if d is None:
                flags[cid].append({"kind": "MISSING", "note": "no decision returned for this candidate"})
                out[cid] = {"id": cid, "keep": False, "reason": "not assessed by screening model", "pros": "NEUTRAL",
                            "def": "NEUTRAL", "fact": "LOW", "props": [], "use": "", "hallucinated": False}
                continue
            reason = str(d.get("reason", "")).strip()
            pros = str(d.get("pros", "NEUTRAL")).upper()
            dfn = str(d.get("def", "NEUTRAL")).upper()
            fact = str(d.get("fact", "LOW")).upper()
            keep = d.get("keep") is True
            hallu = False
            if pros not in STANCES or dfn not in STANCES or fact not in LEVELS:
                flags[cid].append({"kind": "FORMAT", "note": "invalid stance/fact value"})
                pros, dfn, fact = (pros if pros in STANCES else "NEUTRAL"), (dfn if dfn in STANCES else "NEUTRAL"), \
                                  (fact if fact in LEVELS else "LOW")
            shown = packet_ids(pk)
            props = [p for p in (d.get("props") or []) if isinstance(p, str)]
            bad_props = [p for p in props if p not in shown]
            if bad_props:
                hallu = True
                flags[cid].append({"kind": "HALLUCINATION", "note": f"cited holding ids not in packet: {bad_props}"})
                props = [p for p in props if p in shown]
            bad_secs = sorted({m for m in _SEC_RE.findall(reason) if m.upper() not in blob_secs})
            if bad_secs:
                hallu = True
                flags[cid].append({"kind": "HALLUCINATION", "note": f"reason cites section(s) {bad_secs} not in the data"})
            names = [m[0] for m in _CASE_RE.findall(reason)]
            lowered = blob.lower()
            bad_names = [n for n in names if n.lower() not in lowered]
            if bad_names:
                hallu = True
                flags[cid].append({"kind": "HALLUCINATION", "note": f"reason names case(s) not in the data: {bad_names}"})
            if keep and pros == "NEUTRAL" and dfn == "NEUTRAL":
                flags[cid].append({"kind": "INCOHERENT", "note": "kept but neutral for both sides"})
                keep = False
            if not reason:
                flags[cid].append({"kind": "FORMAT", "note": "no reason given"})
            out[cid] = {"id": cid, "keep": keep, "reason": reason, "pros": pros, "def": dfn, "fact": fact,
                        "props": props, "use": str(d.get("use", "")), "hallucinated": hallu}
        return out, flags

    def _apply_verifier(self, vraw: Optional[Dict[str, Any]], decisions: Dict[str, Dict[str, Any]],
                        flags: Dict[str, List[Dict[str, str]]]) -> None:
        if not isinstance(vraw, dict):
            for cid in decisions:
                flags[cid].append({"kind": "VERIFIER_UNAVAILABLE", "note": "verifier reply unparseable; programmatic checks only"})
            return
        for f in vraw.get("flags", []) or []:
            cid = str(f.get("id", ""))
            if cid not in decisions:
                continue
            problem = str(f.get("problem", "")).upper()
            flags[cid].append({"kind": "V_" + problem, "note": str(f.get("note", ""))})
            d = decisions[cid]
            if problem == "UNSUPPORTED":
                d["hallucinated"] = True
            fix = f.get("fix") or {}
            if isinstance(fix.get("keep"), bool):
                d["keep"] = fix["keep"]
            for k in ("pros", "def"):
                v = str(fix.get(k) or "").upper()
                if v in STANCES:
                    d[k] = v

    # ------------------------------------------------------------- conversion
    @staticmethod
    def _type(stance: str, fact: str, keep: bool) -> str:
        if not keep:
            return "LOW_RELEVANCE"
        if stance == "SUPPORTS":
            if fact == "LOW":
                return "BACKGROUND"             # same cap the rule-based verifier applies: low-fact support is background
            return "DIRECTLY_SUPPORTING" if fact == "HIGH" else "STRONGLY_SUPPORTING"
        if stance == "OPPOSES":
            return "DIRECTLY_OPPOSING" if fact == "HIGH" else ("STRONGLY_OPPOSING" if fact == "MODERATE" else "DISTINGUISHABLE")
        if stance == "DISTINGUISHABLE":
            return "DISTINGUISHABLE"
        return "BACKGROUND"

    def _to_evaluations(self, candidates: List[Any], decisions: Dict[str, Dict[str, Any]],
                        flags: Dict[str, List[Dict[str, str]]], calls: int) -> Dict[str, Any]:
        res: Dict[str, List[Dict[str, Any]]] = {"prosecution": [], "defense": []}
        rejected: List[Dict[str, str]] = []
        penalised: List[Dict[str, Any]] = []
        for c in candidates:
            d = decisions[c.case_id]
            fl = flags[c.case_id]
            conf = BASE_CONFIDENCE
            if d["hallucinated"]:
                conf *= HALLUCINATION_FACTOR
            elif any(f["kind"] not in ("VERIFIER_UNAVAILABLE",) for f in fl):
                conf *= OTHER_FLAG_FACTOR
            if fl:
                penalised.append({"case_id": c.case_id, "confidence": round(conf, 2), "flags": fl})
            if not d["keep"]:
                rejected.append({"case_id": c.case_id, "case_name": c.case_name, "reason": d["reason"]})
                continue
            for role, key, own in (("prosecution", "pros", "SUPPORTS"), ("defense", "def", "SUPPORTS")):
                stance = d[key]
                rel = self._type(stance, d["fact"], True)
                ev = {
                    "case_id": c.case_id, "case_name": c.case_name, "is_relevant": True, "relevance_type": rel,
                    "confidence": round(conf, 2), "factual_similarity_level": d["fact"],
                    "supporting_propositions": d["props"] if stance == "SUPPORTS" else [],
                    "contradicting_propositions": d["props"] if stance in ("OPPOSES", "DISTINGUISHABLE") else [],
                    "use_for": [d["use"]] if d["use"] and stance == "SUPPORTS" else [],
                    "against_role": [d["reason"]] if stance in ("OPPOSES", "DISTINGUISHABLE") else [],
                    "screen_reason": d["reason"], "screen_flags": [f["kind"] for f in fl],
                }
                res[role].append({"candidate": c, "evaluation": ev,
                                  "verification": {"verified": not fl, "issues": [f["note"] for f in fl], "evaluation": ev}})
        return {**res, "rejected": rejected,
                "report": {"llm_calls": calls, "candidates": len(candidates), "kept": len(candidates) - len(rejected),
                           "rejected": len(rejected), "penalised": penalised}}
