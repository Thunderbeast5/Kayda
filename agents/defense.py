"""
Defense Agent — MootCourt Simulator
=====================================
Workflow:
  1. Call LexiGraph → retrieve mitigating / exception IPC sections from Neo4j + Pinecone
  2. Inject retrieved laws into the Groq prompt
  3. Build formal defense argument challenging the prosecution
"""

import grok_client
import lexigraph

_SYSTEM = """You are a senior Defense Lawyer in an Indian High Court.
You have been provided with VERIFIED IPC sections retrieved directly from the
legal database (Neo4j graph + Pinecone vector search). Use these to challenge
the prosecution — find exceptions, mitigating provisions, and procedural flaws.

Your argument MUST:
1. Challenge the prosecution's evidence — identify gaps, missing proof, assumptions.
2. Question mens rea (criminal intent) — was intent conclusively proven?
3. Cite specific exceptions or mitigating IPC sections from the retrieved data.
4. Highlight any procedural violations or rights of the accused.
5. Present an alternative narrative consistent with innocence or reduced liability.
6. Use formal legal language with numbered points.

End with: "The defense submits that the accused is NOT GUILTY / deserves acquittal because [reason]."
"""


class DefenseAgent:
    def __init__(self):
        self.name = "Defense Lawyer"
        self.role = "Defense"

    def respond(self, query: str, prosecution_args: str = "", facts: dict = None) -> str:
        """
        Builds a Groq-powered defense argument backed by real DB retrieval.

        Args:
            query:            Formatted case facts string from the Orchestrator.
            prosecution_args: The prosecution's argument to counter.
            facts:            Structured facts dict for targeted Neo4j lookup.

        Returns:
            Formal defense argument grounded in retrieved IPC sections.
        """
        facts = facts or {}

        # ── Step 1: Retrieve from Neo4j + Pinecone BEFORE calling LLM ────────
        # Search for exceptions, mitigating sections, and same-crime sections
        defense_query = f"exception mitigation defense {query}"
        retrieval = lexigraph.retrieve(
            query_text=defense_query,
            crime_type=facts.get("crime", ""),
            section_hint=facts.get("ipc_hint"),
        )
        retrieved_laws = lexigraph.format_for_prompt(retrieval)

        # ── Step 2: Build grounded prompt ─────────────────────────────────────
        user_input = (
            f"CASE FACTS:\n{query}\n\n"
            f"{retrieved_laws}\n\n"
        )
        if prosecution_args:
            user_input += f"PROSECUTION'S ARGUMENT TO COUNTER:\n{prosecution_args}\n\n"

        user_input += (
            "Using the retrieved IPC sections above, build a formal defense argument "
            "that challenges the prosecution and protects the accused."
        )

        return grok_client.chat(
            input_text=user_input,
            system_prompt=_SYSTEM,
            temperature=0.4,
            max_output_tokens=1500,
        )
