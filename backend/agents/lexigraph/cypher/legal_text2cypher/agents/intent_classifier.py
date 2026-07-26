"""
Intent Classifier — Stage 1 of the Text-to-Cypher pipeline.

Uses an LLM to classify natural language legal queries into
one of the defined LegalIntent categories.  Output is structured JSON.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from ..config.settings import get_settings
from ..schemas.models import IntentResult, LegalIntent
from .prompts import INTENT_SYSTEM_PROMPT, INTENT_USER_TEMPLATE

logger = logging.getLogger(__name__)


def _get_llm() -> ChatGroq:
    """Create a ChatGroq instance configured for intent classification."""
    cfg = get_settings()
    return ChatGroq(
        model=cfg.groq_model,
        api_key=cfg.groq_api_key,
        temperature=0.0,
        max_retries=cfg.groq_max_retries,
    )


def _parse_intent_json(raw: str) -> IntentResult:
    """Parse LLM response into IntentResult, with fallback handling."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse intent JSON, falling back to UNKNOWN: %s", raw[:200])
        return IntentResult(
            intent=LegalIntent.UNKNOWN,
            confidence=0.0,
            reasoning="Failed to parse LLM response",
        )

    # Validate intent value
    intent_str = data.get("intent", "unknown").lower().strip()
    try:
        intent = LegalIntent(intent_str)
    except ValueError:
        logger.warning("Unknown intent '%s', falling back to UNKNOWN", intent_str)
        intent = LegalIntent.UNKNOWN

    # Parse secondary intents
    secondary = []
    for si in data.get("secondary_intents", []):
        try:
            secondary.append(LegalIntent(si.lower().strip()))
        except ValueError:
            pass

    return IntentResult(
        intent=intent,
        secondary_intents=secondary,
        confidence=float(data.get("confidence", 0.0)),
        reasoning=str(data.get("reasoning", "")),
    )


def classify_intent(query: str) -> IntentResult:
    """
    Classify a natural language legal query into a LegalIntent.

    Parameters
    ----------
    query : str
        The user's natural language question.

    Returns
    -------
    IntentResult
        Structured classification result.
    """
    logger.info("Classifying intent for query: %s", query[:100])

    llm = _get_llm()
    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=INTENT_USER_TEMPLATE.format(query=query)),
    ]

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        logger.debug("Intent LLM raw response: %s", raw[:300])
        result = _parse_intent_json(raw)
    except Exception as exc:
        logger.error("Intent classification failed: %s", exc)
        result = IntentResult(
            intent=LegalIntent.UNKNOWN,
            confidence=0.0,
            reasoning=f"LLM error: {exc}",
        )

    logger.info("Intent: %s (confidence=%.2f)", result.intent.value, result.confidence)
    return result
