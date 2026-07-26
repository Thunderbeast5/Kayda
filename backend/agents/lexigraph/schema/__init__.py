"""
LexiGraph Schema Governance Package
===================================
Provides canonical label registries, relationship registries, pre-ingestion validation,
schema version metadata management, and non-destructive Cypher graph migrations.
"""

from .schema_constants import SCHEMA_VERSION, MIGRATION_VERSION, CANONICAL_LABELS
from .schema_registry import SchemaRegistry
from .relationship_registry import RelationshipRegistry
from .schema_validator import SchemaValidationService
from .schema_metadata import SchemaMetadataManager
from .schema_migration import SchemaMigrationEngine

__all__ = [
    "SCHEMA_VERSION",
    "MIGRATION_VERSION",
    "CANONICAL_LABELS",
    "SchemaRegistry",
    "RelationshipRegistry",
    "SchemaValidationService",
    "SchemaMetadataManager",
    "SchemaMigrationEngine"
]
