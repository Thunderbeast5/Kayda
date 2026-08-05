#!/usr/bin/env python3
"""
Stage 3: Robust, OCR-aware, context-aware PDF -> JSON extractor for
Supreme Court judgments (offenses against women & children domain).

Why this is a rewrite, not a patch:
  The previous version relied entirely on regex against raw extracted text.
  That breaks on scanned/older judgments (margin column-letters bleeding into
  sentences, OCR noise, hyphenation artifacts) and cannot make the semantic
  judgment calls the task actually needs (e.g. "is this section applied to
  the present case, or only mentioned because a cited precedent discussed
  it?", "what did each judge in a multi-opinion judgment actually hold?").

Pipeline:
  1. Layout-aware text extraction (pdfplumber word boxes, margin-letter
     filtering) with a text-quality score.
  2. Automatic Tesseract OCR fallback when the embedded text layer is bad
     (common for older scanned SCR/SCC judgments).
  3. Deterministic artifact cleanup (SCR column tags, hyphenation, whitespace)
     run on whichever extraction won.
  4. LLM (Groq) structured extraction against a strict JSON schema, per
     document -- this is where the context-aware / semantic work happens.
  5. Grounding validation: every section number the LLM claims is "applied
     to the present case" is checked against the cleaned text; anything
     that doesn't ground gets flagged for manual review instead of silently
     trusted.
  6. JSON output, split into a clean folder and a needs_review folder.

Install:
  pip install pdfplumber PyMuPDF pytesseract pdf2image pillow groq pydantic tqdm pandas
  System deps: tesseract-ocr, poppler-utils
  Env var: GROQ_API_KEY
"""

import os
import io
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
import pdfplumber
from tqdm import tqdm
from pydantic import BaseModel, Field, ValidationError

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from groq import Groq

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class Config:
    # __file__ is in backend/data_extraction/scriptsD/stage_3.py
    project_root: Path = Path(__file__).parent.parent.parent.parent

    # Input PDFs
    pdf_input_dir: Path = project_root / 'backend' / 'data_extraction' / 'pdfs' / 'pdf_downloads_2008'

    # Output directories -- clean output vs. flagged-for-manual-review output
    json_output_dir: Path = project_root / 'backend' / 'data_extraction' / 'json' / 'json_output_2008'
    review_dir: Path = project_root / 'backend' / 'data_extraction' / 'json' / 'needs_review_2008'

    # Extraction settings
    max_pages: int = 150
    num_workers: int = 4  # keep modest: OCR is CPU-heavy and Groq has rate limits

    # Text-quality gate for OCR fallback
    quality_threshold: float = 0.90
    ocr_dpi: int = 300

    # Groq LLM settings.
    # openai/gpt-oss-120b is the pick here: it's a real reasoning model (needed
    # for "is this section applied to the present case or just cited from a
    # precedent" style judgment calls) AND it's one of only two models on Groq
    # that support strict JSON-schema mode (constrained decoding -> the output
    # is guaranteed to match CaseExtraction, no malformed-JSON retries needed).
    # openai/gpt-oss-20b is the cheaper/faster fallback with the same guarantee.
    groq_model: str = "openai/gpt-oss-120b"
    groq_api_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))
    max_llm_retries: int = 3
    llm_max_chars: int = 45000  # keep well within context window after cleanup

    # Models on Groq that support strict:true (constrained decoding / guaranteed
    # schema compliance) as of writing. Anything else falls back to json_object
    # mode, which is best-effort only -- update this set if Groq adds support
    # for more models.
    strict_schema_models: tuple = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")


    def __post_init__(self):
        self.json_output_dir.mkdir(parents=True, exist_ok=True)
        self.review_dir.mkdir(parents=True, exist_ok=True)
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY is not set -- LLM extraction will fail at runtime.")


# ============================================================
# EXTRACTION SCHEMA
# ============================================================

class JudgeOpinion(BaseModel):
    judge_name: str = ""
    holding_summary: str = ""
    concurring: bool = True
    dissenting: bool = False
    sections_relied_on: List[str] = Field(default_factory=list)


