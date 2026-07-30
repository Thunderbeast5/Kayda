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
from .schema import CaseRecord, SECTION_ANCHORS, MODIFICATION_KEYWORDS, ActSection, ProceduralHistory


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
    For fields like Appeal Type that wrap across lines — collect ALL lines.
    Also marks truncated years with a sentinel; extract_fields completes them
    from decided_on_year after that field is populated.
    """
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    result = " ".join(lines)
    # Fix trailing truncated year if it's already complete in raw (rare)
    truncated_year = re.search(r'\bof\s+(1\d|20)\s*$', result)
    if truncated_year:
        full_year = re.search(r'\bof\s+(\d{4})\b', raw)
        if full_year:
            result = result[:truncated_year.start()] + "of " + full_year.group(1)
    return result


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
      "modified"   — existing bail upheld but conditions modified/confirmed with changes
      "deleted"    — onerous condition removed entirely, no replacement amount
      "refused"    — bail refused / cancelled by SC
      "dismissed"  — appeal dismissed (lower court order upheld unchanged)
      "referred"   — matter referred to larger bench (no final order)
      "interim"    — interim protection granted pending further hearing

    Checked in full text of all paragraphs + headnote, in priority order.
    """
    all_text = " ".join(p["text"] for p in paragraphs) + " " + (headnote_raw or "")
    text_lower = all_text.lower()

    # ── Priority 1: Referral to larger bench ──────────────────────────────
    if re.search(r"refer\w*\s+(?:the\s+)?(?:following\s+)?questions?\s+for\s+consideration", text_lower):
        return "referred"
    if re.search(r"place\s+(?:the\s+)?papers?\s+before\s+(?:hon'?ble\s+)?the\s+chief\s+justice", text_lower):
        return "referred"
    if re.search(r"refer\w*\s+to\s+a\s+(?:larger|constitution|five.judge|seven.judge)\s+bench", text_lower):
        return "referred"

    # ── Priority 2: Interim protection ────────────────────────────────────
    if re.search(r"(?:grant|extend|interim)\s+(?:interim\s+)?protection\s+from\s+arrest", text_lower):
        return "interim"
    if re.search(r"interim\s+(?:anticipatory\s+)?bail\s+(?:is\s+)?(?:granted|extended)", text_lower):
        return "interim"

    # ── Priority 3: Cancellation / refusal of bail ────────────────────────
    if re.search(r"cancel(?:l(?:ing|ed|ation))?\s+(?:the\s+)?(?:anticipatory\s+)?bail", text_lower):
        return "refused"
    if re.search(r"(?:set\s+aside|quash(?:ing|ed)?)\s+(?:the\s+)?(?:order\s+)?(?:of|granting)\s+anticipatory\s+bail", text_lower):
        return "refused"
    if re.search(r"bail\s+is\s+(?:hereby\s+)?(?:refused|rejected|denied)", text_lower):
        return "refused"
    # "allow appeal AND quash/dismiss/upset bail order" = bail refused
    if re.search(r"(?:quash|upset|set\s+aside)\s+the\s+impugned\s+order\s+and\s+dismiss\s+the\s+application", text_lower):
        return "refused"
    if re.search(r"dismiss\s+the\s+application\s+(?:of\s+the\s+respondent\s+)?filed\s+under\s+s\.\s*438", text_lower):
        return "refused"
    if re.search(r"quash\s+the\s+order\s+of\s+the\s+high\s+court\s+granting\s+anticipatory\s+bail", text_lower):
        return "refused"
    if re.search(r"(?:petition|application)\s+(?:for\s+anticipatory\s+bail\s+)?(?:is\s+)?dismissed", text_lower):
        return "refused"

    # ── Priority 4: Explicit deletion of an onerous condition ────────────
    if re.search(r"delet(?:e|ing|ed)\s+the\s+(?:direction|condition|requirement)\s+to\s+deposit", text_lower):
        return "deleted"
    if re.search(r"(?:set\s+aside|struck\s+down|quash(?:ed)?)\s+the\s+condition\s+of\s+deposit", text_lower):
        return "deleted"
    if re.search(r"without\s+(?:the\s+)?condition\s+(?:of\s+)?deposit", text_lower):
        return "deleted"

    # ── Priority 5: Modification of conditions ────────────────────────────
    if re.search(r"in\s+modification\s+of", text_lower):
        return "modified"
    if re.search(r"modif(?:y|ying|ied|ication|ies)\s+the\s+(?:impugned|said|order\s+of|conditions?)", text_lower):
        return "modified"
    if re.search(r"modified\s+to\s+the\s+extent\s+indicated", text_lower):
        return "modified"
    if re.search(r"appeal(?:s)?\s+(?:is|are)\s+allowed\s+in\s+part", text_lower):
        return "modified"
    if re.search(r"while\s+confirming\s+the\s+order\s+granting\s+anticipatory\s+bail", text_lower):
        return "modified"
    if re.search(r"subject\s+to\s+(?:the\s+)?(?:following\s+)?(?:modified\s+)?conditions?", text_lower):
        return "modified"
    if re.search(r"conditions?\s+(?:are|is)\s+(?:hereby\s+)?modified", text_lower):
        return "modified"

    # ── Priority 6: Fresh grant of bail ───────────────────────────────────
    if re.search(r"(?:we\s+)?grant\s+anticipatory\s+bail\s+to\s+the\s+(?:appellant|petitioner|accused)", text_lower):
        return "granted"
    if re.search(r"allow\s+the\s+appeal[s]?\s+and\s+grant\s+anticipatory\s+bail", text_lower):
        return "granted"
    if re.search(r"(?:petition|application)\s+(?:for\s+anticipatory\s+bail\s+)?is\s+(?:hereby\s+)?allowed", text_lower):
        return "granted"
    if re.search(r"anticipatory\s+bail\s+is\s+(?:hereby\s+)?granted", text_lower):
        return "granted"
    if re.search(r"(?:we\s+)?accede\s+to\s+the\s+request\s+.*\s+grant\s+(?:them\s+)?anticipatory\s+bail", text_lower):
        return "granted"
    # "order release of the petitioner" — short-form bail grant
    if re.search(r"order\s+release\s+of\s+the\s+(?:petitioner|appellant|accused)", text_lower):
        return "granted"
    # "appeal allowed" + giving fresh bail conditions = granted
    if re.search(r"appeal(?:s)?\s+(?:is|are)\s+allowed", text_lower):
        if re.search(r"(?:shall|will|directed\s+to)\s+(?:abide|comply|cooperate|execute\s+bond|furnish)", text_lower):
            return "granted"
    # "allowed to the extent indicated" with "continue on bail" = granted/modified
    if re.search(r"allowed\s+to\s+the\s+extent\s+indicated", text_lower):
        return "modified"

    # ── Priority 7: Dismissal ─────────────────────────────────────────────
    if re.search(r"appeal(?:s)?\s+(?:is|are)\s+(?:hereby\s+)?dismissed", text_lower):
        return "dismissed"
    if re.search(r"special\s+leave\s+petition\s+(?:is\s+)?dismissed", text_lower):
        return "dismissed"
    if re.search(r"no\s+(?:ground|reason|merit)\s+to\s+interfere", text_lower):
        return "dismissed"
    if re.search(r"we\s+(?:do\s+not\s+find|find\s+no)\s+(?:any\s+)?(?:reason|ground|merit)\s+to\s+(?:grant|allow)", text_lower):
        return "dismissed"
    if re.search(r"not\s+a\s+case\s+for\s+exercising\s+the\s+direction\s+under\s+section\s+438", text_lower):
        return "refused"

    # ── Priority 8: Remand / set aside for fresh consideration ───────────
    if re.search(r"remand\s+(?:the\s+)?matter\s+to\s+the\s+high\s+court\s+for\s+fresh", text_lower):
        return "modified"  # outcome uncertain — classify as modified (court order disturbed)
    if re.search(r"set\s+aside\s+the\s+order\s+of\s+the\s+high\s+court\s+and\s+remand", text_lower):
        return "modified"
    # "set aside the impugned orders" — SC overturns HC's bail-related direction
    if re.search(r"set\s+aside\s+the\s+impugned\s+orders", text_lower):
        return "modified"
    # "appeal allowed" as catch-all when no more specific pattern matched
    if re.search(r"appeal(?:s)?\s+(?:is|are)\s+allowed", text_lower):
        return "granted"

    # ── Priority 8: Disposed (catch-all for non-categorised disposals) ────
    # "disposed" alone is ambiguous — only use if we also see direction language
    if re.search(r"appeal(?:s)?\s+(?:is|are)\s+(?:accordingly\s+)?disposed", text_lower):
        # Try to infer from what the court directed
        if re.search(r"(?:shall|directed\s+to)\s+(?:abide|comply|execute\s+bond|furnish\s+bail|cooperate)", text_lower):
            return "granted"
        if re.search(r"no\s+(?:further|other)\s+condition|conditions?\s+(?:stand|remain)\s+vacated", text_lower):
            return "deleted"
        return "modified"  # disposing an appeal against bail order = some form of modification

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

