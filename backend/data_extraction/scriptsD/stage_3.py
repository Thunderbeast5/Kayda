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
  4. LLM (local, via Ollama) structured extraction against a JSON schema,
     per document -- this is where the context-aware / semantic work happens.
  5. Grounding validation: every section number the LLM claims is "applied
     to the present case" is checked against the cleaned text; anything
     that doesn't ground gets flagged for manual review instead of silently
     trusted.
  6. JSON output, split into a clean folder and a needs_review folder.

Install:
  pip install pdfplumber PyMuPDF pytesseract pdf2image pillow ollama pydantic tqdm pandas
  System deps: tesseract-ocr, poppler-utils
  Requires a running local Ollama server (https://ollama.com) with a model
  pulled, e.g.:
      ollama pull qwen2.5:14b
  Env vars (optional):
      OLLAMA_MODEL  -- model name to use (default: "llama3.2")
      OLLAMA_HOST   -- Ollama server URL (default: "http://localhost:11434")
"""

import os
import io
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
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

import ollama

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
    # Keep modest: OCR is CPU-heavy, and a local Ollama server typically only
    # processes one generation at a time per model (unless you've configured
    # OLLAMA_NUM_PARALLEL), so extra workers mostly just queue up.
    num_workers: int = 2

    # Text-quality gate for OCR fallback
    quality_threshold: float = 0.90
    ocr_dpi: int = 300

    # Local LLM settings (served by Ollama).
    # Pick a model you've pulled locally that's strong enough for real
    # reasoning (needed for "is this section applied to the present case or
    # just cited from a precedent" style judgment calls) and that supports
    # Ollama's structured-output mode (nearly all current models do -- Ollama
    # constrains decoding to the JSON schema itself, so this is the same
    # guarantee Groq's strict mode gave us: no malformed-JSON retries needed).
    # Good options if you haven't pulled one yet: qwen2.5:14b, llama3.1:8b,
    # mistral-nemo. Bigger/instruction-tuned models generally do better on the
    # nuanced "applied vs. merely cited" judgment calls this schema asks for.
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.2"))
    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    max_llm_retries: int = 3
    llm_max_chars: int = 45000  # keep well within context window after cleanup

    # CRITICAL: Ollama defaults num_ctx to a small window (often 2048-4096
    # tokens) *regardless of what the model actually supports*, and it will
    # silently truncate the prompt to fit rather than erroring. Our judgment
    # text alone can be ~45,000 chars (~12-15k tokens), plus the system
    # prompt and the full JSON schema on top -- comfortably larger than the
    # default. If num_ctx isn't raised, the model may only ever see the
    # first page or two of the document, yet still has to fill in every
    # required JSON field -- producing exactly the kind of "same garbage
    # copied into every bucket, real sections from later pages missing
    # entirely" output this pipeline has been seeing. 32768 covers
    # llm_max_chars with room for the prompt/schema/output; raise further if
    # you increase llm_max_chars, and confirm your pulled model actually
    # supports the window you request (check `ollama show <model>`).
    ollama_num_ctx: int = field(default_factory=lambda: int(os.environ.get("OLLAMA_NUM_CTX", "32768")))

    def __post_init__(self):
        self.json_output_dir.mkdir(parents=True, exist_ok=True)
        self.review_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# EXTRACTION SCHEMA
# ============================================================

class JudgeOpinion(BaseModel):
    judge_name: str = ""
    holding_summary: str = ""
    concurring: bool = True
    dissenting: bool = False
    sections_relied_on: List[str] = Field(default_factory=list)


# NOTE: this MUST be a fixed set of named fields, not Dict[str, List[str]].
# A free-form Dict compiles to an open "additionalProperties" JSON schema --
# even in strict mode -- so nothing stops the model from inventing its own
# keys. In practice it did exactly that: instead of bucketing sections under
# one of the real Act keys below, it invented keys like "section_13" out of
# paragraph/citation numbers ("Para - 13", "(2005) 3 SCC 114") that aren't
# statutory sections at all. Fixed named fields force a real choice among the
# 8 known buckets and make additionalProperties=False actually mean something.
class SectionsByAct(BaseModel):
    ipc: List[str] = Field(default_factory=list)
    bns: List[str] = Field(default_factory=list)
    crpc: List[str] = Field(default_factory=list)
    pocso: List[str] = Field(default_factory=list)
    dowry_act: List[str] = Field(default_factory=list)
    posh_act: List[str] = Field(default_factory=list)
    it_act: List[str] = Field(default_factory=list)
    other: List[str] = Field(default_factory=list)


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
    sections_applied_to_present_case: SectionsByAct = Field(default_factory=SectionsByAct)
    sections_only_cited_from_precedent: SectionsByAct = Field(default_factory=SectionsByAct)
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
1. Distinguish sections APPLIED in the present case (the accused was charged/convicted/acquitted under
   them at trial or on appeal -- this is true EVEN IF the current opinion is discussing what a lower
   court did, e.g. an appeal against acquittal reviewing the original trial-court charge) from sections
   that appear ONLY because a DIFFERENT, cited precedent case discussed them (e.g. inside a "referred
   to" / "distinguished" case list about someone else's facts, or inside a quoted extract from another
   judgment about a different accused). The key test: was this section applied to THIS appellant/
   accused, in THIS litigation, at any stage (trial, first appeal, or the present appeal)? If yes, it
   is "applied to the present case" no matter which court is currently being described as having
   applied it. Only use sections_only_cited_from_precedent for sections tied to a genuinely different
   case's facts. If you are unsure which bucket a section belongs in, prefer
   sections_only_cited_from_precedent.
1b. Each section number must be placed under the Act it actually belongs to, matching the Act name/
   abbreviation written next to it in the text (IPC/Penal Code -> ipc, Cr.P.C./Code of Criminal
   Procedure -> crpc, POCSO -> pocso, Dowry Prohibition Act -> dowry_act, POSH -> posh_act, IT Act ->
   it_act). The same bare number can be a real section of more than one Act (e.g. 420 is IPC (cheating)
   but is NOT a CrPC section) -- never place a number under a bucket just because it looks plausible;
   place it only under the Act explicitly named beside it in the source text. If the text does not
   name an Act next to a number at all, do not guess an Act -- put it under "other" instead of forcing
   it into ipc/crpc/etc.
2. If the judgment has multiple judges writing separate opinions (concurring or dissenting), list
   each one separately in "opinions". Do not merge two judges' reasoning into one entry.
2b. The top-level "judges" list must include EVERY judge named in the bench/coram line at the top of
   the judgment (e.g. "(DR. ARIJIT PASAYAT AND DR. MUKUNDAKAM SHARMA, JJ.)" -> both names), even when
   only one judge authored the single judgment delivered "for the Court" and the others did not write
   separately. Do not shrink this list down to only the author of the judgment text.
3. issue_for_consideration must be the actual legal question the court decided (e.g. "whether a
   Managing Director falls within the exemption under s.3(1)(h) of the Act"), not a restatement of
   the underlying facts (e.g. "an employee was assaulted"). If the case is not substantively about
   an offense against women or children -- e.g. it discusses such an offense only as background to
   an unrelated statutory or procedural question -- set is_domain_relevant to false and say why in
   domain_relevance_reason.
4. Only include section numbers that are actually referenced in the supplied text (allowing for the
   OCR errors described above). Do not infer, guess, or fill in numbers from general legal knowledge
   that are not referenced anywhere in the text at all.
4b. CRITICAL -- do not confuse a statutory section number with any other number that happens to
   appear in the text. Indian Supreme Court judgments are full of numbers that are NOT section
   numbers: paragraph markers ("Para - 16", "(Para 22)"), page/column references ("[99-D]",
   "101-F; 102-A"), citation volumes and years ("(2005) 3 SCC 114", "AIR 1952 SC 343", "[2008] 13
   S.C.R. 81"), case numbers ("Criminal Appeal No.1409 of 2008"), and dates. A real statutory section
   reference is textually tied to an Act name or a recognized abbreviation -- e.g. "Section 302",
   "S.376(2)(f)", "s.366 Cr.P.C.", "u/s 498A IPC", "POCSO Act s.6". If a bare number is not accompanied
   by one of these markers (Section/S./s./u/s/ Act name) anywhere near it, it is NOT a section number
   and must not appear anywhere in sections_applied_to_present_case or
   sections_only_cited_from_precedent, no matter how prominent that number looks in the text (e.g. a
   paragraph heading "16." followed by legal-sounding text is still just a paragraph number, not
   Section 16 of anything).
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
8. "sections_relied_on" inside each judge's opinion must contain ONLY bare statutory section numbers
   (e.g. "302", "376(2)(f)") -- the same kind of value that goes into sections_applied_to_present_case.
   NEVER put a case name, party names, or a law-report citation (e.g. "Pratap Misra v. State of
   Orissa (1977) 3 SCC 41") into sections_relied_on; cited case law is not captured anywhere in this
   schema and should simply be omitted, not stuffed into the wrong field. Copy citation years and
   volume numbers (e.g. "(1977) 3 SCC 41") character-for-character from the text if you mention them
   anywhere in a summary field -- do not alter the volume number.
9. When a summary field describes what a specific witness (PW-1, PW-2, "the prosecutrix", "the
   complainant", etc.) said, first locate in the text exactly who that witness number refers to (the
   judgment states this explicitly, e.g. "PW1, the husband of the prosecutrix, deposed that...") and
   attribute the statement to that person's actual role. Do not assume witness numbering by proximity
   or by which party you expect to speak first -- verify each PW number against its explicit
   identification in the text before writing a sentence that names it.

Reference: real, commonly-cited sections in this domain (offenses against women & children) include
IPC 302, 304, 304B, 306, 313, 323, 325, 342, 354, 354A, 354B, 354C, 354D, 375, 376, 376A, 376B, 376C,
376D, 376E, 377, 420, 493, 494, 495, 496, 497, 498, 498A; Dowry Prohibition Act 1961 ss. 3, 4, 4A, 5, 6,
7, 8, 8A, 8B; POCSO Act 2012 ss. 3-20; CrPC ss. 154, 156, 161, 164, 173, 313, 378, 437, 438, 439, 482.
Note IPC and CrPC numbering overlaps (e.g. 420 is IPC only; 378 is CrPC only) -- match the number to
the Act actually named beside it in the text, never by assuming which Act a number "usually" belongs
to. Use this list only to help disambiguate OCR noise -- do not add a section from this list unless it
is actually referenced in the supplied text.
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
# STAGE B: LLM STRUCTURED EXTRACTION (LOCAL, VIA OLLAMA)
# ============================================================

class OllamaExtractor:
    """Context-aware structured extraction. This is where the semantic
    judgment calls happen -- present-case vs. cited-precedent sections,
    per-judge opinions, and domain relevance -- instead of regex heuristics.

    Runs entirely against a local Ollama server instead of a hosted API.
    Ollama's `format` parameter accepts a JSON schema and constrains decoding
    to match it (grammar-based, similar guarantee to Groq's strict mode), so
    we reuse the same schema-patching helper as before."""

    def __init__(self, config: Config):
        self.config = config
        self.client = ollama.Client(host=config.ollama_host)
        self.json_schema = _to_strict_json_schema(CaseExtraction.model_json_schema())
        self._check_model_available()

    def _check_model_available(self) -> None:
        """Fail fast with a clear message if the server is unreachable or the
        model hasn't been pulled, instead of surfacing a confusing error deep
        inside a worker thread later."""
        try:
            local_models = {m.get("model", m.get("name", "")) for m in self.client.list().get("models", [])}
        except Exception as e:
            raise RuntimeError(
                f"Could not reach Ollama server at {self.config.ollama_host} -- "
                f"is it running? (`ollama serve`). Original error: {e}"
            )
        target = self.config.ollama_model
        if not any(m == target or m.startswith(target + ":") or target.startswith(m.split(":")[0]) for m in local_models):
            logger.warning(
                f"Model '{target}' was not found in `ollama list` output. If extraction fails, "
                f"pull it first: ollama pull {target}"
            )

    def extract(self, text: str) -> Optional[CaseExtraction]:
        truncated = text[: self.config.llm_max_chars]
        user_prompt = (
            "Extract structured data from this Supreme Court judgment text. Field meanings:\n"
            f"{json.dumps(EXTRACTION_SCHEMA_HINT, indent=2)}\n\n"
            f"JUDGMENT TEXT:\n{truncated}"
        )

        last_err: Optional[Exception] = None
        for attempt in range(1, self.config.max_llm_retries + 1):
            try:
                resp = self.client.chat(
                    model=self.config.ollama_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    format=self.json_schema,
                    options={"temperature": 0, "num_ctx": self.config.ollama_num_ctx},
                )
                raw = resp["message"]["content"]
                data = json.loads(raw)
                return CaseExtraction.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = e
                logger.warning(f"LLM output failed schema validation (attempt {attempt}): {e}")
                time.sleep(1.5 * attempt)
            except Exception as e:
                last_err = e
                logger.warning(f"Ollama call failed (attempt {attempt}): {e}")
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

# A bare number in a judgment is frequently NOT a section number -- it's a
# paragraph marker, a page/column ref, a citation volume/year, or a case
# number. Requiring one of these cues within a small window is what tells
# "376" (real: "punishable u/s 376 IPC") apart from "16" (really just
# "Para - 16" or "(2005) 3 SCC 114"), which a bare numeric-token match can't.
_LEGAL_CUE_RE = re.compile(
    r'(?i)\b(s{1,2}\.?|sec(?:tion)?s?\.?|u/s|under\s+section|ipc|cr\.?p\.?c\.?|'
    r'pocso|dowry|posh|it\s+act|penal\s+code)\b'
)


def _normalize_for_grounding(s: str) -> str:
    return re.sub(r'[\s\(\)\-]', '', s).upper()


def _extract_numeric_tokens(text: str, window: int = 25) -> Dict[str, List[str]]:
    """Map each normalized numeric token to the text snippets it appears in
    (with surrounding context), so grounding can check for a nearby legal
    cue rather than just bare numeric coincidence."""
    occurrences: Dict[str, List[str]] = {}
    for m in _NUMERIC_TOKEN_RE.finditer(text):
        tok = _normalize_for_grounding(m.group())
        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        occurrences.setdefault(tok, []).append(text[start:end])
    return occurrences


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


def _has_legal_cue(snippets: List[str]) -> bool:
    return any(_LEGAL_CUE_RE.search(s) for s in snippets)


# Act-specific cues, used to catch a section placed under the WRONG Act
# bucket -- e.g. "420" (a real IPC section, cheating) extracted under
# "crpc" instead of "ipc". The same bare number can be a genuine section of
# more than one Act, so grounding alone (does this number appear near *a*
# legal cue) isn't enough; we also check that it appears near *this specific
# Act's* cue at least once, and flag it if it only ever appears near a
# DIFFERENT Act's cue instead.
_ACT_CUES: Dict[str, "re.Pattern"] = {
    "ipc": re.compile(r'(?i)\b(ipc|indian\s+penal\s+code|penal\s+code)\b'),
    "crpc": re.compile(r'(?i)\b(cr\.?\s?p\.?\s?c\.?|code\s+of\s+criminal\s+procedure)\b'),
    "pocso": re.compile(r'(?i)\bpocso\b'),
    "dowry_act": re.compile(r'(?i)\bdowry\b'),
    "posh_act": re.compile(r'(?i)\bposh\b'),
    "it_act": re.compile(r'(?i)\bit\s+act\b'),
}


def _matching_tokens(candidate: str, occurrences: Dict[str, List[str]]) -> List[str]:
    """Return every occurrence-map key that _is_grounded would accept as a
    match for this candidate (exact, or within edit distance 1 for longer
    candidates) -- regardless of legal-cue gating -- so act-consistency can
    inspect the actual surrounding snippets."""
    cand = _normalize_for_grounding(candidate)
    if cand in occurrences:
        return [cand]
    if len(cand) < 3:
        return []
    return [
        tok for tok in occurrences
        if abs(len(tok) - len(cand)) <= 1 and _levenshtein(cand, tok) <= 1
    ]


def _act_mismatch(act: str, candidate: str, occurrences: Dict[str, List[str]]) -> bool:
    """True if this section's own Act cue never appears near any matching
    occurrence, but a DIFFERENT Act's cue does -- a strong signal the LLM
    filed a real section number under the wrong Act bucket."""
    own_cue = _ACT_CUES.get(act)
    if own_cue is None:
        return False  # "other"/"bns" have no fixed cue to check against
    snippets = [s for tok in _matching_tokens(candidate, occurrences) for s in occurrences[tok]]
    if not snippets:
        return False
    if any(own_cue.search(s) for s in snippets):
        return False
    other_acts = [a for a in _ACT_CUES if a != act]
    return any(_ACT_CUES[other].search(s) for s in snippets for other in other_acts)


def _is_grounded(candidate: str, occurrences: Dict[str, List[str]]) -> bool:
    """Exact match (with a nearby legal cue) always counts. For candidates of
    length >= 3 (e.g. "304B", "376A"), also accept a token within edit
    distance 1 -- this is exactly the OCR digit/letter confusion case (304B
    vs 3048). Short candidates (length <= 2, e.g. plain Dowry Prohibition Act
    section numbers like "3", "4") require an exact match, since fuzzy
    matching on 1-2 character strings would match almost any nearby number.
    In all cases, at least one occurrence of the matched token must sit near
    a legal cue (Section/S./IPC/Cr.P.C./etc.) -- a number that only ever
    shows up next to "Para -" or inside a citation is not grounded, no
    matter how exactly the digits match."""
    cand = _normalize_for_grounding(candidate)
    if cand in occurrences:
        return _has_legal_cue(occurrences[cand])
    if len(cand) < 3:
        return False
    for tok, snippets in occurrences.items():
        if abs(len(tok) - len(cand)) <= 1 and _levenshtein(cand, tok) <= 1:
            if _has_legal_cue(snippets):
                return True
    return False


def _detect_bucket_spam(extraction: CaseExtraction) -> List[str]:
    """Detect the 'model ran out of real context and pattern-completed every
    required field with the same list' failure mode: if an identical,
    non-trivial section list shows up in 3+ of the (up to 16) act buckets
    across sections_applied_to_present_case and sections_only_cited_from_precedent,
    that's not a coincidence -- a real judgment doesn't cite the same section
    numbers under IPC, POCSO, the Dowry Act, and CrPC all at once. This is
    surfaced separately from ordinary ungrounded-section warnings because it
    points at a different root cause (context-window truncation or a model
    too weak for the task) rather than a one-off hallucination."""
    from collections import Counter
    buckets = {
        **{f"applied.{k}": v for k, v in extraction.sections_applied_to_present_case.model_dump().items()},
        **{f"cited.{k}": v for k, v in extraction.sections_only_cited_from_precedent.model_dump().items()},
    }
    counts = Counter(tuple(sorted(v)) for v in buckets.values() if len(v) >= 2)
    warnings = []
    for combo, n in counts.items():
        if n >= 3:
            warnings.append(
                f"Suspicious duplication: identical section list {list(combo)} appears in {n} "
                f"different Act buckets -- likely context truncation or model failure, not a "
                f"real extraction (see review_reasons for which buckets)."
            )
    return warnings


def validate_grounding(extraction: CaseExtraction, cleaned_text: str) -> List[str]:
    """Flag section numbers the LLM claims are present but that don't
    actually appear (near a legal cue) in the cleaned text, and separately
    flag sections that ARE grounded but appear to be filed under the wrong
    Act (e.g. an IPC-only number placed in the crpc bucket)."""
    warnings = []
    warnings.extend(_detect_bucket_spam(extraction))
    occurrences = _extract_numeric_tokens(cleaned_text)
    applied = extraction.sections_applied_to_present_case.model_dump()
    for act, sections in applied.items():
        for s in sections:
            if not _is_grounded(s, occurrences):
                warnings.append(f"Ungrounded section: {act}:{s}")
            elif _act_mismatch(act, s, occurrences):
                warnings.append(f"Possible Act mismatch: {act}:{s} appears near a different Act's name in the text")
    return warnings


# ============================================================
# PIPELINE
# ============================================================

class JudgmentPipeline:
    def __init__(self, config: Config):
        self.config = config
        self.extractor = RobustPDFExtractor(config)
        self.llm = OllamaExtractor(config)

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
    logger.info(f"Using Ollama model '{config.ollama_model}' at {config.ollama_host}")

    if not config.pdf_input_dir.exists():
        logger.error(f"PDF directory not found: {config.pdf_input_dir}")
        return

    pdf_files = list(config.pdf_input_dir.glob('*.pdf'))
    if not pdf_files:
        logger.error(f"No PDFs found in: {config.pdf_input_dir}")
        return

    logger.info(f"Found {len(pdf_files)} PDF files to extract")
    try:
        pipeline = JudgmentPipeline(config)
    except RuntimeError as e:
        logger.error(str(e))
        return
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