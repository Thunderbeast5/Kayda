"""
Batch screen over the statute shortlist, then ONE verifier call.

    shortlist (<= ~20 PrecedentCandidates)  ->  screen LLM  ->  programmatic checks + verifier LLM  ->  role evaluations

Screen LLM input : structured input case, Stage 1 sub-queries, Stage 4 summary, and one compact packet per candidate
                   (see case_packet.py).
Screen LLM output: per case: keep/reject, the court's actual HOLDING first, holding_favors (which side the holding
                   favours), then role stances derived FROM that holding (not inferred independently), fact match,
                   cited proposition ids.

                   KEY DESIGN RULE: holding_favors determines stances deterministically:
                     - The favoured side gets SUPPORTS.
                     - The other side gets OPPOSES or DISTINGUISHABLE (if facts differ materially).
                     - NEUTRAL only when holding is genuinely procedural and neither side benefits.
                   This prevents the same proposition being claimed as SUPPORTS by both sides.

Verifier         : (a) deterministic checks — unknown case ids, proposition ids not shown, statute numbers or case
                   names in a reason that appear nowhere in the supplied data, incoherent decisions, stance
                   contradiction with holding_favors; (b) one LLM call that re-reads the same packets and flags
                   unsupported or wrong decisions. Every flag lowers the decision's confidence
                   (hallucination: x0.5, other: x0.65); a flagged decision's claims are removed and a verifier fix
                   is applied when given.

Output is shaped like PrecedentRelevanceBatchEvaluator's, so the existing scoring/selection/output code is reused.
"""
import json
import re
from typing import Any, Dict, List, Optional, Set

from langchain_core.messages import HumanMessage, SystemMessage

from .case_packet import build_packet, packet_ids, packet_text

STANCES = {"SUPPORTS", "OPPOSES", "DISTINGUISHABLE", "NEUTRAL"}
LEVELS = {"HIGH", "MODERATE", "LOW"}
HOLDING_FAVORS = {"prosecution", "defence", "neutral"}
CHANNELS = {"facts", "principle", "procedural"}

# Relevance-type overrides for principle/procedural channel cases.
# A case kept on principle only cannot be DIRECTLY_SUPPORTING — it is at most STRONGLY_SUPPORTING
# (if the principle squarely applies) or BACKGROUND (general principle).
# This prevents a procedurally-different but principle-relevant case from outscoring
# a factually-matching case in the final ranking.
CHANNEL_RELEVANCE_CAP = {
    "facts":      None,           # no cap — normal type derivation applies
    "principle":  "STRONGLY_SUPPORTING",   # cap for SUPPORTS+HIGH; still meaningful
    "procedural": "STRONGLY_SUPPORTING",
}

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

IMPORTANT — Two-phase evaluation per candidate:

PHASE 1 — ESTABLISH THE ACTUAL HOLDING FIRST:
Before assigning any role stances, state what the court in this case actually decided:
- holding: What did the court hold? (<=25 words, from the packet only, no invention)
- holding_favors: Which side does that holding primarily favour?
  "prosecution" = the holding helps deny bail / supports custodial interrogation / establishes guilt
  "defence"     = the holding helps grant bail / protects personal liberty / limits prosecution power
  "neutral"     = purely procedural holding, neither side directly benefits

PHASE 2 — DERIVE ROLE STANCES FROM THE HOLDING:
After establishing the holding, assign stances as follows:
- If holding_favors = "prosecution": pros = SUPPORTS, def = OPPOSES (or DISTINGUISHABLE if facts materially differ)
- If holding_favors = "defence": def = SUPPORTS, pros = OPPOSES (or DISTINGUISHABLE if facts materially differ)
- If holding_favors = "neutral": both sides = NEUTRAL (or one DISTINGUISHABLE if there is a clear factual hook)
- NEVER assign SUPPORTS to BOTH sides for the same holding unless holding_favors = "neutral" AND
  there is a genuine procedural hook each side exploits differently — explain this in reason if so.

KEEP / REJECT RULES — read carefully before deciding:

keep=true for ANY of these three reasons (assign the matching channel):
  channel="facts"      — similar facts AND similar kind of offence/dispute (most on-point)
  channel="principle"  — different facts, BUT the court's holding answers a legal question that
                         arises in the input: e.g. conditions for anticipatory bail, custodial
                         interrogation necessity, economic offence gravity, flight risk, evidence
                         tampering risk — any principle a bail court would apply here.
  channel="procedural" — the case concerns the same procedural question (anticipatory bail grant,
                         AB conditions, pre-arrest protection) even if the underlying offence differs.
                         A case on anticipatory bail in a matrimonial matter still establishes
                         procedural principles relevant to anticipatory bail in a commercial matter.

