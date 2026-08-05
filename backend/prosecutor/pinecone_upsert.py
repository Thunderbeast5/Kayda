"""
IPC → Pinecone Upsert Pipeline  v4
============================================
Changes from v3:
- FIX: State amendments were never captured because the sentinel regex only
  matched "STATE AMENDMENT" (singular). The PDF actually prints
  "STATE AMENDMENTS" (plural). Also, real amendment clauses are numbered
  (1), (2) with nested roman sub-clauses (i), (ii) — NOT named ordinals
  (First/Secondly). The state-amendment parser is rewritten to handle this.
- FIX: Explanation/Illustration/Exception/Proviso are now stored as LISTS.
  Previously, when a section had "Explanation 1", "Explanation 2", ... only
  the last one survived (setattr overwrote the field each loop). Sections
  regularly have 2-5 explanations/illustrations, all are now kept in order.
- NEW: In illustrations, standalone capital letters that are clearly acting
  as party placeholders (e.g. "A is sentenced...", "...A will be discharged")
  are rewritten to "Person A". A letter is left alone if it looks like the
  English article "A" (sentence-initial, single occurrence, followed by a
  noun rather than a verb) — e.g. "A Municipal Commissioner is a public
  servant" is NOT touched.
- NEW: Before embedding, the script writes ipc_structured.json, then STOPS
  and asks you to type "yes" to continue. This gives you a chance to
  hand-edit the JSON (fix a misclassified "A", a mis-parsed amendment, etc.)
  before anything is embedded. The script re-reads the file from disk after
  you confirm, so your edits are what actually gets embedded/upserted.
- ID format: IPC_53(3), IPC_53A(4)(a)  (parentheses, not underscores)
- Named ordinals (First, Secondly …) are NOT structural subsections
"""

import os
import re
import json
import logging
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Optional
from tqdm import tqdm
import time
import fitz
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from pathlib import Path
from dotenv import load_dotenv

# Load .env
for candidate in [
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parents[2] / "backend" / ".env",
    Path("backend/.env"),
    Path(".env"),
]:
    if candidate.exists():
        load_dotenv(candidate)
        break

# ---------- CONFIG ----------
PDF_PATH            = "ipc.pdf"
IPC_START_PAGE       = 13          # 0-indexed → page 14 human
EMBED_MODEL          = "jinaai/jina-embeddings-v3"
EMBED_MAX_SEQ_TOKENS = 1024        # hard cap: prevents one abnormally long node
                                    # (usually a parsing artifact) from blowing up
                                    # attention memory (O(seq_len^2)) for the whole batch
EMBED_BATCH_SIZE     = 16           # smaller batch = smaller worst-case padded batch on CPU
LONG_NODE_WARN_CHARS = 4000         # flag suspiciously long node text for manual review
PINECONE_BATCH_SIZE  = 100
LOG_FILE             = "ipc_parse.log"
STRUCTURED_JSON_PATH = "ipc_structured.json"
# ---------- NEO4J CONFIG ----------
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ---------- DATA MODEL ----------
@dataclass
class IPCNode:
    id:                 str
    chapter:            str           = ""
    chapter_title:      str           = ""
    section_number:     str           = ""
    section_title:      str           = ""
    node_type:          str           = "section"
    parent_id:          Optional[str] = None
    subsection_key:     Optional[str] = None
    text:               str           = ""
    explanation:        list          = field(default_factory=list)
    exception:          list          = field(default_factory=list)
    illustration:       list          = field(default_factory=list)
    proviso:            list          = field(default_factory=list)
    is_state_amendment: bool          = False
    state:              Optional[str] = None
    amended_section:    Optional[str] = None
    citation:           Optional[str] = None   # e.g. "[Vide Karnataka Act 8 of 1972 ...]"
    subsections:        list          = field(default_factory=list)  # merged (1),(2),(a)... content — see collapse_to_section_level
    state_amendments:   dict          = field(default_factory=dict)  # merged per-state amendment content — see collapse_to_section_level
    embedding:          list          = field(default_factory=list)


def node_from_dict(d: dict) -> IPCNode:
    """Rebuild an IPCNode from a (possibly hand-edited) JSON dict.
    Tolerant of missing keys and of old-style string fields for
    explanation/exception/illustration/proviso (auto-wraps into a list)."""
    valid_fields = {f for f in IPCNode.__dataclass_fields__.keys()}
    clean = {k: v for k, v in d.items() if k in valid_fields}
    for list_field in ("explanation", "exception", "illustration", "proviso"):
        v = clean.get(list_field)
        if v is None:
            clean[list_field] = []
        elif isinstance(v, str):
            clean[list_field] = [v] if v.strip() else []
    clean.setdefault("embedding", [])
    return IPCNode(**clean)


# ---------- CONSTANTS & PATTERNS ----------
RE_FOOTNOTE_DIGIT       = re.compile(r'\d{1,3}(?=\[)')
RE_CHAPTER_HEADING      = re.compile(r'^CHAPTER\s+[IVXLC]+$')
RE_SECTION_HEADER       = re.compile(r'^\[?(\d+[A-Z]?)\.\s+(.+)$')
RE_NUMERIC_SUB          = re.compile(r'^\((\d+)\)\s+(.+)$')          # relaxed
RE_ALPHA_SUB            = re.compile(r'^\(([a-z])\)\s+([A-Za-z\[].+)$')
RE_NESTED_SUB           = re.compile(r'^\((\d+)\)\s*\(([a-z])\)\s+([A-Z\[].+)$')

NAMED_SUBSECTIONS = [
    "First", "Second", "Third", "Fourth", "Fifth", "Sixth",
    "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth",
    "Thirteenth", "Fourteenth", "Fifteenth", "Sixteenth",
]
_NAMED_SUB_ALTERNATION = '|'.join(f'{w}ly|{w}' for w in NAMED_SUBSECTIONS)
RE_NAMED_SUB = re.compile(
    r'^(' + _NAMED_SUB_ALTERNATION + r')\s*[,\.—–\-]+\s*(.+)$',
    re.IGNORECASE
)