class CaseExtraction(BaseModel):
    case_title: str = ""
    citation: str = ""
    decision_date: str = ""
    judges: List[str] = Field(default_factory=list)
    bench_type: str = ""  # single / division / full-or-constitution
    case_arising_from: str = ""
    appearances: str = ""
    issue_for_consideration: str = ""
    headnote_summary: str = ""
    opinions: List[JudgeOpinion] = Field(default_factory=list)
    sections_applied_to_present_case: Dict[str, List[str]] = Field(default_factory=dict)
    sections_only_cited_from_precedent: Dict[str, List[str]] = Field(default_factory=dict)
    acts_referred: List[str] = Field(default_factory=list)
    final_disposition: str = ""
    is_domain_relevant: bool = True
    domain_relevance_reason: str = ""


SECTION_KEYS = ["ipc", "bns", "crpc", "pocso", "dowry_act", "posh_act", "it_act", "other"]

EXTRACTION_SCHEMA_HINT = {
    "case_title": "string, 'Petitioner v. Respondent'",
    "citation": "string, e.g. '[2008] 2 S.C.R. 323' or '2008 INSC 117'",
    "decision_date": "string",
    "judges": ["string"],
    "bench_type": "one of: single, division, full/constitution",
    "case_arising_from": "which court/order this appeal arises from",
    "appearances": "counsel for each party, as plain text",
    "issue_for_consideration": "the precise legal question(s) the court had to decide -- NOT a general summary of facts",
    "headnote_summary": "2-5 sentence summary of what was held",
    "opinions": [
        {
            "judge_name": "string",
            "holding_summary": "string",
            "concurring": "bool",
            "dissenting": "bool",
            "sections_relied_on": ["string"],
        }
    ],
    "sections_applied_to_present_case": {k: ["e.g. '376', '304B', '498A'"] for k in SECTION_KEYS},
    "sections_only_cited_from_precedent": {
        k: ["sections that ONLY appear because a cited case discussed them"] for k in SECTION_KEYS
    },
    "acts_referred": ["full names of special acts referenced, e.g. 'POCSO Act, 2012'"],
    "final_disposition": "e.g. 'appeal dismissed', 'conviction upheld', 'sentence modified'",
    "is_domain_relevant": (
        "true only if the actual legal issue being adjudicated concerns an offense "
        "against women or children -- not merely incidental background facts"
    ),
    "domain_relevance_reason": "one sentence justifying is_domain_relevant",
}

def _to_strict_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively patch a Pydantic-generated JSON schema so it satisfies
    Groq's strict-mode requirements: every object must set
    additionalProperties=false and list ALL of its properties as required
    (strict mode has no concept of "optional but present in schema")."""
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        for prop_schema in schema["properties"].values():
            _to_strict_json_schema(prop_schema)
    if schema.get("type") == "array" and "items" in schema:
        _to_strict_json_schema(schema["items"])
    for defs_key in ("$defs", "definitions"):
        if defs_key in schema:
            for sub_schema in schema[defs_key].values():
                _to_strict_json_schema(sub_schema)
    return schema


SYSTEM_PROMPT = """You are a precise legal-document extraction engine for Indian Supreme Court \
judgments. You will be given the OCR-extracted, cleaned text of a single judgment. This text comes \
from OCR and WILL contain character-recognition errors -- most commonly digit/letter confusions such \
as 8<->B, 0<->O, 5<->S, 1<->I/l, 2<->Z, 6<->G, 4<->A. Section numbers are frequently mis-OCR'd this \
way (e.g. "304B" often appears in the text as "3048", "498A" as "4984" or "498/\\", "376" as "3?6").

Extract structured data and return ONLY valid JSON matching the schema you are given -- no prose, no \
markdown fences, no commentary.

