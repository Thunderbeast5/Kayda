from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Hard dependencies — wrap so module loads even if some are missing
# ---------------------------------------------------------------------------
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
except Exception:
    pytesseract = None  # type: ignore

try:
    from PIL import Image
except Exception:
    Image = None  # type: ignore

_TESSERACT_AVAILABLE = bool(pytesseract is not None and Image is not None)

try:
    from PyPDF2 import PdfReader
    _PYPDF2_AVAILABLE = True
except ImportError:
    try:
        from pypdf import PdfReader   # pypdf is the maintained fork
        _PYPDF2_AVAILABLE = True
    except Exception:
        PdfReader = None  # type: ignore
        _PYPDF2_AVAILABLE = False

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False

# Optional Google Vision / pdf2image imports (graceful fallback if not installed)
try:
    from google.cloud import vision
except Exception:
    vision = None

try:
    # pyrefly: ignore [missing-import]
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None

_VISION_AVAILABLE = bool(vision is not None and convert_from_path is not None)

from dotenv import load_dotenv
from config.llm_config import get_llm

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")


FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

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
    if not _FIREBASE_AVAILABLE:
        return None
    if not FIREBASE_CREDENTIALS_PATH:
        return None
    cred_path = BASE_DIR / FIREBASE_CREDENTIALS_PATH
    if not cred_path.exists():
        return None
    if _firebase_app is None:
        try:
            cred = credentials.Certificate(str(cred_path))
            _firebase_app = firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"[Warning] Firebase initialization failed ({e}).")
            return None
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
        text = ""
        if _PYPDF2_AVAILABLE and PdfReader is not None:
            try:
                reader = PdfReader(str(file_path))
                for page in reader.pages:
                    text += page.extract_text() or ""
                text = text.strip()
            except Exception:
                text = ""

        if text:
            return text

        # OCR fallback for scanned PDFs
        if convert_from_path is not None and _TESSERACT_AVAILABLE and pytesseract is not None:
            try:
                images = convert_from_path(str(file_path), dpi=300)
                ocr_text = ""
                for img in images:
                    ocr_text += pytesseract.image_to_string(img, lang=OCR_LANGS, config="--psm 6") + "\n"
                return ocr_text.strip()
            except Exception as e:
                print(f"Warning: OCR fallback failed: {e}")

        if text:
            return text

        return ""

    elif ext in IMAGE_EXTENSIONS:
        if _TESSERACT_AVAILABLE and pytesseract is not None and Image is not None:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image, lang=OCR_LANGS).strip()
        return ""

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


def extract_text_from_any(source: Any) -> str:
    """
    Accepts:
      - A file path (str or Path) to PDF, image, txt, or json
      - Raw text string
    Returns extracted text as string.
    """
    if isinstance(source, Path):
        path = source
    elif isinstance(source, str):
        p = Path(source)
        if p.exists() and p.is_file():
            path = p
        else:
            # It is raw text directly
            return source
    else:
        return str(source)

    ext = path.suffix.lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in ["text", "case_text", "content", "judgement", "judgment", "body"]:
                if key in data and isinstance(data[key], str):
                    return data[key]
            return json.dumps(data, indent=2)
        elif isinstance(data, list):
            return "\n\n".join(str(item) for item in data)
        return str(data)

    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")

    # PDF or Images
    return extract_text(str(path))


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
You are a legal document analyst reviewing an Indian legal document.

Source may be Hindi/Marathi/English mixed with OCR noise.
CRITICAL: Output EVERY string in English only.
- Translate descriptions/locations to English.
- Transliterate person names to Roman script.
- Canonicalize OCR spelling variants of same person into one best form.
- NEVER confuse court staff (typists, stenographers, clerks who sign orders) with
  case parties. A person whose name appears only in a digital signature block at the
  end of an order is court staff, NOT a complainant or victim.
Return ONLY valid JSON (no markdown fences, no commentary).
"""

# ------------------------------------------------------------------
# For FIR / charge-sheet documents
# ------------------------------------------------------------------
UNIFIED_PROMPT = BASE_RULES + """\

Task: Extract complete structured facts from this FIR / charge-sheet / evidence text.

Rules:
- complainant: person who filed the complaint at the police station (from FIR narrative).
- accused: only officially named accused persons.
- victims: only directly harmed persons. Do NOT include accused as victims.
- Incident date/time/place: the offence occurrence, NOT the FIR filing date.
- Use 24-hour time format.
- Preserve quantities/units exactly for property fields.
- estimated_loss: use FIR stated total; compute from itemised amounts if total absent.
- sections: IPC/BNS/special-Act sections; normalise as "BNS 310(2)", "IT Act 66C".

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