# STATE AMENDMENTS handling -------------------------------------------------
# NOTE: the PDF prints "STATE AMENDMENTS" (plural). The old regex required an
# exact singular match and so silently never fired.
RE_STATE_AMENDMENT = re.compile(r'^STATE\s+AMENDMENTS?\s*$', re.IGNORECASE)

# A state/UT name line, e.g. "Karnataka", "Uttar Pradesh", "Jammu and Kashmir"
RE_STATE_NAME_LINE = re.compile(
    r'^([A-Z][a-zA-Z\']*(?:\s+(?:and|of|the|&)\s+[A-Z][a-zA-Z\']*|\s+[A-Z][a-zA-Z\']*)*)$'
)
# Real amendment clauses are numbered like this, not "First/Secondly"
RE_STATE_NUMBERED = re.compile(r'^\((\d+)\)\s+(.+)$')
RE_STATE_ROMAN    = re.compile(r'^\((i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\)\s+(.+)$', re.IGNORECASE)
# Amendment lead-in phrases that confirm "this is the start of an amendment
# clause", used to disambiguate a state-name line from ordinary prose
RE_AMEND_LEADIN = re.compile(
    r'^(In\s+section|After\s+section|For\s+section|Before\s+section|'
    r'In\s+the\s+said\s+section|Omit|Insert|Add|Renumber)',
    re.IGNORECASE
)
RE_VIDE_CITATION = re.compile(r'^\[?Vide\b', re.IGNORECASE)

RE_UNICODE_SUP  = re.compile(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]+')
RE_STAR_NOISE   = re.compile(r'\s*\d*\*{1,3}\s*')
RE_PAGE_NUMBER  = re.compile(r'^\d{1,4}$')
RE_FOOTNOTE_LINE = re.compile(
    r'^\d{1,2}\.\s+(?:Subs\.|Ins\.|Omitted|Rep\.|Added|w\.e\.f|A\.O\.|Act\s+\d+|Certain)',
    re.IGNORECASE
)
_DASH_RE = re.compile(r'[—–]')

# ---------- ILLUSTRATION: standalone-letter → "Person X" ----------
# Verbs/auxiliaries that, when they follow a sentence-initial capital letter,
# indicate the letter is a party placeholder ("A is sentenced...", "A
# commits...") rather than the English article ("A Municipal Commissioner
# is..."). Not exhaustive, but covers the vast majority of IPC illustrations;
# the manual-review step (type "yes" to confirm) is the safety net for the
# rest.
_PARTY_VERB_HINTS = {
    "is", "was", "are", "were", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must", "has", "had", "have", "does", "did",
    "commits", "instigates", "abets", "gives", "gave", "receives", "delivers",
    "procures", "causes", "administers", "throws", "attacks", "strikes",
    "wounds", "kills", "murders", "dies", "agrees", "believes", "intends",
    "knows", "conceals", "steals", "takes", "sets", "buys", "sells", "pays",
    "owes", "lends", "borrows", "forges", "entrusts", "deceives", "cheats",
    "threatens", "assaults", "robs", "kidnaps", "abducts", "poisons",
    "marries", "contracts", "promises", "obtains", "executes", "signs",
    "applies", "uses", "employs", "exhibits", "publishes", "prints",
    "utters", "tenders", "presents", "produces", "shows", "retains",
    "purchases", "accepts", "refuses", "omits", "fails", "neglects",
    "permits", "allows", "suffers", "continues", "remains", "enters",
    "leaves", "induces", "persuades", "directs", "orders", "commands",
    "hires", "engages", "conspires", "aids", "assists", "strikes", "fires",
    "harms", "injures", "discharged", "liable", "guilty", "sentenced",
}
_RE_STANDALONE_LETTER = re.compile(r'(?<![A-Za-z0-9])([A-Z])(?![A-Za-z0-9])')


def humanize_illustration(text: str) -> str:
    """Rewrite standalone capital letters used as party placeholders
    (A, B, C, Z ...) into 'Person A', 'Person B' etc. Leaves alone cases
    that look like the English article 'A' (e.g. 'A Municipal Commissioner
    is a public servant')."""
    if not text:
        return text

    letters = _RE_STANDALONE_LETTER.findall(text)
    freq = Counter(letters)

    def repl(m: re.Match) -> str:
        letter = m.group(1)
        start = m.start(1)
        end = m.end(1)

        # Skip abbreviation-style refs like "S. 34" (Section 34)
        tail = text[end:end + 3]
        if tail.startswith('.') and re.match(r'\.\s*\d', tail):
            return letter

        before = text[:start].rstrip()
        is_sentence_start = (start == 0) or (before and before[-1] in '.!?—–\n')

        if is_sentence_start and freq[letter] <= 1:
            after = text[end:].lstrip()
            next_word_match = re.match(r"[A-Za-z']+", after)
            next_word = next_word_match.group(0).lower() if next_word_match else ""
            if next_word not in _PARTY_VERB_HINTS:
                # Looks like the article "A", not a party name — leave as-is
                return letter

        return f"Person {letter}"

    return _RE_STANDALONE_LETTER.sub(repl, text)


# ---------- STEP 1: PDF EXTRACTION ----------
def extract_structured_text(pdf_path: str, start_page: int) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(start_page, len(doc)):
        page = doc[i]
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        page_lines = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                line_bold = any(bool(s.get("flags", 0) & 16) for s in spans)
                line_italic = all(bool(s.get("flags", 0) & 2) for s in spans if s.get("text", "").strip())
                line_text = "".join(s.get("text", "") for s in spans).strip()
                if line_text:
                    page_lines.append({
                        "text": line_text,
                        "bold": line_bold,
                        "italic": line_italic,
                    })
        if page_lines:
            pages.append({"page_num": i + 1, "lines": page_lines})
    log.info(f"Extracted {len(pages)} pages from PDF")
    return pages

