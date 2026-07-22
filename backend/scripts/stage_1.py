#!/usr/bin/env python3
"""
Stage 1: Candidate Selector for Offences Against Women and Children

This script scans case metadata (title, description, raw_html) and determines
if a case is likely relevant. It uses:
- IPC section references
- BNS section references (Bharatiya Nyaya Sanhita, 2023)
- POCSO detection
- Special Acts (Dowry, DV, Child Marriage, ITPA, JJ Act)
- Legal keywords

Output: CSV of candidate cases for Stage 2 (PDF download)

Author: KAYDA Project
Date: 2026
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

# IPC -> BNS mapping (verified from official correspondence)
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

# Flatten for quick lookup
IPC_TO_CATEGORY = {}
BNS_TO_CATEGORY = {}

for category, mappings in CATEGORY_SECTIONS.items():
    for section in mappings.get("ipc", []):
        IPC_TO_CATEGORY[section] = category
    for section in mappings.get("bns", []):
        BNS_TO_CATEGORY[section] = category

# All IPC sections of interest (for regex extraction)
ALL_IPC_SECTIONS = set()
for mappings in CATEGORY_SECTIONS.values():
    ALL_IPC_SECTIONS.update(mappings.get("ipc", []))

# All BNS sections of interest
ALL_BNS_SECTIONS = set()
for mappings in CATEGORY_SECTIONS.values():
    ALL_BNS_SECTIONS.update(mappings.get("bns", []))

# ============================================================
# CONSTANTS - ACTS AND KEYWORDS
# ============================================================

ACT_KEYWORDS = {
    "pocso": [
        "pocso",
        "protection of children from sexual offences",
        "penetrative sexual assault",
        "aggravated penetrative sexual assault",
        "section 3 pocso",
        "section 4 pocso",
        "section 5 pocso",
        "section 6 pocso",
        "section 7 pocso",
        "section 8 pocso",
        "section 9 pocso",
        "section 10 pocso",
        "sexual assault under pocso"
    ],
    "dowry_prohibition": [
        "dowry prohibition act",
        "dowry act",
        "section 3 of dowry prohibition act",
        "section 4 of dowry prohibition act"
    ],
    "domestic_violence": [
        "domestic violence act",
        "protection of women from domestic violence act",
        "dv act",
        "section 18 of domestic violence act",
        "section 19 of domestic violence act",
        "section 20 of domestic violence act",
        "section 21 of domestic violence act",
        "section 22 of domestic violence act",
        "section 23 of domestic violence act"
    ],
    "child_marriage": [
        "prohibition of child marriage act",
        "child marriage act",
        "section 3 of child marriage act",
        "section 4 of child marriage act",
        "section 5 of child marriage act"
    ],
    "immoral_trafficking": [
        "immoral traffic prevention act",
        "immoral trafficking act",
        "itpa",
        "section 3 of itpa",
        "section 4 of itpa",
        "section 5 of itpa",
        "section 6 of itpa"
    ],
    "juvenile_justice": [
        "juvenile justice act",
        "jj act",
        "care and protection of children act",
        "section 31 of juvenile justice act",
        "section 32 of juvenile justice act",
        "section 33 of juvenile justice act"
    ]
}

# Legal keywords (primary and secondary)
PRIMARY_KEYWORDS = [
    "rape",
    "gang rape",
    "sexual assault",
    "sexual harassment",
    "outraging modesty",
    "modesty",
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

SECONDARY_KEYWORDS = [
    "kidnapping",
    "abduction",
    "minor girl",
    "minor child",
    "child victim",
    "molestation",
    "eve teasing",
    "rape victim",
    "victim compensation",
    "prosecutrix",
    "survivor",
    "woman",
    "wife",
    "girl",
    "female",
    "sexual exploitation",
    "child labour",
    "bonded labour",
    "devadasi",
    "prostitution",
    "pornography",
    "child pornography"
]

# Victim-related terms for context scoring
VICTIM_TERMS = [
    "victim", "survivor", "prosecutrix", "complainant",
    "injured", "aggrieved", "deceased", "minor"
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
    # Convert to lowercase
    text = text.lower()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_sections(text: str) -> Tuple[List[str], List[str]]:
    """
    Extract IPC and BNS sections from text using robust regex.

    Handles formats:
    - u/s 376
    - u/ss 302/34
    - Section 376
    - Sections 302, 34
    - S. 376
    - 376(2)(n)
    - 354-A
    - 302/34 IPC
    - Section 376 of IPC
    - BNS Section 64
    - u/s 64 BNS
    """
    ipc_sections = set()
    bns_sections = set()

    # Normalize text for extraction (preserve case for section numbers)
    text_upper = text.upper()

    # Pattern 1: Standard section references with indicators
    # Matches: u/s, u/ss, Section, S., Sec., etc.
    section_pattern = r'''
        (?:U/S|U/SS|SECTION|SECTIONS|S\.|SEC\.|SS\.)\s*
        (?:OF\s+)?(?:(?:THE\s+)?(?:IPC|BNS)\s+)?
        ([\d,/\-()A-Z]+)
    '''

    matches = re.findall(section_pattern, text_upper, re.VERBOSE)

    for match in matches:
        # Clean up the match
        clean_match = re.sub(r'[^0-9A-Z,/\-()]', '', match)
        # Split by comma or slash
        parts = re.split(r'[,/]', clean_match)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Handle IPC sections
            if part in ALL_IPC_SECTIONS:
                ipc_sections.add(part)
            # Handle BNS sections
            elif part in ALL_BNS_SECTIONS:
                bns_sections.add(part)
            # Handle ranges like 302/34
            elif '/' in part:
                subparts = part.split('/')
                for sub in subparts:
                    sub = sub.strip()
                    if sub in ALL_IPC_SECTIONS:
                        ipc_sections.add(sub)
                    elif sub in ALL_BNS_SECTIONS:
                        bns_sections.add(sub)

    # Pattern 2: Section numbers followed by IPC or BNS
    # Matches: 376 IPC, 64 BNS, 302/34 IPC
    section_with_code = r'''
        \b([0-9A-Z,/\-()]+)\s*(?:OF\s+)?(?:THE\s+)?(IPC|BNS)\b
    '''

    matches = re.findall(section_with_code, text_upper, re.VERBOSE)

    for match_group, code in matches:
        parts = re.split(r'[,/]', match_group)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if code == 'IPC' and part in ALL_IPC_SECTIONS:
                ipc_sections.add(part)
            elif code == 'BNS' and part in ALL_BNS_SECTIONS:
                bns_sections.add(part)

    # Pattern 3: Standalone section numbers in context
    # This is more error-prone, so we're careful
    context_pattern = r'''
        \b(?:SECTION|S\.|SEC\.|SS\.)\s*(?:NO\.?\s*)?
        \s*([0-9]+[A-Z]?)\b
    '''

    matches = re.findall(context_pattern, text_upper, re.VERBOSE)

    for match in matches:
        if match in ALL_IPC_SECTIONS:
            ipc_sections.add(match)
        elif match in ALL_BNS_SECTIONS:
            bns_sections.add(match)

    # Pattern 4: Sections with subsection like 376(2)(n)
    subsection_pattern = r'\b(\d+)[A-Z]?\([^)]+\)'

    matches = re.findall(subsection_pattern, text_upper)

    for match in matches:
        if match in ALL_IPC_SECTIONS:
            ipc_sections.add(match)
        elif match in ALL_BNS_SECTIONS:
            bns_sections.add(match)

    return sorted(ipc_sections), sorted(bns_sections)


def detect_acts(text: str) -> List[str]:
    """Detect which Acts are mentioned in the text"""
    text_lower = normalize_text(text)
    found_acts = []

    for act_name, keywords in ACT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                found_acts.append(act_name)
                break

    return found_acts


def detect_keywords(text: str) -> Tuple[List[str], List[str]]:
    """Detect primary and secondary keywords in text"""
    text_lower = normalize_text(text)
    primary_found = []
    secondary_found = []

    for kw in PRIMARY_KEYWORDS:
        if kw in text_lower:
            primary_found.append(kw)

    for kw in SECONDARY_KEYWORDS:
        if kw in text_lower:
            secondary_found.append(kw)

    return primary_found, secondary_found


def has_victim_context(text: str) -> int:
    """Check if text contains victim-related terms"""
    text_lower = normalize_text(text)
    count = 0
    for term in VICTIM_TERMS:
        if term in text_lower:
            count += 1
    return count


def compute_score(
    ipc_sections: List[str],
    bns_sections: List[str],
    acts: List[str],
    primary_keywords: List[str],
    secondary_keywords: List[str],
    victim_count: int
) -> int:
    """
    Compute a candidate score.

    Scoring:
    - IPC section: 10 points each
    - BNS section: 10 points each
    - Act detected: 10 points each
    - Primary keyword: 3 points each
    - Secondary keyword: 1 point each
    - Victim context: 1 point per term

    Threshold for candidate: score >= 3
    """
    score = 0
    score += len(ipc_sections) * 10
    score += len(bns_sections) * 10
    score += len(acts) * 10
    score += len(primary_keywords) * 3
    score += len(secondary_keywords) * 1
    score += victim_count * 1

    return score


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class CandidateResult:
    """Result of candidate detection for a single case"""
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
    victim_count: int = 0
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
            'victim_context': self.victim_count,
            'categories': ','.join(self.relevant_categories)
        }


# ============================================================
# MAIN PROCESSOR
# ============================================================

class CandidateSelector:
    """Main class for candidate selection"""

    def __init__(self, threshold: int = 3):
        """
        Initialize the candidate selector.

        Args:
            threshold: Minimum score for a case to be considered a candidate
        """
        self.threshold = threshold
        self.stats = {
            'total': 0,
            'candidates': 0,
            'by_category': {},
            'by_act': {},
            'errors': 0
        }

    def process_case(self, row: pd.Series) -> CandidateResult:
        """
        Process a single case row and determine if it's a candidate.

        Args:
            row: Pandas Series containing case metadata

        Returns:
            CandidateResult object
        """
        try:
            # Extract and clean text from all sources
            title = str(row.get('title', ''))
            description = str(row.get('description', ''))
            raw_html = clean_html(row.get('raw_html', ''))

            # Combine all text
            combined_text = f"{title} {description} {raw_html}"

            # Extract sections
            ipc_sections, bns_sections = extract_sections(combined_text)

            # Detect acts
            acts = detect_acts(combined_text)

            # Detect keywords
            primary_kw, secondary_kw = detect_keywords(combined_text)

            # Victim context
            victim_count = has_victim_context(combined_text)

            # Compute score
            score = compute_score(
                ipc_sections,
                bns_sections,
                acts,
                primary_kw,
                secondary_kw,
                victim_count
            )

            # Determine if candidate
            is_candidate = score >= self.threshold

            # Determine relevant categories
            categories = set()

            for section in ipc_sections:
                if section in IPC_TO_CATEGORY:
                    categories.add(IPC_TO_CATEGORY[section])

            for section in bns_sections:
                if section in BNS_TO_CATEGORY:
                    categories.add(BNS_TO_CATEGORY[section])

            # Also derive categories from acts
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
                victim_count=victim_count,
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
        """
        Process an entire DataFrame.

        Args:
            df: Pandas DataFrame with case metadata

        Returns:
            DataFrame with candidate results
        """
        logger.info(f"Processing {len(df)} cases...")

        results = []
        for idx, row in df.iterrows():
            if idx % 1000 == 0:
                logger.info(f"Processed {idx:,} cases")

            result = self.process_case(row)
            results.append(result.to_dict())

        result_df = pd.DataFrame(results)

        # Log statistics
        self._log_stats()

        return result_df

    def _log_stats(self):
        """Log processing statistics"""
        logger.info("=" * 60)
        logger.info("STAGE 1 CANDIDATE SELECTION - STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total cases processed: {self.stats['total']:,}")
        logger.info(f"Candidate cases: {self.stats['candidates']:,}")
        logger.info(f"Candidate rate: {self.stats['candidates']/self.stats['total']*100:.1f}%")
        logger.info(f"Errors: {self.stats['errors']}")

        if self.stats['by_category']:
            logger.info("\nBy Category:")
            for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {cat}: {count:,}")

        if self.stats['by_act']:
            logger.info("\nBy Act:")
            for act, count in sorted(self.stats['by_act'].items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {act}: {count:,}")

        logger.info("=" * 60)


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    """Main entry point"""
    print("=" * 70)
    print("STAGE 1: CANDIDATE SELECTOR")
    print("Offences Against Women and Children")
    print("=" * 70)

    # Configuration
    PROJECT_ROOT = Path(__file__).parent.parent
    DATA_DIR = PROJECT_ROOT / 'data'
    METADATA_DIR = DATA_DIR / 'metadata_2025'

    INPUT_FILE = METADATA_DIR / 'metadata.parquet'
    OUTPUT_FILE = DATA_DIR / 'candidate_cases_2025.csv'

    # Verify input exists
    if not INPUT_FILE.exists():
        logger.error(f"Input file not found: {INPUT_FILE}")
        print(f"\n❌ Input file not found: {INPUT_FILE}")
        print("Please ensure the metadata parquet file exists.")
        return

    logger.info(f"Input file: {INPUT_FILE}")
    logger.info(f"Output file: {OUTPUT_FILE}")

    # Load data
    logger.info("\nLoading metadata...")
    try:
        df = pd.read_parquet(INPUT_FILE)
        logger.info(f"Loaded {len(df):,} records")
        logger.info(f"Columns: {list(df.columns)}")
    except Exception as e:
        logger.error(f"Failed to load parquet: {e}")
        return

    # Process
    logger.info("\nProcessing cases...")
    selector = CandidateSelector(threshold=3)
    result_df = selector.process_dataframe(df)

    # Filter candidates
    candidates = result_df[result_df['candidate'] == True].copy()

    # Sort by score
    candidates = candidates.sort_values('score', ascending=False)

    # Save
    logger.info(f"\nSaving {len(candidates):,} candidates to: {OUTPUT_FILE}")

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Select columns for output
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

    logger.info(f"✅ Saved: {OUTPUT_FILE}")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total cases processed: {len(df):,}")
    print(f"Candidate cases: {len(candidates):,}")
    print(f"Candidate rate: {len(candidates)/len(df)*100:.1f}%")

    print("\n📁 Output saved to:")
    print(f"   {OUTPUT_FILE}")

    # Show top candidates
    if len(candidates) > 0:
        print("\n📋 Top 10 Candidates:")
        for idx, row in candidates.head(10).iterrows():
            print(f"   {row['case_id']}: score={row['score']} | sections={row['ipc_sections']} | acts={row['acts']}")

    print("\n" + "=" * 70)
    print("✅ Stage 1 complete. Ready for Stage 2 PDF download.")


if __name__ == "__main__":
    main()