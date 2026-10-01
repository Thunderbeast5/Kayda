"""
Master Pipeline Runner
Orchestrates all phases of the bail precedent system
"""

import os
import sys
from pathlib import Path
import argparse


def run_phase_1(args):
    """Phase 1: Data normalization and tagging"""
    print("\n" + "="*80)
    print("PHASE 1: DATA NORMALIZATION AND TAGGING")
    print("="*80 + "\n")
    
    # Step 1: Tag propositions
    print("Step 1: Tagging propositions with taxonomy...")
    from tagger import PropositionTagger
    tagger = PropositionTagger(taxonomy_path=args.taxonomy, model=args.tagger_model)
    tagger.tag_all_cases(args.input_dir, args.tagged_dir)
    
    # Step 2: Normalize data
    print("\nStep 2: Normalizing data for database...")
    from normalize_data import CaseDataNormalizer
    normalizer = CaseDataNormalizer()
    normalizer.process_all_cases(args.tagged_dir, args.normalized_file)
    
    print("\n✓ Phase 1 complete!")


def run_phase_2(args):
    """Phase 2: Database setup and ingestion"""
    print("\n" + "="*80)
    print("PHASE 2: DATABASE SETUP AND INGESTION")
    print("="*80 + "\n")
    
    from db_ingest import BailDatabaseIngestor
    
    ingestor = BailDatabaseIngestor(connection_string=args.connection)
    
    try:
        ingestor.connect()
        
        if args.create_schema:
            print("Creating database schema...")
            ingestor.create_schema(args.schema_file)
        
        if args.clear_data:
            print("Clearing existing data...")
            ingestor.clear_tables()
        
        print("Ingesting normalized data...")
        success = ingestor.ingest_normalized_data(args.normalized_file)
        
        if success:
            ingestor.show_stats()
            print("\n✓ Phase 2 complete!")
        else:
            print("\n✗ Phase 2 failed!")
            sys.exit(1)
    
    finally:
        ingestor.close()


def run_phase_3_test(args):
    """Phase 3: Test retrieval pipeline"""
    print("\n" + "="*80)
    print("PHASE 3: TESTING RETRIEVAL PIPELINE")
    print("="*80 + "\n")
    
    if not args.test_case:
        print("✗ No test case provided. Use --test-case <file>")
        return
    
    from retrieval_pipeline import RetrievalPipeline
    
    # Read test case
    with open(args.test_case, 'r', encoding='utf-8') as f:
        case_text = f.read()
    
    # Initialize pipeline
    pipeline = RetrievalPipeline(connection_string=args.connection)
    
    try:
        # Test defense side
        print("\nTesting DEFENSE retrieval...")
        defense_result = pipeline.retrieve(
            case_text=case_text,
            side="defense",
            top_k=5,
            include_adverse=True
        )
        
        print(pipeline.format_output(defense_result))
        
        # Test prosecution side
        print("\n\nTesting PROSECUTION retrieval...")
        prosecution_result = pipeline.retrieve(
            case_text=case_text,
            side="prosecution",
            top_k=5,
            include_adverse=True
        )
        
        print(pipeline.format_output(prosecution_result))
        
        print("\n✓ Phase 3 complete!")
    
    finally:
        pipeline.close()


def main():
    parser = argparse.ArgumentParser(
        description="Master pipeline for bail precedent system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete pipeline
  python run_pipeline.py --all --input-dir out --test-case test_case.txt
  
  # Run only Phase 1 (tagging & normalization)
  python run_pipeline.py --phase 1 --input-dir out
  
  # Run only Phase 2 (database setup)
  python run_pipeline.py --phase 2 --create-schema --clear-data
  
  # Run only Phase 3 (test retrieval)
  python run_pipeline.py --phase 3 --test-case test_case.txt
        """
    )
    
    # Phase selection
    parser.add_argument("--all", action="store_true", help="Run all phases")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="Run specific phase")
    
    # Phase 1 arguments
    parser.add_argument("--input-dir", default="out", help="Input directory with case JSON files")
    parser.add_argument("--tagged-dir", default="tagged", help="Output directory for tagged cases")
    parser.add_argument("--normalized-file", default="normalized_bail_data.json", help="Output normalized data file")
    parser.add_argument("--taxonomy", default="taxonomy.json", help="Taxonomy JSON file")
    parser.add_argument("--tagger-model", default="gpt-4o-mini", help="Model for tagging")
    
    # Phase 2 arguments
    parser.add_argument("--connection", help="PostgreSQL connection string")
    parser.add_argument("--schema-file", default="schema.sql", help="Schema SQL file")
    parser.add_argument("--create-schema", action="store_true", help="Create database schema")
    parser.add_argument("--clear-data", action="store_true", help="Clear existing data")
    
    # Phase 3 arguments
    parser.add_argument("--test-case", help="Test case file for Phase 3")
    
    args = parser.parse_args()
    
    # Determine which phases to run
    phases_to_run = []
    if args.all:
        phases_to_run = [1, 2, 3]
    elif args.phase:
        phases_to_run = [args.phase]
    else:
        parser.print_help()
        sys.exit(1)
    
    # Run phases
    try:
        if 1 in phases_to_run:
            run_phase_1(args)
        
        if 2 in phases_to_run:
            run_phase_2(args)
        
        if 3 in phases_to_run:
            run_phase_3_test(args)
        
        print("\n" + "="*80)
        print("ALL REQUESTED PHASES COMPLETED SUCCESSFULLY!")
        print("="*80 + "\n")
    
    except KeyboardInterrupt:
        print("\n\n✗ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Pipeline failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
