#!/usr/bin/env python3
"""
Stage 3: ACCURATE PDF TO JSON EXTRACTOR

Extracts structured data from Supreme Court judgment PDFs and saves as JSON.

For each PDF, extracts:
- case_id (from filename)
- issue_for_consideration
- headnotes
- list_of_acts
- list_of_keywords
- judgment_text (full)
- case_arising_from
- appearances
- judges
- decision_date
- ipc_sections_referred
- bns_sections_referred
- acts_referred

Input:  data/pdf_downloads_2023/*.pdf
Output: data/json_output_2023/*.json
        data/extraction_summary.csv
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
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
    project_root: Path = Path(__file__).parent.parent.parent if '__file__' in globals() else Path.cwd()
    data_dir: Path = project_root / 'data'
    
    # Input PDFs
    pdf_input_dir: Path = data_dir / 'pdf_downloads_2023'
    
    # Output directories
    json_output_dir: Path = data_dir / 'json_output_2023'
    summary_file: Path = data_dir / 'extraction_summary.csv'
    
    # Extraction settings
    max_pages: int = 100
    num_workers: int = 4
    
    def __post_init__(self):
        self.json_output_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# HIGH-PRECISION PDF PARSER
# ============================================================

class SupremeCourtPDFParser:
    """Parse Supreme Court judgment PDFs with accurate legal section parsing."""
    
    def __init__(self, config: Config):
        self.config = config

    def extract_clean_text(self, pdf_path: Path) -> Tuple[str, int, bool]:
        """
        Extracts clean full text using PyMuPDF block layout mode first, 
        falling back to pdfplumber.
        """
        full_text = ""
        pages_count = 0
        is_digital = False

        # Strategy 1: PyMuPDF Block Layout (Fast & Preserves Structure)
        try:
            doc = fitz.open(pdf_path)
            pages_count = len(doc)
            text_blocks = []

            for page_idx in range(min(pages_count, self.config.max_pages)):
                page = doc[page_idx]
                # 'blocks' sorts text elements in reading order (top-to-bottom, left-to-right)
                blocks = page.get_text("blocks")
                for b in blocks:
                    # b[4] contains text content
                    clean_b = b[4].strip()
                    if clean_b:
                        text_blocks.append(clean_b)
            
            full_text = "\n\n".join(text_blocks)
            if len(full_text.strip()) > 100:
                is_digital = True
                doc.close()
                return full_text, pages_count, is_digital
            doc.close()
        except Exception as e:
            logger.debug(f"PyMuPDF block extraction failed for {pdf_path.name}: {e}")

        # Strategy 2: pdfplumber fallback
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_count = len(pdf.pages)
                page_texts = []
                for page in pdf.pages[:self.config.max_pages]:
                    t = page.extract_text(layout=False) or ""
                    if t.strip():
                        page_texts.append(t.strip())
                
                full_text = "\n\n".join(page_texts)
                if len(full_text.strip()) > 100:
                    is_digital = True
                    return full_text, pages_count, is_digital
        except Exception as e:
            logger.debug(f"pdfplumber failed for {pdf_path.name}: {e}")

        return full_text, pages_count, is_digital

    def parse_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Parse a single PDF into structured metadata and judgment components."""
        result = {
            'case_id': pdf_path.stem,
            'file_name': pdf_path.name,
            'file_size': pdf_path.stat().st_size,
            'extraction_date': datetime.now().isoformat(),
            'pages': 0,
            'full_text': '',
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
            result['error_message'] = "Empty or unreadable scanned PDF text"
            return result

        try:
            # 1. Structural metadata blocks
            self._parse_structured_blocks(full_text, result)
            
            # 2. Extract References
            ipc_sec, bns_sec = self._extract_sections(full_text)
            result['ipc_sections_referred'] = ipc_sec
            result['bns_sections_referred'] = bns_sec
            result['acts_referred'] = self._extract_acts(full_text)
            
        except Exception as e:
            result['has_error'] = True
            result['error_message'] = f"Parsing error: {str(e)}"
            logger.error(f"Error parsing metadata for {pdf_path.name}: {e}")
        
        return result
    
    def _parse_structured_blocks(self, text: str, result: Dict):
        """Extract explicit legal headers using robust matching patterns."""

        # 1. Issue for Consideration
        issue_patterns = [
            r'(?:##\s*|\n|\b)Issue(?:s)?\s+for\s+Consideration\s*[:\n\-]+(.*?)(?=\n\s*(?:##|Headnote|List of Acts|Held|Judgment|ORDER)|$)',
            r'(?:##\s*|\n|\b)Point(?:s)?\s+for\s+Determination\s*[:\n\-]+(.*?)(?=\n\s*(?:##|Headnote|List of Acts|Held|Judgment|ORDER)|$)',
            r'HELD\s*:\s*(.*?)(?=\n\s*(?:Judgment|ORDER|Case Law Cited)|$)'
        ]
        result['issue_for_consideration'] = self._extract_first_match(text, issue_patterns, dotall=True)

        # 2. Headnotes
        headnote_patterns = [
            r'(?:##\s*|\n|\b)Headnote(?:s)?\b†?\s*[:\n\-]+(.*?)(?=\n\s*(?:##|List of Acts|List of Keywords|Case Arising From|Judgment|ORDER)|$)',
            r'\[\s*Headnote\s*\]\s*(.*?)(?=\n\s*\[|\n\s*JUDGMENT|$)'
        ]
        result['headnotes'] = self._extract_first_match(text, headnote_patterns, dotall=True)

        # 3. List of Acts
        acts_patterns = [
            r'(?:##\s*|\n|\b)(?:List of Acts|Acts Referred|Statutes Referred)\s*[:\n\-]+(.*?)(?=\n\s*(?:##|List of Keywords|Headnote|Case Arising From|Judgment)|$)'
        ]
        acts_str = self._extract_first_match(text, acts_patterns, dotall=True)
        result['list_of_acts'] = self._split_list_items(acts_str)

        # 4. List of Keywords
        keywords_patterns = [
            r'(?:##\s*|\n|\b)(?:List of Keywords|Keywords|Subject Index)\s*[:\n\-]+(.*?)(?=\n\s*(?:##|Case Arising From|Headnote|List of Acts|Judgment)|$)'
        ]
        kw_str = self._extract_first_match(text, keywords_patterns, dotall=True)
        result['list_of_keywords'] = self._split_list_items(kw_str)

        # 5. Case Arising From
        arising_patterns = [
            r'(?:##\s*|\n|\b)Case Arising From\s*[:\n\-]+(.*?)(?=\n\s*(?:##|Appearances|Judges|Judgment)|$)',
            r'IN\s+THE\s+SUPREME\ court\s+OF\s+INDIA\s*\n(.*?)(?=\n\s*JUDGMENT|\n\s*ORDER|$)'
        ]
        result['case_arising_from'] = self._extract_first_match(text, arising_patterns, dotall=True)

        # 6. Appearances
        appearances_patterns = [
            r'(?:##\s*|\n|\b)Appearances\s*(?:for Parties)?\s*[:\n\-]+(.*?)(?=\n\s*(?:##|JUDGMENT|ORDER|CORAM)|$)',
            r'For\s+Petitioner\(s\)\s*:\s*(.*?)(?=\n\s*For\s+Respondent|\n\s*JUDGMENT|$)'
        ]
        result['appearances'] = self._extract_first_match(text, appearances_patterns, dotall=True)

        # 7. Judges / Bench
        judges_patterns = [
            r'(?:BENCH|CORAM|PRESENT)\s*:\s*(.*?)(?=\n\n|\n[A-Z\s]{4,}:|$)',
            r'Hon\'ble\s+Mr\.\s+Justice\s+([A-Za-z\s\.]+)(?:and|&)\s+Hon\'ble\s+Mr\.\s+Justice\s+([A-Za-z\s\.]+)',
            r'\[\s*([A-Z\s\.]+,\s*J\.)\s*\]'
        ]
        raw_judges = self._extract_first_match(text, judges_patterns)
        result['judges'] = self._clean_judges(raw_judges)

        # 8. Decision Date
        date_patterns = [
            r'(?:Decided|Dated|Date of Judgment|Pronounced on)\s*[:\n\-]*\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s*,\s*[0-9]{4})',
            r'([0-9]{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+[0-9]{4})',
            r'([0-9]{2}[\/\.-][0-9]{2}[\/\.-][0-9]{4})'
        ]
        result['decision_date'] = self._extract_first_match(text, date_patterns)

        # 9. Citation
        citation_patterns = [
            r'([0-9]{4}\s+INSC\s+[0-9]+)',
            r'([0-9]{4}\s*\(\s*[0-9]+\s*\)\s*S\.C\.R\.\s+[0-9]+)',
            r'([0-9]{4}\s+[0-9]+\s+SCC\s+[0-9]+)'
        ]
        result['citation'] = self._extract_first_match(text, citation_patterns)

        # 10. Judgment Text Body
        judgment_patterns = [
            r'(?:##\s*|\n)(?:JUDGMENT|ORDER)\s*\n+(.*?)(?=\Z)',
            r'J U D G M E N T\s*\n+(.*?)(?=\Z)',
            r'O R D E R\s*\n+(.*?)(?=\Z)'
        ]
        j_text = self._extract_first_match(text, judgment_patterns, dotall=True)
        result['judgment_text'] = j_text if j_text else text

    def _extract_first_match(self, text: str, patterns: List[str], dotall: bool = False) -> str:
        flags = re.IGNORECASE | (re.DOTALL if dotall else 0)
        for pattern in patterns:
            match = re.search(pattern, text, flags)
            if match:
                # Retrieve first non-empty capturing group
                groups = [g for g in match.groups() if g]
                if groups:
                    return groups[0].strip()
        return ""

    def _split_list_items(self, text: str) -> List[str]:
        if not text:
            return []
        # Split by semicolons, bullet points, or line breaks
        items = re.split(r'[;\n\•\*\-]', text)
        cleaned = []
        for item in items:
            item = item.strip(' \t\n\r-•*,;')
            if item and len(item) > 1:
                cleaned.append(item)
        return cleaned

    def _clean_judges(self, raw_text: str) -> List[str]:
        if not raw_text:
            return []
        cleaned = []
        # Filter typical judge titles
        names = re.split(r'[,;\n&]|and', raw_text, flags=re.IGNORECASE)
        for name in names:
            n = re.sub(r'\b(Hon\'ble|Mr\.|Mrs\.|Justice|J\.|C\.J\.I\.)\b', '', name, flags=re.IGNORECASE).strip()
            if len(n) > 2:
                cleaned.append(n)
        return list(dict.fromkeys(cleaned))

    def _extract_sections(self, text: str) -> Tuple[List[str], List[str]]:
        """Separately extract sections for IPC and BNS based on immediate context."""
        ipc_sections = set()
        bns_sections = set()

        sec_num_pattern = r'[0-9]{1,4}(?:-[A-Z]+|[A-Z]+)?(?:\([0-9a-z]+\))?'

        # 1. Capture sections where the act name follows (e.g. "Section 302 of IPC", "u/s 103, BNS")
        ipc_postfix = re.findall(rf'\b(?:Section|Sec\.|S\.|u/s|u/ss)\s*({sec_num_pattern})\s*(?:of\b|in\b|,)?\s*(?:the\b\s*)?(?:IPC|Indian Penal Code)', text, re.IGNORECASE)
        bns_postfix = re.findall(rf'\b(?:Section|Sec\.|S\.|u/s|u/ss)\s*({sec_num_pattern})\s*(?:of\b|in\b|,)?\s*(?:the\b\s*)?(?:BNS|Bharatiya Nyaya Sanhita)', text, re.IGNORECASE)

        # 2. Capture sections where the act name precedes (e.g. "IPC Section 302", "BNS u/s 103")
        ipc_prefix = re.findall(rf'\b(?:IPC|Indian Penal Code)\s*(?:,|\b)?\s*(?:Section|Sec\.|S\.|u/s|u/ss)?\s*({sec_num_pattern})', text, re.IGNORECASE)
        bns_prefix = re.findall(rf'\b(?:BNS|Bharatiya Nyaya Sanhita)\s*(?:,|\b)?\s*(?:Section|Sec\.|S\.|u/s|u/ss)?\s*({sec_num_pattern})', text, re.IGNORECASE)

        ipc_sections.update(ipc_postfix)
        ipc_sections.update(ipc_prefix)
        bns_sections.update(bns_postfix)
        bns_sections.update(bns_prefix)

        # 3. Fallback: If generic section references exist without an explicit act name in the same sentence,
        # assign them to IPC or BNS depending on overall document context.
        if not ipc_sections and not bns_sections:
            generic_matches = re.findall(rf'\b(?:Section|Sec\.|S\.|u/s|u/ss)\s*({sec_num_pattern})', text, re.IGNORECASE)
            if generic_matches:
                if re.search(r'\b(BNS|Bharatiya Nyaya Sanhita)\b', text, re.IGNORECASE):
                    bns_sections.update(generic_matches)
                else:
                    ipc_sections.update(generic_matches)

        return sorted(list(ipc_sections)), sorted(list(bns_sections))

    def _extract_acts(self, text: str) -> List[str]:
        """Detect presence of major criminal/special statutes."""
        act_mapping = {
            "Indian Penal Code": [r"\bIndian Penal Code\b", r"\bIPC\b"],
            "Bharatiya Nyaya Sanhita": [r"\bBharatiya Nyaya Sanhita\b", r"\bBNS\b"],
            "Code of Criminal Procedure": [r"\bCode of Criminal Procedure\b", r"\bCrPC\b"],
            "Bharatiya Nagarik Suraksha Sanhita": [r"\bBharatiya Nagarik Suraksha Sanhita\b", r"\bBNSS\b"],
            "Dowry Prohibition Act": [r"\bDowry Prohibition Act\b", r"\bDowry Act\b"],
            "POCSO": [r"\bProtection of Children from Sexual Offences\b", r"\bPOCSO\b"],
            "Indian Evidence Act": [r"\bIndian Evidence Act\b", r"\bEvidence Act\b"],
            "Domestic Violence Act": [r"\bDomestic Violence Act\b", r"\bDV Act\b"]
        }
        
        found_acts = set()
        for act_name, patterns in act_mapping.items():
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    found_acts.add(act_name)
                    break
        return sorted(list(found_acts))

    def process_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Process PDF file and immediately dump structured JSON output."""
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
    print("STAGE 3: HIGH-ACCURACY PDF TO JSON EXTRACTOR")
    print("=" * 70)
    
    config = Config()
    
    if not config.pdf_input_dir.exists():
        logger.error(f"❌ PDF directory not found: {config.pdf_input_dir}")
        return

    pdf_files = list(config.pdf_input_dir.glob('*.pdf'))
    if not pdf_files:
        logger.error(f"❌ No PDFs found in: {config.pdf_input_dir}")
        return

    logger.info(f"✅ Found {len(pdf_files)} PDF files to extract")
    parser = SupremeCourtPDFParser(config)
    results = []

    # Parallel Execution with ThreadPoolExecutor
    print(f"\n📄 Extracting JSONs using {config.num_workers} threads...")
    with ThreadPoolExecutor(max_workers=config.num_workers) as executor:
        futures = {executor.submit(parser.process_pdf, pdf): pdf for pdf in pdf_files}
        
        for future in tqdm(as_completed(futures), total=len(pdf_files), desc="Extracting"):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                pdf_path = futures[future]
                logger.error(f"Unhandled exception processing {pdf_path.name}: {e}")

    # Summary Generation
    df = pd.DataFrame(results)
    config.summary_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Exclude massive text block from CSV summary for cleanliness
    summary_df = df.drop(columns=['full_text', 'judgment_text'], errors='ignore')
    summary_df.to_csv(config.summary_file, index=False)

    successes = len([r for r in results if not r.get('has_error', False)])
    failures = len(results) - successes

    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE SUMMARY")
    print("=" * 70)
    print(f"Total PDFs Processed: {len(pdf_files)}")
    print(f"Successful Extraction: {successes}")
    print(f"Failed / Empty Texts: {failures}")
    print(f"\n📁 JSON Output Saved to: {config.json_output_dir}")
    print(f"📁 Summary Report Saved to: {config.summary_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()