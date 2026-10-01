# Bail Precedent Retrieval System

A comprehensive system for structured retrieval of Indian bail law precedents, implementing the phases described in the architectural plan.

## Overview

This system replaces embedding-based retrieval with structured, explainable precedent search using:
- **Normalized statutes** (IPC/CrPC → BNS/BNSS mappings)
- **Controlled taxonomy** of 52 bail law issues
- **Structured database** with PostgreSQL
- **LLM-powered** analysis, tagging, and reranking
- **Verification flags** for quote accuracy

## Architecture

```
Input Case
    ↓
[Analyzer] ← Extracts statutes, tags, questions
    ↓
[Database Search] ← Finds candidates by statute/tag overlap
    ↓
[Reranker] ← LLM evaluates relevance and applicability
    ↓
[Verifier] ← Checks quote accuracy (already in DB)
    ↓
Top 5 Precedents + Adverse Precedent
```

## Components

### Phase 1: Data Preparation

#### 1. `taxonomy.json`
- 52 controlled tags across 8 categories
- Categories: procedural, offense_characteristics, evidence_strength, accused_profile, victim_complainant, special_statutes, constitutional, punishment_proportionality

#### 2. `statute_normalizer.py`
- Normalizes statute references to canonical format (e.g., `CrPC-1973:438`)
- Maps IPC → BNS, CrPC → BNSS
- Handles variations: "Section 438 CrPC", "CrPC Section 438", etc.

```python
from statute_normalizer import StatuteNormalizer

normalizer = StatuteNormalizer()
normalized = normalizer.normalize_statute("CrPC 1973", "438")
# Returns: "CrPC-1973:438"

bns_equiv = normalizer.get_bns_equivalent("420")
# Returns: "BNS-2023:318"
```

#### 3. `tagger.py`
- LLM-based proposition tagging
- Tags each proposition with 1-3 taxonomy tags
- Adds `binding_level` (binding/persuasive/reference)
- Extracts `authorities` cited

```bash
# Tag all cases
python tagger.py --input-dir out --output-dir tagged --model gpt-4o-mini
```

#### 4. `normalize_data.py`
- Applies statute normalization
- Extracts structured records for database
- Produces `normalized_bail_data.json`

```bash
python normalize_data.py --input-dir tagged --output normalized_bail_data.json
```

### Phase 2: Database & Storage

#### 5. `schema.sql`
- PostgreSQL schema with two main tables:
  - `bail_cases`: Case-level metadata
  - `bail_propositions`: Proposition-level data with tags, statutes
- Indexes on statutes (GIN), tags (GIN), dates, courts
- `search_propositions()` function for structured retrieval
- Views: `verified_holdings`, `high_quality_propositions`

#### 6. `db_ingest.py`
- Ingests normalized JSON into PostgreSQL
- Creates schema, loads data, shows statistics

```bash
# Setup database (one-time)
python db_ingest.py --data normalized_bail_data.json --create-schema --clear

# Show stats
python db_ingest.py --data normalized_bail_data.json
```

**PostgreSQL Setup:**
```bash
# Install PostgreSQL (if needed)
# On Windows: Download from postgresql.org

# Create database
createdb bail_precedents

# Set environment variable
export POSTGRES_URL="postgresql://user:password@localhost:5432/bail_precedents"
```

### Phase 3: Retrieval Pipeline

#### 7. `analyzer.py`
- Analyzes input case using LLM
- Extracts: statutes, procedural_stage, tags, material_facts
- Generates legal questions for prosecution & defense

```bash
python analyzer.py --input "case_facts.txt" --side defense
```

```python
from analyzer import CaseAnalyzer

analyzer = CaseAnalyzer()
analysis = analyzer.analyze_case(case_text, side="defense")
# Returns: {statutes, tags, stage, questions, material_facts}
```

#### 8. `retrieval_pipeline.py`
- Complete end-to-end retrieval
- Steps:
  1. Analyze case → structured query
  2. Database search → 30-50 candidates
  3. LLM reranking → evaluate relevance
  4. Return top-5 + strongest adverse precedent

```bash
python retrieval_pipeline.py --input case.txt --side defense --top-k 5
```

```python
from retrieval_pipeline import RetrievalPipeline

pipeline = RetrievalPipeline()
result = pipeline.retrieve(case_text, side="defense", top_k=5)

# result contains:
# - analysis: structured case analysis
# - precedents: top 5 relevant precedents
# - adverse_precedent: strongest opposing precedent
```

#### 9. `run_pipeline.py`
- Master orchestrator for all phases

```bash
# Run complete pipeline
python run_pipeline.py --all --input-dir out --test-case test_case.txt --create-schema

# Run only Phase 1 (tagging)
python run_pipeline.py --phase 1 --input-dir out

# Run only Phase 2 (database)
python run_pipeline.py --phase 2 --create-schema --clear-data

# Run only Phase 3 (test retrieval)
python run_pipeline.py --phase 3 --test-case test_case.txt
```

## Quick Start

### 1. Install Dependencies

```bash
pip install openai psycopg2-binary python-dotenv tqdm
```

### 2. Configure Environment

Create `.env` file:
```
OPENAI_API_KEY=your_key_here
POSTGRES_URL=postgresql://localhost:5432/bail_precedents
```

### 3. Run Complete Pipeline

```bash
# From bail_data directory
cd backend/bail_data

# Run all phases
python run_pipeline.py --all \
  --input-dir out \
  --create-schema \
  --clear-data \
  --test-case test_case.txt
```

