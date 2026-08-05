"""
run_schema_migration.py
========================
Executes the schema migration pipeline, applying additive canonical labels,
enforcing compound constraints, and updating versioning metadata in Neo4j.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

sys.path.append(str(BASE_DIR))

from agents.lexigraph.services.neo4j_service import Neo4jService
from agents.lexigraph.schema.schema_migration import SchemaMigrationEngine
from agents.lexigraph.schema.schema_metadata import SchemaMetadataManager


def run_migration():
    print("=" * 80)
    print("RUNNING LEXIGRAPH CANONICAL SCHEMA MIGRATION PIPELINE")
    print("=" * 80)

    neo4j_service = Neo4jService()
    migration_engine = SchemaMigrationEngine(neo4j_service)
    metadata_manager = SchemaMetadataManager(neo4j_service)

    print("\n1. Applying Additive Canonical Labeling (Phase 1)...")
    results = migration_engine.run_additive_canonical_labeling()
    print(f"   [OK] Additive Cases Tagged        : {results.get('cases_tagged')}")
    print(f"   [OK] Additive Articles Tagged     : {results.get('articles_tagged')}")
    print(f"   [OK] Additive BNS Sections Tagged : {results.get('bns_sections_tagged')}")
    print(f"   [OK] Additive IPC Sections Tagged : {results.get('ipc_sections_tagged')}")

    print("\n2. Enforcing Compound Graph Constraints (Phase 2)...")
    applied_constraints = migration_engine.enforce_constraints()
    print(f"   [OK] Enforced Constraints: {applied_constraints}")

    print("\n3. Updating Schema Versioning Metadata in Neo4j...")
    meta = metadata_manager.record_schema_version(
        ingestion_version="v4.2",
        graph_build_version="build-108"
    )
    print(f"   [OK] Current Schema Version    : {meta.get('schema_version')}")
    print(f"   [OK] Migration Release Version : {meta.get('migration_version')}")

    print("\n" + "=" * 80)
    print("SCHEMA MIGRATION PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_migration()
