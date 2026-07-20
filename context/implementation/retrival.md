# UPDATED PROMPT: Legal PDF to AI-Ready Dataset Extractor

## 🎯 PRIMARY OBJECTIVE

Build a production-ready Python project that extracts **ALL useful legal information** from Indian Supreme Court judgment PDFs and converts them into structured datasets ready for Machine Learning, LLM Fine-tuning, RAG, Knowledge Graphs, and Legal QA systems.

**CRITICAL: This is NOT a simple OCR or text extraction script. This is an INTELLIGENT LEGAL DOCUMENT UNDERSTANDING system.**

---

## 📋 INPUT REQUIREMENTS

### PDF Characteristics

- **Format**: Indian Supreme Court Judgments (reference: Vishaka case)

- **Structure**: Contains page numbers, headers, judgment text, numbered paragraphs, guidelines, citations

- **Quality**: Both digital and scanned PDFs (with OCR fallback)

- **Size**: Single or multiple PDFs

### Expected PDF Elements

- Case metadata (title, court, judges, date, petition number)

- Judgment text with paragraph numbering

- Legal citations

- Constitutional provisions (Articles)

- International conventions

- Guidelines/Orders

- Precedents cited

- Quotes and observations

- Final orders

---

## 📊 OUTPUT DATASETS (15 Required)

### Dataset 1: Complete Judgment Metadata

**Columns:**

- `case_id`: Unique identifier (e.g., "VISHAKA_1997")

- `case_title`: Full case name

- `petitioner`: List of petitioners

- `respondent`: List of respondents

- `court`: Full court name

- `bench`: Judges' names

- `judges`: Individual judge names with designations

- `judgment_date`: ISO format date (YYYY-MM-DD)

- `citation`: Official citation (e.g., "1997 Supp 3 SCR 404")

- `neutral_citation`: Neutral citation (e.g., "1997 INSC 1234") - **New field**

- `criminal_or_civil`: "criminal" or "civil"

- `jurisdiction`: "original", "appellate", or "review"

- `petition_number`: Full petition number

- `decision`: "Allowed", "Dismissed", "Disposed", etc.

- `acts_referred`: List of acts

- `articles_referred`: List of constitutional articles

- `sections_referred`: List of sections (if applicable)

- `keywords`: AI-generated keywords (10-15)

- `headnotes`: 2-3 sentence summary for legal databases

- `summary`: 150-word case summary

- `facts`: Facts of the case

- `issues`: Legal issues framed

- `arguments_petitioner`: Summary of petitioner's arguments

- `arguments_respondent`: Summary of respondent's arguments

- `observations`: Court's observations

- `reasoning`: Complete reasoning section

- `ratio_decidendi`: The binding legal principle

- `obiter_dicta`: Non-binding remarks

- `final_order`: Final order/relief

- `relief_granted`: Specific reliefs granted

- `important_quotes`: List of important quotes with metadata

- `international_conventions`: Conventions referred to

- `constitutional_provisions`: List of provisions used

- `precedents_cited`: List of cited cases with metadata

- `cases_referred`: Complete list of referred cases

- `legal_principles`: List of legal principles established

- `guidelines`: Structured guidelines (if applicable)

- `holding`: The court's holding

- `page_numbers`: Page range

- `source_pdf`: Original PDF filename

- `document_hash`: Unique document hash

- `extraction_confidence`: Confidence score (0-1)

- `extraction_timestamp`: Extraction timestamp

- `paragraph_count`: Total paragraphs extracted

- `word_count`: Total word count

- `has_guidelines`: Boolean

- `has_appendix`: Boolean

- `extraction_version`: Script version

---

### Dataset 2: Paragraph Dataset

**Columns:**

- `paragraph_id`: Unique ID

- `case_id`: Foreign key to Dataset 1

- `page_number`: Page number

- `paragraph_number`: Original paragraph number (if present)

- `heading`: Section heading (if any)

