"""
Anchor-based field extractor.
Operates on clean document text produced by cleaner.py.
No OCR here — pure text parsing against fixed structural anchors.

Extraction design notes:
  - Every field extractor has exactly one job. No shared state between them.
  - Where a field may appear in multiple formats (multi-line, wrapped, etc.),
    the extractor handles ALL known variants — documented inline.
  - Heuristic fields (ratio_decidendi, bail_outcome, dispute_nature) document
    their signal phrases explicitly so they can be updated when new patterns
    are found across the 100-PDF corpus.
"""

import re
from datetime import datetime
from .schema import CaseRecord, SECTION_ANCHORS, MODIFICATION_KEYWORDS


# ─────────────────────────────────────────────────────────────────────────────
# Document splitter
# ─────────────────────────────────────────────────────────────────────────────

def _split_on_anchors(text: str) -> dict[str, str]:
    """
    Split the full document string on known section anchor strings.

    Returns dict:
      "_before_first" → text before any anchor (contains citation + court)
      "Coram :"       → text from that anchor until next anchor
      "Headnote:"     → ...
      etc.

    If an anchor appears twice (unusual but possible in some PDFs where the
    structure repeats), the second occurrence's content is appended to the first.
    """
    escaped = [re.escape(a) for a in SECTION_ANCHORS]
    pattern = "(" + "|".join(escaped) + ")"

    parts = re.split(pattern, text)
    # parts layout: [before_text, anchor1, content1, anchor2, content2, ...]

    sections: dict[str, str] = {"_before_first": parts[0].strip()}
    i = 1
    while i < len(parts) - 1:
        anchor = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if anchor in sections:
            sections[anchor] = sections[anchor] + "\n" + content
        else:
            sections[anchor] = content
        i += 2

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# Individual field extractors
# ─────────────────────────────────────────────────────────────────────────────

def _extract_case_citation(before_first: str) -> str | None:
    """
    Citation line: e.g. "LAWS(SC)-2021-1-41"
    Always on its own line, pattern LAWS(XX)-YYYY-N-NNN.
    """
    for line in before_first.splitlines():
        line = line.strip()
        if re.match(r"LAWS\([A-Z]+\)-\d{4}-\d+-\d+", line):
            return line
    return None


def _extract_court(before_first: str) -> str | None:
    """
    Court name: e.g. "SUPREME COURT OF INDIA", "HIGH COURT OF JUDICATURE AT BOMBAY"
    Appears on its own line, all-caps, contains "COURT".
    """
    for line in before_first.splitlines():
        line = line.strip()
        if "COURT" in line.upper() and len(line) < 100 and line == line.upper():
            return line
    return None


def _extract_multiline_field(raw: str) -> str:
    """
    For fields like Appeal Type that wrap across lines — collect ALL lines
    until the content naturally ends (blank line or next anchor already consumed).
    """
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    return " ".join(lines)


def _extract_referred_acts(raw: str) -> list[str]:
    """
    Parse 'Referred Act(s) :' block into individual section references.
    Input: "- Code Of Criminal Procedure, 1973, S.438, S.438(2)\n- ..."
    Output: ["S.438", "S.438(2)"]

    Also captures BNS/IPC section references for forward-compatibility.
    """
    # Join lines that are continuations of a dash-started item
    items = []
    current = ""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("- "):
            if current:
                items.append(current)
            current = line[2:].strip()
        elif line and current:
            current = current + " " + line
    if current:
        items.append(current)

    # Extract section references from each item
    sections: list[str] = []
    for item in items:
        found = re.findall(r"S\.\s*\d+(?:\s*\(\s*\d+\s*\))?", item)
        if found:
            # Normalise spacing: "S. 438 ( 2 )" → "S.438(2)"
            for s in found:
                s = re.sub(r"\s+", "", s)
                sections.append(s)
        else:
            sections.append(item)

    return list(dict.fromkeys(sections))  # deduplicate preserving order