def pages_to_tagged_text(pages: list[dict]) -> str:
    parts = []
    for page in pages:
        parts.append(f"\n[PAGE {page['page_num']}]\n")
        for line in page["lines"]:
            text = line["text"].strip()
            if not text:
                continue

            text = RE_UNICODE_SUP.sub("", text)
            text = RE_FOOTNOTE_DIGIT.sub("", text)
            # Strip footnote digit before "(number)" e.g. "4 (4)" -> "(4)"
            text = re.sub(r'^\d+\s*(\(\d+\))', r'\1', text)
            text = re.sub(r'^\d+(\(\d+\))', r'\1', text)
            text = RE_STAR_NOISE.sub(" ", text).strip()

            if RE_PAGE_NUMBER.match(text):
                continue
            if RE_FOOTNOTE_LINE.match(text):
                continue
            if not text:
                continue

            if line["bold"]:
                parts.append(f"§§{text}§§")
            elif line["italic"]:
                parts.append(f"@@{text}@@")
            else:
                parts.append(text)

    return "\n".join(parts)

# ---------- STEP 2: PARSER ----------
class IPCParser:
    KIND_NUMERIC = 2
    KIND_ALPHA   = 3

    def __init__(self):
        self.nodes:                 list[IPCNode]     = []
        self.current_chapter:       str               = ""
        self.current_chapter_title: str               = ""
        self.current_section:       Optional[IPCNode] = None
        self.in_state_amendment:    bool              = False
        self.current_state:         str               = ""
        self._sa_container:         Optional[IPCNode] = None   # per-state container node
        self._sa_item:               Optional[IPCNode] = None  # current numbered (1),(2) item
        self._sa_subitem:            Optional[IPCNode] = None  # current roman (i),(ii) subitem
        self._stack:                list              = []
        self._seen_ids:             set               = set()
        self._pending:              list[str]         = []
        self._section_has_named_ordinals: bool = False

    # ---- helpers ----
    def _detect_named_ordinal(self, text: str) -> bool:
        pattern = r'\b(First|Secondly?|Thirdly?|Fourthly?|Fifthly?|Sixthly?|Seventhly?|Eighthly?|Ninthly?|Tenthly?|Eleventhly?|Twelfthly?|Thirteenthly?|Fourteenthly?|Fifteenthly?|Sixteenthly?)\b'
        return bool(re.search(pattern, text, re.IGNORECASE))

    def _lookahead_for_named_ordinal(self, lines: list[str], start_idx: int) -> bool:
        for i in range(start_idx, min(start_idx + 30, len(lines))):
            line = lines[i].strip()
            if line.startswith("§§") and line.endswith("§§"):
                inner = line[2:-2].strip()
                if re.match(r'^\d+[A-Z]?\.', inner):
                    break
            if self._detect_named_ordinal(line):
                return True
        return False

    def _register_id(self, node_id: str) -> bool:
        if node_id in self._seen_ids:
            log.warning(f"ID already registered, skipping: {node_id}")
            return False
        self._seen_ids.add(node_id)
        return True

    def _flush_pending(self):
        if not self._pending:
            return
        text = "\n".join(l.strip() for l in self._pending if l.strip())
        self._pending = []
        if not text:
            return
        if self.in_state_amendment:
            target = self._sa_subitem or self._sa_item or self._sa_container
        else:
            target = self._stack[-1][0] if self._stack else self.current_section
        if target:
            target.text = (target.text + "\n" + text).strip() if target.text else text

    # ---- main parse ----
    def parse(self, tagged_text: str) -> list[IPCNode]:
        lines = tagged_text.split("\n")
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.strip()
            i += 1
            if not line or line.startswith("[PAGE"):
                continue
            self._dispatch(line, lines, i)
        self._flush_pending()
        self._post_process_legal_elements()
        return self.nodes

    # ---- dispatcher ----
    def _dispatch(self, line: str, lines: list[str], next_i: int):
        # Tag-stripped view of this line. Headings like "CHAPTER I" and
        # "STATE AMENDMENTS" are printed BOLD in the PDF, so the raw line
        # actually arrives as "§§CHAPTER I§§" / "§§STATE AMENDMENTS§§". The
        # sentinel regexes must be tested against the stripped text, not the
        # tagged raw line, or they silently never match (this was the actual
        # reason state amendments were never detected before).
        _plain_for_sentinel = line
        if (line.startswith("§§") and line.endswith("§§")) or (line.startswith("@@") and line.endswith("@@")):
            _plain_for_sentinel = line[2:-2].strip()

        # 1. Chapter heading
        if RE_CHAPTER_HEADING.match(_plain_for_sentinel):
            self._flush_pending()
            self.current_chapter = _plain_for_sentinel.strip()
            for j in range(next_i, min(next_i + 5, len(lines))):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("[PAGE") and not RE_CHAPTER_HEADING.match(nxt.strip("§§").strip("@@").strip()):
                    self.current_chapter_title = nxt.strip("§§").strip("@@").strip()
                    break
            return

        # 2. STATE AMENDMENTS sentinel (handles being hit again for a 2nd state
        #    under the same section)
        if RE_STATE_AMENDMENT.match(_plain_for_sentinel):
            self._flush_pending()
            self.in_state_amendment = True
            self.current_state = ""
            self._sa_container = None
            self._sa_item = None
            self._sa_subitem = None
            return

        # 3. Inside a state-amendment block
        if self.in_state_amendment:
            self._sa_line_count = getattr(self, "_sa_line_count", 0) + 1
            plain = line.strip("§§").strip("@@").strip()

            # 3a. A bold section header OR a bold chapter heading ends the
            # amendment block outright (both are legitimate ways a state-
            # amendment block can end in the source PDF)
            if line.startswith("§§") and line.endswith("§§"):
                inner = line[2:-2].strip()
                if RE_SECTION_HEADER.match(inner) or RE_CHAPTER_HEADING.match(inner):
                    self.in_state_amendment = False
                    self._sa_line_count = 0
                    # fall through to normal dispatch for this line (below)
                else:
                    self._pending.append(inner)
                    return
            else:
                # 3a-safety: if we've gone a very long stretch inside a
                # state-amendment block without it closing, something didn't
                # match as expected (unusual PDF formatting). Force-exit
                # rather than silently swallowing the rest of the document
                # into one giant node.
                if self._sa_line_count > 200:
                    log.warning(
                        "State-amendment block open for >200 lines without closing — "
                        "forcing exit to avoid swallowing subsequent content. "
                        "Check ipc_structured.json around this point."
                    )
                    self.in_state_amendment = False
                    self._sa_line_count = 0
                    # do NOT return — let this line fall through to normal dispatch (below)
                else:
                    # 3b. Vide citation (e.g. "[Vide Karnataka Act 8 of 1972 ...]")
                    if RE_VIDE_CITATION.match(plain):
                        self._flush_pending()
                        target = self._sa_item or self._sa_container
                        if target:
                            target.citation = ((target.citation + " ") if target.citation else "") + plain
                        return

                    # 3c. New state name (only when we don't already have one open,
                    #     and the *next* non-empty line confirms it's really a
                    #     state heading and not ordinary prose)
                    if not self.current_state and RE_STATE_NAME_LINE.match(plain) \
                            and len(plain.split()) <= 6 \
                            and not re.search(r'Amendment|Section|Act\b|Central', plain):
                        lookahead_ok = False
                        for j in range(next_i, min(next_i + 3, len(lines))):
                            nxt = lines[j].strip().strip("§§").strip("@@").strip()
                            if not nxt:
                                continue
                            if RE_STATE_NUMBERED.match(nxt) or RE_AMEND_LEADIN.match(nxt):
                                lookahead_ok = True
                            break
                        if lookahead_ok:
                            self._flush_pending()
                            self._start_state_amendment_block(plain)
                            return

                    # 3d. Numbered clause (1), (2) ...
                    m = RE_STATE_NUMBERED.match(plain)
                    if m:
                        self._flush_pending()
                        self._add_state_numbered_item(m.group(1), m.group(2).strip())
                        return

                    # 3e. Roman sub-clause (i), (ii) ... (only meaningful once a
                    #     numbered item is open)
                    m = RE_STATE_ROMAN.match(plain)
                    if m and self._sa_item is not None:
                        self._flush_pending()
                        self._add_state_roman_subitem(m.group(1).lower(), m.group(2).strip())
                        return

                    # 3f. Continuation text
                    self._pending.append(plain)
                    return

        # 4. Bold line → potential section header
        if line.startswith("§§") and line.endswith("§§"):
            inner = line[2:-2].strip()
            m = RE_SECTION_HEADER.match(inner)
            if m:
                self._flush_pending()
                self.in_state_amendment = False
                self._start_section(m.group(1), m.group(2).strip(), lines, next_i)
                return
            if re.match(r'^[A-Z\s\-]+$', inner):
                self.current_chapter_title = inner
                return
            self._pending.append(inner)
            return

        # 5. Italic line – often contains named ordinals
        if line.startswith("@@") and line.endswith("@@"):
            inner = line[2:-2].strip()
            if self._detect_named_ordinal(inner):
                self._section_has_named_ordinals = True
            self._pending.append(inner)
            return

        # 6. Plain line
        if self._detect_named_ordinal(line):
            self._section_has_named_ordinals = True
            self._pending.append(line)
            return

        # If inside a section, process structural markers
        if self.current_section:
            m = RE_NAMED_SUB.match(line)
            if m:
                self._section_has_named_ordinals = True
                self._pending.append(f"{m.group(1)},— {m.group(2)}")
                return

            m = RE_NESTED_SUB.match(line)
            if m:
                self._flush_pending()
                self._make_nested_combined(m.group(1), m.group(2), m.group(3).strip())
                return

            m = RE_NUMERIC_SUB.match(line)
            if m:
                if self._section_has_named_ordinals:
                    self._pending.append(line)
                    return
                self._flush_pending()
                self._open_marker(self.KIND_NUMERIC, m.group(1), m.group(2).strip())
                return

            m = RE_ALPHA_SUB.match(line)
            if m and len(self._stack) > 1:
                self._flush_pending()
                self._open_marker(self.KIND_ALPHA, m.group(1), m.group(2).strip())
                return

        # 7. Everything else: continuation text
        self._pending.append(line)

    # ---- start a new section (no early return!) ----
    def _start_section(self, sec_num: str, sec_title_raw: str, lines: list[str], next_i: int):
        node_id = f"IPC_{sec_num}"
        if not self._register_id(node_id):
            # If duplicate, treat as text and return
            self._pending.append(sec_title_raw)
            return

        dash_match = _DASH_RE.search(sec_title_raw)
        if dash_match:
            sec_title = sec_title_raw[:dash_match.start()].strip()
            body_part = sec_title_raw[dash_match.end():].strip()
        else:
            sec_title = sec_title_raw.strip()
            body_part = ""

        node = IPCNode(
            id             = node_id,
            chapter        = self.current_chapter,
            chapter_title  = self.current_chapter_title,
            section_number = sec_num,
            section_title  = sec_title,
            node_type      = "section",
        )
        self.current_section              = node
        self._stack                       = [(node, 0)]
        self._section_has_named_ordinals  = False
        self.nodes.append(node)

        if self._detect_named_ordinal(body_part):
            self._section_has_named_ordinals = True
        else:
            if self._lookahead_for_named_ordinal(lines, next_i):
                self._section_has_named_ordinals = True

        if body_part and not self._section_has_named_ordinals:
            m = RE_NUMERIC_SUB.match(body_part)
            if m:
                self._open_marker(self.KIND_NUMERIC, m.group(1), m.group(2).strip())
            else:
                self._pending.append(body_part)
        elif body_part:
            self._pending.append(body_part)

    # ---- open a structural marker (parentheses for ID) ----
    def _open_marker(self, kind: int, key: str, text: str):
        sec = self.current_section
        if sec is None:
            return

        while self._stack and self._stack[-1][1] >= kind:
            self._stack.pop()
        parent_node = self._stack[-1][0] if self._stack else sec

        node_id = f"{parent_node.id}({key})"
        existing = next((n for n in self.nodes if n.id == node_id), None)
        if existing:
            if text:
                existing.text = (existing.text + "\n" + text).strip() if existing.text else text
            self._stack.append((existing, kind))
            return

        self._register_id(node_id)
        node_type = "subsection" if parent_node is sec else "nested_subsection"
        node = IPCNode(
            id             = node_id,
            chapter        = sec.chapter,
            chapter_title  = sec.chapter_title,
            section_number = sec.section_number,
            section_title  = sec.section_title,
            node_type      = node_type,
            parent_id      = parent_node.id,
            subsection_key = key,
            text           = text,
        )
        self.nodes.append(node)
        self._stack.append((node, kind))

    # ---- combined nested e.g. (4)(a) ----
    def _make_nested_combined(self, parent_key: str, child_key: str, text: str):
        self._open_marker(self.KIND_NUMERIC, parent_key, "")
        self._open_marker(self.KIND_ALPHA, child_key, text)

    # ---- state amendment: container per state, numbered items, roman subitems ----
    def _current_amended_section(self) -> str:
        for n in reversed(self.nodes):
            if not n.is_state_amendment and n.section_number:
                return n.section_number
        return "unknown"

    def _start_state_amendment_block(self, state_name: str):
        self.current_state = state_name
        amends = self._current_amended_section()
        container_id = f"IPC_SA_{state_name}_{amends}"
        # Allow multiple amendment blocks for the same state+section across
        # the doc (rare) by suffixing if needed
        suffix = 2
        base_id = container_id
        while container_id in self._seen_ids:
            container_id = f"{base_id}_{suffix}"
            suffix += 1
        self._register_id(container_id)

        node = IPCNode(
            id                 = container_id,
            chapter            = self.current_chapter,
            chapter_title      = self.current_chapter_title,
            section_number     = amends,
            section_title      = f"State Amendment — {state_name} — Section {amends}",
            node_type          = "state_amendment",
            subsection_key     = None,
            text               = "",
            is_state_amendment = True,
            state              = state_name,
            amended_section    = amends,
        )
        self.nodes.append(node)
        self._sa_container = node
        self._sa_item = None
        self._sa_subitem = None

    def _add_state_numbered_item(self, num: str, text: str):
        if self._sa_container is None:
            # Defensive: a numbered clause appeared before any state name was
            # detected. Create an "Unknown" state container so nothing is lost.
            self._start_state_amendment_block(self.current_state or "Unknown")

        node_id = f"{self._sa_container.id}({num})"
        self._register_id(node_id)
        node = IPCNode(
            id                 = node_id,
            chapter            = self._sa_container.chapter,
            chapter_title      = self._sa_container.chapter_title,
            section_number     = self._sa_container.section_number,
            section_title      = self._sa_container.section_title,
            node_type          = "state_amendment_item",
            parent_id          = self._sa_container.id,
            subsection_key     = num,
            text               = text,
            is_state_amendment = True,
            state              = self._sa_container.state,
            amended_section    = self._sa_container.amended_section,
        )
        self.nodes.append(node)
        self._sa_item = node
        self._sa_subitem = None

    def _add_state_roman_subitem(self, roman: str, text: str):
        node_id = f"{self._sa_item.id}({roman})"
        self._register_id(node_id)
        node = IPCNode(
            id                 = node_id,
            chapter            = self._sa_item.chapter,
            chapter_title      = self._sa_item.chapter_title,
            section_number     = self._sa_item.section_number,
            section_title      = self._sa_item.section_title,
            node_type          = "state_amendment_subitem",
            parent_id          = self._sa_item.id,
            subsection_key     = f"{self._sa_item.subsection_key}({roman})",
            text               = text,
            is_state_amendment = True,
            state              = self._sa_item.state,
            amended_section    = self._sa_item.amended_section,
        )
        self.nodes.append(node)
        self._sa_subitem = node

    # ---- robust extraction of Explanation/Illustration/Exception/Proviso ----
    def _post_process_legal_elements(self):
        markers = [
            ('explanation', r'Explanation\s*[\d\w]*'),
            ('illustration', r'Illustrations?\s*[\d\w]*'),
            ('exception', r'Exception\s*[\d\w]*'),
            ('proviso', r'Provided\s+that'),
        ]
        for node in self.nodes:
            text = node.text
            if not text:
                continue

            positions = []
            for field_name, pattern in markers:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    positions.append((m.start(), m.end(), field_name, m.group()))
            if not positions:
                continue

            positions.sort(key=lambda x: x[0])
            # Extract EVERY segment into its field's list (previously this
            # used setattr and silently dropped all but the last match)
            for i, (start, end, field_name, matched) in enumerate(positions):
                next_start = positions[i + 1][0] if i + 1 < len(positions) else len(text)
                content_start = end
                while content_start < next_start and text[content_start] in ' .,;:—–\t\n\r':
                    content_start += 1
                content = text[content_start:next_start].strip()
                if not content:
                    continue
                if field_name == "illustration":
                    content = humanize_illustration(content)
                getattr(node, field_name).append(content)

            # Remove extracted parts from main text (rebuild)
            new_text = text
            for start, end, field_name, matched in sorted(positions, reverse=True):
                seg_end = len(new_text)
                for next_pos in sorted([p[0] for p in positions if p[0] > start], reverse=False):
                    if next_pos > start:
                        seg_end = next_pos
                        break
                new_text = new_text[:start] + new_text[seg_end:]
            node.text = new_text.strip()