keep=false ONLY when the case has NO usable holding at all: purely academic, entirely unrelated
jurisdiction/statute, or factually so remote that no principle from it could be cited.

DO NOT reject a case merely because:
  - The underlying offence category differs (fraud vs matrimonial vs corruption)
  - The facts are not identical
  - The stage is anticipatory_cancel vs pre_arrest (note the difference in reason, but keep it)

PROCEDURAL STAGE NOTE:
If the candidate is an anticipatory-bail cancellation (anticipatory_cancel) and the input is an
initial anticipatory-bail application (pre_arrest), note this in reason. Assign channel="procedural"
unless the facts also match, in which case channel="facts".

fact: HIGH (same kind of facts/offence) / MODERATE (related facts or same offence category) /
      LOW (different facts but relevant legal principle or procedural holding).
      For channel="principle" or channel="procedural", fact will usually be LOW or MODERATE.

props: ids of holdings you relied on (only ids shown above).
reason: <=40 words. For kept cases: what legal point it establishes and how it helps one side.
        For rejected cases: why it has NO usable holding for this matter.

Return {{"decisions":[{{
  "id":"<case_id>",
  "keep":true,
  "channel":"facts|principle|procedural",
  "holding":"<what the court actually held, <=25 words>",
  "holding_favors":"prosecution|defence|neutral",
  "reason":"...",
  "pros":"SUPPORTS|OPPOSES|DISTINGUISHABLE|NEUTRAL",
  "def":"SUPPORTS|OPPOSES|DISTINGUISHABLE|NEUTRAL",
  "fact":"HIGH|MODERATE|LOW",
  "props":["p1"],
  "use":"<point it is cited for>"
}}]}}
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
 - UNSUPPORTED: the reason or holding states a fact, section, holding or case not present in the packet/input (hallucination).
 - WRONG_KEEP: kept although offence type, dispute or stage clearly mismatches the input, or rejected although it plainly
   decides a point raised by the input.
 - WRONG_STANCE: the assigned pros/def stances contradict holding_favors (e.g. holding_favors=prosecution but def=SUPPORTS
   without a legitimate distinguishing reason, or the same proposition assigned SUPPORTS to both sides).
 - WRONG_HOLDING: holding states something not supported by the packet's propositions or disposition.
