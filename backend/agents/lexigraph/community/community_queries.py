"""
Cypher Queries for Neo4j Graph Data Science (GDS) v2.x Leiden Community Detection.
Includes Graph Projection, Memory Estimation, Stats Mode, Write Mode, Seeded Mode, and Cleanup.
"""

# Check if GDS library is installed & available
CHECK_GDS_AVAILABLE = """
CALL gds.version() YIELD version RETURN version;
"""

# Check if Graph Projection Exists
CHECK_GRAPH_EXISTS = """
CALL gds.graph.exists($graph_name) YIELD exists RETURN exists;
"""

# Drop Existing Graph Projection
DROP_GRAPH_PROJECTION = """
CALL gds.graph.drop($graph_name, false) YIELD graphName;
"""

# Native GDS Graph Projection for Multi-Relational Legal Graph
PROJECT_LEGAL_GRAPH = """
CALL gds.graph.project(
    $graph_name,
    ['LawSection', 'Ingredient', 'EvidenceType', 'Case', 'ConstitutionalArticle', 'LegalPrinciple', 'Punishment', 'Exception', 'Community'],
    ['MORE_SPECIFIC_THAN', 'OVERRIDES', 'HAS_INGREDIENT', 'REQUIRES_EVIDENCE', 'APPLIES_SECTION', 'CITES_CASE', 'INTERPRETS', 'ESTABLISHES', 'SUPPORTED_BY', 'BELONGS_TO', 'HAS_KEYWORD']
)
YIELD graphName, nodeCount, relationshipCount, projectMillis;
"""

# Memory Estimation Mode
ESTIMATE_LEIDEN_MEMORY = """
CALL gds.leiden.write.estimate(
    $graph_name,
    {
        writeProperty: "communityId",
        includeIntermediateCommunities: true,
        relationshipWeightProperty: "weight",
        gamma: $gamma,
        theta: $theta,
        maxLevels: $max_levels,
        tolerance: $tolerance
    }
)
YIELD nodeCount, relationshipCount, bytesMin, bytesMax, requiredMemory;
"""

# Stats Mode (Development & Debugging)
STATS_LEIDEN = """
CALL gds.leiden.stats(
    $graph_name,
    {
        relationshipWeightProperty: "weight",
        gamma: $gamma,
        theta: $theta,
        maxLevels: $max_levels,
        tolerance: $tolerance,
        includeIntermediateCommunities: true
    }
)
YIELD communityCount, modularity, modularities, ranCadence, computeMillis;
"""

# Write Mode (Production Execution with Intermediate Communities)
RUN_LEIDEN_WRITE = """
CALL gds.leiden.write(
    $graph_name,
    {
        writeProperty: "communityId",
        intermediateCommunitiesWriteProperty: "communityHierarchy",
        relationshipWeightProperty: "weight",
        gamma: $gamma,
        theta: $theta,
        maxLevels: $max_levels,
        tolerance: $tolerance,
        includeIntermediateCommunities: true
    }
)
YIELD nodePropertiesWritten, communityCount, modularity, modularities, computeMillis, postProcessingMillis;
"""

# Seeded Write Mode (Stable Incremental Re-Clustering)
RUN_LEIDEN_SEEDED_WRITE = """
CALL gds.leiden.write(
    $graph_name,
    {
        writeProperty: "communityId",
        intermediateCommunitiesWriteProperty: "communityHierarchy",
        relationshipWeightProperty: "weight",
        seedProperty: "communityId",
        gamma: $gamma,
        theta: $theta,
        maxLevels: $max_levels,
        tolerance: $tolerance,
        includeIntermediateCommunities: true
    }
)
YIELD nodePropertiesWritten, communityCount, modularity, computeMillis;
"""

# Post-Processing Cypher: Unpack Hierarchy into Explicit Community Level Properties & Name Labels
UNPACK_COMMUNITY_HIERARCHY = """
MATCH (n) WHERE n.communityHierarchy IS NOT NULL AND size(n.communityHierarchy) > 0
SET n.communityLevel1 = n.communityHierarchy[0],
    n.communityLevel2 = CASE WHEN size(n.communityHierarchy) > 1 THEN n.communityHierarchy[1] ELSE n.communityHierarchy[0] END,
    n.communityLevel3 = CASE WHEN size(n.communityHierarchy) > 2 THEN n.communityHierarchy[2] ELSE n.communityHierarchy[size(n.communityHierarchy)-1] END,
    n.communityId = n.communityHierarchy[size(n.communityHierarchy)-1];
"""

# Cypher for Leiden-Driven Community Retrieval
RETRIEVE_LEIDEN_COMMUNITY = """
MATCH (c:LawSection) WHERE c.communityId = $community_id OR c.communityLevel1 = $community_id OR c.communityLevel2 = $community_id
OPTIONAL MATCH (c)-[:HAS_INGREDIENT]->(i:Ingredient)
OPTIONAL MATCH (c)-[:SUPPORTED_BY|HAS_INGREDIENT]->()-[:REQUIRES_EVIDENCE]->(e:EvidenceType)
OPTIONAL MATCH (cs:Case)-[:APPLIES_SECTION|INTERPRETS]->(c)
RETURN DISTINCT c.section AS section, c.act AS act, c.title AS title, c.category AS category,
       collect(DISTINCT i.name) AS ingredients,
       collect(DISTINCT e.name) AS evidence_types,
       collect(DISTINCT cs.title) AS precedent_cases
LIMIT 25;
"""
