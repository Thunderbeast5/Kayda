"""
Sprint 6: Judge Agent
=====================
Evaluates prosecution vs defense arguments, scores them on three axes,
decides guilty/not-guilty, and — when evidence is insufficient — raises
a targeted question for the Accused agent before delivering a final verdict.

Scoring axes (each 0–10):
  • Legal Validity   — are the cited IPC sections correctly applied?
  • Evidence Linkage — do the facts support the legal claim?
  • Logic Coherence  — is the argument internally consistent?

Routing logic (used by orchestrator_graph.py):
  total_prosecution_score < SUFFICIENCY_THRESHOLD  →  "needs_accused"
  otherwise                                         →  "verdict"

Max debate rounds: configurable via ORCHESTRATOR_MAX_ROUNDS (default 2)
"""

import os
import json
import re
from typing import Any, List

from config.llm_config import get_llm

try:
    from agents.lexigraph.holding_retrieval import format_holdings_for_prompt
except ImportError:
    def format_holdings_for_prompt(holdings):
        return json.dumps(holdings, indent=2)

# If prosecution total score is below this, Judge asks Accused for clarification
SUFFICIENCY_THRESHOLD = float(os.getenv("JUDGE_TOTAL_SUFFICIENCY_THRESHOLD", os.getenv("JUDGE_SUFFICIENCY_THRESHOLD", "15.0")))

