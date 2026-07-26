"""
Entity Extractor — Stage 2 of the Text-to-Cypher pipeline.

Uses an LLM to extract structured legal entities from natural-language
queries.  Never generates Cypher.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from ..config.settings import get_settings
from ..schemas.models import ExtractedEntities
from .prompts import ENTITY_SYSTEM_PROMPT, ENTITY_USER_TEMPLATE

logger = logging.getLogger(__name__)


def _get_llm() -> ChatGroq:
    cfg = get_settings()
    return ChatGroq(
        model=cfg.groq_model,
        api_key=cfg.groq_api_key,
        temperature=0.0,
        max_retries=cfg.groq_max_retries,
    )


def _clean_list(lst: object) -> List[str]:
    """Ensure we always have a list of non-empty strings."""
    if not isinstance(lst, list):
        return []
    return [str(x).strip() for x in lst if str(x).strip()]


def _parse_entities_json(raw: str) -> ExtractedEntities:
    """Parse LLM response into ExtractedEntities, with fallback."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse entity JSON: %s", raw[:200])
        return ExtractedEntities()

    return ExtractedEntities(
        crimes=_clean_list(data.get("crimes")),
        ipc_sections=_clean_list(data.get("ipc_sections")),
        bns_sections=_clean_list(data.get("bns_sections")),
        acts=_clean_list(data.get("acts")),
        chapters=_clean_list(data.get("chapters")),
        punishments=_clean_list(data.get("punishments")),
        keywords=_clean_list(data.get("keywords")),
        legal_concepts=_clean_list(data.get("legal_concepts")),
    )


def extract_entities(query: str) -> ExtractedEntities:
    """
    Extract structured legal entities from a natural-language query.

    Parameters
    ----------
    query : str
        The user's question.

    Returns
    -------
    ExtractedEntities
        All entities found in the query.
    """
    logger.info("Extracting entities from: %s", query[:100])

    llm = _get_llm()
    messages = [
        SystemMessage(content=ENTITY_SYSTEM_PROMPT),
        HumanMessage(content=ENTITY_USER_TEMPLATE.format(query=query)),
    ]

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        logger.debug("Entity LLM raw response: %s", raw[:500])
        result = _parse_entities_json(raw)
    except Exception as exc:
        logger.error("Entity extraction failed: %s", exc)
        result = ExtractedEntities()

    total = (
        len(result.crimes) + len(result.ipc_sections) + len(result.bns_sections) +
        len(result.acts) + len(result.keywords) + len(result.legal_concepts)
    )
    logger.info(
        "Extracted %d entities: crimes=%s, ipc=%s, bns=%s, keywords=%s",
        total, result.crimes, result.ipc_sections, result.bns_sections, result.keywords,
    )
    return result