# ---------- STEP 2.5: COLLAPSE TO SECTION LEVEL ----------
def collapse_to_section_level(nodes: list) -> list:
    """Keep only node_type == 'section' nodes (these correspond to the bold
    headers in the PDF, e.g. '120B.' — the same granularity your Neo4j graph
    uses). Everything nested under a section (subsections like (1)/(2),
    nested subsections like (4)(a), and state-amendment items/subitems) is
    merged into that section's `subsections` / `state_amendments` fields
    instead of becoming its own Pinecone ID (which is what caused the
    120B(2)-vs-120B mismatch against Neo4j)."""

    sections = [n for n in nodes if n.node_type == "section"]

    for sec in sections:
        prefix = f"IPC_{sec.section_number}"

        # ---- fold in subsections / nested subsections ----
        subs = [
            n for n in nodes
            if n.node_type in ("subsection", "nested_subsection")
            and n.section_number == sec.section_number
        ]
        if subs:
            combined_text_parts = []
            for s in subs:
                key_suffix = s.id[len(prefix):] if s.id.startswith(prefix) else s.id  # e.g. "(2)" or "(4)(a)"
                rec = {
                    "key":        key_suffix,
                    "node_type":  s.node_type,
                    "parent_id":  s.parent_id,
                    "text":       s.text,
                }
                if s.explanation:
                    rec["explanation"] = s.explanation
                if s.exception:
                    rec["exception"] = s.exception
                if s.illustration:
                    rec["illustration"] = s.illustration
                if s.proviso:
                    rec["proviso"] = s.proviso
                sec.subsections.append(rec)

                if s.text:
                    combined_text_parts.append(f"{key_suffix} {s.text}")
                # Fold legal elements up so the single section-level vector's
                # embedding text still covers everything a subsection had.
                sec.explanation.extend(s.explanation)
                sec.exception.extend(s.exception)
                sec.illustration.extend(s.illustration)
                sec.proviso.extend(s.proviso)

            if combined_text_parts:
                extra = "\n".join(combined_text_parts)
                sec.text = (sec.text + "\n" + extra).strip() if sec.text else extra

        # ---- fold in state amendments (container -> items -> subitems) ----
        sa_containers = [
            n for n in nodes
            if n.node_type == "state_amendment" and n.amended_section == sec.section_number
        ]
        for cont in sa_containers:
            items = [n for n in nodes if n.node_type == "state_amendment_item" and n.parent_id == cont.id]
            item_records = []
            for it in items:
                subitems = [n for n in nodes if n.node_type == "state_amendment_subitem" and n.parent_id == it.id]
                item_rec = {"key": it.subsection_key, "text": it.text}
                if it.citation:
                    item_rec["citation"] = it.citation
                if subitems:
                    item_rec["subitems"] = [{"key": si.subsection_key, "text": si.text} for si in subitems]
                item_records.append(item_rec)

            state_key = cont.state or "Unknown"
            entry = {"items": item_records}
            if cont.citation:
                entry["citation"] = cont.citation
            sec.state_amendments[state_key] = entry

    log.info(
        f"Collapsed to {len(sections)} section-level nodes "
        f"(folded in {sum(len(s.subsections) for s in sections)} subsections, "
        f"{sum(len(s.state_amendments) for s in sections)} state-amendment blocks)"
    )
    return sections

