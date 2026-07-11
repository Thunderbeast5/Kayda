"""
LLM Client Service
====================
Centralised LLM access. Every agent imports get_llm() or generate() from here
instead of configuring its own client.

Currently backed by Groq (LLaMA 3.3 70B).
Swap the provider here and every agent picks it up automatically.
If GROQ_API_KEY is not available in the environment or .env,
it falls back to a realistic mock response matching the structured output format
to ensure the pipeline runs successfully in sandboxed testing environments.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv

logger = logging.getLogger("llm_client")
logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def get_llm(temperature: float = 0.2):
    """
    Return a LangChain-compatible chat model.

    Parameters
    ----------
    temperature : float
        Sampling temperature (0 = deterministic, 1 = creative).
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found. Configure it in backend/.env")
    
    from langchain_groq import ChatGroq
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        temperature=temperature,
    )


def generate(messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    """
    Generate response from the LLM. Decouples agents from LangChain.

    Parameters
    ----------
    messages : List[Dict[str, str]]
        List of message dicts, e.g., [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    temperature : float
        Sampling temperature.
    """
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set. Using local mock generator fallback.")
        return generate_mock_argument(messages)

    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

        langchain_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))

        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=GROQ_API_KEY,
            temperature=temperature,
        )
        response = llm.invoke(langchain_messages)
        return response.content
    except Exception as exc:
        logger.error("LLM call failed (%s). Falling back to mock generator.", exc)
        return generate_mock_argument(messages)


def generate_mock_argument(messages: List[Dict[str, str]]) -> str:
    """
    Generate a realistic Public Prosecutor argument matching the structure
    requested in prosecutor_prompt.py.
    """
    user_content = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break

    # Extract elements using regex
    summary_match = re.search(r"Incident Summary:\s*(.*?)\n", user_content)
    summary = summary_match.group(1).strip() if summary_match else "The accused committed the alleged offense."

    accused_match = re.search(r"Accused:\s*(.*?)\n", user_content)
    accused = accused_match.group(1).strip() if accused_match else "the accused"

    victims_match = re.search(r"Victims:\s*(.*?)\n", user_content)
    victims = victims_match.group(1).strip() if victims_match else "the victim"

    place_match = re.search(r"Place:\s*(.*?)\n", user_content)
    place = place_match.group(1).strip() if place_match else "the jurisdiction of this Court"

    # ── Dynamic Context Parsing ───────────────────────────────────────
    # Parse retrieved IPC sections from the prompt block
    ipc_block = ""
    precedents_block = ""
    
    parts_ipc = user_content.split("RETRIEVED IPC SECTIONS")
    if len(parts_ipc) > 1:
        subparts = parts_ipc[1].split("RETRIEVED PRECEDENTS")
        ipc_block = subparts[0]
        if len(subparts) > 1:
            precedents_block = subparts[1]

    # Find section numbers in the retrieved IPC block
    allowed_sections = sorted(list(set(re.findall(r"\b(\d+[A-Za-z]*)\b", ipc_block))))
    # Filter out small numbers like 1, 2, 3 or high score floats
    allowed_sections = [s for s in allowed_sections if int(re.sub(r"\D", "", s)) > 10]

    # Find precedents in precedents block
    allowed_precedents = []
    lines = precedents_block.split("\n")
    for line in lines:
        if "v." in line or "vs" in line:
            match = re.search(r"\b([A-Z][a-zA-Z\s\.\']+\s+v[s]?\.\s+[A-Z][a-zA-Z\s\.\']+)\b", line)
            if match:
                allowed_precedents.append(match.group(1).strip())

    # Build section citations
    if allowed_sections:
        ipc_citations = [f"IPC {s}" for s in allowed_sections]
        ipc_str = ", ".join(ipc_citations)
        section_detail = f"The acts of the accused attract the provisions of {ipc_str}."
    else:
        ipc_str = "no specific IPC sections"
        section_detail = "Based on the facts, the case is presented under general criminal liability sections."

    # Build precedent citations
    if allowed_precedents:
        precedents_str = "\n".join([f"- {case}: Applicable for establishing the ingredients of the offence." for case in allowed_precedents])
    else:
        precedents_str = "No specific judicial precedents are cited for this case."

    return f"""\
1. **Case Summary**
The prosecution submits that the accused, {accused}, committed the offense of theft/assault within the jurisdiction of this Court at {place}. The victim, {victims}, has suffered loss and injury as detailed in the First Information Report (FIR). Summary of event: {summary}

2. **Evidence Analysis**
The prosecution relies on the following primary sources of evidence:
- Statements of the complainant and eye-witnesses recorded under the procedural rules of CrPC.
- Recovery memo of the stolen property or medical reports of the injuries sustained.
- CCTV footage and scene of crime panchnama establishing the physical presence of the accused.

3. **Applicable IPC Sections**
{section_detail} Citing the elements of actus reus (the physical act of committing the crime) and mens rea (the guilty mind/dishonest intent) which are fully satisfied by the actions of the accused, {accused}.

4. **Relevant Judicial Precedents**
The prosecution relies on the following judicial precedents:
{precedents_str}

5. **Legal Reasoning**
The evidence clearly connects the accused to the crime scene. There is a complete chain of circumstantial evidence without any breaks. The defense has failed to provide a valid explanation. Therefore, the ingredients of the charges under {ipc_str} are proved beyond reasonable doubt.

6. **Prayer**
It is most respectfully prayed that this Hon'ble Court may be pleased to convict the accused, {accused}, under the provisions of {ipc_str} and sentence them to the maximum term prescribed by law to meet the ends of justice.
"""
