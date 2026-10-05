import json
import re

from config.llm_config import get_llm
from agents.lexigraph import format_for_prompt
from agents.orchestrator.formatting import (
    extract_citations_with_act,
    extract_evidence_references,
    format_argument_markdown,
    link_facts_to_text,
    parse_argument_structure,
)


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
    defense_arguments (formatted in unified moot court schema)
    """

    def __init__(self):
        self.llm = get_llm(temperature=0.2)

    def generate(
        self,
        structured_facts: dict,
        lexigraph_result: dict,
        prosecution_arguments: str,
        evidence_inventory: list = None,
        case_facts: list = None,
    ) -> str:

        retrieved_laws = format_for_prompt(lexigraph_result)
        inv_str = json.dumps(evidence_inventory, indent=2) if evidence_inventory else "No formal inventory; rely on case facts."

        if case_facts:
            facts_lines = []
            for i, f in enumerate(case_facts):
                fid = getattr(f, "id", f.get("id", f"fact_{i+1}") if isinstance(f, dict) else f"fact_{i+1}")
                txt = getattr(f, "text", f.get("text", f.get("value", "")) if isinstance(f, dict) else str(f))
                src = getattr(f, "source", f.get("source", "record") if isinstance(f, dict) else "record")
                facts_lines.append(f"[{fid}] {txt} (Source: {src})")
            facts_display = "\n".join(facts_lines)
        else:
            facts_display = json.dumps(structured_facts, indent=2)

        prompt = f"""
You are an experienced Indian Criminal Defense Lawyer.

Your objective is NOT to prove innocence.

Instead:

• Challenge weaknesses in the prosecution.
• Highlight evidentiary gaps, procedural lapses, and contradictions.
• Explain where intention (mens rea) is not established.
• Raise reasonable doubt.
• Use ONLY the IPC/BNS sections and precedents retrieved from LexiGraph. Include the Act name with every section citation (e.g. "IPC 324", "CrPC 438").
• Reference specific evidence facts by their fact ID tag (e.g. [fact_1], [fact_3]).
• Never invent legal precedents or facts (names, dates, injuries, weapons).

CRITICAL ADVOCACY RULES ON EVIDENCE AND RECORD:
1. CHECK GAPS STRICTLY AGAINST THE EVIDENCE INVENTORY:
   - You may ONLY argue that an item is absent if it is explicitly marked 'not_on_record' in the EVIDENCE INVENTORY (or completely omitted from the case facts).
   - If an item is marked 'present' in the inventory (e.g., eyewitnesses, recovered weapon, identified complainant/victim), you are STRICTLY FORBIDDEN from claiming or implying it is missing, unrecovered, or absent from the record.
   - For items marked 'present', your legal duty is to challenge weight, credibility, interested witness bias, or lack of independent corroboration — NEVER deny their existence.
2. PRECISE PROCEDURAL PHRASING FOR GAPS:
   - When pointing out missing documents or unproduced records (e.g. lack of MLC/medical report or CCTV), you MUST phrase your submission strictly as:
     "The record before the court does not contain..." or "The prosecution has failed to produce on record..."
   - That is legitimate defense advocacy and not factual fabrication.
3. NEVER INVENT ABSENCE OF COMPLAINANT / VICTIM:
   - If the victim/complainant is identified in the facts (e.g. Suresh Gupta), do NOT claim there is no complainant or that no complaint was made.
4. DO NOT INVENT WEAPONS OR CONFLICTING FACTS:
   - Never introduce fabricated firearms, injuries, or non-existent third parties.

------------------------
CASE FACTS (WITH FACT IDS)
------------------------

{facts_display}

------------------------
EVIDENCE INVENTORY (RECORD STATUS)
------------------------

{inv_str}

------------------------
PROSECUTION ARGUMENTS
------------------------

{prosecution_arguments}

------------------------
LEXIGRAPH RETRIEVAL
------------------------

{retrieved_laws}

Return your response strictly as valid JSON matching this schema:
{{
  "theory": "<concise defense theory, e.g. lack of premeditation, mutual altercation, or uncorroborated recovery>",
  "arguments": [
    "<submission 1 challenging prosecution or noting procedural gap with reference to [fact_N]>",
    "<submission 2 on missing record, framed strictly as 'The record before the court does not contain...'>",
    "<submission 3 on statutory ingredients / absence of requisite mens rea under cited sections>"
  ],
  "evidence_refs": ["fact_1", "fact_3"],
  "sections": ["IPC 324", "CrPC 438"]
}}
"""

        response = self.llm.invoke(prompt)
        parsed = parse_argument_structure(response.content)

        facts_lookup = {}
        if case_facts:
            facts_lookup = {
                str(getattr(f, "id", f.get("id", f"fact_{i+1}") if isinstance(f, dict) else f"fact_{i+1}")).lower():
                    str(getattr(f, "text", f.get("text", f.get("value", "")) if isinstance(f, dict) else str(f)))
                for i, f in enumerate(case_facts)
            }

        theory = parsed.get("theory") or "Defense submits reasonable doubt and lack of established ingredients."
        arguments = parsed.get("arguments", [])
        evidence_refs = parsed.get("evidence_refs", [])
        if not evidence_refs and case_facts:
            evidence_refs = link_facts_to_text(response.content, case_facts)
        sections = parsed.get("sections", [])
        if not sections:
            sections = extract_citations_with_act(response.content)

        return format_argument_markdown(
            theory=theory,
            arguments=arguments,
            evidence_refs=evidence_refs,
            sections=sections,
            facts_lookup=facts_lookup,
        )



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