# ------------------------------------------------------------------
# For bail order / anticipatory bail application documents
# ------------------------------------------------------------------
UNIFIED_BAIL_PROMPT = BASE_RULES + """\

Task: Extract complete structured facts from this Indian anticipatory bail or regular
bail court order / application.

IMPORTANT PARTY IDENTIFICATION RULES:
- "applicant" = the accused person seeking bail (named at the top under the case title).
- "complainant" = the original FIR complainant / informant (victim who filed the FIR).
  This is NOT the court typist or stenographer whose name may appear in a digital
  signature block at the very end of the document.
- "victims" = persons who suffered the crime (often same as or includes complainant).
- "co_accused" = other accused persons named in FIR / remand reports / chargesheet
  (EXCLUDING the applicant themselves).
- "court_staff" = persons named only in the digital signature / certification block;
  do NOT include them in any party category.

Return this JSON schema exactly (use null for any absent field):
{{
  "document_type": "bail_order",
  "case_number": "string or null",
  "court": "string or null",
  "judge": "string or null",
  "date_of_order": "DD/MM/YYYY or null",
  "bail_type": "anticipatory or regular",
  "applicant": "name of the accused seeking bail or null",
  "applicant_role_in_crime": "specific role alleged e.g. driver of getaway car or null",
  "respondent": "State of Maharashtra or null",
  "complainant": "original FIR informant / complainant name or null",
  "victims": ["names of persons who suffered the crime"],
  "co_accused": ["other accused persons — NOT the applicant"],
  "applicant_counsel": "advocate name or null",
  "state_counsel": "APP/advocate name or null",
  "investigating_officer": "IO name and designation or null",
  "fir_number": "string or null",
  "police_station": "string or null",
  "district": "string or null",
  "incident_summary": "one clear paragraph describing the underlying crime as narrated in the order",
  "incident_date": "DD/MM/YYYY or null",
  "incident_time": "HH:MM (24h) or null",
  "incident_place": "string or null",
  "offence_nature": "brief label e.g. dacoity at village fair or null",
  "sections_charged": ["e.g. BNS 310(2)", "BNSS 482"],
  "property_stolen": ["item-by-item list of stolen property with values where stated"],
  "total_loss": "total rupee value stated or null",
  "key_evidence_items": [
    "list every piece of evidence mentioned — cell phone, SIM card, vehicle, witness statements, etc."
  ],
  "investigation_findings": [
    "list every factual finding made during investigation as separate strings"
  ],
  "chargesheet_filed": true,
  "applicant_described_as_absconding": true,
  "custodial_interrogation_sought": true,
  "identification_parade_required": true,
  "defense_submissions": [
    "each argument made by defence counsel as a separate string"
  ],
  "prosecution_submissions": [
    "each argument made by prosecution / APP as a separate string"
  ],
  "procedural_history": [
    {{"date": "DD/MM/YYYY or null", "event": "description of procedural step"}}
  ],
  "prior_bail_orders": [
    {{"court": "court name", "application_no": "string or null", "date": "DD/MM/YYYY or null",
      "outcome": "rejected/granted/modified or null", "reason": "brief reason or null"}}
  ],
  "actual_bail_outcome": "granted or rejected or modified or null",
  "court_reasoning": "verbatim or close paraphrase of the court's reasoning paragraphs",
  "ratio_decidendi": "the legal principle/ratio applied by the court or null",
  "judicial_observations": ["each notable observation as a separate string"],
  "key_legal_findings": ["each legal finding as a separate string"],
  "bail_conditions_imposed": ["conditions if bail granted, else empty list"],
  "bail_amount": "surety amount if stated or null"
}}

DOCUMENT TEXT:
{text}
"""