- `subheading`: Sub-section heading (if any)

- `paragraph_text`: Clean paragraph text

- `word_count`: Word count

- `character_count`: Character count

- `section_type`: One of: Introduction, Facts, Issues, Arguments_Petitioner, Arguments_Respondent, Reasoning, Observations, Judgment, Guidelines, Order, Citations, Conclusion, Procedure, Miscellaneous

- `is_numbered`: Boolean

- `is_list_item`: Boolean

- `list_type`: "numbered", "bullet", or None

- `indent_level`: Indentation level (for nested lists)

- `parent_heading`: Parent heading

- `has_citation`: Boolean

- `citation_count`: Number of citations

- `has_article`: Boolean

- `has_section`: Boolean

- `tokens`: Token count

---

### Dataset 3: Sentence Dataset

**Columns:**

- `sentence_id`: Unique ID

- `case_id`: Foreign key

- `page`: Page number

- `paragraph`: Paragraph ID

- `sentence`: Clean sentence text

- `speaker`: "Court", "Petitioner", "Respondent", "Quote", "Unknown"

- `importance_score`: AI-generated score (0-1)

- `contains_article`: Boolean

- `contains_section`: Boolean

- `contains_case_name`: Boolean

- `contains_act`: Boolean

- `contains_person`: Boolean

- `contains_date`: Boolean

- `contains_organization`: Boolean

- `contains_location`: Boolean

- `contains_quote`: Boolean

- `is_definition`: Boolean

- `is_legal_principle`: Boolean

- `sentiment`: "neutral", "positive", or "negative"

- `sentence_type`: "declarative", "interrogative", "imperative", "exclamatory"

- `token_count`: Number of tokens

- `dependency_parse`: Dependency parse tree (optional)

---

### Dataset 4: Legal Entity Dataset

**Columns:**

- `entity_id`: Unique ID

- `entity`: Entity text

- `entity_type`: One of: Person, Organization, Location, Date, Act, Article, Section, Citation, Court, Case_Name, Legal_Principle, Concept, Convention, Committee, Commission, Rule, Notification, Policy, Guideline, Term

- `page`: Page number

- `paragraph`: Paragraph ID

- `context`: Surrounding text (50 words)

- `confidence`: Confidence score

- `position_start`: Character start position

- `position_end`: Character end position

- `normalized_form`: Standardized form of entity

---

### Dataset 5: Case Citation Dataset

**Columns:**

- `citation_id`: Unique ID

- `case_id`: Foreign key

- `cited_case`: Full case name

- `short_name`: Short form citation

- `citation`: Full citation

- `court`: Court that decided the case

- `year`: Year of decision

- `why_cited`: Why this case was cited

- `paragraph`: Paragraph where cited

- `page`: Page number

- `is_precedent`: Boolean (whether binding precedent)

- `is_referred`: Boolean (whether merely referred)

- `is_distinguished`: Boolean (whether distinguished from current)

- `is_overruled`: Boolean (whether overruled)

- `legal_principle_extracted`: Key principle from cited case

- `relevance_score`: AI-generated relevance (0-1)

---

### Dataset 6: Constitution Dataset

**Columns:**

- `article_id`: Unique ID

- `case_id`: Foreign key

- `article_number`: Full article number (e.g., "14", "21")

- `article_title`: Title/description

- `full_text`: Complete text of article (if available)

- `summary`: Summary of the article

- `how_used`: How the court used this article

- `interpretation`: Court's interpretation

- `paragraph`: Paragraph where used

- `page`: Page number

- `is_fundamental_right`: Boolean

- `is_directive_principle`: Boolean

- `is_fundamental_duty`: Boolean

---

### Dataset 7: Acts and Sections Dataset

**Columns:**

- `act_section_id`: Unique ID

- `case_id`: Foreign key

- `act_name`: Full act name

- `act_short_name`: Short form

- `section`: Section number

- `subsection`: Subsection (if applicable)

