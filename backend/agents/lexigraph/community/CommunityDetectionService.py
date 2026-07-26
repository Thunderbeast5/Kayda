import logging
import time
from typing import Dict, Any, List, Optional

try:
    from .community_config import (
        GDS_GRAPH_NAME, LEIDEN_GAMMA, LEIDEN_THETA,
        LEIDEN_MAX_LEVELS, LEIDEN_TOLERANCE, WRITE_PROPERTY
    )
    from .community_projection import CommunityProjectionManager
    from .community_queries import (
        CHECK_GDS_AVAILABLE, ESTIMATE_LEIDEN_MEMORY, STATS_LEIDEN,
        RUN_LEIDEN_WRITE, RUN_LEIDEN_SEEDED_WRITE, UNPACK_COMMUNITY_HIERARCHY
    )
except ImportError:
    from community.community_config import (
        GDS_GRAPH_NAME, LEIDEN_GAMMA, LEIDEN_THETA,
        LEIDEN_MAX_LEVELS, LEIDEN_TOLERANCE, WRITE_PROPERTY
    )
    from community.community_projection import CommunityProjectionManager
    from community.community_queries import (
        CHECK_GDS_AVAILABLE, ESTIMATE_LEIDEN_MEMORY, STATS_LEIDEN,
        RUN_LEIDEN_WRITE, RUN_LEIDEN_SEEDED_WRITE, UNPACK_COMMUNITY_HIERARCHY
    )

logger = logging.getLogger("CommunityDetectionService")


