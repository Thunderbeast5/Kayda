#!/usr/bin/env python3
"""
Stage 1: High-Accuracy Candidate Selector for Offences Against Women and Children

Features:
- Procedural filter (masks CrPC Section 372, CPC sections, Evidence Act).
- Context-aware secondary keyword filtering (e.g., 'wife' in MACT vs. 'wife' in 498A IPC).
- Hard exclusions for commercial, tax, service, and motor accident cases.
- Precision extraction for IPC, BNS, POCSO, and Special Acts.
"""

import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field

import pandas as pd
from bs4 import BeautifulSoup

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
# CONSTANTS - CATEGORY SECTION MAPPINGS
# ============================================================

CATEGORY_SECTIONS = {
    "rape": {
        "ipc": ["375", "376", "376A", "376AB", "376B", "376C", "376D", "376DA", "376DB", "376E"],
        "bns": ["63", "64", "65", "66", "67", "68", "69", "70", "71"]
    },
    "sexual_harassment": {
        "ipc": ["354A"],
        "bns": ["75"]
    },
    "women_modesty": {
        "ipc": ["354", "354B", "509"],
        "bns": ["74", "76", "79"]
    },
    "voyeurism": {
        "ipc": ["354C"],
        "bns": ["77"]
    },
    "stalking": {
        "ipc": ["354D"],
        "bns": ["78"]
    },
    "dowry": {
        "ipc": ["304B", "498A"],
        "bns": ["80", "85"]
    },
    "marriage_offences": {
        "ipc": ["493", "494", "495", "496", "498"],
        "bns": ["81", "82", "83", "84"]
    },
    "kidnapping": {
        "ipc": ["363", "364", "364A", "365", "366", "366A", "366B", "367", "368", "369"],
        "bns": ["137", "138", "140", "142", "87"]
    },
    "trafficking": {
        "ipc": ["370", "370A", "372", "373"],
        "bns": ["143", "144"]
    },
    "acid_attack": {
        "ipc": ["326A", "326B"],
        "bns": ["124"]
    }
}

IPC_TO_CATEGORY = {}
BNS_TO_CATEGORY = {}

for category, mappings in CATEGORY_SECTIONS.items():
    for section in mappings.get("ipc", []):
        IPC_TO_CATEGORY[section] = category
    for section in mappings.get("bns", []):
        BNS_TO_CATEGORY[section] = category

ALL_IPC_SECTIONS = set(IPC_TO_CATEGORY.keys())
ALL_BNS_SECTIONS = set(BNS_TO_CATEGORY.keys())

# Non-criminal acts to mask out before section extraction
NON_RELEVANT_ACTS_PATTERNS = [
    r'NEGOTIABLE\s+INSTRUMENTS?\s+ACT',
    r'N\.?I\.?\s+ACT',
    r'INCOME\s+TAX\s+ACT',
    r'COMPANIES\s+ACT',
    r'COPYRIGHT\s+ACT',
    r'MOTOR\s+VEHICLES?\s+ACT',
    r'ARBITRATION\s+(?:AND\s+CONCILIATION\s+)?ACT',
    r'CONSUMER\s+PROTECTION\s+ACT',
    r'CENTRAL\s+GOODS\s+AND\s+SERVICES\s+TAX\s+ACT',
    r'CGST\s+ACT',
    r'SERVICE\s+TAX',
    r'EXCISE\s+ACT'
]

# Hard Exclusion Subjects / Keywords
HARD_EXCLUSIONS = [
    r'\bMOTOR\s+ACCIDENT\b',
    r'\bMACT\b',
    r'\bINSURANCE\s+CLAIM\b',
    r'\bTAX\s+APPEAL\b',
    r'\bCUSTOMS\s+ACT\b',
    r'\bDISQUALIFICATION\s+OF\s+MP\b',
    r'\bELECTION\s+PETITION\b'
]

# ============================================================
# CONSTANTS - ACTS AND KEYWORDS
# ============================================================

ACT_KEYWORDS = {
    "pocso": [
        "pocso",
        "protection of children from sexual offences",
        "penetrative sexual assault",
        "aggravated penetrative sexual assault",
        "sexual assault under pocso"
    ],
    "dowry_prohibition": [
        "dowry prohibition act",
        "dowry act"
    ],
    "domestic_violence": [
        "domestic violence act",
        "protection of women from domestic violence act",
        "dv act"
    ],
    "child_marriage": [
        "prohibition of child marriage act",
        "child marriage act"
    ],
    "immoral_trafficking": [
        "immoral traffic prevention act",
        "immoral trafficking act",
        "itpa"
    ],
    "juvenile_justice": [
        "juvenile justice act",
        "jj act",
        "care and protection of children act"
    ]
}

