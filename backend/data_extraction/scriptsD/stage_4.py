#!/usr/bin/env python3
"""
Stage 4: ACCURATE JSON CLASSIFIER V6 - FINAL
Complete separation of IPC, BNS, IT Act, POCSO, POSH, and other Special Acts
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
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
    
    json_input_dir: Path = data_dir / 'json_output_2023'
    output_csv: Path = data_dir / 'classified_accurate_v6_2023.csv'
    output_json: Path = data_dir / 'classified_accurate_v6_2023.json'
    cache_file: Path = data_dir / 'accurate_cache_v6_2023.json'
    
    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# IPC SECTION MAPPING
# ============================================================

IPC_SECTIONS = {
    "302": {"category": "homicide", "name": "Murder"},
    "304": {"category": "homicide", "name": "Culpable homicide"},
    "304A": {"category": "homicide", "name": "Death by negligence"},
    "304B": {"category": "dowry", "name": "Dowry death"},
    "305": {"category": "homicide", "name": "Abetment of suicide"},
    "306": {"category": "homicide", "name": "Abetment of suicide"},
    "201": {"category": "evidence_destruction", "name": "Causing disappearance of evidence"},
    "375": {"category": "rape", "name": "Rape definition"},
    "376": {"category": "rape", "name": "Punishment for rape"},
    "376A": {"category": "rape", "name": "Rape causing death"},
    "376AB": {"category": "rape", "name": "Rape of child under 12"},
    "376B": {"category": "rape", "name": "Rape by husband"},
    "376C": {"category": "rape", "name": "Rape by authority"},
    "376D": {"category": "rape", "name": "Gang rape"},
    "376DA": {"category": "rape", "name": "Gang rape of child"},
    "376DB": {"category": "rape", "name": "Gang rape of child"},
    "376E": {"category": "rape", "name": "Repeat offenders"},
    "354": {"category": "modesty", "name": "Assault to outrage modesty"},
    "354A": {"category": "sexual_harassment", "name": "Sexual harassment"},
    "354B": {"category": "modesty", "name": "Assault to disrobe"},
    "354C": {"category": "voyeurism", "name": "Voyeurism"},
    "354D": {"category": "stalking", "name": "Stalking"},
    "509": {"category": "modesty", "name": "Insult to modesty"},
    "363": {"category": "kidnapping", "name": "Kidnapping"},
    "364": {"category": "kidnapping", "name": "Kidnapping for murder"},
    "364A": {"category": "kidnapping", "name": "Kidnapping for ransom"},
    "365": {"category": "kidnapping", "name": "Kidnapping with intent"},
    "366": {"category": "kidnapping", "name": "Kidnapping for marriage"},
    "366A": {"category": "trafficking", "name": "Procuration of minor"},
    "366B": {"category": "trafficking", "name": "Importation of girl"},
    "367": {"category": "kidnapping", "name": "Kidnapping for slavery"},
    "368": {"category": "kidnapping", "name": "Wrongful confinement"},
    "369": {"category": "kidnapping", "name": "Kidnapping child under 10"},
    "370": {"category": "trafficking", "name": "Trafficking"},
    "370A": {"category": "trafficking", "name": "Exploitation"},
    "372": {"category": "trafficking", "name": "Selling minor for prostitution"},
    "373": {"category": "trafficking", "name": "Buying minor for prostitution"},
    "498A": {"category": "matrimonial_cruelty", "name": "Cruelty by husband"},
    "493": {"category": "false_promise_marriage", "name": "Fraudulent marriage"},
    "326A": {"category": "acid_attack", "name": "Acid attack"},
    "326B": {"category": "acid_attack", "name": "Acid attack attempt"},
    "120B": {"category": "criminal_procedure", "name": "Criminal conspiracy"},
}

# BNS SECTIONS - Only plain numbers (no letters, no parentheses)
BNS_SECTIONS = {
    "101": {"category": "homicide", "name": "Murder"},
    "102": {"category": "homicide", "name": "Culpable homicide"},
    "103": {"category": "homicide", "name": "Death by negligence"},
    "105": {"category": "homicide", "name": "Abetment of suicide"},
    "108": {"category": "homicide", "name": "Abetment of suicide"},
    "63": {"category": "rape", "name": "Rape"},
    "64": {"category": "rape", "name": "Punishment for rape"},
    "65": {"category": "rape", "name": "Rape causing death"},
    "66": {"category": "rape", "name": "Rape of child"},
    "67": {"category": "rape", "name": "Rape by authority"},
    "68": {"category": "rape", "name": "Gang rape"},
    "69": {"category": "rape", "name": "Gang rape of child"},
    "70": {"category": "rape", "name": "Repeat offenders"},
    "71": {"category": "rape", "name": "Rape by husband"},
    "74": {"category": "modesty", "name": "Outraging modesty"},
    "75": {"category": "sexual_harassment", "name": "Sexual harassment"},
    "76": {"category": "modesty", "name": "Assault to disrobe"},
    "77": {"category": "voyeurism", "name": "Voyeurism"},
    "78": {"category": "stalking", "name": "Stalking"},
    "79": {"category": "modesty", "name": "Insult to modesty"},
    "80": {"category": "dowry", "name": "Dowry death"},
    "85": {"category": "matrimonial_cruelty", "name": "Cruelty by husband"},
    "86": {"category": "dowry", "name": "Dowry harassment"},
    "137": {"category": "kidnapping", "name": "Kidnapping"},
    "138": {"category": "kidnapping", "name": "Kidnapping for ransom"},
    "140": {"category": "kidnapping", "name": "Kidnapping for murder"},
    "142": {"category": "kidnapping", "name": "Kidnapping for marriage"},
    "87": {"category": "kidnapping", "name": "Wrongful confinement"},
    "143": {"category": "trafficking", "name": "Trafficking"},
    "144": {"category": "trafficking", "name": "Exploitation"},
    "124": {"category": "acid_attack", "name": "Acid attack"},
}

# IT ACT SECTIONS
IT_ACT_SECTIONS = {
    "66": {"category": "cyber_crime", "name": "Computer-related offenses"},
    "66A": {"category": "cyber_crime", "name": "Offensive messages"},
    "66B": {"category": "cyber_crime", "name": "Receiving stolen computer"},
    "66C": {"category": "cyber_crime", "name": "Identity theft"},
    "66D": {"category": "cyber_crime", "name": "Cheating by impersonation"},
    "66E": {"category": "cyber_crime", "name": "Privacy violation"},
    "66F": {"category": "cyber_crime", "name": "Cyber terrorism"},
    "67": {"category": "cyber_crime", "name": "Obscene content"},
    "67A": {"category": "cyber_crime", "name": "Sexually explicit content"},
    "67B": {"category": "cyber_crime", "name": "Child pornography"},
}

# POCSO SECTIONS - Base sections (without letters/parentheses)
POCSO_SECTIONS = {
    "3": {"category": "pocso", "name": "Penetrative sexual assault"},
    "4": {"category": "pocso", "name": "Punishment for penetrative assault"},
    "5": {"category": "pocso", "name": "Aggravated penetrative assault"},
    "6": {"category": "pocso", "name": "Punishment for aggravated assault"},
    "7": {"category": "pocso", "name": "Sexual assault"},
    "8": {"category": "pocso", "name": "Punishment for sexual assault"},
    "9": {"category": "pocso", "name": "Aggravated sexual assault"},
    "10": {"category": "pocso", "name": "Punishment for aggravated sexual assault"},
    "11": {"category": "pocso", "name": "Sexual harassment"},
    "12": {"category": "pocso", "name": "Punishment for sexual harassment"},
    "14": {"category": "pocso", "name": "Using child for pornographic purposes"},
    "15": {"category": "pocso", "name": "Punishment for using child for pornography"},
    "16": {"category": "pocso", "name": "Abetment"},
    "17": {"category": "pocso", "name": "Attempt"},
}

# POSH ACT SECTIONS (Sexual Harassment of Women at Workplace Act, 2013)
POSH_SECTIONS = {
    "2": {"category": "workplace_sexual_harassment", "name": "Definitions"},
    "3": {"category": "workplace_sexual_harassment", "name": "Prevention of sexual harassment"},
    "4": {"category": "workplace_sexual_harassment", "name": "Internal Complaints Committee"},
    "9": {"category": "workplace_sexual_harassment", "name": "Complaint of sexual harassment"},
    "11": {"category": "workplace_sexual_harassment", "name": "Inquiry into complaint"},
    "13": {"category": "workplace_sexual_harassment", "name": "Action on inquiry report"},
    "18": {"category": "workplace_sexual_harassment", "name": "Appeal"},
    "26": {"category": "workplace_sexual_harassment", "name": "Penalty for non-compliance"},
}


# ============================================================
# CATEGORY DISPLAY NAMES
# ============================================================

CATEGORY_DISPLAY = {
    "homicide": "Homicide / Murder",
    "rape": "Rape / Gang Rape",
    "kidnapping": "Kidnapping / Abduction",
    "modesty": "Outraging Modesty",
    "sexual_harassment": "Sexual Harassment",
    "dowry": "Dowry Death / Harassment",
    "matrimonial_cruelty": "Matrimonial Cruelty",
    "trafficking": "Human Trafficking",
    "pocso": "POCSO / Child Sexual Abuse",
    "acid_attack": "Acid Attack",
    "voyeurism": "Voyeurism",
    "stalking": "Stalking",
    "false_promise_marriage": "False Promise of Marriage",
    "domestic_violence": "Domestic Violence",
    "child_marriage": "Child Marriage",
    "cyber_crime": "Cyber Crime (IT Act)",
    "juvenile_justice": "Juvenile Justice",
    "reproductive_rights": "Reproductive Rights",
    "sex_selection": "Sex Selection / Foeticide",
    "quashing_proceedings": "Quashing of Proceedings",
    "sentencing": "Sentencing / Punishment",
    "criminal_procedure": "Criminal Procedure",
    "evidence_destruction": "Destruction of Evidence",
    "workplace_sexual_harassment": "Workplace Sexual Harassment (POSH Act)",
    "irrelevant": "Irrelevant",
}


# ============================================================
# CLEAN SECTION EXTRACTOR
# ============================================================

class CleanSectionExtractor:
    """Extracts sections and correctly classifies them into IPC, BNS, IT Act, POCSO, POSH"""
    
    def __init__(self):
        self.ipc_sections = set(IPC_SECTIONS.keys())
        self.bns_sections = set(BNS_SECTIONS.keys())
        self.it_act_sections = set(IT_ACT_SECTIONS.keys())
        self.pocso_sections = set(POCSO_SECTIONS.keys())
        self.posh_sections = set(POSH_SECTIONS.keys())
        
        # BNS sections are only 2-3 digit numbers without letters
        self.bns_pattern = r'^(6[3-9]|7[0-9]|8[0-7]|10[1-8]|124|13[7-9]|14[0-4])$'
    
    def extract(self, text: str) -> Dict:
        """Extract sections from text and categorize them"""
        text_upper = text.upper()
        
        result = {
            'ipc': [],
            'bns': [],
            'it_act': [],
            'pocso': [],
            'posh': [],
            'ipc_with_subsections': [],
            'section_details': []
        }
        
        # Pre-compiled patterns for better performance
        patterns = [
            # 1. POCSO: "S. 6 r/w S. 5 (m) of POCSO Act"
            r'\bS\.\s+([0-9]+[A-Z]?[\(\)]?[a-z]?)\s+r/w\s+S\.\s+([0-9]+[A-Z]?[\(\)]?[a-z]?)\s+of\s+POCSO\s+Act\b',
            
            # 2. POCSO: "Section 5(m) of POCSO Act"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.)\s+([0-9]+[A-Z]?[\(\)]?[a-z]?)\s+of\s+POCSO\s+Act\b',
            
            # 3. POCSO: "Section 3 POCSO" or "S. 4 POCSO"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.|U/S|U/SS)\s+(?:OF\s+)?(?:THE\s+)?(?:POCSO)\s*\b([0-9]{1,2}[A-Z]?[\(\)]?[a-z]?)\b',
            
            # 4. POSH: "Section 3 of POSH Act" or "S. 4 POSH"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.)\s+([0-9]{1,2})\s+of\s+(?:POSH|Sexual Harassment of Women at Workplace)\s+Act\b',
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.|U/S|U/SS)\s+(?:OF\s+)?(?:THE\s+)?(?:POSH)\s*\b([0-9]{1,2})\b',
            
            # 5. IT Act: "Section 66C of IT Act"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.)\s+([0-9]{2}[A-Z]?)\s+of\s+(?:IT|Information Technology)\s+Act\b',
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.|U/S|U/SS)\s+(?:OF\s+)?(?:THE\s+)?(?:IT\s+ACT)\s*\b([0-9]{2}[A-Z]?)\b',
            
            # 6. IPC with subsections: "Section 376(2)(g)" or "376(2)(g) IPC"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.|U/S|U/SS)\s+(?:OF\s+)?(?:THE\s+)?(?:IPC\s+)?\b([0-9]{2,3}\([0-9]\)[\(]?[a-z]?[\)]?)\b',
            r'\b([0-9]{2,3}\([0-9]\)[\(]?[a-z]?[\)]?)\s+(?:OF\s+)?(?:THE\s+)?(?:IPC)\b',
            
            # 7. IPC: "Section 302", "Section 376A", "S. 498A"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.|U/S|U/SS)\s+(?:OF\s+)?(?:THE\s+)?(?:IPC\s+)?\b([0-9]{2,3}[A-Z]?)\b',
            r'\b([0-9]{2,3}[A-Z]?)\s+(?:OF\s+)?(?:THE\s+)?(?:IPC)\b',
            
            # 8. BNS: "BNS Section 63", "Section 64 BNS"
            r'\b(?:SECTION|SECTIONS|S\.|SEC\.|U/S|U/SS)\s+(?:OF\s+)?(?:THE\s+)?(?:BNS)\s*\b([0-9]{2,3})\b',
            r'\b([0-9]{2,3})\s+(?:OF\s+)?(?:THE\s+)?(?:BNS)\b',
            
            # 9. Standalone "u/s 302" or "S. 366" (generic)
            r'\bU/S\s+([0-9]{2,3}[A-Z]?)\b',
            r'\bS\.\s+([0-9]{2,3}[A-Z]?)\b',
        ]
        
        processed = set()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper, re.IGNORECASE)
            for match in matches:
                # Handle tuple matches (for r/w patterns)
                if isinstance(match, tuple):
                    sections = list(match)
                else:
                    sections = [match]
                
                for section in sections:
                    section = section.strip()
                    if not section or section in processed:
                        continue
                    processed.add(section)
                    
                    # ---- BNS detection ----
                    if re.match(self.bns_pattern, section) and section in self.bns_sections:
                        result['bns'].append(section)
                        result['section_details'].append(f"BNS {section}: {BNS_SECTIONS[section]['name']}")
                        continue
                    
                    # ---- IT Act detection ----
                    if section in self.it_act_sections:
                        result['it_act'].append(section)
                        result['section_details'].append(f"IT Act, 2000 {section}: {IT_ACT_SECTIONS[section]['name']}")
                        continue
                    
                    # ---- POCSO detection ----
                    # Clean the section: remove letters and parentheses to get base
                    base_section = re.sub(r'\([^)]*\)', '', section)  # remove (m)
                    base_section = re.sub(r'[A-Za-z]', '', base_section)  # remove letters
                    if base_section in self.pocso_sections:
                        result['pocso'].append(section)
                        result['section_details'].append(f"POCSO Act, 2012 {section}: {POCSO_SECTIONS[base_section]['name']}")
                        continue
                    
                    # ---- POSH detection ----
                    if section.isdigit() and section in self.posh_sections:
                        result['posh'].append(section)
                        result['section_details'].append(f"POSH Act, 2013 {section}: {POSH_SECTIONS[section]['name']}")
                        continue
                    
                    # ---- IPC with subsections ----
                    if '(' in section:
                        base = re.sub(r'\([^)]*\)', '', section)
                        if base in self.ipc_sections:
                            result['ipc_with_subsections'].append(section)
                            result['section_details'].append(f"IPC {section}: {IPC_SECTIONS[base]['name']}")
                            continue
                    
                    # ---- IPC detection ----
                    if section in self.ipc_sections:
                        result['ipc'].append(section)
                        result['section_details'].append(f"IPC {section}: {IPC_SECTIONS[section]['name']}")
                        continue
                    
                    # ---- Fallback: numeric section ----
                    if section.isdigit():
                        if len(section) >= 2 and section in self.bns_sections:
                            result['bns'].append(section)
                            result['section_details'].append(f"BNS {section}: {BNS_SECTIONS[section]['name']}")
                        elif section in self.ipc_sections:
                            result['ipc'].append(section)
                            result['section_details'].append(f"IPC {section}: {IPC_SECTIONS[section]['name']}")
        
        # Deduplicate and sort
        result['ipc'] = sorted(list(dict.fromkeys(result['ipc'])))
        result['bns'] = sorted(list(dict.fromkeys(result['bns'])))
        result['it_act'] = sorted(list(dict.fromkeys(result['it_act'])))
        result['pocso'] = sorted(list(dict.fromkeys(result['pocso'])))
        result['posh'] = sorted(list(dict.fromkeys(result['posh'])))
        result['ipc_with_subsections'] = sorted(list(dict.fromkeys(result['ipc_with_subsections'])))
        result['section_details'] = sorted(list(dict.fromkeys(result['section_details'])))
        
        return result


# ============================================================
# MAIN ACCURATE CLASSIFIER
# ============================================================

class AccurateClassifier:
    def __init__(self, config: Config):
        self.config = config
        self.section_extractor = CleanSectionExtractor()
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
    
    def _extract_keywords_from_text(self, text: str) -> List[str]:
        keywords = []
        patterns = [
            r'(?:Keywords|Key Words|Keyterms)\s*[:;]\s*([^\n]+(?:\n\s*[A-Za-z,; ]+)*)',
            r'(?:List of Keywords|List of Key Words)\s*[:;]?\s*(.*?)(?=\n\n|\n[A-Z]|$)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1)
                parts = re.split(r'[,;]\s*|\n\s*[-•*]\s*|\n', content)
                for part in parts:
                    part = part.strip()
                    if part and len(part) > 1:
                        keywords.append(part)
                break
        return keywords
    
    def _extract_acts_from_text(self, text: str) -> List[str]:
        acts = []
        patterns = [
            r'(?:List of Acts|Acts|Act)\s*[:;]\s*([^\n]+)',
            r'(?:Acts)\s*[:;]?\s*(.*?)(?=\n\n|\n[A-Z]|$)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1)
                parts = re.split(r'[,;]\s*|\n', content)
                for part in parts:
                    part = part.strip()
                    if part and len(part) > 2:
                        acts.append(part)
                break
        return acts
    
    def _detect_special_act(self, text: str, acts: List[str]) -> List[str]:
        """Detect special acts like POSH, DV Act, etc."""
        text_lower = text.lower()
        categories = []
        
        # POSH Act
        posh_indicators = [
            'sexual harassment of women at workplace',
            'posh act',
            'prevention, prohibition and redressal',
            'local complaint committee',
            'workplace harassment'
        ]
        if any(ind in text_lower for ind in posh_indicators):
            categories.append('workplace_sexual_harassment')
        
        # Domestic Violence Act
        dv_indicators = ['domestic violence act', 'protection of women from domestic violence', 'pwdva']
        if any(ind in text_lower for ind in dv_indicators):
            categories.append('domestic_violence')
        
        # Child Marriage Act
        cm_indicators = ['child marriage act', 'prohibition of child marriage', 'pcm act']
        if any(ind in text_lower for ind in cm_indicators):
            categories.append('child_marriage')
        
        # Juvenile Justice Act
        jj_indicators = ['juvenile justice act', 'jj act', 'care and protection']
        if any(ind in text_lower for ind in jj_indicators):
            categories.append('juvenile_justice')
        
        # PCPNDT Act
        pcpndt_indicators = ['pcpndt', 'sex selection', 'female foeticide', 'pre-natal']
        if any(ind in text_lower for ind in pcpndt_indicators):
            categories.append('sex_selection')
        
        # MTP Act
        mtp_indicators = ['medical termination of pregnancy', 'mtp act', 'abortion']
        if any(ind in text_lower for ind in mtp_indicators):
            categories.append('reproductive_rights')
        
        return list(dict.fromkeys(categories))
    
    def classify_case(self, case_data: Dict) -> Dict:
        case_id = case_data.get('case_id', '')
        
        if case_id in self.cache:
            self.stats['cached'] += 1
            return self.cache[case_id]
        
        # Extract fields
        issue = case_data.get('issue_for_consideration', '')
        headnotes = case_data.get('headnotes', '')
        keywords = case_data.get('list_of_keywords', [])
        acts = case_data.get('list_of_acts', [])
        judgment = case_data.get('judgment_text', '')
        full_text = case_data.get('full_text', '')
        
        if not keywords and full_text:
            keywords = self._extract_keywords_from_text(full_text)
        if not acts and full_text:
            acts = self._extract_acts_from_text(full_text)
        
        combined_text = f"{issue} {headnotes} {judgment} {full_text}"
        combined_lower = combined_text.lower()
        
        # Extract sections
        sections = self.section_extractor.extract(combined_text)
        
        ipc_sections = sections['ipc']
        bns_sections = sections['bns']
        it_act_sections = sections['it_act']
        pocso_sections = sections['pocso']
        posh_sections = sections['posh']
        ipc_with_subsections = sections['ipc_with_subsections']
        section_details = sections['section_details']
        
        # Special acts
        special_act_categories = self._detect_special_act(combined_text, acts)
        
        # Score categories
        category_scores = defaultdict(float)
        evidence = defaultdict(list)
        
        # IPC sections
        for section in ipc_sections + ipc_with_subsections:
            base = re.sub(r'\([^)]*\)', '', section)
            if base in IPC_SECTIONS:
                cat = IPC_SECTIONS[base]['category']
                category_scores[cat] += 2.0
                evidence[cat].append(f"IPC {section}")
        
        # BNS sections
        for section in bns_sections:
            if section in BNS_SECTIONS:
                cat = BNS_SECTIONS[section]['category']
                category_scores[cat] += 2.0
                evidence[cat].append(f"BNS {section}")
        
        # IT Act sections
        for section in it_act_sections:
            if section in IT_ACT_SECTIONS:
                cat = IT_ACT_SECTIONS[section]['category']
                category_scores[cat] += 2.0
                evidence[cat].append(f"IT Act {section}")
        
        # POCSO sections
        for section in pocso_sections:
            cat = POCSO_SECTIONS.get(re.sub(r'\([^)]*\)', '', section), {}).get('category')
            if cat:
                category_scores[cat] += 2.0
                evidence[cat].append(f"POCSO {section}")
        
        # POSH sections
        for section in posh_sections:
            if section in POSH_SECTIONS:
                cat = POSH_SECTIONS[section]['category']
                category_scores[cat] += 2.0
                evidence[cat].append(f"POSH {section}")
        
        # Special acts
        for cat in special_act_categories:
            category_scores[cat] += 2.0
            evidence[cat].append("Special Act detected")
        
        # Keywords
        keyword_map = {
            'murder': 'homicide', 'homicide': 'homicide', 'death': 'homicide',
            'rape': 'rape', 'gang rape': 'rape', 'sexual assault': 'rape',
            'kidnapping': 'kidnapping', 'abduction': 'kidnapping',
            'pocso': 'pocso', 'child sexual': 'pocso',
            'dowry': 'dowry', 'dowry death': 'dowry',
            'cruelty': 'matrimonial_cruelty',
            'evidence': 'criminal_procedure', 'forensic': 'criminal_procedure',
            'sentencing': 'sentencing', 'sentence': 'sentencing',
            'cyber': 'cyber_crime', 'identity theft': 'cyber_crime',
            'sexual harassment': 'workplace_sexual_harassment',
            'workplace': 'workplace_sexual_harassment',
            'posh': 'workplace_sexual_harassment'
        }
        for kw in keywords:
            kw_lower = kw.lower()
            for key, cat in keyword_map.items():
                if key in kw_lower:
                    category_scores[cat] += 0.5
                    evidence[cat].append(f"Keyword: {kw}")
                    break
        
        # Acts
        for act in acts:
            act_lower = act.lower()
            if 'sexual harassment of women at workplace' in act_lower or 'posh act' in act_lower:
                category_scores['workplace_sexual_harassment'] += 2.0
                evidence['workplace_sexual_harassment'].append(f"Act: {act}")
            elif 'pocso' in act_lower or 'protection of children' in act_lower:
                category_scores['pocso'] += 1.0
                evidence['pocso'].append(f"Act: {act}")
            elif 'dowry prohibition' in act_lower:
                category_scores['dowry'] += 1.0
                evidence['dowry'].append(f"Act: {act}")
            elif 'domestic violence' in act_lower:
                category_scores['domestic_violence'] += 1.0
                evidence['domestic_violence'].append(f"Act: {act}")
            elif 'information technology' in act_lower or 'it act' in act_lower:
                category_scores['cyber_crime'] += 1.0
                evidence['cyber_crime'].append(f"Act: {act}")
        
        # Issue analysis
        issue_lower = issue.lower()
        if any(kw in issue_lower for kw in ['murder', '302', 'death']):
            category_scores['homicide'] += 3.0
            evidence['homicide'].append("Issue mentions murder/death")
        if any(kw in issue_lower for kw in ['rape', 'gang rape', '376']):
            category_scores['rape'] += 3.0
            evidence['rape'].append("Issue mentions rape")
        if any(kw in issue_lower for kw in ['kidnap', 'abduction', '366', '363']):
            category_scores['kidnapping'] += 3.0
            evidence['kidnapping'].append("Issue mentions kidnapping/abduction")
        if any(kw in issue_lower for kw in ['pocso', 'child sexual']):
            category_scores['pocso'] += 3.0
            evidence['pocso'].append("Issue mentions POCSO")
        if any(kw in issue_lower for kw in ['sexual harassment', 'workplace', 'posh', 'hostile work']):
            category_scores['workplace_sexual_harassment'] += 3.0
            evidence['workplace_sexual_harassment'].append("Issue mentions workplace sexual harassment")
        if any(kw in issue_lower for kw in ['it act', 'cyber', '66c', 'identity theft']):
            category_scores['cyber_crime'] += 3.0
            evidence['cyber_crime'].append("Issue mentions IT Act/cyber crime")
        if any(kw in issue_lower for kw in ['201', 'disappearance of evidence']):
            category_scores['evidence_destruction'] += 3.0
            evidence['evidence_destruction'].append("Issue mentions evidence destruction")
        
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
            if 'sexual harassment' in combined_lower and 'workplace' in combined_lower:
                categories.append('workplace_sexual_harassment')
                confidence = 0.6
                reasoning_parts.append("Detected workplace sexual harassment")
            elif 'pocso' in combined_lower:
                categories.append('pocso')
                confidence = 0.6
                reasoning_parts.append("Detected POCSO")
        
        if not categories:
            categories = ['unclassified']
            confidence = 0.1
            reasoning_parts = ['No clear category detected']
        
        categories = list(dict.fromkeys(categories))
        if len(categories) > 1:
            if 'irrelevant' in categories:
                categories.remove('irrelevant')
            if 'unclassified' in categories:
                categories.remove('unclassified')
        
        reasoning_str = '; '.join(reasoning_parts) if reasoning_parts else 'Rule-based classification'
        
        all_sections = ipc_sections + bns_sections + it_act_sections + pocso_sections + posh_sections + ipc_with_subsections
        
        result = {
            'case_id': case_id,
            'categories': categories,
            'confidence': round(confidence, 2),
            'reasoning': reasoning_str,
            'ipc_sections': ipc_sections,
            'bns_sections': bns_sections,
            'it_act_sections': it_act_sections,
            'pocso_sections': pocso_sections,
            'posh_sections': posh_sections,
            'ipc_with_subsections': ipc_with_subsections,
            'all_sections': all_sections,
            'section_details': section_details,
            'keywords_found': keywords,
            'acts_found': acts,
            'category_scores': dict(category_scores),
            'method': 'accurate_classifier'
        }
        
        self.stats['processed'] += 1
        for cat in categories:
            self.stats['by_category'][cat] += 1
        
        self.cache[case_id] = result
        self._save_cache()
        
        return result
    
    def process_all_jsons(self) -> pd.DataFrame:
        json_files = list(self.config.json_input_dir.glob('*.json'))
        
        if not json_files:
            logger.error(f"No JSON files found in: {self.config.json_input_dir}")
            return pd.DataFrame()
        
        self.stats['total'] = len(json_files)
        
        logger.info(f"\n📊 Processing {len(json_files)} JSON files...")
        
        results = []
        for json_path in tqdm(json_files, desc="Classifying"):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
                
                result = self.classify_case(case_data)
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error processing {json_path.name}: {e}")
                results.append({
                    'case_id': json_path.stem,
                    'categories': ['error'],
                    'confidence': 0.0,
                    'reasoning': f'Error: {e}',
                    'ipc_sections': [],
                    'bns_sections': [],
                    'it_act_sections': [],
                    'pocso_sections': [],
                    'posh_sections': [],
                    'ipc_with_subsections': [],
                    'all_sections': [],
                    'section_details': [],
                    'keywords_found': [],
                    'acts_found': [],
                    'category_scores': {},
                    'method': 'error'
                })
        
        df = pd.DataFrame(results)
        self._log_stats()
        return df
    
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
                display_name = CATEGORY_DISPLAY.get(cat, cat)
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
            'ipc_sections': row.get('ipc_sections', []),
            'bns_sections': row.get('bns_sections', []),
            'it_act_sections': row.get('it_act_sections', []),
            'pocso_sections': row.get('pocso_sections', []),
            'posh_sections': row.get('posh_sections', []),
            'ipc_with_subsections': row.get('ipc_with_subsections', []),
            'all_sections': row.get('all_sections', []),
            'section_details': row.get('section_details', []),
            'keywords_found': row.get('keywords_found', []),
            'acts_found': row.get('acts_found', []),
            'method': row.get('method', 'unknown')
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
    print("STAGE 4: ACCURATE JSON CLASSIFIER V6 - FINAL")
    print("IPC | BNS | IT Act | POCSO | POSH | Special Acts")
    print("=" * 70)
    
    config = Config()
    
    print(f"\n📁 JSON input: {config.json_input_dir}")
    print(f"📁 Output CSV: {config.output_csv}")
    print(f"📁 Output JSON: {config.output_json}")
    
    if not config.json_input_dir.exists():
        print(f"\n❌ JSON directory not found: {config.json_input_dir}")
        return
    
    json_files = list(config.json_input_dir.glob('*.json'))
    if not json_files:
        print(f"\n❌ No JSON files found in: {config.json_input_dir}")
        return
    
    print(f"\n📄 Found {len(json_files)} JSON files")
    
    try:
        classifier = AccurateClassifier(config)
        result_df = classifier.process_all_jsons()
        
        if not result_df.empty:
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
                display_name = CATEGORY_DISPLAY.get(cat, cat)
                print(f"   {display_name}: {count}")
            
            if len(result_df) > 0:
                sample_row = result_df.iloc[0]
                print(f"\n📋 Sample Classification:")
                print(f"   Case: {sample_row.get('case_id', '')}")
                print(f"   Categories: {sample_row.get('categories', [])}")
                if sample_row.get('section_details'):
                    print(f"   Sections: {sample_row['section_details'][:3]}")
            
            print(f"\n📁 Output files:")
            print(f"   {config.output_csv}")
            print(f"   {config.output_json}")
            
            print("\n" + "=" * 70)
            print("✅ Stage 4 complete!")
        else:
            print("\n❌ No results generated.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()