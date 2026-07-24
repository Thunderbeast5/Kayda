import os
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, firestore


from config.llm_config import get_llm
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Optional Google Vision imports (graceful fallback if not installed)
try:
    from google.cloud import vision
    from pdf2image import convert_from_path
    _VISION_AVAILABLE = True
except Exception:
    _VISION_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "legal-embeddings"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

# OCR mode: "vision" (preferred) | "tesseract"
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "vision").strip().lower()

# Tesseract fallback config
OCR_LANGS = "eng+hin+mar"

# Google Vision creds (if not already set globally in environment)
# You can set either GOOGLE_APPLICATION_CREDENTIALS directly, or this custom var in .env.
GOOGLE_VISION_CREDENTIALS_PATH = os.getenv("GOOGLE_VISION_CREDENTIALS_PATH")

# Documents shorter than this go through a single LLM extraction path (single unified call).
MAX_DIRECT_CHARS = 25_000

# For documents that do need chunking
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 800

# Reconciliation text cap safety
MAX_RECON_FULL_TEXT_CHARS = 60_000

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
# OCR helpers
# ====================================================================

def _configure_google_credentials_if_needed():
    """
    If GOOGLE_APPLICATION_CREDENTIALS is not set but GOOGLE_VISION_CREDENTIALS_PATH is set in .env,
    map it to absolute path and export it.
    """
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    if GOOGLE_VISION_CREDENTIALS_PATH:
        cred_path = BASE_DIR / GOOGLE_VISION_CREDENTIALS_PATH
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path.resolve())


def _extract_text_with_vision_image(image: Image.Image) -> str:
    _configure_google_credentials_if_needed()
    client = vision.ImageAnnotatorClient()

    import io
    buf = io.BytesIO()
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(buf, format="PNG")
    content = buf.getvalue()

    vimg = vision.Image(content=content)
    response = client.document_text_detection(image=vimg)
    if response.error.message:
        raise RuntimeError(f"Google Vision API error: {response.error.message}")

    return (response.full_text_annotation.text or "").strip()


def _extract_text_with_vision_pdf(pdf_path: Path) -> str:
    """
    Convert PDF pages to images and OCR each page via Vision.
    This keeps implementation simple and robust for local files.
    """
    images = convert_from_path(str(pdf_path), dpi=300)
    page_texts = []
    for img in images:
        page_text = _extract_text_with_vision_image(img)
        page_texts.append(page_text)
    return "\n\n".join(t for t in page_texts if t).strip()


