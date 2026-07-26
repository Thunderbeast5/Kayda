# KAYDA Legal Taxonomy System

## Overview

A hierarchical legal taxonomy system for classifying and analyzing Supreme Court judgments related to **Offences Against Women and Children**. This system provides structured matching across multiple levels: Acts → Sections → Categories → Keywords.

## Architecture

```
Legal Taxonomy
├── Acts Layer
│   ├── POCSO Act (sections, keywords, abbreviations)
│   ├── IPC (sections categorized by crime type)
│   ├── BNS (replacement for IPC)
│   ├── CrPC (procedural sections)
│   └── Other Acts (Dowry, POSH, JJ Act, etc.)
│
├── Offence Categories
│   ├── Sexual Offences
│   ├── Harassment
│   ├── Domestic Offences
│   ├── Trafficking
│   └── Child Offences
│
├── Legal Terminology
│   ├── Victims (prosecutrix, survivor, minor)
│   ├── Investigation (FIR, charge sheet, DNA)
│   ├── Evidence (medical report, forensic)
│   └── Court Terms (conviction, bail, appeal)
│
└── Search Optimization
    ├── High Priority Keywords
    ├── Context Indicators (present case vs cited case)
    └── Crime Synonyms
```

## Files

- **`women_children_offences.json`**: Complete taxonomy data
- **`taxonomy_matcher.py`**: Python utility for matching and classification
- **`README.md`**: This file

## Usage

### 1. Basic Import

```python
from legal_taxonomy.taxonomy_matcher import LegalTaxonomyMatcher

matcher = LegalTaxonomyMatcher()
```

### 2. Identify Legal Acts

```python
text = "The accused was charged under POCSO Act and IPC sections 376, 498A"
acts = matcher.identify_acts(text)

# Output:
# {
#   'pocso': {'full_name': 'Protection of Children...', 'mentions': 1},
#   'ipc': {'full_name': 'Indian Penal Code, 1860', 'mentions': 1}
# }
```

### 3. Classify Offences

```python
classification = matcher.classify_offences(judgment_text)

# Output:
# {
#   'primary_categories': ['sexual_offences', 'child_offences'],
#   'detailed_classification': {
#     'sexual_offences': ['rape', 'sexual assault'],
#     'child_offences': ['child sexual abuse']
#   },
#   'confidence_score': 0.85,
#   'matched_keywords': ['rape', 'minor', 'POCSO'],
#   'acts_involved': ['pocso', 'ipc']
# }
```

### 4. Extract Legal Entities

```python
entities = matcher.extract_legal_entities(judgment_text)

# Output:
# {
#   'victims': ['prosecutrix', 'minor girl'],
#   'relationships': ['daughter', 'teacher'],
#   'locations': ['school']
# }
```

### 5. Context Detection (Present Case vs Cited Case)

```python
snippet = "The accused was charged under Section 376 IPC"
context = matcher.get_context_type(snippet)
# Output: 'present_case'

snippet2 = "As held in State v. Kumar, Section 376 IPC applies when..."
context2 = matcher.get_context_type(snippet2)
# Output: 'cited_case'
```

### 6. Generate Search Queries (for GraphRAG)

```python
case_data = {
    'ipc_sections_referred': ['376', '498A', '304B'],
    'pocso_sections_referred': ['5', '6'],
    'full_text': judgment_text
}

queries = matcher.generate_search_queries(case_data)
# Output: [
#   "IPC sections 376, 498A, 304B",
#   "POCSO Act sections 5, 6",
#   "sexual offences cases",
#   "rape"
# ]
```

## Integration with KAYDA Pipeline

### Stage 3: Enhanced Extraction

```python
from legal_taxonomy.taxonomy_matcher import LegalTaxonomyMatcher

class EnhancedPDFParser:
    def __init__(self):
        self.taxonomy_matcher = LegalTaxonomyMatcher()
    
    def parse_pdf(self, pdf_path):
        # ... existing extraction ...
        
        # Add taxonomy-based classification
        classification = self.taxonomy_matcher.classify_offences(full_text)
        
        result['offence_classification'] = classification['primary_categories']
        result['crime_keywords'] = classification['matched_keywords']
        result['confidence_score'] = classification['confidence_score']
        
        # Extract legal entities
        entities = self.taxonomy_matcher.extract_legal_entities(full_text)
        result['victim_types'] = entities.get('victims', [])
        result['relationship_context'] = entities.get('relationships', [])
        
        return result
```