Critical rules:
1. Distinguish sections APPLIED in the present case (the accused was charged/convicted under them,
   or the appeal itself concerns them) from sections that appear ONLY because a cited precedent
   discussed them (e.g. inside a "referred to" / "distinguished" case list, or inside a quoted
   extract from another judgment). Put the former in sections_applied_to_present_case and the
   latter in sections_only_cited_from_precedent. If you are unsure which bucket a section belongs
   in, prefer sections_only_cited_from_precedent.
2. If the judgment has multiple judges writing separate opinions (concurring or dissenting), list
   each one separately in "opinions". Do not merge two judges' reasoning into one entry.
3. issue_for_consideration must be the actual legal question the court decided (e.g. "whether a
   Managing Director falls within the exemption under s.3(1)(h) of the Act"), not a restatement of
   the underlying facts (e.g. "an employee was assaulted"). If the case is not substantively about
   an offense against women or children -- e.g. it discusses such an offense only as background to
   an unrelated statutory or procedural question -- set is_domain_relevant to false and say why in
   domain_relevance_reason.
4. Only include section numbers that are actually referenced in the supplied text (allowing for the
   OCR errors described above). Do not infer, guess, or fill in numbers from general legal knowledge
   that are not referenced anywhere in the text at all.
5. When you encounter an OCR-garbled section number, resolve it to the REAL section of that Act that
   best fits both the garbled characters and the legal context (e.g. dowry-death discussion + a
   provision that reads as "3048" near "IPC" -> this is section 304B, since 304B is the actual IPC
   dowry-death provision and "8" is a common OCR misread of "B"; there is no section "304C" or "3048"
   in the IPC). Prefer real, well-known sections of the named Act over ones that do not exist in that
   Act. If you are not confident which real section is meant, include it in sections_only_cited_from_precedent
   instead of guessing into sections_applied_to_present_case.
6. When sections are cited together as a list -- "3/4", "3 and 4", "323/504/506", "ss. 5(m) and 6" --
   extract EVERY individual section number in that list, not just the last one. Re-check each such
   list in the text before finalizing your answer to make sure none were dropped.
7. If a field cannot be determined from the text, use an empty string, empty list, or empty dict --
   never invent data to fill a field.

Reference: real, commonly-cited sections in this domain (offenses against women & children) include
IPC 302, 304, 304B, 306, 313, 323, 325, 354, 354A, 354B, 354C, 354D, 375, 376, 376A, 376B, 376C, 376D,
376E, 377, 493, 494, 495, 496, 497, 498, 498A; Dowry Prohibition Act 1961 ss. 3, 4, 4A, 5, 6, 7, 8, 8A,
8B; POCSO Act 2012 ss. 3-20; CrPC ss. 154, 156, 161, 164, 173, 313, 437, 438, 439, 482. Use this list
only to help disambiguate OCR noise -- do not add a section from this list unless it is actually
referenced in the supplied text.
"""

# ============================================================
# STAGE A: ROBUST, LAYOUT-AWARE TEXT EXTRACTION WITH OCR FALLBACK
# ============================================================

class RobustPDFExtractor:
    """
    Layout-aware extraction with margin-artifact filtering, a text-quality
    score, and an automatic OCR fallback for scanned/noisy PDFs.
    """

    # SCR/SCC print editions place a single capital letter (A-H) in the
    # margin to mark column position for citation purposes. This is layout
    # furniture, not content, and pollutes sentences if left in.
    MARGIN_LETTER_RE = re.compile(r'^[A-H]$')

    def __init__(self, config: Config):
        self.config = config

    def _extract_words_pdfplumber(self, page) -> str:
        """Extract via word bounding boxes; drop isolated margin-letter tokens
        living in the outer ~6% of the page width before reconstructing lines."""
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        if not words:
            return ""

        page_width = page.width
        margin_band = 0.06 * page_width

        kept = []
        for w in words:
            text = w['text'].strip()
            if not text:
                continue
            in_margin_zone = (w['x0'] < margin_band) or (w['x1'] > page_width - margin_band)
            if in_margin_zone and self.MARGIN_LETTER_RE.match(text):
                continue  # drop the column-position tag
            kept.append(w)

        # Reconstruct reading order: group into lines by vertical position,
        # then left-to-right within each line.
        kept.sort(key=lambda w: (round(w['top'] / 3), w['x0']))
        lines: List[str] = []
        current_line: List[dict] = []
        last_bucket = None
        for w in kept:
            bucket = round(w['top'] / 3)
            if last_bucket is not None and bucket != last_bucket:
                lines.append(' '.join(x['text'] for x in current_line))
                current_line = []
            current_line.append(w)
            last_bucket = bucket
        if current_line:
            lines.append(' '.join(x['text'] for x in current_line))

        return '\n'.join(lines)

    @staticmethod
    def text_quality_score(text: str) -> float:
        """Heuristic 0-1 score: higher means cleaner text, less OCR garbage.
        This replaces the old "len(text) > 100 => is_digital" check, which
        treats garbled OCR text as trustworthy just because it's non-empty."""
        words = re.findall(r"[A-Za-z']+", text)
        if len(words) < 20:
            return 0.0
        junk = 0
        for w in words:
            if len(w) == 1 and w.lower() not in ('a', 'i'):
                junk += 1  # stray single letters (often leaked margin tags)
            elif len(w) > 3 and re.search(r'[^aeiouAEIOU]{5,}', w):
                junk += 1  # unlikely consonant clusters -> OCR garble
        return max(0.0, 1 - (junk / len(words)))

    def _ocr_page(self, doc: 'fitz.Document', page_idx: int) -> str:
        if not OCR_AVAILABLE:
            return ""
        page = doc[page_idx]
        mat = fitz.Matrix(self.config.ocr_dpi / 72, self.config.ocr_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        try:
            return pytesseract.image_to_string(img, config='--psm 6')
        except Exception as e:
            logger.debug(f"Tesseract failed on page {page_idx}: {e}")
            return ""

    def extract(self, pdf_path: Path) -> Dict[str, Any]:
        """Try layout-aware pdfplumber first, fall back to PyMuPDF blocks,
        and finally to Tesseract OCR if nothing produces clean-enough text.
        Returns dict: text, pages, extraction_method, quality_score."""
        result = {"text": "", "pages": 0, "extraction_method": "none", "quality_score": 0.0}

        # Pass 1: layout-aware pdfplumber extraction
        try:
            with pdfplumber.open(pdf_path) as pdf:
                n_pages = min(len(pdf.pages), self.config.max_pages)
                result["pages"] = len(pdf.pages)
                page_texts = [self._extract_words_pdfplumber(p) for p in pdf.pages[:n_pages]]
                text = "\n\n".join(t for t in page_texts if t.strip())
                score = self.text_quality_score(text)
                result["text"], result["quality_score"], result["extraction_method"] = (
                    text, score, "pdfplumber_layout"
                )
        except Exception as e:
            logger.debug(f"pdfplumber layout extraction failed for {pdf_path.name}: {e}")

        if result["quality_score"] >= self.config.quality_threshold:
            return result

        # Pass 2: PyMuPDF raw block extraction as a secondary signal
        try:
            doc = fitz.open(pdf_path)
            result["pages"] = result["pages"] or len(doc)
            blocks_text = []
            for i in range(min(len(doc), self.config.max_pages)):
                for b in doc[i].get_text("blocks", sort=True):
                    t = b[4].strip()
                    if t:
                        blocks_text.append(t)
            fitz_text = "\n\n".join(blocks_text)
            fitz_score = self.text_quality_score(fitz_text)
            if fitz_score > result["quality_score"]:
                result["text"], result["quality_score"], result["extraction_method"] = (
                    fitz_text, fitz_score, "pymupdf_blocks"
                )
            doc.close()
        except Exception as e:
            logger.debug(f"PyMuPDF extraction failed for {pdf_path.name}: {e}")

        if result["quality_score"] >= self.config.quality_threshold or not OCR_AVAILABLE:
            if not OCR_AVAILABLE and result["quality_score"] < self.config.quality_threshold:
                logger.warning(
                    f"{pdf_path.name}: text quality {result['quality_score']:.2f} is below "
                    f"threshold but pytesseract is not installed -- proceeding with best-effort text."
                )
            return result

        # Pass 3: OCR fallback -- the embedded text layer is bad/missing (scan)
        logger.info(f"Falling back to OCR for {pdf_path.name} (quality={result['quality_score']:.2f})")
        try:
            doc = fitz.open(pdf_path)
            n_pages = min(len(doc), self.config.max_pages)
            ocr_pages = [self._ocr_page(doc, i) for i in range(n_pages)]
            doc.close()
            ocr_text = "\n\n".join(t for t in ocr_pages if t.strip())
            ocr_score = self.text_quality_score(ocr_text)
            if ocr_score > result["quality_score"]:
                result["text"], result["quality_score"], result["extraction_method"] = (
                    ocr_text, ocr_score, "tesseract_ocr"
                )
        except Exception as e:
            logger.debug(f"OCR fallback failed for {pdf_path.name}: {e}")

        return result

    @staticmethod
    def clean_artifacts(text: str) -> str:
        """Deterministic cleanup applied after extraction, regardless of method."""
        # Stray isolated margin letters that survived line reconstruction
        text = re.sub(r'(?<=\n)[A-H](?=\n)', '', text)
        text = re.sub(r'(?<=\s)[A-H](?=\s)', ' ', text)
        # De-hyphenate line-break-split words: "compli-\ncity" -> "complicity"
        text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ============================================================
# STAGE B: LLM STRUCTURED EXTRACTION (GROQ)
# ============================================================

class GroqExtractor:
    """Context-aware structured extraction. This is where the semantic
    judgment calls happen -- present-case vs. cited-precedent sections,
    per-judge opinions, and domain relevance -- instead of regex heuristics."""

    def __init__(self, config: Config):
        self.config = config
        self.client = Groq(api_key=config.groq_api_key) if config.groq_api_key else None
        self.use_strict = config.groq_model in config.strict_schema_models
        if self.use_strict:
            self.json_schema = _to_strict_json_schema(CaseExtraction.model_json_schema())
        else:
            logger.warning(
                f"Model '{config.groq_model}' is not in strict_schema_models -- falling back to "
                f"best-effort json_object mode. Malformed/off-schema output is more likely; "
                f"prefer openai/gpt-oss-120b or openai/gpt-oss-20b if possible."
            )

    def _response_format(self) -> Dict[str, Any]:
        if self.use_strict:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "case_extraction",
                    "strict": True,
                    "schema": self.json_schema,
                },
            }
        return {"type": "json_object"}

    def extract(self, text: str) -> Optional[CaseExtraction]:
        if not self.client:
            raise RuntimeError("GROQ_API_KEY not configured")

        truncated = text[: self.config.llm_max_chars]
        # In strict mode the schema itself is passed via response_format, so the
        # hint in the prompt is just for the model's benefit, not for validation.
        user_prompt = (
            "Extract structured data from this Supreme Court judgment text. Field meanings:\n"
            f"{json.dumps(EXTRACTION_SCHEMA_HINT, indent=2)}\n\n"
            f"JUDGMENT TEXT:\n{truncated}"
        )

        last_err: Optional[Exception] = None
        for attempt in range(1, self.config.max_llm_retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config.groq_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0,
                    response_format=self._response_format(),
                )
                raw = resp.choices[0].message.content
                data = json.loads(raw)
                return CaseExtraction.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = e
                logger.warning(f"LLM output failed schema validation (attempt {attempt}): {e}")
                time.sleep(1.5 * attempt)
            except Exception as e:
                last_err = e
                logger.warning(f"Groq call failed (attempt {attempt}): {e}")
                time.sleep(2.0 * attempt)

        logger.error(f"All LLM extraction attempts failed: {last_err}")
        return None


