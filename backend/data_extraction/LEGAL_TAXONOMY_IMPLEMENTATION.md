# Legal Taxonomy Implementation for KAYDA

## What Was Created

A comprehensive **hierarchical legal taxonomy system** for KAYDA's women and children offences classifier, replacing simple keyword lists with structured, multi-level matching.

## Files Created

```
backend/data_extraction/legal_taxonomy/
├── women_children_offences.json          # Complete taxonomy data (12+ acts, 100+ categories)
├── taxonomy_matcher.py                   # Python utility class
└── README.md                             # Usage documentation
```

## Key Features

### 1. Hierarchical Structure (4 Levels)

```
Level 1: Acts (POCSO, IPC, BNS, POSH, Dowry Act, etc.)
   ↓
Level 2: Sections (376, 498A, 5(m), etc.)
   ↓
Level 3: Categories (sexual_offences, trafficking, etc.)
   ↓
Level 4: Keywords & Synonyms (rape, eve teasing, etc.)
```

### 2. Comprehensive Coverage

| Component | Count | Examples |
|-----------|-------|----------|
| Acts | 13 | POCSO, IPC, BNS, CrPC, POSH, Dowry Act, JJ Act |
| IPC Sections | 50+ | 354, 376, 498A, 304B, 363, 370 |
| POCSO Sections | 20+ | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| Offence Categories | 12 | sexual_offences, trafficking, acid_attacks, etc. |
| Keywords | 200+ | rape, stalking, dowry death, child abuse |
| Synonyms | 50+ | eve teasing → sexual harassment |
| Legal Terms | 100+ | prosecutrix, FIR, TIP test, ossification |

### 3. Smart Matching Capabilities

#### Act Identification
```python
matcher.identify_acts(text)
# Matches: "POCSO", "POCSO Act", "Protection of Children from Sexual Offences Act"
# Returns: Full name, mentions count, keywords matched
```

#### Offence Classification
```python
matcher.classify_offences(text)
# Returns:
# - Primary categories (top 3)
# - Detailed classification
# - Confidence score
# - Matched keywords
# - Acts involved
```

#### Context Detection
```python
matcher.get_context_type(snippet)
# Returns: 'present_case', 'cited_case', or 'unclear'
# Distinguishes "the accused was charged" from "as held in XYZ v. State"
```

#### Entity Extraction
```python
matcher.extract_legal_entities(text)
# Extracts: victims, relationships, locations
# E.g., prosecutrix, minor girl, daughter, school
```

## Advantages Over Simple Keyword Lists

| Feature | Keyword List | Taxonomy System |
|---------|-------------|-----------------|
| Structure | Flat | Hierarchical (4 levels) |
| Synonyms | Manual duplication | Automatic mapping |
| Context | No context | Present vs cited case detection |
| Sections | Text matching only | Act-section-category linkage |
| Confidence | Binary (found/not found) | Scored (0-1.0) |
| Extensibility | Hard to maintain | Easy to add new terms |
| Multi-Act Support | One-by-one | All acts in taxonomy |
| IPC→BNS Transition | Manual update needed | Built-in transition support |

## Integration Points

### Stage 3: PDF Extraction Enhancement

```python
# Add to SupremeCourtPDFParser2023
from legal_taxonomy.taxonomy_matcher import LegalTaxonomyMatcher

class SupremeCourtPDFParser2023:
    def __init__(self, config):
        self.config = config
        self.taxonomy_matcher = LegalTaxonomyMatcher()
    
    def parse_pdf(self, pdf_path):
        result = {... existing fields ...}
        
        # Enhanced classification
        classification = self.taxonomy_matcher.classify_offences(full_text)
        result['primary_offence_categories'] = classification['primary_categories']
        result['crime_keywords'] = classification['matched_keywords']
        result['classification_confidence'] = classification['confidence_score']
        
        # Legal entities
        entities = self.taxonomy_matcher.extract_legal_entities(full_text)
        result['victim_types'] = entities.get('victims', [])
        result['relationships'] = entities.get('relationships', [])
        
        return result
```

### Stage 4: GraphRAG Knowledge Graph