def _parse_headnote_points(raw: str) -> tuple[list[dict], str]:
    """
    Split headnote into labelled A/B/C points.

    Headnote structure in these PDFs:
      A. CODE OF CRIMINAL PROCEDURE... - <holding text>
      B. <holding text>
      C. ...

    Returns (points_list, raw_headnote_string).
    points_list: [{"label": "A", "text": "..."}, ...]
    raw: full headnote text (always kept as fallback)

    Handles:
    - Multi-line points (point continues until next uppercase letter + period)
    - Points that end with " - N." (paragraph reference suffix — stripped)
    """
    raw_clean = raw.strip()

    # Split on uppercase letter followed by period at start of a line or
    # after a newline (A. B. C. etc.)
    point_pattern = re.compile(r"(?:^|\n)([A-Z])\.\s+", re.MULTILINE)
    split_parts = point_pattern.split(raw_clean)
    # split_parts: [pre_text, label1, text1, label2, text2, ...]

    points = []
    seen_texts: set[str] = set()
    i = 1
    while i < len(split_parts) - 1:
        label = split_parts[i].strip()
        text = split_parts[i + 1].strip() if i + 1 < len(split_parts) else ""

        # Strip trailing paragraph-reference suffix: " - 5." or "- (3.)"
        text = re.sub(r"\s*-\s*\(?\d+\.?\)?\s*$", "", text).strip()

        # Deduplicate: skip points whose text is identical to an already-seen point
        norm = re.sub(r"\s+", " ", text).strip()
        if label and text and norm not in seen_texts:
            points.append({"label": label, "text": text})
            seen_texts.add(norm)
        i += 2

    return points, raw_clean


def _extract_judgment_author_and_paragraphs(judgment_text: str) -> tuple[str | None, list[dict]]:
    """
    The judgment body contains:
      1. Optional judge byline: "N. Santosh Hegde, S.B. Sinha and A.K. Mathur, JJ."
      2. Numbered paragraphs: (1.) ... (2.) ...

    Returns (judgment_author, paragraphs_list).

    Judge byline detection: appears before paragraph (1.), contains "JJ." or "J."
    at the end, and is not a numbered paragraph.
    """
    # Find the position of the first paragraph marker
    first_para_match = re.search(r"(?:^|\n)\(\d+\.?\)", judgment_text, re.MULTILINE)
    author = None

    if first_para_match:
        pre_para_text = judgment_text[:first_para_match.start()].strip()
        if pre_para_text:
            # Check if it looks like a judge byline (ends with J. or JJ.)
            if re.search(r"\bJJ?\.\s*$", pre_para_text):
                author = pre_para_text.strip()

    # Extract numbered paragraphs
    pattern = r"(?:^|\n)\((\d+)\.?\)"
    parts = re.split(pattern, judgment_text.strip(), flags=re.MULTILINE)

    paragraphs = []
    i = 1
    while i < len(parts) - 1:
        num = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if content:
            paragraphs.append({"number": num, "text": content})
        i += 2

    return author, paragraphs


def _extract_monetary_amounts(paragraphs: list[dict]) -> tuple[str | None, str | None]:
    """
    Extract bail_amount_original and bail_amount_modified.

    Strategy: within each paragraph, find the first occurrence of a MODIFICATION
    keyword. Rs. figures BEFORE that position are "original condition" candidates;
    figures AFTER are "modified condition" candidates.

    DELETION CASE: if the court deletes a condition entirely (no new Rs. figure
    given as replacement), bail_amount_modified must be None. Signal: paragraph
    contains "deleting the direction to deposit" or "set aside the condition"
    without any NEW Rs. figure after the deletion keyword.

    Handles formats:
      Rs. 10 lakhs / Rs.50,000/- / Rs 41 lakhs / Rs.50,000
    """
    rs_pattern = re.compile(
        r"Rs\.?\s*[\d,]+(?:\s*(?:/-|lakhs?|crores?|thousand))?",
        re.IGNORECASE
    )
    mod_pattern = re.compile(
        "|".join(re.escape(k) for k in MODIFICATION_KEYWORDS),
        re.IGNORECASE
    )
    # Pure deletion: court removes condition, does NOT provide a replacement amount
    pure_deletion_pattern = re.compile(
        r"delet(?:e|ing|ed)\s+the\s+(?:direction|condition|requirement)\s+to\s+deposit"
        r"|set\s+aside\s+the\s+(?:condition|direction)"
        r"|without\s+any\s+(?:further\s+)?condition"
        r"|unconditional(?:ly)?",
        re.IGNORECASE
    )

    original_candidates: list[str] = []
    modified_candidates: list[str] = []

    for para in paragraphs:
        text = para["text"]

        mod_match = mod_pattern.search(text)
        mod_pos = mod_match.start() if mod_match else len(text)

        # Check for pure deletion — if the whole paragraph is a deletion,
        # any Rs. figure in it is part of the ORIGINAL condition being cited,
        # not a new modified condition
        is_pure_deletion = bool(pure_deletion_pattern.search(text))

        for m in rs_pattern.finditer(text):
            amt = _normalise_rs_amount(m.group().strip())
            if m.start() < mod_pos:
                original_candidates.append(amt)
            else:
                # After modification keyword — only add as modified if NOT
                # a pure deletion paragraph
                if not is_pure_deletion:
                    modified_candidates.append(amt)

    original = original_candidates[0] if original_candidates else None
    modified = modified_candidates[0] if modified_candidates else None

    # Edge case: only modification amounts found, no pre-mod figure
    if original is None and modified is not None:
        original = modified
        modified = modified_candidates[1] if len(modified_candidates) > 1 else None

    return original, modified