- `clause`: Clause (if applicable)

- `purpose`: Why this section was referred

- `context`: How it was used/interpreted

- `page`: Page number

- `paragraph`: Paragraph

- `is_cited`: Boolean

- `is_interpreted`: Boolean

- `interpretation_given`: If interpreted, the interpretation

---

### Dataset 8: Guidelines Dataset

**Columns:**

- `guideline_id`: Unique ID

- `case_id`: Foreign key

- `guideline_number`: Number (1, 2, 3...)

- `title`: Guideline title

- `full_text`: Complete text of guideline

- `purpose`: Purpose of the guideline

- `sub_guidelines`: List of sub-guidelines

- `page_start`: Start page

- `page_end`: End page

- `applicability`: Who it applies to

- `implementation`: How to implement

- `is_binding`: Boolean

- `is_mandatory`: Boolean

- `effective_from`: Effective date (if specified)

---

### Dataset 9: Legal Principles Dataset

**Columns:**

- `principle_id`: Unique ID

- `case_id`: Foreign key

- `principle`: The legal principle

- `principle_type`: "Ratio Decidendi", "Obiter Dicta", "Observation", "Interpretation", "Rule"

- `source_text`: Exact text from judgment

- `page`: Page number

- `paragraph`: Paragraph

- `context`: Context

- `is_novel`: Whether new principle established

- `jurisprudential_value`: "Landmark", "Important", "Routine"

- `cited_by_count`: Number of times cited elsewhere (if known)

---

### Dataset 10: Important Quotes Dataset

**Columns:**

- `quote_id`: Unique ID

- `case_id`: Foreign key

- `quote`: The exact quote

- `speaker`: Who said it (e.g., "Verma CJ")

- `page`: Page number

- `paragraph`: Paragraph

- `significance`: Why it's important

- `topic`: Topic of the quote

- `is_latin_maxim`: Boolean

- `is_well_known`: Boolean

- `is_principle`: Boolean

---

### Dataset 11: Procedural Timeline Dataset

**Columns:**

- `event_id`: Unique ID

- `case_id`: Foreign key

- `date`: Event date (ISO format)

- `event_type`: "Filing", "Hearing", "Order", "Judgment", "Interim_Order", "Reference", "Other"

- `event_description`: Description of the event

- `page`: Page number

- `paragraph`: Paragraph

- `stage`: Stage of proceedings

---

### Dataset 12: Knowledge Graph Dataset (Triples)

**Columns:**

- `triple_id`: Unique ID

- `case_id`: Foreign key

- `subject`: Subject entity

- `subject_type`: Entity type

- `relation`: Relationship

- `object`: Object entity

- `object_type`: Entity type

- `page`: Page number

- `paragraph`: Paragraph

- `context`: Context of the relationship

- `confidence`: Confidence score

- `is_explicit`: Boolean (explicitly stated or inferred)

**Relation Types Examples:**

- `ESTABLISHED` (Court established guideline)

- `CITED` (Case cited precedent)

- `REFERRED_TO` (Article referred to)

- `INTERPRETED` (Court interpreted provision)

- `APPLIED` (Article applied to facts)

- `OVERULED` (Case overruled precedent)

- `FOLLOWED` (Case followed precedent)

- `DISTINGUISHED` (Case distinguished)

- `DEFINED` (Court defined term)

- `CREATED` (Court created rule)

---

### Dataset 13: Chunk Dataset (For RAG)

**Columns:**

- `chunk_id`: Unique ID

- `case_id`: Foreign key

- `chunk`: Semantic chunk of text

- `chunk_type`: "Introduction", "Facts", "Issues", "Reasoning", "Observations", "Guidelines", "Order", "Citation", "Conclusion"

- `page_start`: Starting page

- `page_end`: Ending page

- `embedding_ready`: Clean text for embedding

- `token_count`: Number of tokens

- `has_citations`: Boolean

- `has_articles`: Boolean

