"""
Orchestrator Agent — MootCourt Simulator
=========================================
The central brain of the system. Uses Groq (llama-3.3-70b-versatile) as its
reasoning engine to:

  1. Understand the incoming case / query and classify intent.
  2. Extract structured facts (who, what, when, where).
  3. Manage the full courtroom simulation loop:
       Prosecutor → Defense (parallel) → Judge
       └─ Judge ──(needs clarification?)──► Accused ──► Judge (verdict)
  4. Return a structured verdict with full debate transcript.

All LLM calls go through grok_client.py (Groq API).
"""

import json
import uuid
import os
from pathlib import Path
from typing import TypedDict, Optional
from dotenv import load_dotenv

import grok_client
import lexigraph
from prosecutor import ProsecutorAgent
from accused import AccusedAgent

# Load env
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ── State schema ──────────────────────────────────────────────────────────────

class CourtSession(TypedDict):
    session_id: str
    raw_input: str                        # original user text / file path
    intent: str                           # what the orchestrator thinks the user wants
    case_facts: dict                      # structured facts from Evidence Analyzer
    prosecutor_arguments: str
    defense_arguments: str
    accused_testimonies: list
    judge_questions: list
    final_verdict: dict
    debate_transcript: list               # full log of every agent turn
    routing_decision: str                 # which sub-flow was triggered


# ── System prompts ────────────────────────────────────────────────────────────

_ORCHESTRATOR_SYSTEM = """
You are the Orchestrator of an Indian MootCourt simulation system.
Your job is to analyse the user's input and decide how to proceed.

You must reply ONLY with valid JSON in this exact shape:
{
  "intent": "<one of: FULL_SIMULATION | PROSECUTOR_ONLY | DEFENSE_ONLY | JUDGE_QUERY | EVIDENCE_QUERY | GENERAL_LEGAL_QUESTION>",
  "routing_decision": "<brief reason for your choice>",
  "extracted_facts": {
    "accused": "<name or 'Unknown'>",
    "crime": "<crime description or 'Unknown'>",
    "when": "<date/time or 'Unknown'>",
    "where": "<location or 'Unknown'>",
    "amount": "<monetary value or 'N/A'>",
    "ipc_hint": "<most likely IPC section or crime type if obvious, else null>"
  },
  "instructions_for_agents": {
    "prosecutor": "<what the prosecutor should focus on>",
    "defense": "<what the defense should focus on>",
    "judge": "<scoring criteria or special instructions>"
  }
}

Intent guide:
- FULL_SIMULATION   : User submitted a full case / FIR / evidence. Run complete trial.
- PROSECUTOR_ONLY   : User specifically asks for prosecution arguments only.
- DEFENSE_ONLY      : User wants defense arguments only.
- JUDGE_QUERY       : User wants a judicial opinion or verdict on given arguments.
- EVIDENCE_QUERY    : User wants IPC sections / laws for a described crime.
- GENERAL_LEGAL_QUESTION : General Indian law question, no simulation needed.
"""

_VERDICT_SUMMARIZER_SYSTEM = """
You are the Chief Justice of the Indian Supreme Court acting as a final summarizer.
Given a complete debate transcript, produce a concise, authoritative final verdict JSON:
{
  "decision": "Guilty | Not Guilty | Inconclusive",
  "confidence_percent": <0-100>,
  "ipc_sections_applied": ["IPC_XXX", ...],
  "key_reasoning": "<2-3 sentences>",
  "dissent_notes": "<any significant defense points that weakened the prosecution, or null>"
}
Reply ONLY with valid JSON.
"""


