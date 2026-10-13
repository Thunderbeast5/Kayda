"""
agents/judge/voting.py
======================
Voting-based judicial decision engine.

Design (per spec):
  * decide()    - calls the LLM n times (default 5), validates each vote
                  structurally, and aggregates by majority.
  * validate()  - STRUCTURAL only: checks cited fact_ids and holding_ids
                  actually exist in the shown sets; rejects escape-hatch
                  NO_OPINION without open_questions, and verdicts with zero
                  fact citations.
  * aggregate() - majority vote; agreement < 0.6 -> NO_OPINION ("judge split").
                  Confidence is the agreement rate (transparent, not arbitrary).

Legal rules come from the holdings data shown to the judge -- never from
if-statements in this file.
"""

from __future__ import annotations

import json
import re
import os
from collections import Counter
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -- Pydantic models -----------------------------------------------------------

class Factor(BaseModel):
    """One judicial factor: a finding tied to specific fact and holding IDs."""
    finding: str
    fact_ids: List[str] = Field(default_factory=list)
    holding_ids: List[str] = Field(default_factory=list)


class JudgeVote(BaseModel):
    """A single LLM judge run output -- structured, citable, validatable."""
    outcome: str
    factors: List[Factor] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    laws_applied: List[str] = Field(default_factory=list)
    raw_explanation: str = ""


class VerdictResult(BaseModel):
    """Aggregated final verdict returned to the orchestrator."""
    outcome: str
    confidence: str                           # "high" | "medium" | "low"
    agreement_rate: float                     # fraction of surviving votes, 0.0-1.0
    why: str
    laws_applied: List[str] = Field(default_factory=list)
    statutes: List[str] = Field(default_factory=list)
    precedents: List[str] = Field(default_factory=list)
    holdings_relied: List[str] = Field(default_factory=list)
    factors: List[Factor] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    vote_tally: Dict[str, int] = Field(default_factory=dict)
    valid_votes: int = 0
    total_votes: int = 0
    agree_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision":         self.outcome,
            "confidence":       self.confidence,
            "confidence_label": self.confidence,
            "agreement_rate":   self.agreement_rate,
            "valid_votes":      self.valid_votes,
            "total_votes":      self.total_votes,
            "agree_count":      self.agree_count,
            "laws_applied":     self.laws_applied,
            "statutes":         self.statutes,
            "precedents":       self.precedents,
            "holdings_relied":  self.holdings_relied,
            "reasoning":        self.why,
            "factors":          [f.model_dump() for f in self.factors],
            "open_questions":   self.open_questions,
            "vote_tally":       self.vote_tally,
        }


# -- Validation (structure only, NOT law) --------------------------------------

def validate(vote: JudgeVote, fact_ids: set, holding_ids: set) -> tuple[bool, str]:
    """
    Structural validator -- never encodes legal rules.

    Rejects a vote if:
      1. It cites a fact_id not in the shown facts          -> invented citation
      2. It cites a holding_id not in the shown holdings    -> invented citation
      3. outcome == NO_OPINION but open_questions is empty  -> escape-hatch abuse
      4. outcome != NO_OPINION but no facts are cited       -> unfounded verdict
    """
    cited_facts = {fid for fac in vote.factors for fid in fac.fact_ids}
    cited_holdings = {hid for fac in vote.factors for hid in fac.holding_ids}

    invented_facts = cited_facts - fact_ids
    if invented_facts:
        return False, f"invented fact_id(s): {sorted(invented_facts)}"

    invented_holdings = cited_holdings - holding_ids
    if invented_holdings:
        return False, f"invented holding_id(s): {sorted(invented_holdings)}"

    if vote.outcome == "NO_OPINION" and not vote.open_questions:
        return False, "outcome is NO_OPINION but open_questions is empty"

    if vote.outcome not in ("NO_OPINION",) and not cited_facts:
        return False, f"outcome is {vote.outcome} but no facts are cited in factors"

    return True, "grounded"


# -- Aggregation ---------------------------------------------------------------

