"""
Prosecutor Agent — MootCourt Simulator
=======================================
Workflow:
  1. Call LexiGraph → retrieve real IPC sections from Neo4j + Pinecone
  2. Inject retrieved laws into the Groq prompt
  3. Build formal prosecution argument grounded in actual database data
"""

import grok_client
import lexigraph

_SYSTEM = """You are a senior Public Prosecutor in an Indian High Court.
You have been provided with VERIFIED IPC sections retrieved directly from the
legal database (Neo4j graph + Pinecone vector search). You MUST base your
argument on these retrieved sections — do not invent or hallucinate IPC numbers.

Your argument MUST:
1. State the charges with the EXACT IPC section numbers provided in the retrieved data.
2. Map each piece of evidence to the relevant retrieved IPC section.
3. Establish mens rea (criminal intent) and actus reus (criminal act).
4. Address burden of proof — explain why the evidence meets the legal standard.
5. Cite the exact punishment from the retrieved data for each section.
6. Use formal legal language with numbered points.

End with: "The prosecution submits that the accused is GUILTY of [charges]."
"""


class ProsecutorAgent:
    def __init__(self):
        self.name = "Prosecutor"
        self.role = "Prosecution"

    def respond(self, query: str, facts: dict = None) -> str:
        """
        Builds a Groq-powered prosecution argument backed by real DB retrieval.

        Args:
            query: Formatted case facts string from the Orchestrator.
            facts: Structured facts dict for targeted Neo4j lookup (optional).

        Returns:
            Formal prosecution argument grounded in retrieved IPC sections.
        """
        facts = facts or {}

        # ── Step 1: Retrieve from Neo4j + Pinecone BEFORE calling LLM ────────
        retrieval = lexigraph.retrieve(
            query_text=query,
            crime_type=facts.get("crime", ""),
            section_hint=facts.get("ipc_hint"),
        )
        retrieved_laws = lexigraph.format_for_prompt(retrieval)

        # ── Step 2: Build grounded prompt ─────────────────────────────────────
        user_input = (
            f"CASE FACTS:\n{query}\n\n"
            f"{retrieved_laws}\n\n"
            "Using ONLY the IPC sections retrieved above, build a formal "
            "prosecution argument."
        )

        return grok_client.chat(
            input_text=user_input,
            system_prompt=_SYSTEM,
            temperature=0.3,
            max_output_tokens=1500,
        )
