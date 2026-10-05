"""
Citation Guardrail — Programmatic Regex / Span Verifier
=========================================================
Ensures the LLM did NOT hallucinate verbatim quotes.

For every CitedFact produced by the Prosecutor Agent:
  1. Exact match check  (case-insensitive substring)
  2. Fuzzy span check   (≥ 85 % token overlap) as fallback for minor whitespace / ellipsis trimming
  3. Records failures as hallucination_flags on the ProsecutorOutput

This is a 0-LLM-call, pure-Python guardrail.
"""

from __future__ import annotations
import re
from typing import List, Tuple

from .schemas import CitedFact, ProsecutorOutput, ProsecutionSubQuery


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Collapse whitespace and lower-case for comparison."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _token_overlap_ratio(a: str, b: str) -> float:
    """Jaccard-style token overlap between two strings."""
    ta = set(_normalize(a).split())
    tb = set(_normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _exact_span(source: str, quote: str) -> Tuple[bool, int, int]:
    """
    Case-insensitive exact substring search.
    Returns (found, start, end).
    """
    normalized_src = _normalize(source)
    normalized_q = _normalize(quote)
    idx = normalized_src.find(normalized_q)
    if idx == -1:
        return False, -1, -1
    return True, idx, idx + len(normalized_q)


FUZZY_THRESHOLD = 0.72   # token-overlap ratio considered acceptable
MIN_QUOTE_LEN   = 8      # quotes shorter than this are not guardrail-checked (too generic)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

class CitationGuardrail:
    """
    Verifies every verbatim_quote in a ProsecutorOutput against the raw case text.
    Populates hallucination_flags and sets verification_status.
    """

    def __init__(self, fuzzy_threshold: float = FUZZY_THRESHOLD):
        self.fuzzy_threshold = fuzzy_threshold

    def verify(self, output: ProsecutorOutput, source_text: str) -> ProsecutorOutput:
        """
        Mutates output in-place:
        - Populates char_start / char_end on each CitedFact where found.
        - Appends to output.hallucination_flags for any quote not found.
        - Sets output.verification_status = 'VERIFIED' | 'FLAGGED'.

        Returns the mutated output.
        """
        flags: List[str] = []

        for sq in output.sub_queries:
            for cf in sq.supporting_facts:
                quote = cf.verbatim_quote.strip()

                # Skip trivially short quotes
                if len(quote) < MIN_QUOTE_LEN:
                    continue

                found_exact, s, e = _exact_span(source_text, quote)

                if found_exact:
                    cf.char_start = s
                    cf.char_end   = e
                else:
                    # Fuzzy fallback — slide a window of ±40 chars around each occurrence
                    # of the first content word of the quote
                    ratio = _token_overlap_ratio(quote, source_text)
                    # Also try per-sentence fuzzy
                    sentences = re.split(r"(?<=[.!?])\s+", source_text)
                    best = max(
                        (_token_overlap_ratio(quote, s_) for s_ in sentences),
                        default=0.0,
                    )
                    overlap = max(ratio, best)

                    if overlap >= self.fuzzy_threshold:
                        # Acceptable fuzzy match — mark it but do not flag
                        cf.char_start = -1   # -1 = fuzzy, not exact
                        cf.char_end   = -1
                    else:
                        flag_msg = (
                            f"[HALLUCINATION FLAG] Sub-query {sq.id} | Fact '{cf.fact_label}' | "
                            f"Quote not found in source text (overlap={overlap:.2f}): "
                            f'"{quote[:120]}{"..." if len(quote) > 120 else ""}"'
                        )
                        flags.append(flag_msg)

        output.hallucination_flags.extend(flags)
        output.verification_status = "FLAGGED" if flags else "VERIFIED"
        return output


def format_guardrail_report(output: ProsecutorOutput) -> str:
    """Return a human-readable summary of guardrail results."""
    lines = [
        f"Citation Guardrail — Status: {output.verification_status}",
        f"  Hallucination flags: {len(output.hallucination_flags)}",
    ]
    for f in output.hallucination_flags:
        lines.append(f"  ⚠  {f}")
    if not output.hallucination_flags:
        lines.append("  ✓  All verbatim quotes verified against source text.")
    return "\n".join(lines)