def _normalise_rs_amount(raw: str) -> str:
    """
    Normalise Rs. amount strings to consistent format.
    "Rs.50,000/-"  → "Rs. 50,000"
    "Rs 41 lakhs"  → "Rs. 41 lakhs"
    "Rs. 10 lakhs" → "Rs. 10 lakhs"  (unchanged)
    """
    raw = raw.strip()
    # Normalise "Rs" / "Rs." / "Rs. " → "Rs. "
    raw = re.sub(r"^Rs\.?\s*", "Rs. ", raw, flags=re.IGNORECASE)
    # Remove trailing /-
    raw = re.sub(r"/-\s*$", "", raw).strip()
    return raw


def _determine_bail_outcome(paragraphs: list[dict], headnote_raw: str) -> str | None:
    """
    Classify the court's outcome as one of:
      "granted"    — bail granted (fresh grant by SC, was rejected below)
      "modified"   — existing bail upheld but conditions modified
      "deleted"    — onerous condition removed entirely, no replacement
      "refused"    — bail refused by SC
      "dismissed"  — appeal dismissed (lower court order upheld unchanged)

    Signal phrases (in priority order) checked in paragraphs + headnote.
    This is the single most important derived field for classification fine-tuning.
    """
    all_text = " ".join(p["text"] for p in paragraphs) + " " + (headnote_raw or "")
    text_lower = all_text.lower()

    # Priority 1: explicit deletion of condition (no replacement)
    if re.search(r"delet(?:e|ing|ed)\s+the\s+(?:direction|condition|requirement)\s+to\s+deposit", text_lower):
        return "deleted"
    if re.search(r"(?:set aside|struck down|quash)\s+the\s+condition", text_lower):
        return "deleted"

    # Priority 2: modification (condition changed to a different amount)
    if re.search(r"in\s+modification\s+of", text_lower):
        return "modified"
    if re.search(r"modif(?:y|ying|ied|ication)\s+the\s+(?:order|condition|bail)", text_lower):
        return "modified"
    if re.search(r"modif(?:y|ying|ied|ication)\s+the\s+(?:impugned|said)\s+order", text_lower):
        return "modified"

    # Priority 3: fresh grant (bail was refused below, SC grants it)
    if re.search(r"grant\s+anticipatory\s+bail", text_lower):
        return "granted"
    if re.search(r"allow\s+the\s+appeal[s]?\s+and\s+grant", text_lower):
        return "granted"

    # Priority 4: refusal
    if re.search(r"(?:dismiss|reject|refuse)\s+the\s+(?:appeal|petition|application)", text_lower):
        if "anticipatory bail" in text_lower:
            return "refused"

    # Priority 5: appeal dismissed (lower order upheld)
    if re.search(r"appeal\s+(?:is\s+)?dismissed", text_lower):
        return "dismissed"

    return None


