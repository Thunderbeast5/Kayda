import logging
from typing import Dict, Any
from .community_config import GDS_GRAPH_NAME
from .community_queries import CHECK_GRAPH_EXISTS, DROP_GRAPH_PROJECTION, PROJECT_LEGAL_GRAPH

logger = logging.getLogger("CommunityProjection")


class CommunityProjectionManager:
    """
    Manages in-memory GDS Graph Projections for LexiGraph.
    Provides idempotent projection creation, existence verification, and safe cleanup.
    """

    def __init__(self, neo4j_service):
        self.neo4j_service = neo4j_service

    def graph_exists(self, graph_name: str = GDS_GRAPH_NAME) -> bool:
        """Checks if an in-memory projection with graph_name exists in Neo4j GDS."""
        try:
            res = self.neo4j_service.run_query(CHECK_GRAPH_EXISTS, {"graph_name": graph_name})
            return bool(res and res[0].get("exists"))
        except Exception as e:
            logger.warning(f"Error checking GDS graph existence: {e}")
            return False

    def drop_graph(self, graph_name: str = GDS_GRAPH_NAME) -> bool:
        """Drops the specified GDS graph projection if it exists."""
        if self.graph_exists(graph_name):
            try:
                self.neo4j_service.run_query(DROP_GRAPH_PROJECTION, {"graph_name": graph_name})
                logger.info(f"Successfully dropped GDS graph projection '{graph_name}'.")
                return True
            except Exception as e:
                logger.error(f"Failed to drop GDS graph projection '{graph_name}': {e}")
                return False
        return True

    def project_graph(self, graph_name: str = GDS_GRAPH_NAME, force_reproject: bool = True) -> Dict[str, Any]:
        """
        Projects the weighted multi-relational legal graph into GDS in-memory catalog.
        If force_reproject is True, drops any existing projection first.
        """
        if force_reproject:
            self.drop_graph(graph_name)

        if self.graph_exists(graph_name):
            logger.info(f"Using existing GDS graph projection '{graph_name}'.")
            return {"graphName": graph_name, "status": "existing"}

        logger.info(f"Creating GDS graph projection '{graph_name}'...")
        try:
            res = self.neo4j_service.run_query(PROJECT_LEGAL_GRAPH, {"graph_name": graph_name})
            if res:
                stats = res[0]
                logger.info(f"Graph Projection Created: {stats.get('graphName')} | Nodes: {stats.get('nodeCount')} | Relationships: {stats.get('relationshipCount')} in {stats.get('projectMillis')}ms")
                return stats
            return {"graphName": graph_name, "status": "error"}
        except Exception as e:
            logger.error(f"Failed to project GDS graph '{graph_name}': {e}")
            raise RuntimeError(f"GDS Graph Projection failed: {e}")
