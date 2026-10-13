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

# pytesseract is optional — only needed when OCR_PROVIDER=tesseract
try:
    import pytesseract
    from PIL import Image
    _TESSERACT_AVAILABLE = True
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
except ImportError:
    pytesseract = None  # type: ignore
    Image = None        # type: ignore
    _TESSERACT_AVAILABLE = False

from PyPDF2 import PdfReader
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from config.llm_config import get_llm

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
        try:
            _firebase_app = firebase_admin.get_app()
        except ValueError:
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
You are a legal document analyst reviewing an Indian criminal case, FIR, petition, or order.

Source may be Hindi/Marathi/English mixed with OCR noise.
CRITICAL: Output EVERY string in English only.
- Translate descriptions/locations to English.
- Transliterate person names to Roman script.
- Canonicalize OCR spelling variants of the same entity.
Return ONLY valid JSON (no markdown fences, no commentary).
"""

UNIFIED_PROMPT = BASE_RULES + """\
Task: Extract an open, comprehensive list of facts from the text.
Extract each distinct factual assertion as an item in a list, tied to its specific source (e.g. paragraph number, page, FIR, complaint, or order) and classify each fact by its type.
Do NOT use fixed category fields. Extract facts freely.

Include all material facts:
- Parties involved (complainant, accused, victim, eyewitnesses)
- Narrative of the alleged incident (dates, times, places, specific actions)
- Physical & documentary evidence (injuries, weapons, medical examination, recoveries, seizure memos)
- Procedural history & investigation status (FIR details, notices, summons, non-bailable warrants, proclamation under Sec 82 CrPC/BNSS, arrest status)
- Statutory sections invoked (IPC, BNS, CrPC, BNSS, etc.)

Classify each fact with "type":
- "allegation": assertions, charges, or factual claims made by complainant, informant, FIR, prosecution, or defense
- "procedural_event": official court or police process events (summons, bailable/non-bailable warrants, Section 82 proclamation, attachment, dates of filing/orders)
- "court_finding": judicial evaluations, findings, observations, or legal conclusions of the presiding judge/court

Return JSON schema:
[
  {{
    "id": "fact_1",
    "text": "Detailed statement of the fact",
    "source": "para 14",
    "type": "allegation|procedural_event|court_finding"
  }}
]

TEXT:
{text}
"""

UNIFIED_RECON_PROMPT = BASE_RULES + """\
Task: Reconcile complete extracted facts from multiple chunk outputs + full OCR text.
Use full OCR text as ground truth where conflicts exist.
Deduplicate and refine into an open list of facts with explicit IDs, sources, and type ("allegation" | "procedural_event" | "court_finding").

Return JSON schema:
[
  {{
    "id": "fact_1",
    "text": "Detailed statement of the fact",
    "source": "para 14",
    "type": "allegation|procedural_event|court_finding"
  }}
]

FULL OCR TEXT:
{full_text}

