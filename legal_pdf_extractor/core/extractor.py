"""
extractor.py — Main orchestrator: coordinates all extraction steps
"""
import os, sys, re, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFIG
from utils.logging_utils import get_logger
from utils.file_utils import compute_hash, save_checkpoint, load_checkpoint, ensure_dirs
from core.ocr_engine import extract_pages
from core.text_cleaner import clean_all_pages, merge_pages_to_text
from core.paragraph_parser import split_into_paragraphs
from core.citation_extractor import extract_citations
from core.constitution_extractor import extract_articles
from core.guideline_extractor import extract_guidelines
from core.entity_extractor import extract_entities
from core.section_classifier import extract_acts_sections
from core.dataset_builder import (
    build_metadata, build_guidelines, build_principles,
    build_quotes, build_timeline, build_kg_triples,
    build_rag_chunks, build_training_data, build_qa_dataset
)
from nlp.sentence_segmenter import extract_sentences

logger = get_logger("extractor", CONFIG["LOG_FILE"], CONFIG["LOG_LEVEL"])


def extract_pdf(pdf_path: str, config: dict = None) -> dict:
    """
    Full pipeline for one PDF.
    Returns dict of all 15 datasets.
    """
    cfg = config or CONFIG
    doc_hash = compute_hash(pdf_path)
    case_id = _make_case_id(pdf_path)

    logger.info(f"═══ Processing: {os.path.basename(pdf_path)} (case_id={case_id})")

    # Step 1: Extract pages
    pages = extract_pages(pdf_path,
                          max_pages=cfg.get("MAX_PAGES"),
                          lang=cfg.get("OCR_LANGUAGE", "eng"),
                          dpi=cfg.get("DPI", 300))

    # Step 2: Clean
    pages = clean_all_pages(pages)
    full_text = merge_pages_to_text(pages)
    logger.info(f"  Text length: {len(full_text)} chars")

    # Step 3: Paragraph parsing
    paragraphs = split_into_paragraphs(pages)
    logger.info(f"  Paragraphs: {len(paragraphs)}")

    # Step 4: Specialized extraction
    citations   = extract_citations(paragraphs, case_id)   if cfg.get("EXTRACT_CITATIONS") else []
    articles    = extract_articles(paragraphs, case_id)    if cfg.get("EXTRACT_ARTICLES") else []
    guidelines  = extract_guidelines(paragraphs, case_id)  if cfg.get("EXTRACT_GUIDELINES") else []
    acts_secs   = extract_acts_sections(paragraphs, case_id)
    entities    = extract_entities(paragraphs, case_id, use_spacy=cfg.get("USE_SPACY", True))
    sentences   = extract_sentences(paragraphs, case_id)

    logger.info(f"  Citations:{len(citations)} Articles:{len(articles)} "
                f"Guidelines:{len(guidelines)} Entities:{len(entities)}")

    # Step 5: Build all 15 datasets
    metadata   = build_metadata(full_text, pages, paragraphs, citations, articles,
                                 guidelines, acts_secs, pdf_path, doc_hash, case_id, cfg)
    principles = build_principles(paragraphs, case_id)
    quotes     = build_quotes(paragraphs, case_id)
    timeline   = build_timeline(paragraphs, case_id)
    kg_triples = build_kg_triples(paragraphs, citations, articles, guidelines,
                                   case_id, metadata.get("case_title", case_id))
    rag_chunks = build_rag_chunks(paragraphs, case_id)
    train_data = build_training_data(paragraphs, metadata, citations, articles, case_id)
    qa_data    = build_qa_dataset(paragraphs, metadata, citations, articles, guidelines, case_id)

    result = {
        "dataset_01_metadata":   [metadata],
        "dataset_02_paragraphs": paragraphs,
        "dataset_03_sentences":  sentences,
        "dataset_04_entities":   entities,
        "dataset_05_citations":  citations,
        "dataset_06_articles":   articles,
        "dataset_07_acts":       acts_secs,
        "dataset_08_guidelines": guidelines,
        "dataset_09_principles": principles,
        "dataset_10_quotes":     quotes,
        "dataset_11_timeline":   timeline,
        "dataset_12_kg_triples": kg_triples,
        "dataset_13_rag_chunks": rag_chunks,
        "dataset_14_training":   train_data,
        "dataset_15_qa":         qa_data,
    }

    logger.info(f"  ✓ All 15 datasets built for {case_id}")
    _log_counts(result)
    return result


def _make_case_id(pdf_path: str) -> str:
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    clean = re.sub(r'[^A-Za-z0-9_]', '_', name).upper()
    year_m = re.search(r'\d{4}', clean)
    year = year_m.group() if year_m else str(datetime.datetime.now().year)
    return f"{clean[:20]}_{year}"


def _log_counts(result: dict):
    for key, val in result.items():
        logger.info(f"    {key}: {len(val)} records")
