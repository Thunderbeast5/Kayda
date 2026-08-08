# Prosecutor Agent Architecture

## Overview

The Prosecutor Agent is designed to defend the State/Complainant in criminal cases by intelligently querying the lexigraphbe legal retrieval system **on-demand** for specific crimes, rather than running the entire pipeline upfront.

## Key Design Principles

### 1. **Query Understanding First**
- Uses lexigraphbe's Stage 1 pipeline to decompose case facts
- Extracts legal concepts without hardcoding section numbers
- Preserves legal regime context (BNS vs IPC)

### 2. **Strategic Crime Identification**
- LLM analyzes which crimes are present in the case
- Categorizes as PRIMARY, SECONDARY, or ANCILLARY
- Determines prosecution strategy before any section retrieval

### 3. **Selective Retrieval**
- **Only queries lexigraphbe for specific crimes when needed**
- Caches results to avoid redundant queries
- Supports multi-round trial (opening → rebuttal → closing)

### 4. **Multi-Turn Capability**
- Opening: Query for primary crime
- Rebuttal: Query for additional crimes if defense attacks them
- Closing: Synthesize all cached results

## Component Interaction

```
┌─────────────────────────────────────────────────────────────┐
│                    Prosecutor Agent                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │  1. Case Analysis                                   │     │
│  │     - Parse case file                               │     │
│  │     - Create CaseProfile                            │     │
│  └─────────────┬──────────────────────────────────────┘     │
│                │                                              │
│                ↓                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  2. Query Understanding (lexigraphbe Stage 1)      │     │
│  │     - QueryUnderstandingAgent                       │     │
│  │     - QueryVerificationAgent                        │     │
│  │     → LegalQueryObject (concepts, sub-queries)     │     │
│  └─────────────┬──────────────────────────────────────┘     │
│                │                                              │
│                ↓                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  3. Crime Strategy Analysis (LLM)                   │     │
│  │     - Identify crimes (primary/secondary)           │     │
│  │     - Determine prosecution theory                  │     │
│  │     - Plan evidence requirements                    │     │
│  │     → ProsecutorAnalysis                           │     │
│  └─────────────┬──────────────────────────────────────┘     │
│                │                                              │
│                ↓                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  4. Selective Crime Queries                         │     │
│  │     FOR EACH crime_to_argue:                        │     │
│  │       - Build focused query                         │     │
│  │       - Call LexiGraphAgent.process_query()        │     │
│  │       - Cache results by crime name                 │     │
│  │     → Retrieved sections + precedents              │     │
│  └─────────────┬──────────────────────────────────────┘     │
│                │                                              │
│                ↓                                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  5. Argument Construction                           │     │
│  │     - Opening: Use primary crime sections           │     │
│  │     - Rebuttal: Query if needed, respond            │     │
│  │     - Closing: Synthesize all cached results        │     │
│  └────────────────────────────────────────────────────┘     │
│                                                               │
└─────────────────────────────────────────────────────────────┘

         ↓ Queries specific crimes ↓

┌─────────────────────────────────────────────────────────────┐
│                    LexiGraphAgent                            │
│                (agents/lexigraph/lexigraph_agent.py)        │
├─────────────────────────────────────────────────────────────┤
│  - Runs Stage 1-6 pipeline for THAT crime                   │
│  - Vector retrieval (Pinecone)                               │
│  - Graph enrichment (Neo4j)                                  │
│  - Community retrieval                                       │
│  - Precedent matching                                        │
│  - Returns sections + cases for THAT crime                   │
└─────────────────────────────────────────────────────────────┘
```

## Data Structures

### CrimeAnalysis
```python
@dataclass
class CrimeAnalysis:
    crime_name: str              # e.g., "Dowry Death"
    severity: str                # "primary" | "secondary" | "ancillary"
    legal_elements: List[str]    # Elements to prove
    prosecution_strategy: str    # How to prove
    required_sections: List[str] # Types of sections needed
    retrieved_sections: List     # From lexigraphbe (populated later)
    supporting_precedents: List  # From lexigraphbe (populated later)
```

### ProsecutorAnalysis
```python
@dataclass
class ProsecutorAnalysis:
    case_summary: str
    identified_crimes: List[CrimeAnalysis]
    primary_crime: str
    prosecution_theory: str
    evidence_requirements: List[str]
    legal_principles: List[str]
```

## Query Flow Example

### Dowry Death Case

