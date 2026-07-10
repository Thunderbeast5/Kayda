"""
Sprint 3: Evidence Analyzer (v2 — reconciliation architecture)

Pipeline
--------
PDF / Image
    → OCR
    → if len(text) ≤ MAX_DIRECT_CHARS:  single LLM extraction
      else:  document-aware chunking → per-chunk extraction → reconciliation LLM
    → Canonical JSON
    → Firestore + Pinecone

Key improvements over v1
------------------------
• FIRs under ~25 000 chars (3–8 pages) are processed in ONE LLM call, eliminating
  inter-chunk inconsistencies (name variants, wrong dates, duplicate persons).
• Large documents are chunked on page / heading boundaries, not arbitrary 1 000-char
  slices, so sentences and names are never split in half.
• A reconciliation LLM pass replaces the old "first non-null / exact-string dedup"
  merge logic for chunked documents, resolving OCR spelling variants semantically.
• The prompt now strictly defines who qualifies as a victim, prioritises the narrative
  section for incident details, and asks the model to compute consolidated loss.
"""

import os
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, firestore

from llm_config import get_llm

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# ── Tesseract path (Windows) ──────────────────────────────────────────────────
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.getenv("TESSERACT_CMD", ""),
]
for _p in _TESSERACT_PATHS:
    if _p and Path(_p).exists():
        pytesseract.pytesseract.tesseract_cmd = _p
        break
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "legal-embeddings"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

# Tesseract languages: English + Hindi + Marathi (mar uses the same "mar" traineddata,
# make sure it's installed alongside "hin" and "eng" -> `apt install tesseract-ocr-hin tesseract-ocr-mar`)
OCR_LANGS = "eng+hin+mar"

# Documents shorter than this go through a single LLM call.
# ~25 000 chars ≈ 6 000–8 000 LLM tokens — well within Llama-3.3-70B's 128 k window.
MAX_DIRECT_CHARS = 25_000

# For documents that *do* need chunking, use larger, overlapping chunks.
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 800


# ====================================================================
# Firebase init (lazy, only once per process)
# ====================================================================
_firebase_app = None


def _get_firestore_client():
    global _firebase_app
    if _firebase_app is None:
        if not FIREBASE_CREDENTIALS_PATH:
            raise ValueError("FIREBASE_CREDENTIALS_PATH not set in .env")
        cred_path = BASE_DIR / FIREBASE_CREDENTIALS_PATH
        cred = credentials.Certificate(str(cred_path))
        _firebase_app = firebase_admin.initialize_app(cred)
    return firestore.client()


# ====================================================================
# Step 1: Text extraction (OCR / PDF)
# ====================================================================
def extract_text(file_path: str) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        # 1. Try pypdf (pure Python)
        try:
            from pypdf import PdfReader as PyPdfReader
            reader = PyPdfReader(str(path))
            text = "".join(p.extract_text() or "" for p in reader.pages).strip()
            if text:
                return text
        except Exception:
            pass

        # 2. Try PyPDF2
        try:
            reader = PdfReader(str(path))
            text = "".join(p.extract_text() or "" for p in reader.pages).strip()
            if text:
                return text
        except Exception:
            pass

        # 3. Scanned PDF — extract embedded images with pikepdf, then OCR
        try:
            import pikepdf
            from pikepdf import PdfImage
            ocr_parts = []
            pdf = pikepdf.open(str(path))
            for page in pdf.pages:
                resources = page.get("/Resources", {})
                xobjects  = resources.get("/XObject", {})
                for key in xobjects:
                    obj = xobjects[key]
                    if obj.get("/Subtype") == "/Image":
                        try:
                            img  = PdfImage(obj).as_pil_image()
                            text = pytesseract.image_to_string(img, lang=OCR_LANGS)
                            if text.strip():
                                ocr_parts.append(text)
                        except Exception:
                            pass
            if ocr_parts:
                return "\n".join(ocr_parts).strip()
        except ImportError:
            pass
        except Exception as e:
            print(f"[evidence_analyzer] pikepdf OCR failed: {e}")

        return "SCANNED_PDF_NO_TEXT: could not extract text. Install Tesseract for OCR."

    elif ext in IMAGE_EXTENSIONS:
        image = Image.open(path)
        return pytesseract.image_to_string(image, lang=OCR_LANGS).strip()

    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ====================================================================
