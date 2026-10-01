"""
SQLite Ingestion Script for Bail Cases (No PostgreSQL Required)
Loads normalized data into SQLite database
"""

import json
import sqlite3
from typing import Dict, List, Any
from pathlib import Path


class BailDatabaseIngestorSQLite:
    """Ingests bail case data into SQLite"""
    
    def __init__(self, db_path: str = "bail_precedents.db"):
        """Initialize with SQLite database path"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            print(f"✓ Connected to SQLite database: {self.db_path}")
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
    
    def create_schema(self):
        """Create SQLite schema"""
        try:
            # Cases table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bail_cases (
                    case_id TEXT PRIMARY KEY,
                    case_name TEXT NOT NULL,
                    petitioner TEXT,
                    respondent TEXT,
                    court TEXT,
                    decided_on TEXT,
                    bench_strength INTEGER,
                    procedural_stage TEXT,
                    offence_types TEXT,
                    dispute_nature TEXT,
                    abstract_facts TEXT,
                    disposition TEXT,
                    lower_court_outcome TEXT,
                    normalized_statutes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Propositions table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS bail_propositions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    proposition_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    speaker TEXT,
                    kind TEXT,
                    is_holding INTEGER DEFAULT 0,
                    favors TEXT,
                    conditions TEXT,
                    normalized_statutes TEXT,
                    tags TEXT,
                    binding_level TEXT,
                    authorities TEXT,
                    anchors TEXT,
                    quote TEXT,
                    quote_verified INTEGER DEFAULT 0,
                    favors_verified INTEGER DEFAULT 1,
                    verification_note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (case_id) REFERENCES bail_cases(case_id),
                    UNIQUE(case_id, proposition_id)
                )
            """)
            
            # Create indexes
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_court ON bail_cases(court)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_stage ON bail_cases(procedural_stage)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_decided_on ON bail_cases(decided_on)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_case_id ON bail_propositions(case_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_kind ON bail_propositions(kind)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_favors ON bail_propositions(favors)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_is_holding ON bail_propositions(is_holding)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_binding_level ON bail_propositions(binding_level)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_props_quote_verified ON bail_propositions(quote_verified)")
            
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
            self.cursor.execute("DELETE FROM bail_propositions")
            self.cursor.execute("DELETE FROM bail_cases")
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
            INSERT OR REPLACE INTO bail_cases (
                case_id, case_name, petitioner, respondent, court, decided_on,
                bench_strength, procedural_stage, offence_types, dispute_nature,
                abstract_facts, disposition, lower_court_outcome, normalized_statutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(case.get("offence_types", [])),
                case.get("dispute_nature"),
                case.get("abstract_facts"),
                case.get("disposition"),
                case.get("lower_court_outcome"),
                json.dumps(case.get("normalized_statutes", []))
            )
            for case in cases
        ]
        
        try:
            self.cursor.executemany(insert_query, values)
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
            INSERT OR REPLACE INTO bail_propositions (
                case_id, proposition_id, text, speaker, kind, is_holding,
                favors, conditions, normalized_statutes, tags, binding_level,
                authorities, anchors, quote, quote_verified, favors_verified,
                verification_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        values = [
            (
                prop.get("case_id"),
                prop.get("proposition_id"),
                prop.get("text"),
                prop.get("speaker"),
                prop.get("kind"),
                1 if prop.get("is_holding", False) else 0,
                prop.get("favors"),
                json.dumps(prop.get("conditions", [])),
                json.dumps(prop.get("normalized_statutes", [])),
                json.dumps(prop.get("tags", [])),
                prop.get("binding_level", "persuasive"),
                json.dumps(prop.get("authorities", [])),
                json.dumps(prop.get("anchors", [])),
                prop.get("quote", ""),
                1 if prop.get("quote_verified", False) else 0,
                1 if prop.get("favors_verified", True) else 0,
                prop.get("verification_note", "")
            )
            for prop in propositions
        ]
        
        try:
            self.cursor.executemany(insert_query, values)
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
            self.cursor.execute("SELECT COUNT(*) FROM bail_cases")
            total_cases = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM bail_propositions")
            total_props = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM bail_propositions WHERE is_holding = 1")
            holdings = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM bail_propositions WHERE quote_verified = 1")
            verified = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM bail_propositions WHERE binding_level = 'binding'")
            binding = self.cursor.fetchone()[0]
            
            print(f"\n{'='*60}")
            print("DATABASE STATISTICS")
            print(f"{'='*60}")
            print(f"Total Cases: {total_cases}")
            print(f"Total Propositions: {total_props}")
            print(f"Holdings: {holdings}")
            print(f"Verified Propositions: {verified}")
            print(f"Binding Propositions: {binding}")
            print(f"{'='*60}\n")
        
        except Exception as e:
            print(f"✗ Error fetching stats: {e}")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest bail case data into SQLite")
    parser.add_argument("--data", default="normalized_bail_data.json", help="Normalized data JSON file")
    parser.add_argument("--db", default="bail_precedents.db", help="SQLite database file")
    parser.add_argument("--create-schema", action="store_true", help="Create schema before ingestion")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before ingestion")
    
    args = parser.parse_args()
    
    # Initialize ingestor
    ingestor = BailDatabaseIngestorSQLite(db_path=args.db)
    
    try:
        # Connect
        ingestor.connect()
        
        # Create schema if requested
        if args.create_schema:
            ingestor.create_schema()
        
        # Clear data if requested
        if args.clear:
            ingestor.clear_tables()
        
        # Ingest data
        success = ingestor.ingest_normalized_data(args.data)
        
        if success:
            print("\n✓ Data ingestion completed successfully!")
        else:
            print("\n✗ Data ingestion failed")
    
    finally:
        ingestor.close()


if __name__ == "__main__":
    main()