def _extract_act_sections(full_text: str, paragraphs: list[dict]) -> list[dict]:
    """
    Extract structured IPC and CrPC section references from the full judgment text.

    Patterns handled:
      IPC: "Section 376 IPC", "Ss. 302 and 34 IPC", "under S. 376 of the IPC",
           "Sections 376, 506 of the Indian Penal Code"
      CrPC: "Section 438 CrPC", "under S. 438 of the Cr.P.C.",
            "Section 438 of the Code of Criminal Procedure"
      BNS: "Section 64 BNS" (Bharatiya Nyaya Sanhita — new IPC replacement)

    Returns list of dicts (serialized ActSection objects).
    """
    # Known section titles — expand as more cases are processed
    IPC_TITLES: dict[str, str] = {
        "302": "Punishment for murder",
        "304": "Punishment for culpable homicide not amounting to murder",
        "304B": "Dowry death",
        "306": "Abetment of suicide",
        "307": "Attempt to murder",
        "324": "Voluntarily causing hurt",
        "326": "Voluntarily causing grievous hurt",
        "354": "Assault or criminal force to woman with intent to outrage her modesty",
        "363": "Punishment for kidnapping",
        "376": "Punishment for rape",
        "376A": "Punishment for causing death or resulting in persistent vegetative state",
        "376D": "Gang rape",
        "379": "Punishment for theft",
        "384": "Punishment for extortion",
        "406": "Punishment for criminal breach of trust",
        "420": "Cheating and dishonestly inducing delivery of property",
        "426": "Punishment for mischief",
        "467": "Forgery of valuable security",
        "468": "Forgery for purpose of cheating",
        "471": "Using as genuine a forged document",
        "489A": "Counterfeiting currency notes",
        "498A": "Husband or relative of husband of a woman subjecting her to cruelty",
        "506": "Punishment for criminal intimidation",
        "509": "Word, gesture or act intended to insult the modesty of a woman",
        "34": "Acts done by several persons in furtherance of common intention",
        "120B": "Punishment of criminal conspiracy",
    }

    CRPC_TITLES: dict[str, str] = {
        "41": "When police may arrest without warrant",
        "154": "Information in cognizable cases (FIR)",
        "156": "Police officer's power to investigate cognizable case",
        "161": "Examination of witnesses by police",
        "164": "Recording of confessions and statements",
        "173": "Report of police officer on completion of investigation",
        "197": "Prosecution of Judges and public servants",
        "204": "Issue of process",
        "227": "Discharge",
        "228": "Framing of charge",
        "239": "When accused shall be discharged",
        "240": "Framing of charge",
        "309": "Power to postpone or adjourn proceedings",
        "313": "Power to examine the accused",
        "374": "Appeals from convictions",
        "397": "Revision of lower court orders",
        "407": "Power of High Court to transfer cases",
        "437": "When bail may be taken in case of non-bailable offence",
        "437A": "Bail to require accused to appear before next appellate court",
        "438": "Direction for grant of bail to person apprehending arrest",
        "438(2)": "Conditions for anticipatory bail",
        "439": "Special powers of High Court or Court of Session regarding bail",
        "482": "Saving of inherent powers of High Court",
    }

    # Act name normalisation
    ACT_PATTERNS: list[tuple[re.Pattern, str, str, int]] = [
        # pattern, act_name, short_name, year
        (re.compile(r'\bI\.?P\.?C\.?\b|\bIndian\s+Penal\s+Code\b', re.I),
         "Indian Penal Code, 1860", "IPC", 1860),
        (re.compile(r'\bCr\.?P\.?C\.?\b|\bCode\s+of\s+Criminal\s+Procedure\b|\bCriminal\s+Procedure\s+Code\b', re.I),
         "Code of Criminal Procedure, 1973", "CrPC", 1973),
        (re.compile(r'\bB\.?N\.?S\.?\b|\bBharatiya\s+Nyaya\s+Sanhita\b', re.I),
         "Bharatiya Nyaya Sanhita, 2023", "BNS", 2023),
        (re.compile(r'\bB\.?N\.?S\.?S\.?\b|\bBharatiya\s+Nagarik\s+Suraksha\s+Sanhita\b', re.I),
         "Bharatiya Nagarik Suraksha Sanhita, 2023", "BNSS", 2023),
        (re.compile(r'\bN\.?D\.?P\.?S\.?\b|\bNarcotic\s+Drugs\s+and\s+Psychotropic\b', re.I),
         "Narcotic Drugs and Psychotropic Substances Act, 1985", "NDPS", 1985),
        (re.compile(r'\bP\.?C\.?\s*Act\b|\bPrevention\s+of\s+Corruption\b', re.I),
         "Prevention of Corruption Act, 1988", "PCA", 1988),
    ]

    # Section extraction: captures "S.376", "Sec.438", "Section 438(2)", "Ss. 302, 306"
    SECTION_PAT = re.compile(
        r'(?:Sections?\s*|Ss\.\s*|S\.\s*)(\d{1,4}[A-Z]?(?:\s*\(\s*\d+\s*\))?)'
        r'(?:\s*(?:,|and|&)\s*(\d{1,4}[A-Z]?(?:\s*\(\s*\d+\s*\))?))*',
        re.IGNORECASE
    )

    found: list[dict] = []
    seen: set[str] = set()  # deduplicate by (short_name, section)

    # Split text into sentences for context extraction
    sentences = re.split(r'(?<=[.!?])\s+', full_text)

    # Per-section act inference:
    # For each section mention, find the NEAREST act identifier in the same sentence.
    # This correctly handles headnotes like "CrPC S.438 ... IPC S.420" where both
    # acts appear in the same sentence.
    #
    # Strategy: build a list of (position, act_info) for all act mentions in the
    # sentence, then assign each section to the closest preceding act mention.

    for sentence in sentences:
        # Build a positional map of all act mentions in this sentence
        act_positions: list[tuple[int, str, str, int]] = []
        for act_pattern, act_name, short_name, year in ACT_PATTERNS:
            for m in act_pattern.finditer(sentence):
                act_positions.append((m.start(), act_name, short_name, year))

        if not act_positions:
            continue

        # Sort by position
        act_positions.sort(key=lambda x: x[0])

        def _act_for_position(pos: int) -> tuple[str, str, int]:
            """Return act info for the nearest act mention before/at pos."""
            best = act_positions[0]  # default: first act in sentence
            for ap in act_positions:
                if ap[0] <= pos:
                    best = ap
                else:
                    break
            return best[1], best[2], best[3]  # act_name, short_name, year

        # Extract section numbers with position
        for m in SECTION_PAT.finditer(sentence):
            raw_section = re.sub(r"\s+", "", m.group(1)).upper()  # normalise to uppercase
            section_num = re.sub(r"\([^)]+\)", "", raw_section)
            subsection_match = re.search(r"\((\d+)\)", raw_section)
            subsection = subsection_match.group(1) if subsection_match else None

            # Assign to nearest act
            act_name, short_name, year = _act_for_position(m.start())

            # Override: if section is in the authoritative CrPC list, force CrPC
            # regardless of which act appeared nearest (guards against ambiguous sentences)
            AUTHORITATIVE_CRPC = {
                "41", "154", "156", "161", "164", "173", "197", "204",
                "227", "228", "239", "240", "309", "313", "374", "397",
                "407", "437", "438", "439", "482",
            }
            if section_num in AUTHORITATIVE_CRPC:
                act_name = "Code of Criminal Procedure, 1973"
                short_name = "CrPC"
                year = 1973

            key = (short_name, raw_section)
            if key in seen:
                continue
            seen.add(key)

            # Title lookup
            title_map = IPC_TITLES if short_name == "IPC" else CRPC_TITLES
            title = title_map.get(raw_section) or title_map.get(section_num)

            how_used = _infer_section_usage(sentence)
            is_charged = _is_charged(sentence)
            is_interpreted = bool(re.search(
                r'interpret|constru|held that|means|refers to', sentence, re.I
            ))
            is_applied = bool(re.search(
                r'applied|invok|grant|reject|allow|dismiss|under section', sentence, re.I
            ))

            ctx = re.sub(r"\s+", " ", sentence).strip()[:300]

            entry = {
                "act_name":       act_name,
                "act_short_name": short_name,
                "act_year":       year,
                "section":        raw_section,
                "subsection":     subsection,
                "section_title":  title,
                "how_used":       how_used,
                "context":        ctx,
                "is_charged":     is_charged,
                "is_convicted":   False,
                "is_applied":     is_applied,
                "is_interpreted": is_interpreted,
                "interpretation": None,
            }
            found.append(entry)

    return found


