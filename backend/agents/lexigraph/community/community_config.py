import os

# ── NEO4J GRAPH DATA SCIENCE (GDS) LEIDEN COMMUNITY DETECTION CONFIG ─────────

GDS_GRAPH_NAME = os.getenv("GDS_GRAPH_NAME", "legal_knowledge_graph")

# Multi-Signal Relationship Weighting Coefficients:
# Weight = (0.40 * Shared Ingredients) + (0.25 * Shared Precedent) + (0.20 * Graph Relationship) + (0.15 * Semantic Similarity)
WEIGHT_SIGNAL_COEFFICIENTS = {
    "SHARED_INGREDIENTS": 0.40,
    "SHARED_PRECEDENT": 0.25,
    "GRAPH_RELATIONSHIP": 0.20,
    "SEMANTIC_SIMILARITY": 0.15
}

# Base Weights for Explicit Graph Hierarchy Relationships
RELATIONSHIP_WEIGHTS = {
    "MORE_SPECIFIC_THAN": 1.00,
    "OVERRIDES": 0.95,
    "HAS_INGREDIENT": 0.90,
    "REQUIRES_EVIDENCE": 0.85,
    "APPLIES_SECTION": 0.80,
    "CITES_CASE": 0.75,
    "INTERPRETS": 0.70,
    "ESTABLISHES": 0.70,
    "PRESCRIBES": 0.65,
    "HAS_EXCEPTION": 0.60,
    "SUPPORTED_BY": 0.60,
    "BELONGS_TO": 0.50,
    "HAS_KEYWORD": 0.40,
    "PROTECTED_BY": 0.40
}

# Leiden Algorithm Parameters Tuned for Legal Graphs
LEIDEN_GAMMA = float(os.getenv("LEIDEN_GAMMA", "1.25"))       # Resolution for fine-grained sub-communities
LEIDEN_THETA = float(os.getenv("LEIDEN_THETA", "0.01"))       # Modularity randomness parameter
LEIDEN_MAX_LEVELS = int(os.getenv("LEIDEN_MAX_LEVELS", "10")) # Hierarchical depth cap
LEIDEN_TOLERANCE = float(os.getenv("LEIDEN_TOLERANCE", "0.0001"))
INCLUDE_INTERMEDIATE_COMMUNITIES = True                       # Enables Level 1 (Macro), Level 2 (Meso), Level 3 (Micro) hierarchy
WRITE_PROPERTY = "communityId"
INTERMEDIATE_COMMUNITIES_WRITE_PROPERTY = "communityHierarchy"

# Node Labels Projected into GDS In-Memory Graph
PROJECTED_NODE_LABELS = [
    "LawSection",
    "Ingredient",
    "EvidenceType",
    "Case",
    "ConstitutionalArticle",
    "LegalPrinciple",
    "Punishment",
    "Exception",
    "Community"
]

# Relationship Types Projected into GDS In-Memory Graph
PROJECTED_RELATIONSHIP_TYPES = list(RELATIONSHIP_WEIGHTS.keys())

# Automatic Re-Clustering Trigger Thresholds
TRIGGER_NEW_SECTIONS_THRESHOLD = int(os.getenv("TRIGGER_NEW_SECTIONS_THRESHOLD", "100"))
TRIGGER_NEW_CASE_LINKS_THRESHOLD = int(os.getenv("TRIGGER_NEW_CASE_LINKS_THRESHOLD", "500"))

