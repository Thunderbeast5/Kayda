"""
relationship_registry.py
========================
Defines allowed relationship types, legacy relationship aliases, and domain-range constraint pairs.
"""

from typing import Dict, Set, Tuple


VALID_RELATIONSHIPS: Set[str] = {
    "REPLACES",
    "REPLACED_BY",
    "HAS_INGREDIENT",
    "REQUIRES_EVIDENCE",
    "RELIED_ON_EVIDENCE",
    "INTERPRETS",
    "INTERPRETED_IN",
    "BINDING_UNDER",
    "PROTECTED_BY",
    "ESTABLISHES",
    "APPLIES_TO",
    "RELATES_TO",
    "BELONGS_TO"
}

RELATIONSHIP_ALIAS_MAP: Dict[str, str] = {
    "APPLIES_SECTION": "INTERPRETS",
    "CITES_CASE": "INTERPRETS",
    "SUPPORTED_BY": "REQUIRES_EVIDENCE",
    "GOVERNED_BY": "PROTECTED_BY",
    "DERIVES_FROM": "PROTECTED_BY",
    "UPHOLDS": "PROTECTED_BY",
    "PROHIBITED_BY": "PROTECTED_BY"
}

# Domain (Source Label) -> Relationship -> Range (Target Label)
ALLOWED_SEMANTIC_PAIRS: Set[Tuple[str, str, str]] = {
    ("LawSection", "REPLACES", "LawSection"),
    ("LawSection", "REPLACED_BY", "LawSection"),
    ("LawSection", "HAS_INGREDIENT", "Ingredient"),
    ("Ingredient", "REQUIRES_EVIDENCE", "EvidenceType"),
    ("LawSection", "REQUIRES_EVIDENCE", "EvidenceType"),
    ("Case", "RELIED_ON_EVIDENCE", "EvidenceType"),
    ("Case", "INTERPRETS", "LawSection"),
    ("LawSection", "INTERPRETED_IN", "Case"),
    ("Case", "BINDING_UNDER", "ConstitutionArticle"),
    ("LawSection", "PROTECTED_BY", "ConstitutionArticle"),
    ("Case", "ESTABLISHES", "LegalPrinciple"),
    ("LegalPrinciple", "APPLIES_TO", "LawSection"),
    ("ConstitutionArticle", "RELATES_TO", "LegalPrinciple"),
    ("LawSection", "BELONGS_TO", "Community"),
    ("Case", "BELONGS_TO", "Community")
}


class RelationshipRegistry:
    """Validates relationship names, aliases, and directional domain-range constraint pairs."""

    def __init__(self):
        self.valid_relationships = VALID_RELATIONSHIPS
        self.alias_map = RELATIONSHIP_ALIAS_MAP
        self.allowed_pairs = ALLOWED_SEMANTIC_PAIRS

    def resolve_relationship(self, rel_type: str) -> str:
        """Maps legacy relationship aliases to standard canonical relationship types."""
        return self.alias_map.get(rel_type, rel_type)

    def validate_relationship(self, source_label: str, rel_type: str, target_label: str) -> tuple[bool, str]:
        """Validates that a directed edge conforms to schema domain-range rules."""
        canonical_rel = self.resolve_relationship(rel_type)
        if canonical_rel not in self.valid_relationships:
            return False, f"Unknown relationship type '{rel_type}'."

        pair = (source_label, canonical_rel, target_label)
        if pair not in self.allowed_pairs:
            return False, f"Invalid semantic edge: ({source_label})-[:{canonical_rel}]->({target_label})."

        return True, "Valid"
