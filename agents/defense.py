"""
Defense Agent — MootCourt Simulator
Powered by Groq (llama-3.3-70b-versatile).

Receives case facts and the prosecution's argument, then builds a counter-narrative
identifying legal gaps, challenging evidence, and citing mitigating IPC provisions.
"""

import grok_client

_SYSTEM = """You are a senior Defense Lawyer in an Indian High Court.
Your job is to challenge the prosecution's case and defend the accused.

Your argument MUST:
1. Challenge the prosecution's evidence — identify gaps, assumptions, or lack of proof.
2. Question the establishment of mens rea (criminal intent) — was intent truly proven?
3. Cite mitigating IPC sections, exceptions, or relevant precedents that favor the accused.
4. Highlight any procedural violations or rights of the accused.
5. Present an alternative narrative consistent with innocence or reduced culpability.
6. Be structured in formal legal language with numbered points.

Do NOT fabricate evidence. Work strictly with the facts provided.
End with a clear statement: "The defense submits that the accused is NOT GUILTY / deserves acquittal because [reason]."
"""


class DefenseAgent:
    def __init__(self):
        self.name = "Defense Lawyer"
        self.role = "Defense"

    def respond(self, query: str, prosecution_args: str = "") -> str:
        """
        Generates a Groq-powered defense argument.

        Args:
            query:            Formatted case facts string from the Orchestrator.
            prosecution_args: The prosecution's argument to counter.

        Returns:
            Formal defense argument as a string.
        """
        user_input = f"Case facts:\n{query}"
        if prosecution_args:
            user_input += f"\n\nProsecution's argument to counter:\n{prosecution_args}"
        user_input += "\n\nBuild a formal defense argument."

        return grok_client.chat(
            input_text=user_input,
            system_prompt=_SYSTEM,
            temperature=0.4,
            max_output_tokens=1500,
        )
