# Prosecutor Agent - Quick Start Guide

## Installation

No additional dependencies needed if you have the main backend environment set up.

```bash
cd backend/prosecutor
python -c "from prosecutor import ProsecutorAgent; print('✓ Ready')"
```

## Basic Usage (3 Steps)

### Step 1: Initialize

```python
from prosecutor import ProsecutorAgent

prosecutor = ProsecutorAgent()
```

### Step 2: Analyze Case

```python
case_file = """
A complaint has been filed against X for dowry harassment.
The complainant alleges physical abuse and continuous demands
for additional dowry of 5 lakhs rupees since the marriage.
"""

analysis = prosecutor.analyze_case(case_file)

print(f"Primary Crime: {analysis.primary_crime}")
print(f"Strategy: {analysis.prosecution_theory}")
```

### Step 3: Build Arguments

```python
# Opening argument (queries lexigraphbe for primary crime)
opening = prosecutor.build_opening_argument()

# Rebuttal (queries for additional crimes if needed)
defense_arg = "The allegations are false..."
rebuttal = prosecutor.handle_rebuttal(defense_arg)

# Closing (uses all cached results)
closing = prosecutor.build_closing_argument()
```

## What Gets Queried When?

```python
# After analyze_case():
prosecutor.retrieved_sections_cache
# => {}  # Nothing queried yet

# After build_opening_argument():
prosecutor.retrieved_sections_cache
# => {"dowry death": {...}}  # Primary crime retrieved

# After handle_rebuttal():
prosecutor.retrieved_sections_cache
# => {"dowry death": {...}, "cruelty": {...}}  # Additional crime if needed

# After build_closing_argument():
prosecutor.retrieved_sections_cache
# => {"dowry death": {...}, "cruelty": {...}, "dowry prohibition act": {...}}
# All crimes now cached
```

## Checking What's Cached

```python
summary = prosecutor.get_analysis_summary()
print(summary["cached_queries"])
# => ["dowry death", "cruelty"]
```

## API Reference

### `analyze_case(case_file: str) -> ProsecutorAnalysis`

Analyzes case and identifies crimes. Runs lexigraphbe Stage 1 for query understanding.

**Returns:**
- `case_summary`: Brief summary
- `identified_crimes`: List of CrimeAnalysis objects
- `primary_crime`: Main offense name
- `prosecution_theory`: Overall strategy
- `evidence_requirements`: Evidence needed
- `legal_principles`: Applicable principles

### `build_opening_argument() -> Dict`

Builds opening argument. Queries lexigraphbe for **primary crimes only**.

**Returns:**
```python
{
    "phase": "opening",
    "prosecution_theory": "...",
    "primary_charges": [
        {
            "crime": "Dowry Death",
            "elements": ["death within 7 years", ...],
            "sections": [...],  # From lexigraphbe
            "strategy": "..."
        }
    ],
    "evidence_framework": [...],
    "legal_principles": [...]
}
```

### `handle_rebuttal(defense_argument: str, specific_crime: Optional[str] = None) -> Dict`

Handles defense rebuttal. Queries lexigraphbe for **additional crimes if defense attacks them**.

**Parameters:**
- `defense_argument`: Defense counsel's argument text
- `specific_crime`: Optional crime to focus on

**Returns:**
```python
{
    "phase": "rebuttal",
    "defense_argument_summary": "...",
    "prosecution_response": {
        "focused_crime": "Cruelty",
        "counter_arguments": [...],
        "additional_sections": {...}  # From lexigraphbe if newly queried
    }
}
```

### `build_closing_argument() -> Dict`

Builds closing argument. Queries lexigraphbe for **any remaining crimes not yet cached**.

**Returns:**
```python
{
    "phase": "closing",
    "case_summary": "...",
    "prosecution_theory": "...",
    "all_charges": [
        {
            "crime": "...",
            "severity": "primary|secondary|ancillary",
            "sections": [...],
            "precedents": [...]
        }
    ],
    "consolidated_evidence": [...],
    "final_prayer": "..."
}
```

### `get_analysis_summary() -> Dict`

Get current state of analysis and cache.

**Returns:**
```python
{
    "case_summary": "...",
    "primary_crime": "...",
    "prosecution_theory": "...",
    "identified_crimes": [
        {"name": "...", "severity": "...", "sections_retrieved": True/False}
    ],
    "cached_queries": ["crime1", "crime2", ...]
}
```

## Common Patterns

### Pattern 1: Full Trial Flow

```python
prosecutor = ProsecutorAgent()

# Pre-trial
analysis = prosecutor.analyze_case(case_file)

# Opening statement
opening = prosecutor.build_opening_argument()
present_to_court(opening["spoken_argument"])

# Defense argues
defense_arg = get_defense_argument()

# Prosecution rebuts
rebuttal = prosecutor.handle_rebuttal(defense_arg)
present_to_court(rebuttal["prosecution_response"])

# Closing
closing = prosecutor.build_closing_argument()
present_to_court(closing["final_prayer"])
```

### Pattern 2: Iterative Rebuttal

```python
prosecutor = ProsecutorAgent()
prosecutor.analyze_case(case_file)
prosecutor.build_opening_argument()

# Multiple rounds of rebuttal
for defense_round in defense_arguments:
    rebuttal = prosecutor.handle_rebuttal(defense_round)
    # Each round may query new crimes as needed
    
closing = prosecutor.build_closing_argument()
```

### Pattern 3: Check Before Querying

```python
prosecutor = ProsecutorAgent()
analysis = prosecutor.analyze_case(case_file)

# See what will be queried
for crime in analysis.identified_crimes:
    print(f"Will query: {crime.crime_name} ({crime.severity})")

# Decide to skip ancillary crimes
primary_crimes = [c for c in analysis.identified_crimes if c.severity == "primary"]
for crime in primary_crimes:
    prosecutor.query_lexigraphbe_for_crime(crime)
```

## Troubleshooting

### "LexiGraphAgent not available"

The prosecutor now uses the NEW `lexigraphbe.runner.run_full_pipeline()` (stages 0-6), not the old `agents/lexigraph/lexigraph_agent.py`.

**Solution:** Ensure lexigraphbe stages are properly configured. The prosecutor will automatically use the new pipeline.

### Query understanding fails

If Stage 1 returns status != "VERIFIED":

```python
analysis = prosecutor.analyze_case(case_file)
if prosecutor.legal_query.flag_for_confirmation:
    print("Manual review required")
    print(prosecutor.legal_query.manual_review)
```

### Empty retrieved sections

Check if lexigraphbe query succeeded:

```python
results = prosecutor.query_lexigraphbe_for_crime(crime)
if "error" in results:
    print(f"Query failed: {results['error']}")
```

## Testing

```bash
# Run basic test
cd backend/prosecutor
python test_prosecutor.py

# Run full example
python prosecutor.py
```

## Next Steps

- Read [ARCHITECTURE.md](./ARCHITECTURE.md) for system design
- Read [README.md](./README.md) for detailed documentation
- Check lexigraphbe documentation for pipeline details
- See `agents/lexigraph/` for the underlying retrieval agent
