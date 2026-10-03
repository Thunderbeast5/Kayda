"""
IssueDetector service — Phase 3

Detects new legal issues raised mid-hearing that are NOT already
covered by the existing legal_context_package or precedent_context.

This is a deterministic service — no LLM calls.

Trigger conditions (from JUDGE_AGENT.md §7):
  1. A section cited by Defence/Prosecution not in legal_context_package
  2. A constitutional provision raised but not in supporting_articles
  3. A precedent cited that is not in precedent_context
  4. A procedural law question arises (BNSS / CrPC provisions)

Output: list of NewLegalIssue objects, each describing what was
detected and what retrieval is needed.
"""

from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, Field

# ── Patterns for extracting legal references from text ────────────────────────

# Matches: BNS 117, IPC 302, BNSS 484, BSA 27, POCSO 4, IT Act 66C, NDPS 20
_SECTION_RE = re.compile(
    r'\b(BNS|IPC|BNSS|BSA|POCSO|IT\s*Act|NDPS|CrPC|Dowry Act|DV Act|JJ Act)\s*'
    r'(\d+[A-Za-z]?)\b',
    re.IGNORECASE,
)

# Matches: Article 14, Article 21, Article 22
_ARTICLE_RE = re.compile(
    r'\bArticle\s+(\d+[A-Za-z]?)\b',
    re.IGNORECASE,
)

# Matches case citations like "v. State" or "AIR 1980" or "(2020) 5 SCC"
_CASE_RE = re.compile(
    r'(?:'
    r'\bv\.\s+(?:State|Union|Government)\b'          # "v. State of..."
    r'|AIR\s+\d{4}'                                  # AIR 1980
    r'|\(\d{4}\)\s+\d+\s+SCC'                        # (2020) 5 SCC
    r'|\d{4}\s+Cri\s*LJ'                             # 2020 Cri LJ
    r')',
    re.IGNORECASE,
)


# ── Data models ────────────────────────────────────────────────────────────────

class NewLegalIssue(BaseModel):
    """
    A single new legal issue detected mid-hearing.

    issue_type    : what kind of new issue it is
    reference     : the exact string found (e.g. "NDPS 37", "Article 22")
    source        : which argument / report it was found in
    description   : human-readable description
    retrieval_needed : which retrieval agent to invoke
    """
    issue_type: Literal[
        "UNKNOWN_SECTION",
        "UNKNOWN_ARTICLE",
        "UNKNOWN_PRECEDENT",
        "PROCEDURAL_LAW",
    ]
    reference:          str
    source:             str   # "Defence" / "Prosecution" / "IO Agent"
    description:        str
    retrieval_needed:   list[str] = Field(default_factory=list)
    # "LexiGraph" | "Precedent" | "Both"


class IssueDetectionResult(BaseModel):
    new_issues:          list[NewLegalIssue] = Field(default_factory=list)
    retrieval_required:  bool = False
    target_agents:       list[str] = Field(default_factory=list)
    # deduplicated list: "LexiGraph" and/or "Precedent"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise_section(act: str, num: str) -> str:
    act = act.strip().upper().replace(" ", "_")
    return f"{act}_{num.strip().upper()}"


def _known_sections(legal_context_package: dict) -> set[str]:
    """
    Build a set of normalised section keys from the existing package.
    e.g. {"BNS_117", "BNS_118", "ARTICLE_21"}
    """
    known: set[str] = set()
    for item in legal_context_package.get("recommended_sections") or []:
        sec = item.get("section") or ""
        # sec looks like "BNS 117" — normalise
        m = re.match(r'([A-Za-z_\s]+)\s+(\d+[A-Za-z]?)', sec.strip())
        if m:
            known.add(_normalise_section(m.group(1), m.group(2)))
    for art in legal_context_package.get("supporting_articles") or []:
        if isinstance(art, str):
            am = re.search(r'Article\s+(\d+[A-Za-z]?)', art, re.IGNORECASE)
            if am:
                known.add(f"ARTICLE_{am.group(1).upper()}")
    return known


def _known_precedents(precedent_context: dict | list) -> set[str]:
    """
    Build a set of lowercased case name fragments from existing precedents.
    """
    known: set[str] = set()
    items = []
    if isinstance(precedent_context, list):
        items = precedent_context
    elif isinstance(precedent_context, dict):
        items = (
            (precedent_context.get("similar_cases") or [])
            + (precedent_context.get("supporting_cases") or [])
        )
    for item in items:
        name = (item.get("case_name") or item.get("title") or "").strip().lower()
        if name:
            known.add(name)
    return known


