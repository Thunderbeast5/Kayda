# Prosecutor Agent - Visual Flow Diagram

## Complete System Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         PROSECUTOR AGENT FLOW                             │
└──────────────────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════╗
║ PHASE 1: CASE INTAKE & QUERY UNDERSTANDING                                ║
╚═══════════════════════════════════════════════════════════════════════════╝

   ┌─────────────┐
   │ Case File   │  "Woman died at matrimonial home. Family demanded 
   │   Input     │   dowry. Physical abuse documented..."
   └──────┬──────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Create CaseProfile                         │
   │  - case_facts: <text>                      │
   │  - legal_regime: "BNS_2023"                │
   │  - documents_text: <text>                  │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Create CaseContextObject                   │
   │  - case_profile: CaseProfile               │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ╔═══════════════════════════════════════════════╗
   ║ lexigraphbe Stage 1 Pipeline                  ║
   ╠═══════════════════════════════════════════════╣
   ║ ┌───────────────────────────────────────┐     ║
   ║ │ QueryUnderstandingAgent               │     ║
   ║ │  - LLM: gpt-4o-mini                   │     ║
   ║ │  - Temperature: 0.1                   │     ║
   ║ │  - Extracts legal concepts            │     ║
   ║ │  - Creates sub-queries                │     ║
   ║ └───────────────┬───────────────────────┘     ║
   ║                 ↓                              ║
   ║ ┌───────────────────────────────────────┐     ║
   ║ │ QueryVerificationAgent                │     ║
   ║ │  - Validates query decomposition      │     ║
   ║ │  - Checks concept quality             │     ║
   ║ │  - Retry logic (max 1 attempt)        │     ║
   ║ └───────────────┬───────────────────────┘     ║
   ╚═════════════════╪═══════════════════════════════╝
                     │
                     ↓
   ┌────────────────────────────────────────────┐
   │ LegalQueryObject                           │
   │  - legal_concepts: [                       │
   │      {concept: "dowry demand",             │
   │       concept_type: "substantive_offence", │
   │       confidence: 0.92},                   │
   │      {concept: "unnatural death", ...}     │
   │    ]                                       │
   │  - sub_queries: [                          │
   │      {sub_query: "Death of married woman", │
   │       confidence: 0.88}                    │
   │    ]                                       │
   │  - legal_regime: "BNS_2023"                │
   └──────┬─────────────────────────────────────┘
          │
          │
╔═══════════════════════════════════════════════════════════════════════════╗
║ PHASE 2: CRIME ANALYSIS & PROSECUTION STRATEGY                            ║
╚═══════════════════════════════════════════════════════════════════════════╝
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ LLM Analysis (gpt-4o, temp=0.2)            │
   │                                            │
   │ Input:                                     │
   │  - Case facts                              │
   │  - Legal concepts from Stage 1             │
   │  - Sub-queries from Stage 1                │
   │                                            │
   │ Prompt:                                    │
   │  "You are a Senior Public Prosecutor..."   │
   │  "Identify primary/secondary crimes..."    │
   │  "Determine prosecution strategy..."       │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ ProsecutorAnalysis                         │
   │                                            │
   │  case_summary: "Dowry death case..."       │
   │  primary_crime: "Dowry Death"              │
   │  prosecution_theory: "Prove demand..."     │
   │                                            │
   │  identified_crimes: [                      │
   │    CrimeAnalysis {                         │
   │      crime_name: "Dowry Death"             │
   │      severity: "primary"                   │
   │      legal_elements: [                     │
   │        "death within 7 years",             │
   │        "dowry demand",                     │
   │        "cruelty before death"              │
   │      ]                                     │
   │      prosecution_strategy: "Prove..."      │
   │      required_sections: ["BNS 80", ...]    │
   │      retrieved_sections: []  ← EMPTY       │
   │      supporting_precedents: [] ← EMPTY     │
   │    },                                      │
   │    CrimeAnalysis {                         │
   │      crime_name: "Cruelty"                 │
   │      severity: "secondary"                 │
   │      ...                                   │
   │    }                                       │
   │  ]                                         │
   │                                            │
   │  evidence_requirements: [...]              │
   │  legal_principles: [...]                   │
   └──────┬─────────────────────────────────────┘
          │
          │