# ============================================================
# STAGE C: GROUNDING VALIDATION (OCR-tolerant)
# ============================================================
#
# The previous exact-match version flagged real, correct extractions as
# "ungrounded" whenever the source OCR had mangled a section number (e.g.
# the source text literally contains "3048" because OCR read "B" as "8",
# but the LLM correctly resolved it to the real section, 304B). An exact
# substring check can never account for that. Instead we extract number-like
# tokens from the text and allow a small edit distance for tokens long
# enough that a 1-character OCR slip is a plausible explanation, while still
# requiring an exact match for short tokens (single/double digit section
# numbers, e.g. Dowry Prohibition Act ss. 3/4) where fuzzy matching would
# produce false positives against unrelated numbers.

_NUMERIC_TOKEN_RE = re.compile(r'\b\d{1,4}[A-Za-z]{0,2}\b')


def _normalize_for_grounding(s: str) -> str:
    return re.sub(r'[\s\(\)\-]', '', s).upper()


def _extract_numeric_tokens(text: str) -> Set[str]:
    return {_normalize_for_grounding(t) for t in _NUMERIC_TOKEN_RE.findall(text)}


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(
                prev[j] + 1,        # deletion
                cur[j - 1] + 1,     # insertion
                prev[j - 1] + (ca != cb),  # substitution
            )
        prev = cur
    return prev[-1]


