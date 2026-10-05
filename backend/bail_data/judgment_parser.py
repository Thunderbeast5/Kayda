#!/usr/bin/env python3
"""
judgment_parser.py - format-tolerant loader for Indian Supreme Court judgments.

Drop-in replacement for load_pdf()/load_laws_json() in extract.py:

    from judgment_parser import load_document, Doc
    doc = load_document("some_judgment.pdf")      # or a LawSuperOnline .json

Design:
  * Every metadata field has an ordered list of independent extractors; the first one that
    succeeds wins and its name is recorded in meta["_sources"][field]. Nothing hard-fails: a field
    that no extractor can fill is left out and a flag is added instead.
  * Reporter formats (SCR / SCC / AIR / slip opinion / unknown) only change *which* header and
    zone-marker patterns get tried; all extractors are generic fallbacks otherwise.
  * Page-edge margin letters (A-H) are removed by geometry, not by regex, so real sentences
    that start with "A ..." are never touched.
  * OCR slips ("[2005)", "S.C .. R.", "ST ATE") are normalised only for metadata matching;
    paragraph text is kept as printed.

Adding a new format = add a profile to PROFILES, or one more pattern to an extractor list.
"""
from __future__ import annotations

import bisect
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

try:
    import pymupdf as fitz  # new name
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

# --------------------------------------------------------------------------- data model


@dataclass
class Doc:
    source: str
    fmt: str
    meta: dict
    headnote: str
    paras: dict                      # id -> {"text","page_start","page_end"}
    authority_table: list = field(default_factory=list)
    flags: list = field(default_factory=list)


MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December")
MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS.split("|"))}
MONTH_NUM.update({k[:3]: v for k, v in list(MONTH_NUM.items())})
MONTH_NUM["sept"] = 9

# --------------------------------------------------------------------------- text helpers


def ocr_norm(s: str) -> str:
    """Normalise common OCR slips for *matching only*."""
    s = re.sub(r"\[\s*(\d{4})\s*[)\]|}]", r"[\1]", s)           # [2005)  -> [2005]
    s = re.sub(r"S\s*\.\s*C\s*\.{1,3}\s*R", "S.C.R", s)          # S.C .. R -> S.C.R
    s = re.sub(r"\bST\s+ATE\b", "STATE", s)
    s = re.sub(r"\bJUDG\s+MENT\b", "JUDGMENT", s)
    return s


# SCR volume fragment: "[2009] 16 (ADDL.) S.C.R." / "[1995] 6 Suppl. SCR" / "[2024] 12 S.C.R."
_SCR_VOL = r"\[\d{4}\]\s*\d+\s*(?:\(?\s*(?:ADDL|ADDITIONAL)\.?\s*\)?\s*|Suppl\.?\s*)?S\.?\s?C\.?\s?R"


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


TITLE_WORDS = re.compile(
    r"(?i)\b(hon'?ble|honourable|the|mr|mrs|ms|dr|shri|smt|justice|chief|cji|c\.?\s?j\.?i?|"
    r"jj?\.?|before|coram|present)\b\.?")


def clean_judge_name(n: str) -> str:
    n = TITLE_WORDS.sub(" ", n)
    n = re.sub(r"[\[\]()<>:;_*]|\.{2,}|-{2,}", " ", n)
    return collapse(n).strip(" ,.-")


# --------------------------------------------------------------------------- PDF reading


def _is_hidden_ocr(spans) -> bool:
    return any("hiddenhorzocr" in (sp.get("font", "") or "").lower() for sp in spans)


def _read_page(pg, ocr_min_chars: int, flags: list, idx: int) -> tuple[str, list[str]]:
    """One page -> (clean text, footnote lines).
    * margin letters A-H dropped by position (relative to the page's own text block, so it works
      whether they sit in the page margin or in a gutter inside the page)
    * superscript footnote markers dropped; small-font lines at the page foot returned as footnotes."""
    def blocks(tp=None):
        d = pg.get_text("dict", textpage=tp) if tp else pg.get_text("dict")
        out = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                sp = [s for s in l["spans"] if s["text"] != ""]
                if sp:
                    out.append((l["bbox"][1], l["bbox"][0], sp))
        return out

    lines = blocks()
    if len("".join(s["text"] for _, _, sp in lines for s in sp).strip()) < ocr_min_chars:
        try:
            lines = blocks(pg.get_textpage_ocr(dpi=300, full=True))
            for _, _, sp in lines:                      # OCR'd text: sizes are unreliable
                for s in sp:
                    s["font"] = "HiddenHorzOCR"
        except Exception:
            flags.append(f"page_{idx + 1}_low_text_no_ocr")
    if not lines:
        return "", []
    lines.sort(key=lambda t: (round(t[0] / 2), t[1]))
    H = pg.rect.height
    hidden = _is_hidden_ocr([s for _, _, sp in lines for s in sp])

    sizes = Counter()
    for _, _, sp in lines:
        for s in sp:
            sizes[round(s["size"], 1)] += len(s["text"].strip())
    body = sizes.most_common(1)[0][0] if sizes else 0

    # pass 1: pieces (text, x0, x1, small?) per line
    plines = []
    for y0, x0, sp in lines:
        pieces = []
        for s in sp:
            t, (a, _, b, _) = s["text"], s["bbox"]
            small = (not hidden) and body and s["size"] < 0.8 * body
            n = max(len(t), 1)
            for m in re.finditer(r"\S+|\s+", t):
                pieces.append((m.group(0), a + (b - a) * m.start() / n, a + (b - a) * m.end() / n, small))
        plines.append((y0, pieces))

    words = [p for _, ps in plines for p in ps if p[0].strip() and len(p[0].strip()) > 1 and not p[3]]
    xs0 = sorted(p[1] for p in words)
    xs1 = sorted(p[2] for p in words)
    L = xs0[int(0.1 * len(xs0))] if xs0 else 0
    R = xs1[int(0.9 * len(xs1))] if xs1 else pg.rect.width

    def is_margin(p):
        return bool(re.fullmatch(r"[A-H]", p[0].strip())) and not p[3] and (p[2] <= L - 3 or p[1] >= R + 3)

    out, foot = [], []
    for y0, ps in plines:
        real = [p for p in ps if p[0].strip()]
        if real and all(p[3] for p in real) and y0 > 0.55 * H:            # footnote line
            foot.append(re.sub(r"^\s*\d{1,2}\s+", "", "".join(p[0] for p in ps)).strip())
            continue
        keep = []
        for p in ps:
            if is_margin(p):
                continue
            if p[3] and re.fullmatch(r"[\d*†‡,]+", p[0].strip()) and len(real) > 1:   # superscript marker
                continue
            keep.append(p[0])
        txt = "".join(keep).strip()
        if txt:
            out.append(txt)
    return "\n".join(out), [f for f in foot if f]


