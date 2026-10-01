"""
PostgreSQL Ingestion Script for Bail Cases
Loads normalized data into PostgreSQL database
"""

import json
import psycopg2
from psycopg2.extras import execute_values
from typing import Dict, List, Any
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class BailDatabaseIngestor:
    """Ingests bail case data into PostgreSQL"""
    
    def __init__(self, connection_string: str = None):
        """
        Initialize with connection string
        Format: postgresql://user:password@host:port/database
        """
        self.connection_string = connection_string or os.getenv(
            "POSTGRES_URL",
            "postgresql://localhost:5432/bail_precedents"
        )
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor()
            print("✓ Connected to PostgreSQL database")
        except Exception as e:
            print(f"✗ Error connecting to database: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("✓ Database connection closed")
    
    def create_schema(self, schema_file: str = "schema.sql"):
        """Execute schema creation SQL"""
        schema_path = Path(schema_file)
        
        if not schema_path.exists():
            print(f"✗ Schema file not found: {schema_file}")
            return False
        
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            self.cursor.execute(schema_sql)
            self.conn.commit()
            print("✓ Database schema created successfully")
            return True
        
        except Exception as e:
            print(f"✗ Error creating schema: {e}")
            self.conn.rollback()
            return False
    
    def clear_tables(self):
        """Clear all data from tables"""
        try:
            self.cursor.execute("TRUNCATE TABLE bail_cases CASCADE;")
            self.conn.commit()
            print("✓ Tables cleared")
        except Exception as e:
            print(f"✗ Error clearing tables: {e}")
            self.conn.rollback()
    
    def insert_cases(self, cases: List[Dict[str, Any]]):
        """Insert case records"""
        if not cases:
            print("No cases to insert")
            return 0
        
        insert_query = """
        INSERT INTO bail_cases (
            case_id, case_name, petitioner, respondent, court, decided_on,
            bench_strength, procedural_stage, offence_types, dispute_nature,
            abstract_facts, disposition, lower_court_outcome, normalized_statutes
        ) VALUES %s
        ON CONFLICT (case_id) DO UPDATE SET
            case_name = EXCLUDED.case_name,
            updated_at = CURRENT_TIMESTAMP
        """
        
        values = [
            (
                case.get("case_id"),
                case.get("case_name"),
                case.get("petitioner"),
                case.get("respondent"),
                case.get("court"),
                case.get("decided_on"),
                case.get("bench_strength"),
                case.get("procedural_stage"),
                case.get("offence_types", []),
                case.get("dispute_nature"),
                case.get("abstract_facts"),
                case.get("disposition"),
                case.get("lower_court_outcome"),
                case.get("normalized_statutes", [])
            )
            for case in cases
        ]
        
        try:
            execute_values(self.cursor, insert_query, values)
            self.conn.commit()
            print(f"✓ Inserted {len(cases)} cases")
            return len(cases)
        except Exception as e:
            print(f"✗ Error inserting cases: {e}")
            self.conn.rollback()
            return 0
    
    def insert_propositions(self, propositions: List[Dict[str, Any]]):
        """Insert proposition records"""
        if not propositions:
            print("No propositions to insert")
            return 0
        
        insert_query = """
        INSERT INTO bail_propositions (
            case_id, proposition_id, text, speaker, kind, is_holding,
            favors, conditions, normalized_statutes, tags, binding_level,
            authorities, anchors, quote, quote_verified, favors_verified,
            verification_note
        ) VALUES %s
        ON CONFLICT (case_id, proposition_id) DO UPDATE SET
            text = EXCLUDED.text,
            tags = EXCLUDED.tags
        """
        
        values = [
            (
                prop.get("case_id"),
                prop.get("proposition_id"),
                prop.get("text"),
                prop.get("speaker"),
                prop.get("kind"),
                prop.get("is_holding", False),
                prop.get("favors"),
                prop.get("conditions", []),
                prop.get("normalized_statutes", []),
                prop.get("tags", []),
                prop.get("binding_level", "persuasive"),
                json.dumps(prop.get("authorities", [])),  # Store as JSONB
                prop.get("anchors", []),
                prop.get("quote", ""),
                prop.get("quote_verified", False),
                prop.get("favors_verified", True),
                prop.get("verification_note", "")
            )
            for prop in propositions
        ]
        
        try:
            execute_values(self.cursor, insert_query, values)
            self.conn.commit()
            print(f"✓ Inserted {len(propositions)} propositions")
            return len(propositions)
        except Exception as e:
            print(f"✗ Error inserting propositions: {e}")
            self.conn.rollback()
            return 0
    
    def ingest_normalized_data(self, data_file: str):
        """Ingest normalized JSON data into database"""
        data_path = Path(data_file)
        
        if not data_path.exists():
            print(f"✗ Data file not found: {data_file}")
            return False
        
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cases = data.get("cases", [])
            propositions = data.get("propositions", [])
            
            print(f"\nIngesting data:")
            print(f"  - {len(cases)} cases")
            print(f"  - {len(propositions)} propositions")
            
            # Insert cases first (foreign key constraint)
            cases_inserted = self.insert_cases(cases)
            
            # Then insert propositions
            props_inserted = self.insert_propositions(propositions)
            
            # Show stats
            self.show_stats()
            
            return cases_inserted > 0 and props_inserted > 0
        
        except Exception as e:
            print(f"✗ Error ingesting data: {e}")
            return False
    
    def show_stats(self):
        """Show database statistics"""
        try:
            self.cursor.execute("SELECT * FROM database_stats")
            stats = self.cursor.fetchone()
            
            if stats:
                print(f"\n{'='*60}")
                print("DATABASE STATISTICS")
                print(f"{'='*60}")
                print(f"Total Cases: {stats[0]}")
                print(f"Total Propositions: {stats[1]}")
                print(f"Holdings: {stats[2]}")
                print(f"Verified Propositions: {stats[3]}")
                print(f"Binding Propositions: {stats[4]}")
                print(f"Unique Tags: {stats[5]}")
                print(f"Unique Statutes: {stats[6]}")
                print(f"{'='*60}\n")
        
        except Exception as e:
            print(f"✗ Error fetching stats: {e}")
    
    def test_search(self):
        """Test the search function"""
        print("\n" + "="*60)
        print("TESTING SEARCH FUNCTION")
        print("="*60)
        
        # Test search
        test_query = """
        SELECT * FROM search_propositions(
            ARRAY['CrPC-1973:438'],
            ARRAY['anticipatory_vs_regular', 'economic_offence_gravity'],
            NULL,
            'accused',
            1970,
            5
        );
        """
        
        try:
            self.cursor.execute(test_query)
            results = self.cursor.fetchall()
            
            print(f"Found {len(results)} results\n")
            
            for i, row in enumerate(results, 1):
                print(f"Result {i}:")
                print(f"  Case: {row[2]}")  # case_name
                print(f"  Court: {row[3]}")  # court
                print(f"  Date: {row[4]}")   # decided_on
                print(f"  Relevance Score: {row[11]:.2f}")  # relevance_score
                print(f"  Tags: {row[8]}")   # tags
                print(f"  Text: {row[6][:150]}...")  # text (truncated)
                print()
        
        except Exception as e:
            print(f"✗ Error testing search: {e}")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest bail case data into PostgreSQL")
    parser.add_argument("--data", default="normalized_bail_data.json", help="Normalized data JSON file")
    parser.add_argument("--schema", default="schema.sql", help="Schema SQL file")
    parser.add_argument("--connection", help="PostgreSQL connection string")
    parser.add_argument("--create-schema", action="store_true", help="Create schema before ingestion")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before ingestion")
    parser.add_argument("--test", action="store_true", help="Run test search after ingestion")
    
    args = parser.parse_args()
    
    # Initialize ingestor
    ingestor = BailDatabaseIngestor(connection_string=args.connection)
    
    try:
        # Connect
        ingestor.connect()
        
        # Create schema if requested
        if args.create_schema:
            ingestor.create_schema(args.schema)
        
        # Clear data if requested
        if args.clear:
            ingestor.clear_tables()
        
        # Ingest data
        success = ingestor.ingest_normalized_data(args.data)
        
        if success:
            print("\n✓ Data ingestion completed successfully!")
            
            # Test search if requested
            if args.test:
                ingestor.test_search()
        else:
            print("\n✗ Data ingestion failed")
    
    finally:
        ingestor.close()


if __name__ == "__main__":
    main()
