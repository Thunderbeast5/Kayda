#!/usr/bin/env python3
"""
Stage 3: HIGHLY ACCURATE PDF TO JSON EXTRACTOR FOR 2017 SUPREME COURT JUDGMENTS

This script is specifically optimized for the 2017 Supreme Court PDF structure
which uses a distinctive format with proper headings and structured sections.

Key improvements:
- Better handling of 2017 PDF structure with explicit section markers
- Improved section extraction for IPC, BNS, POCSO, IT Act sections
- More accurate parsing of judges, appearances, dates
- Better handling of headnotes and case metadata
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm
import pdfplumber
import fitz  # PyMuPDF

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
    # __file__ is in backend/data_extraction/scriptsD/stage_3.py
    # parent.parent.parent goes to project root (MootCourt)
    project_root: Path = Path(__file__).parent.parent.parent.parent
    
    # Input PDFs
    pdf_input_dir: Path = project_root / 'backend' / 'data_extraction' / 'pdfs' / 'pdf_downloads_2017'
    
    # Output directories
    json_output_dir: Path = project_root / 'backend' / 'data_extraction' / 'json' / 'json_output_2017'
    summary_file: Path = project_root / 'backend' / 'data_extraction' / 'extraction_summary_2017.csv'
    
    # Extraction settings
    max_pages: int = 150
    num_workers: int = 4
    
    def __post_init__(self):
        self.json_output_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# IMPROVED PDF PARSER FOR 2017 SUPREME COURT JUDGMENTS
# ============================================================

class SupremeCourtPDFParser2017:
    """Enhanced parser specifically for 2017 SC judgment structure with PRECISION extraction"""
    
    # PRECISION EXTRACTION - Present case indicators
    PRESENT_CASE_INDICATORS = [
        r'\bthe appellant\b',
        r'\bthe accused\b',
        r'\bthe present case\b',
        r'\bthe respondent\b',
        r'\bthe trial court\b',
        r'\bthe prosecutrix\b',
        r'\bthe victim\b',
        r'\bthe fir\b',
        r'\bthe incident\b',
        r'\bcharged (?:with|under)\b',
        r'\bconvicted (?:of|under)\b',
        r'\bsentence(?:d)? (?:to|under)\b',
        r'\bregistered under\b',
        r'\boffence (?:punishable )?under\b',
        r'\bprosecuted under\b',
    ]
    
    # PRECISION EXTRACTION - Cited case indicators (to filter out)
    CITED_CASE_INDICATORS = [
        r'\bv\.?\s+State of\b',
        r'\bv\.?\s+Union of\b',
        r'\bin\s+\w+\s+v\.?\s+\w+',
        r'\bas held in\b',
        r'\bin the case of\b',
        r'\breferred to\b',
        r'\brelied upon\b',
        r'\bcited\b',
        r'\bquoted\b',
        r'\billustration\b',
        r'\bexample\b',
        r'\bparagraph \d+\b',
    ]
    
    def __init__(self, config: Config):
        self.config = config
    
    def is_present_case_context(self, text_chunk: str) -> bool:
        """
        Check if text chunk is about present case (PRECISION RULE).
        Returns True only if context clearly indicates present case.
        """
        text_lower = text_chunk.lower()
        
        # First check: If cited case indicators found, definitely NOT present case
        for pattern in self.CITED_CASE_INDICATORS:
            if re.search(pattern, text_lower):
                return False
        
        # Second check: Look for present case indicators
        for pattern in self.PRESENT_CASE_INDICATORS:
            if re.search(pattern, text_lower):
                return True
        
        # If no clear indicators, default to False (PRECISION > RECALL)
        return False
    
    def filter_sections_by_context(self, text: str, sections_dict: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
        """
        Filter extracted sections to keep ONLY those in present case context.
        This removes sections from cited precedents.
        """
        # Context window (characters around section mention)
        CONTEXT_WINDOW = 300
        
        filtered = {key: set() for key in sections_dict.keys()}
        
        # For each section type, verify each section appears in present case context
        for section_type, sections in sections_dict.items():
            for section in sections:
                # Find all occurrences of this section in text
                # Look for patterns like "Section XXX", "s. XXX", "u/s XXX"
                section_patterns = [
                    rf'\b(?:Section|Sections|ss?\.|u/s)\s+{re.escape(section)}\b',
                    rf'\b{re.escape(section)}\s+(?:IPC|BNS|POCSO|CrPC)',
                ]
                
                found_in_present_case = False
                for pattern in section_patterns:
                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        # Extract context around this mention
                        start = max(0, match.start() - CONTEXT_WINDOW)
                        end = min(len(text), match.end() + CONTEXT_WINDOW)
                        context = text[start:end]
                        
                        # Check if this context is about present case
                        if self.is_present_case_context(context):
                            found_in_present_case = True
                            break
                    
                    if found_in_present_case:
                        break
                
                # Only include if found in present case context
                if found_in_present_case:
                    filtered[section_type].add(section)
        
        return filtered

    def extract_clean_text(self, pdf_path: Path) -> Tuple[str, int, bool]:
        """Extract clean full text using PyMuPDF with layout preservation"""
        full_text = ""
        pages_count = 0
        is_digital = False

        try:
            doc = fitz.open(pdf_path)
            pages_count = len(doc)
            text_blocks = []

            for page_idx in range(min(pages_count, self.config.max_pages)):
                page = doc[page_idx]
                blocks = page.get_text("blocks", sort=True)
                for b in blocks:
                    clean_b = b[4].strip()
                    if clean_b and len(clean_b) > 2:
                        text_blocks.append(clean_b)
            
            full_text = "\n\n".join(text_blocks)
            if len(full_text.strip()) > 100:
                is_digital = True
                doc.close()
                return full_text, pages_count, is_digital
            doc.close()
        except Exception as e:
            logger.debug(f"PyMuPDF extraction failed for {pdf_path.name}: {e}")

        # Fallback to pdfplumber
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_count = len(pdf.pages)
                page_texts = []
                for page in pdf.pages[:self.config.max_pages]:
                    t = page.extract_text(layout=True) or ""
                    if t.strip():
                        page_texts.append(t.strip())
                
                full_text = "\n\n".join(page_texts)
                if len(full_text.strip()) > 100:
                    is_digital = True
        except Exception as e:
            logger.debug(f"pdfplumber failed for {pdf_path.name}: {e}")

        return full_text, pages_count, is_digital

    def parse_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Parse PDF with enhanced extraction logic"""
        result = {
            'case_id': pdf_path.stem,
            'file_name': pdf_path.name,
            'file_size': pdf_path.stat().st_size,
            'extraction_date': datetime.now().isoformat(),
            'pages': 0,
            'full_text': '',
            'case_title': '',
            'issue_for_consideration': '',
            'headnotes': '',
            'list_of_acts': [],
            'list_of_keywords': [],
            'judgment_text': '',
            'case_arising_from': '',
            'appearances': '',
            'judges': [],
            'decision_date': '',
            'citation': '',
            'acts_referred': [],
            'ipc_sections_referred': [],
            'bns_sections_referred': [],
            'pocso_sections_referred': [],
            'it_act_sections_referred': [],
            'dowry_act_sections_referred': [],  # Added Dowry Act sections
            'crpc_sections_referred': [],  # Added CrPC sections
            'posh_act_sections_referred': [],  # Added POSH Act sections
            'is_digital': False,
            'has_error': False,
            'error_message': ''
        }
        
        full_text, pages_count, is_digital = self.extract_clean_text(pdf_path)
        result['pages'] = pages_count
        result['is_digital'] = is_digital
        result['full_text'] = full_text

        if not full_text or len(full_text.strip()) < 50:
            result['has_error'] = True
            result['error_message'] = "Empty or unreadable PDF text"
            return result

        try:
            # Extract all components
            result['case_title'] = self._extract_case_title(full_text)
            result['citation'] = self._extract_citation(full_text)
            result['decision_date'] = self._extract_decision_date(full_text)
            result['judges'] = self._extract_judges(full_text)
            result['case_arising_from'] = self._extract_case_origin(full_text)
            result['appearances'] = self._extract_appearances(full_text)
            result['issue_for_consideration'] = self._extract_issues(full_text)
            result['headnotes'] = self._extract_headnotes(full_text)
            result['list_of_acts'] = self._extract_acts_list(full_text)
            result['list_of_keywords'] = self._extract_keywords(full_text)
            result['judgment_text'] = self._extract_judgment(full_text)
            
            # Extract section references from BOTH headnotes AND judgment body
            # This ensures we capture sections mentioned in the detailed judgment discussion
            headnotes_text = result['headnotes']
            judgment_body = result['judgment_text']
            
            # Combine both for comprehensive section extraction
            text_for_sections = f"{full_text}\n\n{headnotes_text}\n\n{judgment_body}"
            
            sections = self._extract_all_sections(text_for_sections)
            result['ipc_sections_referred'] = sections['ipc']
            result['bns_sections_referred'] = sections['bns']
            result['pocso_sections_referred'] = sections['pocso']
            result['it_act_sections_referred'] = sections['it_act']
            result['dowry_act_sections_referred'] = sections['dowry_act']  # Added
            result['crpc_sections_referred'] = sections['crpc']  # Added CrPC
            result['posh_act_sections_referred'] = sections['posh_act']  # Added POSH Act
            result['acts_referred'] = self._extract_special_acts(text_for_sections)
            
        except Exception as e:
            result['has_error'] = True
            result['error_message'] = f"Parsing error: {str(e)}"
            logger.error(f"Error parsing {pdf_path.name}: {e}")
        
        return result

    def _extract_case_title(self, text: str) -> str:
        """Extract case title (petitioner vs respondent) - ENHANCED FOR 2017-2022"""
        # Multiple patterns to handle various formats in SC judgments
        patterns = [
            # Pattern 1: Handle "ETC." format (2017): "AJAY KUMAR GHOSHAL ETC.\n\nSTATE OF BIHAR & ANR."
            r'([A-Z][A-Z\s\.\&,@\(\)]+ETC\.)\s*\n+([A-Z][A-Z\s\.\&,@\(\)]+)',
            
            # Pattern 2: Handle "v.." (two dots) format: "KUMAR GHIMIREY\n\nv..\n\nTHE STATE OF SIKKIM"
            r'([A-Z][A-Z\s\.\&,@\(\)]+)\s*\n+v\.+\s*\n+([A-Z][A-Z\s\.\&,@\(\)]+)',
            
            # Pattern 3: Two party names with blank line and followed by case indicator
            # Example: "SHYAMLAL DEVDA AND OTHERS\n\nPARIMALA\n\n(Criminal"
            r'^([A-Z][A-Z\s\.\&,@\(\)]{4,50})\n\n([A-Z][A-Z\s\.\&,@\(\)]{3,50})\n\n\(Criminal',
            
            # Pattern 4: Standard v./vs./versus format with newlines
            r'([A-Z][A-Z\s\.\&,@]{5,50})\s*\n+(?:v\.|vs\.|versus)\s*\n+([A-Z][A-Z\s\.\&,@]{3,50})',
            
            # Pattern 5: Standard v./vs. on same line
            r'([A-Z][A-Z\s\.\&,@]{5,50})\s*(?:v\.|vs\.|versus)\s*([A-Z][A-Z\s\.\&,@]{3,50})',
            
            # Pattern 6: Two consecutive all-caps lines (fallback)
            r'([A-Z][A-Z\s\.\&,@]{5,50})\n\n([A-Z][A-Z\s\.\&,@]{3,50})\n',
        ]
        
        for pat in patterns:
            match = re.search(pat, text[:2000], re.MULTILINE)
            if match:
                petitioner = match.group(1).strip()
                respondent = match.group(2).strip()
                
                # Validation checks
                # 1. Length check (not too short, not too long)
                if len(petitioner) < 4 or len(respondent) < 3:
                    continue
                if len(petitioner) > 100 or len(respondent) > 100:
                    continue
                
                # 2. Clean up extra whitespace
                petitioner = ' '.join(petitioner.split())
                respondent = ' '.join(respondent.split())
                
                # 3. Must look like proper names (no numbers at start, not just punctuation)
                if not re.match(r'^[A-Z]', petitioner) or not re.match(r'^[A-Z]', respondent):
                    continue
                
                # 4. Validate it's a real case title by checking for common indicators
                # Either has STATE/UNION/COMMISSIONER in respondent, or followed by case type
                context_after = text[match.end():match.end()+150].upper()
                is_valid = (
                    'STATE' in respondent.upper() or 
                    'UNION' in respondent.upper() or
                    'COMMISSIONER' in respondent.upper() or
                    'GOVERNMENT' in respondent.upper() or
                    'AND OTHERS' in petitioner.upper() or 
                    'ETC.' in petitioner.upper() or  # Added for 2017 format
                    'AND ORS' in petitioner.upper() or
                    'CRIMINAL' in context_after or
                    'APPEAL' in context_after or
                    'PETITION' in context_after
                )
                
                if is_valid:
                    # Normalize the separator to "v."
                    return f"{petitioner} v. {respondent}"
        
        return ""

    def _extract_citation(self, text: str) -> str:
        """Extract case citation - ENHANCED FOR 2017-2022"""
        patterns = [
            # Pattern 1: 2019 INSC 305
            r'(\d{4}\s+INSC\s+\d+)',
            
            # Pattern 2: [2019] 1 S.C.R. 469
            r'(\[\d{4}\]\s+\d+\s+S\.C\.R\.\s+\d+)',
            
            # Pattern 3: (2019) 6 SCC 1
            r'(\(\d{4}\)\s+\d+\s+SCC\s+\d+)',
            
            # Pattern 4: 2019 6 SCC 1 (without parentheses)
            r'(\d{4}\s+\d+\s+SCC\s+\d+)',
            
            # Pattern 5: Criminal Appeal No. 119 of 2017
            r'(Criminal Appeal No\.?\s*\d+(?:-\d+)?\s+of\s+\d{4})',
            
            # Pattern 6: Civil Appeal format
            r'(Civil Appeal No\.?\s*\d+(?:-\d+)?\s+of\s+\d{4})',
            
            # Pattern 7: Writ Petition format
            r'(Writ Petition (?:\(Criminal\)|No\.)\s*\d+\s+of\s+\d{4})',
        ]
        
        for pat in patterns:
            match = re.search(pat, text[:1500], re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    def _extract_decision_date(self, text: str) -> str:
        """Extract judgment date - ENHANCED FOR 2017-2022"""
        patterns = [
            # Pattern 1: JANUARY 31, 2017
            r'([A-Z]+\s+\d{1,2},\s+\d{4})',
            
            # Pattern 2: 31 JANUARY 2017
            r'(\d{1,2}\s+(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{4})',
            
            # Pattern 3: DD.MM.YYYY
            r'(\d{2}\.\d{2}\.\d{4})',
            
            # Pattern 4: DD/MM/YYYY
            r'(\d{2}/\d{2}/\d{4})',
            
            # Pattern 5: Month DD, YYYY (case insensitive)
            r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})',
        ]
        
        for pat in patterns:
            match = re.search(pat, text[:2000], re.IGNORECASE)
            if match:
                date_str = match.group(1)
                # Normalize to uppercase if all caps pattern
                if re.match(r'^[A-Z]', date_str):
                    return date_str
                # Return as-is for mixed case
                return date_str.upper() if date_str.isupper() else date_str
        return ""

    def _extract_judges(self, text: str) -> List[str]:
        """Extract judges' names - ENHANCED FOR 2017-2022"""
        judges = []
        
        # Multiple patterns to handle bracket variations across years
        patterns = [
            # Pattern 1: Standard format [NAME AND NAME, JJ.]
            r'\[([A-Z][A-Z\.\s]+(?:AND|,)[A-Z\.\s]+),\s*JJ?\.\]',
            
            # Pattern 2: 2017 format with closing parenthesis: "[NAME AND NAME, JJ.)"
            r'\[([A-Z][A-Z\.\s]+(?:AND|,)[A-Z\.\s]+),\s*JJ?\.\)',
            
            # Pattern 3: Opening parenthesis format: "(NAME AND NAME, JJ.]"
            r'\(([A-Z][A-Z\.\s]+(?:AND|,)[A-Z\.\s]+),\s*JJ?\.\]',
            
            # Pattern 4: Both parentheses: "(NAME AND NAME, JJ.)"
            r'\(([A-Z][A-Z\.\s]+(?:AND|,)[A-Z\.\s]+),\s*JJ?\.\)',
            
            # Pattern 5: BENCH/CORAM format
            r'(?:BENCH|CORAM)\s*[:–]\s*([A-Z][A-Z\.\s,&]+JJ?\.)' ,
        ]
        
        for pat in patterns:
            match = re.search(pat, text[:2500])
            if match:
                judge_text = match.group(1)
                # Split by AND or comma
                parts = re.split(r'\s+AND\s+|,', judge_text)
                for part in parts:
                    clean = re.sub(r'\bJJ?\.|Hon\'ble|Mr\.|Mrs\.|Ms\.', '', part).strip()
                    if clean and len(clean) > 3:
                        judges.append(clean)
                
                # If we found judges, break to avoid duplicates
                if judges:
                    break
        
        return list(dict.fromkeys(judges))

    def _extract_case_origin(self, text: str) -> str:
        """Extract case origin (which court/tribunal it came from)"""
        patterns = [
            # More flexible pattern for "From the Judgment/Order dated..."
            r'From the (?:Judgment|Order)(?:\s+and\s+Order)?\s+dated\s+[\d\.]+\s+of the[^\n]+(?:High Court|Supreme Court|Tribunal)[^\n.]+',
            r'IN THE SUPREME COURT OF INDIA[^\n]+\n([^\n]+JURISDICTION[^\n]+)',
        ]
        
        for pat in patterns:
            match = re.search(pat, text[:5000], re.IGNORECASE | re.DOTALL)
            if match:
                extracted = match.group(0).strip()
                # Clean up extra whitespace
                extracted = ' '.join(extracted.split())
                return extracted
        return ""

    def _extract_appearances(self, text: str) -> str:
        """Extract appearances (lawyers)"""
        # Multiple strategies for finding lawyer appearances
        
        # Strategy 1: Look for pattern with "for the Appellant/Respondent/Petitioner"
        pattern1 = r'([A-Z][A-Za-z\.\s,]+(?:Adv|Advocate)s?\.?\s+for\s+the\s+(?:Appellant|Respondent|Petitioner)[^\n]*)'
        matches1 = re.findall(pattern1, text[:7000], re.MULTILINE)
        
        # Strategy 2: Look for the structured format "Name1, Name2, ..., Advs. for the X."
        # This is common format: "Shri Singh, Amartya Kanjilal, Ms. Sayali Kadu, Ms. Adeeba Mujahid, Advs. for the Appellant."
        pattern2 = r'(?:Shri|Ms\.|Mr\.|Smt\.|Dr\.)\s+[A-Za-z\s,\.]+(?:Advs?\.)\s+for\s+the\s+(?:Appellant|Respondent|Petitioner)s?\.?'
        matches2 = re.findall(pattern2, text[:7000], re.IGNORECASE)
        
        # Strategy 3: Look for section starting with "For Appellant:" or "For Respondent:"
        pattern3 = r'For\s+(Appellant|Respondent|Petitioner)s?:\s*([^\n]+(?:Adv|AG|AAG|A\.G\.|Dy\.\s*AG)[^\n]*)'
        matches3 = re.findall(pattern3, text[:7000], re.IGNORECASE | re.MULTILINE)
        formatted3 = [f"For {m[0]}: {m[1].strip()}" for m in matches3]
        
        all_matches = matches1 + matches2 + formatted3
        if all_matches:
            return '\n'.join(all_matches)
        return ""

    def _extract_issues(self, text: str) -> str:
        """Extract issues for consideration - ENHANCED to avoid truncation"""
        
        # Strategy 0: Extract from headnotes format "Constitution/Act ... - Issue description"
        # Example: "Constitution of India – Arts. 32, 72 and 161 – Rejection of mercy petition – Judicial review of – ..."
        # ENHANCED: Extend capture to get complete description, not truncated
        headnote_issue_pattern = r'(?:Constitution of India|Penal Code|Code of Criminal Procedure|POCSO|Protection of Children|Act)[^\-–—]{0,150}[–\-—]\s*(.{100,1500}?(?:dismissed|allowed|held|plea|appeal|conviction|sentence|acquit))'
        match = re.search(headnote_issue_pattern, text[:4000], re.IGNORECASE | re.DOTALL)
        if match:
            issue_text = ' '.join(match.group(1).split()).strip()
            
            # Extend to complete sentence if truncated mid-sentence
            if not re.search(r'[.!?]$', issue_text):
                # Look for sentence ending after this point
                continuation_match = re.search(r'^([^.!?]*[.!?])', text[match.end():match.end()+200])
                if continuation_match:
                    issue_text += ' ' + continuation_match.group(1).strip()
            
            # Clean up - ensure it ends properly
            if not issue_text.endswith(('.', '!', '?')):
                issue_text += '.'
            
            # Validate it's a real issue (contains legal keywords)
            legal_keywords = ['petitioner', 'appellant', 'accused', 'charge', 'whether', 'review', 
                            'conviction', 'sentence', 'rejection', 'power', 'offence', 'court', 
                            'trial', 'appeal', 'plea', 'held']
            if len(issue_text) > 100 and any(keyword in issue_text.lower() for keyword in legal_keywords):
                return issue_text[:1500]  # Increased limit from 1000 to 1500
        
        # Strategy 1: Look for numbered paragraph discussion of issues (para 18, 15, etc.)
        # These often contain "whether" statements framing the legal questions
        issue_para_pattern = r'(?:paragraph|para\.?|¶)\s*(?:\d+|[IVX]+)[^\n]{0,100}?(?:issue|question|whether)[^\n]+\n\n([^]+?)(?:\n\n[A-Z]|$)'
        match = re.search(issue_para_pattern, text, re.IGNORECASE)
        if match:
            text_block = match.group(1)
            # Extract the "whether" question from this block
            whether_match = re.search(r'(whether[^?.!]+(?:and[^?.!]+)?\.)', text_block, re.IGNORECASE)
            if whether_match:
                return ' '.join(whether_match.group(1).split())[:1500]
        
        # Strategy 2: Direct search for "whether" in judgment text around "issue" keywords
        # Look within 500 chars after mentioning "issue" or "question"
        context_pattern = r'(?:issue|question|point)[^.]{0,500}?(whether[^?.]+(?:\?|\.))'
        matches = re.findall(context_pattern, text, re.IGNORECASE)
        for match in matches:
            cleaned = ' '.join(match.split()).strip()
            if len(cleaned) > 80 and any(kw in cleaned.lower() for kw in ['act', 'section', 'court', 'conviction']):
                return cleaned[:1500]
        
        # Strategy 3: Find any substantial "whether" question in first 50% of document
        mid_point = len(text) // 2
        whether_pattern = r'(whether\s+(?:the|an?|once|such)[^?.!]{60,800}(?:\?|\.))'
        matches = re.findall(whether_pattern, text[:mid_point], re.IGNORECASE)
        if matches:
            # Return the first substantial question
            for match in matches:
                cleaned = ' '.join(match.split()).strip()
                if len(cleaned) > 80:
                    return cleaned[:1500]
        
        # Strategy 4: Look for "issue" or "question" followed by descriptive text (even without "whether")
        # ENHANCED: Look for longer, more complete descriptions
        issue_descriptive_pattern = r'(?:issue|question|point)(?:\s+(?:for|under|raised|involved|before|to be decided))?\s*(?:is|was|are|were)?\s*[:–\-—]?\s*([A-Z][^.?!]{80,1000}[.?!])'
        match = re.search(issue_descriptive_pattern, text[:10000], re.IGNORECASE)
        if match:
            cleaned = ' '.join(match.group(1).split()).strip()
            if len(cleaned) > 80:
                return cleaned[:1500]
        
        # Strategy 5: Extract from headnotes summary (case synopsis)
        # Often starts with sections and has a dash before description
        headnote_issue_pattern2 = r'(?:ss?\.|sections?|section)\s+[\d,\s/\-A-Z\(\)]+[–\-—]\s*([^–\-—]+[–\-—][^.]+\.)'
        match = re.search(headnote_issue_pattern2, text[:5000], re.IGNORECASE)
        if match:
            cleaned = ' '.join(match.group(1).split()).strip()
            if len(cleaned) > 80 and len(cleaned) < 1500:
                return cleaned[:1500]
        
        # Strategy 6: Fallback - extract first substantial sentence after "HELD:" or judgment start
        fallback_pattern = r'(?:HELD|JUDGMENT|J\s*\.)[:\s]*([A-Z][^.]+(?:\.[^.]+){0,4}\.)'
        match = re.search(fallback_pattern, text[:8000], re.IGNORECASE)
        if match:
            cleaned = ' '.join(match.group(1).split()).strip()
            if 80 < len(cleaned) < 1500:
                return cleaned[:1500]
        
        return ""

    def _extract_headnotes(self, text: str) -> str:
        """Extract headnotes - expanded to capture complete content"""
        # Strategy 1: After HELD: until Case Law Reference or JURISDICTION or next major section
        # Increased window and added more stopping patterns
        pattern1 = r'Held:\s*(.+?)(?=\n\nCase Law Reference|\n\nCRIMINAL APPELLATE JURISDICTION|\n\nCIVIL APPELLATE|\n\nORIGINAL JURISDICTION|^\[UNDER ARTICLE|^The (?:Judgment|Order) of the Court|\n\n\d+\s+SUPREME COURT REPORTS|$)'
        match = re.search(pattern1, text[:20000], re.DOTALL | re.IGNORECASE | re.MULTILINE)  # Increased from 15000 to 20000
        if match:
            extracted = ' '.join(match.group(1).split())
            # Return full headnotes without truncation
            return extracted
        
        # Strategy 2: Look for content between judgment summary and "Case Law Reference"
        pattern2 = r'(?:Code|Act|ss?\.|Section|Constitution)[^.]+\.(.+?)(?=\n\nCase Law Reference|\n\nCRIMINAL APPELLATE|\n\nCIVIL APPELLATE|$)'
        match = re.search(pattern2, text[:20000], re.DOTALL | re.IGNORECASE)
        if match:
            extracted = ' '.join(match.group(1).split())
            if len(extracted) > 200:
                return extracted
        
        return ""

    def _extract_acts_list(self, text: str) -> List[str]:
        """Extract list of acts mentioned - including Constitutional articles"""
        acts = set()
        
        # Extract Constitutional Articles
        const_article_pattern = r'Article[s]?\s+([\d,\s\(\)andor]+)\s+of\s+the\s+Constitution'
        matches = re.findall(const_article_pattern, text[:5000], re.IGNORECASE)
        for match in matches:
            # Extract individual article numbers
            article_nums = re.findall(r'\d+', match)
            for num in article_nums:
                acts.add(f'Constitution of India, Art. {num}')
        
        # Also check for format like "under Article 72"
        const_article_pattern2 = r'(?:under|u/|Article)\s+(?:Article[s]?\s+)?(\d+(?:\([a-z0-9]\))?)\s+(?:of\s+the\s+)?(?:Constitution|Indian Constitution)'
        matches2 = re.findall(const_article_pattern2, text[:8000], re.IGNORECASE)
        for num in matches2:
            acts.add(f'Constitution of India, Art. {num}')
        
        act_patterns = {
            'Indian Penal Code': [r'\bIndian Penal Code,?\s*\d{4}\b', r'\bIPC\b'],
            'Bharatiya Nyaya Sanhita': [r'\bBharatiya Nyaya Sanhita,?\s*\d{4}\b', r'\bBNS\b'],
            'Code of Criminal Procedure': [r'\bCode of Criminal Procedure,?\s*\d{4}\b', r'\bCr\.?P\.?C\.?\b'],
            'POCSO Act': [r'\bProtection of Children from Sexual Offences Act,?\s*\d{4}\b', r'\bPOCSO Act\b', r'\bPOCSO\b'],
            'Juvenile Justice Act': [r'\bJuvenile Justice \(Care and Protection of Children\) Act,?\s*\d{4}\b', r'\bJuvenile Justice.*Act\b', r'\bJ\.?J\.? Act\b'],
            'Dowry Prohibition Act': [r'\bDowry Prohibition Act,?\s*\d{4}\b', r'\bDowry Act\b'],
            'Domestic Violence Act': [r'\bProtection of Women from Domestic Violence Act,?\s*\d{4}\b', r'\bDomestic Violence Act\b', r'\bDV Act\b'],
            'Sexual Harassment at Workplace Act': [r'\bSexual Harassment of Women at Workplace \(Prevention, Prohibition and Redressal\) Act,?\s*\d{4}\b', r'\bSexual Harassment.*Workplace.*Act\b', r'\bPOSH Act\b'],
            'Prohibition of Child Marriage Act': [r'\bProhibition of Child Marriage Act,?\s*\d{4}\b', r'\bChild Marriage.*Act\b', r'\bPCMA\b'],
            'Immoral Traffic Prevention Act': [r'\bImmoral Traffic \(Prevention\) Act,?\s*\d{4}\b', r'\bImmoral Traffic.*Act\b', r'\bITP Act\b', r'\bITPA\b'],
            'Pre-Conception and Pre-Natal Diagnostic Techniques Act': [r'\bPre-Conception and Pre-Natal Diagnostic Techniques \(Prohibition of Sex Selection\) Act,?\s*\d{4}\b', r'\bPC-PNDT Act\b', r'\bPCPNDT Act\b', r'\bPre-Natal.*Act\b'],
            'Indecent Representation of Women Act': [r'\bIndecent Representation of Women \(Prohibition\) Act,?\s*\d{4}\b', r'\bIndecent Representation.*Women.*Act\b'],
            'Commission of Sati Prevention Act': [r'\bCommission of Sati \(Prevention\) Act,?\s*\d{4}\b', r'\bSati.*Prevention.*Act\b', r'\bSati Act\b'],
            'Transplantation of Human Organs Act': [r'\bTransplantation of Human Organs and Tissues Act,?\s*\d{4}\b', r'\bTransplantation.*Organs.*Act\b', r'\bTHOA\b'],
            'Bonded Labour System Abolition Act': [r'\bBonded Labour System \(Abolition\) Act,?\s*\d{4}\b', r'\bBonded Labour.*Act\b'],
            'Child and Adolescent Labour Act': [r'\bChild and Adolescent Labour \(Prohibition and Regulation\) Act,?\s*\d{4}\b', r'\bChild.*Labour.*Act\b', r'\bChild Labour Act\b'],
            'Information Technology Act': [r'\bInformation Technology Act,?\s*\d{4}\b', r'\bIT Act\b'],
            'Prisons Act': [r'\bPrisons Act,?\s*\d{4}\b', r'\bPrison Act\b'],
        }
        
        for act_name, patterns in act_patterns.items():
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    acts.add(act_name)
                    break
        
        return sorted(list(acts))

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract legal keywords from content"""
        keywords = set()
        
        keyword_patterns = [
            r'\b(rape|gang rape|sexual assault|sexual harassment)\b',
            r'\b(kidnapping|abduction|trafficking)\b',
            r'\b(dowry death|dowry harassment|cruelty)\b',
            r'\b(murder|homicide|death|culpable homicide)\b',
            r'\b(modesty|stalking|voyeurism)\b',
            r'\b(acid attack|penetrative assault)\b',
            r'\b(juvenility|juvenile|minor|child)\b',
        ]
        
        for pat in keyword_patterns:
            matches = re.findall(pat, text[:10000], re.IGNORECASE)
            keywords.update([m.lower() for m in matches])
        
        return sorted(list(keywords))

    def _extract_judgment(self, text: str) -> str:
        """Extract judgment body - enhanced to capture everything after judgment marker"""
        # Look for "The Judgment of the Court was delivered by" or "JUDGMENT"
        patterns = [
            r'The Judgment of the Court was delivered by[^\n]*\n+(.+?)$',
            r'(?:J U D G M E N T|JUDGMENT)\s*\n+(.+?)$',
            r'(?:O R D E R|ORDER)\s*\n+(.+?)$',
        ]
        
        for pat in patterns:
            match = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            if match:
                judgment = match.group(1)
                if len(judgment) > 500:
                    return judgment
        
        # Fallback: return second half of document (likely contains judgment)
        mid = len(text) // 2
        return text[mid:]

    def _extract_all_sections(self, text: str) -> Dict[str, List[str]]:
        """
        Extract all section references with BALANCED PRECISION + RECALL.
        
        Strategy:
        1. First pass: Extract ALL sections (HIGH RECALL)
        2. Second pass: Apply context filtering to remove cited case sections (PRECISION)
        3. Keep sections that appear in high-confidence contexts regardless (RECALL SAFETY)
        """
        sections = {
            'ipc': set(),
            'bns': set(),
            'pocso': set(),
            'it_act': set(),
            'dowry_act': set(),  # Added for Dowry Prohibition Act sections
            'crpc': set(),  # Added for Code of Criminal Procedure sections
            'posh_act': set(),  # Added for Sexual Harassment at Workplace Act sections
        }
        
        # HIGH-CONFIDENCE patterns (charged/convicted/sentenced) - ALWAYS include these (RECALL)
        high_confidence_sections = {
            'ipc': set(),
            'bns': set(),
            'pocso': set(),
            'dowry_act': set(),
            'crpc': set(),
        }
        
        # High confidence IPC extraction - including "charged for offences under sections"
        high_conf_ipc_patterns = [
            r'(?:charged|convicted|sentenced|prosecuted|registered|offence)\s+(?:with|of|to|under|for offences under)\s+[^.]{0,100}?(?:Section|Sections|sections|ss?\.|u/s)\s+([\d,\s/\-A-Z\(\)]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
            r'(?:FIR|complaint)\s+(?:registered|filed)\s+(?:under|u/s)\s+[^.]{0,100}?([\d,\s/\-A-Z]+)\s+(?:IPC|Indian Penal Code)',
            r'(?:charged for offences under sections?)\s+([\d,\s/\-A-Z\(\)]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
            # NEW: Pattern for headnote-style section lists at start: "ss.363, 366A, 364, 346, 376D..."
            r'^Penal Code[^\n]*[–\-—]\s*ss?\.\s*([\d,\s\-A-Z]+)\s*[–\-—]',
        ]
        
        for pat in high_conf_ipc_patterns:
            matches = re.findall(pat, text[:3000], re.IGNORECASE | re.MULTILINE)  # Check first 3000 chars for headnotes
            for match in matches:
                nums = re.findall(r'\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]+\))?', match)
                # Normalize by removing hyphens: "498-A" → "498A"
                high_confidence_sections['ipc'].update([n.upper().replace('-', '') for n in nums])
        
        # High confidence POCSO extraction - including formats like "5(m)/6"
        high_conf_pocso_patterns = [
            r'(?:charged|convicted|sentenced|prosecuted|registered|offence)\s+(?:with|of|to|under|for offences under)\s+[^.]{0,100}?(?:Section|Sections|sections|ss?\.|u/s|s\.)\s*([\d,\s/\(\)a-z]+)\s+(?:of\s+)?(?:the\s+)?POCSO',
            r'POCSO\s+Act\s*[–\-—]\s*s\.\s*([\d/\(\)a-z]+)',
            r'sections?\s+([\d/\(\)a-z]+)\s+of\s+the\s+POCSO\s+Act',
        ]
        
        for pat in high_conf_pocso_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                # Extract POCSO sections with subsections: "5(m)/6" → ["5(m)", "6"]
                # Use lookbehind/lookahead to capture number with optional letter subsection in parens
                nums = re.findall(r'(?<![0-9])([1-9]|1[0-9]|20)(?:\([a-z]\))?(?![0-9])', match)
                high_confidence_sections['pocso'].update(nums)
        
        # NEW: IPC Complex Subsection Pattern - Handle formats like "s.376(1), (2)(f), (i), (m)"
        # This captures section with multiple nested subsections
        # Pattern: Look for "Penal Code ... s.NUMBER(subsection), (subsection)(letter), (letter)"
        complex_subsection_pattern = r'(?:Penal Code|IPC)[^\n]{0,50}?[–\-—]\s*s(?:ection)?\.?\s*(\d{2,3}[A-Z]?)\([\d]+\)(?:,\s*\([\d]+\))?(?:\([a-z]+\))?(?:,\s*\([a-z]+\))*'
        matches = re.findall(complex_subsection_pattern, text[:3000], re.IGNORECASE)
        for base_section in matches:
            # Add the base section number (e.g., "376" from "s.376(1), (2)(f)")
            high_confidence_sections['ipc'].add(base_section.upper().replace('-', ''))
        
        # Also capture the full subsection notation: "376(1)", "376(2)" etc.
        # Pattern to extract all subsections from formats like "s.376(1), (2)(f), (i), (m)"
        full_subsection_pattern = r'(?:Penal Code|IPC)[^\n]{0,50}?[–\-—]\s*s(?:ection)?\.?\s*(\d{2,3}[A-Z]?)(?:\([\d]+\)|,\s*\([\d]+\))+(?:\([a-z]+\)|,\s*\([a-z]+\))*'
        full_matches = re.findall(full_subsection_pattern, text[:3000], re.IGNORECASE)
        for base_section in full_matches:
            # Extract the base section
            high_confidence_sections['ipc'].add(base_section.upper().replace('-', ''))
        
        # IPC sections - PATTERN 1: Handle comma-separated AND slash-separated lists
        # Examples: "ss. 376, 452 and 506 IPC" OR "Section 498A, 323/504/506 IPC" OR "498-A IPC"
        list_patterns = [
            r'(?:Sections?|ss\.|Sec\.)\s+([\d,\s/\-A-Z]+(?:and|&)?\s*[\d/\-A-Z]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
            r'\bu/ss?\.\s+([\d,\s/\-A-Z]+(?:and|&)?\s*[\d/\-A-Z]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
            r'(?:under|punishable under)\s+Sections?\s+([\d,\s/\-A-Z]+(?:and|&)?\s*[\d/\-A-Z]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
            r'(?:offences under|commission of offences under)\s+Sections?\s+([\d,\s/\-A-Z]+(?:and|&)?\s*[\d/\-A-Z]+)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
        ]
        
        for pat in list_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                # Extract all numbers from comma OR slash-separated list
                # This handles: "498A, 323/504/506" → extracts 498A, 323, 504, 506
                # Also handles: "498-A" → extracts 498A (removes hyphen)
                nums = re.findall(r'\d{2,3}\-?[A-Z]?', match)
                # Normalize by removing hyphens: "498-A" → "498A"
                sections['ipc'].update([n.upper().replace('-', '') for n in nums])
        
        # IPC sections - PATTERN 2: Individual sections with letters (376A, 498A, 498-A, 304B)
        # Enhanced to capture subsections with numbers AND letters: 376(2)(g), 376(1)(i)
        ipc_patterns = [
            r'(?:Section|Sections|S\.|Sec\.)\s+(\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)\s+(?:of\s+)?(?:the\s+)?(?:Indian Penal Code|IPC)',
            r'(?:IPC|Indian Penal Code)\s+(?:Section|Sections|S\.|Sec\.)\s+(\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)',
            r'\bu/s\s+(\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)\s+(?:IPC|Indian Penal Code)',
            r'\b(\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)\s+(?:IPC|Indian Penal Code)',
            r'(?:under|punishable under)\s+Section\s+(\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)\s+(?:of\s+)?(?:the\s+)?(?:IPC|Indian Penal Code)',
            r'(?:offence|crime|charged|convicted)\s+(?:under|punishable under|u/s)\s+(\d{2,3}\-?[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)',
            # Additional pattern for "ss. 376(2)(g)" format
            r'\bss?\.\s+(\d{2,3}(?:\(\d+\))?(?:\([a-z]\))?)',
        ]
        
        for pat in ipc_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for m in matches:
                # Normalize: remove hyphen "498-A" → "498A", but keep subsections like "376(2)(g)"
                clean = m.strip().upper().replace('-', '')
                # Validate IPC section format: allows 302, 304B, 323, 376(2)(g), 498A, etc.
                if re.match(r'^\d{2,3}[A-Z]?(?:\(\d+\))?(?:\([A-Z]\))?$', clean):
                    sections['ipc'].add(clean)
        
        # Dowry Prohibition Act sections - NEW PATTERN
        # Examples: "Section 3 & 4 of the Dowry Prohibition Act"
        dowry_patterns = [
            r'Section\s+([\d\s&,/]+)\s+of\s+the\s+Dowry Prohibition Act',
            r'(?:Sections|ss\.|Sec\.)\s+([\d\s&,/]+)\s+(?:of\s+)?(?:the\s+)?Dowry Prohibition Act',
        ]
        
        for pat in dowry_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                # Extract all numbers: "3 & 4" → extracts 3, 4
                nums = re.findall(r'\d+', match)
                sections['dowry_act'].update(nums)
        
        # CrPC sections - NEW PATTERN for Code of Criminal Procedure
        # Examples: "Section 482 of CrPC", "u/s 438 Cr.P.C.", "Section 437(3) CrPC", "[by virtue of Section 438(2)]"
        # High confidence pattern: explicitly mentions CrPC/Cr.P.C./Code of Criminal Procedure
        crpc_patterns = [
            r'(?:Section|Sections|S\.|Sec\.)\s+([\d,\s/\(\)A-Z]+(?:and|&)?\s*[\d/\(\)A-Z]+)\s+(?:of\s+)?(?:the\s+)?(?:CrPC|Cr\.P\.C\.|Code of Criminal Procedure)',
            r'(?:CrPC|Cr\.P\.C\.|Code of Criminal Procedure)\s+(?:Section|Sections|S\.|Sec\.)\s+([\d,\s/\(\)]+)',
            r'\bu/s\s+(\d{2,3}[A-Z]?(?:\(\d+\))?)\s+(?:CrPC|Cr\.P\.C\.|Code of Criminal Procedure)',
            r'(?:by virtue of|under)\s+Section\s+(\d{2,3}(?:\(\d+\))?)\s+(?:CrPC|Cr\.P\.C\.|Code of Criminal Procedure)',
            # Pattern for: "Section 173(8) of the Code of Criminal Procedure"
            r'Section\s+(\d{2,3}(?:\(\d+\))?)\s+of\s+the\s+Code\s+of\s+Criminal\s+Procedure',
            # Pattern for: "further investigation under Section 173(8)"
            r'investigation\s+under\s+Section\s+(\d{2,3}(?:\(\d+\))?)',
        ]
        
        for pat in crpc_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                # Extract sections with optional subsections: "437(3)" → extract as "437(3)"
                nums = re.findall(r'\d{2,3}(?:\(\d+\))?[A-Z]?', match)
                sections['crpc'].update([n.upper() for n in nums])
        
        # POSH Act sections - Sexual Harassment of Women at Workplace Act, 2013
        # Examples: "Section 29 of the POSH Act", "Section 3 of Sexual Harassment at Workplace Act"
        posh_patterns = [
            r'Section\s+([\d\s&,/]+)\s+of\s+the\s+(?:POSH Act|Sexual Harassment.*Workplace.*Act)',
            r'(?:Sections|ss\.|Sec\.)\s+([\d\s&,/]+)\s+(?:of\s+)?(?:the\s+)?(?:POSH Act|Sexual Harassment.*Workplace.*Act)',
            r'(?:POSH Act|Sexual Harassment.*Workplace.*Act)\s+(?:Section|Sections|S\.|Sec\.)\s+([\d,\s/]+)',
        ]
        
        for pat in posh_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                # Extract all numbers: "3, 4 & 29" → extracts 3, 4, 29
                nums = re.findall(r'\d+', match)
                sections['posh_act'].update(nums)
        
        # BNS sections - Handle comma-separated lists
        bns_list_patterns = [
            r'(?:Sections|ss\.|Sec\.)\s+([\d,\s]+(?:and|&)?\s*\d+)\s+(?:of\s+)?(?:the\s+)?(?:BNS|Bharatiya Nyaya Sanhita)',
        ]
        
        for pat in bns_list_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                nums = re.findall(r'\d{2,3}', match)
                sections['bns'].update(nums)
        
        # BNS sections - Individual (numeric only, typically 2-3 digits)
        bns_patterns = [
            r'(?:Section|Sections|S\.|Sec\.)\s+(\d{2,3})\s+(?:of\s+)?(?:the\s+)?(?:BNS|Bharatiya Nyaya Sanhita)',
            r'(?:BNS|Bharatiya Nyaya Sanhita)\s+(?:Section|Sections|S\.|Sec\.)\s+(\d{2,3})',
        ]
        
        for pat in bns_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            sections['bns'].update(matches)
        
        # POCSO sections - Handle lists with slashes, commas, and subsections
        # Examples: "s.5(m)/6", "Section 3, 5(m) and 6", "ss. 5/6 POCSO"
        # Properly capture subsections like 5(m), exclude things like 2(12) which are Act definitions
        pocso_list_patterns = [
            r'(?:Sections?|ss?\.|Sec\.)\s*([\d,\s/\(\)a-z]+(?:and|&)?\s*[\d/\(\)a-z]+)\s+(?:of\s+)?(?:the\s+)?POCSO\s+Act',
            r'POCSO\s+Act\s*[–\-—]\s*(?:s\.|Section)\s*([\d/\(\)a-z]+)',
        ]
        
        for pat in pocso_list_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                # Extract POCSO sections (1-20) with single-letter subsections only: "5(m)/6" → ["5(m)", "6"]
                # Negative lookahead to exclude multi-digit subsections like 2(12)
                nums = re.findall(r'([1-9]|1[0-9]|20)(?:\([a-z]\))?(?!\(\d)', match)
                sections['pocso'].update(nums)
        
        # POCSO sections - Individual (avoid matching "section 2(12) of" type references)
        pocso_patterns = [
            r'\bsections?\s+((?:[1-9]|1[0-9]|20)(?:\([a-z]\))?)(?!\(\d)\s+(?:of\s+)?(?:the\s+)?POCSO\s+Act',
            r'\bu/s\s+((?:[1-9]|1[0-9]|20)(?:\([a-z]\))?)(?!\(\d)\s+POCSO',
        ]
        
        for pat in pocso_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            sections['pocso'].update(matches)
        
        # IT Act sections
        it_patterns = [
            r'(?:Section|Sections|S\.|Sec\.)\s+(\d{2}[A-Z]?)\s+(?:of\s+)?(?:the\s+)?(?:IT Act|Information Technology Act)',
            r'(?:IT Act|Information Technology Act)\s+(?:Section|Sections|S\.|Sec\.)\s+(\d{2}[A-Z]?)',
        ]
        
        for pat in it_patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            sections['it_act'].update(matches)
        
        # NEW: FALLBACK IPC EXTRACTION - When nothing else works, search entire document
        # This catches sections mentioned in judgment text like "Section 376(1)" or "Section 376(2)"
        if len(sections['ipc']) == 0 and len(high_confidence_sections['ipc']) == 0:
            # Very lenient pattern to catch any IPC section mention in entire document
            fallback_ipc_patterns = [
                r'\bSection\s+(\d{2,3}[A-Z]?(?:\(\d+\))?)\s+of\s+the\s+Indian\s+Penal\s+Code',
                r'\bSection\s+(\d{2,3}[A-Z]?(?:\(\d+\))?),?\s+which\s+includes?\s+Section',
                r'\bunder\s+Section\s+(\d{2,3}[A-Z]?(?:\(\d+\))?(?:\([a-z]\))?)',
                r'\bcharge\s+was.*?under\s+Section\s+(\d{2,3}[A-Z]?)',
            ]
            
            for pat in fallback_ipc_patterns:
                matches = re.findall(pat, text, re.IGNORECASE)
                for match in matches:
                    clean = match.strip().upper().replace('-', '')
                    # Validate IPC section: allows 302, 304B, 376(2)(g), 498A, etc.
                    if re.match(r'^\d{2,3}[A-Z]?(?:\(\d+\))?(?:\([A-Z]\))?$', clean):
                        high_confidence_sections['ipc'].add(clean)
        
        # PRECISION FILTERING - Apply context checks to remove cited case sections
        # But preserve high-confidence sections (charged/convicted/sentenced contexts)
        filtered_sections = self.filter_sections_by_context(text, sections)
        
        # Merge back high-confidence sections (these bypass filtering for RECALL)
        for section_type in high_confidence_sections:
            filtered_sections[section_type].update(high_confidence_sections[section_type])
        
        # CROSS-CHECK: Remove CrPC sections from IPC sections
        # If a section appears in CrPC, it should NOT be in IPC
        crpc_sections = filtered_sections['crpc']
        if crpc_sections:
            filtered_sections['ipc'] = filtered_sections['ipc'] - crpc_sections
        
        return {k: sorted(list(v)) for k, v in filtered_sections.items()}

    def _extract_special_acts(self, text: str) -> List[str]:
        """Detect special legislation"""
        acts = set()
        
        act_map = {
            'POCSO Act, 2012': r'\bPOCSO\b',
            'Dowry Prohibition Act, 1961': r'\bDowry Prohibition Act\b',
            'Domestic Violence Act, 2005': r'\bDomestic Violence Act\b',
            'Juvenile Justice Act, 2015': r'\bJuvenile Justice.*Act.*2015\b',
            'Sexual Harassment at Workplace Act, 2013': r'\bSexual Harassment.*Workplace.*Act\b|\bPOSH Act\b',
            'Prohibition of Child Marriage Act, 2006': r'\bChild Marriage.*Act\b|\bPCMA\b',
            'Immoral Traffic Prevention Act, 1956': r'\bImmoral Traffic.*Act\b|\bITP Act\b|\bITPA\b',
            'PC-PNDT Act, 1994': r'\bPC-PNDT Act\b|\bPCPNDT Act\b|\bPre-Natal.*Act\b',
            'Indecent Representation of Women Act, 1986': r'\bIndecent Representation.*Women.*Act\b',
            'Commission of Sati Prevention Act, 1987': r'\bSati.*Prevention.*Act\b|\bSati Act\b',
            'Transplantation of Human Organs Act, 1994': r'\bTransplantation.*Organs.*Act\b|\bTHOA\b',
            'Bonded Labour System Abolition Act, 1976': r'\bBonded Labour.*Act\b',
            'Child and Adolescent Labour Act, 1986': r'\bChild.*Labour.*Act\b',
            'Information Technology Act, 2000': r'\bInformation Technology Act\b',
        }
        
        for act_name, pattern in act_map.items():
            if re.search(pattern, text, re.IGNORECASE):
                acts.add(act_name)
        
        return sorted(list(acts))

    def process_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Process PDF and save JSON"""
        result = self.parse_pdf(pdf_path)
        json_path = self.config.json_output_dir / f"{result['case_id']}.json"
        
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            result['json_saved'] = True
            result['json_path'] = str(json_path)
        except Exception as e:
            result['json_saved'] = False
            result['json_error'] = str(e)
            logger.error(f"Failed to save JSON for {pdf_path.name}: {e}")

        return result


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    print("=" * 70)
    print("STAGE 3: IMPROVED PDF TO JSON EXTRACTOR FOR 2017")
    print("Optimized for Supreme Court Judgment Structure")
    print("=" * 70)
    
    config = Config()
    
    if not config.pdf_input_dir.exists():
        logger.error(f"❌ PDF directory not found: {config.pdf_input_dir}")
        return

    pdf_files = list(config.pdf_input_dir.glob('*.pdf'))
    if not pdf_files:
        logger.error(f"No PDFs found in: {config.pdf_input_dir}")
        return

    logger.info(f"Found {len(pdf_files)} PDF files to extract")
    parser = SupremeCourtPDFParser2017(config)
    results = []

    print(f"\nExtracting JSONs using {config.num_workers} threads...")
    with ThreadPoolExecutor(max_workers=config.num_workers) as executor:
        futures = {executor.submit(parser.process_pdf, pdf): pdf for pdf in pdf_files}
        
        for future in tqdm(as_completed(futures), total=len(pdf_files), desc="Extracting"):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                pdf_path = futures[future]
                logger.error(f"Exception processing {pdf_path.name}: {e}")

    # Generate summary
    df = pd.DataFrame(results)
    config.summary_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Exclude massive text from CSV
    summary_cols = [c for c in df.columns if c not in ['full_text', 'judgment_text']]
    df[summary_cols].to_csv(config.summary_file, index=False)

    successes = len([r for r in results if not r.get('has_error', False)])
    failures = len(results) - successes

    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"Successful: {successes}")
    print(f"Failed: {failures}")
    print(f"\n📁 JSON Output: {config.json_output_dir}")
    print(f"📁 Summary: {config.summary_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()