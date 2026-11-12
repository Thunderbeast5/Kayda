"""
Sprint 6: Accused Agent
========================
Simulates the defendant's testimony in response to the Judge's question.

Key behaviours
--------------
1. Loads prior testimony from Redis (session memory) so responses stay consistent.
2. Generates a response using the LLM constrained by the ground-truth case facts.
3. Consistency guardrail — if the generated answer contradicts a known fact,
   the LLM is asked to regenerate (up to MAX_RETRIES times).
4. Saves the new testimony back to Redis for future rounds.
5. Appends the testimony to AgentState['accused_history'].

Redis is optional — if unavailable the agent degrades gracefully and uses
only the in-memory accused_history from AgentState.
"""

import json
import os
import re
from typing import Any

from config.llm_config import get_llm

MAX_RETRIES = 3   # max regeneration attempts for the consistency guardrail


_redis_client = None
_redis_checked = False

def _get_redis():
    """Return a Redis client or None if Redis is not reachable (memoized with fast timeout)."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    try:
        import redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            r = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
            )
        else:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", 6379))
            r = redis.Redis(
                host=host,
                port=port,
                decode_responses=True,
                socket_connect_timeout=0.3,
                socket_timeout=0.3,
            )
        r.ping()
        _redis_client = r
    except Exception:
        _redis_client = None
    _redis_checked = True
    return _redis_client


def _load_history_from_redis(session_id: str) -> list[str]:
    """Pull prior testimonies for this session from Redis."""
    r = _get_redis()
    if r is None:
        return []
    key  = f"accused:{session_id}:history"
    data = r.get(key)
    if data:
        try:
            return json.loads(data)
        except Exception:
            return []
    return []


def _save_history_to_redis(session_id: str, history: list[str]) -> None:
    """Persist updated testimony list to Redis (TTL: 24 h)."""
    r = _get_redis()
    if r is None:
        return
    key = f"accused:{session_id}:history"
    r.set(key, json.dumps(history), ex=86400)


# ── Consistency checker ───────────────────────────────────────────────────────

def _format_facts_for_accused(structured_facts: Any) -> str:
    if isinstance(structured_facts, list):
        lines = []
        for i, f in enumerate(structured_facts):
            fid = getattr(f, "id", f.get("id", f"fact_{i+1}") if isinstance(f, dict) else f"fact_{i+1}")
            txt = getattr(f, "text", f.get("text", f.get("value", str(f))) if isinstance(f, dict) else str(f))
            src = getattr(f, "source", f.get("source", "record") if isinstance(f, dict) else "record")
            lines.append(f"[{fid}] {txt} (Source: {src})")
        return "\n".join(lines) if lines else "No specific facts on record."
    elif isinstance(structured_facts, dict):
        return json.dumps(structured_facts, indent=2)
    return str(structured_facts)


def _is_consistent(
    llm,
    testimony: str,
    structured_facts: dict,
    prior_history: list[str],
) -> tuple[bool, str]:
    """
    Ask the LLM to check whether the new testimony contradicts:
      a) the ground-truth facts in structured_facts, OR
      b) any of the accused's prior statements.

    Returns (is_consistent: bool, reason: str).
    """
    history_block = ""
    if prior_history:
        history_block = "Prior statements by the accused:\n" + "\n".join(
            f"  - {h}" for h in prior_history
        )
    facts_str = _format_facts_for_accused(structured_facts)

    prompt = f"""
You are a legal consistency checker.

Ground-truth facts established in the case:
{facts_str}

{history_block}

New testimony by the accused:
"{testimony}"

Does this new testimony CONTRADICT any ground-truth fact or a prior statement?