def _is_grounded(candidate: str, text_tokens: Set[str]) -> bool:
    """Exact match always counts. For candidates of length >= 3 (e.g. "304B",
    "376A"), also accept a token within edit distance 1 -- this is exactly
    the OCR digit/letter confusion case (304B vs 3048). Short candidates
    (length <= 2, e.g. plain Dowry Prohibition Act section numbers like "3",
    "4") require an exact match, since fuzzy matching on 1-2 character
    strings would match almost any nearby number."""
    cand = _normalize_for_grounding(candidate)
    if cand in text_tokens:
        return True
    if len(cand) < 3:
        return False
    for tok in text_tokens:
        if abs(len(tok) - len(cand)) <= 1 and _levenshtein(cand, tok) <= 1:
            return True
    return False


def validate_grounding(extraction: CaseExtraction, cleaned_text: str) -> List[str]:
    """Flag section numbers the LLM claims are present but that don't
    actually appear in the cleaned text (allowing for plausible OCR noise).
    Catches genuine hallucination without penalizing correct OCR-error
    resolution."""
    warnings = []
    text_tokens = _extract_numeric_tokens(cleaned_text)
    for act, sections in extraction.sections_applied_to_present_case.items():
        for s in sections:
            if not _is_grounded(s, text_tokens):
                warnings.append(f"Ungrounded section: {act}:{s}")
    return warnings


