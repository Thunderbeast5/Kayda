# Prosecutor Agent

A specialized AI agent that defends the State/Complainant in criminal cases by intelligently querying the lexigraphbe legal retrieval system.

## Architecture

```
Case File Input
    ↓
Query Understanding (lexigraphbe Stage 1)
    ↓
Crime Analysis & Strategy
    ↓
Selective Crime-Specific Queries to lexigraphbe
    ↓
Prosecutorial Argument Construction
    ↓
Multi-Round Trial Support (Opening, Rebuttal, Closing)
```

## Key Features

### 1. Intelligent Query Decomposition
- Uses lexigraphbe's `QueryUnderstandingAgent` to decompose case facts
- Identifies legal concepts without hardcoding section numbers
- Preserves legal regime flags (BNS vs IPC)

### 2. Strategic Crime Identification
- Analyzes case to identify PRIMARY, SECONDARY, and ANCILLARY offenses
- Prioritizes which crimes to focus prosecution on
- Determines prosecution theory and evidence requirements

### 3. Selective lexigraphbe Querying
- **Not a full pipeline run** - queries lexigraphbe ONLY for specific crimes as needed
- Caches retrieved sections to avoid redundant queries
- Calls lexigraphbe multiple times during trial (opening, rebuttal, closing)

### 4. Multi-Round Trial Support
- **Opening Argument**: Queries for primary crime sections
- **Rebuttal**: Identifies which crime defense is attacking, queries if needed
- **Closing Argument**: Synthesizes all retrieved sections

## Usage

```python
from prosecutor import ProsecutorAgent

# Initialize
prosecutor = ProsecutorAgent()

# Step 1: Analyze case file
case_file = "A complaint has been filed against X for..."
analysis = prosecutor.analyze_case(case_file)

print(f"Primary Crime: {analysis.primary_crime}")
print(f"Identified Crimes: {[c.crime_name for c in analysis.identified_crimes]}")

# Step 2: Build opening argument (queries lexigraphbe for primary crime)
opening = prosecutor.build_opening_argument()

# Step 3: Handle defense rebuttal (may query lexigraphbe for additional crimes)
defense_arg = "The defendant was acting in self-defense..."
rebuttal = prosecutor.handle_rebuttal(defense_arg)

# Step 4: Build closing argument (uses all cached results)
closing = prosecutor.build_closing_argument()

# Check what's been cached
summary = prosecutor.get_analysis_summary()
print(f"Cached queries: {summary['cached_queries']}")
```

## Integration with lexigraphbe

### What We Use From lexigraphbe:

1. **Stage 1: Query Understanding** (`query_understanding_agent.py`, `stage1_pipeline.py`)
   - Decomposes case into legal concepts
   - No section numbers, just concepts

2. **Stages 2-6: Full Pipeline** (`runner.py`)
   - **Stage 2**: Subquery Mapping
   - **Stage 3**: Chapter Identification
   - **Stage 4**: Statutory Verification
   - **Stage 5**: Bail Reasoning
   - **Stage 6**: Precedent Retrieval

The prosecutor calls `run_full_pipeline()` from `lexigraphbe.runner` which runs all stages 0-6 for each crime query.

### What We DON'T Use:

- Stage 0 (document intake) - we create CaseProfile directly for initial analysis
- The old `agents/lexigraph/lexigraph_agent.py` - we use the new lexigraphbe pipeline instead

**Important**: The prosecutor uses the **NEW** lexigraphbe pipeline (stages 0-6), NOT the old agents/lexigraph folder.

## Data Flow

```
1. Case File → CaseProfile → CaseContextObject
                    ↓
2. Stage1Pipeline.run(context)
                    ↓
3. LegalQueryObject (legal concepts, sub-queries)
                    ↓
4. Prosecutor analyzes → CrimeAnalysis objects
                    ↓
5. For each crime: build focused query
                    ↓
6. Query LexiGraphAgent.process_query(crime_query)
                    ↓
7. Cache results for reuse
                    ↓
8. Build arguments from cached sections
```

## Crime Analysis Structure

```python
@dataclass
class CrimeAnalysis:
    crime_name: str              # "Dowry Death", "Murder", etc.
    severity: str                # "primary", "secondary", "ancillary"
    legal_elements: List[str]    # Elements to prove
    prosecution_strategy: str    # How to prove this crime
    required_sections: List[str] # Types of sections needed
    retrieved_sections: List     # Actual sections from lexigraphbe
    supporting_precedents: List  # Precedents from lexigraphbe
```

## Example: Dowry Death Case

```
Input: "Woman died at matrimonial home, family demanded dowry..."

↓ Query Understanding
Legal Concepts: ["dowry demand", "cruelty", "unnatural death", "matrimonial home"]

↓ Crime Analysis
Primary Crime: Dowry Death (BNS 80 / IPC 304B)
Secondary: Cruelty (BNS 85 / IPC 498A)
Ancillary: Dowry Prohibition Act violations

↓ Opening Argument
Query lexigraphbe for: "Dowry Death | proving unnatural death within 7 years | 
                        dowry demand | cruelty before death"
Retrieved: BNS 80, IPC 304B, Evidence presumption under BSA 118

↓ Defense Rebuttal
Defense: "Death was accidental, no dowry proof"
Query lexigraphbe for: "Circumstantial evidence | dying declaration | 
                        demand through conduct"
Retrieved: Precedents on circumstantial evidence standards

↓ Closing
Synthesize all retrieved sections + precedents
Final prayer for conviction
```

## Extension Points

### 1. Custom Prosecution Strategies
Override `_analyze_prosecution_strategy()` for domain-specific logic

### 2. Enhanced Rebuttal Logic
Override `_identify_crime_from_defense()` to use NLP for better crime detection

### 3. Alternative Query Building
Override `_build_crime_specific_query()` for different query formats

### 4. Integration with Other Agents
```python
# Use with defense agent
defense = DefenseAgent()
defense_arg = defense.build_opening()
prosecutor_rebuttal = prosecutor.handle_rebuttal(defense_arg)
```

## Testing

```bash
# Run the built-in test case
cd backend/prosecutor
python prosecutor.py

# Expected output:
# - Crime analysis with identified offenses
# - Opening argument with retrieved sections
# - Rebuttal handling
# - Closing argument
# - Summary of cached queries
```

## Dependencies

- `lexigraphbe.query_understanding_agent`
- `lexigraphbe.query_verifier_agent`
- `lexigraphbe.stage1_pipeline`
- `lexigraphbe.schemas`
- `agents.lexigraph.lexigraph_agent` (for full retrieval)
- `langchain_groq` - Using Groq API with llama-3.3-70b-versatile
- `python-dotenv` - For environment variable management

**Note**: The prosecutor agent currently uses Groq (llama-3.3-70b-versatile) for LLM operations instead of OpenAI. This is configured directly in the prosecutor.py file and requires `GROQ_API_KEY` in your `.env` file.

## Performance Considerations

1. **Caching**: Retrieved sections are cached by crime name
2. **Selective Queries**: Only queries for crimes that are actually argued
3. **Lazy Loading**: Closing argument is the only phase that ensures all crimes are queried
4. **Reuse**: Rebuttal phase reuses cached results when possible

## Future Enhancements

- [ ] Multi-accused crime distribution
- [ ] Victim rights integration
- [ ] Real-time evidence tracking
- [ ] Precedent ranking by jurisdiction
- [ ] Cross-examination question generation
- [ ] Witness testimony analysis