# Number of LLM votes per verdict call (set via env or default 5)
VOTE_COUNT = int(os.getenv("JUDGE_VOTE_COUNT", "5"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_laws_block(relevant_laws: list) -> str:
    """Format verified LexiGraph laws into a prompt-ready bulleted list."""
    if not relevant_laws:
        return "No specific statutory provisions retrieved."
    lines = []
    for item in relevant_laws:
        if isinstance(item, dict):
            sec = item.get("section", "")
            desc = item.get("description", "") or ""
            pun = item.get("punishment", "") or ""
            line = f"• IPC Section {sec}: {desc.strip()}"
            if pun and str(pun).strip().lower() not in ("nan", "(not specified)", ""):
                line += f" [Punishment: {pun.strip()}]"
            lines.append(line)
        elif isinstance(item, str):
            lines.append(f"• {item}")
    return "\n".join(lines) if lines else "No specific statutory provisions retrieved."


def _format_facts_block(structured_facts: Any) -> str:
    """Format facts into a readable list with ID, text, and source."""
    if isinstance(structured_facts, list):
        lines = []
        for i, f in enumerate(structured_facts):
            fid = getattr(f, "id", f.get("id", f"fact_{i+1}") if isinstance(f, dict) else f"fact_{i+1}")
            txt = getattr(f, "text", f.get("text", f.get("value", str(f))) if isinstance(f, dict) else str(f))
            src = getattr(f, "source", f.get("source", "record") if isinstance(f, dict) else "record")
            lines.append(f"• [{fid}] {txt} (Source: {src})")
        return "\n".join(lines) if lines else "No specific facts extracted."
    elif isinstance(structured_facts, dict):
        return json.dumps(structured_facts, indent=2)
    return str(structured_facts)


def _parse_scores(text: str) -> dict:
    """
    Extract numeric scores from the LLM's scoring response.
    Expects lines like:
        Legal Validity: 7
        Evidence Linkage: 6
        Logic Coherence: 8
    Falls back to 0 if a score cannot be parsed.
    """
    axes = ["legal_validity", "evidence_linkage", "logic_coherence"]
    patterns = {
        "legal_validity":   r"legal\s*validity\s*[:\-]\s*(\d+)",
        "evidence_linkage": r"evidence\s*linkage\s*[:\-]\s*(\d+)",
        "logic_coherence":  r"logic\s*coherence\s*[:\-]\s*(\d+)",
    }
    scores = {}
    lower = text.lower()
    for axis, pattern in patterns.items():
        m = re.search(pattern, lower)
        scores[axis] = int(m.group(1)) if m else 0
    scores["total"] = sum(scores[axis] for axis in axes)
    return scores


def _parse_verdict(text: str, verified_laws: list = None) -> dict:
    """
    Extract structured verdict from the LLM's final verdict response.
    Returns a dict with: decision, laws_applied, confidence, explanation.
    Validates laws_applied against verified legal provisions to prevent hallucination.
    """
    lower = text.lower()

    # Decision parsing: GRANTED | DENIED | NO_OPINION | INTERIM
    m_dec = re.search(r"(?:verdict|decision|order)\s*:\s*([a-z_\s]+)", lower)
    head = m_dec.group(1).strip() if m_dec else lower[:120]

    if "interim" in head:
        decision = "INTERIM"
    elif "no_opinion" in head or "no opinion" in head or "cannot decide" in head:
        decision = "NO_OPINION"
    elif "grant" in head or "allow" in head or "not guilty" in head:
        decision = "GRANTED"
    elif "deni" in head or "reject" in head or "dismiss" in head or "guilty" in head:
        decision = "DENIED"
    elif "interim" in lower:
        decision = "INTERIM"
    elif "no_opinion" in lower or "no opinion" in lower or "inconclusive" in lower:
        decision = "NO_OPINION"
    elif "granted" in lower or "allowed" in lower:
        decision = "GRANTED"
    elif "denied" in lower or "rejected" in lower:
        decision = "DENIED"
    else:
        decision = "NO_OPINION"


    # Confidence — look for "confidence: 82%" or "82 percent" etc.
    conf_match = re.search(r"confidence[:\s]+(\d+)\s*%?", lower)
    confidence = int(conf_match.group(1)) if conf_match else 50

    # IPC sections cited in the verdict text — look for "IPC 379", "Section 302" etc.
    cited_raw = list(set(re.findall(r"(?:ipc\s*|section\s*)(\d+[a-z]?)", lower)))

    # Anti-hallucination verification: collect known/verified section numbers
    verified_sections = set()
    if verified_laws:
        for law in verified_laws:
            if isinstance(law, dict) and law.get("section"):
                verified_sections.add(str(law["section"]).strip().lower())
            elif isinstance(law, str):
                s = re.search(r"\b(\d+[a-z]?)\b", law)
                if s:
                    verified_sections.add(s.group(1).lower())

    if verified_sections:
        # Prioritize cited sections that are verified in LexiGraph
        verified_cited = [s for s in cited_raw if s.lower() in verified_sections]
        laws = verified_cited if verified_cited else cited_raw
    else:
        laws = cited_raw

    # Extract only the actual explanation text after EXPLANATION: header
    explanation_match = re.search(r"(?:###\s*)?EXPLANATION\s*:\s*([\s\S]*)", text, re.IGNORECASE)
    if explanation_match:
        explanation = explanation_match.group(1).strip()
    else:
        # Fallback: strip leading VERDICT, CONFIDENCE, LAWS APPLIED headers
        cleaned = re.sub(
            r"^(?:\s*(?:VERDICT|CONFIDENCE|LAWS\s+APPLIED)[^\n]*\n*)+",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        ).strip()
        explanation = cleaned or text.strip()

    return {
        "decision":     decision,
        "laws_applied": laws,
        "confidence":   confidence,
        "explanation":  explanation,
    }



# ── JudgeAgent ────────────────────────────────────────────────────────────────

class JudgeAgent:
    """
    Judge Agent — evaluates and decides.

    Usage
    -----
    judge = JudgeAgent()

    # Scoring pass
    scores, question = judge.score(structured_facts, prosecution_args, defense_args)

    # Final verdict pass (call after Accused has responded, or directly if sufficient)
    verdict = judge.verdict(structured_facts, prosecution_args, defense_args,
                            accused_history)
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.1)   # low temp for consistent scoring

    # ── pass 1: score ─────────────────────────────────────────────────────────

    def score(
        self,
        structured_facts: dict,
        prosecution_args: str,
        defense_args: str,
        relevant_laws: list = None,
        evidence_inventory: list = None,
        holdings: list = None,
        canonical_case_file: Optional[str] = None,
    ) -> tuple[dict, str]:
        """
        Score both arguments independently against the facts, inventory, and retrieved precedent holdings.
        Uses prompt caching prefix with static case file placed at the very start.
        """
        from agents.orchestrator.case_file import build_canonical_case_file, format_cached_messages

        case_file_block = canonical_case_file or build_canonical_case_file(
            case_facts=structured_facts,
            evidence_inventory=evidence_inventory,
            lexigraph_output={"ipc_sections": relevant_laws or []},
            holdings=holdings,
        )

        role_instructions = """You are the Honourable Judge presiding over an Indian criminal court.

Your task is to SCORE the prosecution and defense arguments INDEPENDENTLY and IMPARTIALLY.
Do NOT decide the verdict yet.

Score each argument on three axes, each out of 10:
  • Legal Validity   (are the cited statutory sections and precedent holdings correctly applied?)
  • Evidence Linkage (do the assertions strictly map to the verified case facts and evidence inventory?)
  • Logic Coherence  (is the argument internally consistent and procedurally sound?)"""

        dynamic_turn_content = f"""------------------------
PROSECUTION ARGUMENTS
------------------------
{prosecution_args}

------------------------
DEFENSE ARGUMENTS
------------------------
{defense_args}

JUDICIAL SCORING CRITERIA:
1. PROSECUTION SCORING:
   - Check if prosecution proves statutory ingredients and correctly cites retrieved precedent holdings (e.g. Srikant Upadhyay on Section 82 proclamation / absconding, custodial necessity).
   - If prosecution claims grievous hurt or attempt to murder without supporting medical evidence on record, reduce Evidence Linkage accordingly.
   - CRITICAL: Simulated accused testimony is unverified simulation. Concessions or statements in simulated testimony must NEVER increase the prosecution's Evidence Linkage score beyond what is verified on the original case record.
2. DEFENSE SCORING:
   - Reward legitimate defense challenges regarding missing documents or absence of proof on record (e.g. "record does not show MLC/medical report", lack of premeditated intent, distinguishing precedent conditions).
   - NOTE ON MERITS VS PROCESS: Missing medical and forensic proof is a trial-stage merits point. It does NOT answer, cure, or counter Section 82 CrPC proclamation / absconding / defiance of process in an anticipatory bail application. Do not award high Legal Validity to defense arguments claiming lack of forensic proof answers a Section 82 proclamation bar.
   - PENALIZE Evidence Linkage heavily if the defense falsely asserts the absence of evidence that is explicitly marked 'present' in the inventory (e.g. falsely claiming no knife was recovered or no eyewitnesses were present).

Respond in EXACTLY this format (no extra text):

PROSECUTION SCORES:
Legal Validity: <0-10>
Evidence Linkage: <0-10>
Logic Coherence: <0-10>

DEFENSE SCORES:
Legal Validity: <0-10>
Evidence Linkage: <0-10>
Logic Coherence: <0-10>

SUFFICIENCY: <YES or NO>
QUESTION FOR ACCUSED (only if SUFFICIENCY is NO): <one precise factual question>"""

        messages = format_cached_messages(case_file_block, role_instructions, dynamic_turn_content)
        response = self.llm.invoke(messages)
        text     = response.content

        # Split prosecution / defense sections
        parts = text.lower().split("defense scores")
        pro_text = parts[0]
        def_text = parts[1] if len(parts) > 1 else ""

        prosecution_scores = _parse_scores(pro_text)
        defense_scores     = _parse_scores(def_text)

        scores = {
            "prosecution": prosecution_scores,
            "defense":     defense_scores,
        }

        # Extract sufficiency and question
        question = ""
        suf_match = re.search(r"sufficiency\s*:\s*(yes|no)", text.lower())
        sufficient = suf_match.group(1) == "yes" if suf_match else (
            prosecution_scores["total"] >= SUFFICIENCY_THRESHOLD
        )

        if not sufficient:
            q_match = re.search(
                r"question for accused.*?:\s*(.+?)(?:\n|$)", text, re.IGNORECASE
            )
            if q_match:
                question = q_match.group(1).strip()
            else:
                question = "Did the accused have the intent to commit the alleged offence?"

        return scores, question

    # -- pass 2: verdict (voting) -----------------------------------------------

    def verdict(
        self,
        structured_facts,
        prosecution_args: str,
        defense_args: str,
        accused_history,
        judge_scores: dict,
        relevant_laws=None,
        evidence_inventory=None,
        holdings=None,
        canonical_case_file: Optional[str] = None,
    ) -> dict:
        """
        Deliver the final verdict via n-shot majority voting.

        Calls voting.decide() which:
          1. Builds a structured prompt with facts + retrieved holdings.
          2. Calls the LLM JUDGE_VOTE_COUNT times (default 5, env: JUDGE_VOTE_COUNT).
          3. Validates each vote structurally (no invented citations, no
             escape-hatch NO_OPINION without justification).
          4. Aggregates by majority vote.

        Returns
        -------
        dict with keys: decision, confidence (0.0-1.0), confidence_label,
                        laws_applied, reasoning, factors, open_questions, vote_tally
        """
        from agents.judge.voting import decide

        # Normalise facts: if it is a list already, pass it; otherwise wrap or empty
        if isinstance(structured_facts, list):
            facts_list = structured_facts
        elif isinstance(structured_facts, dict):
            # Convert legacy dict-style facts into list
            facts_list = [{"id": k, "text": str(v), "source": "record"}
                          for k, v in structured_facts.items() if v]
        else:
            facts_list = []

        result = decide(
            facts=facts_list,
            holdings=holdings or [],
            prosecution_args=prosecution_args or "",
            defense_args=defense_args or "",
            accused_history=accused_history or [],
            llm=self.llm,
            relevant_laws=relevant_laws or [],
            evidence_inventory=evidence_inventory or [],
            n=VOTE_COUNT,
            canonical_case_file=canonical_case_file,
        )
        return result.to_dict()


def _get_judge() -> JudgeAgent:
    global _judge_agent
    if _judge_agent is None:
        _judge_agent = JudgeAgent()
    return _judge_agent


def judge_score_node(state: dict) -> dict:
    """
    LangGraph node — scoring pass.
    Reads prosecution_args + defense_args + relevant_laws, writes judge_scores + judge_question.
    Routing: orchestrator checks state['judge_question'] to decide next node.
    """
    judge = _get_judge()

    scores, question = judge.score(
        structured_facts  = state.get("structured_facts", {}),
        prosecution_args  = state.get("prosecution_args", ""),
        defense_args      = state.get("defense_args", ""),
        relevant_laws     = state.get("relevant_laws", []),
    )

    p = scores.get("prosecution", {})
    d = scores.get("defense", {})
    print(
        f"[Judge] Scoring complete — "
        f"Prosecution: {p.get('total', 0)}/30  |  Defense: {d.get('total', 0)}/30"
    )
    if question:
        print(f"[Judge] Clarification needed — questioning Accused: '{question}'")
    else:
        print("[Judge] Arguments sufficient — proceeding to Verdict.")

    return {
        "judge_scores": scores,
        "judge_question": question,
    }


def judge_verdict_node(state: dict) -> dict:
    """
    LangGraph node — final verdict pass.
    Writes judge_verdict into state.
    """
    judge = _get_judge()

    verdict = judge.verdict(
        structured_facts = state.get("structured_facts", {}),
        prosecution_args = state.get("prosecution_args", ""),
        defense_args     = state.get("defense_args", ""),
        accused_history  = state.get("accused_history", []),
        judge_scores     = state.get("judge_scores", {}),
        relevant_laws    = state.get("relevant_laws", []),
    )

    conf_str = str(verdict.get("confidence_label") or verdict.get("confidence") or "medium").upper()
    print(
        f"[Judge] Final Verdict: {verdict.get('decision', 'Inconclusive')} "
        f"(Confidence: {conf_str} | Laws Applied: {verdict.get('laws_applied', [])})"
    )
    return {"judge_verdict": verdict}


def should_ask_accused(state: dict) -> str:
    """
    LangGraph conditional edge function.
    Returns "needs_accused" or "verdict" based on judge_question and debate_round.
    Configurable via ORCHESTRATOR_MAX_ROUNDS (default 2).
    """
    max_rounds = int(os.getenv("ORCHESTRATOR_MAX_ROUNDS", "2"))
    question   = state.get("judge_question", "")
    rounds     = state.get("debate_round", 0)

    if question and rounds < max_rounds:
        return "needs_accused"
    return "verdict"


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":

    judge = JudgeAgent()

    facts = {
        "who":      {"complainant": "Amit Kumar", "accused": ["Rahul Sharma"], "victims": ["Amit Kumar"]},
        "incident": {"summary": "Accused stole a motorcycle from outside a shop.",
                     "date": "05/07/2026", "time": "14:30", "place": "Pune"},
        "sections": ["IPC 379"],
    }

    prosecution = """
1. The accused was identified on CCTV taking the motorcycle.
2. IPC Section 379 applies — dishonest removal of movable property.
3. No consent was given by the owner Amit Kumar.
4. The motorcycle was recovered from the accused's residence.
"""

    defense = """
1. The CCTV footage is of poor quality — identification is uncertain.
2. The accused claims he believed the motorcycle was abandoned.
3. No direct witness places the accused at the scene.
4. Mens rea (intent to steal) has not been established beyond reasonable doubt.
"""

    print("=" * 70)
    print("SCORING PASS")
    print("=" * 70)
    scores, question = judge.score(facts, prosecution, defense)
    print(f"Prosecution scores: {scores['prosecution']}")
    print(f"Defense scores:     {scores['defense']}")
    print(f"Question for Accused: {question or '(none — sufficient evidence)'}")

    accused_testimony = []
    if question:
        accused_testimony = [
            "I did not intend to steal the motorcycle. I thought it was abandoned "
            "as it had been parked there for three days with no lock."
        ]

    print("\n" + "=" * 70)
    print("VERDICT PASS")
    print("=" * 70)
    verdict = judge.verdict(facts, prosecution, defense, accused_testimony, scores)
    print(f"\nDecision:   {verdict['decision']}")
    print(f"Confidence: {verdict['confidence']}%")
    print(f"Laws:       IPC {', IPC '.join(verdict['laws_applied'])}")
    print(f"\nExplanation:\n{verdict['explanation']}")