def _is_procedural(act: str) -> bool:
    """Return True if the act is a procedural law (BNSS / CrPC)."""
    upper = act.upper().replace(" ", "")
    return upper in ("BNSS", "CRPC")


# ── IssueDetector ──────────────────────────────────────────────────────────────

class IssueDetector:
    """
    Scans new argument text for legal references not already in the
    existing legal_context_package or precedent_context.

    Usage
    -----
    detector = IssueDetector()
    result = detector.detect(
        texts              = {"Defence": "...", "Prosecution": "...", "IO Agent": "..."},
        legal_context_package = current_package,
        precedent_context     = current_precedents,
    )
    if result.retrieval_required:
        # invoke dynamic retrieval
    """

    def detect(
        self,
        texts: dict[str, str],
        legal_context_package: dict,
        precedent_context: dict | list,
    ) -> IssueDetectionResult:
        """
        Parameters
        ----------
        texts                 : {"Defence": text, "Prosecution": text, "IO Agent": text}
        legal_context_package : current LexiGraph output
        precedent_context     : current Precedent Retrieval output

        Returns
        -------
        IssueDetectionResult
        """
        known_sections   = _known_sections(legal_context_package)
        known_precedents = _known_precedents(precedent_context)
        issues:  list[NewLegalIssue] = []
        seen_refs: set[str] = set()  # deduplicate by reference

        for source, text in texts.items():
            if not text:
                continue

            # ── Scan for statutory sections ──────────────────────────────────
            for m in _SECTION_RE.finditer(text):
                act = m.group(1).strip()
                num = m.group(2).strip()
                key = _normalise_section(act, num)

                if key in seen_refs:
                    continue
                seen_refs.add(key)

                if _is_procedural(act):
                    issues.append(NewLegalIssue(
                        issue_type="PROCEDURAL_LAW",
                        reference=m.group(0).strip(),
                        source=source,
                        description=(
                            f"Procedural law question raised: {m.group(0).strip()} "
                            f"({source}). Current package may not cover procedural provisions."
                        ),
                        retrieval_needed=["LexiGraph"],
                    ))
                elif key not in known_sections:
                    issues.append(NewLegalIssue(
                        issue_type="UNKNOWN_SECTION",
                        reference=m.group(0).strip(),
                        source=source,
                        description=(
                            f"Section {m.group(0).strip()} cited by {source} "
                            f"is not in the current legal context package."
                        ),
                        retrieval_needed=["LexiGraph"],
                    ))

            # ── Scan for constitutional articles ─────────────────────────────
            for m in _ARTICLE_RE.finditer(text):
                key = f"ARTICLE_{m.group(1).upper()}"
                if key in seen_refs or key in known_sections:
                    continue
                seen_refs.add(key)
                issues.append(NewLegalIssue(
                    issue_type="UNKNOWN_ARTICLE",
                    reference=m.group(0).strip(),
                    source=source,
                    description=(
                        f"Constitutional provision {m.group(0).strip()} raised by "
                        f"{source} is not in supporting_articles."
                    ),
                    retrieval_needed=["LexiGraph"],
                ))

            # ── Scan for case citations ───────────────────────────────────────
            for m in _CASE_RE.finditer(text):
                ref = m.group(0).strip()
                ref_lower = ref.lower()
                if ref_lower in seen_refs:
                    continue
                # Check if any known precedent name contains this fragment
                if any(ref_lower in kp for kp in known_precedents):
                    continue
                seen_refs.add(ref_lower)
                issues.append(NewLegalIssue(
                    issue_type="UNKNOWN_PRECEDENT",
                    reference=ref,
                    source=source,
                    description=(
                        f"Case citation '{ref}' raised by {source} "
                        f"is not in the current precedent context."
                    ),
                    retrieval_needed=["Precedent"],
                ))

        # ── Build result ──────────────────────────────────────────────────────
        target_agents: set[str] = set()
        for issue in issues:
            for agent in issue.retrieval_needed:
                target_agents.add(agent)

        return IssueDetectionResult(
            new_issues=issues,
            retrieval_required=len(issues) > 0,
            target_agents=sorted(target_agents),
        )
