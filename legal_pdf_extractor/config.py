"""
config.py — Central configuration for Legal PDF Extractor
"""

CONFIG = {
    # PDF Processing
    "OCR_ENGINE": "tesseract",       # "tesseract" or "google_vision"
    "OCR_LANGUAGE": "eng",
    "MAX_PAGES": None,               # None = all pages
    "DETECT_TABLES": True,
    "DPI": 300,                      # DPI for image rendering

    # Extraction toggles
    "EXTRACT_CITATIONS": True,
    "EXTRACT_ARTICLES": True,
    "EXTRACT_GUIDELINES": True,
    "EXTRACT_QUOTES": True,
    "MIN_PARAGRAPH_LENGTH": 20,

    # NLP
    "USE_SPACY": True,
    "USE_NLTK": True,
    "NER_MODEL": "en_core_web_lg",
    "SUMMARIZATION_MODEL": "facebook/bart-large-cnn",
    "KEYWORD_MODEL": "keybert",

    # Output
    "OUTPUT_FORMATS": ["csv", "json", "jsonl", "parquet"],
    "OUTPUT_DIR": "outputs/",
    "SAVE_CHECKPOINTS": True,
    "CHECKPOINT_INTERVAL": 10,

    # Logging
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "logs/extraction.log",

    # Performance
    "USE_MULTIPROCESSING": False,    # Set True for batch processing
    "MAX_WORKERS": 4,
    "BATCH_SIZE": 10,

    # Validation
    "VALIDATE_OUTPUT": True,
    "STRICT_MODE": False,

    # Version
    "EXTRACTION_VERSION": "1.0.0",
}

# Indian legal citation patterns
CITATION_PATTERNS = [
    r'\(\d{4}\)\s+\d+\s+SCC\s+\d+',
    r'AIR\s+\d{4}\s+SC\s+\d+',
    r'\d{4}\s+\(\d+\)\s+SCR\s+\d+',
    r'\d{4}\s+Supp\s+\(\d+\)\s+SCR\s+\d+',
    r'JT\s+\d{4}\s+\(\d+\)\s+SC\s+\d+',
    r'\d{4}\s+INSC\s+\d+',
    r'Writ\s+Petition\s+\(Civil\)\s+No\.\s*\d+\s+of\s+\d{4}',
    r'Criminal\s+Appeal\s+No\.\s*\d+\s+of\s+\d{4}',
]

ARTICLE_PATTERNS = [
    r'Article[s]?\s+(\d+[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)',
    r'Art\.\s*(\d+[A-Z]?)',
]

SECTION_PATTERNS = [
    r'[Ss]ection[s]?\s+(\d+[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)\s+of\s+([\w\s]+Act[\w\s,]*\d{4})',
    r'[Ss]\.\s*(\d+[A-Z]?)\s+of\s+([\w\s]+Act[\w\s,]*\d{4})',
]

JUDGE_DESIGNATIONS = [
    "C.J.I.", "CJI", "J.", "J.J.", "C.J.", "CJ",
    "Chief Justice", "Justice", "Honourable", "Hon'ble"
]

SECTION_TYPE_KEYWORDS = {
    "Introduction":   ["in the matter of", "writ petition", "special leave", "this petition", "the present"],
    "Facts":          ["facts", "background", "the appellant", "the petitioner", "the respondent", "incident", "fir", "complaint"],
    "Issues":         ["issue", "question", "whether", "point for determination", "the question", "to be decided"],
    "Arguments_Petitioner": ["petitioner submits", "petitioner contends", "learned counsel for the petitioner", "mr.", "ms.", "shri"],
    "Arguments_Respondent": ["respondent submits", "respondent contends", "counsel for respondent", "state submits"],
    "Reasoning":      ["we are of the view", "in our opinion", "it is well settled", "this court held", "we hold"],
    "Observations":   ["observed", "it is observed", "the court observed", "we observe", "bench observed"],
    "Guidelines":     ["guideline", "direction", "directed", "shall ensure", "employer shall", "committee shall"],
    "Order":          ["accordingly", "the appeal is", "petition is", "disposed of", "dismissed", "allowed", "ordered"],
    "Citations":      ["reported in", "cited in", "v.", "versus", "state of", "union of india"],
    "Conclusion":     ["in conclusion", "to conclude", "finally", "for the reasons", "in the result"],
}
