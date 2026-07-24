import os
from typing import Dict, Any, List

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

_neo4j_driver = None


class Neo4jService:
    """
    Neo4jService
    
    Handles Graph Database sessions and raw Cypher queries for Neo4j.
    """

    def __init__(self):
        if not NEO4J_URI:
            raise RuntimeError("NEO4J_URI not set in backend/.env")

    def _get_driver(self):
        global _neo4j_driver
        if _neo4j_driver is None:
            from neo4j import GraphDatabase
            _neo4j_driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        return _neo4j_driver

    def run_query(self, cypher: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Executes a Cypher query on the Neo4j database.
        """
        driver = self._get_driver()
        session = driver.session(database=NEO4J_DATABASE)
        try:
            result = session.run(cypher, params)
            return [dict(record) for record in result]
        finally:
            try:
                session.close()
            except Exception:
                pass