# ── Orchestrator class ────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    Master controller for the MootCourt simulation.
    Uses Grok-3 for intent classification, routing decisions,
    and final verdict synthesis.
    """

    def __init__(self):
        self.prosecutor = ProsecutorAgent()
        self.accused    = AccusedAgent()
        # DefenseAgent and JudgeAgent loaded dynamically (graceful fallback if missing)

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, user_input: str, session_id: str = None) -> dict:
        """
        Main entry point. Accepts a case description or free-form legal query.

        Returns:
            Full CourtSession dict with verdict and transcript.
        """
        session_id = session_id or str(uuid.uuid4())
        transcript = []

        # ── Step 1: Orchestrator LLM analyses the input ───────────────────────
        analysis = self._analyse_input(user_input, transcript)

        session: CourtSession = {
            "session_id": session_id,
            "raw_input": user_input,
            "intent": analysis.get("intent", "GENERAL_LEGAL_QUESTION"),
            "case_facts": analysis.get("extracted_facts", {}),
            "prosecutor_arguments": "",
            "defense_arguments": "",
            "accused_testimonies": [],
            "judge_questions": [],
            "final_verdict": {},
            "debate_transcript": transcript,
            "routing_decision": analysis.get("routing_decision", ""),
        }

        instructions = analysis.get("instructions_for_agents", {})

        # ── Step 2: Route to the correct sub-flow ─────────────────────────────
        intent = session["intent"]

        if intent == "FULL_SIMULATION":
            self._run_full_simulation(session, instructions)

        elif intent == "PROSECUTOR_ONLY":
            self._run_prosecutor_only(session, instructions)

        elif intent == "DEFENSE_ONLY":
            self._run_defense_only(session, instructions)

        elif intent == "JUDGE_QUERY":
            self._run_judge_query(session, instructions)

        elif intent == "EVIDENCE_QUERY":
            self._run_evidence_query(session)

        else:  # GENERAL_LEGAL_QUESTION
            self._run_general_query(session)

        return session

    # ── Convenience alias (backward-compatible with old server.py) ────────────

    def analyze_and_route(self, query: str) -> dict:
        """Legacy interface used by server.py."""
        result = self.run(query)

        # Determine the primary agent label based on intent
        intent = result.get("intent", "")
        if intent == "FULL_SIMULATION":
            agent = "Judge"  # final stage of a full simulation
        elif intent == "PROSECUTOR_ONLY":
            agent = "Prosecutor"
        elif intent == "DEFENSE_ONLY":
            agent = "Defense"
        elif intent == "EVIDENCE_QUERY":
            agent = "LexiGraph"
        elif intent == "GENERAL_LEGAL_QUESTION":
            agent = "LegalAdvisor"
        elif intent == "JUDGE_QUERY":
            agent = "Judge"
        else:
            agent = "Orchestrator"

        response_text = self._build_response_text(result)
        return {
            "agent": agent,
            "response": response_text,
            "original_query": query,
            "session_id": result["session_id"],
            "intent": intent,
            "verdict": result["final_verdict"],
            "transcript": result["debate_transcript"],
        }

    # ── Sub-flows ─────────────────────────────────────────────────────────────

    def _run_full_simulation(self, session: CourtSession, instructions: dict):
        """Full courtroom simulation: Prosecutor → Defense → Judge (→ Accused loop)."""
        facts = session["case_facts"]
        transcript = session["debate_transcript"]

        # -- Prosecutor
        p_args = self._call_prosecutor(facts, instructions.get("prosecutor", ""), transcript)
        session["prosecutor_arguments"] = p_args

        # -- Defense  (stub until DefenseAgent is implemented)
        d_args = self._call_defense(facts, p_args, instructions.get("defense", ""), transcript)
        session["defense_arguments"] = d_args

        # -- Judge loop (max 3 clarification rounds)
        verdict = self._judge_loop(session, instructions, max_rounds=3)
        session["final_verdict"] = verdict

    def _run_prosecutor_only(self, session: CourtSession, instructions: dict):
        facts = session["case_facts"]
        p_args = self._call_prosecutor(facts, instructions.get("prosecutor", ""), session["debate_transcript"])
        session["prosecutor_arguments"] = p_args
        session["final_verdict"] = {"note": "Prosecutor-only mode. No verdict issued."}

    def _run_defense_only(self, session: CourtSession, instructions: dict):
        facts = session["case_facts"]
        d_args = self._call_defense(facts, "", instructions.get("defense", ""), session["debate_transcript"])
        session["defense_arguments"] = d_args
        session["final_verdict"] = {"note": "Defense-only mode. No verdict issued."}

    def _run_judge_query(self, session: CourtSession, instructions: dict):
        # Judge evaluates whatever arguments were supplied in the raw input
        verdict = self._call_judge_direct(session["raw_input"], instructions, session["debate_transcript"])
        session["final_verdict"] = verdict

    def _run_evidence_query(self, session: CourtSession):
        """Ask Grok which IPC sections apply to the described crime."""
        answer = self._grok_ipc_lookup(session["case_facts"], session["debate_transcript"])
        session["final_verdict"] = {"ipc_sections": answer}

    def _run_general_query(self, session: CourtSession):
        """Answer a general Indian law question directly using Grok."""
        answer = self._grok_general_answer(session["raw_input"], session["debate_transcript"])
        session["final_verdict"] = {"answer": answer}

    # ── Agent callers ─────────────────────────────────────────────────────────

    def _call_prosecutor(self, facts: dict, instruction: str, transcript: list) -> str:
        """Calls ProsecutorAgent with facts dict — LexiGraph runs inside the agent."""
        query = self._facts_to_query(facts, instruction)
        response = self.prosecutor.respond(query, facts=facts)
        transcript.append({"role": "Prosecutor", "content": response})
        return response

    def _call_defense(self, facts: dict, prosecution_args: str, instruction: str, transcript: list) -> str:
        """Calls DefenseAgent with facts dict — LexiGraph runs inside the agent."""
        try:
            from defense import DefenseAgent
            defense = DefenseAgent()
            query = self._facts_to_query(facts, instruction)
            response = defense.respond(query, prosecution_args, facts=facts)
        except ImportError:
            query = self._facts_to_query(facts, instruction)
            retrieval = lexigraph.retrieve(
                query_text=f"defense exception mitigation {query}",
                crime_type=facts.get("crime", ""),
                section_hint=facts.get("ipc_hint"),
            )
            retrieved_laws = lexigraph.format_for_prompt(retrieval)
            response = grok_client.chat(
                input_text=(
                    f"Case facts: {query}\n\n{retrieved_laws}\n\n"
                    f"Prosecution arguments:\n{prosecution_args}\n\n"
                    "Write a structured defense argument using ONLY the retrieved IPC sections."
                ),
                system_prompt=(
                    "You are a senior Indian defense lawyer. Challenge the prosecution, "
                    "cite only the retrieved IPC sections, be formal and specific."
                ),
                temperature=0.4,
            )
        transcript.append({"role": "Defense", "content": response})
        return response

    def _judge_loop(self, session: CourtSession, instructions: dict, max_rounds: int = 3) -> dict:
        """
        Runs the Judge → (optional Accused clarification) → Judge loop.
        Returns the final verdict dict.
        """
        transcript      = session["debate_transcript"]
        judge_instruction = instructions.get("judge", "")
        rounds          = 0

        while rounds < max_rounds:
            rounds += 1
            judgment = self._call_judge(session, judge_instruction, transcript)

            # If judge needs clarification, trigger Accused
            if judgment.get("needs_clarification"):
                question = judgment.get("clarification_question", "Please clarify your actions.")
                session["judge_questions"].append(question)
                transcript.append({"role": "Judge", "content": f"[Needs clarification] {question}"})

                testimony = self._call_accused(question, session, transcript)
                session["accused_testimonies"].append(testimony)
                # Loop again with the new testimony in transcript
            else:
                # Final verdict reached
                transcript.append({"role": "Judge", "content": json.dumps(judgment)})
                return judgment

        # Max rounds hit — synthesize verdict from full transcript
        return self._synthesize_final_verdict(transcript)

    def _call_judge(self, session: CourtSession, instruction: str, transcript: list) -> dict:
        """
        Judge evaluates both arguments and returns a structured decision.
        Falls back to Grok stub if JudgeAgent not yet implemented.
        """
        try:
            from judge import JudgeAgent
            judge = JudgeAgent()
            return judge.evaluate(
                session["prosecutor_arguments"],
                session["defense_arguments"],
                session["case_facts"],
            )
        except ImportError:
            user_input = (
                f"Case facts: {json.dumps(session['case_facts'])}\n\n"
                f"Prosecution:\n{session['prosecutor_arguments']}\n\n"
                f"Defense:\n{session['defense_arguments']}\n\n"
                + (f"Accused testimony: {session['accused_testimonies']}\n\n" if session['accused_testimonies'] else "")
                + f"Special instruction: {instruction}"
            )
            raw = grok_client.chat_json(
                input_text=user_input,
                system_prompt=(
                    "You are a strict, impartial judge of the Indian High Court. "
                    "Evaluate the prosecution and defense arguments. "
                    "Score each on Legal Validity (0-10), Evidence Linkage (0-10), "
                    "and Logic Coherence (0-10). "
                    "If you need a clarification from the accused, set needs_clarification=true. "
                    "Reply ONLY with valid JSON:\n"
                    '{"prosecution_score":{"legal_validity":0,"evidence_linkage":0,"logic":0},'
                    '"defense_score":{"legal_validity":0,"evidence_linkage":0,"logic":0},'
                    '"needs_clarification":false,"clarification_question":null,'
                    '"decision":"Guilty | Not Guilty | Inconclusive",'
                    '"confidence_percent":0,"ipc_sections_applied":[],"reasoning":""}'
                ),
                temperature=0.2,
                max_output_tokens=1024,
            )
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"decision": "Inconclusive", "reasoning": raw, "needs_clarification": False}

    def _call_judge_direct(self, raw_input: str, instructions: dict, transcript: list) -> dict:
        """Judge evaluates raw arguments passed directly by the user."""
        raw = grok_client.chat_json(
            input_text=raw_input,
            system_prompt=(
                "You are a strict Indian High Court judge. "
                "Evaluate the arguments below and issue a verdict as JSON with keys: "
                "decision, confidence_percent, ipc_sections_applied, reasoning."
            ),
            temperature=0.2,
        )
        transcript.append({"role": "Judge", "content": raw})
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"decision": "Inconclusive", "reasoning": raw}

    def _call_accused(self, question: str, session: CourtSession, transcript: list) -> str:
        """Calls AccusedAgent with Judge's question and full prior testimony history."""
        response = self.accused.respond(
            query=question,
            prior_testimony=session["accused_testimonies"],  # pass history for consistency check
        )
        transcript.append({"role": "Accused", "content": response})
        return response

    def _grok_ipc_lookup(self, facts: dict, transcript: list) -> str:
        """Retrieves IPC sections from Neo4j + Pinecone, then asks Groq to explain them."""
        query_text = self._facts_to_query(facts, "")

        # ── Real DB retrieval first ───────────────────────────────────────────
        retrieval = lexigraph.retrieve(
            query_text=query_text,
            crime_type=facts.get("crime", ""),
            section_hint=facts.get("ipc_hint"),
        )
        retrieved_laws = lexigraph.format_for_prompt(retrieval)
        transcript.append({"role": "LexiGraph[Neo4j+Pinecone]", "content": retrieved_laws})

        # ── Groq explains / summarizes the retrieved sections ─────────────────
        if retrieval["ipc_sections"]:
            answer = grok_client.chat(
                input_text=(
                    f"Crime facts: {query_text}\n\n"
                    f"{retrieved_laws}\n\n"
                    "Explain which of these retrieved IPC sections apply to this crime "
                    "and why. Be concise and accurate."
                ),
                system_prompt=(
                    "You are an expert in Indian Penal Code. "
                    "You have been given VERIFIED IPC sections from a legal database. "
                    "Explain their applicability. Do NOT invent new sections."
                ),
                temperature=0.1,
            )
        else:
            answer = grok_client.chat(
                input_text=f"Crime facts: {json.dumps(facts)}",
                system_prompt=(
                    "You are an expert in Indian Penal Code. "
                    "The database returned no results. Based on your knowledge, "
                    "list applicable IPC sections. Be accurate."
                ),
                temperature=0.1,
            )

        transcript.append({"role": "LexiGraph/Groq", "content": answer})
        return answer

    def _grok_general_answer(self, query: str, transcript: list) -> str:
        answer = grok_client.chat(
            input_text=query,
            system_prompt=(
                "You are a senior Indian legal expert with deep knowledge of IPC, CrPC, CPC, "
                "Evidence Act, and constitutional law. Answer clearly and accurately."
            ),
            temperature=0.3,
        )
        transcript.append({"role": "LegalAdvisor/Grok", "content": answer})
        return answer

    def _synthesize_final_verdict(self, transcript: list) -> dict:
        """Fallback: asks Grok to synthesize a verdict from the full transcript."""
        transcript_text = "\n\n".join(
            f"[{t['role']}]: {t['content']}" for t in transcript
        )
        raw = grok_client.chat_json(
            input_text=transcript_text,
            system_prompt=_VERDICT_SUMMARIZER_SYSTEM,
            temperature=0.2,
            max_output_tokens=512,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"decision": "Inconclusive", "reasoning": raw}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _analyse_input(self, user_input: str, transcript: list) -> dict:
        """Sends the raw input to Grok for intent classification and fact extraction."""
        raw = grok_client.chat_json(
            input_text=user_input,
            system_prompt=_ORCHESTRATOR_SYSTEM,
            temperature=0.1,
            max_output_tokens=800,
        )
        transcript.append({"role": "Orchestrator", "content": raw})
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "intent": "GENERAL_LEGAL_QUESTION",
                "routing_decision": "JSON parse failed — defaulting to general query",
                "extracted_facts": {},
                "instructions_for_agents": {},
            }

    def _facts_to_query(self, facts: dict, extra_instruction: str) -> str:
        parts = []
        if facts.get("accused"):    parts.append(f"Accused: {facts['accused']}")
        if facts.get("crime"):      parts.append(f"Crime: {facts['crime']}")
        if facts.get("when"):       parts.append(f"When: {facts['when']}")
        if facts.get("where"):      parts.append(f"Where: {facts['where']}")
        if facts.get("ipc_hint"):   parts.append(f"Suspected IPC: {facts['ipc_hint']}")
        if extra_instruction:       parts.append(f"Instruction: {extra_instruction}")
        return " | ".join(parts) if parts else "General case — extract from context."

    def _build_response_text(self, result: dict) -> str:
        """Builds a human-readable summary for the legacy API interface."""
        sections = []
        if result.get("prosecutor_arguments"):
            sections.append(f"[PROSECUTOR]\n{result['prosecutor_arguments']}")
        if result.get("defense_arguments"):
            sections.append(f"[DEFENSE]\n{result['defense_arguments']}")
        if result.get("final_verdict"):
            verdict = result["final_verdict"]
            if isinstance(verdict, dict):
                decision = verdict.get("decision") or verdict.get("answer") or verdict.get("ipc_sections", "")
                reasoning = verdict.get("reasoning") or verdict.get("key_reasoning", "")
                sections.append(f"[VERDICT]\n{decision}\n{reasoning}")
            else:
                sections.append(f"[VERDICT]\n{verdict}")
        return "\n\n".join(sections) if sections else "Query processed. See transcript for details."


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    orch = OrchestratorAgent()

    # Quick connectivity / import check — avoids firing real API calls
    if "--check" in sys.argv:
        print("[Orchestrator] Import check passed.")
        sys.exit(0)

    test_cases = [
        # Full simulation
        "Rahul Kumar, a 28-year-old shopkeeper, was arrested on 12th March 2024 in Mumbai "
        "for allegedly stealing ₹50,000 worth of electronics from his employer's store. "
        "CCTV footage shows him carrying goods after working hours.",

        # Evidence query
        "What IPC sections apply to someone who sends threatening messages via WhatsApp?",

        # General legal question
        "What is the difference between IPC 302 and IPC 304?",
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {case[:80]}...")
        print('='*60)
        result = orch.analyze_and_route(case)
        print(f"Intent   : {result.get('intent', 'unknown')}")
        print(f"Agent    : {result['agent']}")
        print(f"Session  : {result['session_id']}")
        print(f"Response :\n{result['response'][:800]}")