Return {{"flags":[{{"id":"<case_id>","problem":"UNSUPPORTED|WRONG_KEEP|WRONG_STANCE|WRONG_HOLDING","note":"<=20 words",
"fix":{{"keep":true|false|null,"pros":"<stance or null>","def":"<stance or null>","holding_favors":"<or null>"}}}}]}}.
Return {{"flags":[]}} if all are sound."""

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


def _infer_stance_from_holding(holding_favors: str, other_side: str, fact: str) -> str:
    """
    Derive the stance for `other_side` given holding_favors.
    If fact is LOW the other side may DISTINGUISH; if MODERATE/HIGH they face OPPOSES.
    """
    if holding_favors == "neutral":
        return "NEUTRAL"
    if holding_favors == other_side:
        return "SUPPORTS"
    # The other side is opposed by this holding
    return "DISTINGUISHABLE" if fact == "LOW" else "OPPOSES"


class BatchPrecedentScreen:
    def __init__(self, llm: Any = None, verifier_llm: Any = None):
        self._llm = llm
        self._vllm = verifier_llm

    @property
    def llm(self):
        if self._llm is None:
            from lexigraphbe.config import get_llm
            self._llm = get_llm(temperature=0.1)
        return self._llm

    @property
    def verifier_llm(self):
        if self._vllm is None:
            from lexigraphbe.config import get_llm
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
        slim = [{k: d[k] for k in ("id", "keep", "holding", "holding_favors", "reason", "pros", "def", "fact", "props")} for d in decisions.values()]
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
                continue
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
                out[cid] = {"id": cid, "keep": False, "channel": "principle",
                            "holding": "", "holding_favors": "neutral",
                            "reason": "not assessed by screening model", "pros": "NEUTRAL",
                            "def": "NEUTRAL", "fact": "LOW", "props": [], "use": "", "hallucinated": False}
                continue
            reason = str(d.get("reason", "")).strip()
            holding = str(d.get("holding", "")).strip()
            holding_favors = str(d.get("holding_favors", "neutral")).lower().strip()
            pros = str(d.get("pros", "NEUTRAL")).upper()
            dfn = str(d.get("def", "NEUTRAL")).upper()
            fact = str(d.get("fact", "LOW")).upper()
            keep = d.get("keep") is True
            hallu = False

            # Validate holding_favors
            if holding_favors not in HOLDING_FAVORS:
                holding_favors = "neutral"
                flags[cid].append({"kind": "FORMAT", "note": f"invalid holding_favors value; reset to neutral"})

            if pros not in STANCES or dfn not in STANCES or fact not in LEVELS:
                flags[cid].append({"kind": "FORMAT", "note": "invalid stance/fact value"})
                pros = pros if pros in STANCES else "NEUTRAL"
                dfn = dfn if dfn in STANCES else "NEUTRAL"
                fact = fact if fact in LEVELS else "LOW"

            # CORE CHECK: Stance consistency with holding_favors.
            # Both sides SUPPORTS is only legitimate when holding_favors=neutral AND both sides
            # have a genuine hook (which requires a reason explaining it). Flag otherwise.
            if pros == "SUPPORTS" and dfn == "SUPPORTS" and holding_favors != "neutral":
                flags[cid].append({
                    "kind": "STANCE_CONTRADICTION",
                    "note": f"both sides SUPPORTS but holding_favors={holding_favors}; correcting stances"
                })
                # Correct: the favoured side keeps SUPPORTS, other gets OPPOSES/DISTINGUISHABLE
                if holding_favors == "prosecution":
                    dfn = _infer_stance_from_holding("prosecution", "defence", fact)
                elif holding_favors == "defence":
                    pros = _infer_stance_from_holding("defence", "prosecution", fact)

            # Also check: if holding_favors says prosecution but def=SUPPORTS without being DISTINGUISHABLE
            if holding_favors == "prosecution" and dfn == "SUPPORTS":
                flags[cid].append({
                    "kind": "STANCE_CONTRADICTION",
                    "note": "holding_favors=prosecution but def=SUPPORTS; correcting to DISTINGUISHABLE"
                })
                dfn = "DISTINGUISHABLE" if fact == "LOW" else "OPPOSES"
            if holding_favors == "defence" and pros == "SUPPORTS":
                flags[cid].append({
                    "kind": "STANCE_CONTRADICTION",
                    "note": "holding_favors=defence but pros=SUPPORTS; correcting to DISTINGUISHABLE"
                })
                pros = "DISTINGUISHABLE" if fact == "LOW" else "OPPOSES"

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
            # Channel — which relevance track did the screen LLM assign?
            channel = str(d.get("channel", "")).lower().strip()
            if channel not in CHANNELS:
                # Tolerate missing channel: infer from fact level as a fallback.
                # HIGH/MODERATE fact → treat as "facts"; LOW → "principle".
                channel = "facts" if fact in ("HIGH", "MODERATE") else "principle"
                if channel != "facts":
                    flags[cid].append({"kind": "FORMAT", "note": f"missing/invalid channel; inferred '{channel}' from fact={fact}"})

            out[cid] = {
                "id": cid, "keep": keep, "channel": channel,
                "holding": holding, "holding_favors": holding_favors,
                "reason": reason, "pros": pros, "def": dfn, "fact": fact,
                "props": props, "use": str(d.get("use", "")), "hallucinated": hallu,
            }
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
            if problem in ("UNSUPPORTED", "WRONG_HOLDING"):
                d["hallucinated"] = True
            fix = f.get("fix") or {}
            if isinstance(fix.get("keep"), bool):
                d["keep"] = fix["keep"]
            # Apply verifier's holding_favors fix first, then re-derive stances if needed
            hf_fix = str(fix.get("holding_favors") or "").lower()
            if hf_fix in HOLDING_FAVORS:
                d["holding_favors"] = hf_fix
                # Re-derive stances from corrected holding_favors
                fact = d.get("fact", "LOW")
                if hf_fix == "prosecution":
                    d["pros"] = "SUPPORTS"
                    d["def"] = _infer_stance_from_holding("prosecution", "defence", fact)
                elif hf_fix == "defence":
                    d["def"] = "SUPPORTS"
                    d["pros"] = _infer_stance_from_holding("defence", "prosecution", fact)
                else:
                    d["pros"] = "NEUTRAL"
                    d["def"] = "NEUTRAL"
            else:
                # Apply explicit stance fixes from verifier if provided
                for k in ("pros", "def"):
                    v = str(fix.get(k) or "").upper()
                    if v in STANCES:
                        d[k] = v

    # ------------------------------------------------------------- conversion
    # Type ordering used for channel cap enforcement (higher index = higher relevance type).
    _TYPE_ORDER = ["LOW_RELEVANCE", "BACKGROUND", "DISTINGUISHABLE", "STRONGLY_OPPOSING",
                   "DIRECTLY_OPPOSING", "STRONGLY_SUPPORTING", "DIRECTLY_SUPPORTING"]

    @classmethod
    def _type(cls, stance: str, fact: str, keep: bool, channel: str = "facts") -> str:
        if not keep:
            return "LOW_RELEVANCE"
        if stance == "SUPPORTS":
            if fact == "LOW":
                base = "BACKGROUND"
            else:
                base = "DIRECTLY_SUPPORTING" if fact == "HIGH" else "STRONGLY_SUPPORTING"
        elif stance == "OPPOSES":
            base = "DIRECTLY_OPPOSING" if fact == "HIGH" else ("STRONGLY_OPPOSING" if fact == "MODERATE" else "DISTINGUISHABLE")
        elif stance == "DISTINGUISHABLE":
            base = "DISTINGUISHABLE"
        else:
            base = "BACKGROUND"

        # Apply channel relevance cap: principle/procedural cases cannot exceed the cap.
        cap = CHANNEL_RELEVANCE_CAP.get(channel)
        if cap is not None:
            base_idx = cls._TYPE_ORDER.index(base) if base in cls._TYPE_ORDER else 0
            cap_idx  = cls._TYPE_ORDER.index(cap)  if cap  in cls._TYPE_ORDER else len(cls._TYPE_ORDER)
            if base_idx > cap_idx:
                base = cap
        return base

    # Role eligibility: which stances qualify a case for a role's affirmative list?
    # SUPPORTS → always eligible (the role can rely on this case)
    # NEUTRAL   → eligible (procedural principle useful to both sides)
    # DISTINGUISHABLE → NOT eligible for the role that must distinguish it; belongs only in the
    #              other role's list as an OPPOSING case they already have via their own key
    # OPPOSES   → NOT eligible for the role it cuts against
    # BACKGROUND is derived from SUPPORTS+LOW_FACT (see _type); it IS eligible — a general
    #             principle cite is still a legitimate use.
    _ROLE_ELIGIBLE_STANCES: Set[str] = {"SUPPORTS", "NEUTRAL"}

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

            holding_favors = d.get("holding_favors", "neutral")
            added_to_any = False

            for role, key in (("prosecution", "pros"), ("defense", "def")):
                stance = d[key]

                # Role-eligibility gate: a case that cuts against this role does NOT
                # appear in that role's affirmative list. It is already present in the
                # other role's list as a SUPPORTS case (via that role's own key).
                # This fixes the symptom: defence list containing "Supports Role: False".
                # Proposition-level override: a case whose single "holding_favors" label
                # points at the other side can still contain holdings that favour this
                # role (e.g. custodial interrogation holdings in a bail case the screen
                # labelled pro-accused). Those holdings make it citable for this role.
                favour_tag = "prosecution" if role == "prosecution" else "accused"
                role_props = [
                    p.get("id") for p in (getattr(c, "propositions", None) or [])
                    if isinstance(p, dict) and p.get("favors") == favour_tag and p.get("is_holding") and p.get("id")
                ]
                prop_backed = bool(role_props) and stance not in self._ROLE_ELIGIBLE_STANCES

                if stance not in self._ROLE_ELIGIBLE_STANCES and not prop_backed:
                    continue

                channel = d.get("channel", "facts")
                rel = self._type("SUPPORTS" if prop_backed else stance, "LOW" if prop_backed else d["fact"], True, channel)
                supports = stance == "SUPPORTS" or bool(role_props)
                shown_props = d["props"] if stance == "SUPPORTS" and d["props"] else role_props
                ev = {
                    "case_id": c.case_id,
                    "case_name": c.case_name,
                    "is_relevant": True,
                    "relevance_type": rel,
                    "channel": channel,
                    "confidence": round(conf, 2),
                    "factual_similarity_level": d["fact"],
                    # Holding metadata — what the court actually decided
                    "holding": d.get("holding", ""),
                    "holding_favors": holding_favors,
                    "supports_role": supports,
                    "supporting_propositions": shown_props if supports else [],
                    "contradicting_propositions": [],
                    "use_for": [d["use"]] if d["use"] and supports else [],
                    "against_role": [],
                    "screen_reason": d["reason"],
                    "screen_flags": [f["kind"] for f in fl],
                }
                res[role].append({
                    "candidate": c,
                    "evaluation": ev,
                    "verification": {"verified": not fl, "issues": [f["note"] for f in fl], "evaluation": ev},
                })
                added_to_any = True

            # If the case was kept but qualifies for neither role's affirmative list
            # (e.g. OPPOSES prosecution AND OPPOSES defence — unusual but possible for
            # purely procedural cases both sides treat as adverse), log it as rejected.
            if not added_to_any:
                rejected.append({
                    "case_id": c.case_id,
                    "case_name": c.case_name,
                    "reason": f"kept by screen but OPPOSES/DISTINGUISHABLE for both roles — not included in either list",
                })
        return {
            **res,
            "rejected": rejected,
            "report": {
                "llm_calls": calls,
                "candidates": len(candidates),
                "kept": len(candidates) - len(rejected),
                "rejected": len(rejected),
                "penalised": penalised,
            },
        }