# ============================================================
# PIPELINE
# ============================================================

class JudgmentPipeline:
    def __init__(self, config: Config):
        self.config = config
        self.extractor = RobustPDFExtractor(config)
        self.llm = GroqExtractor(config)

    def process_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "case_id": pdf_path.stem,
            "file_name": pdf_path.name,
            "file_size": pdf_path.stat().st_size,
            "extraction_date": datetime.now().isoformat(),
            "has_error": False,
            "error_message": "",
            "needs_review": False,
            "review_reasons": [],
        }

        # --- Stage A: robust text extraction ---
        raw = self.extractor.extract(pdf_path)
        result["pages"] = raw["pages"]
        result["text_extraction_method"] = raw["extraction_method"]
        result["text_quality_score"] = round(raw["quality_score"], 3)

        if not raw["text"] or len(raw["text"].strip()) < 50:
            result["has_error"] = True
            result["error_message"] = "No usable text extracted (digital layer and OCR both failed)"
            return result

        cleaned = self.extractor.clean_artifacts(raw["text"])
        result["full_text"] = cleaned

        if raw["quality_score"] < self.config.quality_threshold:
            result["needs_review"] = True
            result["review_reasons"].append(f"low text quality score ({raw['quality_score']:.2f})")

        # --- Stage B: LLM structured extraction ---
        try:
            extraction = self.llm.extract(cleaned)
        except Exception as e:
            result["has_error"] = True
            result["error_message"] = f"LLM extraction error: {e}"
            return result

        if extraction is None:
            result["has_error"] = True
            result["error_message"] = "LLM extraction failed after retries"
            return result

        result.update(extraction.model_dump())

        # --- Stage C: grounding validation ---
        grounding_warnings = validate_grounding(extraction, cleaned)
        if grounding_warnings:
            result["needs_review"] = True
            result["review_reasons"].extend(grounding_warnings)

        if not extraction.is_domain_relevant:
            result["needs_review"] = True
            result["review_reasons"].append("flagged as not domain-relevant by LLM")

        return result

    def save(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save result to appropriate directory:
        - json_output_dir: Only successful extractions without LLM errors
        - review_dir: Cases that succeeded but need review (low quality, ungrounded sections, etc.)
        - NOT SAVED: Cases with LLM extraction errors (has_error = True)
        """
        # Don't save failed extractions at all
        if result.get("has_error"):
            result["json_saved"] = False
            result["json_path"] = "NOT_SAVED (extraction failed)"
            logger.warning(f"❌ Skipping save for {result['case_id']} - {result.get('error_message', 'extraction failed')}")
            return result
        
        # Determine output directory for successful extractions
        # Cases needing review go to review_dir, clean cases go to json_output_dir
        if result.get("needs_review"):
            out_dir = self.config.review_dir
        else:
            out_dir = self.config.json_output_dir
        
        json_path = out_dir / f"{result['case_id']}.json"
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            result["json_saved"] = True
            result["json_path"] = str(json_path)
        except Exception as e:
            result["json_saved"] = False
            result["json_error"] = str(e)
            logger.error(f"Failed to save JSON for {result['case_id']}: {e}")
        return result

    def run_one(self, pdf_path: Path) -> Dict[str, Any]:
        result = self.process_pdf(pdf_path)
        return self.save(result)


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    print("=" * 70)
    print("STAGE 3: ROBUST, OCR-AWARE, CONTEXT-AWARE JUDGMENT EXTRACTOR")
    print("=" * 70)

    config = Config()

    if not config.groq_api_key:
        logger.error("GROQ_API_KEY is not set. Export it before running: export GROQ_API_KEY=...")
        return

    if not config.pdf_input_dir.exists():
        logger.error(f"PDF directory not found: {config.pdf_input_dir}")
        return

    pdf_files = list(config.pdf_input_dir.glob('*.pdf'))
    if not pdf_files:
        logger.error(f"No PDFs found in: {config.pdf_input_dir}")
        return

    logger.info(f"Found {len(pdf_files)} PDF files to extract")
    pipeline = JudgmentPipeline(config)
    results: List[Dict[str, Any]] = []

    print(f"\nExtracting JSONs using {config.num_workers} threads...")
    with ThreadPoolExecutor(max_workers=config.num_workers) as executor:
        futures = {executor.submit(pipeline.run_one, pdf): pdf for pdf in pdf_files}

        for future in tqdm(as_completed(futures), total=len(pdf_files), desc="Extracting"):
            try:
                results.append(future.result())
            except Exception as e:
                pdf_path = futures[future]
                logger.error(f"Exception processing {pdf_path.name}: {e}")
                results.append({"case_id": pdf_path.stem, "has_error": True, "error_message": str(e)})

    # Calculate stats
    successes = len([r for r in results if not r.get('has_error', False)])
    clean_output = len([r for r in results if not r.get('has_error', False) and not r.get('needs_review', False)])
    needs_review = len([r for r in results if not r.get('has_error', False) and r.get('needs_review', False)])
    failures = len([r for r in results if r.get('has_error', False)])

    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"Total PDFs:           {len(pdf_files)}")
    print(f"Successfully processed: {successes}")
    print(f"  ✅ Clean output:     {clean_output}  -> {config.json_output_dir}")
    print(f"  ⚠️  Needs review:     {needs_review}  -> {config.review_dir}")
    print(f"❌ Failed (not saved): {failures}")
    print("=" * 70)


if __name__ == "__main__":
    main()