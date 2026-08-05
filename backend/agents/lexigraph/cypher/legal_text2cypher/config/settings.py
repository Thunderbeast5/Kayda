"""
Configuration settings for the Legal Text-to-Cypher pipeline.

Reads from environment variables with sensible defaults.
Supports .env files via python-dotenv.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# .env auto-discovery: walk up from this file to find the nearest .env
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_ENV_CANDIDATES = [
    *_THIS_DIR.parents,
    Path("."),
    Path("backend"),
]
_ENV_PATH: Optional[Path] = None
for p in _ENV_CANDIDATES:
    candidate = p / ".env"
    if candidate.exists() and candidate.is_file():
        _ENV_PATH = candidate
        break


class Settings(BaseSettings):
    """Central configuration for the Text-to-Cypher pipeline."""

    # ── Neo4j ──────────────────────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j connection URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="password", description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")

    # ── LLM (Groq / OpenAI-compatible) ────────────────────────────────────
    groq_api_key: Optional[str] = Field(default=None, description="Groq API key")
    groq_model: str = Field(default="llama-3.1-8b-instant", description="Default Groq model (fast instant model)")
    # groq_model: str = Field(default="llama-3.3-70b-versatile", description="Default Groq model")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="OpenAI-compatible base URL for Groq",
    )
    groq_temperature: float = Field(default=0.0, description="LLM temperature for determinism")
    groq_max_retries: int = Field(default=3, description="Max retries for LLM calls")

    # ── Fallback LLM ──────────────────────────────────────────────────────
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key (optional fallback)")
    fallback_model: str = Field(default="llama-3.1-8b-instant", description="Fallback model name")

    # ── Cache ──────────────────────────────────────────────────────────────
    cache_enabled: bool = Field(default=True, description="Enable query / entity cache")
    cache_max_size: int = Field(default=1024, description="Max LRU cache entries")
    cache_ttl_seconds: int = Field(default=3600, description="Cache entry TTL in seconds")
    redis_url: Optional[str] = Field(default=None, description="Optional Redis URL for distributed cache")

    # ── Pipeline ──────────────────────────────────────────────────────────
    max_cypher_retries: int = Field(default=3, description="Max retries for Cypher execution")
    cypher_timeout_seconds: int = Field(default=30, description="Neo4j query timeout")
    fulltext_score_threshold: float = Field(default=0.5, description="Min fulltext score for entity linking")
    fulltext_max_results: int = Field(default=10, description="Max fulltext results per query")
    graph_expansion_depth: int = Field(default=2, description="Max hops for graph expansion")

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        description="Logging format string",
    )

    model_config = {
        "env_file": str(_ENV_PATH) if _ENV_PATH else ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Force re-read (useful in tests)."""
    global _settings
    _settings = None