UNIFIED_RECON_PROMPT = BASE_RULES + """\
Task: Reconcile complete structured facts from multiple chunk outputs + full OCR text.
Use full OCR text as ground truth where conflicts exist.
Devanagari OCR denoising is critical for names.
Each real person must appear once in canonical spelling.
Deduplicate legal sections and normalize.

IMPORTANT: The person whose name appears only in a digital signature block at the
END of the document is court staff (typist/stenographer), NOT a complainant or victim.
Identify the complainant from the FIR narrative body, not from signature blocks.

Return JSON schema:
{{
  "who": {{
    "complainant": "FIR complainant from the narrative body, not the digital signer or null",
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
    """Remove markdown code fences and any surrounding commentary."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    last_brace = max(text.rfind("}"), text.rfind("]"))
    if last_brace != -1:
        text = text[:last_brace + 1]
    return text.strip()


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

    def _clean(v: Any) -> Optional[str]:
        """Return None for Python None, the string 'null', or empty strings."""
        if v is None:
            return None
        s = str(v).strip()
        return None if s.lower() in ("null", "") else s

    _PROCEDURAL_PREFIXES_LC = ("bnss", "crpc", "code of criminal procedure")

    def _is_procedural(sec: str) -> bool:
        return any(sec.strip().lower().startswith(p) for p in _PROCEDURAL_PREFIXES_LC)

    clean_complainant = _clean(who.get("complainant"))
    clean_accused = [str(a) for a in (who.get("accused") or [])
                     if a is not None and _clean(str(a)) is not None]
    clean_victims  = [str(v) for v in (who.get("victims") or [])
                      if v is not None and _clean(str(v)) is not None]

    all_sections = [str(x) for x in sections if x is not None and _clean(str(x))]
    offence_secs    = [s for s in all_sections if not _is_procedural(s)]
    procedural_secs = [s for s in all_sections if _is_procedural(s)]

    # Build incident summary with source attribution if it's a plain string
    raw_summary = incident.get("summary")
    if isinstance(raw_summary, dict):
        summary_field = raw_summary  # already attributed
    elif raw_summary:
        summary_field = {
            "text": raw_summary,
            "source": "prosecution_case",
            "certainty": "alleged",
        }
    else:
        summary_field = None

    return {
        "who": {
            "complainant": clean_complainant,
            "accused": clean_accused,
            "victims": clean_victims,
        },
        "incident": {
            "summary": summary_field,
            "date": incident.get("date") or None,
            "time": incident.get("time") or None,
            "place": incident.get("place") or None,
        },
        "property": {
            "cash": prop.get("cash") or None,
            "gold": prop.get("gold") or None,
            "documents": prop.get("documents") or None,
            "vehicles": vehicles,
            "other_property": [str(x) for x in other_property
                               if x is not None and _clean(str(x))],
            "estimated_loss": prop.get("estimated_loss") or None,
        },
        "sections": offence_secs,
        "procedural_provisions": procedural_secs,
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


def _detect_bail_order(raw_text: str) -> bool:
    """
    Quick heuristic: if the text looks like a bail order / application,
    use the bail-aware prompt instead of the FIR prompt.
    Checked before any LLM call to avoid the expensive doc-type detection step
    that lives in case_prep.py (which has its own full classifier).
    """
    markers = [
        "anticipatory bail", "bail application", "anticipatory bail application",
        "bharatiya nagarik suraksha sanhita", "bnss", "coram:", "j.\n",
        "criminal appellate jurisdiction", "sessions judge", "high court",
    ]
    snippet = raw_text[:3000].lower()
    return sum(1 for m in markers if m in snippet) >= 2


def _select_prompt(raw_text: str, doc_type: Optional[str] = None) -> str:
    """Return the appropriate extraction prompt for this document."""
    if doc_type in ("bail_order", "general"):
        return UNIFIED_BAIL_PROMPT
    if doc_type in ("fir", "charge_sheet"):
        return UNIFIED_PROMPT
    # No hint supplied — fall back to heuristic
    return UNIFIED_BAIL_PROMPT if _detect_bail_order(raw_text) else UNIFIED_PROMPT


def _extract_single_call_from_text(
    text: str, doc_type: Optional[str] = None
) -> Dict[str, Any]:
    prompt = _select_prompt(text, doc_type).format(text=text)
    result = _llm_json(prompt)
    # Bail-order extraction returns a richer schema; normalise only the
    # FIR-compatible subset so downstream graph/timeline code still works.
    return _normalise_facts_from_any(result or _empty_facts())


def _build_accused_evolution(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Reconstruct the accused-list changes across FIR → remand → chargesheet stages
    from the procedural_history and defense_submissions in a bail order.

    Issue #5: The investigation story (how the applicant came to be accused)
    is critical for moot court and must be captured explicitly.
    """
    evolution: List[Dict[str, Any]] = []
    co_accused: List[str] = raw.get("co_accused") or []
    applicant: Optional[str] = raw.get("applicant")

    # Stage 1 — FIR (co-accused only; applicant not yet named)
    if co_accused:
        evolution.append({
            "stage": "FIR",
            "persons": co_accused,
            "status": "named_or_unknown",
            "source": "fir",
            "certainty": "recorded",
        })

    # Stage 2+ — procedural history may describe remand reports
    for step in (raw.get("procedural_history") or []):
        if not isinstance(step, dict):
            continue
        event_text = (step.get("event") or "").lower()
        if "first remand" in event_text or "1st remand" in event_text:
            evolution.append({
                "stage": "first_remand",
                "date": step.get("date"),
                "persons": co_accused,
                "source": "procedural_record",
                "certainty": "recorded",
            })
        elif "second remand" in event_text or "2nd remand" in event_text:
            evolution.append({
                "stage": "second_remand",
                "date": step.get("date"),
                "persons": co_accused,
                "source": "procedural_record",
                "certainty": "recorded",
            })

    # Final stage — applicant added through subsequent investigation
    if applicant:
        defence_subs: List[str] = raw.get("defense_submissions") or []
        basis = (
            "co-accused statement"
            if any("co-accused" in s.lower() for s in defence_subs)
            else "investigation"
        )
        evolution.append({
            "stage": "subsequent_investigation",
            "added": [applicant],
            "basis": basis,
            "alleged_role": raw.get("applicant_role_in_crime"),
            "source": "prosecution_case",
            "certainty": "alleged",
        })

    return evolution


def _build_disputed_facts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Derive the principal disputed facts from prosecution and defence submissions.

    Issue #8: Surfaces the actual moot-court issues automatically so
    the Judge/Defense/Prosecution agents have explicit, structured controversy.
    """
    disputed: List[Dict[str, Any]] = []

    defence_subs: List[str] = raw.get("defense_submissions") or []
    prosecution_subs: List[str] = raw.get("prosecution_submissions") or []
    applicant: Optional[str] = raw.get("applicant")

    # Issue 1: applicant's involvement
    if applicant:
        d_pos = next(
            (s for s in defence_subs if "not involved" in s.lower() or "denies" in s.lower()),
            "Applicant denies involvement in the offence.",
        )
        p_pos = next(
            (s for s in prosecution_subs if applicant.split()[0].lower() in s.lower()
             or "involvement" in s.lower()),
            raw.get("applicant_role_in_crime") or "Prosecution alleges applicant participated.",
        )
        disputed.append({
            "issue": "Applicant's involvement in the offence",
            "defence_position": d_pos,
            "prosecution_position": p_pos,
        })

    # Issue 2: basis of implication
    if any("co-accused" in s.lower() for s in defence_subs):
        disputed.append({
            "issue": "Basis of implication of applicant",
            "defence_position": "Applicant implicated solely on the basis of a co-accused's statement.",
            "prosecution_position": (
                next(
                    (s for s in (raw.get("investigation_findings") or [])
                     if "sim" in s.lower() or "phone" in s.lower() or "vehicle" in s.lower()),
                    "Investigation revealed connecting evidence (SIM card / vehicle).",
                )
            ),
        })

    # Issue 3: need for custodial interrogation
    if raw.get("custodial_interrogation_sought") or raw.get("identification_parade_required"):
        disputed.append({
            "issue": "Necessity of custodial interrogation / identification parade",
            "defence_position": (
                next(
                    (s for s in defence_subs if "antecedent" in s.lower() or "bail" in s.lower()),
                    "No criminal antecedents; anticipatory bail should be granted.",
                )
            ),
            "prosecution_position": (
                "Identification parade is required; custodial interrogation is necessary."
            ),
        })

    return disputed


def _normalise_facts_from_any(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept either the FIR schema (who/incident/property/sections)
    or the bail-order schema (applicant, victims, incident_*, sections_charged …)
    and return the canonical FIR-compatible shape.

    Bail-order keys that have no FIR equivalent are preserved under
    the top-level key "bail_details" so callers can still access them.
    """
    # ── Detect which schema we received ──────────────────────────────────
    is_bail = "applicant" in raw or "bail_type" in raw or "document_type" in raw

    if is_bail:
        # Build the canonical who/incident/property/sections subset
        victims: List[str] = raw.get("victims") or []
        co_accused: List[str] = raw.get("co_accused") or []
        applicant: Optional[str] = raw.get("applicant")

        # The applicant IS an accused person for graph/timeline purposes
        accused_list: List[str] = []
        if applicant:
            accused_list.append(applicant)
        accused_list.extend(co_accused)

        # complainant from bail order text
        complainant: Optional[str] = raw.get("complainant") or None

        # If victims list is empty but complainant is known, treat them as victim too
        if complainant and complainant not in victims:
            victims = [complainant] + victims

        # ── Section classification: split offence sections from procedural ones ──
        # BNSS/CrPC provisions (e.g. BNSS 482, CrPC 438) are procedural bail
        # provisions, not substantive offence charges.  Keep them separate so
        # LexiGraph / statutory agents are never confused.
        _PROCEDURAL_PREFIXES = ("bnss", "crpc", "code of criminal procedure")
        all_sections: List[str] = raw.get("sections_charged") or []
        offence_sections: List[str] = []
        procedural_sections: List[str] = []
        for sec in all_sections:
            sec_lower = (sec or "").lower()
            if any(sec_lower.startswith(p) for p in _PROCEDURAL_PREFIXES):
                procedural_sections.append(sec)
            else:
                offence_sections.append(sec)

        # ── Bail application metadata ─────────────────────────────────────────
        # Captures why the applicant is before this court (Issue #4 / #6).
        bail_application = {
            "type": raw.get("bail_type") or "anticipatory",
            "applicant": applicant,
            "provision": procedural_sections[0] if procedural_sections else None,
            "relief_sought": "anticipatory bail" if (
                raw.get("bail_type") or "anticipatory"
            ) == "anticipatory" else "regular bail",
        }

        # ── Applicant's own position (defense submissions distilled) ──────────
        defence_subs: List[str] = raw.get("defense_submissions") or []
        applicant_position = {
            "denies_involvement": any(
                "not involved" in s.lower() or "denies" in s.lower()
                for s in defence_subs
            ),
            "implication_basis": (
                "statement of co-accused"
                if any("co-accused" in s.lower() or "co accused" in s.lower() for s in defence_subs)
                else None
            ),
            "criminal_antecedents": not any(
                "no criminal antecedent" in s.lower() or "no antecedent" in s.lower()
                for s in defence_subs
            ),
            "applicant_described_as_absconding": raw.get(
                "applicant_described_as_absconding", False
            ),
        }

        # ── Investigation story: accused evolution across stages ──────────────
        accused_evolution = _build_accused_evolution(raw)

        # ── Disputed facts for moot court ─────────────────────────────────────
        disputed_facts = _build_disputed_facts(raw)

        canonical = {
            "who": {
                # Never store the string "null" — use Python None.
                "complainant": complainant if complainant and complainant.lower() != "null" else None,
                "accused": [a for a in accused_list if a and str(a).lower() != "null"],
                "victims": [v for v in victims if v and str(v).lower() != "null"],
            },
            "incident": {
                "summary": {
                    "text": raw.get("incident_summary") or None,
                    "source": "prosecution_case",
                    "certainty": "alleged",
                },
                "date": raw.get("incident_date") or None,
                "time": raw.get("incident_time") or None,
                "place": raw.get("incident_place") or None,
            },
            "property": {
                "cash": None,
                "gold": None,
                "documents": None,
                "vehicles": [],
                "other_property": [
                    p for p in (raw.get("property_stolen") or [])
                    if p and str(p).lower() != "null"
                ],
                "estimated_loss": raw.get("total_loss") or None,
            },
            # Offence sections only — no procedural provisions mixed in.
            "sections": offence_sections,
            # Procedural bail provisions stored separately.
            "procedural_provisions": procedural_sections,
            # Bail-application details
            "bail_application": bail_application,
            # Applicant's litigation posture
            "applicant_position": applicant_position,
            # Full investigation story
            "investigation": {
                "accused_evolution": accused_evolution,
            },
            # Moot-court disputed facts layer
            "disputed_facts": disputed_facts,
            # All remaining bail-specific data
            "bail_details": {
                "case_number": raw.get("case_number"),
                "court": raw.get("court"),
                "judge": raw.get("judge"),
                "date_of_order": raw.get("date_of_order"),
                "bail_type": raw.get("bail_type"),
                "applicant": applicant,
                "applicant_role_in_crime": raw.get("applicant_role_in_crime"),
                "applicant_counsel": raw.get("applicant_counsel"),
                "state_counsel": raw.get("state_counsel"),
                "investigating_officer": raw.get("investigating_officer"),
                "fir_number": raw.get("fir_number"),
                "police_station": raw.get("police_station"),
                "district": raw.get("district"),
                "offence_nature": raw.get("offence_nature"),
                "key_evidence_items": raw.get("key_evidence_items") or [],
                "investigation_findings": raw.get("investigation_findings") or [],
                "chargesheet_filed": raw.get("chargesheet_filed", False),
                "custodial_interrogation_sought": raw.get(
                    "custodial_interrogation_sought", False
                ),
                "identification_parade_required": raw.get(
                    "identification_parade_required", False
                ),
                "defense_submissions": defence_subs,
                "prosecution_submissions": raw.get("prosecution_submissions") or [],
                "procedural_history": raw.get("procedural_history") or [],
                "prior_bail_orders": raw.get("prior_bail_orders") or [],
                "actual_bail_outcome": raw.get("actual_bail_outcome"),
                "court_reasoning": raw.get("court_reasoning"),
                "ratio_decidendi": raw.get("ratio_decidendi"),
                "judicial_observations": raw.get("judicial_observations") or [],
                "key_legal_findings": raw.get("key_legal_findings") or [],
                "bail_conditions_imposed": raw.get("bail_conditions_imposed") or [],
                "bail_amount": raw.get("bail_amount"),
            },
        }

        # Normalise the core FIR-compatible subset through the existing normaliser,
        # then re-attach the bail-specific enrichments that _normalise_facts doesn't know about.
        normalised_core = _normalise_facts(canonical)

        # Merge bail-enriched keys back (they are not touched by _normalise_facts).
        for extra_key in (
            "sections",              # offence sections only (already set in canonical)
            "procedural_provisions",
            "bail_application",
            "applicant_position",
            "investigation",
            "disputed_facts",
            "bail_details",
        ):
            if extra_key in canonical:
                normalised_core[extra_key] = canonical[extra_key]

        return normalised_core

    # Plain FIR schema — use existing normaliser as-is
    return _normalise_facts(raw)


def _extract_single_pass(
    raw_text: str, doc_type: Optional[str] = None
) -> Dict[str, Any]:
    """Short docs path: 1 focused call over full text."""
    return _extract_single_call_from_text(raw_text, doc_type)


def _extract_chunked_with_reconciliation(
    raw_text: str, doc_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Long docs path:
      - chunk document-aware
      - per chunk do 1 unified extraction
      - do 1 unified reconciliation with full text + partials
    """
    chunks = _chunk_document_aware(raw_text)
    prompt_template = _select_prompt(raw_text, doc_type)

    partials: List[Dict[str, Any]] = []
    for chunk in chunks:
        p = _llm_json(prompt_template.format(text=chunk))
        if p:
            partials.append(p)

    if not partials:
        if chunks:
            return _extract_single_call_from_text(chunks[0], doc_type)
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
        return _normalise_facts_from_any(partials[0])

    return _normalise_facts_from_any(recon)


def extract_facts(
    raw_text: str, doc_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract structured facts from raw text.

    Args:
        raw_text: extracted text from any legal document.
        doc_type: optional hint — "bail_order", "fir", "charge_sheet", "general".
                  When None, a heuristic detects the document type automatically.
    """
    if len(raw_text) <= MAX_DIRECT_CHARS:
        print(f"[evidence_analyzer] {len(raw_text)} chars — short-doc unified extraction (1 call).")
        return _extract_single_pass(raw_text, doc_type)

    print(
        f"[evidence_analyzer] {len(raw_text)} chars (> {MAX_DIRECT_CHARS}) — "
        "chunked unified extraction + unified reconciliation."
    )
    return _extract_chunked_with_reconciliation(raw_text, doc_type)


# ====================================================================
# Step 4: Store to Firestore
# ====================================================================
def store_to_firestore(session_id: str, raw_text: str, facts: Dict[str, Any]) -> str:
    db = _get_firestore_client()
    if db is None:
        print("[evidence_analyzer] Skipping Firestore: credentials file not found or service unconfigured.")
        return session_id

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
- For bail orders, always capture: incident, FIR registration, each remand report,
  subsequent implication of applicant, chargesheet filing, bail order.
- Typical event sequence for a bail order:
    1. Offence occurrence
    2. FIR registered
    3. First remand report
    4. Second remand report (if any)
    5. Applicant implicated / chargesheet filed
    6. Lower court bail application (if any)
    7. High Court bail hearing and order
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
  ["incident","transaction","communication","threat","promise","following",
   "blocking","harassment","contact_attempt","evidence_recovery","witness_observation",
   "complaint_filed","fir_registered","investigation_action","other"]
<<<<<<< HEAD
- actors: use KNOWN CANONICAL ENTITIES spellings. Include only people directly
  and meaningfully involved in this event.
  CRITICAL for bail orders: Distinguish "alleged_perpetrators" from "applicant_role".
  Do NOT list the bail applicant as a direct perpetrator of the underlying act unless
  the order explicitly says so — only co-accused who were caught at the scene are
  perpetrators. The applicant's role (e.g. getaway driver) is alleged and indirect.
- witnesses: names of any persons who observed this specific event, if stated.
- source: who is asserting this fact — one of [prosecution_case, defence_submission,
  court_finding, procedural_record, fir].
- certainty: one of [alleged, recorded, established].
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
    "witnesses": ["string"],
    "location": "string or null",
    "amount": "string or null",
    "source": "fir or prosecution_case or defence_submission or court_finding or procedural_record",
    "certainty": "alleged or recorded or established"
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
    witnesses_raw = e.get("witnesses") or []
    if not isinstance(witnesses_raw, list):
        witnesses_raw = []
    return {
        "event_id": e.get("event_id") or fallback_id,
        "date": e.get("date") or None,
        "time": e.get("time") or None,
        "event_type": e.get("event_type") or "other",
        "description": e.get("description") or None,
        "actors": [str(a) for a in actors_raw if a is not None],
        "witnesses": [str(w) for w in witnesses_raw if w is not None],
        "location": e.get("location") or None,
        "amount": e.get("amount") or None,
        # Source attribution — who is asserting this fact (Issue #6).
        "source": e.get("source") or "procedural_record",
        "certainty": e.get("certainty") or "recorded",
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

    For bail orders the graph is enriched with applicant-specific relationships:

      Applicant  → APPLICANT_IN          → BailApplication
      Applicant  → ACCUSED_IN            → FIR (with alleged role)
      Applicant  → ALLEGED_ROLE          → RoleNode
      Applicant  → IMPLICATED_THROUGH    → CoAccusedPerson
      Prosecution → ALLEGES              → Applicant
      Defence     → DENIES_ON_BEHALF_OF  → Applicant

    For FIRs / general cases:
      Person(complainant) → FILED       → Case
      Person(accused)    → ACCUSED_IN  → Case
      Person(victim)     → VICTIM_IN   → Case
      Case → OCCURRED_AT     → Location
      Case → CHARGED_UNDER   → Section  (offence sections only)
      Case → INVOLVES_PROPERTY → Property

    Rules:
    - NEVER create a node for None / "null" — skip those entries.
    - Sections in `facts["sections"]` are offence-only (procedural provisions
      live in `facts["procedural_provisions"]` and are NOT graph-connected to Case).
    - Node ids are deterministic slugs for idempotent Neo4j MERGE.
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

    def _is_null(v: Any) -> bool:
        return v is None or str(v).strip().lower() in ("null", "")

    def get_person_node(name: str) -> Optional[str]:
        """Return a Person node id, or None if name is null/empty."""
        if _is_null(name):
            return None
        pid = f"person:{_slug(name)}"
        add_node(pid, "Person", {"name": name})
        return pid

    who = facts.get("who") or {}
    incident = facts.get("incident") or {}
    prop = facts.get("property") or {}
    # Use offence sections only — procedural provisions are not charged offences.
    sections = facts.get("sections") or []
    bail_details = facts.get("bail_details") or {}
    bail_application = facts.get("bail_application") or {}

    # ── Resolve summary text (may be a dict with source attribution) ──────
    summary_raw = incident.get("summary")
    summary_text = (
        summary_raw.get("text") if isinstance(summary_raw, dict) else summary_raw
    )

    # ── Case node ─────────────────────────────────────────────────────────
    case_id = add_node(
        f"case:{session_id}",
        "Case",
        {
            "session_id": session_id,
            "summary": summary_text,
            "date": incident.get("date"),
            "time": incident.get("time"),
            "place": incident.get("place"),
        },
    )

    # ── Primary incident location ──────────────────────────────────────────
    if incident.get("place") and not _is_null(incident["place"]):
        loc_id = add_node(
            f"location:{_slug(incident['place'])}",
            "Location",
            {"name": incident["place"]},
        )
        add_edge(case_id, loc_id, "OCCURRED_AT")

    # ── People ────────────────────────────────────────────────────────────
    complainant = who.get("complainant")
    complainant_id = get_person_node(complainant) if not _is_null(complainant) else None
    if complainant_id:
        add_edge(complainant_id, case_id, "FILED")

    # For bail orders, identify the applicant for richer graph treatment
    applicant_name: Optional[str] = bail_application.get("applicant") or bail_details.get("applicant")

    for name in who.get("accused") or []:
        if _is_null(name):
            continue
        person_id = get_person_node(name)
        if person_id is None:
            continue
        if name == applicant_name and bail_details:
            # Richer relationships for the bail applicant (Issue #7)
            add_edge(person_id, case_id, "ACCUSED_IN",
                     {"basis": "prosecution_allegation", "certainty": "alleged"})

            # APPLICANT_IN → bail application node
            aba_number = bail_details.get("case_number") or session_id
            aba_id = add_node(
                f"bail_application:{_slug(aba_number)}",
                "BailApplication",
                {
                    "case_number": aba_number,
                    "court": bail_details.get("court"),
                    "provision": bail_application.get("provision"),
                    "relief_sought": bail_application.get("relief_sought"),
                },
            )
            add_edge(person_id, aba_id, "APPLICANT_IN")

            # Alleged role in the crime
            role = bail_details.get("applicant_role_in_crime")
            if role and not _is_null(role):
                role_id = add_node(
                    f"role:{_slug(role)}",
                    "AllegedRole",
                    {"description": role, "source": "prosecution_case", "certainty": "alleged"},
                )
                add_edge(person_id, role_id, "ALLEGED_ROLE")

            # Implication through co-accused statement
            appl_pos = facts.get("applicant_position") or {}
            if appl_pos.get("implication_basis"):
                # Find the co-accused whose statement triggered implication
                co_acc_list = bail_details.get("defense_submissions") or []
                # Use the first co-accused as the link source if available
                co_accused_names = who.get("accused") or []
                for co_name in co_accused_names:
                    if co_name != applicant_name and not _is_null(co_name):
                        co_id = get_person_node(co_name)
                        if co_id:
                            add_edge(
                                person_id, co_id, "IMPLICATED_THROUGH",
                                {"basis": appl_pos["implication_basis"]},
                            )
                        break  # only link to the primary implying co-accused
        else:
            add_edge(person_id, case_id, "ACCUSED_IN")

    for name in who.get("victims") or []:
        if _is_null(name):
            continue
        pid = get_person_node(name)
        if pid:
            add_edge(pid, case_id, "VICTIM_IN")

    # ── Prosecution and Defence party nodes (bail orders only) ────────────
    if bail_details:
        pros_id = add_node("party:prosecution", "Party", {"name": "Prosecution", "role": "state"})
        def_id  = add_node("party:defence",     "Party", {"name": "Defence",     "role": "accused_counsel"})
        if applicant_name and not _is_null(applicant_name):
            appl_id = get_person_node(applicant_name)
            if appl_id:
                add_edge(pros_id, appl_id, "ALLEGES")
                add_edge(def_id,  appl_id, "REPRESENTS")
        add_edge(pros_id, case_id, "PARTY_IN")
        add_edge(def_id,  case_id, "PARTY_IN")

    # ── Legal sections (offence sections only) ────────────────────────────
    for sec in sections:
        if sec and not _is_null(sec):
            sec_id = add_node(f"section:{_slug(sec)}", "Section", {"name": sec})
            add_edge(case_id, sec_id, "CHARGED_UNDER")

    # ── Property ──────────────────────────────────────────────────────────
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
        if _is_null(other):
            continue
        prop_index += 1
        pid = add_node(
            f"property:other:{prop_index}",
            "Property",
            {"kind": "other", "description": other},
        )
        add_edge(case_id, pid, "INVOLVES_PROPERTY")

    if prop.get("cash") and not _is_null(prop["cash"]):
        pid = add_node("property:cash:1", "Property", {"kind": "cash", "value": prop["cash"]})
        add_edge(case_id, pid, "INVOLVES_PROPERTY")

    if prop.get("gold") and not _is_null(prop["gold"]):
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
    if db is None:
        return

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

def analyze_evidence_with_context(
    session_id: str,
    file_path: str,
    doc_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full pipeline: extract → store → timeline → graph.

    Args:
        session_id: unique case identifier.
        file_path:  path to PDF / image file.
        doc_type:   optional type hint ("bail_order", "fir", "charge_sheet", "general").
                    When None, auto-detected by heuristic inside extract_facts.
    """
    raw_text = extract_text(file_path)
    facts = extract_facts(raw_text, doc_type)
    store_to_firestore(session_id, raw_text, facts)

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