This will:
1. Tag all cases in `out/` directory
2. Normalize statutes and data
3. Create PostgreSQL schema
4. Ingest data into database
5. Test retrieval with test case

### 4. Use Retrieval API

```python
from retrieval_pipeline import RetrievalPipeline

# Initialize
pipeline = RetrievalPipeline()

# Retrieve precedents
case_text = """
Accused is charged under Section 420 IPC for cheating in a property transaction.
Investigation is complete and chargesheet has been filed. Accused has no prior
criminal record and has deep roots in the community. The alleged loss is Rs. 5 lakhs.
Accused seeks anticipatory bail under Section 438 CrPC.
"""

result = pipeline.retrieve(case_text, side="defense", top_k=5)

# Format output
print(pipeline.format_output(result))

# Close connection
pipeline.close()
```

## Database Schema

### bail_cases
- `case_id` (PK)
- `case_name`, `court`, `decided_on`
- `procedural_stage`, `offence_types`, `disposition`
- `normalized_statutes[]`

### bail_propositions
- `case_id` (FK), `proposition_id`
- `text`, `quote`, `speaker`, `kind`
- `is_holding`, `favors`, `binding_level`
- `normalized_statutes[]`, `tags[]`
- `quote_verified`, `favors_verified`

### Search Function
```sql
SELECT * FROM search_propositions(
    ARRAY['CrPC-1973:438'],           -- statutes
    ARRAY['anticipatory_vs_regular'], -- tags
    'pre_arrest',                     -- stage
    'accused',                        -- favors
    1970,                             -- min_year
    50                                -- limit
);
```

## Scoring Logic

### Database Scoring
```
score = 
  (statute_overlap × 10) +
  (tag_overlap × 5) +
  (binding_level == 'binding' ? 3 : 0) +
  (is_holding ? 2 : 0) +
  (court == 'Supreme Court' ? 2 : 0)
```

### LLM Reranking
- Evaluates: relevance (0-10), applicability (yes/no/partial)
- Usage guidance: apply directly / analogize / distinguish / ignore
- Reasoning: one-sentence explanation

## Taxonomy Categories

1. **Procedural**: custodial_interrogation_necessity, cooperation_with_investigation, delay_in_trial, parity, anticipatory_vs_regular
2. **Offense Characteristics**: economic_offence_gravity, civil_dispute_criminalised, white_collar_crime, violence_involved, sexual_offence
3. **Evidence Strength**: prima_facie_weak, evidence_strong, circumstantial_only
4. **Accused Profile**: first_time_offender, habitual_offender, flight_risk, roots_in_community, influential_accused
5. **Victim/Complainant**: victim_vulnerable, victim_intimidation_risk, complainant_motive
6. **Special Statutes**: ndps_quantity, prevention_of_corruption, sc_st_atrocities, pmla_money_laundering
7. **Constitutional**: right_to_liberty, bail_not_jail, presumption_of_innocence, speedy_trial
8. **Punishment Proportionality**: maximum_punishment_low, already_undergone_substantial

## File Structure

```
bail_data/
├── README.md                      # This file
├── taxonomy.json                  # Issue taxonomy (52 tags)
├── statute_normalizer.py          # Statute normalization
├── tagger.py                      # LLM-based tagging
├── normalize_data.py              # Data normalization
├── schema.sql                     # PostgreSQL schema
├── db_ingest.py                   # Database ingestion
├── analyzer.py                    # Query case analyzer
├── retrieval_pipeline.py          # Complete retrieval pipeline
├── run_pipeline.py                # Master orchestrator
├── out/                           # Input: Original case JSONs
├── tagged/                        # Output: Tagged cases
├── normalized_bail_data.json      # Output: Normalized data
└── test_case.txt                  # Test case for Phase 3
```

## Next Steps

### Phase 4: Evaluation (To Be Implemented)

1. **Build Test Set**
   - Extract citations from judgments
   - Create ground truth dataset
   - Measure Recall@10

2. **Iterative Improvement**
   - Adjust taxonomy based on coverage gaps
   - Tune filter strictness
   - Consider adding Pinecone for semantic fallback

3. **Corpus Growth**
   - Current: ~10 cases
   - Target: 200-500 bail cases
   - Focus: forgery, cheating, property disputes, economic offences

## Performance Notes

- **Tagging**: ~30 seconds per case with gpt-4o-mini (10 propositions avg)
- **Database search**: <100ms for typical query
- **LLM reranking**: ~5-10 seconds for 30 candidates
- **Total retrieval time**: ~15-20 seconds

## Troubleshooting

### Database Connection Error
```bash
# Check PostgreSQL is running
pg_isready

# Check connection string
echo $POSTGRES_URL
```

### Missing Dependencies
```bash
pip install -r requirements.txt
```

### API Key Issues
```bash
# Check .env file
cat .env | grep OPENAI_API_KEY
```

## Contributing

To extend the system:

1. **Add more statute mappings**: Edit `statute_normalizer.py` → IPC_TO_BNS dict
2. **Add taxonomy tags**: Edit `taxonomy.json` → add to relevant category
3. **Improve scoring**: Modify `search_propositions()` in `schema.sql`
4. **Add reranking criteria**: Update prompt in `retrieval_pipeline.py`

## License

Internal use only.

## Contact

For questions or issues, contact the development team.
