"""
Accused Agent — MootCourt Simulator
Powered by Groq (llama-3.3-70b-versatile).

Simulates the defendant's testimony. Maintains consistency with prior statements
stored in the session — contradictions are caught and regenerated.
"""

import grok_client

_SYSTEM = """You are the accused (defendant) in an Indian courtroom.
You are responding to questions from the Judge or Defense lawyer.

Rules for your testimony:
1. Speak in first person — as the accused themselves.
2. Be consistent with any prior statements already made in this session.
3. Do NOT contradict established facts from the case (dates, locations, evidence).
4. You may deny guilt, provide an alibi, explain circumstances, or show remorse.
5. Keep the tone realistic — nervous, respectful, and human.
6. Do NOT use legal jargon — you are a common person, not a lawyer.
7. Keep the response to 3-5 sentences unless the question requires more detail.
"""

_CONSISTENCY_CHECK_SYSTEM = """You are a legal consistency checker.
Given prior testimony and a new statement, determine if they contradict each other.
Reply ONLY with valid JSON: {"contradicts": true/false, "reason": "explanation or null"}
"""


class AccusedAgent:
    def __init__(self):
        self.name = "Accused"
        self.role = "Defendant"

    def respond(self, query: str, prior_testimony: list[str] = None) -> str:
        """
        Generates a consistent testimony from the accused.

        Args:
            query:           The judge's or lawyer's question.
            prior_testimony: List of prior statements made in this session.

        Returns:
            Accused's testimony as a string.
        """
        prior_testimony = prior_testimony or []

        context = ""
        if prior_testimony:
            context = "Your prior statements in this session:\n"
            for i, stmt in enumerate(prior_testimony, 1):
                context += f"{i}. {stmt}\n"
            context += "\nYour new response must be consistent with the above.\n\n"

        response = grok_client.chat(
            input_text=f"{context}Judge/Lawyer's question: {query}\n\nYour testimony:",
            system_prompt=_SYSTEM,
            temperature=0.5,
            max_output_tokens=400,
        )

        # Consistency guardrail — only check if there are prior statements
        if prior_testimony:
            response = self._ensure_consistency(response, prior_testimony, query)

        return response

    def _ensure_consistency(
        self, new_response: str, prior_testimony: list[str], question: str, max_retries: int = 2
    ) -> str:
        """
        Checks if the new response contradicts prior statements.
        If it does, forces a regeneration up to max_retries times.
        """
        import json

        for attempt in range(max_retries):
            prior_text = "\n".join(f"- {s}" for s in prior_testimony)
            check_input = (
                f"Prior testimony:\n{prior_text}\n\n"
                f"New statement:\n{new_response}"
            )
            raw = grok_client.chat_json(
                input_text=check_input,
                system_prompt=_CONSISTENCY_CHECK_SYSTEM,
                temperature=0.1,
                max_output_tokens=150,
            )

            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                break  # Can't parse check — accept the response

            if not result.get("contradicts", False):
                break  # Consistent — accept it

            # Contradicts — regenerate with explicit correction instruction
            reason = result.get("reason", "")
            correction_note = (
                f"WARNING: Your previous answer contradicted your prior testimony. "
                f"Reason: {reason}. "
                f"Regenerate your answer being careful to stay consistent."
            )
            prior_context = "\n".join(f"{i+1}. {s}" for i, s in enumerate(prior_testimony))
            new_response = grok_client.chat(
                input_text=(
                    f"Prior statements:\n{prior_context}\n\n"
                    f"{correction_note}\n\n"
                    f"Question: {question}\n\nYour testimony:"
                ),
                system_prompt=_SYSTEM,
                temperature=0.4,
                max_output_tokens=400,
            )

        return new_response
