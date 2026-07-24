#!/usr/bin/env python3
"""
Stage 4 Enhanced: TAXONOMY-POWERED CLASSIFIER
Integrates hierarchical legal taxonomy for intelligent classification
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from collections import Counter, defaultdict

import pandas as pd
from tqdm import tqdm

# Add taxonomy to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'legal_taxonomy'))

from taxonomy_matcher import LegalTaxonomyMatcher

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class Config:
    project_root: Path = Path(__file__).parent.parent.parent.parent
    
    json_input_dir: Path = project_root / 'backend' / 'data_extraction' / 'json' / 'json_output_2017'
    output_csv: Path = project_root / 'backend' / 'data_extraction' / 'segregation' / '2017' / 'classified_taxonomy_2017.csv'
    output_json: Path = project_root / 'backend' / 'data_extraction' / 'segregation' / '2017' / 'classified_taxonomy_2017.json'
    cache_file: Path = project_root / 'backend' / 'data_extraction' / 'segregation' / '2017' / 'taxonomy_cache_2017.json'
    
    def __post_init__(self):
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        self.output_json.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# TAXONOMY-ENHANCED CLASSIFIER
# ============================================================

class TaxonomyClassifier:
    """Enhanced classifier using legal taxonomy system"""
    
    def __init__(self, config: Config):
        self.config = config
        self.taxonomy = LegalTaxonomyMatcher()
        self.cache = self._load_cache()
        
        self.stats = {
            'total': 0,
            'processed': 0,
            'cached': 0,
            'by_primary_category': defaultdict(int),
            'acts_distribution': defaultdict(int),
            'confidence_distribution': defaultdict(int)
        }
    
    def _load_cache(self) -> Dict:
        """Load classification cache"""
        if self.config.cache_file.exists():
            try:
                with open(self.config.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_cache(self):
        """Save classification cache"""
        try:
            with open(self.config.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")
    
    def classify_case(self, case_data: Dict) -> Dict:
        """
        Classify case using hierarchical taxonomy
        
        Returns enriched case data with:
        - primary_categories: Top categories
        - detailed_classification: Full taxonomy classification
        - acts_involved: All legal acts identified
        - crime_keywords: Matched keywords
        - legal_entities: Victims, relationships, etc.
        - confidence_score: Classification confidence
        """
        case_id = case_data.get('case_id', '')
        
        # Check cache
        if case_id in self.cache:
            self.stats['cached'] += 1
            return self.cache[case_id]
        
        # Extract text components
        full_text = case_data.get('full_text', '')
        headnotes = case_data.get('headnotes', '')
        issue = case_data.get('issue_for_consideration', '')
        judgment = case_data.get('judgment_text', '')
        
        # Combined text for comprehensive analysis
        combined_text = f"{issue}\\n\\n{headnotes}\\n\\n{judgment}"
        if not combined_text.strip():
            combined_text = full_text
        
        # ============================================================
        # TAXONOMY-BASED CLASSIFICATION
        # ============================================================
        
        # 1. Identify acts
        acts_analysis = self.taxonomy.identify_acts(combined_text)
        acts_involved = list(acts_analysis.keys())
        acts_details = {act: data['full_name'] for act, data in acts_analysis.items()}
        
        # 2. Classify offences using taxonomy
        classification = self.taxonomy.classify_offences(
            combined_text,
            extracted_sections={
                'ipc': case_data.get('ipc_sections_referred', []),
                'bns': case_data.get('bns_sections_referred', []),
                'pocso': case_data.get('pocso_sections_referred', []),
                'it_act': case_data.get('it_act_sections_referred', [])
            }
        )
        
        # 3. Extract legal entities
        entities = self.taxonomy.extract_legal_entities(combined_text)
        
        # 4. Generate search queries for GraphRAG
        search_queries = self.taxonomy.generate_search_queries(case_data)
        
        # ============================================================
        # SECTION ANALYSIS WITH TAXONOMY
        # ============================================================
        
        section_categories = []
        section_summary = []
        
        # IPC sections
        for section in case_data.get('ipc_sections_referred', []):
            category = self.taxonomy.get_section_category(section, 'ipc')
            section_categories.append(category)
            section_summary.append(f"IPC {section} ({category})")
        
        # POCSO sections  
        for section in case_data.get('pocso_sections_referred', []):
            category = self.taxonomy.get_section_category(section, 'pocso')
            section_categories.append(category)
            section_summary.append(f"POCSO {section}")
        
        # BNS sections
        for section in case_data.get('bns_sections_referred', []):
            category = self.taxonomy.get_section_category(section, 'bns')
            section_categories.append(category)
            section_summary.append(f"BNS {section} ({category})")
        
        # ============================================================
        # PRIORITY SCORING
        # ============================================================
        
        # Get high-priority keywords from taxonomy
        high_priority = self.taxonomy.get_high_priority_keywords()
        
        # Check for high-priority matches
        priority_matches = []
        for keyword in high_priority:
            if keyword.lower() in combined_text.lower():
                priority_matches.append(keyword)
        
        # Calculate priority score
        priority_score = len(priority_matches) / len(high_priority) if high_priority else 0.0
        
        # ============================================================
        # BUILD RESULT
        # ============================================================
        
        result = {
            # Original data
            'case_id': case_id,
            'file_name': case_data.get('file_name', ''),
            'case_title': case_data.get('case_title', ''),
            'citation': case_data.get('citation', ''),
            'decision_date': case_data.get('decision_date', ''),
            'judges': case_data.get('judges', []),
            
            # Sections (from Stage 3)
            'ipc_sections': case_data.get('ipc_sections_referred', []),
            'bns_sections': case_data.get('bns_sections_referred', []),
            'pocso_sections': case_data.get('pocso_sections_referred', []),
            'it_act_sections': case_data.get('it_act_sections_referred', []),
            'dowry_act_sections': case_data.get('dowry_act_sections_referred', []),
            'crpc_sections': case_data.get('crpc_sections_referred', []),
            'posh_sections': case_data.get('posh_act_sections_referred', []),
            
            # Taxonomy-based classification
            'primary_categories': classification['primary_categories'],
            'detailed_classification': classification['detailed_classification'],
            'confidence_score': classification['confidence_score'],
            'priority_score': priority_score,
            
            # Acts analysis
            'acts_involved': acts_involved,
            'acts_details': acts_details,
            'acts_mentions': {act: data['mentions'] for act, data in acts_analysis.items()},
            
            # Keywords & entities
            'crime_keywords': classification['matched_keywords'],
            'priority_keywords_matched': priority_matches,
            'victim_types': entities.get('victims', []),
            'relationships': entities.get('relationships', []),
            'locations': entities.get('locations', []),
            
            # Section analysis
            'section_categories': list(set(section_categories)),
            'section_summary': section_summary,
            
            # Search optimization
            'search_queries': search_queries,
            
            # Metadata
            'classification_method': 'taxonomy_hierarchical',
            'classification_timestamp': datetime.now().isoformat(),
            'pages': case_data.get('pages', 0)
        }
        
        # Determine if case is relevant
        is_relevant = (
            len(classification['primary_categories']) > 0 or
            len(acts_involved) > 0 or
            priority_score > 0.1
        )
        
        result['is_relevant'] = is_relevant
        result['relevance_reason'] = self._explain_relevance(result)
        
        # Cache result
        self.cache[case_id] = result
        
        # Update stats
        self.stats['processed'] += 1
        for category in classification['primary_categories'][:3]:
            self.stats['by_primary_category'][category] += 1
        for act in acts_involved:
            self.stats['acts_distribution'][act] += 1
        
        # Confidence distribution
        conf_bucket = f"{int(classification['confidence_score'] * 10) * 10}%"
        self.stats['confidence_distribution'][conf_bucket] += 1
        
        return result
    
    def _explain_relevance(self, result: Dict) -> str:
        """Generate human-readable explanation of why case is relevant"""
        reasons = []
        
        if result['primary_categories']:
            top_category = result['primary_categories'][0].replace('_', ' ').title()
            reasons.append(f"Primary category: {top_category}")
        
        if result['acts_involved']:
            acts_str = ', '.join([a.upper() for a in result['acts_involved'][:3]])
            reasons.append(f"Acts: {acts_str}")
        
        if result['crime_keywords']:
            keywords_str = ', '.join(result['crime_keywords'][:3])
            reasons.append(f"Keywords: {keywords_str}")
        
        if result['ipc_sections']:
            sections_str = ', '.join(result['ipc_sections'][:3])
            reasons.append(f"IPC sections: {sections_str}")
        
        if result['pocso_sections']:
            reasons.append(f"POCSO case")
        
        return ' | '.join(reasons) if reasons else 'No clear match'
    
    def process_all(self) -> pd.DataFrame:
        """Process all JSON files"""
        if not self.config.json_input_dir.exists():
            logger.error(f"Input directory not found: {self.config.json_input_dir}")
            return pd.DataFrame()
        
        json_files = list(self.config.json_input_dir.glob('*.json'))
        if not json_files:
            logger.error(f"No JSON files found in {self.config.json_input_dir}")
            return pd.DataFrame()
        
        self.stats['total'] = len(json_files)
        logger.info(f"Found {len(json_files)} JSON files to classify")
        
        results = []
        
        for json_file in tqdm(json_files, desc="Classifying cases"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                result = self.classify_case(case_data)
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error processing {json_file.name}: {e}")
                continue
        
        # Save cache
        self._save_cache()
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        return df


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 80)
    print("STAGE 4 ENHANCED: TAXONOMY-POWERED CLASSIFICATION")
    print("=" * 80)
    
    config = Config()
    classifier = TaxonomyClassifier(config)
    
    # Process all cases
    print("\\n📊 Processing cases with legal taxonomy...")
    df = classifier.process_all()
    
    if df.empty:
        logger.error("No cases processed")
        return
    
    # Save results
    print(f"\\n💾 Saving results...")
    
    # CSV output
    csv_columns = [
        'case_id', 'case_title', 'citation', 'decision_date',
        'primary_categories', 'confidence_score', 'priority_score',
        'acts_involved', 'crime_keywords',
        'ipc_sections', 'pocso_sections', 'bns_sections',
        'victim_types', 'relationships',
        'is_relevant', 'relevance_reason'
    ]
    
    df_csv = df[[col for col in csv_columns if col in df.columns]]
    df_csv.to_csv(config.output_csv, index=False, encoding='utf-8')
    logger.info(f"CSV saved: {config.output_csv}")
    
    # JSON output (full data)
    with open(config.output_json, 'w', encoding='utf-8') as f:
        json.dump(df.to_dict('records'), f, indent=2, ensure_ascii=False)
    logger.info(f"JSON saved: {config.output_json}")
    
    # ============================================================
    # STATISTICS
    # ============================================================
    
    print("\\n" + "=" * 80)
    print("CLASSIFICATION STATISTICS")
    print("=" * 80)
    
    stats = classifier.stats
    
    print(f"\\nTotal cases: {stats['total']}")
    print(f"Processed: {stats['processed']}")
    print(f"From cache: {stats['cached']}")
    
    print(f"\\n📈 Primary Categories Distribution:")
    for category, count in sorted(stats['by_primary_category'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {category.replace('_', ' ').title()}: {count}")
    
    print(f"\\n📚 Acts Distribution:")
    for act, count in sorted(stats['acts_distribution'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {act.upper()}: {count}")
    
    print(f"\\n🎯 Confidence Score Distribution:")
    for bucket, count in sorted(stats['confidence_distribution'].items()):
        print(f"  {bucket}: {count}")
    
    # Relevant vs Irrelevant
    relevant_count = df['is_relevant'].sum() if 'is_relevant' in df.columns else 0
    print(f"\\n✅ Relevant cases: {relevant_count}")
    print(f"❌ Irrelevant cases: {len(df) - relevant_count}")
    
    print("\\n" + "=" * 80)
    print(f"📁 Output files:")
    print(f"  CSV: {config.output_csv}")
    print(f"  JSON: {config.output_json}")
    print(f"  Cache: {config.cache_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
