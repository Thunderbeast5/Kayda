"""
Prosecutor Agent — MootCourt Simulator
Powered by Groq (llama-3.3-70b-versatile).

Receives structured case facts from the Orchestrator, calls Groq to build
a formal Indian prosecution argument mapped to IPC sections.
"""

import grok_client

_SYSTEM = """You are a senior Public Prosecutor in an Indian High Court.
Your job is to build a strong, formal prosecution argument based on the facts provided.

Your argument MUST:
1. Clearly state the charges against the accused with specific IPC section numbers.
2. Map each piece of evidence to the relevant IPC section.
3. Establish mens rea (criminal intent) and actus reus (criminal act).
4. Address the burden of proof — explain why the evidence is sufficient.
5. Cite the applicable punishment under each IPC section.
6. Be structured in formal legal language with numbered points.

Do NOT fabricate evidence. Work strictly with what is provided.
End with a clear statement: "The prosecution submits that the accused is GUILTY of [charges]."
"""


class ProsecutorAgent:
    def __init__(self):
        self.name = "Prosecutor"
        self.role = "Prosecution"

    def respond(self, query: str) -> str:
        """
        Generates a Groq-powered prosecution argument.

        Args:
            query: Formatted case facts string from the Orchestrator.

        Returns:
            Formal prosecution argument as a string.
        """
        return grok_client.chat(
            input_text=(
                f"Build a formal prosecution argument for the following case:\n\n{query}"
            ),
            system_prompt=_SYSTEM,
            temperature=0.3,
            max_output_tokens=1500,
        )