# ---------- STEP 2.5: NEO4J GRAPH ENRICHMENT ----------
# Fetches ingredients, keywords, crimes, cross-links for every IPC section
# from Neo4j so the embed text is richer than raw PDF text alone.

_NEO4J_FETCH_QUERY = """
MATCH (s:LawSection)
WHERE s.act = 'IPC'
OPTIONAL MATCH (s)-[:HAS_INGREDIENT]->(ing:Ingredient)
OPTIONAL MATCH (s)-[:HAS_KEYWORD]->(kw:Keyword)
OPTIONAL MATCH (s)-[:PRESCRIBES]->(pun:Punishment)
OPTIONAL MATCH (s)-[:APPLIES_TO]->(cr:Crime)
OPTIONAL MATCH (s)-[:MORE_SPECIFIC_THAN]->(parent:LawSection)
OPTIONAL MATCH (s)-[:HAS_EXCEPTION]->(exc:Exception)
OPTIONAL MATCH (s)-[:REPLACED_BY]->(new_s:LawSection)
RETURN
    s.id          AS id,
    s.section     AS section,
    s.title       AS title,
    s.description AS description,
    s.category    AS category,
    s.keywords    AS raw_keywords,
    collect(DISTINCT {
        name: ing.name, element_type: ing.element_type,
        fact_key: ing.fact_key, mandatory: ing.mandatory
    }) AS ingredients,
    collect(DISTINCT kw.name)            AS keywords,
    collect(DISTINCT {cognizable: pun.cognizable, bailable: pun.bailable, term: pun.term}) AS punishments,
    collect(DISTINCT cr.name)            AS crimes,
    collect(DISTINCT parent.title)       AS parent_titles,
    collect(DISTINCT exc.description)    AS exceptions,
    collect(DISTINCT new_s.section + ' ' + new_s.act) AS replaced_by_sections
ORDER BY s.section
"""