def read_pdf_pages(path: str, ocr_min_chars: int = 80) -> tuple[list[str], list[str], list[tuple]]:
    """Return (page_texts, flags, footnotes[(page_index, text)])."""
    doc, texts, flags, notes = fitz.open(path), [], [], []
    for i, pg in enumerate(doc):
        t, f = _read_page(pg, ocr_min_chars, flags, i)
        texts.append(t)
        notes += [(i, x) for x in f if not re.fullmatch(r"\*\s*Author", x)]
    return texts, flags, notes


# --------------------------------------------------------------------------- page numbers

PAGE_RUN_HEAD = re.compile(r"^\s*(\d{2,4})\s+SUPREME\s+COURT", re.I)
PAGE_BARE = re.compile(r"^\s*(\d{2,4})A?\s*$")
PAGE_VS_LINE = re.compile(r"^[A-Z][^\n]{0,70}\b[vV]\.\s[^\n]{0,60}?\s(\d{3,4})\s*$")


PAGE_SCR_HDR = re.compile(rf"^\s*(?:(\d{{3,4}})\s+)?{_SCR_VOL}\.?\s*(?:(\d{{3,4}})\b)?")


PAGE_X_OF_N = re.compile(r"(?:^|[A-Za-z.\s])Page\s+(\d{1,4})\s+of\s+\d{1,4}\s*$", re.I)


def detect_page(raw: str) -> Optional[int]:
    lines = raw.splitlines()
    for ln in lines[:6] + lines[-4:]:                    # slip opinions: "Page 2 of 17" (header or footer, maybe glued to a watermark)
        m = PAGE_X_OF_N.search(ln.strip())
        if m:
            return int(m.group(1))
    head = lines[:6]
    for ln in head:
        m = PAGE_RUN_HEAD.match(ln) or PAGE_VS_LINE.match(ln)
        if m:
            return int(m.group(1))
        m = PAGE_SCR_HDR.match(ocr_norm(ln))              # "2084 [2024] 12 S.C.R."  /  "[2024] 12 S.C.R. 2085"
        if m and (m.group(1) or m.group(2)):
            return int(m.group(1) or m.group(2))
    for ln in head:
        m = PAGE_BARE.match(ln)
        if m:
            return int(m.group(1))
    return None


def assign_pages(raws: list[str]) -> list[int]:
    det = [detect_page(r) for r in raws]
    votes = Counter(d - i for i, d in enumerate(det) if d)
    base = votes.most_common(1)[0][0] if votes else 1
    pages, prev = [], None
    for i, d in enumerate(det):
        exp = base + i if prev is None else prev + 1
        pages.append(d if d and abs(d - exp) <= 1 else exp)
        prev = pages[-1]
    return pages


# --------------------------------------------------------------------------- header / noise lines

HDR_PATTERNS = [re.compile(p) for p in [
    r"^\s*\d{2,4}\s+SUPREME\s+COURT\s+.*$",
    r"(?i)^\s*SUPREME\s+COURT\s+(REPORTS|CASES).*$",
    r"^\s*(?:\d{3,4}\s+)?\[\d{4}\]\s*\d+\s*(?:\(?\s*(?:ADDL|ADDITIONAL)\.?\s*\)?\s*|Suppl\.?\s*)?S\.\s?C\.\s?R\.?\s*(?:\d{3,4})?\s*$",   # dots required: "[2013] 12 SCR 772" is a citation, not a header
    r"^\s*\*\s*Author\s*$",
    r"^\s*\(\d{4}\)\s*\d+\s*SCC\s*\d*\s*$",
    r"^\s*\d{2,4}A?\s*$",
    r"^\s*[A-Z][A-Z\.\s,&':]+\b[vV]\.\s[A-Z][A-Z\.\s,&':]+(\(.*?\))?\s*(\[[A-Z\.\s,]+J+\.\])?\s*\d{0,4}\s*$",
    r"^\s*\[[A-Z\.\s,~]+J+\.\]\s*$",
    r"^\s*[A-H]\s*$",
    r"^\s*(Page|Pg\.?)\s*\d+(\s*of\s*\d+)?\s*$",
    r"(?i)^\s*(?:VERDICTUM\.IN|LIVELAW(?:\.IN)?|SCC\s*ONLINE|INDIAN\s*KANOON)\s*(?:Page\s*\d+\s*of\s*\d+)?\s*$",
    r"^\s*\d{4}\s+INSC\s+\d+\s*$",
    r"(?i)^\s*(?:NON-?\s?REPORTABLE|REPORTABLE)\s*$",
    r"^\s*-\s*\d+\s*-\s*$",
    r"^\s*(Digital(ly)? Signed.*|Signature Not Verified.*|Reason:.*|Date:\s*\d{4}\.\d\d\.\d\d.*)$",
]]