def _infer_section_usage(sentence: str) -> str:
    """Classify how a section was used in the sentence."""
    s = sentence.lower()
    if re.search(r'charg|accus|fir|offenc|alleged', s):
        return "Charged"
    if re.search(r'anticipatory bail|bail application|pre.arrest', s):
        return "Applied for bail"
    if re.search(r'interpret|constru|explain|means', s):
        return "Interpreted"
    if re.search(r'invok|appl|under section|pursuant', s):
        return "Applied"
    if re.search(r'refer|cit|mention', s):
        return "Referenced"
    return "Mentioned"


def _is_charged(sentence: str) -> bool:
    """Return True if the sentence indicates a charge was filed under the section."""
    return bool(re.search(
        r'charg(?:ed|es?)\s+under'
        r'|offenc(?:e|es?)\s+under'
        r'|FIR.*(?:under|for)\s+S(?:ec(?:tion)?)?'
        r'|complaint.*(?:under|for)\s+S(?:ec(?:tion)?)?'
        r'|under\s+S(?:ec(?:tion)?)?\s*\d+.*(?:IPC|I\.P\.C|Indian\s+Penal)'
        r'|(?:IPC|I\.P\.C)\s+was\s+filed'
        r'|read\s+with\s+section\s*\d+\s*(?:IPC|I\.P\.C)'
        r'|criminal\s+complaint.*section\s*\d+',
        sentence, re.I | re.DOTALL
    ))


