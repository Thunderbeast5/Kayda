"""
schema_metadata.py
==================
Manages graph schema versioning and governance metadata in Neo4j.
"""

from typing import Dict, Any
from .schema_constants import SCHEMA_VERSION, MIGRATION_VERSION


class SchemaMetadataManager:
    """Reads and records schema versioning state in Neo4j."""

    def __init__(self, neo4j_service=None):
        self.neo4j_service = neo4j_service

    def record_schema_version(self, ingestion_version: str = "v4.2", graph_build_version: str = "build-108") -> Dict[str, Any]:
        """Writes current schema governance metadata to Neo4j metadata node."""
        query = """
        MERGE (m:SchemaMetadata {id: "SINGLETON_GOVERNANCE_NODE"})
        SET m.schema_version = $schema_version,
            m.migration_version = $migration_version,
            m.ingestion_version = $ingestion_version,
            m.graph_build_version = $graph_build_version,
            m.created_at = coalesce(m.created_at, datetime()),
            m.updated_at = datetime()
        RETURN m.schema_version AS schema_version,
               m.migration_version AS migration_version,
               m.ingestion_version AS ingestion_version,
               m.graph_build_version AS graph_build_version
        """
        params = {
            "schema_version": SCHEMA_VERSION,
            "migration_version": MIGRATION_VERSION,
            "ingestion_version": ingestion_version,
            "graph_build_version": graph_build_version
        }
        if self.neo4j_service:
            rows = self.neo4j_service.run_query(query, params)
            if rows:
                return rows[0]
        return params

    def get_schema_version(self) -> Dict[str, Any]:
        """Queries current schema governance metadata from Neo4j."""
        if not self.neo4j_service:
            return {"schema_version": SCHEMA_VERSION, "migration_version": MIGRATION_VERSION}

        query = """
        MATCH (m:SchemaMetadata {id: "SINGLETON_GOVERNANCE_NODE"})
        RETURN m.schema_version AS schema_version,
               m.migration_version AS migration_version,
               m.ingestion_version AS ingestion_version,
               m.graph_build_version AS graph_build_version,
               toString(m.updated_at) AS updated_at
        """
        rows = self.neo4j_service.run_query(query, {})
        if rows:
            return rows[0]
        return {"schema_version": SCHEMA_VERSION, "migration_version": MIGRATION_VERSION}