def _neo4j_fetch_graph_data() -> dict:
    """
    Returns a dict keyed by IPC section number (e.g. '415') → graph record.
    Returns empty dict if Neo4j is unavailable — pipeline degrades gracefully
    to PDF-text-only embedding in that case.
    """
    if not NEO4J_PASSWORD:
        log.warning("[Neo4j] NEO4J_PASSWORD not set — skipping graph enrichment. "
                    "Set NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in .env to enable.")
        return {}
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        with driver.session() as session:
            records = [dict(r) for r in session.run(_NEO4J_FETCH_QUERY)]
        driver.close()
        log.info(f"[Neo4j] Fetched graph data for {len(records)} IPC sections")
        return {str(r["section"]): r for r in records if r.get("section")}
    except Exception as e:
        log.warning(f"[Neo4j] Graph fetch failed ({e}) — falling back to PDF-text-only embedding")
        return {}


def _clean(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _dedup_list(lst: list) -> list:
    seen, out = set(), []
    for item in lst:
        key = str(item).strip()
        if key and key not in seen and key != "None":
            seen.add(key)
            out.append(key)
    return out


def _ingredients_text(ingredients: list) -> str:
    if not ingredients or all(not i.get("name") for i in ingredients):
        return ""
    mandatory, optional = [], []
    for ing in ingredients:
        name = _clean(ing.get("name"))
        if not name:
            continue
        element_type = _clean(ing.get("element_type"))
        fact_key     = _clean(ing.get("fact_key"))
        parts = [name]
        if element_type:
            parts.append(f"[{element_type}]")
        if fact_key and fact_key != name:
            parts.append(f"({fact_key})")
        entry = " ".join(parts)
        if ing.get("mandatory", True):
            mandatory.append(entry)
        else:
            optional.append(entry)
    lines = []
    if mandatory:
        lines.append("Required elements: " + "; ".join(mandatory))
    if optional:
        lines.append("Optional elements: " + "; ".join(optional))
    return "\n".join(lines)


def _punishment_text_from_nodes(punishments: list, fallback: str) -> str:
    clean_puns = [p for p in punishments if p.get("term")]
    if not clean_puns:
        return fallback
    parts = []
    for p in clean_puns:
        term   = _clean(p.get("term"))
        cogniz = p.get("cognizable")
        bail   = p.get("bailable")
        flags  = []
        if cogniz is not None:
            flags.append("cognizable" if cogniz else "non-cognizable")
        if bail is not None:
            flags.append("bailable" if bail else "non-bailable")
        line = term + (" | " + ", ".join(flags) if flags else "")
        parts.append(line)
    return "; ".join(parts)


# ---------- STEP 3: EMBEDDING ----------
def build_embed_text(node: IPCNode, graph_record: dict = None) -> str:
    """
    Build the embedding text for a node.

    When a Neo4j graph_record is provided (ingredients, keywords, crimes,
    cross-links), those fields are merged in to produce a richly-contextualised
    block that dramatically improves retrieval precision for offence queries.

    When graph_record is None (Neo4j unavailable), falls back to PDF-text-only
    embedding: section_title + statutory text + explanations + illustrations.

    What is EXCLUDED from the embed text regardless:
      - chapter / chapter_title  : identical boilerplate across all sections in
                                   a chapter; pulls unrelated sections together.
      - node_type / is_state_amendment / state / citation : schema metadata,
                                   not legal signal.
      - punishment clause text   : identical boilerplate across many sections;
                                   only punishment *type* (cognizable/bailable)
                                   is included via the graph record.
    """
    lines = []

    # ── Header (graph-aware) ─────────────────────────────────────────────────
    header_parts = ["[ACT: IPC]", f"[SECTION: {node.section_number}]"]
    if graph_record:
        category = _clean(graph_record.get("category"))
        crimes   = _dedup_list(graph_record.get("crimes") or [])
        if category:
            header_parts.append(f"[TYPE: {category}]")
        if crimes:
            header_parts.append(f"[DOMAIN: {', '.join(crimes[:5])}]")
    lines.append(" ".join(header_parts))

    # ── Title ────────────────────────────────────────────────────────────────
    title = (graph_record.get("title") if graph_record else None) or node.section_title
    if title:
        lines.append(f"Title: {_clean(title)}")

    # ── Statutory text (from PDF — most authoritative source) ────────────────
    if node.text:
        lines.append(f"Description: {node.text}")

    # ── Graph enrichment (only when Neo4j data available) ────────────────────
    if graph_record:
        crimes = _dedup_list(graph_record.get("crimes") or [])
        if crimes:
            lines.append(f"Applies to: {', '.join(crimes)}")

        ing_text = _ingredients_text(graph_record.get("ingredients") or [])
        if ing_text:
            lines.append(ing_text)

        keywords     = _dedup_list(graph_record.get("keywords") or [])
        raw_kw_str   = graph_record.get("raw_keywords") or ""
        raw_kw       = _dedup_list(raw_kw_str.split(",") if raw_kw_str else [])
        all_keywords = _dedup_list(keywords + raw_kw)
        if all_keywords:
            lines.append(f"Keywords: {', '.join(all_keywords)}")

        pun_text = _punishment_text_from_nodes(
            graph_record.get("punishments") or [],
            _clean(graph_record.get("punishment_text", ""))
        )
        if pun_text:
            lines.append(f"Punishment: {pun_text}")

        parents = _dedup_list(graph_record.get("parent_titles") or [])
        if parents:
            lines.append(f"More specific than: {', '.join(parents)}")

        replaced_by = _dedup_list(graph_record.get("replaced_by_sections") or [])
        if replaced_by:
            lines.append(f"Replaced by: {', '.join(replaced_by)}")

    # ── PDF-sourced enrichment (always included) ─────────────────────────────
    for exp in node.explanation:
        lines.append(f"Explanation: {exp}")

    exceptions_src = []
    if graph_record:
        exceptions_src = _dedup_list(graph_record.get("exceptions") or [])
    if not exceptions_src:
        exceptions_src = node.exception
    for exc in exceptions_src[:3]:
        lines.append(f"Exception: {exc}")

    # Illustrations: highest-value signal — plain-language fact patterns that
    # closely mirror the vocabulary of real case-fact queries
    for ill in node.illustration:
        lines.append(f"Illustration: {ill}")

    for pro in node.proviso:
        lines.append(f"Proviso: {pro}")

    return "\n".join(l for l in lines if l)

def embed_nodes(nodes: list[IPCNode], model: SentenceTransformer) -> list[IPCNode]:
    # Fetch Neo4j graph data once (ingredients, keywords, crimes, cross-links).
    # Returns empty dict if Neo4j is unavailable — build_embed_text degrades
    # gracefully to PDF-text-only in that case.
    graph_data = _neo4j_fetch_graph_data()
    if graph_data:
        log.info(f"[Neo4j] Graph enrichment active for {len(graph_data)} sections")
    else:
        log.warning("[Neo4j] Graph enrichment unavailable — using PDF text only")

    # Hard cap on tokens: attention memory grows with the SQUARE of sequence
    # length, so one abnormally long node (almost always a parsing artifact —
    # e.g. a state-amendment block that didn't close and swallowed several
    # following pages) can blow up memory for the *entire* batch it's in,
    # even if every other text in that batch is normal-sized. Capping here
    # means a rogue node gets truncated instead of crashing the whole run.
    model.max_seq_length = EMBED_MAX_SEQ_TOKENS

    texts = [build_embed_text(n, graph_data.get(n.section_number)) for n in nodes]

    long_nodes = [(n.id, len(t)) for n, t in zip(nodes, texts) if len(t) > LONG_NODE_WARN_CHARS]
    if long_nodes:
        log.warning(
            f"{len(long_nodes)} node(s) have unusually long text (>{LONG_NODE_WARN_CHARS} chars) — "
            f"likely a parsing artifact (e.g. a state-amendment block that didn't close). "
            f"They'll be truncated to ~{EMBED_MAX_SEQ_TOKENS} tokens for embedding, but you should "
            f"check these in ipc_structured.json: {[nid for nid, _ in long_nodes[:15]]}"
        )

    log.info(f"Embedding {len(nodes)} nodes...")
    # task="retrieval.passage" tells jina-v3 these are documents being stored,
    # not search queries.  At search time, EmbeddingService uses the paired
    # task="retrieval.query" so query and passage vectors live in the same
    # asymmetric space — this is the correct usage of jina-embeddings-v3 and
    # gives meaningfully better retrieval precision than generic (no-task) encoding.
    # normalize_embeddings=True is kept so cosine similarity == dot product,
    # which is what Pinecone computes internally.
    # prompt_name="retrieval.passage" is the correct sentence-transformers API
    # for jina-embeddings-v3 task-aware encoding (v3.0+ uses prompt_name, not task=).
    # At query time, EmbeddingService uses prompt_name="retrieval.query" so the
    # two vectors live in the same asymmetric space.
    vecs = model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
        prompt_name="retrieval.passage",
    )
    for node, vec in zip(nodes, vecs):
        node.embedding = vec.tolist()
    return nodes

