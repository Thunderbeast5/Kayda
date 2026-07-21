import json

from config.llm_config import get_llm
from backend.agents.lexigraph.lexigraph import format_for_prompt


class DefenseAgent:
    """
    Defense Lawyer Agent

    Inputs
    ------
    structured_facts
    lexigraph_result
    prosecution_arguments

    Output
    ------
    defense_arguments
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.2)

    def generate(
        self,
        structured_facts: dict,
        lexigraph_result: dict,
        prosecution_arguments: str,
    ) -> str:

        retrieved_laws = format_for_prompt(lexigraph_result)

        prompt = f"""
You are an experienced Indian Criminal Defense Lawyer.

Your objective is NOT to prove innocence.

Instead:

• Challenge weaknesses in the prosecution.
• Highlight missing evidence.
• Identify contradictions.
• Point out procedural lapses.
• Explain where intention (mens rea) is not established.
• Raise reasonable doubt.
• Use ONLY the IPC sections and precedents retrieved from LexiGraph.
• Never invent legal precedents.
• If retrieval is insufficient, explicitly state that.

------------------------
CASE FACTS
------------------------

{json.dumps(structured_facts, indent=2)}

------------------------
PROSECUTION ARGUMENTS
------------------------

{prosecution_arguments}

------------------------
LEXIGRAPH RETRIEVAL
------------------------

{retrieved_laws}

Prepare the response in this format:

1. Defense Theory

2. Weaknesses in Prosecution

3. Contradictions in Evidence

4. Missing Evidence

5. Mitigating Circumstances

6. Relevant IPC Sections

7. Final Defense Submission

Keep the arguments professional and courtroom ready.
"""

        response = self.llm.invoke(prompt)
        return response.content


# -------------------------------------------------------------------
# Standalone Test
# -------------------------------------------------------------------

if __name__ == "__main__":

    agent = DefenseAgent()

    structured_facts = {
        "who": {
            "complainant": "Amit",
            "accused": ["Rahul"],
            "victims": ["Amit"]
        },
        "incident": {
            "summary": "Rahul allegedly stole a motorcycle.",
            "date": "05/07/2026",
            "time": "14:30",
            "place": "Pune"
        },
        "sections": ["IPC 379"]
    }

    lexigraph_result = {
        "ipc_sections": [
            {
                "section": "379",
                "description": "Theft",
                "punishment": "3 years",
                "offense": "Theft",
                "source": "neo4j",
                "score": 1.0
            }
        ],
        "keywords": ["theft"],
        "neo4j_count": 1,
        "pinecone_count": 0,
        "query_used": "Motorcycle theft",
        "rewritten": False,
    }

    prosecution_arguments = """
The accused dishonestly removed the motorcycle without the owner's consent.
The prosecution relies on witness testimony and CCTV footage.
"""

    result = agent.generate(
        structured_facts=structured_facts,
        lexigraph_result=lexigraph_result,
        prosecution_arguments=prosecution_arguments,
    )

    print("\n" + "=" * 80)
    print("DEFENSE ARGUMENTS")
    print("=" * 80)
    print(result)