def _extract_procedural_history(full_text: str, paragraphs: list[dict]) -> dict | None:
    """
    Extract the procedural chain: FIR → sessions court → high court.

    Patterns found across the corpus:
      FIR:      "Crime No. 1192 of 2024 dtd. 27/8/2024"
                "FIR No. 16 dated 15.01.2010"
      Station:  "registered at Police Station Museum"
      HC:       "order dated 24/9/2024 passed by the High Court of Kerala"
      Sessions: "Sessions Court ... rejected"
    """
    all_text = " ".join(p["text"] for p in paragraphs) if paragraphs else full_text
    all_text = re.sub(r"\s+", " ", all_text)

    result: dict = {}

    # ── FIR ──────────────────────────────────────────────────────────────
    fir_patterns = [
        r'(?:Crime|FIR|F\.I\.R\.?)\s*No\.?\s*([\w/]+\s+of\s+\d{4}|\d+\s*(?:/\s*\d+)?)',
        r'First\s+Information\s+Report\s*No\.?\s*([\w/]+)',
        r'Crime\s+No\.\s*([\d/]+)',
    ]
    for pat in fir_patterns:
        m = re.search(pat, all_text, re.I)
        if m:
            result["fir_number"] = m.group(1).strip()
            break

    # FIR date
    fir_date_m = re.search(
        r'(?:FIR|F\.I\.R|Crime\s+No\.[^,]{0,40}?)\s+(?:dtd?\.?|dated?)\s+([\d./\-]+(?:\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)?(?:\s*\d{4})?)',
        all_text, re.I
    )
    if fir_date_m:
        result["fir_date"] = fir_date_m.group(1).strip()

    # Police station
    ps_m = re.search(
        r'(?:Police\s+Station|P\.S\.)\s+([A-Z][A-Za-z\s]+?)(?:\s*,|\s+District|\s+in\s|\s+at\s|\.|$)',
        all_text
    )
    if ps_m:
        result["police_station"] = ps_m.group(1).strip()

    # District
    dist_m = re.search(r'District\s+([A-Z][A-Za-z\s]+?)(?:\s*,|\s*\.|$)', all_text)
    if dist_m:
        result["district"] = dist_m.group(1).strip()

    # ── High Court order ─────────────────────────────────────────────────
    hc_m = re.search(
        r'(?:order|judgment)\s+(?:dtd?\.?|dated?)\s+([\d./\-]+)',
        all_text, re.I
    )
    if hc_m:
        result["high_court_order_date"] = hc_m.group(1).strip()

    # High Court name — match greedily up to a comma, period, or line end
    hc_name_m = re.search(
        r'((?:High\s+Court|HC)\s+of\s+[A-Z][A-Za-z\s&]+?'
        r'(?:\s+at\s+[A-Z][A-Za-z]+)?)'
        r'(?=\s*[,\.;]|\s+(?:dated?|by|in|has|had|grant|reject|allow|dismiss|pass)|\s*$)',
        all_text, re.MULTILINE
    )
    if hc_name_m:
        result["high_court_bench"] = re.sub(r"\s+", " ", hc_name_m.group(1)).strip()

    # HC decision on bail
    hc_decision_m = re.search(
        r'High\s+Court\s+(?:has\s+)?(?:grant(?:ed|ing)|reject(?:ed|ing)|dismiss(?:ed|ing)|allow(?:ed|ing))\s+(?:the\s+)?(?:anticipatory\s+)?bail',
        all_text, re.I
    )
    if hc_decision_m:
        result["high_court_decision"] = hc_decision_m.group(0).strip()

    # ── Sessions Court ────────────────────────────────────────────────────
    sess_m = re.search(
        r'(?:Sessions?\s+(?:Court|Judge)|Additional\s+Sessions?\s+Judge)[^.]{0,100}?'
        r'(grant(?:ed|ing)|reject(?:ed|ing)|dismiss(?:ed|ing)|allow(?:ed|ing))',
        all_text, re.I
    )
    if sess_m:
        result["sessions_court_decision"] = sess_m.group(0).strip()[:200]

    return result if result else None


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

    # Complete any truncated appeal year (e.g. "of 20" → "of 2004") using decided_on_year
    if record.appeal_type and record.decided_on_year:
        record.appeal_type = re.sub(
            r'\bof\s+(1\d|20)\s*$',
            f'of {record.decided_on_year}',
            record.appeal_type,
        )

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

    # ── 13. IPC/CrPC section extraction ────────────────────────────────────
    all_text = clean_text
    record.act_sections = _extract_act_sections(all_text, record.numbered_paragraphs)

    # Post-pass: re-check is_charged against judgment paragraphs for any section
    # that was extracted from a non-complaint sentence (e.g. headnote citation block).
    # A section is charged if ANY paragraph in the full text has charge language
    # referencing that section number.
    para_text = " ".join(p["text"] for p in record.numbered_paragraphs)
    for entry in record.act_sections:
        if not entry["is_charged"] and entry["act_short_name"] == "IPC":
            sec = entry["section"]
            # Look for charge language near this section number anywhere in paragraphs
            charge_near_section = re.search(
                r'(?:complaint|FIR|charg|offenc).{0,150}?' + re.escape(sec) +
                r'|' + re.escape(sec) + r'.{0,80}?(?:IPC|Indian\s+Penal)',
                para_text, re.I | re.DOTALL
            )
            if charge_near_section and _is_charged(charge_near_section.group(0)):
                entry["is_charged"] = True
                entry["how_used"] = "Charged"

    record.ipc_sections_mentioned = sorted({
        s["section"] for s in record.act_sections if s.get("act_short_name") == "IPC"
    })
    record.crpc_sections_mentioned = sorted({
        s["section"] for s in record.act_sections if s.get("act_short_name") == "CrPC"
    })

    # ── 14. Procedural history ─────────────────────────────────────────────
    record.procedural_history = _extract_procedural_history(all_text, record.numbered_paragraphs)

    # ── 15. Quality flags ──────────────────────────────────────────────────
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
