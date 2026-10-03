"""
ArgumentEvaluator service.

Parses the LLM scoring pass output into structured scores
for defence and prosecution arguments.

Scoring axes (each 0-10):
  • Legal Validity   — sections correctly applied?
  • Evidence Linkage — facts support the legal claim?
  • Logic Coherence  — argument internally consistent?
"""

import re
from typing import Tuple

from ..models.judicial_findings import ArgumentScore, ArgumentEvaluation

# If either side's total falls below this, Judge asks clarification questions
SUFFICIENCY_THRESHOLD = 15  # out of 30


def _extract_score_block(text: str, side: str) -> str:
    """
    Pull the scoring block for 'DEFENCE' or 'PROSECUTION' out of the raw LLM text.
    Returns the block text, or empty string if not found.
    """
    pattern = rf"{side}\s+SCORES?:(.*?)(?:(?:DEFENCE|PROSECUTION)\s+SCORES?:|SUFFICIENCY:|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _parse_axis(text: str, axis_name: str) -> int:
    """Extract a single numeric score for the given axis from a text block."""
    pattern = rf"{axis_name}\s*[:\-]\s*(\d+)"
    match = re.search(pattern, text, re.IGNORECASE)
    raw = int(match.group(1)) if match else 0
    return max(0, min(10, raw))  # clamp to 0-10


def _parse_score_block(block: str) -> ArgumentScore:
    lv = _parse_axis(block, r"legal\s*validity")
    el = _parse_axis(block, r"evidence\s*linkage")
    lc = _parse_axis(block, r"logic\s*coherence")
    return ArgumentScore(
        legal_validity=lv,
        evidence_linkage=el,
        logic_coherence=lc,
        total=lv + el + lc,
    )


def _parse_sufficiency(text: str, prosecution_total: int) -> bool:
    """
    Parse SUFFICIENCY: YES/NO from LLM text.
    Falls back to numeric threshold check only when SUFFICIENCY line is present
    but unreadable; if the line is entirely absent, use the threshold.
    """
    match = re.search(r"SUFFICIENCY\s*:\s*(YES|NO)", text, re.IGNORECASE)
    if match:
        return match.group(1).upper() == "YES"
    # No SUFFICIENCY line found — fall back to numeric threshold
    return prosecution_total >= SUFFICIENCY_THRESHOLD


def _parse_new_issues(text: str) -> list[str]:
    """
    Extract NEW LEGAL ISSUES DETECTED block from scoring output.
    Returns a list of issue strings (empty if NONE).
    Filters out the header line that may be repeated in the text.
    """
    block_match = re.search(
        r"NEW LEGAL ISSUES DETECTED\s*(?:\(.*?\))?\s*[:\-]?\s*(.*?)(?:\n\n|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not block_match:
        return []
    block = block_match.group(1).strip()
    if not block:
        return []

    issues = []
    for line in block.splitlines():
        line = line.strip()
        # Skip blank lines, NONE markers, and any repeated header text
        if not line:
            continue
        if line.upper() == "NONE":
            return []
        if re.search(r"list any section|write none|applicable law above", line, re.IGNORECASE):
            continue
        issues.append(line)
    return issues


def _parse_raw_questions(text: str) -> list[dict]:
    """
    Parse the QUESTIONS block from the scoring output.
    Expected line format:
        TARGET: Defence | ISSUE: <gap> | QUESTION: <question>
    """
    questions = []
    block_match = re.search(
        r"QUESTIONS?\s*(?:\(.*?\))?\s*[:\-]?\s*(.*?)(?:NEW LEGAL ISSUES|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not block_match:
        return questions

    for line in block_match.group(1).splitlines():
        line = line.strip()
        if not line or line.upper().startswith("NONE"):
            continue
        target_m = re.search(r"TARGET\s*:\s*([^|]+)", line, re.IGNORECASE)
        issue_m  = re.search(r"ISSUE\s*:\s*([^|]+)", line, re.IGNORECASE)
        q_m      = re.search(r"QUESTION\s*:\s*(.+)", line, re.IGNORECASE)
        if target_m and q_m:
            questions.append({
                "target":   target_m.group(1).strip(),
                "issue":    issue_m.group(1).strip() if issue_m else "Unspecified gap",
                "question": q_m.group(1).strip(),
            })
    return questions


class ArgumentEvaluator:
    """
    Parses raw LLM scoring output into structured ArgumentEvaluation,
    sufficiency flag, raw question list, and new issue list.
    """

    def parse(
        self,
        llm_output: str,
    ) -> Tuple[ArgumentEvaluation, bool, list[dict], list[str]]:
        """
        Parameters
        ----------
        llm_output : str
            Raw text from the SCORING_PROMPT LLM call.

        Returns
        -------
        evaluation     : ArgumentEvaluation
        is_sufficient  : bool — True if hearing can proceed without questions
        raw_questions  : list[dict] — questions to be turned into JudgeQuestion objects
        new_issues     : list[str] — new legal issues detected in arguments
        """
        defence_block     = _extract_score_block(llm_output, "DEFENCE")
        prosecution_block = _extract_score_block(llm_output, "PROSECUTION")

        defence_score     = _parse_score_block(defence_block)
        prosecution_score = _parse_score_block(prosecution_block)

        is_sufficient  = _parse_sufficiency(llm_output, prosecution_score.total)
        raw_questions  = _parse_raw_questions(llm_output)
        new_issues     = _parse_new_issues(llm_output)

        evaluation = ArgumentEvaluation(
            defence_score=defence_score,
            prosecution_score=prosecution_score,
        )

        return evaluation, is_sufficient, raw_questions, new_issues
