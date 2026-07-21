"""
ollama_cleaner.py — LLM-powered data cleaning using local Ollama server
========================================================================
Designed for large-scale processing. Key fixes vs v1:
  - Chunks large text before sending (prevents 0xc0000409 crash)
  - Small, focused prompts (low token count)
  - Auto-recovery after server crash (resets availability cache)
  - Aggressive timeouts + retry logic
  - Skip sentences/paragraphs that are already clean
  - Progress logging every N records

Toggle:
  config.py  →  "USE_OLLAMA": True / False
  CLI        →  python main.py file.pdf --no-ollama
"""

import os
import sys
import re
import time
import requests
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logging_utils import get_logger

logger = get_logger("ollama_cleaner")

# ── Tuning constants (safe for large-scale processing) ───────────────────────
DEFAULT_URL    = "http://127.0.0.1:11434"
DEFAULT_MODEL  = "llama3.1:latest"
MAX_INPUT_CHARS = 800      # hard cap — prevents OOM crash (was 3000, caused 0xc0000409)
TIMEOUT         = 45       # seconds per request (was 120, caused long hangs)
BATCH_PAUSE     = 0.2      # seconds between requests
MAX_RETRIES     = 2        # retries on timeout/500
RETRY_PAUSE     = 3.0      # seconds before retry
LOG_EVERY       = 10       # log progress every N items
SKIP_THRESHOLD  = 30       # skip OCR cleaning if text is shorter than this

# ── OCR noise patterns — skip Ollama if text is already clean ─────────────────
OCR_NOISE_RE = re.compile(
    r'/ife\b|/iberty\b|religfon|rdief|CTI\b|bodi~|mater\s+nity|'
    r'\b[A-H]\s+[A-Z]|\bnonns\b|\bphces\b|\bscheine\b|'
    r'[a-z]-\n[a-z]|ofsexual',
    re.IGNORECASE
)

def _needs_cleaning(text: str) -> bool:
    """Return True only if text has detectable OCR noise."""
    return bool(OCR_NOISE_RE.search(text))


# ── Minimal, low-token prompts ────────────────────────────────────────────────
# Each prompt is kept under 200 tokens so the model has room for output.
PROMPTS = {

    "fix_ocr": (
        "Fix OCR errors only. Rules: fix garbled words, remove stray letters "
        "(A B C D E F G H as column markers), fix broken words. "
        "Do NOT change legal meaning. Return ONLY corrected text.\n\n{text}"
    ),

    "clean_principle": (
        "Clean this legal principle: fix OCR errors, make it 1-2 sentences, "
        "remove page headers. Return ONLY the cleaned principle.\n\n{text}"
    ),

    "clean_guideline": (
        "Clean this guideline text: fix OCR errors, remove page headers like "
        "'SUPREME COURT REPORTS', keep all legal content. "
        "Return ONLY the cleaned text.\n\n{text}"
    ),

    "expand_answer": (
        "Question: {question}\n"
        "Current answer: {text}\n"
        "The answer is too short. Write a complete 2-3 sentence answer "
        "about this Indian Supreme Court case. Return ONLY the answer."
    ),

    "expand_output": (
        "Task: {instruction}\n"
        "Context: {input}\n"
        "Current output: {text}\n"
        "Expand into a complete 2-3 sentence legal answer. Return ONLY the answer."
    ),

    "clean_summary": (
        "Clean this legal case summary: fix OCR errors, ensure it reads clearly. "
        "Keep all facts. Return ONLY the cleaned summary.\n\n{text}"
    ),
}