def _merge_open_questions(votes: List[JudgeVote]) -> List[str]:
    seen: set = set()
    merged: List[str] = []
    for v in votes:
        for q in v.open_questions:
            if q.strip() and q.strip() not in seen:
                seen.add(q.strip())
                merged.append(q.strip())
    return merged


def aggregate(votes: List[JudgeVote], total_attempts: int = 5) -> VerdictResult:
    """
    Majority-vote aggregation with vote-loss penalty.

    Confidence scale: "high" | "medium" | "low" (no percentage string).
    If validation failure rate is high (>20% failed, i.e. <4/5 valid),
    confidence is downgraded to reflect the unreliability of attempts.
    """
    valid_count = len(votes)
    if not votes:
        return VerdictResult(
            outcome="NO_OPINION",
            confidence="low",
            agreement_rate=0.0,
            why="No grounded judge output: all votes failed structural validation.",
            open_questions=["Judge output could not be grounded in cited facts/holdings."],
            valid_votes=0,
            total_votes=total_attempts,
            agree_count=0,
        )

    tally = Counter(v.outcome for v in votes)
    outcome, k = tally.most_common(1)[0]
    agreement = k / valid_count if valid_count > 0 else 0.0
    valid_rate = valid_count / total_attempts if total_attempts > 0 else 0.0

    # Base confidence from survivor agreement
    if agreement < 0.6:
        base_conf = "low"
    elif agreement < 0.8:
        base_conf = "medium"
    else:
        base_conf = "high"

    # Downgrade confidence when many votes fail validation
    if valid_rate < 0.6:       # <= 2 of 5 valid (60%+ failure rate)
        conf_label = "low"
    elif valid_rate < 0.8:     # 3 of 5 valid (40% failure rate)
        conf_label = "medium" if base_conf == "high" else "low"
    else:
        conf_label = base_conf

    if agreement < 0.6:
        return VerdictResult(
            outcome="NO_OPINION",
            confidence="low",
            agreement_rate=agreement,
            why=f"Judge split: {dict(tally)}. No majority outcome (< 60% agreement).",
            open_questions=_merge_open_questions(votes),
            vote_tally=dict(tally),
            valid_votes=valid_count,
            total_votes=total_attempts,
            agree_count=k,
        )

    winning_votes = [v for v in votes if v.outcome == outcome]
    best = winning_votes[0]

    _STATUTE_LAW_RE = re.compile(r'^(IPC|BNS|BNSS|CRPC|CrPC|BSA|IEA|POCSO|DPA|DAAIN)\s+\d', re.IGNORECASE)
    _CASE_CITE_RE = re.compile(r'(\b\d{4}\s+INSC\b|\bv\.\s|\bv\b\s+[A-Z])', re.IGNORECASE)

    raw_statutes: List[str] = []
    seen_statutes: set = set()
    raw_precedents: List[str] = []
    seen_precedents: set = set()

    for v in winning_votes:
        for law in v.laws_applied:
            law_clean = (law or "").strip()
            if not law_clean:
                continue
            if _CASE_CITE_RE.search(law_clean):
                if law_clean.lower() not in seen_precedents:
                    seen_precedents.add(law_clean.lower())
                    raw_precedents.append(law_clean)
            elif _STATUTE_LAW_RE.match(law_clean):
                if law_clean.lower() not in seen_statutes:
                    seen_statutes.add(law_clean.lower())
                    raw_statutes.append(law_clean)

    # Detect legal regime from statutes: if old code (CrPC/IPC) is present, filter out accidental new code (BNSS/BNS)
    has_old = any(s.upper().startswith(("IPC", "CRPC")) for s in raw_statutes)
    has_new = any(s.upper().startswith(("BNS", "BNSS")) for s in raw_statutes)
    statutes: List[str] = []
    for s in raw_statutes:
        if has_old and not has_new and s.upper().startswith(("BNS", "BNSS")):
            continue
        if has_old and s.upper().startswith(("BNS", "BNSS")) and any(s.upper().startswith(("IPC", "CRPC")) for s in raw_statutes):
            # Old code proceedings (e.g. 2020-2023): purge BNSS/BNS
            continue
        statutes.append(s)

    # Deduplicate and consolidate case names & citations so case is not listed twice
    clean_precedents: List[str] = []
    case_names = [p for p in raw_precedents if " v" in p.lower() or " vs" in p.lower()]
    citations = [p for p in raw_precedents if re.search(r'\b\d{4}\s+INSC\b', p, re.IGNORECASE)]

    if case_names and citations:
        # Combine: e.g. "Srikant Upadhyay v. State of Bihar (2024 INSC 202)"
        c_cite = citations[0]
        c_name = case_names[0]
        if c_cite.lower() in c_name.lower():
            clean_precedents.append(c_name)
        else:
            clean_precedents.append(f"{c_name} ({c_cite})")
    elif case_names:
        clean_precedents.extend(case_names)
    elif citations:
        clean_precedents.extend(citations)
    else:
        clean_precedents = raw_precedents

    # Collect holding IDs from best winning vote
    holdings_relied = sorted({hid for fac in best.factors for hid in fac.holding_ids if hid})
    facts_relied = sorted({fid for fac in best.factors for fid in fac.fact_ids if fid})

    # Clean explanation of template lines like "No critical factual gap prevents decision"
    explanation = best.raw_explanation
    explanation = re.sub(r'No critical factual gap prevents decision[,.]?\s*', '', explanation, flags=re.IGNORECASE).strip()
    
    # Grounding appendix
    oq_list = _merge_open_questions(winning_votes)
    oq_text = f"Open Questions: {', '.join(oq_list)}" if oq_list else "Open Questions: None (factual record complete)"
    grounding_info = f"\n\n[Record Basis: Facts relied on: {', '.join(facts_relied) or 'record'}; Holdings relied on: {', '.join(holdings_relied) or 'general ratio'}; {oq_text}]"
    final_why = explanation + grounding_info

    # All laws for backward compat
    all_laws = statutes + clean_precedents

    return VerdictResult(
        outcome=outcome,
        confidence=conf_label,
        agreement_rate=agreement,
        why=final_why,
        laws_applied=all_laws,
        statutes=statutes,
        precedents=clean_precedents,
        holdings_relied=holdings_relied,
        factors=best.factors,
        open_questions=oq_list,
        vote_tally=dict(tally),
        valid_votes=valid_count,
        total_votes=total_attempts,
        agree_count=k,
    )



