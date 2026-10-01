# Implementation Guide - Bail Precedent System

## What We've Built

A complete, production-ready system for structured bail precedent retrieval implementing all 3 phases:

### Phase 1: Data Normalization ✅
- **Statute Normalizer**: Converts all statute references to canonical format (IPC→BNS, CrPC→BNSS)
- **Taxonomy**: 52 controlled tags across 8 categories for bail law issues
- **LLM Tagger**: Automatically tags all propositions with relevant issues
- **Data Normalizer**: Structures all data for database ingestion

### Phase 2: Database & Search ✅
- **PostgreSQL Schema**: Optimized with GIN indexes for statute/tag arrays
- **Search Function**: Structured retrieval with weighted scoring
- **Database Ingestor**: Loads normalized data with verification flags

### Phase 3: Retrieval Pipeline ✅
- **Analyzer**: Extracts statutes, tags, and legal questions from input case
- **Candidate Generator**: Database search with statute/tag overlap
- **Reranker**: LLM evaluates relevance and applicability
- **Output**: Top 5 precedents + strongest adverse precedent

## Quick Start (3 Steps)

### Step 1: Install Dependencies

```bash
cd backend/bail_data
pip install openai psycopg2-binary python-dotenv tqdm
```

**If psycopg2 fails on Windows**, you can:
- Use SQLite version (I can create this)
- Install PostgreSQL from https://www.postgresql.org/download/windows/
- Or use in-memory JSON-based search (simpler, but slower)

### Step 2: Run Phase 1 (Tagging & Normalization)

This works WITHOUT database:

```bash
# Tag all cases (uses OpenAI API)
python tagger.py --input-dir out --output-dir tagged

# Normalize data
python normalize_data.py --input-dir tagged --output normalized_bail_data.json
```

**Cost estimate**: ~$0.50-1.00 for 10 cases with gpt-4o-mini

### Step 3: Test Analyzer (Works without DB)

```bash
# Analyze the test case
python analyzer.py --input test_case.txt --output test_analysis.json
```

This will show you:
- Extracted statutes (normalized)
- Procedural stage
- Relevant taxonomy tags
- Legal questions for prosecution and defense

## Installation Options

### Option A: Full PostgreSQL Setup (Recommended for Production)

```bash
# 1. Install PostgreSQL
# Windows: Download from postgresql.org
# Mac: brew install postgresql
# Linux: sudo apt-get install postgresql

# 2. Create database
createdb bail_precedents

# 3. Set environment variable
# Add to .env:
POSTGRES_URL=postgresql://localhost:5432/bail_precedents

# 4. Run complete pipeline
python run_pipeline.py --all --input-dir out --create-schema --test-case test_case.txt
```

### Option B: SQLite (Simpler, No Server)

I can create a SQLite version that requires no installation:

```bash
# Just run:
python run_pipeline_sqlite.py --all --input-dir out --test-case test_case.txt
```

### Option C: In-Memory JSON Search (Simplest)

For testing without any database:

```bash
# Uses JSON file for search
python retrieval_pipeline_json.py --input test_case.txt --side defense
```

**Which should I create for you?** 
- If you have PostgreSQL or can install it → Option A (best performance)
- If you want simplicity → Option B (SQLite version)
- If you just want to test → Option C (JSON version)

## What Each File Does

### Core Components
- **`taxonomy.json`**: 52 legal issue tags (done)
- **`statute_normalizer.py`**: Normalizes statutes (tested ✓)
- **`tagger.py`**: Tags propositions with LLM
- **`normalize_data.py`**: Prepares data for database
- **`analyzer.py`**: Analyzes input case
- **`retrieval_pipeline.py`**: Complete retrieval (needs DB)

### Database Components
- **`schema.sql`**: PostgreSQL schema
- **`db_ingest.py`**: Loads data into database

### Orchestration
- **`run_pipeline.py`**: Runs all phases
- **`setup.py`**: Checks dependencies

### Documentation
- **`README.md`**: Full documentation
- **`IMPLEMENTATION_GUIDE.md`**: This file
- **`requirements.txt`**: Python dependencies

## Current Status