PARTIALS:
{partial_jsons}
"""


# ====================================================================
# Step 3 logic helpers
# ====================================================================

def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences and extract the outermost JSON value (array or object)."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()

    # Try to find a JSON array first (preferred output format)
    arr_start = cleaned.find("[")
    arr_end   = cleaned.rfind("]")
    obj_start = cleaned.find("{")
    obj_end   = cleaned.rfind("}")

    if arr_start != -1 and arr_end > arr_start:
        # Array found — but only prefer it over an object if it starts earlier or at same pos
        if obj_start == -1 or arr_start <= obj_start:
            return cleaned[arr_start:arr_end + 1]

    if obj_start != -1 and obj_end > obj_start:
        return cleaned[obj_start:obj_end + 1]

    return cleaned


def _parse_llm_json(raw_response: str) -> Optional[Any]:
    if not raw_response or not isinstance(raw_response, str):
        return None
    cleaned = _strip_json_fences(raw_response)
    try:
        result = json.loads(cleaned)
        # Reject if the parser returned a bare string (broken JSON capture)
        if isinstance(result, str):
            print(f"[evidence_analyzer] Warning: JSON parsed to bare string, skipping.")
            return None
        return result
    except json.JSONDecodeError:
        # Try json_repair if available
        try:
            import json_repair
            repaired = json_repair.repair_json(cleaned, return_objects=True)
            if isinstance(repaired, (dict, list)):
                return repaired
        except ImportError:
            pass
        print("Warning: could not parse LLM output:")
        print(cleaned[:600])
        return None


# key = os.getenv("GROQ_API_KEY")
# print("Using key:", key[:12], "...", key[-6:])

def _llm_json(prompt: str) -> Optional[Any]:
    llm = get_llm(temperature=0)
    response = llm.invoke(prompt)
    return _parse_llm_json(response.content)


def _normalise_facts(facts: Any) -> List[Dict[str, Any]]:
    """
    Normalise whatever the LLM returned into List[{id, text, source}].
    Handles:
      - Correct: list of fact dicts           [{"id":..., "text":..., "source":...}, ...]
      - Wrapper: dict with facts/items key     {"facts": [{...}]}
      - Single:  a single fact dict            {"id":..., "text":..., "source":...}
      - Legacy:  nested key-value dict         {"accused": {"name": "X"}, ...}
      - String:  bare string (broken capture)  -> empty
    """
    # Unwrap common wrapper patterns
    if isinstance(facts, dict):
        for wrapper_key in ("facts", "items", "result", "results", "data", "extracted_facts"):
            if wrapper_key in facts and isinstance(facts[wrapper_key], list):
                facts = facts[wrapper_key]
                break
        else:
            # Check if it looks like a single fact object
            if "text" in facts or "value" in facts:
                single_txt = str(facts.get("text") or facts.get("value") or "").strip()
                if single_txt:
                    return [{"id": "fact_1",
                             "text": single_txt,
                             "source": str(facts.get("source", "record")).strip()}]
            # Legacy nested dict: flatten
            out: List[Dict[str, Any]] = []
            for k, v in facts.items():
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        if sub_v:
                            out.append({"id": f"fact_{len(out) + 1}",
                                        "text": f"{k}.{sub_k}: {sub_v}",
                                        "source": "record"})
                elif isinstance(v, list):
                    for item in v:
                        if item:
                            out.append({"id": f"fact_{len(out) + 1}",
                                        "text": f"{k}: {item}",
                                        "source": "record"})
                elif v:
                    out.append({"id": f"fact_{len(out) + 1}",
                                "text": f"{k}: {v}",
                                "source": "record"})
            return out

    if isinstance(facts, list):
        out = []
        for i, item in enumerate(facts):
            if isinstance(item, dict):
                fid = item.get("id") or f"fact_{i + 1}"
                txt = item.get("text") or item.get("value") or str(item)
                src = item.get("source") or "record"
                ftype = item.get("type") or "allegation"
                out.append({"id": str(fid), "text": str(txt).strip(), "source": str(src).strip(), "type": str(ftype).strip()})
            elif isinstance(item, str) and item.strip():
                out.append({"id": f"fact_{i + 1}", "text": item.strip(), "source": "record", "type": "allegation"})
        return out

    # Anything else (None, string, int) — return empty
    return []


def _empty_facts() -> List[Dict[str, Any]]:
    return []


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
        # fallback: merge all partial results
        merged: List[Dict[str, Any]] = []
        seen_texts: set = set()
        for partial in partials:
            for fact in _normalise_facts(partial):
                txt = fact.get("text", "").strip()
                if txt and txt not in seen_texts:
                    seen_texts.add(txt)
                    fact["id"] = f"fact_{len(merged) + 1}"
                    merged.append(fact)
        return merged if merged else _normalise_facts(partials[0])

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

    if isinstance(facts, list):
        text_for_embedding = " ".join([f.get("text", "") for f in facts[:10]]).strip()
        place_meta = ""
    elif isinstance(facts, dict):
        text_for_embedding = facts.get("incident", {}).get("summary") or ""
        place_meta = facts.get("incident", {}).get("place") or ""
    else:
        text_for_embedding = str(facts).strip()
        place_meta = ""

    if not text_for_embedding:
        print("Skipping Pinecone: no facts text to embed")
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
            "summary": text_for_embedding[:500],
            "place": place_meta,
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
    try:
        store_to_firestore(session_id, raw_text, facts)
    except Exception as e:
        print(f"[EvidenceAnalyzer] Skipping Firestore storage: {e}")
    try:
        store_to_pinecone(session_id, facts)
    except Exception as e:
        print(f"[EvidenceAnalyzer] Skipping Pinecone storage: {e}")
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