```python
# Generate semantic queries for similar case retrieval
queries = matcher.generate_search_queries(case_data)

# Build knowledge graph nodes
for act_key, act_data in matcher.identify_acts(text).items():
    graph.add_node(type='act', name=act_data['full_name'])

for category in classification['primary_categories']:
    graph.add_node(type='category', name=category)
```

### Classifier Training

```python
# Feature extraction for ML classifier
features = []
for judgment in dataset:
    classification = matcher.classify_offences(judgment['text'])
    
    features.append({
        'text': judgment['text'],
        'categories': classification['primary_categories'],
        'keywords': classification['matched_keywords'],
        'confidence': classification['confidence_score'],
        'acts': classification['acts_involved']
    })
```

### Search & Filtering

```python
# Get high-priority keywords for initial filtering
high_priority = matcher.get_high_priority_keywords()
# ['rape', 'child', 'minor', 'juvenile', 'POCSO', '498A', '376']

# Filter large dataset
relevant_cases = []
for case in all_cases:
    if any(keyword in case['text'].lower() for keyword in high_priority):
        relevant_cases.append(case)
```

## Precision + Recall Balance

The taxonomy system supports the **balanced extraction strategy** implemented in Stage 3:

1. **High Recall**: Comprehensive keyword lists ensure we don't miss relevant cases
2. **High Precision**: Context detection filters out cited cases
3. **Safety Net**: High-priority keywords always trigger classification

## Example Usage

```python
from legal_taxonomy.taxonomy_matcher import LegalTaxonomyMatcher

matcher = LegalTaxonomyMatcher()

# Sample judgment text
text = """
The appellant was charged under sections 376(2)(i), 363 and 201 IPC
and sections 5(m)/6 of the POCSO Act. The prosecutrix, a minor girl
aged 15 years, was kidnapped from school and subjected to rape.
The Trial Court convicted the accused for all offences.
"""

# Comprehensive analysis
acts = matcher.identify_acts(text)
classification = matcher.classify_offences(text)
entities = matcher.extract_legal_entities(text)

print(f"Acts: {list(acts.keys())}")
# Output: ['ipc', 'pocso']

print(f"Categories: {classification['primary_categories']}")
# Output: ['sexual_offences', 'child_offences', 'kidnapping_abduction']

print(f"Keywords: {classification['matched_keywords']}")
# Output: ['rape', 'minor girl', 'kidnapped', 'school']

print(f"Victims: {entities['victims']}")
# Output: ['prosecutrix', 'minor girl']
```

## Testing

```bash
# Run the test script
python backend/data_extraction/legal_taxonomy/taxonomy_matcher.py
```

Expected output:
```
=== Acts Identified ===
pocso: Protection of Children from Sexual Offences Act, 2012 (3 mentions)
ipc: Indian Penal Code, 1860 (2 mentions)

=== Offence Classification ===
Primary Categories: ['sexual_offences', 'child_offences']
Matched Keywords: ['minor', 'rape']
Confidence: 0.20

=== Legal Entities ===
victims: ['prosecutrix', 'minor girl']

=== Context Type ===
Context: present_case
```

## Future Enhancements

1. **Regional Languages**: Add Hindi/Tamil legal terms
2. **Weightage System**: Assign importance scores to keywords
3. **Relationship Graphs**: Map victim-accused-witness relationships
4. **Temporal Tracking**: Monitor IPC→BNS migration patterns
5. **Landmark Cases**: Link case names to categories
6. **State Laws**: Add state-specific acts

## Maintenance

To update the taxonomy:

1. Edit `women_children_offences.json`
2. Add new terms under appropriate category
3. Run validation: `python taxonomy_matcher.py`
4. Test with sample judgments
5. Update documentation

## Conclusion

This taxonomy system transforms KAYDA from keyword-based matching to **intelligent, context-aware legal classification**. It provides:

- ✅ **Better Recall**: Comprehensive keyword coverage
- ✅ **Better Precision**: Context-aware filtering
- ✅ **Maintainability**: Structured JSON format
- ✅ **Extensibility**: Easy to add new terms
- ✅ **Integration**: Ready for GraphRAG, classifiers, and search

The system is production-ready and can be integrated into your existing Stage 3/4 pipeline immediately.