- `topic`: Main topic

- `keywords`: List of keywords

- `embedding`: Vector embedding (optional)

---

### Dataset 14: Training Dataset for LLM Fine-tuning

**Columns:**

- `train_id`: Unique ID

- `case_id`: Foreign key

- `instruction`: The task instruction

- `input`: The context/input

- `output`: The ground truth output

- `context`: Additional context

- `metadata`: JSON object with case info

- `difficulty`: "Easy", "Medium", "Hard"

- `topic`: Main topic

- `subtopic`: Subtopic

- `legal_domain`: "Constitutional Law", "Criminal Law", "Corporate Law", etc.

- `task_type`: "Summary", "QA", "Extraction", "Interpretation", "Application"

- `skill_type`: "Knowledge", "Reasoning", "Application", "Analysis"

**Example Rows:**

```json

{

  "instruction": "Explain why Article 21 was applied in the Vishaka case",

  "input": "The court held that sexual harassment violates fundamental rights...",

  "output": "Article 21 guarantees Right to Life and Liberty, which includes the right to live with dignity. The court held that workplace sexual harassment violates a woman's right to life with dignity, thereby triggering Article 21 protection.",

  "context": "Full judgment text",

  "metadata": {"case": "Vishaka v. State of Rajasthan", "page": 4, "year": 1997},

  "difficulty": "Medium",

  "topic": "Fundamental Rights",

  "subtopic": "Article 21 - Right to Life",

  "legal_domain": "Constitutional Law",

  "task_type": "Interpretation",

  "skill_type": "Reasoning"

}

```

---

### Dataset 15: Question Answer Dataset

**Columns:**

- `qa_id`: Unique ID

- `case_id`: Foreign key

- `question`: Question text

- `answer`: Answer text

- `supporting_paragraph`: Paragraph supporting answer

- `page`: Page number

- `difficulty`: "Easy", "Medium", "Hard"

- `type`: "Fact-based", "Reasoning", "Definition", "Application", "Comparison", "Article-based", "Section-based"

- `format`: "Short Answer", "Long Answer", "True/False", "MCQ", "Scenario Based"

- `topic`: Topic

- `has_options`: Boolean (for MCQ)

- `options`: List of options (if MCQ)

**Question Types Examples:**

1. Fact-based: "Who were the petitioners in Vishaka case?"

2. Reasoning: "Why did the court rely on international conventions?"

3. Definition: "Define sexual harassment as per the Vishaka guidelines."

4. Application: "How would the Vishaka guidelines apply to a private company?"

5. Article-based: "Which constitutional articles were invoked in Vishaka?"

6. True/False: "The Vishaka guidelines are binding until legislation is enacted."

7. MCQ: "Which article guarantees right to life with dignity?"

---

## 🛠️ TECHNICAL REQUIREMENTS

### OCR & Text Extraction

```python

# Must handle:

- Digital PDFs → Direct text extraction

- Scanned PDFs → OCR with Tesseract/Google Vision

- Mixed PDFs → Hybrid approach

- Multi-column layouts → Column detection

- Tables → Table structure extraction

- Encrypted PDFs → Decryption handling

- Corrupted PDFs → Error recovery

- Rotated pages → Rotation detection

- Image-only pages → Full-page OCR

```

### Text Cleaning

```python

# Must clean:

- Page numbers (multiple formats)

- Headers and footers

- Repeated titles

- OCR artifacts

- Random spaces

- Broken words

- Hyphenated line breaks

- Multiple blank lines

- Invisible characters

- Unicode normalization

- PDF encoding issues

- Watermarks (ignore)

```

### Intelligent Parsing

```python

# Must detect:

- Headings (various levels)

- Subheadings

- Numbered paragraphs

- Numbered lists (1., 2., 3.)

- Bullet points

- Tables

- Case citations (format detection)

- Constitution articles (Article X)

- Sections (Section X of Act Y)

- Judges and designations

- Bench composition

- Dates (multiple formats)

- Footnotes

- Appendix

- Schedules

- Guidelines

- Orders

- Quotes (with attribution)

```