PRIMARY_KEYWORDS = [
    "rape",
    "gang rape",
    "sexual assault",
    "sexual harassment",
    "outraging modesty",
    "modesty of woman",
    "stalking",
    "voyeurism",
    "acid attack",
    "dowry death",
    "dowry harassment",
    "cruelty by husband",
    "trafficking",
    "human trafficking",
    "child trafficking",
    "child marriage",
    "female foeticide",
    "sex selection",
    "pre-natal diagnostic"
]

# Strictly requires surrounding context to avoid false hits
CONTEXTUAL_SECONDARY_KEYWORDS = [
    "kidnapping", "abduction", "minor girl", "minor child", 
    "child victim", "molestation", "prosecutrix", "survivor"
]

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def clean_html(html: Any) -> str:
    """Convert HTML to plain text using BeautifulSoup"""
    if pd.isna(html) or html is None:
        return ""
    try:
        if isinstance(html, str):
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(" ", strip=True)
        return str(html)
    except Exception as e:
        logger.debug(f"HTML cleaning failed: {e}")
        return str(html)


def normalize_text(text: str) -> str:
    """Normalize text for consistent searching"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def sanitize_procedural_sections(text: str) -> str:
    """
    Mask procedural code references (CrPC, CPC) so Section 372 CrPC 
    is not confused with IPC Section 372 (trafficking).
    """
    text_upper = text.upper()
    
    # 1. Neutralize non-relevant Acts
    for pattern in NON_RELEVANT_ACTS_PATTERNS:
        text_upper = re.sub(r'(?:SECTION|S\.|SEC\.)\s*\d+[A-Z]?\s*(?:OF\s+)?(?:THE\s+)?' + pattern, ' ', text_upper)
        text_upper = re.sub(pattern + r'\s*(?:SECTION|S\.|SEC\.)?\s*\d+[A-Z]?', ' ', text_upper)

    # 2. Neutralize explicit CrPC / Code of Criminal Procedure section hits
    text_upper = re.sub(r'(?:SECTION|S\.|SEC\.)\s*\d+[A-Z]?\s*(?:OF\s+)?(?:THE\s+)?(?:CODE\s+OF\s+CRIMINAL\s+PROCEDURE|CR\.?P\.?C)', ' ', text_upper)
    text_upper = re.sub(r'(?:CODE\s+OF\s+CRIMINAL\s+PROCEDURE|CR\.?P\.?C)\s*(?:SECTION|S\.|SEC\.)?\s*\d+[A-Z]?', ' ', text_upper)

    # 3. Specific neutralization of Section 372 CrPC (Appeals against acquittal)
    text_upper = re.sub(r'372\s*(?:CRPC|CR\.P\.C|CODE\s+OF\s+CRIMINAL\s+PROCEDURE)', ' ', text_upper)

    return text_upper


def extract_sections(text: str) -> Tuple[List[str], List[str]]:
    """
    Extract IPC and BNS sections with strict context matching.
    """
    ipc_sections = set()
    bns_sections = set()

    # Pre-clean procedural and non-relevant references
    text_sanitized = sanitize_procedural_sections(text)

    # BNS Sections (Must have explicit BNS context)
    bns_patterns = [
        r'(?:BHARATIYA\s+NYAYA\s+SANHITA|BNS)\b.*?\b(?:SECTION|S\.|SEC\.)\s*([0-9]+[A-Z]?)',
        r'(?:SECTION|S\.|SEC\.|U/S|U/SS)\s*([0-9]+[A-Z]?)\s*(?:OF\s+)?(?:THE\s+)?(?:BHARATIYA\s+NYAYA\s+SANHITA|BNS)\b'
    ]

    for pat in bns_patterns:
        matches = re.findall(pat, text_sanitized)
        for match in matches:
            if match in ALL_BNS_SECTIONS:
                bns_sections.add(match)

    # IPC Sections (Explicit IPC mention)
    ipc_explicit_patterns = [
        r'(?:INDIAN\s+PENAL\s+CODE|IPC)\b.*?\b(?:SECTION|S\.|SEC\.)\s*([0-9]+[A-Z]?)',
        r'(?:SECTION|S\.|SEC\.|U/S|U/SS)\s*([0-9]+[A-Z]?)\s*(?:OF\s+)?(?:THE\s+)?(?:INDIAN\s+PENAL\s+CODE|IPC)\b'
    ]

    for pat in ipc_explicit_patterns:
        matches = re.findall(pat, text_sanitized)
        for match in matches:
            if match in ALL_IPC_SECTIONS:
                ipc_sections.add(match)

    # Fallback IPC matching for standard u/s indicators
    general_pattern = r'\b(?:U/S|U/SS|SECTION|SEC\.|S\.)\s*([0-9]+[A-Z]?)\b'
    matches = re.findall(general_pattern, text_sanitized)
    for match in matches:
        if match in ALL_IPC_SECTIONS:
            # Re-verify it is NOT Section 372 without explicit IPC context
            if match == "372" and "IPC" not in text_sanitized and "INDIAN PENAL CODE" not in text_sanitized:
                continue
            ipc_sections.add(match)

    return sorted(ipc_sections), sorted(bns_sections)


def detect_acts(text: str) -> List[str]:
    """Detect specific gender/child protection Acts"""
    text_lower = normalize_text(text)
    found_acts = []

    for act_name, keywords in ACT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                found_acts.append(act_name)
                break

    return found_acts


def detect_keywords(text: str) -> Tuple[List[str], List[str]]:
    """Detect primary and verified secondary keywords"""
    text_lower = normalize_text(text)
    primary_found = []
    secondary_found = []

    for kw in PRIMARY_KEYWORDS:
        if kw in text_lower:
            primary_found.append(kw)

    for kw in CONTEXTUAL_SECONDARY_KEYWORDS:
        if kw in text_lower:
            secondary_found.append(kw)

    return primary_found, secondary_found


def is_hard_excluded(text: str) -> bool:
    """Check if the text matches non-relevant categories (Insurance, Tax, Corporate)"""
    text_upper = text.upper()
    for pattern in HARD_EXCLUSIONS:
        if re.search(pattern, text_upper):
            # Only exclude if no explicit POCSO or 376/498A IPC exists
            if not re.search(r'\b(POCSO|376|498A|304B)\b', text_upper):
                return True
    return False


def compute_score(
    ipc_sections: List[str],
    bns_sections: List[str],
    acts: List[str],
    primary_keywords: List[str],
    secondary_keywords: List[str]
) -> int:
    """Compute precision-weighted candidate score"""
    score = 0
    score += len(ipc_sections) * 10
    score += len(bns_sections) * 10
    score += len(acts) * 10
    score += len(primary_keywords) * 4
    score += len(secondary_keywords) * 1

    return score


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class CandidateResult:
    case_id: str
    title: str
    decision_date: Optional[str]
    path: Optional[str]
    is_candidate: bool
    score: int
    ipc_sections: List[str] = field(default_factory=list)
    bns_sections: List[str] = field(default_factory=list)
    acts: List[str] = field(default_factory=list)
    primary_keywords: List[str] = field(default_factory=list)
    secondary_keywords: List[str] = field(default_factory=list)
    relevant_categories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'case_id': self.case_id,
            'title': self.title,
            'decision_date': self.decision_date,
            'path': self.path,
            'candidate': self.is_candidate,
            'score': self.score,
            'ipc_sections': ','.join(self.ipc_sections),
            'bns_sections': ','.join(self.bns_sections),
            'acts': ','.join(self.acts),
            'primary_keywords': ','.join(self.primary_keywords),
            'secondary_keywords': ','.join(self.secondary_keywords),
            'categories': ','.join(self.relevant_categories)
        }


# ============================================================
# MAIN PROCESSOR
# ============================================================

class CandidateSelector:

    def __init__(self, threshold: int = 4):
        self.threshold = threshold
        self.stats = {
            'total': 0,
            'candidates': 0,
            'by_category': {},
            'by_act': {},
            'errors': 0
        }

    def process_case(self, row: pd.Series) -> CandidateResult:
        try:
            title = str(row.get('title', ''))
            description = str(row.get('description', ''))
            raw_html = clean_html(row.get('raw_html', ''))

            combined_text = f"{title} {description} {raw_html}"

            # Hard Exclusion check
            if is_hard_excluded(combined_text):
                return CandidateResult(
                    case_id=str(row.get('case_id', '')),
                    title=title,
                    decision_date=str(row.get('decision_date', '')),
                    path=str(row.get('path', '')),
                    is_candidate=False,
                    score=0
                )

            # Extract sections and features
            ipc_sections, bns_sections = extract_sections(combined_text)
            acts = detect_acts(combined_text)
            primary_kw, secondary_kw = detect_keywords(combined_text)

            score = compute_score(
                ipc_sections,
                bns_sections,
                acts,
                primary_kw,
                secondary_kw
            )

            is_candidate = score >= self.threshold

            # Map categories based on verified matches
            categories = set()

            for section in ipc_sections:
                if section in IPC_TO_CATEGORY:
                    categories.add(IPC_TO_CATEGORY[section])

            for section in bns_sections:
                if section in BNS_TO_CATEGORY:
                    categories.add(BNS_TO_CATEGORY[section])

            act_to_category = {
                'pocso': 'pocso',
                'dowry_prohibition': 'dowry',
                'domestic_violence': 'domestic_violence',
                'child_marriage': 'child_marriage',
                'immoral_trafficking': 'trafficking',
                'juvenile_justice': 'juvenile_justice'
            }

            for act in acts:
                if act in act_to_category:
                    categories.add(act_to_category[act])

            # Update stats
            self.stats['total'] += 1
            if is_candidate:
                self.stats['candidates'] += 1
                for cat in categories:
                    self.stats['by_category'][cat] = self.stats['by_category'].get(cat, 0) + 1
                for act in acts:
                    self.stats['by_act'][act] = self.stats['by_act'].get(act, 0) + 1

            return CandidateResult(
                case_id=str(row.get('case_id', '')),
                title=title,
                decision_date=str(row.get('decision_date', '')),
                path=str(row.get('path', '')),
                is_candidate=is_candidate,
                score=score,
                ipc_sections=ipc_sections,
                bns_sections=bns_sections,
                acts=acts,
                primary_keywords=primary_kw,
                secondary_keywords=secondary_kw,
                relevant_categories=sorted(categories)
            )

        except Exception as e:
            logger.error(f"Error processing case: {e}")
            self.stats['errors'] += 1
            return CandidateResult(
                case_id=str(row.get('case_id', 'unknown')),
                title=str(row.get('title', 'error')),
                decision_date=None,
                path=None,
                is_candidate=False,
                score=0
            )

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        logger.info(f"Processing {len(df)} cases...")

        results = []
        for idx, row in df.iterrows():
            if idx % 1000 == 0:
                logger.info(f"Processed {idx:,} cases")

            result = self.process_case(row)
            results.append(result.to_dict())

        result_df = pd.DataFrame(results)
        self._log_stats()
        return result_df

    def _log_stats(self):
        logger.info("=" * 60)
        logger.info("STAGE 1 CANDIDATE SELECTION - STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total cases processed: {self.stats['total']:,}")
        logger.info(f"Candidate cases: {self.stats['candidates']:,}")
        if self.stats['total'] > 0:
            logger.info(f"Candidate rate: {self.stats['candidates']/self.stats['total']*100:.1f}%")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("=" * 60)


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    print("=" * 70)
    print("STAGE 1: HIGH-ACCURACY CANDIDATE SELECTOR")
    print("Offences Against Women and Children")
    print("=" * 70)

    PROJECT_ROOT = Path(__file__).parent.parent.parent          # → MOOTCOURT
    BACKEND_DIR = PROJECT_ROOT / 'backend'                     # → MOOTCOURT/backend
    METADATA_BASE1 = BACKEND_DIR / 'data_extraction'                   # → MOOTCOURT/backend/metadata
    METADATA_BASE2 = METADATA_BASE1 / 'metadata'
    METADATA_DIR = METADATA_BASE2/ 'metadata_2022'
    
    
    possible_inputs = [
        METADATA_DIR / 'metadata.parquet',
        METADATA_DIR / 'metadata_parquet',
    ]

    INPUT_FILE = None
    for path in possible_inputs:
        if path.exists():
            INPUT_FILE = path
            break
    
    SEGREGATION = BACKEND_DIR / 'data_extraction'   
    SEGREGATION_DIR = SEGREGATION/'segregation' 
    OUTPUT_FILE = SEGREGATION_DIR / 'cases_2022.csv'

    if not INPUT_FILE:
        logger.error("Input file not found!")
        return

    logger.info(f"Input file: {INPUT_FILE}")
    logger.info(f"Output file: {OUTPUT_FILE}")

    try:
        df = pd.read_parquet(INPUT_FILE)
        logger.info(f"Loaded {len(df):,} records")
    except Exception as e:
        logger.error(f"Failed to load parquet: {e}")
        return

    selector = CandidateSelector(threshold=4)
    result_df = selector.process_dataframe(df)

    candidates = result_df[result_df['candidate'] == True].copy()
    candidates = candidates.sort_values('score', ascending=False)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output_columns = [
        'case_id',
        'title',
        'decision_date',
        'path',
        'score',
        'ipc_sections',
        'bns_sections',
        'acts',
        'primary_keywords',
        'secondary_keywords',
        'categories'
    ]

    candidates[output_columns].to_csv(OUTPUT_FILE, index=False)

    logger.info(f" Saved clean candidates to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()