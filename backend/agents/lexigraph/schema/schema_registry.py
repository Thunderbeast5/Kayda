"""
schema_registry.py
==================
Production Schema Registry enforcing canonical node definitions, aliases, and property rules.
"""

from typing import Dict, Any, List, Set
from .schema_constants import CANONICAL_LABELS, LABEL_ALIAS_MAP, REQUIRED_NODE_PROPERTIES


class SchemaRegistry:
    """Central registry for node labels, properties, and canonical mapping rules."""

    def __init__(self):
        self.canonical_labels: Set[str] = set(CANONICAL_LABELS.keys())
        self.alias_map: Dict[str, str] = LABEL_ALIAS_MAP
        self.required_properties: Dict[str, List[str]] = REQUIRED_NODE_PROPERTIES

    def get_canonical_label(self, label: str) -> str:
        """Resolves any historical or specialized alias to its canonical umbrella label."""
        return self.alias_map.get(label, label)

    def validate_node_schema(self, labels: List[str], properties: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validates node label compliance and mandatory property presence."""
        errors = []
        resolved_labels = [self.get_canonical_label(lbl) for lbl in labels]
        
        # Check if at least one canonical label is present
        has_canonical = any(lbl in self.canonical_labels for lbl in resolved_labels)
        if not has_canonical:
            errors.append(f"Node labels {labels} contain no recognized canonical label.")

        # Check required properties for present canonical labels
        for lbl in resolved_labels:
            if lbl in self.required_properties:
                for req_prop in self.required_properties[lbl]:
                    if req_prop not in properties or properties[req_prop] is None:
                        errors.append(f"Canonical label '{lbl}' missing required property '{req_prop}'.")

        return len(errors) == 0, errors
