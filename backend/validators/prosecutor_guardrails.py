"""
Prosecutor Guardrails
======================
Output validators for the Prosecutor agent.

Sprint 5 / Step 4 requirements:
  - Verify that the response is not empty.
  - Verify it follows the required legal structure:
      1. Case Summary
      2. Evidence Analysis
      3. Applicable IPC Sections
      4. Relevant Judicial Precedents
      5. Legal Reasoning
      6. Prayer (or Conclusion)
  - Verify it only cites IPC/BNS sections returned by LexiGraph.
  - Verify it only cites precedents provided in the retrieval context.
  - If validation fails, return structured errors and feedback.
"""

import re
from typing import List, Set, Tuple
from pydantic import BaseModel, Field


class GuardrailResult(BaseModel):
    """Structured validation results from the guardrails check."""

    is_valid: bool = Field(..., description="True if all checks pass.")
    errors: List[str] = Field(default_factory=list, description="List of failure descriptions.")
    feedback: str = Field(
        default="",
        description="Constructive feedback to append to the LLM retry prompt.",
    )


# Regex patterns for structure checks
REQUIRED_HEADERS = [
    (r"Case\s+Summary", "1. Case Summary"),
    (r"Evidence\s+Analysis", "2. Evidence Analysis"),
    (r"Applicable\s+(?:IPC|BNS)\s+Sections", "3. Applicable IPC Sections"),
    (r"Relevant\s+(?:Judicial\s+)?Precedents", "4. Relevant Judicial Precedents"),
    (r"Legal\s+Reasoning", "5. Legal Reasoning"),
    (r"Prayer|Conclusion", "6. Prayer"),
]

# Pattern to extract cited section numbers, e.g. "IPC 379" -> "379", "BNS 303" -> "303"
# Excludes general procedural citations like "Section 161" or "Section 164" of CrPC.
SECTION_NUMBER_PATTERN = re.compile(
    r"\b(?:IPC|BNS)\s*(\d+[A-Za-z]*)\b",
    re.IGNORECASE,
)

# Pattern to find case precedents in the text, e.g. "State of Maharashtra v. Rahul" or "Nanavati v. State"
CASE_CITATION_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z\s\.\']+\s+v[s]?\.\s+[A-Z][a-zA-Z\s\.\']+)\b"
)


def validate_draft_argument(
    text: str,
    valid_section_numbers: List[str],
    retrieved_precedents_text: str,
) -> GuardrailResult:
    """
    Validate the drafted prosecution argument.

    Parameters
    ----------
    text : str
        The raw LLM draft argument.
    valid_section_numbers : List[str]
        List of section numbers retrieved by LexiGraph, e.g. ['379', '411'].
    retrieved_precedents_text : str
        The precedents text that was passed in the user prompt.
    """
    errors = []

    # 1. Non-empty check
    if not text or not text.strip():
        return GuardrailResult(
            is_valid=False,
            errors=["Draft argument is empty."],
            feedback="The generated argument is empty. Please generate a full, structured prosecution argument.",
        )

    # 2. Structural Check (headers)
    for pattern, header_name in REQUIRED_HEADERS:
        if not re.search(pattern, text, re.IGNORECASE):
            errors.append(f"Missing required section: '{header_name}'")

    # 3. Citation Check (IPC/BNS sections)
    # Extract cited section numbers from draft
    cited_numbers = set(SECTION_NUMBER_PATTERN.findall(text))
    
    # Filter out empty or common false positives (like Section numbers from sections format itself)
    # Normalize valid numbers
    norm_valid_sections = {str(n).strip() for n in valid_section_numbers}

    invalid_sections = []
    for num in cited_numbers:
        # If the LLM cited a section not in retrieval, it fails (unless retrieval was empty, but even then LLM should state no laws apply)
        if num not in norm_valid_sections:
            invalid_sections.append(num)

    if invalid_sections:
        errors.append(
            f"Hallucinated or unretrieved IPC/BNS section(s) cited: {', '.join(invalid_sections)}. "
            f"Only the following sections are retrieved and allowed: {', '.join(valid_section_numbers) if valid_section_numbers else 'None'}."
        )

    # 4. Precedents Check
    # Find all case citations in draft
    cited_cases = CASE_CITATION_PATTERN.findall(text)
    invalid_cases = []
    for case in cited_cases:
        # Check if keywords of the case name are present in retrieved precedents text
        case_clean = case.lower()
        # Extract name parts, e.g., "nanavati" or "rahul sharma"
        parts = [p.strip() for p in re.split(r"\s+v[s]?\.\s+", case_clean)]
        found = False
        for part in parts:
            if part in ("state", "union of india", "uoi", "state of", "vs", "v", "versus"):
                continue
            if part in retrieved_precedents_text.lower():
                found = True
                break
        if not found:
            invalid_cases.append(case)

    if invalid_cases:
        errors.append(
            f"Hallucinated or unretrieved precedent(s) cited: {', '.join(invalid_cases)}. "
            "Do not cite cases that were not retrieved by LexiGraph."
        )

    # Build Feedback if invalid
    if errors:
        feedback_lines = [
            "Your draft argument did not pass validation for the following reasons:"
        ]
        for err in errors:
            feedback_lines.append(f"- {err}")
        feedback_lines.append(
            "\nPlease rewrite the argument. Follow the required structure, "
            f"strictly use only the retrieved sections ({', '.join(valid_section_numbers) if valid_section_numbers else 'None'}), "
            "and only cite the provided judicial precedents. Do not invent any legal codes or cases."
        )

        return GuardrailResult(
            is_valid=False,
            errors=errors,
            feedback="\n".join(feedback_lines),
        )

    return GuardrailResult(is_valid=True, errors=[], feedback="OK")