```
Input Case:
"Woman died at matrimonial home. Family demanded dowry.
Physical abuse documented. Death within 2 years of marriage."

↓ [Step 1: Query Understanding]

LegalQueryObject:
  legal_concepts:
    - "unnatural death within matrimonial relationship"
    - "dowry demand and harassment"
    - "physical cruelty"
  sub_queries:
    - "Death of married woman under suspicious circumstances"
    - "Continuous demand for dowry by husband and in-laws"
    - "Physical assault causing bodily harm"

↓ [Step 2: Crime Analysis - LLM]

ProsecutorAnalysis:
  primary_crime: "Dowry Death"
  identified_crimes:
    1. Dowry Death (primary)
       - severity: "primary"
       - legal_elements: ["death within 7 years", "dowry demand",
                          "cruelty before death"]
       - prosecution_strategy: "Prove demand + death sequence"
    
    2. Cruelty (secondary)
       - severity: "secondary"
       - legal_elements: ["harassment for dowry", "physical violence"]
       - prosecution_strategy: "Corroborate dowry death charge"
    
    3. Dowry Prohibition Act (ancillary)
       - severity: "ancillary"
       - legal_elements: ["taking dowry", "demanding dowry"]

↓ [Step 3: Opening Argument - Query Primary Crime]

Query to LexiGraphAgent:
  "Crime: Dowry Death | Legal elements: death within 7 years,
   dowry demand, cruelty before death | Case context: Woman died..."

Retrieved from lexigraphbe:
  - BNS 80 (Dowry Death)
  - IPC 304B (equivalent)
  - BSA 118 (statutory presumption)
  - Precedents: State of Punjab v. Iqbal Singh (1991)
  - Evidence: dying declaration, demand letters, witness testimony

↓ [Step 4: Defense Rebuts]

Defense: "Death was accidental. No proof of dowry."

Prosecutor identifies: Attacking primary crime (Dowry Death)
Check cache: Dowry Death already queried ✓
Response: Use cached sections + precedents on circumstantial evidence

↓ [Step 5: Defense Shifts Focus]

Defense: "No physical cruelty shown. Wife made false allegations."

Prosecutor identifies: Attacking secondary crime (Cruelty)
Check cache: Cruelty NOT yet queried ✗

Query to LexiGraphAgent:
  "Crime: Cruelty | Legal elements: harassment for dowry,
   physical violence | Case context: ..."

Retrieved:
  - BNS 85 (Cruelty)
  - IPC 498A (equivalent)
  - Precedents on defining cruelty
  - Evidence standards for proving mental cruelty

↓ [Step 6: Closing Argument]

Synthesize ALL cached results:
  - Dowry Death sections (cached from opening)
  - Cruelty sections (cached from rebuttal)
  - Query Dowry Prohibition Act (not yet retrieved)

Final argument uses all 3 crime categories with their sections.
```

## Key Differences from lexigraphbe Standalone

| Aspect | lexigraphbe Standalone | Prosecutor Agent |
|--------|------------------------|------------------|
| **Input** | Single user query | Complete case file |
| **Query Understanding** | Direct to pipeline | Stage 1 only, then analyze |
| **Section Retrieval** | One-shot for all | On-demand per crime |
| **Multi-Round** | No session state | Maintains context across rounds |
| **Strategy** | Neutral retrieval | Prosecutorial perspective |
| **Caching** | No | Yes, by crime name |

## Benefits of This Design

1. **Efficiency**: Only retrieves sections for crimes actually being argued
2. **Flexibility**: Can adapt strategy mid-trial based on defense
3. **Context Preservation**: Multi-turn conversation with memory
4. **Targeted**: Each crime gets a focused query, better results
5. **Explainable**: Clear mapping of crime → query → sections

## Integration Points

### With lexigraphbe:
- `QueryUnderstandingAgent` - for case decomposition
- `QueryVerificationAgent` - for quality assurance
- `Stage1Pipeline` - orchestration + retry logic

### With agents/lexigraph:
- `LexiGraphAgent.process_query()` - for full section retrieval
- Returns: recommended_sections, similar_cases, supporting_graph

### With LLM:
- Crime analysis and strategy formulation
- Counter-argument generation
- Argument structuring

## Extension: Defense Agent

The same architecture can be inverted for a Defense Agent:

```python
class DefenseAgent:
    def analyze_case(self, case_file: str, charges: List[str]):
        # Use Stage 1 to understand charges
        # Analyze defense strategy (alibi, procedural, substantive)
        # Query lexigraphbe for:
        #   - Exceptions to charges
        #   - Burden of proof standards
        #   - Precedents favoring accused
        pass
    
    def build_opening_argument(self):
        # Query for procedural safeguards (bail, presumption of innocence)
        pass
    
    def handle_rebuttal(self, prosecution_argument: str):
        # Identify which charge prosecution is emphasizing
        # Query for counter-sections (defenses, exceptions)
        pass
```

## Performance Considerations

1. **Stage 1 is fast** (~2-3 seconds) - runs once per case
2. **Crime analysis is fast** (~3-5 seconds) - runs once per case  
3. **lexigraphbe queries are expensive** (~10-15 seconds each)
   - Cache results to avoid re-querying
   - Only query when actually needed
4. **Total for typical case**:
   - Opening: 15-20 seconds (1 crime query)
   - Rebuttal: 2-15 seconds (cache hit or new query)
   - Closing: 5-30 seconds (query remaining crimes)

## Future Enhancements

- [ ] Parallel crime queries (query all primary crimes at once)
- [ ] Smart cache invalidation (refresh if new evidence)
- [ ] Evidence-to-section mapping
- [ ] Victim rights integration
- [ ] Multi-accused charge distribution
- [ ] Real-time transcript analysis
- [ ] Precedent strength scoring