# -- Judge prompt & LLM call ---------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """\
You are deciding an anticipatory bail application under Section 438 CrPC / Section 482 BNSS.
You are NOT deciding guilt.

Outcomes (choose exactly one):
  GRANTED    -- bail allowed with conditions (weak prima facie case, cooperation shown, no flight/tampering risk)
  DENIED     -- application rejected (absconding, Section 82 proclamation, custodial interrogation indispensable)
  NO_OPINION -- record is insufficient to decide (critical facts absent -- warrants, cooperation, injury details)
  INTERIM    -- urgent interim protection pending police status report / case diary

ANTI-ESCAPE-HATCH: Use NO_OPINION ONLY if open_questions could genuinely change the outcome.
If facts and holdings give a clear answer, choose GRANTED or DENIED.

Apply a retrieved holding ONLY if its stated conditions are met by the facts.
If a holding's conditions cannot be checked from the facts, list it in open_questions.

CRITICAL JUDICIAL ORDER REQUIREMENTS:
1. Absconding and Precedent Exceptions:
   If considering refusal under Srikant Upadhyay / Section 82 CrPC (proclamation/absconding), you MUST explicitly evaluate whether the case falls within the narrow Paragraph 24 exception ("extreme, exceptional cases" where warrant or proclamation was issued without jurisdiction or as malicious abuse of process) and explain why the case does or does not fall within that exception.
2. Individual Roles of Appellants / Co-Accused:
   In an anticipatory bail order, you MUST address the individual roles of specific applicants/appellants (distinguish specific overt acts alleged in the FIR/record against individual appellants versus general allegations or acts of non-appellants).