# Step 2: Document-aware chunking (only for large documents)
# ====================================================================
# Headings commonly found in Indian FIRs (English and transliterated).
_HEADING_PATTERN = re.compile(
    r"(?:^|\n)(?:"
    r"First\s+Information\s+(?:Contents|Report)"
    r"|Action\s+Taken"
    r"|Details\s+of\s+(?:Known|Suspected|Unknown)\s+(?:Accused|Person)"
    r"|Particulars\s+of\s+(?:Properties|Property)"
    r"|Reasons?\s+for\s+[Dd]elay"
    r"|Complainant\s*/?\s*Informant"
    r"|Item\s+\d+"
    r"|FIR\s+(?:Contents|Details)"
    r")",
    re.IGNORECASE,
)

# Page-break markers commonly left by OCR or PDF extraction.
_PAGE_BREAK = re.compile(r"\f|---+\s*Page\s+\d+\s*---+", re.IGNORECASE)


def _chunk_document_aware(raw_text: str) -> list[str]:
    """
    Split a long document on natural boundaries:
      1. Page breaks  (form-feeds, --- Page N --- markers)
      2. FIR section headings
      3. Character-count fallback with overlap (last resort)
    """
    # --- Split on page breaks first --------------------------------
    segments = _PAGE_BREAK.split(raw_text)

    # --- Sub-split oversized segments on headings ------------------
    refined: list[str] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= CHUNK_SIZE:
            refined.append(seg)
        else:
            # Try splitting on headings
            parts = _HEADING_PATTERN.split(seg)
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                refined.append(p)

    # --- Final pass: break anything still too large ----------------
    final_chunks: list[str] = []
    for seg in refined:
        if len(seg) <= CHUNK_SIZE:
            final_chunks.append(seg)
        else:
            # Character-based split with overlap as last resort
            start = 0
            while start < len(seg):
                end = start + CHUNK_SIZE
                final_chunks.append(seg[start:end])
                start += CHUNK_SIZE - CHUNK_OVERLAP

    return final_chunks


# ====================================================================
# Step 3: LLM fact extraction — prompts
# ====================================================================

SINGLE_PASS_PROMPT = """\
You are a legal document analyst reviewing an Indian FIR (First Information Report)
or related evidence document.

## Source language
The text may be in Hindi, Marathi, English, or a mix (including Devanagari script),
and may contain OCR noise or broken characters. Read and understand the text
regardless of language.

## Output language
CRITICAL: every string value you output MUST be in English.
- Translate descriptions, summaries, and place names into English.
- Transliterate all person names into English (Roman) script
  (e.g. "अनिल शंकरराव विझेकर" → "Anil Shankarrao Vizhekar").
- If OCR produces multiple spellings of the same name, choose the SINGLE most
  probable canonical spelling. Do NOT output multiple variants of the same person.

## CRITICAL: Devanagari OCR name denoising
OCR of Devanagari script frequently garbles characters that look similar.
Common confusions include:
  - र ↔ श  (e.g. "राजेंद्र" misread as "राजेश" — Rajendra vs Rajesh)
  - अ ↔ आ, न ↔ ण, स ↔ श
  - Vowel matras (ि ↔ ी, ु ↔ ू, े ↔ ै)
  - Compound consonants getting split or merged

To handle this:
1. Find EVERY occurrence of each person's name across the ENTIRE document
   (header, accused list, narrative, action-taken section).
2. Cross-reference all occurrences — the STRUCTURED fields (accused list,
   complainant header) are usually more reliable than inline narrative text.
3. Pick the most COMPLETE and most FREQUENTLY occurring form as canonical.
4. Be especially careful with first names — do NOT substitute a common name
   (like "Rajesh" or "Ashok") if the structured fields show a different name
   (like "Rajendra" or "Anil").
5. For spouse names in "wife of / पत्नी" constructions, the wife's own name
   comes BEFORE "wife of" — read carefully.

## Field definitions

### who.complainant
The person who filed the complaint / gave the first information.

### who.accused
Return ONLY persons officially named as accused in the FIR.
- Do NOT infer additional accused.
- Do NOT create spelling variants — pick one canonical name per person.
- Do NOT include witnesses, police officers, or investigating officers.

### who.victims
Victims = people who DIRECTLY suffered the offence.
DO NOT include:
  - police officers or investigating officers
  - witnesses who were not harmed
  - complainants UNLESS they are also direct victims
  - accused persons
  - relatives mentioned only for background

### incident (date / time / place / summary)
PRIORITY for date, time, and place:
  1. The complaint narrative (Item 12 / "First Information Contents" / "Gist of FIR")
  2. The incident description section
  3. The registration header (use ONLY if the narrative is missing)

This means you should return the date/time/place of the ACTUAL OFFENCE as
described in the complaint, NOT the date the FIR was registered, unless the
narrative does not specify.

TIME FORMAT: Always use 24-hour format (HH:MM).
  - If the source says "02:30 PM" or "दोपहर 2:30", output "14:30".
  - If the source says "02:30 AM" or "रात्री 2:30", output "02:30".
  - For time ranges, use "HH:MM - HH:MM" (e.g. "14:30 - 16:00").

### property & estimated_loss
List each category of loss separately.
For estimated_loss, compute the total if the individual amounts are stated,
OR use the FIR's own stated total if one exists. Prefer the FIR's stated total.

PROPERTY RULES:
- Report quantities and units EXACTLY as stated in the FIR. Do NOT convert units.
  - If the FIR says "3 grams", write "3 grams" — do NOT write "3 tola".
  - If the FIR says "3 tola", write "3 tola" — do NOT write "~30 grams".
- For gold/jewellery, describe each item separately with its stated weight.
  e.g. "Gold earrings (~3 grams) + gold mangalsutra (~3 grams)"

### sections
List IPC / BNS / special-Act sections cited (e.g. "IPC 420", "IPC 467").

## Output format
Return ONLY valid JSON — no markdown fences, no preamble.
Schema:
{{
  "who": {{
    "complainant": "string or null",
    "accused": ["string"],
    "victims": ["string"]
  }},
  "incident": {{
    "summary": "string describing the crime, or null",
    "date": "DD/MM/YYYY or null",
    "time": "time or time-range string or null",
    "place": "location string or null"
  }},
  "property": {{
    "cash": "string or null",
    "gold": "string or null",
    "documents": "string or null",
    "estimated_loss": "total value string or null"
  }},
  "sections": ["IPC 420", "..."]
}}

If a field is not mentioned, use null (or [] for lists).

## TEXT
{text}
"""


