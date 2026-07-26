"""
schema_constants.py
===================
Canonical schema constants, version strings, label mappings, and property definitions
for the LexiGraphAgent Knowledge Graph.
"""

SCHEMA_VERSION = "2.1.0"
MIGRATION_VERSION = "2026.07.01"

CANONICAL_LABELS = {
    "LawSection": ["IPCSection", "BNSSection", "BNSSSection", "BSASection"],
    "Case": ["SupremeCourtCase", "HighCourtCase", "DistrictCourtCase", "CourtCase"],
    "ConstitutionArticle": ["ConstitutionalArticle", "Article", "FundamentalRight", "DirectivePrinciple"],
    "Ingredient": ["StatutoryIngredient"],
    "EvidenceType": ["EvidentiaryProof"],
    "LegalPrinciple": ["ConstitutionalPrinciple", "DoctrinalPrinciple"],
    "Community": ["LeidenCluster"]
}

LABEL_ALIAS_MAP = {
    "SupremeCourtCase": "Case",
    "HighCourtCase": "Case",
    "CourtCase": "Case",
    "ConstitutionalArticle": "ConstitutionArticle",
    "Article": "ConstitutionArticle",
    "StatutoryIngredient": "Ingredient",
    "EvidentiaryProof": "EvidenceType"
}

REQUIRED_NODE_PROPERTIES = {
    "LawSection": ["act", "section", "title"],
    "Case": ["case_name", "citation"],
    "ConstitutionArticle": ["article_number", "title"],
    "Ingredient": ["name"],
    "EvidenceType": ["name"],
    "LegalPrinciple": ["name"]
}