# ── Core client ───────────────────────────────────────────────────────────────
class OllamaCleaner:
    def __init__(self, url: str = DEFAULT_URL, model: str = DEFAULT_MODEL,
                 enabled: bool = True):
        self.url      = url.rstrip("/")
        self.model    = model
        self.enabled  = enabled
        self._available: Optional[bool] = None
        self._fail_count = 0
        self._max_fails  = 5   # disable after 5 consecutive failures

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        # Disable after too many consecutive failures
        if self._fail_count >= self._max_fails:
            if self._available:
                logger.warning("Too many Ollama failures — disabling for this run")
                self._available = False
            return False
        if self._available is not None:
            return self._available
        return self._check_server()

    def _check_server(self) -> bool:
        try:
            resp = requests.get(f"{self.url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                base   = self.model.split(":")[0]
                self._available = any(base in m for m in models)
                if self._available:
                    logger.info(f"Ollama ready: {self.model} at {self.url}")
                else:
                    logger.warning(f"Model '{self.model}' not found. Available: {models}")
                return self._available
        except Exception as e:
            logger.warning(f"Ollama not reachable: {e}")
        self._available = False
        return False

    def _reset_after_crash(self):
        """After a 500/crash, pause and re-check availability."""
        logger.info("  Ollama crashed — waiting 5s and rechecking...")
        time.sleep(5)
        self._available = None   # force re-check
        self._check_server()

    def clean(self, prompt_key: str, text: str, **kwargs) -> str:
        """
        Send text to Ollama. Chunks large input. Returns original on failure.
        """
        if not self.enabled or not self.is_available():
            return text
        if not text or len(text.strip()) < SKIP_THRESHOLD:
            return text

        # Chunk if text exceeds safe limit
        if len(text) > MAX_INPUT_CHARS:
            return self._clean_chunked(prompt_key, text, **kwargs)

        return self._call(prompt_key, text, **kwargs)

    def _clean_chunked(self, prompt_key: str, text: str, **kwargs) -> str:
        """Split text into chunks, clean each, rejoin."""
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) < MAX_INPUT_CHARS:
                current += (" " if current else "") + sent
            else:
                if current:
                    chunks.append(current)
                current = sent
        if current:
            chunks.append(current)

        cleaned_parts = []
        for chunk in chunks:
            cleaned_parts.append(self._call(prompt_key, chunk, **kwargs))
        return " ".join(cleaned_parts)

    def _call(self, prompt_key: str, text: str, **kwargs) -> str:
        """Single Ollama API call with retry logic."""
        template = PROMPTS.get(prompt_key, PROMPTS["fix_ocr"])
        try:
            prompt = template.format(text=text[:MAX_INPUT_CHARS], **{
                k: str(v)[:200] for k, v in kwargs.items()
            })
        except KeyError:
            prompt = PROMPTS["fix_ocr"].format(text=text[:MAX_INPUT_CHARS])

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(
                    f"{self.url}/api/generate",
                    json={
                        "model":  self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature":   0.1,
                            "num_predict":   512,   # limit output length
                            "num_ctx":       2048,  # reduced context (was 4096 — caused crash)
                            "stop": ["\n\n\n", "---"],
                        }
                    },
                    timeout=TIMEOUT
                )

                if resp.status_code == 200:
                    self._fail_count = 0   # reset on success
                    result = resp.json().get("response", "").strip()
                    return result if result else text

                elif resp.status_code == 500:
                    self._fail_count += 1
                    logger.warning(f"  Ollama 500 (attempt {attempt+1}): {resp.text[:80]}")
                    self._reset_after_crash()
                    if not self.is_available():
                        return text
                    time.sleep(RETRY_PAUSE)

                else:
                    logger.warning(f"  Ollama {resp.status_code}")
                    return text

            except requests.Timeout:
                self._fail_count += 1
                logger.warning(f"  Ollama timeout (attempt {attempt+1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_PAUSE)
                    self._available = None
                    self._check_server()
                else:
                    return text

            except Exception as e:
                self._fail_count += 1
                logger.warning(f"  Ollama error: {e}")
                return text

        return text


# ── Dataset cleaning functions ────────────────────────────────────────────────
def clean_datasets(result: dict, cleaner: OllamaCleaner) -> dict:
    if not cleaner.enabled:
        logger.info("Ollama cleaning: DISABLED (USE_OLLAMA=False)")
        return result

    if not cleaner.is_available():
        logger.warning("Ollama cleaning: SKIPPED — server not available")
        return result

    logger.info(f"Ollama cleaning: START — model={cleaner.model}")

    result = _clean_paragraphs(result, cleaner)
    result = _clean_guidelines(result, cleaner)
    result = _clean_principles(result, cleaner)
    result = _clean_quotes(result, cleaner)
    result = _clean_metadata(result, cleaner)
    result = _clean_qa(result, cleaner)
    result = _clean_training(result, cleaner)

    logger.info("Ollama cleaning: DONE")
    return result


def _clean_paragraphs(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_02_paragraphs", [])
    if not rows:
        return result
    cleaned = 0
    skipped = 0
    for i, row in enumerate(rows):
        text = row.get("paragraph_text", "")
        if text and _needs_cleaning(text):
            row["paragraph_text"] = cleaner.clean("fix_ocr", text)
            cleaned += 1
            time.sleep(BATCH_PAUSE)
        else:
            skipped += 1
        if (i + 1) % LOG_EVERY == 0 or (i + 1) == len(rows):
            logger.info(f"  Paragraphs: {i+1}/{len(rows)} "
                        f"(cleaned={cleaned}, skipped={skipped})")
    return result


def _clean_guidelines(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_08_guidelines", [])
    if not rows:
        return result
    logger.info(f"  Cleaning {len(rows)} guidelines...")
    for row in rows:
        if row.get("full_text"):
            row["full_text"] = cleaner.clean("clean_guideline", row["full_text"])
            time.sleep(BATCH_PAUSE)
    return result


def _clean_principles(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_09_principles", [])
    if not rows:
        return result
    logger.info(f"  Cleaning {len(rows)} principles...")
    for row in rows:
        p = row.get("principle", "")
        if p and _needs_cleaning(p):
            row["principle"] = cleaner.clean("clean_principle", p)
            time.sleep(BATCH_PAUSE)
    return result


def _clean_quotes(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_10_quotes", [])
    if not rows:
        return result
    logger.info(f"  Cleaning {len(rows)} quotes...")
    for row in rows:
        q = row.get("quote", "")
        if q and _needs_cleaning(q):
            row["quote"] = cleaner.clean("fix_ocr", q)
            time.sleep(BATCH_PAUSE)
    return result


def _clean_metadata(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_01_metadata", [])
    if not rows:
        return result
    row = rows[0]
    logger.info("  Cleaning metadata fields...")
    for field, prompt_key in [
        ("summary",         "clean_summary"),
        ("ratio_decidendi", "clean_principle"),
        ("facts",           "fix_ocr"),
        ("headnotes",       "fix_ocr"),
    ]:
        val = str(row.get(field, ""))
        if val and len(val) > 30 and _needs_cleaning(val):
            row[field] = cleaner.clean(prompt_key, val)
            time.sleep(BATCH_PAUSE)
    return result


def _clean_qa(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_15_qa", [])
    if not rows:
        return result
    expanded = 0
    logger.info(f"  Cleaning {len(rows)} QA answers...")
    for i, row in enumerate(rows):
        answer   = row.get("answer", "")
        question = row.get("question", "")
        if not answer:
            continue
        if len(answer.strip()) < 25:
            # Expand thin answers
            row["answer"] = cleaner.clean(
                "expand_answer", answer,
                question=question[:200]
            )
            expanded += 1
            time.sleep(BATCH_PAUSE)
        elif _needs_cleaning(answer):
            row["answer"] = cleaner.clean("fix_ocr", answer)
            time.sleep(BATCH_PAUSE)
        if (i + 1) % LOG_EVERY == 0 or (i + 1) == len(rows):
            logger.info(f"  QA: {i+1}/{len(rows)} (expanded={expanded})")
    return result


def _clean_training(result: dict, cleaner: OllamaCleaner) -> dict:
    rows = result.get("dataset_14_training", [])
    if not rows:
        return result
    expanded = 0
    logger.info(f"  Cleaning {len(rows)} training outputs...")
    for i, row in enumerate(rows):
        output      = row.get("output", "")
        instruction = row.get("instruction", "")
        inp         = row.get("input", "")
        if not output:
            continue
        if len(output.strip()) < 20:
            row["output"] = cleaner.clean(
                "expand_output", output,
                instruction=instruction[:200],
                input=inp[:300]
            )
            expanded += 1
            time.sleep(BATCH_PAUSE)
        elif _needs_cleaning(output):
            row["output"] = cleaner.clean("fix_ocr", output)
            time.sleep(BATCH_PAUSE)
        if (i + 1) % LOG_EVERY == 0 or (i + 1) == len(rows):
            logger.info(f"  Training: {i+1}/{len(rows)} (expanded={expanded})")
    return result