def _backfill_truncated_headnote_points(
    points: list[dict],
    paragraphs: list[dict]
) -> list[dict]:
    """
    Some PDFs have headnote points that end with a bare "Rs." because the
    vendor's headnote itself is truncated at a page boundary in the source PDF.
    The actual amounts only appear in the judgment paragraphs.

    This function detects truncated points (ending with bare "Rs." + no digits
    following) and replaces them with the corresponding sentence from the
    judgment paragraphs that contains the same factual context.

    Matching strategy: find the judgment paragraph whose text has the most
    word overlap with the truncated headnote point's text (excluding stopwords).
    """
    TRUNCATION_SIGNAL = re.compile(r"Rs\.?\s*$")
    STOPWORDS = {"the", "a", "an", "and", "or", "of", "in", "to", "is", "was",
                 "be", "for", "on", "at", "by", "as", "it", "that", "this",
                 "with", "from", "are", "were", "has", "have", "had", "not"}

    def _keywords(text: str) -> set[str]:
        words = re.findall(r"\b[a-z]{4,}\b", text.lower())
        return {w for w in words if w not in STOPWORDS}

    def _best_matching_para(point_text: str) -> str | None:
        point_keys = _keywords(point_text)
        if not point_keys:
            return None
        best_score = 0
        best_text = None
        for para in paragraphs:
            para_keys = _keywords(para["text"])
            overlap = len(point_keys & para_keys)
            if overlap > best_score:
                best_score = overlap
                best_text = para["text"]
        # Only substitute if meaningful overlap (>= 3 keywords in common)
        return best_text if best_score >= 3 else None

    fixed = []
    any_fixed = False
    for pt in points:
        text = pt["text"]
        if TRUNCATION_SIGNAL.search(text.rstrip()):
            # Find the best matching paragraph
            replacement = _best_matching_para(text)
            if replacement:
                fixed.append({"label": pt["label"], "text": replacement})
                any_fixed = True
            else:
                fixed.append(pt)  # can't fix, keep as-is
        else:
            fixed.append(pt)

    return fixed, any_fixed


def _extract_bail_conditions(paragraphs: list[dict]) -> list[str]:
    """
    Extract the specific conditions imposed on the bail grant as clean sentences.

    Sentence splitting uses a negative lookbehind to avoid splitting on Rs.N,
    abbreviations like S.438, Cr.P.C., etc.
    """
    # Sentence boundary: period followed by space/newline, BUT NOT when period
    # is preceded by a digit (Rs.50,000), a single letter (S.438, J., JJ.), or "Cr"
    sentence_split_pattern = re.compile(
        r"(?<![A-Za-z]\.[A-Za-z])"   # not abbreviation like Cr.P
        r"(?<!Rs)"                    # not Rs.
        r"(?<!\d)"                    # not digit (e.g. 50,000.)
        r"\.\s+",
        re.IGNORECASE
    )

    condition_patterns = [
        r"(?:personal|self)[- ]bond.{0,120}",
        r"(?:one\s+)?surety.{5,120}",
        r"cooperat\w+\s+(?:with|for)\s+(?:the\s+)?investigation.{0,100}",
        r"abide\s+by\s+(?:all\s+)?(?:the\s+)?conditions.{0,80}438.{0,60}",
        r"(?:not\s+)?(?:leave|travel)\s+(?:the\s+)?(?:country|jurisdiction).{0,80}",
        r"surrender.{0,30}passport.{0,80}",
        r"report(?:ing)?\s+to\s+(?:the\s+)?(?:police|station|SHO|officer).{0,80}",
        r"(?:not\s+)?tamper\s+with.{0,60}(?:evidence|witness).{0,60}",
        r"execute\s+(?:personal\s+)?bond[s]?\s+of\s+Rs.{0,60}",
    ]

    # Only look at paragraphs that contain condition language — skip background/fact paras
    # A condition paragraph typically contains "condition", "on condition", "shall",
    # "abide", "execute", "bond", "surety", "cooperat"
    condition_para_signals = re.compile(
        r"\bon\s+condition\b|\bshall\s+(?:abide|execute|cooperate|furnish|not\s+(?:leave|travel))"
        r"|\bpersonal\s+bond\b|\bself.bond\b|\bsurety\b|\babide\s+by\b|\bexecute\s+bond",
        re.IGNORECASE
    )

    found: list[str] = []
    seen: set[str] = set()

    for para in paragraphs:
        text = para["text"]

        # Skip paragraphs that are clearly background/factual (not condition paragraphs)
        if not condition_para_signals.search(text):
            continue

        sentences = sentence_split_pattern.split(text)
        for sentence in sentences:
            sentence = re.sub(r"\s+", " ", sentence).strip()
            if not sentence or len(sentence) < 20:
                continue
            sentence_lower = sentence.lower()
            for pattern in condition_patterns:
                if re.search(pattern, sentence_lower):
                    if sentence_lower not in seen:
                        seen.add(sentence_lower)
                        found.append(sentence)
                    break

    return found


