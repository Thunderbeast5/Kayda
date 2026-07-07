"""
Sprint 3: Evidence Analyzer
Extracts text from PDFs/images -> chunks -> LLM fact extraction -> Firestore + Pinecone.
"""

import os
import json
import re
from pathlib import Path

from openai import images

import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, firestore

from llm_config import get_llm

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "legal-embeddings"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


# --------------------------------------------------------------------
# Firebase init (lazy, only once per process)
# --------------------------------------------------------------------
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


# --------------------------------------------------------------------
# Step 1: Text extraction (OCR / PDF)
# --------------------------------------------------------------------
def extract_text(file_path: str) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        reader = PdfReader(str(path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        text = text.strip()

        if text:  # real text layer found
            return text

        # Fallback: no text layer -> OCR each page as an image
        from pdf2image import convert_from_path
        images = convert_from_path(str(path), dpi=300)
        ocr_text = ""
        for img in images:
            ocr_text += pytesseract.image_to_string(img, config="--psm 6") + "\n"
        return ocr_text.strip()

    elif ext in IMAGE_EXTENSIONS:
        image = Image.open(path)
        return pytesseract.image_to_string(image).strip()

    else:
        raise ValueError(f"Unsupported file type: {ext}")


# --------------------------------------------------------------------
# Step 2: Chunking
# --------------------------------------------------------------------
def chunk_text(raw_text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    return splitter.split_text(raw_text)


# --------------------------------------------------------------------
# Step 3: LLM fact extraction
# --------------------------------------------------------------------
FACT_EXTRACTION_PROMPT = """You are a legal document analyst. Extract facts from the text below.

Return ONLY valid JSON, no markdown fences, no preamble, matching exactly this schema:
{{
  "who": {{"accused": "string or null", "victims": ["string"]}},
  "what": "string describing the crime, or null if not present",
  "when": "date/time string or null",
  "where": "location string or null",
  "amount": "monetary value string or null",
  "sections_cited": ["list of IPC/Act sections mentioned, e.g. 'IPC 147', 'IPC 307'"]
}}

If a field is not mentioned in the text, use null (or empty list for victims/sections_cited).

TEXT:
{text}
"""


def _strip_json_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def extract_facts(raw_text: str) -> dict:
    llm = get_llm(temperature=0)
    chunks = chunk_text(raw_text)

    merged = {
        "who": {"accused": None, "victims": []},
        "what": None,
        "when": None,
        "where": None,
        "amount": None,
        "sections_cited": [],
    }

    for chunk in chunks:
        prompt = FACT_EXTRACTION_PROMPT.format(text=chunk)
        response = llm.invoke(prompt)
        cleaned = _strip_json_fences(response.content)

        try:
            facts = json.loads(cleaned)
        except json.JSONDecodeError:
            print("Warning: could not parse LLM output:")
            print(cleaned)
            continue

        # Merge sections
        for s in facts.get("sections_cited", []):
            if s not in merged["sections_cited"]:
                merged["sections_cited"].append(s)

        # Merge accused
        if facts.get("who", {}).get("accused") and not merged["who"]["accused"]:
            merged["who"]["accused"] = facts["who"]["accused"]

        # Merge victims
        for v in facts.get("who", {}).get("victims", []):
            if v not in merged["who"]["victims"]:
                merged["who"]["victims"].append(v)

        # Merge remaining fields
        for field in ["what", "when", "where", "amount"]:
            if facts.get(field) and not merged[field]:
                merged[field] = facts[field]

    return merged


# --------------------------------------------------------------------
# Step 4: Store to Firestore
# --------------------------------------------------------------------
def store_to_firestore(session_id: str, raw_text: str, facts: dict) -> str:
    db = _get_firestore_client()
    doc_ref = db.collection("document_store").document(session_id)

    doc_ref.set({
        "session_id": session_id,
        "raw_text": raw_text,
        "facts": facts,
    })
    return doc_ref.id


# --------------------------------------------------------------------
# Step 5: Embed + store to Pinecone (same model as Sprint 1 ingestion)
# --------------------------------------------------------------------
def store_to_pinecone(session_id: str, facts: dict):
    if not PINECONE_API_KEY:
        print("Skipping Pinecone: PINECONE_API_KEY not set")
        return

    from sentence_transformers import SentenceTransformer
    from pinecone import Pinecone

    text_for_embedding = facts.get("what") or ""
    if not text_for_embedding:
        print("Skipping Pinecone: no 'what' field to embed")
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
            "what": text_for_embedding,
            "where": facts.get("where") or "",
        },
    }])


# --------------------------------------------------------------------
# Orchestrator entry point
# --------------------------------------------------------------------
def analyze_evidence(session_id: str, file_path: str) -> dict:
    raw_text = extract_text(file_path)
    facts = extract_facts(raw_text)
    store_to_firestore(session_id, raw_text, facts)
    store_to_pinecone(session_id, facts)
    return facts


if __name__ == "__main__":
    test_file = "test_fir.pdf"
    if Path(test_file).exists():
        result = analyze_evidence("test-session-001", test_file)
        print(json.dumps(result, indent=2))
    else:
        print(f"No test file at {test_file} — add one to test, or call analyze_evidence() directly.")