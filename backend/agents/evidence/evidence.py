import os
import sys
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add agents directory to path for imports
agents_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agents_dir))

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
    # client = vision.ImageAnnotatorClient()
    client = vision.ImageAnnotatorClient(transport="rest")

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


# ====================================================================
# ADDITIVE: Timeline extraction
# (New feature. Does not alter any of the pipeline above.)
# ====================================================================

TIMELINE_PROMPT = BASE_RULES + """\

Task: Extract a concise, chronological timeline of KEY events from this FIR/evidence
text. This is used as case context for legal agents.

KNOWN CANONICAL ENTITIES — use EXACTLY these spellings in the "actors" field:
{known_entities}

INCIDENT ANCHOR (verified by fact extraction — treat as ground truth):
{incident_anchor}

Rules:
- Extract 4 to 8 KEY events only. Do NOT extract micro-steps.
  CONSOLIDATE related sub-actions into one event:
    e.g. "parked vehicle, went to market, returned, found vehicle missing" = ONE event
         ("Complainant parked vehicle and discovered it stolen upon return").
- Typical event sequence for a theft FIR:
    1. Offence occurrence (vehicle parked / theft took place)
    2. Complainant searched area
    3. Complainant filed complaint at police station
    4. FIR registered
    5. IO assigned
- date: "DD/MM/YYYY" if stated, else null.
- time: "HH:MM" strictly in 24-hour format. CRITICAL 12h→24h rule:
    * Marathi/Hindi evening markers: सायंकाळी, संध्याकाळी, सायं, रात्री near a digit
      < 12 → ADD 12  (e.g. सायं 7:30 = 19:30, सायं 8:00 = 20:00).
    * English: "evening", "night", "PM", "p.m." → same rule.
    * Morning: सकाळी, सकाळ, "morning", "AM" → keep < 12.
    * Incident anchor time is ground truth — use it to validate.
- CRITICAL ordering rule:
    * complaint_filed and fir_registered events MUST use the actual police station
      filing date (shown in the FIR header), NOT the incident date.
    * complaint_filed / fir_registered always come AFTER all incident events.
- event_type: one of
  ["incident","transaction","communication","threat","promise",
   "complaint_filed","fir_registered","investigation_action","other"]
- actors: use KNOWN CANONICAL ENTITIES spellings. Include only people directly
  and meaningfully involved in this event.
- amount: numeric string without currency symbol, or null.
- location: string or null.
- description: one clear, factual sentence in English.
- Return ONLY a valid JSON array (no markdown fences, no commentary).

Return JSON schema:
[
  {{
    "date": "DD/MM/YYYY or null",
    "time": "HH:MM or null",
    "event_type": "string",
    "description": "string",
    "actors": ["string"],
    "location": "string or null",
    "amount": "string or null"
  }}
]

TEXT:
{text}
"""

TIMELINE_RECON_PROMPT = BASE_RULES + """\
Task: Reconcile and CONSOLIDATE a clean chronological timeline from multiple partial
event lists + full OCR text as ground truth.

KNOWN CANONICAL ENTITIES — use EXACTLY these spellings in the "actors" field:
{known_entities}

INCIDENT ANCHOR (verified by fact extraction — treat as ground truth):
{incident_anchor}

Rules:
- Merge all duplicate / near-duplicate events. Final output: 4–8 KEY events only.
- CONSOLIDATE micro-steps: parking + going to market + returning + discovering theft
  should be 1–2 events, NOT 4 separate events.
- Sort ascending by date then time. Events with null date sort to the end.
- Assign sequential ids "E1", "E2", ... in final chronological order.
- Canonicalize actor names using KNOWN CANONICAL ENTITIES spellings.
- CRITICAL: complaint_filed / fir_registered MUST have the police station filing date
  (NOT the incident date). They come AFTER all incident events.
- CRITICAL 12h/24h: if anchor says 19:30 but a partial shows 07:30 for same incident,
  correct to 19:30.
- Return ONLY a valid JSON array (no markdown fences, no commentary).

Return JSON schema:
[
  {{
    "event_id": "E1",
    "date": "DD/MM/YYYY or null",
    "time": "HH:MM or null",
    "event_type": "string",
    "description": "string",
    "actors": ["string"],
    "location": "string or null",
    "amount": "string or null"
  }}
]

FULL OCR TEXT:
{full_text}

PARTIAL EVENT LISTS:
{partial_jsons}
"""


