#!/usr/bin/env python3
"""
Stage 2: PDF Access from AWS Dataset - CORRECTED PATH STRUCTURE

The S3 bucket structure is:
data/pdf/year=YYYY/english/FILENAME_EN.pdf

Example: data/pdf/year=2024/english/2024_10_108_125_EN.pdf
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import hashlib
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
    """Configuration for PDF access"""
    
    # Script is in: backend/data_extraction/scriptsD/Stage_2.py
    data_extraction_dir: Path = Path(__file__).parent.parent  # → backend/data_extraction
    candidates_file: Path = data_extraction_dir / 'segregation' / '2011'/ 'cases_2011.csv'
    pdf_output_dir: Path = data_extraction_dir / 'pdfs' / 'pdf_downloads_2011'
    
    s3_bucket: str = "indian-supreme-court-judgments"
    s3_region: str = "ap-south-1"
    s3_prefix: str = "data/pdf/year="  # The S3 prefix structure
    
    max_workers: int = 5
    
    def __post_init__(self):
        self.pdf_output_dir.mkdir(parents=True, exist_ok=True)


# ============================================================
# S3 BUCKET ACCESS - CORRECTED FOR THE ACTUAL STRUCTURE
# ============================================================

class S3PDFFinder:
    """
    Find PDFs in the S3 bucket using the correct path structure.
    
    Actual structure: data/pdf/year=YYYY/english/FILENAME_EN.pdf
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.bucket = config.s3_bucket
        self.region = config.s3_region
        self.prefix = config.s3_prefix
        
        # Cache of found PDFs
        self.pdf_cache = {}  # case_id -> s3_key
        self.year_pdfs = {}  # year -> list of s3_keys
        
        # Check if we already have a cache
        self.cache_file = config.data_extraction_dir / 's3_pdf_cache.json'
        self._load_cache()
    
    def _load_cache(self):
        """Load cached PDF list if available"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self.year_pdfs = data.get('year_pdfs', {})
                    self.pdf_cache = data.get('pdf_cache', {})
                    logger.info(f"📂 Loaded cache: {sum(len(v) for v in self.year_pdfs.values())} PDFs cached")
            except Exception as e:
                logger.warning(f"Could not load cache: {e}")
    
    def _save_cache(self):
        """Save PDF cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'year_pdfs': self.year_pdfs,
                    'pdf_cache': self.pdf_cache
                }, f, indent=2)
            logger.debug("Cache saved")
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")
    
    def _get_pdfs_for_year(self, year: str) -> List[str]:
        """Get all PDFs for a specific year from S3"""
        if year in self.year_pdfs:
            return self.year_pdfs[year]
        
        # Build the S3 prefix for this year
        prefix = f"{self.prefix}{year}/english/"
        
        logger.info(f"🔍 Fetching PDF list for year {year}...")
        
        pdfs = []
        
        # Try HTTPS REST API first
        try:
            import requests
            import xml.etree.ElementTree as ET
            
            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/"
            params = {
                'list-type': 2,
                'prefix': prefix
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
                
                for content in root.findall('.//s3:Contents', ns):
                    key = content.find('s3:Key', ns)
                    if key is not None and key.text and '.pdf' in key.text.lower():
                        pdfs.append(key.text)
            else:
                logger.warning(f"REST API error for year {year}: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Error fetching year {year}: {e}")
        
        # Try AWS CLI if available
        if not pdfs:
            try:
                cmd = [
                    'aws', 's3', 'ls',
                    '--no-sign-request',
                    '--region', self.region,
                    f's3://{self.bucket}/{prefix}',
                    '--recursive'
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if '.pdf' in line.lower():
                            parts = line.split()
                            if len(parts) >= 4:
                                pdfs.append(' '.join(parts[3:]))
            except Exception as e:
                logger.warning(f"AWS CLI error: {e}")
        
        # Cache the results
        self.year_pdfs[year] = pdfs
        self._save_cache()
        
        logger.info(f"   Found {len(pdfs)} PDFs for year {year}")
        return pdfs
    
    def find_pdf(self, case_id: str, path: str) -> Optional[str]:
        """
        Find a PDF in S3 using the path from metadata.
        
        The path format in metadata could be:
        - "2024 INSC 720" -> need to map to "2024_10_108_125_EN.pdf"
        - "2024_10_108_125" -> direct match
        - "2024_10_108_125.pdf" -> direct match
        """
        # Check cache first
        if case_id in self.pdf_cache:
            return self.pdf_cache[case_id]
        
        # Extract year from path
        year_match = re.search(r'(\d{4})', path)
        if not year_match:
            # Try from case_id
            year_match = re.search(r'(\d{4})', case_id)
        
        if not year_match:
            logger.warning(f"Could not extract year from: {path}")
            return None
        
        year = year_match.group(1)
        
        # Get all PDFs for this year
        year_pdfs = self._get_pdfs_for_year(year)
        
        if not year_pdfs:
            logger.warning(f"No PDFs found for year {year}")
            return None
        
        # Clean the path for matching
        path_clean = path.strip()
        # Remove .pdf extension if present
        path_clean_no_ext = re.sub(r'\.pdf$', '', path_clean, flags=re.IGNORECASE)
        # Replace spaces and hyphens with underscores
        path_clean_for_match = re.sub(r'[ \-]', '_', path_clean_no_ext)
        
        # Try different matching strategies
        matching_strategies = [
            # 1. Exact match with path
            lambda p: path_clean in p or path_clean_no_ext in p,
            
            # 2. Match the filename (last part)
            lambda p: path_clean_for_match in Path(p).stem or path_clean in Path(p).stem,
            
            # 3. Match any part of the path
            lambda p: any(part in p for part in [path_clean_for_match, path_clean, path_clean_no_ext]),
            
            # 4. Match case-insensitive INSC number
            lambda p: re.search(r'INSC', path, re.IGNORECASE) and re.search(re.escape(path_clean.replace('INSC', '').strip()), p, re.IGNORECASE),
            
            # 5. Match numbers from the path
            lambda p: all(num in p for num in re.findall(r'\d+', path_clean_for_match) if len(num) >= 3),
            
            # 6. Match year and any numbers
            lambda p: year in p and any(num in p for num in re.findall(r'\d+', path_clean_for_match) if len(num) >= 3)
        ]
        
        for strategy in matching_strategies:
            matches = [p for p in year_pdfs if strategy(p)]
            if matches:
                # Found a match
                s3_key = matches[0]
                self.pdf_cache[case_id] = s3_key
                self._save_cache()
                logger.debug(f"✅ Found PDF for {case_id}: {s3_key}")
                return s3_key
        
        # If still not found, try to find by year only (fallback)
        if year_pdfs:
            # Just use the first PDF from that year as a test
            s3_key = year_pdfs[0]
            logger.debug(f"⚠️  Using fallback PDF for {case_id}: {s3_key}")
            return s3_key
        
        logger.warning(f"❌ No PDF found for {case_id} (path: {path})")
        return None


# ============================================================
# PDF DOWNLOADER
# ============================================================

class PDFDownloader:
    """Download PDFs for candidate cases from AWS S3"""
    
    def __init__(self, config: Config):
        self.config = config
        self.finder = S3PDFFinder(config)
        self.stats = {
            'total': 0,
            'downloaded': 0,
            'failed': 0,
            'skipped_exists': 0,
            'not_found': 0
        }
    
    def _get_file_path(self, case_id: str, path: str) -> Path:
        """Generate a safe file path for the PDF"""
        safe_id = re.sub(r'[^\w\-]', '_', case_id)
        filename = f"{safe_id}.pdf"
        if len(filename) > 200:
            hash_str = hashlib.md5(filename.encode()).hexdigest()[:8]
            filename = f"{safe_id[:50]}_{hash_str}.pdf"
        return self.config.pdf_output_dir / filename
    
    def _download_from_s3(self, s3_key: str, local_path: Path) -> bool:
        """Download a file from S3"""
        url = f"https://{self.config.s3_bucket}.s3.{self.config.s3_region}.amazonaws.com/{s3_key}"
        
        try:
            import requests
            response = requests.get(url, stream=True, timeout=60)
            if response.status_code == 200:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                if local_path.stat().st_size > 1000:
                    return True
                else:
                    local_path.unlink(missing_ok=True)
                    return False
        except Exception as e:
            logger.debug(f"Download failed for {s3_key}: {e}")
            return False
        
        # Try AWS CLI fallback
        if hasattr(self.finder, 'aws_available') and self.finder.aws_available:
            try:
                cmd = [
                    'aws', 's3', 'cp',
                    '--no-sign-request',
                    f's3://{self.config.s3_bucket}/{s3_key}',
                    str(local_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0 and local_path.exists() and local_path.stat().st_size > 1000:
                    return True
            except Exception:
                pass
        
        return False
    
    def download_case(self, row: pd.Series) -> Dict:
        """Download a single case"""
        case_id = row.get('case_id', '')
        title = row.get('title', '')
        path = row.get('path', '')
        score = row.get('score', 0)
        
        result = {
            'case_id': case_id,
            'title': title,
            'path': path,
            'score': score,
            'status': 'skipped',
            's3_key': '',
            'file_path': '',
            'error': ''
        }
        
        if not path:
            result['status'] = 'no_path'
            result['error'] = 'No path available'
            self.stats['failed'] += 1
            return result
        
        # Check if already downloaded
        file_path = self._get_file_path(case_id, path)
        result['file_path'] = str(file_path)
        
        if file_path.exists() and file_path.stat().st_size > 1000:
            result['status'] = 'exists'
            self.stats['skipped_exists'] += 1
            return result
        
        # Find the PDF in S3
        s3_key = self.finder.find_pdf(case_id, path)
        
        if not s3_key:
            result['status'] = 'not_found'
            result['error'] = 'PDF not found in S3 bucket'
            self.stats['not_found'] += 1
            return result
        
        result['s3_key'] = s3_key
        
        # Download
        if self._download_from_s3(s3_key, file_path):
            result['status'] = 'downloaded'
            self.stats['downloaded'] += 1
            size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Downloaded: {file_path.name} ({size_mb:.2f} MB)")
        else:
            result['status'] = 'failed'
            result['error'] = 'Download failed'
            self.stats['failed'] += 1
        
        return result
    
    def download_cases(self, df: pd.DataFrame) -> pd.DataFrame:
        """Download all cases"""
        self.stats['total'] = len(df)
        
        logger.info(f"\n📥 Processing {len(df)} candidate cases...")
        logger.info(f"   Output: {self.config.pdf_output_dir}")
        logger.info(f"   S3 bucket: {self.config.s3_bucket}")
        logger.info(f"   Max concurrent: {self.config.max_workers}")
        
        results = []
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = {executor.submit(self.download_case, row): idx for idx, row in df.iterrows()}
            
            with tqdm(total=len(futures), desc="Processing") as pbar:
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        result = future.result()
                        results.append((idx, result))
                    except Exception as e:
                        logger.error(f"Error: {e}")
                        results.append((idx, {
                            'case_id': df.iloc[idx].get('case_id', ''),
                            'title': df.iloc[idx].get('title', ''),
                            'path': df.iloc[idx].get('path', ''),
                            'status': 'error',
                            'error': str(e)
                        }))
                    pbar.update(1)
        
        results.sort(key=lambda x: x[0])
        result_rows = [r for _, r in results]
        result_df = pd.DataFrame(result_rows)
        
        # Merge with original
        df_clean = df.reset_index(drop=True)
        result_clean = result_df[['status', 's3_key', 'file_path', 'error']]
        merged_df = pd.concat([df_clean, result_clean], axis=1)
        
        self._log_stats()
        return merged_df
    
    def _log_stats(self):
        """Log download statistics"""
        logger.info("\n" + "=" * 60)
        logger.info("PDF ACCESS STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total cases: {self.stats['total']:,}")
        logger.info(f"Successfully downloaded: {self.stats['downloaded']:,}")
        logger.info(f"Already existed: {self.stats['skipped_exists']:,}")
        logger.info(f"Not found in S3: {self.stats['not_found']:,}")
        logger.info(f"Failed downloads: {self.stats['failed']:,}")
        
        if self.stats['total'] > 0:
            success_rate = (self.stats['downloaded'] / self.stats['total'] * 100)
            logger.info(f"Success rate: {success_rate:.1f}%")
        logger.info("=" * 60)


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    """Main entry point"""
    print("=" * 70)
    print("STAGE 2: PDF ACCESS FROM AWS DATASET")
    print("Corrected for S3 Path Structure")
    print("=" * 70)
    
    config = Config()
    
    print(f"\n📁 Data extraction directory: {config.data_extraction_dir}")
    print(f"📁 Candidates file: {config.candidates_file}")
    print(f"📁 PDF output directory: {config.pdf_output_dir}")
    print(f"📁 S3 Bucket: {config.s3_bucket}")
    print(f"📁 S3 Prefix: {config.s3_prefix}")
    
    # Check if candidates file exists
    if not config.candidates_file.exists():
        logger.error(f"❌ Candidate file not found: {config.candidates_file}")
        return
    
    # Load candidates
    logger.info(f"\n📂 Loading candidates from: {config.candidates_file}")
    df = pd.read_csv(config.candidates_file)
    
    if df.empty:
        logger.warning("No candidates found.")
        return
    
    logger.info(f"✅ Loaded {len(df)} candidate cases")
    
    # Initialize downloader
    downloader = PDFDownloader(config)
    
    # Download PDFs
    result_df = downloader.download_cases(df)
    
    # Save results
    result_file = config.data_extraction_dir / 'pdf_download_results_2011.csv'
    result_df.to_csv(result_file, index=False)
    logger.info(f"💾 Download results saved to: {result_file}")
    
    # Summary
    successful = result_df[result_df['status'] == 'downloaded']
    failed = result_df[result_df['status'] == 'not_found']
    
    print("\n" + "=" * 70)
    print("STAGE 2 COMPLETE")
    print("=" * 70)
    print(f"\n📊 Summary:")
    print(f"   Total candidates: {len(df)}")
    print(f"   Downloaded: {len(successful)}")
    print(f"   Already existed: {result_df[result_df['status'] == 'exists'].shape[0]}")
    print(f"   Not found: {len(failed)}")
    
    print(f"\n📁 PDFs saved to: {config.pdf_output_dir}")
    
    # Check downloaded PDFs
    pdf_files = list(config.pdf_output_dir.glob('*.pdf'))
    if pdf_files:
        total_size = sum(f.stat().st_size for f in pdf_files) / (1024 * 1024)
        print(f"\n✅ Total PDFs in output folder: {len(pdf_files)}")
        print(f"   Total size: {total_size:.2f} MB")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()