╔═══════════════════════════════════════════════════════════════════════════╗
║ PHASE 3: OPENING ARGUMENT (Query Primary Crime)                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ build_opening_argument()                   │
   │                                            │
   │ Step 1: Filter primary crimes              │
   │   crimes_to_query = [                      │
   │     "Dowry Death" (severity="primary")     │
   │   ]                                        │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ FOR crime IN primary_crimes:               │
   │   query_lexigraphbe_for_crime(crime)       │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ╔═══════════════════════════════════════════════╗
   ║ query_lexigraphbe_for_crime()                 ║
   ╠═══════════════════════════════════════════════╣
   ║ Step 1: Check cache                           ║
   ║   cache_key = "dowry death"                   ║
   ║   if cache_key in cache:                      ║
   ║     return cached_results ← CACHE HIT         ║
   ║                                               ║
   ║ Step 2: Build focused query                   ║
   ║   query = _build_crime_specific_query(crime)  ║
   ║   → "Crime: Dowry Death | Legal elements: ... ║
   ║       death within 7 years, dowry demand... | ║
   ║       Case context: Woman died..."            ║
   ║                                               ║
   ║ Step 3: Call LexiGraphAgent                   ║
   ║   ┌───────────────────────────────────────┐   ║
   ║   │ from agents.lexigraph.lexigraph_agent │   ║
   ║   │ import LexiGraphAgent                 │   ║
   ║   │                                       │   ║
   ║   │ lexigraph = LexiGraphAgent()         │   ║
   ║   │ results = lexigraph.process_query(   │   ║
   ║   │   query, debug=False                 │   ║
   ║   │ )                                     │   ║
   ║   └───────────────┬───────────────────────┘   ║
   ║                   │                            ║
   ║                   │ LexiGraphAgent runs:       ║
   ║                   │  - Stage 1-6 pipeline      ║
   ║                   │  - Vector retrieval        ║
   ║                   │  - Graph enrichment        ║
   ║                   │  - Community retrieval     ║
   ║                   │  - Precedent matching      ║
   ║                   │  → Returns sections        ║
   ║                   ↓                            ║
   ║   ┌───────────────────────────────────────┐   ║
   ║   │ results = {                           │   ║
   ║   │   "recommended_sections": [           │   ║
   ║   │     {act: "BNS", section: "80", ...}, │   ║
   ║   │     {act: "IPC", section: "304B",...} │   ║
   ║   │   ],                                  │   ║
   ║   │   "similar_cases": [                  │   ║
   ║   │     {case_name: "State v. Singh",...} │   ║
   ║   │   ],                                  │   ║
   ║   │   "supporting_articles": [...],       │   ║
   ║   │   "supporting_evidence": [...]        │   ║
   ║   │ }                                     │   ║
   ║   └───────────────┬───────────────────────┘   ║
   ║                   │                            ║
   ║ Step 4: Cache results                         ║
   ║   cache["dowry death"] = results              ║
   ║                                               ║
   ║ Step 5: Update crime object                   ║
   ║   crime.retrieved_sections = results[...]     ║
   ║   crime.supporting_precedents = results[...]  ║
   ╚═══════════════════╪═══════════════════════════╝
                       │
                       ↓
   ┌────────────────────────────────────────────┐
   │ Return Opening Argument                    │
   │  {                                         │
   │    "phase": "opening",                     │
   │    "prosecution_theory": "...",            │
   │    "primary_charges": [                    │
   │      {                                     │
   │        "crime": "Dowry Death",             │
   │        "elements": [...],                  │
   │        "sections": [                       │
   │          {act: "BNS", section: "80",...}   │
   │        ],                                  │
   │        "strategy": "..."                   │
   │      }                                     │
   │    ]                                       │
   │  }                                         │
   └────────────────────────────────────────────┘

   Cache State: {"dowry death": {...}}
                 ↑ PRIMARY CRIME CACHED


╔═══════════════════════════════════════════════════════════════════════════╗
║ PHASE 4: REBUTTAL (Selective Query on Defense Attack)                     ║
╚═══════════════════════════════════════════════════════════════════════════╝

   ┌────────────────────────────────────────────┐
   │ Defense Argument                           │
   │ "No physical cruelty shown. Wife made      │
   │  false allegations of abuse."              │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ handle_rebuttal(defense_argument)          │
   │                                            │
   │ Step 1: Identify crime from defense        │
   │   crime_mentioned = "Cruelty"              │
   │   (keyword: "physical cruelty")            │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Step 2: Check cache                        │
   │   cache_key = "cruelty"                    │
   │   if "cruelty" in cache:                   │
   │     use cached ← CACHE MISS                │
   │   else:                                    │
   │     query lexigraphbe                      │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ╔═══════════════════════════════════════════════╗
   ║ query_lexigraphbe_for_crime("Cruelty")        ║
   ╠═══════════════════════════════════════════════╣
   ║ Query: "Crime: Cruelty | Legal elements:      ║
   ║         harassment for dowry, physical... "   ║
   ║                                               ║
   ║ LexiGraphAgent returns:                       ║
   ║  - BNS 85 (Cruelty by husband/relatives)      ║
   ║  - IPC 498A (equivalent)                      ║
   ║  - Precedents on defining cruelty             ║
   ║  - Evidence standards                         ║
   ║                                               ║
   ║ cache["cruelty"] = results                    ║
   ╚═══════════════════════════════════════════════╝
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Generate counter-arguments (LLM)           │
   │  - "Evidence shows pattern of abuse..."    │
   │  - "Precedent: cruelty includes mental..." │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Return Rebuttal                            │
   │  {                                         │
   │    "phase": "rebuttal",                    │
   │    "focused_crime": "Cruelty",             │
   │    "counter_arguments": [...],             │
   │    "additional_sections": {                │
   │      "recommended_sections": [             │
   │        {act: "BNS", section: "85",...}     │
   │      ]                                     │
   │    }                                       │
   │  }                                         │
   └────────────────────────────────────────────┘

   Cache State: {
     "dowry death": {...},
     "cruelty": {...}  ← NEW CRIME CACHED
   }


