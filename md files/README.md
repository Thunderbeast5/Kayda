# Legal PDF Extractor — 15 Dataset Generator

Extracts ALL legal information from Indian Supreme Court judgment PDFs into 15 structured datasets ready for ML, LLM fine-tuning, RAG, and Knowledge Graphs.

## Setup

```cmd
cd legal_pdf_extractor
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

For Tesseract OCR (scanned PDFs):
- Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
- Add to PATH after install

## Usage

### Single PDF
```cmd
python main.py path/to/judgment.pdf
```

### Specific output formats
```cmd
python main.py path/to/judgment.pdf --formats csv json jsonl
```

### Batch process a folder
```cmd
python main.py data/fir/ --batch --output outputs/
```

### Process the FIR PDFs in this project
```cmd
python main.py ../data/fir/0083\ Publish\ FIR.pdf
```

## Output

15 datasets saved in `outputs/` (CSV, JSON, JSONL, Parquet):

| # | Dataset | Description |
|---|---------|-------------|
| 01 | metadata | Case metadata, summary, ratio, final order |
| 02 | paragraphs | All paragraphs with section classification |
| 03 | sentences | All sentences with NLP annotations |
| 04 | entities | Named entities (Person, Act, Article, Court...) |
| 05 | citations | All cited cases with context |
| 06 | articles | Constitutional articles invoked |
| 07 | acts | Acts and sections referenced |
| 08 | guidelines | Structured guidelines/directions |
| 09 | principles | Legal principles (ratio, obiter) |
| 10 | quotes | Important quotes with attribution |
| 11 | timeline | Procedural event timeline |
| 12 | kg_triples | Knowledge graph triples (subject-relation-object) |
| 13 | rag_chunks | Semantic chunks for RAG/embedding |
| 14 | training | LLM fine-tuning data (instruction-input-output) |
| 15 | qa | Question-answer pairs for legal QA models |

## Configuration

Edit `config.py` to control:
- OCR engine (tesseract / google_vision)
- Which datasets to extract
- Output formats
- NLP models
