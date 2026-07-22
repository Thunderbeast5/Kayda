#!/usr/bin/env python3
"""
Stage 3: OCR / Text Extraction from PDFs

Handles both digital and scanned PDFs:
1. Digital PDF → Extract text directly (pdfplumber / pymupdf)
2. Scanned PDF → OCR using Tesseract (pdf2image + pytesseract)

Input:  data/pdf_downloads/*.pdf
Output: data/extracted_text/*.txt
        data/extraction_results.csv
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import hashlib

import pandas as pd
from tqdm import tqdm

# PDF Processing
import pdfplumber
import fitz  # PyMuPDF

# OCR
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

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
    """Configuration for text extraction"""
    
    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = project_root / 'data'
    
    # Input PDFs from Stage 2
    pdf_input_dir: Path = data_dir / 'pdf_downloads'
    
    # Output directories
    text_output_dir: Path = data_dir / 'extracted_text'
    ocr_temp_dir: Path = data_dir / 'temp_ocr'
    
    # OCR settings
    ocr_language: str = 'eng'  # Language for Tesseract
    ocr_dpi: int = 300  # DPI for image conversion
    ocr_workers: int = 2  # Concurrent OCR processes
    max_pages_for_ocr: int = 50  # Max pages to OCR per PDF
    pdf2image_timeout: int = 60  # Seconds per page
    
    # Text extraction settings
    min_text_length: int = 100  # Minimum characters to consider "digital"
    
    def __post_init__(self):
        """Create necessary directories"""
        self.text_output_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_temp_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# TEXT EXTRACTOR
# ============================================================

class PDFTextExtractor:
    """
    Extract text from PDFs using multiple methods.
    
    Methods:
    1. pdfplumber (best for digital PDFs with tables)
    2. PyMuPDF (fast, good for digital PDFs)
    3. Tesseract OCR (for scanned PDFs)
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.stats = {
            'total': 0,
            'digital': 0,
            'scanned_ocr': 0,
            'failed': 0,
            'skipped_exists': 0,
            'empty_text': 0
        }
    
    def _extract_with_pdfplumber(self, pdf_path: Path) -> Tuple[str, bool]:
        """
        Extract text using pdfplumber.
        Returns: (text, has_text)
        """
        try:
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ''
                    if page_text.strip():
                        text_parts.append(page_text)
            
            full_text = '\n'.join(text_parts)
            has_text = len(full_text.strip()) > self.config.min_text_length
            return full_text, has_text
            
        except Exception as e:
            logger.debug(f"pdfplumber failed for {pdf_path.name}: {e}")
            return "", False
    
    def _extract_with_pymupdf(self, pdf_path: Path) -> Tuple[str, bool]:
        """
        Extract text using PyMuPDF (fitz).
        Returns: (text, has_text)
        """
        try:
            text_parts = []
            doc = fitz.open(pdf_path)
            for page in doc:
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(page_text)
            doc.close()
            
            full_text = '\n'.join(text_parts)
            has_text = len(full_text.strip()) > self.config.min_text_length
            return full_text, has_text
            
        except Exception as e:
            logger.debug(f"PyMuPDF failed for {pdf_path.name}: {e}")
            return "", False
    
    def _extract_with_ocr(self, pdf_path: Path, max_pages: int = None) -> Tuple[str, bool]:
        """
        Extract text using OCR (Tesseract).
        Returns: (text, success)
        """
        if max_pages is None:
            max_pages = self.config.max_pages_for_ocr
        
        try:
            text_parts = []
            
            # Convert PDF to images
            images = convert_from_path(
                str(pdf_path),
                dpi=self.config.ocr_dpi,
                timeout=self.config.pdf2image_timeout,
                first_page=1,
                last_page=max_pages
            )
            
            # OCR each image
            for i, image in enumerate(images):
                # Preprocess image for better OCR
                image = self._preprocess_image(image)
                
                # OCR
                page_text = pytesseract.image_to_string(
                    image,
                    lang=self.config.ocr_language,
                    config='--psm 6'  # Assume uniform text block
                )
                
                if page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")
            
            full_text = '\n'.join(text_parts)
            has_text = len(full_text.strip()) > self.config.min_text_length
            
            # Clean up temp images if needed
            if not self.config.ocr_temp_dir.exists():
                self.config.ocr_temp_dir.mkdir(parents=True, exist_ok=True)
            
            return full_text, has_text
            
        except Exception as e:
            logger.debug(f"OCR failed for {pdf_path.name}: {e}")
            return "", False
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR results.
        - Convert to grayscale
        - Apply thresholding
        """
        try:
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Apply threshold (optional)
            # image = image.point(lambda x: 0 if x < 128 else 255, '1')
            
            return image
        except:
            return image
    
    def _get_text_from_pdf(self, pdf_path: Path) -> Dict:
        """
        Extract text from a PDF using the best available method.
        
        Returns:
            Dict with: text, method, has_text, success, error
        """
        result = {
            'file_name': pdf_path.name,
            'file_size': pdf_path.stat().st_size,
            'text': '',
            'method': 'none',
            'has_text': False,
            'success': False,
            'error': '',
            'word_count': 0
        }
        
        # Try digital extraction methods first
        methods = [
            ('pdfplumber', self._extract_with_pdfplumber),
            ('pymupdf', self._extract_with_pymupdf),
        ]
        
        for method_name, method_func in methods:
            try:
                text, has_text = method_func(pdf_path)
                if has_text:
                    result['text'] = text
                    result['method'] = method_name
                    result['has_text'] = True
                    result['success'] = True
                    result['word_count'] = len(text.split())
                    return result
            except Exception as e:
                logger.debug(f"Method {method_name} failed: {e}")
                continue
        
        # If no digital text found, try OCR
        logger.info(f"🔄 No digital text found in {pdf_path.name}, trying OCR...")
        
        try:
            text, success = self._extract_with_ocr(pdf_path)
            if success:
                result['text'] = text
                result['method'] = 'ocr_tesseract'
                result['has_text'] = True
                result['success'] = True
                result['word_count'] = len(text.split())
                return result
        except Exception as e:
            logger.warning(f"OCR failed for {pdf_path.name}: {e}")
            result['error'] = str(e)
        
        # All methods failed
        result['error'] = 'No text could be extracted'
        return result
    
    def extract_text_from_pdf(self, pdf_path: Path) -> Dict:
        """
        Extract text from a single PDF file.
        Handles both digital and scanned PDFs.
        """
        result = {
            'file_name': pdf_path.name,
            'file_path': str(pdf_path),
            'file_size': pdf_path.stat().st_size,
            'text': '',
            'method': 'none',
            'has_text': False,
            'success': False,
            'error': '',
            'word_count': 0
        }
        
        # Check if output already exists
        output_file = self.config.text_output_dir / f"{pdf_path.stem}.txt"
        
        if output_file.exists() and output_file.stat().st_size > 100:
            # Read existing text
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    text = f.read()
                result['text'] = text
                result['method'] = 'cached'
                result['has_text'] = True
                result['success'] = True
                result['word_count'] = len(text.split())
                self.stats['skipped_exists'] += 1
                return result
            except:
                pass
        
        # Extract text from PDF
        try:
            extraction_result = self._get_text_from_pdf(pdf_path)
            result.update(extraction_result)
            
            # Save extracted text
            if result['has_text']:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result['text'])
                
                # Update stats
                if result['method'] in ['pdfplumber', 'pymupdf']:
                    self.stats['digital'] += 1
                elif result['method'] == 'ocr_tesseract':
                    self.stats['scanned_ocr'] += 1
                
                logger.info(f"✅ Extracted: {pdf_path.name} ({result['word_count']:,} words, method: {result['method']})")
            else:
                self.stats['empty_text'] += 1
                logger.warning(f"⚠️  No text extracted: {pdf_path.name}")
            
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            self.stats['failed'] += 1
            logger.error(f"❌ Failed: {pdf_path.name} - {e}")
        
        return result
    
    def extract_all_pdfs(self, pdf_files: List[Path], max_workers: int = 4) -> pd.DataFrame:
        """
        Extract text from all PDF files.
        
        Args:
            pdf_files: List of PDF file paths
            max_workers: Number of concurrent workers
            
        Returns:
            DataFrame with extraction results
        """
        self.stats['total'] = len(pdf_files)
        
        logger.info(f"\n📥 Extracting text from {len(pdf_files)} PDFs...")
        logger.info(f"   Output directory: {self.config.text_output_dir}")
        logger.info(f"   Concurrent workers: {max_workers}")
        
        results = []
        
        # Process sequentially (OCR can be resource-intensive)
        if max_workers == 1:
            for pdf_path in tqdm(pdf_files, desc="Extracting"):
                result = self.extract_text_from_pdf(pdf_path)
                results.append(result)
        else:
            # Process concurrently
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self.extract_text_from_pdf, pdf_path): pdf_path
                    for pdf_path in pdf_files
                }
                
                with tqdm(total=len(futures), desc="Extracting") as pbar:
                    for future in as_completed(futures):
                        pdf_path = futures[future]
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            logger.error(f"Error processing {pdf_path.name}: {e}")
                            results.append({
                                'file_name': pdf_path.name,
                                'file_path': str(pdf_path),
                                'success': False,
                                'error': str(e)
                            })
                        pbar.update(1)
        
        # Create DataFrame
        df = pd.DataFrame(results)
        
        # Log statistics
        self._log_stats()
        
        return df
    
    def _log_stats(self):
        """Log extraction statistics"""
        logger.info("\n" + "=" * 60)
        logger.info("TEXT EXTRACTION STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total PDFs: {self.stats['total']:,}")
        logger.info(f"Digital PDFs (pdfplumber/pymupdf): {self.stats['digital']:,}")
        logger.info(f"Scanned PDFs (OCR): {self.stats['scanned_ocr']:,}")
        logger.info(f"Already extracted: {self.stats['skipped_exists']:,}")
        logger.info(f"Empty/No text: {self.stats['empty_text']:,}")
        logger.info(f"Failed: {self.stats['failed']:,}")
        logger.info("=" * 60)


# ============================================================
# TEXT CLEANING AND METADATA EXTRACTION
# ============================================================

class TextCleaner:
    """Clean extracted text and extract metadata"""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean extracted text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page number headers/footers (common patterns)
        text = re.sub(r'\bPage\s+\d+\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\d+\s+of\s+\d+\b', '', text)
        
        # Remove special characters (keep Indian language characters)
        text = re.sub(r'[^\w\s.,;:!?()\[\]{}\'\"-]', ' ', text)
        
        # Normalize multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    @staticmethod
    def extract_metadata(text: str) -> Dict:
        """Extract key metadata from text"""
        metadata = {
            'case_number': None,
            'year': None,
            'judges': [],
            'parties': [],
            'acts_referred': [],
            'sections_referred': []
        }
        
        if not text:
            return metadata
        
        # Extract year
        year_match = re.search(r'\b(19[5-9][0-9]|20[0-2][0-9])\b', text)
        if year_match:
            metadata['year'] = year_match.group(1)
        
        # Extract case number patterns
        patterns = [
            r'(?:Writ\s+Petition|Civil\s+Appeal|Criminal\s+Appeal)\s+\(?[A-Z]\)?\s+No\.?\s+(\d+/\d+)',
            r'(?:SLP|Review\s+Petition)\s+\(?[A-Z]\)?\s+No\.?\s+(\d+/\d+)',
            r'Case\s+No\.?\s*([A-Z0-9/\-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata['case_number'] = match.group(1)
                break
        
        # Extract judge names
        judge_patterns = [
            r'(?:Hon\'?ble|Justice|J\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+J\.',
        ]
        
        judges = set()
        for pattern in judge_patterns:
            matches = re.findall(pattern, text)
            judges.update(matches)
        
        metadata['judges'] = list(judges)
        
        # Extract sections referred
        section_pattern = r'\bSection\s+(\d+[A-Z]?)\b'
        sections = set(re.findall(section_pattern, text, re.IGNORECASE))
        metadata['sections_referred'] = list(sections)
        
        # Extract acts referred
        act_patterns = [
            r'Indian\s+Penal\s+Code',
            r'Code\s+of\s+Criminal\s+Procedure',
            r'Indian\s+Evidence\s+Act',
            r'Protection\s+of\s+Children\s+from\s+Sexual\s+Offences',
            r'POCSO',
            r'Dowry\s+Prohibition\s+Act',
            r'Domestic\s+Violence\s+Act',
            r'Juvenile\s+Justice\s+Act'
        ]
        
        for pattern in act_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                metadata['acts_referred'].append(pattern)
        
        return metadata


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    """Main entry point"""
    print("=" * 70)
    print("STAGE 3: OCR / TEXT EXTRACTION")
    print("Extracting text from PDFs (digital + scanned)")
    print("=" * 70)
    
    config = Config()
    
    print(f"\n📁 Project root: {config.project_root}")
    print(f"📁 Data directory: {config.data_dir}")
    print(f"📁 PDF input directory: {config.pdf_input_dir}")
    print(f"📁 Text output directory: {config.text_output_dir}")
    
    # Check if PDFs exist
    if not config.pdf_input_dir.exists():
        logger.error(f"❌ PDF directory not found: {config.pdf_input_dir}")
        print("\n⚠️  No PDFs found. Please run Stage 2 first.")
        return
    
    # Get all PDF files
    pdf_files = list(config.pdf_input_dir.glob('*.pdf'))
    
    if not pdf_files:
        logger.error(f"❌ No PDFs found in: {config.pdf_input_dir}")
        return
    
    logger.info(f"✅ Found {len(pdf_files)} PDF files")
    
    # Check Tesseract availability
    try:
        pytesseract.get_tesseract_version()
        logger.info("✅ Tesseract OCR available")
    except:
        logger.warning("⚠️  Tesseract OCR not found. Scanned PDFs will fail.")
        logger.warning("   Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki")
    
    # Initialize extractor
    extractor = PDFTextExtractor(config)
    
    # Extract text from all PDFs
    result_df = extractor.extract_all_pdfs(
        pdf_files,
        max_workers=2  # OCR is memory-intensive, use fewer workers
    )
    
    # Save results
    results_file = config.data_dir / 'extraction_results.csv'
    result_df.to_csv(results_file, index=False)
    logger.info(f"💾 Extraction results saved to: {results_file}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("STAGE 3 COMPLETE")
    print("=" * 70)
    
    successful = result_df[result_df['success'] == True]
    failed = result_df[result_df['success'] == False]
    
    print(f"\n📊 Summary:")
    print(f"   Total PDFs: {len(pdf_files)}")
    print(f"   Successfully extracted: {len(successful)}")
    print(f"   Failed: {len(failed)}")
    
    if len(successful) > 0:
        avg_words = successful['word_count'].mean()
        print(f"   Average words per document: {avg_words:,.0f}")
        
        # Method breakdown
        method_counts = successful['method'].value_counts()
        print(f"\n   Extraction methods:")
        for method, count in method_counts.items():
            print(f"      - {method}: {count}")
    
    print(f"\n📁 Extracted text saved to: {config.text_output_dir}")
    
    # Show sample extracted text
    if len(successful) > 0:
        sample = successful.iloc[0]
        print(f"\n📋 Sample extracted text ({sample['file_name']}):")
        text_preview = sample['text'][:500] + "..." if len(sample['text']) > 500 else sample['text']
        print(f"   {text_preview}")
    
    print("\n" + "=" * 70)
    print("✅ Stage 3 complete. Ready for Stage 4 classification.")


if __name__ == "__main__":
    main()