CHUNK_EXTRACTION_PROMPT = """\
You are a legal document analyst. This is ONE CHUNK of a larger Indian FIR.
Extract whatever facts are present in this chunk.

Rules:
- Output ALL values in English (translate / transliterate from Hindi/Marathi).
- For person names, pick the most probable canonical English spelling.
- If this chunk does not contain information for a field, use null / [].
- Return ONLY valid JSON (no markdown fences).

Schema:
{{
  "who": {{
    "complainant": "string or null",
    "accused": ["string"],
    "victims": ["string"]
  }},
  "incident": {{
    "summary": "string or null",
    "date": "DD/MM/YYYY or null",
    "time": "time string or null",
    "place": "string or null"
  }},
  "property": {{
    "cash": "string or null",
    "gold": "string or null",
    "documents": "string or null",
    "estimated_loss": "string or null"
  }},
  "sections": ["string"]
}}

CHUNK:
{text}
"""


RECONCILIATION_PROMPT = """\
You are a legal document analyst performing a RECONCILIATION step.

Below you will find:
1. The FULL OCR text of an Indian FIR.
2. Multiple PARTIAL JSON extractions from individual chunks of the same FIR.

Your job is to produce ONE canonical JSON output by:

### Names (CRITICAL — Devanagari OCR denoising)
- OCR of Devanagari frequently confuses similar characters:
  र ↔ श (Rajendra vs Rajesh), अ ↔ आ, न ↔ ण, स ↔ श, vowel matras (ि ↔ ी, ु ↔ ू, े ↔ ै).
- Identify spelling variants of the same person caused by OCR noise
  (e.g. "Anil Vizhekar" / "Ashnil Vizhekar" / "Ashnal Vizhekar" are likely
  the same person → pick "Anil Shankarrao Vizhekar" if the full name appears).
- Cross-reference names across the FULL OCR text: structured fields (accused list,
  complainant header) are more reliable than inline narrative.
- Do NOT substitute common names ("Rajesh", "Ashok") if structured fields show
  different names ("Rajendra", "Anil").
- Each real person should appear EXACTLY ONCE.

### who.accused
Return ONLY persons officially named as accused.
Do NOT include police officers, investigating officers, or witnesses.

### who.victims
Victims = people who DIRECTLY suffered the offence.
DO NOT include:
  - police officers or investigating officers
  - witnesses who were not harmed
  - complainants UNLESS they are also direct victims
  - accused persons
  - relatives mentioned only for background

### incident (date / time / place)
PRIORITY:
  1. Complaint narrative (Item 12 / "First Information Contents")
  2. Incident description section
  3. Registration header (only if narrative missing)
Return the OFFENCE date/time/place, not the FIR filing date.
Always use 24-hour time format (e.g. "02:30 PM" → "14:30").

### property
- Report quantities and units EXACTLY as stated. Do NOT convert units
  (e.g. "3 grams" stays "3 grams", not "3 tola").
- Describe gold/jewellery items separately with stated weights.

### estimated_loss
Compute total from individual amounts OR use the FIR's stated total (prefer stated total).

### sections
Deduplicate. Use standard format: "IPC 420", "IPC 467", etc.

Return ONLY valid JSON — no markdown fences, no commentary.

Schema:
{{
  "who": {{
    "complainant": "string or null",
    "accused": ["string"],
    "victims": ["string"]
  }},
  "incident": {{
    "summary": "string describing the crime, or null",
    "date": "DD/MM/YYYY or null",
    "time": "time or time-range string or null",
    "place": "location string or null"
  }},
  "property": {{
    "cash": "string or null",
    "gold": "string or null",
    "documents": "string or null",
    "estimated_loss": "total value string or null"
  }},
  "sections": ["string"]
}}

---

## FULL OCR TEXT
{full_text}

---

## PARTIAL EXTRACTIONS
{partial_jsons}
"""