### Stage 4: GraphRAG Integration

```python
def build_knowledge_graph(case_data):
    matcher = LegalTaxonomyMatcher()
    
    # Generate semantic search queries
    search_queries = matcher.generate_search_queries(case_data)
    
    # Build graph nodes
    nodes = []
    
    # Act nodes
    acts = matcher.identify_acts(case_data['full_text'])
    for act_key, act_data in acts.items():
        nodes.append({
            'type': 'act',
            'name': act_data['full_name'],
            'mentions': act_data['mentions']
        })
    
    # Category nodes
    classification = matcher.classify_offences(case_data['full_text'])
    for category in classification['primary_categories']:
        nodes.append({
            'type': 'offence_category',
            'name': category
        })
    
    return nodes
```

### Classifier Training

```python
def prepare_training_data():
    matcher = LegalTaxonomyMatcher()
    
    # Get all high-priority keywords for feature extraction
    keywords = matcher.get_high_priority_keywords()
    
    # For each judgment
    for judgment in judgments:
        classification = matcher.classify_offences(judgment['full_text'])
        
        # Use as training labels
        labels = classification['primary_categories']
        features = classification['matched_keywords']
        
        training_data.append({
            'text': judgment['full_text'],
            'labels': labels,
            'features': features,
            'confidence': classification['confidence_score']
        })
```

## Taxonomy Structure

### Acts Coverage

| Act | Sections Covered | Keywords | Use Case |
|-----|------------------|----------|----------|
| POCSO Act | 3-17, 19-42A | child sexual abuse, penetrative assault | Child sexual offences |
| IPC | 354-377, 498A, 304B, 363-370A | rape, dowry, kidnapping, trafficking | General criminal offences |
| BNS | Corresponding to IPC | Same as IPC | Post-2024 cases |
| Dowry Act | 2-8 | dowry death, harassment | Dowry-related cases |
| POSH Act | All | workplace harassment, ICC | Workplace sexual harassment |
| JJ Act | Key sections | juvenility, JJB | Juvenile offenders |

### Offence Categories

1. **Sexual Offences**: rape, gang rape, sexual assault, child sexual abuse
2. **Harassment**: sexual harassment, stalking, cyber harassment
3. **Modesty Offences**: outraging modesty, molestation, eve teasing
4. **Privacy Offences**: voyeurism, revenge porn, morphing
5. **Domestic Offences**: domestic violence, cruelty, dowry harassment
6. **Acid Attacks**: acid attack, acid throwing, disfigurement
7. **Kidnapping/Abduction**: kidnapping, wrongful confinement
8. **Trafficking**: human trafficking, forced prostitution, commercial sexual exploitation
9. **Marriage Offences**: forced marriage, child marriage, bigamy
10. **Reproductive Offences**: forced abortion, female foeticide
11. **Child Offences**: child abuse, child labour, exploitation
12. **Murder Related**: dowry death, honour killing, abetment of suicide

## Advantages Over Keyword Lists

### 1. Hierarchical Structure
- Easy to navigate Acts → Sections → Categories → Terms
- Supports drill-down from high-level to specific

### 2. Multi-Level Matching
- Act level: "POCSO" → identifies Protection of Children from Sexual Offences Act
- Section level: "376" → identifies rape under IPC
- Category level: "rape" → identifies sexual_offences category
- Synonym level: "eve teasing" → maps to sexual_harassment

### 3. Context Awareness
- Distinguishes present case from cited cases
- Identifies victim types, relationships, locations
- Provides confidence scores

### 4. Extensible
- Easy to add new acts (e.g., state-specific laws)
- Can add regional language terms
- Supports multiple legal systems (IPC → BNS transition)

### 5. Integration Ready
- JSON format for easy parsing
- Python utility class for programmatic access
- Ready for GraphRAG, classifiers, and semantic search

## Future Enhancements

1. **Regional Language Support**: Add Hindi, Tamil, Telugu legal terms
2. **State Laws**: Add state-specific domestic violence acts
3. **Landmark Cases**: Map landmark case names to categories
4. **Temporal Evolution**: Track IPC → BNS migration
5. **Weighted Scoring**: Assign importance weights to different keywords
6. **Entity Relationships**: Build relationship graphs (victim-accused-witness)

## Contributing

To add new terms or categories:

1. Edit `women_children_offences.json`
2. Run validation: `python taxonomy_matcher.py`
3. Test with sample judgments
4. Update this README

## License

This taxonomy is part of the KAYDA Trial Mootcourt project.
