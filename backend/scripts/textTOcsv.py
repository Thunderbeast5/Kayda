#!/usr/bin/env python3
"""
Combine extracted TXT files into a single CSV for Stage 4.
This script reads all .txt files in the extracted_text folder
and creates extracted_texts_combined.csv
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

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

class Config:
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / 'data'
    text_dir = data_dir / 'extracted_text'
    output_file = data_dir / 'extracted_texts_combined.csv'


def combine_texts():
    """Combine all TXT files into a single CSV"""
    config = Config()
    
    print("=" * 70)
    print("COMBINING EXTRACTED TEXTS")
    print("=" * 70)
    
    print(f"\n📁 Text directory: {config.text_dir}")
    print(f"📁 Output file: {config.output_file}")
    
    # Check if text directory exists
    if not config.text_dir.exists():
        logger.error(f"❌ Text directory not found: {config.text_dir}")
        print("\n⚠️  No extracted text files found.")
        print("   Please run Stage 3 OCR extraction first.")
        return None
    
    # Get all TXT files
    txt_files = list(config.text_dir.glob('*.txt'))
    
    if not txt_files:
        logger.error(f"❌ No TXT files found in: {config.text_dir}")
        return None
    
    logger.info(f"✅ Found {len(txt_files)} TXT files")
    
    # Read all files
    data = []
    
    for txt_path in tqdm(txt_files, desc="Reading files"):
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Extract case_id from filename
            case_id = txt_path.stem
            
            # Try to extract year
            year_match = re.search(r'(\d{4})', case_id)
            year = year_match.group(1) if year_match else None
            
            data.append({
                'case_id': case_id,
                'year': year,
                'text': text,
                'word_count': len(text.split()),
                'char_count': len(text),
                'file_path': str(txt_path),
                'file_size': txt_path.stat().st_size
            })
            
        except Exception as e:
            logger.error(f"Error reading {txt_path.name}: {e}")
    
    if not data:
        logger.error("No data could be read from files")
        return None
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Sort by case_id
    df = df.sort_values('case_id').reset_index(drop=True)
    
    # Save to CSV
    df.to_csv(config.output_file, index=False)
    logger.info(f"💾 Saved to: {config.output_file}")
    
    # Print statistics
    print("\n" + "=" * 70)
    print("COMBINED DATA STATISTICS")
    print("=" * 70)
    print(f"Total documents: {len(df)}")
    print(f"Total words: {df['word_count'].sum():,}")
    print(f"Average words: {df['word_count'].mean():,.0f}")
    print(f"Min words: {df['word_count'].min():,}")
    print(f"Max words: {df['word_count'].max():,}")
    print(f"Total size: {df['file_size'].sum() / (1024*1024):.2f} MB")
    
    # Year distribution
    if 'year' in df.columns:
        year_counts = df['year'].value_counts().sort_index()
        print("\n📅 Year Distribution:")
        for year, count in year_counts.items():
            print(f"   {year}: {count} documents")
    
    # Show sample
    print("\n📋 Sample files:")
    for _, row in df.head(5).iterrows():
        print(f"   {row['case_id']}: {row['word_count']:,} words")
    
    print("=" * 70)
    
    return df


def main():
    """Main execution"""
    df = combine_texts()
    
    if df is not None:
        print("\n✅ Ready for Stage 4 classification!")
        print("   Run: python stage4_gemini_classify.py")
    else:
        print("\n❌ Failed to combine texts.")
        print("   Please check that the extracted_text folder contains .txt files.")

if __name__ == "__main__":
    main()