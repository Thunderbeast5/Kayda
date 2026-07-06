"""
Neo4j Connection Manager
Handles connection to the Neo4j AuraDB cloud instance.
Credentials are loaded from the .env file at the project root.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# Load .env from the project root (one level up from agents/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

URI      = os.getenv("NEO4J_URI",      "neo4j+s://feeeda69.databases.neo4j.io")
USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def get_driver():
    """
    Returns a Neo4j Driver instance using credentials from .env.
    The caller is responsible for closing the driver when done.
    Use as a context manager (with get_driver() as driver:) for automatic cleanup.
    """
    return GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))


def verify_connection() -> bool:
    """
    Opens a driver, calls verify_connectivity(), and closes it.
    Returns True if the connection succeeds, False otherwise.
    """
    try:
        with get_driver() as driver:
            driver.verify_connectivity()
            print(f"[Neo4j] Connected to {URI} (database: {DATABASE})")
            return True
    except AuthError as e:
        print(f"[Neo4j] Authentication failed: {e}")
        return False
    except ServiceUnavailable as e:
        print(f"[Neo4j] Service unavailable: {e}")
        return False
    except Exception as e:
        print(f"[Neo4j] Unexpected error: {e}")
        return False


def execute_query(cypher: str, parameters: dict = None, database: str = None):
    """
    Convenience wrapper around driver.execute_query().

    Args:
        cypher:     Cypher query string. Use $param placeholders — never concatenate values.
        parameters: Dict of parameter values matching the $param placeholders.
        database:   Override the default database from .env.

    Returns:
        (records, summary, keys) tuple — same as driver.execute_query().
    """
    parameters = parameters or {}
    db = database or DATABASE

    with get_driver() as driver:
        records, summary, keys = driver.execute_query(cypher, parameters, database_=db)
    return records, summary, keys


# ── Quick connectivity test ───────────────────────────────────────────────────
if __name__ == "__main__":
    ok = verify_connection()
    if not ok:
        raise SystemExit(1)