# ====================================================================
# Step 3: LLM fact extraction — logic
# ====================================================================

def _strip_json_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def _parse_llm_json(raw_response: str) -> dict | None:
    """Parse LLM output to JSON, returning None on failure."""
    cleaned = _strip_json_fences(raw_response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print("Warning: could not parse LLM output:")
        print(cleaned[:500])
        return None


def _extract_single_pass(raw_text: str) -> dict:
    """One-shot extraction — the whole document in a single LLM call."""
    llm = get_llm(temperature=0)
    prompt = SINGLE_PASS_PROMPT.format(text=raw_text)
    response = llm.invoke(prompt)
    facts = _parse_llm_json(response.content)

    if facts is None:
        return _empty_facts()

    return _normalise_facts(facts)


def _extract_chunked_with_reconciliation(raw_text: str) -> dict:
    """
    For large documents:
      1. Chunk on document boundaries.
      2. Extract facts per chunk.
      3. Reconcile all partials + full text in one final LLM call.
    """
    llm = get_llm(temperature=0)
    chunks = _chunk_document_aware(raw_text)

    partial_results: list[dict] = []
    for chunk in chunks:
        prompt = CHUNK_EXTRACTION_PROMPT.format(text=chunk)
        response = llm.invoke(prompt)
        facts = _parse_llm_json(response.content)
        if facts is not None:
            partial_results.append(facts)

    if not partial_results:
        return _empty_facts()

    # --- Reconciliation pass ------------------------------------------
    # Truncate full text if it's extremely long (shouldn't happen since we
    # only reach this path for >25k docs, but guard against 100k+ edge cases).
    full_text_for_reconciliation = raw_text[:60_000]

    partial_jsons_str = "\n\n".join(
        f"### Chunk {i+1}\n```json\n{json.dumps(p, indent=2, ensure_ascii=False)}\n```"
        for i, p in enumerate(partial_results)
    )

    prompt = RECONCILIATION_PROMPT.format(
        full_text=full_text_for_reconciliation,
        partial_jsons=partial_jsons_str,
    )
    response = llm.invoke(prompt)
    reconciled = _parse_llm_json(response.content)

    if reconciled is None:
        # Fallback: return the first partial rather than nothing.
        return _normalise_facts(partial_results[0])

    return _normalise_facts(reconciled)


def _empty_facts() -> dict:
    """Return a valid but empty facts structure."""
    return {
        "who": {"complainant": None, "accused": [], "victims": []},
        "incident": {"summary": None, "date": None, "time": None, "place": None},
        "property": {"cash": None, "gold": None, "documents": None, "estimated_loss": None},
        "sections": [],
    }


def _normalise_facts(facts: dict) -> dict:
    """Ensure the facts dict matches the expected schema with correct types."""
    who = facts.get("who") or {}
    incident = facts.get("incident") or {}
    prop = facts.get("property") or {}

    return {
        "who": {
            "complainant": who.get("complainant") or None,
            "accused": list(who.get("accused") or []),
            "victims": list(who.get("victims") or []),
        },
        "incident": {
            "summary": incident.get("summary") or None,
            "date": incident.get("date") or None,
            "time": incident.get("time") or None,
            "place": incident.get("place") or None,
        },
        "property": {
            "cash": prop.get("cash") or None,
            "gold": prop.get("gold") or None,
            "documents": prop.get("documents") or None,
            "estimated_loss": prop.get("estimated_loss") or None,
        },
        "sections": list(facts.get("sections") or []),
    }


def extract_facts(raw_text: str) -> dict:
    """
    Main extraction entry point.

    Short documents (≤ MAX_DIRECT_CHARS) → single-pass LLM call.
    Long  documents (> MAX_DIRECT_CHARS) → chunk + reconciliation pipeline.
    """
    if len(raw_text) <= MAX_DIRECT_CHARS:
        print(f"[evidence_analyzer] Document is {len(raw_text)} chars — using single-pass extraction.")
        return _extract_single_pass(raw_text)
    else:
        print(
            f"[evidence_analyzer] Document is {len(raw_text)} chars (> {MAX_DIRECT_CHARS}) — "
            f"using chunked extraction with reconciliation."
        )
        return _extract_chunked_with_reconciliation(raw_text)


# ====================================================================
# Step 4: Store to Firestore
# ====================================================================
def store_to_firestore(session_id: str, raw_text: str, facts: dict) -> str:
    """
    Always creates a NEW document keyed by session_id. session_id is expected to be
    unique per run (see build_session_id()) so existing case records are never
    overwritten.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("document_store").document(session_id)

    if doc_ref.get().exists:
        raise ValueError(
            f"session_id '{session_id}' already exists in document_store — "
            "refusing to overwrite an existing case record."
        )

    doc_ref.set({
        "session_id": session_id,
        "raw_text": raw_text,
        "facts": facts,
        "created_at": datetime.utcnow().isoformat(),
    })
    return doc_ref.id


# ====================================================================
# Step 5: Embed + store to Pinecone (same model as Sprint 1 ingestion)
# ====================================================================
def store_to_pinecone(session_id: str, facts: dict):
    if not PINECONE_API_KEY:
        print("Skipping Pinecone: PINECONE_API_KEY not set")
        return

    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone

    text_for_embedding = facts.get("incident", {}).get("summary") or ""
    if not text_for_embedding:
        print("Skipping Pinecone: no incident summary to embed")
        return

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embedding = model.encode(text_for_embedding).tolist()

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    index.upsert(vectors=[{
        "id": f"CASE_{session_id}",
        "values": embedding,
        "metadata": {
            "type": "case_evidence",
            "session_id": session_id,
            "summary": text_for_embedding,
            "place": facts.get("incident", {}).get("place") or "",
        },
    }])


# ====================================================================
# Session ID helper — guarantees a new, unique record on every run
# ====================================================================
def build_session_id(file_path: str) -> str:
    base_name = Path(file_path).stem
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{base_name}_{timestamp}_{short_uuid}"


# ====================================================================
# Orchestrator entry point
# ====================================================================
def analyze_evidence(session_id: str, file_path: str) -> dict:
    raw_text = extract_text(file_path)
    facts = extract_facts(raw_text)
    store_to_firestore(session_id, raw_text, facts)
    store_to_pinecone(session_id, facts)
    return facts


if __name__ == "__main__":
    test_file = input("Enter path to the FIR/evidence file (PDF or image): ").strip()

    if not test_file:
        print("No file name entered. Exiting.")
    elif not Path(test_file).exists():
        print(f"No file found at '{test_file}'.")
    else:
        session_id = build_session_id(test_file)
        print(f"Creating new session: {session_id}")
        result = analyze_evidence(session_id, test_file)
        # ensure_ascii=False so any translation gaps are visible as readable text,
        # not \uXXXX escapes — but the prompt already forces English-only output.
        print(json.dumps(result, indent=2, ensure_ascii=False))