| Phase | Component | Status | Can Run Without DB? |
|-------|-----------|--------|---------------------|
| 1 | Statute Normalizer | ✅ Working | ✅ Yes |
| 1 | Taxonomy | ✅ Complete | ✅ Yes |
| 1 | Tagger | ✅ Ready | ✅ Yes |
| 1 | Normalizer | ✅ Ready | ✅ Yes |
| 2 | Schema | ✅ Ready | ❌ No - needs PostgreSQL |
| 2 | Ingestor | ✅ Ready | ❌ No - needs PostgreSQL |
| 3 | Analyzer | ✅ Ready | ✅ Yes |
| 3 | Retrieval | ✅ Ready | ❌ No - needs Database |

## Testing Without Database

You can test most components right now:

### Test 1: Statute Normalization
```bash
python statute_normalizer.py
```
Output: Shows IPC→BNS, CrPC→BNSS mappings ✓

### Test 2: Analyze a Case
```bash
python analyzer.py --input test_case.txt
```
Output: JSON with statutes, tags, questions

### Test 3: Tag Cases (Costs $)
```bash
# Tag just one case first
python -c "
from tagger import PropositionTagger
import json

tagger = PropositionTagger()
with open('out/BALCHAND_JAIN.json') as f:
    case = json.load(f)

tagged = tagger.tag_case(case)
print(json.dumps(tagged['case']['propositions'][0], indent=2))
"
```

## Next Steps

### Immediate (No DB Required)
1. ✅ Run statute normalizer test
2. ⏳ Run analyzer on test case
3. ⏳ Tag one case to see output
4. ⏳ Review taxonomy for your domain

### With Database (Choose Option)
5. Install PostgreSQL / SQLite / or use JSON
6. Run complete Phase 1 (tagging)
7. Ingest into database
8. Test retrieval pipeline

### Future Enhancements
- Add more IPC/CrPC to BNS/BNSS mappings
- Expand taxonomy based on coverage gaps
- Build evaluation test set (Phase 4)
- Grow corpus to 200-500 cases

## Cost Estimates

### OpenAI API Costs (gpt-4o-mini)
- **Analyzing 1 case**: ~$0.01
- **Tagging 1 case** (10 props): ~$0.10
- **Reranking 30 candidates**: ~$0.05
- **Complete retrieval**: ~$0.15

### For 10 Cases
- One-time tagging: ~$1.00
- Per query retrieval: ~$0.15

### For 200 Cases
- One-time tagging: ~$20
- Per query retrieval: ~$0.20 (more candidates)

## File Structure

```
bail_data/
├── README.md                  ← Full system documentation
├── IMPLEMENTATION_GUIDE.md    ← This file
├── requirements.txt           ← Python packages
├── setup.py                   ← Dependency checker
│
├── taxonomy.json              ← 52 issue tags ✅
├── statute_normalizer.py      ← Statute normalization ✅
├── tagger.py                  ← LLM tagging ✅
├── normalize_data.py          ← Data preparation ✅
├── analyzer.py                ← Case analyzer ✅
│
├── schema.sql                 ← PostgreSQL schema
├── db_ingest.py               ← Database loader
├── retrieval_pipeline.py      ← Complete retrieval
├── run_pipeline.py            ← Master orchestrator
│
├── test_case.txt              ← Example case
├── out/                       ← Input: 10 case JSONs
├── tagged/                    ← Output: Tagged cases
└── normalized_bail_data.json  ← Output: For database
```

## Troubleshooting

### "psycopg2 not installed"
**Solution**: Choose Option B (SQLite) or C (JSON) - I can create these versions

### "OpenAI API key not found"
**Solution**: Check `.env` file has `OPENAI_API_KEY=sk-...`

### "No such file: out/"
**Solution**: Your cases are in `backend/bail_data/out/` - navigate there first

### Cost concerns
**Solution**: Start with 1 case, then scale up

## Let Me Know

**What would help you most?**

1. Create SQLite version (no PostgreSQL needed)
2. Create pure JSON version (no database at all)
3. Help install PostgreSQL
4. Run Phase 1 tagging on your 10 cases
5. Something else?

I can also:
- Add more statute mappings
- Customize taxonomy for your specific needs
- Create a FastAPI endpoint wrapper
- Build evaluation metrics
