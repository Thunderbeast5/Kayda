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

Max debate rounds: 2  (prevents infinite loops)
"""

import json
import re

from llm_config import get_llm

# If prosecution total score is below this, Judge asks Accused for clarification
SUFFICIENCY_THRESHOLD = 15   # out of 30


# ── helpers ───────────────────────────────────────────────────────────────────

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


def _parse_verdict(text: str) -> dict:
    """
    Extract structured verdict from the LLM's final verdict response.
    Returns a dict with: decision, laws_applied, confidence, explanation.
    """
    lower = text.lower()

    # Decision
    if "not guilty" in lower:
        decision = "Not Guilty"
    elif "guilty" in lower:
        decision = "Guilty"
    else:
        decision = "Inconclusive"

    # Confidence — look for "confidence: 82%" or "82 percent" etc.
    conf_match = re.search(r"confidence[:\s]+(\d+)\s*%?", lower)
    confidence = int(conf_match.group(1)) if conf_match else 50

    # IPC sections cited — look for "IPC 379", "Section 302" etc.
    laws = list(set(re.findall(r"(?:ipc\s*|section\s*)(\d+[a-z]?)", lower)))

    return {
        "decision":     decision,
        "laws_applied": laws,
        "confidence":   confidence,
        "explanation":  text.strip(),
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
    ) -> tuple[dict, str]:
        """
        Score both arguments and decide if a clarification question is needed.

        Returns
        -------
        scores   : dict  — {prosecution: {...}, defense: {...}}
        question : str   — non-empty only when prosecution total < SUFFICIENCY_THRESHOLD
        """
        prompt = f"""
You are the Honourable Judge presiding over an Indian criminal court.

Your task is to SCORE the prosecution and defense arguments independently.
Do NOT decide the verdict yet.

Score each argument on three axes, each out of 10:
  • Legal Validity   (are the cited IPC sections correctly applied?)
  • Evidence Linkage (do the facts map to the legal claim?)
  • Logic Coherence  (is the argument internally consistent?)

------------------------
CASE FACTS
------------------------
{json.dumps(structured_facts, indent=2)}

------------------------
PROSECUTION ARGUMENTS
------------------------
{prosecution_args}

------------------------
DEFENSE ARGUMENTS
------------------------
{defense_args}

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
QUESTION FOR ACCUSED (only if SUFFICIENCY is NO): <one precise factual question>
"""

        response = self.llm.invoke(prompt)
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

    # ── pass 2: verdict ───────────────────────────────────────────────────────

    def verdict(
        self,
        structured_facts: dict,
        prosecution_args: str,
        defense_args: str,
        accused_history: list[str],
        judge_scores: dict,
    ) -> dict:
        """
        Deliver the final verdict after all arguments (and any Accused testimony)
        have been heard.

        Returns
        -------
        verdict_object : dict — {decision, laws_applied, confidence, explanation}
        """
        testimony_block = ""
        if accused_history:
            testimony_block = "\n------------------------\nACCUSED TESTIMONY\n------------------------\n"
            for i, t in enumerate(accused_history, 1):
                testimony_block += f"\nRound {i}:\n{t}\n"

        score_summary = ""
        if judge_scores:
            p = judge_scores.get("prosecution", {})
            d = judge_scores.get("defense", {})
            score_summary = (
                f"\nPrevious scoring summary:\n"
                f"  Prosecution — Legal: {p.get('legal_validity',0)}, "
                f"Evidence: {p.get('evidence_linkage',0)}, "
                f"Logic: {p.get('logic_coherence',0)}, "
                f"Total: {p.get('total',0)}/30\n"
                f"  Defense     — Legal: {d.get('legal_validity',0)}, "
                f"Evidence: {d.get('evidence_linkage',0)}, "
                f"Logic: {d.get('logic_coherence',0)}, "
                f"Total: {d.get('total',0)}/30\n"
            )

        prompt = f"""
You are the Honourable Judge presiding over an Indian criminal court.

You have heard all arguments and testimony. Now deliver the FINAL VERDICT.

------------------------
CASE FACTS
------------------------
{json.dumps(structured_facts, indent=2)}

------------------------
PROSECUTION ARGUMENTS
------------------------
{prosecution_args}

------------------------
DEFENSE ARGUMENTS
------------------------
{defense_args}
{testimony_block}
{score_summary}

Deliver your verdict in this EXACT format:

VERDICT: <Guilty / Not Guilty>

CONFIDENCE: <percentage, e.g. 78%>

LAWS APPLIED:
<List each IPC section you are relying on, one per line, e.g. IPC 379>

EXPLANATION:
<3–5 paragraphs. Explain your reasoning, how you weighed the evidence,
which argument was stronger, and why you arrived at this verdict.
Cite specific facts and IPC sections. Be precise and impartial.>
"""

        response = self.llm.invoke(prompt)
        return _parse_verdict(response.content)


# ── LangGraph node wrappers ───────────────────────────────────────────────────

_judge_agent = None


def _get_judge() -> JudgeAgent:
    global _judge_agent
    if _judge_agent is None:
        _judge_agent = JudgeAgent()
    return _judge_agent


def judge_score_node(state: dict) -> dict:
    """
    LangGraph node — scoring pass.
    Reads prosecution_args + defense_args, writes judge_scores + judge_question.
    Routing: orchestrator checks state['judge_question'] to decide next node.
    """
    judge = _get_judge()

    scores, question = judge.score(
        structured_facts  = state.get("structured_facts", {}),
        prosecution_args  = state.get("prosecution_args", ""),
        defense_args      = state.get("defense_args", ""),
    )

    state["judge_scores"]   = scores
    state["judge_question"] = question

    p = scores["prosecution"]
    d = scores["defense"]
    print(
        f"[Judge] Scoring done. "
        f"Prosecution: {p['total']}/30  |  Defense: {d['total']}/30"
    )
    if question:
        print(f"[Judge] Evidence insufficient — asking Accused: '{question}'")

    return state


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
    )

    state["judge_verdict"] = verdict
    print(
        f"[Judge] Verdict: {verdict['decision']}  "
        f"(confidence {verdict['confidence']}%)"
    )
    return state


def should_ask_accused(state: dict) -> str:
    """
    LangGraph conditional edge function.
    Returns "needs_accused" or "verdict" based on judge_question and debate_round.
    """
    MAX_ROUNDS = 2
    question   = state.get("judge_question", "")
    rounds     = state.get("debate_round", 0)

    if question and rounds < MAX_ROUNDS:
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