# ---------- STEP 4: PINECONE UPSERT ----------
def node_to_vector(node: IPCNode) -> dict:
    def s(v, n=1000): return (v or "")[:n]
    def s_list(vs, n=1000): return [str(v)[:n] for v in vs if v]

    metadata = {
        "chapter":            s(node.chapter,         50),
        "chapter_title":      s(node.chapter_title,   100),
        "section_number":     s(node.section_number,  20),
        "section_title":      s(node.section_title,   200),
        "node_type":          node.node_type,
        "parent_id":          s(node.parent_id,       60),
        "subsection_key":     s(node.subsection_key,  50),
        "text":               s(node.text,            2000),
        "is_state_amendment": node.is_state_amendment,
        "state":              s(node.state,           50),
        "amended_section":    s(node.amended_section, 20),
        "citation":           s(node.citation,         300),
        "explanation":        s_list(node.explanation, 1000),
        "exception":          s_list(node.exception,   1000),
        "illustration":       s_list(node.illustration, 1000),
        "proviso":            s_list(node.proviso,     500),
        "subsections":        json.dumps(node.subsections, ensure_ascii=False)[:4000] if node.subsections else "",
        "state_amendments":   json.dumps(node.state_amendments, ensure_ascii=False)[:4000] if node.state_amendments else "",
    }
    # Drop empty values (but always keep is_state_amendment, a real bool)
    metadata = {
        k: v for k, v in metadata.items()
        if k == "is_state_amendment" or (v not in ("", None) and v != [])
    }
    return {"id": node.id, "values": node.embedding, "metadata": metadata}