def _extract_dispute_nature(paragraphs: list[dict]) -> str | None:
    """
    Heuristic classification of the underlying dispute type.
    Useful for grouping cases by fact pattern for fine-tuning variety.
    """
    all_text = " ".join(p["text"] for p in paragraphs).lower()

    patterns = [
        (r"civil\s+(?:dispute|suit|nature)", "civil dispute"),
        (r"land|property|agricultural\s+land", "property/land dispute"),
        (r"matrimonial|divorce|dowry", "matrimonial"),
        (r"cheating|fraud|criminal\s+breach\s+of\s+trust", "cheating/fraud"),
        (r"murder|culpable\s+homicide", "homicide"),
        (r"assault|hurt|bodily", "assault/hurt"),
        (r"sexual\s+assault|rape|pocso", "sexual offence"),
        (r"drug|ndps|narcotic", "NDPS/drugs"),
        (r"corruption|bribery|prevention\s+of\s+corruption", "corruption"),
        (r"financial\s+(?:fraud|offence)|money\s+laundering|pmla", "financial crime"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, all_text):
            return label
    return None


def _extract_ratio_decidendi(paragraphs: list[dict]) -> tuple[str | None, str | None]:
    """
    Find the paragraph containing the generalizable legal principle (ratio).

    Signal phrases — ordered by reliability:
    1. "it is well settled"  — highest signal, direct statement of settled law
    2. "factors to be taken into consideration"  — classic bail factor enumeration
    3. "this court has consistently held"
    4. "it has been held by this court"
    5. "the law is well established"
    6. "on the facts and circumstances" — lower signal, also appears in factual paras

    Returns (paragraph_text, paragraph_number) or (None, None).
    """
    ratio_signals = [
        ("it is well settled", 10),
        ("factors to be taken into consideration", 9),
        ("this court has consistently held", 9),
        ("it has been held by this court", 8),
        ("it has been consistently held", 8),
        ("the law is well established", 8),
        ("criminal proceedings are not for realization", 9),
        ("bail is the rule", 8),
        ("personal liberty", 6),
    ]

    best_score = 0
    best_para_text = None
    best_para_num = None

    for para in paragraphs:
        text_lower = para["text"].lower()
        score = sum(
            weight for signal, weight in ratio_signals
            if signal in text_lower
        )
        if score > best_score:
            best_score = score
            best_para_text = para["text"]
            best_para_num = para["number"]

    if best_score > 0:
        return best_para_text, best_para_num

    # Fallback: no high-signal phrase found (short disposal orders).
    # Use the last substantive paragraph — defined as the last paragraph
    # that is neither a one-line disposal sentence nor a bare condition reference.
    DISPOSAL_PATTERNS = re.compile(
        r"^(?:leave granted|heard learned|appeal(?:s)? (?:is|are) (?:allowed|disposed|dismissed)"
        r"|petition (?:is )?(?:allowed|disposed|dismissed)"
        r"|pending applications|disposed of in the above terms"
        r"|.*abide by.*438.*|.*section 438.*conditions.*)\s*\.?\s*$",
        re.IGNORECASE | re.DOTALL
    )
    for para in reversed(paragraphs):
        text = para["text"].strip()
        if not DISPOSAL_PATTERNS.match(text) and len(text) > 60:
            return text, para["number"]

    return None, None


def _extract_cited_judgments(raw: str) -> list[str]:
    """
    Parse 'Cited Judgement(s) :' block.
    Handles line-wrapped entries — lines without a leading '- ' are continuations
    of the previous item.
    """
    items = []
    current = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            if current:
                items.append(current.strip())
            current = line[2:].strip()
        else:
            # Continuation line
            if current:
                current = current + " " + line
    if current:
        items.append(current.strip())
    return [i for i in items if i]


def _extract_equivalent_citations(raw: str) -> list[str]:
    """
    Parse 'Equivalent Citation :' block.
    Items are comma-separated but may be multi-line.
    Handles split artefacts like "GLHEL- 2005-0-35687" (hyphen at line end).
    """
    # Join all lines first, then split on commas
    joined = re.sub(r"-\s*\n\s*", "-", raw)  # heal hyphenated line wraps
    joined = re.sub(r"\s+", " ", joined)
    items = [c.strip() for c in joined.split(",") if c.strip()]
    # Filter out fragments that are clearly broken (less than 6 chars)
    return [i for i in items if len(i) >= 6]


def _parse_year(date_str: str | None) -> int | None:
    """Extract the 4-digit year from a date string for train/val/test splitting."""
    if not date_str:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", date_str)
    return int(match.group()) if match else None


def _infer_verdict_from_paragraphs(paragraphs: list[dict]) -> str | None:
    """
    Fallback for PDFs without a 'Final Verdict :' header.
    Checks last 3 paragraphs first, then earlier ones.
    """
    verdict_patterns = [
        (r"appeal[s]?\s+(?:is|are)\s+(?:accordingly\s+)?disposed", "Appeal disposed"),
        (r"appeal[s]?\s+(?:is|are)\s+(?:accordingly\s+)?allowed", "Appeal allowed"),
        (r"appeal[s]?\s+(?:is|are)\s+(?:accordingly\s+)?dismissed", "Appeal dismissed"),
        (r"disposed\s+of\s+in\s+the\s+above\s+terms", "Appeal disposed"),
        (r"petition\s+(?:is\s+)?disposed", "Petition disposed"),
        (r"petition\s+(?:is\s+)?allowed", "Petition allowed"),
        (r"petition\s+(?:is\s+)?dismissed", "Petition dismissed"),
        (r"slp\s+(?:is\s+)?disposed", "SLP disposed"),
        (r"slp\s+(?:is\s+)?dismissed", "SLP dismissed"),
    ]
    check_order = paragraphs[-3:] + paragraphs[:-3]
    for para in check_order:
        text_lower = para["text"].lower()
        for pattern, label in verdict_patterns:
            if re.search(pattern, text_lower):
                return label
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def extract_fields(clean_text: str, source_file: str, extraction_path: str) -> CaseRecord:
    """
    Main extraction function. Given a cleaned full-document string, extract
    all fields into a CaseRecord.

    Call order matters for derived fields:
      1. Split on anchors (prerequisite for all field extraction)
      2. Header/party fields (from anchor-delimited blocks)
      3. Judgment body (paragraphs needed for monetary, outcome, ratio)
      4. Derived fields (depend on paragraphs being populated)
      5. Quality flags (depend on all fields being attempted)
    """
    record = CaseRecord(
        source_file=source_file,
        extraction_path=extraction_path,
    )

    sections = _split_on_anchors(clean_text)
    before_first = sections.get("_before_first", "")

    # ── 1. Header fields ───────────────────────────────────────────────────
    record.case_citation = _extract_case_citation(before_first)
    record.court = _extract_court(before_first)

    coram_raw = sections.get("Coram :", "")
    record.coram = coram_raw.splitlines()[0].strip() if coram_raw else None

    decided_raw = sections.get("Decided On :", "")
    record.decided_on = decided_raw.splitlines()[0].strip() if decided_raw else None
    record.decided_on_year = _parse_year(record.decided_on)

    # Appeal type: may wrap across lines — collect all lines
    appeal_raw = sections.get("Appeal Type :", "")
    record.appeal_type = _extract_multiline_field(appeal_raw) if appeal_raw else None

    final_verdict_raw = sections.get("Final Verdict :", "")
    record.final_verdict = final_verdict_raw.splitlines()[0].strip() if final_verdict_raw else None

    # ── 2. Parties ─────────────────────────────────────────────────────────
    appellant_raw = sections.get("Appellant(s) :", "")
    record.appellant = appellant_raw.splitlines()[0].strip() if appellant_raw else None

    respondent_raw = sections.get("Respondent(s) :", "")
    record.respondent = respondent_raw.splitlines()[0].strip() if respondent_raw else None

    advocates_raw = sections.get("Advocate(s) :", "")
    record.advocates = advocates_raw.strip() if advocates_raw else None

    # ── 3. Citations ───────────────────────────────────────────────────────
    equiv_raw = sections.get("Equivalent Citation :", "")
    if equiv_raw:
        record.equivalent_citations = _extract_equivalent_citations(equiv_raw)

    cited_raw = sections.get("Cited Judgement(s) :", "")
    if cited_raw:
        record.cited_judgments = _extract_cited_judgments(cited_raw)

    # ── 4. Referred acts ───────────────────────────────────────────────────
    acts_raw = sections.get("Referred Act(s) :", "")
    record.referred_acts = _extract_referred_acts(acts_raw) if acts_raw else []

    # ── 5. Headnote ────────────────────────────────────────────────────────
    headnote_raw = sections.get("Headnote:", "")
    if headnote_raw:
        points, raw_clean = _parse_headnote_points(headnote_raw)
        record.headnote_raw = raw_clean
        record.headnote_points = points

    # ── 6. Judgment body ───────────────────────────────────────────────────
    judgment_raw = sections.get("Judgment :", "")
    if judgment_raw:
        author, paragraphs = _extract_judgment_author_and_paragraphs(judgment_raw)
        record.judgment_author = author
        record.numbered_paragraphs = paragraphs

    # ── 6b. Backfill truncated headnote points from judgment paragraphs ────
    if record.headnote_points and record.numbered_paragraphs:
        fixed_points, was_fixed = _backfill_truncated_headnote_points(
            record.headnote_points, record.numbered_paragraphs
        )
        if was_fixed:
            # Deduplicate post-backfill (two truncated points may map to same paragraph)
            seen_norm: set[str] = set()
            deduped = []
            for pt in fixed_points:
                norm = re.sub(r"\s+", " ", pt["text"]).strip()
                if norm not in seen_norm:
                    deduped.append(pt)
                    seen_norm.add(norm)
            record.headnote_points = deduped
            # Rebuild headnote_raw as one continuous text from unique points
            record.headnote_raw = " ".join(
                pt["label"] + ". " + re.sub(r"\s+", " ", pt["text"]).strip()
                for pt in deduped
            )
            record.warnings.append(
                "headnote_points backfilled from judgment paragraphs "
                "(source PDF had truncated headnote at page boundary)"
            )

    # ── 7. Final verdict fallback (if no header line) ──────────────────────
    if not record.final_verdict and record.numbered_paragraphs:
        record.final_verdict = _infer_verdict_from_paragraphs(record.numbered_paragraphs)

    # ── 9. Bail outcome classification ─────────────────────────────────────
    record.bail_outcome = _determine_bail_outcome(
        record.numbered_paragraphs, record.headnote_raw
    )

    # ── 10. Bail conditions ────────────────────────────────────────────────
    record.bail_conditions = _extract_bail_conditions(record.numbered_paragraphs)

    # ── 8. Derived monetary fields ─────────────────────────────────────────
    if record.numbered_paragraphs:
        orig, modified = _extract_monetary_amounts(record.numbered_paragraphs)
        record.bail_amount_original = orig
        record.bail_amount_modified = modified
        # For deletion outcomes: modified is None (condition removed, not replaced)
        if record.bail_outcome == "deleted":
            record.bail_amount_modified = None
        record.bail_amount_original_normalized = record.bail_amount_original
        record.bail_amount_modified_normalized = record.bail_amount_modified

    # ── 11. Ratio decidendi ────────────────────────────────────────────────
    ratio_text, ratio_num = _extract_ratio_decidendi(record.numbered_paragraphs)
    record.ratio_decidendi = ratio_text
    record.ratio_para_number = ratio_num

    # ── 12. Dispute nature ─────────────────────────────────────────────────
    record.dispute_nature = _extract_dispute_nature(record.numbered_paragraphs)

    # ── 13. Quality flags ──────────────────────────────────────────────────
    critical_anchors = ["Referred Act(s) :", "Headnote:", "Judgment :"]
    for anchor in critical_anchors:
        if anchor not in sections:
            record.missing_anchors.append(anchor)

    if not record.has_section_438:
        record.warnings.append(
            "Section 438 not found in referred_acts — "
            "verify this is an anticipatory bail case"
        )

    if record.headnote_raw and not record.headnote_points:
        record.warnings.append(
            "Headnote A/B/C point splitting failed — "
            "headnote_raw preserved but headnote_points is empty"
        )

    if record.numbered_paragraphs and not record.bail_outcome:
        record.warnings.append(
            "Could not determine bail_outcome — "
            "add a signal phrase to _determine_bail_outcome for this case"
        )

    if record.numbered_paragraphs and not record.ratio_decidendi:
        record.warnings.append(
            "No ratio_decidendi found — "
            "case may lack a general principle paragraph"
        )

    return record
