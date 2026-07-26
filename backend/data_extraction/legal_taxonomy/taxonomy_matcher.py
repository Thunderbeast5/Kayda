#!/usr/bin/env python3
"""
Legal Taxonomy Matcher for KAYDA
Provides hierarchical matching and classification for women & children offences
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


class LegalTaxonomyMatcher:
    """
    Hierarchical legal taxonomy matcher for KAYDA.
    Supports multi-level matching: Acts → Sections → Categories → Keywords
    """
    
    def __init__(self, taxonomy_path: str = None):
        if taxonomy_path is None:
            taxonomy_path = Path(__file__).parent / "women_children_offences.json"
        
        with open(taxonomy_path, 'r', encoding='utf-8') as f:
            self.taxonomy = json.load(f)
        
        # Build reverse indexes for fast lookup
        self._build_indexes()
    
    def _build_indexes(self):
        """Build reverse indexes for efficient matching"""
        
        # Act name → act_key mapping
        self.act_name_to_key = {}
        for act_key, act_data in self.taxonomy['acts'].items():
            # Full name
            self.act_name_to_key[act_data['full_name'].lower()] = act_key
            
            # Short names
            for name in act_data.get('short_names', []):
                self.act_name_to_key[name.lower()] = act_key
            
            # Abbreviations
            for abbr in act_data.get('abbreviations', []):
                self.act_name_to_key[abbr.lower()] = act_key
        
        # Section number → acts mapping
        self.section_to_acts = defaultdict(list)
        for act_key, act_data in self.taxonomy['acts'].items():
            if 'sections' in act_data:
                for section in act_data['sections']:
                    self.section_to_acts[section].append(act_key)
            elif 'women_children_sections' in act_data:
                for category, sections in act_data['women_children_sections'].items():
                    for section in sections:
                        self.section_to_acts[section].append(act_key)
        
        # Keyword → category mapping
        self.keyword_to_categories = defaultdict(set)
        for category, terms in self.taxonomy['offence_categories'].items():
            if isinstance(terms, dict):
                for subcategory, keywords in terms.items():
                    for keyword in keywords:
                        self.keyword_to_categories[keyword.lower()].add(f"{category}.{subcategory}")
            elif isinstance(terms, list):
                for keyword in terms:
                    self.keyword_to_categories[keyword.lower()].add(category)
    
    def identify_acts(self, text: str) -> Dict[str, Dict]:
        """
        Identify all legal acts mentioned in text.
        
        Returns:
            {
                'pocso': {'full_name': '...', 'mentions': 3},
                'ipc': {'full_name': '...', 'mentions': 5}
            }
        """
        text_lower = text.lower()
        acts_found = defaultdict(lambda: {'mentions': 0, 'full_name': '', 'keywords_matched': []})
        
        for act_key, act_data in self.taxonomy['acts'].items():
            mentions = 0
            keywords_matched = []
            
            # Check full name
            if act_data['full_name'].lower() in text_lower:
                mentions += 1
            
            # Check short names
            for name in act_data.get('short_names', []):
                mentions += len(re.findall(r'\b' + re.escape(name.lower()) + r'\b', text_lower))
            
            # Check abbreviations
            for abbr in act_data.get('abbreviations', []):
                mentions += len(re.findall(r'\b' + re.escape(abbr.lower()) + r'\b', text_lower))
            
            # Check keywords
            for keyword in act_data.get('keywords', []):
                if keyword.lower() in text_lower:
                    keywords_matched.append(keyword)
            
            if mentions > 0 or keywords_matched:
                acts_found[act_key] = {
                    'full_name': act_data['full_name'],
                    'mentions': mentions,
                    'keywords_matched': keywords_matched
                }
        
        return dict(acts_found)
    
    def classify_offences(self, text: str, extracted_sections: Dict[str, List[str]] = None) -> Dict[str, any]:
        """
        Classify offences mentioned in text using hierarchical taxonomy.
        
        Args:
            text: Full judgment text
            extracted_sections: Pre-extracted sections from stage 3
        
        Returns:
            {
                'primary_categories': ['sexual_offences', 'child_offences'],
                'detailed_classification': {
                    'sexual_offences': ['rape', 'sexual assault'],
                    'child_offences': ['child sexual abuse']
                },
                'confidence_score': 0.95,
                'matched_keywords': ['rape', 'minor', 'POCSO'],
                'acts_involved': ['pocso', 'ipc']
            }
        """
        text_lower = text.lower()
        
        # Find all matching categories
        matched_categories = defaultdict(list)
        matched_keywords = set()
        
        for category, terms in self.taxonomy['offence_categories'].items():
            if isinstance(terms, dict):
                for subcategory, keywords in terms.items():
                    for keyword in keywords:
                        if keyword.lower() in text_lower:
                            matched_categories[category].append(keyword)
                            matched_keywords.add(keyword)
            elif isinstance(terms, list):
                for keyword in terms:
                    if keyword.lower() in text_lower:
                        matched_categories[category].append(keyword)
                        matched_keywords.add(keyword)
        
        # Identify acts
        acts_involved = list(self.identify_acts(text).keys())
        
        # Calculate confidence based on multiple matches
        confidence_score = min(1.0, len(matched_keywords) / 10.0)
        
        # Determine primary categories (those with most matches)
        category_counts = {cat: len(keywords) for cat, keywords in matched_categories.items()}
        sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
        primary_categories = [cat for cat, _ in sorted_categories[:3]]
        
        return {
            'primary_categories': primary_categories,
            'detailed_classification': dict(matched_categories),
            'confidence_score': confidence_score,
            'matched_keywords': sorted(list(matched_keywords)),
            'acts_involved': acts_involved
        }
    
    def extract_legal_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract all legal entities from text: victims, accused, relationships, etc.
        
        Returns:
            {
                'victims': ['prosecutrix', 'minor girl'],
                'relationships': ['daughter', 'teacher'],
                'locations': ['school', 'residence']
            }
        """
        text_lower = text.lower()
        entities = defaultdict(list)
        
        # Extract from legal terminology
        legal_terms = self.taxonomy['legal_terminology']
        
        # Victims
        for term in legal_terms['victims']:
            if term.lower() in text_lower:
                entities['victims'].append(term)
        
        # Relationships
        if 'relationships' in legal_terms:
            for rel_type, rel_terms in legal_terms['relationships'].items():
                for term in rel_terms:
                    if term.lower() in text_lower:
                        entities['relationships'].append(term)
                        entities[f'relationship_{rel_type}'].append(term)
        
        # Locations
        for term in legal_terms.get('locations', []):
            if term.lower() in text_lower:
                entities['locations'].append(term)
        
        return dict(entities)
    
    def get_context_type(self, text_snippet: str) -> str:
        """
        Determine if text snippet is about present case or cited case.
        
        Returns: 'present_case', 'cited_case', or 'unclear'
        """
        text_lower = text_snippet.lower()
        
        present_count = 0
        cited_count = 0
        
        for indicator in self.taxonomy['search_optimization']['context_indicators']['present_case']:
            if indicator.lower() in text_lower:
                present_count += 1
        
        for indicator in self.taxonomy['search_optimization']['context_indicators']['cited_case']:
            if indicator.lower() in text_lower:
                cited_count += 1
        
        if present_count > cited_count:
            return 'present_case'
        elif cited_count > present_count:
            return 'cited_case'
        else:
            return 'unclear'
    
    def get_high_priority_keywords(self) -> List[str]:
        """Get high-priority keywords for initial filtering"""
        return self.taxonomy['search_optimization']['high_priority_keywords']
    
    def get_section_category(self, section_num: str, act: str = 'ipc') -> str:
        """
        Get the crime category for a specific section number.
        
        Args:
            section_num: Section number (e.g., "376", "498A")
            act: Act name (e.g., 'ipc', 'pocso')
        
        Returns:
            Category name (e.g., 'rape_sexual_assault', 'dowry')
        """
        if act not in self.taxonomy['acts']:
            return 'unknown'
        
        act_data = self.taxonomy['acts'][act]
        
        if 'women_children_sections' in act_data:
            for category, sections in act_data['women_children_sections'].items():
                if section_num in sections or section_num.upper() in sections:
                    return category
        
        return 'other'
    
    def generate_search_queries(self, case_data: Dict) -> List[str]:
        """
        Generate optimized search queries based on case data.
        For GraphRAG semantic search.
        
        Args:
            case_data: Extracted case data with sections, keywords, etc.
        
        Returns:
            List of search query strings
        """
        queries = []
        
        # Primary query from sections
        if case_data.get('ipc_sections_referred'):
            sections_str = ", ".join(case_data['ipc_sections_referred'][:5])
            queries.append(f"IPC sections {sections_str}")
        
        if case_data.get('pocso_sections_referred'):
            queries.append(f"POCSO Act sections {', '.join(case_data['pocso_sections_referred'])}")
        
        # Category-based queries
        classification = self.classify_offences(case_data.get('full_text', ''))
        for category in classification['primary_categories'][:2]:
            queries.append(f"{category.replace('_', ' ')} cases")
        
        # Keyword-based queries
        for keyword in classification['matched_keywords'][:3]:
            queries.append(keyword)
        
        return queries


# Example usage
if __name__ == "__main__":
    matcher = LegalTaxonomyMatcher()
    
    # Test text
    test_text = """
    The appellant was charged under sections 376, 363 and 201 IPC and 
    sections 5(m) and 6 of the POCSO Act. The prosecutrix, a minor girl,
    was kidnapped and subjected to rape. The Trial Court convicted the 
    accused for all offences.
    """
    
    # Test identification
    print("=== Acts Identified ===")
    acts = matcher.identify_acts(test_text)
    for act_key, data in acts.items():
        print(f"{act_key}: {data['full_name']} ({data['mentions']} mentions)")
    
    print("\n=== Offence Classification ===")
    classification = matcher.classify_offences(test_text)
    print(f"Primary Categories: {classification['primary_categories']}")
    print(f"Matched Keywords: {classification['matched_keywords']}")
    print(f"Confidence: {classification['confidence_score']:.2f}")
    
    print("\n=== Legal Entities ===")
    entities = matcher.extract_legal_entities(test_text)
    for entity_type, terms in entities.items():
        print(f"{entity_type}: {terms}")
    
    print("\n=== Context Type ===")
    print(f"Context: {matcher.get_context_type(test_text)}")