def _hkey(l: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", l.strip().lower()))


def repeating_lines(raws: list[str], min_frac: float = 0.4, edge: int = 5) -> set:
    """Lines that recur at the top/bottom of many pages (digits ignored) are running headers/footers."""
    n = len(raws)
    if n < 4:
        return set()
    cnt = Counter()
    for r in raws:
        ls = [l.strip() for l in r.splitlines() if l.strip()]
        cnt.update({_hkey(l) for l in ls[:edge] + ls[-edge:]})
    thr = max(3, int(min_frac * n + 0.999))
    return {k for k, c in cnt.items() if c >= thr and len(k) > 2}


def _is_title(line: str, title_norm: str) -> bool:
    if not title_norm:
        return False
    a = re.sub(r"[^a-z0-9]", "", line.lower())
    return len(a) > 8 and SequenceMatcher(None, a, title_norm).ratio() >= 0.88


def clean_page(raw: str, drop_keys: frozenset = frozenset(), title_norm: str = "") -> list[str]:
    return [l.rstrip() for l in raw.splitlines()
            if l.strip() and not any(p.match(l) for p in HDR_PATTERNS)
            and _hkey(l) not in drop_keys and not _is_title(l, title_norm)]


# --------------------------------------------------------------------------- format profiles


@dataclass
class Profile:
    name: str
    signature: Callable[[str], bool]
    headnote_end: list[str]          # regexes; first hit ends the headnote zone
    body_start: list[str]            # regexes; first hit starts the judgment body (match end = start)


BODY_START_COMMON = [
    r"(?i)the\s+(?:judgment|order|reasons?)\s+of\s+the\s+(?:court|bench)\s+(?:was|were)\s+delivered\s+by",
    r"(?i)(?:delivered|pronounced)\s+the\s+following\s+(?:judgment|order)",
    r"(?im)^\s*J\s?U\s?D\s?G\s?M\s?E\s?N\s?T\s*:?\s*$",
    r"(?im)^\s*O\s?R\s?D\s?E\s?R\s*:?\s*$",
    r"(?im)^\s*(?:COMMON\s+)?(?:JUDGMENT|ORDER)\s*:?\s*$",
    r"(?im)^\s*Leave\s+granted\.?",
]
JURIS = r"(?i)(?:CRIMINAL|CIVIL)\s*(?:APPELLATE|ORIGINAL|REVIEW|WRIT|EXTRAORDINARY)?\s*JURISDICTION"

PROFILES = [
    Profile("scr_modern",
            lambda t: bool(re.search(r"Issue\s+for\s+Consideration|Headnotes\s*†", t)) and bool(re.search(r"S\.?C\.?R", t)),
            [JURIS], BODY_START_COMMON),
    Profile("scr_reporter",
            lambda t: bool(re.search(r"SUPREME\s+COURT\s+REPORTS|S\.?C\.?R\b", t)) and "HELD" in t,
            [JURIS], BODY_START_COMMON),
    Profile("scc_reporter",
            lambda t: bool(re.search(r"SUPREME\s+COURT\s+CASES|\(\d{4}\)\s*\d+\s*SCC\s*\d+", t)),
            [JURIS, r"(?im)^\s*(?:Advocates?|Counsel)\s+who\s+appeared"], BODY_START_COMMON),
    Profile("air_reporter",
            lambda t: bool(re.search(r"AIR\s+\d{4}\s+SUPREME\s+COURT|S\.?\s?C\.?\s+\d+\s*\(V\s*\d+", t)),
            [r"(?i)Cases?\s+Referred", JURIS], BODY_START_COMMON),
    Profile("slip_opinion",
            lambda t: bool(re.search(r"(?i)REPORTABLE|NON-?REPORTABLE|IN\s+THE\s+SUPREME\s+COURT\s+OF\s+INDIA", t)),
            [JURIS, r"(?im)^\s*J\s?U\s?D\s?G\s?M\s?E\s?N\s?T\s*:?\s*$", r"(?im)^\s*O\s?R\s?D\s?E\s?R\s*:?\s*$"],
            BODY_START_COMMON),
]
UNKNOWN = Profile("unknown", lambda t: True, [JURIS], BODY_START_COMMON)


def detect_profile(first_pages_text: str) -> Profile:
    t = ocr_norm(first_pages_text)
    for p in PROFILES:
        if p.signature(t):
            return p
    return UNKNOWN


# --------------------------------------------------------------------------- metadata extractors


def _vote(cands: list[tuple]) -> Optional[tuple]:
    return Counter(cands).most_common(1)[0][0] if cands else None


HDR_NOISE = re.compile(r"(?i)\b(referred|relied|followed|distinguished|overruled|paras?)\b|\sv\.?\s")


def header_lines(raws: list[str], n_pages: int = 8, n_lines: int = 6) -> list[str]:
    """Top lines of each page that look like running headers (not case-law citations in the headnote)."""
    out = []
    for r in raws[:n_pages]:
        out += [ocr_norm(l) for l in r.splitlines()[:n_lines] if len(l) < 90 and not HDR_NOISE.search(l)]
    return out


def extract_citation(raws: list[str], pages: list[int]) -> dict:
    """Reporter citation from running headers (voted across pages), then neutral citation."""
    hdr = "\n".join(header_lines(raws))
    head_all = ocr_norm("\n".join(raws[:3]))
    out: dict = {}
    neutral = re.search(r"\b(\d{4})\s+INSC\s+(\d+)\b", ocr_norm("\n".join(raws[0].splitlines()[:3])))
    if neutral:                                      # only from the very top of page 1, never from cited cases
        out.update(citation_neutral=f"{neutral[1]} INSC {neutral[2]}", neutral_year=int(neutral[1]))
    scr = [(int(m[1]), int(m[2])) for m in re.finditer(r"\[(\d{4})\]\s*(\d+)\s*(?:\(?\s*(?:ADDL|ADDITIONAL)\.?\s*\)?\s*|Suppl\.?\s*)?S\.?\s?C\.?\s?R", hdr)]
    if v := _vote(scr):
        return {**out, "citation_scr": f"[{v[0]}] {v[1]} SCR {pages[0]}", "scr_year": v[0], "scr_volume": v[1],
                "scr_first_page": pages[0], "_src": "scr_running_header"}
    scc = [(int(m[1]), int(m[2]), int(m[3])) for m in
           re.finditer(r"\((\d{4})\)\s*(\d+)\s*SCC\s*(\d+)", hdr)]
    if v := _vote([(y, vol) for y, vol, _ in scc]):
        first = min(p for y, vol, p in scc if (y, vol) == v)
        return {**out, "citation_scc": f"({v[0]}) {v[1]} SCC {first}", "scc_year": v[0], "_src": "scc_running_header"}
    m = re.search(r"\b(?:AIR)\s+(\d{4})\s+(?:SUPREME\s+COURT|SC)\s+(\d+)", hdr + head_all)
    if m:
        return {**out, "citation_air": f"AIR {m[1]} SC {m[2]}", "air_year": int(m[1]), "_src": "air_header"}
    if out:
        return {**out, "_src": "neutral"}
    m = re.search(r"\b(\d{4})\s+SCC\s+OnLine\s+SC\s+(\d+)\b", head_all)
    if m:
        return {"citation_online": f"{m[1]} SCC OnLine SC {m[2]}", "neutral_year": int(m[1]), "_src": "scc_online"}
    return {}


def _mk_date(d: int, mon: str, y: int) -> Optional[date]:
    try:
        return date(y, MONTH_NUM[mon.lower().rstrip(".")], d)
    except (KeyError, ValueError):
        return None


DATE_PATTERNS = [   # (name, regex, builder)  -- regex groups map via builder
    ("month_d_y", rf"(?i)\b({MONTHS}|Sept?|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Oct|Nov|Dec)\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})",
     lambda m: _mk_date(int(m[2]), m[1], int(m[3]))),
    ("d_month_y", rf"(?i)\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({MONTHS}|Sept?|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Oct|Nov|Dec)\.?,?\s+(\d{{4}})",
     lambda m: _mk_date(int(m[1]), m[2], int(m[3]))),
    ("dmy_numeric", r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b",
     lambda m: _safe_date(int(m[3]), int(m[2]), int(m[1]))),
]
# NB: bare "dated" is deliberately absent - "Judgment and Order dated 25.07.2023" is the impugned order, not this judgment
DATE_CONTEXT = r"(?i)(?:date\s+of\s+judg(?:e)?ment|decided\s+on|judgment\s+delivered\s+on|pronounced\s+on|" \
               r"reserved\s+on|date\s+of\s+decision|\bdated\s*:)\s*[:\-]?\s*"


def _safe_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _tail_date(tail: str) -> Optional[str]:
    """Last date in the closing block ('NEW DELHI; SEPTEMBER 24, 2025.' / 'Dated: 24.09.2025')."""
    t = ocr_norm(tail)
    best = None
    for name, rx, mk in DATE_PATTERNS:
        for m in re.finditer(rx, t):
            if (d := mk(m)):
                best = max(best, (m.start(), d.isoformat(), name)) if best else (m.start(), d.isoformat(), name)
    return best and f"{best[1]}|{best[2]}"


def extract_decided_on(first_page: str, head: str, tail: str = "") -> dict:
    """1) date after a label, 2) first free-standing date on page 1 (reporter title block),
    3) first date anywhere in the head. Reporter 'appeal from ... dated' lines are skipped."""
    t = ocr_norm(head)
    # 1. labelled
    for lm in re.finditer(DATE_CONTEXT, t):
        if re.search(r"(?i)reserved", lm.group(0)):
            continue
        seg = t[lm.end(): lm.end() + 40]
        for name, rx, mk in DATE_PATTERNS:
            m = re.match(rx, seg)
            if m and (d := mk(m)):
                return {"decided_on": d.isoformat(), "_src": f"labelled:{name}"}
    # 2. page-1 title block (skip the 'From the Judgment and Order dated ...' appeal line)
    p1 = "\n".join(l for l in ocr_norm(first_page).splitlines()
                   if not re.search(r"(?i)from\s+the\s+(?:judgment|order)|order\s+dated|impugned", l))
    for name, rx, mk in DATE_PATTERNS[:2]:
        m = re.search(rx, p1)
        if m and (d := mk(m)):
            return {"decided_on": d.isoformat(), "_src": f"page1:{name}"}
    # 3. closing block of slip opinions (after the judges' signatures)
    if tail and (r := _tail_date(tail)):
        iso, name = r.split("|")
        return {"decided_on": iso, "_src": f"tail:{name}"}
    return {}


CORAM_PATTERNS = [
    ("bracket_jj", re.compile(r"\[\s*([^\[\]]*?\bJJ?\.?)\s*\]", re.S)),
    ("paren_jj", re.compile(r"\(\s*([A-Z][^()]*?\bJJ?\.?)\s*\)", re.S)),
    ("coram_block", re.compile(r"(?is)(?:CORAM|BEFORE|PRESENT)\s*:?\s*(.{10,400}?)(?=\n\s*\n|\bIN\s+THE\b|\bCRIMINAL\b|\bCIVIL\b|$)")),
    ("hon_justice", re.compile(r"(?is)((?:HON'?BLE\s+)?(?:MR\.?|MRS\.?|MS\.?|DR\.?)?\s*JUSTICE\s+[A-Z][^\n]{3,80}(?:\n\s*(?:AND\s+)?(?:HON'?BLE\s+)?(?:MR\.?|MRS\.?|MS\.?)?\s*JUSTICE\s+[A-Z][^\n]{3,80}){0,8})")),
]


SIGN_RX = re.compile(r"[.…_\-]{3,}\s*(?:C\.?\s?J\.?\s?I?\.?|J{1,2}\.?)\s*\n?\s*\(\s*([^)\n]{4,60}?)\s*\)")


def extract_coram_from_signatures(tail: str) -> dict:
    """Slip opinions name the bench only in the signature block: '......J.  (B.V. NAGARATHNA)'."""
    names = [clean_judge_name(m.group(1)) for m in SIGN_RX.finditer(ocr_norm(tail))]
    names = [n for n in dict.fromkeys(names) if len(n) > 3]
    if not names:
        return {}
    return {"coram_raw": " , ".join(names), "coram_regex": names, "bench_strength_regex": len(names),
            "constitution_bench": len(names) >= 5, "_src": "coram:signature_block"}


def extract_coram(head: str) -> dict:
    t = ocr_norm(head[:2500])
    for name, rx in CORAM_PATTERNS:
        m = rx.search(t)
        if not m:
            continue
        raw = collapse(m.group(1))
        parts = re.split(r",|&|\bAND\b|\n|\bJUSTICE\b", raw, flags=re.I)
        names = [clean_judge_name(p) for p in parts]
        names = [n for n in names if len(n) > 3 and not re.fullmatch(r"(?i)(and|jj?|c\.?j\.?)", n)]
        if names:
            res = {"coram_raw": raw, "coram_regex": names, "bench_strength_regex": len(names),
                   "constitution_bench": len(names) >= 5, "_src": f"coram:{name}"}
            star = re.search(r"([A-Z][A-Za-z\.\s'-]{3,40}?)\s*\*", raw)          # modern SCR marks the author: [Vikram Nath* and ...]
            if star:
                res["judgment_author_from_coram"] = clean_judge_name(star.group(1))
            return res
    return {}


AUTHOR_PATTERNS = [
    re.compile(r"(?m)^\s*([A-Z][A-Za-z\.\s'~-]{3,45}?),?\s*\(?(?:C\.?\s?J\.?(?:I\.?)?|J\.)\)?(?=\s|$|[:\-–—])"),   # PASAYAT, J. / Vikram Nath, J.
    re.compile(r"(?i)(?:judg(?:e)?ment|order)\s+(?:of\s+the\s+court\s+)?(?:was\s+)?delivered\s+by\s+(?:hon'?ble\s+)?(?:mr\.?\s+)?(?:justice\s+)?([A-Z][A-Za-z\.\s'-]{3,40}?)(?:[,.]|\n)"),
    re.compile(r"(?m)\.{3,}\s*(?:C\.?J\.?I?\.?|J\.?)\s*\n?\s*\(([^)\n]{4,50})\)"),             # ......J. (NAME) signature
    re.compile(r"(?i)hon'?ble\s+(?:mr\.?\s+)?justice\s+([A-Za-z\.\s'-]{4,40}?)\s*(?:\n|:)"),
]


def extract_author(body_start_text: str, tail_text: str) -> dict:
    for i, rx in enumerate(AUTHOR_PATTERNS):
        src = tail_text if i == 2 else body_start_text
        m = rx.search(ocr_norm(src))
        if m:
            n = clean_judge_name(m.group(1))
            if len(n) > 3:
                return {"judgment_author_regex": n, "_src": f"author:{i}"}
    return {}


def extract_case_no(head: str) -> dict:
    t = ocr_norm(head)
    m = re.search(rf"{JURIS}\s*[:\-]?\s*(.{{5,160}}?\b(?:of|/)\s*\d{{4}})", t, re.S)
    if m:
        return {"case_no": collapse(m.group(1)), "_src": "juris_line"}
    m = re.search(r"(?i)((?:Criminal|Civil)\s+Appeal\s+No\(?s?\)?\.?\s*[\d\s,&-]+(?:of|/)\s*\d{4})", t)
    if m:
        return {"case_no": collapse(m.group(1)), "_src": "appeal_no"}
    m = re.search(r"(?i)((?:SLP|S\.L\.P\.?)\s*\(?(?:Crl|Civil|C)\.?\)?\s*(?:No\(?s?\)?\.?)?\s*[\d\s,&/-]+(?:of|/)\s*\d{4})", t)
    if m:
        return {"case_no": collapse(m.group(1)), "_src": "slp_no"}
    return {}


def extract_appeal_from(head: str) -> dict:
    t = ocr_norm(head)
    m = re.search(r"(?s)[Ff]rom\s+the\s+(?:[Jj]udgment|[Oo]rder)[^.]{0,40}?dated\s+.{5,250}?\b\d{4}(?=\s*\.|\s+[A-Z]|\s*$)", t)
    if m:
        return {"appeal_from_raw": collapse(m.group(0))[:300], "_src": "from_the_judgment"}
    m = re.search(r"(?is)(?:arises?\s+out\s+of|challenge[sd]?|assail(?:s|ed|ing)?|impugned)[^\n]{0,60}?(?:judgment|order)"
                  r"(?:\s+and\s+order)?\s+dated\s+[\d./\-A-Za-z ,]{6,25}?\s+(?:passed|rendered|made)\s+by\s+the\s+"
                  r"(?:High\s+Court|Supreme\s+Court|Court|Tribunal)[^\n]{0,40}.{0,60}?\bof\s+\d{4}", t)
    if m:
        return {"appeal_from_raw": collapse(m.group(0))[:300], "_src": "arises_out_of"}
    m = re.search(r"(?i)(?:impugned|against)\s+(?:the\s+)?(?:judgment|order)[^.]{0,40}dated\s+(.{5,160}?High\s+Court[^.]{0,80})", t)
    if m:
        return {"appeal_from_raw": collapse(m.group(0))[:300], "_src": "impugned"}
    return {}


def extract_parties(first_page: str, case_no_hint: str = "") -> dict:
    """Reporter title block ('X / v. / Y / DATE'), or slip-opinion 'X ... Appellant(s) / VERSUS / Y ... Respondent(s)'."""
    t = ocr_norm(first_page)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    lines = [l for l in lines if not re.fullmatch(r"[A-H]", l)]
    vs = next((i for i, l in enumerate(lines) if re.fullmatch(r"(?i)v(?:s|ersus)?\.?", l)), None)
    if vs is None:
        vs = next((i for i, l in enumerate(lines) if re.search(r"(?i)\s(?:v\.?|vs\.?|versus)\s", l)), None)
        if vs is None:
            return {}
        a, b = re.split(r"(?i)\s(?:v\.?|vs\.?|versus)\s", lines[vs], maxsplit=1)
        return {"petitioner_regex": a.strip(), "respondent_regex": b.strip(), "_src": "inline_v"}
    pet, i = [], vs - 1
    while i >= 0 and len(pet) < 4 and not re.search(
            r"(?i)jurisdiction|reportable|court of india|^\d|\bno\.?\s*\d|arising|\bof\s+\d{4}\b|^\(|^\[\d{4}\]|S\.?\s?C\.?\s?R|INSC|\bSCC\b", lines[i]):
        pet.insert(0, lines[i]); i -= 1
    res, i = [], vs + 1
    while i < len(lines) and len(res) < 4 and not re.search(
            rf"(?i)^({MONTHS})|^\d{{1,2}}\s+({MONTHS})|^\[|^\(|code of|jurisdiction|appeal|petition", lines[i]):
        res.append(lines[i]); i += 1
    clean = lambda xs: collapse(re.sub(r"^[^A-Za-z0-9(\[]+", "", re.sub(r"(?i)[.…]{2,}.*|….*|\b(appellants?|respondents?|petitioners?)\b.*", "", " ".join(xs))))
    if pet and res:
        return {"petitioner_regex": clean(pet), "respondent_regex": clean(res), "_src": "title_block"}
    return {}


def extract_court(head: str) -> dict:
    t = ocr_norm(head)
    if re.search(r"(?i)supreme\s+court\s+(of\s+india|reports|cases)|SUPREME\s+COURT", t):
        return {"court_regex": "Supreme Court of India", "_src": "supreme_court"}
    m = re.search(r"(?i)in\s+the\s+(high\s+court\s+of[^\n]{3,60})", t)
    return {"court_regex": collapse(m[1]), "_src": "high_court"} if m else {}


# --------------------------------------------------------------------------- zone split + paragraphs


def split_zones(full: str, prof: Profile, flags: list) -> tuple[str, str, str]:
    """returns (headnote, pre_judgment_block, body)."""
    he = None
    for rx in prof.headnote_end:
        m = re.search(rx, full)
        if m:
            he = m.start(); break
    if he is None:
        for rx in UNKNOWN.headnote_end:
            m = re.search(rx, full)
            if m:
                he = m.start(); break
    bs_m = None
    search_from = he or 0
    for rx in prof.body_start:
        m = re.compile(rx).search(full, search_from)
        if m and (bs_m is None or m.start() < bs_m.start() or rx == prof.body_start[0]):
            bs_m = m
            if rx == prof.body_start[0]:
                break
    if he is None:
        flags.append("headnote_end_not_found")
    if bs_m is None:
        flags.append("zone_split_failed_using_whole_text")
        return (full[:he] if he else ""), "", full
    prev = re.findall(r"⟦p\d+⟧", full[:bs_m.start()])
    lead = (prev[-1] + "\n") if prev else ""            # keep the page anchor for the first paragraph
    return (full[:he] if he else ""), (full[he:bs_m.start()] if he else ""), lead + full[bs_m.end():]


NUM_RX = re.compile(r"(?m)^[ \t]*\(?(\d{1,3})[.)]\s+(?=[A-Z“\"(‘'])")


def dehyphen(txt: str) -> str:
    return collapse(re.sub(r"(\w)-\s+(?=[a-z])", r"\1-", txt))


def _inside_quote(seg: str) -> bool:
    """True if the text since the last paragraph start has an unclosed opening quote (a quoted
    judgment's own paragraph numbers must not be taken as this judgment's paragraphs)."""
    return 0 < len(seg) < 12000 and seg.count("\u201c") - seg.count("\u201d") > 0


def _looks_like_first_para(preamble: str) -> bool:
    """Text before a '2.'/'3.' is only a short preface ('Leave granted.', judge's name), so the numbering plausibly starts here."""
    p = re.sub(r"⟦p\d+⟧", " ", preamble)
    return len(collapse(p)) < 250


def segment_numbered(body: str, flags: list):
    """Sequential numbers; tolerates up to 2 skipped numbers once a run of 3 is established
    (OCR often drops a paragraph number). Candidates inside an open quotation are ignored."""
    hits, last, gaps, skipped_quotes = [], 0, [], 0
    for m in NUM_RX.finditer(body):
        n = int(m.group(1))
        # slip opinions often open "Leave granted." (= implicit para 1) then "2." - allow a run to start at 2 or 3
        first_ok = (not hits) and n in (2, 3) and _looks_like_first_para(body[:m.start()])
        ok = n == last + 1 or first_ok or (last >= 3 and last + 1 < n <= last + 3)
        if ok and hits and _inside_quote(body[hits[-1][2]:m.start()]):
            skipped_quotes += 1
            continue
        if ok:
            if n != last + 1 and not first_ok:
                gaps.append(f"{last + 1}-{n - 1}")
            hits.append((m.start(), n, m.end())); last = n
    if hits and hits[0][1] > 1:
        flags.append(f"numbering_starts_at_{hits[0][1]}")
    if gaps:
        flags.append(f"para_number_gaps: {', '.join(gaps)}")
    if skipped_quotes:
        flags.append(f"numbers_inside_quotations_ignored: {skipped_quotes}")
    return hits


def to_paras_numbered(body: str, hits) -> dict:
    """P<n> per numbered paragraph; where the judgment uses 4.1 / 4.2 sub-numbering, the intro stays
    in P4 and each sub-paragraph becomes P4.1, P4.2 ... (matches the reporter's '[Para 7.1]' refs)."""
    marks = [(m.start(), int(m.group(1))) for m in re.finditer(r"⟦p(\d+)⟧", body)]
    pos = [p for p, _ in marks]

    def page_at(i):
        j = bisect.bisect_right(pos, i) - 1
        return marks[j][1] if j >= 0 else None

    def put(paras, pid, a, b):
        txt = re.sub(r"⟦p\d+⟧", " ", body[a:b])
        paras[pid] = {"text": dehyphen(txt), "page_start": page_at(a), "page_end": page_at(b - 1)}

    paras = {}
    for k, (s0, n, e) in enumerate(hits):
        end = hits[k + 1][0] if k + 1 < len(hits) else len(body)
        sub_rx = re.compile(rf"(?m)^[ \t]*{n}\.(\d{{1,2}})\s+(?=[A-Z\u201c\"(\u2018'])")
        subs, last = [], 0
        for m in sub_rx.finditer(body, e, end):
            if int(m.group(1)) == last + 1:
                subs.append((m.start(), m.end(), last + 1)); last += 1
        if not subs:
            put(paras, f"P{n}", e, end)
            continue
        if body[e:subs[0][0]].strip():
            put(paras, f"P{n}", e, subs[0][0])
        for j, (a, b, minor) in enumerate(subs):
            put(paras, f"P{n}.{minor}", b, subs[j + 1][0] if j + 1 < len(subs) else end)
    return paras


MARK = re.compile(r"^⟦p(\d+)⟧$")


def to_paras_unnumbered(body: str) -> dict:
    """Paragraph = run of lines ending in a short line that closes a sentence. Ids are p<page>.<n>."""
    lines = body.split("\n")
    widths = [len(l) for l in lines if len(l) > 30 and not l.startswith("⟦")]
    med = statistics.median(widths) if widths else 60
    paras, cur, page, cur_page, per_page = {}, [], None, None, Counter()

    def flush():
        nonlocal cur
        if cur:
            per_page[cur_page] += 1
            txt = " ".join(cur)
            paras[f"p{cur_page}.{per_page[cur_page]}"] = {"text": dehyphen(txt), "page_start": cur_page,
                                                          "page_end": page}
        cur = []

    for l in lines:
        m = MARK.match(l.strip())
        if m:
            page = int(m.group(1)); continue
        l = l.strip()
        if not l:
            continue
        if not cur:
            cur_page = page
        cur.append(l)
        if re.search(r"[.:;?\"”)]$", l) and len(l) < 0.8 * med:
            flush()
    flush()
    return paras


_CITE = (r"(?:\(\d{4}\)\s*\d+\s*SCC\s*\d+|[\[(]\d{4}[\])]\s*\d+\s*(?:SCC|SCR|S\.C\.R\.?)\s*\d+|"
         r"\d{4}\s+INSC\s+\d+|AIR\s*\(?\d{4}\)?\s*SC\s*\d+)")
_TREAT = r"(?:relied\s+on|referred\s+to|followed|distinguished|applied|overruled|approved|not\s+followed|considered)"


def parse_authority_table(headnote: str) -> list[dict]:
    """Authorities listed by the reporter. Handles
         'Name v. Name, (2014) 2 SCC 171 : [2013] 12 SCR 772 - referred to.'      (headnote list)
         '[2013] 12 SCR 772 referred to para 4.5'                                  (case-law-reference table)
         '<cite> relied on Para 7'                                                 (older SCR tables)
       and merges the paragraph reference onto the named authority when both are present."""
    t = collapse(headnote)
    rows, prev_end = [], 0
    for m in re.finditer(rf"(?P<cite>{_CITE}(?:\s*[:;]\s*{_CITE})*)\s*[,–-]?\s*(?P<treat>{_TREAT})\b", t):
        left = t[prev_end:m.start()]
        name = None
        vs = list(re.finditer(r"\sv\.?\s|\svs\.?\s", left))
        if vs:
            pos = vs[-1].start()
            back = left[max(0, pos - 80):pos]
            bounds = [b.end() for b in re.finditer(r"(?<![A-Z])\.\s+(?=[A-Z])|[\]|;]\s*|Case Law (?:Cited|Reference)\s*", back)]
            cand = (back[bounds[-1]:] if bounds else back) + left[pos:]
            cites = list(re.finditer(_CITE, cand))                      # 'X v. Y, AIR (1996) SC 1042 and Z v. W' -> keep Z v. W
            if cites:
                cand = re.sub(r"^\s*(?:and|&)\s+", "", cand[cites[-1].end():].strip(" ,;:"))
            cand = cand.strip(" ,;:.–-")
            name = cand if 5 < len(cand) < 170 and re.search(r"\sv\.?\s|\svs\.?\s", cand) else None
        para = re.match(r"\s*(?:Paras?\.?\s*)?(\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*)", t[m.end():m.end() + 30], re.I) \
            if re.match(r"\s*(?:Paras?)\b", t[m.end():m.end() + 12], re.I) else None
        rows.append({"name": name, "cite": collapse(m["cite"]), "treatment": re.sub(r"\s+", "_", m["treat"].strip().lower()),   # relied_on / referred_to / not_followed (matches extract.py's Literal)
                     "para": para.group(1) if para else None})
        prev_end = m.end() + (para.end() if para else 0)
    # merge: a cite-only row ("[2013] 12 SCR 772 referred to para 4.5") joins the named row that contains that cite
    merged = []
    for r in rows:
        twin = next((x for x in merged if x["name"] and r["cite"] in x["cite"]), None)
        if twin and not r["name"]:
            twin["para"] = twin["para"] or r["para"]
        else:
            merged.append(r)
    return merged


SECTION_HEADS = ["Issue for Consideration", "Headnotes", "Case Law Cited", "List of Acts", "List of Keywords",
                 "Case Arising From", "Appearances for Parties"]


def extract_sections(text: str) -> dict:
    """Modern SCR headnote blocks, keyed by heading. Empty dict for formats without them."""
    idx = []
    for h in SECTION_HEADS:
        m = re.search(rf"(?im)^\s*{re.escape(h)}\s*[†:]?\s*$", text)
        if m:
            idx.append((m.start(), m.end(), h))
    idx.sort()
    return {h: collapse(text[e:(idx[i + 1][0] if i + 1 < len(idx) else len(text))])
            for i, (_, e, h) in enumerate(idx)}


TRAILER_RX = re.compile(
    r"(?m)^(?:\s*[.…_]{5,}\s*(?:C\.?\s?J\.?\s?I?\.?|J{1,2}\.?)\s*$|\s*Result\s+of\s+the\s+case\s*:|\s*†?\s*Headnotes\s+prepared\s+by\s*:|"
    r"[A-Z][A-Za-z.\s]{3,40}?\s+(?:Appeals?|Petitions?|Writ\s+Petitions?)\b[^\n]{0,40}?"
    r"(?:allowed|dismissed|disposed\s+of)[^\n]{0,30}$)")


def split_trailer(body: str) -> tuple[str, str]:
    """Reporter furniture after the last paragraph ('Devika Gujral Appeal allowed.', 'Result of the case: ...',
    'Headnotes prepared by ...') is not part of the court's words."""
    cut = max(0, len(body) - 700)
    m = TRAILER_RX.search(body, cut)
    return (body[:m.start()], body[m.start():]) if m else (body, "")


def noise_score(text: str) -> float:
    toks = text.split() or ["x"]
    bad = sum(bool(re.search(r"[A-Za-z][^\w\s.,;:'\"()\-\[\]/&–—][A-Za-z]|\b\w*\d\w*[a-z]\w*\b", t)) for t in toks)
    return bad / len(toks)


# --------------------------------------------------------------------------- loaders


def load_pdf(path: str) -> Doc:
    raws, flags, notes = read_pdf_pages(path)
    pages = assign_pages(raws)
    meta: dict = {"source_file": Path(path).name, "pdf_pages": len(raws), "_sources": {}}

    def put(d: dict, label: str):
        if not d:
            flags.append(f"{label}_not_found"); return
        src = d.pop("_src", "?")
        meta.update(d); meta["_sources"][label] = src

    head_raw = "\n".join(raws[:2])
    prof = detect_profile("\n".join(raws[:3]))
    meta["format_profile"] = prof.name
    if prof is UNKNOWN:
        flags.append("format_unrecognised_using_generic_patterns")

    put(extract_citation(raws, pages), "citation")
    put(extract_decided_on(raws[0], head_raw[:2500], "\n".join(raws[-1].splitlines()[-14:])), "decided_on")
    put(extract_coram(head_raw) or extract_coram_from_signatures("\n".join(raws[-2:])), "coram")
    put(extract_parties(raws[0]), "parties")
    put(extract_court(head_raw + "\n" + "\n".join(raws[2:5])), "court")

    # year: decision year is primary; reporting year kept separately
    if meta.get("decided_on"):
        meta["year"] = int(meta["decided_on"][:4]); meta["_sources"]["year"] = "decided_on"
    else:
        for k in ("scr_year", "scc_year", "air_year", "neutral_year"):
            if meta.get(k):
                meta["year"] = meta[k]; meta["_sources"]["year"] = k; break
        else:
            m = re.search(r"\bof\s+(\d{4})\b", meta.get("case_no", ""))
            if m:
                meta["year"] = int(m[1]); meta["_sources"]["year"] = "case_no (filing year - weak)"
                flags.append("year_is_filing_year")
            else:
                flags.append("year_not_found")
    if "year" in meta and meta.get("scr_year") and meta["scr_year"] != meta["year"]:
        flags.append(f"decided_year {meta['year']} != reporter year {meta['scr_year']}")

    drop = frozenset(repeating_lines(raws))
    title = re.sub(r"[^a-z0-9]", "", f"{meta.get('petitioner_regex', '')}v{meta.get('respondent_regex', '')}".lower())
    title = title if meta.get("petitioner_regex") else ""
    full = "\n".join(f"⟦p{pg}⟧\n" + "\n".join(clean_page(r, drop, title)) for pg, r in zip(pages, raws))
    if notes:
        meta["footnotes"] = [{"page": pages[i], "text": t} for i, t in notes]
    headnote, pre_block, body = split_zones(full, prof, flags)
    body, trailer = split_trailer(body)
    if trailer.strip():
        meta["reporter_trailer"] = collapse(re.sub(r"⟦p\d+⟧", " ", trailer))[:400]
        r = re.search(r"(?i)result\s+of\s+the\s+case\s*:\s*([^\n†]{3,80})|((?:appeal|petition)s?[^\n]{0,40}?(?:allowed|dismissed|disposed\s+of)[^\n]{0,30})", trailer)
        if r:
            meta["result_of_case"] = collapse(r.group(1) or r.group(2))
    pre = collapse(re.sub(r"⟦p\d+⟧", " ", pre_block))
    if pre:
        meta["pre_judgment_block"] = pre[:1500]
    # the case number of THIS appeal sits in the pre-judgment block; the headnote only cites other cases
    put(extract_case_no(pre) or extract_case_no(head_raw), "case_no")
    put(extract_appeal_from(pre) or extract_appeal_from(head_raw)
        or extract_appeal_from(re.sub(r"⟦p\d+⟧", " ", body[:1800])), "appeal_from")

    put(extract_author(re.sub(r"⟦p\d+⟧", " ", body[:600]), re.sub(r"⟦p\d+⟧", " ", body[-800:])), "author")
    if not meta.get("judgment_author_regex") and meta.get("judgment_author_from_coram"):
        meta["judgment_author_regex"] = meta["judgment_author_from_coram"]
        meta["_sources"]["author"] = "coram_asterisk"
        flags[:] = [f for f in flags if f != "author_not_found"]

    secs = extract_sections(re.sub(r"⟦p\d+⟧", " ", headnote) + "\n" + re.sub(r"⟦p\d+⟧", " ", pre_block))
    if secs.get("Issue for Consideration"):
        meta["issue_for_consideration"] = secs["Issue for Consideration"]
    if secs.get("List of Keywords"):
        meta["keywords"] = [k.strip(" .") for k in secs["List of Keywords"].split(";") if k.strip(" .")]
    if secs.get("List of Acts"):
        meta["acts_listed"] = [a.strip(" .") for a in re.split(r";|\.\s", secs["List of Acts"]) if a.strip(" .")]

    hits = segment_numbered(body, flags)
    if len(hits) >= 5:
        paras, layout = to_paras_numbered(body, hits), "numbered_paras"
    else:
        paras, layout = to_paras_unnumbered(body), "unnumbered_page_anchored"
        flags = [f for f in flags if not f.startswith("para_number_gaps")]
    meta["layout"] = layout
    ns = noise_score(full)
    meta["ocr_noise_score"] = round(ns, 4)
    if ns > 0.03:
        flags.append("ocr_noisy: copy quotes as printed; never 'correct' names or numbers by guessing")
    if not paras:
        flags.append("no_paragraphs_extracted")
    headnote = re.sub(r"⟦p\d+⟧", " ", headnote)
    return Doc(path, f"pdf:{prof.name}", meta, headnote, paras, parse_authority_table(headnote), flags)


def load_laws_json(path: str) -> Doc:
    j = json.load(open(path, encoding="utf-8"))
    flags = ["laws_json: 'cited_judgments' = cited_by; procedural_history date is unreliable (e.g. '11')"]
    decided = j.get("decided_on")
    year = j.get("decided_on_year")
    if not year and decided:
        m = re.search(r"\b(19|20)\d{2}\b", str(decided))
        year = int(m.group(0)) if m else None
    if not year:
        flags.append("year_not_found")
    meta = {"source_file": Path(path).name, "citation_laws": j.get("case_citation"), "court": j.get("court"),
            "decided_on": decided, "year": year, "coram_raw": j.get("coram"), "layout": "numbered_paras",
            "equivalent_citations": j.get("equivalent_citations"), "cited_by": j.get("cited_judgments")}
    paras = {f"P{p['number']}": {"text": collapse(p["text"]), "page_start": None, "page_end": None}
             for p in j.get("numbered_paragraphs", [])}
    if not paras:
        flags.append("no_paragraphs_extracted")
    return Doc(path, "laws_json", meta, j.get("headnote_raw", ""), paras, [], flags)


def load_document(path: str) -> Doc:
    p = path.lower()
    if p.endswith(".pdf"):
        return load_pdf(path)
    if p.endswith(".json"):
        return load_laws_json(path)
    raise ValueError(f"unsupported file type: {path}")


if __name__ == "__main__":
    import sys
    for fp in sys.argv[1:]:
        d = load_document(fp)
        print(json.dumps({"fmt": d.fmt, "meta": {k: v for k, v in d.meta.items() if k != "cited_by"},
                          "flags": d.flags, "n_paras": len(d.paras), "para_ids": list(d.paras)[:12],
                          "authority_table": d.authority_table}, indent=2, ensure_ascii=False))