### NLP Requirements

```python

Required:

- Sentence Segmentation (NLTK/spaCy)

- Named Entity Recognition (NER)

- Part-of-Speech (POS) tagging

- Dependency Parsing

- Coreference Resolution

- Topic Detection

- Keyword Extraction (RAKE/KeyBERT)

- Legal Entity Recognition

- Summarization (Extractive/Abstractive)

- Duplicate Removal

- Paragraph Clustering

- Semantic Segmentation

- Citation Extraction

- Quote Attribution

```

### Legal-Specific Processing

```python

# Must handle:

- Indian legal citation formats

- Supreme Court judgment structure

- Constitutional article references

- Act and section references

- International conventions (CEDAW, UN, etc.)

- Legal Latin maxims

- Standard legal phrases

- Court-specific formatting

```

---

## 📁 PROJECT STRUCTURE

```

legal_pdf_extractor/

├── __init__.py

├── config.py                     # All configurations

├── main.py                       # Entry point / CLI

├── requirements.txt

├── README.md

├── .env.example

├── .gitignore

│

├── core/

│   ├── __init__.py

│   ├── extractor.py              # Main extraction orchestrator

│   ├── ocr_engine.py             # OCR handling

│   ├── text_cleaner.py           # Text cleaning

│   ├── paragraph_parser.py       # Paragraph detection

│   ├── entity_extractor.py       # NER and entity extraction

│   ├── citation_extractor.py     # Citation detection

│   ├── constitution_extractor.py # Article extraction

│   ├── guideline_extractor.py    # Guidelines extraction

│   ├── section_classifier.py     # Section classification

│   └── dataset_builder.py        # Dataset construction

│

├── nlp/

│   ├── __init__.py

│   ├── sentence_segmenter.py

│   ├── summarizer.py

│   ├── keyword_extractor.py

│   ├── entity_recognizer.py

│   ├── legal_ner.py              # Custom legal NER

│   ├── relation_extractor.py

│   └── preprocessor.py

│

├── models/

│   ├── __init__.py

│   ├── legal_ner_model.py        # Fine-tuned NER

│   ├── citation_model.py

│   └── section_classifier.py

│

├── utils/

│   ├── __init__.py

│   ├── file_utils.py

│   ├── pdf_utils.py

│   ├── text_utils.py

│   ├── date_utils.py

│   ├── logging_utils.py

│   ├── progress_utils.py

│   ├── checkpoint_utils.py

│   └── validation_utils.py

│

├── outputs/

│   ├── csv/

│   ├── json/

│   ├── jsonl/

│   └── parquet/

│

├── logs/

│   └── extraction.log

│

├── checkpoints/

│   └── checkpoint.pkl

│

├── tests/

│   ├── __init__.py

│   ├── test_extractor.py

│   ├── test_cleaner.py

│   ├── test_parser.py

│   └── test_entities.py

│

└── scripts/

    ├── batch_extract.py

    ├── validate_output.py

    └── generate_summary.py

```

---

## 🚀 PERFORMANCE REQUIREMENTS

### Scalability

- Support processing **thousands** of PDFs

- **Multiprocessing** for parallel extraction

- **Batch processing** capabilities

- **Chunking** for large documents

- **Memory optimization**

### Reliability

- **Checkpointing** - Resume after interruption

- **Progress bar** (tqdm)

- **Comprehensive logging**

- **Error recovery** for problematic PDFs

- **Validation** of extracted data

- **Fallback strategies** for extraction failures

### Configurability

