"""
schema_validator.py
===================
Pre-ingestion validation pipeline enforcing node, property, and relationship rules.
"""

from typing import Dict, Any, List
from .schema_registry import SchemaRegistry
from .relationship_registry import RelationshipRegistry


class SchemaValidationService:
    """Runs pre-ingestion validation on graph write payloads."""

    def __init__(self):
        self.schema_registry = SchemaRegistry()
        self.relationship_registry = RelationshipRegistry()

    def validate_node_payload(self, node_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validates node labels and required properties."""
        labels = node_payload.get("labels", [])
        properties = node_payload.get("properties", {})
        
        is_valid, errors = self.schema_registry.validate_node_schema(labels, properties)
        return {
            "valid": is_valid,
            "errors": errors,
            "canonical_labels": [self.schema_registry.get_canonical_label(l) for l in labels]
        }

    def validate_relationship_payload(self, rel_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validates directed relationship names and domain-range constraint pairs."""
        src_label = self.schema_registry.get_canonical_label(rel_payload.get("source_label", ""))
        tgt_label = self.schema_registry.get_canonical_label(rel_payload.get("target_label", ""))
        rel_type = rel_payload.get("relationship_type", "")

        is_valid, reason = self.relationship_registry.validate_relationship(src_label, rel_type, tgt_label)
        return {
            "valid": is_valid,
            "reason": reason,
            "canonical_relationship": self.relationship_registry.resolve_relationship(rel_type)
        }