Answer in EXACTLY this format:
CONSISTENT: <YES or NO>
REASON: <one sentence explaining why, or "No contradiction found.">
"""

    response = llm.invoke(prompt)
    text     = response.content.lower()

    consistent = "consistent: yes" in text

    reason_match = re.search(r"reason\s*:\s*(.+?)(?:\n|$)", response.content, re.IGNORECASE)
    reason = reason_match.group(1).strip() if reason_match else ""

    return consistent, reason


# ── AccusedAgent ──────────────────────────────────────────────────────────────

class AccusedAgent:
    """
    Accused Agent — generates testimony and enforces consistency.

    Usage
    -----
    agent = AccusedAgent()
    testimony = agent.respond(
        session_id        = "abc123",
        question          = "Did you intend to steal the motorcycle?",
        structured_facts  = {...},
        prior_history     = [...],   # pass state['accused_history']
    )
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.4)   # slight creativity for human-like answers

    def respond(
        self,
        session_id:       str,
        question:         str,
        structured_facts: dict,
        prior_history:    list[str] | None = None,
    ) -> str:
        """
        Generate a testimony response that is consistent with the facts and
        prior statements.  Returns the final testimony string.
        """
        # 1. Load history — Redis first, fall back to in-memory
        redis_history = _load_history_from_redis(session_id)
        history = list(set((prior_history or []) + redis_history))

        history_block = ""
        if history:
            history_block = (
                "\nYour prior statements (you MUST NOT contradict these):\n"
                + "\n".join(f"  - {h}" for h in history)
            )

        # 2. Generate testimony (with retry loop for consistency)
        testimony = ""
        for attempt in range(1, MAX_RETRIES + 1):
            prompt = f"""
You are the accused in an Indian criminal court case.
Answer the Judge's question truthfully and consistently.

Rules:
• Your answer MUST align with the established case facts.
• Do NOT contradict your prior statements.
• Speak in first person, in plain simple English.
• Keep the answer to 2–4 sentences.
• Do NOT make up new facts that contradict the case record.

------------------------
CASE FACTS (ground truth)
------------------------
{_format_facts_for_accused(structured_facts)}
{history_block}

------------------------
JUDGE'S QUESTION
------------------------
{question}

Your response:
"""
            response  = self.llm.invoke(prompt)
            testimony = response.content.strip()

            # 3. Consistency guardrail
            consistent, reason = _is_consistent(
                self.llm, testimony, structured_facts, history
            )

            if consistent:
                break

            print(
                f"[Accused] Attempt {attempt}: inconsistency detected — {reason}. "
                f"Regenerating…"
            )
            if attempt == MAX_RETRIES:
                # Last resort: force a neutral, fact-safe response
                print("[Accused] Max retries reached. Using safe fallback response.")
                testimony = (
                    "I respect the court. I wish to state that I did not intend "
                    "to cause any harm or commit any offence. I request the court "
                    "to consider the full facts before reaching a conclusion."
                )

        # 4. Persist updated history
        updated_history = history + [testimony]
        _save_history_to_redis(session_id, updated_history)

        return testimony


# ── LangGraph node wrapper ────────────────────────────────────────────────────

_accused_agent = None


def _get_accused() -> AccusedAgent:
    global _accused_agent
    if _accused_agent is None:
        _accused_agent = AccusedAgent()
    return _accused_agent


def accused_node(state: dict) -> dict:
    """
    LangGraph node.
    Reads judge_question, generates testimony, appends to accused_history,
    increments debate_round, clears judge_question so the next routing
    check can re-evaluate.
    """
    agent = _get_accused()

    testimony = agent.respond(
        session_id       = state.get("session_id", "default"),
        question         = state.get("judge_question", ""),
        structured_facts = state.get("structured_facts", {}),
        prior_history    = state.get("accused_history", []),
    )

    history = list(state.get("accused_history", [])) + [testimony]
    rounds  = state.get("debate_round", 0) + 1

    state["accused_history"] = history
    state["debate_round"]    = rounds
    state["judge_question"]  = ""   # cleared — Judge will re-score next

    print(f"[Accused] Round {rounds} testimony recorded.")
    return state


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":

    agent = AccusedAgent()

    facts = {
        "who":      {"complainant": "Amit Kumar", "accused": ["Rahul Sharma"]},
        "incident": {
            "summary": "Accused took a motorcycle parked outside a shop without owner's consent.",
            "date": "05/07/2026", "place": "Pune",
        },
        "sections": ["IPC 379"],
    }

    question = "Did you have the intent to permanently deprive the owner of the motorcycle?"

    print("=" * 70)
    print(f"Question: {question}")
    print("=" * 70)

    testimony = agent.respond(
        session_id       = "test_session_001",
        question         = question,
        structured_facts = facts,
        prior_history    = [],
    )

    print(f"\nTestimony:\n{testimony}")

    # Second round — test consistency enforcement
    print("\n" + "=" * 70)
    print("Round 2 — follow-up question")
    print("=" * 70)

    question2 = "You said the motorcycle was abandoned. But it was parked for only 10 minutes — how do you explain that?"

    testimony2 = agent.respond(
        session_id       = "test_session_001",
        question         = question2,
        structured_facts = facts,
        prior_history    = [testimony],
    )

    print(f"\nTestimony:\n{testimony2}")