def upsert(nodes: list[IPCNode], index) -> None:
    vectors = [node_to_vector(n) for n in nodes if n.embedding]
    total = 0
    for i in tqdm(range(0, len(vectors), PINECONE_BATCH_SIZE), desc="Upserting"):
        index.upsert(vectors=vectors[i: i + PINECONE_BATCH_SIZE])
        total += min(PINECONE_BATCH_SIZE, len(vectors) - i)
    log.info(f"Upserted {total} vectors")

# ---------- STEP 3.5: MANUAL REVIEW GATE ----------
def wait_for_manual_review(json_path: str) -> list[IPCNode]:
    """Blocks until the user types 'yes'. Re-reads the JSON file from disk
    afterwards, so any hand-edits the user made are what gets embedded."""
    print("\n" + "=" * 70)
    print(f"Structured data saved to: {json_path}")
    print("Open it now and fix anything that looks wrong — misclassified")
    print("'Person X' labels, mis-parsed state amendments, explanation")
    print("boundaries, etc. Save the file when you're done.")
    print("=" * 70)
    while True:
        answer = input("\nType 'yes' to continue with embedding + upsert (or 'quit' to exit): ").strip().lower()
        if answer == "yes":
            break
        if answer in ("quit", "q", "exit", "no", "n"):
            log.info("Aborted by user before embedding. No vectors were upserted.")
            raise SystemExit(0)
        print("Please type 'yes' to continue, or 'quit' to exit without embedding.")

    with open(json_path, "r", encoding="utf-8") as f:
        raw_nodes = json.load(f)
    nodes = [node_from_dict(d) for d in raw_nodes]
    log.info(f"Re-loaded {len(nodes)} nodes from {json_path} after manual review")
    return nodes

# ---------- MAIN ----------
def main():
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", ""))
    model = SentenceTransformer(
        EMBED_MODEL,
        trust_remote_code=True,
        local_files_only=True,
        tokenizer_kwargs={"fix_mistral_regex": True},   # suppresses tokenizer warning
    )

    pages = extract_structured_text(PDF_PATH, IPC_START_PAGE)
    tagged_text = pages_to_tagged_text(pages)

    with open("ipc_tagged.txt", "w", encoding="utf-8") as f:
        f.write(tagged_text)
    log.info("Saved ipc_tagged.txt")

    parser = IPCParser()
    nodes = parser.parse(tagged_text)
    log.info(f"Parsed {len(nodes)} raw nodes")
    for t in ("section", "subsection", "nested_subsection",
              "state_amendment", "state_amendment_item", "state_amendment_subitem"):
        log.info(f"  {t}: {sum(1 for n in nodes if n.node_type == t)}")

    # Only bold-section nodes (e.g. "120B.") get their own Pinecone ID, to
    # match the granularity of the Neo4j graph. Everything nested under a
    # section — subsections like (1)/(2), nested subsections like (4)(a),
    # and state amendments — is folded into that section's node as
    # structured metadata instead of becoming a separate vector.
    nodes = collapse_to_section_level(nodes)

    with open(STRUCTURED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(
            [{k: v for k, v in asdict(n).items() if k != "embedding"} for n in nodes],
            f, ensure_ascii=False, indent=2
        )
    log.info(f"Saved {STRUCTURED_JSON_PATH} — REVIEW before upserting")

    # ---- STOP HERE for manual review ----
    nodes = wait_for_manual_review(STRUCTURED_JSON_PATH)

    nodes = embed_nodes(nodes, model)
    upsert(nodes, index)
    log.info("[DONE]")

if __name__ == "__main__":
    main()