3. Merits vs Process:
   Defense arguments concerning absence of forensic or medical proof go to trial-stage merits; they do NOT answer or cure non-appearance and defiance of process under Section 82.
4. No Template Cliches:
   Do NOT use template phrases such as "No critical factual gap prevents decision". Explicitly set out any open questions in "open_questions" (or leave it empty if none), and cite the specific fact IDs and holding IDs relied upon.
5. Legal Regime:
   For proceedings arising from offences or cases filed before July 1, 2024, apply IPC and CrPC (e.g. Section 438 CrPC, not BNSS).

Respond in this EXACT JSON format (no markdown, no prose outside the JSON):

{
  "outcome": "GRANTED|DENIED|NO_OPINION|INTERIM",
  "factors": [
    {
      "finding": "<one sentence judicial finding addressing specific accused role and holding condition>",
      "fact_ids": ["fact_1", "fact_2"],
      "holding_ids": ["srikant_para23"]
    }
  ],
  "open_questions": ["<question if outcome is NO_OPINION or holding condition unverifiable>"],
  "laws_applied": ["CrPC 438", "CrPC 82", "IPC 174", "2024 INSC 202"],
  "raw_explanation": "<3-5 sentences summarising the decision, including analysis of the Paragraph 24 exception and individual applicants' roles>"
}
"""


def _build_user_prompt(
    facts,
    holdings,
    prosecution_args,
    defense_args,
    accused_history,
    relevant_laws,
    evidence_inventory,
) -> str:
    from agents.judge.judge import _format_facts_block, _format_laws_block
    try:
        from agents.lexigraph.holding_retrieval import format_holdings_for_prompt
    except ImportError:
        def format_holdings_for_prompt(h):
            return json.dumps(h, indent=2)

    facts_block = _format_facts_block(facts)
    laws_block = _format_laws_block(relevant_laws) if relevant_laws else "No statutory provisions retrieved."
    holdings_block = format_holdings_for_prompt(holdings) if holdings else "No holdings retrieved."
    inv_str = json.dumps(evidence_inventory, indent=2) if evidence_inventory else "No formal inventory."

    accused_block = ""
    if accused_history:
        accused_block = (
            "\n\n[SIMULATED ACCUSED TESTIMONY - UNVERIFIED SIMULATION]:\n"
            "(Note: This testimony is generated by a simulation agent. Concessions or statements here "
            "do NOT constitute verified evidence on record and must not be used to establish factual ingredients.)\n"
            + "\n".join(f"Round {i+1}: {t}" for i, t in enumerate(accused_history))
        )

    return (
        f"FACTS (cite by id in your factors):\n{facts_block}\n\n"
        f"EVIDENCE INVENTORY:\n{inv_str}\n\n"
        f"APPLICABLE LAWS:\n{laws_block}\n\n"
        f"APPLICABLE PRECEDENT HOLDINGS (cite by id in your factors):\n{holdings_block}\n\n"
        f"PROSECUTION ARGUMENTS:\n{prosecution_args}\n\n"
        f"DEFENSE ARGUMENTS:\n{defense_args}{accused_block}\n\n"
        f"Now output your JSON verdict."
    )


def _parse_vote(raw_text: str) -> Optional[JudgeVote]:
    """Parse LLM JSON output into a JudgeVote. Returns None on failure."""
    try:
        text = raw_text.strip()
        m = re.search(r"`(?:json)?\s*(\{[\s\S]*?\})\s*`", text)
        if m:
            text = m.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                text = text[start:end+1]

        data = json.loads(text)

        factors = []
        for fac in data.get("factors", []):
            factors.append(Factor(
                finding=fac.get("finding", ""),
                fact_ids=fac.get("fact_ids", []),
                holding_ids=fac.get("holding_ids", []),
            ))

        raw_outcome = str(data.get("outcome", "NO_OPINION")).upper().strip()
        if "INTERIM" in raw_outcome:
            outcome = "INTERIM"
        elif "NO_OPINION" in raw_outcome or "NO OPINION" in raw_outcome:
            outcome = "NO_OPINION"
        elif "GRANT" in raw_outcome or "ALLOW" in raw_outcome:
            outcome = "GRANTED"
        elif "DENI" in raw_outcome or "REJECT" in raw_outcome or "DISMISS" in raw_outcome:
            outcome = "DENIED"
        else:
            outcome = "NO_OPINION"

        return JudgeVote(
            outcome=outcome,
            factors=factors,
            open_questions=data.get("open_questions", []),
            laws_applied=data.get("laws_applied", []),
            raw_explanation=data.get("raw_explanation", ""),
        )
    except Exception:
        return None


# -- Public API ----------------------------------------------------------------

def decide(
    facts,
    holdings,
    prosecution_args: str,
    defense_args: str,
    accused_history,
    llm,
    relevant_laws=None,
    evidence_inventory=None,
    n: int = 5,
    canonical_case_file: Optional[str] = None,
) -> VerdictResult:
    """
    n-shot voting judge with prompt caching.

    1. Uses canonical case file at prefix 0 for instant prefix-cache reuse across all n calls.
    2. Calls LLM n times (majority voting).
    3. Validates each vote structurally.
    4. Aggregates by majority.
    """
    from agents.orchestrator.case_file import build_canonical_case_file, format_cached_messages

    fact_ids: set = set()
    for f in facts:
        fid = getattr(f, "id", f.get("id", None) if isinstance(f, dict) else None)
        if fid:
            fact_ids.add(str(fid))

    holding_ids: set = set()
    for h in (holdings or []):
        hid = h.get("id") if isinstance(h, dict) else getattr(h, "id", None)
        if hid:
            holding_ids.add(str(hid))

    case_file_block = canonical_case_file or build_canonical_case_file(
        case_facts=facts,
        evidence_inventory=evidence_inventory,
        lexigraph_output={"ipc_sections": relevant_laws or []},
        holdings=holdings,
    )

    accused_block = ""
    if accused_history:
        accused_block = (
            "\n\n[SIMULATED ACCUSED TESTIMONY - UNVERIFIED SIMULATION]:\n"
            "(Note: This testimony is generated by a simulation agent. Concessions or statements here "
            "do NOT constitute verified evidence on record and must not be used to establish factual ingredients.)\n"
            + "\n".join(f"Round {i+1}: {t}" for i, t in enumerate(accused_history))
        )

    dynamic_user_prompt = (
        f"PROSECUTION ARGUMENTS:\n{prosecution_args}\n\n"
        f"DEFENSE ARGUMENTS:\n{defense_args}{accused_block}\n\n"
        f"Now output your JSON verdict."
    )

    messages = format_cached_messages(
        canonical_case_file=case_file_block,
        role_instruction=_JUDGE_SYSTEM_PROMPT,
        dynamic_turn_content=dynamic_user_prompt,
    )

    votes: List[JudgeVote] = []
    for i in range(n):
        try:
            response = llm.invoke(messages)
            raw = response.content if hasattr(response, "content") else str(response)
            vote = _parse_vote(raw)
            if vote is None:
                print(f"[VotingJudge] Vote {i+1}/{n}: parse failure (malformed JSON) -- skipping.")
                continue
            is_valid, reason = validate(vote, fact_ids, holding_ids)
            if not is_valid:
                print(f"[VotingJudge] Vote {i+1}/{n}: validation failed (outcome={vote.outcome}) [{reason}] -- skipping.")
                continue
            print(f"[VotingJudge] Vote {i+1}/{n}: grounded -> {vote.outcome}")
            votes.append(vote)
        except Exception as exc:
            print(f"[VotingJudge] Vote {i+1}/{n}: LLM error -- {exc}")

    result = aggregate(votes, total_attempts=n)
    valid_count = len(votes)
    print(
        f"[VotingJudge] Tally={result.vote_tally} -> {result.outcome} "
        f"({valid_count}/{n} valid, {result.agree_count}/{valid_count if valid_count else 1} agree, confidence={result.confidence})"
    )
    return result