def _llm_json_any(prompt: str) -> Optional[Any]:
    """Like _llm_json but does not assume a dict — timeline calls return a JSON array."""
    llm = get_llm(temperature=0)
    response = llm.invoke(prompt)
    return _parse_llm_json(response.content)


def _normalise_timeline_event(e: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    actors_raw = e.get("actors") or []
    if not isinstance(actors_raw, list):
        actors_raw = []
    return {
        "event_id": e.get("event_id") or fallback_id,
        "date": e.get("date") or None,
        "time": e.get("time") or None,
        "event_type": e.get("event_type") or "other",
        "description": e.get("description") or None,
        "actors": [str(a) for a in actors_raw if a is not None],
        "location": e.get("location") or None,
        "amount": e.get("amount") or None,
    }


def _sort_key_for_event(e: Dict[str, Any]) -> tuple:
    d = e.get("date")
    t = e.get("time") or "00:00"
    if d:
        try:
            day, month, year = d.split("/")
            date_key = (int(year), int(month), int(day))
        except Exception:
            date_key = (9999, 12, 31)  # undated -> push to end, stable-sorted by narrative order
    else:
        date_key = (9999, 12, 31)
    try:
        hh, mm = t.split(":")[:2]
        time_key = (int(hh), int(mm))
    except Exception:
        time_key = (0, 0)
    return date_key + time_key


# ====================================================================
# Facts-context helpers for timeline
# ====================================================================

def _build_known_entities_str(facts: Dict[str, Any]) -> str:
    """Build a bullet-list of canonical person names from already-extracted facts."""
    who = facts.get("who") or {}
    lines = []
    if who.get("complainant"):
        lines.append(f"- Complainant: {who['complainant']}")
    for name in who.get("accused") or []:
        if name and name.lower() != "unknown":
            lines.append(f"- Accused: {name}")
    for name in who.get("victims") or []:
        if name:
            lines.append(f"- Victim: {name}")
    return "\n".join(lines) if lines else "(none identified yet)"


def _build_incident_anchor_str(facts: Dict[str, Any]) -> str:
    """Summarise the ground-truth incident date/time/place for the LLM."""
    incident = facts.get("incident") or {}
    parts = []
    if incident.get("date"):
        parts.append(f"Date: {incident['date']}")
    if incident.get("time"):
        parts.append(f"Time: {incident['time']} (24h)")
    if incident.get("place"):
        parts.append(f"Place: {incident['place']}")
    return ", ".join(parts) if parts else "(not available)"


# Evening / morning markers for 12h→24h post-processing
_EVENING_RE = re.compile(
    r"\b(evening|night|pm|p\.m\.|dusk|afternoon|"
    r"\u0938\u093e\u092f\u0902\u0915\u093e\u0933\u0940|"  # सायंकाळी
    r"\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940|"  # संध्याकाळी
    r"\u0930\u093e\u0924\u094d\u0930\u0940|"  # रात्री
    r"\u0926\u0941\u092a\u093e\u0930|"  # दुपार
    r"\u0938\u093e\u092f\u0902)\b",  # सायं
    re.IGNORECASE,
)
_MORNING_RE = re.compile(
    r"\b(morning|am|a\.m\.|dawn|sunrise|"
    r"\u0938\u0915\u093e\u0933\u0940|"  # सकाळी
    r"\u0938\u0915\u093e\u0933|"  # सकाळ
    r"\u092a\u0939\u093e\u091f\u0947)\b",  # पहाटे
    re.IGNORECASE,
)


def _normalize_timeline_times(
    events: List[Dict[str, Any]],
    facts: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Post-process timeline events to fix 12h/24h confusion.

    Strategy:
      1. If an event description contains an evening/night keyword and its
         extracted time hour < 12, shift it by +12 hours.
      2. For incident-typed events on the same date as the FIR incident,
         cross-check against facts.incident.time (reliably extracted).
         If the anchor is clearly PM (>= 12h) but the event hour < 12, shift.
    """
    incident = facts.get("incident") or {}
    incident_date = incident.get("date")
    incident_time_str = incident.get("time") or ""

    # Derive anchor hour from facts incident time (e.g. "19:30 - 20:00" → 19)
    anchor_hour: Optional[int] = None
    try:
        first_part = incident_time_str.split("-")[0].strip()
        if ":" in first_part:
            anchor_hour = int(first_part.split(":")[0])
    except Exception:
        pass

    for e in events:
        t = e.get("time")
        if not t or ":" not in t:
            continue
        try:
            hh = int(t.split(":")[0])
            mm = int(t.split(":")[1][:2])
        except Exception:
            continue

        if hh >= 12:
            continue  # already 24h, no fix needed

        description = (e.get("description") or "").lower()
        needs_shift = False

        # Rule 1: evening/night keyword in the (English) description
        if _EVENING_RE.search(description):
            needs_shift = True

        # Rule 2: incident-type event on incident date, anchor is PM
        if (
            not needs_shift
            and anchor_hour is not None
            and anchor_hour >= 12
            and e.get("event_type") == "incident"
            and e.get("date") == incident_date
        ):
            needs_shift = True

        if needs_shift:
            new_hh = hh + 12
            if new_hh < 24:
                e["time"] = f"{new_hh:02d}:{mm:02d}"

    return events


def _validate_and_deduplicate_timeline(
    events: List[Dict[str, Any]],
    facts: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Python-level validation pass after LLM extraction.

    1. Deduplicate: identical (date, time, event_type) pairs → keep first.
    2. Ordering guard: complaint_filed / fir_registered events that have the
       same date as the incident are likely wrong (LLM confused incident date
       with filing date). Push them to end by nulling their date+time so
       the sort places them after all dated incident events.
    3. Cap: if somehow > 10 events were returned, trim to 10 (edge cases
       where LLM ignored the 4-8 rule).
    """
    incident_date = (facts.get("incident") or {}).get("date")

    # --- step 1: deduplicate on (date, time, event_type) ---
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for e in events:
        key = (e.get("date"), e.get("time"), e.get("event_type"))
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    # --- step 2: ordering guard for complaint/FIR events ---
    _FILING_TYPES = {"complaint_filed", "fir_registered"}
    validated: List[Dict[str, Any]] = []
    for e in deduped:
        if e.get("event_type") in _FILING_TYPES and incident_date:
            if e.get("date") == incident_date:
                # Wrong date: complaint cannot precede or share the incident date
                # unless there's a clear same-day filing (rare for theft FIRs).
                # Null out date+time so sort pushes it to the end.
                e = dict(e)
                e["date"] = None
                e["time"] = None
        validated.append(e)

    # --- step 3: cap at 10 events ---
    return validated[:10]


def _extract_timeline_single_pass(
    raw_text: str,
    facts: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    facts = facts or {}
    known_entities = _build_known_entities_str(facts)
    incident_anchor = _build_incident_anchor_str(facts)
    prompt = TIMELINE_PROMPT.format(
        text=raw_text,
        known_entities=known_entities,
        incident_anchor=incident_anchor,
    )
    result = _llm_json_any(prompt)
    events_raw = result if isinstance(result, list) else []
    events = [
        _normalise_timeline_event(e, f"E{i+1}")
        for i, e in enumerate(events_raw)
        if isinstance(e, dict)
    ]
    events = _normalize_timeline_times(events, facts)
    events = _validate_and_deduplicate_timeline(events, facts)
    events.sort(key=_sort_key_for_event)
    for i, e in enumerate(events):
        e["event_id"] = f"E{i+1}"
    return events


def _extract_timeline_chunked_with_reconciliation(
    raw_text: str,
    facts: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    facts = facts or {}
    known_entities = _build_known_entities_str(facts)
    incident_anchor = _build_incident_anchor_str(facts)

    chunks = _chunk_document_aware(raw_text)

    partials: List[List[Dict[str, Any]]] = []
    for chunk in chunks:
        prompt = TIMELINE_PROMPT.format(
            text=chunk,
            known_entities=known_entities,
            incident_anchor=incident_anchor,
        )
        p = _llm_json_any(prompt)
        if isinstance(p, list) and p:
            partials.append(p)

    if not partials:
        if chunks:
            return _extract_timeline_single_pass(chunks[0], facts)
        return []

    full_text_cut = raw_text[:MAX_RECON_FULL_TEXT_CHARS]
    partial_jsons_str = "\n\n".join(
        f"### Chunk {i+1}\n```json\n{json.dumps(p, indent=2, ensure_ascii=False)}\n```"
        for i, p in enumerate(partials)
    )

    recon = _llm_json_any(
        TIMELINE_RECON_PROMPT.format(
            full_text=full_text_cut,
            partial_jsons=partial_jsons_str,
            known_entities=known_entities,
            incident_anchor=incident_anchor,
        )
    )

    if not isinstance(recon, list) or not recon:
        # fallback: flatten + sort the partials we already have
        flat = [e for plist in partials for e in plist if isinstance(e, dict)]
        events = [_normalise_timeline_event(e, f"E{i+1}") for i, e in enumerate(flat)]
        events = _normalize_timeline_times(events, facts)
        events = _validate_and_deduplicate_timeline(events, facts)
        events.sort(key=_sort_key_for_event)
        for i, e in enumerate(events):
            e["event_id"] = f"E{i+1}"
        return events

    events = [
        _normalise_timeline_event(e, f"E{i+1}")
        for i, e in enumerate(recon)
        if isinstance(e, dict)
    ]
    events = _normalize_timeline_times(events, facts)
    events = _validate_and_deduplicate_timeline(events, facts)
    events.sort(key=_sort_key_for_event)
    for i, e in enumerate(events):
        e["event_id"] = f"E{i+1}"
    return events


def extract_timeline(
    raw_text: str,
    facts: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Produces a chronologically ordered list of case events, meant to be handed
    to other agents (Prosecutor/Defense/Judge/Accused) as shared context.

    `facts` — the already-extracted fact dict from extract_facts(). Passing it
    ensures the timeline LLM uses identical canonical person names and is
    anchored to the correct incident date/time, fixing 12h/24h confusion.

    Reuses the same short-doc vs chunked+reconciliation strategy as extract_facts.
    """
    if len(raw_text) <= MAX_DIRECT_CHARS:
        print(f"[evidence_analyzer] timeline: {len(raw_text)} chars — single-pass extraction.")
        return _extract_timeline_single_pass(raw_text, facts)

    print(
        f"[evidence_analyzer] timeline: {len(raw_text)} chars (> {MAX_DIRECT_CHARS}) — "
        "chunked extraction + reconciliation."
    )
    return _extract_timeline_chunked_with_reconciliation(raw_text, facts)


# ====================================================================
# ADDITIVE: Relationship graph builder
# (Deterministic — no LLM calls. Builds a Neo4j-shaped {nodes, edges}
#  structure from `facts` that can be imported later via MERGE statements.
#  Nothing is written to Neo4j yet.)
# ====================================================================

def _slug(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def build_case_graph(
    session_id: str,
    facts: Dict[str, Any],
    timeline: Optional[List[Dict[str, Any]]] = None,  # kept for API compat, not used
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns {"nodes": [...], "edges": [...]}.

    Node shape:   {"id", "label", "properties": {...}}
    Edge shape:   {"source", "target", "type", "properties": {...}}

    Minimal, clean graph — only the essential case facts:
      Person(complainant) → FILED       → Case
      Person(accused)    → ACCUSED_IN  → Case
      Person(victim)     → VICTIM_IN   → Case
      Case → OCCURRED_AT     → Location
      Case → CHARGED_UNDER   → Section
      Case → INVOLVES_PROPERTY → Property

    No event nodes, no NEXT chains, no per-event edges.
    Node ids are deterministic slugs for idempotent Neo4j MERGE.
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    _edge_set: set = set()  # (source, target, type) dedup

    def add_node(node_id: str, label: str, properties: Dict[str, Any]) -> str:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "properties": properties}
        return node_id

    def add_edge(
        source: str,
        target: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = (source, target, rel_type)
        if key in _edge_set:
            return
        _edge_set.add(key)
        edges.append({
            "source": source,
            "target": target,
            "type": rel_type,
            "properties": properties or {},
        })

    who = facts.get("who") or {}
    incident = facts.get("incident") or {}
    prop = facts.get("property") or {}
    sections = facts.get("sections") or []

    # ── Case node ─────────────────────────────────────────────────────
    case_id = add_node(
        f"case:{session_id}",
        "Case",
        {
            "session_id": session_id,
            "summary": incident.get("summary"),
            "date": incident.get("date"),
            "time": incident.get("time"),
            "place": incident.get("place"),
        },
    )

    # ── Primary incident location ──────────────────────────────────────
    if incident.get("place"):
        loc_id = add_node(
            f"location:{_slug(incident['place'])}",
            "Location",
            {"name": incident["place"]},
        )
        add_edge(case_id, loc_id, "OCCURRED_AT")

    # ── People (from facts only — canonical spelling guaranteed) ────────
    def get_person_node(name: str) -> str:
        pid = f"person:{_slug(name)}"
        add_node(pid, "Person", {"name": name})
        return pid

    complainant = who.get("complainant")
    if complainant:
        add_edge(get_person_node(complainant), case_id, "FILED")

    for name in who.get("accused") or []:
        if name:
            add_edge(get_person_node(name), case_id, "ACCUSED_IN")

    for name in who.get("victims") or []:
        if name:
            add_edge(get_person_node(name), case_id, "VICTIM_IN")

    # ── Legal sections ────────────────────────────────────────────────
    for sec in sections:
        if sec:
            sec_id = add_node(f"section:{_slug(sec)}", "Section", {"name": sec})
            add_edge(case_id, sec_id, "CHARGED_UNDER")

    # ── Property ──────────────────────────────────────────────────────
    prop_index = 0
    for veh in prop.get("vehicles") or []:
        prop_index += 1
        pid = add_node(
            f"property:vehicle:{prop_index}",
            "Property",
            {"kind": "vehicle", **veh},
        )
        add_edge(case_id, pid, "INVOLVES_PROPERTY")

    for other in prop.get("other_property") or []:
        prop_index += 1
        pid = add_node(
            f"property:other:{prop_index}",
            "Property",
            {"kind": "other", "description": other},
        )
        add_edge(case_id, pid, "INVOLVES_PROPERTY")

    if prop.get("cash"):
        pid = add_node("property:cash:1", "Property", {"kind": "cash", "value": prop["cash"]})
        add_edge(case_id, pid, "INVOLVES_PROPERTY")

    if prop.get("gold"):
        pid = add_node("property:gold:1", "Property", {"kind": "gold", "value": prop["gold"]})
        add_edge(case_id, pid, "INVOLVES_PROPERTY")

    return {"nodes": list(nodes.values()), "edges": edges}


# ====================================================================
# ADDITIVE: Store timeline + graph
# (Uses .update() on the doc that store_to_firestore already created —
#  never overwrites raw_text/facts, and never touches store_to_firestore's
#  own overwrite-guard logic.)
# ====================================================================

def store_timeline_and_graph(
    session_id: str,
    timeline: List[Dict[str, Any]],
    graph: Dict[str, List[Dict[str, Any]]],
) -> None:
    db = _get_firestore_client()
    doc_ref = db.collection("document_store").document(session_id)

    if not doc_ref.get().exists:
        raise ValueError(
            f"session_id '{session_id}' not found in document_store — "
            "run store_to_firestore (via analyze_evidence) first."
        )

    doc_ref.update({
        "timeline": timeline,
        "graph": graph,
        "context_schema_version": "v1_timeline_graph",
    })


# ====================================================================
# ADDITIVE: Extended orchestrator
# (Wraps the existing, untouched pipeline and adds timeline + graph on top.
#  analyze_evidence() above remains fully independent and unchanged.)
# ====================================================================

def analyze_evidence_with_context(session_id: str, file_path: str) -> Dict[str, Any]:
    raw_text = extract_text(file_path)
    facts = extract_facts(raw_text)
    store_to_firestore(session_id, raw_text, facts)
    store_to_pinecone(session_id, facts)

    # Pass already-extracted facts so timeline LLM uses identical canonical names
    # and is anchored to the correct incident date/time (fixes 12h/24h confusion).
    timeline = extract_timeline(raw_text, facts)
    graph = build_case_graph(session_id, facts, timeline)
    store_timeline_and_graph(session_id, timeline, graph)

    return {
        "rawText": raw_text,
        "facts": facts,
        "timeline": timeline,
        "graph": graph,
    }


if __name__ == "__main__":
    test_file = input("Enter path to the FIR/evidence file (PDF or image): ").strip()

    if not test_file:
        print("No file name entered. Exiting.")
    elif not Path(test_file).exists():
        print(f"No file found at '{test_file}'.")
    else:
        session_id = build_session_id(test_file)
        print(f"Creating new session: {session_id}")
        # Use the context-aware pipeline here so CLI runs also produce
        # timeline + graph output and persist them to Firestore.
        result = analyze_evidence_with_context(session_id, test_file)
        print(json.dumps(result, indent=2, ensure_ascii=False))