def _extract_text_with_tesseract(file_path: Path) -> str:
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        reader = PdfReader(str(file_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        text = text.strip()

        if text:
            return text

        # OCR fallback for scanned PDFs
        from pdf2image import convert_from_path
        images = convert_from_path(str(file_path), dpi=300)
        ocr_text = ""
        for img in images:
            ocr_text += pytesseract.image_to_string(img, lang=OCR_LANGS, config="--psm 6") + "\n"
        return ocr_text.strip()

    elif ext in IMAGE_EXTENSIONS:
        image = Image.open(file_path)
        return pytesseract.image_to_string(image, lang=OCR_LANGS).strip()

    raise ValueError(f"Unsupported file type: {ext}")


# ====================================================================
# Step 1: Text extraction (Google Vision preferred + fallback)
# ====================================================================
def extract_text(file_path: str) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in IMAGE_EXTENSIONS and ext != ".pdf":
        raise ValueError(f"Unsupported file type: {ext}")

    # Prefer Google Vision when configured
    if OCR_PROVIDER == "vision":
        if not _VISION_AVAILABLE:
            print("Google Vision libs not available; falling back to Tesseract.")
            return _extract_text_with_tesseract(path)

        try:
            if ext == ".pdf":
                return _extract_text_with_vision_pdf(path)
            else:
                image = Image.open(path)
                return _extract_text_with_vision_image(image)
        except Exception as e:
            print(f"Google Vision OCR failed ({e}); falling back to Tesseract.")
            return _extract_text_with_tesseract(path)

    # Explicit tesseract mode
    return _extract_text_with_tesseract(path)


# ====================================================================
# Step 2: Document-aware chunking
# ====================================================================
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

_PAGE_BREAK = re.compile(r"\f|---+\s*Page\s+\d+\s*---+", re.IGNORECASE)


def _chunk_document_aware(raw_text: str) -> List[str]:
    segments = _PAGE_BREAK.split(raw_text)

    refined: List[str] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= CHUNK_SIZE:
            refined.append(seg)
        else:
            parts = _HEADING_PATTERN.split(seg)
            for p in parts:
                p = p.strip()
                if p:
                    refined.append(p)

    final_chunks: List[str] = []
    for seg in refined:
        if len(seg) <= CHUNK_SIZE:
            final_chunks.append(seg)
        else:
            start = 0
            while start < len(seg):
                end = start + CHUNK_SIZE
                final_chunks.append(seg[start:end])
                start += CHUNK_SIZE - CHUNK_OVERLAP

    return final_chunks


# ====================================================================
# Step 3: Unified prompt (single extraction call per text/chunk)
# ====================================================================

BASE_RULES = """\
You are a legal document analyst reviewing an Indian FIR/evidence document.

Source may be Hindi/Marathi/English mixed with OCR noise.
CRITICAL: Output EVERY string in English only.
- Translate descriptions/locations to English.
- Transliterate person names to Roman script.
- Canonicalize OCR spelling variants of same person into one best form.
Return ONLY valid JSON (no markdown fences, no commentary).
"""

UNIFIED_PROMPT = BASE_RULES + """\

Task: Extract complete structured facts from this FIR/evidence text.

Rules:
- complainant: person who filed complaint.
- accused: only officially named accused.
- victims: only directly harmed persons (exclude police/witnesses unless harmed).
- Do NOT include accused as victims.
- Incident date/time/place should describe offence occurrence (not FIR filing date unless needed).
- Priority for date/time/place:
  1) complaint narrative / first information contents / gist
  2) incident description section
  3) registration header only if narrative missing
- Use 24-hour time format.
- Preserve quantities/units exactly for property fields (no conversion).
- estimated_loss: use FIR stated total if present, else compute from stated amounts.
- sections: include IPC/BNS/special Act sections; deduplicate/normalize
  like "IPC 420", "BNS 303", "IT Act 66C".

Return JSON schema:
{{
  "who": {{
    "complainant": "string or null",
    "accused": ["string"],
    "victims": ["string"]
  }},
  "incident": {{
    "summary": "string or null",
    "date": "DD/MM/YYYY or null",
    "time": "HH:MM or HH:MM - HH:MM or null",
    "place": "string or null"
  }},
  "property": {{
    "cash": "string or null",
    "gold": "string or null",
    "documents": "string or null",
    "vehicles": [
      {{
        "type": "string or null",
        "registration_no": "string or null",
        "make_model": "string or null",
        "engine_chassis_no": "string or null",
        "estimated_value": "string or null"
      }}
    ],
    "other_property": ["string"],
    "estimated_loss": "string or null"
  }},
  "sections": ["string"]
}}

TEXT:
{text}
"""

UNIFIED_RECON_PROMPT = BASE_RULES + """\
Task: Reconcile complete structured facts from multiple chunk outputs + full OCR text.
Use full OCR text as ground truth where conflicts exist.
Devanagari OCR denoising is critical for names.
Each real person must appear once in canonical spelling.
Deduplicate legal sections and normalize.

Return JSON schema:
{{
  "who": {{
    "complainant": "string or null",
    "accused": ["string"],
    "victims": ["string"]
  }},
  "incident": {{
    "summary": "string or null",
    "date": "DD/MM/YYYY or null",
    "time": "HH:MM or HH:MM - HH:MM or HH:MM or null",
    "place": "string or null"
  }},
  "property": {{
    "cash": "string or null",
    "gold": "string or null",
    "documents": "string or null",
    "vehicles": [
      {{
        "type": "string or null",
        "registration_no": "string or null",
        "make_model": "string or null",
        "engine_chassis_no": "string or null",
        "estimated_value": "string or null"
      }}
    ],
    "other_property": ["string"],
    "estimated_loss": "string or null"
  }},
  "sections": ["string"]
}}

FULL OCR TEXT:
{full_text}

PARTIALS:
{partial_jsons}
"""


# ====================================================================
# Step 3 logic helpers
# ====================================================================

def _strip_json_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def _parse_llm_json(raw_response: str) -> Optional[Dict[str, Any]]:
    cleaned = _strip_json_fences(raw_response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print("Warning: could not parse LLM output:")
        print(cleaned[:600])
        return None


# key = os.getenv("GROQ_API_KEY")
# print("Using key:", key[:12], "...", key[-6:])

def _llm_json(prompt: str) -> Optional[Dict[str, Any]]:
    llm = get_llm(temperature=0)
    response = llm.invoke(prompt)
    return _parse_llm_json(response.content)


def _normalise_vehicle(v: Dict[str, Any]) -> Dict[str, Optional[str]]:
    return {
        "type": (v.get("type") or None),
        "registration_no": (v.get("registration_no") or None),
        "make_model": (v.get("make_model") or None),
        "engine_chassis_no": (v.get("engine_chassis_no") or None),
        "estimated_value": (v.get("estimated_value") or None),
    }


def _normalise_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    who = facts.get("who") or {}
    incident = facts.get("incident") or {}
    prop = facts.get("property") or {}

    vehicles_raw = prop.get("vehicles") or []
    vehicles = []
    if isinstance(vehicles_raw, list):
        for item in vehicles_raw:
            if isinstance(item, dict):
                vehicles.append(_normalise_vehicle(item))

    other_property = prop.get("other_property") or []
    if not isinstance(other_property, list):
        other_property = []

    sections = facts.get("sections") or []
    if not isinstance(sections, list):
        sections = []

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
            "vehicles": vehicles,
            "other_property": [str(x) for x in other_property if x is not None],
            "estimated_loss": prop.get("estimated_loss") or None,
        },
        "sections": [str(x) for x in sections if x is not None],
    }


def _empty_facts() -> Dict[str, Any]:
    return {
        "who": {"complainant": None, "accused": [], "victims": []},
        "incident": {"summary": None, "date": None, "time": None, "place": None},
        "property": {
            "cash": None,
            "gold": None,
            "documents": None,
            "vehicles": [],
            "other_property": [],
            "estimated_loss": None,
        },
        "sections": [],
    }


def _extract_single_call_from_text(text: str) -> Dict[str, Any]:
    result = _llm_json(UNIFIED_PROMPT.format(text=text))
    return _normalise_facts(result or _empty_facts())


def _extract_single_pass(raw_text: str) -> Dict[str, Any]:
    """
    Short docs path: 1 focused call over full text.
    """
    return _extract_single_call_from_text(raw_text)


def _extract_chunked_with_reconciliation(raw_text: str) -> Dict[str, Any]:
    """
    Long docs path:
      - chunk document-aware
      - per chunk do 1 unified extraction
      - do 1 unified reconciliation with full text + partials
    """
    chunks = _chunk_document_aware(raw_text)

    partials: List[Dict[str, Any]] = []
    for chunk in chunks:
        p = _llm_json(UNIFIED_PROMPT.format(text=chunk))
        if p:
            partials.append(p)

    if not partials:
        # fallback: best effort from first chunk if available
        if chunks:
            return _extract_single_call_from_text(chunks[0])
        return _empty_facts()

    full_text_cut = raw_text[:MAX_RECON_FULL_TEXT_CHARS]
    partial_jsons_str = "\n\n".join(
        f"### Chunk {i+1}\n```json\n{json.dumps(p, indent=2, ensure_ascii=False)}\n```"
        for i, p in enumerate(partials)
    )

    recon = _llm_json(
        UNIFIED_RECON_PROMPT.format(
            full_text=full_text_cut,
            partial_jsons=partial_jsons_str,
        )
    )

    if not recon:
        # fallback to first partial if reconciliation fails
        return _normalise_facts(partials[0])

    return _normalise_facts(recon)


def extract_facts(raw_text: str) -> Dict[str, Any]:
    if len(raw_text) <= MAX_DIRECT_CHARS:
        print(f"[evidence_analyzer] {len(raw_text)} chars — short-doc unified extraction (1 call).")
        return _extract_single_pass(raw_text)

    print(
        f"[evidence_analyzer] {len(raw_text)} chars (> {MAX_DIRECT_CHARS}) — "
        "chunked unified extraction + unified reconciliation."
    )
    return _extract_chunked_with_reconciliation(raw_text)


# ====================================================================
# Step 4: Store to Firestore
# ====================================================================
def store_to_firestore(session_id: str, raw_text: str, facts: Dict[str, Any]) -> str:
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "v4_unified_prompt",
        "ocr_provider": OCR_PROVIDER,
    })
    return doc_ref.id


# ====================================================================
# Step 5: Embed + store to Pinecone
# ====================================================================
def store_to_pinecone(session_id: str, facts: Dict[str, Any]):
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
# Session ID helper
# ====================================================================
def build_session_id(file_path: str) -> str:
    base_name = Path(file_path).stem
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{base_name}_{timestamp}_{short_uuid}"


# ====================================================================
# Orchestrator
# ====================================================================
def analyze_evidence(session_id: str, file_path: str) -> Dict[str, Any]:
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
        print(json.dumps(result, indent=2, ensure_ascii=False))