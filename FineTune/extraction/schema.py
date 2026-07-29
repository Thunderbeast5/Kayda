"""
Field schema for anticipatory bail case records.
Single source of truth — extraction, validation, and dataset construction
all import from here. Do not add fields here without updating field_extractor.py.

Field design rationale:
  Every field must earn its place by enabling at least one distinct fine-tuning
  instruction/output pair type that the others cannot cover. Fields that are
  pure duplicates of other fields (different wording, same content) waste the
  training budget on repetition rather than variety.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


# ── Boilerplate strings ───────────────────────────────────────────────────────
# Any line *containing* one of these strings is dropped during cleaning.
BOILERPLATE_PATTERNS: list[str] = [
    "Licensed to :-",
    "Client Code :-",
    "Copyright © 2026 by Regent Computronics",
    "Copyright © 2025 by Regent Computronics",
    "Copyright © 2024 by Regent Computronics",
    "Copyright © 2023 by Regent Computronics",
    "Copyright © 2022 by Regent Computronics",
    "Copyright © 2021 by Regent Computronics",
    "Copyright © 2020 by Regent Computronics",
    "Copyright © 2019 by Regent Computronics",
    "Copyright © 2018 by Regent Computronics",
    "Copyright © 2017 by Regent Computronics",
    "Copyright © 2016 by Regent Computronics",
    "Copyright © 2015 by Regent Computronics",
    "Copyright © 2014 by Regent Computronics",
    "Copyright © 2013 by Regent Computronics",
    "Copyright © 2012 by Regent Computronics",
    "Copyright © 2011 by Regent Computronics",
    "Copyright © 2010 by Regent Computronics",
    "Copyright © 2009 by Regent Computronics",
    "Copyright © 2008 by Regent Computronics",
    "www.the-laws.com",
    "Regent Computronics Private Limited",
    "Regent Computronics Pvt",
]

# Page-footer pattern matched at start of stripped line.
PAGE_FOOTER_PATTERN = r"^Page\s+\d+\s+of\s+\d+"

# ── Section anchors ───────────────────────────────────────────────────────────
# Order: reflects appearance order in PDFs.
# These are split anchors — text between consecutive anchors belongs to the first.
SECTION_ANCHORS: list[str] = [
    "Coram :",
    "Decided On :",
    "Appeal Type :",
    "Final Verdict :",
    "Appellant(s) :",
    "Respondent(s) :",
    "Advocate(s) :",
    "Equivalent Citation :",
    "Cited Judgement(s) :",
    "Referred Act(s) :",
    "Headnote:",
    "Judgment :",
]

# ── Monetary modification keywords ───────────────────────────────────────────
# Used to find the boundary between "original condition" and "modified condition"
# amounts inside the same paragraph.
MODIFICATION_KEYWORDS: list[str] = [
    "modif",          # modify, modified, modification
    "self-bond",
    "self bond",
    "personal bond",
    "furnish",
    "execute",        # "execute personal bonds"
    "reduced",
    "in lieu",
    "deleting the direction",
    "delete",
    "set aside",
]

# Bail outcome classification labels
BAIL_OUTCOME_LABELS = {
    "granted":   "Bail granted by this court",
    "modified":  "Bail conditions modified (original bail upheld, conditions changed)",
    "deleted":   "Onerous bail condition removed entirely",
    "refused":   "Bail application rejected or cancelled",
    "dismissed": "Appeal dismissed (lower court's bail order upheld unchanged)",
    "referred":  "Matter referred to larger bench — no final bail order",
    "interim":   "Interim protection from arrest granted pending further hearing",
}

# ── Triage threshold ──────────────────────────────────────────────────────────
CHARS_PER_PAGE_THRESHOLD = 50


# ── Case record dataclass ─────────────────────────────────────────────────────

@dataclass
class HeadnotePoint:
    """One labelled point (A, B, C...) within the headnote block."""
    label: str        # "A", "B", "C", etc.
    text: str         # full text of that point


@dataclass
class Paragraph:
    """One numbered paragraph from the judgment body."""
    number: str       # "1", "2", "3" etc.
    text: str


@dataclass
class CaseRecord:
    """
    One extracted case — maps 1:1 to one source PDF.

    Field groups:
      PROVENANCE     — file tracking
      HEADER         — metadata from the top block
      PARTIES        — appellant, respondent, advocates
      CITATIONS      — equivalent citations and cited judgments
      ACTS           — referred statutes (the statutory anchor)
      HEADNOTE       — structured A/B/C points (prime fine-tuning signal)
      JUDGMENT_BODY  — judge byline + numbered paragraphs
      DERIVED        — fields computed after extraction (bail amounts, outcome, ratio)
      QA_FLAGS       — quality/completeness indicators
    """

    # ── PROVENANCE ────────────────────────────────────────────────────────────
    source_file: str = ""
    extraction_path: str = ""        # "TEXT_LAYER" | "OCR"

    # ── HEADER ────────────────────────────────────────────────────────────────
    case_citation: Optional[str] = None       # "LAWS(SC)-2021-1-41"
    court: Optional[str] = None               # "SUPREME COURT OF INDIA"
    coram: Optional[str] = None               # full coram line
    decided_on: Optional[str] = None          # raw date string from PDF
    decided_on_year: Optional[int] = None     # parsed year — for train/val/test split
    appeal_type: Optional[str] = None         # full multi-line appeal type string
    final_verdict: Optional[str] = None       # "Appeal disposed" / "Appeal allowed" etc.

    # ── PARTIES ───────────────────────────────────────────────────────────────
    appellant: Optional[str] = None
    respondent: Optional[str] = None
    advocates: Optional[str] = None

    # ── CITATIONS ─────────────────────────────────────────────────────────────
    equivalent_citations: list[str] = field(default_factory=list)
    cited_judgments: list[str] = field(default_factory=list)

    # ── ACTS ──────────────────────────────────────────────────────────────────
    # List of section references e.g. ["S.438", "S.438(2)"]
    # Critical: this IS the statutory anchor for fine-tuning
    referred_acts: list[str] = field(default_factory=list)

    # ── HEADNOTE ──────────────────────────────────────────────────────────────
    # Raw full headnote block (for cases where point splitting fails)
    headnote_raw: Optional[str] = None
    # Structured list of labelled headnote points
    # Each: {"label": "A", "text": "..."} — directly usable as fine-tuning targets
    headnote_points: list[dict] = field(default_factory=list)

    # ── JUDGMENT BODY ─────────────────────────────────────────────────────────
    # Judge byline as written in the judgment body (may differ from coram)
    judgment_author: Optional[str] = None
    # Numbered paragraphs — richest source of reasoning-chain training examples
    # Each: {"number": "5", "text": "..."}
    numbered_paragraphs: list[dict] = field(default_factory=list)

    # ── DERIVED ───────────────────────────────────────────────────────────────
    # Monetary figures — critical for "onerous condition" reasoning pattern
    bail_amount_original: Optional[str] = None   # condition imposed by lower court
    bail_amount_modified: Optional[str] = None   # condition after SC modification (None if deleted)
    bail_amount_original_normalized: Optional[str] = None  # canonical form e.g. "10,00,000"
    bail_amount_modified_normalized: Optional[str] = None

    # Outcome classification — the primary label for a classification fine-tune
    # Values: "granted" | "modified" | "deleted" | "refused" | "dismissed" | null
    bail_outcome: Optional[str] = None

    # Bail conditions imposed — list of plain-English condition strings
    # e.g. ["Personal bond of Rs.50,000", "Cooperation with investigation",
    #        "Abide by S.438(2) conditions"]
    bail_conditions: list[str] = field(default_factory=list)

    # The paragraph containing the generalizable legal rule (ratio decidendi)
    # Selected by heuristic signal phrases — not every case will have one
    ratio_decidendi: Optional[str] = None
    ratio_para_number: Optional[str] = None   # which paragraph number it came from

    # Nature of dispute if discernible from judgment text
    # e.g. "civil dispute - land purchase", "matrimonial", "cheating/fraud"
    dispute_nature: Optional[str] = None

    # ── QA FLAGS ──────────────────────────────────────────────────────────────
    missing_anchors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @property
    def has_section_438(self) -> bool:
        return any("438" in act for act in self.referred_acts)

    @property
    def missing_critical_fields(self) -> list[str]:
        """Returns names of critical fields that are empty — for QA gate."""
        missing = []
        if not self.referred_acts:
            missing.append("referred_acts")
        if not self.headnote_raw:
            missing.append("headnote_raw")
        if not self.numbered_paragraphs:
            missing.append("numbered_paragraphs")
        if not self.final_verdict:
            missing.append("final_verdict")
        if not self.bail_outcome:
            missing.append("bail_outcome")
        return missing