╔═══════════════════════════════════════════════════════════════════════════╗
║ PHASE 5: CLOSING ARGUMENT (Query Remaining Crimes)                        ║
╚═══════════════════════════════════════════════════════════════════════════╝

   ┌────────────────────────────────────────────┐
   │ build_closing_argument()                   │
   │                                            │
   │ Step 1: Ensure all crimes queried          │
   │   for crime in identified_crimes:          │
   │     if crime not in cache:                 │
   │       query_lexigraphbe_for_crime(crime)   │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Remaining crime: "Dowry Prohibition Act"   │
   │   (ancillary, not yet cached)              │
   └──────┬─────────────────────────────────────┘
          │
          ↓
   ╔═══════════════════════════════════════════════╗
   ║ query_lexigraphbe_for_crime("DPA")            ║
   ║                                               ║
   ║ LexiGraphAgent returns:                       ║
   ║  - DPA Section 3 (Taking dowry)               ║
   ║  - DPA Section 4 (Demanding dowry)            ║
   ║  - Precedents on DPA violations               ║
   ║                                               ║
   ║ cache["dowry prohibition act"] = results      ║
   ╚═══════════════════════════════════════════════╝
          │
          ↓
   ┌────────────────────────────────────────────┐
   │ Synthesize ALL cached results              │
   │                                            │
   │ Return Closing Argument                    │
   │  {                                         │
   │    "phase": "closing",                     │
   │    "case_summary": "...",                  │
   │    "prosecution_theory": "...",            │
   │    "all_charges": [                        │
   │      {                                     │
   │        "crime": "Dowry Death",             │
   │        "severity": "primary",              │
   │        "sections": [...],  ← FROM CACHE    │
   │        "precedents": [...] ← FROM CACHE    │
   │      },                                    │
   │      {                                     │
   │        "crime": "Cruelty",                 │
   │        "severity": "secondary",            │
   │        "sections": [...],  ← FROM CACHE    │
   │        "precedents": [...]                 │
   │      },                                    │
   │      {                                     │
   │        "crime": "Dowry Prohibition",       │
   │        "severity": "ancillary",            │
   │        "sections": [...],  ← JUST QUERIED  │
   │        "precedents": [...]                 │
   │      }                                     │
   │    ],                                      │
   │    "final_prayer": "In light of..."        │
   │  }                                         │
   └────────────────────────────────────────────┘

   Final Cache State: {
     "dowry death": {...},
     "cruelty": {...},
     "dowry prohibition act": {...}
   }
   ↑ ALL CRIMES NOW CACHED


╔═══════════════════════════════════════════════════════════════════════════╗
║ SUMMARY: Query Count                                                      ║
╚═══════════════════════════════════════════════════════════════════════════╝

  Stage 1 (Understanding):  1 query  (QueryUnderstandingAgent)
  Crime Analysis:           1 query  (LLM strategy)
  Opening:                  1 query  (lexigraphbe for "Dowry Death")
  Rebuttal:                 1 query  (lexigraphbe for "Cruelty")
  Closing:                  1 query  (lexigraphbe for "DPA")
                           ─────────
  Total LexiGraphAgent:     3 queries (on-demand per crime)

  Compare to running full pipeline once: Would query everything upfront
  Prosecutor approach: Queries only what's argued, when it's argued


╔═══════════════════════════════════════════════════════════════════════════╗
║ KEY EFFICIENCY GAINS                                                      ║
╚═══════════════════════════════════════════════════════════════════════════╝

  1. Cache Reuse
     - Rebuttal checks cache before querying
     - If defense attacks already-cached crime: 0 new queries

  2. Lazy Loading
     - Ancillary crimes not queried until closing
     - If trial ends early, some crimes never queried

  3. Focused Queries
     - Each query targets ONE crime
     - Better retrieval quality vs. generic "all crimes" query

  4. Multi-Round Support
     - Maintains context across opening → rebuttal → closing
     - Defense can shift focus, prosecutor adapts
```

## Legend

```
┌─────┐
│ Box │  = Process/Data structure
└─────┘

╔═════╗
║ Box ║  = External service (lexigraphbe, LLM)
╚═════╝

  ↓     = Data flow
  │

← LABEL = Annotation/State
```