```python

# config.py

CONFIG = {

    # PDF Processing

    "OCR_ENGINE": "tesseract",  # or "google_vision"

    "OCR_LANGUAGE": "eng",

    "MAX_PAGES": None,  # None for all

    "DETECT_TABLES": True,

    

    # Extraction

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

    "CHECKPOINT_INTERVAL": 10,  # every 10 documents

    

    # Logging

    "LOG_LEVEL": "INFO",

    "LOG_FILE": "logs/extraction.log",

    

    # Performance

    "USE_MULTIPROCESSING": True,

    "MAX_WORKERS": 4,

    "BATCH_SIZE": 10,

    

    # Validation

    "VALIDATE_OUTPUT": True,

    "STRICT_MODE": False,

}

```

---

## 🔧 IMPLEMENTATION DETAILS

### Library Justification

```python

Required Libraries:

1. PyPDF2/PDFPlumber - PDF text extraction (digital)

2. PyTesseract - OCR (scanned PDFs)

3. OpenCV - Image preprocessing for OCR

4. spaCy - NLP (NER, POS, Dependency)

5. NLTK - Sentence segmentation, tokenization

6. Transformers - BERT-based models for summarization

7. KeyBERT - Keyword extraction

8. Rake-NLTK - Alternative keyword extraction

9. Pandas - Dataset manipulation

10. PyArrow - Parquet support

11. tqdm - Progress bars

12. Loguru - Structured logging

13. Pydantic - Data validation

14. Dataclasses - Structured data

15. Multiprocessing - Parallel processing

```

### Error Handling Strategy

```python

# For each extraction step, implement:

1. Try primary method

2. Catch specific exceptions

3. Log error with context

4. Use fallback method

5. If all fail, log and continue

6. Update checkpoint for resume capability

```

### Validation Pipeline

```python

# After extraction, validate:

1. Required fields are present

2. Data types are correct

3. Date formats are ISO standard

4. Citations follow Indian format

5. Entity extraction confidence > threshold

6. No empty required fields

7. Page numbers are sequential

8. No duplicate entries

```

---

## ✅ SUCCESS CRITERIA

### For the Code:

1. **Production-ready** - Clean, documented, tested

2. **Type-hinted** - All functions have type hints

3. **Modular** - Each component is independent

4. **Configurable** - Behavior controlled by config

5. **Performant** - Handles 1000+ PDFs

6. **Reliable** - Checkpoints and error recovery

7. **Testable** - Unit tests for all components

8. **Documented** - README and docstrings

### For the Output:

1. All 15 datasets generated

2. No manual cleaning required

3. Ready for ML/LLM/RAG pipelines

4. Structurally consistent across documents

5. Entity extraction with >90% accuracy

6. Citation extraction >95% accuracy

7. Paragraph classification >85% accuracy

8. Semantic chunks properly segmented

---

## 📝 FINAL CHECKLIST

Before delivery, ensure:

- [ ] Complete project structure

- [ ] All 15 dataset generators implemented

- [ ] OCR for scanned PDFs working

- [ ] Text cleaning properly removes artifacts

- [ ] Paragraph detection handles all formats

- [ ] Legal entity extraction (NER) working

- [ ] Citation extraction complete

- [ ] Constitution article extraction complete

- [ ] Guideline extraction complete

- [ ] LLM training dataset generation working

- [ ] QA dataset generation complete

- [ ] Knowledge graph triples extraction

- [ ] Performance optimization (multiprocessing)

- [ ] Checkpoint and resume functionality

- [ ] Comprehensive logging

- [ ] Unit tests for core functions

- [ ] README with usage examples

- [ ] Sample output for the Vishaka case

- [ ] Validation against expected output

---

## 🎯 FINAL OUTPUT EXPECTATION

Provide a **complete Python project** that when run on the Vishaka PDF, produces:

1. 15 clean datasets (CSV, JSON, JSONL, Parquet)

2. No manual cleaning required

3. Ready for immediate use in:

   - ML training

   - LLM fine-tuning

   - RAG systems

   - Legal search engines

   - Knowledge graphs

**The extracted data should be so clean and structured that it can directly feed into any AI/ML pipeline without additional preprocessing.**