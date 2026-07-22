#!/usr/bin/env python3
"""
Stage 4: CONTEXT-AWARE CLASSIFIER
Properly disambiguates Section 3 (POCSO vs Dowry Act vs CrPC)
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from collections import Counter, defaultdict
import time

import pandas as pd
from tqdm import tqdm

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
    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = project_root / 'data'
    
    input_file: Path = data_dir / 'extracted_texts_combined.csv'
    output_csv: Path = data_dir / 'classified_context_aware.csv'
    output_json: Path = data_dir / 'classified_context_aware.json'
    cache_file: Path = data_dir / 'context_aware_cache.json'
    
    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# CATEGORY DEFINITIONS
# ============================================================

CATEGORY_DEFINITIONS = {
    "homicide": {
        "name": "Homicide / Murder",
        "ipc_sections": ["302", "304", "304A", "304B", "305", "306", "201"],
        "bns_sections": ["101", "102", "103", "105", "108"],
        "keywords": ["murder", "homicide", "culpable homicide", "death", "strangulation", "killed"]
    },
    "rape": {
        "name": "Rape / Sexual Assault",
        "ipc_sections": ["375", "376", "376A", "376AB", "376B", "376C", "376D", "376DA", "376DB", "376E"],
        "bns_sections": ["63", "64", "65", "66", "67", "68", "70", "71"],
        "keywords": ["rape", "sexual assault", "gang rape", "without consent", "non-consensual"],
        "exclude_if": ["false pretext of marriage", "false promise of marriage", "promise to marry"]
    },
    "false_promise_marriage": {
        "name": "False Promise / Pretext of Marriage",
        "ipc_sections": ["376", "493"],
        "bns_sections": ["69"],
        "keywords": ["false pretext of marriage", "false promise of marriage", "promise to marry", "would marry", "refused to marry"]
    },
    "matrimonial_cruelty": {
        "name": "Matrimonial Cruelty",
        "ipc_sections": ["498A"],
        "bns_sections": ["85"],
        "keywords": ["cruelty", "matrimonial cruelty", "cruelty by husband", "498a"]
    },
    "dowry": {
        "name": "Dowry Death / Harassment",
        "ipc_sections": ["304B"],
        "bns_sections": ["80", "86"],
        "dowry_act_sections": ["3", "4"],  # Dowry Prohibition Act sections
        "keywords": ["dowry", "dowry death", "dowry harassment", "dowry demand", "dowry prohibition act"]
    },
    "domestic_violence": {
        "name": "Domestic Violence",
        "act_required": "dv_act",
        "keywords": ["domestic violence", "protection order", "dv act", "pwdva"]
    },
    "trafficking": {
        "name": "Human Trafficking",
        "ipc_sections": ["366A", "366B", "370", "370A", "372", "373"],
        "bns_sections": ["143", "144"],
        "keywords": ["trafficking", "human trafficking", "child trafficking", "bonded labour"]
    },
    "kidnapping": {
        "name": "Kidnapping / Abduction",
        "ipc_sections": ["363", "364", "364A", "365", "366"],
        "bns_sections": ["137", "138", "140", "142"],
        "keywords": ["kidnapping", "abduction", "wrongful confinement"]
    },
    "pocso": {
        "name": "POCSO - Child Sexual Abuse",
        "pocso_sections": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "14", "15"],
        "act_required": "pocso",
        "keywords": ["pocso", "protection of children", "child sexual abuse", "penetrative sexual assault"]
    },
    "child_marriage": {
        "name": "Child Marriage",
        "act_required": "pcm_act",
        "keywords": ["child marriage", "prohibition of child marriage", "minor marriage"]
    },
    "acid_attack": {
        "name": "Acid Attack",
        "ipc_sections": ["326A", "326B"],
        "bns_sections": ["124"],
        "keywords": ["acid attack", "acid throwing", "chemical attack"]
    },
    "modesty": {
        "name": "Outraging Modesty",
        "ipc_sections": ["354", "509"],
        "bns_sections": ["74", "76", "79"],
        "keywords": ["outraging modesty", "eve teasing", "insulting modesty"]
    },
    "sexual_harassment": {
        "name": "Sexual Harassment (Workplace)",
        "ipc_sections": ["354A"],
        "bns_sections": ["75"],
        "keywords": ["sexual harassment", "workplace harassment", "vishaka", "posh"]
    },
    "voyeurism": {
        "name": "Voyeurism",
        "ipc_sections": ["354C"],
        "bns_sections": ["77"],
        "special_act_sections": ["66E"],
        "keywords": ["voyeurism", "peeping", "privacy violation"]
    },
    "stalking": {
        "name": "Stalking",
        "ipc_sections": ["354D"],
        "bns_sections": ["78"],
        "keywords": ["stalking", "cyberstalking", "354d"]
    },
    "cyber_crime": {
        "name": "Cyber Crime",
        "special_act_sections": ["67", "67A", "67B"],
        "act_required": "it_act",
        "keywords": ["cyber", "online", "pornography", "obscene", "information technology"]
    },
    "juvenile_justice": {
        "name": "Juvenile Justice",
        "act_required": "jj_act",
        "keywords": ["juvenile justice", "child in conflict", "care and protection", "jj act"]
    },
    "sex_selection": {
        "name": "Sex Selection / Foeticide",
        "act_required": "pcpndt_act",
        "keywords": ["sex selection", "female foeticide", "pre-natal", "pndt"]
    },
    "reproductive_rights": {
        "name": "Reproductive Rights",
        "act_required": "mtp_act",
        "keywords": ["medical termination of pregnancy", "abortion", "mtp act"]
    },
    "quashing_proceedings": {
        "name": "Quashing of Proceedings",
        "crpc_sections": ["482"],
        "keywords": ["quashing", "section 482", "inherent power", "frivolous", "vexatious"]
    },
    "sentencing": {
        "name": "Sentencing / Punishment",
        "keywords": ["sentence", "sentencing", "punishment", "death penalty", "leniency", "commutation"]
    },
    "criminal_procedure": {
        "name": "Criminal Procedure",
        "keywords": ["bail", "trial", "evidence", "investigation", "procedure", "crpc"]
    },
    "irrelevant": {
        "name": "Irrelevant",
        "keywords": ["income tax", "service matter", "promotion", "appointment", "civil suit", "contract"]
    }
}

# ============================================================
# SECTION MAPPING WITH CONTEXT
# ============================================================

SECTION_MAPPING = {
    # IPC Sections
    "302": ("homicide", "ipc"),
    "304": ("homicide", "ipc"),
    "304A": ("homicide", "ipc"),
    "304B": ("dowry", "ipc"),
    "305": ("homicide", "ipc"),
    "306": ("homicide", "ipc"),
    "201": ("homicide", "ipc"),
    "375": ("rape", "ipc"),
    "376": ("rape", "ipc"),
    "376A": ("rape", "ipc"),
    "376AB": ("rape", "ipc"),
    "376B": ("rape", "ipc"),
    "376C": ("rape", "ipc"),
    "376D": ("rape", "ipc"),
    "376DA": ("rape", "ipc"),
    "376DB": ("rape", "ipc"),
    "376E": ("rape", "ipc"),
    "354": ("modesty", "ipc"),
    "354A": ("sexual_harassment", "ipc"),
    "354B": ("modesty", "ipc"),
    "354C": ("voyeurism", "ipc"),
    "354D": ("stalking", "ipc"),
    "509": ("modesty", "ipc"),
    "363": ("kidnapping", "ipc"),
    "364": ("kidnapping", "ipc"),
    "364A": ("kidnapping", "ipc"),
    "365": ("kidnapping", "ipc"),
    "366": ("kidnapping", "ipc"),
    "366A": ("trafficking", "ipc"),
    "366B": ("trafficking", "ipc"),
    "370": ("trafficking", "ipc"),
    "370A": ("trafficking", "ipc"),
    "372": ("trafficking", "ipc"),
    "373": ("trafficking", "ipc"),
    "493": ("false_promise_marriage", "ipc"),
    "498A": ("matrimonial_cruelty", "ipc"),
    "326A": ("acid_attack", "ipc"),
    "326B": ("acid_attack", "ipc"),
    
    # BNS Sections
    "101": ("homicide", "bns"),
    "102": ("homicide", "bns"),
    "103": ("homicide", "bns"),
    "105": ("homicide", "bns"),
    "108": ("homicide", "bns"),
    "63": ("rape", "bns"),
    "64": ("rape", "bns"),
    "65": ("rape", "bns"),
    "66": ("rape", "bns"),
    "67": ("rape", "bns"),
    "68": ("rape", "bns"),
    "69": ("false_promise_marriage", "bns"),
    "70": ("rape", "bns"),
    "71": ("rape", "bns"),
    "74": ("modesty", "bns"),
    "75": ("sexual_harassment", "bns"),
    "76": ("modesty", "bns"),
    "77": ("voyeurism", "bns"),
    "78": ("stalking", "bns"),
    "79": ("modesty", "bns"),
    "80": ("dowry", "bns"),
    "85": ("matrimonial_cruelty", "bns"),
    "86": ("dowry", "bns"),
    "137": ("kidnapping", "bns"),
    "138": ("kidnapping", "bns"),
    "140": ("kidnapping", "bns"),
    "142": ("kidnapping", "bns"),
    "143": ("trafficking", "bns"),
    "144": ("trafficking", "bns"),
    "124": ("acid_attack", "bns"),
    
    # CrPC
    "482": ("quashing_proceedings", "crpc"),
}

# ============================================================
# CONTEXT-AWARE SECTION 3 DISAMBIGUATION
# ============================================================

class Section3Disambiguator:
    """
    Disambiguates Section 3 based on context:
    - POCSO Act, 2012: Section 3 (if POCSO mentioned)
    - Dowry Prohibition Act, 1961: Section 3 (if dowry mentioned)
    - Code of Criminal Procedure, 1973: Section 3 (if CrPC mentioned)
    - IPC: Section 3 (rare)
    """
    
    def __init__(self):
        self.context_patterns = {
            "POCSO Act, 2012": {
                "keywords": ["pocso", "protection of children", "child sexual abuse", "penetrative sexual assault"],
                "section": "3"
            },
            "Dowry Prohibition Act, 1961": {
                "keywords": ["dowry prohibition act", "dowry act", "dowry", "dowry demand", "dowry harassment"],
                "section": "3"
            },
            "Code of Criminal Procedure, 1973": {
                "keywords": ["crpc", "code of criminal procedure", "criminal procedure code"],
                "section": "3"
            },
            "Indian Penal Code, 1860": {
                "keywords": ["ipc", "indian penal code", "section 3 ipc"],
                "section": "3"
            }
        }
    
    def disambiguate(self, text: str, section_number: str) -> str:
        """Determine which Act Section 3 belongs to based on context"""
        if section_number != "3":
            return f"Section {section_number}"
        
        text_lower = text.lower()
        
        # Check each context
        for act_name, patterns in self.context_patterns.items():
            for keyword in patterns["keywords"]:
                if keyword in text_lower:
                    return f"{act_name}: Section 3"
        
        # Default: if no context found, check for explicit mention
        if "dowry prohibition act" in text_lower or "dowry act" in text_lower:
            return "Dowry Prohibition Act, 1961: Section 3"
        elif "pocso" in text_lower or "protection of children" in text_lower:
            return "POCSO Act, 2012: Section 3"
        elif "crpc" in text_lower or "code of criminal procedure" in text_lower:
            return "Code of Criminal Procedure, 1973: Section 3"
        else:
            return "Section 3 (Context Unknown)"


# ============================================================
# SECTION EXTRACTOR WITH CONTEXT-AWARE SECTION 3
# ============================================================

class SectionExtractor:
    def __init__(self):
        self.section_mapping = SECTION_MAPPING
        self.valid_sections = set(SECTION_MAPPING.keys())
        self.section3_disambiguator = Section3Disambiguator()
        
        # Special Act section ranges
        self.pocso_sections = {"3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "14", "15"}
        self.dowry_act_sections = {"3", "4"}
        self.it_act_sections = {"67", "67A", "67B", "66E"}
    
    def extract(self, text: str) -> Dict:
        text_upper = text.upper()
        text_lower = text.lower()
        
        result = {
            'ipc': [],
            'bns': [], 
            'crpc': [],
            'special_act': []
        }
        
        # Patterns for section extraction
        patterns = [
            r'\b(?:U/S|U/SS|SECTION|SECTIONS|S\.|SEC\.)\s*(?:OF\s+)?(?:THE\s+)?(?:IPC|BNS|CRPC|POCSO|IT\s+ACT)?\s*\b([0-9A-Z,/\-()]+)\b',
            r'\b([0-9]+[A-Z]?)\s*(?:OF\s+)?(?:THE\s+)?(?:IPC|BNS|CRPC|POCSO)\b',
            r'\bunder\s+(?:section|sec\.?)\s+([0-9]+[A-Z]?)\b',
            r'\bsection\s+([0-9]+[A-Z]?)\s+of\s+the\s+(?:indian penal code|bharatiya nyaya sanhita|code of criminal procedure|ipc|bns|crpc)\b',
        ]
        
        all_sections = []
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper, re.IGNORECASE)
            for match in matches:
                section_part = match[0] if isinstance(match, tuple) else match
                section_part = re.sub(r'[^0-9A-Z]', '', section_part)
                if not section_part:
                    continue
                if section_part in self.valid_sections:
                    all_sections.append(section_part)
        
        # Process each section with context
        for section in all_sections:
            if section in self.section_mapping:
                category, act_type = self.section_mapping[section]
                
                if act_type == "ipc":
                    result['ipc'].append(section)
                elif act_type == "bns":
                    result['bns'].append(section)
                elif act_type == "crpc":
                    result['crpc'].append(section)
                else:
                    # Special Act - disambiguate Section 3
                    if section == "3":
                        special_entry = self.section3_disambiguator.disambiguate(text, section)
                        result['special_act'].append(special_entry)
                    else:
                        # Other special sections
                        if section in self.pocso_sections:
                            result['special_act'].append(f"POCSO Act, 2012: Section {section}")
                        elif section in self.dowry_act_sections:
                            result['special_act'].append(f"Dowry Prohibition Act, 1961: Section {section}")
                        elif section in self.it_act_sections:
                            result['special_act'].append(f"Information Technology Act, 2000: Section {section}")
                        else:
                            result['special_act'].append(f"Special Act: Section {section}")
        
        # Deduplicate
        result['ipc'] = list(dict.fromkeys(result['ipc']))
        result['bns'] = list(dict.fromkeys(result['bns']))
        result['crpc'] = list(dict.fromkeys(result['crpc']))
        result['special_act'] = list(dict.fromkeys(result['special_act']))
        
        return result


# ============================================================
# ACT EXTRACTOR
# ============================================================

class ActExtractor:
    def __init__(self):
        self.act_patterns = {
            "pocso": ["pocso", "protection of children from sexual offences"],
            "dv_act": ["domestic violence act", "protection of women from domestic violence", "pwdva"],
            "dowry_act": ["dowry prohibition act", "dowry act"],
            "it_act": ["information technology act", "it act"],
            "posh_act": ["sexual harassment of women at workplace", "posh act"],
            "pcm_act": ["prohibition of child marriage act", "pcm act"],
            "jj_act": ["juvenile justice act", "jj act"],
            "pcpndt_act": ["pcpndt act", "pre-conception", "pre-natal diagnostic"],
            "mtp_act": ["medical termination of pregnancy act", "mtp act"],
            "crpc": ["code of criminal procedure", "criminal procedure code", "crpc"]
        }
    
    def extract(self, text: str) -> List[str]:
        text_lower = text.lower()
        found_acts = set()
        for act_name, keywords in self.act_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_acts.add(act_name)
                    break
        return list(found_acts)


# ============================================================
# KEYWORD EXTRACTOR
# ============================================================

class KeywordExtractor:
    def __init__(self):
        self.patterns = [
            r'(?:Keywords|Key Words|Keyterms)\s*[:;]\s*([^\n]+(?:\n\s*[A-Za-z,; ]+)*)',
            r'\[(?:Keywords|Key Words)\s*[:;]\s*([^\]]+)\]',
            r'(?:List of Keywords|List of Key Words)\s*[:;]?\s*(.*?)(?=\n\n|\n[A-Z]|$)'
        ]
    
    def extract(self, text: str) -> List[str]:
        keywords = []
        for pattern in self.patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1)
                parts = re.split(r'[,;]\s*|\n\s*[-•*]\s*|\n', content)
                for part in parts:
                    part = part.strip()
                    part = re.sub(r'^[-•*\s]+', '', part)
                    if part and len(part) > 1 and len(part) < 100:
                        keywords.append(part.lower())
                if keywords:
                    break
        return list(dict.fromkeys(keywords))


def detect_false_pretext(text: str) -> bool:
    patterns = [
        r'false\s+pretext\s+of\s+marriage',
        r'false\s+promise\s+of\s+marriage',
        r'promise\s+to\s+marry',
        r'pretext\s+of\s+marriage',
        r'assured\s+that\s+he\s+would\s+marry',
        r'would\s+marry\s+her',
        r'refused\s+to\s+marry',
    ]
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


# ============================================================
# RULE-BASED CLASSIFIER
# ============================================================

class RuleBasedClassifier:
    def __init__(self):
        self.category_definitions = CATEGORY_DEFINITIONS
        self.section_extractor = SectionExtractor()
        self.act_extractor = ActExtractor()
        self.keyword_extractor = KeywordExtractor()
        self.section3_disambiguator = Section3Disambiguator()
    
    def classify(self, text: str) -> Dict:
        keywords = self.keyword_extractor.extract(text)
        acts = self.act_extractor.extract(text)
        sections = self.section_extractor.extract(text)
        
        ipc_sections = sections['ipc']
        bns_sections = sections['bns']
        crpc_sections = sections['crpc']
        special_act_sections = sections['special_act']
        
        is_false_pretext = detect_false_pretext(text)
        
        category_scores = defaultdict(float)
        evidence = defaultdict(list)
        
        # Score IPC sections
        for section in ipc_sections:
            if section in SECTION_MAPPING:
                cat, _ = SECTION_MAPPING[section]
                if section in ['376'] and is_false_pretext:
                    cat = 'false_promise_marriage'
                    evidence[cat].append(f"Section {section} + false pretext")
                else:
                    evidence[cat].append(f"IPC {section}")
                category_scores[cat] += 1.0
        
        # Score BNS sections
        for section in bns_sections:
            if section in SECTION_MAPPING:
                cat, _ = SECTION_MAPPING[section]
                if section in ['63'] and is_false_pretext:
                    cat = 'false_promise_marriage'
                    evidence[cat].append(f"BNS {section} + false pretext")
                else:
                    evidence[cat].append(f"BNS {section}")
                category_scores[cat] += 1.0
        
        # Score CrPC sections
        for section in crpc_sections:
            if section == '482':
                category_scores['quashing_proceedings'] += 1.0
                evidence['quashing_proceedings'].append(f"CrPC {section}")
            else:
                category_scores['criminal_procedure'] += 0.5
        
        # Score Special Act sections
        for special in special_act_sections:
            # Check if it contains "POCSO"
            if "POCSO" in special:
                category_scores['pocso'] += 0.8
                evidence['pocso'].append(f"Special Act: {special}")
            # Check if it contains "Dowry Prohibition"
            elif "Dowry Prohibition" in special:
                category_scores['dowry'] += 0.8
                evidence['dowry'].append(f"Special Act: {special}")
            # Check if it contains "CrPC"
            elif "CrPC" in special:
                category_scores['criminal_procedure'] += 0.5
                evidence['criminal_procedure'].append(f"Special Act: {special}")
            else:
                # Try to infer from acts
                for act in acts:
                    for cat, info in self.category_definitions.items():
                        if info.get('act_required') == act:
                            category_scores[cat] += 0.5
                            evidence[cat].append(f"Special Act: {special}")
        
        # Score acts
        for act in acts:
            for cat, info in self.category_definitions.items():
                if info.get('act_required') == act:
                    category_scores[cat] += 0.8
                    evidence[cat].append(f"Act: {act}")
        
        # Score keywords
        for kw in keywords:
            for cat, info in self.category_definitions.items():
                for cat_kw in info.get('keywords', []):
                    if cat_kw in kw or kw in cat_kw:
                        category_scores[cat] += 0.3
                        evidence[cat].append(f"Keyword: {kw}")
                        break
        
        # Handle false pretext
        if is_false_pretext:
            if 'false_promise_marriage' not in category_scores:
                category_scores['false_promise_marriage'] = 0.5
                evidence['false_promise_marriage'].append("False pretext detected")
            else:
                category_scores['false_promise_marriage'] += 0.5
        
        # Auto-add categories from sections
        for section in ipc_sections + bns_sections:
            if section in SECTION_MAPPING:
                cat, _ = SECTION_MAPPING[section]
                if cat in ['homicide', 'kidnapping', 'trafficking', 'acid_attack']:
                    if cat not in category_scores or category_scores[cat] < 0.3:
                        category_scores[cat] = max(category_scores.get(cat, 0), 0.5)
                        evidence[cat].append(f"Auto-added from Section {section}")
        
        # Determine categories
        categories = []
        confidence = 0.0
        reasoning_parts = []
        
        if category_scores:
            max_score = max(category_scores.values())
            if max_score > 0:
                normalized = {k: v/max_score for k, v in category_scores.items()}
                threshold = 0.2
                
                for cat, score in sorted(normalized.items(), key=lambda x: x[1], reverse=True):
                    if score >= threshold:
                        categories.append(cat)
                        if cat in evidence:
                            reasoning_parts.append(f"{cat}: {', '.join(evidence[cat][:2])}")
                
                confidence = max(normalized.values())
        
        if not categories:
            categories = ['unclassified']
            confidence = 0.1
            reasoning_parts = ['No clear category detected']
        
        # Clean up
        if len(categories) > 1:
            if 'irrelevant' in categories:
                categories.remove('irrelevant')
            if 'unclassified' in categories:
                categories.remove('unclassified')
        
        # Special: Ensure pocso is only added if POCSO mentioned
        if 'pocso' in categories:
            pocso_mentioned = False
            for special in special_act_sections:
                if "POCSO" in special:
                    pocso_mentioned = True
                    break
            if not pocso_mentioned and 'pocso' not in acts:
                categories.remove('pocso')
                reasoning_parts.append("Removed POCSO: No POCSO context found")
        
        # Special: Ensure dowry is added if Dowry Act Section 3 found
        if 'dowry' not in categories:
            for special in special_act_sections:
                if "Dowry Prohibition" in special:
                    categories.append('dowry')
                    reasoning_parts.append("Added dowry: Dowry Prohibition Act section found")
                    break
        
        reasoning_str = '; '.join(reasoning_parts) if reasoning_parts else 'Rule-based classification'
        
        return {
            'categories': list(dict.fromkeys(categories)),
            'confidence': round(confidence, 2),
            'reasoning': reasoning_str,
            'keywords_found': keywords,
            'acts_found': acts,
            'ipc_sections': ipc_sections,
            'bns_sections': bns_sections,
            'crpc_sections': crpc_sections,
            'special_act_sections': special_act_sections,
            'evidence': dict(evidence),
            'is_false_pretext': is_false_pretext,
            'method': 'rule_based'
        }


# ============================================================
# MAIN CLASSIFIER
# ============================================================

class Classifier:
    def __init__(self, config: Config):
        self.config = config
        self.rule_based = RuleBasedClassifier()
        self.cache = self._load_cache()
        
        self.stats = {
            'total': 0,
            'processed': 0,
            'cached': 0,
            'by_category': defaultdict(int)
        }
    
    def _load_cache(self) -> Dict:
        if self.config.cache_file.exists():
            try:
                with open(self.config.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_cache(self):
        try:
            with open(self.config.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")
    
    def classify_text(self, case_id: str, text: str) -> Dict:
        if case_id in self.cache:
            self.stats['cached'] += 1
            return self.cache[case_id]
        
        result = self.rule_based.classify(text)
        
        if not result.get('reasoning') or pd.isna(result.get('reasoning')):
            result['reasoning'] = 'Rule-based classification'
        
        self.stats['processed'] += 1
        for cat in result.get('categories', []):
            self.stats['by_category'][cat] += 1
        
        self.cache[case_id] = result
        self._save_cache()
        
        return result
    
    def classify_dataframe(self, df: pd.DataFrame, text_column: str = 'text') -> pd.DataFrame:
        self.stats['total'] = len(df)
        
        logger.info(f"\n📊 Classifying {len(df)} cases with context-aware classifier...")
        
        results = []
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Classifying"):
            case_id = row.get('case_id', f'case_{idx}')
            text = row.get(text_column, '')
            
            if not text or len(text.strip()) < 50:
                result = {
                    'categories': ['unclassified'],
                    'confidence': 0.0,
                    'reasoning': 'Text too short',
                    'keywords_found': [],
                    'acts_found': [],
                    'ipc_sections': [],
                    'bns_sections': [],
                    'crpc_sections': [],
                    'special_act_sections': [],
                    'is_false_pretext': False,
                    'method': 'skipped'
                }
            else:
                result = self.classify_text(case_id, text)
            
            results.append(result)
        
        result_df = pd.DataFrame(results)
        
        if 'reasoning' in result_df.columns:
            result_df['reasoning'] = result_df['reasoning'].fillna('No reasoning available')
        
        final_df = pd.concat([df.reset_index(drop=True), result_df], axis=1)
        
        self._log_stats()
        return final_df
    
    def _log_stats(self):
        logger.info("\n" + "=" * 60)
        logger.info("CLASSIFICATION STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total: {self.stats['total']:,}")
        logger.info(f"Processed: {self.stats['processed']:,}")
        logger.info(f"Cached: {self.stats['cached']:,}")
        
        if self.stats['by_category']:
            logger.info("\nCategory distribution:")
            for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: x[1], reverse=True):
                display_name = CATEGORY_DEFINITIONS.get(cat, {}).get('name', cat)
                logger.info(f"  {display_name}: {count:,}")
        logger.info("=" * 60)


# ============================================================
# OUTPUT FUNCTIONS
# ============================================================

def save_outputs(df: pd.DataFrame, config: Config):
    if 'reasoning' in df.columns:
        df['reasoning'] = df['reasoning'].fillna('No reasoning available')
    
    df.to_csv(config.output_csv, index=False)
    logger.info(f"💾 CSV: {config.output_csv}")
    
    results = []
    for _, row in df.iterrows():
        result = {
            'case_id': row.get('case_id', ''),
            'categories': row.get('categories', []),
            'confidence': float(row.get('confidence', 0)) if pd.notna(row.get('confidence', 0)) else 0.0,
            'reasoning': str(row.get('reasoning', 'No reasoning available')),
            'method': row.get('method', 'unknown'),
            'is_false_pretext': bool(row.get('is_false_pretext', False)),
            'keywords_found': row.get('keywords_found', []),
            'acts_found': row.get('acts_found', []),
            'ipc_sections': row.get('ipc_sections', []),
            'bns_sections': row.get('bns_sections', []),
            'crpc_sections': row.get('crpc_sections', []),
            'special_act_sections': row.get('special_act_sections', [])
        }
        results.append(result)
    
    with open(config.output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 JSON: {config.output_json}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("STAGE 4: CONTEXT-AWARE CLASSIFIER")
    print("Properly disambiguates Section 3")
    print("=" * 70)
    
    config = Config()
    
    print(f"\n📁 Input: {config.input_file}")
    print(f"📁 Output CSV: {config.output_csv}")
    print(f"📁 Output JSON: {config.output_json}")
    
    if not config.input_file.exists():
        print(f"\n❌ Input file not found: {config.input_file}")
        return
    
    df = pd.read_csv(config.input_file)
    logger.info(f"✅ Loaded {len(df)} cases")
    
    try:
        classifier = Classifier(config)
        result_df = classifier.classify_dataframe(df, 'text')
        
        save_outputs(result_df, config)
        
        print("\n" + "=" * 70)
        print("CLASSIFICATION SUMMARY")
        print("=" * 70)
        
        all_cats = []
        for cats in result_df['categories']:
            if isinstance(cats, list):
                all_cats.extend(cats)
            elif isinstance(cats, str):
                try:
                    cats_list = json.loads(cats.replace("'", '"'))
                    all_cats.extend(cats_list)
                except:
                    pass
        
        cat_counts = Counter(all_cats)
        print("\n📊 Category Distribution:")
        for cat, count in cat_counts.most_common():
            display_name = CATEGORY_DEFINITIONS.get(cat, {}).get('name', cat)
            print(f"   {display_name}: {count}")
        
        print(f"\n📁 Output files:")
        print(f"   {config.output_csv}")
        print(f"   {config.output_json}")
        
        print("\n" + "=" * 70)
        print("✅ Stage 4 complete!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()