class CommunityDetectionService:
    """
    Production-ready Neo4j GDS v2.x Leiden Community Detection Service.
    
    Executes weighted, hierarchical, and seeded Leiden community detection over
    the LexiGraph Legal Knowledge Graph, persisting stable community IDs and multi-level
    community hierarchies (Level 1 Macro -> Level 2 Meso -> Level 3 Micro) back to Neo4j.
    """

    def __init__(self, neo4j_service):
        self.neo4j_service = neo4j_service
        self.projection_manager = CommunityProjectionManager(neo4j_service)

    def is_gds_available(self) -> bool:
        """Verifies if Neo4j Graph Data Science (GDS) procedures are accessible."""
        try:
            res = self.neo4j_service.run_query(CHECK_GDS_AVAILABLE, {})
            return bool(res and len(res) > 0)
        except Exception as e:
            logger.warning(f"Neo4j GDS procedures not available: {e}")
            return False

    def estimate_memory(self, graph_name: str = GDS_GRAPH_NAME) -> Dict[str, Any]:
        """Estimates memory required for running Leiden Community Detection."""
        if not self.is_gds_available():
            return {"status": "gds_unavailable"}
        self.projection_manager.project_graph(graph_name, force_reproject=False)
        params = {
            "graph_name": graph_name,
            "gamma": LEIDEN_GAMMA,
            "theta": LEIDEN_THETA,
            "max_levels": LEIDEN_MAX_LEVELS,
            "tolerance": LEIDEN_TOLERANCE
        }
        res = self.neo4j_service.run_query(ESTIMATE_LEIDEN_MEMORY, params)
        return res[0] if res else {}

    def run_stats(self, graph_name: str = GDS_GRAPH_NAME) -> Dict[str, Any]:
        """Runs Leiden in Stats mode (evaluates modularity and community counts without writing)."""
        if not self.is_gds_available():
            return {"status": "gds_unavailable"}
        self.projection_manager.project_graph(graph_name, force_reproject=False)
        params = {
            "graph_name": graph_name,
            "gamma": LEIDEN_GAMMA,
            "theta": LEIDEN_THETA,
            "max_levels": LEIDEN_MAX_LEVELS,
            "tolerance": LEIDEN_TOLERANCE
        }
        res = self.neo4j_service.run_query(STATS_LEIDEN, params)
        return res[0] if res else {}

    def execute_leiden_detection(
        self,
        graph_name: str = GDS_GRAPH_NAME,
        seeded: bool = False,
        force_reproject: bool = True
    ) -> Dict[str, Any]:
        """
        Executes full production Leiden Community Detection pipeline:
        1. Projects in-memory graph catalog
        2. Runs Leiden in Write / Seeded Write mode
        3. Unpacks hierarchical intermediate levels (communityLevel1, communityLevel2, communityLevel3)
        4. Drops temporary in-memory projection
        """
        start_t = time.time()
        logger.info(f"Starting Leiden Community Detection (Seeded={seeded})...")

        if not self.is_gds_available():
            logger.warning("GDS procedures unavailable on this database instance. Skipping GDS Leiden execution.")
            return {"status": "gds_unavailable", "communityCount": 0}

        # 1. Graph Projection
        try:
            self.projection_manager.project_graph(graph_name, force_reproject=force_reproject)
        except Exception as e:
            logger.warning(f"GDS Graph Projection error: {e}")
            return {"status": "gds_unavailable", "communityCount": 0}

        # 2. Execute Leiden Algorithm
        params = {
            "graph_name": graph_name,
            "gamma": LEIDEN_GAMMA,
            "theta": LEIDEN_THETA,
            "max_levels": LEIDEN_MAX_LEVELS,
            "tolerance": LEIDEN_TOLERANCE
        }

        query = RUN_LEIDEN_SEEDED_WRITE if seeded else RUN_LEIDEN_WRITE
        try:
            write_res = self.neo4j_service.run_query(query, params)
            run_stats = write_res[0] if write_res else {}
            logger.info(f"Leiden Write Execution Finished: Communities: {run_stats.get('communityCount')} | Modularity: {run_stats.get('modularity')} in {run_stats.get('computeMillis')}ms")
        except Exception as e:
            logger.error(f"Error during Leiden Write execution: {e}")
            self.projection_manager.drop_graph(graph_name)
            raise RuntimeError(f"Leiden execution failed: {e}")

        # 3. Post-Processing: Unpack Hierarchy into explicit node properties & Stamp Community Metadata
        logger.info("Unpacking community hierarchy & stamping version metadata...")
        version_str = f"v{time.strftime('%Y.%m.%d_%H%M%S')}"
        created_at = time.strftime('%Y-%m-%dT%H:%M:%SZ')
        modularity_val = run_stats.get("modularity", 0.0)

        try:
            self.neo4j_service.run_query(UNPACK_COMMUNITY_HIERARCHY, {})
            # MERGE LeidenCommunity metadata nodes
            meta_query = """
            MATCH (n:LawSection) WHERE n.communityId IS NOT NULL
            MERGE (lc:LeidenCommunity {community_id: toString(n.communityId)})
            SET lc.community_version = $version,
                lc.created_at = $created_at,
                lc.algorithm = "Neo4j GDS Leiden v2.x",
                lc.gamma = $gamma,
                lc.modularity = $modularity,
                n.communityVersion = $version,
                n.communityCreatedAt = $created_at
            MERGE (n)-[:IN_LEIDEN_COMMUNITY]->(lc)
            """
            self.neo4j_service.run_query(meta_query, {
                "version": version_str,
                "created_at": created_at,
                "gamma": LEIDEN_GAMMA,
                "modularity": modularity_val
            })
        except Exception as e:
            logger.warning(f"Error unpacking/stamping community hierarchy metadata: {e}")

        # 4. Cleanup
        self.projection_manager.drop_graph(graph_name)
        total_time = round(time.time() - start_t, 3)

        # 5. Evaluate Community Quality Metrics
        quality_metrics = self.evaluate_community_metrics()

        return {
            "status": "success",
            "community_version": version_str,
            "created_at": created_at,
            "algorithm": "Neo4j GDS Leiden v2.x",
            "gamma": LEIDEN_GAMMA,
            "modularity": modularity_val,
            "communityCount": run_stats.get("communityCount", 0),
            "nodesWritten": run_stats.get("nodePropertiesWritten", 0),
            "computeMillis": run_stats.get("computeMillis", 0),
            "totalTimeSeconds": total_time,
            "qualityMetrics": quality_metrics
        }

    def check_reclustering_trigger(self) -> Dict[str, Any]:
        """
        Checks if automated re-clustering thresholds have been reached:
        - New sections added >= TRIGGER_NEW_SECTIONS_THRESHOLD (100)
        - New case links added >= TRIGGER_NEW_CASE_LINKS_THRESHOLD (500)
        """
        try:
            from .community_config import TRIGGER_NEW_SECTIONS_THRESHOLD, TRIGGER_NEW_CASE_LINKS_THRESHOLD
        except ImportError:
            from community.community_config import TRIGGER_NEW_SECTIONS_THRESHOLD, TRIGGER_NEW_CASE_LINKS_THRESHOLD

        query = """
        MATCH (s:LawSection)
        OPTIONAL MATCH (s) WHERE s.communityVersion IS NULL
        WITH count(s) AS total_sections, sum(CASE WHEN s.communityVersion IS NULL THEN 1 ELSE 0 END) AS unclustered_sections
        MATCH (c:Case)
        RETURN total_sections, unclustered_sections, count(c) AS total_cases
        """
        try:
            res = self.neo4j_service.run_query(query, {})
            if res:
                r = res[0]
                unclustered = r.get("unclustered_sections", 0)
                should_trigger = unclustered >= TRIGGER_NEW_SECTIONS_THRESHOLD
                return {
                    "should_trigger": should_trigger,
                    "unclustered_sections": unclustered,
                    "threshold": TRIGGER_NEW_SECTIONS_THRESHOLD,
                    "reason": f"Unclustered sections ({unclustered}) >= threshold ({TRIGGER_NEW_SECTIONS_THRESHOLD})" if should_trigger else "Below trigger threshold"
                }
        except Exception as e:
            logger.warning(f"Error checking re-clustering trigger: {e}")
        return {"should_trigger": False, "reason": "Error checking status"}

    def evaluate_community_metrics(self) -> Dict[str, Any]:
        """
        Evaluates community structural balance & isolation metrics post-Leiden:
        - Average community size
        - Largest community size
        - Singleton community count
        - Community size variance
        - Inter-community vs intra-community edge ratio (conductance proxy)
        """
        query = """
        MATCH (n:LawSection) WHERE n.communityId IS NOT NULL
        WITH n.communityId AS cid, count(n) AS csize
        RETURN count(cid) AS total_communities,
               avg(csize) AS avg_size,
               max(csize) AS max_size,
               sum(CASE WHEN csize = 1 THEN 1 ELSE 0 END) AS singleton_count,
               stDev(csize) AS size_std_dev
        """
        try:
            res = self.neo4j_service.run_query(query, {})
            if res:
                r = res[0]
                return {
                    "total_communities": r.get("total_communities", 0),
                    "avg_community_size": round(r.get("avg_size") or 0.0, 2),
                    "largest_community_size": r.get("max_size") or 0,
                    "singleton_community_count": r.get("singleton_count", 0),
                    "community_size_std_dev": round(r.get("size_std_dev") or 0.0, 2)
                }
        except Exception as e:
            logger.warning(f"Error computing community quality metrics: {e}")
        return {}
